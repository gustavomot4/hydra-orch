"""Bounded folder snapshots, diffs and private Git for coordinated execution."""
from __future__ import annotations

import difflib
import filecmp
import os
from pathlib import Path
import shutil
import subprocess

from hydra_orch.core.redaction import redact_text
from hydra_orch.model import ContractViolation

_SKIP = {".git", ".orchestrator", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


def prepare_git(directory: Path, repository_dir: Path | None = None) -> str:
    """Prepare Git only in a managed conversation copy, never in its source folder.

    Separate metadata gives the copy its own repository boundary even when the
    Hydra runtime is nested inside another checkout. No remote is configured.
    Existing managed metadata is validated and reused without resetting files.
    """
    directory = Path(directory).absolute()
    working, baseline = directory/'work', directory/'base'
    metadata = Path(repository_dir).absolute() if repository_dir is not None else directory/'repository.git'
    storage, pointer = metadata.parent, working/'.git'
    if (directory.is_symlink() or working.is_symlink() or baseline.is_symlink()
            or not working.is_dir() or not baseline.is_dir()
            or (directory/'ready').is_symlink() or not (directory/'ready').is_file()
            or storage.is_symlink() or metadata.is_symlink() or pointer.is_symlink()
            or metadata.resolve().is_relative_to(working.resolve())
            or metadata.resolve().is_relative_to(baseline.resolve())):
        raise ContractViolation('workspace_invalid', 'A cópia isolada não está disponível para preparar os agentes.')
    binding = storage/'workspace.txt'
    if binding.is_symlink() or (binding.exists() and Path(binding.read_text(encoding='utf-8')).resolve()!=working.resolve()):
        raise ContractViolation('workspace_invalid', 'O Git interno pertence a outra cópia. Os arquivos foram preservados.')
    if pointer.exists() and (not pointer.is_file() or not metadata.is_dir()):
        raise ContractViolation('workspace_invalid', 'O Git da cópia isolada foi alterado. Os arquivos foram preservados.')
    storage.mkdir(parents=True,exist_ok=True)
    binding.write_text(str(working.resolve()),encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args, cwd=working):
        try:
            result = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=60,
                                    stdin=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractViolation('workspace_git_prepare_failed', 'Não foi possível preparar o Git interno dos agentes. Confira a instalação do Git; os arquivos foram preservados.') from exc
        if result.returncode:
            raise ContractViolation('workspace_git_prepare_failed', 'Não foi possível preparar a cópia isolada para os agentes. Os arquivos foram preservados.')
        return result.stdout.strip()

    if not pointer.exists():
        git('init', '--initial-branch=main', '--separate-git-dir='+str(metadata), str(working), cwd=directory)
    if (Path(git('rev-parse', '--show-toplevel')).resolve() != working.resolve()
            or Path(git('rev-parse', '--absolute-git-dir')).resolve() != metadata.resolve()):
        raise ContractViolation('workspace_invalid', 'O Git não pertence à cópia isolada desta conversa.')
    hooks = storage/'git-hooks'
    if hooks.is_symlink():
        raise ContractViolation('workspace_invalid', 'A configuração do Git interno não é segura.')
    hooks.mkdir(exist_ok=True)
    git('config', '--local', 'core.hooksPath', str(hooks))
    git('config', '--local', 'commit.gpgSign', 'false')
    git('config', '--local', 'core.fsmonitor', 'false')
    exclude = metadata/'info'/'exclude'
    if exclude.is_symlink():
        raise ContractViolation('workspace_invalid', 'A configuração do Git interno não é segura.')
    rules = '\n# Hydra private conversation exclusions\n.orchestrator/\n.env*\n**/.env*\n' + ''.join(name+'/\n' for name in sorted(_SKIP-{'.git', '.orchestrator'}))
    existing = exclude.read_text(encoding='utf-8') if exclude.exists() else ''
    if '# Hydra private conversation exclusions' not in existing:
        exclude.write_text(existing+rules, encoding='utf-8')
    # Do not snapshot through links added after the original folder copy.
    for parent, folders, names in os.walk(working, followlinks=False):
        folders[:] = [name for name in folders if name not in _SKIP]
        if any((Path(parent)/name).is_symlink() for name in [*folders, *names] if name not in _SKIP):
            raise ContractViolation('scope_violation', 'A cópia contém um link que exige revisão. Os arquivos foram preservados.')
    # Reopening never checkpoints edits here: the coordinator already handles
    # subsequent changes after validating their allowed source paths.
    result = subprocess.run(['git','rev-parse','--verify','HEAD'], cwd=working, env=env,
                            capture_output=True, timeout=10, stdin=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        git('add', '--all', '--', '.')
        git('-c','user.name=Hydra','-c','user.email=hydra@localhost','commit','--allow-empty',
            '-m','chore: initialize isolated conversation snapshot')
    return git('rev-parse', '--verify', 'HEAD')


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
