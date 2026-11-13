"""FastAPI OpenAI-compatible proxy and M1 Control Plane server for hydra-orch (T01 / T07)."""

from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Sequence
import uuid

from fastapi import APIRouter, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse as BaseJSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hydra_orch.config import ConfigError, HydraConfig, load_config
from hydra_orch.core.auth import load_cors_origins, load_token_verifier, validate_cors_origins
from hydra_orch.core.redaction import install_log_redaction, redact
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
from hydra_orch.core.session_service import SessionService, SessionState
from hydra_orch.core.metrics import MetricsService, MetricScope
from hydra_orch.core.hitl import HITLService, HitlKind, HitlRequest
from hydra_orch.core.agent_registry import AgentRegistry
from hydra_orch.core.route_selector import RouteSelector
from hydra_orch.core.consent import ConsentService, ConsentRecord, MemoryScope, ScopeType
from hydra_orch.core.memory_store import MemoryStore, MemoryWrite, MemoryEntry
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.core.ssh_tunnel import SshTunnelManager
import secrets
import shutil
from hydra_orch.bridge.transport_registry import (
    TransportCertificationReport,
    TransportDefinition,
    TransportRegistry,
)
from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.agent_registry import AgentDefinition, CERTIFICATION_CHECKS, DRIVERS
from hydra_orch.core.budget import BudgetGovernor
from hydra_orch.core.conflict_resolver import ConflictResolver
from hydra_orch.core.consent import ConsentPurpose
from hydra_orch.core.discovery import DiscoveryService, KNOWN_CAPABILITIES
from hydra_orch.core.extension_host import ExtensionHost, ExtensionManifest
from hydra_orch.core.packaging import PRPackager
from hydra_orch.core.preferences import PreferenceService
from hydra_orch.core.profile_service import MemoryPolicy, ProfileDefinition, ProfileService
from hydra_orch.core.skill_registry import (
    DeclaredTool,
    McpDefinition,
    SecretRef,
    SkillDefinition,
    SkillRegistry,
)
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
    ExecutorCapability,
    Sha256,
    TaskSpec,
)

install_log_redaction()
logger = logging.getLogger(__name__)


class JSONResponse(BaseJSONResponse):
    """Sanitize JSON evidence and errors before HTTP exposure."""

    def render(self, content: Any) -> bytes:
        return super().render(redact(content))


DEFAULT_CORS_ALLOW_ORIGINS: List[str] = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

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
    app.state.token_verifier = load_token_verifier()
    if app.state.token_verifier is None:
        raise RuntimeError("Configure HYDRA_API_TOKEN_HASH or HYDRA_API_TOKEN before serving HTTP")
    validate_cors_origins(app.state.cors_allow_origins)
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
    async def reconcile_deadlines():
        while True:
            await asyncio.sleep(1)
            try:
                store = _run_service.store if _run_service is not None else router.checkpointer
                await HITLService(store).expire_due()
            except Exception:
                logger.exception("Human intervention deadline reconciliation failed")
    deadline_task = asyncio.create_task(reconcile_deadlines(), name="hydra-hitl-deadlines")
    try:
        yield
    finally:
        deadline_task.cancel()
        with suppress(asyncio.CancelledError):
            await deadline_task
        shutdown_event()


app = FastAPI(
    title=config.server.title,
    description=config.server.description,
    version="0.1.0",
    lifespan=_lifespan,
    default_response_class=JSONResponse,
)

app.state.cors_allow_origins = load_cors_origins(DEFAULT_CORS_ALLOW_ORIGINS)
app.state.token_verifier = load_token_verifier()
app.state.expired_cursors = {}  # run_id -> min_valid_seq
app.state.local_principal_id = "operator"  # Identity of the authenticated single local operator.

app.add_middleware(
    CORSMiddleware,
    allow_origins=app.state.cors_allow_origins,
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


async def _check_control_plane_security(request: Request) -> Optional[JSONResponse]:
    """Require Bearer auth for all HTTP routes; validate browser origin first."""
    try:
        allowed_origins = validate_cors_origins(app.state.cors_allow_origins)
    except ValueError:
        return _error_response(503, "cors_configuration_invalid", "Invalid CORS allowlist")
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed_origins:
        return _error_response(403, "cors_origin_forbidden", "Origin is not authorized")

    # Browsers cannot send Authorization on the preflight itself. CORS middleware
    # validates method/headers and returns no application data on this path.
    if (request.method == "OPTIONS" and origin is not None
            and "access-control-request-method" in request.headers):
        return None
    auth_headers = request.headers.getlist("authorization")
    auth_header = auth_headers[0] if len(auth_headers) == 1 else ""
    scheme, _, provided_token = auth_header.partition(" ")
    verifier = getattr(app.state, "token_verifier", None)
    if (scheme.lower() != "bearer" or verifier is None
            or not await asyncio.to_thread(verifier.verify, provided_token)):
        response = _error_response(401, "unauthorized", "A valid local Bearer token is required")
        response.headers["WWW-Authenticate"] = "Bearer"
        return response
    return None


@app.middleware("http")
async def control_plane_security_middleware(request: Request, call_next: Any) -> Any:
    sec_err = await _check_control_plane_security(request)
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
    workspace_id: Optional[str] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


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
            "areas": True,
            "workspaces": True,
            "repositories": True,
            "agents": True,
            "executors": True,
            "capabilities": True,
            "profiles": True,
            "sessions": True,
            "discovery": True,
            "skills": True,
            "mcps": True,
            "secrets": True,
            "extensions": True,
            "preferences": True,
            "transports": True,
            "tokens": True,
            "conflicts": True,
            "budget": True,
            "pr_package": True,
        },
    }


@app.post("/v1/control-plane/projects", status_code=201)
@app.post("/projects", status_code=201)
async def create_project_endpoint(payload: ProjectCreatePayload) -> Dict[str, Any]:
    if payload.workspace_id is not None:
        return await _get_workspace_registry().create_project(
            payload.workspace_id,
            payload.name,
            payload.canonical_root,
            principal_id=app.state.local_principal_id,
            base_branch=payload.base_branch,
            base_sha=payload.base_sha,
            metadata=payload.metadata,
        )
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


class SessionCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin_ref: Optional[str] = Field(default=None, max_length=256)
    agent_ref: Optional[str] = Field(default=None, max_length=128)


def _allowed_roots(attr: str) -> List[Path]:
    svc = get_run_service()
    configured = getattr(app.state, attr, None)
    if configured:
        return [Path(root) for root in configured]
    return [svc.repo_root]


def _get_workspace_registry() -> WorkspaceRegistry:
    runs = get_run_service()
    return WorkspaceRegistry(runs.store, allowed_roots=_allowed_roots("workspace_allowed_roots"))


def _get_agent_registry() -> AgentRegistry:
    runs = get_run_service()
    cert_root = getattr(app.state, "certification_root", None)
    locator = getattr(app.state, "executable_locator", None)
    kwargs: Dict[str, Any] = {}
    if cert_root is not None:
        kwargs["certification_root"] = Path(cert_root)
    if locator is not None:
        kwargs["executable_locator"] = locator
    return AgentRegistry(runs.store, **kwargs)


