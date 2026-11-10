"""T26 durable human intervention at execution boundaries, never a fake process pause."""

from datetime import datetime, timedelta, timezone
import json
from typing import Literal, Optional

from pydantic import Field

from hydra_orch.core.checkpointer import ExecutionStore, IdempotencyConflictError, OptimisticLockError
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import (
    ContractViolation, ExecutionModel, Identifier, NonEmpty, RunStatus, TaskStatus,
    UtcTimestamp, transition_status,
)

HitlKind = Literal["needs_context", "needs_approval"]


class HitlRequest(ExecutionModel):
    request_id: Identifier
    run_id: Identifier
    task_id: Optional[Identifier] = None
    kind: HitlKind
    question: NonEmpty
    state: Literal["pending", "answered", "denied", "expired", "cancelled"] = "pending"
    revision: int = Field(default=1, ge=1, strict=True)
    created_at: UtcTimestamp
    deadline: UtcTimestamp
    response: Optional[str] = None
    actor: Optional[str] = None
    resolved_at: Optional[UtcTimestamp] = None


class HITLService:
    def __init__(self, store: ExecutionStore):
        self.store = store

    async def _find(self, db, run_id, request_id):
        row = await (await db.execute("SELECT * FROM commands WHERE scope='hitl' AND json_extract(response_json,'$.request_id')=?", (request_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Human intervention request does not exist")
        if row["run_id"] != run_id:
            raise ContractViolation("authorization_denied", "Human intervention request belongs to another run")
        return row, HitlRequest.model_validate_json(row["response_json"])

    async def _run(self, db, run_id):
        row = await (await db.execute("SELECT * FROM runs WHERE id=?", (run_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Run does not exist")
        return row

    async def _run_state(self, db, run_id, target, event, payload):
        row = await self._run(db, run_id)
        transition_status(RunStatus(row["status"]), target)
        await db.execute("UPDATE runs SET status=?,revision=revision+1,updated_at=datetime('now') WHERE id=?", (target.value, run_id))
        await self.store._insert_event_in_tx(db, run_id=run_id, event_type=event, payload=payload)

    async def request(self, run_id: str, kind: HitlKind, question: str, *, idempotency_key: str,
                      timeout_seconds: int = 300, task_id: Optional[str] = None):
        if (kind not in {"needs_context", "needs_approval"} or not question.strip() or len(question)>100_000
                or not 16<=len(idempotency_key)<=64 or not 1<=timeout_seconds<=86400):
            raise ContractViolation("hitl_invalid", "Invalid bounded intervention request")
        request_hash = self.store.compute_request_hash({"run_id":run_id,"task_id":task_id,"kind":kind,
            "question":question,"timeout_seconds":timeout_seconds})
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                run = await self._run(db, run_id)
                previous = await (await db.execute("SELECT * FROM commands WHERE scope='hitl' AND idempotency_key=?", (idempotency_key,))).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise IdempotencyConflictError("Intervention key has a different payload")
                    return HitlRequest.model_validate_json(previous["response_json"])
                if run["status"] not in {"queued","running"}:
                    raise ContractViolation("hitl_conflict", "Run must be queued or running at an intervention boundary")
                busy = await (await db.execute("""SELECT 1 FROM tasks WHERE run_id=? AND status='running'
                    UNION ALL SELECT 1 FROM attempts a JOIN tasks t ON t.id=a.task_id
                    WHERE t.run_id=? AND a.process_status IN ('queued','running') LIMIT 1""", (run_id,run_id))).fetchone()
                if busy:
                    raise ContractViolation("hitl_busy", "Running attempts must stop and preserve work before requesting intervention")
                unfinished = await (await db.execute("SELECT 1 FROM tasks WHERE run_id=? AND status NOT IN ('ready_for_review','accepted') LIMIT 1", (run_id,))).fetchone()
                if not unfinished:
                    raise ContractViolation("hitl_conflict", "Completed task results use the explicit review workflow")
                await self.store._assert_no_pending_hitl_in_tx(db, run_id)
                if task_id:
                    task = await (await db.execute("SELECT * FROM tasks WHERE id=?", (task_id,))).fetchone()
                    if task is None or task["run_id"]!=run_id:
                        raise ContractViolation("authorization_denied", "Task does not belong to this run")
                    if task["status"] in {"ready_for_review","accepted"}:
                        raise ContractViolation("hitl_conflict", "Completed task results use review rather than intervention")
                    if task["status"] == "pending":
                        transition_status(TaskStatus.PENDING,TaskStatus.BLOCKED)
                        await db.execute("UPDATE tasks SET status='blocked',revision=revision+1,updated_at=datetime('now') WHERE id=?", (task_id,))
                now = datetime.now(timezone.utc)
                request = HitlRequest(request_id=new_id(),run_id=run_id,task_id=task_id,kind=kind,
                    question=redact_text(question),created_at=now,deadline=now+timedelta(seconds=timeout_seconds))
                await self.store._record_command_in_tx(db,scope="hitl",idempotency_key=idempotency_key,
                    request_hash=request_hash,run_id=run_id,response_payload=request.model_dump(mode="json"),status="pending")
                if run["status"] == "queued":
                    await self._run_state(db,run_id,RunStatus.RUNNING,"run.started",{"reason":"coordinator_intervention"})
                await self._run_state(db,run_id,RunStatus.WAITING,"run.waiting",
                    {"reason":"hitl","kind":kind,"request_id":request.request_id,"deadline":request.deadline.isoformat()})
                await self.store._insert_event_in_tx(db,run_id=run_id,event_type="hitl.requested",task_id=task_id,
                    payload=request.model_dump(mode="json"))
                return request

    async def _finish(self, db, row, request, state, *, now, response=None, actor=None):
        run = await self._run(db,request.run_id)
        if run["status"] in {"succeeded","failed","cancelled"}:
            state="cancelled"
        elif state=="answered" and run["status"]!="waiting":
            raise ContractViolation("hitl_conflict","Run is no longer waiting for intervention")
        updated=HitlRequest.model_validate({**request.model_dump(mode="json"),"state":state,
            "revision":request.revision+1,"response":redact_text(response) if response is not None else None,
            "actor":redact_text(actor) if actor is not None else None,"resolved_at":now})
        await db.execute("UPDATE commands SET response_json=?,status=?,updated_at=datetime('now') WHERE id=?",
            (updated.model_dump_json(),"completed" if state=="answered" else "failed",row["id"]))
        if state!="cancelled":
            if state=="answered":
                await self._run_state(db,request.run_id,RunStatus.RUNNING,"run.resumed",{"reason":"hitl_answered","request_id":request.request_id})
            else:
                reason="hitl_timeout" if state=="expired" else "hitl_denied"
                if request.task_id:
                    task=await (await db.execute("SELECT status FROM tasks WHERE id=?",(request.task_id,))).fetchone()
                    if task and task[0] in {"pending","blocked","needs_context"}:
                        transition_status(TaskStatus(task[0]),TaskStatus.FAILED)
                        await db.execute("UPDATE tasks SET status='failed',revision=revision+1 WHERE id=?",(request.task_id,))
                        await self.store._insert_event_in_tx(db,run_id=request.run_id,event_type="task.failed",task_id=request.task_id,payload={"reason":reason})
                await self._run_state(db,request.run_id,RunStatus.FAILED,"run.finished",{"reason":reason,"request_id":request.request_id})
        await self.store._insert_event_in_tx(db,run_id=request.run_id,event_type="hitl.resolved",task_id=request.task_id,
            payload=updated.model_dump(mode="json"))
        return updated

    async def expire_due(self, *, run_id: Optional[str]=None, now: Optional[datetime]=None):
        await self.store.initialize()
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ContractViolation("hitl_invalid","Deadline reconciliation requires an aware clock")
        changed=[]
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                rows=await (await db.execute("SELECT * FROM commands WHERE scope='hitl' AND status='pending' AND (? IS NULL OR run_id=?)",(run_id,run_id))).fetchall()
                for row in rows:
                    request=HitlRequest.model_validate_json(row["response_json"])
                    run=await self._run(db,request.run_id)
                    if request.deadline<=now or run["status"] in {"succeeded","failed","cancelled"}:
                        changed.append(await self._finish(db,row,request,"expired",now=now,actor="scheduler"))
        return tuple(changed)

    async def get_request(self, run_id: str, request_id: str):
        await self.expire_due(run_id=run_id)
        async with self.store._connect() as db:
            return (await self._find(db,run_id,request_id))[1]

    async def list_requests(self, run_id: str):
        await self.expire_due(run_id=run_id)
        async with self.store._connect() as db:
            await self._run(db,run_id)
            rows=await (await db.execute("SELECT response_json FROM commands WHERE scope='hitl' AND run_id=? ORDER BY id",(run_id,))).fetchall()
            return tuple(HitlRequest.model_validate_json(row[0]) for row in rows)

    async def respond(self, run_id: str, request_id: str, response: str, *, actor: str,
                      expected_revision: int, idempotency_key: str, approved: bool=True):
        if not actor.strip() or not response.strip() or len(response)>100_000 or not 16<=len(idempotency_key)<=64:
            raise ContractViolation("hitl_invalid","Bounded operator response and idempotency key are required")
        await self.expire_due(run_id=run_id)
        request_hash=self.store.compute_request_hash({"run_id":run_id,"request_id":request_id,"response":response,
            "actor":actor,"approved":approved,"expected_revision":expected_revision})
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row,request=await self._find(db,run_id,request_id)
                scope=f"hitl-response:{request_id}"
                previous=await (await db.execute("SELECT request_hash,response_json FROM commands WHERE scope=? AND idempotency_key=?",(scope,idempotency_key))).fetchone()
                if previous:
                    if previous["request_hash"]!=request_hash:
                        raise IdempotencyConflictError("Response key has a different payload")
                    return HitlRequest.model_validate_json(previous["response_json"])
                if request.revision!=expected_revision:
                    raise OptimisticLockError("Intervention revision changed")
                if request.state!="pending":
                    raise ContractViolation("hitl_conflict","Intervention is no longer pending")
                # Recheck the deadline under the writer lock; expire_due ran before it.
                now=datetime.now(timezone.utc)
                if request.deadline<=now:
                    raise ContractViolation("hitl_conflict","Intervention deadline expired")
                updated=await self._finish(db,row,request,"answered" if approved else "denied",now=now,response=response,actor=actor)
                await self.store._record_command_in_tx(db,scope=scope,idempotency_key=idempotency_key,
                    request_hash=request_hash,run_id=run_id,response_payload=updated.model_dump(mode="json"))
                return updated

    async def assert_dispatchable(self, run_id: str):
        await self.expire_due(run_id=run_id)
        async with self.store._connect() as db:
            await self.store._assert_no_pending_hitl_in_tx(db,run_id)

    async def context_for_task(self, run_id: str, task_id: str):
        requests=await self.list_requests(run_id)
        return [{"request_id":r.request_id,"kind":r.kind,"response":r.response} for r in requests
            if r.state=="answered" and r.task_id in {None,task_id}]
