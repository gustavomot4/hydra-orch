"""Interactive PTY / bidirectional terminal session runner (M5 / T31)."""

from __future__ import annotations

import asyncio
import codecs
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
from typing import Any, AsyncIterator, Deque, Dict, List, Literal, Mapping, Optional, Sequence, Set, Tuple, Union

from pydantic import Field

import threading

from hydra_orch.bridge.conpty import ConPtyError, ConPtyProcess, conpty_available
from hydra_orch.bridge.worker_runner import cancel_process_tree, filter_worker_env, is_process_alive
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import ContractViolation, ExecutionModel, Identifier, NonEmpty, UtcTimestamp

try:
    import fcntl
    import pty
    import termios
    _HAS_POSIX_PTY = os.name != "nt"
except ImportError:  # pragma: no cover - Windows runtime path
    fcntl = None  # type: ignore[assignment]
    pty = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]
    _HAS_POSIX_PTY = False

logger = logging.getLogger(__name__)

PtySessionStatus = Literal["running", "exited", "cancelled", "crashed"]
PtyStreamName = Literal["pty", "stdout", "stderr", "system"]

_EOF_SENTINEL = object()
_DETACH_SENTINEL = object()


PTY_BACKEND_ENV = "HYDRA_PTY_BACKEND"
"""Optional override: set to ``pipe`` to force the uncertified pipe bridge on Windows."""


def _windows_conpty_enabled() -> bool:
    if os.name != "nt" or _HAS_POSIX_PTY:
        return False
    if os.environ.get(PTY_BACKEND_ENV, "").strip().lower() in {"pipe", "pipe_interactive_bridge"}:
        return False
    return conpty_available()


def detect_pty_backend() -> Tuple[str, bool]:
    """Return `(backend_kind, pty_certified)` for the active host OS."""
    if _HAS_POSIX_PTY:
        return ("posix_pty", True)
    if _windows_conpty_enabled():
        return ("windows_conpty", True)
    return ("pipe_interactive_bridge", False)


def _thread_future(loop: asyncio.AbstractEventLoop, fn: Any, *, name: str) -> "asyncio.Future[Any]":
    """Run a long blocking call on a dedicated daemon thread (keeps the shared executor free)."""
    future: asyncio.Future[Any] = loop.create_future()

    def _resolve(result: Any, error: Optional[BaseException]) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def _run() -> None:
        try:
            result, error = fn(), None
        except BaseException as exc:  # pragma: no cover - surfaced to awaiting coroutine
            result, error = None, exc
        with suppress(RuntimeError):  # event loop already closed
            loop.call_soon_threadsafe(_resolve, result, error)

    threading.Thread(target=_run, name=name, daemon=True).start()
    return future


class _ConPtyProcessHandle:
    """Minimal ``asyncio.subprocess.Process``-like facade over :class:`ConPtyProcess`."""

    stdin = None
    stdout = None
    stderr = None

    def __init__(self, conpty: ConPtyProcess) -> None:
        self._conpty = conpty
        self.pid = conpty.pid

    @property
    def returncode(self) -> Optional[int]:
        return self._conpty.poll()

    async def wait(self) -> int:
        code = self._conpty.poll()
        if code is None:
            loop = asyncio.get_running_loop()
            code = await _thread_future(loop, self._conpty.wait_blocking, name=f"conpty-wait-{self.pid}")
        return int(code if code is not None else -1)

    def terminate(self) -> None:
        self._conpty.kill_tree()

    def kill(self) -> None:
        self._conpty.kill_tree()


class PtyChunk(ExecutionModel):
    """Redacted output chunk emitted by an interactive terminal session."""

    seq: int = Field(ge=1, strict=True)
    session_id: Identifier
    stream: PtyStreamName = "stdout"
    text: str
    raw_bytes_len: int = Field(default=0, ge=0, strict=True)
    timestamp: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


