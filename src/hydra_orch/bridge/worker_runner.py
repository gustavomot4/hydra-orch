"""Worker runner for autonomous SWE CLI tools (Codex, Claude Code, OpenCode, Aider, Agy, Gemini CLI)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import uuid

from hydra_orch.model import (
    Artifact,
    ContractViolation,
    ExecutorCapabilities,
    ExecutorCapability,
    FailureDetail,
    ProcessStatus,
    TaskAttempt,
)

logger = logging.getLogger(__name__)

_SAFE_ENV_EXACT = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "SYSTEMDRIVE",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERNAME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "COLORTERM",
        "PYTHONPATH",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "OS",
    }
)

_SENSITIVE_ENV_SUBSTRINGS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "API_KEY",
    "APIKEY",
    "ACCESS_KEY",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "SESSION_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "CONNECTION_STRING",
    "BEARER",
    "WEBHOOK",
)

_DRIVER_EXECUTABLES: Dict[str, str] = {
    "codex": "codex",
    "claude": "claude",
    "claude_code": "claude",
    "opencode": "opencode",
    "agy": "agy",
    "gemini": "gemini",
    "gemini_cli": "gemini",
    "aider": "aider",
}

_DRIVER_CAPABILITIES: Dict[str, Tuple[ExecutorCapability, ...]] = {
    "codex": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.NATIVE_RESUME,
        ExecutorCapability.CANCEL_PROCESS_TREE,
        ExecutorCapability.FILESYSTEM_SANDBOX,
    ),
    "claude": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.NATIVE_RESUME,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "claude_code": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.NATIVE_RESUME,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "opencode": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "agy": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "gemini": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "gemini_cli": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "aider": (
        ExecutorCapability.INFERENCE,
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "python_fake": (
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
    "custom": (
        ExecutorCapability.WORKSPACE_EXECUTION,
        ExecutorCapability.TOOL_EXECUTION,
        ExecutorCapability.CANCEL_PROCESS_TREE,
    ),
}


@dataclass(frozen=True)
class InvocationPlan:
    """Immutable subprocess invocation plan built for a specific CLI driver."""

    driver: str
    executable: str
    argv: Tuple[str, ...]
    stdin_bytes: Optional[bytes] = None
    capabilities: ExecutorCapabilities = field(
        default_factory=lambda: ExecutorCapabilities(
            executor_id="custom",
            capabilities=(
                ExecutorCapability.WORKSPACE_EXECUTION,
                ExecutorCapability.CANCEL_PROCESS_TREE,
            ),
        )
    )


@dataclass
class _ActiveProcessEntry:
    attempt_id: str
    process: asyncio.subprocess.Process
    cancelled_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_reason: str = "cancelled_by_operator"
    tree_killed: bool = False


def filter_worker_env(
    base_env: Optional[Mapping[str, str]] = None,
    allowed_env: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Build a sanitized environment dictionary for worker subprocesses.

    Preserves only safe OS/runtime variables from `base_env`, strips any variable
    matching sensitive secret/token patterns, and overlays explicitly authorized
    variables from `allowed_env`.
    """
    source = os.environ if base_env is None else base_env
    filtered: Dict[str, str] = {}

    for key, value in source.items():
        if "\x00" in key or "\x00" in str(value):
            continue
        upper_key = key.upper()
        if any(token in upper_key for token in _SENSITIVE_ENV_SUBSTRINGS):
            continue
        if upper_key in _SAFE_ENV_EXACT or upper_key.startswith(("LC_", "XDG_")):
            filtered[key] = str(value)

    filtered["HYDRA_WORKER_ISOLATED"] = "1"
    filtered["GIT_TERMINAL_PROMPT"] = "0"
    filtered["PYTHONUNBUFFERED"] = "1"

    if allowed_env:
        for key, value in allowed_env.items():
            if not key or "\x00" in key or "\x00" in str(value):
                raise ContractViolation("invalid_env_var", f"Invalid environment variable '{key}'")
            filtered[key] = str(value)

    return filtered


