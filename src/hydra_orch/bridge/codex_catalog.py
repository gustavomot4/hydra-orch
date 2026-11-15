"""Per-invocation gateway catalog derived from the installed CLI's own schema."""
from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path
import subprocess

from hydra_orch.bridge.pty_runner import _bundled_codex_needs_no_daemon
from hydra_orch.model import ContractViolation


@lru_cache(maxsize=4)
def bundled(executable: str):
    args = [executable]
    if _bundled_codex_needs_no_daemon(executable):
        args += ['--no-daemon']
    result = subprocess.run(args + ['debug', 'models', '--bundled'], capture_output=True, timeout=20, stdin=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ContractViolation('route_unsupported', 'Esta versão do Codex não fornece o catálogo de ferramentas necessário ao gateway.')
    entries = json.loads(result.stdout).get('models', [])
    plain = [e for e in entries if e.get('tool_mode') != 'code_mode_only' and not e.get('use_responses_lite')]
    if not plain:
        raise ContractViolation('route_unsupported', 'O Codex não tem um perfil de ferramentas compatível com este gateway.')
    return next((e for e in plain if e.get('slug') == 'gpt-5.5'), plain[0])


def gateway_catalog(executable, target, folder: Path):
    entry = copy.deepcopy(bundled(executable))
    entry.update(slug=target, display_name=target, tool_mode=None, use_responses_lite=False,
                 multi_agent_version=None, multi_agent_reasoning_effort=None,
                 experimental_supported_tools=[], service_tiers=[], additional_speed_tiers=[],
                 context_window=64000, max_context_window=64000, upgrade=None, availability_nux=None)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'gateway-model.json'
    if path.is_symlink():
        raise ContractViolation('context_path_escape', 'O catálogo local não é seguro.')
    path.write_text(json.dumps({'models': [entry]}), encoding='utf-8')
    return path
