"""Bounded folder snapshots, diffs, 3-way sync and private Git for coordinated execution."""
from __future__ import annotations

from contextlib import suppress
import difflib
import filecmp
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import uuid

from hydra_orch.core.git_workspace import is_link_or_junction, win_long_path
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import ContractViolation, _validate_relative_path

_SKIP = {".git", ".orchestrator", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
_MAX_SNAPSHOT_FILES = 10000
_MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024


def is_ignored_rel_path(rel_posix: str) -> bool:
    """Return True if a relative POSIX path targets skipped directories or .env files."""
    normalized = rel_posix.replace("\\", "/").strip("/")
    if not normalized:
        return True
    parts = PurePosixPath(normalized).parts
    return any(part in _SKIP or part.lower().startswith(".env") for part in parts)


def validate_sync_rel_path(rel_posix: str) -> Path:
    """Validate that a relative path is safe to synchronize with a project root."""
    try:
        clean = _validate_relative_path(rel_posix)
    except ValueError as exc:
        raise ContractViolation(
            "scope_violation",
            "O caminho relativo contém segmentos inválidos para sincronização.",
        ) from exc
    if any(ord(ch) < 32 for ch in clean) or is_ignored_rel_path(clean):
        raise ContractViolation(
            "scope_violation",
            "O caminho pertence a arquivos ignorados ou protegidos e não pode ser sincronizado.",
        )
    return Path(clean)


def has_link_on_rel_path(root: Path, rel: Path) -> bool:
    """Return True if `root` or any segment of `rel` beneath `root` is a symlink or NTFS junction."""
    if is_link_or_junction(root):
        return True
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if is_link_or_junction(cursor):
            return True
    return False


def assert_no_links_in_tree(tree_root: Path) -> None:
    """Raise ContractViolation('scope_violation') if `tree_root` or any non-skipped entry is a link/junction."""
    if is_link_or_junction(tree_root) or is_link_or_junction(tree_root / ".git"):
        raise ContractViolation(
            "scope_violation",
            "A cópia contém um link que exige revisão. Os arquivos foram preservados.",
        )
    for directory, folders, names in os.walk(win_long_path(tree_root), followlinks=False):
        parent = Path(directory)
        for name in [*folders, *names]:
            if name in _SKIP:
                continue
            if is_link_or_junction(parent / name):
                raise ContractViolation(
                    "scope_violation",
                    "A cópia contém um link que exige revisão. Os arquivos foram preservados.",
                )
        folders[:] = [name for name in folders if name not in _SKIP and not is_link_or_junction(parent / name)]


def atomic_copy_file(src_file: Path, dst_file: Path) -> None:
    """Atomically copy `src_file` to `dst_file` via a sibling temporary file and `os.replace`."""
    if is_link_or_junction(src_file) or is_link_or_junction(dst_file):
        raise ContractViolation(
            "scope_violation",
            "A cópia contém um link que exige revisão. Os arquivos foram preservados.",
        )
    lp_src = win_long_path(src_file)
    lp_parent = win_long_path(dst_file.parent)
    lp_parent.mkdir(parents=True, exist_ok=True)
    lp_dst = win_long_path(dst_file)
    tmp_path = dst_file.parent / f".{dst_file.name}.hydra-{uuid.uuid4().hex[:12]}.tmp"
    lp_tmp = win_long_path(tmp_path)
    try:
        with open(lp_src, "rb") as rf, open(lp_tmp, "wb") as wf:
            shutil.copyfileobj(rf, wf, length=1024 * 1024)
            wf.flush()
            os.fsync(wf.fileno())
        with suppress(OSError):
            shutil.copymode(lp_src, lp_tmp)
        if is_link_or_junction(dst_file):
            raise ContractViolation(
                "scope_violation",
                "O destino mudou para um link durante a cópia. Os arquivos foram preservados.",
            )
        os.replace(lp_tmp, lp_dst)
    except BaseException:
        with suppress(OSError):
            lp_tmp.unlink(missing_ok=True)
        raise


def prune_empty_parents(child: Path, stop_root: Path) -> None:
    """Remove empty parent subdirectories inside `stop_root`, never deleting `stop_root` itself."""
    if is_link_or_junction(stop_root):
        return
    stop_norm = os.path.normcase(os.path.realpath(win_long_path(stop_root)))
    parent = child.parent
    while True:
        if is_link_or_junction(parent):
            break
        parent_norm = os.path.normcase(os.path.realpath(win_long_path(parent)))
        if parent_norm == stop_norm or not parent_norm.startswith(stop_norm + os.sep):
            break
        try:
            win_long_path(parent).rmdir()
        except OSError:
            break
        parent = parent.parent


def prepare_git(directory: Path, repository_dir: Path | None = None) -> str:
    """Prepare Git only in a managed conversation copy, never in its source folder.

    Separate metadata gives the copy its own repository boundary even when the
    Hydra runtime is nested inside another checkout. No remote is configured.
    Existing managed metadata is validated and reused without resetting files.
    """
    directory = Path(directory).absolute()
    working, baseline = directory / "work", directory / "base"
    metadata = Path(repository_dir).absolute() if repository_dir is not None else directory / "repository.git"
    storage, pointer = metadata.parent, working / ".git"
    if (
        is_link_or_junction(directory)
        or is_link_or_junction(working)
        or is_link_or_junction(baseline)
        or not working.is_dir()
        or not baseline.is_dir()
        or is_link_or_junction(directory / "ready")
        or not (directory / "ready").is_file()
        or is_link_or_junction(storage)
        or is_link_or_junction(metadata)
        or is_link_or_junction(pointer)
        or metadata.resolve().is_relative_to(working.resolve())
        or metadata.resolve().is_relative_to(baseline.resolve())
    ):
        raise ContractViolation("workspace_invalid", "A cópia isolada não está disponível para preparar os agentes.")
    binding = storage / "workspace.txt"
    if is_link_or_junction(binding) or (
        binding.exists() and Path(binding.read_text(encoding="utf-8")).resolve() != working.resolve()
    ):
        raise ContractViolation("workspace_invalid", "O Git interno pertence a outra cópia. Os arquivos foram preservados.")
    if pointer.exists() and (not pointer.is_file() or not metadata.is_dir()):
        raise ContractViolation("workspace_invalid", "O Git da cópia isolada foi alterado. Os arquivos foram preservados.")
    storage.mkdir(parents=True, exist_ok=True)
    binding.write_text(str(working.resolve()), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args, cwd=working):
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractViolation(
                "workspace_git_prepare_failed",
                "Não foi possível preparar o Git interno dos agentes. Confira a instalação do Git; os arquivos foram preservados.",
            ) from exc
        if result.returncode:
            raise ContractViolation(
                "workspace_git_prepare_failed",
                "Não foi possível preparar a cópia isolada para os agentes. Os arquivos foram preservados.",
            )
        return result.stdout.strip()

    if not pointer.exists():
        git("init", "--initial-branch=main", "--separate-git-dir=" + str(metadata), str(working), cwd=directory)
    if (
        Path(git("rev-parse", "--show-toplevel")).resolve() != working.resolve()
        or Path(git("rev-parse", "--absolute-git-dir")).resolve() != metadata.resolve()
    ):
        raise ContractViolation("workspace_invalid", "O Git não pertence à cópia isolada desta conversa.")
    hooks = storage / "git-hooks"
    if is_link_or_junction(hooks):
        raise ContractViolation("workspace_invalid", "A configuração do Git interno não é segura.")
    hooks.mkdir(exist_ok=True)
    git("config", "--local", "core.hooksPath", str(hooks))
    git("config", "--local", "commit.gpgSign", "false")
    git("config", "--local", "core.fsmonitor", "false")
    exclude = metadata / "info" / "exclude"
    if is_link_or_junction(exclude):
        raise ContractViolation("workspace_invalid", "A configuração do Git interno não é segura.")
    rules = "\n# Hydra private conversation exclusions\n.orchestrator/\n.env*\n**/.env*\n" + "".join(
        name + "/\n" for name in sorted(_SKIP - {".git", ".orchestrator"})
    )
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if "# Hydra private conversation exclusions" not in existing:
        exclude.write_text(existing + rules, encoding="utf-8")
    # Do not snapshot through links or NTFS junctions added after the original folder copy.
    assert_no_links_in_tree(working)
    # Reopening never checkpoints edits here: the coordinator already handles
    # subsequent changes after validating their allowed source paths.
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=working,
        env=env,
        capture_output=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        git("add", "--all", "--", ".")
        git(
            "-c",
            "user.name=Hydra",
            "-c",
            "user.email=hydra@localhost",
            "commit",
            "--allow-empty",
            "-m",
            "chore: initialize isolated conversation snapshot",
        )
    return git("rev-parse", "--verify", "HEAD")


def files(root: Path):
    if is_link_or_junction(root):
        return
    visited = set()
    root_resolved = root.resolve()
    for directory, folders, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        if is_link_or_junction(parent):
            folders[:] = []
            continue
        parent_resolved = parent.resolve()
        if parent_resolved in visited:
            folders[:] = []
            continue
        visited.add(parent_resolved)
        folders[:] = [
            name
            for name in folders
            if name not in _SKIP
            and not is_link_or_junction(parent / name)
            and (parent / name).resolve().is_relative_to(root_resolved)
        ]
        for name in names:
            path = parent / name
            if name in _SKIP or name.lower().startswith(".env") or is_link_or_junction(path):
                continue
            if win_long_path(path).is_file() and path.resolve().is_relative_to(root_resolved):
                yield path.relative_to(root)


def refresh_clean_from_source(source: Path, directory: Path) -> list[str]:
    """Refresh untouched files in `base/` and `work/` when `source` changed externally."""
    source = Path(source)
    directory = Path(directory)
    baseline, working, marker = directory / "base", directory / "work", directory / "ready"
    if (
        is_link_or_junction(directory)
        or is_link_or_junction(baseline)
        or is_link_or_junction(working)
        or is_link_or_junction(marker)
    ):
        raise ContractViolation("workspace_invalid", "A cópia isolada não está disponível.")
    if not (win_long_path(marker).is_file() and win_long_path(baseline).is_dir() and win_long_path(working).is_dir()):
        return []
    assert_no_links_in_tree(working)
    assert_no_links_in_tree(baseline)
    if is_link_or_junction(source):
        raise ContractViolation("scope_violation", "A pasta original contém um link que exige revisão.")
    if not win_long_path(source).is_dir():
        return []

    base_map = {p.as_posix(): p for p in files(baseline)}
    work_map = {p.as_posix(): p for p in files(working)}
    source_map = {p.as_posix(): p for p in files(source)}

    base_count = len(base_map)
    work_count = len(work_map)
    base_bytes = sum(win_long_path(baseline / r).stat().st_size for r in base_map)
    work_bytes = sum(win_long_path(working / r).stat().st_size for r in work_map)

    refreshed: list[str] = []

    # 1. Remove files deleted externally only when `work/` is still identical to `base/`.
    for rel_str in sorted(set(base_map) - set(source_map)):
        rel_path = Path(rel_str)
        if has_link_on_rel_path(source, rel_path):
            continue
        if rel_str not in work_map:
            continue
        if not filecmp.cmp(win_long_path(baseline / rel_str), win_long_path(working / rel_str), shallow=False):
            continue
        old_base_size = win_long_path(baseline / rel_str).stat().st_size
        old_work_size = win_long_path(working / rel_str).stat().st_size
        win_long_path(working / rel_str).unlink(missing_ok=True)
        prune_empty_parents(working / rel_str, working)
        win_long_path(baseline / rel_str).unlink(missing_ok=True)
        prune_empty_parents(baseline / rel_str, baseline)
        base_bytes = max(0, base_bytes - old_base_size)
        work_bytes = max(0, work_bytes - old_work_size)
        base_count -= 1
        work_count -= 1
        del base_map[rel_str]
        del work_map[rel_str]
        refreshed.append(rel_str)

    # 2. Copy external additions and modifications only when `work/` is untouched relative to `base/`.
    for rel_str in sorted(source_map):
        if is_ignored_rel_path(rel_str):
            continue
        rel_path = Path(rel_str)
        if (
            has_link_on_rel_path(source, rel_path)
            or has_link_on_rel_path(working, rel_path)
            or has_link_on_rel_path(baseline, rel_path)
        ):
            continue
        src_file = source / rel_str
        new_size = win_long_path(src_file).stat().st_size
        if rel_str in base_map:
            if filecmp.cmp(win_long_path(baseline / rel_str), win_long_path(src_file), shallow=False):
                continue
            if rel_str not in work_map or not filecmp.cmp(
                win_long_path(baseline / rel_str), win_long_path(working / rel_str), shallow=False
            ):
                continue
            old_base_size = win_long_path(baseline / rel_str).stat().st_size
            old_work_size = win_long_path(working / rel_str).stat().st_size
            if (
                base_bytes - old_base_size + new_size > _MAX_SNAPSHOT_BYTES
                or work_bytes - old_work_size + new_size > _MAX_SNAPSHOT_BYTES
            ):
                continue
            atomic_copy_file(src_file, baseline / rel_str)
            atomic_copy_file(baseline / rel_str, working / rel_str)
            base_bytes = base_bytes - old_base_size + new_size
            work_bytes = work_bytes - old_work_size + new_size
            refreshed.append(rel_str)
        else:
            if rel_str in work_map or win_long_path(working / rel_str).exists():
                continue
            parent_rel = rel_path.parent
            ancestor_collision = False
            while parent_rel != Path("."):
                if parent_rel.as_posix() in work_map or win_long_path(working / parent_rel).is_file():
                    ancestor_collision = True
                    break
                parent_rel = parent_rel.parent
            if ancestor_collision:
                continue
            if (
                base_count + 1 > _MAX_SNAPSHOT_FILES
                or work_count + 1 > _MAX_SNAPSHOT_FILES
                or base_bytes + new_size > _MAX_SNAPSHOT_BYTES
                or work_bytes + new_size > _MAX_SNAPSHOT_BYTES
            ):
                continue
            atomic_copy_file(src_file, baseline / rel_str)
            atomic_copy_file(baseline / rel_str, working / rel_str)
            base_count += 1
            work_count += 1
            base_bytes += new_size
            work_bytes += new_size
            base_map[rel_str] = rel_path
            work_map[rel_str] = rel_path
            refreshed.append(rel_str)

    return sorted(refreshed)


def snapshot(source: Path, directory: Path) -> Path:
    """Keep immutable baseline and working copy under the orchestrator runtime."""
    source = Path(source)
    directory = Path(directory)
    baseline, working = directory / "base", directory / "work"
    marker = directory / "ready"
    if is_link_or_junction(source):
        raise ContractViolation("scope_violation", "A pasta original contém um link que exige revisão.")
    if is_link_or_junction(directory):
        raise ContractViolation("workspace_invalid", "A cópia isolada desta conversa não é segura.")
    if marker.is_file() and baseline.is_dir() and working.is_dir():
        refresh_clean_from_source(source, directory)
        return working
    if directory.exists():
        raise ContractViolation(
            "workspace_incomplete",
            "A cópia desta conversa ficou incompleta. Abra um novo chat; a pasta original foi preservada.",
        )
    selected, total = [], 0
    for name in files(source):
        selected.append(name)
        total += (source / name).stat().st_size
        if len(selected) > _MAX_SNAPSHOT_FILES or total > _MAX_SNAPSHOT_BYTES:
            raise ContractViolation(
                "folder_too_large",
                "A pasta ultrapassa o limite da cópia para conversa (10 mil arquivos ou 256 MB). Selecione uma pasta menor.",
            )
    baseline.mkdir(parents=True)
    working.mkdir()
    for name in selected:
        for target_root, origin in ((baseline, source), (working, baseline)):
            origin_file = origin / name
            if is_link_or_junction(origin_file):
                raise ContractViolation(
                    "workspace_invalid",
                    "Um link mudou durante a cópia. Abra um novo chat com uma pasta estável.",
                )
            target = target_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin_file, target, follow_symlinks=False)
            if is_link_or_junction(target):
                raise ContractViolation(
                    "workspace_invalid",
                    "Um link mudou durante a cópia. Abra um novo chat com uma pasta estável.",
                )
    marker.write_text("ready", encoding="ascii")
    return working


