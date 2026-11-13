"""Hermetic cross-cutting CI gate for OpenAPI parity, CLI surface and G-M4 negative rules (T24)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import subprocess
from urllib.parse import urlparse

import pytest
import yaml
from fastapi.testclient import TestClient as BaseTestClient
from typer.testing import CliRunner

from hydra_orch import cli
from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.preferences import (
    AccessibilitySettings,
    ColorTokenPair,
    validate_a11y_contract,
)
from hydra_orch.core.run_service import RunService
from hydra_orch.model import ContractViolation
from hydra_orch.server import app, set_run_service


TEST_TOKEN = "hydra-t24-ci-gate-bearer-token-0123456789"
TEST_VERIFIER = TokenVerifier.from_token(TEST_TOKEN)


def _init_repo(base_dir: Path) -> Path:
    repo = base_dir / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@hydra.local"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra CI"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# ci fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def isolated_env(monkeypatch, tmp_path: Path):
    repo = _init_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    set_run_service(svc)
    monkeypatch.setitem(app.state._state, "token_verifier", TEST_VERIFIER)
    monkeypatch.setenv("HYDRA_API_TOKEN", TEST_TOKEN)
    monkeypatch.delenv("HYDRA_API_TOKEN_HASH", raising=False)
    client = BaseTestClient(app, headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    try:
        yield svc, repo, client
    finally:
        set_run_service(None)


@pytest.mark.integration
def test_openapi_paths_match_fastapi_routes():
    spec_path = Path(__file__).resolve().parents[1] / "doc" / "f_api" / "openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert spec["openapi"] == "3.0.3"
    base = urlparse(spec["servers"][0]["url"]).path.rstrip("/")

    def _norm(path: str) -> str:
        return re.sub(r"\{[^}]+\}", "{}", path)

    spec_routes = set()
    for raw_path in spec["paths"]:
        if raw_path == "/chat/completions":
            full = "/v1/chat/completions"
        elif raw_path in {"/health", "/models", "/orchestrator/status"}:
            full = raw_path
        else:
            full = f"{base}{raw_path}"
        spec_routes.add(_norm(full))

    app_routes = {_norm(route.path) for route in app.routes}
    missing = sorted(spec_routes - app_routes)
    assert missing == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "group",
    [
        "area",
        "workspace",
        "project",
        "repo",
        "agent",
        "profile",
        "session",
        "metrics",
        "consent",
        "memory",
        "discovery",
        "skill",
        "mcp",
        "secret",
        "extension",
        "preference",
        "transport",
        "token",
        "conflict",
        "budget",
        "pr-package",
    ],
)
def test_cli_extended_groups_help_offline(group: str):
    result = CliRunner().invoke(cli.app, [group, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


@pytest.mark.negative
@pytest.mark.security
def test_negative_memory_write_without_consent_blocked_cli_and_http(isolated_env):
    _, _, client = isolated_env
    runner = CliRunner()

    cli_res = runner.invoke(
        cli.app,
        [
            "memory",
            "write",
            "--scope-type",
            "workspace",
            "--scope-id",
            "ws-unconsented",
            "--content",
            "should fail without consent",
            "--json",
        ],
    )
    assert cli_res.exit_code == 3
    assert "consent" in cli_res.output.lower()

    resp = client.post(
        "/v1/control-plane/memory",
        json={
            "scope_type": "workspace",
            "scope_id": "ws-unconsented",
            "content": "should fail without consent",
            "retention_policy": "day",
        },
    )
    assert resp.status_code == 409


@pytest.mark.negative
@pytest.mark.security
def test_negative_discovery_outside_allowed_roots_blocked_cli_and_http(isolated_env, tmp_path: Path):
    _, _, client = isolated_env
    outside_dir = tmp_path / "outside_root"
    outside_dir.mkdir(parents=True, exist_ok=True)
    runner = CliRunner()

    cli_res = runner.invoke(
        cli.app,
        [
            "discovery",
            "scan",
            "--root",
            str(outside_dir),
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert cli_res.exit_code == 1

    resp = client.post(
        "/v1/control-plane/discovery/scan",
        json={"authorized_root": str(outside_dir), "opt_in": True},
    )
    assert resp.status_code == 403


@pytest.mark.negative
@pytest.mark.security
def test_negative_secret_literal_and_plaintext_token_never_persisted(isolated_env):
    svc, _, client = isolated_env
    runner = CliRunner()
    raw_literal = "sk-live-secretvalue-1234567890abcdef"

    cli_secret = runner.invoke(
        cli.app,
        [
            "secret",
            "register",
            "--name",
            "bad-literal",
            "--provider",
            "env",
            "--source-key",
            raw_literal,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert cli_secret.exit_code == 1

    resp = client.post(
        "/v1/control-plane/secrets",
        json={
            "secret_name": "bad-literal-http",
            "provider_type": "env",
            "source_key": raw_literal,
            "principal_id": "op-1",
        },
    )
    assert resp.status_code in (400, 422)

    raw_token = "hydra-local-raw-token-never-in-sqlite-0001"
    tok_res = runner.invoke(
        cli.app,
        [
            "token",
            "create",
            "--principal-id",
            "op-1",
            "--scopes",
            "read,write",
            "--token",
            raw_token,
            "--json",
        ],
    )
    assert tok_res.exit_code == 0, tok_res.output
    payload = json.loads(tok_res.output)
    assert raw_token not in tok_res.output

    with sqlite3.connect(svc.store.db_path) as conn:
        row = conn.execute(
            "SELECT token_hash FROM access_tokens WHERE id = ?",
            (payload["token_id"],),
        ).fetchone()
    assert row is not None
    stored_hash = str(row[0])
    assert raw_token not in stored_hash
    assert stored_hash.startswith("pbkdf2_sha256$")


@pytest.mark.negative
@pytest.mark.security
def test_negative_pr_publish_without_authorization_blocked(isolated_env):
    _, repo, client = isolated_env
    runner = CliRunner()
    sub_res = runner.invoke(
        cli.app,
        [
            "submit",
            "--repo-root",
            str(repo),
            "--objective",
            "T24 publish negative gate",
            "--task-id",
            "t1",
            "--executor",
            "codex",
            "--idempotency-key",
            "idem-t24-neg-pr-001",
            "--json",
        ],
    )
    assert sub_res.exit_code == 0, sub_res.output
    run_id = json.loads(sub_res.output)["run_id"]

    build_res = runner.invoke(
        cli.app,
        ["pr-package", "build", run_id, "--no-create-git-branch", "--json"],
    )
    assert build_res.exit_code == 0, build_res.output
    package_id = json.loads(build_res.output)["package_id"]

    pub_cli = runner.invoke(cli.app, ["pr-package", "publish", package_id, "--json"])
    assert pub_cli.exit_code == 3

    pub_http = client.post(
        f"/v1/control-plane/runs/{run_id}/pr-package/publish",
        json={"authorized": False},
    )
    assert pub_http.status_code in (403, 409)


@pytest.mark.negative
@pytest.mark.a11y
def test_negative_a11y_wcag_aa_low_contrast_rejected():
    low_contrast = AccessibilitySettings(
        color_pairs=(
            ColorTokenPair(name="muted_on_white", foreground="#aaaaaa", background="#ffffff", kind="normal_text"),
        )
    )
    with pytest.raises(ContractViolation) as exc_info:
        validate_a11y_contract(low_contrast, raise_on_failure=True)
    assert exc_info.value.code == "a11y_contract_violation"
