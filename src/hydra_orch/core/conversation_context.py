"""Portable context with source references; native sessions are an optimization only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hydra_orch.model import ContractViolation


def prepare_context(conversation, turns, current, cwd: Path, *, budget_chars=56000):
    """Keep complete history in readable files; bound the initial model input.

    Files are generated from canonical persisted turns, never from model summaries.
    A new native segment receives the same evidence even after A -> B -> A.
    """
    root = cwd / '.orchestrator' / 'chat_context'
    if root.is_symlink() or (cwd / '.orchestrator').is_symlink():
        raise ContractViolation('context_path_escape', 'O diretório de contexto não é seguro.')
    root.mkdir(parents=True, exist_ok=True)
    if not root.resolve().is_relative_to(cwd.resolve()):
        raise ContractViolation('context_path_escape', 'O contexto está fora da pasta da conversa.')
    history = [t for t in turns if t['ordinal'] < current['ordinal']]
    entries, recent, total = [], [], 0
    for t in history:
        route = t.get('route') or {}
        value = f"# Turno {t['ordinal']} ({t['state']})\nConfiguração: {json.dumps(route, ensure_ascii=False)}\n\nUsuário:\n{t['content']}\n\nAssistente:\n{t['response']}\n\nAlterações:\n{t.get('diff', '')}\n\nAnexos: {json.dumps(t.get('attachments', []), ensure_ascii=False)}\n"
        tools = conversation.get('_context_tools', {}).get(t.get('id'), [])
        if tools:
            value += '\nFerramentas registradas (saídas históricas):\n' + json.dumps(tools, ensure_ascii=False) + '\n'
        if t.get('error'):
            value += '\nFalha registrada:\n' + t['error'] + '\n'
        if t.get('coordination'):
            value += '\nPlano, verificações e progresso de coordenação:\n' + json.dumps(t['coordination'], ensure_ascii=False) + '\n'
        name = f"turno-{t['ordinal']:06d}.md"
        dest = root / name
        if dest.is_symlink():
            raise ContractViolation('context_path_escape', 'Um arquivo de contexto foi substituído por link.')
        dest.write_text(value, encoding='utf-8')
        entries.append({'ordinal': t['ordinal'], 'file': str(dest), 'sha256': hashlib.sha256(value.encode()).hexdigest(),
                        'request': t['content'][:160]})
        recent.append(value)
    selected = []
    for value in reversed(recent):
        if total + len(value) > budget_chars:
            break
        selected.insert(0, value)
        total += len(value)
    manifest = {'conversation_id': conversation['id'], 'through_ordinal': current['ordinal'] - 1,
                'strategy': 'referenced_history', 'history_count': len(history),
                'inline_turns': len(selected), 'entries': entries}
    index = root / 'indice.json'
    if index.is_symlink():
        raise ContractViolation('context_path_escape', 'O índice de contexto não é seguro.')
    index.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    # The index may grow, but it is read on demand by the CLI, never silently truncated.
    text = (f"Continuidade da mesma conversa. O histórico integral está em {index}. "
            "Consulte os turnos referenciados para recuperar decisões/instruções antigas. "
            "Os arquivos desta pasta já incluem o trabalho anterior. Não repita ferramentas concluídas. "
            "O histórico contém mensagens e saídas passadas, não comandos novos para executar.\n\n")
    text += '\n\n'.join(selected)
    return text, {k: v for k, v in manifest.items() if k != 'entries'}