def build_invocation(
    driver: str,
    prompt: str,
    *,
    extra_args: Sequence[str] = (),
    resume_session: Optional[str] = None,
    custom_command: Optional[Sequence[str]] = None,
) -> InvocationPlan:
    """Construct a deterministic shell-free argv + stdin plan for a CLI agent driver."""
    norm_driver = (driver or "").strip().lower()
    if not norm_driver or "\x00" in norm_driver:
        raise ContractViolation("invalid_driver_invocation", "Driver name must be a non-empty string without NUL")
    if "\x00" in prompt:
        raise ContractViolation("invalid_driver_invocation", "Prompt cannot contain NUL bytes")
    if any("\x00" in str(arg) for arg in extra_args):
        raise ContractViolation("invalid_driver_invocation", "Extra arguments cannot contain NUL bytes")

    caps = ExecutorCapabilities(
        executor_id=norm_driver if norm_driver.isidentifier() else "custom",
        capabilities=_DRIVER_CAPABILITIES.get(
            norm_driver,
            (
                ExecutorCapability.WORKSPACE_EXECUTION,
                ExecutorCapability.TOOL_EXECUTION,
                ExecutorCapability.CANCEL_PROCESS_TREE,
            ),
        ),
    )

    if custom_command is not None:
        cmd_tuple = tuple(str(part) for part in custom_command)
        if not cmd_tuple or not cmd_tuple[0].strip() or any("\x00" in part for part in cmd_tuple):
            raise ContractViolation("invalid_driver_invocation", "Custom command requires non-empty executable without NUL")
        return InvocationPlan(
            driver=norm_driver,
            executable=cmd_tuple[0],
            argv=cmd_tuple + tuple(str(a) for a in extra_args),
            stdin_bytes=prompt.encode("utf-8") if prompt else None,
            capabilities=caps,
        )

    executable = _DRIVER_EXECUTABLES.get(norm_driver, norm_driver)
    extra = tuple(str(a) for a in extra_args)

    if norm_driver == "codex":
        if resume_session:
            argv = (executable, "exec", "resume", resume_session, "--sandbox", "workspace-write", "-") + extra
        else:
            argv = (executable, "exec", "--sandbox", "workspace-write", "-") + extra
        return InvocationPlan(
            driver=norm_driver,
            executable=executable,
            argv=argv,
            stdin_bytes=prompt.encode("utf-8"),
            capabilities=caps,
        )

    if norm_driver in {"claude", "claude_code"}:
        base: List[str] = [executable, "--print", "--output-format", "text"]
        if resume_session:
            base.extend(["--resume", resume_session])
        argv = tuple(base) + extra
        return InvocationPlan(
            driver=norm_driver,
            executable=executable,
            argv=argv,
            stdin_bytes=prompt.encode("utf-8"),
            capabilities=caps,
        )

    if norm_driver == "opencode":
        argv = (executable, "run", prompt) + extra
        return InvocationPlan(driver=norm_driver, executable=executable, argv=argv, stdin_bytes=None, capabilities=caps)

    if norm_driver == "agy":
        argv = (executable, "chat", "--prompt", prompt) + extra
        return InvocationPlan(driver=norm_driver, executable=executable, argv=argv, stdin_bytes=None, capabilities=caps)

    if norm_driver in {"gemini", "gemini_cli"}:
        argv = (executable, "--prompt", prompt) + extra
        return InvocationPlan(driver=norm_driver, executable=executable, argv=argv, stdin_bytes=None, capabilities=caps)

    if norm_driver == "aider":
        argv = (executable, "--yes-always", "--no-auto-commits", "--message", prompt) + extra
        return InvocationPlan(driver=norm_driver, executable=executable, argv=argv, stdin_bytes=None, capabilities=caps)

    argv = (executable, "--message", prompt) + extra
    return InvocationPlan(driver=norm_driver, executable=executable, argv=argv, stdin_bytes=None, capabilities=caps)


