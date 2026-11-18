"""CLI for hydra-orch: serve, run, status, quota, and control-plane commands (T01 / T07 / T23)."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
import inspect as _py_inspect
import io
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import sys
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence
import uuid

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError
import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.table import Table

from hydra_orch.config import ConfigError, HydraConfig, load_config
from hydra_orch.core.checkpointer import (
    ExecutionStore,
    IdempotencyConflictError,
    OptimisticLockError,
    StorageError,
    StorageIntegrityError,
)
from hydra_orch.core.git_workspace import GitWorkspaceError, GitWorkspaceService
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
    RelativePath,
    RunSpec,
    TaskSpec,
)
from hydra_orch.server import get_run_service

_DEFAULT_SERVER_GET_RUN_SERVICE = get_run_service
_ACTIVE_CONFIG_PATH: Optional[Path] = None
_CLI_SERVICE_CACHE: Dict[tuple[str, str], RunService] = {}


def _ensure_utf8_streams() -> None:
    """Safely configure UTF-8 output on redirected/Windows consoles without breaking test streams."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
                pass


_ensure_utf8_streams()

app = typer.Typer(
    name="hydra",
    help="hydra-orch: Universal Autonomous LLM Orchestrator CLI",
    add_completion=False,
)
console = Console()


@app.callback()
def _main_callback(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        envvar="HYDRA_CONFIG",
        help="Path to Hydra YAML configuration file (or HYDRA_CONFIG)",
    ),
) -> None:
    """Configure UTF-8 console output and optional explicit --config file."""
    global _ACTIVE_CONFIG_PATH
    _ensure_utf8_streams()
    if config is None or not str(config).strip():
        _ACTIVE_CONFIG_PATH = None
        return

    as_json = "--json" in sys.argv
    resolved = Path(config).expanduser()
    if not resolved.is_file():
        _handle_cli_exception(
            ConfigError(f"Configuration file not found: {resolved}"),
            as_json=as_json,
        )
    resolved = resolved.resolve()
    os.environ["HYDRA_CONFIG"] = str(resolved)
    _ACTIVE_CONFIG_PATH = resolved
    try:
        import hydra_orch.config as _cfg_mod

        if load_config is _cfg_mod.load_config:
            loaded = _cfg_mod.load_config(resolved, reload=True)
        else:
            try:
                loaded = load_config(resolved, reload=True)
            except TypeError:
                try:
                    loaded = load_config(resolved)
                except TypeError:
                    loaded = load_config()
        _cfg_mod._CONFIG_CACHE = loaded
        _cfg_mod._CONFIG_CACHE_PATH = resolved
        try:
            import hydra_orch.server as _srv_mod

            _srv_mod.config = loaded
        except Exception:
            pass
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)


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


def _load_active_config() -> HydraConfig:
    explicit_path = _ACTIVE_CONFIG_PATH
    if explicit_path is None:
        env_cfg = os.environ.get("HYDRA_CONFIG", "").strip()
        if env_cfg:
            explicit_path = Path(env_cfg).expanduser()
    if explicit_path is not None:
        try:
            return load_config(explicit_path)
        except TypeError:
            return load_config()
    return load_config()


def _parse_repair_command(
    repair_command: Optional[str],
    repair_args: Optional[Sequence[str]] = None,
) -> Optional[List[str]]:
    tokens: List[str] = []
    if repair_command is not None and repair_command.strip():
        raw_tokens = shlex.split(repair_command.strip(), posix=(os.name != "nt"))
        if os.name == "nt":
            cleaned: List[str] = []
            for tok in raw_tokens:
                if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in {'"', "'"}:
                    quote = tok[0]
                    inner = tok[1:-1]
                    if quote == '"':
                        inner = inner.replace('\\"', '"')
                    cleaned.append(inner)
                else:
                    cleaned.append(tok)
            tokens.extend(cleaned)
        else:
            tokens.extend(raw_tokens)
    if repair_args:
        tokens.extend(str(arg) for arg in repair_args)
    return tokens if tokens else None


class _DetachedCliRunService(RunService):
    """CWD-independent RunService when the operator invokes Hydra outside a Git repository."""

    def __init__(
        self,
        base_dir: Path,
        *,
        store: Optional[ExecutionStore] = None,
        runtime_dir: Optional[Path] = None,
    ) -> None:
        from hydra_orch.bridge.worker_runner import WorkerRunner
        from hydra_orch.core.budget import BudgetGovernor
        from hydra_orch.core.run_service import CheckRunner

        resolved_base = Path(os.path.realpath(base_dir))
        rt_dir = Path(os.path.realpath(runtime_dir or (resolved_base / ".orchestrator")))
        self.repo_root = resolved_base
        self.runtime_dir = rt_dir
        self.store = store or ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
        self.git_workspace = None  # type: ignore[assignment]
        self.worker_runner = WorkerRunner()
        self.check_runner = CheckRunner(repo_root=resolved_base, runtime_dir=rt_dir)
        self._workspaces_by_root = {}
        self._check_runners_by_root = {os.path.normcase(str(resolved_base)): self.check_runner}
        self._project_meta = {}
        self.budget_governor = BudgetGovernor(self.store)


def get_cli_run_service() -> RunService:
    """Resolve the active CLI RunService instance without crashing outside a Git repository."""
    if get_run_service is not _DEFAULT_SERVER_GET_RUN_SERVICE:
        return get_run_service()

    import hydra_orch.server as _srv_mod

    if _srv_mod._run_service is not None:
        return _srv_mod._run_service

    try:
        cfg = _load_active_config()
        state_db_rel = cfg.hydra.state_db
    except Exception:
        state_db_rel = ".orchestrator/checkpoints.sqlite"

    cwd_real = Path(os.path.realpath(Path.cwd()))
    try:
        repo_root = GitWorkspaceService.resolve_repo_root(cwd_real)
        db_candidate = Path(state_db_rel)
        db_path = db_candidate if db_candidate.is_absolute() else (repo_root / db_candidate)
        rt_dir = db_path.parent
        cache_key = ("git", os.path.normcase(str(repo_root)) + "::" + os.path.normcase(str(db_path)))
        cached = _CLI_SERVICE_CACHE.get(cache_key)
        if cached is None:
            cached = RunService(
                repo_root=repo_root,
                store=ExecutionStore(db_path=db_path),
                runtime_dir=rt_dir,
            )
            _CLI_SERVICE_CACHE[cache_key] = cached
        return cached
    except (GitWorkspaceError, ContractViolation):
        db_candidate = Path(state_db_rel)
        db_path = db_candidate if db_candidate.is_absolute() else (cwd_real / db_candidate)
        rt_dir = db_path.parent
        cache_key = ("detached", os.path.normcase(str(cwd_real)) + "::" + os.path.normcase(str(db_path)))
        cached = _CLI_SERVICE_CACHE.get(cache_key)
        if cached is None:
            cached = _DetachedCliRunService(
                cwd_real,
                store=ExecutionStore(db_path=db_path),
                runtime_dir=rt_dir,
            )
            _CLI_SERVICE_CACHE[cache_key] = cached
        return cached


