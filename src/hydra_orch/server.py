"""FastAPI OpenAI-compatible proxy server for hydra-orch."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from hydra_orch.config import ConfigError, HydraConfig, load_config
from hydra_orch.core.router import HydraRouter
from hydra_orch.core.ssh_tunnel import SshTunnelManager
from hydra_orch.model import (
    ChatChoice,
    ChatChoiceDelta,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelCard,
    ModelListResponse,
)

logger = logging.getLogger(__name__)

config = load_config()
router = HydraRouter(config)
ssh_manager: SshTunnelManager | None = None
ssh_remote = config.remote_ssh_gpu
if ssh_remote.enabled:
    ssh_manager = SshTunnelManager(ssh_remote.model_dump())

app = FastAPI(
    title=config.server.title,
    description=config.server.description,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    await router.ensure_gateway()
    await router.checkpointer.initialize()
    if ssh_manager:
        ssh_manager.start_tunnel()
    logger.info("Hydra Orchestrator server started successfully.")


@app.on_event("shutdown")
def shutdown_event() -> None:
    if ssh_manager:
        ssh_manager.stop_tunnel()
    logger.info("Hydra Orchestrator server stopped.")


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
    # Model name can encode mode: e.g. "hydra-swarm"
    if request.model == "hydra-swarm":
        request.mode = "swarm"
    elif request.model == "hydra-relay":
        request.mode = "relay"
    elif request.model == "hydra-persistent":
        request.mode = "persistent"

    router.validate_request(request)
    await router.ensure_gateway()

    # If stream requested, stream SSE format
    if request.stream:
        async def event_generator() -> AsyncIterator[str]:
            async for chunk in router.stream_chat_completion(request):
                chunk_obj = ChatCompletionChunk(
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

    # Non-streaming response: collect all chunks and return complete response
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


@app.get("/v1/control-plane/bootstrap")
async def control_plane_bootstrap() -> Dict[str, Any]:
    """Expose non-secret capability metadata for future visual clients.

    It reports configured capabilities rather than claiming that an executor,
    provider, or UI client is already running.
    """
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
            "projects": False,
            "runs": False,
            "worktrees": False,
            "diffs": False,
        },
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


@app.exception_handler(ConfigError)
async def configuration_error_handler(request: Request, exc: ConfigError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={
        "code": exc.code, "message": str(exc), "run_id": None, "retryable": False,
    })


def start_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run uvicorn server directly."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)
