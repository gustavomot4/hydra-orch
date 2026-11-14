"""Interactive Orchestration Cockpit (TUI) for hydra-orch (T30 / RF26-RF30 / RT28)."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Protocol, Sequence, TextIO, Tuple, Union
from urllib.parse import urlsplit
import uuid

import httpx
from pydantic import Field, ValidationError
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from hydra_orch.bridge.omniroute_client import OmniRouteClient, _unknown_quota_payload
from hydra_orch.config import ConfigError, HydraConfig, load_config
from hydra_orch.core.agent_registry import AgentRegistry
from hydra_orch.core.attachments import read_safe_preview
from hydra_orch.core.checkpointer import (
    IdempotencyConflictError,
    OptimisticLockError,
    StorageError,
    StorageIntegrityError,
)
from hydra_orch.core.conflict_resolver import ConflictResolver
from hydra_orch.core.git_workspace import GitWorkspaceError
from hydra_orch.core.hitl import HITLService
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.packaging import PRPackager
from hydra_orch.core.redaction import REDACTED, redact, redact_text, redaction_scope
from hydra_orch.core.route_selector import RouteSelector
from hydra_orch.core.run_service import RunService
from hydra_orch.core.session_service import EventCursor, SessionService
from hydra_orch.model import ContractViolation, ExecutionModel, IntegrationStatus, TaskStatus

_MAX_EVENTS_RETAINED = 100
_MAX_PREVIEW_LINES = 60
_MAX_PREVIEW_CHARS = 4000
_MAX_LINE_COMMANDS = 10_000


class CockpitCommandOutcome(ExecutionModel):
    """Structured result of executing a single operator command in the cockpit."""

    command: str
    ok: bool
    should_quit: bool = False
    message: str = ""
    error_code: Optional[str] = None
    data: Any = None


@dataclass
class CockpitState:
    """In-memory view model for the live orchestration cockpit."""

    connection_mode: Literal["local", "http"] = "local"
    api_url: Optional[str] = None
    active_run_id: Optional[str] = None
    runs: List[Dict[str, Any]] = field(default_factory=list)
    snapshot: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    last_seq: int = 0
    seen_seqs: set[int] = field(default_factory=set)
    route_inventory: Dict[str, Any] = field(default_factory=dict)
    hitl_requests: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    pr_package: Optional[Dict[str, Any]] = None
    route_decisions: List[Dict[str, Any]] = field(default_factory=list)
    metrics_usage: Dict[str, Any] = field(default_factory=dict)
    detail_title: str = "Inspector"
    detail_body: str = "Select a run or enter a command ('help' for commands)."
    last_message: str = ""
    last_error: Optional[str] = None
    last_error_code: Optional[str] = None
    step_count: int = 0


def _safe_str(value: Any) -> str:
    """Convert any value to a redacted string."""
    if value is None:
        return "—"
    return redact_text(str(value))


def _safe_text(value: Any, *, style: Optional[str] = None) -> Text:
    """Create a Rich Text renderable guaranteed to be redacted and markup-safe."""
    return Text(_safe_str(value), style=style or "", overflow="fold")


def sanitize_api_url(api_url: str) -> str:
    """Validate an HTTP(S) Control Plane base URL without accepting embedded credentials."""
    raw = api_url.strip()
    parsed = urlsplit(raw)
    if (
        not raw
        or any(ch.isspace() for ch in raw)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ContractViolation(
            "invalid_api_url",
            "API URL must be an http(s) URL without embedded credentials or fragments",
        )
    return raw.rstrip("/")


def resolve_api_token(
    *,
    api_token: Optional[str] = None,
    api_token_env: str = "HYDRA_API_TOKEN",
    interactive: bool = False,
    prompt_fn: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    """Resolve Bearer token from explicit argument, environment variable, or hidden prompt."""
    if api_token is not None:
        stripped = api_token.strip()
        return stripped or None
    env_val = os.environ.get(api_token_env, "").strip()
    if env_val:
        return env_val
    if interactive:
        asker = prompt_fn or getpass.getpass
        entered = asker(f"Bearer token ({api_token_env}): ").strip()
        return entered or None
    return None


def format_quota_entry(entry: Any) -> str:
    """Render a single provider quota observation without ever turning unknown into 0%."""
    if not isinstance(entry, dict):
        return "— (unknown)"
    status = str(entry.get("status") or "unknown").lower()
    pct = entry.get("remaining_percent")
    if status == "unknown" or pct is None or isinstance(pct, bool):
        return "— (unknown)"
    try:
        pct_num = float(pct)
    except (TypeError, ValueError):
        return "— (unknown)"
    pct_str = f"{int(pct_num)}%" if pct_num.is_integer() else f"{pct_num:.1f}%"
    reset = entry.get("resets_in_seconds")
    reset_str = f", reset {int(float(reset))}s" if isinstance(reset, (int, float)) and not isinstance(reset, bool) else ""
    return f"{pct_str} ({status}{reset_str})"


def compute_task_waves(tasks: Sequence[Dict[str, Any]], mode: str) -> Dict[str, Tuple[int, str]]:
    """Compute topological Wave 0 / Wave 1+ labels for Swarm or ordered step labels for Relay/Persist."""
    by_id: Dict[str, Dict[str, Any]] = {
        str(t.get("task_id") or t.get("id")): t for t in tasks if (t.get("task_id") or t.get("id"))
    }
    waves: Dict[str, int] = {}

    def _wave(tid: str, visiting: set[str]) -> int:
        if tid in waves:
            return waves[tid]
        if tid in visiting:
            return 0
        visiting.add(tid)
        task = by_id.get(tid, {})
        deps = task.get("dependencies") or task.get("spec", {}).get("dependencies") or []
        if not deps:
            depth = 0
        else:
            depth = 1 + max(_wave(str(dep), visiting) for dep in deps if str(dep) in by_id) if any(
                str(dep) in by_id for dep in deps
            ) else 1
        visiting.remove(tid)
        waves[tid] = depth
        return depth

    labels: Dict[str, Tuple[int, str]] = {}
    for idx, t in enumerate(tasks, start=1):
        tid = str(t.get("task_id") or t.get("id") or f"task-{idx}")
        depth = _wave(tid, set())
        if mode == "swarm":
            role = "Foundation" if depth == 0 else "Worker"
            labels[tid] = (depth, f"Wave {depth} ({role})")
        elif mode == "persistent":
            labels[tid] = (depth, f"Persist #{idx}")
        else:
            labels[tid] = (depth, f"Relay #{idx}")
    return labels


def parse_sse_events(raw_text: str) -> List[Dict[str, Any]]:
    """Parse SSE frames into normalized, redacted event dictionaries (ignoring heartbeats)."""
    normalized: List[Dict[str, Any]] = []
    blocks = raw_text.replace("\r\n", "\n").split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_id: Optional[str] = None
        event_name = "message"
        data_lines: List[str] = []
        for line in block.split("\n"):
            if not line or line.startswith(":"):
                continue
            if ":" in line:
                field_name, rest = line.split(":", 1)
                value = rest[1:] if rest.startswith(" ") else rest
            else:
                field_name, value = line, ""
            if field_name == "id":
                event_id = value.strip()
            elif field_name == "event":
                event_name = value.strip()
            elif field_name == "data":
                data_lines.append(value)

        if event_name == "heartbeat" or not data_lines:
            continue
        raw_data = "\n".join(data_lines)
        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue

        seq_raw = parsed.get("seq", event_id)
        try:
            seq = int(seq_raw)
        except (TypeError, ValueError):
            continue

        normalized.append(
            redact(
                {
                    "seq": seq,
                    "run_id": parsed.get("run_id"),
                    "event_type": parsed.get("type") or parsed.get("event_type") or event_name,
                    "task_id": parsed.get("task_id"),
                    "attempt_id": parsed.get("attempt_id"),
                    "timestamp": parsed.get("timestamp"),
                    "payload": parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {},
                }
            )
        )
    return normalized


def _summarize_checks(checks: Sequence[Dict[str, Any]]) -> str:
    if not checks:
        return "—"
    total = len(checks)
    passed = sum(1 for c in checks if c.get("exit_code") == 0)
    failed = total - passed
    if failed == 0:
        return f"{passed}/{total} PASS"
    return f"{passed}/{total} FAIL ({failed})"


def _bound_preview_text(text: str) -> str:
    safe = redact_text(text)
    lines = safe.splitlines()
    if len(lines) > _MAX_PREVIEW_LINES:
        lines = [*lines[:_MAX_PREVIEW_LINES], f"... ({len(lines) - _MAX_PREVIEW_LINES} more lines truncated)"]
    joined = "\n".join(lines)
    if len(joined) > _MAX_PREVIEW_CHARS:
        joined = joined[:_MAX_PREVIEW_CHARS] + "\n... (output truncated)"
    return joined


def _safe_split_command(raw_line: str) -> List[str]:
    stripped = raw_line.strip()
    if not stripped:
        return []
    try:
        return shlex.split(stripped)
    except ValueError:
        return stripped.split()


class CockpitBackend(Protocol):
    """Backend transport abstraction for local RunService or remote REST+SSE API."""

    mode: Literal["local", "http"]

    async def list_runs(self, *, limit: int = 20) -> List[Dict[str, Any]]: ...

    async def get_run_snapshot(self, run_id: str) -> Dict[str, Any]: ...

    async def replay_events(
        self, run_id: str, *, after_seq: int = 0, limit: int = 200
    ) -> Tuple[List[Dict[str, Any]], bool]: ...

    async def get_route_inventory(self, *, scope_id: str = "default") -> Dict[str, Any]: ...

    async def select_account(
        self, scope_id: str, provider: str, account_id: str, *, principal_id: str
    ) -> Dict[str, Any]: ...

    async def inspect_diff(self, run_id: str, task_id: str) -> Dict[str, Any]: ...

    async def inspect_checks(self, run_id: str, task_id: str) -> Dict[str, Any]: ...

    async def review_task(
        self,
        run_id: str,
        task_id: str,
        decision: str,
        reason: str,
        *,
        actor: str,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]: ...

    async def list_hitl(self, run_id: str) -> List[Dict[str, Any]]: ...

    async def reply_hitl(
        self, run_id: str, hitl_id: str, action: str, note: str, *, actor: str
    ) -> Dict[str, Any]: ...

    async def list_conflicts(self, run_id: str) -> List[Dict[str, Any]]: ...

    async def auto_repair_conflict(
        self,
        run_id: str,
        conflict_id: str,
        *,
        actor: str,
        max_repair_attempts: Optional[int] = None,
        repair_command: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]: ...

    async def manual_conflict(
        self,
        run_id: str,
        conflict_id: str,
        *,
        actor: str,
        finalize: bool = False,
        worktree_path: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    async def discard_conflict(
        self, run_id: str, conflict_id: str, *, actor: str, reason: str = "operator_discarded"
    ) -> Dict[str, Any]: ...

    async def integrate_run(
        self, run_id: str, *, target_branch: Optional[str] = None
    ) -> Dict[str, Any]: ...

    async def get_pr_package(self, run_id: str) -> Optional[Dict[str, Any]]: ...

    async def build_pr_package(
        self, run_id: str, *, pr_branch: Optional[str] = None, create_git_branch: bool = True
    ) -> Dict[str, Any]: ...

    async def publish_pr_package(
        self,
        run_id: str,
        *,
        package_id: Optional[str] = None,
        authorized: bool = False,
        remote: str = "origin",
        actor: str = "operator",
    ) -> Dict[str, Any]: ...

    async def list_route_decisions(self, run_id: str) -> List[Dict[str, Any]]: ...

    async def get_usage_metrics(self, run_id: str) -> Dict[str, Any]: ...

    async def aclose(self) -> None: ...


class LocalRunBackend:
    """In-process backend operating directly over RunService and core domain services."""

    mode: Literal["local", "http"] = "local"

    def __init__(
        self,
        run_service: RunService,
        *,
        route_selector: Optional[RouteSelector] = None,
        omniroute_transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.svc = run_service
        self._route_selector = route_selector
        self._omniroute_transport = omniroute_transport

    def _get_route_selector(self) -> RouteSelector:
        if self._route_selector is not None:
            return self._route_selector
        cfg_path = self.svc.repo_root / "config.yaml"
        try:
            cfg = load_config(cfg_path) if cfg_path.is_file() else load_config()
        except ConfigError:
            cfg = HydraConfig()
        gateway = OmniRouteClient(
            base_url=cfg.omniroute.base_url,
            quota_api_url=cfg.omniroute.quota_api_url,
            enabled=not cfg.is_direct_mode,
            transport=self._omniroute_transport,
            api_key_env=cfg.omniroute.api_key_env,
        )
        return RouteSelector(
            self.svc.store,
            AgentRegistry(self.svc.store),
            MetricsService(self.svc.store),
            gateway=gateway,
            connection_mode=cfg.omniroute.connection_mode,
        )

    def _read_artifact_preview(self, run_spec_repo_root: str, relative_path: str, *, max_bytes: int) -> Dict[str, Any]:
        candidates = [Path(run_spec_repo_root), self.svc.repo_root]
        last_exc: Optional[ContractViolation] = None
        for root in candidates:
            try:
                return read_safe_preview(root, relative_path, max_bytes=max_bytes)
            except ContractViolation as exc:
                if exc.code == "resource_not_found":
                    last_exc = exc
                    continue
                raise
        if relative_path.startswith(".orchestrator/"):
            rel_in_rt = relative_path[len(".orchestrator/"):]
            try:
                return read_safe_preview(self.svc.runtime_dir, rel_in_rt, max_bytes=max_bytes)
            except ContractViolation as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise ContractViolation("resource_not_found", f"Artifact '{relative_path}' not found")

    async def list_runs(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        resp = await self.svc.list_runs(page=1, size=max(1, min(limit, 100)))
        return redact(list(resp.get("items", [])))

    async def get_run_snapshot(self, run_id: str) -> Dict[str, Any]:
        detail = await self.svc.get_run_detail(run_id)
        if detail is None:
            raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
        for task in detail.get("tasks", []):
            tid = task.get("task_id") or task.get("id")
            attempt_models = await self.svc.store.list_attempts(str(tid))
            path_by_id = {a.attempt_id: a.workspace_path for a in attempt_models}
            for att in task.get("attempts", []):
                att["workspace_path"] = path_by_id.get(att.get("attempt_id"))
                res = att.get("result")
                if isinstance(res, dict):
                    att["last_check_summary"] = _summarize_checks(res.get("checks", []))
            curr = task.get("current_attempt")
            if isinstance(curr, dict):
                curr["workspace_path"] = path_by_id.get(curr.get("attempt_id"))
                res = curr.get("result")
                if isinstance(res, dict):
                    curr["last_check_summary"] = _summarize_checks(res.get("checks", []))
        return redact(detail)

    async def replay_events(
        self, run_id: str, *, after_seq: int = 0, limit: int = 200
    ) -> Tuple[List[Dict[str, Any]], bool]:
        try:
            events = await SessionService(self.svc.store).replay(run_id, after_seq=after_seq, limit=limit)
        except ContractViolation as exc:
            if exc.code == "cursor_expired":
                return [], True
            raise
        items = [
            redact(
                {
                    "seq": ev.seq,
                    "run_id": ev.run_id,
                    "event_type": ev.event_type,
                    "task_id": ev.task_id,
                    "attempt_id": ev.attempt_id,
                    "timestamp": ev.timestamp.isoformat(),
                    "payload": ev.redacted_payload,
                }
            )
            for ev in events
        ]
        return items, False

    async def get_route_inventory(self, *, scope_id: str = "default") -> Dict[str, Any]:
        inv = await self._get_route_selector().gateway_inventory(scope_id=scope_id)
        return redact(inv)

    async def select_account(
        self, scope_id: str, provider: str, account_id: str, *, principal_id: str
    ) -> Dict[str, Any]:
        res = await self._get_route_selector().select_next_account(
            scope_id,
            provider,
            account_id,
            principal_id=principal_id,
        )
        return redact(res)

    async def inspect_diff(self, run_id: str, task_id: str) -> Dict[str, Any]:
        snapshot = await self.get_run_snapshot(run_id)
        task = next((t for t in snapshot.get("tasks", []) if t.get("task_id") == task_id), None)
        if task is None:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' not found in run '{run_id}'")

        curr = task.get("current_attempt") or {}
        res = curr.get("result") or {}
        attempt_id = curr.get("attempt_id")
        patch_art_id = res.get("patch_artifact_id")
        patch_sha = res.get("patch_commit_sha")
        changed_files = list(res.get("changed_files", ()))
        worktree_path = curr.get("workspace_path")
        repo_root = str(snapshot.get("spec", {}).get("repo_root") or self.svc.repo_root)

        preview_text = ""
        truncated = False
        if attempt_id:
            artifacts = await self.svc.store.get_artifacts(run_id, attempt_id=attempt_id)
            patch_art = next(
                (a for a in artifacts if a.artifact_id == patch_art_id or a.kind == "patch"),
                None,
            )
            if patch_art is not None:
                patch_art_id = patch_art.artifact_id
                try:
                    preview = self._read_artifact_preview(repo_root, patch_art.relative_path, max_bytes=32_768)
                    preview_text = str(preview.get("content") or "")
                    truncated = bool(preview.get("truncated", False))
                except ContractViolation as exc:
                    preview_text = f"[{exc.code}] {exc}"

        if not preview_text and worktree_path and Path(worktree_path).exists():
            try:
                proc = subprocess.run(
                    ["git", "status", "--short"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                stat_proc = subprocess.run(
                    ["git", "diff", "--stat"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                preview_text = "\n".join(
                    part for part in (proc.stdout.strip(), stat_proc.stdout.strip()) if part
                ) or "(no uncommitted diff in preserved worktree)"
            except OSError:
                preview_text = "(worktree diff unavailable)"

        if not preview_text:
            preview_text = "(no patch artifact recorded yet for this task)"

        return redact(
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "workspace_path": worktree_path,
                "patch_commit_sha": patch_sha,
                "patch_artifact_id": patch_art_id,
                "changed_files": changed_files,
                "truncated": truncated,
                "preview": _bound_preview_text(preview_text),
            }
        )

    async def inspect_checks(self, run_id: str, task_id: str) -> Dict[str, Any]:
        snapshot = await self.get_run_snapshot(run_id)
        task = next((t for t in snapshot.get("tasks", []) if t.get("task_id") == task_id), None)
        if task is None:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' not found in run '{run_id}'")

        curr = task.get("current_attempt") or {}
        res = curr.get("result") or {}
        attempt_id = curr.get("attempt_id")
        repo_root = str(snapshot.get("spec", {}).get("repo_root") or self.svc.repo_root)
        artifacts_by_id = {
            a.artifact_id: a
            for a in await self.svc.store.get_artifacts(run_id, attempt_id=attempt_id)
        }

        enriched_checks: List[Dict[str, Any]] = []
        for chk in res.get("checks", []):
            entry = dict(chk)
            for stream_key, preview_key in (
                ("stdout_artifact_id", "stdout_preview"),
                ("stderr_artifact_id", "stderr_preview"),
            ):
                art_id = entry.get(stream_key)
                art = artifacts_by_id.get(art_id) if art_id else None
                if art is not None:
                    try:
                        prev = self._read_artifact_preview(repo_root, art.relative_path, max_bytes=8_192)
                        entry[preview_key] = _bound_preview_text(str(prev.get("content") or ""))
                    except ContractViolation as exc:
                        entry[preview_key] = f"[{exc.code}] {exc}"
                else:
                    entry[preview_key] = ""
            enriched_checks.append(entry)

        return redact(
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "task_status": task.get("status"),
                "checks": enriched_checks,
                "failures": list(res.get("failures", ())),
            }
        )

    async def review_task(
        self,
        run_id: str,
        task_id: str,
        decision: str,
        reason: str,
        *,
        actor: str,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        decision_norm = decision.strip().lower()
        if decision_norm not in {"accepted", "rejected", "needs_repair"}:
            raise ContractViolation(
                "invalid_review_decision",
                f"Review decision must be accepted, rejected, or needs_repair; got '{decision}'",
            )
        if not reason.strip():
            raise ContractViolation("invalid_review_reason", "Review reason must be non-empty")

        attempts = await self.svc.store.list_attempts(task_id)
        if not attempts:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' has no attempts to review")
        latest_res = await self.svc.store.get_result_by_attempt(attempts[-1].attempt_id)
        if latest_res is None or latest_res.run_id != run_id:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' has no result in run '{run_id}'")

        effective_decision = "rejected" if decision_norm == "needs_repair" else decision_norm
        effective_reason = (
            reason.strip()
            if decision_norm != "needs_repair" or "needs_repair" in reason.lower()
            else f"needs_repair: {reason.strip()}"
        )
        rev = expected_revision if expected_revision is not None else int(latest_res.revision)

        reviewed = await self.svc.review_task_result(
            run_id=run_id,
            result_id=latest_res.result_id,
            actor=actor,
            decision=effective_decision,
            reason=effective_reason,
            expected_revision=rev,
        )
        return redact(
            {
                "run_id": run_id,
                "task_id": task_id,
                "result_id": reviewed.result_id,
                "decision": effective_decision,
                "requested_decision": decision_norm,
                "task_status": reviewed.task_status.value,
                "revision": reviewed.revision,
            }
        )

    async def list_hitl(self, run_id: str) -> List[Dict[str, Any]]:
        reqs = await HITLService(self.svc.store).list_requests(run_id)
        return redact([r.model_dump(mode="json") for r in reqs])

    async def reply_hitl(
        self, run_id: str, hitl_id: str, action: str, note: str, *, actor: str
    ) -> Dict[str, Any]:
        action_norm = action.strip().lower()
        clean_note = note.strip()
        if action_norm in {"approved", "approve", "yes"}:
            approved = True
            response_text = clean_note or "approved"
        elif action_norm in {"rejected", "reject", "denied", "deny", "no"}:
            approved = False
            response_text = clean_note or "rejected"
        elif action_norm == "answer":
            if not clean_note:
                raise ContractViolation("hitl_invalid", "Answer text is required for 'hitl-reply <id> answer <note>'")
            approved = True
            response_text = clean_note
        else:
            raise ContractViolation(
                "hitl_invalid",
                f"HITL reply action must be approved, rejected, or answer; got '{action}'",
            )

        svc = HITLService(self.svc.store)
        current = await svc.get_request(run_id, hitl_id)
        updated = await svc.respond(
            run_id,
            hitl_id,
            response_text,
            actor=actor,
            expected_revision=current.revision,
            idempotency_key=f"tui-hitl-{uuid.uuid4().hex[:16]}",
            approved=approved,
        )
        return redact(updated.model_dump(mode="json"))

    async def list_conflicts(self, run_id: str) -> List[Dict[str, Any]]:
        reports = await ConflictResolver(self.svc.store).list_reports(run_id=run_id)
        return redact([r.model_dump(mode="json") for r in reports])

    async def auto_repair_conflict(
        self,
        run_id: str,
        conflict_id: str,
        *,
        actor: str,
        max_repair_attempts: Optional[int] = None,
        repair_command: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        resolver = ConflictResolver(self.svc.store)
        report = await resolver.get_report(conflict_id, include_details=False)
        if report.run_id != run_id:
            raise ContractViolation("resource_not_found", f"Conflict '{conflict_id}' does not belong to run '{run_id}'")
        res = await resolver.auto_repair(
            conflict_id,
            repair_command=repair_command,
            max_repair_attempts=max_repair_attempts,
            actor=actor,
        )
        return redact(res.model_dump(mode="json"))

    async def manual_conflict(
        self,
        run_id: str,
        conflict_id: str,
        *,
        actor: str,
        finalize: bool = False,
        worktree_path: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolver = ConflictResolver(self.svc.store)
        report = await resolver.get_report(conflict_id, include_details=False)
        if report.run_id != run_id:
            raise ContractViolation("resource_not_found", f"Conflict '{conflict_id}' does not belong to run '{run_id}'")
        res = await resolver.resolve_manual(
            conflict_id,
            actor=actor,
            finalize=finalize,
            worktree_path=worktree_path,
            commit_message=commit_message,
        )
        return redact(res.model_dump(mode="json"))

    async def discard_conflict(
        self, run_id: str, conflict_id: str, *, actor: str, reason: str = "operator_discarded"
    ) -> Dict[str, Any]:
        resolver = ConflictResolver(self.svc.store)
        report = await resolver.get_report(conflict_id, include_details=False)
        if report.run_id != run_id:
            raise ContractViolation("resource_not_found", f"Conflict '{conflict_id}' does not belong to run '{run_id}'")
        res = await resolver.discard(conflict_id, actor=actor, reason=reason)
        return redact(res.model_dump(mode="json"))

    async def integrate_run(
        self, run_id: str, *, target_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        outcome = await self.svc.integrate_run(run_id, target_branch=target_branch)
        return redact(
            {
                "integration_id": outcome.integration_id,
                "run_id": outcome.run_id,
                "status": outcome.status.value,
                "target_branch": outcome.target_branch,
                "result_sha": outcome.result_sha,
                "conflicted_files": list(outcome.conflicted_files),
            }
        )

    async def get_pr_package(self, run_id: str) -> Optional[Dict[str, Any]]:
        pkg = await PRPackager(self.svc.store).get_package(run_id)
        return redact(pkg.model_dump(mode="json")) if pkg is not None else None

    async def build_pr_package(
        self, run_id: str, *, pr_branch: Optional[str] = None, create_git_branch: bool = True
    ) -> Dict[str, Any]:
        pkg = await PRPackager(self.svc.store).build(
            run_id,
            pr_branch=pr_branch,
            create_git_branch=create_git_branch,
            runtime_dir=self.svc.runtime_dir,
        )
        return redact(pkg.model_dump(mode="json"))

    async def publish_pr_package(
        self,
        run_id: str,
        *,
        package_id: Optional[str] = None,
        authorized: bool = False,
        remote: str = "origin",
        actor: str = "operator",
    ) -> Dict[str, Any]:
        packager = PRPackager(self.svc.store)
        target_pkg_id = package_id
        if not target_pkg_id:
            pkg = await packager.get_package(run_id)
            if pkg is None:
                if not authorized:
                    raise ContractViolation(
                        "publish_not_authorized",
                        "PR package publication requires explicit authorization",
                    )
                raise ContractViolation("resource_not_found", f"PR package not found for run '{run_id}'")
            target_pkg_id = pkg.package_id
        res = await packager.publish(
            target_pkg_id,
            authorized=authorized,
            remote=remote,
            actor=actor,
        )
        return redact(res.model_dump(mode="json"))

    async def list_route_decisions(self, run_id: str) -> List[Dict[str, Any]]:
        try:
            decisions = await self._get_route_selector().list_decisions(run_id)
        except ContractViolation:
            return []
        return redact(list(decisions))

    async def get_usage_metrics(self, run_id: str) -> Dict[str, Any]:
        usage = await MetricsService(self.svc.store).aggregate_usage(run_id)
        return redact(usage)

    async def aclose(self) -> None:
        return None


class HttpRunBackend:
    """REST + SSE HTTP backend targeting an authenticated hydra-orch Control Plane server."""

    mode: Literal["local", "http"] = "http"

    def __init__(
        self,
        api_url: str,
        *,
        api_token: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout: float = 15.0,
    ):
        self.base_url = sanitize_api_url(api_url)
        self._api_token = api_token.strip() if api_token else None
        self._transport = transport
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Accept": "application/json"}
            if self._api_token:
                headers["Authorization"] = f"Bearer {self._api_token}"
            kwargs: Dict[str, Any] = {
                "base_url": self.base_url,
                "headers": headers,
                "timeout": self._timeout,
            }
            if self._transport is not None:
                kwargs["transport"] = self._transport
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        code = f"http_{resp.status_code}"
        message = f"Control Plane returned HTTP {resp.status_code}"
        try:
            data = resp.json()
            if isinstance(data, dict):
                if isinstance(data.get("error"), dict):
                    code = str(data["error"].get("code") or code)
                    message = str(data["error"].get("message") or message)
                else:
                    code = str(data.get("code") or code)
                    message = str(data.get("message") or data.get("detail") or message)
        except Exception:
            if resp.text:
                message = resp.text[:300]
        raise ContractViolation(code, redact_text(message))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        allow_statuses: Tuple[int, ...] = (),
    ) -> httpx.Response:
        client = self._get_client()
        scope_cm = redaction_scope([self._api_token]) if self._api_token else nullcontext()
        with scope_cm:
            resp = await client.request(method, path, json=json_body, params=params, headers=headers)
            if resp.status_code not in allow_statuses:
                self._raise_for_error(resp)
            return resp

    async def list_runs(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        resp = await self._request("GET", "/v1/control-plane/runs", params={"page": 1, "size": max(1, min(limit, 100))})
        return redact(list(resp.json().get("items", [])))

    async def get_run_snapshot(self, run_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/v1/control-plane/runs/{run_id}")
        detail = resp.json()
        for task in detail.get("tasks", []):
            for att in task.get("attempts", []):
                res = att.get("result")
                if isinstance(res, dict):
                    att["last_check_summary"] = _summarize_checks(res.get("checks", []))
            curr = task.get("current_attempt")
            if isinstance(curr, dict):
                res = curr.get("result")
                if isinstance(res, dict):
                    curr["last_check_summary"] = _summarize_checks(res.get("checks", []))
        return redact(detail)

    async def replay_events(
        self, run_id: str, *, after_seq: int = 0, limit: int = 200
    ) -> Tuple[List[Dict[str, Any]], bool]:
        headers = {"Accept": "text/event-stream"}
        if after_seq > 0:
            headers["Last-Event-ID"] = str(after_seq)
        resp = await self._request(
            "GET",
            f"/v1/control-plane/runs/{run_id}/events",
            params={"follow": "false", "limit": str(limit)},
            headers=headers,
            allow_statuses=(410,),
        )
        if resp.status_code == 410:
            return [], True
        return parse_sse_events(resp.text), False

    async def get_route_inventory(self, *, scope_id: str = "default") -> Dict[str, Any]:
        resp = await self._request("GET", "/v1/control-plane/omniroute/inventory", params={"scope_id": scope_id})
        return redact(resp.json())

    async def select_account(
        self, scope_id: str, provider: str, account_id: str, *, principal_id: str
    ) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            "/v1/control-plane/omniroute/account",
            json_body={"scope_id": scope_id, "provider": provider, "account_id": account_id},
        )
        return redact(resp.json())

    async def inspect_diff(self, run_id: str, task_id: str) -> Dict[str, Any]:
        snapshot = await self.get_run_snapshot(run_id)
        task = next((t for t in snapshot.get("tasks", []) if t.get("task_id") == task_id), None)
        if task is None:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' not found in run '{run_id}'")
        curr = task.get("current_attempt") or {}
        res = curr.get("result") or {}
        attempt_id = curr.get("attempt_id")
        patch_art_id = res.get("patch_artifact_id")
        preview_text = ""
        truncated = False
        if not patch_art_id:
            arts = (await self._request("GET", f"/v1/control-plane/runs/{run_id}/artifacts", params={"kind": "patch"})).json()
            match = next((a for a in arts if a.get("attempt_id") == attempt_id), None)
            if match:
                patch_art_id = match.get("artifact_id") or match.get("id")
        if patch_art_id:
            art_resp = await self._request(
                "GET",
                f"/v1/control-plane/runs/{run_id}/artifacts/{patch_art_id}/content",
                params={"max_bytes": 32_768},
                allow_statuses=(404,),
            )
            if art_resp.status_code == 200:
                payload = art_resp.json()
                preview_text = str(payload.get("content") or "")
                truncated = bool(payload.get("truncated", False))
        if not preview_text:
            preview_text = "(no patch artifact recorded yet for this task)"
        return redact(
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "workspace_path": curr.get("workspace_path"),
                "patch_commit_sha": res.get("patch_commit_sha"),
                "patch_artifact_id": patch_art_id,
                "changed_files": list(res.get("changed_files", ())),
                "truncated": truncated,
                "preview": _bound_preview_text(preview_text),
            }
        )

    async def inspect_checks(self, run_id: str, task_id: str) -> Dict[str, Any]:
        snapshot = await self.get_run_snapshot(run_id)
        task = next((t for t in snapshot.get("tasks", []) if t.get("task_id") == task_id), None)
        if task is None:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' not found in run '{run_id}'")
        curr = task.get("current_attempt") or {}
        res = curr.get("result") or {}
        enriched_checks: List[Dict[str, Any]] = []
        for chk in res.get("checks", []):
            entry = dict(chk)
            for stream_key, preview_key in (
                ("stdout_artifact_id", "stdout_preview"),
                ("stderr_artifact_id", "stderr_preview"),
            ):
                art_id = entry.get(stream_key)
                entry[preview_key] = ""
                if art_id:
                    art_resp = await self._request(
                        "GET",
                        f"/v1/control-plane/runs/{run_id}/artifacts/{art_id}/content",
                        params={"max_bytes": 8_192},
                        allow_statuses=(404,),
                    )
                    if art_resp.status_code == 200:
                        entry[preview_key] = _bound_preview_text(str(art_resp.json().get("content") or ""))
            enriched_checks.append(entry)
        return redact(
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": curr.get("attempt_id"),
                "task_status": task.get("status"),
                "checks": enriched_checks,
                "failures": list(res.get("failures", ())),
            }
        )

    async def review_task(
        self,
        run_id: str,
        task_id: str,
        decision: str,
        reason: str,
        *,
        actor: str,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        decision_norm = decision.strip().lower()
        if decision_norm not in {"accepted", "rejected", "needs_repair"}:
            raise ContractViolation(
                "invalid_review_decision",
                f"Review decision must be accepted, rejected, or needs_repair; got '{decision}'",
            )
        if not reason.strip():
            raise ContractViolation("invalid_review_reason", "Review reason must be non-empty")

        snapshot = await self.get_run_snapshot(run_id)
        task = next((t for t in snapshot.get("tasks", []) if t.get("task_id") == task_id), None)
        if task is None:
            raise ContractViolation("resource_not_found", f"Task '{task_id}' not found in run '{run_id}'")
        res = (task.get("current_attempt") or {}).get("result")
        if not isinstance(res, dict):
            raise ContractViolation("resource_not_found", f"Task '{task_id}' has no result to review")

        effective_decision = "rejected" if decision_norm == "needs_repair" else decision_norm
        effective_reason = (
            reason.strip()
            if decision_norm != "needs_repair" or "needs_repair" in reason.lower()
            else f"needs_repair: {reason.strip()}"
        )
        rev = expected_revision if expected_revision is not None else int(res.get("revision", 1))
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/tasks/{task_id}/review",
            json_body={
                "decision": effective_decision,
                "reason": effective_reason,
                "expected_revision": rev,
                "actor": actor,
                "result_id": res.get("result_id"),
            },
        )
        payload = resp.json()
        payload["requested_decision"] = decision_norm
        return redact(payload)

    async def list_hitl(self, run_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/v1/control-plane/runs/{run_id}/interventions")
        return redact(list(resp.json()))

    async def reply_hitl(
        self, run_id: str, hitl_id: str, action: str, note: str, *, actor: str
    ) -> Dict[str, Any]:
        action_norm = action.strip().lower()
        clean_note = note.strip()
        if action_norm in {"approved", "approve", "yes"}:
            approved, response_text = True, clean_note or "approved"
        elif action_norm in {"rejected", "reject", "denied", "deny", "no"}:
            approved, response_text = False, clean_note or "rejected"
        elif action_norm == "answer":
            if not clean_note:
                raise ContractViolation("hitl_invalid", "Answer text is required for 'hitl-reply <id> answer <note>'")
            approved, response_text = True, clean_note
        else:
            raise ContractViolation("hitl_invalid", f"Unsupported HITL action '{action}'")

        cur = (await self._request("GET", f"/v1/control-plane/runs/{run_id}/interventions/{hitl_id}")).json()
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/interventions/{hitl_id}/response",
            headers={"Idempotency-Key": f"tui-hitl-{uuid.uuid4().hex[:16]}"},
            json_body={
                "response": response_text,
                "actor": actor,
                "expected_revision": int(cur["revision"]),
                "approved": approved,
            },
        )
        return redact(resp.json())

    async def list_conflicts(self, run_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/v1/control-plane/runs/{run_id}/conflicts")
        return redact(list(resp.json()))

    async def auto_repair_conflict(
        self,
        run_id: str,
        conflict_id: str,
        *,
        actor: str,
        max_repair_attempts: Optional[int] = None,
        repair_command: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if max_repair_attempts is not None:
            body["max_repair_attempts"] = max_repair_attempts
        if repair_command is not None:
            body["repair_command"] = list(repair_command)
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/conflicts/{conflict_id}/auto-repair",
            json_body=body,
        )
        return redact(resp.json())

    async def manual_conflict(
        self,
        run_id: str,
        conflict_id: str,
        *,
        actor: str,
        finalize: bool = False,
        worktree_path: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"finalize": finalize}
        if worktree_path is not None:
            body["worktree_path"] = worktree_path
        if commit_message is not None:
            body["commit_message"] = commit_message
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/conflicts/{conflict_id}/manual",
            json_body=body,
        )
        return redact(resp.json())

    async def discard_conflict(
        self, run_id: str, conflict_id: str, *, actor: str, reason: str = "operator_discarded"
    ) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/conflicts/{conflict_id}/discard",
            json_body={"reason": reason},
        )
        return redact(resp.json())

    async def integrate_run(
        self, run_id: str, *, target_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if target_branch is not None:
            body["target_branch"] = target_branch
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/integrate",
            json_body=body,
            allow_statuses=(422,),
        )
        data = resp.json()
        if resp.status_code == 422:
            if data.get("code") == "merge_conflict" or data.get("status") == IntegrationStatus.CONFLICTED.value:
                return redact(
                    {
                        "integration_id": data.get("integration_id"),
                        "run_id": run_id,
                        "status": IntegrationStatus.CONFLICTED.value,
                        "target_branch": target_branch or f"integrate/{run_id}",
                        "result_sha": None,
                        "conflicted_files": list(data.get("conflicted_files", ())),
                    }
                )
            self._raise_for_error(resp)
        return redact(data)

    async def get_pr_package(self, run_id: str) -> Optional[Dict[str, Any]]:
        resp = await self._request("GET", f"/v1/control-plane/runs/{run_id}/pr-package", allow_statuses=(404,))
        if resp.status_code == 404:
            return None
        return redact(resp.json())

    async def build_pr_package(
        self, run_id: str, *, pr_branch: Optional[str] = None, create_git_branch: bool = True
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"create_git_branch": create_git_branch}
        if pr_branch is not None:
            body["pr_branch"] = pr_branch
        resp = await self._request("POST", f"/v1/control-plane/runs/{run_id}/pr-package", json_body=body)
        return redact(resp.json())

    async def publish_pr_package(
        self,
        run_id: str,
        *,
        package_id: Optional[str] = None,
        authorized: bool = False,
        remote: str = "origin",
        actor: str = "operator",
    ) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            f"/v1/control-plane/runs/{run_id}/pr-package/publish",
            json_body={"authorized": authorized, "remote": remote},
        )
        return redact(resp.json())

    async def list_route_decisions(self, run_id: str) -> List[Dict[str, Any]]:
        resp = await self._request(
            "GET", f"/v1/control-plane/runs/{run_id}/route-decisions", allow_statuses=(404,)
        )
        if resp.status_code == 404:
            return []
        return redact(list(resp.json()))

    async def get_usage_metrics(self, run_id: str) -> Dict[str, Any]:
        resp = await self._request(
            "GET", f"/v1/control-plane/runs/{run_id}/metrics/usage", allow_statuses=(404,)
        )
        if resp.status_code == 404:
            return {}
        return redact(resp.json())

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class HydraTuiCockpit:
    """Interactive Rich-based orchestration cockpit over RunService or REST+SSE Control Plane."""

    HELP_TEXT = "\n".join(
        [
            "Available Cockpit Commands:",
            "  runs                                             List recent runs",
            "  select-run <run_id>                              Switch active run & reset cursor",
            "  route-inventory [scope_id]                       Inspect OmniRoute models, quotas & overrides",
            "  select-account <provider> <account_id> [scope]   Persist next-run account override",
            "  inspect-diff <task_id>                           Inspect redacted patch/diff summary",
            "  inspect-checks <task_id>                         Inspect acceptance checks & bounded logs",
            "  review <task_id> <accepted|rejected|needs_repair> <reason...>",
            "                                                   Apply explicit task review decision",
            "  hitl-list                                        List intervention requests",
            "  hitl-reply <hitl_id> <approved|rejected|answer> [note...]",
            "                                                   Respond to pending HITL gate",
            "  conflict-list                                    List conflict reports",
            "  conflict-auto <conflict_id>                      Attempt bounded merge auto-repair",
            "  conflict-manual <conflict_id> [--finalize]       Open or finalize manual conflict resolution",
            "  conflict-discard <conflict_id> [reason...]       Discard conflict resolution",
            "  integrate [target_branch]                        Integrate all accepted tasks",
            "  pr-build [pr_branch] [--no-create-git-branch]    Compile redacted PR package",
            "  pr-publish [--authorized] [--remote origin]      Publish PR branch (requires --authorized)",
            "  refresh (r) | help (h, ?) | quit (q)             Refresh, show help, or exit cockpit",
        ]
    )

    def __init__(
        self,
        *,
        run_service: Optional[RunService] = None,
        route_selector: Optional[RouteSelector] = None,
        omniroute_transport: Optional[httpx.AsyncBaseTransport] = None,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        api_token_env: str = "HYDRA_API_TOKEN",
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
        backend: Optional[CockpitBackend] = None,
        run_id: Optional[str] = None,
        principal_id: str = "operator",
        console: Optional[Console] = None,
        refresh_seconds: float = 2.0,
        no_alt_screen: bool = False,
        input_stream: Optional[TextIO] = None,
        command_queue: Optional[Union[Sequence[str], Iterable[str], asyncio.Queue[str]]] = None,
        max_steps: Optional[int] = None,
        once: bool = False,
        prompt_fn: Optional[Callable[[str], str]] = None,
    ):
        self.console = console or Console()
        self.principal_id = principal_id.strip() or "operator"
        self.refresh_seconds = max(float(refresh_seconds), 0.1)
        self.no_alt_screen = no_alt_screen
        self.input_stream = input_stream
        self.command_queue = command_queue
        self.max_steps = max_steps
        self.once = once
        self._prompt_fn = prompt_fn

        self._api_token: Optional[str] = None
        if backend is not None:
            self.backend: CockpitBackend = backend
            conn_mode: Literal["local", "http"] = backend.mode
            sanitized_url = getattr(backend, "base_url", None)
        elif api_url is not None:
            sanitized_url = sanitize_api_url(api_url)
            is_tty = bool(getattr(sys.stdin, "isatty", lambda: False)()) and input_stream is None and command_queue is None and not once
            resolved_token = resolve_api_token(
                api_token=api_token,
                api_token_env=api_token_env,
                interactive=is_tty,
                prompt_fn=prompt_fn,
            )
            self._api_token = resolved_token
            self.backend = HttpRunBackend(
                sanitized_url,
                api_token=resolved_token,
                transport=http_transport,
            )
            conn_mode = "http"
        else:
            if run_service is None:
                from hydra_orch.server import get_run_service

                run_service = get_run_service()
            self.backend = LocalRunBackend(
                run_service,
                route_selector=route_selector,
                omniroute_transport=omniroute_transport,
            )
            conn_mode = "local"
            sanitized_url = None

        self.state = CockpitState(
            connection_mode=conn_mode,
            api_url=sanitized_url,
            active_run_id=run_id.strip() if isinstance(run_id, str) and run_id.strip() else None,
        )
        self._cursor: Optional[EventCursor] = (
            EventCursor(run_id=self.state.active_run_id) if self.state.active_run_id else None
        )
        self._input_buffer: str = ""

    def _redaction_ctx(self):
        return redaction_scope([self._api_token]) if self._api_token else nullcontext()

    def _set_error(self, code: str, message: str) -> None:
        self.state.last_error_code = redact_text(code)
        self.state.last_error = redact_text(message)
        self.state.last_message = ""

    def _set_message(self, message: str) -> None:
        self.state.last_error_code = None
        self.state.last_error = None
        self.state.last_message = redact_text(message)

    def _format_exception(self, exc: Exception) -> Tuple[str, str]:
        if isinstance(exc, ContractViolation):
            return exc.code, redact_text(str(exc))
        if isinstance(exc, GitWorkspaceError):
            return exc.failure.code, redact_text(exc.failure.message)
        if isinstance(exc, OptimisticLockError):
            return "optimistic_lock_conflict", redact_text(str(exc))
        if isinstance(exc, IdempotencyConflictError):
            return "idempotency_conflict", redact_text(str(exc))
        if isinstance(exc, StorageIntegrityError):
            code = "resource_not_found" if "not found" in str(exc).lower() or "does not exist" in str(exc).lower() else "storage_integrity_error"
            return code, redact_text(str(exc))
        if isinstance(exc, StorageError):
            return "storage_error", redact_text(str(exc))
        if isinstance(exc, (ValidationError, ValueError)):
            return "validation_error", redact_text(str(exc))
        if isinstance(exc, httpx.HTTPError):
            return "http_error", redact_text(str(exc))
        return "cockpit_error", redact_text(str(exc))

    async def _ingest_events(self, run_id: str, events: Sequence[Dict[str, Any]]) -> int:
        if self._cursor is None or self._cursor.run_id != run_id:
            self._cursor = EventCursor(run_id=run_id)
        added = 0
        for ev in sorted(events, key=lambda item: int(item.get("seq", 0))):
            seq = int(ev.get("seq", 0))
            if seq <= 0 or seq in self.state.seen_seqs or seq <= self.state.last_seq:
                continue
            self.state.seen_seqs.add(seq)
            self.state.last_seq = max(self.state.last_seq, seq)
            self._cursor.last_seq = self.state.last_seq
            self.state.events.append(redact(ev))
            added += 1
        if len(self.state.events) > _MAX_EVENTS_RETAINED:
            self.state.events = self.state.events[-_MAX_EVENTS_RETAINED:]
        return added

    async def refresh(self) -> CockpitState:
        """Reload run snapshot, governance readiness, OmniRoute inventory, and incremental events."""
        with self._redaction_ctx():
            self.state.runs = await self.backend.list_runs(limit=20)
            if self.state.active_run_id is None and self.state.runs:
                self.state.active_run_id = str(self.state.runs[0].get("run_id") or self.state.runs[0].get("id"))
                self.state.events.clear()
                self.state.seen_seqs.clear()
                self.state.last_seq = 0
                self._cursor = EventCursor(run_id=self.state.active_run_id)

            run_id = self.state.active_run_id
            scope_id = run_id or "default"
            try:
                self.state.route_inventory = await self.backend.get_route_inventory(scope_id=scope_id)
            except Exception as exc:
                code, msg = self._format_exception(exc)
                self.state.route_inventory = {
                    "connection_mode": "unknown",
                    "available": False,
                    "models": [],
                    "accounts": [],
                    "quota": _unknown_quota_payload(),
                    "next_account_overrides": {},
                    "error": f"{code}: {msg}",
                }

            if not run_id:
                self.state.snapshot = None
                self.state.hitl_requests = []
                self.state.conflicts = []
                self.state.pr_package = None
                self.state.route_decisions = []
                self.state.metrics_usage = {}
                return self.state

            self.state.snapshot = await self.backend.get_run_snapshot(run_id)
            self.state.hitl_requests = await self.backend.list_hitl(run_id)
            self.state.conflicts = await self.backend.list_conflicts(run_id)
            self.state.pr_package = await self.backend.get_pr_package(run_id)
            self.state.route_decisions = await self.backend.list_route_decisions(run_id)
            self.state.metrics_usage = await self.backend.get_usage_metrics(run_id)

            events, reset_required = await self.backend.replay_events(run_id, after_seq=self.state.last_seq)
            if reset_required:
                self.state.events.clear()
                self.state.seen_seqs.clear()
                self.state.last_seq = 0
                self._cursor = EventCursor(run_id=run_id)
                self.state.snapshot = await self.backend.get_run_snapshot(run_id)
                events, _ = await self.backend.replay_events(run_id, after_seq=0)
            await self._ingest_events(run_id, events)
            return self.state

    def _require_active_run(self) -> str:
        if not self.state.active_run_id:
            raise ContractViolation("no_active_run", "No run selected; use 'runs' and 'select-run <run_id>'")
        return self.state.active_run_id

    @staticmethod
    def _format_runs_detail(runs: Sequence[Dict[str, Any]]) -> str:
        if not runs:
            return "No runs persisted yet."
        lines = []
        for item in runs:
            rid = item.get("run_id") or item.get("id")
            lines.append(
                f"{rid} | mode={item.get('mode', '—')} | status={item.get('status', '—')} "
                f"| rev={item.get('revision', '—')} | {_safe_str(item.get('objective', ''))[:70]}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_route_inventory_detail(inv: Dict[str, Any]) -> str:
        lines = [
            f"connection_mode: {inv.get('connection_mode', 'unknown')} | "
            f"available: {inv.get('available', False)} | "
            f"direct_mode_supported: {inv.get('direct_mode_supported', True)}",
            "Quota:",
        ]
        quota = inv.get("quota") or {}
        if isinstance(quota, dict):
            for key, entry in quota.items():
                if isinstance(entry, dict):
                    lines.append(f"  - {key}: {format_quota_entry(entry)}")
        models = inv.get("models") or []
        lines.append(f"Models ({len(models)}):")
        for m in models[:15]:
            if isinstance(m, dict):
                lines.append(f"  - {m.get('id')} (provider={m.get('provider', 'unknown')})")
        accounts = inv.get("accounts") or []
        lines.append(f"Accounts ({len(accounts)}):")
        for acc in accounts[:15]:
            if isinstance(acc, dict):
                lines.append(
                    f"  - {acc.get('provider', 'unknown')}/{acc.get('account_id')}: "
                    f"{format_quota_entry(acc)}"
                )
        overrides = inv.get("next_account_overrides") or {}
        lines.append(f"Next-Run Overrides ({len(overrides)}):")
        for prov, ov in overrides.items():
            if isinstance(ov, dict):
                lines.append(
                    f"  - {prov} -> {ov.get('account_id')} (applies_to={ov.get('applies_to', 'next_run')}, scope={ov.get('scope_id')})"
                )
        return redact_text("\n".join(lines))

    @staticmethod
    def _format_diff_detail(diff: Dict[str, Any]) -> str:
        changed = ", ".join(diff.get("changed_files") or []) or "none"
        header = [
            f"task={diff.get('task_id')} attempt={diff.get('attempt_id') or '—'}",
            f"worktree={_safe_str(diff.get('workspace_path'))}",
            f"patch_sha={diff.get('patch_commit_sha') or '—'} artifact={diff.get('patch_artifact_id') or '—'}",
            f"changed_files={changed}",
            "-" * 60,
            str(diff.get("preview") or ""),
        ]
        return redact_text("\n".join(header))

    @staticmethod
    def _format_checks_detail(checks_info: Dict[str, Any]) -> str:
        lines = [
            f"task={checks_info.get('task_id')} attempt={checks_info.get('attempt_id') or '—'} status={checks_info.get('task_status', '—')}"
        ]
        checks = checks_info.get("checks") or []
        if not checks:
            lines.append("No check results recorded yet.")
        for chk in checks:
            cmd = " ".join(str(x) for x in chk.get("command", ()))
            lines.append(
                f"[{chk.get('check_id')}] exit={chk.get('exit_code')} "
                f"dur={float(chk.get('duration_seconds', 0.0)):.3f}s sha={str(chk.get('tested_sha', ''))[:10]} cmd={cmd}"
            )
            if chk.get("stdout_preview"):
                lines.append(f"  stdout:\n{chk['stdout_preview']}")
            if chk.get("stderr_preview"):
                lines.append(f"  stderr:\n{chk['stderr_preview']}")
        for fail in checks_info.get("failures") or []:
            lines.append(f"FAILURE [{fail.get('code')}]: {fail.get('message')}")
        return redact_text("\n".join(lines))

    @staticmethod
    def _format_hitl_detail(items: Sequence[Dict[str, Any]]) -> str:
        if not items:
            return "No intervention requests for active run."
        lines = []
        for req in items:
            lines.append(
                f"{req.get('request_id')} | state={req.get('state')} | kind={req.get('kind')} "
                f"| task={req.get('task_id') or '—'} | rev={req.get('revision')} | Q: {req.get('question')}"
            )
            if req.get("response"):
                lines.append(f"  reply ({req.get('actor')}): {req.get('response')}")
        return redact_text("\n".join(lines))

    @staticmethod
    def _format_conflicts_detail(reports: Sequence[Dict[str, Any]]) -> str:
        if not reports:
            return "No conflicts recorded for active run."
        lines = []
        for rep in reports:
            files = ", ".join(rep.get("conflicted_files") or ())
            lines.append(
                f"{rep.get('conflict_id')} | status={rep.get('status')} "
                f"| repair={rep.get('repair_attempts_used', 0)}/{rep.get('max_repair_attempts', 0)} "
                f"| files=[{files}] | worktree={_safe_str(rep.get('repair_worktree_path'))}"
            )
            for fd in rep.get("file_details") or ():
                if fd.get("merged_preview"):
                    lines.append(f"  --- {fd.get('path')} ---\n{_bound_preview_text(str(fd.get('merged_preview')))}")
        return redact_text("\n".join(lines))

    async def execute_command(self, raw_line: str) -> CockpitCommandOutcome:
        """Execute a single line command or shortcut deterministically without crashing."""
        with self._redaction_ctx():
            tokens = _safe_split_command(raw_line)
            if not tokens:
                await self.refresh()
                self._set_message("Refreshed cockpit state")
                return CockpitCommandOutcome(command="refresh", ok=True, message=self.state.last_message)

            cmd = tokens[0].lower()
            args = tokens[1:]
            aliases = {
                "h": "help",
                "?": "help",
                "r": "refresh",
                "q": "quit",
                "exit": "quit",
                "list-runs": "runs",
                "use": "select-run",
                "routes": "route-inventory",
                "quota": "route-inventory",
                "i": "route-inventory",
                "diff": "inspect-diff",
                "checks": "inspect-checks",
                "hitl": "hitl-list",
                "l": "hitl-list",
                "conflicts": "conflict-list",
                "c": "conflict-list",
                "g": "integrate",
                "p": "pr-build",
            }
            cmd = aliases.get(cmd, cmd)

            try:
                if cmd == "quit":
                    self._set_message("Cockpit exited cleanly")
                    return CockpitCommandOutcome(command="quit", ok=True, should_quit=True, message=self.state.last_message)

                if cmd == "help":
                    self.state.detail_title = "Help — Cockpit Commands"
                    self.state.detail_body = self.HELP_TEXT
                    self._set_message("Displayed command reference")
                    return CockpitCommandOutcome(command="help", ok=True, message=self.state.last_message)

                if cmd == "refresh":
                    await self.refresh()
                    self._set_message(f"Refreshed run={self.state.active_run_id or 'none'} (last_seq={self.state.last_seq})")
                    return CockpitCommandOutcome(command="refresh", ok=True, message=self.state.last_message)

                if cmd == "runs":
                    runs = await self.backend.list_runs(limit=20)
                    self.state.runs = runs
                    self.state.detail_title = f"Runs ({len(runs)})"
                    self.state.detail_body = self._format_runs_detail(runs)
                    self._set_message(f"Listed {len(runs)} run(s)")
                    return CockpitCommandOutcome(command="runs", ok=True, message=self.state.last_message, data=runs)

                if cmd == "select-run":
                    if len(args) != 1:
                        raise ContractViolation("invalid_command", "Usage: select-run <run_id>")
                    target_run = args[0]
                    await self.backend.get_run_snapshot(target_run)
                    self.state.active_run_id = target_run
                    self.state.events.clear()
                    self.state.seen_seqs.clear()
                    self.state.last_seq = 0
                    self._cursor = EventCursor(run_id=target_run)
                    await self.refresh()
                    self._set_message(f"Switched active run to {target_run}")
                    return CockpitCommandOutcome(command="select-run", ok=True, message=self.state.last_message, data={"run_id": target_run})

                if cmd == "route-inventory":
                    scope_id = args[0] if args else (self.state.active_run_id or "default")
                    inv = await self.backend.get_route_inventory(scope_id=scope_id)
                    self.state.route_inventory = inv
                    self.state.detail_title = f"OmniRoute Inventory ({scope_id})"
                    self.state.detail_body = self._format_route_inventory_detail(inv)
                    self._set_message(f"Loaded route inventory for scope={scope_id}")
                    return CockpitCommandOutcome(command="route-inventory", ok=True, message=self.state.last_message, data=inv)

                if cmd == "select-account":
                    if len(args) not in {2, 3}:
                        raise ContractViolation("invalid_command", "Usage: select-account <provider> <account_id> [scope_id]")
                    provider, account_id = args[0], args[1]
                    scope_id = args[2] if len(args) == 3 else (self.state.active_run_id or "default")
                    override = await self.backend.select_account(
                        scope_id,
                        provider,
                        account_id,
                        principal_id=self.principal_id,
                    )
                    await self.refresh()
                    self._set_message(
                        f"Selected next-run account {override['provider']}/{override['account_id']} (scope={override['scope_id']})"
                    )
                    return CockpitCommandOutcome(command="select-account", ok=True, message=self.state.last_message, data=override)

                if cmd == "inspect-diff":
                    if len(args) != 1:
                        raise ContractViolation("invalid_command", "Usage: inspect-diff <task_id>")
                    run_id = self._require_active_run()
                    diff = await self.backend.inspect_diff(run_id, args[0])
                    self.state.detail_title = f"Diff — {args[0]}"
                    self.state.detail_body = self._format_diff_detail(diff)
                    self._set_message(f"Inspected diff for task {args[0]}")
                    return CockpitCommandOutcome(command="inspect-diff", ok=True, message=self.state.last_message, data=diff)

                if cmd == "inspect-checks":
                    if len(args) != 1:
                        raise ContractViolation("invalid_command", "Usage: inspect-checks <task_id>")
                    run_id = self._require_active_run()
                    checks_info = await self.backend.inspect_checks(run_id, args[0])
                    self.state.detail_title = f"Checks — {args[0]}"
                    self.state.detail_body = self._format_checks_detail(checks_info)
                    self._set_message(f"Inspected checks for task {args[0]}")
                    return CockpitCommandOutcome(command="inspect-checks", ok=True, message=self.state.last_message, data=checks_info)

                if cmd == "review":
                    if len(args) < 3:
                        raise ContractViolation(
                            "invalid_command",
                            "Usage: review <task_id> <accepted|rejected|needs_repair> <reason>",
                        )
                    run_id = self._require_active_run()
                    task_id, decision = args[0], args[1]
                    reason = " ".join(args[2:])
                    reviewed = await self.backend.review_task(
                        run_id,
                        task_id,
                        decision,
                        reason,
                        actor=self.principal_id,
                    )
                    await self.refresh()
                    self._set_message(
                        f"Reviewed {task_id}: decision={reviewed['decision']} task_status={reviewed['task_status']} rev={reviewed['revision']}"
                    )
                    return CockpitCommandOutcome(command="review", ok=True, message=self.state.last_message, data=reviewed)

                if cmd == "hitl-list":
                    run_id = self._require_active_run()
                    items = await self.backend.list_hitl(run_id)
                    self.state.hitl_requests = items
                    self.state.detail_title = f"HITL Interventions ({len(items)})"
                    self.state.detail_body = self._format_hitl_detail(items)
                    self._set_message(f"Loaded {len(items)} HITL intervention(s)")
                    return CockpitCommandOutcome(command="hitl-list", ok=True, message=self.state.last_message, data=items)

                if cmd == "hitl-reply":
                    if len(args) < 2:
                        raise ContractViolation(
                            "invalid_command",
                            "Usage: hitl-reply <hitl_id> <approved|rejected|answer> [note]",
                        )
                    run_id = self._require_active_run()
                    hitl_id, action = args[0], args[1]
                    note = " ".join(args[2:])
                    updated = await self.backend.reply_hitl(
                        run_id,
                        hitl_id,
                        action,
                        note,
                        actor=self.principal_id,
                    )
                    await self.refresh()
                    self._set_message(f"HITL {hitl_id} resolved -> state={updated.get('state')}")
                    return CockpitCommandOutcome(command="hitl-reply", ok=True, message=self.state.last_message, data=updated)

                if cmd == "conflict-list":
                    run_id = self._require_active_run()
                    reports = await self.backend.list_conflicts(run_id)
                    self.state.conflicts = reports
                    self.state.detail_title = f"Conflicts ({len(reports)})"
                    self.state.detail_body = self._format_conflicts_detail(reports)
                    self._set_message(f"Loaded {len(reports)} conflict report(s)")
                    return CockpitCommandOutcome(command="conflict-list", ok=True, message=self.state.last_message, data=reports)

                if cmd == "conflict-auto":
                    if not args:
                        raise ContractViolation("invalid_command", "Usage: conflict-auto <conflict_id>")
                    run_id = self._require_active_run()
                    conflict_id = args[0]
                    max_att: Optional[int] = None
                    idx = 1
                    while idx < len(args):
                        if args[idx] == "--max-repair-attempts" and idx + 1 < len(args):
                            max_att = int(args[idx + 1])
                            idx += 2
                        else:
                            raise ContractViolation("invalid_command", f"Unknown flag '{args[idx]}' for conflict-auto")
                    res = await self.backend.auto_repair_conflict(
                        run_id,
                        conflict_id,
                        actor=self.principal_id,
                        max_repair_attempts=max_att,
                    )
                    await self.refresh()
                    self._set_message(
                        f"Conflict {conflict_id} auto-repair -> status={res.get('status')} repaired={res.get('repaired')}"
                    )
                    return CockpitCommandOutcome(command="conflict-auto", ok=True, message=self.state.last_message, data=res)

                if cmd == "conflict-manual":
                    if not args:
                        raise ContractViolation(
                            "invalid_command",
                            "Usage: conflict-manual <conflict_id> [--finalize] [--worktree-path PATH]",
                        )
                    run_id = self._require_active_run()
                    conflict_id = args[0]
                    finalize = False
                    wt_path: Optional[str] = None
                    idx = 1
                    while idx < len(args):
                        if args[idx] == "--finalize":
                            finalize = True
                            idx += 1
                        elif args[idx] == "--worktree-path" and idx + 1 < len(args):
                            wt_path = args[idx + 1]
                            idx += 2
                        else:
                            raise ContractViolation("invalid_command", f"Unknown flag '{args[idx]}' for conflict-manual")
                    res = await self.backend.manual_conflict(
                        run_id,
                        conflict_id,
                        actor=self.principal_id,
                        finalize=finalize,
                        worktree_path=wt_path,
                    )
                    await self.refresh()
                    self._set_message(
                        f"Conflict {conflict_id} manual -> status={res.get('status')} worktree={_safe_str(res.get('repair_worktree_path'))}"
                    )
                    return CockpitCommandOutcome(command="conflict-manual", ok=True, message=self.state.last_message, data=res)

                if cmd == "conflict-discard":
                    if not args:
                        raise ContractViolation("invalid_command", "Usage: conflict-discard <conflict_id> [reason]")
                    run_id = self._require_active_run()
                    conflict_id = args[0]
                    reason = " ".join(args[1:]) or "operator_discarded"
                    res = await self.backend.discard_conflict(run_id, conflict_id, actor=self.principal_id, reason=reason)
                    await self.refresh()
                    self._set_message(f"Conflict {conflict_id} -> status={res.get('status')}")
                    return CockpitCommandOutcome(command="conflict-discard", ok=True, message=self.state.last_message, data=res)

                if cmd == "integrate":
                    if len(args) > 1:
                        raise ContractViolation("invalid_command", "Usage: integrate [target_branch]")
                    run_id = self._require_active_run()
                    target_branch = args[0] if args else None
                    outcome = await self.backend.integrate_run(run_id, target_branch=target_branch)
                    await self.refresh()
                    status_val = outcome.get("status")
                    if status_val == IntegrationStatus.CONFLICTED.value:
                        files = ", ".join(outcome.get("conflicted_files") or ())
                        self._set_error(
                            "merge_conflict",
                            f"Integration {outcome.get('integration_id')} conflicted on [{files}]; use conflict-list",
                        )
                        return CockpitCommandOutcome(
                            command="integrate",
                            ok=False,
                            error_code="merge_conflict",
                            message=self.state.last_error or "",
                            data=outcome,
                        )
                    self._set_message(
                        f"Integrated run {run_id} -> {outcome.get('target_branch')} ({str(outcome.get('result_sha') or '')[:10]})"
                    )
                    return CockpitCommandOutcome(command="integrate", ok=True, message=self.state.last_message, data=outcome)

                if cmd == "pr-build":
                    run_id = self._require_active_run()
                    pr_branch: Optional[str] = None
                    create_git_branch = True
                    for arg in args:
                        if arg in {"--no-create-git-branch", "--no-branch"}:
                            create_git_branch = False
                        elif arg.startswith("-"):
                            raise ContractViolation("invalid_command", f"Unknown flag '{arg}' for pr-build")
                        elif pr_branch is None:
                            pr_branch = arg
                        else:
                            raise ContractViolation("invalid_command", "Usage: pr-build [pr_branch] [--no-create-git-branch]")
                    pkg = await self.backend.build_pr_package(
                        run_id,
                        pr_branch=pr_branch,
                        create_git_branch=create_git_branch,
                    )
                    await self.refresh()
                    self.state.detail_title = f"PR Package — {pkg.get('package_id')}"
                    self.state.detail_body = redact_text(str(pkg.get("description_markdown") or ""))
                    self._set_message(f"Built PR package {pkg.get('package_id')} on branch {pkg.get('pr_branch')}")
                    return CockpitCommandOutcome(command="pr-build", ok=True, message=self.state.last_message, data=pkg)

                if cmd == "pr-publish":
                    run_id = self._require_active_run()
                    authorized = False
                    remote = "origin"
                    package_id: Optional[str] = None
                    idx = 0
                    while idx < len(args):
                        arg = args[idx]
                        if arg == "--authorized":
                            authorized = True
                            idx += 1
                        elif arg == "--remote" and idx + 1 < len(args):
                            remote = args[idx + 1]
                            idx += 2
                        elif arg.startswith("-"):
                            raise ContractViolation("invalid_command", f"Unknown flag '{arg}' for pr-publish")
                        elif package_id is None:
                            package_id = arg
                            idx += 1
                        else:
                            raise ContractViolation("invalid_command", "Usage: pr-publish [--authorized] [--remote origin]")
                    pub = await self.backend.publish_pr_package(
                        run_id,
                        package_id=package_id,
                        authorized=authorized,
                        remote=remote,
                        actor=self.principal_id,
                    )
                    await self.refresh()
                    self._set_message(
                        f"Published PR package {pub.get('package_id')} to {pub.get('remote')} ({pub.get('pr_branch')})"
                    )
                    return CockpitCommandOutcome(command="pr-publish", ok=True, message=self.state.last_message, data=pub)

                raise ContractViolation("unknown_command", f"Unknown command '{cmd}'. Type 'help' for commands.")

            except Exception as exc:
                code, msg = self._format_exception(exc)
                self._set_error(code, msg)
                return CockpitCommandOutcome(
                    command=cmd,
                    ok=False,
                    error_code=code,
                    message=msg,
                )

    def _compute_readiness(self) -> Dict[str, str]:
        snap = self.state.snapshot
        if not snap:
            return {
                "hitl": "0 pending",
                "conflicts": "0 open",
                "integration": "unavailable",
                "pr_package": "none",
                "budget": "unknown",
            }
        pending_hitl = sum(1 for h in self.state.hitl_requests if h.get("state") == "pending")
        open_conflicts = sum(1 for c in self.state.conflicts if c.get("status") in {"open", "auto_repair", "manual"})
        tasks = snap.get("tasks", [])
        all_accepted = bool(tasks) and all(t.get("status") == TaskStatus.ACCEPTED.value for t in tasks)
        run_status = str(snap.get("status") or "unknown")
        if run_status == "succeeded":
            int_state = "integrated"
        elif pending_hitl > 0 or open_conflicts > 0:
            int_state = "blocked"
        elif all_accepted:
            int_state = "ready"
        else:
            int_state = "awaiting_review"

        pkg = self.state.pr_package
        pr_state = f"{pkg.get('package_id')} ({pkg.get('pr_branch')})" if pkg else ("ready_to_build" if run_status == "succeeded" else "not_built")

        budget = snap.get("budget") or {}
        cur_usd = budget.get("current_usd")
        max_usd = budget.get("max_usd")
        if cur_usd is None:
            usd_text = "unknown"
        else:
            usd_text = f"${cur_usd:.4f}"
        if max_usd is not None:
            usd_text = f"{usd_text} / ${max_usd:.2f}"
        budget_state = f"{budget.get('status', 'unknown')} ({usd_text})"

        return {
            "hitl": f"{pending_hitl} pending" if pending_hitl else "0 pending",
            "conflicts": f"{open_conflicts} open" if open_conflicts else "0 open",
            "integration": int_state,
            "pr_package": pr_state,
            "budget": budget_state,
        }

    def _build_header_panel(self) -> Panel:
        snap = self.state.snapshot
        readiness = self._compute_readiness()
        conn_label = f"http ({_safe_str(self.state.api_url)})" if self.state.connection_mode == "http" else "local (RunService)"
        if not snap:
            content = Group(
                _safe_text(f"HYDRA-ORCH COCKPIT | connection={conn_label} | active_run=none", style="bold cyan"),
                _safe_text("No active run loaded. Use 'runs' then 'select-run <run_id>' or submit a run.", style="yellow"),
            )
            return Panel(content, title="Hydra Orchestration Cockpit", border_style="cyan")

        mode = str(snap.get("mode") or snap.get("spec", {}).get("orchestration_mode") or "unknown")
        line1 = _safe_text(
            f"Run: {snap.get('run_id')} | Project: {snap.get('project_id')} | "
            f"Mode: {mode} | Status: {snap.get('status')} (rev {snap.get('revision')}) | "
            f"Base: {str(snap.get('base_sha', ''))[:10]} | Conn: {conn_label}",
            style="bold white",
        )
        line2 = _safe_text(f"Objective: {snap.get('objective', '')}", style="dim")
        line3 = _safe_text(
            f"HITL: {readiness['hitl']} | Conflicts: {readiness['conflicts']} | "
            f"Integration: {readiness['integration']} | PR: {readiness['pr_package']} | Budget: {readiness['budget']}",
            style="cyan",
        )
        return Panel(Group(line1, line2, line3), title="Live Run Overview", border_style="cyan")

    def _build_tasks_panel(self) -> Panel:
        snap = self.state.snapshot
        if not snap:
            return Panel(_safe_text("No run tasks to display."), title="Orchestration Matrix", border_style="blue")

        tasks = snap.get("tasks", [])
        mode = str(snap.get("mode") or snap.get("spec", {}).get("orchestration_mode") or "relay")
        wave_map = compute_task_waves(tasks, mode)

        tree = Tree(_safe_text(f"Mode: {mode.upper()} ({len(tasks)} tasks)", style="bold cyan"))
        if mode == "swarm":
            w0_branch = tree.add(_safe_text("Wave 0 — Foundation", style="bold yellow"))
            w1_branch = tree.add(_safe_text("Wave 1+ — Parallel Workers", style="bold green"))
            for t in tasks:
                tid = str(t.get("task_id") or t.get("id"))
                depth, _ = wave_map.get(tid, (0, ""))
                deps = ", ".join(t.get("dependencies") or ()) or "root"
                node_txt = _safe_text(f"{tid} [{t.get('status')}] (deps={deps})")
                (w0_branch if depth == 0 else w1_branch).add(node_txt)
        else:
            for idx, t in enumerate(tasks, start=1):
                tid = str(t.get("task_id") or t.get("id"))
                att = t.get("current_attempt") or {}
                att_count = len(t.get("attempts") or ())
                handoff_txt = f"attempts={att_count}" + (f", model={att.get('model')}" if att else "")
                tree.add(_safe_text(f"Step {idx}: {tid} [{t.get('status')}] ({handoff_txt})"))

        table = Table(expand=True, border_style="blue")
        table.add_column("Wave/Step", overflow="fold")
        table.add_column("Task ID", overflow="fold")
        table.add_column("Status", overflow="fold")
        table.add_column("Executor", overflow="fold")
        table.add_column("Model", overflow="fold")
        table.add_column("Provider", overflow="fold")
        table.add_column("Worktree Path", overflow="fold")
        table.add_column("Last Check", overflow="fold")
        table.add_column("Rev", overflow="fold")

        for t in tasks:
            tid = str(t.get("task_id") or t.get("id"))
            _, wave_label = wave_map.get(tid, (0, "—"))
            spec = t.get("spec") or {}
            att = t.get("current_attempt") or {}
            res = att.get("result") or {}
            executor = att.get("executor_id") or spec.get("assigned_executor") or "—"
            model = att.get("model") or "—"
            provider = att.get("provider") or "—"
            worktree = att.get("workspace_path") or "—"
            check_txt = att.get("last_check_summary") or _summarize_checks(res.get("checks", []))
            res_rev = res.get("revision") if isinstance(res, dict) and res.get("revision") is not None else t.get("revision", "—")
            table.add_row(
                _safe_text(wave_label),
                _safe_text(tid),
                _safe_text(t.get("status")),
                _safe_text(executor),
                _safe_text(model),
                _safe_text(provider),
                _safe_text(worktree),
                _safe_text(check_txt),
                _safe_text(res_rev),
            )

        return Panel(Group(tree, table), title="Orchestration & Task Attempt Matrix", border_style="blue")

    def _build_governance_panel(self) -> Panel:
        inv = self.state.route_inventory or {}
        quota = inv.get("quota") or {}

        q_table = Table(title="OmniRoute Quota & Overrides", expand=True, border_style="green")
        q_table.add_column("Provider / Key", overflow="fold")
        q_table.add_column("Quota", overflow="fold")
        q_table.add_column("Next-Run Override", overflow="fold")

        overrides = inv.get("next_account_overrides") or {}
        seen_keys: set[str] = set()
        if isinstance(quota, dict):
            for key, entry in quota.items():
                if not isinstance(entry, dict):
                    continue
                seen_keys.add(key)
                ov = overrides.get(key)
                ov_str = f"{ov.get('account_id')} (next_run)" if isinstance(ov, dict) else "—"
                q_table.add_row(_safe_text(key), _safe_text(format_quota_entry(entry)), _safe_text(ov_str))
        for prov, ov in overrides.items():
            if prov not in seen_keys and isinstance(ov, dict):
                q_table.add_row(_safe_text(prov), _safe_text("— (unknown)"), _safe_text(f"{ov.get('account_id')} (next_run)"))

        hitl_lines = [
            f"- {h.get('request_id')} [{h.get('state')}] ({h.get('kind')}, rev={h.get('revision')}): {h.get('question')}"
            for h in self.state.hitl_requests[:5]
        ] or ["- None"]

        cfl_lines = [
            f"- {c.get('conflict_id')} [{c.get('status')}] files={','.join(c.get('conflicted_files') or ())}"
            for c in self.state.conflicts[:5]
        ] or ["- None"]

        pkg = self.state.pr_package
        pr_line = (
            f"PR Package: {pkg.get('package_id')} branch={pkg.get('pr_branch')} head={str(pkg.get('head_sha') or '')[:10]}"
            if pkg
            else "PR Package: not built"
        )

        usage = self.state.metrics_usage.get("usage", {}) if isinstance(self.state.metrics_usage, dict) else {}
        cost_entry = usage.get("cost", {}) if isinstance(usage, dict) else {}
        cost_val = cost_entry.get("value")
        cost_display = f"${cost_val}" if cost_val is not None else "unknown"
        usage_line = f"Telemetry Cost: {cost_display} (status={cost_entry.get('status', 'unknown')})"

        body = Group(
            _safe_text(f"Gateway mode={inv.get('connection_mode', 'unknown')} | available={inv.get('available', False)} | {usage_line}"),
            q_table,
            _safe_text("HITL Gates:\n" + "\n".join(hitl_lines), style="yellow"),
            _safe_text("Conflicts:\n" + "\n".join(cfl_lines), style="magenta"),
            _safe_text(pr_line, style="green"),
        )
        return Panel(body, title="Routes, HITL, Conflicts & PR Readiness", border_style="green")

    def _build_events_panel(self) -> Panel:
        table = Table(expand=True, border_style="dim")
        table.add_column("Seq", width=5)
        table.add_column("Event", overflow="fold")
        table.add_column("Task", overflow="fold")
        table.add_column("Summary", overflow="fold")

        recent = self.state.events[-12:]
        if not recent:
            return Panel(_safe_text(f"Cursor seq={self.state.last_seq} (no events replayed yet)"), title="Event Feed (Last-Event-ID)", border_style="dim")

        for ev in recent:
            payload_str = json.dumps(ev.get("payload") or {}, sort_keys=True)
            if len(payload_str) > 100:
                payload_str = payload_str[:97] + "..."
            table.add_row(
                _safe_text(ev.get("seq")),
                _safe_text(ev.get("event_type")),
                _safe_text(ev.get("task_id") or "—"),
                _safe_text(payload_str),
            )
        return Panel(table, title=f"Event Feed (Last-Event-ID={self.state.last_seq})", border_style="dim")

    def _build_detail_panel(self) -> Panel:
        return Panel(
            _safe_text(self.state.detail_body),
            title=_safe_str(self.state.detail_title),
            border_style="white",
        )

    def _build_footer_panel(self) -> Panel:
        if self.state.last_error:
            banner = _safe_text(
                f"ERROR [{self.state.last_error_code or 'error'}]: {self.state.last_error}",
                style="bold red",
            )
        elif self.state.last_message:
            banner = _safe_text(f"OK: {self.state.last_message}", style="bold green")
        else:
            banner = _safe_text("Ready.", style="dim")

        hints = _safe_text(
            "Commands: select-run | route-inventory | select-account | inspect-diff | inspect-checks | "
            "review | hitl-list | hitl-reply | conflict-list | conflict-auto | conflict-manual | "
            "integrate | pr-build | pr-publish --authorized | refresh (r) | help (h) | quit (q)",
            style="dim",
        )
        items: List[Text] = [banner, hints]
        if self._input_buffer:
            items.append(_safe_text(f"hydra> {self._input_buffer}_", style="bold cyan"))
        return Panel(Group(*items), border_style="red" if self.state.last_error else "cyan")

    def build_layout(self) -> Layout:
        """Assemble the full Rich Layout representing the current cockpit state."""
        root = Layout(name="root")
        root.split_column(
            Layout(self._build_header_panel(), name="header", size=6),
            Layout(name="main", ratio=1),
            Layout(self._build_footer_panel(), name="footer", size=5 if not self._input_buffer else 6),
        )
        root["main"].split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2),
        )
        root["left"].split_column(
            Layout(self._build_tasks_panel(), name="tasks", ratio=3),
            Layout(self._build_detail_panel(), name="detail", ratio=2),
        )
        root["right"].split_column(
            Layout(self._build_governance_panel(), name="governance", ratio=3),
            Layout(self._build_events_panel(), name="events", ratio=2),
        )
        return root

    def render_text(self, *, width: int = 160) -> str:
        """Render the dashboard deterministically to plain redacted text (safe for tests and logs)."""
        buf = io.StringIO()
        rec_console = Console(
            file=buf,
            width=width,
            height=60,
            force_terminal=False,
            color_system=None,
            legacy_windows=False,
        )
        with self._redaction_ctx():
            rec_console.print(self.build_layout())
        return redact_text(buf.getvalue())

    def render(self) -> None:
        """Print the current cockpit dashboard to the active console."""
        with self._redaction_ctx():
            self.console.print(self.build_layout())

    def _is_interactive_tty(self) -> bool:
        if self.once or self.input_stream is not None or self.command_queue is not None:
            return False
        stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
        stdout_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        return stdin_tty and stdout_tty

    def _step_limit_reached(self) -> bool:
        return self.max_steps is not None and self.state.step_count >= self.max_steps

    async def _run_scripted_loop(self) -> None:
        if self.command_queue is not None:
            if isinstance(self.command_queue, asyncio.Queue):
                while not self._step_limit_reached():
                    try:
                        line = await asyncio.wait_for(self.command_queue.get(), timeout=self.refresh_seconds)
                    except asyncio.TimeoutError:
                        await self.refresh()
                        self.state.step_count += 1
                        self.render()
                        continue
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    outcome = await self.execute_command(stripped)
                    self.state.step_count += 1
                    self.render()
                    if outcome.should_quit:
                        break
            else:
                for line in self.command_queue:
                    if self._step_limit_reached():
                        break
                    stripped = str(line).strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    outcome = await self.execute_command(stripped)
                    self.state.step_count += 1
                    self.render()
                    if outcome.should_quit:
                        break
            return

        if self.input_stream is not None:
            while not self._step_limit_reached():
                line = self.input_stream.readline()
                if line == "":
                    break
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                outcome = await self.execute_command(stripped)
                self.state.step_count += 1
                self.render()
                if outcome.should_quit:
                    break
            return

        # Non-TTY fallback without explicit queue/stream: read stdin lines cleanly if piped
        while not self._step_limit_reached():
            line = sys.stdin.readline()
            if line == "":
                break
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            outcome = await self.execute_command(stripped)
            self.state.step_count += 1
            self.render()
            if outcome.should_quit:
                break

    async def _run_interactive_tty_loop(self) -> None:
        if os.name == "nt":
            try:
                import msvcrt

                with Live(
                    self.build_layout(),
                    console=self.console,
                    screen=not self.no_alt_screen,
                    auto_refresh=False,
                ) as live:
                    last_refresh = time.monotonic()
                    while not self._step_limit_reached():
                        while msvcrt.kbhit():
                            ch = msvcrt.getwch()
                            if ch in {"\x03", "\x04"}:
                                return
                            if ch in {"\r", "\n"}:
                                line = self._input_buffer.strip()
                                self._input_buffer = ""
                                outcome = await self.execute_command(line or "refresh")
                                self.state.step_count += 1
                                last_refresh = time.monotonic()
                                live.update(self.build_layout(), refresh=True)
                                if outcome.should_quit:
                                    return
                            elif ch in {"\b", "\x7f"}:
                                self._input_buffer = self._input_buffer[:-1]
                                live.update(self.build_layout(), refresh=True)
                            elif ch in {"\x00", "\xe0"}:
                                if msvcrt.kbhit():
                                    msvcrt.getwch()
                            elif ch.isprintable():
                                self._input_buffer += ch
                                live.update(self.build_layout(), refresh=True)

                        now = time.monotonic()
                        if now - last_refresh >= self.refresh_seconds:
                            await self.refresh()
                            self.state.step_count += 1
                            last_refresh = now
                            live.update(self.build_layout(), refresh=True)
                        await asyncio.sleep(0.05)
                return
            except Exception:
                pass

        # POSIX / generic TTY fallback: render panel and read prompt cleanly
        while not self._step_limit_reached():
            try:
                prompt_reader = self._prompt_fn or (lambda prompt: self.console.input(prompt))
                line = prompt_reader("[bold cyan]hydra>[/bold cyan] ")
            except (EOFError, KeyboardInterrupt):
                break
            outcome = await self.execute_command(line.strip() or "refresh")
            self.state.step_count += 1
            self.render()
            if outcome.should_quit:
                break

    async def run_async(self) -> CockpitState:
        """Run initial refresh/render and execute either single-shot, scripted, or interactive loop."""
        try:
            with self._redaction_ctx():
                try:
                    await self.refresh()
                except Exception as exc:
                    code, msg = self._format_exception(exc)
                    self._set_error(code, msg)

                if self.once:
                    self.state.step_count += 1
                    self.render()
                    return self.state

                if self._is_interactive_tty():
                    await self._run_interactive_tty_loop()
                else:
                    self.render()
                    await self._run_scripted_loop()
                return self.state
        finally:
            await self.backend.aclose()

    def run(self) -> CockpitState:
        """Synchronous entry point running the cockpit loop."""
        return asyncio.run(self.run_async())


def load_script_commands(script_path: Path) -> List[str]:
    """Load non-empty, non-comment deterministic commands from a script file."""
    if not script_path.is_file():
        raise FileNotFoundError(f"Cockpit script file not found: {script_path}")
    lines = script_path.read_text(encoding="utf-8").splitlines()
    commands: List[str] = []
    for raw in lines[:_MAX_LINE_COMMANDS]:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return commands


def run_cockpit(
    *,
    run_service: Optional[RunService] = None,
    route_selector: Optional[RouteSelector] = None,
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    api_token_env: str = "HYDRA_API_TOKEN",
    http_transport: Optional[httpx.AsyncBaseTransport] = None,
    run_id: Optional[str] = None,
    principal_id: str = "operator",
    console: Optional[Console] = None,
    refresh_seconds: float = 2.0,
    no_alt_screen: bool = False,
    once: bool = False,
    script: Optional[Path] = None,
    input_stream: Optional[TextIO] = None,
    command_queue: Optional[Union[Sequence[str], Iterable[str], asyncio.Queue[str]]] = None,
    max_steps: Optional[int] = None,
) -> CockpitState:
    """Programmatic runner helper used by `hydra watch`, `hydra ui`, and automated tests."""
    commands = load_script_commands(script) if script is not None else command_queue
    cockpit = HydraTuiCockpit(
        run_service=run_service,
        route_selector=route_selector,
        api_url=api_url,
        api_token=api_token,
        api_token_env=api_token_env,
        http_transport=http_transport,
        run_id=run_id,
        principal_id=principal_id,
        console=console,
        refresh_seconds=refresh_seconds,
        no_alt_screen=no_alt_screen,
        once=once,
        input_stream=input_stream,
        command_queue=commands,
        max_steps=max_steps,
    )
    return cockpit.run()


__all__ = [
    "CockpitBackend",
    "CockpitCommandOutcome",
    "CockpitState",
    "HttpRunBackend",
    "HydraTuiCockpit",
    "LocalRunBackend",
    "compute_task_waves",
    "format_quota_entry",
    "load_script_commands",
    "parse_sse_events",
    "resolve_api_token",
    "run_cockpit",
    "sanitize_api_url",
]
