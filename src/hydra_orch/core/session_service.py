"""T14 sessions, scoped thread trees, idempotent messages and replay cursors."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from typing import Literal, Optional

from hydra_orch.core.checkpointer import ExecutionStore, IdempotencyConflictError, OptimisticLockError
from hydra_orch.core.identifier import new_id
from hydra_orch.model import ContractViolation, RunEvent

SessionState = Literal["created", "running", "waiting", "completed", "failed", "cancelled"]
TERMINAL = {"completed", "failed", "cancelled"}
TRANSITIONS = {
    "created": {"running", "cancelled"},
    "running": {"waiting", "completed", "failed", "cancelled"},
    "waiting": {"running", "completed", "failed", "cancelled"},
    "completed": set(), "failed": set(), "cancelled": set(),
}


@dataclass
class EventCursor:
    """Reference client cursor for ordered SSE delivery; concurrent dedup is atomic."""
    run_id: str
    last_seq: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def accept(self, event: RunEvent) -> bool:
        async with self._lock:
            if event.run_id != self.run_id:
                raise ContractViolation("session_scope_mismatch", "Event belongs to a different run")
            if event.seq <= self.last_seq:
                return False
            self.last_seq = event.seq
            return True


class SessionService:
    def __init__(self, store: ExecutionStore):
        self.store = store

    async def _run(self, db, run_id):
        row = await (await db.execute("SELECT id FROM runs WHERE id=?", (run_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Run does not exist")

    async def _session(self, db, run_id, session_id):
        row = await (await db.execute("SELECT * FROM sessions WHERE id=?", (session_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Session does not exist")
        if row["run_id"] != run_id:
            raise ContractViolation("session_scope_mismatch", "Session belongs to another run")
        return row

    async def _thread(self, db, run_id, session_id, thread_id):
        row = await (await db.execute("SELECT * FROM threads WHERE id=?", (thread_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Thread does not exist")
        await self._session(db, run_id, row["session_id"])
        if session_id is not None and row["session_id"] != session_id:
            raise ContractViolation("thread_scope_mismatch", "Thread belongs to another session")
        return row

    async def create_session(self, run_id: str, *, origin_ref: Optional[str] = None, agent_ref: Optional[str] = None):
        await self.store.initialize()
        session_id = new_id()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._run(db, run_id)
                await db.execute("INSERT INTO sessions(id,run_id,origin_ref,agent_ref) VALUES (?,?,?,?)",
                    (session_id, run_id, origin_ref, agent_ref))
                await self.store._insert_event_in_tx(db, run_id=run_id, event_type="session.created", session_id=session_id,
                    payload={"state": "created"})
            return dict(await self._session(db, run_id, session_id))

    async def list_sessions(self, run_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._run(db, run_id)
            return [dict(r) for r in await (await db.execute("SELECT * FROM sessions WHERE run_id=? ORDER BY id", (run_id,))).fetchall()]

    async def get_session(self, run_id: str, session_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            return dict(await self._session(db, run_id, session_id))

    async def create_thread(self, run_id: str, session_id: str, *, parent_thread_id: Optional[str] = None,
                            agent_ref: Optional[str] = None):
        await self.store.initialize()
        thread_id = new_id()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                session = await self._session(db, run_id, session_id)
                if session["state"] in TERMINAL:
                    raise ContractViolation("session_state_conflict", "Session is closed")
                if parent_thread_id:
                    parent = await self._thread(db, run_id, session_id, parent_thread_id)
                    if parent["state"] in TERMINAL:
                        raise ContractViolation("thread_state_conflict", "Parent thread is closed")
                await db.execute("INSERT INTO threads(id,session_id,parent_thread_id,agent_ref) VALUES (?,?,?,?)",
                    (thread_id, session_id, parent_thread_id, agent_ref))
                await self.store._insert_event_in_tx(db, run_id=run_id, event_type="thread.created",
                    session_id=session_id, thread_id=thread_id, payload={"parent_thread_id": parent_thread_id, "state": "created"})
            return dict(await self._thread(db, run_id, session_id, thread_id))

    async def list_threads(self, run_id: str, session_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._session(db, run_id, session_id)
            return [dict(r) for r in await (await db.execute("SELECT * FROM threads WHERE session_id=? ORDER BY id", (session_id,))).fetchall()]

    @staticmethod
    def _transition(current: str, target: str, expected: str):
        if current != expected:
            raise OptimisticLockError("Session/thread state changed")
        if target not in TRANSITIONS[current]:
            raise ContractViolation("invalid_transition", "Illegal session/thread state transition")

    async def transition_session(self, run_id: str, session_id: str, target: SessionState, *, expected_state: SessionState):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                session = await self._session(db, run_id, session_id)
                self._transition(session["state"], target, expected_state)
                children = await (await db.execute("SELECT * FROM threads WHERE session_id=? AND state NOT IN ('completed','failed','cancelled')", (session_id,))).fetchall()
                if target == "completed" and children:
                    raise ContractViolation("session_state_conflict", "Session still has active threads")
                if target in {"cancelled", "failed"}:
                    for thread in children:
                        child_target = "cancelled" if thread["state"] == "created" else target
                        await db.execute("UPDATE threads SET state=? WHERE id=?", (child_target, thread["id"]))
                        await self.store._insert_event_in_tx(db, run_id=run_id, event_type="thread.state_changed",
                            session_id=session_id, thread_id=thread["id"], payload={"from": thread["state"], "to": child_target})
                await db.execute("UPDATE sessions SET state=?,closed_at=CASE WHEN ? IN ('completed','failed','cancelled') THEN datetime('now') ELSE NULL END WHERE id=?",
                    (target, target, session_id))
                await self.store._insert_event_in_tx(db, run_id=run_id, event_type="session.state_changed",
                    session_id=session_id, payload={"from": session["state"], "to": target})
            return dict(await self._session(db, run_id, session_id))

    async def transition_thread(self, run_id: str, session_id: str, thread_id: str, target: SessionState, *, expected_state: SessionState):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                session = await self._session(db, run_id, session_id)
                thread = await self._thread(db, run_id, session_id, thread_id)
                self._transition(thread["state"], target, expected_state)
                if session["state"] in TERMINAL or target == "running" and session["state"] != "running":
                    raise ContractViolation("session_state_conflict", "Session must be running for an active thread")
                children = await (await db.execute("""WITH RECURSIVE subtree(id) AS (
                    SELECT id FROM threads WHERE parent_thread_id=?
                    UNION ALL SELECT t.id FROM threads t JOIN subtree s ON t.parent_thread_id=s.id)
                    SELECT * FROM threads WHERE id IN (SELECT id FROM subtree) AND state NOT IN ('completed','failed','cancelled')""", (thread_id,))).fetchall()
                if target == "completed" and children:
                    raise ContractViolation("thread_state_conflict", "Thread still has active descendants")
                affected = [thread, *(children if target in {"failed", "cancelled"} else [])]
                for item in affected:
                    child_target = "cancelled" if item["state"] == "created" and target in {"failed", "cancelled"} else target
                    await db.execute("UPDATE threads SET state=? WHERE id=?", (child_target, item["id"]))
                    await self.store._insert_event_in_tx(db, run_id=run_id, event_type="thread.state_changed",
                        session_id=session_id, thread_id=item["id"], payload={"from": item["state"], "to": child_target})
            return dict(await self._thread(db, run_id, session_id, thread_id))

    async def append_message(self, run_id: str, session_id: str, thread_id: str, content: str, *,
                             idempotency_key: str, expected_last_seq: int):
        if not isinstance(content, str) or not content.strip() or len(content) > 100_000 or not 16 <= len(idempotency_key) <= 64:
            raise ContractViolation("message_invalid", "Bounded message content and idempotency key are required")
        request_hash = self.store.compute_request_hash({"thread_id": thread_id, "content": content, "expected_last_seq": expected_last_seq})
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                session = await self._session(db, run_id, session_id)
                thread = await self._thread(db, run_id, session_id, thread_id)
                scope = f"session:{session_id}"
                previous = await (await db.execute("SELECT request_hash,response_json FROM commands WHERE scope=? AND idempotency_key=?", (scope, idempotency_key))).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise IdempotencyConflictError("Message idempotency key has a different payload")
                    return json.loads(previous["response_json"])
                if session["state"] != "running" or thread["state"] != "running":
                    raise ContractViolation("thread_state_conflict", "Messages require a running session and thread")
                if thread["last_seq"] != expected_last_seq:
                    raise OptimisticLockError("Thread message cursor changed")
                event = await self.store._insert_event_in_tx(db, run_id=run_id, event_type="thread.message",
                    session_id=session_id, thread_id=thread_id, payload={"content": content})
                await db.execute("UPDATE threads SET last_seq=? WHERE id=?", (event.seq, thread_id))
                response = {"run_id": run_id, "session_id": session_id, "thread_id": thread_id, "seq": event.seq}
                await self.store._record_command_in_tx(db, scope=scope, idempotency_key=idempotency_key, request_hash=request_hash,
                    run_id=run_id, response_payload=response)
                return response

    async def replay(self, run_id: str, *, after_seq: int = 0, session_id: Optional[str] = None,
                     thread_id: Optional[str] = None, limit: int = 1000):
        if after_seq < 0 or not 1 <= limit <= 1000:
            raise ContractViolation("invalid_cursor", "Invalid replay cursor or page size")
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._run(db, run_id)
            if session_id:
                await self._session(db, run_id, session_id)
            if thread_id:
                await self._thread(db, run_id, session_id, thread_id)
            oldest = (await (await db.execute("SELECT MIN(seq) FROM events WHERE run_id=?", (run_id,))).fetchone())[0]
            if after_seq and oldest is not None and after_seq < oldest - 1:
                raise ContractViolation("cursor_expired", "Requested run event prefix is no longer retained")
        return await self.store.get_events(run_id, after_seq=after_seq, limit=limit,
            session_id=session_id, thread_id=thread_id)
