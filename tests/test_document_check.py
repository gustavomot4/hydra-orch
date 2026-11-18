from pathlib import Path
import subprocess

from hydra_orch.core.document_check import check


def test_local_links_and_committed_whitespace_are_checked(tmp_path: Path):
    for args in [('init',), ('config', 'user.name', 'Hydra Test'), ('config', 'user.email', 'test@hydra.local')]:
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path/'guide.md').write_text('# Guide\n', encoding='utf-8')
    readme = tmp_path/'README.md'
    readme.write_text('[Guide](guide.md#anchor)\n[Web](https://example.invalid/)\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'README.md', 'guide.md'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-m', 'fixture'], cwd=tmp_path, check=True, capture_output=True)
    assert not check(['README.md'], tmp_path)
    readme.write_text('[Missing](missing.md)  \n', encoding='utf-8')
    subprocess.run(['git', 'add', 'README.md'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-m', 'broken links and whitespace'], cwd=tmp_path, check=True, capture_output=True)
    errors = check(['README.md'], tmp_path)
    assert any('missing.md' in e for e in errors)
    assert any('trailing whitespace' in e for e in errors)
