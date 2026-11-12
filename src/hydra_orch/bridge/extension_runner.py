"""T20: isolated subprocess runner and JSON-RPC 2.0 pipe bridge for extensions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence

from hydra_orch.bridge.worker_runner import cancel_process_tree, filter_worker_env, is_process_alive
from hydra_orch.core.redaction import redact
from hydra_orch.model import ContractViolation

_SANDBOX_BOOTSTRAP = r"""
import asyncio
import inspect
import importlib.util
import json
import os
import sqlite3
import sys
import traceback

def _norm(p):
    return os.path.normcase(os.path.realpath(os.fsdecode(p)))

def _within(target, root):
    if target == root:
        return True
    sep = os.sep
    if not root.endswith(sep):
        root = root + sep
    return target.startswith(root)

policy_line = sys.stdin.readline()
if not policy_line:
    sys.exit(2)
policy = json.loads(policy_line)

entrypoint = _norm(policy["entrypoint"])
sandbox_workdir = _norm(policy["sandbox_workdir"])
allowed_read = [_norm(p) for p in policy.get("allowed_read_roots", ())]
allowed_write = [_norm(p) for p in policy.get("allowed_write_roots", ())]
forbidden = [_norm(p) for p in policy.get("forbidden_paths", ())]
allow_loopback = bool(policy.get("allow_net_loopback", False))
allow_external = bool(policy.get("allow_net_external", False))
allow_spawn = bool(policy.get("allow_spawn", False))

sys_read_roots = []
for candidate in (sys.prefix, sys.base_prefix, sys.exec_prefix, getattr(sys, "base_exec_prefix", sys.exec_prefix), *sys.path):
    if candidate:
        try:
            sys_read_roots.append(_norm(candidate))
        except OSError:
            pass
sys_read_roots = tuple(dict.fromkeys(sys_read_roots))

anomalies = []

def _trip(msg):
    if msg not in anomalies:
        anomalies.append(msg)
    raise PermissionError("sandbox_policy_violation: " + msg)

def _check_forbidden(real_path):
    for f in forbidden:
        if _within(real_path, f):
            _trip("access to core database or forbidden path denied")

def _check_read(path_arg):
    if isinstance(path_arg, int):
        return
    if not isinstance(path_arg, (str, bytes, os.PathLike)):
        return
    raw = os.fsdecode(path_arg)
    if not raw or raw in (os.devnull,):
        return
    real = _norm(raw)
    _check_forbidden(real)
    if real == entrypoint or _within(real, sandbox_workdir):
        return
    if any(_within(real, r) for r in sys_read_roots):
        return
    if any(_within(real, r) for r in allowed_read):
        return
    _trip("filesystem read outside permitted sandbox roots")

def _check_write(path_arg):
    if isinstance(path_arg, int):
        return
    if not isinstance(path_arg, (str, bytes, os.PathLike)):
        return
    raw = os.fsdecode(path_arg)
    if not raw or raw == os.devnull:
        return
    real = _norm(raw)
    _check_forbidden(real)
    if real == entrypoint:
        _trip("extension cannot modify its own entrypoint")
    if _within(real, sandbox_workdir) or any(_within(real, r) for r in allowed_write):
        return
    _trip("filesystem write outside permitted sandbox roots")

def _audit(event, args):
    if event == "sqlite3.connect":
        target = args[0] if args else ""
        if isinstance(target, (str, bytes, os.PathLike)):
            s = os.fsdecode(target)
            if s != ":memory:" and not s.startswith("file::memory:"):
                real = _norm(s)
                _check_forbidden(real)
                if not _within(real, sandbox_workdir):
                    _trip("sqlite database access outside sandbox denied")
    elif event == "open":
        path_arg = args[0] if len(args) > 0 else None
        mode = args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 else 0
        is_write = (isinstance(mode, str) and any(c in mode for c in ("w", "a", "x", "+"))) or bool(
            isinstance(flags, int) and (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | getattr(os, "O_APPEND", 0)))
        )
        if is_write:
            _check_write(path_arg)
        else:
            _check_read(path_arg)
    elif event in ("os.scandir", "os.listdir"):
        if args:
            _check_read(args[0])
    elif event in ("os.remove", "os.unlink", "os.rmdir", "os.mkdir"):
        if args:
            _check_write(args[0])
    elif event in ("os.rename", "os.replace", "shutil.copyfile", "shutil.copymode"):
        for a in args[:2]:
            _check_write(a)
    elif event == "socket.__new__":
        if not (allow_loopback or allow_external):
            _trip("network socket creation denied")
    elif event in ("socket.connect", "socket.bind", "socket.sendto"):
        if not (allow_loopback or allow_external):
            _trip("network socket access denied")
        if not allow_external and len(args) > 1 and isinstance(args[1], tuple) and args[1]:
            host = str(args[1][0]).lower()
            if host not in ("127.0.0.1", "::1", "localhost"):
                _trip("external network access denied")
    elif event in ("subprocess.Popen", "os.system", "os.exec", "os.spawn"):
        if not allow_spawn:
            _trip("subprocess spawn denied")