def _get_discovery_service(*, opt_in: Optional[bool] = None) -> DiscoveryService:
    runs = get_run_service()
    app_enabled = getattr(app.state, "discovery_enabled", None)
    if app_enabled is not None:
        enabled = bool(app_enabled) if opt_in is None else bool(app_enabled and opt_in)
    else:
        enabled = True if opt_in is None else bool(opt_in)
    return DiscoveryService(
        runs.store,
        allowed_roots=_allowed_roots("discovery_allowed_roots"),
        enabled=enabled,
        principal_id=app.state.local_principal_id,
    )


def _get_profile_service() -> ProfileService:
    runs = get_run_service()
    return ProfileService(
        runs.store,
        _get_agent_registry(),
        _get_workspace_registry(),
        discovery=_get_discovery_service(),
    )


def _get_skill_registry() -> SkillRegistry:
    runs = get_run_service()
    return SkillRegistry(runs.store, discovery=_get_discovery_service())


def _get_extension_host() -> ExtensionHost:
    runs = get_run_service()
    workspaces = _get_workspace_registry()
    consents = ConsentService(runs.store, workspaces)
    runtime_dir = getattr(app.state, "extension_runtime_dir", None)
    kwargs: Dict[str, Any] = {"allowed_roots": _allowed_roots("extension_allowed_roots")}
    if runtime_dir is not None:
        kwargs["runtime_dir"] = Path(runtime_dir)
    return ExtensionHost(runs.store, consents, **kwargs)


def _get_transport_registry() -> TransportRegistry:
    return TransportRegistry(get_run_service().store)


class ConsentCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    scope_type: ScopeType
    scope_id: str = Field(min_length=1, max_length=128)
    purpose: Optional[ConsentPurpose] = None


def get_memory_store() -> MemoryStore:
    runs = get_run_service()
    return MemoryStore(ConsentService(runs.store, _get_workspace_registry()))


@app.post("/v1/control-plane/consents", status_code=201)
async def create_consent_endpoint(payload: ConsentCreatePayload) -> ConsentRecord:
    purpose: ConsentPurpose = payload.purpose or ("extension" if payload.scope_type == "extension" else "memory")
    return await get_memory_store().consents.request(
        MemoryScope(scope_type=payload.scope_type, scope_id=payload.scope_id),
        principal_id=app.state.local_principal_id,
        purpose=purpose,
    )





@app.get("/v1/control-plane/consents")
async def list_consents_endpoint(
    scope_type: ScopeType,
    scope_id: str,
    purpose: Optional[ConsentPurpose] = Query(default=None),
) -> tuple[ConsentRecord, ...]:
    resolved_purpose: ConsentPurpose = purpose or ("extension" if scope_type == "extension" else "memory")
    return await get_memory_store().consents.list(
        MemoryScope(scope_type=scope_type, scope_id=scope_id),
        principal_id=app.state.local_principal_id,
        purpose=resolved_purpose,
    )





class ConsentActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["granted", "denied", "revoked", "expired"]


@app.post("/v1/control-plane/consents/{consent_id}")
async def decide_consent_endpoint(consent_id: str, payload: ConsentActionPayload) -> ConsentRecord:
    return await get_memory_store().consents.decide(consent_id, payload.action, principal_id=app.state.local_principal_id)


@app.post("/v1/control-plane/consents/{consent_id}/revoke")
async def revoke_consent_endpoint(consent_id: str) -> ConsentRecord:
    return await get_memory_store().consents.decide(consent_id, 'revoked', principal_id=app.state.local_principal_id)


@app.post("/v1/control-plane/memory", status_code=201)
async def create_memory_endpoint(payload: MemoryWrite) -> MemoryEntry:
    return await get_memory_store().write(payload, principal_id=app.state.local_principal_id)


@app.get("/v1/control-plane/memory")
async def query_memory_endpoint(scope_type: ScopeType, scope_id: str, query: str = Query(default='', max_length=256)) -> tuple[MemoryEntry, ...]:
    return await get_memory_store().query(MemoryScope(scope_type=scope_type, scope_id=scope_id),
        principal_id=app.state.local_principal_id, query=query)


@app.put("/v1/control-plane/memory/{memory_id}")
async def update_memory_endpoint(memory_id: str, payload: MemoryWrite, expected_version: int = Query(ge=1)) -> MemoryEntry:
    return await get_memory_store().update(memory_id, payload, principal_id=app.state.local_principal_id, expected_version=expected_version)


@app.post("/v1/control-plane/memory/{memory_id}/revoke")
async def revoke_memory_endpoint(memory_id: str) -> MemoryEntry:
    return await get_memory_store().revoke(memory_id, principal_id=app.state.local_principal_id)


@app.get("/v1/control-plane/runs/{run_id}/metrics")
async def run_metrics_endpoint(run_id: str, scope: MetricScope = Query(default="run"),
    scope_id: Optional[str] = Query(default=None), max_age_seconds: float = Query(default=300, ge=0, le=86400)):
    return await MetricsService(get_run_service().store).query(run_id, scope, scope_id or run_id, max_age_seconds=max_age_seconds)


@app.get("/v1/control-plane/runs/{run_id}/metrics/usage")
async def run_usage_metrics_endpoint(run_id: str):
    return await MetricsService(get_run_service().store).aggregate_usage(run_id)


@app.get("/v1/control-plane/runs/{run_id}/route-decisions")
async def list_route_decisions_endpoint(run_id: str):
    store = get_run_service().store
    return await RouteSelector(store, AgentRegistry(store), MetricsService(store)).list_decisions(run_id)


class ThreadCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_thread_id: Optional[str] = Field(default=None, max_length=128)
    agent_ref: Optional[str] = Field(default=None, max_length=128)


class HitlCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: HitlKind
    question: str = Field(min_length=1, max_length=100_000)
    task_id: Optional[str] = None
    timeout_seconds: int = Field(default=300, ge=1, le=86400, strict=True)


class HitlResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str = Field(min_length=1, max_length=100_000)
    actor: str = Field(min_length=1, max_length=256)
    expected_revision: int = Field(ge=1, strict=True)
    approved: bool = True


@app.post("/v1/control-plane/runs/{run_id}/interventions", status_code=201)
async def request_intervention_endpoint(run_id: str, payload: HitlCreatePayload,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=64)) -> HitlRequest:
    return await HITLService(get_run_service().store).request(run_id, idempotency_key=idempotency_key, **payload.model_dump())


@app.get("/v1/control-plane/runs/{run_id}/interventions")
async def list_interventions_endpoint(run_id: str) -> tuple[HitlRequest, ...]:
    return await HITLService(get_run_service().store).list_requests(run_id)


@app.get("/v1/control-plane/runs/{run_id}/interventions/{request_id}")
async def get_intervention_endpoint(run_id: str, request_id: str) -> HitlRequest:
    return await HITLService(get_run_service().store).get_request(run_id, request_id)


