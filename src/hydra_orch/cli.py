"""CLI for hydra-orch: serve, run, status, quota, and M1 control-plane commands (T01 / T07)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

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


def _emit_output(
    data: Any,
    *,
    as_json: bool = False,
    output_file: Optional[Path] = None,
    summary_text: Optional[str] = None,
) -> None:
    serialized = json.dumps(data, indent=2, sort_keys=True, default=str)
    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(serialized + "\n", encoding="utf-8")
    if as_json:
        typer.echo(serialized)
    elif summary_text:
        console.print(summary_text, markup=False)
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
    }
    if isinstance(exc, (IdempotencyConflictError, OptimisticLockError)):
        code = "idempotency_conflict" if isinstance(exc, IdempotencyConflictError) else "optimistic_lock_conflict"
        exit_code = 3
        msg = str(exc)
    elif isinstance(exc, ContractViolation):
        code = exc.code
        exit_code = 3 if exc.code in conflict_codes else 1
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
    elif isinstance(exc, StorageError):
        code = "storage_error"
        exit_code = 2
        msg = str(exc)
    else:
        code = "system_error"
        exit_code = 2
        msg = str(exc)

    if as_json:
        typer.echo(
            json.dumps(
                {"code": code, "message": msg, "exit_code": exit_code},
                sort_keys=True,
            )
        )
    else:
        console.print(f"{code}: {msg}", markup=False)
    raise typer.Exit(code=exit_code) from exc


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


if __name__ == "__main__":
    app()
