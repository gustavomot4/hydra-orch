"""Hermetic M5 OS PTY certification matrix, process-tree cleanup, and capabilities tests (T36)."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi.testclient import TestClient as BaseTestClient
import pytest
from typer.testing import CliRunner

from hydra_orch import cli
from hydra_orch.bridge import pty_runner as pty_runner_mod
from hydra_orch.bridge.pty_runner import PtyRunner, detect_pty_backend
from hydra_orch.bridge.worker_runner import is_process_alive
from hydra_orch.config import HydraConfig
from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.run_service import RunService
from hydra_orch.core.search_index import build_host_capabilities
from hydra_orch.server import app, set_run_service


def test_bundled_codex_uses_only_a_supported_no_daemon_option(tmp_path, monkeypatch):
    bundled = str(tmp_path / "app" / "resources" / "codex.exe")
    standalone = str(tmp_path / "bin" / "codex.exe")
    calls = []

    def help_with_option(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="Options: --no-daemon")

    pty_runner_mod._bundled_codex_needs_no_daemon.cache_clear()
    try:
        monkeypatch.setattr(pty_runner_mod.subprocess, "run", help_with_option)
        assert pty_runner_mod._bundled_codex_needs_no_daemon(bundled) is True
        assert pty_runner_mod._bundled_codex_needs_no_daemon(bundled) is True
        assert pty_runner_mod._bundled_codex_needs_no_daemon(standalone) is False
        assert len(calls) == 1

        pty_runner_mod._bundled_codex_needs_no_daemon.cache_clear()
        monkeypatch.setattr(pty_runner_mod.subprocess, "run",
                            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Options: --help"))
        assert pty_runner_mod._bundled_codex_needs_no_daemon(bundled) is False
    finally:
        pty_runner_mod._bundled_codex_needs_no_daemon.cache_clear()


async def _wait_for_dead(pids: List[int], *, attempts: int = 100, interval: float = 0.05) -> None:
    """Poll until all tracked OS process IDs have terminated."""
    for _ in range(attempts):
        if all(not is_process_alive(pid) for pid in pids):
            return
        await asyncio.sleep(interval)


async def _wait_for_output_substring(
    runner: PtyRunner,
    session_id: str,
    needle: str,
    *,
    attempts: int = 80,
    interval: float = 0.05,
) -> str:
    """Poll session scrollback until `needle` appears or attempts expire."""
    combined = ""
    for _ in range(attempts):
        chunks = runner.read_output(session_id, after_seq=0)
        combined = "".join(c.text for c in chunks)
        if needle in combined:
            return combined
        await asyncio.sleep(interval)
    return combined


# ---------------------------------------------------------------------------
# 1. Active Host OS PTY Certification & Lifecycle Matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pty_active_host_os_capability_and_lifecycle(tmp_path: Path) -> None:
    """Verify host OS PTY backend detection, capabilities, echo, resize, and zero surviving PIDs."""
    runner = PtyRunner()
    expected_backend, expected_certified = detect_pty_backend()
    caps = build_host_capabilities(HydraConfig())
    pty_cap = caps["hosts"]["local"]["capabilities"]["pty"]

    if os.name == "nt" and pty_runner_mod._windows_conpty_enabled():
        assert (expected_backend, expected_certified) == ("windows_conpty", True)
        assert runner.backend_info == ("windows_conpty", True)
        assert runner.backend_kind == "windows_conpty"
        assert runner.pty_certified is True
        assert pty_cap["backend_kind"] == "windows_conpty"
        assert pty_cap["certified"] is True
        assert pty_cap["status"] == "available"
        assert pty_cap["supported"] is True
        assert pty_cap["reason"] is None
    elif os.name == "nt":
        assert (expected_backend, expected_certified) == ("pipe_interactive_bridge", False)
        assert runner.backend_info == ("pipe_interactive_bridge", False)
        assert runner.backend_kind == "pipe_interactive_bridge"
        assert runner.pty_certified is False
        assert pty_cap["backend_kind"] == "pipe_interactive_bridge"
        assert pty_cap["certified"] is False
        assert pty_cap["status"] == "degraded"
        assert pty_cap["supported"] is True
        assert pty_cap["reason"] == "windows_conpty_uncertified_using_pipe_bridge"
    else:
        assert (expected_backend, expected_certified) == ("posix_pty", True)
        assert runner.backend_info == ("posix_pty", True)
        assert runner.backend_kind == "posix_pty"
        assert runner.pty_certified is True
        assert pty_cap["backend_kind"] == "posix_pty"
        assert pty_cap["certified"] is True
        assert pty_cap["status"] == "available"
        assert pty_cap["supported"] is True
        assert pty_cap["reason"] is None

    echo_wait_script = (
        "import sys, time\n"
        "print('MATRIX_READY', flush=True)\n"
        "line = sys.stdin.readline().strip()\n"
        "print(f'MATRIX_ECHO:{line}', flush=True)\n"
        "time.sleep(30)\n"
    )
    tree_script = (
        "import json, os, pathlib, subprocess, sys, time\n"
        f"pids_path = pathlib.Path({str(tmp_path / 'matrix_tree_pids.json')!r})\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "pids_path.write_text(json.dumps({'parent': os.getpid(), 'child': child.pid}), encoding='utf-8')\n"
        "print('TREE_READY', flush=True)\n"
        "line = sys.stdin.readline().strip()\n"
        "print(f'TREE_ECHO:{line}', flush=True)\n"
        "time.sleep(60)\n"
    )

    try:
        # Phase A: real spawn -> stdin echo -> resize -> interrupt -> zero surviving PID
        info_a = await runner.open_session(
            [sys.executable, "-u", "-c", echo_wait_script],
            cwd=tmp_path,
            session_id="matrix-interrupt",
            cols=80,
            rows=24,
        )
        assert info_a.backend_kind == expected_backend
        assert info_a.pty_certified is expected_certified
        assert info_a.pid is not None

        assert "MATRIX_READY" in await _wait_for_output_substring(runner, "matrix-interrupt", "MATRIX_READY")
        await runner.write_input("matrix-interrupt", "hello-os-matrix\n")
        assert "MATRIX_ECHO:hello-os-matrix" in await _wait_for_output_substring(
            runner, "matrix-interrupt", "MATRIX_ECHO:hello-os-matrix"
        )

        resized_a = await runner.resize("matrix-interrupt", cols=120, rows=40)
        assert (resized_a.cols, resized_a.rows) == (120, 40)

        await runner.interrupt("matrix-interrupt")
        done_a = await runner.wait("matrix-interrupt", timeout=5.0)
        assert done_a.status in {"exited", "cancelled"}
        await _wait_for_dead([info_a.pid])
        assert is_process_alive(info_a.pid) is False

        # Phase B: real spawn with grandchild -> stdin echo -> resize -> close_session -> tree dead
        info_b = await runner.open_session(
            [sys.executable, "-u", "-c", tree_script],
            cwd=tmp_path,
            session_id="matrix-tree-close",
            cols=90,
            rows=28,
        )
        assert info_b.backend_kind == expected_backend
        assert info_b.pty_certified is expected_certified

        pids_file = tmp_path / "matrix_tree_pids.json"
        for _ in range(80):
            if pids_file.exists() and "TREE_READY" in "".join(c.text for c in runner.read_output("matrix-tree-close")):
                break
            await asyncio.sleep(0.05)

        assert pids_file.exists()
        pids = json.loads(pids_file.read_text(encoding="utf-8"))
        parent_pid = int(pids["parent"])
        child_pid = int(pids["child"])
        assert is_process_alive(parent_pid) is True
        assert is_process_alive(child_pid) is True

        await runner.write_input("matrix-tree-close", "tree-ping\n")
        assert "TREE_ECHO:tree-ping" in await _wait_for_output_substring(
            runner, "matrix-tree-close", "TREE_ECHO:tree-ping"
        )

        resized_b = await runner.resize("matrix-tree-close", cols=132, rows=44)
        assert (resized_b.cols, resized_b.rows) == (132, 44)

        closed_b = await runner.close_session("matrix-tree-close", keep_running=False)
        assert closed_b.status == "cancelled"
        await _wait_for_dead([parent_pid, child_pid])
        assert is_process_alive(parent_pid) is False
        assert is_process_alive(child_pid) is False
    finally:
        await runner.close_all()


@pytest.mark.asyncio
async def test_pty_openpty_oserror_graceful_fallback_to_pipe_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify POSIX PTY branch falls back cleanly to pipe_interactive_bridge if openpty() raises OSError."""

    def _raise_oserror() -> Tuple[int, int]:
        raise OSError("simulated openpty exhaustion")

    monkeypatch.setattr(pty_runner_mod, "_HAS_POSIX_PTY", True)
    if pty_runner_mod.pty is not None:
        monkeypatch.setattr(pty_runner_mod.pty, "openpty", _raise_oserror)
    else:
        monkeypatch.setattr(pty_runner_mod, "pty", SimpleNamespace(openpty=_raise_oserror))
        monkeypatch.setattr(pty_runner_mod, "termios", SimpleNamespace(TIOCSCTTY=0x540E, TIOCSWINSZ=0x5414))
        monkeypatch.setattr(pty_runner_mod, "fcntl", SimpleNamespace(ioctl=lambda *args, **kwargs: None))

    runner = PtyRunner()
    assert detect_pty_backend() == ("posix_pty", True)

    script = (
        "import sys\n"
        "print('FALLBACK_READY', flush=True)\n"
        "line = sys.stdin.readline().strip()\n"
        "print(f'FALLBACK_ECHO:{line}', flush=True)\n"
    )
    try:
        info = await runner.open_session(
            [sys.executable, "-u", "-c", script],
            cwd=tmp_path,
            session_id="pty-fallback-1",
        )
        assert info.backend_kind == "pipe_interactive_bridge"
        assert info.pty_certified is False
        assert info.pid is not None

        assert "FALLBACK_READY" in await _wait_for_output_substring(runner, "pty-fallback-1", "FALLBACK_READY")
        await runner.write_input("pty-fallback-1", "fallback-ok\n")
        done = await runner.wait("pty-fallback-1", timeout=5.0)
        assert done.status == "exited"
        assert done.exit_code == 0

        combined = "".join(c.text for c in runner.read_output("pty-fallback-1", after_seq=0))
        assert "FALLBACK_ECHO:fallback-ok" in combined
        await _wait_for_dead([info.pid])
        assert is_process_alive(info.pid) is False
    finally:
        await runner.close_all()


