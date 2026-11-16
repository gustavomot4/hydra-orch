from pathlib import Path
import os
import subprocess
import pytest
from hydra_orch.core import folder_workspace as folder
from hydra_orch.model import ContractViolation


def git(cwd, *args):
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    return subprocess.run(['git',*args],cwd=cwd,env=env,check=True,capture_output=True,text=True).stdout.strip()


def test_snapshot_uses_one_baseline_even_if_original_changes_during_copy(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("Original\n")
    copy = folder.shutil.copyfile
    changed = False
    def concurrent_edit(origin, target, **kwargs):
        nonlocal changed
        result = copy(origin, target, **kwargs)
        if not changed:
            changed = True
            (source / "note.txt").write_text("Edição concorrente\n")
        return result
    monkeypatch.setattr(folder.shutil, "copyfile", concurrent_edit)
    work = folder.snapshot(source, tmp_path / "snapshot")
    assert (work / "note.txt").read_text() == "Original\n"
    assert folder.diff(work.parent / "base", work) == ""
    assert not (source / ".git").exists()


def test_diff_handles_empty_new_files_deletion_and_ignored_secrets(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "delete.txt").write_text("Apagar\n")
    (source / ".env.local").write_text("SENSITIVE=example")
    (source / "node_modules").mkdir()
    (source / "node_modules" / "dependency.txt").write_text("Dependency")
    work = folder.snapshot(source, tmp_path / "snapshot")
    assert not (work / ".env.local").exists()
    assert not (work / "node_modules").exists()
    (work / "empty.txt").touch()
    (work / "delete.txt").unlink()
    result = folder.diff(work.parent / "base", work)
    assert "empty.txt" in result and "adicionado" in result
    assert "delete.txt" in result and "-Apagar" in result
    assert (source / "delete.txt").read_text() == "Apagar\n"


@pytest.mark.parametrize('empty', [False, True])
def test_private_git_prepares_empty_or_populated_copy_inside_another_repo(tmp_path, empty, monkeypatch):
    outer = tmp_path/'outer'
    outer.mkdir()
    git(outer,'init','-b','main')
    git(outer,'-c','user.name=Test','-c','user.email=test@localhost','commit','--allow-empty','-m','outer')
    head = git(outer,'rev-parse','HEAD')
    source = tmp_path/'source'
    source.mkdir()
    if not empty:
        (source/'README.md').write_text('Original\n')
    directory = outer/'.orchestrator'/'folder_workspace'/'chat'
    work = folder.snapshot(source,directory)
    (work/'.env.local').write_text('PRIVATE=do-not-track')
    # A launcher/environment pointing at another Git repository must not be used.
    monkeypatch.setenv('GIT_DIR',str(outer/'.git'))
    base = folder.prepare_git(directory)
    assert len(base)==40
    assert (work/'.git').is_file()
    assert Path(git(work,'rev-parse','--show-toplevel')).resolve()==work.resolve()
    assert Path(git(work,'rev-parse','--absolute-git-dir')).resolve()==(directory/'repository.git').resolve()
    assert git(outer,'rev-parse','HEAD')==head
    assert git(work,'remote')==''
    assert '.env.local' not in git(work,'ls-files')
    assert '.orchestrator' not in git(work,'ls-files')
    assert not (source/'.git').exists()
    (work/'local.txt').write_text('Keep uncommitted edits')
    assert folder.prepare_git(directory)==base
    assert (work/'local.txt').read_text()=='Keep uncommitted edits'
    assert 'local.txt' not in git(work,'ls-files')


def test_private_git_rejects_foreign_pointer_without_touching_it(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    directory = tmp_path/'copy'
    work = folder.snapshot(source,directory)
    (work/'.git').write_text('gitdir: /foreign/repository\n')
    with pytest.raises(ContractViolation,match='Git da cópia'):
        folder.prepare_git(directory)
    assert (work/'.git').read_text()=='gitdir: /foreign/repository\n'
    assert not (directory/'repository.git').exists()


def test_private_git_recovers_failed_initial_commit_without_losing_files(tmp_path, monkeypatch):
    source = tmp_path/'source'
    source.mkdir()
    directory = tmp_path/'copy'
    work = folder.snapshot(source,directory)
    original = folder.subprocess.run
    def fail_commit(args,**kwargs):
        if 'commit' in args:
            return subprocess.CompletedProcess(args,1,'','controlled failure')
        return original(args,**kwargs)
    monkeypatch.setattr(folder.subprocess,'run',fail_commit)
    with pytest.raises(ContractViolation,match='preparar a cópia'):
        folder.prepare_git(directory)
    (work/'keep.md').write_text('Preserved after interruption')
    monkeypatch.setattr(folder.subprocess,'run',original)
    folder.prepare_git(directory)
    assert git(work,'show','HEAD:keep.md')=='Preserved after interruption'


def test_private_git_storage_cannot_be_reused_for_another_conversation(tmp_path):
    source=tmp_path/'source'
    source.mkdir()
    first=tmp_path/'first'
    second=tmp_path/'second'
    repository=tmp_path/'short-metadata'/'repo.git'
    work=folder.snapshot(source,first)
    folder.snapshot(source,second)
    head=folder.prepare_git(first,repository)
    with pytest.raises(ContractViolation,match='outra cópia'):
        folder.prepare_git(second,repository)
    assert git(work,'rev-parse','HEAD')==head
    assert not (second/'work'/'.git').exists()
