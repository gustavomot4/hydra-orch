"""CLI for hydra-orch: serve, run, status, quota, and control-plane commands (T01 / T07 / T23)."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import secrets
import shutil
from typing import Any, Awaitable, Callable, Dict, List, Optional
import uuid

from pydantic import BaseModel, ValidationError
import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from hydra_orch.config import ConfigError, load_config
from hydra_orch.core.checkpointer import (
    IdempotencyConflictError,
    OptimisticLockError,
    StorageError,
    StorageIntegrityError,
)
from hydra_orch.core.git_workspace import GitWorkspaceError
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text, redaction_scope
from hydra_orch.core.router import HydraRouter
from hydra_orch.core.run_service import RunService
from hydra_orch.model import (
    BudgetPolicy,
    ChatCompletionRequest,
    ChatMessage,
    CheckSpec,
    ContractViolation,
    IntegrationStatus,
    RunSpec,
    TaskSpec,
)
from hydra_orch.server import get_run_service

app = typer.Typer(
    name="hydra",
    help="hydra-orch: Universal Autonomous LLM Orchestrator CLI",
    add_completion=False,
)
console = Console()


def _to_jsonable(value: Any) -> Any:
    """Convert Pydantic models, dataclasses, Paths, Enums, and tuples into JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)


def _emit_output(
    data: Any,
    *,
    as_json: bool = False,
    output_file: Optional[Path] = None,
    summary_text: Optional[str] = None,
) -> None:
    safe_data = redact(_to_jsonable(data))
    serialized = json.dumps(safe_data, indent=2, sort_keys=True, default=str)
    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(serialized + "\n", encoding="utf-8")
    if as_json:
        typer.echo(serialized)
    elif summary_text:
        console.print(redact_text(summary_text), markup=False)
    else:
        typer.echo(serialized)


def _handle_cli_exception(exc: Exception, *, as_json: bool = False) -> None:
    conflict_codes = {
        "invalid_transition",
        "invalid_run_state",
        "invalid_task_state",
        "result_not_accepted",
        "result_not_ready_for_review",
        "simulated_result_not_integrable",
        "SimulatedResultNotIntegrable",
        "missing_check_results",
        "failed_check_blocks_acceptance",
        "active_attempt_exists",
        "revision_mismatch",
        "dirty_worktree_preserved",
        "artifact_tampered",
        "session_state_conflict",
        "thread_state_conflict",
        "hitl_pending",
        "hitl_busy",
        "hitl_conflict",
        "consent_required",
        "consent_conflict",
        "memory_conflict",
        "registry_conflict",
        "workspace_archived",
        "profile_snapshot_conflict",
        "profile_snapshot_late",
        "discovery_untrusted",
        "component_untrusted",
        "component_revoked",
        "manifest_conflict",
        "extension_manifest_conflict",
        "extension_revoked",
        "extension_quarantined",
        "extension_not_active",
        "extension_already_installed",
        "rollback_unavailable",
        "preference_snapshot_conflict",
        "preference_snapshot_late",
        "explicit_preference_precedence",
        "preference_revert_unavailable",
        "transport_uncertified",
        "transport_unhealthy",
        "transport_conflict",
        "conflict_already_resolved",
        "invalid_conflict_transition",
        "invalid_conflict_state",
        "conflict_not_applicable",
        "no_conflict_detected",
        "auto_repair_failed",
        "amendment_conflict",
        "budget_frozen",
        "budget_exhausted",
        "budget_conflict",
        "pr_package_exists",
        "packaging_branch_conflict",
        "publish_not_authorized",
        "packaging_conflict",
    }
    if isinstance(exc, (IdempotencyConflictError, OptimisticLockError)):
        code = "idempotency_conflict" if isinstance(exc, IdempotencyConflictError) else "optimistic_lock_conflict"
        exit_code = 3
        msg = str(exc)
    elif isinstance(exc, ContractViolation):
        code = exc.code
        exit_code = 3 if exc.code in conflict_codes or exc.code.endswith("_conflict") else 1
        msg = str(exc)
    elif isinstance(exc, GitWorkspaceError):
        code = exc.failure.code
        exit_code = 3 if code == "dirty_worktree_preserved" else 1
        msg = exc.failure.message
    elif isinstance(exc, StorageIntegrityError):
        code = "storage_integrity_error"
        exit_code = 1 if "not found" in str(exc).lower() or "does not exist" in str(exc).lower() else 3
        msg = str(exc)
    elif isinstance(exc, ConfigError):
        code = exc.code
        exit_code = 1
        msg = str(exc)
    elif isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError)):
        code = "validation_error"
        exit_code = 1
        msg = str(exc)
    elif isinstance(exc, FileNotFoundError):
        code = "not_found"
        exit_code = 1
        msg = str(exc)
    elif isinstance(exc, PermissionError):
        code = "permission_denied"
        exit_code = 1
        msg = str(exc)
    elif isinstance(exc, StorageError):
        code = "storage_error"
        exit_code = 2
        msg = str(exc)
    else:
        code = "system_error"
        exit_code = 2
        msg = str(exc)

    safe_msg = redact_text(msg)
    if as_json:
        typer.echo(
            json.dumps(
                {"code": code, "message": safe_msg, "exit_code": exit_code},
                sort_keys=True,
            )
        )
    else:
        console.print(f"{code}: {safe_msg}", markup=False)
    raise typer.Exit(code=exit_code) from exc


def _default_principal(principal_id: Optional[str]) -> str:
    return principal_id or os.environ.get("HYDRA_PRINCIPAL_ID") or "operator"


def _parse_csv(raw: Optional[str]) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _parse_json_obj(raw: Optional[str], *, flag_name: str) -> dict[str, Any]:
    if raw is None or not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{flag_name} must decode to a JSON object")
    return parsed


def _parse_json_list(raw: Optional[str], *, flag_name: str) -> list[Any]:
    if raw is None or not raw.strip():
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError(f"{flag_name} must decode to a JSON list")
    return parsed


def _parse_json_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _run_cli_action(
    action: Callable[[RunService], Awaitable[Any]],
    *,
    as_json: bool = False,
    output_file: Optional[Path] = None,
    render_summary: Optional[Callable[[Any], str]] = None,
) -> Any:
    svc = get_run_service()
    try:
        result = asyncio.run(action(svc))
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)
    summary = render_summary(result) if render_summary is not None else None
    _emit_output(result, as_json=as_json, output_file=output_file, summary_text=summary)
    return result


def _build_agent_registry(svc: RunService):
    from hydra_orch.core.agent_registry import AgentRegistry

    return AgentRegistry(svc.store, executable_locator=lambda name: shutil.which(name))


def _build_workspace_registry(svc: RunService):
    from hydra_orch.core.workspace_registry import WorkspaceRegistry

    return WorkspaceRegistry(svc.store, allowed_roots=[svc.repo_root])


def _build_discovery_service(svc: RunService, *, principal_id: str, enabled: bool = True):
    from hydra_orch.core.discovery import DiscoveryService

    return DiscoveryService(
        svc.store,
        allowed_roots=[svc.repo_root],
        enabled=enabled,
        principal_id=principal_id,
    )


def _build_skill_registry(svc: RunService, *, principal_id: str = "operator"):
    from hydra_orch.core.skill_registry import SkillRegistry

    discovery = _build_discovery_service(svc, principal_id=principal_id, enabled=True)
    return SkillRegistry(svc.store, discovery=discovery)


def _build_extension_host(svc: RunService):
    from hydra_orch.core.consent import ConsentService
    from hydra_orch.core.extension_host import ExtensionHost

    consents = ConsentService(svc.store, _build_workspace_registry(svc))
    return ExtensionHost(
        svc.store,
        consents,
        allowed_roots=[svc.repo_root],
        runtime_dir=svc.runtime_dir / "extensions",
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host address (loopback by default)"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the OpenAI-compatible proxy and Control Plane server (http://127.0.0.1:8000/v1)."""
    banner = (
        "[bold cyan]HYDRA ORCHESTRATOR[/bold cyan]\n"
        "[dim]Universal Autonomous LLM Orchestrator & Control Plane[/dim]\n\n"
        f"API Endpoint: [green]http://{host}:{port}/v1[/green]\n"
        f"Control Plane: [green]http://{host}:{port}/v1/control-plane[/green]"
    )
    console.print(Panel(banner, border_style="cyan"))

    import uvicorn

    uvicorn.run("hydra_orch.server:app", host=host, port=port, reload=reload)


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Prompt or task instruction to execute"),
    mode: Optional[str] = typer.Option(
        None, "--mode", "-m", help="Execution mode: swarm | relay | persistent"
    ),
    provider: Optional[str] = typer.Option(
        None, "--provider", "-P", help="Specific adapter to target (e.g. claude_pro, deepseek, ollama_local)"
    ),
) -> None:
    """Run an inference instruction directly through hydra-orch (Swarm, Relay, or Persistent)."""
    cfg = load_config()
    chosen_mode = mode or cfg.orchestrator.default_mode

    console.print(
        Panel(
            f"[bold green]Starting Task in Mode:[/bold green] [yellow]{chosen_mode.upper()}[/yellow]\n"
            f"[bold]Prompt:[/bold] {prompt}",
            border_style="green",
        )
    )

    router = HydraRouter(cfg)
    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content=prompt)],
        mode=chosen_mode,
        preferred_provider=provider,
        stream=True,
    )

    async def _execute() -> None:
        await router.checkpointer.initialize()
        accumulated = []
        with Live(console=console, refresh_per_second=8) as live:
            async for chunk in router.stream_chat_completion(request):
                accumulated.append(chunk)
                full_text = "".join(accumulated)
                live.update(Markdown(full_text))

    try:
        asyncio.run(_execute())
    except ConfigError as exc:
        console.print(f"{exc.code}: {exc}", markup=False)
        raise typer.Exit(code=1) from exc


