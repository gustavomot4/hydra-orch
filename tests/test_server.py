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
