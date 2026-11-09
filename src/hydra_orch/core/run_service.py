"""Deterministic CheckRunner and application RunService coordinating execution, review, and integration (S05 / T06)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import uuid

from hydra_orch.bridge.worker_runner import (
    WorkerRunner,
    cancel_process_tree,
    filter_worker_env,
)
from hydra_orch.core.checkpointer import (
    ExecutionStore,
    OptimisticLockError,
    StorageIntegrityError,
)
from hydra_orch.core.git_workspace import (
    GitWorkspaceError,
    GitWorkspaceService,
    IntegrationOutcome,
    WorkspaceRecord,
)
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import (
    Artifact,
    CheckResult,
    CheckSpec,
    ContractViolation,
    FailureDetail,
    IntegrationStatus,
    ProcessStatus,
    ReviewDecision,
    RunSpec,
    RunStatus,
    TaskAttempt,
    TaskResult,
    TaskSpec,
    TaskStatus,
    assert_integrable,
    transition_status,
    validate_result,
)

logger = logging.getLogger(__name__)

_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RE.sub("_", value.strip())
    return cleaned.strip("._-") or "item"


def _normalize_rel_posix(path_str: str) -> str:
    normalized = path_str.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _write_check_artifact_atomic(
    target_path: Path,
    content: bytes,
    *,
    artifact_id: str,
    run_id: str,
    attempt_id: Optional[str],
    relative_path: str,
) -> Artifact:
    content = redact_text(content.decode("utf-8", errors="replace")).encode("utf-8")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp_path, "wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target_path)
    digest = hashlib.sha256(content).hexdigest()
    return Artifact(
        artifact_id=artifact_id,
        run_id=run_id,
        attempt_id=attempt_id,
        relative_path=relative_path,
        kind="check_output",
        sha256=digest,
        size_bytes=len(content),
    )


@dataclass(frozen=True)
class TaskExecutionOutcome:
    """Complete outcome of executing a single TaskAttempt through WorkerRunner, GitWorkspaceService, and CheckRunner."""

    run_id: str
    task_id: str
    attempt: TaskAttempt
    workspace: WorkspaceRecord
    result: TaskResult
    worker_raw: Dict[str, Any]


class CheckRunner:
    """
    Executes CheckSpec commands deterministically as argv arrays (without shell) inside a target workspace,
    capturing stdout/stderr as SHA-256 artifacts and binding results to tested_sha (RT06 / T06.1).
    """

    def __init__(
        self,
        repo_root: Union[str, Path],
        runtime_dir: Union[str, Path] = ".orchestrator",
        default_timeout_seconds: float = 120.0,
    ):
        self.repo_root = Path(os.path.realpath(repo_root))
        rt_candidate = Path(runtime_dir)
        if not rt_candidate.is_absolute():
            rt_candidate = self.repo_root / rt_candidate
        self.runtime_dir = Path(os.path.realpath(rt_candidate))
        self.default_timeout_seconds = default_timeout_seconds

    async def run_checks(
        self,
        *,
        run_id: str,
        attempt_id: Optional[str],
        workspace_path: Union[str, Path],
        tested_sha: str,
        checks: Sequence[CheckSpec],
        scope_prefix: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        allowed_env: Optional[Mapping[str, str]] = None,
    ) -> Tuple[Tuple[CheckResult, ...], Tuple[Artifact, ...]]:
        """Execute a sequence of CheckSpecs and return (check_results, artifacts)."""
        ws_real = Path(os.path.realpath(workspace_path))
        if not ws_real.exists() or not ws_real.is_dir():
            raise ContractViolation(
                "workspace_invalid",
                f"Check workspace directory does not exist: '{ws_real}'",
            )

        safe_run = _sanitize_token(run_id)
        safe_scope = _sanitize_token(scope_prefix or attempt_id or "integration")
        checks_dir = self.runtime_dir / "run" / safe_run / "checks" / safe_scope
        checks_dir.mkdir(parents=True, exist_ok=True)

        env = filter_worker_env(allowed_env=allowed_env)
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        effective_timeout = timeout_seconds or self.default_timeout_seconds

        results: List[CheckResult] = []
        artifacts: List[Artifact] = []

        for spec in checks:
            if spec.cwd:
                target_cwd = Path(os.path.realpath(ws_real / spec.cwd))
                ws_norm = os.path.normcase(str(ws_real))
                cwd_norm = os.path.normcase(str(target_cwd))
                if not (cwd_norm == ws_norm or cwd_norm.startswith(ws_norm + os.sep)):
                    raise ContractViolation(
                        "scope_violation",
                        f"Check '{spec.check_id}' cwd '{spec.cwd}' escapes workspace '{ws_real}'",
                    )
            else:
                target_cwd = ws_real

            t0 = time.perf_counter()
            stdout_bytes = b""
            stderr_bytes = b""
            exit_code = -1
            proc: Optional[asyncio.subprocess.Process] = None

            try:
                kwargs: Dict[str, Any] = {
                    "cwd": str(target_cwd),
                    "stdin": asyncio.subprocess.DEVNULL,
                    "stdout": asyncio.subprocess.PIPE,
                    "stderr": asyncio.subprocess.PIPE,
                    "env": env,
                }
                if os.name != "nt":
                    kwargs["start_new_session"] = True
                else:
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

                proc = await asyncio.create_subprocess_exec(*spec.command, **kwargs)
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=effective_timeout,
                )
                exit_code = int(proc.returncode if proc.returncode is not None else 1)
            except asyncio.TimeoutError:
                if proc is not None and proc.pid:
                    await cancel_process_tree(proc.pid)
                stderr_bytes = (
                    stderr_bytes
                    + f"\nCheck '{spec.check_id}' timed out after {effective_timeout}s\n".encode("utf-8")
                )
                exit_code = 124
            except FileNotFoundError as exc:
                stderr_bytes = f"Check executable not found: {exc}\n".encode("utf-8")
                exit_code = 127
            except Exception as exc:
                stderr_bytes = f"Check execution failed: {exc}\n".encode("utf-8")
                exit_code = 1

            duration = max(time.perf_counter() - t0, 0.0)
            safe_chk = _sanitize_token(spec.check_id)
            stdout_file = checks_dir / f"{safe_chk}.stdout.log"
            stderr_file = checks_dir / f"{safe_chk}.stderr.log"

            try:
                stdout_rel = _normalize_rel_posix(str(stdout_file.relative_to(self.repo_root)))
                stderr_rel = _normalize_rel_posix(str(stderr_file.relative_to(self.repo_root)))
            except ValueError:
                stdout_rel = f".orchestrator/run/{safe_run}/checks/{safe_scope}/{safe_chk}.stdout.log"
                stderr_rel = f".orchestrator/run/{safe_run}/checks/{safe_scope}/{safe_chk}.stderr.log"

            stdout_art_id = f"art-chk-{safe_scope}-{safe_chk}-stdout"
            stderr_art_id = f"art-chk-{safe_scope}-{safe_chk}-stderr"

            stdout_art = _write_check_artifact_atomic(
                stdout_file,
                stdout_bytes,
                artifact_id=stdout_art_id,
                run_id=run_id,
                attempt_id=attempt_id,
                relative_path=stdout_rel,
            )
            stderr_art = _write_check_artifact_atomic(
                stderr_file,
                stderr_bytes,
                artifact_id=stderr_art_id,
                run_id=run_id,
                attempt_id=attempt_id,
                relative_path=stderr_rel,
            )
            artifacts.extend((stdout_art, stderr_art))

            results.append(
                CheckResult(
                    check_id=spec.check_id,
                    command=spec.command,
                    cwd=spec.cwd,
                    tested_sha=tested_sha,
                    exit_code=exit_code,
                    duration_seconds=duration,
                    stdout_artifact_id=stdout_art.artifact_id,
                    stderr_artifact_id=stderr_art.artifact_id,
                )
            )

        return tuple(results), tuple(artifacts)


class RunService:
    """
    Canonical application service coordinating run submission, isolated worktree execution,
    deterministic check validation, optimistic review, serialized integration, retry, and cancellation (T06).
    """

    def __init__(
        self,
        repo_root: Union[str, Path],
        store: Optional[ExecutionStore] = None,
        git_workspace: Optional[GitWorkspaceService] = None,
        worker_runner: Optional[WorkerRunner] = None,
        check_runner: Optional[CheckRunner] = None,
        runtime_dir: Union[str, Path] = ".orchestrator",
    ):
        self.repo_root = GitWorkspaceService.resolve_repo_root(repo_root)
        rt_candidate = Path(runtime_dir)
        if not rt_candidate.is_absolute():
            rt_candidate = self.repo_root / rt_candidate
        self.runtime_dir = Path(os.path.realpath(rt_candidate))

        self.store = store or ExecutionStore(
            db_path=self.runtime_dir / "checkpoints.sqlite",
        )
        self.git_workspace = git_workspace or GitWorkspaceService(
            repo_root=self.repo_root,
            runtime_dir=self.runtime_dir,
            store=self.store,
        )
        if self.git_workspace.store is None:
            self.git_workspace.store = self.store
        self.worker_runner = worker_runner or WorkerRunner()
        self.check_runner = check_runner or CheckRunner(
            repo_root=self.repo_root,
            runtime_dir=self.runtime_dir,
        )
        self._workspaces_by_root: Dict[str, GitWorkspaceService] = {
            os.path.normcase(str(self.repo_root)): self.git_workspace
        }
        self._check_runners_by_root: Dict[str, CheckRunner] = {
            os.path.normcase(str(self.repo_root)): self.check_runner
        }
        self._project_meta: Dict[str, Dict[str, str]] = {}

    def _get_git_workspace(self, repo_root: Union[str, Path]) -> GitWorkspaceService:
        resolved = GitWorkspaceService.resolve_repo_root(repo_root)
        key = os.path.normcase(str(resolved))
        ws = self._workspaces_by_root.get(key)
        if ws is None:
            rt_dir = resolved / ".orchestrator" if resolved != self.repo_root else self.runtime_dir
            ws = GitWorkspaceService(
                repo_root=resolved,
                runtime_dir=rt_dir,
                store=self.store,
            )
            self._workspaces_by_root[key] = ws
        return ws

    def _get_check_runner(self, repo_root: Union[str, Path]) -> CheckRunner:
        resolved = GitWorkspaceService.resolve_repo_root(repo_root)
        key = os.path.normcase(str(resolved))
        cr = self._check_runners_by_root.get(key)
        if cr is None:
            rt_dir = resolved / ".orchestrator" if resolved != self.repo_root else self.runtime_dir
            cr = CheckRunner(
                repo_root=resolved,
                runtime_dir=rt_dir,
            )
            self._check_runners_by_root[key] = cr
        return cr

    async def create_project(
        self,
        canonical_root: Union[str, Path],
        name: str,
        base_branch: str = "main",
        base_sha: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate a Git repository root and register it as a project in ExecutionStore."""
        await self.store.initialize()
        raw_str = str(canonical_root).strip()
        if not raw_str or ".." in Path(raw_str).parts:
            raise ContractViolation(
                "workspace_invalid",
                f"Invalid or path-traversal canonical_root: '{canonical_root}'",
            )
        candidate = Path(os.path.realpath(raw_str))
        if not candidate.exists() or not candidate.is_dir() or not (candidate / ".git").exists():
            raise ContractViolation(
                "workspace_invalid",
                f"Path '{canonical_root}' is not a valid Git repository root containing .git",
            )
        resolved_root = GitWorkspaceService.resolve_repo_root(candidate)
        if os.path.normcase(str(resolved_root)) != os.path.normcase(str(candidate)):
            raise ContractViolation(
                "workspace_invalid",
                f"Path '{canonical_root}' is not the top-level Git root ('{resolved_root}')",
            )

        ws = self._get_git_workspace(resolved_root)
        if base_sha:
            resolved_sha = ws.resolve_commit_sha(base_sha)
        else:
            try:
                resolved_sha = ws.resolve_commit_sha(base_branch)
            except (ContractViolation, GitWorkspaceError):
                resolved_sha = ws.resolve_commit_sha("HEAD")

        pid = project_id or f"proj-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                cur = await db.execute(
                    "SELECT id, canonical_root FROM projects WHERE id = ? OR canonical_root = ?",
                    (pid, str(resolved_root)),
                )
                existing = await cur.fetchone()
                if existing is not None:
                    raise StorageIntegrityError(
                        f"Project already registered for root '{resolved_root}' (id={existing['id']})"
                    )
                await db.execute(
                    """
                    INSERT INTO projects (id, canonical_root, name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pid, str(resolved_root), name.strip(), now_iso, now_iso),
                )

        self._project_meta[pid] = {
            "base_branch": base_branch,
            "base_sha": resolved_sha,
        }
        return {
            "id": pid,
            "canonical_root": str(resolved_root),
            "name": name.strip(),
            "base_branch": base_branch,
            "base_sha": resolved_sha,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a registered project by ID."""
        await self.store.initialize()
        async with self.store._connect() as db:
            cur = await db.execute(
                "SELECT id, canonical_root, name, created_at, updated_at FROM projects WHERE id = ?",
                (project_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            meta = self._project_meta.get(project_id, {})
            base_branch = meta.get("base_branch", "main")
            base_sha = meta.get("base_sha")
            if not base_sha:
                try:
                    ws = self._get_git_workspace(row["canonical_root"])
                    base_sha = ws.resolve_commit_sha("HEAD")
                except Exception:
                    base_sha = "0" * 40
            return {
                "id": row["id"],
                "canonical_root": row["canonical_root"],
                "name": row["name"],
                "base_branch": base_branch,
                "base_sha": base_sha,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all registered projects."""
        await self.store.initialize()
        async with self.store._connect() as db:
            cur = await db.execute("SELECT id FROM projects ORDER BY created_at DESC, id ASC")
            ids = [r["id"] for r in await cur.fetchall()]
        projects: List[Dict[str, Any]] = []
        for pid in ids:
            proj = await self.get_project(pid)
            if proj is not None:
                projects.append(proj)
        return projects

    async def submit_run(
        self,
        run_spec: RunSpec,
        *,
        request_hash: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Validate repository and base_sha, then persist RunSpec idempotently in ExecutionStore."""
        await self.store.initialize()
        resolved_root = GitWorkspaceService.resolve_repo_root(run_spec.repo_root)
        if os.path.normcase(str(resolved_root)) != os.path.normcase(str(self.repo_root)):
            proj = await self.get_project(run_spec.project_id)
            if proj is None or os.path.normcase(str(proj["canonical_root"])) != os.path.normcase(str(resolved_root)):
                raise ContractViolation(
                    "workspace_invalid",
                    f"RunSpec repo_root '{resolved_root}' does not match service repo_root '{self.repo_root}'",
                )
        ws = self._get_git_workspace(resolved_root)
        verified_sha = ws.resolve_commit_sha(run_spec.base_sha)
        if verified_sha != run_spec.base_sha:
            raise ContractViolation(
                "base_sha_mismatch",
                f"RunSpec base_sha '{run_spec.base_sha}' did not resolve to exact commit '{verified_sha}'",
            )
        return await self.store.submit_run_idempotent(
            run_spec,
            request_hash=request_hash,
            initial_status=RunStatus.QUEUED,
            correlation_id=correlation_id,
        )

    async def _ensure_run_running(
        self,
        run_id: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")
        current_status = RunStatus(run_rec["status"])
        if current_status == RunStatus.RUNNING:
            return run_rec
        if current_status in {RunStatus.QUEUED, RunStatus.WAITING, RunStatus.REVIEWING}:
            ev_type = "run.started" if current_status == RunStatus.QUEUED else "run.resumed"
            return await self.store.update_run_status_atomic(
                run_id=run_id,
                new_status=RunStatus.RUNNING,
                expected_revision=int(run_rec["revision"]),
                event_type=ev_type,
                correlation_id=correlation_id,
            )
        raise ContractViolation(
            "invalid_run_state",
            f"Run '{run_id}' in terminal status '{current_status.value}' cannot start task execution",
        )

    async def _prepare_task_running(
        self,
        run_id: str,
        task_id: str,
        allow_retry_from_terminal: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_rec = await self.store.get_task(task_id)
        if task_rec is None or task_rec["run_id"] != run_id:
            raise StorageIntegrityError(f"Task '{task_id}' not found in run '{run_id}'")

        current_status = TaskStatus(task_rec["status"])
        current_rev = int(task_rec["revision"])

        if current_status == TaskStatus.RUNNING:
            return task_rec

        if current_status in {TaskStatus.PENDING, TaskStatus.NEEDS_CONTEXT, TaskStatus.BLOCKED}:
            return await self.store.update_task_status_atomic(
                task_id=task_id,
                new_status=TaskStatus.RUNNING,
                expected_revision=current_rev,
                event_type="task.started",
                correlation_id=correlation_id,
            )

        if allow_retry_from_terminal and current_status in {
            TaskStatus.FAILED,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
        }:
            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    upd = await db.execute(
                        """
                        UPDATE tasks
                        SET status = ?, revision = revision + 1, updated_at = datetime('now')
                        WHERE id = ? AND revision = ?
                        """,
                        (TaskStatus.RUNNING.value, task_id, current_rev),
                    )
                    if upd.rowcount != 1:
                        raise OptimisticLockError(f"Concurrent modification on task '{task_id}'")
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="task.started",
                        payload={
                            "previous_status": current_status.value,
                            "status": TaskStatus.RUNNING.value,
                            "revision": current_rev + 1,
                            "retry": True,
                        },
                        correlation_id=correlation_id,
                        task_id=task_id,
                    )
            refreshed = await self.store.get_task(task_id)
            assert refreshed is not None
            return refreshed

        raise ContractViolation(
            "invalid_task_state",
            f"Task '{task_id}' in status '{current_status.value}' cannot be started",
        )

    async def execute_task_attempt(
        self,
        run_id: str,
        task_id: str,
        *,
        prompt: Optional[str] = None,
        provider: str = "local_cli",
        model: str = "default",
        dry_run: bool = False,
        custom_command: Optional[Sequence[str]] = None,
        extra_args: Sequence[str] = (),
        forbidden_paths: Sequence[str] = (),
        allowed_env: Optional[Mapping[str, str]] = None,
        allow_retry_from_terminal: bool = False,
        correlation_id: Optional[str] = None,
    ) -> TaskExecutionOutcome:
        """
        Execute a single task attempt inside an isolated Git worktree, validate scope, commit patch,
        run acceptance checks on the resulting commit SHA, and persist TaskResult atomically.
        """
        run_rec = await self._ensure_run_running(run_id, correlation_id=correlation_id)
        run_spec: RunSpec = run_rec["spec"]

        task_rec = await self._prepare_task_running(
            run_id=run_id,
            task_id=task_id,
            allow_retry_from_terminal=allow_retry_from_terminal,
            correlation_id=correlation_id,
        )
        task_spec: TaskSpec = task_rec["spec"]

        prior_attempts = await self.store.list_attempts(task_id)
        if len(prior_attempts) >= run_spec.budget_policy.max_attempts:
            raise ContractViolation(
                "max_attempts_exceeded",
                f"Task '{task_id}' has reached max_attempts ({run_spec.budget_policy.max_attempts})",
            )
        ordinal = (prior_attempts[-1].ordinal + 1) if prior_attempts else 1
        attempt_id = f"att_{_sanitize_token(task_id)}_{ordinal}"
        result_id = f"res_{_sanitize_token(task_id)}_{ordinal}"

        git_ws = self._get_git_workspace(run_spec.repo_root)
        chk_runner = self._get_check_runner(run_spec.repo_root)

        # 1. Create isolated Git worktree at pinned base_sha
        ws_record = git_ws.create_worktree(
            run_id=run_id,
            task_id=task_id,
            attempt_id=attempt_id,
            base_sha=run_spec.base_sha,
        )

        started_dt = datetime.now(timezone.utc)
        running_attempt = TaskAttempt(
            attempt_id=attempt_id,
            task_id=task_id,
            run_id=run_id,
            ordinal=ordinal,
            executor_id=task_spec.assigned_executor,
            provider=provider,
            model=model,
            base_sha=run_spec.base_sha,
            workspace_path=str(ws_record.canonical_path),
            process_status=ProcessStatus.RUNNING,
            started_at=started_dt,
        )
        await self.store.save_attempt_atomic(
            running_attempt,
            event_type="attempt.started",
            correlation_id=correlation_id,
        )
        await git_ws.save_workspace_record(ws_record)

        safe_run = _sanitize_token(run_id)
        safe_att = _sanitize_token(attempt_id)
        logs_dir = git_ws.runtime_dir / "run" / safe_run / "logs" / safe_att
        logs_rel_prefix = f".orchestrator/run/{safe_run}/logs/{safe_att}"

        # 2. Run worker subprocess in worktree
        worker_raw = await self.worker_runner.execute_task_in_worktree(
            ws_record.canonical_path,
            prompt or task_spec.objective,
            cli_name=task_spec.assigned_executor,
            timeout=float(task_spec.timeout_seconds),
            dry_run=dry_run,
            forbidden_files=list(forbidden_paths),
            attempt_id=attempt_id,
            task_id=task_id,
            run_id=run_id,
            ordinal=ordinal,
            provider=provider,
            model=model,
            base_sha=run_spec.base_sha,
            custom_command=custom_command,
            extra_args=extra_args,
            allowed_env=allowed_env,
            artifacts_dir=logs_dir,
            artifacts_rel_prefix=logs_rel_prefix,
        )

        raw_attempt: TaskAttempt = worker_raw["attempt"]
        # Ensure executor_id matches task_spec.assigned_executor for strict attribution validation
        finished_attempt = TaskAttempt(
            attempt_id=raw_attempt.attempt_id,
            task_id=task_spec.task_id,
            run_id=run_id,
            ordinal=ordinal,
            executor_id=task_spec.assigned_executor,
            provider=provider,
            model=model,
            base_sha=run_spec.base_sha,
            workspace_path=str(ws_record.canonical_path),
            provider_session=raw_attempt.provider_session,
            process_status=raw_attempt.process_status,
            exit_code=raw_attempt.exit_code,
            started_at=raw_attempt.started_at or started_dt,
            finished_at=raw_attempt.finished_at or datetime.now(timezone.utc),
            exit_reason=raw_attempt.exit_reason,
        )
        worker_artifacts: List[Artifact] = list(worker_raw.get("artifacts", ()))
        is_simulated = bool(worker_raw.get("simulated", False))

        # 3. Evaluate worker output, scope, diff, and checks
        if is_simulated:
            ws_record.status = "preserved"
            await git_ws.save_workspace_record(ws_record)
            result = TaskResult(
                result_id=result_id,
                attempt_id=attempt_id,
                run_id=run_id,
                base_sha=run_spec.base_sha,
                process_status=finished_attempt.process_status,
                exit_code=finished_attempt.exit_code,
                task_status=TaskStatus.FAILED,
                summary="Dry-run simulated execution completed (not eligible for review or integration)",
                simulated=True,
                artifacts=tuple(worker_artifacts),
                failures=(
                    FailureDetail(
                        code="simulated_execution",
                        message="Simulated dry-run results cannot be promoted to ready_for_review or integrated",
                        retryable=False,
                    ),
                ),
            )
        elif finished_attempt.process_status != ProcessStatus.EXITED or finished_attempt.exit_code != 0:
            ws_record.status = "preserved"
            await git_ws.save_workspace_record(ws_record)
            worker_failure: FailureDetail = worker_raw.get("failure") or FailureDetail(
                code="worker_execution_failed",
                message=f"Worker process terminated with status {finished_attempt.process_status.value}",
                retryable=True,
            )
            target_task_status = (
                TaskStatus.CANCELLED
                if finished_attempt.process_status == ProcessStatus.CANCELLED
                else TaskStatus.FAILED
            )
            result = TaskResult(
                result_id=result_id,
                attempt_id=attempt_id,
                run_id=run_id,
                base_sha=run_spec.base_sha,
                process_status=finished_attempt.process_status,
                exit_code=finished_attempt.exit_code,
                task_status=target_task_status,
                summary=f"Worker execution failed ({worker_failure.code})",
                simulated=False,
                artifacts=tuple(worker_artifacts),
                failures=(worker_failure,),
            )
        else:
            # Worker exited 0 -> validate scope and capture patch
            try:
                diff_art = git_ws.capture_and_commit_patch(
                    ws_record,
                    commit_message=f"feat({task_id}): {task_spec.objective[:72]}",
                    allowed_paths=task_spec.allowed_paths,
                    forbidden_paths=forbidden_paths,
                )
            except GitWorkspaceError as git_err:
                ws_record.status = "preserved"
                await git_ws.save_workspace_record(ws_record)
                result = TaskResult(
                    result_id=result_id,
                    attempt_id=attempt_id,
                    run_id=run_id,
                    base_sha=run_spec.base_sha,
                    process_status=finished_attempt.process_status,
                    exit_code=finished_attempt.exit_code,
                    task_status=TaskStatus.FAILED,
                    summary=f"Scope validation failed: {git_err.failure.message}",
                    simulated=False,
                    artifacts=tuple(worker_artifacts),
                    failures=(git_err.failure,),
                )
            else:
                if not diff_art.has_changes or diff_art.patch_commit_sha is None or diff_art.artifact is None:
                    ws_record.status = "preserved"
                    await git_ws.save_workspace_record(ws_record)
                    result = TaskResult(
                        result_id=result_id,
                        attempt_id=attempt_id,
                        run_id=run_id,
                        base_sha=run_spec.base_sha,
                        process_status=finished_attempt.process_status,
                        exit_code=finished_attempt.exit_code,
                        task_status=TaskStatus.FAILED,
                        summary="Worker exited with code 0 but produced no file modifications",
                        simulated=False,
                        artifacts=tuple(worker_artifacts),
                        failures=(
                            FailureDetail(
                                code="empty_patch",
                                message="Coding task requires attributable file changes; none were produced",
                                retryable=True,
                            ),
                        ),
                    )
                else:
                    # Run acceptance checks against the committed patch SHA
                    await self.store.record_event_atomic(
                        run_id=run_id,
                        event_type="check.started",
                        payload={
                            "tested_sha": diff_art.patch_commit_sha,
                            "check_ids": [c.check_id for c in task_spec.acceptance_criteria],
                        },
                        correlation_id=correlation_id,
                        task_id=task_id,
                        attempt_id=attempt_id,
                    )
                    check_results, check_artifacts = await chk_runner.run_checks(
                        run_id=run_id,
                        attempt_id=attempt_id,
                        workspace_path=ws_record.canonical_path,
                        tested_sha=diff_art.patch_commit_sha,
                        checks=task_spec.acceptance_criteria,
                        scope_prefix=attempt_id,
                        timeout_seconds=float(task_spec.timeout_seconds),
                        allowed_env=allowed_env,
                    )
                    await self.store.record_event_atomic(
                        run_id=run_id,
                        event_type="check.finished",
                        payload={
                            "tested_sha": diff_art.patch_commit_sha,
                            "all_passed": all(c.exit_code == 0 for c in check_results),
                            "checks": [
                                {"check_id": c.check_id, "exit_code": c.exit_code}
                                for c in check_results
                            ],
                        },
                        correlation_id=correlation_id,
                        task_id=task_id,
                        attempt_id=attempt_id,
                    )

                    all_artifacts = (*worker_artifacts, diff_art.artifact, *check_artifacts)
                    failed_checks = [c for c in check_results if c.exit_code != 0]

                    if failed_checks:
                        ws_record.status = "preserved"
                        await git_ws.save_workspace_record(ws_record)
                        failed_ids = ", ".join(c.check_id for c in failed_checks)
                        result = TaskResult(
                            result_id=result_id,
                            attempt_id=attempt_id,
                            run_id=run_id,
                            base_sha=run_spec.base_sha,
                            process_status=finished_attempt.process_status,
                            exit_code=finished_attempt.exit_code,
                            task_status=TaskStatus.FAILED,
                            summary=f"Acceptance checks failed: {failed_ids}",
                            simulated=False,
                            patch_commit_sha=diff_art.patch_commit_sha,
                            patch_artifact_id=diff_art.artifact.artifact_id,
                            changed_files=diff_art.changed_files,
                            checks_executed=check_results,
                            artifacts=all_artifacts,
                            failures=(
                                FailureDetail(
                                    code="acceptance_check_failed",
                                    message=f"Required acceptance checks failed: {failed_ids}",
                                    retryable=True,
                                ),
                            ),
                        )
                    else:
                        result = TaskResult(
                            result_id=result_id,
                            attempt_id=attempt_id,
                            run_id=run_id,
                            base_sha=run_spec.base_sha,
                            process_status=finished_attempt.process_status,
                            exit_code=finished_attempt.exit_code,
                            task_status=TaskStatus.READY_FOR_REVIEW,
                            summary=f"Task '{task_id}' produced verified patch {diff_art.patch_commit_sha[:8]} and passed all checks",
                            simulated=False,
                            patch_commit_sha=diff_art.patch_commit_sha,
                            patch_artifact_id=diff_art.artifact.artifact_id,
                            changed_files=diff_art.changed_files,
                            checks_executed=check_results,
                            artifacts=all_artifacts,
                            failures=(),
                        )

        await self.store.save_task_result_atomic(
            task_spec=task_spec,
            attempt=finished_attempt,
            result=result,
            correlation_id=correlation_id,
        )
        await self._reconcile_run_status_after_task(run_id, correlation_id=correlation_id)

        return TaskExecutionOutcome(
            run_id=run_id,
            task_id=task_id,
            attempt=finished_attempt,
            workspace=ws_record,
            result=result,
            worker_raw=worker_raw,
        )

    async def _reconcile_run_status_after_task(
        self,
        run_id: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")
        current_run_status = RunStatus(run_rec["status"])
        if current_run_status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return run_rec

        tasks = await self.store.list_tasks(run_id)
        statuses = {TaskStatus(t["status"]) for t in tasks}

        if statuses and statuses.issubset({TaskStatus.READY_FOR_REVIEW, TaskStatus.ACCEPTED}):
            if current_run_status == RunStatus.RUNNING:
                return await self.store.update_run_status_atomic(
                    run_id=run_id,
                    new_status=RunStatus.REVIEWING,
                    expected_revision=int(run_rec["revision"]),
                    event_type="run.waiting",
                    event_payload={"reason": "ready_for_review"},
                    correlation_id=correlation_id,
                )
        return run_rec

    async def review_task_result(
        self,
        run_id: str,
        result_id: str,
        *,
        actor: str,
        decision: str,
        reason: str,
        expected_revision: int,
        expected_task_revision: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> TaskResult:
        """Apply an explicit operator review decision ('accepted' or 'rejected') with optimistic concurrency."""
        result = await self.store.get_result(result_id)
        if result is None or result.run_id != run_id:
            raise StorageIntegrityError(f"Result '{result_id}' not found in run '{run_id}'")

        attempt = await self.store.get_attempt(result.attempt_id)
        if attempt is None:
            raise StorageIntegrityError(f"Attempt '{result.attempt_id}' not found")

        task_rec = await self.store.get_task(attempt.task_id)
        if task_rec is None:
            raise StorageIntegrityError(f"Task '{attempt.task_id}' not found")

        review_obj = ReviewDecision(
            result_id=result_id,
            actor=actor,
            decision=decision,  # type: ignore[arg-type]
            reason=reason,
            expected_revision=expected_revision,
        )
        reviewed = await self.store.record_review_atomic(
            task_spec=task_rec["spec"],
            attempt=attempt,
            decision=review_obj,
            expected_task_revision=expected_task_revision,
            correlation_id=correlation_id,
        )
        await self._reconcile_run_status_after_task(run_id, correlation_id=correlation_id)
        return reviewed

    async def integrate_run(
        self,
        run_id: str,
        *,
        target_branch: Optional[str] = None,
        cleanup_on_success: bool = True,
        correlation_id: Optional[str] = None,
    ) -> IntegrationOutcome:
        """
        Integrate all accepted task results for a run in topological/task order into `integrate/<run_id>`,
        re-running all combined acceptance checks on the merged tree before marking the run SUCCEEDED.
        """
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")
        run_spec: RunSpec = run_rec["spec"]

        accepted_results: List[TaskResult] = []
        combined_checks: List[CheckSpec] = []
        seen_checks: set[Tuple[str, Tuple[str, ...], Optional[str]]] = set()

        for task_spec in run_spec.tasks:
            attempts = await self.store.list_attempts(task_spec.task_id)
            if not attempts:
                raise ContractViolation(
                    "result_not_accepted",
                    f"Task '{task_spec.task_id}' has no attempts to integrate",
                )
            latest_attempt = attempts[-1]
            latest_result = await self.store.get_result_by_attempt(latest_attempt.attempt_id)
            if latest_result is None:
                raise ContractViolation(
                    "result_not_accepted",
                    f"Task '{task_spec.task_id}' attempt '{latest_attempt.attempt_id}' has no result",
                )
            assert_integrable(task_spec, latest_attempt, latest_result)
            accepted_results.append(latest_result)

            for chk in task_spec.acceptance_criteria:
                key = (chk.check_id, chk.command, chk.cwd)
                if key not in seen_checks:
                    seen_checks.add(key)
                    combined_checks.append(chk)

        await self.store.record_event_atomic(
            run_id=run_id,
            event_type="merge.started",
            payload={
                "base_sha": run_spec.base_sha,
                "result_ids": [r.result_id for r in accepted_results],
            },
            correlation_id=correlation_id,
        )

        git_ws = self._get_git_workspace(run_spec.repo_root)
        chk_runner = self._get_check_runner(run_spec.repo_root)

        async def _combined_check_runner(
            int_wt_path: Path,
            merged_sha: str,
            checks: Sequence[CheckSpec],
        ) -> Tuple[Tuple[CheckResult, ...], Tuple[Artifact, ...]]:
            return await chk_runner.run_checks(
                run_id=run_id,
                attempt_id=None,
                workspace_path=int_wt_path,
                tested_sha=merged_sha,
                checks=checks,
                scope_prefix=f"integrate_{_sanitize_token(run_id)}",
            )

        outcome = await git_ws.integrate_results(
            run_id=run_id,
            expected_base_sha=run_spec.base_sha,
            results=accepted_results,
            target_branch=target_branch,
            post_merge_checks=tuple(combined_checks),
            check_runner=_combined_check_runner,
        )

        refreshed_run = await self.store.get_run(run_id)
        assert refreshed_run is not None
        run_status = RunStatus(refreshed_run["status"])
        run_rev = int(refreshed_run["revision"])

        if outcome.status == IntegrationStatus.INTEGRATED:
            if run_status == RunStatus.RUNNING:
                refreshed_run = await self.store.update_run_status_atomic(
                    run_id=run_id,
                    new_status=RunStatus.REVIEWING,
                    expected_revision=run_rev,
                    event_type="run.waiting",
                    event_payload={"reason": "integration_verified"},
                    correlation_id=correlation_id,
                )
                run_rev = int(refreshed_run["revision"])

            await self.store.update_run_status_atomic(
                run_id=run_id,
                new_status=RunStatus.SUCCEEDED,
                expected_revision=run_rev,
                event_type="run.finished",
                event_payload={
                    "integration_id": outcome.integration_id,
                    "result_sha": outcome.result_sha,
                    "target_branch": outcome.target_branch,
                },
                correlation_id=correlation_id,
            )
            if cleanup_on_success:
                for res in accepted_results:
                    ws_rec = git_ws._workspaces.get(res.attempt_id)
                    if ws_rec is not None and ws_rec.canonical_path.exists():
                        try:
                            git_ws.cleanup_worktree(
                                ws_rec,
                                force_discard=True,
                                delete_branch=False,
                            )
                            await git_ws.save_workspace_record(ws_rec)
                        except GitWorkspaceError:
                            pass
        else:
            if run_status in {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING, RunStatus.REVIEWING}:
                await self.store.update_run_status_atomic(
                    run_id=run_id,
                    new_status=RunStatus.FAILED,
                    expected_revision=run_rev,
                    event_type="run.finished",
                    event_payload={
                        "integration_id": outcome.integration_id,
                        "integration_status": outcome.status.value,
                        "conflicted_files": list(outcome.conflicted_files),
                    },
                    correlation_id=correlation_id,
                )

        return outcome

    async def retry_task(
        self,
        run_id: str,
        task_id: str,
        *,
        prompt: Optional[str] = None,
        provider: str = "local_cli",
        model: str = "default",
        custom_command: Optional[Sequence[str]] = None,
        extra_args: Sequence[str] = (),
        forbidden_paths: Sequence[str] = (),
        allowed_env: Optional[Mapping[str, str]] = None,
        correlation_id: Optional[str] = None,
    ) -> TaskExecutionOutcome:
        """Create a new attempt (ordinal + 1) in a fresh isolated worktree for a failed/rejected/blocked task."""
        return await self.execute_task_attempt(
            run_id=run_id,
            task_id=task_id,
            prompt=prompt,
            provider=provider,
            model=model,
            dry_run=False,
            custom_command=custom_command,
            extra_args=extra_args,
            forbidden_paths=forbidden_paths,
            allowed_env=allowed_env,
            allow_retry_from_terminal=True,
            correlation_id=correlation_id,
        )

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str = "operator_cancelled",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel all active attempts and tasks in a run, preserving worktree evidence."""
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")

        current_run_status = RunStatus(run_rec["status"])
        if current_run_status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ContractViolation(
                "invalid_run_state",
                f"Cannot cancel run '{run_id}' already in terminal status '{current_run_status.value}'",
            )

        tasks = await self.store.list_tasks(run_id)
        cancelled_attempts: List[str] = []

        for t in tasks:
            tid = t["id"]
            attempts = await self.store.list_attempts(tid)
            for att in attempts:
                if att.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}:
                    await self.worker_runner.cancel(att.attempt_id, reason=reason)
                    cancelled_attempts.append(att.attempt_id)

        await self.store.reconcile_interrupted_attempts(run_id=run_id, reason=reason)

        # Transition any non-terminal tasks to CANCELLED
        tasks_after = await self.store.list_tasks(run_id)
        for t in tasks_after:
            t_status = TaskStatus(t["status"])
            if t_status in {
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
                TaskStatus.NEEDS_CONTEXT,
                TaskStatus.BLOCKED,
                TaskStatus.READY_FOR_REVIEW,
            }:
                await self.store.update_task_status_atomic(
                    task_id=t["id"],
                    new_status=TaskStatus.CANCELLED,
                    expected_revision=int(t["revision"]),
                    event_type="task.cancelled",
                    event_payload={"reason": reason},
                    correlation_id=correlation_id,
                )

        latest_run = await self.store.get_run(run_id)
        assert latest_run is not None
        updated_run = await self.store.update_run_status_atomic(
            run_id=run_id,
            new_status=RunStatus.CANCELLED,
            expected_revision=int(latest_run["revision"]),
            event_type="run.cancelled",
            event_payload={
                "reason": reason,
                "cancelled_attempts": cancelled_attempts,
            },
            correlation_id=correlation_id,
        )
        return updated_run

    async def cancel_task(
        self,
        run_id: str,
        task_id: str,
        *,
        reason: str = "operator_cancelled",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel a single task within a run without terminating sibling tasks."""
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")

        task_rec = await self.store.get_task(task_id)
        if task_rec is None or task_rec["run_id"] != run_id:
            raise StorageIntegrityError(f"Task '{task_id}' not found in run '{run_id}'")

        t_status = TaskStatus(task_rec["status"])
        if t_status in {TaskStatus.ACCEPTED, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise ContractViolation(
                "invalid_task_state",
                f"Cannot cancel task '{task_id}' already in terminal status '{t_status.value}'",
            )

        cancelled_attempts: List[str] = []
        attempts = await self.store.list_attempts(task_id)
        for att in attempts:
            if att.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}:
                await self.worker_runner.cancel(att.attempt_id, reason=reason)
                cancelled_attempts.append(att.attempt_id)
                updated_att = TaskAttempt(
                    attempt_id=att.attempt_id,
                    task_id=att.task_id,
                    run_id=att.run_id,
                    ordinal=att.ordinal,
                    executor_id=att.executor_id,
                    provider=att.provider,
                    model=att.model,
                    base_sha=att.base_sha,
                    workspace_path=att.workspace_path,
                    provider_session=att.provider_session,
                    process_status=ProcessStatus.CANCELLED,
                    exit_code=att.exit_code,
                    started_at=att.started_at,
                    finished_at=datetime.now(timezone.utc),
                    exit_reason=reason,
                )
                await self.store.save_attempt_atomic(
                    updated_att,
                    event_type="attempt.finished",
                    event_payload={"cancelled": True, "reason": reason},
                    correlation_id=correlation_id,
                )

        refreshed_task = await self.store.get_task(task_id)
        assert refreshed_task is not None
        updated_task = await self.store.update_task_status_atomic(
            task_id=task_id,
            new_status=TaskStatus.CANCELLED,
            expected_revision=int(refreshed_task["revision"]),
            event_type="task.cancelled",
            event_payload={"reason": reason, "cancelled_attempts": cancelled_attempts},
            correlation_id=correlation_id,
        )
        return updated_task

    async def list_runs(
        self,
        *,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> Dict[str, Any]:
        """Return paginated run summaries."""
        await self.store.initialize()
        page_num = max(int(page), 1)
        page_size = max(min(int(size), 100), 1)
        offset = (page_num - 1) * page_size

        where_clauses: List[str] = []
        params: List[Any] = []
        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        async with self.store._connect() as db:
            cnt_cur = await db.execute(f"SELECT COUNT(*) AS cnt FROM runs{where_sql}", tuple(params))
            cnt_row = await cnt_cur.fetchone()
            total = int(cnt_row["cnt"]) if cnt_row else 0

            cur = await db.execute(
                f"SELECT id, project_id, spec_json, base_sha, status, revision, created_at, updated_at "
                f"FROM runs{where_sql} ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
                tuple([*params, page_size, offset]),
            )
            rows = await cur.fetchall()

        items: List[Dict[str, Any]] = []
        for r in rows:
            spec = RunSpec.model_validate_json(r["spec_json"])
            items.append(
                {
                    "id": r["id"],
                    "run_id": r["id"],
                    "project_id": r["project_id"],
                    "objective": spec.objective,
                    "mode": spec.orchestration_mode,
                    "status": r["status"],
                    "revision": int(r["revision"]),
                    "base_sha": r["base_sha"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        pages = max((total + page_size - 1) // page_size, 1)
        return {
            "items": items,
            "total": total,
            "page": page_num,
            "size": page_size,
            "pages": pages,
        }

    async def list_run_tasks(self, run_id: str) -> List[Dict[str, Any]]:
        """List all tasks of a run with their attempts and latest results."""
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")
        tasks = await self.store.list_tasks(run_id)
        out: List[Dict[str, Any]] = []
        for t in tasks:
            tid = t["id"]
            attempts = await self.store.list_attempts(tid)
            attempt_dicts: List[Dict[str, Any]] = []
            for att in attempts:
                res = await self.store.get_result_by_attempt(att.attempt_id)
                res_dict: Optional[Dict[str, Any]] = None
                if res is not None:
                    outcome_str = (
                        "success"
                        if res.task_status in {TaskStatus.READY_FOR_REVIEW, TaskStatus.ACCEPTED}
                        else ("partial" if res.task_status == TaskStatus.NEEDS_CONTEXT else "failure")
                    )
                    res_dict = {
                        "id": res.result_id,
                        "result_id": res.result_id,
                        "attempt_id": res.attempt_id,
                        "exit_code": res.exit_code,
                        "simulated": res.simulated,
                        "outcome": outcome_str,
                        "task_status": res.task_status.value,
                        "revision": res.revision,
                        "summary": res.summary,
                        "patch_commit_sha": res.patch_commit_sha,
                        "patch_artifact_id": res.patch_artifact_id,
                        "changed_files": list(res.changed_files),
                        "checks": [c.model_dump(mode="json") for c in res.checks_executed],
                        "failures": [f.model_dump(mode="json") for f in res.failures],
                    }
                attempt_dicts.append(
                    {
                        "id": att.attempt_id,
                        "attempt_id": att.attempt_id,
                        "task_id": att.task_id,
                        "ordinal": att.ordinal,
                        "executor_id": att.executor_id,
                        "provider": att.provider,
                        "model": att.model,
                        "provider_model_json": f'{{"model":"{att.model}","provider":"{att.provider}"}}',
                        "provider_session": att.provider_session,
                        "process_status": att.process_status.value,
                        "exit_code": att.exit_code,
                        "started_at": att.started_at.isoformat() if att.started_at else None,
                        "finished_at": att.finished_at.isoformat() if att.finished_at else None,
                        "result": res_dict,
                    }
                )
            t_spec: TaskSpec = t["spec"]
            out.append(
                {
                    "id": tid,
                    "task_id": tid,
                    "run_id": run_id,
                    "spec": t_spec.model_dump(mode="json"),
                    "status": t["status"],
                    "revision": int(t["revision"]),
                    "dependencies": list(t.get("dependencies", ())),
                    "current_attempt": attempt_dicts[-1] if attempt_dicts else None,
                    "attempts": attempt_dicts,
                    "created_at": t["created_at"],
                    "updated_at": t["updated_at"],
                }
            )
        return out

    async def get_run_detail(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete RunDetailResponse snapshot for a run."""
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            return None
        spec: RunSpec = run_rec["spec"]
        tasks = await self.list_run_tasks(run_id)
        bp = spec.budget_policy
        budget_status = "active"
        async with self.store._connect() as db:
            cur = await db.execute("SELECT status FROM budget_policies WHERE run_id = ?", (run_id,))
            brow = await cur.fetchone()
            if brow is not None:
                budget_status = brow["status"]

        return {
            "id": run_id,
            "run_id": run_id,
            "project_id": run_rec["project_id"],
            "objective": spec.objective,
            "mode": spec.orchestration_mode,
            "status": run_rec["status"],
            "revision": int(run_rec["revision"]),
            "base_sha": run_rec["base_sha"],
            "spec": spec.model_dump(mode="json"),
            "tasks": tasks,
            "budget": {
                "max_usd": bp.max_usd,
                "max_tokens_in": bp.max_tokens_in,
                "max_tokens_out": bp.max_tokens_out,
                "max_wall_seconds": bp.max_wall_seconds,
                "alert_threshold_pct": bp.alert_threshold_pct,
                "current_usd": None,
                "current_tokens_in": None,
                "current_tokens_out": None,
                "status": budget_status,
            },
            "created_at": run_rec["created_at"],
            "updated_at": run_rec["updated_at"],
        }

    async def discard_run_runtime(
        self,
        run_id: str,
        *,
        force: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Explicitly discard temporary worktrees for a run only after verifying artifact retention (RF15 / RT11).
        Never deletes persisted SQLite records or retained evidence artifacts.
        """
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise StorageIntegrityError(f"Run '{run_id}' does not exist")

        r_status = RunStatus(run_rec["status"])
        if r_status not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED} and not force:
            raise ContractViolation(
                "invalid_run_state",
                f"Cannot discard runtime for active run '{run_id}' in status '{r_status.value}'",
            )

        run_spec: RunSpec = run_rec["spec"]
        git_ws = self._get_git_workspace(run_spec.repo_root)

        # Verify integrity of all persisted artifacts before allowing runtime cleanup
        artifacts = await self.store.get_artifacts(run_id)
        verified_artifacts: List[str] = []
        for art in artifacts:
            art_path = git_ws.repo_root / art.relative_path
            if art_path.exists():
                actual_sha = hashlib.sha256(art_path.read_bytes()).hexdigest()
                if actual_sha != art.sha256:
                    raise ContractViolation(
                        "artifact_tampered",
                        f"Retained artifact '{art.artifact_id}' at '{art.relative_path}' failed SHA-256 verification",
                    )
                verified_artifacts.append(art.artifact_id)

        cleaned_worktrees: List[str] = []
        preserved_worktrees: List[str] = []
        tasks = await self.store.list_tasks(run_id)
        for t in tasks:
            attempts = await self.store.list_attempts(t["id"])
            for att in attempts:
                ws_rec = git_ws._workspaces.get(att.attempt_id)
                if ws_rec is not None and ws_rec.canonical_path.exists():
                    try:
                        git_ws.cleanup_worktree(ws_rec, force_discard=force, delete_branch=False)
                        await git_ws.save_workspace_record(ws_rec)
                        cleaned_worktrees.append(att.attempt_id)
                    except GitWorkspaceError:
                        preserved_worktrees.append(att.attempt_id)

        return {
            "run_id": run_id,
            "status": "discarded",
            "retained_artifacts_count": len(artifacts),
            "verified_artifacts": verified_artifacts,
            "cleaned_worktrees": cleaned_worktrees,
            "preserved_worktrees": preserved_worktrees,
        }


__all__ = [
    "CheckRunner",
    "RunService",
    "TaskExecutionOutcome",
]