with open(entrypoint, "rb") as _ep_fh:
    _ep_source = _ep_fh.read()

sys.addaudithook(_audit)

import types as _types
mod = _types.ModuleType("hydra_sandboxed_extension")
mod.__file__ = policy["entrypoint"]
try:
    _ep_code = compile(_ep_source, policy["entrypoint"], "exec")
    exec(_ep_code, mod.__dict__)
except Exception as exc:
    msg = anomalies[0] if anomalies else str(exc)
    print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": msg, "data": {"anomaly": True}}}), flush=True)
    sys.exit(4)

handler = getattr(mod, "handle", None)
if not callable(handler):
    sys.stderr.write("Extension entrypoint must define callable handle(method, params)\n")
    sys.exit(3)

for raw_line in sys.stdin:
    raw_line = raw_line.strip()
    if not raw_line:
        continue
    req_id = None
    try:
        req = json.loads(raw_line)
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        if method == "initialize":
            result = {"ok": True, "api_version": policy.get("api_version", "1.0")}
        else:
            out = handler(method, params)
            if inspect.isawaitable(out):
                out = asyncio.run(out)
            result = out
        if anomalies:
            resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32001, "message": anomalies[0], "data": {"anomaly": True}}}
            print(json.dumps(resp), flush=True)
            break
        print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}), flush=True)
    except Exception as exc:
        is_anom = bool(anomalies) or "sandbox_policy_violation" in str(exc)
        msg = anomalies[0] if anomalies else str(exc)
        print(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32001 if is_anom else -32000, "message": msg, "data": {"anomaly": is_anom}}}), flush=True)
        if is_anom:
            break