def is_process_alive(pid: int) -> bool:
    """Check whether an OS process with the given PID is currently active (not terminated/zombie)."""
    if pid <= 0:
        return False

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            err = kernel32.GetLastError()
            return err == ERROR_ACCESS_DENIED
        try:
            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return int(exit_code.value) == STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            stat_text = proc_stat.read_text(encoding="utf-8", errors="ignore")
            rparen = stat_text.rfind(")")
            if rparen != -1 and len(stat_text) > rparen + 2:
                state_char = stat_text[rparen + 2]
                if state_char == "Z":
                    return False
        except OSError:
            pass
    return True


async def cancel_process_tree(
    pid: int,
    *,
    grace_seconds: float = 0.2,
    verify_timeout: float = 3.0,
) -> bool:
    """Terminate a process and all of its descendants across Windows and POSIX, verifying death."""
    if pid <= 0 or not is_process_alive(pid):
        return True

    if os.name == "nt":
        try:
            kill_proc = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(kill_proc.communicate(), timeout=max(verify_timeout, 2.0))
        except Exception:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        if is_process_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

        deadline_grace = time.monotonic() + max(grace_seconds, 0.05)
        while time.monotonic() < deadline_grace:
            if not is_process_alive(pid):
                return True
            await asyncio.sleep(0.02)

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    deadline = time.monotonic() + max(verify_timeout, 0.5)
    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            return True
        await asyncio.sleep(0.025)

    return not is_process_alive(pid)


def _write_artifact_atomic(
    target_path: Path,
    content: bytes,
    *,
    artifact_id: str,
    run_id: str,
    attempt_id: Optional[str],
    relative_path: str,
    kind: str = "check_output",
) -> Artifact:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp_path, "wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target_path)
    digest = hashlib.sha256(content).hexdigest()
    return Artifact(
        artifact_id=artifact_id,
        run_id=run_id,
        attempt_id=attempt_id,
        relative_path=relative_path,
        kind=kind,  # type: ignore[arg-type]
        sha256=digest,
        size_bytes=len(content),
    )