def _launch_tui(
    *,
    run_id: Optional[str] = None,
    api_url: Optional[str] = None,
    api_token_env: str = "HYDRA_API_TOKEN",
    refresh_seconds: float = 2.0,
    once: bool = False,
    script: Optional[Path] = None,
    no_alt_screen: bool = False,
    max_steps: Optional[int] = None,
    principal_id: Optional[str] = None,
) -> None:
    """Launch the interactive Rich TUI cockpit in local or remote HTTP mode."""
    from hydra_orch.tui import run_cockpit

    resolved_principal = _default_principal(principal_id)
    try:
        svc = None if api_url else get_cli_run_service()
        run_cockpit(
            run_service=svc,
            api_url=api_url,
            api_token_env=api_token_env,
            run_id=run_id,
            principal_id=resolved_principal,
            console=None,
            refresh_seconds=refresh_seconds,
            no_alt_screen=no_alt_screen,
            once=once,
            script=script,
            max_steps=max_steps,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_cli_exception(exc, as_json=False)


def _run_cli_action(
    action: Callable[[RunService], Awaitable[Any]],
    *,
    as_json: bool = False,
    output_file: Optional[Path] = None,
    render_summary: Optional[Callable[[Any], str]] = None,
) -> Any:
    try:
        svc = get_cli_run_service()
        result = asyncio.run(action(svc))
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)
    summary = render_summary(result) if render_summary is not None else None
    _emit_output(result, as_json=as_json, output_file=output_file, summary_text=summary)
    return result


def _resolve_allowed_roots(svc: RunService) -> List[Path]:
    configured: List[str] = []
    try:
        cfg = _load_cli_config(svc)
        raw_cfg_roots = getattr(cfg, "allowed_workspace_roots", None) or getattr(
            getattr(cfg, "hydra", None), "allowed_workspace_roots", None
        )
        if raw_cfg_roots:
            configured = [str(p) for p in raw_cfg_roots if p]
    except Exception:
        pass

    if not configured:
        env_raw = os.environ.get("HYDRA_ALLOWED_WORKSPACE_ROOTS", "").strip()
        if env_raw:
            try:
                parsed = (
                    json.loads(env_raw)
                    if env_raw.startswith("[")
                    else [p.strip() for p in env_raw.split(",") if p.strip()]
                )
                configured = [str(p) for p in parsed if p]
            except json.JSONDecodeError:
                configured = [p.strip() for p in env_raw.split(",") if p.strip()]

    if configured:
        return [Path(root) for root in configured]
    return [svc.repo_root]


def _build_agent_registry(svc: RunService):
    from hydra_orch.core.agent_registry import AgentRegistry

    return AgentRegistry(svc.store, executable_locator=lambda name: shutil.which(name))


def _build_workspace_registry(svc: RunService):
    from hydra_orch.core.workspace_registry import WorkspaceRegistry

    return WorkspaceRegistry(svc.store, allowed_roots=_resolve_allowed_roots(svc))