@app.command()
def submit(
    objective: Optional[str] = typer.Option(None, "--objective", "-o", help="Run objective"),
    spec_file: Optional[Path] = typer.Option(None, "--spec-file", "-f", help="Path to RunSpec JSON file"),
    project_id: str = typer.Option("proj-default", "--project-id", help="Target project ID"),
    repo_root: Optional[Path] = typer.Option(None, "--repo-root", help="Git repository root"),
    base_branch: str = typer.Option("main", "--base-branch", help="Base branch name"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Pinned 40-char base commit SHA"),
    task_id: str = typer.Option("task-1", "--task-id", help="Task identifier"),
    executor: str = typer.Option("codex", "--executor", help="Assigned CLI executor driver"),
    check_cmd: Optional[List[str]] = typer.Option(
        None, "--check-cmd", help="Check command token(s) for acceptance_criteria"
    ),
    idempotency_key: Optional[str] = typer.Option(
        None, "--idempotency-key", "-k", help="Idempotency key for safe retries"
    ),
    execute: bool = typer.Option(False, "--execute", help="Execute the task attempt immediately"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Use fake_subprocess in dry-run mode"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Submit a canonical M1 run through RunService (and optionally execute it)."""
    async def _do_submit() -> Dict[str, Any]:
        svc: RunService = get_run_service()
        if spec_file is not None:
            raw_data = json.loads(spec_file.read_text(encoding="utf-8"))
            run_spec = RunSpec.model_validate(raw_data)
            req_hash = svc.store.compute_request_hash(run_spec)
        else:
            if not objective:
                raise ContractViolation("missing_objective", "Either --spec-file or --objective must be provided")
            resolved_repo = Path(repo_root) if repo_root is not None else svc.repo_root
            ws = svc._get_git_workspace(resolved_repo)
            resolved_sha = base_sha or ws.resolve_commit_sha("HEAD")
            cmd_tokens = tuple(check_cmd) if check_cmd else ("git", "status", "--short")
            idem = idempotency_key or f"cli-idem-{uuid.uuid4().hex[:16]}"
            gen_run_id = f"run-{uuid.uuid4().hex[:12]}"
            exec_id = "fake_subprocess" if dry_run else executor
            t_spec = TaskSpec(
                task_id=task_id,
                run_id=gen_run_id,
                objective=objective,
                allowed_paths=("*",),
                acceptance_criteria=(
                    CheckSpec(
                        check_id="chk-default",
                        command=cmd_tokens,
                    ),
                ),
                assigned_executor=exec_id,
            )
            semantic = {
                "project_id": project_id,
                "repo_root": str(ws.repo_root),
                "base_sha": resolved_sha,
                "objective": objective,
                "task_id": task_id,
                "command": list(cmd_tokens),
                "assigned_executor": exec_id,
            }
            req_hash = svc.store.compute_request_hash(semantic)
            run_spec = RunSpec(
                run_id=gen_run_id,
                project_id=project_id,
                repo_root=str(ws.repo_root),
                base_branch=base_branch,
                base_sha=resolved_sha,
                objective=objective,
                orchestration_mode="relay",
                tasks=(t_spec,),
                budget_policy=BudgetPolicy(),
                idempotency_key=idem,
            )

        created, run_rec = await svc.submit_run(run_spec, request_hash=req_hash)
        if created and execute:
            for t in run_spec.tasks:
                await svc.execute_task_attempt(
                    run_id=run_rec["id"],
                    task_id=t.task_id,
                    dry_run=dry_run,
                )
            refreshed = await svc.store.get_run(run_rec["id"])
            if refreshed is not None:
                run_rec = refreshed

        return {
            "run_id": run_rec["id"],
            "project_id": run_rec["project_id"],
            "status": run_rec["status"],
            "revision": int(run_rec["revision"]),
            "created": created,
            "base_sha": run_rec["base_sha"],
        }

    try:
        res = asyncio.run(_do_submit())
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=f"Run {res['run_id']} submitted (status={res['status']}, created={res['created']})",
        )
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


@app.command()
def inspect(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Inspect a persisted run, its tasks, attempts, and artifacts via RunService."""
    async def _do_inspect() -> Dict[str, Any]:
        svc = get_run_service()
        detail = await svc.get_run_detail(run_id)
        if detail is None:
            raise StorageIntegrityError(f"Run '{run_id}' not found")
        artifacts = await svc.store.get_artifacts(run_id)
        events = await svc.store.get_events(run_id)
        detail["artifacts"] = [a.model_dump(mode="json") for a in artifacts]
        detail["events_count"] = len(events)
        return detail

    try:
        res = asyncio.run(_do_inspect())
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=(
                f"Run {res['run_id']} | status={res['status']} | revision={res['revision']} | "
                f"tasks={len(res['tasks'])} | artifacts={len(res['artifacts'])}"
            ),
        )
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


@app.command()
def review(
    run_id: str = typer.Argument(..., help="Run ID"),
    task_id: str = typer.Argument(..., help="Task ID to review"),
    decision: str = typer.Option(..., "--decision", "-d", help="Review decision: accepted | rejected"),
    reason: str = typer.Option(..., "--reason", "-r", help="Review justification"),
    expected_revision: int = typer.Option(1, "--expected-revision", "-e", help="Expected result revision"),
    actor: str = typer.Option("operator", "--actor", help="Reviewer principal identifier"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Apply an explicit review decision (accepted/rejected) to a task result via RunService."""
    async def _do_review() -> Dict[str, Any]:
        svc = get_run_service()
        attempts = await svc.store.list_attempts(task_id)
        if not attempts:
            raise StorageIntegrityError(f"Task '{task_id}' has no attempts")
        latest_res = await svc.store.get_result_by_attempt(attempts[-1].attempt_id)
        if latest_res is None:
            raise StorageIntegrityError(f"Task '{task_id}' has no result to review")

        reviewed = await svc.review_task_result(
            run_id=run_id,
            result_id=latest_res.result_id,
            actor=actor,
            decision=decision,
            reason=reason,
            expected_revision=expected_revision,
        )
        return {
            "run_id": run_id,
            "task_id": task_id,
            "result_id": reviewed.result_id,
            "decision": decision,
            "task_status": reviewed.task_status.value,
            "revision": reviewed.revision,
        }

    try:
        res = asyncio.run(_do_review())
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=(
                f"Reviewed {res['result_id']}: decision={res['decision']} "
                f"task_status={res['task_status']} revision={res['revision']}"
            ),
        )
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


@app.command()
def integrate(
    run_id: str = typer.Argument(..., help="Run ID to integrate"),
    target_branch: Optional[str] = typer.Option(None, "--target-branch", help="Optional integration branch"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Integrate accepted task results for a run into integrate/<run_id> via RunService."""
    async def _do_integrate() -> Dict[str, Any]:
        svc = get_run_service()
        outcome = await svc.integrate_run(run_id=run_id, target_branch=target_branch)
        return {
            "integration_id": outcome.integration_id,
            "run_id": outcome.run_id,
            "status": outcome.status.value,
            "target_branch": outcome.target_branch,
            "result_sha": outcome.result_sha,
            "conflicted_files": list(outcome.conflicted_files),
        }

    try:
        res = asyncio.run(_do_integrate())
        if res["status"] in {IntegrationStatus.CONFLICTED.value, IntegrationStatus.FAILED.value}:
            if as_json:
                typer.echo(json.dumps(res, sort_keys=True))
            else:
                console.print(f"integration_{res['status']}: {res}", markup=False)
            raise typer.Exit(code=1)
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=(
                f"Integrated run {res['run_id']} into {res['target_branch']} "
                f"(sha={res['result_sha']}, status={res['status']})"
            ),
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


@app.command()
def cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel"),
    task_id: Optional[str] = typer.Option(None, "--task-id", "-t", help="Cancel only a specific task in the run"),
    reason: str = typer.Option("operator_cancelled", "--reason", "-r", help="Cancellation reason"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Cancel an active run or a specific task via RunService."""
    async def _do_cancel() -> Dict[str, Any]:
        svc = get_run_service()
        if task_id:
            updated_task = await svc.cancel_task(run_id=run_id, task_id=task_id, reason=reason)
            return {
                "scope": "task",
                "run_id": run_id,
                "task_id": task_id,
                "status": updated_task["status"],
            }
        updated_run = await svc.cancel_run(run_id=run_id, reason=reason)
        return {
            "scope": "run",
            "run_id": run_id,
            "status": updated_run["status"],
        }

    try:
        res = asyncio.run(_do_cancel())
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=f"Cancelled {res['scope']} {res.get('task_id') or res['run_id']} (status={res['status']})",
        )
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


@app.command()
def retry(
    run_id: str = typer.Argument(..., help="Run ID"),
    task_id: str = typer.Argument(..., help="Task ID to retry"),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="Optional updated prompt for the retry attempt"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Retry a failed, rejected, or blocked task in a new isolated worktree via RunService."""
    async def _do_retry() -> Dict[str, Any]:
        svc = get_run_service()
        outcome = await svc.retry_task(run_id=run_id, task_id=task_id, prompt=prompt)
        return {
            "run_id": run_id,
            "task_id": task_id,
            "attempt_id": outcome.attempt.attempt_id,
            "ordinal": outcome.attempt.ordinal,
            "result_id": outcome.result.result_id,
            "task_status": outcome.result.task_status.value,
        }

    try:
        res = asyncio.run(_do_retry())
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=(
                f"Retried task {res['task_id']} (attempt={res['attempt_id']}, "
                f"ordinal={res['ordinal']}, status={res['task_status']})"
            ),
        )
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


@app.command()
def status() -> None:
    """Display status of all configured adapters, ports, and resilience checkpoints."""
    cfg = load_config()
    router = HydraRouter(cfg)

    table = Table(title="Hydra Orchestrator - Adapter Statuses", border_style="cyan")
    table.add_column("Adapter Name", style="bold white")
    table.add_column("Type", style="cyan")
    table.add_column("Health / Status", style="green")
    table.add_column("Details", style="dim")

    async def _check() -> None:
        async def _probe(name: str, adapter: Any) -> tuple[str, str, str, str]:
            avail = await adapter.is_available()
            status_text = "[green]ONLINE[/green]" if avail else "[red]OFFLINE[/red]"
            details = adapter.last_error or "Ready"
            if hasattr(adapter, "cdp_port"):
                details = f"Port: {adapter.cdp_port} | {details}"
            elif hasattr(adapter, "base_url"):
                details = f"URL: {adapter.base_url} | {details}"
            return (name, adapter.__class__.__name__, status_text, details)

        results = await asyncio.gather(
            *[_probe(name, adapter) for name, adapter in router.adapters.items()]
        )
        for row in results:
            table.add_row(*row)

    asyncio.run(_check())
    console.print(table)


@app.command()
def quota() -> None:
    """Display real-time 5-hour subscription quota windows (Claude, ChatGPT, Gemini)."""
    from hydra_orch.bridge.omniroute_client import OmniRouteClient

    cfg = load_config()
    client = OmniRouteClient(
        base_url=cfg.omniroute.base_url,
        quota_api_url=cfg.omniroute.quota_api_url,
        enabled=not cfg.is_direct_mode,
    )

    table = Table(title="OmniRoute 5h Quota Tracker", border_style="green")
    table.add_column("Subscription / Model", style="bold white")
    table.add_column("Remaining Quota", style="cyan")
    table.add_column("Resets In", style="yellow")
    table.add_column("Status", style="green")

    async def _fetch() -> None:
        data = await client.get_quota_status()
        for k, v in data.items():
            if isinstance(v, dict):
                remaining = v.get("remaining_percent")
                reset = v.get("resets_in_seconds")
                rem = f"{remaining}%" if remaining is not None else "unknown"
                resets = f"{reset}s" if reset is not None else "unknown"
                status_str = v.get("status", "unknown").upper()
                table.add_row(k.replace("_", " ").title(), rem, resets, status_str)

    asyncio.run(_fetch())
    console.print(table)


# ---------------------------------------------------------------------------
# Missing M1 top-level control-plane commands
# ---------------------------------------------------------------------------


@app.command("project-create")
def project_create_cmd(
    canonical_root: Path = typer.Option(..., "--root", help="Canonical project repository root"),
    name: str = typer.Option(..., "--name", help="Project name"),
    base_branch: str = typer.Option("main", "--base-branch", help="Default base branch"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Pinned base commit SHA"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Optional explicit project ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register an M1 project directly against RunService."""
    _run_cli_action(
        lambda svc: svc.create_project(
            str(canonical_root),
            name,
            base_branch=base_branch,
            base_sha=base_sha,
            project_id=project_id,
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"project={res.get('id')} name={res.get('name')} branch={res.get('base_branch')}",
    )


@app.command("project-list")
def project_list_cmd(
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List M1 registered projects."""
    _run_cli_action(
        lambda svc: svc.list_projects(),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"projects={len(res)}",
    )


@app.command("runs")
def runs_cmd(
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Filter by project ID"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by run status"),
    page: int = typer.Option(1, "--page", help="Page number (1-indexed)"),
    size: int = typer.Option(20, "--size", help="Page size"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List orchestration runs."""
    _run_cli_action(
        lambda svc: svc.list_runs(project_id=project_id, status=status, page=page, size=size),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"runs={len(res.get('items', []))} total={res.get('total', 0)}",
    )


# ---------------------------------------------------------------------------
# Extended Control Plane subcommand groups (T23)
# ---------------------------------------------------------------------------

area_app = typer.Typer(help="Manage organizational areas.")
workspace_app = typer.Typer(help="Manage workspaces within an area.")
project_app = typer.Typer(help="Manage workspace-scoped projects and legacy adoption.")
repo_app = typer.Typer(help="Manage project repositories and principal grants.")
agent_app = typer.Typer(help="Manage agent definitions, certifications, and capabilities.")
profile_app = typer.Typer(help="Manage execution profiles and run snapshots.")
session_app = typer.Typer(help="Manage execution sessions and threads.")
metrics_app = typer.Typer(help="Query run/session telemetry and aggregated usage.")
consent_app = typer.Typer(help="Request, decide, list, and revoke explicit consents.")
memory_app = typer.Typer(help="Write, query, and revoke consent-gated scoped memories.")
discovery_app = typer.Typer(help="Scan, list, approve, and reject discovered resources.")

app.add_typer(area_app, name="area")
app.add_typer(workspace_app, name="workspace")
app.add_typer(project_app, name="project")
app.add_typer(repo_app, name="repo")
app.add_typer(agent_app, name="agent")
app.add_typer(profile_app, name="profile")
app.add_typer(session_app, name="session")
app.add_typer(metrics_app, name="metrics")
app.add_typer(consent_app, name="consent")
app.add_typer(memory_app, name="memory")
app.add_typer(discovery_app, name="discovery")


@area_app.command("create")
def area_create(
    name: str = typer.Option(..., "--name", help="Area name"),
    description: Optional[str] = typer.Option(None, "--description", help="Optional description"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create an organizational area."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).create_area(name, principal_id=actor, description=description),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"area={res.get('area_id')} name={res.get('name')}",
    )


@area_app.command("list")
def area_list(
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List areas visible to the acting principal."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).list_areas(principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"areas={len(res)}",
    )


@workspace_app.command("create")
def workspace_create(
    area_id: str = typer.Option(..., "--area-id", help="Parent area ID"),
    name: str = typer.Option(..., "--name", help="Workspace name"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create a workspace inside an area."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).create_workspace(area_id, name, principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"workspace={res.get('workspace_id')} area={res.get('area_id')}",
    )


@workspace_app.command("list")
def workspace_list(
    area_id: str = typer.Option(..., "--area-id", help="Parent area ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List workspaces for an area."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).list_workspaces(area_id, principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"workspaces={len(res)}",
    )


@workspace_app.command("archive")
def workspace_archive(
    workspace_id: str = typer.Argument(..., help="Workspace ID to archive"),
    expected_revision: int = typer.Option(..., "--expected-revision", help="Expected optimistic revision"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Archive a workspace using optimistic revision check."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        await _build_workspace_registry(svc).archive_workspace(
            workspace_id,
            principal_id=actor,
            expected_revision=expected_revision,
        )
        return {"workspace_id": workspace_id, "archived": True, "expected_revision": expected_revision}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"workspace={res['workspace_id']} archived=True",
    )


@project_app.command("create")
def project_create_scoped(
    workspace_id: str = typer.Option(..., "--workspace-id", help="Target workspace ID"),
    name: str = typer.Option(..., "--name", help="Project name"),
    root: Path = typer.Option(..., "--root", help="Canonical project root path"),
    base_branch: str = typer.Option("main", "--base-branch", help="Default base branch"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Pinned base commit SHA"),
    metadata_json: Optional[str] = typer.Option(None, "--metadata-json", help="Optional metadata JSON object"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create a workspace-scoped project."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        metadata = _parse_json_obj(metadata_json, flag_name="--metadata-json")
        return await _build_workspace_registry(svc).create_project(
            workspace_id,
            name,
            root,
            principal_id=actor,
            base_branch=base_branch,
            base_sha=base_sha,
            metadata=metadata or None,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"project={res.get('project_id')} workspace={res.get('workspace_id')}",
    )


@project_app.command("list")
def project_list_scoped(
    workspace_id: str = typer.Option(..., "--workspace-id", help="Workspace ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List projects in a workspace."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).list_projects(workspace_id, principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"projects={len(res)}",
    )


@project_app.command("adopt")
def project_adopt(
    project_id: str = typer.Argument(..., help="Legacy project ID to adopt"),
    workspace_id: str = typer.Option(..., "--workspace-id", help="Destination workspace ID"),
    expected_revision: int = typer.Option(..., "--expected-revision", help="Expected project revision"),
    base_branch: str = typer.Option("main", "--base-branch", help="Base branch"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Adopt a legacy project into a workspace."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).adopt_legacy_project(
            project_id,
            workspace_id,
            principal_id=actor,
            expected_revision=expected_revision,
            base_branch=base_branch,
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"project={res.get('project_id')} workspace={res.get('workspace_id')}",
    )


@repo_app.command("register")
def repo_register(
    project_id: str = typer.Option(..., "--project-id", help="Parent project ID"),
    root: Path = typer.Option(..., "--root", help="Canonical repository root"),
    authorized_principal: Optional[str] = typer.Option(None, "--authorized-principal", help="Authorized principal ID"),
    scopes: str = typer.Option("read,write", "--scopes", help="Comma-separated authorization scopes"),
    allowed_paths: Optional[str] = typer.Option(None, "--allowed-paths", help="Comma-separated allowed relative paths"),
    base_branch: str = typer.Option("main", "--base-branch", help="Repository base branch"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Pinned base commit SHA"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register a canonical repository under a project."""
    actor = _default_principal(principal_id)
    grantee = authorized_principal or actor
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).register_repository(
            project_id,
            root,
            principal_id=actor,
            authorized_principal_id=grantee,
            scopes=list(_parse_csv(scopes)),
            allowed_paths=list(_parse_csv(allowed_paths)),
            base_branch=base_branch,
            base_sha=base_sha,
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"repository={res.get('repository_id')} project={res.get('project_id')}",
    )


@repo_app.command("list")
def repo_list(
    project_id: str = typer.Option(..., "--project-id", help="Parent project ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List repositories registered for a project."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_workspace_registry(svc).list_repositories(project_id, principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"repositories={len(res)}",
    )


@repo_app.command("grant")
def repo_grant(
    repository_id: str = typer.Argument(..., help="Repository ID"),
    authorized_principal: str = typer.Option(..., "--authorized-principal", help="Principal to grant access to"),
    scopes: str = typer.Option("read", "--scopes", help="Comma-separated authorization scopes"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Grant principal authorization on a repository."""
    actor = _default_principal(principal_id)
    scope_list = list(_parse_csv(scopes))

    async def _action(svc: RunService) -> dict[str, Any]:
        auth_id = await _build_workspace_registry(svc).grant_repository(
            repository_id,
            principal_id=actor,
            authorized_principal_id=authorized_principal,
            scopes=scope_list,
        )
        return {
            "authorization_id": auth_id,
            "repository_id": repository_id,
            "authorized_principal_id": authorized_principal,
            "scopes": scope_list,
        }

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"authorization={res['authorization_id']} repo={repository_id}",
    )


@repo_app.command("revoke")
def repo_revoke(
    authorization_id: str = typer.Argument(..., help="Authorization ID to revoke"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke a repository authorization."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        await _build_workspace_registry(svc).revoke_authorization(authorization_id, principal_id=actor)
        return {"authorization_id": authorization_id, "revoked": True}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"authorization={res['authorization_id']} revoked=True",
    )


@agent_app.command("register")
def agent_register(
    name: str = typer.Option(..., "--name", help="Agent name"),
    version: str = typer.Option("1.0.0", "--version", help="Agent version"),
    driver_type: str = typer.Option("claude_code", "--driver-type", help="Driver type"),
    capabilities: Optional[str] = typer.Option(None, "--capabilities", help="Comma-separated ExecutorCapability values"),
    limitations: Optional[str] = typer.Option(None, "--limitations", help="Comma-separated limitation strings"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", help="Optional explicit agent ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register an agent definition."""

    async def _action(svc: RunService):
        from hydra_orch.core.agent_registry import AgentDefinition
        from hydra_orch.model import ExecutorCapability

        caps = tuple(ExecutorCapability(c) for c in _parse_csv(capabilities))
        definition = AgentDefinition(
            agent_id=agent_id or new_id(),
            name=name,
            version=version,
            driver_type=driver_type,
            declared_capabilities=caps,
            limitations=_parse_csv(limitations),
        )
        return await _build_agent_registry(svc).register_agent(definition)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"agent={res.agent_id} driver={res.driver_type}",
    )


@agent_app.command("list")
def agent_list(
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List registered agents."""

    _run_cli_action(
        lambda svc: _build_agent_registry(svc).list_agents(),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"agents={len(res)}",
    )


@agent_app.command("certify")
def agent_certify(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    report: Path = typer.Option(..., "--report", help="Path to certification JSON report"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Import an attestation certification report for an agent."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        cert_id = await _build_agent_registry(svc).import_certificate(agent_id, report, principal_id=actor)
        return {"certificate_id": cert_id, "agent_id": agent_id}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"certificate={res['certificate_id']} agent={agent_id}",
    )


@agent_app.command("revoke-cert")
def agent_revoke_cert(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    platform: str = typer.Option(..., "--platform", help="Certified platform name to revoke"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke an agent certification for a platform."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        await _build_agent_registry(svc).revoke_certification(agent_id, platform, principal_id=actor)
        return {"agent_id": agent_id, "platform": platform, "revoked": True}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"agent={agent_id} platform={platform} revoked=True",
    )


@agent_app.command("resolve")
def agent_resolve(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    required: Optional[str] = typer.Option(None, "--required", help="Comma-separated required ExecutorCapability values"),
    platform: Optional[str] = typer.Option(None, "--platform", help="Target OS platform name"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Resolve certified agent capabilities for execution."""

    async def _action(svc: RunService):
        from hydra_orch.model import ExecutorCapability

        req_caps = tuple(ExecutorCapability(c) for c in _parse_csv(required))
        return await _build_agent_registry(svc).resolve_capabilities(
            agent_id,
            required=req_caps,
            platform_name=platform,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"agent={res.definition.agent_id} executable={res.executable} platform={res.platform}",
    )


@profile_app.command("create")
def profile_create(
    name: str = typer.Option(..., "--name", help="Profile name"),
    agent_ref: str = typer.Option(..., "--agent-ref", help="Registered agent ID"),
    executor_ref: str = typer.Option(..., "--executor-ref", help="Executor reference"),
    model_ref: str = typer.Option(..., "--model-ref", help="Model reference"),
    skills: Optional[str] = typer.Option(None, "--skills", help="Comma-separated skill IDs"),
    mcps: Optional[str] = typer.Option(None, "--mcps", help="Comma-separated MCP IDs"),
    required_capabilities: Optional[str] = typer.Option(None, "--required-capabilities", help="Comma-separated capabilities"),
    orchestration_mode: str = typer.Option("relay", "--orchestration-mode", help="Orchestration mode"),
    memory_policy_json: Optional[str] = typer.Option(None, "--memory-policy-json", help="MemoryPolicy JSON object"),
    resource_limits_json: Optional[str] = typer.Option(None, "--resource-limits-json", help="BudgetPolicy JSON object"),
    revision: int = typer.Option(1, "--revision", help="Profile revision"),
    profile_id: Optional[str] = typer.Option(None, "--profile-id", help="Optional explicit profile ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create an execution profile."""

    async def _action(svc: RunService):
        from hydra_orch.core.agent_registry import AgentRegistry
        from hydra_orch.core.profile_service import MemoryPolicy, ProfileDefinition, ProfileService
        from hydra_orch.model import ExecutorCapability

        mem_data = _parse_json_obj(memory_policy_json, flag_name="--memory-policy-json")
        lim_data = _parse_json_obj(resource_limits_json, flag_name="--resource-limits-json")
        req_caps = tuple(ExecutorCapability(c) for c in _parse_csv(required_capabilities))
        definition = ProfileDefinition(
            profile_id=profile_id or new_id(),
            name=name,
            agent_ref=agent_ref,
            executor_ref=executor_ref,
            model_ref=model_ref,
            skills_refs=_parse_csv(skills),
            mcp_refs=_parse_csv(mcps),
            memory_policy=MemoryPolicy(**mem_data) if mem_data else MemoryPolicy(),
            resource_limits=BudgetPolicy(**lim_data) if lim_data else BudgetPolicy(),
            required_capabilities=req_caps,
            orchestration_mode=orchestration_mode,
            revision=revision,
        )
        service = ProfileService(
            svc.store,
            _build_agent_registry(svc),
            _build_workspace_registry(svc),
            discovery=_build_discovery_service(svc, principal_id="operator"),
        )
        return await service.create_profile(definition)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"profile={res.profile_id} name={res.name}",
    )


@profile_app.command("get")
def profile_get(
    profile_id: str = typer.Argument(..., help="Profile ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Fetch a registered profile."""

    async def _action(svc: RunService):
        from hydra_orch.core.profile_service import ProfileService

        service = ProfileService(svc.store, _build_agent_registry(svc), _build_workspace_registry(svc))
        return await service.get_profile(profile_id)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"profile={res.profile_id} agent={res.agent_ref} rev={res.revision}",
    )


@profile_app.command("resolve")
def profile_resolve(
    profile_id: str = typer.Argument(..., help="Profile ID"),
    repository_id: str = typer.Option(..., "--repository-id", help="Authorized repository ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Resolve an effective profile against repository, discovery, and agent policy."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.profile_service import ProfileService

        service = ProfileService(
            svc.store,
            _build_agent_registry(svc),
            _build_workspace_registry(svc),
            discovery=_build_discovery_service(svc, principal_id=actor),
        )
        return await service.resolve_effective(profile_id, repository_id, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"profile={profile_id} repo={repository_id} resolved=True",
    )


@profile_app.command("snapshot")
def profile_snapshot(
    profile_id: str = typer.Argument(..., help="Profile ID"),
    run_id: str = typer.Option(..., "--run-id", help="Target run ID"),
    repository_id: str = typer.Option(..., "--repository-id", help="Repository ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Freeze a profile snapshot for a run."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.profile_service import ProfileService

        service = ProfileService(
            svc.store,
            _build_agent_registry(svc),
            _build_workspace_registry(svc),
            discovery=_build_discovery_service(svc, principal_id=actor),
        )
        return await service.snapshot(profile_id, run_id, repository_id, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"snapshot_run={run_id} profile={profile_id}",
    )


@session_app.command("create")
def session_create(
    run_id: str = typer.Argument(..., help="Run ID"),
    origin_ref: Optional[str] = typer.Option(None, "--origin-ref", help="Origin reference"),
    agent_ref: Optional[str] = typer.Option(None, "--agent-ref", help="Agent reference"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create a session for a run."""

    async def _action(svc: RunService):
        from hydra_orch.core.session_service import SessionService

        return await SessionService(svc.store).create_session(run_id, origin_ref=origin_ref, agent_ref=agent_ref)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"session={res.get('id')} state={res.get('state')}",
    )


@session_app.command("list")
def session_list(
    run_id: str = typer.Argument(..., help="Run ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List sessions for a run."""

    async def _action(svc: RunService):
        from hydra_orch.core.session_service import SessionService

        return await SessionService(svc.store).list_sessions(run_id)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"sessions={len(res)}",
    )


@session_app.command("threads")
def session_threads(
    run_id: str = typer.Argument(..., help="Run ID"),
    session_id: str = typer.Argument(..., help="Session ID"),
    create: bool = typer.Option(False, "--create", help="Create a thread instead of listing"),
    parent_thread_id: Optional[str] = typer.Option(None, "--parent-thread-id", help="Parent thread ID when creating"),
    agent_ref: Optional[str] = typer.Option(None, "--agent-ref", help="Agent reference when creating"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List threads in a session (or create one with --create)."""

    async def _action(svc: RunService):
        from hydra_orch.core.session_service import SessionService

        service = SessionService(svc.store)
        if create:
            return await service.create_thread(
                run_id,
                session_id,
                parent_thread_id=parent_thread_id,
                agent_ref=agent_ref,
            )
        return await service.list_threads(run_id, session_id)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: (
            f"thread={res.get('id')} state={res.get('state')}" if isinstance(res, dict) else f"threads={len(res)}"
        ),
    )


@session_app.command("transition")
def session_transition(
    run_id: str = typer.Argument(..., help="Run ID"),
    session_id: str = typer.Argument(..., help="Session ID"),
    target: str = typer.Option(..., "--target", help="Target SessionState"),
    expected_state: str = typer.Option(..., "--expected-state", help="Expected current SessionState"),
    thread_id: Optional[str] = typer.Option(None, "--thread-id", help="Transition this thread instead of session"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Transition a session or thread state with optimistic state guard."""

    async def _action(svc: RunService):
        from hydra_orch.core.session_service import SessionService

        service = SessionService(svc.store)
        if thread_id:
            return await service.transition_thread(
                run_id,
                session_id,
                thread_id,
                target,  # type: ignore[arg-type]
                expected_state=expected_state,  # type: ignore[arg-type]
            )
        return await service.transition_session(
            run_id,
            session_id,
            target,  # type: ignore[arg-type]
            expected_state=expected_state,  # type: ignore[arg-type]
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"id={res.get('id')} state={res.get('state')}",
    )


@metrics_app.command("query")
def metrics_query(
    run_id: str = typer.Argument(..., help="Run ID"),
    scope: str = typer.Option("run", "--scope", help="Metric scope: run|attempt|session|thread"),
    scope_id: Optional[str] = typer.Option(None, "--scope-id", help="Scope ID (defaults to run_id when scope=run)"),
    max_age_seconds: int = typer.Option(300, "--max-age-seconds", help="Freshness window in seconds"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Query fresh metric samples for a run/attempt/session/thread."""

    async def _action(svc: RunService):
        from hydra_orch.core.metrics import MetricsService

        resolved_scope_id = scope_id or run_id
        return await MetricsService(svc.store).query(
            run_id,
            scope,  # type: ignore[arg-type]
            resolved_scope_id,
            max_age_seconds=max_age_seconds,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"samples={len(res)}",
    )


@metrics_app.command("usage")
def metrics_usage(
    run_id: str = typer.Argument(..., help="Run ID"),
    max_age_seconds: int = typer.Option(300, "--max-age-seconds", help="Freshness window in seconds"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Aggregate usage metrics across scopes for a run."""

    async def _action(svc: RunService):
        from hydra_orch.core.metrics import MetricsService

        return await MetricsService(svc.store).aggregate_usage(run_id, max_age_seconds=max_age_seconds)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"aggregates={len(res)}",
    )


@consent_app.command("request")
def consent_request(
    scope_type: str = typer.Option(..., "--scope-type", help="principal|area|workspace|project|extension"),
    scope_id: str = typer.Option(..., "--scope-id", help="Scope identifier"),
    purpose: str = typer.Option("memory", "--purpose", help="Consent purpose: memory|extension"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Request explicit consent for a scope and purpose."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService, MemoryScope

        service = ConsentService(svc.store, _build_workspace_registry(svc))
        return await service.request(
            MemoryScope(scope_type=scope_type, scope_id=scope_id),  # type: ignore[arg-type]
            principal_id=actor,
            purpose=purpose,  # type: ignore[arg-type]
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"consent={res.consent_id} status={res.status}",
    )


@consent_app.command("list")
def consent_list(
    scope_type: str = typer.Option(..., "--scope-type", help="principal|area|workspace|project|extension"),
    scope_id: str = typer.Option(..., "--scope-id", help="Scope identifier"),
    purpose: str = typer.Option("memory", "--purpose", help="Consent purpose: memory|extension"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List consents for a scope and purpose."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService, MemoryScope

        service = ConsentService(svc.store, _build_workspace_registry(svc))
        return await service.list(
            MemoryScope(scope_type=scope_type, scope_id=scope_id),  # type: ignore[arg-type]
            principal_id=actor,
            purpose=purpose,  # type: ignore[arg-type]
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"consents={len(res)}",
    )


@consent_app.command("decide")
def consent_decide(
    consent_id: str = typer.Argument(..., help="Consent ID"),
    action: str = typer.Option(..., "--action", help="granted|denied|revoked|expired"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Record a decision on a consent request."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService

        service = ConsentService(svc.store, _build_workspace_registry(svc))
        return await service.decide(consent_id, action, principal_id=actor)  # type: ignore[arg-type]

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"consent={res.consent_id} status={res.status}",
    )


@consent_app.command("revoke")
def consent_revoke(
    consent_id: str = typer.Argument(..., help="Consent ID to revoke"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke an existing consent."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService

        service = ConsentService(svc.store, _build_workspace_registry(svc))
        return await service.decide(consent_id, "revoked", principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"consent={res.consent_id} status={res.status}",
    )


@memory_app.command("write")
def memory_write(
    scope_type: str = typer.Option(..., "--scope-type", help="principal|area|workspace|project|extension"),
    scope_id: str = typer.Option(..., "--scope-id", help="Scope identifier"),
    content: str = typer.Option(..., "--content", help="Memory content (will be redacted on write)"),
    consent_id: Optional[str] = typer.Option(None, "--consent-id", help="Granted consent ID"),
    retention: str = typer.Option("day", "--retention", help="Retention policy: day|month"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Write a consent-gated memory entry."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService
        from hydra_orch.core.memory_store import MemoryStore, MemoryWrite

        store = MemoryStore(ConsentService(svc.store, _build_workspace_registry(svc)))
        payload = MemoryWrite(
            scope_type=scope_type,  # type: ignore[arg-type]
            scope_id=scope_id,
            content=content,
            consent_id=consent_id,
            retention_policy=retention,  # type: ignore[arg-type]
        )
        return await store.write(payload, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"memory={res.memory_id} status={res.status}",
    )


@memory_app.command("query")
def memory_query(
    scope_type: str = typer.Option(..., "--scope-type", help="principal|area|workspace|project|extension"),
    scope_id: str = typer.Option(..., "--scope-id", help="Scope identifier"),
    query: str = typer.Option("", "--query", help="Substring search query"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Query active memory entries within a scope."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService, MemoryScope
        from hydra_orch.core.memory_store import MemoryStore

        store = MemoryStore(ConsentService(svc.store, _build_workspace_registry(svc)))
        return await store.query(
            MemoryScope(scope_type=scope_type, scope_id=scope_id),  # type: ignore[arg-type]
            principal_id=actor,
            query=query,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"entries={len(res)}",
    )


@memory_app.command("revoke")
def memory_revoke(
    memory_id: str = typer.Argument(..., help="Memory entry ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke a memory entry."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.consent import ConsentService
        from hydra_orch.core.memory_store import MemoryStore

        store = MemoryStore(ConsentService(svc.store, _build_workspace_registry(svc)))
        return await store.revoke(memory_id, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"memory={res.memory_id} status={res.status}",
    )


@discovery_app.command("scan")
def discovery_scan(
    root: Path = typer.Option(..., "--root", help="Authorized root path to scan"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable discovery opt-in flag"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Scan an authorized root for untrusted local resources."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_discovery_service(svc, principal_id=actor, enabled=enabled).scan(
            root, principal_id=actor
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"discovered={len(res)}",
    )


@discovery_app.command("list")
def discovery_list(
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List discovered resources visible to the principal."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_discovery_service(svc, principal_id=actor).list(principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"discovered={len(res)}",
    )


@discovery_app.command("approve")
def discovery_approve(
    resource_id: str = typer.Argument(..., help="Discovered resource ID"),
    expected_hash: str = typer.Option(..., "--expected-hash", help="Expected SHA-256 content hash"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Approve a discovered resource after explicit hash verification."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_discovery_service(svc, principal_id=actor).approve(
            resource_id, expected_hash, principal_id=actor
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"resource={res.discovery_id} status={res.trust_status}",
    )


@discovery_app.command("reject")
def discovery_reject(
    resource_id: str = typer.Argument(..., help="Discovered resource ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Reject a discovered resource."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_discovery_service(svc, principal_id=actor).decide(
            resource_id, "rejected", principal_id=actor
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"resource={res.discovery_id} status={res.trust_status}",
    )


skill_app = typer.Typer(help="Register, inspect, and revoke approved skills.")
mcp_app = typer.Typer(help="Register, inspect, and revoke MCP servers.")
secret_app = typer.Typer(help="Register, inspect, and revoke secret references (no plaintext secrets).")
extension_app = typer.Typer(help="Manage extension manifests, installs, lifecycle, and rollback.")
preference_app = typer.Typer(help="Manage layered preferences, precedence resolution, revert, and snapshots.")
transport_app = typer.Typer(help="Register, certify, list, and check health of execution transports.")
token_app = typer.Typer(help="Create hashed access tokens and revoke tokens.")
conflict_app = typer.Typer(help="Analyze, auto-repair, manually resolve, or discard integration conflicts.")
budget_app = typer.Typer(help="Inspect and extend run execution budgets.")
pr_package_app = typer.Typer(help="Build and publish run PR packages.")

app.add_typer(skill_app, name="skill")
app.add_typer(mcp_app, name="mcp")
app.add_typer(secret_app, name="secret")
app.add_typer(extension_app, name="extension")
app.add_typer(preference_app, name="preference")
app.add_typer(transport_app, name="transport")
app.add_typer(token_app, name="token")
app.add_typer(conflict_app, name="conflict")
app.add_typer(budget_app, name="budget")
app.add_typer(pr_package_app, name="pr-package")


@skill_app.command("register")
def skill_register(
    name: str = typer.Option(..., "--name", help="Skill name"),
    version: str = typer.Option("1.0.0", "--version", help="Skill version"),
    manifest_ref: str = typer.Option(..., "--manifest-ref", help="Canonical manifest reference"),
    checksum: str = typer.Option(..., "--checksum", help="64-hex SHA-256 checksum"),
    discovered_resource_id: Optional[str] = typer.Option(
        None, "--discovered-resource-id", help="Approved discovery resource ID"
    ),
    permissions: Optional[str] = typer.Option(None, "--permissions", help="Comma-separated declared permissions"),
    skill_id: Optional[str] = typer.Option(None, "--skill-id", help="Optional explicit skill ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register a validated skill definition."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.skill_registry import SkillDefinition

        skill = SkillDefinition(
            skill_id=skill_id or new_id(),
            name=name,
            version=version,
            manifest_ref=manifest_ref,
            discovered_resource_id=discovered_resource_id,
            permissions_declared=_parse_csv(permissions),
            checksum=checksum,
        )
        return await _build_skill_registry(svc, principal_id=actor).register_skill(skill, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"skill={res.skill_id} name={res.name}",
    )


@skill_app.command("get")
def skill_get(
    skill_id: str = typer.Argument(..., help="Skill ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Fetch a registered skill definition."""
    _run_cli_action(
        lambda svc: _build_skill_registry(svc).get_skill(skill_id),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"skill={res.skill_id} name={res.name} version={res.version}",
    )


@skill_app.command("revoke")
def skill_revoke(
    skill_id: str = typer.Argument(..., help="Skill ID to revoke"),
    reason: str = typer.Option("operator_revoked", "--reason", help="Revocation reason"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke a registered skill."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        await _build_skill_registry(svc, principal_id=actor).revoke_skill(
            skill_id, principal_id=actor, reason=reason
        )
        return {"skill_id": skill_id, "revoked": True, "reason": reason}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"skill={skill_id} revoked=True",
    )


@mcp_app.command("register")
def mcp_register(
    server_name: str = typer.Option(..., "--server-name", help="MCP server name"),
    transport_type: str = typer.Option("stdio", "--transport-type", help="stdio|sse|websocket"),
    endpoint: str = typer.Option(..., "--endpoint", help="MCP command or endpoint"),
    discovered_resource_id: Optional[str] = typer.Option(
        None, "--discovered-resource-id", help="Approved discovery resource ID"
    ),
    secret_ref: Optional[str] = typer.Option(None, "--secret-ref", help="Secret reference ID"),
    tools_json: Optional[str] = typer.Option(None, "--tools-json", help="JSON list of DeclaredTool objects"),
    permissions: Optional[str] = typer.Option(None, "--permissions", help="Comma-separated permissions"),
    mcp_id: Optional[str] = typer.Option(None, "--mcp-id", help="Optional explicit MCP ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register an MCP server definition."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.skill_registry import DeclaredTool, McpDefinition

        tools = tuple(DeclaredTool(**item) for item in _parse_json_list(tools_json, flag_name="--tools-json"))
        mcp = McpDefinition(
            mcp_id=mcp_id or new_id(),
            server_name=server_name,
            transport_type=transport_type,  # type: ignore[arg-type]
            endpoint=endpoint,
            discovered_resource_id=discovered_resource_id,
            secret_ref=secret_ref,
            declared_tools=tools,
            permissions=_parse_csv(permissions),
        )
        return await _build_skill_registry(svc, principal_id=actor).register_mcp(mcp, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"mcp={res.mcp_id} server={res.server_name}",
    )


@mcp_app.command("get")
def mcp_get(
    mcp_id: str = typer.Argument(..., help="MCP ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Fetch a registered MCP server definition."""
    _run_cli_action(
        lambda svc: _build_skill_registry(svc).get_mcp(mcp_id),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"mcp={res.mcp_id} server={res.server_name}",
    )


@mcp_app.command("revoke")
def mcp_revoke(
    mcp_id: str = typer.Argument(..., help="MCP ID to revoke"),
    reason: str = typer.Option("operator_revoked", "--reason", help="Revocation reason"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke a registered MCP server."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        await _build_skill_registry(svc, principal_id=actor).revoke_mcp(mcp_id, principal_id=actor, reason=reason)
        return {"mcp_id": mcp_id, "revoked": True, "reason": reason}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"mcp={mcp_id} revoked=True",
    )


@secret_app.command("register")
def secret_register(
    name: str = typer.Option(..., "--name", help="Secret reference name"),
    provider: str = typer.Option("env", "--provider", help="Provider type: env|vault|keyring"),
    source_key: str = typer.Option(..., "--source-key", help="External reference key (never a literal secret)"),
    secret_id: Optional[str] = typer.Option(None, "--secret-id", help="Optional explicit secret ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register a secret reference (refuses literal secrets; never prints resolved values)."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        return await _build_skill_registry(svc, principal_id=actor).create_secret_ref(
            secret_name=name,
            provider_type=provider,  # type: ignore[arg-type]
            source_key=source_key,
            principal_id=actor,
            secret_id=secret_id,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"secret={res.secret_id} name={res.secret_name} provider={res.provider_type}",
    )


@secret_app.command("get")
def secret_get(
    secret_id: str = typer.Argument(..., help="Secret reference ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Fetch secret reference metadata (never resolves or prints secret values)."""
    _run_cli_action(
        lambda svc: _build_skill_registry(svc).get_secret_ref(secret_id),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"secret={res.secret_id} name={res.secret_name} provider={res.provider_type}",
    )


@secret_app.command("revoke")
def secret_revoke(
    secret_id: str = typer.Argument(..., help="Secret reference ID to revoke"),
    reason: str = typer.Option("operator_revoked", "--reason", help="Revocation reason"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke a secret reference."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        await _build_skill_registry(svc, principal_id=actor).revoke_secret_ref(
            secret_id, principal_id=actor, reason=reason
        )
        return {"secret_id": secret_id, "revoked": True, "reason": reason}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"secret={secret_id} revoked=True",
    )


@extension_app.command("register")
def extension_register(
    name: str = typer.Option(..., "--name", help="Extension name"),
    version: str = typer.Option("1.0.0", "--version", help="Extension version"),
    entrypoint: str = typer.Option(..., "--entrypoint", help="Path or entrypoint inside allowed root"),
    checksum: str = typer.Option(..., "--checksum", help="64-hex SHA-256 checksum"),
    permissions: Optional[str] = typer.Option(None, "--permissions", help="Comma-separated permissions required"),
    api_version: str = typer.Option("1.0", "--api-version", help="Compatible extension host API version"),
    extension_id: Optional[str] = typer.Option(None, "--extension-id", help="Optional explicit extension ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register an extension manifest."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.extension_host import ExtensionManifest

        manifest = ExtensionManifest(
            extension_id=extension_id or new_id(),
            name=name,
            version=version,
            entrypoint=entrypoint,
            permissions_required=_parse_csv(permissions),
            compatible_api_version=api_version,
            checksum=checksum,
        )
        return await _build_extension_host(svc).register_manifest(manifest, principal_id=actor)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"extension={res.extension_id} version={res.version}",
    )


@extension_app.command("install")
def extension_install(
    extension_id: str = typer.Option(..., "--extension-id", help="Extension manifest ID"),
    name: str = typer.Option(..., "--name", help="Extension name"),
    version: str = typer.Option("1.0.0", "--version", help="Extension version"),
    entrypoint: str = typer.Option(..., "--entrypoint", help="Entrypoint inside allowed root"),
    checksum: str = typer.Option(..., "--checksum", help="64-hex SHA-256 checksum"),
    consent_id: str = typer.Option(..., "--consent-id", help="Granted extension consent ID"),
    permissions: Optional[str] = typer.Option(None, "--permissions", help="Comma-separated permissions required"),
    api_version: str = typer.Option("1.0", "--api-version", help="Compatible extension host API version"),
    activate: bool = typer.Option(True, "--activate/--no-activate", help="Activate immediately after install"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Install (and optionally activate) a consent-approved extension."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        from hydra_orch.core.extension_host import ExtensionManifest

        manifest = ExtensionManifest(
            extension_id=extension_id,
            name=name,
            version=version,
            entrypoint=entrypoint,
            permissions_required=_parse_csv(permissions),
            compatible_api_version=api_version,
            checksum=checksum,
        )
        return await _build_extension_host(svc).install(
            manifest,
            consent_id,
            principal_id=actor,
            activate=activate,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"install={res.install_id} status={res.status}",
    )


@extension_app.command("list")
def extension_list(
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List extension installations."""
    _run_cli_action(
        lambda svc: _build_extension_host(svc).list_installs(),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"installs={len(res)}",
    )


@extension_app.command("activate")
def extension_activate(
    install_id: str = typer.Argument(..., help="Extension install ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Activate an installed extension."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_extension_host(svc).activate(install_id, principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"install={res.install_id} status={res.status}",
    )


@extension_app.command("disable")
def extension_disable(
    install_id: str = typer.Argument(..., help="Extension install ID"),
    reason: str = typer.Option("operator_disabled", "--reason", help="Disable reason"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Disable an active extension."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_extension_host(svc).disable(install_id, principal_id=actor, reason=reason),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"install={res.install_id} status={res.status}",
    )


@extension_app.command("revoke")
def extension_revoke(
    install_id: str = typer.Argument(..., help="Extension install ID"),
    reason: str = typer.Option("operator_revoked", "--reason", help="Revocation reason"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke an extension installation."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_extension_host(svc).revoke(install_id, principal_id=actor, reason=reason),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"install={res.install_id} status={res.status}",
    )


@extension_app.command("rollback")
def extension_rollback(
    install_id: str = typer.Argument(..., help="Extension install ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Rollback an extension installation to its previous active version."""
    actor = _default_principal(principal_id)
    _run_cli_action(
        lambda svc: _build_extension_host(svc).rollback(install_id, principal_id=actor),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"install={res.install_id} manifest={res.extension_manifest_id} status={res.status}",
    )


@preference_app.command("set")
def preference_set(
    scope_type: str = typer.Option(..., "--scope-type", help="user|area|project"),
    scope_id: str = typer.Option(..., "--scope-id", help="Scope identifier"),
    key: str = typer.Option(..., "--key", help="Preference key"),
    value: str = typer.Option(..., "--value", help="Preference value (JSON literal or string)"),
    source: str = typer.Option("explicit", "--source", help="explicit|adaptive"),
    opt_in: bool = typer.Option(False, "--opt-in", help="Explicit opt-in flag for adaptive preferences"),
    actor: str = typer.Option("operator", "--actor", help="Acting operator ID"),
    expected_version: Optional[int] = typer.Option(None, "--expected-version", help="Expected optimistic version"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Set a scoped preference value."""

    async def _action(svc: RunService):
        from hydra_orch.core.preferences import PreferenceService

        return await PreferenceService(svc.store).set_preference(
            scope_type,  # type: ignore[arg-type]
            scope_id,
            key,
            _parse_json_value(value),
            source=source,  # type: ignore[arg-type]
            opt_in=opt_in,
            actor=actor,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"key={res.key} scope={res.scope_type}:{res.scope_id} v={res.version}",
    )


@preference_app.command("list")
def preference_list(
    scope_type: Optional[str] = typer.Option(None, "--scope-type", help="Optional filter: user|area|project"),
    scope_id: Optional[str] = typer.Option(None, "--scope-id", help="Optional scope identifier filter"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List active preferences."""

    async def _action(svc: RunService):
        from hydra_orch.core.preferences import PreferenceService

        return await PreferenceService(svc.store).list_preferences(
            scope_type=scope_type,  # type: ignore[arg-type]
            scope_id=scope_id,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"preferences={len(res)}",
    )


@preference_app.command("resolve")
def preference_resolve(
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User scope ID"),
    area_id: Optional[str] = typer.Option(None, "--area-id", help="Area scope ID"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project scope ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Resolve effective preferences across user/area/project scopes."""

    async def _action(svc: RunService):
        from hydra_orch.core.preferences import PreferenceService

        return await PreferenceService(svc.store).resolve_effective(
            user_id=user_id,
            area_id=area_id,
            project_id=project_id,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"resolved_keys={len(res)}",
    )


@preference_app.command("revert")
def preference_revert(
    scope_type: str = typer.Option(..., "--scope-type", help="user|area|project"),
    scope_id: str = typer.Option(..., "--scope-id", help="Scope identifier"),
    key: str = typer.Option(..., "--key", help="Preference key"),
    target_version: Optional[int] = typer.Option(None, "--target-version", help="Optional target historical version"),
    actor: str = typer.Option("operator", "--actor", help="Acting operator ID"),
    expected_version: Optional[int] = typer.Option(None, "--expected-version", help="Expected current version"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revert a preference to a prior version or clear it if no prior value."""

    async def _action(svc: RunService) -> dict[str, Any]:
        from hydra_orch.core.preferences import PreferenceService

        reverted = await PreferenceService(svc.store).revert_preference(
            scope_type,  # type: ignore[arg-type]
            scope_id,
            key,
            target_version=target_version,
            actor=actor,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
        return {"reverted": True, "preference": reverted}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"reverted=True key={key}",
    )


@preference_app.command("snapshot")
def preference_snapshot(
    run_id: str = typer.Argument(..., help="Target run ID"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User scope ID"),
    area_id: Optional[str] = typer.Option(None, "--area-id", help="Area scope ID"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project scope ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Freeze an immutable preference snapshot for a run."""

    async def _action(svc: RunService):
        from hydra_orch.core.preferences import PreferenceService

        return await PreferenceService(svc.store).snapshot_for_run(
            run_id,
            user_id=user_id,
            area_id=area_id,
            project_id=project_id,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"snapshot_run={res.run_id} keys={len(res.resolved_preferences)}",
    )


@transport_app.command("register")
def transport_register(
    transport_type: str = typer.Option(..., "--type", help="local|ssh|ide|cdp|remote"),
    target_identity: str = typer.Option(..., "--target-identity", help="Target host/endpoint identity"),
    capabilities: Optional[str] = typer.Option(None, "--capabilities", help="Comma-separated capabilities"),
    transport_id: Optional[str] = typer.Option(None, "--transport-id", help="Optional explicit transport ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Register a transport definition (always starts uncertified)."""

    async def _action(svc: RunService):
        from hydra_orch.bridge.transport_registry import TransportDefinition, TransportRegistry

        definition = TransportDefinition(
            transport_id=transport_id or new_id(),
            type=transport_type,  # type: ignore[arg-type]
            target_identity=target_identity,
            capabilities=_parse_csv(capabilities),
            is_certified=False,
        )
        return await TransportRegistry(svc.store).register_transport(definition)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"transport={res.transport_id} type={res.type} certified={res.is_certified}",
    )


@transport_app.command("list")
def transport_list(
    certified_only: bool = typer.Option(False, "--certified-only", help="Show only certified transports"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List registered transports."""

    async def _action(svc: RunService):
        from hydra_orch.bridge.transport_registry import TransportRegistry

        return await TransportRegistry(svc.store).list_transports(certified_only=certified_only)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"transports={len(res)}",
    )


@transport_app.command("certify")
def transport_certify(
    transport_id: str = typer.Argument(..., help="Transport ID"),
    report: Path = typer.Option(..., "--report", help="Path to TransportCertificationReport JSON file"),
    platform_name: Optional[str] = typer.Option(None, "--platform", help="Optional target platform check"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Certify a transport from a validated non-simulated JSON report."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        from hydra_orch.bridge.transport_registry import TransportCertificationReport, TransportRegistry

        raw = json.loads(report.read_text(encoding="utf-8"))
        parsed_report = TransportCertificationReport(**raw)
        cert_id = await TransportRegistry(svc.store).certify_transport(
            transport_id,
            parsed_report,
            principal_id=actor,
            platform_name=platform_name,
        )
        return {"certification_id": cert_id, "transport_id": transport_id}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"certification={res['certification_id']} transport={transport_id}",
    )


@transport_app.command("health")
def transport_health(
    transport_id: str = typer.Argument(..., help="Transport ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Execute and record a transport health check."""

    async def _action(svc: RunService):
        from hydra_orch.bridge.transport_registry import TransportRegistry

        return await TransportRegistry(svc.store).check_health(transport_id)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"transport={res.transport_id} status={res.status}",
    )


@token_app.command("create")
def token_create(
    principal_id: str = typer.Option(..., "--principal-id", help="Principal ID bound to the token"),
    scopes: Optional[str] = typer.Option(None, "--scopes", help="Comma-separated authorization scopes"),
    expires_at: Optional[str] = typer.Option(None, "--expires-at", help="Optional ISO-8601 expiration timestamp"),
    token: Optional[str] = typer.Option(None, "--token", help="Raw token (>=32 chars); hashed immediately, never persisted"),
    token_env: Optional[str] = typer.Option(None, "--token-env", help="Env var holding raw token"),
    token_id: Optional[str] = typer.Option(None, "--token-id", help="Optional explicit token record ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create a hashed access token in access_tokens without storing or printing plaintext."""
    if token is not None and token_env is not None:
        _handle_cli_exception(ValueError("Specify either --token or --token-env, not both"), as_json=as_json)

    raw_token: str
    if token is not None:
        raw_token = token
    elif token_env is not None:
        raw_token = os.environ.get(token_env, "")
        if not raw_token:
            _handle_cli_exception(
                ValueError(f"Environment variable '{token_env}' is unset or empty"),
                as_json=as_json,
            )
    else:
        raw_token = secrets.token_urlsafe(32)

    async def _action(svc: RunService) -> dict[str, Any]:
        from hydra_orch.core.auth import TokenVerifier

        tid = token_id or new_id()
        scope_list = list(_parse_csv(scopes))
        with redaction_scope([raw_token]):
            token_hash = TokenVerifier.from_token(raw_token).encode()
            await svc.store.initialize()
            async with svc.store._connect() as db:
                async with svc.store._transaction(db):
                    await db.execute(
                        """
                        INSERT INTO access_tokens(id, token_hash, principal_id, scopes_json, expires_at, revoked_at)
                        VALUES (?, ?, ?, ?, ?, NULL)
                        """,
                        (tid, token_hash, principal_id, json.dumps(scope_list), expires_at),
                    )
                    audit_meta = {"token_id": tid, "principal_id": principal_id, "scopes": scope_list}
                    await svc.store._record_command_in_tx(
                        db,
                        scope="auth",
                        idempotency_key=new_id(),
                        request_hash=svc.store.compute_request_hash(audit_meta),
                        response_payload={"event": "token.created", **audit_meta},
                    )
        return {
            "token_id": tid,
            "principal_id": principal_id,
            "scopes": scope_list,
            "expires_at": expires_at,
            "created": True,
        }

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"token_id={res['token_id']} principal={principal_id} created=True",
    )


@token_app.command("revoke")
def token_revoke(
    token_id: str = typer.Argument(..., help="Access token ID to revoke"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Revoke an access token record in access_tokens."""

    async def _action(svc: RunService) -> dict[str, Any]:
        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                row = await (
                    await db.execute("SELECT id, revoked_at FROM access_tokens WHERE id = ?", (token_id,))
                ).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"Access token '{token_id}' not found")
                await db.execute(
                    "UPDATE access_tokens SET revoked_at = COALESCE(revoked_at, datetime('now')) WHERE id = ?",
                    (token_id,),
                )
                audit_meta = {"token_id": token_id, "action": "revoke"}
                await svc.store._record_command_in_tx(
                    db,
                    scope="auth",
                    idempotency_key=new_id(),
                    request_hash=svc.store.compute_request_hash(audit_meta),
                    response_payload={"event": "token.revoked", "token_id": token_id},
                )
        return {"token_id": token_id, "revoked": True}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"token_id={token_id} revoked=True",
    )


@conflict_app.command("analyze")
def conflict_analyze(
    integration_id: str = typer.Argument(..., help="Integration ID"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Base commit SHA"),
    ours_sha: Optional[str] = typer.Option(None, "--ours-sha", help="Ours commit SHA"),
    theirs_sha: Optional[str] = typer.Option(None, "--theirs-sha", help="Theirs commit SHA"),
    max_repair_attempts: Optional[int] = typer.Option(None, "--max-repair-attempts", help="Max auto-repair attempts"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Analyze a merge/integration conflict and generate a typed conflict report."""

    async def _action(svc: RunService):
        from hydra_orch.core.conflict_resolver import ConflictResolver

        return await ConflictResolver(svc.store).analyze(
            integration_id,
            base_sha=base_sha,
            ours_sha=ours_sha,
            theirs_sha=theirs_sha,
            max_repair_attempts=max_repair_attempts,
            idempotency_key=idempotency_key,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"conflict={res.conflict_id} status={res.status}",
    )


@conflict_app.command("auto-repair")
def conflict_auto_repair(
    conflict_id: str = typer.Argument(..., help="Conflict ID"),
    repair_command: Optional[str] = typer.Option(None, "--repair-command", help="Optional repair command"),
    max_repair_attempts: Optional[int] = typer.Option(None, "--max-repair-attempts", help="Max repair attempts"),
    actor: str = typer.Option("conflict_resolver", "--actor", help="Acting actor ID"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Attempt bounded automatic conflict repair."""

    async def _action(svc: RunService):
        from hydra_orch.core.conflict_resolver import ConflictResolver

        return await ConflictResolver(svc.store).auto_repair(
            conflict_id,
            repair_command=repair_command,
            max_repair_attempts=max_repair_attempts,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"conflict={res.conflict_id} status={res.status}",
    )


@conflict_app.command("manual")
def conflict_manual(
    conflict_id: str = typer.Argument(..., help="Conflict ID"),
    actor: str = typer.Option("operator", "--actor", help="Acting operator ID"),
    finalize: bool = typer.Option(False, "--finalize", help="Finalize manual resolution immediately"),
    worktree_path: Optional[Path] = typer.Option(None, "--worktree-path", help="Resolved worktree path"),
    commit_message: Optional[str] = typer.Option(None, "--commit-message", help="Commit message when finalizing"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Resolve a conflict manually (or enter manual resolution state)."""

    async def _action(svc: RunService):
        from hydra_orch.core.conflict_resolver import ConflictResolver

        return await ConflictResolver(svc.store).resolve_manual(
            conflict_id,
            actor=actor,
            finalize=finalize,
            worktree_path=worktree_path,
            commit_message=commit_message,
            idempotency_key=idempotency_key,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"conflict={res.conflict_id} status={res.status}",
    )


@conflict_app.command("discard")
def conflict_discard(
    conflict_id: str = typer.Argument(..., help="Conflict ID"),
    actor: str = typer.Option("operator", "--actor", help="Acting operator ID"),
    reason: str = typer.Option("operator_discarded", "--reason", help="Discard reason"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Discard a conflict resolution and leave conflicting target preserved."""

    async def _action(svc: RunService):
        from hydra_orch.core.conflict_resolver import ConflictResolver

        return await ConflictResolver(svc.store).discard(
            conflict_id,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"conflict={res.conflict_id} status={res.status}",
    )


@budget_app.command("status")
def budget_status(
    run_id: str = typer.Argument(..., help="Run ID"),
    max_age_seconds: float = typer.Option(300.0, "--max-age-seconds", help="Telemetry freshness window"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Get budget governor status for a run."""

    async def _action(svc: RunService):
        from hydra_orch.core.budget import BudgetGovernor

        return await BudgetGovernor(svc.store).get_status(run_id, max_age_seconds=max_age_seconds)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"run={res.run_id} status={res.status} current_usd={res.current_usd}",
    )


@budget_app.command("extend")
def budget_extend(
    run_id: str = typer.Argument(..., help="Run ID"),
    additional_usd: Optional[float] = typer.Option(None, "--additional-usd", help="Additional USD allowance"),
    additional_tokens_in: Optional[int] = typer.Option(None, "--additional-tokens-in", help="Additional input tokens"),
    additional_tokens_out: Optional[int] = typer.Option(None, "--additional-tokens-out", help="Additional output tokens"),
    additional_wall_seconds: Optional[int] = typer.Option(
        None, "--additional-wall-seconds", help="Additional wall seconds"
    ),
    approved: bool = typer.Option(True, "--approved/--denied", help="Approve or deny budget extension"),
    actor: str = typer.Option("operator", "--actor", help="Acting operator ID"),
    reason: str = typer.Option("operator_budget_decision", "--reason", help="Decision reason"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Approve or deny a budget extension for a run."""

    async def _action(svc: RunService):
        from hydra_orch.core.budget import BudgetGovernor

        return await BudgetGovernor(svc.store).extend(
            run_id,
            additional_usd=additional_usd,
            additional_tokens_in=additional_tokens_in,
            additional_tokens_out=additional_tokens_out,
            additional_wall_seconds=additional_wall_seconds,
            approved=approved,
            actor=actor,
            reason=reason,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"run={res.run_id} approved={res.approved} status={res.status}",
    )


@pr_package_app.command("build")
def pr_package_build(
    run_id: str = typer.Argument(..., help="Run ID"),
    pr_branch: Optional[str] = typer.Option(None, "--pr-branch", help="Optional target PR branch name"),
    create_git_branch: bool = typer.Option(
        True, "--create-git-branch/--no-create-git-branch", help="Create local git PR branch"
    ),
    runtime_dir: Optional[Path] = typer.Option(None, "--runtime-dir", help="Optional PR package artifact directory"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Build a traceable PR package for a completed/integrated run."""

    async def _action(svc: RunService):
        from hydra_orch.core.packaging import PRPackager

        return await PRPackager(svc.store).build(
            run_id,
            pr_branch=pr_branch,
            create_git_branch=create_git_branch,
            runtime_dir=runtime_dir or svc.runtime_dir,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"package={res.package_id} branch={res.pr_branch} base={res.base_branch}",
    )


@pr_package_app.command("publish")
def pr_package_publish(
    package_id: str = typer.Argument(..., help="PR package ID"),
    authorized: bool = typer.Option(False, "--authorized", help="Explicit operator authorization to push"),
    policy_authorized: Optional[bool] = typer.Option(
        None, "--policy-authorized/--policy-denied", help="Optional policy authorization override"
    ),
    remote: str = typer.Option("origin", "--remote", help="Target git remote"),
    actor: str = typer.Option("operator", "--actor", help="Acting operator ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Publish a built PR package to a remote repository when explicitly authorized."""

    async def _action(svc: RunService):
        from hydra_orch.core.packaging import PRPackager

        return await PRPackager(svc.store).publish(
            package_id,
            authorized=authorized,
            policy_authorized=policy_authorized,
            remote=remote,
            actor=actor,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"package={res.package_id} published={res.published} remote={res.remote}",
    )


if __name__ == "__main__":
    app()