@app.post("/v1/control-plane/runs/{run_id}/interventions/{request_id}/response")
async def respond_intervention_endpoint(run_id: str, request_id: str, payload: HitlResponsePayload,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=64)) -> HitlRequest:
    return await HITLService(get_run_service().store).respond(run_id, request_id,
        idempotency_key=idempotency_key, **payload.model_dump())


class SessionTransitionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: SessionState
    expected_state: SessionState


class ThreadMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=100_000)
    expected_last_seq: int = Field(ge=0, strict=True)


@app.post("/v1/control-plane/runs/{run_id}/sessions", status_code=201)
async def create_session_endpoint(run_id: str, payload: SessionCreatePayload):
    return await SessionService(get_run_service().store).create_session(run_id, **payload.model_dump())


@app.get("/v1/control-plane/runs/{run_id}/sessions")
async def list_sessions_endpoint(run_id: str):
    return await SessionService(get_run_service().store).list_sessions(run_id)


@app.get("/v1/control-plane/runs/{run_id}/sessions/{session_id}")
async def get_session_endpoint(run_id: str, session_id: str):
    return await SessionService(get_run_service().store).get_session(run_id, session_id)


@app.post("/v1/control-plane/runs/{run_id}/sessions/{session_id}/state")
async def transition_session_endpoint(run_id: str, session_id: str, payload: SessionTransitionPayload):
    return await SessionService(get_run_service().store).transition_session(run_id, session_id,
        payload.state, expected_state=payload.expected_state)


@app.post("/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads", status_code=201)
async def create_thread_endpoint(run_id: str, session_id: str, payload: ThreadCreatePayload):
    return await SessionService(get_run_service().store).create_thread(run_id, session_id, **payload.model_dump())


@app.get("/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads")
async def list_threads_endpoint(run_id: str, session_id: str):
    return await SessionService(get_run_service().store).list_threads(run_id, session_id)


@app.post("/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads/{thread_id}/state")
async def transition_thread_endpoint(run_id: str, session_id: str, thread_id: str, payload: SessionTransitionPayload):
    return await SessionService(get_run_service().store).transition_thread(run_id, session_id, thread_id,
        payload.state, expected_state=payload.expected_state)


@app.post("/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads/{thread_id}/messages")
async def append_thread_message_endpoint(run_id: str, session_id: str, thread_id: str, payload: ThreadMessagePayload,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=64)):
    return await SessionService(get_run_service().store).append_message(run_id, session_id, thread_id,
        payload.content, idempotency_key=idempotency_key, expected_last_seq=payload.expected_last_seq)


async def _stream_events_response(
    request: Request,
    run_id: str,
    *,
    last_event_id: Optional[str] = None,
    after_seq: Optional[int] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    follow: bool = False,
    limit: int = 1000,
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
    min_valid_seq = max(
        expired_map.get(run_id, 0),
        expired_map.get(session_id, 0) if session_id else 0,
    )
    if cursor_seq > 0 and cursor_seq < min_valid_seq:
        return _error_response(
            410,
            "cursor_expired",
            f"Cursor {cursor_seq} is older than minimum retained sequence {min_valid_seq}; fetch full run snapshot",
            run_id=run_id,
        )

    sessions = SessionService(svc.store)
    events = await sessions.replay(run_id, after_seq=cursor_seq, session_id=session_id, thread_id=thread_id, limit=limit)

    async def sse_generator() -> AsyncIterator[str]:
        cursor, batch = cursor_seq, events
        heartbeat_at = asyncio.get_running_loop().time() + 15
        while True:
            for ev in batch:
                cursor = ev.seq
                payload_obj = {"run_id": ev.run_id, "seq": ev.seq, "type": ev.event_type,
                    "correlation_id": ev.correlation_id, "task_id": ev.task_id, "attempt_id": ev.attempt_id,
                    "session_id": ev.session_id, "thread_id": ev.thread_id,
                    "payload": redact(ev.redacted_payload), "timestamp": ev.timestamp.isoformat()}
                yield f"id: {ev.seq}\nevent: {ev.event_type}\nretry: 15000\ndata: {json.dumps(payload_obj, sort_keys=True)}\n\n"
            now = asyncio.get_running_loop().time()
            if not follow or now >= heartbeat_at:
                heartbeat_obj = {"run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat()}
                if session_id is not None:
                    heartbeat_obj["session_id"] = session_id
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat_obj)}\n\n"
                heartbeat_at = now + 15
            if not follow or await request.is_disconnected():
                break
            # Poll SQLite rather than relying on an in-memory queue lost on restart.
            await asyncio.sleep(0.25)
            batch = await sessions.replay(run_id, after_seq=cursor, session_id=session_id, thread_id=thread_id, limit=limit)

    return StreamingResponse(sse_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/v1/control-plane/runs/{run_id}/events")
@app.get("/runs/{run_id}/events")
async def stream_run_events_endpoint(
    request: Request,
    run_id: str,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    after_seq: Optional[int] = Query(default=None, ge=0),
    session_id: Optional[str] = Query(default=None),
    thread_id: Optional[str] = Query(default=None),
    follow: bool = Query(default=False),
    limit: int = Query(default=1000, ge=1, le=1000),
) -> Any:
    return await _stream_events_response(
        request,
        run_id,
        last_event_id=last_event_id,
        after_seq=after_seq,
        session_id=session_id,
        thread_id=thread_id,
        follow=follow,
        limit=limit,
    )


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
# EXTENDED CONTROL PLANE ENDPOINTS (T23)
# ============================================================================


class AreaCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)


class WorkspaceCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)


class WorkspaceArchivePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, strict=True)


class ProjectAdoptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=1, strict=True)
    base_branch: str = Field(default="main", min_length=1, max_length=128)


class RepositoryCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_canonical: str = Field(min_length=1)
    authorized_principal_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    scopes: List[str] = Field(default_factory=lambda: ["read", "write"])
    allowed_paths: List[str] = Field(default_factory=lambda: ["*"])
    base_branch: str = Field(default="main", min_length=1, max_length=128)
    base_sha: Optional[str] = Field(default=None)


class RepositoryGrantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorized_principal_id: str = Field(min_length=1, max_length=128)
    scopes: List[str] = Field(min_length=1)


class RepositoryRevokePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_id: str = Field(min_length=1, max_length=128)


@app.get("/v1/control-plane/areas")
async def list_areas_endpoint() -> List[Dict[str, Any]]:
    return await _get_workspace_registry().list_areas(principal_id=app.state.local_principal_id)


@app.post("/v1/control-plane/areas", status_code=201)
async def create_area_endpoint(payload: AreaCreatePayload) -> Dict[str, Any]:
    return await _get_workspace_registry().create_area(
        payload.name,
        principal_id=app.state.local_principal_id,
        description=payload.description,
    )


@app.get("/v1/control-plane/workspaces")
async def list_workspaces_endpoint(area_id: Optional[str] = Query(default=None)) -> List[Dict[str, Any]]:
    reg = _get_workspace_registry()
    principal_id = app.state.local_principal_id
    if area_id is not None:
        return await reg.list_workspaces(area_id, principal_id=principal_id)
    areas = await reg.list_areas(principal_id=principal_id)
    workspaces: List[Dict[str, Any]] = []
    for area in areas:
        workspaces.extend(await reg.list_workspaces(area["id"], principal_id=principal_id))
    return workspaces


