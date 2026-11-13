"""Tests for FastAPI proxy server initialization and M1 Control Plane endpoints (T01 / T07)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Tuple

import pytest
from fastapi.testclient import TestClient as BaseTestClient
from hydra_orch.core.auth import TokenVerifier

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.run_service import RunService
from hydra_orch.core.ssh_tunnel import SshTunnelManager
from hydra_orch.server import app, config, get_run_service, router, set_run_service


def _init_temp_git_repo(base_dir: Path) -> Tuple[Path, str]:
    repo = base_dir / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@hydra.local"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra Server Test"], cwd=repo, check=True, capture_output=True)
    if os.name == "nt":
        subprocess.run(["git", "config", "core.longpaths", "true"], cwd=repo, check=True, capture_output=True)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "calc.py").write_text("def double(x: int) -> int:\n    return x\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, sha


TEST_API_TOKEN = "hydra-test-local-bearer-token-0123456789"
TEST_VERIFIER = TokenVerifier.from_token(TEST_API_TOKEN)


def TestClient(application):
    return BaseTestClient(application, headers={"Authorization": f"Bearer {TEST_API_TOKEN}"})


@pytest.fixture(autouse=True)
def authenticated_api(monkeypatch):
    monkeypatch.setitem(app.state._state, "token_verifier", TEST_VERIFIER)
    monkeypatch.setenv("HYDRA_API_TOKEN", TEST_API_TOKEN)
    monkeypatch.delenv("HYDRA_API_TOKEN_HASH", raising=False)


@pytest.fixture
def isolated_run_service(tmp_path: Path):
    repo, base_sha = _init_temp_git_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    set_run_service(svc)
    prev_expired = dict(getattr(app.state, "expired_cursors", {}))
    app.state.expired_cursors = {}
    try:
        yield svc, repo, base_sha
    finally:
        set_run_service(None)
        app.state.expired_cursors = prev_expired


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
    assert "/v1/control-plane/projects" in route_paths
    assert "/v1/control-plane/runs" in route_paths


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
    assert data["implemented_read_models"]["runs"] is True
    assert data["implemented_read_models"]["projects"] is True
    assert data["implemented_read_models"]["worktrees"] is True
    assert data["implemented_read_models"]["diffs"] is True


def test_ssh_tunnel_instantiation_conditions():
    """Verify that SshTunnelManager is created only when ssh_remote is enabled."""
    from hydra_orch.config import RemoteLocalConfig

    disabled_cfg = RemoteLocalConfig(enabled=False, host="gpu-node.local")
    manager_1 = None
    if disabled_cfg and getattr(disabled_cfg, "enabled", False):
        manager_1 = SshTunnelManager(disabled_cfg.model_dump())
    assert manager_1 is None

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


# ============================================================================
# T07 CONTROL PLANE TESTS (RF01-RF08, RF13, RF15 / RT10, RT11)
# ============================================================================

def test_create_project_valid_root(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    resp = client.post(
        "/v1/control-plane/projects",
        json={
            "canonical_root": str(repo),
            "name": "hydra-fixture",
            "base_branch": "main",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "hydra-fixture"
    assert data["base_sha"] == base_sha
    assert os.path.normcase(data["canonical_root"]) == os.path.normcase(str(repo))

    get_resp = client.get(f"/v1/control-plane/projects/{data['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == data["id"]

    # Duplicate registration for same root returns 409 Conflict
    dup_resp = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(repo), "name": "dup"},
    )
    assert dup_resp.status_code == 409


def test_create_project_invalid_root(isolated_run_service, tmp_path: Path):
    client = TestClient(app)
    non_git_dir = tmp_path / "not_a_git_repo"
    non_git_dir.mkdir(parents=True, exist_ok=True)

    resp1 = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(non_git_dir), "name": "invalid-repo"},
    )
    assert resp1.status_code == 400
    assert resp1.json()["code"] == "workspace_invalid"

    # Path traversal '..' rejected with 400
    resp2 = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": f"{non_git_dir}/../repo", "name": "traversal"},
    )
    assert resp2.status_code == 400
    assert resp2.json()["code"] == "workspace_invalid"


def test_create_run_idempotent(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    payload = {
        "project_id": "proj-idem",
        "objective": "Implement idempotent run creation",
        "mode": "relay",
        "task_spec": {
            "task_id": "t-idem",
            "objective": "Implement idempotent task",
            "acceptance_criteria": [
                {"check_id": "chk-1", "command": [sys.executable, "-c", "print('ok')"]}
            ],
            "allowed_paths": ["src/*"],
        },
    }
    headers = {"Idempotency-Key": "idem-key-1234567890abcdef"}

    r1 = client.post("/v1/control-plane/runs", json=payload, headers=headers)
    assert r1.status_code == 202
    d1 = r1.json()
    assert d1["created"] is True
    assert d1["status"] == "queued"

    r2 = client.post("/v1/control-plane/runs", json=payload, headers=headers)
    assert r2.status_code == 202
    d2 = r2.json()
    assert d2["run_id"] == d1["run_id"]
    assert d2["created"] is False

    list_resp = client.get("/v1/control-plane/runs?project_id=proj-idem")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


def test_create_run_idempotent_conflict(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    headers = {"Idempotency-Key": "idem-conflict-key-999999"}
    payload_a = {
        "project_id": "proj-conflict",
        "objective": "First objective for idempotency key",
        "mode": "relay",
        "task_spec": {
            "task_id": "t-1",
            "objective": "First task objective",
            "acceptance_criteria": [
                {"check_id": "chk-1", "command": [sys.executable, "-c", "print(1)"]}
            ],
        },
    }
    payload_b = {
        **payload_a,
        "objective": "Mutated objective reusing the exact same idempotency key",
    }

    r1 = client.post("/v1/control-plane/runs", json=payload_a, headers=headers)
    assert r1.status_code == 202

    r2 = client.post("/v1/control-plane/runs", json=payload_b, headers=headers)
    assert r2.status_code == 409
    err = r2.json()
    assert err["code"] == "idempotency_conflict"
    assert err["retryable"] is False


def test_run_with_executor_config(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    worker_py = (
        "from pathlib import Path\n"
        "Path('src/calc.py').write_text('def double(x: int) -> int:\\n    return x * 2\\n', encoding='utf-8')\n"
    )
    payload = {
        "run_id": "run-exec-cfg",
        "project_id": "proj-exec",
        "objective": "Fix double() implementation via configured executor",
        "mode": "relay",
        "execute": True,
        "custom_command": [sys.executable, "-c", worker_py],
        "task_spec": {
            "task_id": "t-calc",
            "objective": "Fix double(x) in src/calc.py",
            "allowed_paths": ["src/*"],
            "acceptance_criteria": [
                {
                    "check_id": "chk-calc",
                    "command": [sys.executable, "-c", "from src.calc import double; assert double(4) == 8"],
                }
            ],
        },
        "idempotency_key": "idem-exec-cfg-0001",
    }

    resp = client.post("/v1/control-plane/runs", json=payload)
    assert resp.status_code == 202
    assert resp.json()["status"] == "reviewing"

    tasks_resp = client.get("/v1/control-plane/runs/run-exec-cfg/tasks")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "ready_for_review"
    assert tasks[0]["current_attempt"]["result"]["outcome"] == "success"

    arts_resp = client.get("/v1/control-plane/runs/run-exec-cfg/artifacts?kind=patch")
    assert arts_resp.status_code == 200
    patches = arts_resp.json()
    assert len(patches) == 1
    assert patches[0]["kind"] == "patch"


def test_review_accepted(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    worker_py = (
        "from pathlib import Path\n"
        "Path('src/calc.py').write_text('def double(x: int) -> int:\\n    return x * 2\\n', encoding='utf-8')\n"
    )
    client.post(
        "/v1/control-plane/runs",
        json={
            "run_id": "run-rev-acc",
            "project_id": "proj-rev",
            "objective": "Implement feature and accept review",
            "execute": True,
            "custom_command": [sys.executable, "-c", worker_py],
            "task_spec": {
                "task_id": "t-acc",
                "objective": "Update src/calc.py",
                "allowed_paths": ["src/*"],
                "acceptance_criteria": [
                    {"check_id": "chk-1", "command": [sys.executable, "-c", "from src.calc import double; assert double(3) == 6"]}
                ],
            },
            "idempotency_key": "idem-rev-acc-0001",
        },
    )

    # Stale/wrong expected_revision -> 409 Conflict
    stale_resp = client.post(
        "/v1/control-plane/runs/run-rev-acc/tasks/t-acc/review",
        json={"decision": "accepted", "reason": "stale revision", "expected_revision": 99},
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["code"] == "optimistic_lock_conflict"

    # Valid review -> 200 OK
    rev_resp = client.post(
        "/v1/control-plane/runs/run-rev-acc/tasks/t-acc/review",
        json={"decision": "accepted", "reason": "All checks verified", "expected_revision": 1},
    )
    assert rev_resp.status_code == 200
    rev_data = rev_resp.json()
    assert rev_data["decision"] == "accepted"
    assert rev_data["task_status"] == "accepted"
    assert rev_data["revision"] == 2

    # Integrate accepted run -> 200 OK
    int_resp = client.post("/v1/control-plane/runs/run-rev-acc/integrate", json={})
    assert int_resp.status_code == 200
    assert int_resp.json()["status"] == "succeeded"
    assert int_resp.json()["result_sha"] is not None


def test_review_rejected(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    worker_py = (
        "from pathlib import Path\n"
        "Path('src/calc.py').write_text('def double(x: int) -> int:\\n    return x + x\\n', encoding='utf-8')\n"
    )
    client.post(
        "/v1/control-plane/runs",
        json={
            "run_id": "run-rev-rej",
            "project_id": "proj-rev",
            "objective": "Implement feature and reject review",
            "execute": True,
            "custom_command": [sys.executable, "-c", worker_py],
            "task_spec": {
                "task_id": "t-rej",
                "objective": "Update src/calc.py",
                "allowed_paths": ["src/*"],
                "acceptance_criteria": [
                    {"check_id": "chk-1", "command": [sys.executable, "-c", "from src.calc import double; assert double(5) == 10"]}
                ],
            },
            "idempotency_key": "idem-rev-rej-0001",
        },
    )

    rev_resp = client.post(
        "/v1/control-plane/runs/run-rev-rej/tasks/t-rej/review",
        json={"decision": "rejected", "reason": "Prefer multiplication operator", "expected_revision": 1},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["decision"] == "rejected"
    assert rev_resp.json()["task_status"] == "rejected"

    # Integration must fail with 409 because result is rejected
    int_resp = client.post("/v1/control-plane/runs/run-rev-rej/integrate", json={})
    assert int_resp.status_code == 409
    assert int_resp.json()["code"] == "result_not_accepted"


def test_sse_replay_cursor(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    worker_py = (
        "from pathlib import Path\n"
        "Path('src/calc.py').write_text('def double(x: int) -> int:\\n    return x * 2\\n', encoding='utf-8')\n"
    )
    client.post(
        "/v1/control-plane/runs",
        json={
            "run_id": "run-sse-1",
            "project_id": "proj-sse",
            "objective": "Generate events for SSE replay",
            "execute": True,
            "custom_command": [sys.executable, "-c", worker_py],
            "task_spec": {
                "task_id": "t-sse",
                "objective": "Modify src/calc.py",
                "allowed_paths": ["src/*"],
                "acceptance_criteria": [
                    {"check_id": "chk-1", "command": [sys.executable, "-c", "print('ok')"]}
                ],
            },
            "idempotency_key": "idem-sse-cursor-0001",
        },
    )

    # Full stream without cursor
    full_resp = client.get("/v1/control-plane/runs/run-sse-1/events")
    assert full_resp.status_code == 200
    assert "text/event-stream" in full_resp.headers["content-type"]

    full_ids = [
        int(line.split(":", 1)[1].strip())
        for line in full_resp.text.splitlines()
        if line.startswith("id: ")
    ]
    assert len(full_ids) >= 4
    assert full_ids == list(range(1, len(full_ids) + 1))

    # Replay with Last-Event-ID: 2 returns only seq > 2
    replay_resp = client.get(
        "/v1/control-plane/runs/run-sse-1/events",
        headers={"Last-Event-ID": "2"},
    )
    assert replay_resp.status_code == 200
    replay_ids = [
        int(line.split(":", 1)[1].strip())
        for line in replay_resp.text.splitlines()
        if line.startswith("id: ")
    ]
    assert replay_ids == [seq for seq in full_ids if seq > 2]

    # Expired cursor returns 410 Gone
    app.state.expired_cursors["run-sse-1"] = 3
    expired_resp = client.get(
        "/v1/control-plane/runs/run-sse-1/events",
        headers={"Last-Event-ID": "1"},
    )
    assert expired_resp.status_code == 410
    assert expired_resp.json()["code"] == "cursor_expired"


def test_cancel_run(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    client.post(
        "/v1/control-plane/runs",
        json={
            "run_id": "run-cancel-1",
            "project_id": "proj-cancel",
            "objective": "Test run cancellation",
            "task_spec": {
                "task_id": "t-cancel",
                "objective": "Pending task to cancel",
                "acceptance_criteria": [
                    {"check_id": "chk-1", "command": [sys.executable, "-c", "print(1)"]}
                ],
            },
            "idempotency_key": "idem-cancel-0001",
        },
    )

    c_resp = client.post("/v1/control-plane/runs/run-cancel-1/cancel", json={"scope": "run"})
    assert c_resp.status_code == 200
    assert c_resp.json()["status"] == "cancelled"

    detail = client.get("/v1/control-plane/runs/run-cancel-1").json()
    assert detail["status"] == "cancelled"
    assert detail["tasks"][0]["status"] == "cancelled"

    # Cancelling an already terminal run returns 409 Conflict
    c_again = client.post("/v1/control-plane/runs/run-cancel-1/cancel", json={"scope": "run"})
    assert c_again.status_code == 409
    assert c_again.json()["code"] == "invalid_run_state"


def test_cancel_task_in_swarm(isolated_run_service):
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    client.post(
        "/v1/control-plane/runs",
        json={
            "run_id": "run-swarm-cancel",
            "project_id": "proj-swarm",
            "objective": "Swarm run with two independent tasks",
            "mode": "swarm",
            "tasks": [
                {
                    "task_id": "t-keep",
                    "objective": "Keep this task pending",
                    "allowed_paths": ["src/keep.py"],
                    "acceptance_criteria": [
                        {"check_id": "chk-k", "command": [sys.executable, "-c", "print(1)"]}
                    ],
                },
                {
                    "task_id": "t-drop",
                    "objective": "Cancel only this task",
                    "allowed_paths": ["src/drop.py"],
                    "acceptance_criteria": [
                        {"check_id": "chk-d", "command": [sys.executable, "-c", "print(2)"]}
                    ],
                },
            ],
            "idempotency_key": "idem-swarm-cancel-0001",
        },
    )

    c_resp = client.post(
        "/v1/control-plane/runs/run-swarm-cancel/cancel",
        json={"scope": "task", "task_id": "t-drop", "reason": "drop_single_task"},
    )
    assert c_resp.status_code == 200
    assert c_resp.json()["task_id"] == "t-drop"
    assert c_resp.json()["task_status"] == "cancelled"

    tasks = {
        t["id"]: t["status"]
        for t in client.get("/v1/control-plane/runs/run-swarm-cancel/tasks").json()
    }
    assert tasks["t-drop"] == "cancelled"
    assert tasks["t-keep"] == "pending"


def test_auth_required(isolated_run_service):
    client = BaseTestClient(app)

    # Without Authorization header -> 401
    r_no_auth = client.get("/v1/control-plane/runs")
    assert r_no_auth.status_code == 401
    assert r_no_auth.json()["code"] == "unauthorized"

    # With wrong token -> 401
    r_bad = client.get(
        "/v1/control-plane/runs",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r_bad.status_code == 401

    # With valid token -> 200
    r_ok = client.get(
        "/v1/control-plane/runs",
        headers={"Authorization": "Bearer hydra-test-local-bearer-token-0123456789"},
    )
    assert r_ok.status_code == 200


def test_cors_strict_allowlist(isolated_run_service):
    client = TestClient(app)

    # Disallowed external origin -> 403 Forbidden
    r_evil = client.get(
        "/v1/control-plane/bootstrap",
        headers={"Origin": "https://malicious.example.com"},
    )
    assert r_evil.status_code == 403
    assert r_evil.json()["code"] == "cors_origin_forbidden"

    # Wildcard origin -> 403 Forbidden
    r_wild = client.get(
        "/v1/control-plane/bootstrap",
        headers={"Origin": "*"},
    )
    assert r_wild.status_code == 403

    # Allowed local origin -> 200 OK
    r_local = client.get(
        "/v1/control-plane/bootstrap",
        headers={"Origin": "http://127.0.0.1:8000"},
    )
    assert r_local.status_code == 200


def test_ui_commands_same_service(isolated_run_service):
    """Verify that API endpoints and CLI commands operate on the exact same RunService and SQLite store."""
    from typer.testing import CliRunner
    from hydra_orch import cli

    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)
    cli_runner = CliRunner()

    assert get_run_service() is svc

    # 1. Submit run via CLI
    cli_res = cli_runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Shared service verification between CLI and HTTP API",
            "--project-id",
            "proj-shared",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--task-id",
            "t-shared",
            "--idempotency-key",
            "idem-shared-service-01",
            "--json",
        ],
    )
    assert cli_res.exit_code == 0
    submitted = json.loads(cli_res.stdout)
    run_id = submitted["run_id"]

    # 2. Query the same run via HTTP API
    api_detail = client.get(f"/v1/control-plane/runs/{run_id}")
    assert api_detail.status_code == 200
    assert api_detail.json()["run_id"] == run_id
    assert api_detail.json()["objective"] == "Shared service verification between CLI and HTTP API"

    # 3. Cancel via HTTP API and verify via CLI inspect
    cancel_resp = client.post(f"/v1/control-plane/runs/{run_id}/cancel", json={"scope": "run"})
    assert cancel_resp.status_code == 200

    inspect_res = cli_runner.invoke(cli.app, ["inspect", run_id, "--json"])
    assert inspect_res.exit_code == 0
    inspected = json.loads(inspect_res.stdout)
    assert inspected["status"] == "cancelled"


def test_discard_preserves_retention(isolated_run_service):
    """Verify explicit runtime discard refuses active runs, checks SHA-256 integrity, and retains evidence."""
    svc, repo, base_sha = isolated_run_service
    client = TestClient(app)

    worker_py = (
        "from pathlib import Path\n"
        "Path('src/calc.py').write_text('def double(x: int) -> int:\\n    return x * 2\\n', encoding='utf-8')\n"
    )
    client.post(
        "/v1/control-plane/runs",
        json={
            "run_id": "run-discard-1",
            "project_id": "proj-discard",
            "objective": "Test runtime discard with retention check",
            "execute": True,
            "custom_command": [sys.executable, "-c", worker_py],
            "task_spec": {
                "task_id": "t-disc",
                "objective": "Update src/calc.py",
                "allowed_paths": ["src/*"],
                "acceptance_criteria": [
                    {"check_id": "chk-1", "command": [sys.executable, "-c", "print('ok')"]}
                ],
            },
            "idempotency_key": "idem-discard-0001",
        },
    )

    # Cannot discard while run is still in 'reviewing' (non-terminal) without force
    active_disc = client.post("/v1/control-plane/runs/run-discard-1/discard", json={"force": False})
    assert active_disc.status_code == 409
    assert active_disc.json()["code"] == "invalid_run_state"

    # Cancel run to make it terminal
    client.post("/v1/control-plane/runs/run-discard-1/cancel", json={"scope": "run"})

    # Discard runtime now succeeds and retains all artifacts in store and disk
    ok_disc = client.post("/v1/control-plane/runs/run-discard-1/discard", json={"force": False})
    assert ok_disc.status_code == 200
    disc_data = ok_disc.json()
    assert disc_data["status"] == "discarded"
    assert disc_data["retained_artifacts_count"] >= 3

    arts = client.get("/v1/control-plane/runs/run-discard-1/artifacts").json()
    assert len(arts) == disc_data["retained_artifacts_count"]

    # Tamper with a retained artifact on disk -> discard detects SHA-256 mismatch (409 artifact_tampered)
    patch_art = next(a for a in arts if a["kind"] == "patch")
    (repo / patch_art["relative_path"]).write_bytes(b"corrupted-bytes")
    tampered_disc = client.post("/v1/control-plane/runs/run-discard-1/discard", json={"force": True})
    assert tampered_disc.status_code == 409
    assert tampered_disc.json()["code"] == "artifact_tampered"


def _init_extra_repo(base_dir: Path, name: str) -> tuple[Path, str]:
    repo = base_dir / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra Test Operator"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "operator@hydra.local"], cwd=str(repo), check=True, capture_output=True)
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo), text=True).strip()
    return repo, sha


def _write_cert_report(cert_root: Path, filename: str, payload: dict) -> Path:
    cert_root.mkdir(parents=True, exist_ok=True)
    path = cert_root / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_multi_repo_project(isolated_run_service, tmp_path: Path):
    _svc, repo_root, _base_sha = isolated_run_service
    client = TestClient(app)
    parent_root = repo_root.parent
    repo_two, sha_two = _init_extra_repo(parent_root, "repo-two")

    old_roots = getattr(app.state, "workspace_allowed_roots", None)
    app.state.workspace_allowed_roots = [repo_root, repo_two]
    try:
        area_resp = client.post("/v1/control-plane/areas", json={"name": "Engineering", "description": "Main area"})
        assert area_resp.status_code == 201, area_resp.text
        area = area_resp.json()

        areas_resp = client.get("/v1/control-plane/areas")
        assert areas_resp.status_code == 200
        assert any(a["id"] == area["id"] for a in areas_resp.json())

        ws_resp = client.post("/v1/control-plane/workspaces", json={"area_id": area["id"], "name": "Backend"})
        assert ws_resp.status_code == 201, ws_resp.text
        ws = ws_resp.json()

        ws_list = client.get("/v1/control-plane/workspaces", params={"area_id": area["id"]})
        assert ws_list.status_code == 200
        assert len(ws_list.json()) == 1

        proj_resp = client.post(
            "/v1/control-plane/projects",
            json={
                "workspace_id": ws["id"],
                "name": "hydra-multi",
                "canonical_root": str(repo_root),
                "base_branch": "main",
            },
        )
        assert proj_resp.status_code == 201, proj_resp.text
        project = proj_resp.json()

        r1 = client.post(
            f"/v1/control-plane/projects/{project['id']}/repositories",
            json={"root_canonical": str(repo_root), "scopes": ["read", "write"], "allowed_paths": ["src/*"]},
        )
        r2 = client.post(
            f"/v1/control-plane/projects/{project['id']}/repositories",
            json={"root_canonical": str(repo_two), "scopes": ["read"], "allowed_paths": ["*"], "base_sha": sha_two},
        )
        assert r1.status_code == 201, r1.text
        assert r2.status_code == 201, r2.text

        repos_resp = client.get(f"/v1/control-plane/projects/{project['id']}/repositories")
        assert repos_resp.status_code == 200
        assert len(repos_resp.json()) == 2

        repo1_id = r1.json()["id"]
        grant_resp = client.post(
            f"/v1/control-plane/repositories/{repo1_id}/grant",
            json={"authorized_principal_id": "reviewer-1", "scopes": ["read"]},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        auth_id = grant_resp.json()["authorization_id"]

        revoke_resp = client.post(
            f"/v1/control-plane/repositories/{repo1_id}/revoke",
            json={"authorization_id": auth_id},
        )
        assert revoke_resp.status_code == 200, revoke_resp.text
        assert revoke_resp.json()["revoked"] is True

        arch_resp = client.post(
            f"/v1/control-plane/workspaces/{ws['id']}/archive",
            json={"expected_revision": ws["revision"]},
        )
        assert arch_resp.status_code == 200, arch_resp.text

        blocked_proj = client.post(
            "/v1/control-plane/projects",
            json={"workspace_id": ws["id"], "name": "blocked", "canonical_root": str(repo_root)},
        )
        assert blocked_proj.status_code == 409
        assert blocked_proj.json()["code"] == "workspace_archived"
    finally:
        app.state.workspace_allowed_roots = old_roots


def test_profile_resolve_pre_exec(isolated_run_service, tmp_path: Path):
    _svc, repo_root, _base_sha = isolated_run_service
    client = TestClient(app)
    cert_root = tmp_path / "certs"
    fake_bin = tmp_path / "bin" / "codex"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")

    old_cert_root = getattr(app.state, "certification_root", None)
    old_locator = getattr(app.state, "executable_locator", None)
    old_ws_roots = getattr(app.state, "workspace_allowed_roots", None)
    app.state.certification_root = cert_root
    app.state.executable_locator = lambda exe: str(fake_bin) if exe == "codex" else None
    app.state.workspace_allowed_roots = [repo_root]
    try:
        area = client.post("/v1/control-plane/areas", json={"name": "ProfilesArea"}).json()
        ws = client.post("/v1/control-plane/workspaces", json={"area_id": area["id"], "name": "ProfWS"}).json()
        proj = client.post(
            "/v1/control-plane/projects",
            json={"workspace_id": ws["id"], "name": "prof-proj", "canonical_root": str(repo_root)},
        ).json()
        repo = client.post(
            f"/v1/control-plane/projects/{proj['id']}/repositories",
            json={"root_canonical": str(repo_root), "scopes": ["read", "write", "execute"]},
        ).json()

        agent_payload = {
            "agent_id": "agent-codex-1",
            "name": "Codex Local",
            "version": "1.0.0",
            "driver_type": "codex",
            "declared_capabilities": ["workspace_execution", "cancel_process_tree", "tool_execution"],
        }
        reg_resp = client.post("/v1/control-plane/agents", json=agent_payload)
        assert reg_resp.status_code == 201, reg_resp.text

        agents_resp = client.get("/v1/control-plane/agents")
        assert agents_resp.status_code == 200
        assert any(a["agent_id"] == "agent-codex-1" for a in agents_resp.json())

        execs_resp = client.get("/v1/control-plane/executors")
        assert execs_resp.status_code == 200
        assert execs_resp.json()[0]["agent_id"] == "agent-codex-1"
        assert execs_resp.json()[0]["status"] == "unavailable"

        caps_resp = client.get("/v1/control-plane/capabilities")
        assert caps_resp.status_code == 200
        assert "drivers" in caps_resp.json()

        import platform as _platform
        from datetime import datetime, timezone
        from hydra_orch.core.agent_registry import CERTIFICATION_CHECKS

        report_path = _write_cert_report(
            cert_root,
            "codex.json",
            {
                "agent_id": "agent-codex-1",
                "driver_type": "codex",
                "agent_version": "1.0.0",
                "platform": _platform.system(),
                "executable_sha256": _sha256_bytes(fake_bin.read_bytes()),
                "capabilities": ["workspace_execution", "cancel_process_tree", "tool_execution"],
                "passed_checks": sorted(CERTIFICATION_CHECKS),
                "simulated": False,
                "issued_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        cert_resp = client.post(
            "/v1/control-plane/agents/agent-codex-1/certificate",
            json={"report_path": str(report_path)},
        )
        assert cert_resp.status_code == 201, cert_resp.text

        profile_payload = {
            "profile_id": "prof-1",
            "name": "Safe Profile",
            "agent_ref": "agent-codex-1",
            "executor_ref": "agent-codex-1",
            "model_ref": "gpt-5-codex",
            "required_capabilities": ["workspace_execution", "cancel_process_tree"],
        }
        prof_resp = client.post("/v1/control-plane/profiles", json=profile_payload)
        assert prof_resp.status_code == 201, prof_resp.text

        profs_list = client.get("/v1/control-plane/profiles")
        assert profs_list.status_code == 200
        assert any(p["profile_id"] == "prof-1" for p in profs_list.json())

        resolved = client.post(
            "/v1/control-plane/profiles/prof-1/resolve",
            json={"repository_id": repo["id"]},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["profile"]["profile_id"] == "prof-1"
        assert resolved.json()["agent"]["definition"]["agent_id"] == "agent-codex-1"

        missing_prof = client.post(
            "/v1/control-plane/profiles/nonexistent/resolve",
            json={"repository_id": repo["id"]},
        )
        assert missing_prof.status_code == 404
    finally:
        app.state.certification_root = old_cert_root
        app.state.executable_locator = old_locator
        app.state.workspace_allowed_roots = old_ws_roots


def test_session_events_sse(isolated_run_service):
    _svc, repo_root, base_sha = isolated_run_service
    client = TestClient(app)
    proj = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(repo_root), "name": "sse-sess-proj", "base_branch": "main", "base_sha": base_sha},
    ).json()
    run_resp = client.post(
        "/v1/control-plane/runs",
        headers={"Idempotency-Key": "sse-sess-run-idem-0001"},
        json={
            "project_id": proj["id"],
            "objective": "Session SSE test",
            "mode": "relay",
            "execute": False,
            "task_spec": {"task_id": "t1", "objective": "op", "acceptance_criteria": [{"check_id": "c1", "command": ["echo", "ok"]}]},
        },
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["run_id"]

    sess_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/sessions",
        json={"origin_ref": "ui://panel"},
    )
    assert sess_resp.status_code == 201, sess_resp.text
    session_id = sess_resp.json()["id"]

    assert client.post(f"/v1/control-plane/runs/{run_id}/sessions/{session_id}/state", json={"state": "running", "expected_state": "created"}).status_code == 200
    th_resp = client.post(f"/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads", json={})
    assert th_resp.status_code == 201
    thread_id = th_resp.json()["id"]
    assert client.post(f"/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads/{thread_id}/state", json={"state": "running", "expected_state": "created"}).status_code == 200

    msg_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/sessions/{session_id}/threads/{thread_id}/messages",
        headers={"Idempotency-Key": "sess-msg-idem-00000001"},
        json={"content": "Hello session stream", "expected_last_seq": th_resp.json()["last_seq"]},
    )
    assert msg_resp.status_code == 200, msg_resp.text
    msg_seq = msg_resp.json()["seq"]

    top_sessions = client.get("/v1/control-plane/sessions")
    assert top_sessions.status_code == 200
    assert any(s["id"] == session_id for s in top_sessions.json())

    top_threads = client.get(f"/v1/control-plane/sessions/{session_id}/threads")
    assert top_threads.status_code == 200
    assert any(t["id"] == thread_id for t in top_threads.json())

    sse_all = client.get(f"/v1/control-plane/sessions/{session_id}/events")
    assert sse_all.status_code == 200
    assert f"id: {msg_seq}" in sse_all.text
    assert "event: heartbeat" in sse_all.text

    sse_resume = client.get(
        f"/v1/control-plane/sessions/{session_id}/events",
        headers={"Last-Event-ID": str(msg_seq - 1)},
    )
    assert sse_resume.status_code == 200
    assert f"id: {msg_seq}" in sse_resume.text

    old_cursors = getattr(app.state, "expired_cursors", {}).copy()
    app.state.expired_cursors = {session_id: msg_seq + 1}
    try:
        expired_resp = client.get(
            f"/v1/control-plane/sessions/{session_id}/events",
            headers={"Last-Event-ID": str(msg_seq)},
        )
        assert expired_resp.status_code == 410
        assert expired_resp.json()["code"] == "cursor_expired"
    finally:
        app.state.expired_cursors = old_cursors

    invalid_resp = client.get(
        f"/v1/control-plane/sessions/{session_id}/events",
        headers={"Last-Event-ID": "abc"},
    )
    assert invalid_resp.status_code == 400
    assert invalid_resp.json()["code"] == "invalid_cursor"
    assert client.get("/v1/control-plane/sessions/does-not-exist/events").status_code == 404


def test_discovery_approve_reject(isolated_run_service, tmp_path: Path):
    _svc, repo_root, _base_sha = isolated_run_service
    client = TestClient(app)
    skill_dir = repo_root / ".agents" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\nRun checks.\n", encoding="utf-8")

    mcp_file = repo_root / "mcp.json"
    mcp_file.write_text(
        json.dumps({"mcpServers": {"local-tools": {"command": "python", "args": ["-m", "http.server"]}}}),
        encoding="utf-8",
    )

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True, exist_ok=True)

    bad_scan = client.post("/v1/control-plane/discovery/scan", json={"authorized_root": str(outside_dir)})
    assert bad_scan.status_code == 403
    assert bad_scan.json()["code"] == "discovery_scope"

    disabled_scan = client.post("/v1/control-plane/discovery/scan", json={"authorized_root": str(repo_root), "opt_in": False})
    assert disabled_scan.status_code == 403
    assert disabled_scan.json()["code"] == "discovery_disabled"

    scan_resp = client.post("/v1/control-plane/discovery/scan", json={"authorized_root": str(repo_root)})
    assert scan_resp.status_code == 200, scan_resp.text
    discovered = scan_resp.json()
    assert len(discovered) >= 2

    listed = client.get("/v1/control-plane/discovery/resources")
    assert listed.status_code == 200
    assert len(listed.json()) == len(discovered)

    first, second = discovered[0], discovered[1]
    approve_resp = client.post(
        f"/v1/control-plane/discovery/resources/{first['discovery_id']}/approve",
        json={"expected_hash": first["content_hash"]},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["trust_status"] in {"approved", "active"}

    reject_resp = client.post(f"/v1/control-plane/discovery/resources/{second['discovery_id']}/reject")
    assert reject_resp.status_code == 200, reject_resp.text
    assert reject_resp.json()["trust_status"] == "rejected"


def test_skills_mcps_secrets_endpoints(isolated_run_service):
    _svc, _repo_root, _base_sha = isolated_run_service
    client = TestClient(app)

    raw_extra = client.post(
        "/v1/control-plane/secrets",
        json={"secret_name": "api", "provider_type": "env", "source_key": "API_KEY", "value": "sk-raw-secret-value-12345"},
    )
    assert raw_extra.status_code == 422

    raw_literal = client.post(
        "/v1/control-plane/secrets",
        json={"secret_name": "api", "provider_type": "env", "source_key": "sk-1234567890abcdef"},
    )
    assert raw_literal.status_code == 400
    assert raw_literal.json()["code"] == "secret_value_rejected"

    sec_resp = client.post(
        "/v1/control-plane/secrets",
        json={"secret_name": "github_token", "provider_type": "env", "source_key": "HYDRA_GH_TOKEN", "secret_id": "sec-gh-1"},
    )
    assert sec_resp.status_code == 201, sec_resp.text

    skill_payload = {
        "skill_id": "skill-1",
        "name": "code-lint",
        "version": "1.0.0",
        "manifest_ref": "skills/code-lint/SKILL.md",
        "permissions_declared": ["fs:read"],
        "checksum": _sha256_bytes(b"skill-1"),
    }
    sk_resp = client.post("/v1/control-plane/skills", json=skill_payload)
    assert sk_resp.status_code == 201, sk_resp.text

    mcp_payload = {
        "mcp_id": "mcp-1",
        "server_name": "github-mcp",
        "transport_type": "stdio",
        "endpoint": "stdio://github-mcp",
        "secret_ref": "sec-gh-1",
        "declared_tools": [{"name": "get_issue", "description": "Fetch issue"}],
        "permissions": ["secret:sec-gh-1"],
    }
    mcp_resp = client.post("/v1/control-plane/mcps", json=mcp_payload)
    assert mcp_resp.status_code == 201, mcp_resp.text

    assert any(s["skill_id"] == "skill-1" for s in client.get("/v1/control-plane/skills").json())
    assert any(m["mcp_id"] == "mcp-1" for m in client.get("/v1/control-plane/mcps").json())
    assert any(sec["secret_id"] == "sec-gh-1" for sec in client.get("/v1/control-plane/secrets").json())

    assert client.post("/v1/control-plane/skills/skill-1/revoke").json()["revoked"] is True
    assert client.post("/v1/control-plane/mcps/mcp-1/revoke").json()["revoked"] is True
    assert client.post("/v1/control-plane/secrets/sec-gh-1/revoke").json()["revoked"] is True
    assert any(s["skill_id"] == "skill-1" and s["revoked"] is True for s in client.get("/v1/control-plane/skills").json())


def test_extension_lifecycle(isolated_run_service, tmp_path: Path):
    _svc, repo_root, _base_sha = isolated_run_service
    client = TestClient(app)
    ext_dir = repo_root / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    ep1 = ext_dir / "ext_v1.py"
    ep2 = ext_dir / "ext_v2.py"
    b1 = b"def run(ctx):\n    return {'v': 1}\n"
    b2 = b"def run(ctx):\n    return {'v': 2}\n"
    ep1.write_bytes(b1)
    ep2.write_bytes(b2)

    m1 = {
        "extension_id": "ext-m1",
        "name": "sample-ext",
        "version": "1.0.0",
        "entrypoint": "extensions/ext_v1.py",
        "permissions_required": ["fs:read"],
        "compatible_api_version": "1.0",
        "checksum": _sha256_bytes(b1),
    }
    m2 = {
        "extension_id": "ext-m2",
        "name": "sample-ext",
        "version": "2.0.0",
        "entrypoint": "extensions/ext_v2.py",
        "permissions_required": ["fs:read"],
        "compatible_api_version": "1.0",
        "checksum": _sha256_bytes(b2),
    }

    reg_resp = client.post("/v1/control-plane/extensions", json=m1)
    assert reg_resp.status_code == 201, reg_resp.text

    c_req = client.post("/v1/control-plane/consents", json={"scope_type": "extension", "scope_id": "sample-ext"})
    assert c_req.status_code == 201, c_req.text
    consent_id = c_req.json()["consent_id"]

    unconsented = client.post(
        "/v1/control-plane/extensions/install",
        json={"manifest_id": "ext-m1", "consent_id": consent_id},
    )
    assert unconsented.status_code == 409
    assert unconsented.json()["code"] == "consent_required"

    c_grant = client.post(f"/v1/control-plane/consents/{consent_id}", json={"action": "granted"})
    assert c_grant.status_code == 200

    inst1 = client.post(
        "/v1/control-plane/extensions/install",
        json={"manifest_id": "ext-m1", "consent_id": consent_id, "activate": True},
    )
    assert inst1.status_code == 201, inst1.text
    assert inst1.json()["status"] == "active"

    inst2 = client.post(
        "/v1/control-plane/extensions/install",
        json={"manifest": m2, "consent_id": consent_id, "activate": True},
    )
    assert inst2.status_code == 201, inst2.text
    install2_id = inst2.json()["install_id"]

    rb_resp = client.post(f"/v1/control-plane/extensions/{install2_id}/rollback")
    assert rb_resp.status_code == 200, rb_resp.text
    assert rb_resp.json()["extension_manifest_id"] == "ext-m1"
    assert rb_resp.json()["status"] == "active"

    listed = client.get("/v1/control-plane/extensions")
    assert listed.status_code == 200
    active_ids = [item["install_id"] for item in listed.json() if item["status"] == "active"]
    assert len(active_ids) == 1

    rev_resp = client.post(f"/v1/control-plane/extensions/{active_ids[0]}/revoke", json={"reason": "audit_revoke"})
    assert rev_resp.status_code == 200, rev_resp.text
    assert rev_resp.json()["status"] == "revoked"


def test_preference_snapshot_run(isolated_run_service):
    _svc, repo_root, base_sha = isolated_run_service
    client = TestClient(app)
    proj = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(repo_root), "name": "pref-proj", "base_branch": "main", "base_sha": base_sha},
    ).json()
    run_resp = client.post(
        "/v1/control-plane/runs",
        headers={"Idempotency-Key": "pref-run-idem-000001"},
        json={
            "project_id": proj["id"],
            "objective": "Preference snapshot run",
            "mode": "relay",
            "execute": False,
            "task_spec": {"task_id": "t1", "objective": "op", "acceptance_criteria": [{"check_id": "c1", "command": ["echo", "ok"]}]},
        },
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["run_id"]

    bad_pref = client.put(
        "/v1/control-plane/preferences",
        json={"scope_type": "user", "scope_id": "operator", "key": "theme", "value": "dark", "source": "inferred_opt_in"},
    )
    assert bad_pref.status_code == 400
    assert bad_pref.json()["code"] == "opt_in_required"

    p1 = client.put(
        "/v1/control-plane/preferences",
        json={"scope_type": "user", "scope_id": "operator", "key": "model_tier", "value": "fast"},
    )
    assert p1.status_code == 200
    assert p1.json()["version"] == 1

    p2 = client.put(
        "/v1/control-plane/preferences",
        json={"scope_type": "user", "scope_id": "operator", "key": "model_tier", "value": "deep", "expected_version": 1},
    )
    assert p2.status_code == 200
    assert p2.json()["version"] == 2

    stale = client.put(
        "/v1/control-plane/preferences",
        json={"scope_type": "user", "scope_id": "operator", "key": "model_tier", "value": "other", "expected_version": 1},
    )
    assert stale.status_code == 409

    rev = client.post(
        "/v1/control-plane/preferences/revert",
        json={"scope_type": "user", "scope_id": "operator", "key": "model_tier", "target_version": 1},
    )
    assert rev.status_code == 200
    assert json.loads(rev.json()["preference"]["value_json"]) == "fast"

    listed = client.get("/v1/control-plane/preferences", params={"scope_type": "user", "scope_id": "operator"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    snap = client.post(
        f"/v1/control-plane/runs/{run_id}/preferences/snapshot",
        json={"user_id": "operator", "project_id": proj["id"]},
    )
    assert snap.status_code == 201, snap.text
    assert json.loads(snap.json()["resolved_preferences_json"])["preferences"]["model_tier"] == "fast"


def test_transports_and_tokens(isolated_run_service):
    svc, _repo_root, _base_sha = isolated_run_service
    client = TestClient(app)
    import platform as _platform
    from hydra_orch.bridge.transport_registry import REQUIRED_CHECKS_BY_TYPE

    old_probe = getattr(app.state, "transport_health_probe", None)
    app.state.transport_health_probe = lambda _d: {"status": "healthy"}
    try:
        tr_resp = client.post(
            "/v1/control-plane/transports",
            json={"transport_id": "tr-local-1", "type": "local", "target_identity": "127.0.0.1:local"},
        )
        assert tr_resp.status_code == 201, tr_resp.text

        health = client.get("/v1/control-plane/transports/tr-local-1/health")
        assert health.status_code == 200, health.text
        assert health.json()["status"] == "healthy"

        bad_cert = client.post(
            "/v1/control-plane/transports/tr-local-1/certify",
            json={
                "transport_id": "tr-local-1",
                "transport_type": "local",
                "target_identity": "127.0.0.1:local",
                "platform": _platform.system(),
                "version": "1.0.0", "passed_checks": list(REQUIRED_CHECKS_BY_TYPE["local"]),
                "simulated": True,
            },
        )
        assert bad_cert.status_code == 422

        missing_check_cert = client.post(
            "/v1/control-plane/transports/tr-local-1/certify",
            json={
                "transport_id": "tr-local-1",
                "transport_type": "local",
                "target_identity": "127.0.0.1:wrong",
                "platform": _platform.system(),
                "version": "1.0.0", "passed_checks": list(REQUIRED_CHECKS_BY_TYPE["local"]),
                "simulated": False,
            },
        )
        assert missing_check_cert.status_code == 400
        assert missing_check_cert.json()["code"] == "certification_invalid"

        cert = client.post(
            "/v1/control-plane/transports/tr-local-1/certify",
            json={
                "transport_id": "tr-local-1",
                "transport_type": "local",
                "target_identity": "127.0.0.1:local",
                "platform": _platform.system(),
                "version": "1.0.0", "passed_checks": list(REQUIRED_CHECKS_BY_TYPE["local"]),
                "simulated": False,
            },
        )
        assert cert.status_code == 201, cert.text
        assert cert.json()["certified"] is True

        certified_list = client.get("/v1/control-plane/transports", params={"certified_only": True})
        assert certified_list.status_code == 200
        assert any(t["transport_id"] == "tr-local-1" for t in certified_list.json())
    finally:
        app.state.transport_health_probe = old_probe

    from datetime import datetime, timedelta, timezone

    future_iso = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    tok_resp = client.post(
        "/v1/control-plane/tokens",
        json={"principal_id": "ui-local", "scopes": ["control-plane:read"], "expires_at": future_iso},
    )
    assert tok_resp.status_code == 201, tok_resp.text
    tok_data = tok_resp.json()
    raw_token = tok_data["token"]
    assert raw_token.startswith("hydra_tok_")
    assert tok_data["token_hash"].startswith("pbkdf2_sha256$")
    assert TokenVerifier.decode(tok_data["token_hash"]).verify(raw_token)

    import sqlite3

    with sqlite3.connect(str(svc.store.db_path)) as conn:
        row = conn.execute("SELECT token_hash, revoked_at FROM access_tokens WHERE id = ?", (tok_data["id"],)).fetchone()
        assert row is not None
        assert row[0] == tok_data["token_hash"]
        assert row[1] is None
        cmd_count = conn.execute("SELECT COUNT(*) FROM commands WHERE response_json LIKE ?", (f"%{raw_token}%",)).fetchone()[0]
        assert cmd_count == 0

    redacted_resp = client.post(
        "/v1/control-plane/tokens",
        json={"principal_id": "ui-local", "scopes": ["control-plane:read"], "expires_at": future_iso, "redact_token": True},
    )
    assert redacted_resp.status_code == 201
    assert redacted_resp.json()["token"] == "[REDACTED]"

    rev_resp = client.post(f"/v1/control-plane/tokens/{tok_data['id']}/revoke")
    assert rev_resp.status_code == 200, rev_resp.text
    assert rev_resp.json()["revoked_at"] is not None

    past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert client.post(
        "/v1/control-plane/tokens",
        json={"principal_id": "ui-local", "scopes": ["control-plane:read"], "expires_at": past_iso},
    ).status_code == 400


def test_conflict_resolution_endpoints(isolated_run_service):
    svc, repo_root, base_sha = isolated_run_service
    client = TestClient(app)
    proj = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(repo_root), "name": "conf-proj", "base_branch": "main", "base_sha": base_sha},
    ).json()
    run_resp = client.post(
        "/v1/control-plane/runs",
        headers={"Idempotency-Key": "conf-run-idem-000001"},
        json={
            "project_id": proj["id"],
            "objective": "Conflict endpoints test",
            "mode": "relay",
            "execute": False,
            "task_spec": {"task_id": "t1", "objective": "op", "acceptance_criteria": [{"check_id": "c1", "command": ["echo", "ok"]}]},
        },
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["run_id"]

    import sqlite3

    with sqlite3.connect(str(svc.store.db_path)) as conn:
        conn.execute(
            "INSERT INTO integrations (id, run_id, workspace_path, expected_base_sha, status) VALUES (?, ?, ?, ?, ?)",
            ("int-1", run_id, str(repo_root), base_sha, "conflicted"),
        )
        conn.execute(
            """
            INSERT INTO conflict_reports (
                id, integration_id, base_sha, ours_sha, theirs_sha,
                conflicted_files_json, resolution_options_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("conf-1", "int-1", base_sha, base_sha, base_sha, json.dumps(["README.md"]), json.dumps(["auto_repair", "manual", "discarded"]), "open"),
        )
        conn.execute(
            """
            INSERT INTO conflict_reports (
                id, integration_id, base_sha, ours_sha, theirs_sha,
                conflicted_files_json, resolution_options_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("conf-2", "int-1", base_sha, base_sha, base_sha, json.dumps(["other.txt"]), json.dumps(["auto_repair", "manual", "discarded"]), "open"),
        )
        conn.commit()

    listed = client.get(f"/v1/control-plane/runs/{run_id}/conflicts")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 2

    manual_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/conflicts/conf-1/manual",
        json={"finalize": False},
    )
    assert manual_resp.status_code == 200, manual_resp.text
    assert manual_resp.json()["status"] == "manual"

    discard_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/conflicts/conf-2/discard",
        json={"reason": "operator_rejected"},
    )
    assert discard_resp.status_code == 200, discard_resp.text
    assert discard_resp.json()["status"] == "discarded"
    assert client.get("/v1/control-plane/runs/missing-run/conflicts").status_code == 404
    assert client.post(f"/v1/control-plane/runs/{run_id}/conflicts/missing-conf/discard").status_code == 404


def test_budget_governor_events(isolated_run_service):
    svc, repo_root, base_sha = isolated_run_service
    client = TestClient(app)
    proj = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(repo_root), "name": "bud-proj", "base_branch": "main", "base_sha": base_sha},
    ).json()
    run_resp = client.post(
        "/v1/control-plane/runs",
        headers={"Idempotency-Key": "bud-run-idem-0000001"},
        json={
            "project_id": proj["id"],
            "objective": "Budget endpoints test",
            "mode": "relay",
            "execute": False,
            "task_spec": {"task_id": "t1", "objective": "op", "acceptance_criteria": [{"check_id": "c1", "command": ["echo", "ok"]}]},
        },
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["run_id"]

    import asyncio
    from hydra_orch.core.budget import BudgetGovernor

    gov = BudgetGovernor(svc.store)
    asyncio.run(gov.configure(run_id, max_usd=1.0, alert_threshold_pct=80.0))

    status_resp = client.get(f"/v1/control-plane/runs/{run_id}/budget")
    assert status_resp.status_code == 200, status_resp.text
    assert status_resp.json()["status"] == "active"

    asyncio.run(gov.freeze(run_id, reason="limit_reached"))
    assert client.get(f"/v1/control-plane/runs/{run_id}/budget").json()["status"] == "frozen"

    ext_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/budget/extend",
        json={"additional_usd": 4.0, "approved": True, "reason": "approved_topup"},
    )
    assert ext_resp.status_code == 200, ext_resp.text
    assert ext_resp.json()["status"] == "active"
    assert ext_resp.json()["budget_status"]["max_usd"] == 5.0

    deny_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/budget/extend",
        json={"approved": False, "reason": "budget_cap_denied"},
    )
    assert deny_resp.status_code == 200, deny_resp.text
    assert deny_resp.json()["status"] == "exhausted"

    exhausted_resp = client.post(
        f"/v1/control-plane/runs/{run_id}/budget/extend",
        json={"additional_usd": 2.0, "approved": True, "reason": "too_late"},
    )
    assert exhausted_resp.status_code == 409
    assert exhausted_resp.json()["code"] == "budget_exhausted"


def test_pr_package_endpoint(isolated_run_service, tmp_path: Path):
    _svc, repo_root, base_sha = isolated_run_service
    client = TestClient(app)
    proj = client.post(
        "/v1/control-plane/projects",
        json={"canonical_root": str(repo_root), "name": "pr-proj", "base_branch": "main", "base_sha": base_sha},
    ).json()
    run_resp = client.post(
        "/v1/control-plane/runs",
        headers={"Idempotency-Key": "pr-pkg-run-idem-0001"},
        json={
            "project_id": proj["id"],
            "objective": "PR package endpoint test",
            "mode": "relay",
            "execute": False,
            "task_spec": {
                "task_id": "t1",
                "objective": "Create feature module",
                "acceptance_criteria": [{"check_id": "ok", "command": [sys.executable, "-c", "print('ok')"]}],
                "allowed_paths": ["src/*"],
            },
        },
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["run_id"]

    old_rt = getattr(app.state, "pr_package_runtime_dir", None)
    app.state.pr_package_runtime_dir = tmp_path / "pr_runtime"
    try:
        assert client.get(f"/v1/control-plane/runs/{run_id}/pr-package").status_code == 404

        build_resp = client.post(
            f"/v1/control-plane/runs/{run_id}/pr-package",
            json={"pr_branch": f"hydra/pr-{run_id[:8]}", "create_git_branch": True},
        )
        assert build_resp.status_code == 201, build_resp.text
        pkg = build_resp.json()
        assert pkg["run_id"] == run_id
        assert pkg["pr_branch"] == f"hydra/pr-{run_id[:8]}"

        get_resp = client.get(f"/v1/control-plane/runs/{run_id}/pr-package")
        assert get_resp.status_code == 200
        assert get_resp.json()["package_id"] == pkg["package_id"]

        dup_resp = client.post(f"/v1/control-plane/runs/{run_id}/pr-package", json={"create_git_branch": False})
        assert dup_resp.status_code == 409
        assert dup_resp.json()["code"] == "pr_package_exists"

        pub_resp = client.post(f"/v1/control-plane/runs/{run_id}/pr-package/publish", json={"authorized": False})
        assert pub_resp.status_code == 403
        assert pub_resp.json()["code"] == "publish_not_authorized"
    finally:
        app.state.pr_package_runtime_dir = old_rt


def test_extended_auth_and_error_semantics(isolated_run_service):
    _svc, _repo_root, _base_sha = isolated_run_service
    client = TestClient(app)
    unauth = BaseTestClient(app)

    for method, path in [
        ("GET", "/v1/control-plane/areas"),
        ("GET", "/v1/control-plane/workspaces"),
        ("GET", "/v1/control-plane/agents"),
        ("GET", "/v1/control-plane/executors"),
        ("GET", "/v1/control-plane/capabilities"),
        ("GET", "/v1/control-plane/profiles"),
        ("GET", "/v1/control-plane/sessions"),
        ("GET", "/v1/control-plane/discovery/resources"),
        ("GET", "/v1/control-plane/skills"),
        ("GET", "/v1/control-plane/mcps"),
        ("GET", "/v1/control-plane/secrets"),
        ("GET", "/v1/control-plane/extensions"),
        ("GET", "/v1/control-plane/preferences"),
        ("GET", "/v1/control-plane/transports"),
        ("POST", "/v1/control-plane/tokens"),
        ("GET", "/v1/control-plane/runs/r1/conflicts"),
        ("GET", "/v1/control-plane/runs/r1/budget"),
        ("GET", "/v1/control-plane/runs/r1/pr-package"),
        ("GET", "/v1/control-plane/omniroute/inventory"),
        ("POST", "/v1/control-plane/omniroute/account"),
        ("GET", "/v1/control-plane/pty/sessions"),
        ("POST", "/v1/control-plane/pty/sessions"),
        ("GET", "/v1/control-plane/sessions/s1/attachments"),
        ("POST", "/v1/control-plane/sessions/s1/attachments"),
        ("GET", "/v1/control-plane/runs/r1/artifacts/a1/content"),
        ("GET", "/v1/control-plane/search"),
        ("GET", "/v1/control-plane/automations"),
        ("POST", "/v1/control-plane/automations"),
    ]:
        r = unauth.request(method, path)
        assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"

    assert client.post("/v1/control-plane/areas", json={"name": "A", "unexpected": 1}).status_code == 422
def test_wave12_omniroute_pty_attachments_search_and_automations(isolated_run_service, tmp_path):
    import asyncio
    import base64
    import time
    from hydra_orch.bridge.pty_runner import PtyRunner
    from hydra_orch.core.identifier import new_id
    from hydra_orch.model import Artifact, CheckSpec, RunSpec, TaskSpec

    svc, repo_root, base_sha = isolated_run_service
    old_runner = getattr(app.state, "pty_runner", None)
    old_mode = getattr(app.state, "omniroute_connection_mode", None)
    app.state.pty_runner = PtyRunner()
    app.state.omniroute_connection_mode = "optional"
    try:
        headers = {"Authorization": f"Bearer {TEST_API_TOKEN}"}
        with BaseTestClient(app, headers=headers) as client:
            # Bootstrap & Capabilities
            boot = client.get("/v1/control-plane/bootstrap")
            assert boot.status_code == 200
            caps = boot.json()["capabilities"]["hosts"]["local"]["capabilities"]
            assert caps["quickopen"]["status"] == "available"
            assert caps["mobile_emulator"]["status"] == "unavailable"
            assert caps["computer_use"]["status"] == "unavailable"

            cap_resp = client.get("/v1/control-plane/capabilities")
            assert cap_resp.status_code == 200
            assert "hosts" in cap_resp.json()["host_capabilities"]

            # OmniRoute inventory & account selection
            inv = client.get("/v1/control-plane/omniroute/inventory")
            assert inv.status_code == 200
            assert inv.json()["connection_mode"] == "optional"

            acct_ok = client.post(
                "/v1/control-plane/omniroute/account",
                json={"scope_id": "default", "provider": "codex", "account_id": "acct-work"},
            )
            assert acct_ok.status_code == 200, acct_ok.text
            assert acct_ok.json()["account_id"] == "acct-work"
            assert acct_ok.json()["applies_to"] == "next_run"

            acct_secret = client.post(
                "/v1/control-plane/omniroute/account",
                json={"scope_id": "default", "provider": "codex", "account_id": "sk-secret-token-should-fail-1234567890"},
            )
            assert acct_secret.status_code == 400
            assert acct_secret.json()["code"] == "secret_in_account_override"

            # Register project + run + artifact for preview, search & automation dispatch
            proj_resp = client.post(
                "/v1/control-plane/projects",
                json={
                    "project_id": "proj-w12",
                    "name": "Wave 12 Project",
                    "canonical_root": str(repo_root),
                    "base_branch": "main",
                    "base_sha": base_sha,
                },
            )
            assert proj_resp.status_code == 201, proj_resp.text

            sample_rel = "src/preview_note.md"
            (repo_root / sample_rel).write_text("# Hello\n<script>alert(1)</script>\nSafe text", encoding="utf-8")
            run_id = "run-w12-" + new_id()[:6]
            art_id = "art-w12-" + new_id()[:6]

            async def _seed_run_artifact():
                await svc.store.initialize()
                await svc.submit_run(
                    RunSpec(
                        run_id=run_id,
                        project_id="proj-w12",
                        repo_root=str(repo_root),
                        base_branch="main",
                        base_sha=base_sha,
                        objective="Wave 12 search and preview test",
                        idempotency_key=f"w12-seed-{run_id}".ljust(16, "_"),
                        tasks=(
                            TaskSpec(
                                task_id="t1",
                                run_id=run_id,
                                objective="Inspect",
                                assigned_executor="codex",
                                allowed_paths=("src",),
                                acceptance_criteria=(CheckSpec(check_id="c1", command=(sys.executable, "-c", "print('ok')")),),
                            ),
                        ),
                    )
                )
                import hashlib
                raw_bytes = (repo_root / sample_rel).read_bytes()
                await svc.store.save_artifact(
                    Artifact(
                        artifact_id=art_id,
                        run_id=run_id,
                        relative_path=sample_rel,
                        kind="report",
                        sha256=hashlib.sha256(raw_bytes).hexdigest(),
                        size_bytes=len(raw_bytes),
                    )
                )

            asyncio.run(_seed_run_artifact())

            preview = client.get(f"/v1/control-plane/runs/{run_id}/artifacts/{art_id}/content")
            assert preview.status_code == 200, preview.text
            pv_data = preview.json()
            assert pv_data["status"] == "ok"
            assert pv_data["script_stripped"] is True
            assert "<script>" not in (pv_data.get("sanitized_markdown") or "")

            missing_pv = client.get(f"/v1/control-plane/runs/{run_id}/artifacts/missing-art/content")
            assert missing_pv.status_code == 404

            # Attachments upload + validation
            txt_b64 = base64.b64encode(b"hello attachment\n").decode("ascii")
            att_ok = client.post(
                "/v1/control-plane/sessions/sess-w12/attachments",
                json={"workspace_id": "ws-w12", "filename": "notes.txt", "content_base64": txt_b64},
            )
            assert att_ok.status_code == 201, att_ok.text
            assert att_ok.json()["filename"] == "notes.txt"

            att_list = client.get("/v1/control-plane/sessions/sess-w12/attachments")
            assert att_list.status_code == 200
            assert len(att_list.json()) == 1

            att_bad_ext = client.post(
                "/v1/control-plane/sessions/sess-w12/attachments",
                json={"workspace_id": "ws-w12", "filename": "evil.html", "content_base64": txt_b64},
            )
            assert att_bad_ext.status_code == 400
            assert att_bad_ext.json()["code"] == "unsupported_attachment_type"

            # Global QuickOpen search
            srch = client.get("/v1/control-plane/search", params={"q": "Wave 12"})
            assert srch.status_code == 200, srch.text
            assert any(item["id"] == "proj-w12" for item in srch.json()["items"])

            # Automations CRUD + state + trigger + tick + delete
            auto_bad = client.post(
                "/v1/control-plane/automations",
                json={"name": "Bad Cron", "prompt": "fail", "cron_expr": "bad cron"},
            )
            assert auto_bad.status_code == 400
            assert auto_bad.json()["code"] == "invalid_schedule"

            auto_cr = client.post(
                "/v1/control-plane/automations",
                json={
                    "name": "Nightly Check",
                    "prompt": "Run nightly check",
                    "interval_seconds": 3600,
                    "timezone": "UTC",
                    "project_id": "proj-w12",
                },
            )
            assert auto_cr.status_code == 201, auto_cr.text
            sched_id = auto_cr.json()["id"]

            assert client.post(f"/v1/control-plane/automations/{sched_id}/pause").json()["enabled"] is False
            assert client.post(f"/v1/control-plane/automations/{sched_id}/resume").json()["enabled"] is True

            trig = client.post(f"/v1/control-plane/automations/{sched_id}/trigger")
            assert trig.status_code == 200, trig.text
            assert trig.json()["status"] in {"dispatched", "queued"}, trig.text

            runs_hist = client.get(f"/v1/control-plane/automations/{sched_id}/runs")
            assert runs_hist.status_code == 200
            assert len(runs_hist.json()) >= 1

            tick_res = client.post("/v1/control-plane/automations/tick")
            assert tick_res.status_code == 200
            assert "dispatched_count" in tick_res.json()

            del_res = client.delete(f"/v1/control-plane/automations/{sched_id}")
            assert del_res.status_code == 200
            assert del_res.json()["deleted"] is True

            # PTY HTTP lifecycle + WS unauth rejection + WS authenticated echo
            pty_script = "import sys; print('PTY_READY', flush=True); line=sys.stdin.readline().strip(); print('ECHO:' + line, flush=True)"
            pty_cr = client.post(
                "/v1/control-plane/pty/sessions",
                json={
                    "command": [sys.executable, "-c", pty_script],
                    "cwd": str(repo_root),
                    "workspace_id": "ws-w12",
                    "cols": 90,
                    "rows": 30,
                },
            )
            assert pty_cr.status_code == 201, pty_cr.text
            sid = pty_cr.json()["session_id"]

            assert client.post(f"/v1/control-plane/pty/sessions/{sid}/resize", json={"cols": 100, "rows": 36}).status_code == 200
            assert client.post(f"/v1/control-plane/pty/sessions/{sid}/input", json={"data": "ping\n"}).status_code == 200

            collected = ""
            for _ in range(30):
                out = client.get(f"/v1/control-plane/pty/sessions/{sid}/output", params={"after_seq": 0})
                assert out.status_code == 200
                collected = "".join(c["text"] for c in out.json()["chunks"])
                if "ECHO:ping" in collected:
                    break
                time.sleep(0.05)
            assert "PTY_READY" in collected
            assert "ECHO:ping" in collected

            sse_resp = client.get(f"/v1/control-plane/pty/sessions/{sid}/stream", params={"after_seq": 0})
            assert sse_resp.status_code == 200
            assert "event: pty.state" in sse_resp.text

            assert client.post(f"/v1/control-plane/pty/sessions/{sid}/close", json={"keep_running": False}).status_code == 200

            # WebSocket auth check on a fresh interactive session
            ws_cr = client.post(
                "/v1/control-plane/pty/sessions",
                json={"command": [sys.executable, "-c", "import time; print('WS_HI', flush=True); time.sleep(0.2)"], "cwd": str(repo_root)},
            )
            assert ws_cr.status_code == 201
            ws_sid = ws_cr.json()["session_id"]

            unauth_client = BaseTestClient(app)
            with pytest.raises(Exception):
                with unauth_client.websocket_connect(f"/v1/control-plane/pty/sessions/{ws_sid}/ws"):
                    pass

            with client.websocket_connect(f"/v1/control-plane/pty/sessions/{ws_sid}/ws", headers=headers) as ws:
                msgs = [ws.receive_json()]
                for _ in range(5):
                    if any(m.get("type") == "state" or "WS_HI" in str(m) for m in msgs):
                        break
                    msgs.append(ws.receive_json())
                assert any(m.get("type") in {"chunk", "state"} for m in msgs)
    finally:
        app.state.pty_runner = old_runner
        app.state.omniroute_connection_mode = old_mode
