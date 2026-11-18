"""Offline Markdown acceptance: local links and whitespace, without provider calls."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def check(paths: list[str], root: Path) -> list[str]:
    errors = []
    for name in paths:
        source = (root / name).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file() or source.suffix.lower() != '.md':
            errors.append(f'{name}: expected a Markdown file inside the workspace')
            continue
        content = source.read_text(encoding='utf-8')
        content = re.sub(r'```.*?```', '', content, flags=re.S)
        for raw in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)', content):
            target = raw.split('>')[0][1:] if raw.startswith('<') else raw.split()[0]
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            linked = root / unquote(url.path.lstrip('/')) if url.path.startswith('/') else source.parent / unquote(url.path)
            if not linked.exists():
                errors.append(f'{name}: missing local link {target}')
    result = subprocess.run(['git', 'diff', '--check', 'HEAD'], cwd=root, capture_output=True, text=True)
    if result.returncode:
        errors.append(result.stdout + result.stderr)
    committed = subprocess.run(['git', 'show', '--format=', '--check', 'HEAD', '--', *paths], cwd=root, capture_output=True, text=True)
    if committed.returncode:
        errors.append(committed.stdout + committed.stderr)
    return errors


def main() -> int:
    errors = check(sys.argv[1:], Path.cwd())
    print('\n'.join(errors) if errors else 'Local Markdown links and git diff --check passed.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
