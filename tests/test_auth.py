"""T09 negative security contracts: auth, CORS and evidence redaction."""

import json
from contextlib import closing
import logging
import hashlib
import sqlite3
import sys

from fastapi.testclient import TestClient
import pytest

from hydra_orch.core.auth import TokenVerifier, load_cors_origins, load_token_verifier, validate_cors_origins
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.redaction import REDACTED, install_log_redaction, redact, redact_text
from hydra_orch.server import app, startup_event
from test_checkpointer import _make_run_spec

TOKEN = "hydra-security-test-token-0123456789"
VERIFIER = TokenVerifier.from_token(TOKEN)
pytestmark = pytest.mark.security


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setitem(app.state._state, "token_verifier", VERIFIER)
    monkeypatch.setitem(app.state._state, "cors_allow_origins", ["http://localhost:3000"])
    return TestClient(app)


def test_hash_roundtrip_and_salt():
    other = TokenVerifier.from_token(TOKEN)
    assert VERIFIER.encode() != other.encode()
    assert TOKEN not in repr(VERIFIER)
    assert TOKEN not in VERIFIER.encode()
    restored = TokenVerifier.decode(VERIFIER.encode())
    assert restored.verify(TOKEN)
    assert not restored.verify("wrong-token")
    assert not restored.verify("")
    assert not restored.verify("x" * 4097)
    assert not restored.verify(TOKEN + "\n")
    assert load_token_verifier({}) is None
    assert load_token_verifier({"HYDRA_API_TOKEN": TOKEN}).verify(TOKEN)
    assert load_token_verifier({"HYDRA_API_TOKEN_HASH": VERIFIER.encode()}).verify(TOKEN)
    with pytest.raises(ValueError):
        load_token_verifier({"HYDRA_API_TOKEN_HASH": VERIFIER.encode(), "HYDRA_API_TOKEN": TOKEN})


@pytest.mark.parametrize("encoded", ["invalid", "pbkdf2_sha256$1$ab$cd", "sha256$600000$ab$cd", None])
def test_bad_verifier_is_rejected(encoded):
    with pytest.raises(ValueError, match="Invalid PBKDF2"):
        TokenVerifier.decode(encoded)


@pytest.mark.parametrize("token", ["short", "a" * 4097, "a" * 32 + " "])
def test_bad_token_configuration(token):
    with pytest.raises(ValueError):
        TokenVerifier.from_token(token)


@pytest.mark.parametrize("path", ["/health", "/v1/health", "/v1/models", "/v1/quota",
    "/v1/orchestrator/status", "/v1/chat/completions", "/v1/control-plane/runs",
    "/runs", "/projects", "/docs", "/openapi.json"])
def test_all_routes_require_token_even_on_loopback(secured, path):
    response = secured.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert TOKEN not in response.text


@pytest.mark.parametrize("header", ["Basic abc", "Bearer", "Bearer wrong", "Bearer ", "Bearer  " + TOKEN])
def test_invalid_bearer(secured, header):
    assert secured.get("/health", headers={"Authorization": header}).status_code == 401


def test_missing_verifier_fails_closed(secured, monkeypatch):
    monkeypatch.setitem(app.state._state, "token_verifier", None)
    assert secured.get("/health", headers={"Authorization": "Bearer " + TOKEN}).status_code == 401


@pytest.mark.asyncio
async def test_startup_without_token_fails_before_side_effects(monkeypatch):
    monkeypatch.delenv("HYDRA_API_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_API_TOKEN_HASH", raising=False)
    monkeypatch.setitem(app.state._state, "token_verifier", VERIFIER)
    with pytest.raises(RuntimeError, match="Configure HYDRA_API"):
        await startup_event()


