"""Security and Windows ConPTY/.cmd hardening tests (Wave 1C: SEC-02, DAY-01, BE-18, SEC-06, SEC-07)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Dict, List

import httpx
import pytest

from hydra_orch.adapter.ui_cdp import UiCdpAdapter
from hydra_orch.bridge.agent_executable import (
    format_windows_cmd_commandline,
    resolve_npm_node_script,
)
from hydra_orch.bridge.conpty import ConPtyProcess, conpty_available
from hydra_orch.bridge.conversation_runner import ConversationRunner
from hydra_orch.bridge.extension_runner import (
    ExtensionAnomalyError,
    ExtensionPolicy,
    ExtensionRunner,
)
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.bridge.pty_runner import PtyRunner
from hydra_orch.bridge.ssh_tunnel import (
    SshTunnelManager,
    TransportSecurityError,
    compute_ssh_host_key_fingerprint,
)
from hydra_orch.bridge.worker_runner import WorkerRunner
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.conversation_route import ConversationRouteStore, ConversationRoutes
from hydra_orch.model import ContractViolation


def _make_ssh_key_blob(seed: bytes) -> tuple[str, str]:
    raw_key = b"\x00\x00\x00\x0bssh-ed25519" + hashlib.sha256(seed).digest()
    b64 = base64.b64encode(raw_key).decode("ascii")
    return b64, compute_ssh_host_key_fingerprint(b64)


# ---------------------------------------------------------------------------
# 1. SEC-02 + DAY-01: npm .cmd unwrapping, cmd.exe escaping & injection defense
# ---------------------------------------------------------------------------


def test_resolve_npm_node_script_unwraps_npm_shims_and_preserves_custom_shims(tmp_path: Path) -> None:
    bin_dir = tmp_path / "npm_bin"
    js_dir = bin_dir / "node_modules" / "@openai" / "codex" / "bin"
    js_dir.mkdir(parents=True)
    js_entry = js_dir / "codex.js"
    js_entry.write_text("console.log('ok');\n", encoding="utf-8")

    fake_node = bin_dir / ("node.exe" if os.name == "nt" else "node")
    fake_node.write_bytes(b"MZ-fake-node")

    # Classic npm cmd-shim format using %dp0%
    dp0_shim = bin_dir / "codex.cmd"
    dp0_shim.write_text(
        '@ECHO off\r\n'
        'GOTO start\r\n'
        ':find_dp0\r\n'
        'SET dp0=%~dp0\r\n'
        'EXIT /b\r\n'
        ':start\r\n'
        'SETLOCAL\r\n'
        'CALL :find_dp0\r\n'
        'IF EXIST "%dp0%\\node.exe" (\r\n'
        '  SET "_prog=%dp0%\\node.exe"\r\n'
        ') ELSE (\r\n'
        '  SET "_prog=node"\r\n'
        ')\r\n'
        '"%_prog%"  "%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js" %*\r\n',
        encoding="utf-8",
    )
    resolved_dp0 = resolve_npm_node_script(dp0_shim)
    assert resolved_dp0 == (str(fake_node), str(js_entry.resolve()))

    # Direct %~dp0 format + node resolved via PATH when not adjacent
    other_dir = tmp_path / "other_bin"
    other_js_dir = other_dir / "node_modules" / "gemini-cli"
    other_js_dir.mkdir(parents=True)
    mjs_entry = other_js_dir / "cli.mjs"
    mjs_entry.write_text("export {};\n", encoding="utf-8")
    tilde_shim = other_dir / "gemini.cmd"
    tilde_shim.write_text(
        '@IF EXIST "%~dp0\\node.exe" (\r\n'
        '  "%~dp0\\node.exe" "%~dp0\\node_modules\\gemini-cli\\cli.mjs" %*\r\n'
        ') ELSE (\r\n'
        '  node "%~dp0\\node_modules\\gemini-cli\\cli.mjs" %*\r\n'
        ')\r\n',
        encoding="utf-8",
    )
    resolved_tilde = resolve_npm_node_script(tilde_shim, path=str(bin_dir))
    assert resolved_tilde == (str(fake_node), str(mjs_entry.resolve()))

    # Custom test python shim MUST return None so .cmd test shims remain supported
    py_shim = bin_dir / "custom_test.cmd"
    py_shim.write_text(f'@echo off\r\n"{sys.executable}" "fake_cli.py" %*\r\n', encoding="utf-8")
    assert resolve_npm_node_script(py_shim) is None

    # Native .exe inside node_modules (e.g. claude.exe) MUST return None (not JS)
    exe_in_nm = js_dir / "native.exe"
    exe_in_nm.write_bytes(b"MZ")
    native_shim = bin_dir / "claude_native.cmd"
    native_shim.write_text('"%dp0%\\node_modules\\@openai\\codex\\bin\\native.exe" %*\r\n', encoding="utf-8")
    assert resolve_npm_node_script(native_shim) is None


def test_format_windows_cmd_commandline_rejects_control_chars_and_escapes_meta() -> None:
    for bad in ("line1\nline2", "line1\rline2", "nul\x00byte"):
        with pytest.raises(ValueError):
            format_windows_cmd_commandline(["C:\\bin\\tool.cmd", bad])

    with pytest.raises(ValueError):
        format_windows_cmd_commandline([])
    with pytest.raises(ValueError):
        format_windows_cmd_commandline(['C:\\bin\\bad"quote.cmd', "ok"])
    with pytest.raises(ValueError):
        format_windows_cmd_commandline(["C:\\bin\\%PATH%\\tool.cmd", "ok"])

    formatted = format_windows_cmd_commandline(
        ["C:\\Program Files\\Tool\\agent.cmd", '" & echo INJECTED', "%PATH%", "!TEMP!"]
    )
    assert formatted.startswith('"C:\\Program Files\\Tool\\agent.cmd" ')
    assert "^&" in formatted
    assert "%^P" in formatted
    assert "^!" in formatted


@pytest.mark.skipif(os.name != "nt", reason="Windows real .cmd / ConPTY injection suite")
@pytest.mark.asyncio
async def test_windows_cmd_shim_blocks_command_injection_in_worker_and_conpty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYDRA_INJECT_PROBE", "SENSITIVE_EXPANDED_VALUE")
    shim_dir = tmp_path / "bin with spaces"
    shim_dir.mkdir(parents=True)
    marker = tmp_path / "marker.txt"
    recorded = tmp_path / "recorded.json"

    probe_py = shim_dir / "probe_cli.py"
    probe_py.write_text(
        "import json, pathlib, sys\n"
        "stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ''\n"
        "payload = {'argv': sys.argv[1:], 'stdin': stdin_text}\n"
        f"pathlib.Path({str(recorded)!r}).write_text(json.dumps(payload), encoding='utf-8')\n"
        "print(json.dumps(payload), flush=True)\n",
        encoding="utf-8",
    )

    # Create shims for gemini.cmd, codex.cmd, and a generic custom shim
    for name in ("gemini.cmd", "opencode.cmd", "codex.cmd", "raw shim.cmd"):
        (shim_dir / name).write_text(
            f'@echo off\r\n"{sys.executable}" "{probe_py}" %*\r\n',
            encoding="utf-8",
        )

    attack_arg = f'" & echo PWNED > "{marker}" & echo %HYDRA_INJECT_PROBE% !PATH!'
    simple_attack = f'" & echo PWNED > {marker}'
    patched_path = f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    # 1. WorkerRunner custom_command with .cmd shim + malicious argv payloads
    runner = WorkerRunner(default_cli="codex")
    res_custom = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="stdin-body",
        custom_command=(str(shim_dir / "raw shim.cmd"), simple_attack, attack_arg, "%HYDRA_INJECT_PROBE%"),
    )
    assert res_custom["success"] is True, res_custom
    assert not marker.exists(), "Command injection executed via WorkerRunner custom_command!"
    data_custom = json.loads(recorded.read_text(encoding="utf-8"))
    assert data_custom["argv"] == [simple_attack, attack_arg, "%HYDRA_INJECT_PROBE%"]
    assert "SENSITIVE_EXPANDED_VALUE" not in json.dumps(data_custom)

    # 2. WorkerRunner DAY-01 + SEC-02: driver resolved from PATH (.cmd) with malicious multiline prompt
    recorded.unlink(missing_ok=True)
    malicious_prompt = f'Fix issue\n" & echo PWNED > {marker}\n%HYDRA_INJECT_PROBE%'
    res_gemini = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt=malicious_prompt,
        cli_name="gemini",
        extra_args=(simple_attack,),
        allowed_env={"PATH": patched_path},
    )
    assert res_gemini["success"] is True, res_gemini
    assert not marker.exists(), "Command injection executed via gemini.cmd driver!"
    data_gemini = json.loads(recorded.read_text(encoding="utf-8"))
    # Prompt was moved to stdin (not argv) for .cmd driver, and extra_args was safely escaped!
    assert data_gemini["argv"] == [simple_attack]
    assert data_gemini["stdin"] == malicious_prompt

    # 3. WorkerRunner DAY-01: codex.cmd resolved from PATH without custom_command (no WinError 2!)
    recorded.unlink(missing_ok=True)
    res_codex = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="apply fix",
        cli_name="codex",
        allowed_env={"PATH": patched_path},
    )
    assert res_codex["success"] is True, res_codex
    assert not marker.exists()

    # 4. Direct ConPtyProcess with .cmd shim + malicious argument
    pty_py = shim_dir / "pty_arg_probe.py"
    pty_out = tmp_path / "pty_argv.json"
    pty_py.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(pty_out)!r}).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
        "print('CONPTY_DONE', flush=True)\n",
        encoding="utf-8",
    )
    pty_shim = shim_dir / "conpty_shim.cmd"
    pty_shim.write_text(f'@echo off\r\n"{sys.executable}" "{pty_py}" %*\r\n', encoding="utf-8")

    if conpty_available():
        cproc = ConPtyProcess(
            [str(pty_shim), simple_attack, attack_arg, "%HYDRA_INJECT_PROBE%"],
            cwd=str(tmp_path),
            env=dict(os.environ),
        )
        try:
            await asyncio.to_thread(cproc.wait_blocking, 8.0)
            await asyncio.to_thread(cproc.close_console)
            while await asyncio.to_thread(cproc.read_blocking, 4096):
                pass
        finally:
            await asyncio.to_thread(cproc.close)

        assert not marker.exists(), "Command injection executed inside ConPtyProcess!"
        assert pty_out.is_file()
        assert json.loads(pty_out.read_text(encoding="utf-8")) == [
            simple_attack,
            attack_arg,
            "%HYDRA_INJECT_PROBE%",
        ]

    # 5. PtyRunner pipe bridge fallback also prevents .cmd injection and rejects newline args
    monkeypatch.setenv("HYDRA_PTY_BACKEND", "pipe")
    pty_runner = PtyRunner()
    try:
        with pytest.raises(ContractViolation) as bad_cmd_exc:
            await pty_runner.open_session(
                [str(pty_shim), "bad\ninjection"],
                cwd=tmp_path,
            )
        assert bad_cmd_exc.value.code == "invalid_pty_command"

        pty_out.unlink(missing_ok=True)
        sess = await pty_runner.open_session(
            [str(pty_shim), simple_attack, "%HYDRA_INJECT_PROBE%"],
            cwd=tmp_path,
        )
        await pty_runner.wait(sess.session_id, timeout=8.0)
        assert not marker.exists(), "Command injection executed via PtyRunner pipe bridge!"
        assert json.loads(pty_out.read_text(encoding="utf-8")) == [simple_attack, "%HYDRA_INJECT_PROBE%"]
    finally:
        await pty_runner.close_all()


@pytest.mark.asyncio
async def test_conversation_runner_validates_session_id_model_hint_and_unwraps_npm_shim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hydra_orch.bridge.conversation_runner as conv_mod

    # Create a fake npm codex.cmd + codex.js + fake node binary
    npm_dir = tmp_path / "npm"
    codex_js_dir = npm_dir / "node_modules" / "@openai" / "codex" / "bin"
    codex_js_dir.mkdir(parents=True)
    codex_js = codex_js_dir / "codex.js"
    codex_js.write_text("// codex entrypoint\n", encoding="utf-8")
    node_bin = npm_dir / ("node.exe" if os.name == "nt" else "node")
    node_bin.write_bytes(b"MZ")
    codex_cmd = npm_dir / "codex.cmd"
    codex_cmd.write_text('"%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js" node %*\r\n', encoding="utf-8")

    monkeypatch.setattr(conv_mod, "resolve_agent_executable", lambda _drv: str(codex_cmd))
    runner = ConversationRunner()

    # Reject malicious native_session_id values
    for bad_session in (
        "--dangerously-bypass-approvals-and-sandbox",
        'sess" & calc',
        "sess\ninjected",
        "sess with space",
        "../escape",
    ):
        with pytest.raises(ContractViolation) as s_exc:
            await runner.invocation(
                {"executor": "codex", "access_mode": "read-only", "native_session_id": bad_session},
                tmp_path,
            )
        assert s_exc.value.code == "invalid_session_id"

    # Reject malicious target_ref / model_hint values
    for bad_model in (
        "--evil-flag",
        'gpt-5" & echo pwned',
        "model\nname",
        "model;id",
        "%PATH%",
        "!TEMP!",
        " leading-space",
    ):
        with pytest.raises(ContractViolation) as m_exc:
            await runner.invocation(
                {
                    "executor": "codex",
                    "access_mode": "read-only",
                    "route": {"connection_mode": "direct", "target_ref": bad_model},
                },
                tmp_path,
            )
        assert m_exc.value.code == "route_invalid"

        with pytest.raises(ContractViolation) as mh_exc:
            await runner.invocation(
                {
                    "executor": "codex",
                    "access_mode": "read-only",
                    "model_hint": bad_model,
                },
                tmp_path,
            )
        assert mh_exc.value.code == "route_invalid"

    # Valid session + valid model on Windows unwraps npm .cmd directly to [node_exe, codex.js, --sandbox, ...]
    args, _env, transport, _obs = await runner.invocation(
        {
            "executor": "codex",
            "access_mode": "read-only",
            "native_session_id": "sess-valid_01",
            "route": {"connection_mode": "direct", "target_ref": "gpt-5.4"},
        },
        tmp_path,
    )
    transport.close()
    if os.name == "nt":
        assert args[0] == str(node_bin)
        assert args[1] == str(codex_js.resolve())
        assert args[2:4] == ["--sandbox", "read-only"]


# ---------------------------------------------------------------------------
# 2. BE-18: Async conpty.close() & LRU/TTL closed session pruning in PtyRunner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pty_runner_async_conpty_close_and_lru_ttl_pruning(tmp_path: Path) -> None:
    runner = PtyRunner(max_closed_sessions=2, closed_ttl_seconds=60.0)
    close_threads: List[bool] = []

    if os.name == "nt" and conpty_available():
        orig_close = ConPtyProcess.close

        def tracked_close(self: ConPtyProcess) -> None:
            close_threads.append(threading.current_thread() is not threading.main_thread())
            orig_close(self)

        ConPtyProcess.close = tracked_close  # type: ignore[method-assign]
    else:
        orig_close = None

    ttl_runner = PtyRunner(max_closed_sessions=32, closed_ttl_seconds=0.2)
    try:
        finished_ids: List[str] = []
        for idx in range(4):
            sid = f"prune-lru-{idx}"
            info = await runner.open_session(
                [sys.executable, "-c", f"print('done-{idx}')"],
                cwd=tmp_path,
                session_id=sid,
            )
            done = await runner.wait(info.session_id, timeout=5.0)
            assert done.status == "exited"
            # ConPTY handle reference on state must be cleared as soon as session finalizes
            if sid in runner._sessions:
                assert runner._sessions[sid].conpty is None
            finished_ids.append(sid)

        if close_threads:
            assert all(close_threads), "ConPtyProcess.close() must run off the main event-loop thread"

        # With max_closed_sessions=2, only the 2 most recently closed sessions remain
        remaining = [s.session_id for s in runner.list_sessions()]
        assert len(remaining) == 2
        assert set(remaining) == set(finished_ids[-2:])
        for evicted_id in finished_ids[:2]:
            with pytest.raises(ContractViolation) as nf:
                runner.get_session(evicted_id)
            assert nf.value.code == "resource_not_found"

        # Now verify TTL pruning on ttl_runner: closed sessions expire while running sessions stay untouched
        exp_info = await ttl_runner.open_session(
            [sys.executable, "-c", "print('will-expire')"],
            cwd=tmp_path,
            session_id="ttl-expired-1",
        )
        await ttl_runner.wait(exp_info.session_id, timeout=5.0)

        live = await ttl_runner.open_session(
            [sys.executable, "-u", "-c", "import time; print('UP', flush=True); time.sleep(30)"],
            cwd=tmp_path,
            session_id="keep-alive-running",
        )
        await asyncio.sleep(0.3)  # Exceed closed_ttl_seconds=0.2

        # Opening another session triggers TTL pruning of expired closed sessions while preserving running
        short = await ttl_runner.open_session(
            [sys.executable, "-c", "print('fresh')"],
            cwd=tmp_path,
            session_id="fresh-after-ttl",
        )
        await ttl_runner.wait(short.session_id, timeout=5.0)

        active_ids = {s.session_id for s in ttl_runner.list_sessions()}
        assert live.session_id in active_ids
        assert short.session_id in active_ids
        assert exp_info.session_id not in active_ids
    finally:
        if orig_close is not None:
            ConPtyProcess.close = orig_close  # type: ignore[method-assign]
        await runner.close_all()
        await ttl_runner.close_all()


# ---------------------------------------------------------------------------
# 3. SEC-06: Extension sandbox (native binary block + ctypes/DNS block),
#            OmniRoute loopback/auth guard, and CDP strict origin matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extension_runner_blocks_native_binaries_ctypes_and_dns(tmp_path: Path) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    workdir = tmp_path / "work"

    # 1. Non-.py entrypoint rejected unless allow_native_binary=True
    native_ep = ext_dir / ("plugin.exe" if os.name == "nt" else "plugin.bin")
    native_ep.write_bytes(b"MZ-binary")
    denied_policy = ExtensionPolicy(
        entrypoint=native_ep,
        sandbox_workdir=workdir,
        forbidden_paths=(),
    )
    runner_denied = ExtensionRunner(denied_policy)
    with pytest.raises(ContractViolation) as un_exc:
        await runner_denied.start()
    assert un_exc.value.code == "extension_sandbox_unsupported"

    # 2. Python sandbox blocks ctypes.CDLL, ctypes.cdll/windll, and socket.getaddrinfo when net disabled
    py_ep = ext_dir / "sandbox_probe.py"
    py_ep.write_text(
        "import ctypes, socket\n"
        "def handle(method, params):\n"
        "    if method == 'ctypes_cdll':\n"
        "        return str(ctypes.cdll.msvcrt)\n"
        "    if method == 'ctypes_windll':\n"
        "        loader = getattr(ctypes, 'windll', ctypes.cdll)\n"
        "        return str(loader.kernel32)\n"
        "    if method == 'ctypes_dlopen':\n"
        "        return str(ctypes.CDLL('libc.so.6'))\n"
        "    if method == 'dns_lookup':\n"
        "        return str(socket.getaddrinfo('example.com', 80))\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )

    for probe_method in ("ctypes_cdll", "ctypes_windll", "ctypes_dlopen", "dns_lookup"):
        policy = ExtensionPolicy(
            entrypoint=py_ep,
            sandbox_workdir=workdir / probe_method,
            forbidden_paths=(),
            allow_net_loopback=False,
            allow_net_external=False,
        )
        ext_runner = ExtensionRunner(policy, timeout_seconds=5.0)
        await ext_runner.start()
        try:
            assert await ext_runner.call("ping") == {"ok": True}
            with pytest.raises(ExtensionAnomalyError) as anom:
                await ext_runner.call(probe_method)
            assert anom.value.code == "extension_sandbox_violation"
        finally:
            await ext_runner.stop()


@pytest.mark.asyncio
async def test_omniroute_loopback_allowlist_and_external_auth_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HYDRA_OMNIROUTE_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("HYDRA_OMNIROUTE_ALLOW_EXTERNAL_AUTH", raising=False)
    monkeypatch.setenv("OMNIROUTE_API_KEY", "sk-omni-local-secret-999")

    store = ExecutionStore(tmp_path / "routes.sqlite")
    gateway = OmniRouteClient(enabled=False)
    routes = ConversationRouteStore(store, gateway)
    assert isinstance(routes, ConversationRoutes)

    # Non-loopback host rejected by both save_settings and OmniRouteClient
    with pytest.raises(ContractViolation) as save_exc:
        await routes.save_settings(
            base_url="https://omniroute.evil.example/v1",
            enabled=True,
            expected_version=0,
            idempotency_key="reject-ext-1",
        )
    assert save_exc.value.code == "route_invalid"

    with pytest.raises(ContractViolation) as init_exc:
        OmniRouteClient(base_url="https://omniroute.evil.example/v1")
    assert init_exc.value.code == "route_invalid"

    # Loopback hosts allowed by default and receive OMNIROUTE_API_KEY automatically
    for loopback_url in (
        "http://127.0.0.1:20128/v1",
        "http://localhost:20128/v1",
        "http://[::1]:20128/v1",
    ):
        lb_client = OmniRouteClient(base_url=loopback_url)
        assert lb_client._resolve_api_key() == "sk-omni-local-secret-999"

    # Explicit allowlist (CSV and JSON) permits the host, WITHOUT sending env OMNIROUTE_API_KEY automatically
    monkeypatch.setenv("HYDRA_OMNIROUTE_ALLOWED_HOSTS", "gateway.corp.internal, 10.20.30.40")
    saved = await routes.save_settings(
        base_url="https://gateway.corp.internal:8443/v1",
        enabled=True,
        expected_version=0,
        idempotency_key="allow-ext-1",
    )
    assert saved["base_url"] == "https://gateway.corp.internal:8443/v1"
    assert saved["credential_available"] is False

    seen_auth: List[str | None] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"data": [{"id": "codex/gpt-5"}]})

    ext_client = OmniRouteClient(
        base_url="https://gateway.corp.internal:8443/v1",
        quota_api_url="https://gateway.corp.internal:8443/api/usage/quota",
        transport=httpx.MockTransport(mock_handler),
    )
    assert ext_client._resolve_api_key() is None
    await ext_client.list_models()
    assert seen_auth == [None]

    # Opt-in HYDRA_OMNIROUTE_ALLOW_EXTERNAL_AUTH=1 enables sending env API key to allowed external host
    monkeypatch.setenv("HYDRA_OMNIROUTE_ALLOWED_HOSTS", '["gateway.corp.internal"]')
    monkeypatch.setenv("HYDRA_OMNIROUTE_ALLOW_EXTERNAL_AUTH", "1")
    assert ext_client._resolve_api_key() == "sk-omni-local-secret-999"
    await ext_client.list_models()
    assert seen_auth[-1] == "Bearer sk-omni-local-secret-999"


@pytest.mark.asyncio
async def test_ui_cdp_strict_origin_matching_and_no_first_tab_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages_payload: List[Dict[str, Any]] = [
        {
            "type": "page",
            "url": "https://mail.google.com/mail/u/0/#inbox",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/gmail-user-tab",
        },
        {
            "type": "page",
            "url": "https://evil.example/?redirect=https://claude.ai/chat",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/substring-spoof",
        },
        {
            "type": "page",
            "url": "https://claude.ai.evil.example/chat",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/subdomain-spoof",
        },
        {
            "type": "page",
            "url": "http://claude.ai/chat",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/wrong-scheme",
        },
        {
            "type": "page",
            "url": "https://claude.ai:8443/chat",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/wrong-port",
        },
    ]

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, url: str) -> httpx.Response:
            return httpx.Response(200, json=pages_payload)

    monkeypatch.setattr("hydra_orch.adapter.ui_cdp.httpx.AsyncClient", _FakeAsyncClient)

    adapter = UiCdpAdapter("claude_pro", {"cdp_port": 9222, "target_url": "https://claude.ai/new"})

    # No tab matches exact (https, claude.ai, 443) -> MUST raise explicit error and NEVER fall back to pages[0]!
    assert await adapter.is_available() is False
    with pytest.raises(ContractViolation) as cdp_exc:
        await adapter._get_websocket_url()
    assert cdp_exc.value.code == "cdp_target_mismatch"

    # Empty target_url is also rejected (never attaches to arbitrary tab)
    empty_adapter = UiCdpAdapter("claude_pro", {"cdp_port": 9222, "target_url": ""})
    with pytest.raises(ContractViolation) as empty_exc:
        await empty_adapter._get_websocket_url()
    assert empty_exc.value.code == "cdp_target_mismatch"

    # Adding a real https://claude.ai tab matches exact (scheme, hostname, port)
    pages_payload.append(
        {
            "type": "page",
            "url": "https://claude.ai/chat/session-42",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/legit-claude",
        }
    )
    assert await adapter.is_available() is True
    assert await adapter._get_websocket_url() == "ws://127.0.0.1:9222/devtools/page/legit-claude"


# ---------------------------------------------------------------------------
# 4. SEC-07: SshTunnelManager option injection defense, `--`, and filtered env
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_cfg",
    [
        {"host": ""},
        {"host": "   "},
        {"host": "-oProxyCommand=calc.exe"},
        {"host": "gpu node.local"},
        {"host": "gpu\nnode.local"},
        {"remote_host": ""},
        {"remote_host": "-oLocalCommand=evil"},
        {"remote_host": "127.0.0.1 22"},
        {"user": ""},
        {"user": "-oProxyCommand=evil"},
        {"user": "bad user"},
        {"user": "bad\x00user"},
        {"ssh_target": ""},
        {"ssh_target": "-oProxyCommand=evil@host"},
        {"ssh_target": "hydra@-oProxyCommand=evil"},
        {"ssh_target": "hydra@bad host"},
        {"key_path": ""},
        {"key_path": "-oProxyCommand=evil"},
        {"key_path": "path with space/id_ed25519"},
        {"key_path": "bad\nkey"},
        {"ssh_key": "-i"},
        {"key_file": ""},
    ],
)
def test_ssh_tunnel_rejects_dangerous_or_empty_parameters(bad_cfg: Dict[str, Any]) -> None:
    with pytest.raises((TransportSecurityError, ContractViolation, ValueError)) as exc_info:
        SshTunnelManager(bad_cfg)
    assert isinstance(exc_info.value, ContractViolation)
    assert isinstance(exc_info.value, ValueError)


def test_ssh_tunnel_command_double_dash_and_filtered_env_on_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_b64, expected_fp = _make_ssh_key_blob(b"sec07-host-key")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"[gpu.internal]:2222 ssh-ed25519 {key_b64}\n", encoding="utf-8")
    key_file = tmp_path / "id_ed25519"
    key_file.write_text("DUMMY_KEY_CONTENT\n", encoding="utf-8")

    manager = SshTunnelManager(
        {
            "host": "gpu.internal",
            "remote_host": "127.0.0.1",
            "user": "hydra",
            "port": 2222,
            "local_port": 15435,
            "remote_port": 11434,
            "key_path": str(key_file),
            "known_hosts_file": str(known_hosts),
            "expected_host_key_fingerprint": expected_fp,
        },
        host_key_verifier=lambda _h, _p: expected_fp,
    )

    cmd = manager.build_ssh_command()
    # "--" MUST appear immediately before positional destination "hydra@gpu.internal"
    assert cmd[-2:] == ["--", "hydra@gpu.internal"]
    dash_idx = cmd.index("--")
    assert "-p" in cmd[:dash_idx]
    assert "-i" in cmd[:dash_idx]
    assert "-L" in cmd[:dash_idx]

    # Verify start_tunnel passes sanitized filter_worker_env() to subprocess.Popen
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-must-not-leak-to-ssh")
    monkeypatch.setenv("HYDRA_API_TOKEN", "hydra-secret-must-not-leak-to-ssh")
    captured: Dict[str, Any] = {}

    class _DummyProc:
        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(popen_cmd: List[str], **kwargs: Any) -> _DummyProc:
        captured["cmd"] = popen_cmd
        captured["env"] = kwargs.get("env")
        return _DummyProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    assert manager.start_tunnel() is True
    assert captured["cmd"][-2:] == ["--", "hydra@gpu.internal"]
    assert isinstance(captured["env"], dict)
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "HYDRA_API_TOKEN" not in captured["env"]
    assert captured["env"].get("HYDRA_WORKER_ISOLATED") == "1"
    manager.stop_tunnel()
