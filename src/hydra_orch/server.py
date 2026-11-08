"""FastAPI OpenAI-compatible proxy and M1 Control Plane server for hydra-orch (T01 / T07)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Sequence
import uuid

from fastapi import APIRouter, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hydra_orch.config import ConfigError, HydraConfig, load_config
from hydra_orch.core.checkpointer import (
    IdempotencyConflictError,
    OptimisticLockError,
    StorageError,
    StorageIntegrityError,
    StorageLockError,
)
from hydra_orch.core.git_workspace import GitWorkspaceError
from hydra_orch.core.router import HydraRouter
from hydra_orch.core.run_service import RunService
from hydra_orch.core.ssh_tunnel import SshTunnelManager
from hydra_orch.model import (
    BudgetPolicy,
    ChatChoice,
    ChatChoiceDelta,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CheckSpec,
    ContractViolation,
    IntegrationStatus,
    ModelCard,
    ModelListResponse,
    RunSpec,
    TaskSpec,
)

logger = logging.getLogger(__name__)

DEFAULT_CORS_ALLOW_ORIGINS: List[str] = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

config = load_config()
router = HydraRouter(config)
ssh_manager: SshTunnelManager | None = None
ssh_remote = config.remote_ssh_gpu
if ssh_remote.enabled:
    ssh_manager = SshTunnelManager(ssh_remote.model_dump())

_run_service: Optional[RunService] = None


def get_run_service() -> RunService:
    """Return the shared canonical RunService instance used by both API and CLI."""
    global _run_service
    if _run_service is None:
        repo_root = Path.cwd()
        _run_service = RunService(
            repo_root=repo_root,
            store=router.checkpointer,
        )
    return _run_service


def set_run_service(service: Optional[RunService]) -> None:
    """Override the shared RunService instance (for dependency injection and hermetic tests)."""
    global _run_service
    _run_service = service


async def startup_event() -> None:
    await router.ensure_gateway()
    await router.checkpointer.initialize()
    if ssh_manager:
        ssh_manager.start_tunnel()
    logger.info("Hydra Orchestrator server started successfully.")


def shutdown_event() -> None:
    if ssh_manager:
        ssh_manager.stop_tunnel()
    logger.info("Hydra Orchestrator server stopped.")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await startup_event()
    try:
        yield
    finally:
        shutdown_event()


app = FastAPI(
    title=config.server.title,
    description=config.server.description,
    version="0.1.0",
    lifespan=_lifespan,
)

app.state.cors_allow_origins = list(DEFAULT_CORS_ALLOW_ORIGINS)
app.state.api_token = os.environ.get("HYDRA_API_TOKEN")
app.state.require_auth = False
app.state.expired_cursors = {}  # run_id -> min_valid_seq

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEFAULT_CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    run_id: Optional[str] = None,
    retryable: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    payload: Dict[str, Any] = {
        "code": code,
        "message": message,
        "run_id": run_id,
        "retryable": retryable,
    }
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _check_control_plane_security(request: Request) -> Optional[JSONResponse]:
    """Enforce strict CORS origin allowlist and local loopback / Bearer token authentication."""
    origin = request.headers.get("origin")
    allowed_origins = getattr(app.state, "cors_allow_origins", DEFAULT_CORS_ALLOW_ORIGINS)
    if origin is not None:
        if origin.strip() == "*" or origin not in allowed_origins:
            return _error_response(
                403,
                "cors_origin_forbidden",
                f"Origin '{origin}' is not in the strict local CORS allowlist",
                retryable=False,
            )

    expected_token = getattr(app.state, "api_token", None) or os.environ.get("HYDRA_API_TOKEN")
    require_auth = bool(getattr(app.state, "require_auth", False)) or bool(expected_token)
    client_host = request.client.host if request.client else "127.0.0.1"

    if not require_auth and client_host not in _LOOPBACK_HOSTS:
        require_auth = True

    if require_auth:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return _error_response(
                401,
                "unauthorized",
                "Local Bearer token is required in Authorization header",
                retryable=False,
            )
        provided_token = auth_header[7:].strip()
        if not expected_token or not hmac.compare_digest(provided_token, str(expected_token)):
            return _error_response(
                401,
                "unauthorized",
                "Invalid local Bearer token",
                retryable=False,
            )
    return None


@app.middleware("http")
async def control_plane_security_middleware(request: Request, call_next: Any) -> Any:
    path = request.url.path
    if path.startswith("/v1/control-plane") or path in {"/projects", "/runs"} or path.startswith("/runs/"):
        sec_err = _check_control_plane_security(request)
        if sec_err is not None:
            return sec_err
    return await call_next(request)


# ============================================================================
# REQUEST / RESPONSE SCHEMAS FOR M1 CONTROL PLANE (T07)
# ============================================================================

class ProjectCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_root: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    base_branch: str = Field(default="main", min_length=1)
    base_sha: Optional[str] = Field(default=None)
    project_id: Optional[str] = Field(default=None)


class TaskSpecPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default="task-1", min_length=1)
    objective: str = Field(min_length=1, max_length=5000)
    acceptance_criteria: List[CheckSpec] = Field(min_length=1)
    allowed_paths: List[str] = Field(default_factory=lambda: ["*"])
    dependencies: List[str] = Field(default_factory=list)
    assigned_executor: str = Field(default="codex", min_length=1)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_repair_attempts: int = Field(default=2, ge=0, le=5)


class BudgetPolicyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)
    max_parallel_tasks: int = Field(default=2, ge=1)
    max_wall_seconds: int = Field(default=3600, ge=1)
    max_tokens_in: Optional[int] = Field(default=None, ge=0)
    max_tokens_out: Optional[int] = Field(default=None, ge=0)
    max_usd: Optional[float] = Field(default=None, ge=0.0)
    alert_threshold_pct: float = Field(default=80.0, ge=50.0, le=99.0)


class RunCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: Optional[str] = Field(default=None)
    project_id: str = Field(min_length=1)
    repo_root: Optional[str] = Field(default=None)
    base_branch: str = Field(default="main", min_length=1)
    base_sha: Optional[str] = Field(default=None)
    objective: str = Field(min_length=1, max_length=5000)
    mode: Literal["swarm", "relay", "persistent"] = "relay"
    orchestration_mode: Optional[Literal["swarm", "relay", "persistent"]] = None
    task_spec: Optional[TaskSpecPayload] = None
    tasks: Optional[List[TaskSpecPayload]] = None
    budget: Optional[BudgetPolicyPayload] = None
    profile_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=128)
    execute: bool = False
    dry_run: bool = False
    custom_command: Optional[List[str]] = None


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=1)
    actor: str = Field(default="operator", min_length=1)
    result_id: Optional[str] = None
    expected_task_revision: Optional[int] = None


class CancelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["run", "task", "attempt"] = "run"
    task_id: Optional[str] = None
    attempt_id: Optional[str] = None
    reason: str = Field(default="operator_cancelled", min_length=1)


class RetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_reconciliation: bool = False
    prompt: Optional[str] = None
    provider: str = "local_cli"
    model: str = "default"
    custom_command: Optional[List[str]] = None
    extra_args: List[str] = Field(default_factory=list)


class IntegratePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
    target_branch: Optional[str] = None
    cleanup_on_success: bool = True


class DiscardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False


# ============================================================================
# HEALTH, MODELS, AND INFERENCE ROUTES
# ============================================================================

@app.get("/health")
@app.get("/v1/health")
async def health_check() -> Dict[str, Any]:
    adapter_statuses = {name: ad.get_status() for name, ad in router.adapters.items()}
    return {
        "status": "healthy",
        "default_mode": config.orchestrator.default_mode,
        "adapters": adapter_statuses,
    }


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    base_models = [
        "hydra-default",
        "hydra-relay",
        "hydra-persistent",
    ]
    adapter_names = router.list_available_adapters()
    all_models = [ModelCard(id=m) for m in base_models + adapter_names]
    return ModelListResponse(data=all_models)


@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest) -> Any:
    if request.model == "hydra-swarm":
        request.mode = "swarm"
    elif request.model == "hydra-relay":
        request.mode = "relay"
    elif request.model == "hydra-persistent":
        request.mode = "persistent"

    router.validate_request(request)
    await router.ensure_gateway()

    if request.stream:
        async def event_generator() -> AsyncIterator[str]:
            stream_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            async for chunk in router.stream_chat_completion(request):
                chunk_obj = ChatCompletionChunk(
                    id=stream_id,
                    model=request.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatChoiceDelta(content=chunk),
                            finish_reason=None,
                        )
                    ],
                )
                yield f"data: {chunk_obj.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    collected_text = []
    async for chunk in router.stream_chat_completion(request):
        collected_text.append(chunk)

    full_content = "".join(collected_text)
    return ChatCompletionResponse(
        model=request.model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=full_content),
                finish_reason="stop",
            )
        ],
    )


@app.get("/v1/orchestrator/status")
async def orchestrator_status() -> Dict[str, Any]:
    return {
        "default_mode": config.orchestrator.default_mode,
        "worktrees_dir": config.swarm.worktrees_dir,
        "adapters_count": len(router.adapters),
        "adapters": [ad.get_status() for ad in router.adapters.values()],
        "ssh_tunnel_active": ssh_manager.is_running() if ssh_manager else False,
    }


@app.get("/v1/quota")
async def quota_status() -> Dict[str, Any]:
    from hydra_orch.bridge.omniroute_client import OmniRouteClient

    client = OmniRouteClient(
        base_url=config.omniroute.base_url,
        quota_api_url=config.omniroute.quota_api_url,
        enabled=not config.is_direct_mode,
    )
    return await client.get_quota_status()


# ============================================================================
# CONTROL PLANE ROUTES (/v1/control-plane/*)
# ============================================================================


@app.get("/v1/control-plane/bootstrap")
async def control_plane_bootstrap() -> Dict[str, Any]:
    """Expose non-secret capability metadata for visual and CLI clients."""
    ui = config.visual_interface
    return {
        "api_version": "v1",
        "product": "hydra-orch",
        "ui": {
            "enabled": ui.enabled,
            "host": ui.host,
            "port": ui.port,
            "api_base_path": ui.api_base_path,
            "features": {
                "projects": ui.expose_projects,
                "runs": ui.expose_runs,
                "worktrees": ui.expose_worktrees,
                "diffs": ui.expose_diffs,
                "quota": ui.expose_quota,
            },
        },
        "integrations": {
            "omniroute": {
                "enabled": config.omniroute.enabled,
                "connection_mode": config.omniroute.connection_mode,
                "configured": bool(config.omniroute.base_url),
            },
            "ssh_gpu": {"enabled": config.remote_ssh_gpu.enabled},
        },
        "implemented_read_models": {
            "health": True,
            "models": True,
            "orchestrator_status": True,
            "quota": True,
            "projects": True,
            "runs": True,
            "worktrees": True,
            "diffs": True,
        },
    }


@app.post("/v1/control-plane/projects", status_code=201)
@app.post("/projects", status_code=201)
async def create_project_endpoint(payload: ProjectCreatePayload) -> Dict[str, Any]:
    svc = get_run_service()
    return await svc.create_project(
        canonical_root=payload.canonical_root,
        name=payload.name,
        base_branch=payload.base_branch,
        base_sha=payload.base_sha,
        project_id=payload.project_id,
    )


@app.get("/v1/control-plane/projects")
@app.get("/projects")
async def list_projects_endpoint() -> List[Dict[str, Any]]:
    svc = get_run_service()
    return await svc.list_projects()


@app.get("/v1/control-plane/projects/{project_id}")
@app.get("/projects/{project_id}")
async def get_project_endpoint(project_id: str) -> Any:
    svc = get_run_service()
    proj = await svc.get_project(project_id)
    if proj is None:
        return _error_response(404, "project_not_found", f"Project '{project_id}' not found")
    return proj


@app.post("/v1/control-plane/runs", status_code=202)
@app.post("/runs", status_code=202)
async def create_run_endpoint(
    payload: RunCreatePayload,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    svc = get_run_service()

    if idempotency_key_header and payload.idempotency_key and idempotency_key_header != payload.idempotency_key:
        return _error_response(
            400,
            "idempotency_key_mismatch",
            "Header Idempotency-Key does not match body idempotency_key",
        )
    idem_key = (idempotency_key_header or payload.idempotency_key or "").strip()
    if not idem_key:
        return _error_response(
            400,
            "missing_idempotency_key",
            "Idempotency-Key header or idempotency_key field is required",
        )

    # Resolve project and repository root
    proj = await svc.get_project(payload.project_id)
    repo_root = payload.repo_root or (proj["canonical_root"] if proj else str(svc.repo_root))
    base_branch = payload.base_branch or (proj["base_branch"] if proj else "main")
    base_sha = payload.base_sha or (proj["base_sha"] if proj else None)
    if not base_sha:
        ws = svc._get_git_workspace(repo_root)
        try:
            base_sha = ws.resolve_commit_sha(base_branch)
        except (ContractViolation, GitWorkspaceError):
            base_sha = ws.resolve_commit_sha("HEAD")

    raw_tasks = payload.tasks if payload.tasks is not None else ([payload.task_spec] if payload.task_spec else [])
    if not raw_tasks:
        return _error_response(400, "missing_tasks", "At least one task_spec or tasks entry is required")

    default_driver = config.execution.driver if hasattr(config, "execution") else "codex"
    chosen_mode = payload.orchestration_mode or payload.mode
    run_id = payload.run_id or f"run-{uuid.uuid4().hex[:12]}"

    bp_in = payload.budget
    budget_policy = (
        BudgetPolicy(
            max_attempts=bp_in.max_attempts,
            max_parallel_tasks=bp_in.max_parallel_tasks,
            max_wall_seconds=bp_in.max_wall_seconds,
            max_tokens_in=bp_in.max_tokens_in,
            max_tokens_out=bp_in.max_tokens_out,
            max_usd=bp_in.max_usd,
            alert_threshold_pct=bp_in.alert_threshold_pct,
        )
        if bp_in is not None
        else BudgetPolicy()
    )

    task_specs: List[TaskSpec] = []
    semantic_tasks: List[Dict[str, Any]] = []
    for idx, t_item in enumerate(raw_tasks, start=1):
        assert t_item is not None
        tid = t_item.task_id if t_item.task_id != "task-1" or idx == 1 else f"task-{idx}"
        exec_id = t_item.assigned_executor or default_driver
        task_specs.append(
            TaskSpec(
                task_id=tid,
                run_id=run_id,
                objective=t_item.objective,
                allowed_paths=tuple(t_item.allowed_paths),
                acceptance_criteria=tuple(t_item.acceptance_criteria),
                dependencies=tuple(t_item.dependencies),
                assigned_executor=exec_id,
                timeout_seconds=t_item.timeout_seconds,
            )
        )
        semantic_tasks.append(
            {
                "task_id": tid,
                "objective": t_item.objective,
                "allowed_paths": list(t_item.allowed_paths),
                "acceptance_criteria": [c.model_dump(mode="json") for c in t_item.acceptance_criteria],
                "dependencies": list(t_item.dependencies),
                "assigned_executor": exec_id,
                "timeout_seconds": t_item.timeout_seconds,
            }
        )

    # Compute request hash over the semantic request content (independent of auto-generated run_id)
    semantic_payload = {
        "project_id": payload.project_id,
        "repo_root": str(Path(os.path.realpath(repo_root))),
        "base_sha": base_sha,
        "objective": payload.objective,
        "mode": chosen_mode,
        "tasks": semantic_tasks,
        "budget": budget_policy.model_dump(mode="json"),
    }
    request_hash = svc.store.compute_request_hash(semantic_payload)

    run_spec = RunSpec(
        run_id=run_id,
        project_id=payload.project_id,
        repo_root=str(Path(os.path.realpath(repo_root))),
        base_branch=base_branch,
        base_sha=base_sha,
        objective=payload.objective,
        orchestration_mode=chosen_mode,
        tasks=tuple(task_specs),
        budget_policy=budget_policy,
        idempotency_key=idem_key,
    )

    created, run_rec = await svc.submit_run(run_spec, request_hash=request_hash)

    if created and payload.execute:
        for t_spec in run_spec.tasks:
            await svc.execute_task_attempt(
                run_id=run_rec["id"],
                task_id=t_spec.task_id,
                dry_run=payload.dry_run,
                custom_command=payload.custom_command,
            )
        refreshed = await svc.store.get_run(run_rec["id"])
        if refreshed is not None:
            run_rec = refreshed

    return {
        "run_id": run_rec["id"],
        "status": run_rec["status"],
        "revision": int(run_rec["revision"]),
        "created": created,
        "created_at": run_rec["created_at"],
    }


@app.get("/v1/control-plane/runs")
@app.get("/runs")
async def list_runs_endpoint(
    project_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    svc = get_run_service()
    return await svc.list_runs(project_id=project_id, status=status, page=page, size=size)


@app.get("/v1/control-plane/runs/{run_id}")
@app.get("/runs/{run_id}")
async def get_run_endpoint(run_id: str) -> Any:
    svc = get_run_service()
    detail = await svc.get_run_detail(run_id)
    if detail is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)
    return detail


@app.get("/v1/control-plane/runs/{run_id}/tasks")
@app.get("/runs/{run_id}/tasks")
async def list_run_tasks_endpoint(run_id: str) -> Any:
    svc = get_run_service()
    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)
    return await svc.list_run_tasks(run_id)


@app.get("/v1/control-plane/runs/{run_id}/artifacts")
@app.get("/runs/{run_id}/artifacts")
async def list_run_artifacts_endpoint(
    run_id: str,
    kind: Optional[str] = Query(default=None),
) -> Any:
    svc = get_run_service()
    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)
    artifacts = await svc.store.get_artifacts(run_id, kind=kind)
    return [
        {
            "id": a.artifact_id,
            "artifact_id": a.artifact_id,
            "run_id": a.run_id,
            "attempt_id": a.attempt_id,
            "relative_path": a.relative_path,
            "kind": a.kind,
            "sha256": a.sha256,
            "size_bytes": a.size_bytes,
            "created_at": run_rec["created_at"],
        }
        for a in artifacts
    ]


@app.get("/v1/control-plane/runs/{run_id}/events")
@app.get("/runs/{run_id}/events")
async def stream_run_events_endpoint(
    run_id: str,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    after_seq: Optional[int] = Query(default=None, ge=0),
) -> Any:
    svc = get_run_service()
    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)

    cursor_seq = after_seq or 0
    if last_event_id is not None and last_event_id.strip() != "":
        try:
            cursor_seq = int(last_event_id.strip())
        except ValueError:
            return _error_response(
                400,
                "invalid_cursor",
                f"Invalid Last-Event-ID header value: '{last_event_id}'",
                run_id=run_id,
            )
        if cursor_seq < 0:
            return _error_response(
                410,
                "cursor_expired",
                f"Cursor {cursor_seq} has expired; fetch full run snapshot",
                run_id=run_id,
            )

    expired_map: Dict[str, int] = getattr(app.state, "expired_cursors", {})
    min_valid_seq = expired_map.get(run_id, 0)
    if cursor_seq > 0 and cursor_seq < min_valid_seq:
        return _error_response(
            410,
            "cursor_expired",
            f"Cursor {cursor_seq} is older than minimum retained sequence {min_valid_seq}; fetch full run snapshot",
            run_id=run_id,
        )

    events = await svc.store.get_events(run_id, after_seq=cursor_seq)

    async def sse_generator() -> AsyncIterator[str]:
        for ev in events:
            payload_obj = {
                "run_id": ev.run_id,
                "seq": ev.seq,
                "type": ev.event_type,
                "correlation_id": ev.correlation_id,
                "task_id": ev.task_id,
                "attempt_id": ev.attempt_id,
                "payload": ev.redacted_payload,
                "timestamp": ev.timestamp.isoformat(),
            }
            yield (
                f"id: {ev.seq}\n"
                f"event: {ev.event_type}\n"
                f"retry: 15000\n"
                f"data: {json.dumps(payload_obj, sort_keys=True)}\n\n"
            )
        heartbeat_obj = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        yield f"event: heartbeat\ndata: {json.dumps(heartbeat_obj)}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.post("/v1/control-plane/runs/{run_id}/cancel")
@app.post("/runs/{run_id}/cancel")
async def cancel_run_endpoint(
    run_id: str,
    payload: Optional[CancelPayload] = None,
) -> Any:
    svc = get_run_service()
    req = payload or CancelPayload()

    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)

    if req.scope == "task":
        if not req.task_id:
            return _error_response(400, "missing_task_id", "task_id is required when scope='task'", run_id=run_id)
        task_rec = await svc.store.get_task(req.task_id)
        if task_rec is None or task_rec["run_id"] != run_id:
            return _error_response(
                404,
                "task_not_found",
                f"Task '{req.task_id}' not found in run '{run_id}'",
                run_id=run_id,
            )
        updated_task = await svc.cancel_task(run_id, req.task_id, reason=req.reason)
        return {
            "status": "cancelled",
            "scope": "task",
            "run_id": run_id,
            "task_id": req.task_id,
            "task_status": updated_task["status"],
            "message": f"Task '{req.task_id}' cancelled",
            "killed_pids": [],
        }

    updated_run = await svc.cancel_run(run_id, reason=req.reason)
    return {
        "status": "cancelled",
        "scope": "run",
        "run_id": run_id,
        "run_status": updated_run["status"],
        "message": f"Run '{run_id}' cancelled",
        "killed_pids": [],
    }


@app.post("/v1/control-plane/runs/{run_id}/tasks/{task_id}/retry")
@app.post("/runs/{run_id}/tasks/{task_id}/retry")
async def retry_task_endpoint(
    run_id: str,
    task_id: str,
    payload: Optional[RetryPayload] = None,
) -> Any:
    svc = get_run_service()
    req = payload or RetryPayload()

    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)

    task_rec = await svc.store.get_task(task_id)
    if task_rec is None or task_rec["run_id"] != run_id:
        return _error_response(404, "task_not_found", f"Task '{task_id}' not found in run '{run_id}'", run_id=run_id)

    if req.force_reconciliation:
        await svc.store.reconcile_interrupted_attempts(run_id=run_id)

    outcome = await svc.retry_task(
        run_id=run_id,
        task_id=task_id,
        prompt=req.prompt,
        provider=req.provider,
        model=req.model,
        custom_command=req.custom_command,
        extra_args=req.extra_args,
    )
    return {
        "attempt_id": outcome.attempt.attempt_id,
        "result_id": outcome.result.result_id,
        "task_id": task_id,
        "run_id": run_id,
        "ordinal": outcome.attempt.ordinal,
        "status": outcome.attempt.process_status.value,
        "task_status": outcome.result.task_status.value,
    }


@app.post("/v1/control-plane/runs/{run_id}/tasks/{task_id}/review")
@app.post("/runs/{run_id}/tasks/{task_id}/review")
async def review_task_endpoint(
    run_id: str,
    task_id: str,
    payload: ReviewPayload,
) -> Any:
    svc = get_run_service()
    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)

    task_rec = await svc.store.get_task(task_id)
    if task_rec is None or task_rec["run_id"] != run_id:
        return _error_response(404, "task_not_found", f"Task '{task_id}' not found in run '{run_id}'", run_id=run_id)

    result_id = payload.result_id
    if not result_id:
        attempts = await svc.store.list_attempts(task_id)
        if not attempts:
            return _error_response(
                404,
                "result_not_found",
                f"Task '{task_id}' has no attempts to review",
                run_id=run_id,
            )
        latest_res = await svc.store.get_result_by_attempt(attempts[-1].attempt_id)
        if latest_res is None:
            return _error_response(
                404,
                "result_not_found",
                f"Task '{task_id}' attempt '{attempts[-1].attempt_id}' has no result",
                run_id=run_id,
            )
        result_id = latest_res.result_id

    reviewed = await svc.review_task_result(
        run_id=run_id,
        result_id=result_id,
        actor=payload.actor,
        decision=payload.decision,
        reason=payload.reason,
        expected_revision=payload.expected_revision,
        expected_task_revision=payload.expected_task_revision,
    )
    return {
        "review_id": f"rev-{reviewed.result_id}-{reviewed.revision}",
        "result_id": reviewed.result_id,
        "task_id": task_id,
        "run_id": run_id,
        "decision": payload.decision,
        "task_status": reviewed.task_status.value,
        "revision": reviewed.revision,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/control-plane/runs/{run_id}/integrate")
@app.post("/runs/{run_id}/integrate")
async def integrate_run_endpoint(
    run_id: str,
    payload: Optional[IntegratePayload] = None,
) -> Any:
    svc = get_run_service()
    req = payload or IntegratePayload()

    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)

    outcome = await svc.integrate_run(
        run_id=run_id,
        target_branch=req.target_branch,
        cleanup_on_success=req.cleanup_on_success,
    )
    if outcome.status == IntegrationStatus.CONFLICTED:
        return _error_response(
            422,
            "merge_conflict",
            f"Merge conflict while integrating run '{run_id}'",
            run_id=run_id,
            retryable=True,
            extra={
                "integration_id": outcome.integration_id,
                "status": "conflicted",
                "conflicted_files": list(outcome.conflicted_files),
                "conflict_report_id": f"conflict-{outcome.integration_id}",
            },
        )
    if outcome.status == IntegrationStatus.FAILED:
        return _error_response(
            409,
            "integration_checks_failed",
            f"Combined post-merge checks failed for run '{run_id}'",
            run_id=run_id,
            retryable=True,
            extra={
                "integration_id": outcome.integration_id,
                "status": "failed",
            },
        )

    return {
        "integration_id": outcome.integration_id,
        "status": "succeeded",
        "integration_status": outcome.status.value,
        "result_sha": outcome.result_sha,
        "target_branch": outcome.target_branch,
        "conflict_report_id": None,
    }


@app.post("/v1/control-plane/runs/{run_id}/discard")
@app.post("/runs/{run_id}/discard")
async def discard_run_endpoint(
    run_id: str,
    payload: Optional[DiscardPayload] = None,
) -> Any:
    svc = get_run_service()
    req = payload or DiscardPayload()

    run_rec = await svc.store.get_run(run_id)
    if run_rec is None:
        return _error_response(404, "run_not_found", f"Run '{run_id}' not found", run_id=run_id)

    return await svc.discard_run_runtime(run_id=run_id, force=req.force)


# ============================================================================
# EXCEPTION HANDLERS (CANONICAL ERROR ENVELOPE)
# ============================================================================

@app.exception_handler(ConfigError)
async def configuration_error_handler(request: Request, exc: ConfigError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, str(exc), retryable=False)


@app.exception_handler(IdempotencyConflictError)
async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictError) -> JSONResponse:
    return _error_response(409, "idempotency_conflict", str(exc), retryable=False)


@app.exception_handler(OptimisticLockError)
async def optimistic_lock_handler(request: Request, exc: OptimisticLockError) -> JSONResponse:
    return _error_response(409, "optimistic_lock_conflict", str(exc), retryable=True)


@app.exception_handler(ContractViolation)
async def contract_violation_handler(request: Request, exc: ContractViolation) -> JSONResponse:
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
    bad_request_codes = {
        "workspace_invalid",
        "base_sha_mismatch",
        "git_command_failed",
        "scope_violation",
    }
    if exc.code in conflict_codes:
        status_code = 409
    elif exc.code in bad_request_codes:
        status_code = 400
    else:
        status_code = 422
    return _error_response(status_code, exc.code, str(exc), retryable=False)


@app.exception_handler(GitWorkspaceError)
async def git_workspace_error_handler(request: Request, exc: GitWorkspaceError) -> JSONResponse:
    status_code = 409 if exc.failure.code == "dirty_worktree_preserved" else 400
    return _error_response(
        status_code,
        exc.failure.code,
        exc.failure.message,
        retryable=exc.failure.retryable,
    )


@app.exception_handler(StorageIntegrityError)
async def storage_integrity_handler(request: Request, exc: StorageIntegrityError) -> JSONResponse:
    msg = str(exc)
    if "not found" in msg.lower() or "does not exist" in msg.lower():
        return _error_response(404, "resource_not_found", msg, retryable=False)
    return _error_response(409, "storage_conflict", msg, retryable=False)


@app.exception_handler(StorageLockError)
async def storage_lock_handler(request: Request, exc: StorageLockError) -> JSONResponse:
    return _error_response(503, "storage_locked", str(exc), retryable=True)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        422,
        "validation_error",
        "Request payload validation failed",
        retryable=False,
        extra={"details": exc.errors()},
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return _error_response(
        422,
        "validation_error",
        str(exc),
        retryable=False,
    )


def start_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run uvicorn server directly on loopback interface by default."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)