@pytest.mark.asyncio
async def test_pty_simulated_posix_pty_tiocswinsz_and_master_fd_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hermetically test POSIX PTY branch (TIOCSWINSZ, TIOCSCTTY, master_fd close) on any OS."""
    real_os = os
    next_pair_idx = 0
    fd_pairs = [(9001, 9002), (9003, 9004)]
    open_fds: Dict[int, Dict[str, Any]] = {}
    closed_fds: List[int] = []
    ioctl_calls: List[Tuple[int, int, bytes]] = []
    written_to_master: List[Tuple[int, bytes]] = []
    set_blocking_calls: List[Tuple[int, bool]] = []
    readers: Dict[int, Callable[[], None]] = {}
    removed_readers: List[int] = []
    alive_pids: set[int] = set()
    killed_pids: List[int] = []
    sessions_by_pid: Dict[int, Tuple[int, "_FakeProcess"]] = {}

    def _fake_openpty() -> Tuple[int, int]:
        nonlocal next_pair_idx
        master_fd, slave_fd = fd_pairs[next_pair_idx]
        next_pair_idx += 1
        open_fds[master_fd] = {"chunks": [], "eof": False}
        open_fds[slave_fd] = {"chunks": [], "eof": False}
        return master_fd, slave_fd

    def _fake_ioctl(fd: int, request: int, arg: Any = 0) -> None:
        raw_bytes = bytes(arg) if isinstance(arg, (bytes, bytearray)) else b""
        ioctl_calls.append((fd, request, raw_bytes))

    class _FakeOsProxy:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_os, name)

        def close(self, fd: int) -> None:
            if fd in open_fds:
                open_fds.pop(fd, None)
                closed_fds.append(fd)
                return
            real_os.close(fd)

        def set_blocking(self, fd: int, flag: bool) -> None:
            if fd in open_fds:
                set_blocking_calls.append((fd, flag))
                return
            if hasattr(real_os, "set_blocking"):
                real_os.set_blocking(fd, flag)

        def read(self, fd: int, n: int) -> bytes:
            if fd in open_fds:
                chunks: List[bytes] = open_fds[fd]["chunks"]
                if chunks:
                    return chunks.pop(0)[:n]
                if open_fds[fd]["eof"]:
                    return b""
                raise BlockingIOError()
            return real_os.read(fd, n)

        def write(self, fd: int, data: bytes) -> int:
            if fd in open_fds:
                written_to_master.append((fd, bytes(data)))
                return len(data)
            return real_os.write(fd, data)

        def getpgid(self, pid: int) -> int:
            if pid in alive_pids:
                return pid
            return real_os.getpgid(pid)

        def killpg(self, pgid: int, sig: int) -> None:
            if pgid in sessions_by_pid:
                killed_pids.append(pgid)
                return
            real_os.killpg(pgid, sig)

    class _FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid
            self.returncode: Optional[int] = None
            self.stdin = None
            self.stdout = None
            self.stderr = None
            self._done = asyncio.Event()

        def finish(self, code: int) -> None:
            self.returncode = code
            alive_pids.discard(self.pid)
            self._done.set()

        async def wait(self) -> int:
            await self._done.wait()
            assert self.returncode is not None
            return self.returncode

    next_pid = 81000

    async def _fake_create_subprocess_exec(*command: str, **kwargs: Any) -> _FakeProcess:
        nonlocal next_pid
        next_pid += 1
        pid = next_pid
        assert kwargs.get("start_new_session") is True
        assert kwargs.get("close_fds") is True
        assert kwargs.get("stdin") == kwargs.get("stdout") == kwargs.get("stderr")
        preexec = kwargs.get("preexec_fn")
        if callable(preexec):
            preexec()
        proc = _FakeProcess(pid)
        alive_pids.add(pid)
        master_fd = int(kwargs["stdin"]) - 1
        sessions_by_pid[pid] = (master_fd, proc)
        return proc

    def _fake_is_process_alive(pid: int) -> bool:
        return pid in alive_pids

    async def _fake_cancel_process_tree(pid: int, **kwargs: Any) -> bool:
        killed_pids.append(pid)
        entry = sessions_by_pid.get(pid)
        if entry is not None:
            master_fd, proc = entry
            proc.finish(-15)
            if master_fd in open_fds:
                open_fds[master_fd]["eof"] = True
                cb = readers.get(master_fd)
                if cb is not None:
                    cb()
        return True

    loop = asyncio.get_running_loop()

    def _fake_add_reader(fd: int, cb: Callable[[], None]) -> None:
        readers[fd] = cb

    def _fake_remove_reader(fd: int) -> bool:
        removed_readers.append(fd)
        return readers.pop(fd, None) is not None

    TIOCSCTTY = 0x540E
    TIOCSWINSZ = 0x5414

    monkeypatch.setattr(pty_runner_mod, "_HAS_POSIX_PTY", True)
    monkeypatch.setattr(pty_runner_mod, "pty", SimpleNamespace(openpty=_fake_openpty))
    monkeypatch.setattr(pty_runner_mod, "termios", SimpleNamespace(TIOCSCTTY=TIOCSCTTY, TIOCSWINSZ=TIOCSWINSZ))
    monkeypatch.setattr(pty_runner_mod, "fcntl", SimpleNamespace(ioctl=_fake_ioctl))
    monkeypatch.setattr(pty_runner_mod, "os", _FakeOsProxy())
    monkeypatch.setattr(pty_runner_mod, "is_process_alive", _fake_is_process_alive)
    monkeypatch.setattr(pty_runner_mod, "cancel_process_tree", _fake_cancel_process_tree)
    monkeypatch.setattr(pty_runner_mod.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(loop, "add_reader", _fake_add_reader)
    monkeypatch.setattr(loop, "remove_reader", _fake_remove_reader)

    assert detect_pty_backend() == ("posix_pty", True)
    posix_caps = build_host_capabilities(HydraConfig())["hosts"]["local"]["capabilities"]["pty"]
    assert posix_caps["status"] == "available"
    assert posix_caps["certified"] is True
    assert posix_caps["backend_kind"] == "posix_pty"

    runner = PtyRunner()
    try:
        # Session 1: verify TIOCSWINSZ on spawn & resize, write_input, read via master_fd, close on natural EOF
        info1 = await runner.open_session(
            ["/bin/sh", "-i"],
            cwd=tmp_path,
            session_id="sim-posix-eof",
            cols=80,
            rows=24,
        )
        assert info1.backend_kind == "posix_pty"
        assert info1.pty_certified is True
        assert 9002 in closed_fds  # slave_fd closed immediately in parent
        assert (9002, TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0)) in ioctl_calls
        assert (9002, TIOCSCTTY, b"") in ioctl_calls

        await asyncio.sleep(0)  # allow _pump_posix_pty to register reader
        assert 9001 in readers
        assert (9001, False) in set_blocking_calls

        open_fds[9001]["chunks"].append(b"\x1b[32mPOSIX_OK\x1b[0m\n")
        readers[9001]()
        await asyncio.sleep(0)

        chunks1 = runner.read_output("sim-posix-eof", after_seq=0)
        assert len(chunks1) == 1
        assert chunks1[0].stream == "pty"
        assert "POSIX_OK" in chunks1[0].text

        written = await runner.write_input("sim-posix-eof", "uname -a\n")
        assert written == len(b"uname -a\n")
        assert (9001, b"uname -a\n") in written_to_master

        resized = await runner.resize("sim-posix-eof", cols=132, rows=48)
        assert (resized.cols, resized.rows) == (132, 48)
        assert (9001, TIOCSWINSZ, struct.pack("HHHH", 48, 132, 0, 0)) in ioctl_calls

        # Trigger natural EOF + process exit -> master_fd 9001 must be removed & closed
        open_fds[9001]["eof"] = True
        readers[9001]()
        sessions_by_pid[info1.pid][1].finish(0)
        done1 = await runner.wait("sim-posix-eof", timeout=2.0)
        assert done1.status == "exited"
        assert done1.exit_code == 0
        assert 9001 in removed_readers
        assert 9001 in closed_fds

        # Session 2: verify close_session(keep_running=False) kills process tree & closes master_fd
        info2 = await runner.open_session(
            ["/bin/sh", "-i"],
            cwd=tmp_path,
            session_id="sim-posix-close",
            cols=100,
            rows=30,
        )
        await asyncio.sleep(0)
        assert 9004 in closed_fds
        assert 9003 in readers

        closed2 = await runner.close_session("sim-posix-close", keep_running=False)
        assert closed2.status == "cancelled"
        assert info2.pid in killed_pids
        assert 9003 in removed_readers
        assert 9003 in closed_fds
    finally:
        await runner.close_all()


# ---------------------------------------------------------------------------
# 2. Zero Orphaned Child/Grandchild Processes on PtyRunner.close_all()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pty_close_all_terminates_concurrent_sessions_and_grandchildren(tmp_path: Path) -> None:
    """Verify PtyRunner.close_all() leaves zero orphan parent or grandchild PIDs across concurrent sessions."""
    runner = PtyRunner()
    session_count = 3
    all_pids: List[int] = []
    session_ids = [f"orphan-check-{i}" for i in range(session_count)]

    try:
        for idx, sid in enumerate(session_ids):
            pid_file = tmp_path / f"pids_{idx}.json"
            script = (
                "import json, os, pathlib, subprocess, sys, time\n"
                "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                f"pathlib.Path({str(pid_file)!r}).write_text("
                "json.dumps({'parent': os.getpid(), 'grandchild': grandchild.pid}), encoding='utf-8')\n"
                f"print('CONCURRENT_READY_{idx}', flush=True)\n"
                "time.sleep(60)\n"
            )
            await runner.open_session(
                [sys.executable, "-u", "-c", script],
                cwd=tmp_path,
                session_id=sid,
            )

        for idx, sid in enumerate(session_ids):
            pid_file = tmp_path / f"pids_{idx}.json"
            for _ in range(100):
                ready = f"CONCURRENT_READY_{idx}" in "".join(c.text for c in runner.read_output(sid))
                if pid_file.exists() and ready:
                    break
                await asyncio.sleep(0.05)
            assert pid_file.exists(), f"PID file missing for session {sid}"
            payload = json.loads(pid_file.read_text(encoding="utf-8"))
            parent_pid = int(payload["parent"])
            grandchild_pid = int(payload["grandchild"])
            assert is_process_alive(parent_pid) is True
            assert is_process_alive(grandchild_pid) is True
            all_pids.extend([parent_pid, grandchild_pid])

        # Detach one session first to verify close_all() kills both attached and detached trees
        detached = await runner.close_session(session_ids[0], keep_running=True)
        assert detached.detached is True
        assert detached.status == "running"

        await runner.close_all()
        await _wait_for_dead(all_pids)

        for pid in all_pids:
            assert is_process_alive(pid) is False, f"Orphan PID survived close_all(): {pid}"
        for sid in session_ids:
            assert runner.get_session(sid).status == "cancelled"
    finally:
        await runner.close_all()


# ---------------------------------------------------------------------------
# 3. Control Plane Bootstrap & Capabilities Honest Reporting + CLI Smoke
# ---------------------------------------------------------------------------


def _init_temp_git_repo(base_dir: Path) -> Path:
    """Create a minimal Git repository inside `base_dir` for isolated RunService tests."""
    repo = base_dir / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@hydra.local"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra Matrix Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("hydra matrix test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    return repo


def test_control_plane_bootstrap_and_capabilities_honest_reporting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify /v1/control-plane/bootstrap and /capabilities report honest PTY and Parking Lot status."""
    token = "hydra-m5-matrix-local-bearer-token-0123456789"
    verifier = TokenVerifier.from_token(token)
    monkeypatch.setitem(app.state._state, "token_verifier", verifier)
    monkeypatch.setenv("HYDRA_API_TOKEN", token)
    monkeypatch.delenv("HYDRA_API_TOKEN_HASH", raising=False)

    repo = _init_temp_git_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    asyncio.run(store.initialize())
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    set_run_service(svc)
    try:
        client = BaseTestClient(app, headers={"Authorization": f"Bearer {token}"})
        expected_backend, expected_certified = detect_pty_backend()
        expected_pty_status = "available" if expected_certified else "degraded"

        boot_resp = client.get("/v1/control-plane/bootstrap")
        assert boot_resp.status_code == 200, boot_resp.text
        boot_data = boot_resp.json()
        boot_local_caps = boot_data["capabilities"]["hosts"]["local"]["capabilities"]

        assert boot_local_caps["pty"]["backend_kind"] == expected_backend
        assert boot_local_caps["pty"]["certified"] is expected_certified
        assert boot_local_caps["pty"]["status"] == expected_pty_status
        assert boot_local_caps["pty"]["supported"] is True

        assert boot_local_caps["mobile_emulator"]["status"] == "unavailable"
        assert boot_local_caps["mobile_emulator"]["certified"] is False
        assert boot_local_caps["mobile_emulator"]["supported"] is False
        assert boot_local_caps["mobile_emulator"]["reason"] == "uncertified_parking_lot_bridge"

        assert boot_local_caps["computer_use"]["status"] == "unavailable"
        assert boot_local_caps["computer_use"]["certified"] is False
        assert boot_local_caps["computer_use"]["supported"] is False
        assert boot_local_caps["computer_use"]["reason"] == "uncertified_parking_lot_bridge"

        assert boot_local_caps["dictation_stt"]["certified"] is False
        assert boot_local_caps["dictation_stt"]["duplex_voice_enabled"] is False
        assert boot_local_caps["dictation_stt"]["available_modes"] == ["browser_optional_text_draft"]

        cap_resp = client.get("/v1/control-plane/capabilities")
        assert cap_resp.status_code == 200, cap_resp.text
        cap_data = cap_resp.json()
        cap_local_caps = cap_data["host_capabilities"]["hosts"]["local"]["capabilities"]

        assert cap_local_caps["pty"]["backend_kind"] == expected_backend
        assert cap_local_caps["pty"]["certified"] is expected_certified
        assert cap_local_caps["pty"]["status"] == expected_pty_status
        assert cap_local_caps["mobile_emulator"]["status"] == "unavailable"
        assert cap_local_caps["mobile_emulator"]["certified"] is False
        assert cap_local_caps["computer_use"]["status"] == "unavailable"
        assert cap_local_caps["computer_use"]["certified"] is False
    finally:
        set_run_service(None)


