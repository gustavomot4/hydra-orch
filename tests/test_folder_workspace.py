from pathlib import Path
from hydra_orch.core import folder_workspace as folder


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
