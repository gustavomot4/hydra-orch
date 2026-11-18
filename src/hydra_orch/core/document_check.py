"""Offline Markdown acceptance: local links and whitespace, without provider calls."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from hydra_orch.bridge.worker_runner import filter_worker_env
from hydra_orch.core.git_workspace import (
    build_hardened_git_prefix,
    ensure_empty_git_hooks_dir,
    is_link_or_junction,
    win_long_path,
)


def _has_link_between(root_resolved: Path, target_path: Path) -> bool:
    try:
        rel_parts = target_path.relative_to(root_resolved).parts
    except ValueError:
        return True
    cursor = root_resolved
    for part in rel_parts:
        cursor = cursor / part
        if is_link_or_junction(cursor):
            return True
    return False


def check(paths: list[str], root: Path) -> list[str]:
    errors = []
    root_resolved = root.resolve()
    for name in paths:
        raw_source = root_resolved / name
        source = raw_source.resolve(strict=False)
        if (
            not source.is_relative_to(root_resolved)
            or _has_link_between(root_resolved, raw_source)
            or not win_long_path(source).is_file()
            or source.suffix.lower() != '.md'
        ):
            errors.append(f'{name}: expected a Markdown file inside the workspace')
            continue
        content = win_long_path(source).read_text(encoding='utf-8')
        content = re.sub(r'```.*?```', '', content, flags=re.S)
        for raw in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)', content):
            target = raw.split('>')[0][1:] if raw.startswith('<') else raw.split()[0]
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            rel_target = unquote(url.path)
            raw_linked = (
                root_resolved / rel_target.lstrip('/')
                if rel_target.startswith('/')
                else source.parent / rel_target
            )
            linked = raw_linked.resolve(strict=False)
            if not linked.is_relative_to(root_resolved):
                errors.append(f'{name}: link outside repository is not allowed: {target}')
                continue
            if not win_long_path(linked).exists():
                errors.append(f'{name}: missing local link {target}')

    hooks_dir = ensure_empty_git_hooks_dir()
    prefix = build_hardened_git_prefix(hooks_dir)
    env = filter_worker_env()
    result = subprocess.run(
        ['git', *prefix, 'diff', '--check', 'HEAD'],
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        errors.append(result.stdout + result.stderr)
    if paths:
        committed = subprocess.run(
            ['git', *prefix, 'show', '--format=', '--check', 'HEAD', '--', *paths],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        if committed.returncode:
            errors.append(committed.stdout + committed.stderr)
    return errors


def main() -> int:
    errors = check(sys.argv[1:], Path.cwd())
    print('\n'.join(errors) if errors else 'Local Markdown links and git diff --check passed.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