class PtySessionInfo(ExecutionModel):
    """Immutable snapshot of an interactive terminal session state."""

    session_id: Identifier
    workspace_id: Optional[str] = None
    host_id: NonEmpty = "local"
    cwd: NonEmpty
    command: Tuple[str, ...]
    pid: Optional[int] = None
    cols: int = Field(default=80, ge=1, le=1000, strict=True)
    rows: int = Field(default=24, ge=1, le=1000, strict=True)
    status: PtySessionStatus = "running"
    detached: bool = False
    exit_code: Optional[int] = None
    backend_kind: NonEmpty
    pty_certified: bool
    last_seq: int = Field(default=0, ge=0, strict=True)
    oldest_seq: int = Field(default=0, ge=0, strict=True)
    created_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[UtcTimestamp] = None


@dataclass
class _PtySessionState:
    session_id: str
    workspace_id: Optional[str]
    host_id: str
    cwd: str
    command: Tuple[str, ...]
    process: Any  # asyncio.subprocess.Process or _ConPtyProcessHandle
    backend_kind: str
    pty_certified: bool
    cols: int
    rows: int
    created_at: datetime
    status: PtySessionStatus = "running"
    detached: bool = False
    exit_code: Optional[int] = None
    finished_at: Optional[datetime] = None
    master_fd: Optional[int] = None
    master_closed: bool = False
    last_seq: int = 0
    evicted_through_seq: int = 0
    scrollback: Deque[PtyChunk] = field(default_factory=deque)
    scrollback_bytes: int = 0
    subscribers: Set[asyncio.Queue[Any]] = field(default_factory=set)
    reader_tasks: List[asyncio.Task[Any]] = field(default_factory=list)
    wait_task: Optional[asyncio.Task[Any]] = None
    eof_reached: bool = False
    cancel_requested: bool = False
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    conpty: Optional[ConPtyProcess] = None

    def oldest_retained_seq(self) -> int:
        if self.scrollback:
            return self.scrollback[0].seq
        return self.last_seq if self.last_seq > 0 else 0

    def to_info(self) -> PtySessionInfo:
        return PtySessionInfo(
            session_id=self.session_id,
            workspace_id=self.workspace_id,
            host_id=self.host_id,
            cwd=self.cwd,
            command=self.command,
            pid=self.process.pid,
            cols=self.cols,
            rows=self.rows,
            status=self.status,
            detached=self.detached,
            exit_code=self.exit_code,
            backend_kind=self.backend_kind,
            pty_certified=self.pty_certified,
            last_seq=self.last_seq,
            oldest_seq=self.oldest_retained_seq(),
            created_at=self.created_at,
            finished_at=self.finished_at,
        )


def _validate_cwd(cwd: Union[Path, str]) -> str:
    raw = str(cwd) if cwd is not None else ""
    if not raw.strip() or "\x00" in raw:
        raise ContractViolation("invalid_workspace_cwd", "Terminal cwd cannot be empty or contain NUL bytes")
    resolved = Path(os.path.realpath(raw))
    if not resolved.exists() or not resolved.is_dir():
        raise ContractViolation("invalid_workspace_cwd", f"Terminal cwd does not exist or is not a directory: {resolved}")
    return str(resolved)


def _validate_command(command: Sequence[str]) -> Tuple[str, ...]:
    if isinstance(command, (str, bytes)) or not command:
        raise ContractViolation("invalid_pty_command", "Terminal command must be a non-empty sequence of arguments")
    parts = tuple(str(arg) for arg in command)
    if not parts[0].strip() or any("\x00" in part for part in parts):
        raise ContractViolation("invalid_pty_command", "Terminal executable and arguments cannot be empty or contain NUL bytes")
    return parts


def _validate_dimensions(cols: int, rows: int) -> Tuple[int, int]:
    if type(cols) is not int or type(rows) is not int or cols < 1 or cols > 1000 or rows < 1 or rows > 1000:
        raise ContractViolation("invalid_pty_dimensions", "Terminal dimensions cols/rows must be integers between 1 and 1000")
    return cols, rows