class WorkerRunner:
    """Dispatches and monitors coding worker CLI agents inside target Git Worktrees."""

    def __init__(self, default_cli: str = "opencode"):
        self.default_cli = default_cli
        self._active_attempts: Dict[str, _ActiveProcessEntry] = {}
        self._terminated_attempts: Dict[str, Dict[str, Any]] = {}

    def capabilities(self, cli_name: Optional[str] = None) -> ExecutorCapabilities:
        driver = (cli_name or self.default_cli).strip().lower()
        return ExecutorCapabilities(
            executor_id=driver if driver.isidentifier() else "custom",
            capabilities=_DRIVER_CAPABILITIES.get(
                driver,
                (
                    ExecutorCapability.WORKSPACE_EXECUTION,
                    ExecutorCapability.TOOL_EXECUTION,
                    ExecutorCapability.CANCEL_PROCESS_TREE,
                ),
            ),
        )

    def is_cli_installed(self, cli_name: Optional[str] = None) -> bool:
        target = (cli_name or self.default_cli).strip()
        if not target:
            return False
        executable = _DRIVER_EXECUTABLES.get(target.lower(), target)
        if Path(executable).is_Absolute() if hasattr(Path, "is_Absolute") else Path(executable).is_absolute():
            return Path(executable).is_file()
        return shutil.which(executable) is not None

    @staticmethod
    def _Filtered_env(allowed_env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        """Filter sensitive environment variables not explicitly authorized for the worker."""
        return filter_worker_env(allowed_env=allowed_env)

    def build_invocation(
        self,
        prompt: str,
        cli_name: Optional[str] = None,
        *,
        extra_args: Sequence[str] = (),
        resume_session: Optional[str] = None,
        custom_command: Optional[Sequence[str]] = None,
    ) -> InvocationPlan:
        return build_invocation(
            cli_name or self.default_cli,
            prompt,
            extra_args=extra_args,
            resume_session=resume_session,
            custom_command=custom_command,
        )

    async def cancel_process_tree(self, pid: int, *, verify_timeout: float = 3.0) -> bool:
        return await cancel_process_tree(pid, verify_timeout=verify_timeout)

    async def cancel(self, attempt_id: str, *, reason: str = "cancelled_by_operator") -> Dict[str, Any]:
        """Idempotently cancel an in-flight or already-terminated worker attempt."""
        active = self._active_attempts.get(attempt_id)
        if active is None:
            prior = self._terminated_attempts.get(attempt_id)
            return {
                "attempt_id": attempt_id,
                "cancelled": True,
                "already_terminated": True,
                "tree_killed": prior.get("tree_killed", True) if prior else True,
                "reason": prior.get("reason", reason) if prior else reason,
            }

        active.cancel_reason = reason
        active.cancelled_event.set()
        pid = active.process.pid
        killed = await self.cancel_process_tree(pid) if pid else True
        active.tree_killed = killed
        record = {
            "attempt_id": attempt_id,
            "cancelled": True,
            "already_terminated": False,
            "tree_killed": killed,
            "reason": reason,
            "pid": pid,
        }
        self._terminated_attempts[attempt_id] = record
        return record

    async def execute_task_in_worktree(
        self,
        worktree_path: Path | str,
        prompt: str,
        cli_name: Optional[str] = None,
        timeout: float = 300,
        dry_run: bool = False,
        forbidden_files: Optional[List[str]] = None,
        *,
        attempt_id: Optional[str] = None,
        task_id: str = "task-default",
        run_id: str = "run-default",
        ordinal: int = 1,
        provider: str = "local_cli",
        model: str = "default",
        base_sha: str = "0" * 40,
        custom_command: Optional[Sequence[str]] = None,
        extra_args: Sequence[str] = (),
        resume_session: Optional[str] = None,
        allowed_env: Optional[Mapping[str, str]] = None,
        artifacts_dir: Optional[Path | str] = None,
        artifacts_rel_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a worker command in the resolved worktree directory.

        Conforms to S04 / T04 (RF04, RF06, RT04, GAP A02, GAP A11):
        - Resolves and validates `worktree_path` as an existing directory (`cwd`).
        - Filters sensitive environment variables (`filter_worker_env`).
        - Missing CLI returns `success=False`, `error="executor_unavailable"`, `simulated=False` unless `dry_run=True`.
        - Timeout or `cancel(attempt_id)` terminates the entire process tree (`cancel_process_tree`) and verifies death.
        """
        resolved_attempt_id = attempt_id or f"att-{uuid.uuid4().hex[:12]}"
        cli = (cli_name or self.default_cli).strip()
        raw_path_str = str(worktree_path)

        if not raw_path_str or "\x00" in raw_path_str:
            failure = FailureDetail(
                code="invalid_workspace_cwd",
                message="Workspace path cannot be empty or contain NUL bytes",
                retryable=False,
            )
            return {
                "success": False,
                "cli": cli,
                "exit_code": None,
                "output": "",
                "stderr": "",
                "error": "invalid_workspace_cwd",
                "simulated": False,
                "process_status": ProcessStatus.CRASHED.value,
                "cwd": None,
                "failure": failure,
            }

        target_dir = Path(os.path.realpath(raw_path_str))
        if not target_dir.exists() or not target_dir.is_dir():
            failure = FailureDetail(
                code="invalid_workspace_cwd",
                message=f"Workspace directory does not exist: {target_dir}",
                retryable=False,
            )
            return {
                "success": False,
                "cli": cli,
                "exit_code": None,
                "output": "",
                "stderr": "",
                "error": "invalid_workspace_cwd",
                "simulated": False,
                "process_status": ProcessStatus.CRASHED.value,
                "cwd": str(target_dir),
                "failure": failure,
            }

        if dry_run:
            now_dt = datetime.now(timezone.utc)
            contract_file = target_dir / "CONTRACT_APPLIED.md"
            contract_file.write_text(f"# Dry-run simulation by {cli}\n\n{prompt}", encoding="utf-8")
            sim_attempt = TaskAttempt(
                attempt_id=resolved_attempt_id,
                task_id=task_id,
                run_id=run_id,
                ordinal=ordinal,
                executor_id=cli if cli.isidentifier() else "dry_run",
                provider=provider,
                model=model,
                base_sha=base_sha,
                workspace_path=str(target_dir),
                process_status=ProcessStatus.EXITED,
                exit_code=0,
                started_at=now_dt,
                finished_at=now_dt,
                exit_reason="dry_run_simulated",
            )
            return {
                "success": True,
                "cli": cli,
                "exit_code": 0,
                "output": f"Dry-run simulated execution for task in {target_dir}",
                "stderr": "",
                "simulated": True,
                "error": None,
                "process_status": ProcessStatus.EXITED.value,
                "cwd": str(target_dir),
                "attempt_id": resolved_attempt_id,
                "attempt": sim_attempt,
                "artifacts": (),
            }

        plan = self.build_invocation(
            prompt,
            cli_name=cli,
            extra_args=extra_args,
            resume_session=resume_session,
            custom_command=custom_command,
        )

        if custom_command is None and not self.is_cli_installed(plan.executable):
            logger.error(f"Worker CLI '{cli}' ('{plan.executable}') not found in PATH (executor_unavailable).")
            now_dt = datetime.now(timezone.utc)
            failure = FailureDetail(
                code="executor_unavailable",
                message=f"Required CLI '{plan.executable}' is not installed or not in PATH",
                retryable=False,
            )
            crashed_attempt = TaskAttempt(
                attempt_id=resolved_attempt_id,
                task_id=task_id,
                run_id=run_id,
                ordinal=ordinal,
                executor_id=plan.capabilities.executor_id,
                provider=provider,
                model=model,
                base_sha=base_sha,
                workspace_path=str(target_dir),
                process_status=ProcessStatus.CRASHED,
                started_at=now_dt,
                finished_at=now_dt,
                exit_reason="executor_unavailable",
            )
            return {
                "success": False,
                "cli": cli,
                "exit_code": None,
                "output": "",
                "stderr": "",
                "error": "executor_unavailable",
                "simulated": False,
                "process_status": ProcessStatus.CRASHED.value,
                "cwd": str(target_dir),
                "argv": plan.argv,
                "attempt_id": resolved_attempt_id,
                "attempt": crashed_attempt,
                "failure": failure,
                "artifacts": (),
            }

        env = filter_worker_env(allowed_env=allowed_env)
        if forbidden_files:
            env["HYDRA_FORBIDDEN_FILES"] = ",".join(forbidden_files)

        process: Optional[asyncio.subprocess.Process] = None
        active_entry: Optional[_ActiveProcessEntry] = None
        schedule_t0 = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        stdout_bytes = b""
        stderr_bytes = b""
        dispatch_latency_ms = 0.0

        try:
            kwargs: Dict[str, Any] = {
                "cwd": str(target_dir),
                "stdin": asyncio.subprocess.PIPE if plan.stdin_bytes is not None else asyncio.subprocess.DEVNULL,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
                "env": env,
            }
            if os.name != "nt":
                kwargs["start_new_session"] = True
            else:
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            process = await asyncio.create_subprocess_exec(*plan.argv, **kwargs)
            dispatch_latency_ms = (time.perf_counter() - schedule_t0) * 1000.0
            active_entry = _ActiveProcessEntry(attempt_id=resolved_attempt_id, process=process)
            self._active_attempts[resolved_attempt_id] = active_entry

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=plan.stdin_bytes),
                timeout=timeout,
            )
            finished_at = datetime.now(timezone.utc)
            duration_seconds = max((finished_at - started_at).total_seconds(), 0.0)

            if active_entry.cancelled_event.is_set():
                proc_status = ProcessStatus.CANCELLED
                exit_reason = active_entry.cancel_reason
                error_code: Optional[str] = "execution_cancelled"
                success = False
                failure_obj: Optional[FailureDetail] = FailureDetail(
                    code="execution_cancelled",
                    message=f"Worker execution cancelled: {exit_reason}",
                    retryable=True,
                )
            else:
                proc_status = ProcessStatus.EXITED
                exit_code = int(process.returncode or 0)
                success = exit_code == 0
                exit_reason = "completed" if success else f"exited_with_code_{exit_code}"
                stderr_text_tmp = stderr_bytes.decode("utf-8", errors="replace")
                error_code = None if success else (stderr_text_tmp.strip() or "worker_nonzero_exit")
                failure_obj = (
                    None
                    if success
                    else FailureDetail(
                        code="worker_nonzero_exit",
                        message=f"Worker exited with code {exit_code}",
                        retryable=True,
                    )
                )

            artifacts = self._persist_stdio_artifacts(
                artifacts_dir=artifacts_dir,
                artifacts_rel_prefix=artifacts_rel_prefix,
                run_id=run_id,
                attempt_id=resolved_attempt_id,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
            )

            attempt_model = TaskAttempt(
                attempt_id=resolved_attempt_id,
                task_id=task_id,
                run_id=run_id,
                ordinal=ordinal,
                executor_id=plan.capabilities.executor_id,
                provider=provider,
                model=model,
                base_sha=base_sha,
                workspace_path=str(target_dir),
                process_status=proc_status,
                exit_code=int(process.returncode) if proc_status == ProcessStatus.EXITED and process.returncode is not None else None,
                started_at=started_at,
                finished_at=finished_at,
                exit_reason=exit_reason,
            )

            self._terminated_attempts[resolved_attempt_id] = {
                "attempt_id": resolved_attempt_id,
                "cancelled": proc_status == ProcessStatus.CANCELLED,
                "already_terminated": True,
                "tree_killed": active_entry.tree_killed,
                "reason": exit_reason,
                "pid": process.pid,
            }

            return {
                "success": success,
                "cli": cli,
                "pid": process.pid,
                "exit_code": process.returncode if proc_status == ProcessStatus.EXITED else None,
                "output": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "error": error_code,
                "simulated": False,
                "process_status": proc_status.value,
                "cwd": str(target_dir),
                "argv": plan.argv,
                "duration_seconds": duration_seconds,
                "dispatch_latency_ms": dispatch_latency_ms,
                "tree_killed": active_entry.tree_killed,
                "attempt_id": resolved_attempt_id,
                "attempt": attempt_model,
                "failure": failure_obj,
                "artifacts": artifacts,
            }

        except asyncio.TimeoutError:
            tree_killed = True
            pid_val = process.pid if process else None
            if process is not None:
                tree_killed = await self.cancel_process_tree(process.pid)
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except Exception:
                    pass

            finished_at = datetime.now(timezone.utc)
            duration_seconds = max((finished_at - started_at).total_seconds(), 0.0)
            artifacts = self._persist_stdio_artifacts(
                artifacts_dir=artifacts_dir,
                artifacts_rel_prefix=artifacts_rel_prefix,
                run_id=run_id,
                attempt_id=resolved_attempt_id,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
            )

            if active_entry and active_entry.cancelled_event.is_set():
                proc_status = ProcessStatus.CANCELLED
                err_str = "execution_cancelled"
                reason_str = active_entry.cancel_reason
            else:
                proc_status = ProcessStatus.TIMED_OUT
                err_str = "execution_timed_out"
                reason_str = f"timed_out_after_{timeout}s"

            attempt_model = TaskAttempt(
                attempt_id=resolved_attempt_id,
                task_id=task_id,
                run_id=run_id,
                ordinal=ordinal,
                executor_id=plan.capabilities.executor_id,
                provider=provider,
                model=model,
                base_sha=base_sha,
                workspace_path=str(target_dir),
                process_status=proc_status,
                started_at=started_at,
                finished_at=finished_at,
                exit_reason=reason_str,
            )
            self._terminated_attempts[resolved_attempt_id] = {
                "attempt_id": resolved_attempt_id,
                "cancelled": proc_status == ProcessStatus.CANCELLED,
                "already_terminated": True,
                "tree_killed": tree_killed,
                "reason": reason_str,
                "pid": pid_val,
            }
            return {
                "success": False,
                "cli": cli,
                "pid": pid_val,
                "exit_code": None,
                "output": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "error": err_str,
                "simulated": False,
                "process_status": proc_status.value,
                "cwd": str(target_dir),
                "argv": plan.argv,
                "duration_seconds": duration_seconds,
                "dispatch_latency_ms": dispatch_latency_ms,
                "tree_killed": tree_killed,
                "attempt_id": resolved_attempt_id,
                "attempt": attempt_model,
                "failure": FailureDetail(
                    code=err_str,
                    message=f"Worker {reason_str}",
                    retryable=True,
                ),
                "artifacts": artifacts,
            }
        except Exception as exc:
            logger.error(f"Failed running worker {cli}: {exc}")
            finished_at = datetime.now(timezone.utc)
            crashed_attempt = TaskAttempt(
                attempt_id=resolved_attempt_id,
                task_id=task_id,
                run_id=run_id,
                ordinal=ordinal,
                executor_id=plan.capabilities.executor_id,
                provider=provider,
                model=model,
                base_sha=base_sha,
                workspace_path=str(target_dir),
                process_status=ProcessStatus.CRASHED,
                started_at=started_at,
                finished_at=finished_at,
                exit_reason=str(exc) or "spawn_error",
            )
            return {
                "success": False,
                "cli": cli,
                "exit_code": None,
                "output": "",
                "stderr": "",
                "error": str(exc),
                "simulated": False,
                "process_status": ProcessStatus.CRASHED.value,
                "cwd": str(target_dir),
                "argv": plan.argv,
                "attempt_id": resolved_attempt_id,
                "attempt": crashed_attempt,
                "failure": FailureDetail(
                    code="worker_spawn_error",
                    message=str(exc) or "Worker failed to start",
                    retryable=False,
                ),
                "artifacts": (),
            }
        finally:
            self._active_attempts.pop(resolved_attempt_id, None)

    @staticmethod
    def _persist_stdio_artifacts(
        *,
        artifacts_dir: Optional[Path | str],
        artifacts_rel_prefix: Optional[str],
        run_id: str,
        attempt_id: str,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
    ) -> Tuple[Artifact, ...]:
        if artifacts_dir is None:
            return ()
        out_dir = Path(artifacts_dir)
        prefix = (artifacts_rel_prefix or f"attempt/{attempt_id}").strip("/")
        stdout_art = _write_artifact_atomic(
            out_dir / "stdout.log",
            stdout_bytes,
            artifact_id=f"art-{attempt_id}-stdout",
            run_id=run_id,
            attempt_id=attempt_id,
            relative_path=f"{prefix}/stdout.log",
            kind="log",
        )
        stderr_art = _write_artifact_atomic(
            out_dir / "stderr.log",
            stderr_bytes,
            artifact_id=f"art-{attempt_id}-stderr",
            run_id=run_id,
            attempt_id=attempt_id,
            relative_path=f"{prefix}/stderr.log",
            kind="log",
        )
        return (stdout_art, stderr_art)


__all__ = [
    "InvocationPlan",
    "WorkerRunner",
    "build_invocation",
    "cancel_process_tree",
    "filter_worker_env",
    "is_process_alive",
]