@app.post("/v1/control-plane/workspaces", status_code=201)
async def create_workspace_endpoint(payload: WorkspaceCreatePayload) -> Dict[str, Any]:
    return await _get_workspace_registry().create_workspace(
        payload.area_id,
        payload.name,
        principal_id=app.state.local_principal_id,
    )


@app.post("/v1/control-plane/workspaces/{workspace_id}/archive")
async def archive_workspace_endpoint(workspace_id: str, payload: WorkspaceArchivePayload) -> Dict[str, Any]:
    await _get_workspace_registry().archive_workspace(
        workspace_id,
        principal_id=app.state.local_principal_id,
        expected_revision=payload.expected_revision,
    )
    return {
        "workspace_id": workspace_id,
        "status": "archived",
        "revision": payload.expected_revision + 1,
    }


@app.post("/v1/control-plane/projects/{project_id}/adopt")
async def adopt_project_endpoint(project_id: str, payload: ProjectAdoptPayload) -> Dict[str, Any]:
    return await _get_workspace_registry().adopt_legacy_project(
        project_id,
        payload.workspace_id,
        principal_id=app.state.local_principal_id,
        expected_revision=payload.expected_revision,
        base_branch=payload.base_branch,
    )


@app.get("/v1/control-plane/projects/{project_id}/repositories")
async def list_project_repositories_endpoint(project_id: str) -> List[Dict[str, Any]]:
    return await _get_workspace_registry().list_repositories(
        project_id,
        principal_id=app.state.local_principal_id,
    )


@app.post("/v1/control-plane/projects/{project_id}/repositories", status_code=201)
async def register_project_repository_endpoint(project_id: str, payload: RepositoryCreatePayload) -> Dict[str, Any]:
    return await _get_workspace_registry().register_repository(
        project_id,
        payload.root_canonical,
        principal_id=app.state.local_principal_id,
        authorized_principal_id=payload.authorized_principal_id or app.state.local_principal_id,
        scopes=payload.scopes,
        allowed_paths=payload.allowed_paths,
        base_branch=payload.base_branch,
        base_sha=payload.base_sha,
    )


@app.post("/v1/control-plane/repositories/{repository_id}/grant", status_code=201)
async def grant_repository_endpoint(repository_id: str, payload: RepositoryGrantPayload) -> Dict[str, Any]:
    authorization_id = await _get_workspace_registry().grant_repository(
        repository_id,
        principal_id=app.state.local_principal_id,
        authorized_principal_id=payload.authorized_principal_id,
        scopes=payload.scopes,
    )
    return {
        "authorization_id": authorization_id,
        "repository_id": repository_id,
        "principal_id": payload.authorized_principal_id,
        "scopes": payload.scopes,
    }


@app.post("/v1/control-plane/repositories/{repository_id}/revoke")
async def revoke_repository_endpoint(repository_id: str, payload: RepositoryRevokePayload) -> Dict[str, Any]:
    await _get_workspace_registry().revoke_authorization(
        payload.authorization_id,
        principal_id=app.state.local_principal_id,
    )
    return {
        "authorization_id": payload.authorization_id,
        "repository_id": repository_id,
        "revoked": True,
    }


class AgentCertificatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_path: str = Field(min_length=1)


class ProfileResolvePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_id: str = Field(min_length=1, max_length=128)
    run_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


@app.get("/v1/control-plane/agents")
async def list_agents_endpoint() -> List[AgentDefinition]:
    return list(await _get_agent_registry().list_agents())


@app.post("/v1/control-plane/agents", status_code=201)
async def register_agent_endpoint(payload: AgentDefinition) -> AgentDefinition:
    return await _get_agent_registry().register_agent(payload)


@app.post("/v1/control-plane/agents/{agent_id}/certificate", status_code=201)
async def import_agent_certificate_endpoint(agent_id: str, payload: AgentCertificatePayload) -> Dict[str, Any]:
    cert_id = await _get_agent_registry().import_certificate(
        agent_id,
        Path(payload.report_path),
        principal_id=app.state.local_principal_id,
    )
    return {"certificate_id": cert_id, "agent_id": agent_id}


@app.get("/v1/control-plane/executors")
async def list_executors_endpoint() -> List[Dict[str, Any]]:
    registry = _get_agent_registry()
    agents = await registry.list_agents()
    executors: List[Dict[str, Any]] = []
    for agent in agents:
        resolved_bin: Optional[str] = None
        is_certified = False
        platform_name: Optional[str] = None
        reason: Optional[str] = None
        try:
            resolved = await registry.resolve_capabilities(agent.agent_id)
            resolved_bin = resolved.executable
            is_certified = True
            platform_name = resolved.platform
        except ContractViolation as exc:
            reason = exc.code
            with suppress(ContractViolation):
                resolved_bin = str(registry._executable(agent))
        executors.append(
            {
                "id": agent.agent_id,
                "agent_id": agent.agent_id,
                "name": agent.name,
                "version": agent.version,
                "driver": agent.driver_type,
                "driver_type": agent.driver_type,
                "executable": resolved_bin,
                "executable_found": resolved_bin is not None,
                "is_certified": is_certified,
                "status": "ready" if is_certified else "unavailable",
                "reason": reason,
                "capabilities": [cap.value for cap in agent.declared_capabilities],
                "platform": platform_name,
            }
        )
    if not executors:
        for driver_name in sorted(DRIVERS):
            executors.append(
                {
                    "id": f"driver:{driver_name}",
                    "name": driver_name,
                    "driver": driver_name,
                    "driver_type": driver_name,
                    "executable": None,
                    "executable_found": False,
                    "is_certified": False,
                    "status": "registered_driver",
                    "capabilities": [],
                    "platform": None,
                }
            )
    return executors


@app.get("/v1/control-plane/capabilities")
async def list_capabilities_endpoint() -> Dict[str, Any]:
    registry = _get_agent_registry()
    agents = await registry.list_agents()
    agent_entries: List[Dict[str, Any]] = []
    for agent in agents:
        is_certified = False
        with suppress(ContractViolation):
            await registry.resolve_capabilities(agent.agent_id)
            is_certified = True
        agent_entries.append(
            {
                "id": agent.agent_id,
                "agent_id": agent.agent_id,
                "driver": agent.driver_type,
                "driver_type": agent.driver_type,
                "version": agent.version,
                "is_certified": is_certified,
                "capabilities": [cap.value for cap in agent.declared_capabilities],
            }
        )
    return {
        "known_capabilities": list(KNOWN_CAPABILITIES),
        "executor_capabilities": [cap.value for cap in ExecutorCapability],
        "certification_checks": list(CERTIFICATION_CHECKS),
        "drivers": sorted(DRIVERS),
        "agents": agent_entries,
    }
@app.get("/v1/control-plane/profiles")
async def list_profiles_endpoint() -> List[ProfileDefinition]:
    runs = get_run_service()
    await runs.store.initialize()
    svc = _get_profile_service()
    async with runs.store._connect() as db:
        rows = await (await db.execute("SELECT id FROM profiles ORDER BY id")).fetchall()
    return [await svc.get_profile(row["id"]) for row in rows]