def diff(baseline: Path, working: Path, *, path: Path | None = None) -> str:
    if is_link_or_junction(baseline):
        raise ContractViolation(
            "scope_violation",
            "A cópia contém um link que exige revisão. Os arquivos foram preservados.",
        )
    assert_no_links_in_tree(working)
    names = set(files(baseline)) | set(files(working)) if path is None else {path}
    if path is not None and (path.is_absolute() or '..' in path.parts or
                             has_link_on_rel_path(baseline, path) or has_link_on_rel_path(working, path)):
        raise ContractViolation('scope_violation', 'O arquivo selecionado está fora da revisão.')
    result = ""
    for name in sorted(names):
        before, after = baseline / name, working / name
        before_exists = before.is_file()
        after_exists = after.is_file()
        if max(before.stat().st_size if before_exists else 0, after.stat().st_size if after_exists else 0) > 100000:
            if not before_exists and after_exists:
                result += f"Arquivo grande adicionado: {name.as_posix()}\n"
            elif before_exists and not after_exists:
                result += f"Arquivo grande removido: {name.as_posix()}\n"
            elif before_exists and after_exists and not filecmp.cmp(before, after, shallow=False):
                result += f"Arquivo grande alterado: {name.as_posix()}\n"
            if len(result) >= 200000:
                break
            continue
        old = before.read_bytes() if before_exists else b""
        new = after.read_bytes() if after_exists else b""
        if old == new and before_exists == after_exists:
            continue
        if not old and not new:
            result += f"Arquivo {'adicionado' if after_exists else 'removido'}: {name.as_posix()}\n"
            if len(result) >= 200000:
                break
            continue
        if b"\0" in old or b"\0" in new:
            if not before_exists and after_exists:
                result += f"Arquivo binário adicionado: {name.as_posix()}\n"
            elif before_exists and not after_exists:
                result += f"Arquivo binário removido: {name.as_posix()}\n"
            else:
                result += f"Arquivo binário alterado: {name.as_posix()}\n"
        else:
            result += "".join(
                difflib.unified_diff(
                    old.decode("utf-8", errors="replace").splitlines(keepends=True),
                    new.decode("utf-8", errors="replace").splitlines(keepends=True),
                    fromfile=f"a/{name.as_posix()}",
                    tofile=f"b/{name.as_posix()}",
                )
            )
        if len(result) >= 200000:
            break
    return redact_text(result)[:200000]