def test_m5_cli_entrypoint_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke check M5 CLI commands (route, automation, watch, ui) with isolated state."""
    repo = _init_temp_git_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    monkeypatch.setattr(cli, "get_cli_run_service", lambda: svc)
    monkeypatch.setattr(cli, "load_config", lambda *args, **kwargs: HydraConfig())

    runner = CliRunner()
    for args in (
        ["route", "--help"],
        ["automation", "--help"],
        ["watch", "--help"],
        ["ui", "--help"],
    ):
        res = runner.invoke(cli.app, args)
        assert res.exit_code == 0, f"CLI smoke failed for {args}: {res.output}"

    inv_res = runner.invoke(cli.app, ["route", "inventory", "--json"])
    assert inv_res.exit_code == 0, inv_res.output
    inv_payload = json.loads(inv_res.output)
    assert inv_payload["connection_mode"] == "disabled"
    assert inv_payload["available"] is False

@pytest.mark.asyncio
async def test_m5_windows_conpty_tty_resize_cmd_shim_and_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Certify native Windows ConPTY isatty/resize/.cmd shim execution and pipe fallback."""
    import os
    import sys

    if os.name != "nt":
        assert detect_pty_backend() in {("posix_pty", True), ("pipe_interactive_bridge", False)}
        return

    monkeypatch.delenv("HYDRA_PTY_BACKEND", raising=False)
    assert detect_pty_backend() == ("windows_conpty", True)

    shim_dir = tmp_path / "shim dir"
    shim_dir.mkdir(parents=True, exist_ok=True)
    py_script = shim_dir / "tty_probe.py"
    py_script.write_text(
        "import os, sys, time\n"
        "print(f'ISATTY:{os.isatty(1)}', flush=True)\n"
        "sz1 = os.get_terminal_size(1)\n"
        "print(f'SIZE1:{sz1.columns}x{sz1.lines} ARG:{sys.argv[1]}', flush=True)\n"
        "line = sys.stdin.readline().strip()\n"
        "sz2 = os.get_terminal_size(1)\n"
        "print(f'SIZE2:{sz2.columns}x{sz2.lines} LINE:{line}', flush=True)\n",
        encoding="utf-8",
    )
    shim_cmd = shim_dir / "probe shim.cmd"
    shim_cmd.write_text(
        f'@echo off\r\n"{sys.executable}" "{py_script}" %*\r\n',
        encoding="utf-8",
    )

    runner = PtyRunner()
    try:
        info = await runner.open_session(
            [str(shim_cmd), "arg with space"],
            cwd=str(tmp_path),
            cols=100,
            rows=32,
        )
        assert info.backend_kind == "windows_conpty"
        assert info.pty_certified is True

        deadline = asyncio.get_running_loop().time() + 10.0
        buf = ""
        cursor = 0
        while asyncio.get_running_loop().time() < deadline:
            for chunk in runner.read_output(info.session_id, after_seq=cursor):
                buf += chunk.text
                cursor = chunk.seq
            if "SIZE1:100x32" in buf and "ARG:arg with space" in buf:
                break
            await asyncio.sleep(0.05)

        assert "ISATTY:True" in buf
        assert "SIZE1:100x32" in buf
        assert "ARG:arg with space" in buf

        resized = await runner.resize(info.session_id, cols=132, rows=44)
        assert resized.cols == 132
        assert resized.rows == 44
        await asyncio.sleep(0.15)
        await runner.write_input(info.session_id, "go\n")

        deadline2 = asyncio.get_running_loop().time() + 10.0
        while asyncio.get_running_loop().time() < deadline2:
            for chunk in runner.read_output(info.session_id, after_seq=cursor):
                buf += chunk.text
                cursor = chunk.seq
            if "SIZE2:132x44" in buf and "LINE:go" in buf:
                break
            await asyncio.sleep(0.05)

        assert "SIZE2:132x44" in buf
        assert "LINE:go" in buf
    finally:
        await runner.close_all()

    monkeypatch.setenv("HYDRA_PTY_BACKEND", "pipe")
    assert detect_pty_backend() == ("pipe_interactive_bridge", False)
    caps = build_host_capabilities()
    local_pty = caps["hosts"]["local"]["capabilities"]["pty"]
    assert local_pty["backend_kind"] == "pipe_interactive_bridge"
    assert local_pty["certified"] is False
    assert local_pty["status"] == "degraded"