@app.post("/v1/control-plane/profiles", status_code=201)
async def create_profile_endpoint(payload: ProfileDefinition) -> ProfileDefinition:
    return await _get_profile_service().create_profile(payload)


@app.post("/v1/control-plane/profiles/{profile_id}/resolve")
async def resolve_profile_endpoint(profile_id: str, payload: ProfileResolvePayload) -> Any:
    svc = _get_profile_service()
    if payload.run_id is not None:
        return await svc.snapshot(
            profile_id,
            payload.run_id,
            payload.repository_id,
            principal_id=app.state.local_principal_id,
        )
    return await svc.resolve_effective(
        profile_id,
        payload.repository_id,
        principal_id=app.state.local_principal_id,
    )


@app.get("/v1/control-plane/sessions")
async def list_top_level_sessions_endpoint(run_id: Optional[str] = Query(default=None)) -> List[Dict[str, Any]]:
    store = get_run_service().store
    if run_id is not None:
        return await SessionService(store).list_sessions(run_id)
    await store.initialize()
    async with store._connect() as db:
        rows = await (await db.execute("SELECT * FROM sessions ORDER BY created_at, id")).fetchall()
    return [dict(row) for row in rows]


@app.get("/v1/control-plane/sessions/{session_id}/threads")
async def list_session_threads_top_level_endpoint(session_id: str) -> List[Dict[str, Any]]:
    store = get_run_service().store
    await store.initialize()
    async with store._connect() as db:
        row = await (await db.execute("SELECT run_id FROM sessions WHERE id = ?", (session_id,))).fetchone()
    if row is None:
        raise ContractViolation("resource_not_found", f"Session '{session_id}' does not exist")
    return await SessionService(store).list_threads(row["run_id"], session_id)


@app.get("/v1/control-plane/sessions/{session_id}/events")
async def stream_session_events_endpoint(
    request: Request,
    session_id: str,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    after_seq: Optional[int] = Query(default=None, ge=0),
    thread_id: Optional[str] = Query(default=None),
    follow: bool = Query(default=False),
    limit: int = Query(default=1000, ge=1, le=1000),
) -> Any:
    store = get_run_service().store
    await store.initialize()
    async with store._connect() as db:
        row = await (await db.execute("SELECT run_id FROM sessions WHERE id = ?", (session_id,))).fetchone()
    if row is None:
        return _error_response(404, "resource_not_found", f"Session '{session_id}' does not exist")
    return await _stream_events_response(
        request,
        row["run_id"],
        last_event_id=last_event_id,
        after_seq=after_seq,
        session_id=session_id,
        thread_id=thread_id,
        follow=follow,
        limit=limit,
    )


class DiscoveryScanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorized_root: str = Field(min_length=1)
    opt_in: bool = True


class DiscoveryApprovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_hash: Sha256


class DiscoveryRejectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["rejected", "revoked"] = "rejected"


@app.post("/v1/control-plane/discovery/scan")
async def scan_discovery_endpoint(payload: DiscoveryScanPayload) -> List[Any]:
    results = await _get_discovery_service(opt_in=payload.opt_in).scan(
        payload.authorized_root,
        principal_id=app.state.local_principal_id,
    )
    return list(results)


@app.get("/v1/control-plane/discovery/resources")
async def list_discovery_resources_endpoint() -> List[Any]:
    results = await _get_discovery_service().list(principal_id=app.state.local_principal_id)
    return list(results)


@app.post("/v1/control-plane/discovery/resources/{resource_id}/approve")
async def approve_discovery_resource_endpoint(resource_id: str, payload: DiscoveryApprovePayload) -> Any:
    return await _get_discovery_service().approve(
        resource_id,
        payload.expected_hash,
        principal_id=app.state.local_principal_id,
    )


@app.post("/v1/control-plane/discovery/resources/{resource_id}/reject")
async def reject_discovery_resource_endpoint(
    resource_id: str,
    payload: Optional[DiscoveryRejectPayload] = None,
) -> Any:
    action = payload.action if payload is not None else "rejected"
    return await _get_discovery_service().decide(
        resource_id,
        action,
        principal_id=app.state.local_principal_id,
    )


class SkillRevokePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="operator_revoked", min_length=1, max_length=256)


class SecretRefCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret_name: str = Field(min_length=1, max_length=128)
    provider_type: Literal["env", "vault", "keyring"]
    source_key: str = Field(min_length=1, max_length=256)
    secret_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


@app.get("/v1/control-plane/skills")
async def list_skills_endpoint() -> List[Dict[str, Any]]:
    runs = get_run_service()
    await runs.store.initialize()
    reg = _get_skill_registry()
    async with runs.store._connect() as db:
        rows = await (
            await db.execute(
                """SELECT id, name, version, manifest_ref, discovered_resource_id,
                          permissions_declared_json, checksum, created_at
                   FROM skill_definitions ORDER BY id"""
            )
        ).fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            revoked = await reg._is_revoked(db, "skill", row["id"])
            items.append(
                {
                    "skill_id": row["id"],
                    "name": row["name"],
                    "version": row["version"],
                    "manifest_ref": row["manifest_ref"],
                    "discovered_resource_id": row["discovered_resource_id"],
                    "permissions_declared": json.loads(row["permissions_declared_json"]),
                    "checksum": row["checksum"],
                    "revoked": revoked,
                    "created_at": row["created_at"],
                }
            )
    return items


@app.post("/v1/control-plane/skills", status_code=201)
async def register_skill_endpoint(payload: SkillDefinition) -> SkillDefinition:
    return await _get_skill_registry().register_skill(payload, principal_id=app.state.local_principal_id)


@app.post("/v1/control-plane/skills/{skill_id}/revoke")
async def revoke_skill_endpoint(skill_id: str, payload: Optional[SkillRevokePayload] = None) -> Dict[str, Any]:
    reason = payload.reason if payload is not None else "operator_revoked"
    await _get_skill_registry().revoke_skill(
        skill_id,
        principal_id=app.state.local_principal_id,
        reason=reason,
    )
    return {"skill_id": skill_id, "revoked": True, "reason": reason}


@app.get("/v1/control-plane/mcps")
async def list_mcps_endpoint() -> List[Dict[str, Any]]:
    runs = get_run_service()
    await runs.store.initialize()
    reg = _get_skill_registry()
    async with runs.store._connect() as db:
        rows = await (
            await db.execute(
                """SELECT id, server_name, transport_type, endpoint, discovered_resource_id,
                          secret_ref, declared_tools_json, permissions_json, created_at
                   FROM mcp_definitions ORDER BY id"""
            )
        ).fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            revoked = await reg._is_revoked(db, "mcp", row["id"])
            items.append(
                {
                    "mcp_id": row["id"],
                    "server_name": row["server_name"],
                    "transport_type": row["transport_type"],
                    "endpoint": row["endpoint"],
                    "discovered_resource_id": row["discovered_resource_id"],
                    "secret_ref": row["secret_ref"],
                    "declared_tools": json.loads(row["declared_tools_json"]),
                    "permissions": json.loads(row["permissions_json"]),
                    "revoked": revoked,
                    "created_at": row["created_at"],
                }
            )
    return items


