"""Tests for FastAPI proxy server initialization and endpoints."""

import pytest
from fastapi.testclient import TestClient
from hydra_orch.server import app, config, router
from hydra_orch.core.ssh_tunnel import SshTunnelManager


def test_server_metadata_and_routes():
    """Verify that the FastAPI application initializes with correct metadata and routes."""
    assert app.title == "Hydra Orchestrator API"
    assert app.version == "0.1.0"
    assert app.description is not None

    route_paths = [route.path for route in app.routes]
    assert "/health" in route_paths
    assert "/v1/health" in route_paths
    assert "/v1/models" in route_paths
    assert "/v1/chat/completions" in route_paths
    assert "/v1/orchestrator/status" in route_paths
    assert "/v1/control-plane/bootstrap" in route_paths


def test_server_health_endpoints():
    """Verify that /health and /v1/health return healthy status with adapter map."""
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["default_mode"] in ("relay", "swarm", "persistent")
    assert "adapters" in data
    assert isinstance(data["adapters"], dict)

    # Alias /v1/health should yield identical status
    v1_response = client.get("/v1/health")
    assert v1_response.status_code == 200
    assert v1_response.json()["status"] == "healthy"


def test_server_models_endpoint():
    """Verify that /v1/models returns OpenAI-compatible ModelListResponse."""
    client = TestClient(app)

    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data.get("object") == "list"
    assert isinstance(data.get("data"), list)

    model_ids = [m["id"] for m in data["data"]]
    # Base orchestration models must be present
    assert "hydra-default" in model_ids
    assert "hydra-swarm" not in model_ids
    assert "hydra-relay" in model_ids
    assert "hydra-persistent" in model_ids


def test_server_orchestrator_status_endpoint():
    """Verify /v1/orchestrator/status returns internal architecture metrics."""
    client = TestClient(app)

    response = client.get("/v1/orchestrator/status")
    assert response.status_code == 200
    data = response.json()
    assert "default_mode" in data
    assert data["worktrees_dir"] in (".orchestrator/worktree", ".hydra/worktree")
    assert "adapters_count" in data
    assert data["adapters_count"] > 0
    assert "ssh_tunnel_active" in data
    assert data["ssh_tunnel_active"] is False


def test_control_plane_bootstrap_reports_configuration_without_claiming_runtime():
    client = TestClient(app)

    response = client.get("/v1/control-plane/bootstrap")

    assert response.status_code == 200
    data = response.json()
    assert data["api_version"] == "v1"
    assert "ui" in data
    assert "omniroute" in data["integrations"]
    assert data["implemented_read_models"]["health"] is True
    assert data["implemented_read_models"]["runs"] is False


def test_ssh_tunnel_instantiation_conditions():
    """Verify that SshTunnelManager is created only when ssh_remote is enabled."""
    from hydra_orch.config import RemoteLocalConfig

    # Scenario 1: Disabled (default config state)
    disabled_cfg = RemoteLocalConfig(enabled=False, host="gpu-node.local")
    manager_1 = None
    if disabled_cfg and getattr(disabled_cfg, "enabled", False):
        manager_1 = SshTunnelManager(disabled_cfg.model_dump())
    assert manager_1 is None

    # Scenario 2: Enabled
    enabled_cfg = RemoteLocalConfig(enabled=True, host="gpu-node.local", port=2222)
    manager_2 = None
    if enabled_cfg and getattr(enabled_cfg, "enabled", False):
        manager_2 = SshTunnelManager(enabled_cfg.model_dump())
    assert manager_2 is not None
    assert isinstance(manager_2, SshTunnelManager)
    assert manager_2.host == "gpu-node.local"
    assert manager_2.port == 2222


def test_missing_provider_is_structured_503_before_stream(monkeypatch):
    monkeypatch.setattr(router, "adapters", {})
    response = TestClient(app).post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "test"}], "stream": True,
    })
    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"
    assert "traceback" not in response.text.lower()


def test_swarm_inference_request_rejected_without_git_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Inference must not create worktrees")
    monkeypatch.setattr(router.swarm, "create_worktree", forbidden)
    response = TestClient(app).post("/v1/chat/completions", json={
        "model": "hydra-swarm", "messages": [{"role": "user", "content": "test"}],
    })
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_mode"


def test_quota_disabled_has_no_http_calls(monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled gateway must not make HTTP calls")
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    response = TestClient(app).get("/v1/quota")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert response.json()["claude_pro"]["remaining_percent"] is None


@pytest.mark.asyncio
async def test_required_gateway_failure_precedes_startup_side_effects(monkeypatch):
    from hydra_orch.config import GatewayUnavailableError
    from hydra_orch.server import startup_event

    async def unavailable():
        raise GatewayUnavailableError("Required gateway unavailable")
    async def forbidden():
        pytest.fail("Startup must stop before checkpoint initialization")

    monkeypatch.setattr(router, "ensure_gateway", unavailable)
    monkeypatch.setattr(router.checkpointer, "initialize", forbidden)
    with pytest.raises(GatewayUnavailableError):
        await startup_event()
