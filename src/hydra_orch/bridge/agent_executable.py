"""Find an agent in PATH or its registered Windows desktop installation, with safe Windows .cmd handling."""
from __future__ import annotations

import asyncio
import asyncio.subprocess as _aio_subprocess
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Mapping, Optional, Sequence, Tuple

_codex_cache = None

_NPM_NODE_SCRIPT_RE = re.compile(
    r'"%(?:~dp0|dp0%)[\\/]?((?:(?:\.\.[\\/])+)?node_modules[\\/][^"\r\n]+?\.(?:c|m)?js)"',
    re.IGNORECASE,
)

_ORIG_CREATE_SUBPROCESS_EXEC = asyncio.create_subprocess_exec


def resolve_agent_executable(command, *, path=None):
    found = shutil.which(command) if path is None else shutil.which(command, path=path)
    if found:
        return found
    if os.name != 'nt' or command.lower() not in {'codex', 'codex.exe'}:
        return None
    global _codex_cache
    if _codex_cache and Path(_codex_cache[1]).is_file() and time.monotonic()-_codex_cache[0] < 60:
        return _codex_cache[1]
    # The Store app can be installed without its CLI directory in Explorer's
    # inherited PATH. Query the registered package; never pin a versioned path.
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command',
            'Get-AppxPackage -Name OpenAI.Codex | Select-Object -ExpandProperty InstallLocation'],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=8,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            return None
        for root in result.stdout.decode(errors='replace').splitlines():
            candidate = Path(root.strip()) / 'app/resources/codex.exe'
            if candidate.is_file():
                _codex_cache = (time.monotonic(), str(candidate))
                return str(candidate)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def get_windows_comspec(env: Optional[Mapping[str, str]] = None) -> str:
    """Resolve Windows cmd.exe safely without relying on mutable PATH shims."""
    if env:
        for key in ("ComSpec", "COMSPEC"):
            val = env.get(key)
            if val and "\x00" not in val and Path(val).is_file():
                return str(val)
    for key in ("ComSpec", "COMSPEC"):
        val = os.environ.get(key)
        if val and "\x00" not in val and Path(val).is_file():
            return str(val)
    sys_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    candidate = Path(sys_root) / "System32" / "cmd.exe"
    if candidate.is_file():
        return str(candidate)
    return shutil.which("cmd.exe") or "cmd.exe"


def _find_node_binary(shim_dir: Path, *, path: Optional[str] = None) -> Optional[str]:
    for sibling_name in ("node.exe", "node"):
        sibling = shim_dir / sibling_name
        if sibling.is_file() and sibling.suffix.lower() not in {".cmd", ".bat"}:
            return str(sibling)
    search_path = path if path is not None else os.environ.get("PATH")
    for bin_name in ("node.exe", "node"):
        found = shutil.which(bin_name, path=search_path)
        if found:
            fp = Path(found)
            if fp.is_file() and fp.suffix.lower() not in {".cmd", ".bat"}:
                return str(fp)
    return None