"""


@dataclass(frozen=True)
class ExtensionPolicy:
    entrypoint: Path
    sandbox_workdir: Path
    forbidden_paths: tuple[Path, ...]
    allowed_read_roots: tuple[Path, ...] = ()
    allowed_write_roots: tuple[Path, ...] = ()
    allow_net_loopback: bool = False
    allow_net_external: bool = False
    allow_spawn: bool = False
    api_version: str = "1.0"


class ExtensionAnomalyError(ContractViolation):
    """Raised when an isolated extension violates sandbox or IPC boundaries."""

    def __init__(self, message: str):
        super().__init__("extension_sandbox_violation", message)


class ExtensionRunner:
    """Manages an isolated subprocess and line-delimited JSON-RPC 2.0 channel for one extension install."""

    def __init__(
        self,
        policy: ExtensionPolicy,
        *,
        allowed_env: Optional[Mapping[str, str]] = None,
        timeout_seconds: float = 10.0,
        max_message_bytes: int = 1024 * 1024,
    ):
        self.policy = policy
        self._allowed_env = dict(allowed_env or {})
        self.timeout_seconds = float(timeout_seconds)
        self.max_message_bytes = int(max_message_bytes)
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id = 1

    @property
    def pid(self) -> Optional[int]:
        if self._proc is None:
            return None
        return self._proc.pid

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and is_process_alive(self._proc.pid)

    async def start(self) -> None:
        if self.is_running:
            return
        self.policy.sandbox_workdir.mkdir(parents=True, exist_ok=True)
        env = filter_worker_env(allowed_env=self._allowed_env)
        env["HYDRA_EXTENSION_ISOLATED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        is_python = self.policy.entrypoint.suffix.lower() == ".py"
        if is_python:
            argv: Sequence[str] = (sys.executable, "-I", "-B", "-c", _SANDBOX_BOOTSTRAP)
        else:
            argv = (str(self.policy.entrypoint),)

        popen_kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": env,
            "cwd": str(self.policy.sandbox_workdir),
            "limit": self.max_message_bytes,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            self._proc = await asyncio.create_subprocess_exec(*argv, **popen_kwargs)
        except OSError as exc:
            raise ContractViolation("extension_spawn_failed", f"Failed to spawn extension process: {exc}") from exc

        if is_python:
            assert self._proc.stdin is not None
            policy_payload = json.dumps(
                {
                    "entrypoint": str(self.policy.entrypoint),
                    "sandbox_workdir": str(self.policy.sandbox_workdir),
                    "allowed_read_roots": [str(p) for p in self.policy.allowed_read_roots],
                    "allowed_write_roots": [str(p) for p in self.policy.allowed_write_roots],
                    "forbidden_paths": [str(p) for p in self.policy.forbidden_paths],
                    "allow_net_loopback": self.policy.allow_net_loopback,
                    "allow_net_external": self.policy.allow_net_external,
                    "allow_spawn": self.policy.allow_spawn,
                    "api_version": self.policy.api_version,
                },
                separators=(",", ":"),
            )
            self._proc.stdin.write((policy_payload + "\n").encode("utf-8"))
            await self._proc.stdin.drain()

        try:
            await self.call("initialize", {"api_version": self.policy.api_version})
        except Exception:
            await self.stop()
            raise

    async def call(self, method: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise ContractViolation("extension_not_running", "Extension subprocess is not running")
        if self._proc.returncode is not None:
            raise ContractViolation("extension_not_running", "Extension subprocess has exited")
        req_id = self._next_id
        self._next_id += 1
        encoded = (
            json.dumps(
                {"jsonrpc": "2.0", "id": req_id, "method": method, "params": dict(params or {})},
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > self.max_message_bytes:
            raise ContractViolation("extension_message_too_large", "Extension request exceeds max_message_bytes")
        try:
            self._proc.stdin.write(encoded)
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            await self.stop()
            raise ExtensionAnomalyError(f"Extension pipe failed during write: {exc}") from exc

        async def _read() -> Any:
            assert self._proc is not None and self._proc.stdout is not None
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    stderr_tail = b""
                    if self._proc.stderr is not None:
                        try:
                            stderr_tail = await asyncio.wait_for(self._proc.stderr.read(4096), timeout=0.2)
                        except asyncio.TimeoutError:
                            pass
                    detail = redact(stderr_tail.decode("utf-8", errors="replace").strip())
                    raise ExtensionAnomalyError(f"Extension exited unexpectedly ({detail or 'eof'})")
                if len(line) > self.max_message_bytes:
                    raise ExtensionAnomalyError("Extension response exceeds max_message_bytes")
                msg = json.loads(line.decode("utf-8"))
                if not isinstance(msg, dict):
                    continue
                if msg.get("id") is not None and msg.get("id") != req_id:
                    continue
                if "error" in msg and msg["error"] is not None:
                    err = msg["error"]
                    err_msg = redact(str(err.get("message", err) if isinstance(err, dict) else err))
                    is_anom = isinstance(err, dict) and bool((err.get("data") or {}).get("anomaly"))
                    if is_anom:
                        raise ExtensionAnomalyError(err_msg)
                    raise ContractViolation("extension_call_failed", err_msg)
                return redact(msg.get("result"))

        try:
            return await asyncio.wait_for(_read(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            await self.stop()
            raise ExtensionAnomalyError(f"Extension call '{method}' timed out after {self.timeout_seconds}s") from exc
        except ExtensionAnomalyError:
            await self.stop()
            raise
        except ContractViolation:
            raise
        except (ValueError, UnicodeError) as exc:
            await self.stop()
            raise ExtensionAnomalyError(f"Invalid extension JSON-RPC payload: {exc}") from exc

    async def stop(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
        except OSError:
            pass
        if proc.returncode is None:
            await cancel_process_tree(proc.pid)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