class PtyRunner:
    """Manages interactive child terminal sessions with sanitized env, scrollback replay, and tree kill."""

    def __init__(
        self,
        *,
        max_scrollback_chunks: int = 2000,
        max_scrollback_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if max_scrollback_chunks < 1 or max_scrollback_bytes < 1024:
            raise ContractViolation("invalid_pty_config", "Scrollback limits must be positive")
        self.max_scrollback_chunks = max_scrollback_chunks
        self.max_scrollback_bytes = max_scrollback_bytes
        self._sessions: Dict[str, _PtySessionState] = {}

    @property
    def backend_kind(self) -> str:
        """Return the host default PTY/interactive terminal backend identifier."""
        return detect_pty_backend()[0]

    @property
    def pty_certified(self) -> bool:
        """Return whether the active host OS backend is a certified native PTY."""
        return detect_pty_backend()[1]

    @property
    def backend_info(self) -> Tuple[str, bool]:
        """Return the host default `(backend_kind, pty_certified)` capability tuple."""
        return detect_pty_backend()

    async def open_session(
        self,
        command: Sequence[str],
        *,
        cwd: Union[Path, str],
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        host_id: str = "local",
        cols: int = 80,
        rows: int = 24,
        allowed_env: Optional[Mapping[str, str]] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> PtySessionInfo:
        """Spawn a new interactive terminal session bound to `cwd` with filtered env."""
        resolved_cwd = _validate_cwd(cwd)
        cmd_parts = _validate_command(command)
        cols_val, rows_val = _validate_dimensions(cols, rows)

        sid = session_id or new_id()
        if not isinstance(sid, str) or not sid.strip() or "\x00" in sid:
            raise ContractViolation("invalid_session_id", "session_id must be a valid non-empty identifier")
        if sid in self._sessions and self._sessions[sid].status == "running":
            raise ContractViolation("pty_session_conflict", f"PTY session '{sid}' is already running")

        extra_env: Dict[str, str] = {}
        if env:
            extra_env.update({str(k): str(v) for k, v in env.items()})
        if allowed_env:
            extra_env.update({str(k): str(v) for k, v in allowed_env.items()})
        child_env = filter_worker_env(allowed_env=extra_env or None)
        child_env.setdefault("TERM", "xterm-256color")
        child_env.setdefault("PYTHONIOENCODING", "utf-8")
        child_env.setdefault("PYTHONUTF8", "1")
        child_env["COLUMNS"] = str(cols_val)
        child_env["LINES"] = str(rows_val)

        if _HAS_POSIX_PTY:
            state = await self._spawn_posix_pty(
                sid=sid,
                command=cmd_parts,
                cwd=resolved_cwd,
                env=child_env,
                workspace_id=workspace_id,
                host_id=host_id,
                cols=cols_val,
                rows=rows_val,
            )
        elif _windows_conpty_enabled():
            state = await self._spawn_windows_conpty(
                sid=sid,
                command=cmd_parts,
                cwd=resolved_cwd,
                env=child_env,
                workspace_id=workspace_id,
                host_id=host_id,
                cols=cols_val,
                rows=rows_val,
            )
        else:
            state = await self._spawn_pipe_bridge(
                sid=sid,
                command=cmd_parts,
                cwd=resolved_cwd,
                env=child_env,
                workspace_id=workspace_id,
                host_id=host_id,
                cols=cols_val,
                rows=rows_val,
            )

        self._sessions[sid] = state
        return state.to_info()

    async def _spawn_posix_pty(
        self,
        *,
        sid: str,
        command: Tuple[str, ...],
        cwd: str,
        env: Dict[str, str],
        workspace_id: Optional[str],
        host_id: str,
        cols: int,
        rows: int,
    ) -> _PtySessionState:
        assert pty is not None and termios is not None and fcntl is not None
        try:
            master_fd, slave_fd = pty.openpty()
        except OSError as exc:
            logger.warning("POSIX pty.openpty() unavailable (%s); falling back to pipe_interactive_bridge", exc)
            return await self._spawn_pipe_bridge(
                sid=sid,
                command=command,
                cwd=cwd,
                env=env,
                workspace_id=workspace_id,
                host_id=host_id,
                cols=cols,
                rows=rows,
            )

        def _child_setup() -> None:
            with suppress(OSError):
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

        try:
            with suppress(OSError):
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
                preexec_fn=_child_setup,
            )
        except Exception as exc:
            with suppress(OSError):
                os.close(master_fd)
            raise ContractViolation("pty_spawn_failed", f"Failed to spawn PTY process: {redact_text(str(exc))}") from exc
        finally:
            with suppress(OSError):
                os.close(slave_fd)

        state = _PtySessionState(
            session_id=sid,
            workspace_id=workspace_id,
            host_id=host_id,
            cwd=cwd,
            command=command,
            process=process,
            backend_kind="posix_pty",
            pty_certified=True,
            cols=cols,
            rows=rows,
            created_at=datetime.now(timezone.utc),
            master_fd=master_fd,
        )
        reader_task = asyncio.create_task(self._pump_posix_pty(state), name=f"pty-reader-{sid}")
        state.reader_tasks.append(reader_task)
        state.wait_task = asyncio.create_task(self._finalize_when_done(state), name=f"pty-wait-{sid}")
        return state

    async def _spawn_windows_conpty(
        self,
        *,
        sid: str,
        command: Tuple[str, ...],
        cwd: str,
        env: Dict[str, str],
        workspace_id: Optional[str],
        host_id: str,
        cols: int,
        rows: int,
    ) -> _PtySessionState:
        exec_command = list(command)
        # CreateProcessW skips PATHEXT (.cmd/.bat npm shims) unless resolved explicitly.
        resolved = shutil.which(exec_command[0], path=env.get("PATH"))
        if resolved:
            exec_command[0] = resolved
        try:
            conpty = ConPtyProcess(exec_command, cwd=cwd, env=env, cols=cols, rows=rows)
        except ConPtyError as exc:
            logger.warning("Windows ConPTY spawn failed (%s); falling back to pipe_interactive_bridge", exc)
            if exc.errno == 2 or "WinError 2:" in str(exc):
                raise ContractViolation(
                    "pty_spawn_failed", f"Failed to spawn terminal process: {redact_text(str(exc))}"
                ) from exc
            return await self._spawn_pipe_bridge(
                sid=sid,
                command=command,
                cwd=cwd,
                env=env,
                workspace_id=workspace_id,
                host_id=host_id,
                cols=cols,
                rows=rows,
            )

        state = _PtySessionState(
            session_id=sid,
            workspace_id=workspace_id,
            host_id=host_id,
            cwd=cwd,
            command=command,
            process=_ConPtyProcessHandle(conpty),
            backend_kind="windows_conpty",
            pty_certified=True,
            cols=cols,
            rows=rows,
            created_at=datetime.now(timezone.utc),
            conpty=conpty,
        )
        state.reader_tasks.append(
            asyncio.create_task(self._pump_windows_conpty(state), name=f"pty-conpty-reader-{sid}")
        )
        state.reader_tasks.append(
            asyncio.create_task(self._close_conpty_on_exit(state), name=f"pty-conpty-exit-{sid}")
        )
        state.wait_task = asyncio.create_task(self._finalize_when_done(state), name=f"pty-wait-{sid}")
        return state

    async def _pump_windows_conpty(self, state: _PtySessionState) -> None:
        assert state.conpty is not None
        conpty = state.conpty
        loop = asyncio.get_running_loop()
        raw_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

        def _push(item: Optional[bytes]) -> None:
            raw_queue.put_nowait(item)

        def _reader_thread() -> None:
            try:
                while True:
                    try:
                        data = conpty.read_blocking(4096)
                    except OSError:
                        data = b""
                    if not data:
                        break
                    with suppress(RuntimeError):
                        loop.call_soon_threadsafe(_push, data)
            finally:
                with suppress(RuntimeError):
                    loop.call_soon_threadsafe(_push, None)

        threading.Thread(target=_reader_thread, name=f"conpty-read-{state.session_id}", daemon=True).start()
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            data = await raw_queue.get()
            if data is None:
                tail = decoder.decode(b"", final=True)
                if tail:
                    self._append_chunk(state, "pty", tail, 0)
                break
            text = decoder.decode(data, final=False)
            if text:
                self._append_chunk(state, "pty", text, len(data))

    async def _close_conpty_on_exit(self, state: _PtySessionState) -> None:
        """ConPTY keeps the output pipe open after the child exits; close it so readers reach EOF."""
        assert state.conpty is not None
        conpty = state.conpty
        loop = asyncio.get_running_loop()
        await _thread_future(loop, conpty.wait_blocking, name=f"conpty-exit-{state.session_id}")
        await _thread_future(loop, conpty.close_console, name=f"conpty-close-{state.session_id}")

    async def _spawn_pipe_bridge(
        self,
        *,
        sid: str,
        command: Tuple[str, ...],
        cwd: str,
        env: Dict[str, str],
        workspace_id: Optional[str],
        host_id: str,
        cols: int,
        rows: int,
    ) -> _PtySessionState:
        spawn_kwargs: Dict[str, Any] = {
            "cwd": cwd,
            "env": env,
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if os.name == "nt":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            spawn_kwargs["start_new_session"] = True

        exec_command = list(command)
        if os.name == "nt" and exec_command:
            # Windows CreateProcessW skips PATHEXT (.cmd/.bat, e.g. npm shims) unless resolved explicitly.
            resolved = shutil.which(exec_command[0], path=env.get("PATH"))
            if resolved:
                exec_command[0] = resolved

        try:
            process = await asyncio.create_subprocess_exec(*exec_command, **spawn_kwargs)
        except Exception as exc:
            raise ContractViolation("pty_spawn_failed", f"Failed to spawn terminal process: {redact_text(str(exc))}") from exc

        state = _PtySessionState(
            session_id=sid,
            workspace_id=workspace_id,
            host_id=host_id,
            cwd=cwd,
            command=command,
            process=process,
            backend_kind="pipe_interactive_bridge",
            pty_certified=False,
            cols=cols,
            rows=rows,
            created_at=datetime.now(timezone.utc),
        )
        if process.stdout is not None:
            state.reader_tasks.append(
                asyncio.create_task(self._pump_pipe(state, process.stdout, "stdout"), name=f"pty-stdout-{sid}")
            )
        if process.stderr is not None:
            state.reader_tasks.append(
                asyncio.create_task(self._pump_pipe(state, process.stderr, "stderr"), name=f"pty-stderr-{sid}")
            )
        state.wait_task = asyncio.create_task(self._finalize_when_done(state), name=f"pty-wait-{sid}")
        return state

    def _close_master_fd(self, state: _PtySessionState) -> None:
        if state.master_fd is not None and not state.master_closed:
            state.master_closed = True
            with suppress(Exception):
                asyncio.get_running_loop().remove_reader(state.master_fd)
            with suppress(OSError):
                os.close(state.master_fd)

    async def _pump_posix_pty(self, state: _PtySessionState) -> None:
        assert state.master_fd is not None
        fd = state.master_fd
        loop = asyncio.get_running_loop()
        raw_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        os.set_blocking(fd, False)

        def _on_readable() -> None:
            if state.master_closed:
                with suppress(Exception):
                    loop.remove_reader(fd)
                raw_queue.put_nowait(None)
                return
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                return
            except OSError:
                data = b""
            if not data:
                with suppress(Exception):
                    loop.remove_reader(fd)
                raw_queue.put_nowait(None)
            else:
                raw_queue.put_nowait(data)

        loop.add_reader(fd, _on_readable)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                data = await raw_queue.get()
                if data is None:
                    tail = decoder.decode(b"", final=True)
                    if tail:
                        self._append_chunk(state, "pty", tail, 0)
                    break
                text = decoder.decode(data, final=False)
                if text or data:
                    self._append_chunk(state, "pty", text, len(data))
        except asyncio.CancelledError:
            raise
        finally:
            with suppress(Exception):
                loop.remove_reader(fd)
            self._close_master_fd(state)

    async def _pump_pipe(
        self,
        state: _PtySessionState,
        stream: asyncio.StreamReader,
        stream_name: PtyStreamName,
    ) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                data = await stream.read(4096)
                if not data:
                    tail = decoder.decode(b"", final=True)
                    if tail:
                        self._append_chunk(state, stream_name, tail, 0)
                    break
                text = decoder.decode(data, final=False)
                if text:
                    self._append_chunk(state, stream_name, text, len(data))
        except asyncio.CancelledError:
            raise

    def _append_chunk(
        self,
        state: _PtySessionState,
        stream_name: PtyStreamName,
        text: str,
        raw_bytes_len: int,
    ) -> None:
        sanitized = redact_text(text)
        state.last_seq += 1
        chunk = PtyChunk(
            seq=state.last_seq,
            session_id=state.session_id,
            stream=stream_name,
            text=sanitized,
            raw_bytes_len=raw_bytes_len,
        )
        chunk_bytes = len(sanitized.encode("utf-8"))
        state.scrollback.append(chunk)
        state.scrollback_bytes += chunk_bytes

        while state.scrollback and (
            len(state.scrollback) > self.max_scrollback_chunks
            or (state.scrollback_bytes > self.max_scrollback_bytes and len(state.scrollback) > 1)
        ):
            evicted = state.scrollback.popleft()
            state.scrollback_bytes -= len(evicted.text.encode("utf-8"))
            state.evicted_through_seq = max(state.evicted_through_seq, evicted.seq)

        for queue in list(state.subscribers):
            queue.put_nowait(chunk)

    async def _finalize_when_done(self, state: _PtySessionState) -> None:
        try:
            if state.reader_tasks:
                await asyncio.gather(*state.reader_tasks, return_exceptions=True)
            exit_code = await state.process.wait()
            state.exit_code = int(exit_code)
            if state.cancel_requested:
                state.status = "cancelled"
            else:
                state.status = "exited"
            state.finished_at = datetime.now(timezone.utc)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive state finalization
            state.status = "crashed"
            state.finished_at = datetime.now(timezone.utc)
        finally:
            self._close_master_fd(state)
            if state.conpty is not None:
                with suppress(Exception):
                    state.conpty.close()
            state.eof_reached = True
            for queue in list(state.subscribers):
                queue.put_nowait(_EOF_SENTINEL)

    def _require_session(self, session_id: str) -> _PtySessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise ContractViolation("resource_not_found", f"PTY session '{session_id}' does not exist")
        return state

    def get_session(self, session_id: str) -> PtySessionInfo:
        """Return the current state snapshot of a PTY session."""
        return self._require_session(session_id).to_info()

    def list_sessions(self) -> List[PtySessionInfo]:
        """List all tracked PTY sessions."""
        return [state.to_info() for state in self._sessions.values()]

    async def write_input(self, session_id: str, data: Union[str, bytes]) -> int:
        """Write interactive UTF-8 text or raw bytes to the session stdin/PTY."""
        state = self._require_session(session_id)
        if state.status != "running":
            raise ContractViolation("pty_session_closed", f"PTY session '{session_id}' is not running ({state.status})")

        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if not payload:
            return 0

        async with state.write_lock:
            if state.conpty is not None:
                # Console line discipline submits on CR (Enter); normalize LF/CRLF from API clients.
                normalized = payload.replace(b"\r\n", b"\r").replace(b"\n", b"\r")
                try:
                    await asyncio.to_thread(state.conpty.write_blocking, normalized)
                except OSError as exc:
                    raise ContractViolation("pty_write_failed", f"Failed writing to ConPTY input: {exc}") from exc
                return len(payload)

            if state.master_fd is not None and not state.master_closed:
                try:
                    written = await asyncio.to_thread(os.write, state.master_fd, payload)
                    return int(written)
                except OSError as exc:
                    raise ContractViolation("pty_write_failed", f"Failed writing to PTY master: {exc}") from exc

            stdin = state.process.stdin
            if stdin is None or stdin.is_closing():
                raise ContractViolation("pty_session_closed", f"PTY session '{session_id}' stdin is closed")
            try:
                stdin.write(payload)
                await stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                raise ContractViolation("pty_write_failed", f"Failed writing to terminal stdin: {exc}") from exc
            return len(payload)

    async def resize(self, session_id: str, *, cols: int, rows: int) -> PtySessionInfo:
        """Update terminal dimensions and emit TIOCSWINSZ on real POSIX PTYs."""
        cols_val, rows_val = _validate_dimensions(cols, rows)
        state = self._require_session(session_id)
        if state.status != "running":
            raise ContractViolation("pty_session_closed", f"Cannot resize non-running PTY session '{session_id}'")

        state.cols = cols_val
        state.rows = rows_val
        if state.conpty is not None:
            with suppress(OSError):
                state.conpty.resize(cols_val, rows_val)
        if (
            state.backend_kind == "posix_pty"
            and state.master_fd is not None
            and not state.master_closed
            and fcntl is not None
            and termios is not None
        ):
            winsize = struct.pack("HHHH", rows_val, cols_val, 0, 0)
            with suppress(OSError):
                fcntl.ioctl(state.master_fd, termios.TIOCSWINSZ, winsize)
        return state.to_info()

    async def interrupt(self, session_id: str) -> PtySessionInfo:
        """Send an interactive interrupt signal (\\x03 / SIGINT / Ctrl+Break) to the session."""
        state = self._require_session(session_id)
        if state.status != "running" or state.process.returncode is not None:
            return state.to_info()

        pid = state.process.pid
        if state.conpty is not None:
            # ConPTY translates ETX into a CTRL_C_EVENT for every process attached to the pseudo console.
            with suppress(OSError):
                await asyncio.to_thread(state.conpty.write_blocking, b"\x03")
        elif state.backend_kind == "posix_pty" and state.master_fd is not None and not state.master_closed:
            try:
                await asyncio.to_thread(os.write, state.master_fd, b"\x03")
            except OSError:
                pass
            if pid and is_process_alive(pid):
                with suppress(ProcessLookupError, OSError):
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGINT)
        elif os.name == "nt":
            if state.process.stdin is not None and not state.process.stdin.is_closing():
                with suppress(OSError, BrokenPipeError, asyncio.TimeoutError):
                    state.process.stdin.write(b"\x03")
                    await asyncio.wait_for(state.process.stdin.drain(), timeout=0.2)
            if pid and is_process_alive(pid):
                try:
                    os.kill(pid, signal.CTRL_BREAK_EVENT)
                except OSError:
                    with suppress(OSError):
                        state.process.terminate()
        else:
            if state.process.stdin is not None and not state.process.stdin.is_closing():
                with suppress(OSError, BrokenPipeError, asyncio.TimeoutError):
                    state.process.stdin.write(b"\x03")
                    await asyncio.wait_for(state.process.stdin.drain(), timeout=0.2)
            if pid and is_process_alive(pid):
                with suppress(ProcessLookupError, OSError):
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGINT)

        return state.to_info()

    def read_output(self, session_id: str, *, after_seq: int = 0) -> List[PtyChunk]:
        """Return buffered chunks strictly after `after_seq` for reconnect replay."""
        if after_seq < 0:
            raise ContractViolation("invalid_cursor", "after_seq must be >= 0")
        state = self._require_session(session_id)
        if after_seq > 0 and state.evicted_through_seq > 0 and after_seq < state.evicted_through_seq:
            raise ContractViolation(
                "cursor_expired",
                f"PTY scrollback cursor {after_seq} expired (oldest retained > {state.evicted_through_seq})",
            )
        return [chunk for chunk in state.scrollback if chunk.seq > after_seq]

    async def stream(self, session_id: str, *, after_seq: int = 0) -> AsyncIterator[PtyChunk]:
        """Subscribe to live and buffered PTY chunks starting strictly after `after_seq`."""
        if after_seq < 0:
            raise ContractViolation("invalid_cursor", "after_seq must be >= 0")
        state = self._require_session(session_id)
        if after_seq > 0 and state.evicted_through_seq > 0 and after_seq < state.evicted_through_seq:
            raise ContractViolation(
                "cursor_expired",
                f"PTY scrollback cursor {after_seq} expired (oldest retained > {state.evicted_through_seq})",
            )

        if state.status == "running" and state.detached:
            state.detached = False

        queue: asyncio.Queue[Any] = asyncio.Queue()
        state.subscribers.add(queue)
        cursor = after_seq
        try:
            for chunk in list(state.scrollback):
                if chunk.seq > cursor:
                    cursor = chunk.seq
                    yield chunk

            if state.eof_reached:
                return

            while True:
                item = await queue.get()
                if item is _EOF_SENTINEL or item is _DETACH_SENTINEL:
                    break
                if isinstance(item, PtyChunk) and item.seq > cursor:
                    cursor = item.seq
                    yield item
        finally:
            state.subscribers.discard(queue)

    async def wait(self, session_id: str, *, timeout: Optional[float] = None) -> PtySessionInfo:
        """Await session termination and reader task drain."""
        state = self._require_session(session_id)
        if state.wait_task is not None and not state.wait_task.done():
            if timeout is not None:
                await asyncio.wait_for(asyncio.shield(state.wait_task), timeout=timeout)
            else:
                await asyncio.shield(state.wait_task)
        return state.to_info()

    async def close_session(self, session_id: str, *, keep_running: bool = False) -> PtySessionInfo:
        """Detach UI stream consumers (`keep_running=True`) or kill the full process tree."""
        state = self._require_session(session_id)
        if keep_running:
            if state.status == "running":
                state.detached = True
            for queue in list(state.subscribers):
                queue.put_nowait(_DETACH_SENTINEL)
            return state.to_info()

        state.detached = False
        if state.status == "running" or (state.process.pid and is_process_alive(state.process.pid)):
            state.cancel_requested = True
            if state.process.stdin is not None and not state.process.stdin.is_closing():
                with suppress(Exception):
                    state.process.stdin.close()
            if state.process.pid:
                await cancel_process_tree(state.process.pid)
            if state.conpty is not None:
                with suppress(Exception):
                    state.conpty.kill_tree()
            self._close_master_fd(state)

            if state.wait_task is not None and not state.wait_task.done():
                try:
                    await asyncio.wait_for(state.wait_task, timeout=2.0)
                except asyncio.TimeoutError:
                    for task in state.reader_tasks:
                        task.cancel()
                    await asyncio.gather(*state.reader_tasks, return_exceptions=True)
                    state.wait_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await state.wait_task
                    with suppress(Exception):
                        await asyncio.wait_for(state.process.wait(), timeout=1.0)
                    state.exit_code = state.process.returncode
                    state.status = "cancelled"
                    state.finished_at = datetime.now(timezone.utc)
            else:
                state.status = "cancelled"
                state.finished_at = state.finished_at or datetime.now(timezone.utc)
        else:
            self._close_master_fd(state)
            if state.wait_task is not None and not state.wait_task.done():
                with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait_for(state.wait_task, timeout=1.0)

        state.eof_reached = True
        for queue in list(state.subscribers):
            queue.put_nowait(_EOF_SENTINEL)
        return state.to_info()

    async def close_all(self) -> None:
        """Terminate all tracked PTY sessions and clean up reader tasks on shutdown."""
        for session_id in list(self._sessions.keys()):
            with suppress(Exception):
                await self.close_session(session_id, keep_running=False)


__all__ = [
    "PtyChunk",
    "PtyRunner",
    "PtySessionInfo",
    "PtySessionStatus",
    "PtyStreamName",
    "detect_pty_backend",
]