@app.post("/v1/control-plane/mcps", status_code=201)
async def register_mcp_endpoint(payload: McpDefinition) -> McpDefinition:
    return await _get_skill_registry().register_mcp(payload, principal_id=app.state.local_principal_id)


@app.post("/v1/control-plane/mcps/{mcp_id}/revoke")
async def revoke_mcp_endpoint(mcp_id: str, payload: Optional[SkillRevokePayload] = None) -> Dict[str, Any]:
    reason = payload.reason if payload is not None else "operator_revoked"
    await _get_skill_registry().revoke_mcp(
        mcp_id,
        principal_id=app.state.local_principal_id,
        reason=reason,
    )
    return {"mcp_id": mcp_id, "revoked": True, "reason": reason}


@app.get("/v1/control-plane/secrets")
async def list_secrets_endpoint() -> List[Dict[str, Any]]:
    runs = get_run_service()
    await runs.store.initialize()
    reg = _get_skill_registry()
    async with runs.store._connect() as db:
        rows = await (
            await db.execute("SELECT id, secret_name, provider_type, source_key FROM secret_refs ORDER BY id")
        ).fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            revoked = await reg._is_revoked(db, "secret_ref", row["id"])
            items.append(
                {
                    "secret_id": row["id"],
                    "secret_name": row["secret_name"],
                    "provider_type": row["provider_type"],
                    "source_key": row["source_key"],
                    "revoked": revoked,
                }
            )
    return items


@app.post("/v1/control-plane/secrets", status_code=201)
async def create_secret_ref_endpoint(payload: SecretRefCreatePayload) -> SecretRef:
    return await _get_skill_registry().create_secret_ref(
        secret_name=payload.secret_name,
        provider_type=payload.provider_type,
        source_key=payload.source_key,
        principal_id=app.state.local_principal_id,
        secret_id=payload.secret_id,
    )


@app.post("/v1/control-plane/secrets/{secret_id}/revoke")
async def revoke_secret_ref_endpoint(secret_id: str, payload: Optional[SkillRevokePayload] = None) -> Dict[str, Any]:
    reason = payload.reason if payload is not None else "operator_revoked"
    await _get_skill_registry().revoke_secret_ref(
        secret_id,
        principal_id=app.state.local_principal_id,
        reason=reason,
    )
    return {"secret_id": secret_id, "revoked": True, "reason": reason}


class ExtensionInstallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: Optional[ExtensionManifest] = None
    manifest_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    consent_id: str = Field(min_length=1, max_length=128)
    activate: bool = True


@app.get("/v1/control-plane/extensions")
async def list_extensions_endpoint() -> List[Any]:
    return list(await _get_extension_host().list_installs())


@app.post("/v1/control-plane/extensions", status_code=201)
async def register_extension_manifest_endpoint(payload: ExtensionManifest) -> ExtensionManifest:
    return await _get_extension_host().register_manifest(
        payload,
        principal_id=app.state.local_principal_id,
    )


@app.post("/v1/control-plane/extensions/install", status_code=201)
async def install_extension_endpoint(payload: ExtensionInstallPayload) -> Any:
    manifest = payload.manifest
    if manifest is None:
        if payload.manifest_id is None:
            raise ContractViolation("extension_invalid_entrypoint", "Either manifest or manifest_id is required")
        runs = get_run_service()
        await runs.store.initialize()
        async with runs.store._connect() as db:
            row = await (
                await db.execute("SELECT * FROM extension_manifests WHERE id = ?", (payload.manifest_id,))
            ).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", f"Extension manifest '{payload.manifest_id}' does not exist")
        manifest = ExtensionManifest(
            extension_id=row["id"],
            name=row["name"],
            version=row["version"],
            entrypoint=row["entrypoint"],
            permissions_required=tuple(json.loads(row["permissions_required_json"])),
            compatible_api_version=row["compatible_api_version"],
            checksum=row["checksum"],
            created_at=row["created_at"],
        )
    return await _get_extension_host().install(
        manifest,
        payload.consent_id,
        principal_id=app.state.local_principal_id,
        activate=payload.activate,
    )


@app.post("/v1/control-plane/extensions/{install_id}/revoke")
async def revoke_extension_endpoint(install_id: str, payload: Optional[SkillRevokePayload] = None) -> Any:
    reason = payload.reason if payload is not None else "operator_revoked"
    return await _get_extension_host().revoke(
        install_id,
        principal_id=app.state.local_principal_id,
        reason=reason,
    )


@app.post("/v1/control-plane/extensions/{install_id}/rollback")
async def rollback_extension_endpoint(install_id: str) -> Any:
    return await _get_extension_host().rollback(
        install_id,
        principal_id=app.state.local_principal_id,
    )


class PreferenceSetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: Literal["user", "area", "project"]
    scope_id: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=128)
    value: Any
    source: Literal["explicit", "inferred_opt_in"] = "explicit"
    opt_in: bool = False
    expected_version: Optional[int] = Field(default=None, ge=1, strict=True)
    idempotency_key: Optional[str] = Field(default=None, min_length=16, max_length=64)


class PreferenceRevertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: Literal["user", "area", "project"]
    scope_id: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=128)
    target_version: Optional[int] = Field(default=None, ge=1, strict=True)
    expected_version: Optional[int] = Field(default=None, ge=1, strict=True)
    idempotency_key: Optional[str] = Field(default=None, min_length=16, max_length=64)


class PreferenceSnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    area_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    project_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