def _build_discovery_service(svc: RunService, *, principal_id: str, enabled: bool = True):
    from hydra_orch.core.discovery import DiscoveryService

    return DiscoveryService(
        svc.store,
        allowed_roots=_resolve_allowed_roots(svc),
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
        allowed_roots=_resolve_allowed_roots(svc),
        runtime_dir=svc.runtime_dir / "extensions",
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host address (loopback by default)"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the OpenAI-compatible proxy and Control Plane server (http://127.0.0.1:8000/v1)."""
    safe_host = rich_escape(str(host))
    banner = (
        "[bold cyan]HYDRA ORCHESTRATOR[/bold cyan]\n"
        "[dim]Universal Autonomous LLM Orchestrator & Control Plane[/dim]\n\n"
        f"API Endpoint: [green]http://{safe_host}:{port}/v1[/green]\n"
        f"Control Plane: [green]http://{safe_host}:{port}/v1/control-plane[/green]"
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
    try:
        cfg = _load_active_config()
    except Exception as exc:
        _handle_cli_exception(exc, as_json=False)
    chosen_mode = mode or cfg.orchestrator.default_mode
    safe_mode = rich_escape(redact_text(str(chosen_mode).upper()))
    safe_prompt = rich_escape(redact_text(prompt))

    console.print(
        Panel(
            f"[bold green]Starting Task in Mode:[/bold green] [yellow]{safe_mode}[/yellow]\n"
            f"[bold]Prompt:[/bold] {safe_prompt}",
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
        console.print(f"{exc.code}: {redact_text(str(exc))}", markup=False)
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
    allowed_paths: str = typer.Option(
        "*", "--allowed-paths", help="Comma-separated allowed relative paths for the task"
    ),
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
    async def _do_submit() -> tuple[Dict[str, Any], bool]:
        svc: RunService = get_cli_run_service()
        if spec_file is not None:
            raw_data = json.loads(spec_file.read_text(encoding="utf-8"))
            if isinstance(raw_data, dict) and isinstance(raw_data.get("tasks"), list):
                for idx, raw_task in enumerate(raw_data["tasks"]):
                    if isinstance(raw_task, dict) and not raw_task.get("allowed_paths"):
                        raise ContractViolation(
                            "validation_error",
                            f"Task #{idx + 1} in --spec-file must declare non-empty allowed_paths",
                        )
            run_spec = RunSpec.model_validate(raw_data)
            if isinstance(svc, _DetachedCliRunService):
                svc = RunService(
                    repo_root=run_spec.repo_root,
                    store=svc.store,
                    runtime_dir=svc.runtime_dir,
                )
            req_hash = svc.store.compute_request_hash(run_spec)
        else:
            if not objective:
                raise ContractViolation("missing_objective", "Either --spec-file or --objective must be provided")
            parsed_allowed = _parse_csv(allowed_paths)
            if not parsed_allowed:
                raise ContractViolation(
                    "validation_error",
                    "--allowed-paths must specify at least one relative path pattern (e.g. '*' or 'src/**')",
                )
            try:
                validated_allowed = tuple(
                    TypeAdapter(RelativePath).validate_python(pat) for pat in parsed_allowed
                )
            except ValidationError as exc:
                raise ContractViolation(
                    "scope_violation",
                    f"Invalid --allowed-paths pattern: {exc}",
                ) from exc

            resolved_repo = Path(repo_root) if repo_root is not None else svc.repo_root
            ws = svc._get_git_workspace(resolved_repo)
            if isinstance(svc, _DetachedCliRunService):
                svc = RunService(
                    repo_root=ws.repo_root,
                    store=svc.store,
                    runtime_dir=svc.runtime_dir,
                )
            resolved_sha = base_sha or ws.resolve_commit_sha("HEAD")
            cmd_tokens = tuple(check_cmd) if check_cmd else ("git", "status", "--short")
            idem = idempotency_key or f"cli-idem-{uuid.uuid4().hex[:16]}"
            gen_run_id = f"run-{uuid.uuid4().hex[:12]}"
            exec_id = "fake_subprocess" if dry_run else executor
            t_spec = TaskSpec(
                task_id=task_id,
                run_id=gen_run_id,
                objective=objective,
                allowed_paths=validated_allowed,
                acceptance_criteria=(
                    CheckSpec(
                        check_id="chk-default",
                        command=cmd_tokens,
                    ),
                ),
                assigned_executor=exec_id,
            )
            semantic: Dict[str, Any] = {
                "project_id": project_id,
                "repo_root": str(ws.repo_root),
                "base_sha": resolved_sha,
                "objective": objective,
                "task_id": task_id,
                "command": list(cmd_tokens),
                "assigned_executor": exec_id,
            }
            if validated_allowed != ("*",):
                semantic["allowed_paths"] = list(validated_allowed)
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
        task_failed = False
        if created and execute:
            for t in run_spec.tasks:
                outcome = await svc.execute_task_attempt(
                    run_id=run_rec["id"],
                    task_id=t.task_id,
                    dry_run=dry_run,
                )
                if outcome.result.task_status.value in {"failed", "cancelled", "blocked"}:
                    task_failed = True
            refreshed = await svc.store.get_run(run_rec["id"])
            if refreshed is not None:
                run_rec = refreshed

        final_status = "failed" if (task_failed and run_rec["status"] == "running") else run_rec["status"]
        payload = {
            "run_id": run_rec["id"],
            "project_id": run_rec["project_id"],
            "status": final_status,
            "revision": int(run_rec["revision"]),
            "created": created,
            "base_sha": run_rec["base_sha"],
        }
        exec_failed = bool(execute and (task_failed or final_status in {"failed", "cancelled", "blocked"}))
        return payload, exec_failed

    try:
        res, exec_failed = asyncio.run(_do_submit())
        rid = res.get("run_id") or res.get("id")
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=f"Run {rid} submitted (status={res['status']}, created={res['created']})",
        )
        if exec_failed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
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
        svc = get_cli_run_service()
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
        rid = res.get("run_id") or res.get("id")
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=(
                f"Run {rid} | status={res['status']} | revision={res['revision']} | "
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
        svc = get_cli_run_service()
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
        svc = get_cli_run_service()
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
                typer.echo(json.dumps(redact(_to_jsonable(res)), sort_keys=True))
            else:
                console.print(f"integration_{res['status']}: {redact(_to_jsonable(res))}", markup=False)
            raise typer.Exit(code=1)
        rid = res.get("run_id") or res.get("id")
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=(
                f"Integrated run {rid} into {res['target_branch']} "
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
        svc = get_cli_run_service()
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
            summary_text=f"Cancelled {res['scope']} {res.get('task_id') or res.get('run_id') or res.get('id')} (status={res['status']})",
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
        svc = get_cli_run_service()
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
    try:
        cfg = _load_active_config()
    except Exception as exc:
        _handle_cli_exception(exc, as_json=False)
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
            details = str(adapter.last_error or "Ready")
            if hasattr(adapter, "cdp_port"):
                details = f"Port: {adapter.cdp_port} | {details}"
            elif hasattr(adapter, "base_url"):
                details = f"URL: {adapter.base_url} | {details}"
            return (
                rich_escape(redact_text(str(name))),
                rich_escape(str(adapter.__class__.__name__)),
                status_text,
                rich_escape(redact_text(details)),
            )

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

    try:
        cfg = _load_active_config()
    except Exception as exc:
        _handle_cli_exception(exc, as_json=False)
    client = OmniRouteClient(
        base_url=cfg.omniroute.base_url,
        quota_api_url=cfg.omniroute.quota_api_url,
        enabled=not cfg.is_direct_mode,
        api_key_env=cfg.omniroute.api_key_env,
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
                status_str = str(v.get("status", "unknown")).upper()
                table.add_row(
                    rich_escape(redact_text(str(k).replace("_", " ").title())),
                    rich_escape(rem),
                    rich_escape(resets),
                    rich_escape(redact_text(status_str)),
                )

    asyncio.run(_fetch())
    console.print(table)


# ---------------------------------------------------------------------------
# Missing M1 top-level control-plane commands
# ---------------------------------------------------------------------------


@app.command("project-create")
def project_create_cmd(
    canonical_root: Path = typer.Option(..., "--root", help="Canonical project repository or folder root"),
    name: str = typer.Option(..., "--name", help="Project name"),
    base_branch: str = typer.Option("main", "--base-branch", help="Default base branch"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Pinned base commit SHA"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Optional explicit project ID"),
    allow_plain_folder: bool = typer.Option(
        False, "--allow-plain-folder", help="Allow registering a plain folder without a Git repository"
    ),
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
            allow_plain_folder=allow_plain_folder,
        ),
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"project={res.get('project_id') or res.get('id')} name={res.get('name')} branch={res.get('base_branch')}",
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


async def _cli_http_request(
    method: str,
    api_url: str,
    path: str,
    *,
    api_token_env: str = "HYDRA_API_TOKEN",
    json_body: Any = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    from hydra_orch.tui import resolve_api_token, sanitize_api_url

    base_url = sanitize_api_url(api_url)
    token = resolve_api_token(api_token_env=api_token_env, interactive=False)
    headers: Dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    scope_cm = redaction_scope([token]) if token else redaction_scope([])
    with scope_cm:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:
            resp = await client.request(method, path, json=json_body, params=params)
            if resp.status_code >= 400:
                code = f"http_{resp.status_code}"
                msg = f"Control Plane returned HTTP {resp.status_code}"
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        code = str(data.get("code") or code)
                        msg = str(data.get("message") or data.get("detail") or msg)
                except Exception:
                    if resp.text:
                        msg = resp.text[:300]
                if resp.status_code == 409 and code in {"http_409", "optimistic_lock_conflict"}:
                    raise OptimisticLockError(redact_text(msg))
                raise ContractViolation(code, redact_text(msg))
            return resp.json() if resp.content else {}


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
        render_summary=lambda res: f"area={res.get('area_id') or res.get('id')} name={res.get('name')}",
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
        render_summary=lambda res: f"workspace={res.get('workspace_id') or res.get('id')} area={res.get('area_id')}",
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


@workspace_app.command("update")
def workspace_update(
    workspace_id: str = typer.Argument(..., help="Workspace ID to update"),
    name: str = typer.Option(..., "--name", help="Updated workspace name"),
    expected_revision: Optional[int] = typer.Option(None, "--expected-revision", help="Optional expected revision"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Optional remote Control Plane base URL"),
    api_token_env: str = typer.Option("HYDRA_API_TOKEN", "--api-token-env", help="Env var holding Bearer token"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Update workspace metadata (such as name) with optional optimistic revision check."""
    actor = _default_principal(principal_id)
    if api_url is not None:
        body: Dict[str, Any] = {"name": name}
        if expected_revision is not None:
            body["expected_revision"] = expected_revision
        try:
            res = asyncio.run(
                _cli_http_request(
                    "PUT",
                    api_url,
                    f"/v1/control-plane/workspaces/{workspace_id}",
                    api_token_env=api_token_env,
                    json_body=body,
                )
            )
        except Exception as exc:
            _handle_cli_exception(exc, as_json=as_json)
        ws_id = res.get("workspace_id") or res.get("id") or workspace_id
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=f"workspace={ws_id} name={res.get('name', name)}",
        )
        return

    async def _action(svc: RunService) -> dict[str, Any]:
        reg = _build_workspace_registry(svc)
        if hasattr(reg, "update_workspace"):
            sig = _py_inspect.signature(reg.update_workspace)
            kwargs: Dict[str, Any] = {"principal_id": actor}
            if "name" in sig.parameters:
                kwargs["name"] = name
            if expected_revision is not None and "expected_revision" in sig.parameters:
                kwargs["expected_revision"] = expected_revision
            return await reg.update_workspace(workspace_id, **kwargs)

        clean_name = name.strip()
        if not clean_name or len(clean_name) > 256 or "\x00" in clean_name:
            raise ContractViolation("registry_invalid", "Expected a nonempty bounded identifier or name")
        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                row = await reg._workspace(db, workspace_id, actor)
                if expected_revision is not None and int(row["revision"]) != expected_revision:
                    raise OptimisticLockError("Workspace revision changed")
                await db.execute(
                    "UPDATE area_workspaces SET name = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                    (clean_name, workspace_id),
                )
                await reg._audit(db, "workspace.updated", actor, workspace_id)
            return dict(await reg._workspace(db, workspace_id, actor))

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"workspace={res.get('workspace_id') or res.get('id')} name={res.get('name')}",
    )


@workspace_app.command("delete")
def workspace_delete(
    workspace_id: str = typer.Argument(..., help="Workspace ID to delete"),
    expected_revision: Optional[int] = typer.Option(None, "--expected-revision", help="Optional expected revision"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Optional remote Control Plane base URL"),
    api_token_env: str = typer.Option("HYDRA_API_TOKEN", "--api-token-env", help="Env var holding Bearer token"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Delete an empty workspace owned by the acting principal."""
    actor = _default_principal(principal_id)
    if api_url is not None:
        params: Optional[Dict[str, Any]] = (
            {"expected_revision": expected_revision} if expected_revision is not None else None
        )
        try:
            res = asyncio.run(
                _cli_http_request(
                    "DELETE",
                    api_url,
                    f"/v1/control-plane/workspaces/{workspace_id}",
                    api_token_env=api_token_env,
                    params=params,
                )
            )
        except Exception as exc:
            _handle_cli_exception(exc, as_json=as_json)
        ws_id = res.get("workspace_id") or res.get("id") or workspace_id
        _emit_output(
            res or {"workspace_id": ws_id, "deleted": True},
            as_json=as_json,
            output_file=output,
            summary_text=f"workspace={ws_id} deleted=True",
        )
        return

    async def _action(svc: RunService) -> dict[str, Any]:
        reg = _build_workspace_registry(svc)
        if hasattr(reg, "delete_workspace"):
            sig = _py_inspect.signature(reg.delete_workspace)
            kwargs: Dict[str, Any] = {"principal_id": actor}
            if expected_revision is not None and "expected_revision" in sig.parameters:
                kwargs["expected_revision"] = expected_revision
            out = await reg.delete_workspace(workspace_id, **kwargs)
            return out if isinstance(out, dict) else {"workspace_id": workspace_id, "deleted": True}

        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                row = await (await db.execute("SELECT * FROM area_workspaces WHERE id = ?", (workspace_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", "Workspace does not exist")
                await reg._area(db, row["area_id"], actor)
                if expected_revision is not None and int(row["revision"]) != expected_revision:
                    raise OptimisticLockError("Workspace revision changed")
                linked_projects = (
                    await (
                        await db.execute("SELECT COUNT(*) FROM projects WHERE workspace_id = ?", (workspace_id,))
                    ).fetchone()
                )[0]
                if linked_projects > 0:
                    raise ContractViolation(
                        "registry_conflict",
                        "Cannot delete workspace while projects remain attached to it",
                    )
                await db.execute("DELETE FROM area_workspaces WHERE id = ?", (workspace_id,))
                await reg._audit(db, "workspace.deleted", actor, workspace_id)
        return {"workspace_id": workspace_id, "deleted": True}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"workspace={res.get('workspace_id') or res.get('id') or workspace_id} deleted=True",
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
    allow_plain_folder: bool = typer.Option(
        False, "--allow-plain-folder", help="Allow registering a plain folder without Git"
    ),
    metadata_json: Optional[str] = typer.Option(None, "--metadata-json", help="Optional metadata JSON object"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create a workspace-scoped project."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        metadata = _parse_json_obj(metadata_json, flag_name="--metadata-json")
        reg = _build_workspace_registry(svc)
        kwargs: Dict[str, Any] = {
            "principal_id": actor,
            "base_branch": base_branch,
            "base_sha": base_sha,
            "metadata": metadata or None,
        }
        sig = _py_inspect.signature(reg.create_project)
        if "allow_plain_folder" in sig.parameters:
            kwargs["allow_plain_folder"] = allow_plain_folder
        elif allow_plain_folder and not (Path(root) / ".git").exists():
            raw_root = reg._absolute(root).resolve()
            if not any(raw_root == allowed or allowed in raw_root.parents for allowed in reg.allowed_roots):
                raise ContractViolation("authorization_denied", "Project directory is outside the root allowlist")
            if not raw_root.is_dir():
                raise ContractViolation("workspace_invalid", "Project folder does not exist")
            merged_meta = dict(metadata or {})
            merged_meta.setdefault("workspace_kind", "folder")
            await svc.store.initialize()
            async with svc.store._connect() as db:
                async with svc.store._transaction(db):
                    await reg._workspace(db, workspace_id, actor)
                    pid = new_id()
                    await db.execute(
                        """INSERT INTO projects
                        (id,canonical_root,name,workspace_id,metadata_json,base_branch,base_sha)
                        VALUES (?,?,?,?,?,?,?)""",
                        (pid, str(raw_root), name.strip(), workspace_id, json.dumps(redact(merged_meta), sort_keys=True), None, None),
                    )
                    await reg._audit(db, "project.created", actor, pid)
                return dict((await reg._project(db, pid, actor))[0])
        return await reg.create_project(workspace_id, name, root, **kwargs)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"project={res.get('project_id') or res.get('id')} workspace={res.get('workspace_id')}",
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
        render_summary=lambda res: f"project={res.get('project_id') or res.get('id')} workspace={res.get('workspace_id')}",
    )


@repo_app.command("register")
def repo_register(
    project_id: str = typer.Option(..., "--project-id", help="Parent project ID"),
    root: Path = typer.Option(..., "--root", help="Canonical repository root"),
    authorized_principal: Optional[str] = typer.Option(None, "--authorized-principal", help="Authorized principal ID"),
    scopes: str = typer.Option("read,write", "--scopes", help="Comma-separated authorization scopes"),
    allowed_paths: str = typer.Option(..., "--allowed-paths", help="Comma-separated allowed relative paths (required)"),
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
        render_summary=lambda res: f"repository={res.get('repository_id') or res.get('id')} project={res.get('project_id')}",
    )


@repo_app.command("update")
def repo_update(
    repository_id: str = typer.Argument(..., help="Repository ID to update"),
    allowed_paths: Optional[str] = typer.Option(None, "--allowed-paths", help="Updated comma-separated allowed relative paths"),
    base_branch: Optional[str] = typer.Option(None, "--base-branch", help="Updated repository base branch"),
    base_sha: Optional[str] = typer.Option(None, "--base-sha", help="Updated pinned base commit SHA"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Update an existing repository registration (such as allowed_paths or base_branch)."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        reg = _build_workspace_registry(svc)
        parsed_paths = list(_parse_csv(allowed_paths)) if allowed_paths is not None else None
        if hasattr(reg, "update_repository"):
            sig = _py_inspect.signature(reg.update_repository)
            kwargs: Dict[str, Any] = {"principal_id": actor}
            if parsed_paths is not None and "allowed_paths" in sig.parameters:
                kwargs["allowed_paths"] = parsed_paths
            if base_branch is not None and "base_branch" in sig.parameters:
                kwargs["base_branch"] = base_branch
            if base_sha is not None and "base_sha" in sig.parameters:
                kwargs["base_sha"] = base_sha
            return await reg.update_repository(repository_id, **kwargs)

        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                repo = await (await db.execute("SELECT * FROM repositories WHERE id = ?", (repository_id,))).fetchone()
                if repo is None:
                    raise ContractViolation("resource_not_found", "Repository does not exist")
                await reg._project(db, repo["project_id"], actor)
                new_paths_json = repo["allowed_paths_json"]
                if parsed_paths is not None:
                    if not parsed_paths:
                        raise ContractViolation("scope_violation", "Explicit repository file scope is required")
                    try:
                        validated = tuple(TypeAdapter(RelativePath).validate_python(p) for p in parsed_paths)
                    except ValidationError:
                        raise ContractViolation("scope_violation", "File scopes must be relative without traversal") from None
                    new_paths_json = json.dumps(validated)
                eff_branch = base_branch or repo["base_branch"]
                if base_branch is not None or base_sha is not None:
                    _, eff_sha = await reg._git_identity(repo["root_canonical"], eff_branch, base_sha)
                else:
                    eff_sha = repo["base_sha"]
                await db.execute(
                    "UPDATE repositories SET allowed_paths_json = ?, base_branch = ?, base_sha = ? WHERE id = ?",
                    (new_paths_json, eff_branch, eff_sha, repository_id),
                )
                await reg._audit(db, "repository.updated", actor, repository_id)
            return dict(await (await db.execute("SELECT * FROM repositories WHERE id = ?", (repository_id,))).fetchone())

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"repository={res.get('repository_id') or res.get('id')} project={res.get('project_id')}",
    )


@repo_app.command("delete")
def repo_delete(
    repository_id: str = typer.Argument(..., help="Repository ID to delete"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting principal ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Delete a repository registration and revoke its authorizations."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService) -> dict[str, Any]:
        reg = _build_workspace_registry(svc)
        if hasattr(reg, "delete_repository"):
            out = await reg.delete_repository(repository_id, principal_id=actor)
            return out if isinstance(out, dict) else {"repository_id": repository_id, "deleted": True}

        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                repo = await (await db.execute("SELECT * FROM repositories WHERE id = ?", (repository_id,))).fetchone()
                if repo is None:
                    raise ContractViolation("resource_not_found", "Repository does not exist")
                await reg._project(db, repo["project_id"], actor)
                await db.execute(
                    "UPDATE authorizations SET revoked_at = COALESCE(revoked_at, datetime('now')) WHERE resource_ref = ?",
                    (f"repository:{repository_id}",),
                )
                await db.execute("DELETE FROM repositories WHERE id = ?", (repository_id,))
                await reg._audit(db, "repository.deleted", actor, repository_id)
        return {"repository_id": repository_id, "deleted": True}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"repository={res.get('repository_id') or res.get('id') or repository_id} deleted=True",
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
    report: Path = typer.Option(
        ...,
        "--report",
        help="Path to certification JSON report (under .orchestrator/certification/)",
    ),
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
        render_summary=lambda res: f"session={res.get('session_id') or res.get('id')} state={res.get('state')}",
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
            f"thread={res.get('thread_id') or res.get('id')} state={res.get('state')}"
            if isinstance(res, dict)
            else f"threads={len(res)}"
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
        render_summary=lambda res: f"id={res.get('id') or res.get('thread_id') or res.get('session_id')} state={res.get('state')}",
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
route_app = typer.Typer(help="Inspect OmniRoute models/quotas and select next-run provider accounts.")
automation_app = typer.Typer(help="Manage durable automation schedules and view trigger history.")
conversation_app = typer.Typer(help="List conversations and apply isolated workspace changes to source projects.")

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
app.add_typer(route_app, name="route")
app.add_typer(automation_app, name="automation")
app.add_typer(conversation_app, name="conversation")


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
    repair_command: Optional[str] = typer.Option(
        None, "--repair-command", help="Optional repair command (parsed via shlex.split)"
    ),
    repair_arg: Optional[List[str]] = typer.Option(
        None, "--repair-arg", help="Optional repeatable repair command argument token"
    ),
    max_repair_attempts: Optional[int] = typer.Option(None, "--max-repair-attempts", help="Max repair attempts"),
    actor: str = typer.Option("conflict_resolver", "--actor", help="Acting actor ID"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Attempt bounded automatic conflict repair."""
    try:
        parsed_cmd = _parse_repair_command(repair_command, repair_arg)
    except Exception as exc:
        _handle_cli_exception(exc, as_json=as_json)

    async def _action(svc: RunService):
        from hydra_orch.core.conflict_resolver import ConflictResolver

        return await ConflictResolver(svc.store).auto_repair(
            conflict_id,
            repair_command=parsed_cmd,
            max_repair_attempts=max_repair_attempts,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    res = _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda r: f"conflict={r.conflict_id} status={r.status} repaired={r.repaired}",
    )
    repaired = getattr(res, "repaired", res.get("repaired") if isinstance(res, dict) else None)
    status_val = getattr(res, "status", res.get("status") if isinstance(res, dict) else None)
    failures = getattr(res, "failures", res.get("failures") if isinstance(res, dict) else ()) or ()
    only_missing_repairer = (
        parsed_cmd is None
        and len(failures) == 1
        and (
            getattr(failures[0], "code", None)
            or (failures[0].get("code") if isinstance(failures[0], dict) else None)
        )
        == "repairer_missing"
    )
    if status_val == "failed" or (repaired is False and not only_missing_repairer):
        raise typer.Exit(code=1)


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


def _load_cli_config(svc: RunService):
    if _ACTIVE_CONFIG_PATH is not None:
        return load_config(_ACTIVE_CONFIG_PATH)
    env_cfg = os.environ.get("HYDRA_CONFIG", "").strip()
    if env_cfg:
        return load_config(Path(env_cfg).expanduser())
    cfg_path = svc.repo_root / "config.yaml"
    return load_config(cfg_path) if cfg_path.is_file() else load_config()


def _build_route_selector(svc: RunService):
    from hydra_orch.bridge.omniroute_client import OmniRouteClient
    from hydra_orch.core.agent_registry import AgentRegistry
    from hydra_orch.core.metrics import MetricsService
    from hydra_orch.core.route_selector import RouteSelector

    cfg = _load_cli_config(svc)
    gateway = OmniRouteClient(
        base_url=cfg.omniroute.base_url,
        quota_api_url=cfg.omniroute.quota_api_url,
        enabled=not cfg.is_direct_mode,
        api_key_env=cfg.omniroute.api_key_env,
    )
    return RouteSelector(
        svc.store,
        AgentRegistry(svc.store),
        MetricsService(svc.store),
        gateway=gateway,
        connection_mode=cfg.omniroute.connection_mode,
    )


def _build_scheduler_service(svc: RunService):
    from hydra_orch.core.scheduler import SchedulerService

    async def _dispatch(schedule, occurrence_key: str):
        if not schedule.project_id:
            raise ContractViolation(
                "automation_dispatch_unavailable",
                f"Schedule '{schedule.id}' requires project_id",
            )
        proj = await svc.get_project(schedule.project_id)
        if proj is None:
            raise ContractViolation(
                "automation_dispatch_unavailable",
                f"Registered project '{schedule.project_id}' was not found",
            )
        run_id = f"auto-{schedule.id[:8]}-{uuid.uuid4().hex[:8]}"
        task = TaskSpec(
            task_id="task-1",
            run_id=run_id,
            objective=schedule.prompt,
            acceptance_criteria=(CheckSpec(check_id="chk-auto", command=("python", "-c", "print('scheduled')")),),
            allowed_paths=("*",),
            assigned_executor=schedule.executor_id,
        )
        idem_key = f"auto:{occurrence_key}".replace(" ", "_")[:64].ljust(16, "_")
        spec = RunSpec(
            run_id=run_id,
            project_id=schedule.project_id,
            repo_root=str(proj["canonical_root"]),
            base_branch=str(proj.get("base_branch") or "main"),
            base_sha=str(proj["base_sha"]),
            objective=schedule.prompt,
            orchestration_mode="relay",
            tasks=(task,),
            idempotency_key=idem_key,
        )
        _, res = await svc.submit_run(spec)
        return {"run_id": str(res.get("run_id") or res.get("id") or run_id), "status": "dispatched"}

    return SchedulerService(svc.store, dispatcher=_dispatch)


@route_app.command("inventory")
def route_inventory(
    scope_id: str = typer.Option("default", "--scope-id", help="Target scope or run ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Inspect OmniRoute gateway availability, discovered models, quotas, and account overrides."""

    async def _action(svc: RunService):
        return await _build_route_selector(svc).gateway_inventory(scope_id=scope_id)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"mode={res['connection_mode']} available={res['available']} models={len(res['models'])} accounts={len(res['accounts'])}",
    )


@route_app.command("select-account")
def route_select_account(
    provider: str = typer.Option(..., "--provider", help="Provider identifier"),
    account_id: str = typer.Option(..., "--account-id", help="Non-secret account label/identifier for next runs"),
    scope_id: str = typer.Option("default", "--scope-id", help="Target scope or run ID"),
    principal_id: Optional[str] = typer.Option(None, "--principal-id", help="Acting operator ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Select an OmniRoute/provider account for future runs without mutating running attempts."""
    actor = _default_principal(principal_id)

    async def _action(svc: RunService):
        return await _build_route_selector(svc).select_next_account(
            scope_id,
            provider,
            account_id,
            principal_id=actor,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"provider={res['provider']} account={res['account_id']} applies_to={res['applies_to']}",
    )


@automation_app.command("list")
def automation_list(
    workspace_id: Optional[str] = typer.Option(None, "--workspace-id", help="Filter by workspace ID"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Filter by project ID"),
    enabled: Optional[bool] = typer.Option(None, "--enabled/--disabled", help="Filter by enabled status"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List persisted automation schedules."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).list_schedules(
            workspace_id=workspace_id,
            project_id=project_id,
            enabled=enabled,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"schedules={len(res)}",
    )


@automation_app.command("create")
def automation_create(
    name: str = typer.Option(..., "--name", help="Schedule name"),
    prompt: str = typer.Option(..., "--prompt", help="Automation objective/prompt"),
    cron_expr: Optional[str] = typer.Option(None, "--cron", help="5-field cron expression"),
    interval_seconds: Optional[int] = typer.Option(None, "--interval-seconds", help="Interval in seconds (>=60)"),
    timezone_name: str = typer.Option("UTC", "--timezone", help="IANA timezone identifier"),
    workspace_id: Optional[str] = typer.Option(None, "--workspace-id", help="Optional workspace ID"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Optional registered project ID"),
    target_host: str = typer.Option("local", "--target-host", help="Target host identifier"),
    executor_id: str = typer.Option("codex", "--executor", help="Executor ID"),
    overlap_policy: str = typer.Option("skip", "--overlap-policy", help="skip | queue | allow"),
    missed_policy: str = typer.Option("skip", "--missed-policy", help="skip | run_once"),
    max_retries: int = typer.Option(0, "--max-retries", help="Max retries (0..5)"),
    disabled: bool = typer.Option(False, "--disabled", help="Create schedule initially disabled"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Create a durable automation schedule."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).create_schedule(
            name,
            prompt,
            cron_expr=cron_expr,
            interval_seconds=interval_seconds,
            timezone=timezone_name,
            workspace_id=workspace_id,
            project_id=project_id,
            target_host=target_host,
            executor_id=executor_id,
            enabled=not disabled,
            overlap_policy=overlap_policy,  # type: ignore[arg-type]
            missed_policy=missed_policy,  # type: ignore[arg-type]
            max_retries=max_retries,
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"schedule={res.id} enabled={res.enabled} tz={res.timezone} next={res.next_run_at}",
    )


@automation_app.command("pause")
def automation_pause(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    expected_revision: Optional[int] = typer.Option(None, "--expected-revision", help="Expected revision"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Pause an automation schedule."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).set_enabled(
            schedule_id, False, expected_revision=expected_revision
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"schedule={res.id} enabled={res.enabled}",
    )


@automation_app.command("resume")
def automation_resume(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    expected_revision: Optional[int] = typer.Option(None, "--expected-revision", help="Expected revision"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Resume a paused automation schedule."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).set_enabled(
            schedule_id, True, expected_revision=expected_revision
        )

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"schedule={res.id} enabled={res.enabled}",
    )


@automation_app.command("trigger")
def automation_trigger(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Trigger an automation schedule immediately."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).trigger_now(schedule_id)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"schedule={schedule_id} status={res.get('status')} run_id={res.get('run_id') or res.get('id')}",
    )


@automation_app.command("history")
def automation_history(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    limit: int = typer.Option(50, "--limit", help="Maximum records"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Inspect run dispatch history for an automation schedule."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).list_runs(schedule_id, limit=limit)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"schedule={schedule_id} runs={len(res)}",
    )


@automation_app.command("tick")
def automation_tick(
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Evaluate due automation schedules idempotently."""

    async def _action(svc: RunService):
        return await _build_scheduler_service(svc).tick()

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"dispatches={len(res)}",
    )


@automation_app.command("delete")
def automation_delete(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Delete an automation schedule."""

    async def _action(svc: RunService):
        await _build_scheduler_service(svc).delete_schedule(schedule_id)
        return {"deleted": True, "schedule_id": schedule_id}

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"deleted={res['schedule_id']}",
    )


async def _fallback_apply_conversation_changes(
    svc: RunService,
    conversation_id: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Fallback 3-way conversation sync when ConversationService.apply_changes is not yet wired."""
    from hydra_orch.core.conversation_service import ConversationService
    from hydra_orch.core.folder_workspace import files as list_folder_files

    conv_svc = ConversationService(svc)
    conv = await conv_svc.snapshot(conversation_id)
    proj = await svc.get_project(conv["project_id"])
    if proj is None:
        raise ContractViolation("project_not_found", "Projeto da conversa não encontrado.")
    source_root = Path(proj["canonical_root"]).resolve()
    ws_path_raw = conv.get("workspace_path")
    if not ws_path_raw:
        return {"conversation_id": conversation_id, "applied": False, "changed_files": [], "conflicts": []}

    kind = proj.get("workspace_kind", "git")
    if kind == "folder":
        work_dir = Path(ws_path_raw).resolve()
        base_dir = work_dir.parent / "base"
        if not work_dir.is_dir() or not base_dir.is_dir():
            raise ContractViolation("workspace_missing", "A cópia isolada desta conversa não está disponível.")
        base_files = set(list_folder_files(base_dir))
        work_files = set(list_folder_files(work_dir))
        source_files = set(list_folder_files(source_root))
        all_rel = sorted(base_files | work_files | source_files)
        conflicts: List[str] = []
        to_write: List[Path] = []
        to_delete: List[Path] = []
        for rel in all_rel:
            b_bytes = (base_dir / rel).read_bytes() if rel in base_files else None
            w_bytes = (work_dir / rel).read_bytes() if rel in work_files else None
            s_bytes = (source_root / rel).read_bytes() if rel in source_files else None
            if w_bytes == b_bytes:
                continue
            if s_bytes != b_bytes and s_bytes != w_bytes:
                conflicts.append(rel.as_posix())
                if not force:
                    continue
            if w_bytes is None:
                to_delete.append(rel)
            else:
                to_write.append(rel)
        if conflicts and not force:
            raise ContractViolation(
                "conversation_apply_conflict",
                f"Arquivos editados externamente no projeto original: {', '.join(conflicts)}",
            )
        applied_files: List[str] = []
        for rel in to_write:
            dst = source_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work_dir / rel, dst, follow_symlinks=False)
            base_dst = base_dir / rel
            base_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work_dir / rel, base_dst, follow_symlinks=False)
            applied_files.append(rel.as_posix())
        for rel in to_delete:
            dst = source_root / rel
            if dst.is_file():
                dst.unlink()
            base_dst = base_dir / rel
            if base_dst.is_file():
                base_dst.unlink()
            applied_files.append(rel.as_posix())
        return {
            "conversation_id": conversation_id,
            "applied": True,
            "workspace_kind": "folder",
            "changed_files": applied_files,
            "conflicts": conflicts,
        }

    ws = svc._get_git_workspace(source_root)
    work_dir = Path(ws_path_raw).resolve()
    status_out = ws._run_git(["status", "--porcelain"], cwd=work_dir).stdout.strip()
    if status_out:
        ws._run_git(["add", "--all", "--", "."], cwd=work_dir)
        ws._run_git(
            ["-c", "user.name=Hydra", "-c", "user.email=hydra@localhost", "commit", "-m", f"feat(chat): apply {conversation_id}"],
            cwd=work_dir,
        )
    head_sha = ws.resolve_commit_sha("HEAD" if not work_dir.exists() else ws._run_git(["rev-parse", "HEAD"], cwd=work_dir).stdout.strip())
    merge_args = ["merge", "--ff-only", head_sha] if not force else ["merge", "--no-edit", head_sha]
    proc = ws._run_git(merge_args, cwd=source_root, check=False)
    if proc.returncode != 0:
        raise ContractViolation("conversation_apply_conflict", redact_text(proc.stderr.strip() or "Merge conflict applying conversation"))
    return {
        "conversation_id": conversation_id,
        "applied": True,
        "workspace_kind": "git",
        "result_sha": head_sha,
    }


@conversation_app.command("list")
def conversation_list(
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Filter by project ID"),
    limit: int = typer.Option(30, "--limit", help="Maximum conversations to return"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Optional title filter"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Optional remote Control Plane base URL"),
    api_token_env: str = typer.Option("HYDRA_API_TOKEN", "--api-token-env", help="Env var holding Bearer token"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """List persisted conversations."""
    if api_url is not None:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if project_id:
            params["project_id"] = project_id
        if query:
            params["q"] = query
        try:
            res = asyncio.run(
                _cli_http_request(
                    "GET",
                    api_url,
                    "/v1/control-plane/conversations",
                    api_token_env=api_token_env,
                    params=params,
                )
            )
        except Exception as exc:
            _handle_cli_exception(exc, as_json=as_json)
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=f"conversations={len(res.get('items', []))} total={res.get('total', 0)}",
        )
        return

    async def _action(svc: RunService):
        from hydra_orch.core.conversation_service import ConversationService

        return await ConversationService(svc).list(project_id=project_id, offset=offset, limit=limit, q=query)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: f"conversations={len(res.get('items', []))} total={res.get('total', 0)}",
    )


@conversation_app.command("apply")
def conversation_apply(
    conversation_id: str = typer.Argument(..., help="Conversation ID whose isolated edits should be applied"),
    force: bool = typer.Option(False, "--force", help="Force apply even when source files changed externally"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Optional remote Control Plane base URL"),
    api_token_env: str = typer.Option("HYDRA_API_TOKEN", "--api-token-env", help="Env var holding Bearer token"),
    as_json: bool = typer.Option(False, "--json", help="Emit structured JSON output"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON output to file"),
) -> None:
    """Apply isolated conversation changes back to the original folder or Git project."""
    if api_url is not None:
        try:
            res = asyncio.run(
                _cli_http_request(
                    "POST",
                    api_url,
                    f"/v1/control-plane/conversations/{conversation_id}/apply",
                    api_token_env=api_token_env,
                    json_body={"force": force},
                )
            )
        except Exception as exc:
            _handle_cli_exception(exc, as_json=as_json)
        cid = res.get("conversation_id") or res.get("id") or conversation_id
        _emit_output(
            res,
            as_json=as_json,
            output_file=output,
            summary_text=f"conversation={cid} applied={res.get('applied', True)}",
        )
        return

    async def _action(svc: RunService):
        from hydra_orch.core.conversation_service import ConversationService

        conv_svc = ConversationService(svc)
        if hasattr(conv_svc, "apply_changes"):
            return await conv_svc.apply_changes(conversation_id, force=force)
        return await _fallback_apply_conversation_changes(svc, conversation_id, force=force)

    _run_cli_action(
        _action,
        as_json=as_json,
        output_file=output,
        render_summary=lambda res: (
            f"conversation={res.get('conversation_id') or res.get('id') or conversation_id} "
            f"applied={res.get('applied', True)}"
        ),
    )


@app.command("watch")
def watch(
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Target run ID to watch (defaults to latest run)"
    ),
    api_url: Optional[str] = typer.Option(
        None, "--api-url", help="Remote Hydra REST/SSE base URL (Bearer token from env or prompt)"
    ),
    api_token_env: str = typer.Option(
        "HYDRA_API_TOKEN", "--api-token-env", help="Environment variable holding Bearer token for --api-url"
    ),
    refresh_seconds: float = typer.Option(
        2.0, "--refresh-seconds", help="Live refresh polling interval in seconds"
    ),
    once: bool = typer.Option(False, "--once", help="Render one snapshot and exit"),
    script: Optional[Path] = typer.Option(
        None, "--script", help="Path to deterministic line-command script file"
    ),
    no_alt_screen: bool = typer.Option(
        False, "--no-alt-screen", help="Render directly without alternate screen buffer"
    ),
    max_steps: Optional[int] = typer.Option(
        None, "--max-steps", help="Maximum interactive/scripted steps before exit"
    ),
    principal_id: Optional[str] = typer.Option(
        None, "--principal-id", help="Operator principal ID recorded on governance actions"
    ),
) -> None:
    """Launch the live orchestration cockpit watching runs, tasks, HITL, routes, and PR gates."""
    _launch_tui(
        run_id=run_id,
        api_url=api_url,
        api_token_env=api_token_env,
        refresh_seconds=refresh_seconds,
        once=once,
        script=script,
        no_alt_screen=no_alt_screen,
        max_steps=max_steps,
        principal_id=principal_id,
    )


@app.command("ui")
def ui(
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Target run ID to open (defaults to latest run)"
    ),
    api_url: Optional[str] = typer.Option(
        None, "--api-url", help="Remote Hydra REST/SSE base URL (Bearer token from env or prompt)"
    ),
    api_token_env: str = typer.Option(
        "HYDRA_API_TOKEN", "--api-token-env", help="Environment variable holding Bearer token for --api-url"
    ),
    refresh_seconds: float = typer.Option(
        2.0, "--refresh-seconds", help="Live refresh polling interval in seconds"
    ),
    once: bool = typer.Option(False, "--once", help="Render one snapshot and exit"),
    script: Optional[Path] = typer.Option(
        None, "--script", help="Path to deterministic line-command script file"
    ),
    no_alt_screen: bool = typer.Option(
        False, "--no-alt-screen", help="Render directly without alternate screen buffer"
    ),
    max_steps: Optional[int] = typer.Option(
        None, "--max-steps", help="Maximum interactive/scripted steps before exit"
    ),
    principal_id: Optional[str] = typer.Option(
        None, "--principal-id", help="Operator principal ID recorded on governance actions"
    ),
) -> None:
    """Shortcut alias launching the interactive orchestration cockpit."""
    _launch_tui(
        run_id=run_id,
        api_url=api_url,
        api_token_env=api_token_env,
        refresh_seconds=refresh_seconds,
        once=once,
        script=script,
        no_alt_screen=no_alt_screen,
        max_steps=max_steps,
        principal_id=principal_id,
    )


if __name__ == "__main__":
    app()
