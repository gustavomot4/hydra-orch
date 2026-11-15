"""Find an agent in PATH or its registered Windows desktop installation."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

_codex_cache = None


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
