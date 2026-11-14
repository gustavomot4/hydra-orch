"""Opt-in live read-only validation against local OmniRoute v3.x daemon (:20128).

Set HYDRA_OMNIROUTE_LIVE=1 (and OMNIROUTE_API_KEY in the environment) to execute
live checks. Never sends paid inference calls (/v1/chat/completions) and never
writes secrets, OAuth emails, or API keys into outputs.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.config import load_config
from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.run_service import RunService
from hydra_orch.server import app, set_run_service

_RUN_LIVE = os.environ.get("HYDRA_OMNIROUTE_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not _RUN_LIVE,
    reason="Opt-in live OmniRoute integration test (set HYDRA_OMNIROUTE_LIVE=1)",
)


def _assert_no_leaks(payload: object, secret: str) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "@" not in serialized, "Unexpected email/PII detected in OmniRoute payload"
    if secret:
        assert secret not in serialized, "Unexpected API key leak detected in OmniRoute payload"
    for forbidden in ("refreshToken", "accessToken", "providerSpecificData", "apiKey"):
        assert forbidden not in serialized


def _init_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "hydra@example.invalid"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("hydra live omniroute repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_omniroute_live_read_only_client() -> None:
    cfg = load_config(reload=True)
    token = os.environ.get(cfg.omniroute.api_key_env, "").strip()
    assert token, f"Missing live credential env var: {cfg.omniroute.api_key_env}"

    client = OmniRouteClient(
        base_url=cfg.omniroute.base_url,
        quota_api_url=cfg.omniroute.quota_api_url,
        enabled=True,
        api_key_env=cfg.omniroute.api_key_env,
    )
    assert await client.is_available() is True

    models_resp = await client.list_models()
    assert models_resp["status"] == "available"
    assert models_resp["source"] == "omniroute:models_api"
    model_ids = {item["id"] for item in models_resp["models"]}
    assert len(model_ids) >= 100
    expected_catalog = {
        cfg.omniroute.logical_models["architect_heavy"].primary,
        cfg.omniroute.logical_models["fullstack_coder"].primary,
        cfg.omniroute.logical_models["context_and_docs"].primary,
        "auto/best-reasoning",
        "auto/best-coding",
        "auto/fast",
    }
    assert expected_catalog <= model_ids

    quota = await client.get_quota_status()
    _assert_no_leaks(quota, token)
    for key in ("claude_pro", "chatgpt_plus", "gemini_pro"):
        assert isinstance(quota.get(key), dict)
        entry = quota[key]
        if entry["status"] == "observed":
            assert isinstance(entry["remaining_percent"], (int, float))
            assert 0 <= entry["remaining_percent"] <= 100
        else:
            assert entry["remaining_percent"] is None

    accounts = await client.list_accounts()
    _assert_no_leaks(accounts, token)
    assert accounts["source"] in {"omniroute:providers_api", "omniroute:accounts_api", "omniroute:quota_api"}
    assert len(accounts["accounts"]) >= 1
    for account in accounts["accounts"]:
        assert account["account_id"]
        assert account["provider"]
        assert account["label"]
        if account["status"] == "observed":
            assert isinstance(account["remaining_percent"], (int, float))
            assert 0 <= account["remaining_percent"] <= 100
        else:
            assert account["remaining_percent"] is None


def test_omniroute_live_control_plane_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(reload=True)
    secret = os.environ.get(cfg.omniroute.api_key_env, "").strip()
    assert secret, f"Missing live credential env var: {cfg.omniroute.api_key_env}"

    hydra_token = "hydra-live-omniroute-test-token-0123456789"
    monkeypatch.setenv("HYDRA_API_TOKEN", hydra_token)
    monkeypatch.delenv("HYDRA_API_TOKEN_HASH", raising=False)
    monkeypatch.setitem(app.state._state, "token_verifier", TokenVerifier.from_token(hydra_token))
    monkeypatch.setitem(app.state._state, "omniroute_transport", None)
    monkeypatch.setitem(app.state._state, "omniroute_connection_mode", "optional")

    live_cfg = cfg.model_copy(
        update={
            "omniroute": cfg.omniroute.model_copy(
                update={"enabled": True, "connection_mode": "optional"}
            )
        }
    )
    monkeypatch.setattr("hydra_orch.server.config", live_cfg)

    repo = _init_git_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    import asyncio

    asyncio.run(store.initialize())
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    set_run_service(svc)
    try:
        client = TestClient(app, headers={"Authorization": f"Bearer {hydra_token}"})
        quota_resp = client.get("/v1/quota")
        assert quota_resp.status_code == 200, quota_resp.text
        _assert_no_leaks(quota_resp.json(), secret)

        inv_resp = client.get("/v1/control-plane/omniroute/inventory")
        assert inv_resp.status_code == 200, inv_resp.text
        inv = inv_resp.json()
        _assert_no_leaks(inv, secret)
        assert inv["available"] is True
        assert inv["connection_mode"] == "optional"
        assert inv["direct_mode_supported"] is True
        assert inv["quota"]["status"] in {"observed", "unknown"}
        assert len(inv["models"]) >= 100
        assert len(inv["accounts"]) >= 1
    finally:
        set_run_service(None)