def _validate_folder_sync_roots(source: Path, directory: Path) -> tuple[Path, Path, Path]:
    source = Path(source)
    directory = Path(directory)
    baseline, working, marker = directory / "base", directory / "work", directory / "ready"
    if is_link_or_junction(source):
        raise ContractViolation("scope_violation", "A pasta original contém um link que exige revisão.")
    if not win_long_path(source).is_dir():
        raise ContractViolation("workspace_invalid", "A pasta original do projeto não está disponível.")
    if (
        is_link_or_junction(directory)
        or is_link_or_junction(baseline)
        or is_link_or_junction(working)
        or is_link_or_junction(marker)
        or not win_long_path(marker).is_file()
        or not win_long_path(baseline).is_dir()
        or not win_long_path(working).is_dir()
    ):
        raise ContractViolation("workspace_invalid", "A cópia isolada desta conversa não está disponível.")
    assert_no_links_in_tree(working)
    assert_no_links_in_tree(baseline)
    return source, baseline, working


def inspect_sync_status(source: Path, directory: Path) -> dict:
    """Perform 3-way inspection across `base/`, `work/`, and `source`."""
    source, baseline, working = _validate_folder_sync_roots(source, directory)
    base_map = {p.as_posix(): p for p in files(baseline)}
    work_map = {p.as_posix(): p for p in files(working)}
    source_map = {p.as_posix(): p for p in files(source)}

    agent_added: list[str] = []
    agent_modified: list[str] = []
    agent_deleted: list[str] = []

    for rel_str in sorted(set(base_map) | set(work_map)):
        in_base = rel_str in base_map
        in_work = rel_str in work_map
        if not in_base and in_work:
            agent_added.append(rel_str)
        elif in_base and not in_work:
            agent_deleted.append(rel_str)
        elif not filecmp.cmp(win_long_path(baseline / rel_str), win_long_path(working / rel_str), shallow=False):
            agent_modified.append(rel_str)

    agent_changed_set = set(agent_added) | set(agent_modified) | set(agent_deleted)
    external_changed: list[str] = []
    conflicts_set: set[str] = set()

    for rel_str in sorted(set(base_map) | set(source_map) | agent_changed_set):
        rel_path = Path(rel_str)
        if has_link_on_rel_path(source, rel_path):
            external_changed.append(rel_str)
            if rel_str in agent_changed_set:
                conflicts_set.add(rel_str)
            continue

        in_base = rel_str in base_map
        in_src = rel_str in source_map
        ext_diff = False
        if not in_base and in_src:
            ext_diff = True
        elif in_base and not in_src:
            ext_diff = True
        elif in_base and in_src and not filecmp.cmp(
            win_long_path(baseline / rel_str), win_long_path(source / rel_str), shallow=False
        ):
            ext_diff = True

        if ext_diff:
            external_changed.append(rel_str)

        if rel_str in agent_changed_set:
            if rel_str in work_map:
                src_target = source / rel_path
                if win_long_path(src_target).is_dir():
                    conflicts_set.add(rel_str)
                    continue
                parent_rel = rel_path.parent
                collision = False
                while parent_rel != Path("."):
                    if parent_rel.as_posix() in source_map or win_long_path(source / parent_rel).is_file():
                        collision = True
                        break
                    parent_rel = parent_rel.parent
                if collision:
                    conflicts_set.add(rel_str)
                    continue

            if ext_diff:
                in_work = rel_str in work_map
                if not in_work and not in_src:
                    pass
                elif in_work and in_src and filecmp.cmp(
                    win_long_path(working / rel_str), win_long_path(source / rel_str), shallow=False
                ):
                    pass
                else:
                    conflicts_set.add(rel_str)

    conflicts = sorted(conflicts_set)
    has_agent_changes = bool(agent_added or agent_modified or agent_deleted)
    return {
        "has_agent_changes": has_agent_changes,
        "clean_to_apply": len(conflicts) == 0,
        "agent_added": agent_added,
        "agent_modified": agent_modified,
        "agent_deleted": agent_deleted,
        "external_changed": sorted(set(external_changed)),
        "conflicts": conflicts,
    }


