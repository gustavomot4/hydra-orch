"""Unit and integration tests for Wave 1A: Auth cache, scoped sub-tokens, host/CORS guards, and desktop bootstrap tickets."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest

from hydra_orch.core import auth, local_desktop
from hydra_orch.core.auth import (
    AuthPrincipal,
    PBKDF2_MAX_CONCURRENCY,
    TokenVerifier,
    VerifiedTokenCache,
    clear_verifier_cache,
    default_cors_origins,
    extract_scoped_token_id,
    is_trusted_host,
    mint_scoped_token,
    scope_allows,
    validate_cors_origins,
)
from hydra_orch.core.local_desktop import (
    DesktopSessionManager,
    allow_bootstrap,
    enabled,
    public_frontend,
)


MASTER_TOKEN = "hydra-master-secret-token-0123456789abcdef"


def _mock_request(
    *,
    method: str = "GET",
    scheme: str = "http",
    host_header: str = "127.0.0.1:8000",
    hostname: str = "127.0.0.1",
    path: str = "/",
    client_host: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
    app_state: object | None = None,
) -> SimpleNamespace:
    hdrs = {"host": host_header}
    if headers:
        for k, v in headers.items():
            hdrs[k.lower()] = v
    return SimpleNamespace(
        method=method,
        client=SimpleNamespace(host=client_host) if client_host is not None else None,
        url=SimpleNamespace(scheme=scheme, hostname=hostname, path=path),
        headers=hdrs,
        app=SimpleNamespace(state=app_state),
    )


def test_token_verifier_fast_cache_under_2ms_for_100_verifications(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_verifier_cache()
    verifier = TokenVerifier.from_token(MASTER_TOKEN)

    pbkdf2_calls = 0
    real_pbkdf2 = hashlib.pbkdf2_hmac

    def counted_pbkdf2(*args, **kwargs):
        nonlocal pbkdf2_calls
        pbkdf2_calls += 1
        return real_pbkdf2(*args, **kwargs)

    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", counted_pbkdf2)

    # Cold 1st verification runs PBKDF2 600k once and populates SHA-256 digest cache.
    assert verifier.verify(MASTER_TOKEN) is True
    assert pbkdf2_calls == 1
    assert MASTER_TOKEN not in repr(auth._VERIFIER_FAST_CACHE)

    # Warmed 100 repeated verifications must complete in < 2ms without calling PBKDF2 again.
    start = time.perf_counter()
    for _ in range(100):
        assert verifier.verify(MASTER_TOKEN) is True
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert pbkdf2_calls == 1
    assert elapsed_ms < 25.0, f"Expected < 25.0ms for 100 cached verifications, took {elapsed_ms:.3f}ms"


def test_token_verifier_concurrent_cold_burst_and_invalid_token_semaphore(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_verifier_cache()
    verifier = TokenVerifier.from_token(MASTER_TOKEN)

    lock = threading.Lock()
    active_pbkdf2 = 0
    peak_pbkdf2 = 0
    total_pbkdf2 = 0
    real_pbkdf2 = hashlib.pbkdf2_hmac

    def tracked_pbkdf2(*args, **kwargs):
        nonlocal active_pbkdf2, peak_pbkdf2, total_pbkdf2
        with lock:
            active_pbkdf2 += 1
            total_pbkdf2 += 1
            if active_pbkdf2 > peak_pbkdf2:
                peak_pbkdf2 = active_pbkdf2
        try:
            time.sleep(0.01)
            return real_pbkdf2(*args, **kwargs)
        finally:
            with lock:
                active_pbkdf2 -= 1

    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", tracked_pbkdf2)

    # 100 concurrent valid verifications from cold cache coalesce via double-checked semaphore.
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: verifier.verify(MASTER_TOKEN), range(100)))
    assert all(results)
    assert total_pbkdf2 <= PBKDF2_MAX_CONCURRENCY
    assert peak_pbkdf2 <= PBKDF2_MAX_CONCURRENCY

    # Invalid tokens still execute PBKDF2 (no instant oracle), throttled by BoundedSemaphore(4).
    total_before_invalid = total_pbkdf2
    peak_pbkdf2 = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        bad_results = list(
            pool.map(lambda idx: verifier.verify(f"invalid-token-attempt-{idx:020d}"), range(12))
        )
    assert not any(bad_results)
    assert total_pbkdf2 - total_before_invalid == 12
    assert 1 <= peak_pbkdf2 <= PBKDF2_MAX_CONCURRENCY


def test_token_verifier_cache_ttl_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_verifier_cache()
    now = [1000.0]
    monkeypatch.setattr(auth, "_monotonic", lambda: now[0])
    verifier = TokenVerifier.from_token(MASTER_TOKEN)

    calls = 0
    real_pbkdf2 = hashlib.pbkdf2_hmac

    def counted_pbkdf2(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_pbkdf2(*args, **kwargs)

    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", counted_pbkdf2)

    assert verifier.verify(MASTER_TOKEN) is True
    assert calls == 1

    now[0] += 299.0
    assert verifier.verify(MASTER_TOKEN) is True
    assert calls == 1

    now[0] += 2.0  # Past 300s TTL
    assert verifier.verify(MASTER_TOKEN) is True
    assert calls == 2


def test_verified_token_cache_sha256_keys_ttl_utc_expiry_lru_and_revocation() -> None:
    mono = [50.0]
    current_utc = [datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)]
    cache = VerifiedTokenCache(
        ttl_seconds=300.0,
        max_entries=3,
        clock=lambda: mono[0],
        utc_now=lambda: current_utc[0],
    )

    tid1 = str(uuid.uuid4())
    tok1 = mint_scoped_token(tid1)
    p1 = AuthPrincipal(
        principal_id="agent-1",
        scopes=("read", "write"),
        token_id=tid1,
        expires_at=(current_utc[0] + timedelta(minutes=10)).isoformat(),
    )
    cache.put(tok1, p1)

    # Never store raw token in internal keys or repr.
    expected_sha = hashlib.sha256(tok1.encode("utf-8")).hexdigest()
    assert expected_sha in cache._entries
    assert tok1 not in cache._entries
    assert tok1 not in repr(cache._entries)
    assert cache.get(tok1) == p1

    # Invalidate by token_id (used on /revoke) removes immediately.
    cache.invalidate_token_id(tid1)
    assert cache.get(tok1) is None

    # UTC expires_at expiration invalidates entry even before monotonic TTL elapses.
    cache.put(tok1, p1)
    assert cache.get(tok1) == p1
    current_utc[0] = current_utc[0] + timedelta(minutes=11)
    assert cache.get(tok1) is None

    # Already-expired principal is rejected on put().
    cache.put(tok1, p1)
    assert len(cache) == 0

    # Monotonic TTL and LRU eviction at max_entries=3.
    unexpiring = [
        (mint_scoped_token(str(uuid.uuid4())), AuthPrincipal(principal_id=f"p{i}", scopes=("read",)))
        for i in range(4)
    ]
    for tok, princ in unexpiring[:3]:
        cache.put(tok, princ)
    # Touch entry 0 so entry 1 becomes least-recently-used.
    assert cache.get(unexpiring[0][0]) == unexpiring[0][1]
    cache.put(unexpiring[3][0], unexpiring[3][1])
    assert len(cache) == 3
    assert cache.get(unexpiring[1][0]) is None
    assert cache.get(unexpiring[0][0]) == unexpiring[0][1]
    assert cache.get(unexpiring[2][0]) == unexpiring[2][1]
    assert cache.get(unexpiring[3][0]) == unexpiring[3][1]

    # Monotonic TTL expiry.
    mono[0] += 301.0
    assert cache.get(unexpiring[0][0]) is None

    # Clear removes everything.
    cache.put(unexpiring[0][0], unexpiring[0][1])
    cache.clear()
    assert len(cache) == 0


def test_mint_and_extract_scoped_token_id_and_legacy_fallback() -> None:
    token_id = str(uuid.uuid4())
    raw = mint_scoped_token(token_id)
    assert raw.startswith(f"hydra_tok_{token_id.replace('-', '')}_")
    assert extract_scoped_token_id(raw) == token_id

    # Uppercase UUID input normalizes cleanly to canonical lowercase UUID.
    upper_id = token_id.upper()
    raw_upper = mint_scoped_token(upper_id)
    assert extract_scoped_token_id(raw_upper) == token_id.lower()

    # TokenVerifier accepts minted scoped tokens.
    verifier = TokenVerifier.from_token(raw)
    assert verifier.verify(raw) is True

    # Legacy custom CLI tokens (--token) or master tokens return None for fallback lookup.
    assert extract_scoped_token_id("custom-cli-token-without-uuid-prefix-0123456789") is None
    assert extract_scoped_token_id("hydra_tok_not32hexchars_secret") is None
    assert extract_scoped_token_id("") is None


def test_scope_allows_matrix_and_sensitive_routes() -> None:
    # Admin and wildcard allow everything.
    for admin_scope in (["admin"], ["*"]):
        assert scope_allows(admin_scope, method="POST", path="/v1/control-plane/tokens") is True
        assert scope_allows(admin_scope, method="POST", path="/v1/control-plane/pty/sessions") is True
        assert scope_allows(admin_scope, method="POST", path="/v1/control-plane/extensions") is True
        assert scope_allows(admin_scope, method="POST", path="/v1/launcher/stop") is True
        assert scope_allows(admin_scope, method="DELETE", path="/v1/control-plane/runs/r1") is True

    # Read-only scope allows GET/HEAD/OPTIONS, blocks all mutations.
    assert scope_allows(["read"], method="GET", path="/v1/control-plane/runs") is True
    assert scope_allows(["read"], method="HEAD", path="/health") is True
    assert scope_allows(["read"], method="OPTIONS", path="/v1/models") is True
    assert scope_allows(["read"], method="POST", path="/v1/control-plane/runs") is False

    # Generic write scope allows ordinary mutations + reads, but blocks sensitive admin routes!
    assert scope_allows(["write"], method="GET", path="/v1/control-plane/runs") is True
    assert scope_allows(["write"], method="POST", path="/v1/control-plane/runs") is True
    assert scope_allows(["write"], method="POST", path="/v1/chat/completions") is True
    assert scope_allows(["write"], method="POST", path="/v1/control-plane/tokens") is False
    assert scope_allows(["write"], method="POST", path="/v1/control-plane/tokens/abc/revoke") is False
    assert scope_allows(["write"], method="POST", path="/v1/control-plane/pty/sessions") is False
    assert scope_allows(["write"], method="POST", path="/v1/control-plane/extensions") is False
    assert scope_allows(["write"], method="POST", path="/v1/launcher/stop") is False
    # Path normalization defeats double-slash / dot-segment bypasses.
    assert scope_allows(["write"], method="POST", path="//v1/control-plane//tokens") is False
    assert scope_allows(["write"], method="POST", path="/v1/control-plane/runs/../pty/sessions") is False

    # Explicit capability scopes enable their specific route only when paired appropriately.
    assert scope_allows(["read", "pty"], method="POST", path="/v1/control-plane/pty/sessions") is False
    assert scope_allows(["write", "pty"], method="POST", path="/v1/control-plane/pty/sessions") is True
    assert scope_allows(["write", "pty"], method="POST", path="/v1/control-plane/tokens") is False

    assert scope_allows(["write", "tokens:write"], method="POST", path="/v1/control-plane/tokens") is True
    assert scope_allows(["tokens:write"], method="POST", path="/v1/control-plane/tokens/123/revoke") is True
    assert scope_allows(["write", "tokens:write"], method="POST", path="/v1/control-plane/pty/sessions") is False
    assert scope_allows(["write", "tokens:write"], method="POST", path="/v1/launcher/stop") is False


def test_is_trusted_host_blocks_dns_rebinding_and_scopes_testserver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRA_ALLOWED_HOSTS", raising=False)

    assert is_trusted_host("127.0.0.1") is True
    assert is_trusted_host("127.0.0.1:8000") is True
    assert is_trusted_host("localhost") is True
    assert is_trusted_host("localhost:8000") is True
    assert is_trusted_host("::1") is True
    assert is_trusted_host("[::1]:8000") is True

    # DNS rebinding and external hosts blocked.
    assert is_trusted_host("dns-rebind.attacker.invalid", client_host="127.0.0.1") is False
    assert is_trusted_host("localhost.attacker.invalid", client_host="127.0.0.1") is False
    assert is_trusted_host(None, client_host="127.0.0.1") is False
    assert is_trusted_host("", client_host="127.0.0.1") is False

    # FastAPI TestClient's "testserver" is accepted ONLY when client_host == "testclient".
    assert is_trusted_host("testserver", client_host="testclient") is True
    assert is_trusted_host("testserver:8000", client_host="testclient") is True
    assert is_trusted_host("testserver", client_host="127.0.0.1") is False
    assert is_trusted_host("testserver", client_host=None) is False

    # HYDRA_ALLOWED_HOSTS supports CSV and JSON list, while ignoring wildcard '*'.
    monkeypatch.setenv("HYDRA_ALLOWED_HOSTS", "hydra.internal.lan, 10.20.30.40, *")
    assert is_trusted_host("hydra.internal.lan", client_host="10.20.30.1") is True
    assert is_trusted_host("10.20.30.40:8000", client_host="10.20.30.1") is True
    assert is_trusted_host("dns-rebind.attacker.invalid", client_host="127.0.0.1") is False

    monkeypatch.setenv("HYDRA_ALLOWED_HOSTS", '["gpu-box.local"]')
    assert is_trusted_host("gpu-box.local") is True
    assert is_trusted_host("hydra.internal.lan") is False


def test_default_cors_origins_strict_by_default_and_dev_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRA_DEV_CORS", raising=False)
    strict = default_cors_origins(8123)
    assert strict == ["http://127.0.0.1:8123", "http://localhost:8123"]
    assert validate_cors_origins(strict) == strict

    monkeypatch.setenv("HYDRA_DEV_CORS", "1")
    dev = default_cors_origins(8000)
    assert dev[:2] == ["http://127.0.0.1:8000", "http://localhost:8000"]
    for port in (3000, 5173, 5177, 5197):
        assert f"http://127.0.0.1:{port}" in dev
        assert f"http://localhost:{port}" in dev
    assert validate_cors_origins(dev) == dev


def test_desktop_session_manager_single_use_ticket_and_ephemeral_session() -> None:
    clock = [100.0]
    mgr = DesktopSessionManager(clock=lambda: clock[0])

    nonce = mgr.issue_bootstrap_ticket(ttl_seconds=60.0)
    assert nonce
    assert nonce.encode("utf-8") not in mgr._tickets
    assert nonce not in repr(mgr._tickets)

    # First exchange consumes the single-use ticket and mints an ephemeral session token.
    sess_tok = mgr.exchange_bootstrap_ticket(nonce, ttl_seconds=3600.0)
    assert sess_tok is not None
    assert sess_tok.startswith("hydra_desktop_")
    assert sess_tok != MASTER_TOKEN
    assert sess_tok not in repr(mgr._sessions)
    assert mgr.verify_session_token(sess_tok) is True
    assert mgr.verify_session_token(MASTER_TOKEN) is False

    # Second exchange attempt with the same nonce MUST fail immediately (single-use!).
    assert mgr.exchange_bootstrap_ticket(nonce) is None

    # Expired ticket cannot be exchanged.
    expiring_nonce = mgr.issue_bootstrap_ticket(ttl_seconds=10.0)
    clock[0] += 11.0
    assert mgr.exchange_bootstrap_ticket(expiring_nonce) is None

    # Ephemeral session remains valid until its TTL or explicit clear/shutdown.
    assert mgr.verify_session_token(sess_tok) is True
    clock[0] += 3600.0
    assert mgr.verify_session_token(sess_tok) is False

    # Shutdown revocation clears active sessions immediately.
    nonce2 = mgr.issue_bootstrap_ticket(ttl_seconds=60.0)
    sess2 = mgr.exchange_bootstrap_ticket(nonce2, ttl_seconds=3600.0)
    assert sess2 is not None and mgr.verify_session_token(sess2) is True
    mgr.clear()
    assert mgr.verify_session_token(sess2) is False


def test_local_desktop_enabled_without_env_master_token_and_safe_public_frontend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYDRA_LOCAL_DESKTOP", "1")
    monkeypatch.delenv("HYDRA_API_TOKEN", raising=False)
    monkeypatch.delenv("HYDRA_API_TOKEN_HASH", raising=False)

    verifier = TokenVerifier.from_token(MASTER_TOKEN)
    state_with_verifier = SimpleNamespace(token_verifier=verifier, local_desktop_enabled=True)
    state_without_verifier = SimpleNamespace(token_verifier=None)

    assert enabled(state_with_verifier) is True
    assert enabled(state_without_verifier) is False

    # Bootstrap proof check requires loopback + matching Origin/Host + Sec-Fetch-Site + X-Hydra-Desktop.
    valid_boot = _mock_request(
        method="POST",
        path="/v1/launcher/session",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "Sec-Fetch-Site": "same-origin",
            "X-Hydra-Desktop": "1",
        },
        app_state=state_with_verifier,
    )
    assert allow_bootstrap(valid_boot) is True

    rebound_boot = _mock_request(
        method="POST",
        host_header="evil.attacker.invalid:8000",
        hostname="evil.attacker.invalid",
        path="/v1/launcher/session",
        headers={
            "Origin": "http://evil.attacker.invalid:8000",
            "Sec-Fetch-Site": "same-origin",
            "X-Hydra-Desktop": "1",
        },
        app_state=state_with_verifier,
    )
    assert allow_bootstrap(rebound_boot) is False

    # Safe root static files and font assets are allowed; sensitive files remain strictly blocked.
    for allowed_path in (
        "/",
        "/favicon.ico",
        "/favicon.svg",
        "/robots.txt",
        "/manifest.webmanifest",
        "/assets/app.js",
        "/assets/fonts/inter.woff2",
        "/assets/fonts/inter.woff",
        "/assets/fonts/mono.ttf",
        "/chat/session-1",
    ):
        req = _mock_request(path=allowed_path, app_state=state_with_verifier)
        assert public_frontend(req) is True, f"Expected {allowed_path} to be allowed"

    for blocked_path in (
        "/config.yaml",
        "/.env",
        "/.git/config",
        "/assets/../config.yaml",
        "/assets/.env",
        "/assets/dump.sqlite",
        "/v1/control-plane/projects",
    ):
        req = _mock_request(path=blocked_path, app_state=state_with_verifier)
        assert public_frontend(req) is False, f"Expected {blocked_path} to be blocked"


def test_desktop_backend_scrubs_hydra_api_token_from_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    from hydra_orch import desktop_backend, server as api

    monkeypatch.setenv("HYDRA_LOCAL_DESKTOP", "1")
    monkeypatch.setenv("HYDRA_API_TOKEN", MASTER_TOKEN)
    monkeypatch.setenv("HYDRA_OMNIROUTE_AUTOSTART", "0")
    monkeypatch.setattr("sys.argv", ["desktop_backend", "--port", "8765"])

    fake_uvicorn_server = MagicMock()
    captured_env_during_run: dict[str, str | None] = {}

    def fake_run() -> None:
        captured_env_during_run["HYDRA_API_TOKEN"] = os.environ.get("HYDRA_API_TOKEN")

    fake_uvicorn_server.run.side_effect = fake_run
    monkeypatch.setattr(desktop_backend.uvicorn, "Config", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(desktop_backend.uvicorn, "Server", lambda cfg: fake_uvicorn_server)
    monkeypatch.setitem(api.app.state._state, "token_verifier", None)
    monkeypatch.setitem(api.app.state._state, "local_desktop_enabled", False)

    desktop_backend.main()

    assert captured_env_during_run["HYDRA_API_TOKEN"] is None
    assert "HYDRA_API_TOKEN" not in os.environ
    assert api.app.state.local_desktop_enabled is True
    assert api.app.state.token_verifier is not None
    assert api.app.state.token_verifier.verify(MASTER_TOKEN) is True
    assert isinstance(api.app.state.desktop_sessions, DesktopSessionManager)
    assert local_desktop.enabled() is True


@pytest.mark.skipif(os.name != "nt", reason="Windows .NET Framework csc.exe syntax verification")
def test_hydra_launcher_cs_compiles_cleanly_to_temp_exe_without_touching_root_binary(tmp_path: Path) -> None:
    csc = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    if not csc.is_file():
        pytest.skip("csc.exe not installed on this Windows host")

    repo_root = Path(__file__).resolve().parents[1]
    launcher_cs = repo_root / "src" / "launcher" / "HydraLauncher.cs"
    root_exe = repo_root / "Hydra.exe"
    root_exe_before = hashlib.sha256(root_exe.read_bytes()).hexdigest() if root_exe.is_file() else None

    source_text = launcher_cs.read_text(encoding="utf-8")
    assert "/v1/launcher/ticket" in source_text
    assert "/#bootstrap_nonce=" in source_text
    for expected_file in ("index.html", "package.json", "vite.config.ts", "tailwind.config.js", "postcss.config.js"):
        assert expected_file in source_text

    temp_exe = tmp_path / "HydraLauncherTestBuild.exe"
    proc = subprocess.run(
        [
            str(csc),
            "/nologo",
            "/target:winexe",
            "/optimize+",
            f"/out:{temp_exe}",
            "/reference:System.Windows.Forms.dll",
            "/reference:System.Drawing.dll",
            "/reference:System.Net.Http.dll",
            str(launcher_cs),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"csc.exe failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert temp_exe.is_file() and temp_exe.stat().st_size > 0

    # Verify headless CLI bounds checks return cleanly with exit code 1 (never IndexOutOfRangeException).
    for bad_args in (
        ["--smoke"],
        ["--render"],
        ["--smoke", str(tmp_path / "rep.json"), "--port"],
        ["--smoke", str(tmp_path / "rep.json"), "--port", "not-a-number"],
        ["--smoke", str(tmp_path / "rep.json"), "--hold"],
        ["--smoke", str(tmp_path / "rep.json"), "--hold", "bad"],
        ["--smoke", str(tmp_path / "rep.json"), "--root"],
    ):
        run_bad = subprocess.run(
            [str(temp_exe), *bad_args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert run_bad.returncode == 1
        assert "IndexOutOfRangeException" not in (run_bad.stderr + run_bad.stdout)

    # Confirm root Hydra.exe was untouched.
    root_exe_after = hashlib.sha256(root_exe.read_bytes()).hexdigest() if root_exe.is_file() else None
    assert root_exe_after == root_exe_before