@app.get("/v1/control-plane/preferences")
async def list_preferences_endpoint(
    scope_type: Optional[Literal["user", "area", "project"]] = Query(default=None),
    scope_id: Optional[str] = Query(default=None),
) -> List[Any]:
    prefs = await PreferenceService(get_run_service().store).list_preferences(
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return list(prefs)


@app.put("/v1/control-plane/preferences")
async def set_preference_endpoint(
    payload: PreferenceSetPayload,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    return await PreferenceService(get_run_service().store).set_preference(
        payload.scope_type,
        payload.scope_id,
        payload.key,
        payload.value,
        source=payload.source,
        opt_in=payload.opt_in,
        actor=app.state.local_principal_id,
        expected_version=payload.expected_version,
        idempotency_key=payload.idempotency_key or idempotency_key_header,
    )


@app.post("/v1/control-plane/preferences/revert")
async def revert_preference_endpoint(
    payload: PreferenceRevertPayload,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Dict[str, Any]:
    reverted = await PreferenceService(get_run_service().store).revert_preference(
        payload.scope_type,
        payload.scope_id,
        payload.key,
        target_version=payload.target_version,
        actor=app.state.local_principal_id,
        expected_version=payload.expected_version,
        idempotency_key=payload.idempotency_key or idempotency_key_header,
    )
    return {"reverted": True, "preference": reverted}


@app.post("/v1/control-plane/runs/{run_id}/preferences/snapshot", status_code=201)
async def snapshot_run_preferences_endpoint(
    run_id: str,
    payload: Optional[PreferenceSnapshotPayload] = None,
) -> Any:
    req = payload or PreferenceSnapshotPayload()
    return await PreferenceService(get_run_service().store).snapshot_for_run(
        run_id,
        user_id=req.user_id,
        area_id=req.area_id,
        project_id=req.project_id,
    )


@app.get("/v1/control-plane/transports")
async def list_transports_endpoint(certified_only: bool = Query(default=False)) -> List[TransportDefinition]:
    return list(await _get_transport_registry().list_transports(certified_only=certified_only))


@app.post("/v1/control-plane/transports", status_code=201)
async def register_transport_endpoint(payload: TransportDefinition) -> TransportDefinition:
    return await _get_transport_registry().register_transport(payload)


@app.get("/v1/control-plane/transports/{transport_id}/health")
async def get_transport_health_endpoint(transport_id: str, refresh: bool = Query(default=False)) -> Any:
    reg = _get_transport_registry()
    await reg.get_transport(transport_id)
    probe = getattr(app.state, "transport_health_probe", None)
    if refresh:
        return await reg.check_health(transport_id, probe=probe)
    latest = await reg.get_latest_health(transport_id)
    if latest is not None:
        return latest
    return await reg.check_health(transport_id, probe=probe)


@app.post("/v1/control-plane/transports/{transport_id}/certify", status_code=201)
async def certify_transport_endpoint(
    transport_id: str,
    payload: TransportCertificationReport,
    platform_name: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    cert_id = await _get_transport_registry().certify_transport(
        transport_id,
        payload,
        principal_id=app.state.local_principal_id,
        platform_name=platform_name,
    )
    return {"certificate_id": cert_id, "transport_id": transport_id, "certified": True}


class TokenCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal_id: str = Field(min_length=1, max_length=128)
    scopes: List[str] = Field(min_length=1)
    expires_at: str = Field(min_length=1)
    redact_token: bool = False


@app.post("/v1/control-plane/tokens", status_code=201)
async def create_token_endpoint(payload: TokenCreatePayload) -> BaseJSONResponse:
    principal = payload.principal_id.strip()
    if not principal:
        raise ContractViolation("token_invalid", "Token principal_id cannot be empty")
    scopes = [s.strip() for s in payload.scopes if isinstance(s, str) and s.strip()]
    if len(scopes) != len(payload.scopes) or not scopes:
        raise ContractViolation("token_invalid", "Token scopes must be non-empty strings")
    try:
        expires_dt = datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractViolation("token_invalid", f"Invalid expires_at timestamp: '{payload.expires_at}'") from exc
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    if expires_dt <= datetime.now(timezone.utc):
        raise ContractViolation("token_invalid", "Token expires_at must be in the future")

    token_id = str(uuid.uuid4())
    raw_token = f"hydra_tok_{secrets.token_urlsafe(32)}"
    token_hash = await asyncio.to_thread(lambda: TokenVerifier.from_token(raw_token).encode())
    expires_iso = expires_dt.astimezone(timezone.utc).isoformat()

    store = get_run_service().store
    await store.initialize()
    audit_payload = {
        "event": "token.created",
        "token_id": token_id,
        "principal_id": principal,
        "scopes": scopes,
        "expires_at": expires_iso,
    }
    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute(
                """
                INSERT INTO access_tokens (id, token_hash, principal_id, scopes_json, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (token_id, token_hash, principal, json.dumps(scopes), expires_iso),
            )
            await store._record_command_in_tx(
                db,
                scope="access_tokens",
                idempotency_key=f"token-create:{token_id}",
                request_hash=store.compute_request_hash(audit_payload),
                response_payload=audit_payload,
            )

    body = {
        "id": token_id,
        "token_hash": token_hash,
        "principal_id": principal,
        "scopes": scopes,
        "expires_at": expires_iso,
        "revoked_at": None,
        "token": raw_token,
    }
    if payload.redact_token:
        return JSONResponse(status_code=201, content=body)
    return BaseJSONResponse(status_code=201, content=body)


@app.post("/v1/control-plane/tokens/{token_id}/revoke")
async def revoke_token_endpoint(token_id: str) -> Dict[str, Any]:
    store = get_run_service().store
    await store.initialize()
    async with store._connect() as db:
        async with store._transaction(db):
            row = await (
                await db.execute("SELECT * FROM access_tokens WHERE id = ?", (token_id,))
            ).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"Token '{token_id}' does not exist")
            revoked_at = row["revoked_at"]
            if revoked_at is None:
                revoked_at = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    "UPDATE access_tokens SET revoked_at = ? WHERE id = ?",
                    (revoked_at, token_id),
                )
                audit_payload = {
                    "event": "token.revoked",
                    "token_id": token_id,
                    "principal_id": row["principal_id"],
                    "revoked_by": app.state.local_principal_id,
                    "revoked_at": revoked_at,
                }
                await store._record_command_in_tx(
                    db,
                    scope="access_tokens",
                    idempotency_key=f"token-revoke:{token_id}",
                    request_hash=store.compute_request_hash(audit_payload),
                    response_payload=audit_payload,
                )
    return {
        "id": row["id"],
        "token_hash": row["token_hash"],
        "principal_id": row["principal_id"],
        "scopes": json.loads(row["scopes_json"]),
        "expires_at": row["expires_at"],
        "revoked_at": revoked_at,
    }


class ConflictAutoRepairPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repair_command: Optional[List[str]] = None
    max_repair_attempts: Optional[int] = Field(default=None, ge=0, strict=True)
    allowed_paths: Optional[List[str]] = None
    forbidden_paths: List[str] = Field(default_factory=list)
    idempotency_key: Optional[str] = Field(default=None, min_length=16, max_length=64)


class ConflictManualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finalize: bool = False
    worktree_path: Optional[str] = None
    commit_message: Optional[str] = Field(default=None, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, min_length=16, max_length=64)


class ConflictDiscardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="operator_discarded", min_length=1, max_length=256)
    idempotency_key: Optional[str] = Field(default=None, min_length=16, max_length=64)


async def _ensure_run_conflict(run_id: str, conflict_id: str) -> ConflictResolver:
    store = get_run_service().store
    if await store.get_run(run_id) is None:
        raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
    resolver = ConflictResolver(store)
    reports = await resolver.list_reports(run_id=run_id)
    if not any(report.conflict_id == conflict_id for report in reports):
        raise ContractViolation("resource_not_found", f"Conflict '{conflict_id}' not found in run '{run_id}'")
    return resolver


@app.get("/v1/control-plane/runs/{run_id}/conflicts")
async def list_run_conflicts_endpoint(run_id: str) -> List[Any]:
    store = get_run_service().store
    if await store.get_run(run_id) is None:
        raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
    return list(await ConflictResolver(store).list_reports(run_id=run_id))


@app.post("/v1/control-plane/runs/{run_id}/conflicts/{conflict_id}/auto-repair")
async def auto_repair_conflict_endpoint(
    run_id: str,
    conflict_id: str,
    payload: Optional[ConflictAutoRepairPayload] = None,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    resolver = await _ensure_run_conflict(run_id, conflict_id)
    req = payload or ConflictAutoRepairPayload()
    return await resolver.auto_repair(
        conflict_id,
        repair_command=req.repair_command,
        max_repair_attempts=req.max_repair_attempts,
        actor=app.state.local_principal_id,
        allowed_paths=req.allowed_paths,
        forbidden_paths=req.forbidden_paths,
        idempotency_key=req.idempotency_key or idempotency_key_header,
    )


@app.post("/v1/control-plane/runs/{run_id}/conflicts/{conflict_id}/manual")
async def manual_resolve_conflict_endpoint(
    run_id: str,
    conflict_id: str,
    payload: Optional[ConflictManualPayload] = None,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    resolver = await _ensure_run_conflict(run_id, conflict_id)
    req = payload or ConflictManualPayload()
    return await resolver.resolve_manual(
        conflict_id,
        actor=app.state.local_principal_id,
        finalize=req.finalize,
        worktree_path=req.worktree_path,
        commit_message=req.commit_message,
        idempotency_key=req.idempotency_key or idempotency_key_header,
    )


@app.post("/v1/control-plane/runs/{run_id}/conflicts/{conflict_id}/discard")
async def discard_conflict_endpoint(
    run_id: str,
    conflict_id: str,
    payload: Optional[ConflictDiscardPayload] = None,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    resolver = await _ensure_run_conflict(run_id, conflict_id)
    req = payload or ConflictDiscardPayload()
    return await resolver.discard(
        conflict_id,
        actor=app.state.local_principal_id,
        reason=req.reason,
        idempotency_key=req.idempotency_key or idempotency_key_header,
    )


class BudgetExtendPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    additional_usd: Optional[float] = Field(default=None, gt=0)
    additional_tokens_in: Optional[int] = Field(default=None, gt=0, strict=True)
    additional_tokens_out: Optional[int] = Field(default=None, gt=0, strict=True)
    additional_wall_seconds: Optional[int] = Field(default=None, gt=0, strict=True)
    approved: bool = True
    reason: str = Field(default="operator_budget_decision", min_length=1, max_length=500)


@app.get("/v1/control-plane/runs/{run_id}/budget")
async def get_run_budget_endpoint(run_id: str) -> Any:
    return await BudgetGovernor(get_run_service().store).get_status(run_id)


@app.post("/v1/control-plane/runs/{run_id}/budget/extend")
async def extend_run_budget_endpoint(run_id: str, payload: BudgetExtendPayload) -> Any:
    return await BudgetGovernor(get_run_service().store).extend(
        run_id,
        payload.additional_usd,
        additional_tokens_in=payload.additional_tokens_in,
        additional_tokens_out=payload.additional_tokens_out,
        additional_wall_seconds=payload.additional_wall_seconds,
        approved=payload.approved,
        actor=app.state.local_principal_id,
        reason=payload.reason,
    )


class PRPackageBuildPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_branch: Optional[str] = Field(default=None, min_length=1, max_length=256)
    create_git_branch: bool = True


class PRPackagePublishPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorized: bool = False
    policy_authorized: Optional[bool] = None
    remote: str = Field(default="origin", min_length=1, max_length=128)


@app.get("/v1/control-plane/runs/{run_id}/pr-package")
async def get_pr_package_endpoint(run_id: str) -> Any:
    store = get_run_service().store
    if await store.get_run(run_id) is None:
        raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
    pkg = await PRPackager(store).get_package(run_id)
    if pkg is None:
        raise ContractViolation("resource_not_found", f"PR package not found for run '{run_id}'")
    return pkg


@app.post("/v1/control-plane/runs/{run_id}/pr-package", status_code=201)
async def build_pr_package_endpoint(
    run_id: str,
    payload: Optional[PRPackageBuildPayload] = None,
) -> Any:
    req = payload or PRPackageBuildPayload()
    runtime_dir = getattr(app.state, "pr_package_runtime_dir", None)
    return await PRPackager(get_run_service().store).build(
        run_id,
        pr_branch=req.pr_branch,
        create_git_branch=req.create_git_branch,
        runtime_dir=Path(runtime_dir) if runtime_dir is not None else None,
    )


@app.post("/v1/control-plane/runs/{run_id}/pr-package/publish")
async def publish_pr_package_endpoint(
    run_id: str,
    payload: Optional[PRPackagePublishPayload] = None,
) -> Any:
    store = get_run_service().store
    if await store.get_run(run_id) is None:
        raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
    packager = PRPackager(store)
    pkg = await packager.get_package(run_id)
    if pkg is None:
        raise ContractViolation("resource_not_found", f"PR package not found for run '{run_id}'")
    req = payload or PRPackagePublishPayload()
    return await packager.publish(
        pkg.package_id,
        authorized=req.authorized,
        policy_authorized=req.policy_authorized,
        remote=req.remote,
        actor=app.state.local_principal_id,
    )


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
        "registry_invalid",
        "authorization_invalid",
        "discovery_invalid",
        "certification_invalid",
        "preference_invalid",
        "opt_in_required",
        "budget_invalid",
        "packaging_invalid",
        "amendment_invalid",
        "invalid_wave0_task",
        "invalid_repair_budget",
        "amendment_handler_missing",
        "secret_in_payload",
        "secret_in_profile",
        "secret_unavailable",
        "secret_value_rejected",
        "token_invalid",
        "message_invalid",
    }
    conflict_codes |= {
        "session_state_conflict",
        "thread_state_conflict",
        "hitl_pending",
        "hitl_busy",
        "hitl_conflict",
        "consent_required",
        "consent_conflict",
        "memory_conflict",
        "explicit_preference_precedence",
        "workspace_archived",
        "registry_conflict",
        "driver_not_certified",
        "certification_stale",
        "executor_unavailable",
        "component_revoked",
        "component_untrusted",
        "discovery_changed",
        "discovery_untrusted",
        "extension_revoked",
        "extension_quarantined",
        "extension_not_active",
        "rollback_unavailable",
        "profile_integrity",
        "profile_snapshot_conflict",
        "profile_snapshot_late",
        "transport_uncertified",
        "budget_exhausted",
        "budget_frozen",
        "pr_package_exists",
        "packaging_branch_conflict",
        "amendment_not_proposed",
        "amendment_check_failed",
        "amendment_command_failed",
        "revalidation_base_mismatch",
        "empty_patch",
        "a11y_contract_violation",
    }
    forbidden_codes = {
        "authorization_denied",
        "session_scope_mismatch",
        "thread_scope_mismatch",
        "metric_scope_mismatch",
        "discovery_scope",
        "discovery_disabled",
        "extension_permission_denied",
        "publish_not_authorized",
        "profile_scope_mismatch",
    }
    if exc.code in forbidden_codes:
        status_code = 403
    elif exc.code == "resource_not_found":
        status_code = 404
    elif exc.code == "cursor_expired":
        status_code = 410
    elif exc.code == "invalid_cursor":
        status_code = 400
    elif exc.code in conflict_codes:
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
