"""Bounded snapshots and text diffs for chats in ordinary folders; never initializes Git."""
from __future__ import annotations

import difflib
import filecmp
import os
from pathlib import Path
import shutil

from hydra_orch.core.redaction import redact_text
from hydra_orch.model import ContractViolation

_SKIP = {".git", ".orchestrator", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


def files(root: Path):
    visited = set()
    for directory, folders, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        if parent.resolve() in visited:
            folders[:] = []
            continue
        visited.add(parent.resolve())
        folders[:] = [name for name in folders if name not in _SKIP and not (parent / name).is_symlink() and (parent / name).resolve().is_relative_to(root.resolve())]
        for name in names:
            path = parent / name
            if name in _SKIP or name.lower().startswith(".env") or path.is_symlink():
                continue
            if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                yield path.relative_to(root)


def snapshot(source: Path, directory: Path) -> Path:
    """Keep immutable baseline and working copy under the orchestrator runtime."""
    baseline, working = directory / "base", directory / "work"
    marker = directory / "ready"
    if marker.is_file() and baseline.is_dir() and working.is_dir():
        return working
    if directory.exists():
        raise ContractViolation("workspace_incomplete", "A cópia desta conversa ficou incompleta. Abra um novo chat; a pasta original foi preservada.")
    selected, total = [], 0
    for name in files(source):
        selected.append(name)
        total += (source / name).stat().st_size
        if len(selected) > 10000 or total > 256 * 1024 * 1024:
            raise ContractViolation("folder_too_large", "A pasta ultrapassa o limite da cópia para conversa (10 mil arquivos ou 256 MB). Selecione uma pasta menor.")
    baseline.mkdir(parents=True)
    working.mkdir()
    for name in selected:
        for target_root, origin in ((baseline, source), (working, baseline)):
            target = target_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin / name, target, follow_symlinks=False)
            if target.is_symlink():
                raise ContractViolation("workspace_invalid", "Um link mudou durante a cópia. Abra um novo chat com uma pasta estável.")
    marker.write_text("ready", encoding="ascii")
    return working


def diff(baseline: Path, working: Path) -> str:
    for directory, folders, names in os.walk(working, followlinks=False):
        folders[:] = [name for name in folders if name not in _SKIP]
        for name in [*folders, *names]:
            candidate = Path(directory) / name
            if candidate.is_symlink():
                raise ContractViolation("scope_violation", "A cópia contém um link que exige revisão. Os arquivos foram preservados.")
    names = set(files(baseline)) | set(files(working))
    result = ""
    for name in sorted(names):
        before, after = baseline / name, working / name
        if max(before.stat().st_size if before.is_file() else 0, after.stat().st_size if after.is_file() else 0) > 100000:
            if not before.is_file() or not after.is_file() or not filecmp.cmp(before, after, shallow=False):
                result += f"Arquivo grande alterado: {name.as_posix()}\n"
            continue
        old = before.read_bytes() if before.is_file() else b""
        new = after.read_bytes() if after.is_file() else b""
        if old == new and before.exists() == after.exists():
            continue
        if not old and not new:
            result += f"Arquivo {'adicionado' if after.exists() else 'removido'}: {name.as_posix()}\n"
            continue
        if b"\0" in old or b"\0" in new:
            result += f"Arquivo binário alterado: {name.as_posix()}\n"
        else:
            result += "".join(difflib.unified_diff(old.decode("utf-8", errors="replace").splitlines(keepends=True), new.decode("utf-8", errors="replace").splitlines(keepends=True), fromfile=f"a/{name.as_posix()}", tofile=f"b/{name.as_posix()}"))
        if len(result) >= 200000:
            break
    return redact_text(result)[:200000]