def test_valid_auth_origin_and_preflight(secured):
    headers = {"Authorization": "bEaReR " + TOKEN, "Origin": "http://localhost:3000"}
    response = secured.get("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    # Non-browser local clients can omit Origin; browsers preflight without Bearer.
    assert secured.get("/health", headers={"Authorization": "Bearer " + TOKEN}).status_code == 200
    preflight = secured.options("/health", headers={"Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "Authorization"})
    assert preflight.status_code == 200
    assert "healthy" not in preflight.text
    assert secured.options("/health").status_code == 401
    assert secured.get("/health", headers=[("Authorization", "Bearer " + TOKEN),
        ("Authorization", "Bearer " + TOKEN)]).status_code == 401


@pytest.mark.parametrize("origin", ["*", "null", "https://evil.example", "http://localhost:3000.evil"])
def test_forbidden_origin_even_with_valid_token(secured, origin):
    for method in (secured.get, secured.options):
        response = method("/health", headers={"Origin": origin, "Authorization": "Bearer " + TOKEN})
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["*", "https://evil.example", "http://localhost/path",
    "http://user:pass@localhost", "http://localhost:bad", "http://localhost?x=1",
    "http://localhost#frag", "file://localhost", "http://localhost:0"])
def test_invalid_cors_configuration(origin, secured, monkeypatch):
    with pytest.raises(ValueError):
        validate_cors_origins([origin])
    monkeypatch.setitem(app.state._state, "cors_allow_origins", [origin])
    assert secured.get("/health", headers={"Authorization": "Bearer " + TOKEN}).status_code == 503


def test_cors_list_validation():
    with pytest.raises(ValueError):
        validate_cors_origins("*")
    assert validate_cors_origins(["http://[::1]:3000", "http://[::1]:3000"]) == ["http://[::1]:3000"]


def test_cors_environment(monkeypatch):
    monkeypatch.delenv("HYDRA_CORS_ALLOW_ORIGINS", raising=False)
    assert load_cors_origins([]) == []
    monkeypatch.setenv("HYDRA_CORS_ALLOW_ORIGINS", '["http://localhost:3000"]')
    assert load_cors_origins([]) == ["http://localhost:3000"]
    monkeypatch.setenv("HYDRA_CORS_ALLOW_ORIGINS", "invalid")
    with pytest.raises(ValueError):
        load_cors_origins([])


@pytest.mark.parametrize("secret", ["sk-proj-1234567890abcdef", "ghp_1234567890abcdef",
    "github_pat_1234567890abcdef", "glpat-1234567890abcdef", "xoxb-1234567890abcdef",
    "Bearer arbitrary-unprefixed-secret", "password='two word password'",
    'api_key="two word key"', "client_secret=oauth-secret", "access_token=oauth-secret",
    "https://alice:password@example.com/path",
    "-----BEGIN OPENSSH PRIVATE KEY-----\nkey material\n-----END OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----\nincomplete key"])
def test_secret_patterns(secret):
    assert REDACTED in redact_text(secret)
    assert redact_text(secret) != secret
    assert redact_text(redact_text(secret)) == redact_text(secret)


def test_recursive_redaction_and_benign_fields():
    payload = {"password": "arbitrary", "nested": [{"Authorization": TOKEN,
        "refresh_token": TOKEN, "notes": "Bearer " + TOKEN}],
        "task_id": "task-123", "max_tokens_in": 100, "sha256": "a" * 64}
    safe = redact(payload)
    assert TOKEN not in json.dumps(safe)
    assert safe["task_id"] == payload["task_id"]
    assert safe["max_tokens_in"] == 100
    assert safe["sha256"] == payload["sha256"]
    assert payload["password"] == "arbitrary"
    assert redact(("safe", 1, None)) == ["safe", 1, None]
    # A deterministic benign corpus, not a general claim about real-world FP rate.
    for i in range(2000):
        text = f"task-{i} tested commit {'a' * 40}, duration_ms={i}, max_tokens_in=100"
        assert redact_text(text) == text


def test_logging_redacts_interpolation_and_tracebacks(caplog):
    install_log_redaction()
    factory = logging.getLogRecordFactory()
    install_log_redaction()
    assert logging.getLogRecordFactory() is factory
    with caplog.at_level(logging.WARNING):
        logging.getLogger("hydra_orch.auth_test").warning("Authorization: Bearer %s", TOKEN)
        logging.getLogger("hydra_orch.auth_test").warning({"password": TOKEN})
        logging.getLogger("hydra_orch.auth_test").warning("details: %s", {"token": TOKEN})
        logging.getLogger("hydra_orch.auth_test").warning("password=%(password)s", {"password": TOKEN})
        try:
            raise ValueError("password=private-value")
        except ValueError:
            logging.getLogger("hydra_orch.auth_test").exception("worker failed", stack_info=True)
    assert TOKEN not in caplog.text
    assert "private-value" not in caplog.text
    assert REDACTED in caplog.text


@pytest.mark.asyncio
async def test_events_redacted_before_sqlite_and_legacy_replay(tmp_path):
    store = ExecutionStore(tmp_path / "security.sqlite")
    spec = _make_run_spec(str(tmp_path))
    await store.submit_run_idempotent(spec)
    event = await store.record_event_atomic(run_id=spec.run_id, event_type="run.started",
        payload={"password": TOKEN, "nested": {"detail": "Bearer " + TOKEN}})
    assert TOKEN not in event.model_dump_json()
    with closing(sqlite3.connect(store.db_path)) as db:
        raw = db.execute("SELECT payload_json FROM events WHERE seq=?", (event.seq,)).fetchone()[0]
        assert TOKEN not in raw
        db.execute("UPDATE events SET payload_json=? WHERE seq=?",
            (json.dumps({"api_key": TOKEN}), event.seq))
        db.commit()
    replay = await store.get_events(spec.run_id, after_seq=event.seq - 1)
    assert replay[0].redacted_payload == {"api_key": REDACTED}
    assert replay[0].seq == event.seq


@pytest.mark.asyncio
async def test_worker_and_check_logs_redacted_before_hashing(tmp_path):
    from hydra_orch.bridge.worker_runner import WorkerRunner
    from hydra_orch.core.run_service import CheckRunner
    from hydra_orch.model import CheckSpec

    script = "import sys; print('password=private-value'); sys.stderr.write('Bearer private-value')"
    output_dir = tmp_path / "worker"
    outcome = await WorkerRunner().execute_task_in_worktree(
        worktree_path=tmp_path, prompt="test", cli_name="python_fake",
        custom_command=(sys.executable, "-c", script), run_id="redaction-run",
        task_id="redaction-task", attempt_id="redaction-attempt", base_sha="a" * 40,
        artifacts_dir=output_dir)
    assert outcome["success"]
    assert "private-value" not in outcome["output"] + outcome["stderr"]
    for name in ("stdout.log", "stderr.log"):
        assert b"private-value" not in (output_dir / name).read_bytes()
    checks, artifacts = await CheckRunner(tmp_path).run_checks(
        run_id="redaction-run", attempt_id="redaction-attempt", workspace_path=tmp_path,
        tested_sha="a" * 40, checks=(CheckSpec(check_id="redact", command=(sys.executable, "-c", script)),))
    assert checks[0].exit_code == 0
    for artifact in artifacts:
        data = (tmp_path / artifact.relative_path).read_bytes()
        assert b"private-value" not in data
        assert artifact.sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.asyncio
async def test_sse_and_json_sanitize_legacy_evidence(tmp_path, secured, monkeypatch):
    from hydra_orch import server
    from hydra_orch.core.run_service import RunService

    from test_server import _init_temp_git_repo

    repo, _ = _init_temp_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "sse.sqlite")
    spec = _make_run_spec(str(repo))
    await store.submit_run_idempotent(spec)
    await store.record_event_atomic(run_id=spec.run_id, event_type="run.started",
        payload={"detail": "Bearer " + TOKEN})
    svc = RunService(repo_root=repo, store=store)
    monkeypatch.setattr(server, "_run_service", svc)
    headers = {"Authorization": "Bearer " + TOKEN}
    response = secured.get(f"/v1/control-plane/runs/{spec.run_id}/events", headers=headers)
    assert response.status_code == 200
    assert TOKEN not in response.text
    assert REDACTED in response.text
    safe = server.JSONResponse({"detail": "Bearer " + TOKEN})
    assert TOKEN.encode() not in safe.body