def apply_to_source(source: Path, directory: Path, *, force: bool = False) -> dict:
    """Atomically apply isolated conversation changes from `work/` back to `source` and advance `base/`."""
    source, baseline, working = _validate_folder_sync_roots(source, directory)
    status = inspect_sync_status(source, directory)

    source_resolved = source.resolve()
    all_targets = [*status["agent_added"], *status["agent_modified"], *status["agent_deleted"]]
    for rel_str in all_targets:
        rel_path = validate_sync_rel_path(rel_str)
        if (
            has_link_on_rel_path(source, rel_path)
            or has_link_on_rel_path(working, rel_path)
            or has_link_on_rel_path(baseline, rel_path)
        ):
            raise ContractViolation(
                "scope_violation",
                "O caminho de destino na pasta original contém um link que exige revisão.",
            )
        target = source / rel_path
        if not target.resolve(strict=False).is_relative_to(source_resolved):
            raise ContractViolation(
                "scope_violation",
                "O caminho de destino sai da pasta original do projeto.",
            )

    if status["conflicts"] and not force:
        exc = ContractViolation(
            "workspace_sync_conflict",
            f"Conflito ao aplicar alterações: a pasta original foi modificada externamente em {', '.join(status['conflicts'][:5])}.",
        )
        exc.conflicts = list(status["conflicts"])
        raise exc

    applied_files = sorted(status["agent_added"] + status["agent_modified"])
    deleted_files = list(status["agent_deleted"])

    # Delete removed files before writing new/modified paths to avoid file/directory collisions.
    for rel_str in deleted_files:
        src_target = source / rel_str
        if win_long_path(src_target).is_dir():
            raise ContractViolation(
                "workspace_sync_conflict",
                f"Conflito ao aplicar alterações: '{rel_str}' tornou-se uma pasta no projeto original.",
            )
        win_long_path(src_target).unlink(missing_ok=True)
        prune_empty_parents(src_target, source)
        base_target = baseline / rel_str
        win_long_path(base_target).unlink(missing_ok=True)
        prune_empty_parents(base_target, baseline)

    for rel_str in applied_files:
        src_target = source / rel_str
        if win_long_path(src_target).is_dir():
            raise ContractViolation(
                "workspace_sync_conflict",
                f"Conflito ao aplicar alterações: '{rel_str}' é uma pasta no projeto original.",
            )
        atomic_copy_file(working / rel_str, src_target)
        atomic_copy_file(working / rel_str, baseline / rel_str)

    has_changes = bool(applied_files or deleted_files)
    return {
        "status": "applied" if has_changes else "noop",
        "applied_files": applied_files,
        "deleted_files": deleted_files,
        "conflicts": list(status["conflicts"]),
    }
