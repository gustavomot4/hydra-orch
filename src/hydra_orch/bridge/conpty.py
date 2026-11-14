"""Native Windows ConPTY (pseudo console) process wrapper via ``ctypes``.

Implements a real pseudo terminal on Windows 10 1809+ / Windows 11 using
``CreatePseudoConsole`` without third-party dependencies. The child process is
created suspended, assigned to a Job Object configured with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` (whole-tree kill without orphans) and
then resumed. Output is read from the pseudo console pipe as a VT byte stream;
input (including ``\\x03`` for Ctrl+C) is written to the input pipe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from typing import Mapping, Optional, Sequence

__all__ = ["ConPtyError", "ConPtyProcess", "conpty_available"]


class ConPtyError(OSError):
    """Raised when the native pseudo console cannot be created or driven."""


if os.name == "nt":  # pragma: no branch - platform specific module body
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    HPCON = wintypes.HANDLE

    class _COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class _STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class _STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    _CREATE_UNICODE_ENVIRONMENT = 0x00000400
    _CREATE_SUSPENDED = 0x00000004
    _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
    _STARTF_USESTDHANDLES = 0x00000100
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JobObjectExtendedLimitInformation = 9
    _INFINITE = 0xFFFFFFFF
    _WAIT_OBJECT_0 = 0
    _STILL_ACTIVE = 259
    _ERROR_BROKEN_PIPE = 109
    _ERROR_NO_DATA = 232

    def _bind(name: str, restype, argtypes):  # type: ignore[no-untyped-def]
        fn = getattr(_kernel32, name, None)
        if fn is None:
            return None
        fn.restype = restype
        fn.argtypes = argtypes
        return fn

    _CreatePipe = _bind(
        "CreatePipe",
        wintypes.BOOL,
        [ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p, wintypes.DWORD],
    )
    _CreatePseudoConsole = _bind(
        "CreatePseudoConsole",
        ctypes.c_long,
        [_COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(HPCON)],
    )
    _ResizePseudoConsole = _bind("ResizePseudoConsole", ctypes.c_long, [HPCON, _COORD])
    _ClosePseudoConsole = _bind("ClosePseudoConsole", None, [HPCON])
    _InitializeProcThreadAttributeList = _bind(
        "InitializeProcThreadAttributeList",
        wintypes.BOOL,
        [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)],
    )
    _UpdateProcThreadAttribute = _bind(
        "UpdateProcThreadAttribute",
        wintypes.BOOL,
        [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ],
    )
    _DeleteProcThreadAttributeList = _bind("DeleteProcThreadAttributeList", None, [ctypes.c_void_p])
    _CreateProcessW = _bind(
        "CreateProcessW",
        wintypes.BOOL,
        [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOEXW),
            ctypes.POINTER(_PROCESS_INFORMATION),
        ],
    )
    _ResumeThread = _bind("ResumeThread", wintypes.DWORD, [wintypes.HANDLE])
    _CloseHandle = _bind("CloseHandle", wintypes.BOOL, [wintypes.HANDLE])
    _ReadFile = _bind(
        "ReadFile",
        wintypes.BOOL,
        [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p],
    )
    _WriteFile = _bind(
        "WriteFile",
        wintypes.BOOL,
        [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p],
    )
    _WaitForSingleObject = _bind("WaitForSingleObject", wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD])
    _GetExitCodeProcess = _bind("GetExitCodeProcess", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)])
    _CreateJobObjectW = _bind("CreateJobObjectW", wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR])
    _SetInformationJobObject = _bind(
        "SetInformationJobObject", wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    )
    _AssignProcessToJobObject = _bind("AssignProcessToJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE])
    _TerminateJobObject = _bind("TerminateJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT])
    _TerminateProcess = _bind("TerminateProcess", wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT])

    def _last_error(message: str) -> ConPtyError:
        code = ctypes.get_last_error()
        return ConPtyError(code, f"{message} (WinError {code}: {ctypes.FormatError(code).strip()})")

    def _close(handle: Optional[int]) -> None:
        if handle:
            _CloseHandle(handle)

    def _environment_block(env: Mapping[str, str]) -> ctypes.Array:  # type: ignore[type-arg]
        items = sorted(((str(k), str(v)) for k, v in env.items()), key=lambda kv: kv[0].upper())
        block = "".join(f"{k}={v}\0" for k, v in items if k and "=" not in k) + "\0"
        return ctypes.create_unicode_buffer(block, len(block))

    def _coord(cols: int, rows: int) -> _COORD:
        return _COORD(max(1, min(int(cols), 32767)), max(1, min(int(rows), 32767)))


def conpty_available() -> bool:
    """Return True when the host exposes the native ConPTY API (Win10 1809+)."""
    if os.name != "nt":
        return False
    return _CreatePseudoConsole is not None and _ResizePseudoConsole is not None and _ClosePseudoConsole is not None


class ConPtyProcess:
    """A child process attached to a native Windows pseudo console."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        cols: int = 80,
        rows: int = 24,
    ) -> None:
        if not conpty_available():
            raise ConPtyError(0, "ConPTY API is not available on this host")
        self._lock = threading.Lock()
        self._hpc: Optional[int] = None
        self._in_write: Optional[int] = None
        self._out_read: Optional[int] = None
        self._h_process: Optional[int] = None
        self._h_job: Optional[int] = None
        self._returncode: Optional[int] = None
        self._pc_closed = False
        self.pid: int = 0
        self._spawn(list(command), cwd, env, cols, rows)

    # ------------------------------------------------------------------ spawn
    def _spawn(self, command: list, cwd: str, env: Mapping[str, str], cols: int, rows: int) -> None:
        in_read, in_write = wintypes.HANDLE(), wintypes.HANDLE()
        out_read, out_write = wintypes.HANDLE(), wintypes.HANDLE()
        if not _CreatePipe(ctypes.byref(in_read), ctypes.byref(in_write), None, 0):
            raise _last_error("CreatePipe(input) failed")
        if not _CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write), None, 0):
            _close(in_read.value)
            _close(in_write.value)
            raise _last_error("CreatePipe(output) failed")

        hpc = HPCON()
        hr = _CreatePseudoConsole(_coord(cols, rows), in_read, out_write, 0, ctypes.byref(hpc))
        # The pseudo console duplicates the pipe ends it needs.
        _close(in_read.value)
        _close(out_write.value)
        if hr != 0:
            _close(in_write.value)
            _close(out_read.value)
            raise ConPtyError(hr, f"CreatePseudoConsole failed (HRESULT 0x{hr & 0xFFFFFFFF:08X})")
        self._hpc = hpc.value
        self._in_write = in_write.value
        self._out_read = out_read.value

        attr_size = ctypes.c_size_t(0)
        _InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attr_size))
        attr_buf = (ctypes.c_byte * attr_size.value)()
        if not _InitializeProcThreadAttributeList(attr_buf, 1, 0, ctypes.byref(attr_size)):
            self._abort_spawn()
            raise _last_error("InitializeProcThreadAttributeList failed")
        try:
            hpc_value = HPCON(self._hpc)
            if not _UpdateProcThreadAttribute(
                attr_buf,
                0,
                _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                hpc_value,
                ctypes.sizeof(HPCON),
                None,
                None,
            ):
                raise _last_error("UpdateProcThreadAttribute(PSEUDOCONSOLE) failed")

            siex = _STARTUPINFOEXW()
            siex.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
            # Prevent inheriting the parent's std handles: the pseudo console owns stdio.
            siex.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
            siex.lpAttributeList = ctypes.cast(attr_buf, ctypes.c_void_p)
            pi = _PROCESS_INFORMATION()
            cmd_str = subprocess.list2cmdline(command)
            if command and command[0].lower().endswith((".cmd", ".bat")):
                comspec = env.get("ComSpec") or env.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
                comspec_q = f'"{comspec}"' if any(c.isspace() for c in comspec) else comspec
                # Preserve exact inner quotes for npm/CLI .cmd shims under cmd.exe /s /c.
                cmd_str = f'{comspec_q} /d /s /c "{cmd_str}"'
            cmdline = ctypes.create_unicode_buffer(cmd_str)
            env_block = _environment_block(env)
            flags = _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT | _CREATE_SUSPENDED
            if not _CreateProcessW(
                None,
                cmdline,
                None,
                None,
                False,
                flags,
                ctypes.cast(env_block, ctypes.c_void_p),
                cwd,
                ctypes.byref(siex),
                ctypes.byref(pi),
            ):
                raise _last_error("CreateProcessW failed")
        except BaseException:
            _DeleteProcThreadAttributeList(attr_buf)
            self._abort_spawn()
            raise
        _DeleteProcThreadAttributeList(attr_buf)

        self._h_process = pi.hProcess
        self.pid = int(pi.dwProcessId)
        self._h_job = self._create_kill_on_close_job(pi.hProcess)
        _ResumeThread(pi.hThread)
        _close(pi.hThread)

    @staticmethod
    def _create_kill_on_close_job(h_process: int) -> Optional[int]:
        job = _CreateJobObjectW(None, None)
        if not job:
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _SetInformationJobObject(
            job, _JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        ) and _AssignProcessToJobObject(job, h_process)
        if not ok:
            _close(job)
            return None
        return job

    def _abort_spawn(self) -> None:
        if self._hpc is not None:
            _ClosePseudoConsole(self._hpc)
            self._hpc = None
            self._pc_closed = True
        _close(self._in_write)
        _close(self._out_read)
        self._in_write = None
        self._out_read = None

    # --------------------------------------------------------------- runtime
    @property
    def job_assigned(self) -> bool:
        """Whether the child tree is bound to a kill-on-close Job Object."""
        return self._h_job is not None

    @property
    def returncode(self) -> Optional[int]:
        return self.poll()

    def poll(self) -> Optional[int]:
        if self._returncode is None and self._h_process:
            code = wintypes.DWORD()
            if _GetExitCodeProcess(self._h_process, ctypes.byref(code)) and code.value != _STILL_ACTIVE:
                self._returncode = int(code.value)
            elif _WaitForSingleObject(self._h_process, 0) == _WAIT_OBJECT_0:
                if _GetExitCodeProcess(self._h_process, ctypes.byref(code)):
                    self._returncode = int(code.value)
        return self._returncode

    def wait_blocking(self, timeout: Optional[float] = None) -> Optional[int]:
        """Block until the child exits (thread helper). Returns the exit code or None on timeout."""
        if self._h_process and self._returncode is None:
            ms = _INFINITE if timeout is None else max(0, int(timeout * 1000))
            if _WaitForSingleObject(self._h_process, ms) != _WAIT_OBJECT_0:
                return None
        return self.poll()

    def read_blocking(self, size: int = 4096) -> bytes:
        """Read VT output bytes; returns b'' at EOF (pseudo console closed)."""
        handle = self._out_read
        if not handle:
            return b""
        buf = ctypes.create_string_buffer(size)
        read = wintypes.DWORD(0)
        if not _ReadFile(handle, buf, size, ctypes.byref(read), None):
            err = ctypes.get_last_error()
            if err in (_ERROR_BROKEN_PIPE, _ERROR_NO_DATA) or self._out_read is None:
                return b""
            raise ConPtyError(err, f"ReadFile(pseudo console) failed (WinError {err})")
        return buf.raw[: read.value]

    def write_blocking(self, data: bytes) -> int:
        """Write input bytes to the pseudo console (\\x03 is delivered as Ctrl+C)."""
        with self._lock:
            handle = self._in_write
            if not handle:
                raise ConPtyError(_ERROR_BROKEN_PIPE, "pseudo console input is closed")
            total = 0
            view = memoryview(bytes(data))
            while total < len(view):
                chunk = bytes(view[total:])
                written = wintypes.DWORD(0)
                if not _WriteFile(handle, chunk, len(chunk), ctypes.byref(written), None):
                    raise _last_error("WriteFile(pseudo console) failed")
                total += int(written.value)
            return total

    def resize(self, cols: int, rows: int) -> None:
        with self._lock:
            if self._hpc is None or self._pc_closed:
                return
            hr = _ResizePseudoConsole(self._hpc, _coord(cols, rows))
        if hr != 0:
            raise ConPtyError(hr, f"ResizePseudoConsole failed (HRESULT 0x{hr & 0xFFFFFFFF:08X})")

    def kill_tree(self) -> None:
        """Terminate the whole process tree (Job Object), falling back to the root process."""
        if self._h_job:
            _TerminateJobObject(self._h_job, 1)
        if self._h_process and self.poll() is None:
            _TerminateProcess(self._h_process, 1)

    def close_console(self) -> None:
        """Close the pseudo console; the output pipe then reaches EOF.

        Must run while a reader keeps draining output: on older Windows builds
        ``ClosePseudoConsole`` blocks until pending output is consumed.
        """
        with self._lock:
            if self._pc_closed or self._hpc is None:
                return
            self._pc_closed = True
            hpc = self._hpc
            self._hpc = None
            in_write = self._in_write
            self._in_write = None
        _close(in_write)
        _ClosePseudoConsole(hpc)

    def close(self) -> None:
        """Release every native handle (idempotent). Kills the tree if still alive."""
        self.close_console()
        with self._lock:
            out_read, self._out_read = self._out_read, None
            h_job, self._h_job = self._h_job, None
        _close(out_read)
        self.poll()
        _close(h_job)  # KILL_ON_JOB_CLOSE reaps any surviving descendants.
        if self._h_process:
            self.poll()
            _close(self._h_process)
            self._h_process = None
