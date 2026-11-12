"""T27 assisted merge conflict resolution and Wave 0 Contract Amendment protocol (RT28)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple, Type, TypeVar, Union
import uuid

from pydantic import Field

from hydra_orch.bridge.worker_runner import cancel_process_tree, filter_worker_env
from hydra_orch.core.checkpointer import (
    ExecutionStore,
    IdempotencyConflictError,
    OptimisticLockError,
    StorageIntegrityError,
)
from hydra_orch.core.git_workspace import (
    GitWorkspaceError,
    GitWorkspaceService,
    ThreeWayInspection,
    WorkspaceRecord,
)
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.core.run_service import CheckRunner
from hydra_orch.model import (
    Artifact,
    CheckResult,
    CheckSpec,
    ContractViolation,
    ExecutionModel,
    FailureDetail,
    GitSha,
    Identifier,
    IntegrationStatus,
    NonEmpty,
    RelativePath,
    RunSpec,
    TaskSpec,
    TaskStatus,
    transition_status,
)

logger = logging.getLogger(__name__)

ConflictStatus = Literal["open", "auto_repair", "manual", "discarded"]
ResolutionOption = Literal["auto_repair", "manual", "discarded"]
RESOLUTION_OPTIONS: tuple[ResolutionOption, ...] = ("auto_repair", "manual", "discarded")

_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_CONFLICT_TRANSITIONS: dict[str, set[str]] = {
    "open": {"open", "auto_repair", "manual", "discarded"},
    "auto_repair": {"open", "auto_repair"},
    "manual": {"manual", "discarded"},
    "discarded": set(),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RE.sub("_", value.strip())
    return cleaned.strip("._-") or "item"


def _short_token(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _normalize_rel_posix(path_str: str) -> str:
    normalized = path_str.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


_ModelT = TypeVar("_ModelT", bound="ExecutionModel")


def _parse_command_model(model_cls: Type[_ModelT], raw_json: str) -> _ModelT:
    data = json.loads(raw_json)
    filtered = {k: v for k, v in data.items() if k in model_cls.model_fields}
    return model_cls.model_validate(filtered)


class ConflictedFileDetail(ExecutionModel):
    """Three-way snapshot and conflict hunks for a single conflicted file."""

    path: str
    base_content: Optional[str] = None
    ours_content: Optional[str] = None
    theirs_content: Optional[str] = None
    merged_preview: str = ""
    hunks: tuple[str, ...] = ()


class ConflictReport(ExecutionModel):
    """Canonical 3-way conflict report persisted in conflict_reports."""

    conflict_id: Identifier
    integration_id: Identifier
    run_id: Identifier
    base_sha: GitSha
    ours_sha: GitSha
    theirs_sha: GitSha
    conflicted_files: tuple[str, ...] = Field(min_length=1)
    file_details: tuple[ConflictedFileDetail, ...] = ()
    resolution_options: tuple[ResolutionOption, ...] = RESOLUTION_OPTIONS
    status: ConflictStatus = "open"
    repair_attempts_used: int = Field(default=0, ge=0, strict=True)
    max_repair_attempts: int = Field(default=2, ge=0, strict=True)
    repair_worktree_path: Optional[str] = None
    repair_branch: Optional[str] = None
    resolved_sha: Optional[GitSha] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None


class RepairResult(ExecutionModel):
    """Outcome of an auto_repair, manual resolution, or discard transition."""

    conflict_id: Identifier
    integration_id: Identifier
    run_id: Identifier
    option: ResolutionOption
    status: ConflictStatus
    repaired: bool
    attempt_number: int = Field(default=0, ge=0, strict=True)
    repair_attempt_id: Optional[str] = None
    repair_worktree_path: Optional[str] = None
    repair_branch: Optional[str] = None
    resolved_sha: Optional[GitSha] = None
    checks_executed: tuple[CheckResult, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    failures: tuple[FailureDetail, ...] = ()
    resolved_at: Optional[str] = None
    prompt_context: Optional[str] = None


class ContractAmendmentProposal(ExecutionModel):
    """Auditable Wave 0 contract amendment proposal and application state."""

    amendment_id: Identifier
    run_id: Identifier
    wave0_task_id: Identifier
    requested_by_task_id: Optional[Identifier] = None
    actor: NonEmpty
    expected_run_revision: int = Field(ge=1, strict=True)
    reason: NonEmpty
    target_files: tuple[RelativePath, ...] = Field(min_length=1)
    summary: NonEmpty
    status: Literal["proposed", "applied", "rejected"] = "proposed"
    base_sha_before: GitSha
    base_sha_after: Optional[GitSha] = None
    run_revision_after: Optional[int] = Field(default=None, ge=1, strict=True)
    affected_wave1_task_ids: tuple[Identifier, ...] = ()
    revalidated_worktrees: tuple[str, ...] = ()
    conflicted_worktrees: tuple[str, ...] = ()
    checks_executed: tuple[CheckResult, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    created_at: Optional[str] = None
    applied_at: Optional[str] = None


class ConflictResolver:
    """
    Assisted merge conflict analyzer/resolver and Wave 0 Contract Amendment coordinator (RT28 / T27).

    Strictly preserves the operator's root checkout and active branch across all operations,
    enforces SQLite conflict_reports state invariants ('open', 'auto_repair', 'manual', 'discarded'),
    and logs transitions in both `events` and `commands(scope='conflict_resolver')`.
    """

    def __init__(
        self,
        store: ExecutionStore,
        git_workspace: Optional[GitWorkspaceService] = None,
        *,
        repo_root: Optional[Union[str, Path]] = None,
        check_runner: Optional[CheckRunner] = None,
        default_max_repair_attempts: int = 2,
    ):
        self.store = store
        self._git_workspace = git_workspace
        if self._git_workspace is None and repo_root is not None:
            self._git_workspace = GitWorkspaceService(repo_root=repo_root, store=store)
        self._check_runner = check_runner
        if default_max_repair_attempts < 0:
            raise ValueError("default_max_repair_attempts must be >= 0")
        self.default_max_repair_attempts = default_max_repair_attempts

    def _get_git_workspace(self, repo_root: Optional[Union[str, Path]] = None) -> GitWorkspaceService:
        if self._git_workspace is not None:
            if repo_root is not None:
                resolved = GitWorkspaceService.resolve_repo_root(repo_root)
                if os.path.normcase(str(resolved)) != os.path.normcase(str(self._git_workspace.repo_root)):
                    return GitWorkspaceService(repo_root=resolved, store=self.store)
            return self._git_workspace
        if repo_root is None:
            raise ContractViolation("workspace_invalid", "Repository root is required for ConflictResolver")
        self._git_workspace = GitWorkspaceService(repo_root=repo_root, store=self.store)
        return self._git_workspace

    def _get_check_runner(self, git_ws: GitWorkspaceService) -> CheckRunner:
        if self._check_runner is not None:
            return self._check_runner
        return CheckRunner(repo_root=git_ws.repo_root, runtime_dir=git_ws.runtime_dir)

    @staticmethod
    def _validate_conflict_transition(current: ConflictStatus, target: ConflictStatus, resolved_at: Optional[str]) -> None:
        if resolved_at is not None:
            raise ContractViolation(
                "conflict_already_resolved",
                f"Conflict report is already resolved in status '{current}' at '{resolved_at}'",
            )
        if target not in _CONFLICT_TRANSITIONS.get(current, set()):
            raise ContractViolation(
                "invalid_conflict_transition",
                f"Invalid conflict status transition: {current} -> {target}",
            )

    @staticmethod
    def _collect_run_checks(run_spec: RunSpec) -> tuple[CheckSpec, ...]:
        checks: List[CheckSpec] = []
        seen: set[tuple[str, tuple[str, ...], Optional[str]]] = set()
        for task in run_spec.tasks:
            for chk in task.acceptance_criteria:
                key = (chk.check_id, chk.command, chk.cwd)
                if key not in seen:
                    seen.add(key)
                    checks.append(chk)
        return tuple(checks)

    @staticmethod
    def _inspection_to_details(inspection: ThreeWayInspection) -> tuple[ConflictedFileDetail, ...]:
        return tuple(
            ConflictedFileDetail(
                path=fc.path,
                base_content=redact_text(fc.base_content) if fc.base_content is not None else None,
                ours_content=redact_text(fc.ours_content) if fc.ours_content is not None else None,
                theirs_content=redact_text(fc.theirs_content) if fc.theirs_content is not None else None,
                merged_preview=redact_text(fc.merged_preview),
                hunks=tuple(redact_text(h) for h in fc.hunks),
            )
            for fc in inspection.file_conflicts
        )

    async def _check_idempotency(
        self,
        db: Any,
        *,
        idempotency_key: Optional[str],
        request_hash: str,
    ) -> Optional[str]:
        if not idempotency_key:
            return None
        row = await (
            await db.execute(
                "SELECT request_hash, response_json FROM commands WHERE scope = 'conflict_resolver' AND idempotency_key = ?",
                (idempotency_key,),
            )
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise IdempotencyConflictError(
                f"Idempotency key '{idempotency_key}' in scope 'conflict_resolver' reused with different payload"
            )
        return row["response_json"]

    async def _record_audit_in_tx(
        self,
        db: Any,
        *,
        run_id: str,
        action: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        request_hash: Optional[str] = None,
        status: str = "completed",
        event_type: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        safe_payload = redact(payload)
        cmd_key = idempotency_key or f"{action}:{uuid.uuid4().hex}"
        req_hash = request_hash or self.store.compute_request_hash(safe_payload)
        await self.store._record_command_in_tx(
            db,
            scope="conflict_resolver",
            idempotency_key=cmd_key,
            request_hash=req_hash,
            run_id=run_id,
            response_payload=safe_payload,
            status=status,
        )
        if event_type is not None:
            await self.store._insert_event_in_tx(
                db,
                run_id=run_id,
                event_type=event_type,
                payload=redact(event_payload if event_payload is not None else safe_payload),
                task_id=task_id,
                attempt_id=attempt_id,
                correlation_id=correlation_id,
            )

    async def _load_conflict_meta(self, db: Any, conflict_id: str) -> Dict[str, Any]:
        rows = await (
            await db.execute(
                """
                SELECT response_json FROM commands
                WHERE scope = 'conflict_resolver'
                  AND json_extract(response_json, '$.conflict_id') = ?
                ORDER BY rowid DESC
                """,
                (conflict_id,),
            )
        ).fetchall()
        meta: Dict[str, Any] = {
            "repair_attempts_used": 0,
            "max_repair_attempts": self.default_max_repair_attempts,
            "repair_worktree_path": None,
            "repair_branch": None,
            "resolved_sha": None,
        }
        attempts_seen: set[int] = set()
        found_latest = False
        for row in rows:
            if not row["response_json"]:
                continue
            data = json.loads(row["response_json"])
            if not found_latest and "max_repair_attempts" in data:
                meta["max_repair_attempts"] = int(data["max_repair_attempts"])
                found_latest = True
            if meta["repair_worktree_path"] is None and data.get("repair_worktree_path"):
                meta["repair_worktree_path"] = data["repair_worktree_path"]
            if meta["repair_branch"] is None and data.get("repair_branch"):
                meta["repair_branch"] = data["repair_branch"]
            if meta["resolved_sha"] is None and data.get("resolved_sha"):
                meta["resolved_sha"] = data["resolved_sha"]
            if data.get("option") == "auto_repair" and data.get("attempt_number"):
                attempts_seen.add(int(data["attempt_number"]))
        if attempts_seen:
            meta["repair_attempts_used"] = max(attempts_seen)
        return meta

    async def _resolve_integration_shas(
        self,
        db: Any,
        integration_row: Any,
        git_ws: GitWorkspaceService,
        *,
        ours_sha: Optional[str],
        theirs_sha: Optional[str],
        base_sha: Optional[str],
    ) -> tuple[str, str, str]:
        run_id = integration_row["run_id"]
        int_id = integration_row["id"]
        int_ws_path = Path(integration_row["workspace_path"])

        resolved_ours: Optional[str] = None
        resolved_theirs: Optional[str] = None

        if ours_sha is not None:
            resolved_ours = git_ws.resolve_commit_sha(ours_sha, cwd=git_ws.repo_root)
        elif int_ws_path.exists():
            resolved_ours = git_ws.resolve_commit_sha("HEAD", cwd=int_ws_path)
        else:
            resolved_ours = git_ws.resolve_commit_sha(integration_row["expected_base_sha"], cwd=git_ws.repo_root)

        if theirs_sha is not None:
            resolved_theirs = git_ws.resolve_commit_sha(theirs_sha, cwd=git_ws.repo_root)
        else:
            # 1. Check active MERGE_HEAD in integration worktree if merge was left un-aborted
            if int_ws_path.exists():
                mh_res = git_ws._run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=int_ws_path)
                if mh_res.returncode == 0 and mh_res.stdout.strip():
                    resolved_theirs = git_ws.resolve_commit_sha(mh_res.stdout.strip(), cwd=int_ws_path)

            # 2. Check integration_items joined with results for the first unmerged commit
            if resolved_theirs is None:
                items = await (
                    await db.execute(
                        """
                        SELECT r.patch_commit_sha
                        FROM integration_items ii
                        JOIN results r ON r.id = ii.result_id
                        WHERE ii.integration_id = ?
                        ORDER BY ii.position ASC
                        """,
                        (int_id,),
                    )
                ).fetchall()
                for item in items:
                    cand = item["patch_commit_sha"]
                    if not cand:
                        continue
                    anc = git_ws._run_git(["merge-base", "--is-ancestor", cand, resolved_ours], cwd=git_ws.repo_root)
                    if anc.returncode != 0:
                        resolved_theirs = git_ws.resolve_commit_sha(cand, cwd=git_ws.repo_root)
                        break

            # 3. Fallback to merge.conflicted event payload recorded by GitWorkspaceService
            if resolved_theirs is None:
                ev_rows = await (
                    await db.execute(
                        "SELECT payload_json FROM events WHERE run_id = ? AND type = 'merge.conflicted' ORDER BY seq DESC",
                        (run_id,),
                    )
                ).fetchall()
                for ev in ev_rows:
                    payload = json.loads(ev["payload_json"])
                    if payload.get("integration_id") == int_id and payload.get("theirs_sha"):
                        if ours_sha is None and payload.get("ours_sha"):
                            resolved_ours = git_ws.resolve_commit_sha(payload["ours_sha"], cwd=git_ws.repo_root)
                        resolved_theirs = git_ws.resolve_commit_sha(payload["theirs_sha"], cwd=git_ws.repo_root)
                        break

        if resolved_theirs is None:
            raise ContractViolation(
                "conflict_context_missing",
                f"Cannot determine conflicting commit (theirs_sha) for integration '{int_id}'",
            )

        if base_sha is not None:
            resolved_base = git_ws.resolve_commit_sha(base_sha, cwd=git_ws.repo_root)
        else:
            mb_res = git_ws._run_git(["merge-base", resolved_ours, resolved_theirs], cwd=git_ws.repo_root)
            if mb_res.returncode == 0 and mb_res.stdout.strip():
                resolved_base = git_ws.resolve_commit_sha(mb_res.stdout.strip(), cwd=git_ws.repo_root)
            else:
                resolved_base = git_ws.resolve_commit_sha(integration_row["expected_base_sha"], cwd=git_ws.repo_root)

        return resolved_base, resolved_ours, resolved_theirs

    async def analyze(
        self,
        integration_id: str,
        *,
        base_sha: Optional[str] = None,
        ours_sha: Optional[str] = None,
        theirs_sha: Optional[str] = None,
        max_repair_attempts: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> ConflictReport:
        """
        Inspect a conflicted integration 3-way (base/ours/theirs), produce a ConflictReport
        with hunks and options ('auto_repair', 'manual', 'discarded'), and persist it as 'open'.
        """
        await self.store.initialize()
        effective_max = self.default_max_repair_attempts if max_repair_attempts is None else max_repair_attempts
        if effective_max < 0:
            raise ContractViolation("invalid_repair_budget", "max_repair_attempts must be >= 0")

        req_hash = self.store.compute_request_hash(
            {
                "op": "analyze",
                "integration_id": integration_id,
                "base_sha": base_sha,
                "ours_sha": ours_sha,
                "theirs_sha": theirs_sha,
                "max_repair_attempts": effective_max,
            }
        )

        async with self.store._connect() as db:
            cached = await self._check_idempotency(db, idempotency_key=idempotency_key, request_hash=req_hash)
            if cached is not None:
                data = json.loads(cached)
                if "conflict_id" in data and "integration_id" in data:
                    return await self.get_report(data["conflict_id"])

            int_row = await (
                await db.execute("SELECT * FROM integrations WHERE id = ?", (integration_id,))
            ).fetchone()
            if int_row is None:
                raise ContractViolation("resource_not_found", f"Integration '{integration_id}' does not exist")
            if int_row["status"] in {IntegrationStatus.INTEGRATED.value, IntegrationStatus.DISCARDED.value}:
                raise ContractViolation(
                    "conflict_not_applicable",
                    f"Integration '{integration_id}' is already in terminal status '{int_row['status']}'",
                )

            run_rec = await self.store.get_run(int_row["run_id"])
            if run_rec is None:
                raise StorageIntegrityError(f"Run '{int_row['run_id']}' does not exist")
            run_spec: RunSpec = run_rec["spec"]
            git_ws = self._get_git_workspace(run_spec.repo_root)
            snap_before = git_ws.snapshot_operator_checkout()

            resolved_base, resolved_ours, resolved_theirs = await self._resolve_integration_shas(
                db,
                int_row,
                git_ws,
                ours_sha=ours_sha,
                theirs_sha=theirs_sha,
                base_sha=base_sha,
            )

            existing = await (
                await db.execute(
                    """
                    SELECT * FROM conflict_reports
                    WHERE integration_id = ? AND base_sha = ? AND ours_sha = ? AND theirs_sha = ? AND status = 'open'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (integration_id, resolved_base, resolved_ours, resolved_theirs),
                )
            ).fetchone()
            if existing is not None:
                git_ws.assert_operator_checkout_intact(snap_before)
                return await self.get_report(existing["id"])

            inspection = git_ws.inspect_three_way(resolved_ours, resolved_theirs, base_sha=resolved_base)
            if not inspection.has_conflicts or not inspection.conflicted_files:
                raise ContractViolation(
                    "no_conflict_detected",
                    f"No 3-way merge conflicts detected between '{resolved_ours}' and '{resolved_theirs}'",
                )

            conflict_id = f"cfl-{new_id()}"
            created_at = _utc_now_iso()
            details = self._inspection_to_details(inspection)
            report = ConflictReport(
                conflict_id=conflict_id,
                integration_id=integration_id,
                run_id=run_spec.run_id,
                base_sha=inspection.base_sha,
                ours_sha=inspection.ours_sha,
                theirs_sha=inspection.theirs_sha,
                conflicted_files=inspection.conflicted_files,
                file_details=details,
                resolution_options=RESOLUTION_OPTIONS,
                status="open",
                repair_attempts_used=0,
                max_repair_attempts=effective_max,
                created_at=created_at,
                resolved_at=None,
            )

            async with self.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO conflict_reports (
                        id, integration_id, base_sha, ours_sha, theirs_sha,
                        conflicted_files_json, resolution_options_json, status, created_at, resolved_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, NULL)
                    """,
                    (
                        conflict_id,
                        integration_id,
                        report.base_sha,
                        report.ours_sha,
                        report.theirs_sha,
                        json.dumps(list(report.conflicted_files)),
                        json.dumps(list(report.resolution_options)),
                        created_at,
                    ),
                )
                await self._record_audit_in_tx(
                    db,
                    run_id=run_spec.run_id,
                    action="analyze",
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    payload={
                        "action": "conflict_report.created",
                        "conflict_id": conflict_id,
                        "integration_id": integration_id,
                        "status": "open",
                        "base_sha": report.base_sha,
                        "ours_sha": report.ours_sha,
                        "theirs_sha": report.theirs_sha,
                        "conflicted_files": list(report.conflicted_files),
                        "resolution_options": list(report.resolution_options),
                        "max_repair_attempts": effective_max,
                    },
                    event_type="merge.conflict_analyzed",
                    event_payload={
                        "conflict_id": conflict_id,
                        "integration_id": integration_id,
                        "base_sha": report.base_sha,
                        "ours_sha": report.ours_sha,
                        "theirs_sha": report.theirs_sha,
                        "conflicted_files": list(report.conflicted_files),
                        "resolution_options": list(report.resolution_options),
                    },
                    correlation_id=correlation_id,
                )

            git_ws.assert_operator_checkout_intact(snap_before)
            return report

    async def get_report(self, conflict_id: str, *, include_details: bool = True) -> ConflictReport:
        """Load a persisted ConflictReport from SQLite and rehydrate 3-way file details."""
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute(
                    """
                    SELECT c.*, i.run_id
                    FROM conflict_reports c
                    JOIN integrations i ON i.id = c.integration_id
                    WHERE c.id = ?
                    """,
                    (conflict_id,),
                )
            ).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"Conflict report '{conflict_id}' does not exist")

            meta = await self._load_conflict_meta(db, conflict_id)

        details: tuple[ConflictedFileDetail, ...] = ()
        if include_details:
            run_rec = await self.store.get_run(row["run_id"])
            if run_rec is not None:
                git_ws = self._get_git_workspace(run_rec["spec"].repo_root)
                inspection = git_ws.inspect_three_way(
                    row["ours_sha"],
                    row["theirs_sha"],
                    base_sha=row["base_sha"],
                )
                details = self._inspection_to_details(inspection)

        return ConflictReport(
            conflict_id=row["id"],
            integration_id=row["integration_id"],
            run_id=row["run_id"],
            base_sha=row["base_sha"],
            ours_sha=row["ours_sha"],
            theirs_sha=row["theirs_sha"],
            conflicted_files=tuple(json.loads(row["conflicted_files_json"])),
            file_details=details,
            resolution_options=tuple(json.loads(row["resolution_options_json"])),
            status=row["status"],
            repair_attempts_used=meta["repair_attempts_used"],
            max_repair_attempts=meta["max_repair_attempts"],
            repair_worktree_path=meta["repair_worktree_path"],
            repair_branch=meta["repair_branch"],
            resolved_sha=meta["resolved_sha"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )

    async def list_reports(
        self,
        *,
        integration_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> tuple[ConflictReport, ...]:
        """List persisted ConflictReports filtered optionally by integration_id or run_id."""
        await self.store.initialize()
        query = (
            "SELECT c.id FROM conflict_reports c "
            "JOIN integrations i ON i.id = c.integration_id"
        )
        clauses: List[str] = []
        params: List[Any] = []
        if integration_id is not None:
            clauses.append("c.integration_id = ?")
            params.append(integration_id)
        if run_id is not None:
            clauses.append("i.run_id = ?")
            params.append(run_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY c.created_at ASC, c.id ASC"

        async with self.store._connect() as db:
            rows = await (await db.execute(query, tuple(params))).fetchall()
        reports = [await self.get_report(r["id"]) for r in rows]
        return tuple(reports)

    def build_repair_prompt(self, report: ConflictReport) -> str:
        """Build a structured, redacted 3-way merge_repair prompt from a ConflictReport."""
        sections = [
            "--- [HYDRA MERGE REPAIR CONTEXT] ---",
            f"conflict_id: {report.conflict_id}",
            f"integration_id: {report.integration_id}",
            f"base_sha: {report.base_sha}",
            f"ours_sha: {report.ours_sha}",
            f"theirs_sha: {report.theirs_sha}",
            f"conflicted_files: {', '.join(report.conflicted_files)}",
        ]
        for detail in report.file_details:
            sections.append(f"\n### File: {detail.path}")
            if detail.base_content is not None:
                sections.append(f"[BASE]\n{redact_text(detail.base_content)}")
            if detail.merged_preview:
                sections.append(f"[3-WAY CONFLICT]\n{redact_text(detail.merged_preview)}")
        sections.append(
            "\nINSTRUCTION: Resolve all conflict markers cleanly in the isolated merge_repair worktree "
            "without violating task scope or mutating the operator checkout."
        )
        return "\n".join(sections)

    async def _run_repair_command(
        self,
        command: Sequence[str],
        cwd: Path,
        prompt_text: str,
        timeout_seconds: float = 120.0,
    ) -> tuple[int, str, str]:
        env = filter_worker_env()
        env["HYDRA_REPAIR_PROMPT"] = prompt_text
        kwargs: Dict[str, Any] = {
            "cwd": str(cwd),
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": env,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = await asyncio.create_subprocess_exec(*command, **kwargs)
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(input=prompt_text.encode("utf-8")),
                timeout=timeout_seconds,
            )
            return int(proc.returncode or 0), out_b.decode("utf-8", errors="replace"), err_b.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            if proc.pid:
                await cancel_process_tree(proc.pid)
            return 124, "", f"Repair command timed out after {timeout_seconds}s"

    async def _persist_check_evidence_in_tx(
        self,
        db: Any,
        *,
        integration_id: str,
        checks_executed: Sequence[CheckResult],
        artifacts: Sequence[Artifact],
    ) -> None:
        for art in artifacts:
            await self.store._upsert_artifact_in_tx(db, art)
        for chk in checks_executed:
            chk_row_id = f"chk-{integration_id}-{chk.check_id}"
            stdout_id = (
                chk.stdout_artifact_id
                if await (await db.execute("SELECT 1 FROM artifacts WHERE id = ?", (chk.stdout_artifact_id,))).fetchone()
                else None
            )
            stderr_id = (
                chk.stderr_artifact_id
                if await (await db.execute("SELECT 1 FROM artifacts WHERE id = ?", (chk.stderr_artifact_id,))).fetchone()
                else None
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO check_results (
                    id, result_id, integration_id, check_id, command_json, cwd,
                    tested_sha, exit_code, duration_seconds,
                    stdout_artifact_id, stderr_artifact_id, output_artifact_id,
                    started_at, finished_at
                )
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    chk_row_id,
                    integration_id,
                    chk.check_id,
                    json.dumps(list(chk.command)),
                    chk.cwd,
                    chk.tested_sha,
                    chk.exit_code,
                    chk.duration_seconds,
                    stdout_id,
                    stderr_id,
                    stdout_id,
                ),
            )

    async def _fail_auto_repair(
        self,
        *,
        git_ws: GitWorkspaceService,
        report: ConflictReport,
        attempt_number: int,
        repair_attempt_id: str,
        repair_wt: Optional[Path],
        repair_branch: Optional[str],
        failure: FailureDetail,
        checks_executed: tuple[CheckResult, ...] = (),
        artifacts: tuple[Artifact, ...] = (),
        prompt_context: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        request_hash: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RepairResult:
        # Abort incomplete merge inside the repair worktree so no dirty merge remains while preserving worktree/logs
        if repair_wt is not None and repair_wt.exists():
            mh = git_ws._run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=repair_wt)
            if mh.returncode == 0:
                git_ws._run_git(["merge", "--abort"], cwd=repair_wt)

        result = RepairResult(
            conflict_id=report.conflict_id,
            integration_id=report.integration_id,
            run_id=report.run_id,
            option="auto_repair",
            status="open",
            repaired=False,
            attempt_number=attempt_number,
            repair_attempt_id=repair_attempt_id,
            repair_worktree_path=str(repair_wt) if repair_wt is not None else None,
            repair_branch=repair_branch,
            resolved_sha=None,
            checks_executed=checks_executed,
            artifacts=artifacts,
            failures=(failure,),
            resolved_at=None,
            prompt_context=prompt_context,
        )
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE conflict_reports SET status = 'open', resolved_at = NULL WHERE id = ?",
                    (report.conflict_id,),
                )
                await self._persist_check_evidence_in_tx(
                    db,
                    integration_id=report.integration_id,
                    checks_executed=checks_executed,
                    artifacts=artifacts,
                )
                await self._record_audit_in_tx(
                    db,
                    run_id=report.run_id,
                    action="auto_repair_failed",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    status="failed",
                    payload={
                        **result.model_dump(mode="json"),
                        "action": "auto_repair.failed",
                        "max_repair_attempts": report.max_repair_attempts,
                    },
                    event_type="merge.conflict_repair_failed",
                    event_payload={
                        "conflict_id": report.conflict_id,
                        "integration_id": report.integration_id,
                        "attempt_number": attempt_number,
                        "repair_attempt_id": repair_attempt_id,
                        "failure_code": failure.code,
                        "failure_message": failure.message,
                        "status": "open",
                    },
                    correlation_id=correlation_id,
                )
        return result

    async def auto_repair(
        self,
        conflict_id: str,
        *,
        repairer: Optional[Callable[[Path, ConflictReport, int], Any]] = None,
        repair_command: Optional[Sequence[str]] = None,
        checks: Optional[Sequence[CheckSpec]] = None,
        max_repair_attempts: Optional[int] = None,
        actor: str = "conflict_resolver",
        allowed_paths: Optional[Sequence[str]] = None,
        forbidden_paths: Sequence[str] = (),
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RepairResult:
        """
        Execute bounded merge_repair in an isolated worktree (open -> auto_repair).

        Only marks the conflict resolved and integrates after all mandatory checks pass.
        On failure or exhausted budget, preserves evidence without mutating operator checkout
        and returns conflict status to 'open' without leaving a dirty merge.
        """
        report = await self.get_report(conflict_id)
        effective_max = report.max_repair_attempts if max_repair_attempts is None else max_repair_attempts
        if effective_max < 0:
            raise ContractViolation("invalid_repair_budget", "max_repair_attempts must be >= 0")

        req_hash = self.store.compute_request_hash(
            {
                "op": "auto_repair",
                "conflict_id": conflict_id,
                "actor": actor,
                "max_repair_attempts": effective_max,
                "repair_command": list(repair_command) if repair_command else None,
            }
        )

        async with self.store._connect() as db:
            cached = await self._check_idempotency(db, idempotency_key=idempotency_key, request_hash=req_hash)
            if cached is not None:
                return _parse_command_model(RepairResult, cached)

        self._validate_conflict_transition(report.status, "auto_repair", report.resolved_at)
        if report.status != "open":
            raise ContractViolation(
                "invalid_conflict_state",
                f"auto_repair requires conflict '{conflict_id}' in 'open' status, got '{report.status}'",
            )

        run_rec = await self.store.get_run(report.run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{report.run_id}' does not exist")
        run_spec: RunSpec = run_rec["spec"]
        git_ws = self._get_git_workspace(run_spec.repo_root)
        snap_before = git_ws.snapshot_operator_checkout()

        if report.repair_attempts_used >= effective_max:
            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    await self._record_audit_in_tx(
                        db,
                        run_id=report.run_id,
                        action="auto_repair_budget_exhausted",
                        idempotency_key=idempotency_key,
                        request_hash=req_hash,
                        status="failed",
                        payload={
                            "action": "auto_repair.budget_exhausted",
                            "conflict_id": conflict_id,
                            "integration_id": report.integration_id,
                            "repair_attempts_used": report.repair_attempts_used,
                            "max_repair_attempts": effective_max,
                            "status": "open",
                        },
                        event_type="merge.conflict_repair_failed",
                        event_payload={
                            "conflict_id": conflict_id,
                            "integration_id": report.integration_id,
                            "reason": "repair_budget_exhausted",
                            "repair_attempts_used": report.repair_attempts_used,
                            "max_repair_attempts": effective_max,
                        },
                        correlation_id=correlation_id,
                    )
            git_ws.assert_operator_checkout_intact(snap_before)
            raise ContractViolation(
                "repair_budget_exhausted",
                f"Conflict '{conflict_id}' reached max_repair_attempts ({effective_max})",
            )

        attempt_number = report.repair_attempts_used + 1
        repair_prompt = self.build_repair_prompt(report)
        ws_record = git_ws.create_merge_repair_worktree(
            run_id=report.run_id,
            conflict_id=conflict_id,
            attempt_ordinal=attempt_number,
            ours_sha=report.ours_sha,
            theirs_sha=report.theirs_sha,
            populate_conflict=True,
            prefix="repair",
        )

        # Transition open -> auto_repair
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE conflict_reports SET status = 'auto_repair', resolved_at = NULL WHERE id = ? AND status = 'open'",
                    (conflict_id,),
                )
                await self._record_audit_in_tx(
                    db,
                    run_id=report.run_id,
                    action="auto_repair_started",
                    payload={
                        "action": "auto_repair.started",
                        "conflict_id": conflict_id,
                        "integration_id": report.integration_id,
                        "option": "auto_repair",
                        "attempt_number": attempt_number,
                        "repair_attempt_id": ws_record.attempt_id,
                        "repair_worktree_path": str(ws_record.canonical_path),
                        "repair_branch": ws_record.branch,
                        "max_repair_attempts": effective_max,
                        "status": "auto_repair",
                    },
                    event_type="merge.conflict_repair_started",
                    event_payload={
                        "conflict_id": conflict_id,
                        "integration_id": report.integration_id,
                        "attempt_number": attempt_number,
                        "repair_attempt_id": ws_record.attempt_id,
                        "repair_worktree_path": str(ws_record.canonical_path),
                        "repair_branch": ws_record.branch,
                        "actor": actor,
                    },
                    correlation_id=correlation_id,
                )

        report_for_repair = report.model_copy(
            update={
                "status": "auto_repair",
                "repair_attempts_used": attempt_number,
                "max_repair_attempts": effective_max,
                "repair_worktree_path": str(ws_record.canonical_path),
                "repair_branch": ws_record.branch,
            }
        )

        # Invoke repairer (callable or CLI command) inside the isolated merge_repair worktree
        try:
            if repairer is not None:
                outcome_val = repairer(ws_record.canonical_path, report_for_repair, attempt_number)
                if asyncio.iscoroutine(outcome_val):
                    outcome_val = await outcome_val
                if outcome_val is False:
                    res = await self._fail_auto_repair(
                        git_ws=git_ws,
                        report=report_for_repair,
                        attempt_number=attempt_number,
                        repair_attempt_id=ws_record.attempt_id,
                        repair_wt=ws_record.canonical_path,
                        repair_branch=ws_record.branch,
                        failure=FailureDetail(
                            code="repairer_rejected",
                            message="Repairer declined or failed to resolve merge conflict",
                            retryable=True,
                        ),
                        prompt_context=repair_prompt,
                        idempotency_key=idempotency_key,
                        request_hash=req_hash,
                        correlation_id=correlation_id,
                    )
                    git_ws.assert_operator_checkout_intact(snap_before)
                    return res
            elif repair_command is not None:
                rc, _, stderr_txt = await self._run_repair_command(
                    repair_command,
                    ws_record.canonical_path,
                    repair_prompt,
                )
                if rc != 0:
                    res = await self._fail_auto_repair(
                        git_ws=git_ws,
                        report=report_for_repair,
                        attempt_number=attempt_number,
                        repair_attempt_id=ws_record.attempt_id,
                        repair_wt=ws_record.canonical_path,
                        repair_branch=ws_record.branch,
                        failure=FailureDetail(
                            code="repair_command_failed",
                            message=f"Repair command exited with code {rc}: {redact_text(stderr_txt).strip()}",
                            retryable=True,
                        ),
                        prompt_context=repair_prompt,
                        idempotency_key=idempotency_key,
                        request_hash=req_hash,
                        correlation_id=correlation_id,
                    )
                    git_ws.assert_operator_checkout_intact(snap_before)
                    return res
            else:
                res = await self._fail_auto_repair(
                    git_ws=git_ws,
                    report=report_for_repair,
                    attempt_number=attempt_number,
                    repair_attempt_id=ws_record.attempt_id,
                    repair_wt=ws_record.canonical_path,
                    repair_branch=ws_record.branch,
                    failure=FailureDetail(
                        code="repairer_missing",
                        message="No repairer callable or repair_command provided for auto_repair",
                        retryable=True,
                    ),
                    prompt_context=repair_prompt,
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    correlation_id=correlation_id,
                )
                git_ws.assert_operator_checkout_intact(snap_before)
                return res
        except Exception as exc:
            res = await self._fail_auto_repair(
                git_ws=git_ws,
                report=report_for_repair,
                attempt_number=attempt_number,
                repair_attempt_id=ws_record.attempt_id,
                repair_wt=ws_record.canonical_path,
                repair_branch=ws_record.branch,
                failure=FailureDetail(
                    code="repair_execution_error",
                    message=f"Repairer raised error: {redact_text(str(exc))}",
                    retryable=True,
                ),
                prompt_context=repair_prompt,
                idempotency_key=idempotency_key,
                request_hash=req_hash,
                correlation_id=correlation_id,
            )
            git_ws.assert_operator_checkout_intact(snap_before)
            return res

        # Verify conflicts are actually resolved on disk and index
        remaining = git_ws.inspect_worktree_conflicts(
            ws_record.canonical_path,
            candidate_files=report.conflicted_files,
        )
        if remaining:
            res = await self._fail_auto_repair(
                report=report_for_repair,
                attempt_number=attempt_number,
                repair_attempt_id=ws_record.attempt_id,
                repair_wt=ws_record.canonical_path,
                repair_branch=ws_record.branch,
                git_ws=git_ws,
                failure=FailureDetail(
                    code="unresolved_conflicts_remain",
                    message=f"Unresolved conflict markers or unmerged paths remain: {', '.join(remaining)}",
                    retryable=True,
                ),
                prompt_context=repair_prompt,
                idempotency_key=idempotency_key,
                request_hash=req_hash,
                correlation_id=correlation_id,
            )
            git_ws.assert_operator_checkout_intact(snap_before)
            return res

        # Optional scope gate on the repair worktree
        if allowed_paths is not None or forbidden_paths:
            scope = git_ws.validate_worktree_scope(
                ws_record.canonical_path,
                base_sha=report.ours_sha,
                allowed_paths=tuple(allowed_paths) if allowed_paths is not None else ("**/*",),
                forbidden_paths=forbidden_paths,
            )
            if not scope.valid:
                res = await self._fail_auto_repair(
                    git_ws=git_ws,
                    report=report_for_repair,
                    attempt_number=attempt_number,
                    repair_attempt_id=ws_record.attempt_id,
                    repair_wt=ws_record.canonical_path,
                    repair_branch=ws_record.branch,
                    failure=FailureDetail(
                        code="scope_violation",
                        message=f"Repair modified forbidden or out-of-scope paths: {', '.join(scope.violations)}",
                        retryable=False,
                    ),
                    prompt_context=repair_prompt,
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    correlation_id=correlation_id,
                )
                git_ws.assert_operator_checkout_intact(snap_before)
                return res

        resolved_sha = git_ws.commit_resolved_worktree(
            ws_record.canonical_path,
            commit_message=f"fix(merge_repair): resolve conflict {conflict_id} (attempt {attempt_number})",
            candidate_files=report.conflicted_files,
        )

        # Mandatory post-repair checks before acceptance
        effective_checks = tuple(checks) if checks is not None else self._collect_run_checks(run_spec)
        check_runner = self._get_check_runner(git_ws)
        executed_checks: tuple[CheckResult, ...] = ()
        check_artifacts: tuple[Artifact, ...] = ()
        if effective_checks:
            executed_checks, check_artifacts = await check_runner.run_checks(
                run_id=report.run_id,
                attempt_id=None,
                workspace_path=ws_record.canonical_path,
                tested_sha=resolved_sha,
                checks=effective_checks,
                scope_prefix=f"rep-{_short_token(conflict_id)}-{attempt_number}",
            )
            failed_checks = [c for c in executed_checks if c.exit_code != 0]
            if failed_checks:
                res = await self._fail_auto_repair(
                    git_ws=git_ws,
                    report=report_for_repair,
                    attempt_number=attempt_number,
                    repair_attempt_id=ws_record.attempt_id,
                    repair_wt=ws_record.canonical_path,
                    repair_branch=ws_record.branch,
                    failure=FailureDetail(
                        code="post_repair_check_failed",
                        message=f"Mandatory checks failed after merge_repair: {', '.join(c.check_id for c in failed_checks)}",
                        retryable=True,
                    ),
                    checks_executed=executed_checks,
                    artifacts=check_artifacts,
                    prompt_context=repair_prompt,
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    correlation_id=correlation_id,
                )
                git_ws.assert_operator_checkout_intact(snap_before)
                return res

        resolved_at = _utc_now_iso()
        ws_record.status = "preserved"
        final_result = RepairResult(
            conflict_id=conflict_id,
            integration_id=report.integration_id,
            run_id=report.run_id,
            option="auto_repair",
            status="auto_repair",
            repaired=True,
            attempt_number=attempt_number,
            repair_attempt_id=ws_record.attempt_id,
            repair_worktree_path=str(ws_record.canonical_path),
            repair_branch=ws_record.branch,
            resolved_sha=resolved_sha,
            checks_executed=executed_checks,
            artifacts=check_artifacts,
            failures=(),
            resolved_at=resolved_at,
            prompt_context=repair_prompt,
        )

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE conflict_reports SET status = 'auto_repair', resolved_at = ? WHERE id = ?",
                    (resolved_at, conflict_id),
                )
                await db.execute(
                    "UPDATE integrations SET status = 'integrated', result_sha = ?, workspace_path = ? WHERE id = ?",
                    (resolved_sha, str(ws_record.canonical_path), report.integration_id),
                )
                await self._persist_check_evidence_in_tx(
                    db,
                    integration_id=report.integration_id,
                    checks_executed=executed_checks,
                    artifacts=check_artifacts,
                )
                await self._record_audit_in_tx(
                    db,
                    run_id=report.run_id,
                    action="auto_repair_succeeded",
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    status="completed",
                    payload={
                        **final_result.model_dump(mode="json"),
                        "action": "auto_repair.succeeded",
                        "max_repair_attempts": effective_max,
                    },
                    event_type="merge.conflict_resolved",
                    event_payload={
                        "conflict_id": conflict_id,
                        "integration_id": report.integration_id,
                        "option": "auto_repair",
                        "status": "auto_repair",
                        "attempt_number": attempt_number,
                        "resolved_sha": resolved_sha,
                        "resolved_at": resolved_at,
                        "actor": actor,
                    },
                    correlation_id=correlation_id,
                )
                await self.store._insert_event_in_tx(
                    db,
                    run_id=report.run_id,
                    event_type="merge.completed",
                    payload={
                        "integration_id": report.integration_id,
                        "conflict_id": conflict_id,
                        "resolution_option": "auto_repair",
                        "result_sha": resolved_sha,
                    },
                    correlation_id=correlation_id,
                )

        git_ws.assert_operator_checkout_intact(snap_before)
        return final_result

    async def resolve_manual(
        self,
        conflict_id: str,
        *,
        actor: str = "operator",
        finalize: bool = False,
        worktree_path: Optional[Union[str, Path]] = None,
        checks: Optional[Sequence[CheckSpec]] = None,
        commit_message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RepairResult:
        """
        Hand off a conflict for manual developer resolution in a preserved isolated worktree
        (open -> manual), or finalize manual resolution after verifying clean tree and checks.
        """
        report = await self.get_report(conflict_id)
        req_hash = self.store.compute_request_hash(
            {
                "op": "resolve_manual",
                "conflict_id": conflict_id,
                "actor": actor,
                "finalize": finalize,
                "worktree_path": str(worktree_path) if worktree_path else None,
            }
        )

        async with self.store._connect() as db:
            cached = await self._check_idempotency(db, idempotency_key=idempotency_key, request_hash=req_hash)
            if cached is not None:
                return _parse_command_model(RepairResult, cached)

        self._validate_conflict_transition(report.status, "manual", report.resolved_at)

        run_rec = await self.store.get_run(report.run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{report.run_id}' does not exist")
        run_spec: RunSpec = run_rec["spec"]
        git_ws = self._get_git_workspace(run_spec.repo_root)
        snap_before = git_ws.snapshot_operator_checkout()

        manual_wt: Optional[Path] = None
        manual_branch: Optional[str] = report.repair_branch
        if worktree_path is not None:
            manual_wt = Path(os.path.realpath(worktree_path))
        elif report.repair_worktree_path and Path(report.repair_worktree_path).exists():
            manual_wt = Path(os.path.realpath(report.repair_worktree_path))

        if manual_wt is None:
            ws_record = git_ws.create_merge_repair_worktree(
                run_id=report.run_id,
                conflict_id=conflict_id,
                attempt_ordinal=report.repair_attempts_used + 1,
                ours_sha=report.ours_sha,
                theirs_sha=report.theirs_sha,
                populate_conflict=True,
                prefix="manual",
            )
            manual_wt = ws_record.canonical_path
            manual_branch = ws_record.branch

        # Ensure manual worktree is never the operator's root checkout
        if os.path.normcase(str(manual_wt)) == os.path.normcase(str(git_ws.repo_root)):
            raise ContractViolation(
                "operator_checkout_protected",
                "Manual conflict resolution must use an isolated worktree, never the operator root checkout",
            )

        if not finalize:
            prompt_ctx = self.build_repair_prompt(report)
            res_pending = RepairResult(
                conflict_id=conflict_id,
                integration_id=report.integration_id,
                run_id=report.run_id,
                option="manual",
                status="manual",
                repaired=False,
                attempt_number=report.repair_attempts_used,
                repair_worktree_path=str(manual_wt),
                repair_branch=manual_branch,
                resolved_sha=None,
                resolved_at=None,
                prompt_context=prompt_ctx,
            )
            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    await db.execute(
                        "UPDATE conflict_reports SET status = 'manual', resolved_at = NULL WHERE id = ?",
                        (conflict_id,),
                    )
                    await self._record_audit_in_tx(
                        db,
                        run_id=report.run_id,
                        action="manual_opened",
                        idempotency_key=idempotency_key,
                        request_hash=req_hash,
                        status="pending",
                        payload={
                            **res_pending.model_dump(mode="json"),
                            "action": "manual.opened",
                            "actor": actor,
                            "max_repair_attempts": report.max_repair_attempts,
                        },
                        event_type="task.needs_context",
                        event_payload={
                            "conflict_id": conflict_id,
                            "integration_id": report.integration_id,
                            "option": "manual",
                            "status": "manual",
                            "repair_worktree_path": str(manual_wt),
                            "actor": actor,
                        },
                        correlation_id=correlation_id,
                    )
            git_ws.assert_operator_checkout_intact(snap_before)
            return res_pending

        # Finalize manual resolution: verify no remaining conflicts + commit + checks pass
        remaining = git_ws.inspect_worktree_conflicts(manual_wt, candidate_files=report.conflicted_files)
        if remaining:
            raise ContractViolation(
                "unresolved_conflicts_remain",
                f"Cannot finalize manual resolution; unresolved conflicts remain in: {', '.join(remaining)}",
            )

        resolved_sha = git_ws.commit_resolved_worktree(
            manual_wt,
            commit_message=commit_message or f"fix(manual): resolve merge conflict {conflict_id}",
            candidate_files=report.conflicted_files,
        )

        effective_checks = tuple(checks) if checks is not None else self._collect_run_checks(run_spec)
        executed_checks: tuple[CheckResult, ...] = ()
        check_artifacts: tuple[Artifact, ...] = ()
        if effective_checks:
            check_runner = self._get_check_runner(git_ws)
            executed_checks, check_artifacts = await check_runner.run_checks(
                run_id=report.run_id,
                attempt_id=None,
                workspace_path=manual_wt,
                tested_sha=resolved_sha,
                checks=effective_checks,
                scope_prefix=f"man-{_short_token(conflict_id)}",
            )
            failed_checks = [c for c in executed_checks if c.exit_code != 0]
            if failed_checks:
                res_failed = RepairResult(
                    conflict_id=conflict_id,
                    integration_id=report.integration_id,
                    run_id=report.run_id,
                    option="manual",
                    status="manual",
                    repaired=False,
                    attempt_number=report.repair_attempts_used,
                    repair_worktree_path=str(manual_wt),
                    repair_branch=manual_branch,
                    resolved_sha=None,
                    checks_executed=executed_checks,
                    artifacts=check_artifacts,
                    failures=(
                        FailureDetail(
                            code="post_repair_check_failed",
                            message=f"Mandatory checks failed on manual resolution: {', '.join(c.check_id for c in failed_checks)}",
                            retryable=True,
                        ),
                    ),
                    resolved_at=None,
                )
                async with self.store._connect() as db:
                    async with self.store._transaction(db):
                        await db.execute(
                            "UPDATE conflict_reports SET status = 'manual', resolved_at = NULL WHERE id = ?",
                            (conflict_id,),
                        )
                        await self._persist_check_evidence_in_tx(
                            db,
                            integration_id=report.integration_id,
                            checks_executed=executed_checks,
                            artifacts=check_artifacts,
                        )
                        await self._record_audit_in_tx(
                            db,
                            run_id=report.run_id,
                            action="manual_check_failed",
                            idempotency_key=idempotency_key,
                            request_hash=req_hash,
                            status="failed",
                            payload={
                                **res_failed.model_dump(mode="json"),
                                "action": "manual.check_failed",
                                "actor": actor,
                            },
                            event_type="check.finished",
                            event_payload={
                                "conflict_id": conflict_id,
                                "integration_id": report.integration_id,
                                "status": "manual",
                                "passed": False,
                                "failed_checks": [c.check_id for c in failed_checks],
                            },
                            correlation_id=correlation_id,
                        )
                git_ws.assert_operator_checkout_intact(snap_before)
                return res_failed

        resolved_at = _utc_now_iso()
        res_done = RepairResult(
            conflict_id=conflict_id,
            integration_id=report.integration_id,
            run_id=report.run_id,
            option="manual",
            status="manual",
            repaired=True,
            attempt_number=report.repair_attempts_used,
            repair_worktree_path=str(manual_wt),
            repair_branch=manual_branch,
            resolved_sha=resolved_sha,
            checks_executed=executed_checks,
            artifacts=check_artifacts,
            failures=(),
            resolved_at=resolved_at,
        )
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE conflict_reports SET status = 'manual', resolved_at = ? WHERE id = ?",
                    (resolved_at, conflict_id),
                )
                await db.execute(
                    "UPDATE integrations SET status = 'integrated', result_sha = ?, workspace_path = ? WHERE id = ?",
                    (resolved_sha, str(manual_wt), report.integration_id),
                )
                await self._persist_check_evidence_in_tx(
                    db,
                    integration_id=report.integration_id,
                    checks_executed=executed_checks,
                    artifacts=check_artifacts,
                )
                await self._record_audit_in_tx(
                    db,
                    run_id=report.run_id,
                    action="manual_resolved",
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    status="completed",
                    payload={
                        **res_done.model_dump(mode="json"),
                        "action": "manual.resolved",
                        "actor": actor,
                    },
                    event_type="merge.conflict_resolved",
                    event_payload={
                        "conflict_id": conflict_id,
                        "integration_id": report.integration_id,
                        "option": "manual",
                        "status": "manual",
                        "resolved_sha": resolved_sha,
                        "resolved_at": resolved_at,
                        "actor": actor,
                    },
                    correlation_id=correlation_id,
                )
                await self.store._insert_event_in_tx(
                    db,
                    run_id=report.run_id,
                    event_type="merge.completed",
                    payload={
                        "integration_id": report.integration_id,
                        "conflict_id": conflict_id,
                        "resolution_option": "manual",
                        "result_sha": resolved_sha,
                    },
                    correlation_id=correlation_id,
                )

        git_ws.assert_operator_checkout_intact(snap_before)
        return res_done

    async def finalize_manual(
        self,
        conflict_id: str,
        *,
        actor: str = "operator",
        worktree_path: Optional[Union[str, Path]] = None,
        checks: Optional[Sequence[CheckSpec]] = None,
        commit_message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RepairResult:
        """Finalize a manual conflict resolution after verifying clean tree and passing checks."""
        return await self.resolve_manual(
            conflict_id,
            actor=actor,
            finalize=True,
            worktree_path=worktree_path,
            checks=checks,
            commit_message=commit_message,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    async def discard(
        self,
        conflict_id: str,
        *,
        actor: str = "operator",
        reason: str = "operator_discarded",
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RepairResult:
        """Discard a conflicted integration without touching the operator's active branch."""
        report = await self.get_report(conflict_id)
        req_hash = self.store.compute_request_hash(
            {
                "op": "discard",
                "conflict_id": conflict_id,
                "actor": actor,
                "reason": reason,
            }
        )

        async with self.store._connect() as db:
            cached = await self._check_idempotency(db, idempotency_key=idempotency_key, request_hash=req_hash)
            if cached is not None:
                return _parse_command_model(RepairResult, cached)

        self._validate_conflict_transition(report.status, "discarded", report.resolved_at)

        run_rec = await self.store.get_run(report.run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{report.run_id}' does not exist")
        git_ws = self._get_git_workspace(run_rec["spec"].repo_root)
        snap_before = git_ws.snapshot_operator_checkout()

        resolved_at = _utc_now_iso()
        res_discard = RepairResult(
            conflict_id=conflict_id,
            integration_id=report.integration_id,
            run_id=report.run_id,
            option="discarded",
            status="discarded",
            repaired=False,
            attempt_number=report.repair_attempts_used,
            repair_worktree_path=report.repair_worktree_path,
            repair_branch=report.repair_branch,
            resolved_sha=None,
            resolved_at=resolved_at,
        )

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE conflict_reports SET status = 'discarded', resolved_at = ? WHERE id = ?",
                    (resolved_at, conflict_id),
                )
                await db.execute(
                    "UPDATE integrations SET status = 'discarded' WHERE id = ?",
                    (report.integration_id,),
                )
                await self._record_audit_in_tx(
                    db,
                    run_id=report.run_id,
                    action="discarded",
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    status="completed",
                    payload={
                        **res_discard.model_dump(mode="json"),
                        "action": "conflict.discarded",
                        "actor": actor,
                        "reason": redact_text(reason),
                    },
                    event_type="merge.conflict_discarded",
                    event_payload={
                        "conflict_id": conflict_id,
                        "integration_id": report.integration_id,
                        "status": "discarded",
                        "actor": actor,
                        "reason": redact_text(reason),
                        "resolved_at": resolved_at,
                    },
                    correlation_id=correlation_id,
                )

        git_ws.assert_operator_checkout_intact(snap_before)
        return res_discard

    # -------------------------------------------------------------------------
    # Wave 0 Contract Amendment Protocol (RT28 / PRD §3.6.3)
    # -------------------------------------------------------------------------

    async def _assert_amendment_authorized(
        self,
        db: Any,
        *,
        actor: str,
        authorized_actors: Optional[Sequence[str]],
        authorization_id: Optional[str],
    ) -> None:
        if not actor or not actor.strip():
            raise ContractViolation("authorization_denied", "Non-empty actor is required for contract amendment")
        if authorized_actors is not None and actor not in authorized_actors:
            raise ContractViolation(
                "authorization_denied",
                f"Actor '{actor}' is not authorized for Wave 0 contract amendment",
            )
        if authorization_id is not None:
            auth_row = await (
                await db.execute(
                    "SELECT principal_id, scopes_json, revoked_at FROM authorizations WHERE id = ?",
                    (authorization_id,),
                )
            ).fetchone()
            if auth_row is None or auth_row["revoked_at"] is not None or auth_row["principal_id"] != actor:
                raise ContractViolation(
                    "authorization_denied",
                    f"Authorization '{authorization_id}' is invalid, revoked, or belongs to another principal",
                )
            scopes = set(json.loads(auth_row["scopes_json"]))
            if not (scopes & {"write", "integrate"}):
                raise ContractViolation(
                    "authorization_denied",
                    f"Authorization '{authorization_id}' lacks 'write' or 'integrate' scope",
                )

    async def _find_dependent_tasks(self, db: Any, run_id: str, root_task_id: str) -> tuple[str, ...]:
        rows = await (
            await db.execute(
                """
                SELECT td.task_id, td.prerequisite_id
                FROM task_dependencies td
                JOIN tasks t ON t.id = td.task_id
                WHERE t.run_id = ?
                """,
                (run_id,),
            )
        ).fetchall()
        children: Dict[str, List[str]] = {}
        for r in rows:
            children.setdefault(r["prerequisite_id"], []).append(r["task_id"])

        visited: set[str] = set()
        queue: List[str] = list(children.get(root_task_id, []))
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            queue.extend(children.get(cur, []))
        return tuple(sorted(visited))

    async def _latest_run_base_sha(self, db: Any, run_id: str, fallback_sha: str) -> str:
        row = await (
            await db.execute(
                """
                SELECT result_sha FROM integrations
                WHERE run_id = ? AND status = 'integrated' AND result_sha IS NOT NULL
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (run_id,),
            )
        ).fetchone()
        if row is not None and row["result_sha"]:
            return str(row["result_sha"])
        return fallback_sha

    async def propose_contract_amendment(
        self,
        run_id: str,
        wave0_task_id: str,
        *,
        reason: str,
        target_files: Sequence[str],
        summary: str,
        actor: str,
        expected_run_revision: int,
        requested_by_task_id: Optional[str] = None,
        authorized_actors: Optional[Sequence[str]] = None,
        authorization_id: Optional[str] = None,
        transition_requester_needs_context: bool = False,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> ContractAmendmentProposal:
        """
        Propose a Contract Amendment to a Wave 0 foundation task, validating revision,
        authorization, and identifying dependent Wave 1 tasks requiring revalidation.
        """
        await self.store.initialize()
        norm_targets = tuple(_normalize_rel_posix(p) for p in target_files if _normalize_rel_posix(p))
        if not norm_targets:
            raise ContractViolation("amendment_invalid", "target_files must contain at least one relative path")

        req_hash = self.store.compute_request_hash(
            {
                "op": "propose_contract_amendment",
                "run_id": run_id,
                "wave0_task_id": wave0_task_id,
                "requested_by_task_id": requested_by_task_id,
                "actor": actor,
                "expected_run_revision": expected_run_revision,
                "reason": reason,
                "target_files": list(norm_targets),
                "summary": summary,
            }
        )

        async with self.store._connect() as db:
            cached = await self._check_idempotency(db, idempotency_key=idempotency_key, request_hash=req_hash)
            if cached is not None:
                return _parse_command_model(ContractAmendmentProposal, cached)

            async with self.store._transaction(db):
                await self._assert_amendment_authorized(
                    db,
                    actor=actor,
                    authorized_actors=authorized_actors,
                    authorization_id=authorization_id,
                )
                run_row = await (
                    await db.execute("SELECT id, base_sha, status, revision, spec_json FROM runs WHERE id = ?", (run_id,))
                ).fetchone()
                if run_row is None:
                    raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
                if int(run_row["revision"]) != expected_run_revision:
                    raise OptimisticLockError(
                        f"Optimistic lock failed for run '{run_id}': "
                        f"expected revision {expected_run_revision}, found {run_row['revision']}"
                    )

                w0_row = await (
                    await db.execute("SELECT id, run_id, spec_json, status FROM tasks WHERE id = ?", (wave0_task_id,))
                ).fetchone()
                if w0_row is None or w0_row["run_id"] != run_id:
                    raise ContractViolation("resource_not_found", f"Wave 0 task '{wave0_task_id}' not found in run '{run_id}'")
                w0_spec = TaskSpec.model_validate_json(w0_row["spec_json"])
                if w0_spec.dependencies:
                    raise ContractViolation(
                        "invalid_wave0_task",
                        f"Task '{wave0_task_id}' has dependencies and is not a Wave 0 foundation task",
                    )

                for tf in norm_targets:
                    if not GitWorkspaceService._matches_any_pattern(tf, w0_spec.allowed_paths):
                        raise ContractViolation(
                            "scope_violation",
                            f"Target file '{tf}' is outside Wave 0 task '{wave0_task_id}' allowed_paths",
                        )

                if requested_by_task_id is not None:
                    req_row = await (
                        await db.execute(
                            "SELECT id, run_id, status, revision FROM tasks WHERE id = ?",
                            (requested_by_task_id,),
                        )
                    ).fetchone()
                    if req_row is None or req_row["run_id"] != run_id:
                        raise ContractViolation(
                            "resource_not_found",
                            f"Requesting task '{requested_by_task_id}' not found in run '{run_id}'",
                        )
                    if transition_requester_needs_context and req_row["status"] == TaskStatus.RUNNING.value:
                        transition_status(TaskStatus.RUNNING, TaskStatus.NEEDS_CONTEXT)
                        await db.execute(
                            "UPDATE tasks SET status = 'needs_context', revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                            (requested_by_task_id,),
                        )

                affected_wave1 = await self._find_dependent_tasks(db, run_id, wave0_task_id)
                base_sha_before = await self._latest_run_base_sha(db, run_id, run_row["base_sha"])

                amendment_id = f"amd-{new_id()}"
                created_at = _utc_now_iso()
                proposal = ContractAmendmentProposal(
                    amendment_id=amendment_id,
                    run_id=run_id,
                    wave0_task_id=wave0_task_id,
                    requested_by_task_id=requested_by_task_id,
                    actor=redact_text(actor),
                    expected_run_revision=expected_run_revision,
                    reason=redact_text(reason),
                    target_files=norm_targets,
                    summary=redact_text(summary),
                    status="proposed",
                    base_sha_before=base_sha_before,
                    affected_wave1_task_ids=affected_wave1,
                    created_at=created_at,
                )

                await self._record_audit_in_tx(
                    db,
                    run_id=run_id,
                    action="contract_amendment_proposed",
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    status="pending",
                    payload={
                        **proposal.model_dump(mode="json"),
                        "action": "contract_amendment.proposed",
                    },
                    event_type="contract.amendment_proposed",
                    event_payload={
                        "amendment_id": amendment_id,
                        "wave0_task_id": wave0_task_id,
                        "requested_by_task_id": requested_by_task_id,
                        "actor": proposal.actor,
                        "expected_run_revision": expected_run_revision,
                        "target_files": list(norm_targets),
                        "affected_wave1_task_ids": list(affected_wave1),
                        "base_sha_before": base_sha_before,
                    },
                    task_id=requested_by_task_id or wave0_task_id,
                    correlation_id=correlation_id,
                )
                return proposal

    async def get_amendment(self, amendment_id: str) -> ContractAmendmentProposal:
        """Load the latest persisted state of a ContractAmendmentProposal."""
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute(
                    """
                    SELECT response_json FROM commands
                    WHERE scope = 'conflict_resolver'
                      AND json_extract(response_json, '$.amendment_id') = ?
                    ORDER BY rowid DESC LIMIT 1
                    """,
                    (amendment_id,),
                )
            ).fetchone()
            if row is None or not row["response_json"]:
                raise ContractViolation("resource_not_found", f"Contract amendment '{amendment_id}' does not exist")
            return _parse_command_model(ContractAmendmentProposal, row["response_json"])

    async def get_pending_revalidations(self, run_id: str) -> tuple[str, ...]:
        """Return Wave 1 task IDs currently marked for revalidation due to an applied Contract Amendment."""
        await self.store.initialize()
        async with self.store._connect() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT response_json FROM commands
                    WHERE scope = 'conflict_resolver' AND run_id = ?
                    ORDER BY rowid ASC
                    """,
                    (run_id,),
                )
            ).fetchall()
        pending: set[str] = set()
        for row in rows:
            if not row["response_json"]:
                continue
            data = json.loads(row["response_json"])
            action = data.get("action")
            if action == "contract_amendment.applied":
                pending.update(data.get("affected_wave1_task_ids", []))
            elif action == "contract_amendment.task_revalidated" and data.get("task_id"):
                pending.discard(data["task_id"])
        return tuple(sorted(pending))

    async def mark_task_revalidated(
        self,
        run_id: str,
        task_id: str,
        *,
        tested_sha: str,
        actor: str = "coordinator",
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> tuple[str, ...]:
        """Clear revalidation requirement for a Wave 1 task after it has been revalidated against the amended base SHA."""
        await self.store.initialize()
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
        git_ws = self._get_git_workspace(run_rec["spec"].repo_root)
        verified_sha = git_ws.resolve_commit_sha(tested_sha, cwd=git_ws.repo_root)
        if verified_sha != run_rec["base_sha"]:
            raise ContractViolation(
                "revalidation_base_mismatch",
                f"Task '{task_id}' revalidation SHA '{verified_sha}' does not match current run base_sha '{run_rec['base_sha']}'",
            )

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._record_audit_in_tx(
                    db,
                    run_id=run_id,
                    action="task_revalidated",
                    idempotency_key=idempotency_key,
                    payload={
                        "action": "contract_amendment.task_revalidated",
                        "run_id": run_id,
                        "task_id": task_id,
                        "tested_sha": verified_sha,
                        "actor": actor,
                    },
                    event_type="check.finished",
                    event_payload={
                        "action": "contract_amendment.task_revalidated",
                        "task_id": task_id,
                        "tested_sha": verified_sha,
                        "actor": actor,
                    },
                    task_id=task_id,
                    correlation_id=correlation_id,
                )
        return await self.get_pending_revalidations(run_id)

    async def apply_contract_amendment(
        self,
        amendment_id: str,
        *,
        actor: str,
        expected_run_revision: int,
        amend_fn: Optional[Callable[[Path, ContractAmendmentProposal], Any]] = None,
        patch_files: Optional[Mapping[str, str]] = None,
        amend_command: Optional[Sequence[str]] = None,
        checks: Optional[Sequence[CheckSpec]] = None,
        authorized_actors: Optional[Sequence[str]] = None,
        authorization_id: Optional[str] = None,
        active_worktrees: Sequence[Union[WorkspaceRecord, Path]] = (),
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> ContractAmendmentProposal:
        """
        Apply a proposed Wave 0 Contract Amendment in an isolated worktree, verify mandatory
        checks, advance run revision & integration base SHA, rebase active worktrees if provided,
        and mark dependent Wave 1 tasks for revalidation before proceeding.
        """
        proposal = await self.get_amendment(amendment_id)
        req_hash = self.store.compute_request_hash(
            {
                "op": "apply_contract_amendment",
                "amendment_id": amendment_id,
                "actor": actor,
                "expected_run_revision": expected_run_revision,
                "patch_files": dict(patch_files) if patch_files else None,
                "amend_command": list(amend_command) if amend_command else None,
            }
        )

        async with self.store._connect() as db:
            cached = await self._check_idempotency(db, idempotency_key=idempotency_key, request_hash=req_hash)
            if cached is not None:
                return _parse_command_model(ContractAmendmentProposal, cached)

            await self._assert_amendment_authorized(
                db,
                actor=actor,
                authorized_actors=authorized_actors,
                authorization_id=authorization_id,
            )

        if proposal.status != "proposed":
            raise ContractViolation(
                "amendment_not_proposed",
                f"Contract amendment '{amendment_id}' is in status '{proposal.status}' and cannot be applied",
            )

        run_rec = await self.store.get_run(proposal.run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{proposal.run_id}' does not exist")
        if int(run_rec["revision"]) != expected_run_revision:
            raise OptimisticLockError(
                f"Optimistic lock failed for run '{proposal.run_id}': "
                f"expected revision {expected_run_revision}, found {run_rec['revision']}"
            )
        run_spec: RunSpec = run_rec["spec"]
        git_ws = self._get_git_workspace(run_spec.repo_root)
        snap_before = git_ws.snapshot_operator_checkout()

        w0_rec = await self.store.get_task(proposal.wave0_task_id)
        if w0_rec is None:
            raise StorageIntegrityError(f"Wave 0 task '{proposal.wave0_task_id}' does not exist")
        w0_spec: TaskSpec = w0_rec["spec"]

        # Create isolated amendment worktree anchored at proposal.base_sha_before
        ws_record = git_ws.create_merge_repair_worktree(
            run_id=proposal.run_id,
            conflict_id=amendment_id,
            attempt_ordinal=1,
            ours_sha=proposal.base_sha_before,
            theirs_sha=None,
            populate_conflict=False,
            branch_name=f"amend/{_sanitize_token(proposal.run_id)[:16]}/{_sanitize_token(amendment_id)[:16]}",
            prefix="amend",
        )

        try:
            if patch_files:
                for rel_raw, content in patch_files.items():
                    rel_norm = _normalize_rel_posix(rel_raw)
                    target = ws_record.canonical_path / rel_norm
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
            elif amend_fn is not None:
                res_fn = amend_fn(ws_record.canonical_path, proposal)
                if asyncio.iscoroutine(res_fn):
                    await res_fn
            elif amend_command is not None:
                rc, _, err = await self._run_repair_command(
                    amend_command,
                    ws_record.canonical_path,
                    proposal.summary,
                )
                if rc != 0:
                    raise ContractViolation(
                        "amendment_command_failed",
                        f"Amendment command exited with code {rc}: {redact_text(err).strip()}",
                    )
            else:
                raise ContractViolation(
                    "amendment_handler_missing",
                    "Applying a contract amendment requires patch_files, amend_fn, or amend_command",
                )

            scope = git_ws.validate_worktree_scope(
                ws_record.canonical_path,
                base_sha=proposal.base_sha_before,
                allowed_paths=proposal.target_files,
            )
            if not scope.valid:
                raise ContractViolation(
                    "scope_violation",
                    f"Contract amendment modified files outside target_files: {', '.join(scope.violations)}",
                )
            if not scope.changed_files:
                raise ContractViolation(
                    "empty_patch",
                    "Contract amendment produced no changes in the isolated worktree",
                )

            new_base_sha = git_ws.commit_resolved_worktree(
                ws_record.canonical_path,
                commit_message=f"feat(contract-amendment): {proposal.summary}",
            )

            effective_checks = tuple(checks) if checks is not None else w0_spec.acceptance_criteria
            check_runner = self._get_check_runner(git_ws)
            executed_checks, check_artifacts = await check_runner.run_checks(
                run_id=proposal.run_id,
                attempt_id=None,
                workspace_path=ws_record.canonical_path,
                tested_sha=new_base_sha,
                checks=effective_checks,
                scope_prefix=f"amd-{_short_token(amendment_id)}",
            )
            failed_checks = [c for c in executed_checks if c.exit_code != 0]
            if failed_checks:
                async with self.store._connect() as db:
                    async with self.store._transaction(db):
                        for art in check_artifacts:
                            await self.store._upsert_artifact_in_tx(db, art)
                        await self._record_audit_in_tx(
                            db,
                            run_id=proposal.run_id,
                            action="contract_amendment_check_failed",
                            status="failed",
                            payload={
                                "action": "contract_amendment.check_failed",
                                "amendment_id": amendment_id,
                                "failed_checks": [c.check_id for c in failed_checks],
                                "tested_sha": new_base_sha,
                                "actor": actor,
                            },
                            event_type="check.finished",
                            event_payload={
                                "amendment_id": amendment_id,
                                "passed": False,
                                "failed_checks": [c.check_id for c in failed_checks],
                                "tested_sha": new_base_sha,
                            },
                            task_id=proposal.wave0_task_id,
                            correlation_id=correlation_id,
                        )
                raise ContractViolation(
                    "amendment_check_failed",
                    f"Wave 0 checks failed on contract amendment: {', '.join(c.check_id for c in failed_checks)}",
                )

            # Rebase active Wave 1 worktrees onto the verified new_base_sha (never touching repo_root)
            rebased_paths: List[str] = []
            conflicted_paths: List[str] = []
            for wt_item in active_worktrees:
                wt_p = wt_item.canonical_path if isinstance(wt_item, WorkspaceRecord) else Path(wt_item)
                ok, _, _ = git_ws.update_worktree_base(wt_p, new_base_sha)
                if ok:
                    rebased_paths.append(str(wt_p))
                else:
                    conflicted_paths.append(str(wt_p))

            applied_at = _utc_now_iso()
            integration_id = f"int-amend-{_sanitize_token(amendment_id)[:24]}"

            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    upd_run = await db.execute(
                        """
                        UPDATE runs
                        SET base_sha = ?, revision = revision + 1, updated_at = datetime('now')
                        WHERE id = ? AND revision = ?
                        """,
                        (new_base_sha, proposal.run_id, expected_run_revision),
                    )
                    if upd_run.rowcount != 1:
                        raise OptimisticLockError(
                            f"Concurrent modification detected on run '{proposal.run_id}' while applying amendment"
                        )

                    await db.execute(
                        """
                        INSERT INTO integrations (id, run_id, workspace_path, expected_base_sha, result_sha, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'integrated', datetime('now'))
                        """,
                        (
                            integration_id,
                            proposal.run_id,
                            str(ws_record.canonical_path),
                            proposal.base_sha_before,
                            new_base_sha,
                        ),
                    )
                    await self._persist_check_evidence_in_tx(
                        db,
                        integration_id=integration_id,
                        checks_executed=executed_checks,
                        artifacts=check_artifacts,
                    )

                    # Mark dependent Wave 1 tasks for revalidation
                    for dep_tid in proposal.affected_wave1_task_ids:
                        t_row = await (
                            await db.execute("SELECT status, revision FROM tasks WHERE id = ?", (dep_tid,))
                        ).fetchone()
                        if t_row is None:
                            continue
                        cur_st = TaskStatus(t_row["status"])
                        if cur_st in {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.NEEDS_CONTEXT}:
                            target_st = transition_status(cur_st, TaskStatus.BLOCKED)
                            await db.execute(
                                "UPDATE tasks SET status = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                                (target_st.value, dep_tid),
                            )
                        elif cur_st == TaskStatus.READY_FOR_REVIEW:
                            target_st = transition_status(cur_st, TaskStatus.REJECTED)
                            await db.execute(
                                "UPDATE tasks SET status = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                                (target_st.value, dep_tid),
                            )
                        elif cur_st == TaskStatus.BLOCKED:
                            await db.execute(
                                "UPDATE tasks SET revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                                (dep_tid,),
                            )
                        # ACCEPTED tasks cannot transition in TaskStatus._TRANSITIONS; they remain tracked
                        # in get_pending_revalidations(run_id) and require re-verification against new_base_sha.

                    applied = ContractAmendmentProposal(
                        amendment_id=proposal.amendment_id,
                        run_id=proposal.run_id,
                        wave0_task_id=proposal.wave0_task_id,
                        requested_by_task_id=proposal.requested_by_task_id,
                        actor=redact_text(actor),
                        expected_run_revision=expected_run_revision,
                        reason=proposal.reason,
                        target_files=proposal.target_files,
                        summary=proposal.summary,
                        status="applied",
                        base_sha_before=proposal.base_sha_before,
                        base_sha_after=new_base_sha,
                        run_revision_after=expected_run_revision + 1,
                        affected_wave1_task_ids=proposal.affected_wave1_task_ids,
                        revalidated_worktrees=tuple(rebased_paths),
                        conflicted_worktrees=tuple(conflicted_paths),
                        checks_executed=executed_checks,
                        artifacts=check_artifacts,
                        created_at=proposal.created_at,
                        applied_at=applied_at,
                    )

                    await self._record_audit_in_tx(
                        db,
                        run_id=proposal.run_id,
                        action="contract_amendment_applied",
                        idempotency_key=idempotency_key,
                        request_hash=req_hash,
                        status="completed",
                        payload={
                            **applied.model_dump(mode="json"),
                            "action": "contract_amendment.applied",
                            "integration_id": integration_id,
                        },
                        event_type="contract.amended",
                        event_payload={
                            "amendment_id": amendment_id,
                            "integration_id": integration_id,
                            "wave0_task_id": proposal.wave0_task_id,
                            "actor": applied.actor,
                            "base_sha_before": proposal.base_sha_before,
                            "base_sha_after": new_base_sha,
                            "run_revision_after": expected_run_revision + 1,
                            "affected_wave1_task_ids": list(proposal.affected_wave1_task_ids),
                            "revalidated_worktrees": rebased_paths,
                            "conflicted_worktrees": conflicted_paths,
                        },
                        task_id=proposal.wave0_task_id,
                        correlation_id=correlation_id,
                    )

            git_ws.assert_operator_checkout_intact(snap_before)
            return applied
        except Exception:
            git_ws.assert_operator_checkout_intact(snap_before)
            raise


__all__ = [
    "ConflictReport",
    "ConflictResolver",
    "ConflictStatus",
    "ConflictedFileDetail",
    "ContractAmendmentProposal",
    "RESOLUTION_OPTIONS",
    "RepairResult",
    "ResolutionOption",
]