def resolve_npm_node_script(
    cmd_path: str | Path,
    *,
    path: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """Unwrap an npm-generated Windows .cmd/.bat shim to `(node_exe, js_script)` for direct CreateProcess.

    Returns `None` for custom `.cmd`/`.bat` shims (e.g. test shims invoking `python.exe fake_cli.py`
    or shims wrapping native `.exe` binaries) so callers keep supporting arbitrary `.cmd` wrappers.
    """
    if not cmd_path or "\x00" in str(cmd_path):
        return None
    shim = Path(cmd_path)
    if shim.suffix.lower() not in {".cmd", ".bat"} or not shim.is_file():
        return None
    try:
        content = shim.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if "node" not in content.lower():
        return None
    match = _NPM_NODE_SCRIPT_RE.search(content)
    if not match:
        return None

    rel_js = match.group(1).replace("\\", os.sep).replace("/", os.sep)
    if "\x00" in rel_js:
        return None
    try:
        js_target = (shim.parent / rel_js).resolve()
    except OSError:
        return None
    if not js_target.is_file():
        return None

    node_exe = _find_node_binary(shim.parent, path=path)
    if not node_exe:
        return None
    return (node_exe, str(js_target))


def _encode_cmd_bat_argument(arg: str) -> str:
    """Encode a single argument for `cmd.exe /d /s /c` -> `.cmd` `%*` -> MSVCRT (CVE-2024-24576 safe).

    1. Builds MSVCRT-quoted form using paired `""` for literal quotes so every non-quote character
       remains strictly inside `cmd.exe` quote state during `.cmd` `%*` re-parsing (Pass 2).
    2. Escapes all `cmd.exe` metacharacters (`^`, `"`, `&`, `|`, `<`, `>`, `(`, `)`, `!`) with `^`
       for `cmd.exe /d /s /c` (Pass 1, outside quote mode) and breaks `%VAR%` expansion by caret-escaping
       the character immediately following `%`.
    """
    out = ['"']
    backslashes = 0
    for ch in arg:
        if ch == "\\":
            backslashes += 1
        elif ch == '"':
            out.append("\\" * (backslashes * 2))
            out.append('""')
            backslashes = 0
        else:
            if backslashes:
                out.append("\\" * backslashes)
                backslashes = 0
            out.append(ch)
    if backslashes:
        out.append("\\" * (backslashes * 2))
    out.append('"')
    pass2_safe = "".join(out)

    pass1_out = []
    prev_percent = False
    for ch in pass2_safe:
        if ch in '^"&|<>()!':
            pass1_out.append("^" + ch)
            prev_percent = False
        elif ch == "%":
            pass1_out.append("%")
            prev_percent = True
        else:
            if prev_percent and ch not in " \t":
                pass1_out.append("^" + ch)
            else:
                pass1_out.append(ch)
            prev_percent = False
    return "".join(pass1_out)


def format_windows_cmd_commandline(argv: Sequence[str]) -> str:
    """Build a shell-injection-safe inner command string for `cmd.exe /d /s /c "<inner>"`.

    Rejects `\\r`, `\\n`, and `\\x00` in any element with `ValueError`, quotes the target `.cmd`/`.bat`
    path safely, and escapes every argument against `cmd.exe` metacharacter injection and `%VAR%` expansion.
    """
    if isinstance(argv, (str, bytes)) or not argv:
        raise ValueError("argv must be a non-empty sequence of strings")

    parts = [str(item) for item in argv]
    for item in parts:
        if "\x00" in item or "\r" in item or "\n" in item:
            raise ValueError("Windows .cmd/.bat arguments cannot contain CR, LF, or NUL characters")

    prog = parts[0]
    if not prog.strip() or '"' in prog:
        raise ValueError("Windows .cmd/.bat executable path must be non-empty and cannot contain quotes")
    if "%" in prog:
        raise ValueError("Windows .cmd/.bat executable path cannot contain percent metacharacters")

    formatted = [f'"{prog}"']
    for arg in parts[1:]:
        formatted.append(_encode_cmd_bat_argument(arg))
    return " ".join(formatted)


async def spawn_windows_cmd_subprocess(
    comspec: str,
    inner_cmdline: str,
    *,
    exec_fn: Any = None,
    **kwargs: Any,
) -> _aio_subprocess.Process:
    """Launch `cmd.exe /d /s /c "<inner_cmdline>"` on Windows without `list2cmdline` quote corruption."""
    target_exec_fn = asyncio.create_subprocess_exec if exec_fn is None else exec_fn
    if os.name != "nt" or target_exec_fn is not _ORIG_CREATE_SUBPROCESS_EXEC:
        return await target_exec_fn(comspec, "/d", "/s", "/c", inner_cmdline, **kwargs)

    limit = kwargs.pop("limit", 2**16)
    stdin = kwargs.pop("stdin", subprocess.PIPE)
    stdout = kwargs.pop("stdout", subprocess.PIPE)
    stderr = kwargs.pop("stderr", subprocess.PIPE)

    comspec_q = f'"{comspec}"' if any(c.isspace() for c in comspec) else comspec
    raw_cmdline = f'{comspec_q} /d /s /c "{inner_cmdline}"'
    exe_arg = comspec if Path(comspec).is_file() else None

    loop = asyncio.get_running_loop()
    protocol = _aio_subprocess.SubprocessStreamProtocol(limit=limit, loop=loop)
    transport = await loop._make_subprocess_transport(  # type: ignore[attr-defined]
        protocol,
        raw_cmdline,
        False,
        stdin,
        stdout,
        stderr,
        0,
        executable=exe_arg,
        **kwargs,
    )
    return _aio_subprocess.Process(transport, protocol, loop)


def run_windows_cmd_sync(
    argv: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Synchronously execute a `.cmd`/`.bat` command line safely via `cmd.exe /d /s /c`."""
    comspec = get_windows_comspec(env)
    inner = format_windows_cmd_commandline(argv)
    comspec_q = f'"{comspec}"' if any(c.isspace() for c in comspec) else comspec
    raw_cmdline = f'{comspec_q} /d /s /c "{inner}"'
    exe_arg = comspec if Path(comspec).is_file() else None
    return subprocess.run(raw_cmdline, executable=exe_arg, shell=False, env=env, **kwargs)
