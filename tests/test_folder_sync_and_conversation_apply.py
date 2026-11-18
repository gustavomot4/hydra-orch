"""Tests for FolderWorkspace 3-way sync, DAY-15 diff labels, DAY-20 messages, and ConversationService.apply_changes."""
from __future__ import annotations

import asyncio
from pathlib import Path
import os
import shutil
import subprocess

import pytest
from pydantic import ValidationError

from hydra_orch.core import folder_workspace as folder
from hydra_orch.core.attachments import AttachmentService
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.conversation_coordinator import CoordinatorPlan
from hydra_orch.core.conversation_service import ConversationService
from hydra_orch.core.git_workspace import is_link_or_junction
from hydra_orch.core.run_service import RunService
from hydra_orch.model import ContractViolation


def _make_dir_junction_or_symlink(link_path: Path, target_dir: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        link_path.symlink_to(target_dir, target_is_directory=True)
    assert is_link_or_junction(link_path)


def _remove_dir_junction_or_symlink(link_path: Path) -> None:
    if not is_link_or_junction(link_path):
        return
    if os.name == "nt":
        os.rmdir(link_path)
    else:
        link_path.unlink()


class ScriptedConversationRunner:
    def __init__(self):
        self.step = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def capabilities(self):
        return [{"id": "codex", "name": "Codex", "available": True}]

    async def run(self, turn, conv, prompt, cwd, emit):
        await emit("session.started", {"session_id": "sync-test-session"})
        self.started.set()
        await self.release.wait()
        if self.step is not None:
            await self.step(turn, conv, prompt, cwd, emit)
        await emit("text.delta", {"text": "Concluído."})

    async def cancel(self, tid):
        self.release.set()


@pytest.fixture
def sync_service(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ("init", "-b", "main"),
        ("config", "user.email", "test@hydra.local"),
        ("config", "user.name", "Hydra Test"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Projeto Inicial\nLinha 1\n", encoding="utf-8")
    (repo / "obsolete.txt").write_text("Remover depois\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".orchestrator/\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md", "obsolete.txt", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    runs = RunService(repo, store=ExecutionStore(tmp_path / "state.sqlite"), runtime_dir=tmp_path / "runtime")
    runner = ScriptedConversationRunner()
    return ConversationService(runs, runner=runner, attachments=AttachmentService(tmp_path / "attachments"))


async def _wait_turn(service: ConversationService, cid: str, state: str = "completed", ordinal: int = 1) -> dict:
    for _ in range(120):
        snap = await service.snapshot(cid)
        if len(snap["turns"]) >= ordinal and snap["turns"][ordinal - 1]["state"] == state:
            return snap
        await asyncio.sleep(0.05)
    raise AssertionError(await service.snapshot(cid))


# ============================================================================
# DAY-15: Binary & Large File Diff Labels
# ============================================================================


def test_day15_large_file_added_modified_deleted_diff_labels(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "modify_large.txt").write_bytes(b"A" * 105_000)
    (source / "remove_large.txt").write_bytes(b"R" * 105_000)
    (source / "same_large.txt").write_bytes(b"S" * 105_000)

    directory = tmp_path / "snap"
    work = folder.snapshot(source, directory)

    (work / "added_large.txt").write_bytes(b"N" * 105_000)
    (work / "modify_large.txt").write_bytes(b"B" * 105_000)
    (work / "remove_large.txt").unlink()

    output = folder.diff(directory / "base", work)
    assert "Arquivo grande adicionado: added_large.txt\n" in output
    assert "Arquivo grande alterado: modify_large.txt\n" in output
    assert "Arquivo grande removido: remove_large.txt\n" in output
    assert "same_large.txt" not in output


def test_day15_binary_file_added_modified_deleted_diff_labels(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "modify.bin").write_bytes(b"\x89PNG\x00old")
    (source / "remove.bin").write_bytes(b"\x00\x01\x02\x03")
    (source / "same.bin").write_bytes(b"\x00unchanged")

    directory = tmp_path / "snap"
    work = folder.snapshot(source, directory)

    (work / "added.bin").write_bytes(b"\x00\xffnew")
    (work / "modify.bin").write_bytes(b"\x89PNG\x00new")
    (work / "remove.bin").unlink()

    output = folder.diff(directory / "base", work)
    assert "Arquivo binário adicionado: added.bin\n" in output
    assert "Arquivo binário alterado: modify.bin\n" in output
    assert "Arquivo binário removido: remove.bin\n" in output
    assert "same.bin" not in output


# ============================================================================
# DAY-02: FolderWorkspace 3-Way Inspection, Refresh, Clean Apply & Conflicts
# ============================================================================


def test_folder_workspace_3way_clean_apply_and_idempotent_noop(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("Original\n", encoding="utf-8")
    (source / "nested" / "deep").mkdir(parents=True)
    (source / "nested" / "deep" / "legacy.txt").write_text("Legacy\n", encoding="utf-8")
    (source / ".env").write_text("SECRET=keep", encoding="utf-8")

    directory = tmp_path / "snap"
    work = folder.snapshot(source, directory)

    (work / "README.md").write_text("Atualizado pelo agente\n", encoding="utf-8")
    (work / "src").mkdir()
    (work / "src" / "app.py").write_text("VALUE = 42\n", encoding="utf-8")
    (work / "nested" / "deep" / "legacy.txt").unlink()

    status = folder.inspect_sync_status(source, directory)
    assert status == {
        "has_agent_changes": True,
        "clean_to_apply": True,
        "agent_added": ["src/app.py"],
        "agent_modified": ["README.md"],
        "agent_deleted": ["nested/deep/legacy.txt"],
        "external_changed": [],
        "conflicts": [],
    }

    applied = folder.apply_to_source(source, directory)
    assert applied == {
        "status": "applied",
        "applied_files": ["README.md", "src/app.py"],
        "deleted_files": ["nested/deep/legacy.txt"],
        "conflicts": [],
    }
    assert (source / "README.md").read_text(encoding="utf-8") == "Atualizado pelo agente\n"
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 42\n"
    assert not (source / "nested").exists()
    assert source.is_dir()
    assert (source / ".env").read_text(encoding="utf-8") == "SECRET=keep"

    second = folder.apply_to_source(source, directory)
    assert second == {
        "status": "noop",
        "applied_files": [],
        "deleted_files": [],
        "conflicts": [],
    }


def test_folder_workspace_external_non_overlapping_edit_preserved_and_refreshed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "agent_file.py").write_text("x = 1\n", encoding="utf-8")
    (source / "user_file.md").write_text("Nota inicial\n", encoding="utf-8")
    (source / "to_remove_externally.txt").write_text("Temp\n", encoding="utf-8")

    directory = tmp_path / "snap"
    work = folder.snapshot(source, directory)

    # Agent modifies only agent_file.py
    (work / "agent_file.py").write_text("x = 2\n", encoding="utf-8")

    # User edits user_file.md, adds user_added.txt, deletes to_remove_externally.txt, and adds .env.local
    (source / "user_file.md").write_text("Nota do usuário\n", encoding="utf-8")
    (source / "user_added.txt").write_text("Criado fora do chat\n", encoding="utf-8")
    (source / "to_remove_externally.txt").unlink()
    (source / ".env.local").write_text("TOKEN=hidden\n", encoding="utf-8")

    status = folder.inspect_sync_status(source, directory)
    assert status["has_agent_changes"] is True
    assert status["clean_to_apply"] is True
    assert status["conflicts"] == []
    assert status["external_changed"] == [
        "to_remove_externally.txt",
        "user_added.txt",
        "user_file.md",
    ]

    applied = folder.apply_to_source(source, directory)
    assert applied["status"] == "applied"
    assert applied["applied_files"] == ["agent_file.py"]
    assert (source / "agent_file.py").read_text(encoding="utf-8") == "x = 2\n"
    assert (source / "user_file.md").read_text(encoding="utf-8") == "Nota do usuário\n"
    assert (source / "user_added.txt").read_text(encoding="utf-8") == "Criado fora do chat\n"

    # Next turn calls snapshot() -> refreshes untouched external edits into base/ and work/
    (work / "agent_turn2.py").write_text("y = 3\n", encoding="utf-8")
    refreshed_work = folder.snapshot(source, directory)
    assert refreshed_work == work
    assert (work / "user_file.md").read_text(encoding="utf-8") == "Nota do usuário\n"
    assert (work / "user_added.txt").read_text(encoding="utf-8") == "Criado fora do chat\n"
    assert not (work / "to_remove_externally.txt").exists()
    assert not (work / ".env.local").exists()
    # Agent work in progress was not lost, and refreshed user edits do not pollute agent diff
    assert (work / "agent_turn2.py").read_text(encoding="utf-8") == "y = 3\n"
    turn_diff = folder.diff(directory / "base", work)
    assert "agent_turn2.py" in turn_diff
    assert "user_file.md" not in turn_diff
    assert "user_added.txt" not in turn_diff


def test_folder_workspace_convergent_edit_and_conflict_override(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "convergent.txt").write_text("base\n", encoding="utf-8")
    (source / "both_deleted.txt").write_text("bye\n", encoding="utf-8")
    (source / "conflicted.txt").write_text("base\n", encoding="utf-8")

    directory = tmp_path / "snap"
    work = folder.snapshot(source, directory)

    # Convergent modifications & deletions
    (work / "convergent.txt").write_text("same-content\n", encoding="utf-8")
    (source / "convergent.txt").write_text("same-content\n", encoding="utf-8")
    (work / "both_deleted.txt").unlink()
    (source / "both_deleted.txt").unlink()

    # Divergent edit -> real conflict
    (work / "conflicted.txt").write_text("agent-version\n", encoding="utf-8")
    (source / "conflicted.txt").write_text("user-version\n", encoding="utf-8")

    status = folder.inspect_sync_status(source, directory)
    assert status["clean_to_apply"] is False
    assert status["conflicts"] == ["conflicted.txt"]

    with pytest.raises(ContractViolation) as exc_info:
        folder.apply_to_source(source, directory, force=False)
    assert exc_info.value.code == "workspace_sync_conflict"
    assert "conflicted.txt" in str(exc_info.value)
    assert getattr(exc_info.value, "conflicts", None) == ["conflicted.txt"]
    assert (source / "conflicted.txt").read_text(encoding="utf-8") == "user-version\n"

    forced = folder.apply_to_source(source, directory, force=True)
    assert forced["status"] == "applied"
    assert forced["conflicts"] == ["conflicted.txt"]
    assert (source / "conflicted.txt").read_text(encoding="utf-8") == "agent-version\n"
    assert folder.apply_to_source(source, directory)["status"] == "noop"


def test_folder_workspace_rejects_ntfs_junctions_and_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("DO_NOT_TOUCH\n", encoding="utf-8")

    source = tmp_path / "source"
    source.mkdir()
    (source / "sub").mkdir()
    (source / "sub" / "item.txt").write_text("v1\n", encoding="utf-8")

    directory = tmp_path / "snap"
    work = folder.snapshot(source, directory)

    # 1. Junction inside work/ must be rejected by diff, inspect_sync_status, prepare_git, and apply_to_source
    work_link = work / "junction_escape"
    _make_dir_junction_or_symlink(work_link, outside)
    try:
        for fn in (
            lambda: folder.diff(directory / "base", work),
            lambda: folder.inspect_sync_status(source, directory),
            lambda: folder.prepare_git(directory),
            lambda: folder.apply_to_source(source, directory, force=True),
        ):
            with pytest.raises(ContractViolation) as exc_info:
                fn()
            assert exc_info.value.code == "scope_violation"
    finally:
        _remove_dir_junction_or_symlink(work_link)

    # 2. Junction at target parent inside source must be rejected even with force=True
    (work / "sub" / "item.txt").write_text("agent-update\n", encoding="utf-8")
    shutil.rmtree(source / "sub")
    _make_dir_junction_or_symlink(source / "sub", outside)
    try:
        status = folder.inspect_sync_status(source, directory)
        assert "sub/item.txt" in status["conflicts"]
        with pytest.raises(ContractViolation) as exc_info:
            folder.apply_to_source(source, directory, force=True)
        assert exc_info.value.code == "scope_violation"
        assert (outside / "secret.txt").read_text(encoding="utf-8") == "DO_NOT_TOUCH\n"
        assert not (outside / "item.txt").exists()
    finally:
        _remove_dir_junction_or_symlink(source / "sub")


# ============================================================================
# DAY-02: ConversationService.inspect_changes & apply_changes (Folder + Git)
# ============================================================================


@pytest.mark.asyncio
async def test_conversation_service_apply_changes_plain_folder_and_event(sync_service, tmp_path):
    plain = tmp_path / "plain_project"
    plain.mkdir()
    (plain / "README.md").write_text("Versão 0\n", encoding="utf-8")
    (plain / "old.txt").write_text("Remover\n", encoding="utf-8")

    project = await sync_service.runs.create_project(plain, "Projeto Pasta", allow_plain_folder=True)

    async def step(turn, conv, prompt, cwd, emit):
        (cwd / "README.md").write_text("Versão 1\n", encoding="utf-8")
        (cwd / "novo.py").write_text("OK = True\n", encoding="utf-8")
        (cwd / "old.txt").unlink()

    sync_service.runner.step = step
    created = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Atualize a pasta",
        access_mode="workspace-write",
        idempotency_key="folder-apply-create-0001",
    )
    cid = created["conversation_id"]
    await sync_service.start()
    try:
        await _wait_turn(sync_service, cid, "completed")
        inspection = await sync_service.inspect_changes(cid)
        assert inspection == {
            "mode": "folder",
            "has_agent_changes": True,
            "clean_to_apply": True,
            "agent_added": ["novo.py"],
            "agent_modified": ["README.md"],
            "agent_deleted": ["old.txt"],
            "external_changed": [],
            "conflicts": [],
        }

        result = await sync_service.apply_changes(cid)
        assert result["mode"] == "folder"
        assert result["status"] == "applied"
        assert result["applied_files"] == ["README.md", "novo.py"]
        assert result["deleted_files"] == ["old.txt"]
        assert (plain / "README.md").read_text(encoding="utf-8") == "Versão 1\n"
        assert (plain / "novo.py").read_text(encoding="utf-8") == "OK = True\n"
        assert not (plain / "old.txt").exists()

        events = await sync_service.events(cid)
        applied_events = [e for e in events if e["type"] == "conversation.applied"]
        assert len(applied_events) == 1
        assert applied_events[0]["seq"] == result["seq"]
        assert applied_events[0]["payload"] == {
            "mode": "folder",
            "status": "applied",
            "applied_files": ["README.md", "novo.py"],
            "deleted_files": ["old.txt"],
        }
        assert (await sync_service.snapshot(cid))["last_seq"] == result["seq"]

        second = await sync_service.apply_changes(cid)
        assert second["status"] == "noop"
        assert second["applied_files"] == []
        assert second["deleted_files"] == []
    finally:
        await sync_service.close()


@pytest.mark.asyncio
async def test_conversation_service_apply_changes_git_worktree_uncommitted_committed_and_conflict(sync_service):
    repo = sync_service.runs.repo_root
    project = await sync_service.runs.create_project(repo, "Projeto Git")

    async def turn1_step(turn, conv, prompt, cwd, emit):
        (cwd / "README.md").write_text("# Projeto Atualizado\n", encoding="utf-8")
        (cwd / "src").mkdir(exist_ok=True)
        (cwd / "src" / "feature.py").write_text("FEATURE = 1\n", encoding="utf-8")
        (cwd / "obsolete.txt").unlink()
        (cwd / ".env.secret").write_text("API_KEY=never_sync\n", encoding="utf-8")
        (cwd / ".orchestrator" / "chat_context").mkdir(parents=True, exist_ok=True)
        (cwd / ".orchestrator" / "chat_context" / "ctx.txt").write_text("internal\n", encoding="utf-8")

    sync_service.runner.step = turn1_step
    created = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Implemente feature",
        access_mode="workspace-write",
        idempotency_key="git-apply-create-0001",
    )
    cid = created["conversation_id"]
    await sync_service.start()
    try:
        await _wait_turn(sync_service, cid, "completed", 1)

        inspection = await sync_service.inspect_changes(cid)
        assert inspection == {
            "mode": "git",
            "has_agent_changes": True,
            "clean_to_apply": True,
            "agent_added": ["src/feature.py"],
            "agent_modified": ["README.md"],
            "agent_deleted": ["obsolete.txt"],
            "external_changed": [],
            "conflicts": [],
        }

        # Conflicting external edit in repo_root blocks apply unless force=True
        (repo / "README.md").write_text("# Edição externa concorrente\n", encoding="utf-8")
        conflict_check = await sync_service.inspect_changes(cid)
        assert conflict_check["clean_to_apply"] is False
        assert conflict_check["conflicts"] == ["README.md"]

        with pytest.raises(ContractViolation) as exc_info:
            await sync_service.apply_changes(cid, force=False)
        assert exc_info.value.code == "workspace_sync_conflict"
        assert (repo / "README.md").read_text(encoding="utf-8") == "# Edição externa concorrente\n"

        applied = await sync_service.apply_changes(cid, force=True)
        assert applied["mode"] == "git"
        assert applied["status"] == "applied"
        assert applied["applied_files"] == ["README.md", "src/feature.py"]
        assert applied["deleted_files"] == ["obsolete.txt"]
        assert (repo / "README.md").read_text(encoding="utf-8") == "# Projeto Atualizado\n"
        assert (repo / "src" / "feature.py").read_text(encoding="utf-8") == "FEATURE = 1\n"
        assert not (repo / "obsolete.txt").exists()
        assert not (repo / ".env.secret").exists()

        # Idempotent re-apply returns noop even with uncommitted applied changes in repo_root
        noop_res = await sync_service.apply_changes(cid)
        assert noop_res["status"] == "noop"
        assert noop_res["applied_files"] == []
        assert noop_res["deleted_files"] == []

        # Turn 2: committed changes inside the isolated conversation worktree
        async def turn2_step(turn, conv, prompt, cwd, emit):
            (cwd / "committed_mod.py").write_text("COMMITTED = True\n", encoding="utf-8")
            subprocess.run(["git", "add", "committed_mod.py"], cwd=cwd, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Hydra", "-c", "user.email=hydra@localhost", "commit", "-m", "feat: mod"],
                cwd=cwd,
                check=True,
                capture_output=True,
            )

        sync_service.runner.step = turn2_step
        snap = await sync_service.snapshot(cid)
        await sync_service.send(
            cid,
            content="Segunda etapa",
            idempotency_key="git-apply-turn2-0002",
            expected_last_seq=snap["last_seq"],
        )
        await _wait_turn(sync_service, cid, "completed", 2)

        applied2 = await sync_service.apply_changes(cid)
        assert applied2["status"] == "applied"
        assert applied2["applied_files"] == ["committed_mod.py"]
        assert (repo / "committed_mod.py").read_text(encoding="utf-8") == "COMMITTED = True\n"
        assert (await sync_service.apply_changes(cid))["status"] == "noop"

        events = [e for e in await sync_service.events(cid) if e["type"] == "conversation.applied"]
        assert [e["payload"]["status"] for e in events] == ["applied", "noop", "applied", "noop"]
    finally:
        await sync_service.close()


@pytest.mark.asyncio
async def test_conversation_service_guards_not_found_readonly_and_busy(sync_service):
    with pytest.raises(ContractViolation) as missing_exc:
        await sync_service.apply_changes("conversation-does-not-exist")
    assert missing_exc.value.code == "resource_not_found"

    project = await sync_service.runs.create_project(sync_service.runs.repo_root, "Guards")

    # Read-only conversation rejected
    ro = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Somente leitura",
        access_mode="read-only",
        idempotency_key="guard-readonly-0001",
    )
    with pytest.raises(ContractViolation) as ro_exc:
        await sync_service.apply_changes(ro["conversation_id"])
    assert ro_exc.value.code == "workspace_readonly"

    # Workspace-write conversation before workspace provisioning rejected with workspace_readonly
    unstarted = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Ainda na fila",
        access_mode="workspace-write",
        idempotency_key="guard-unstarted-0002",
    )
    with pytest.raises(ContractViolation) as unstarted_exc:
        await sync_service.inspect_changes(unstarted["conversation_id"])
    assert unstarted_exc.value.code == "workspace_readonly"

    # Cancel queued turns so consumer runs our controlled busy conversation next
    snap_ro = await sync_service.snapshot(ro["conversation_id"])
    await sync_service.cancel(ro["conversation_id"], snap_ro["turns"][0]["id"])
    snap_un = await sync_service.snapshot(unstarted["conversation_id"])
    await sync_service.cancel(unstarted["conversation_id"], snap_un["turns"][0]["id"])

    # Active running turn rejected with conversation_busy
    sync_service.runner.started.clear()
    sync_service.runner.release.clear()
    busy_conv = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Turno em andamento",
        access_mode="workspace-write",
        idempotency_key="guard-busy-turn-0003",
    )
    await sync_service.start()
    try:
        await asyncio.wait_for(sync_service.runner.started.wait(), 5)
        with pytest.raises(ContractViolation) as busy_exc:
            await sync_service.apply_changes(busy_conv["conversation_id"])
        assert busy_exc.value.code == "conversation_busy"
        sync_service.runner.release.set()
        await _wait_turn(sync_service, busy_conv["conversation_id"], "completed")
    finally:
        sync_service.runner.release.set()
        await sync_service.close()


def test_day20_coordinator_plan_validation_messages_are_portuguese():
    with pytest.raises(ValidationError) as dup_exc:
        CoordinatorPlan.model_validate(
            {
                "objective": "Plano inválido",
                "tasks": [
                    {
                        "id": "a",
                        "title": "Tarefa A",
                        "objective": "Implementar módulo A",
                        "paths": ["a.py", "a.py"],
                        "check_kind": "python_compile",
                        "check_paths": ["a.py"],
                    }
                ],
            }
        )
    assert "Caminhos duplicados" in str(dup_exc.value)


@pytest.mark.asyncio
async def test_conversation_service_git_rejects_junction_and_accepts_convergent_edit(sync_service, tmp_path):
    outside = tmp_path / "outside_git"
    outside.mkdir()
    (outside / "secret.txt").write_text("KEEP_SAFE\n", encoding="utf-8")

    repo = sync_service.runs.repo_root
    project = await sync_service.runs.create_project(repo, "Git Junction & Convergent")

    async def step(turn, conv, prompt, cwd, emit):
        (cwd / "converged.py").write_text("X = 10\n", encoding="utf-8")
        (cwd / "sub").mkdir(exist_ok=True)
        (cwd / "sub" / "mod.py").write_text("Y = 20\n", encoding="utf-8")

    sync_service.runner.step = step
    created = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Mudanças convergentes",
        access_mode="workspace-write",
        idempotency_key="git-junction-convergent-0001",
    )
    cid = created["conversation_id"]
    await sync_service.start()
    try:
        await _wait_turn(sync_service, cid, "completed")
        # Convergent external creation of converged.py
        (repo / "converged.py").write_text("X = 10\n", encoding="utf-8")
        inspection = await sync_service.inspect_changes(cid)
        assert inspection["clean_to_apply"] is True
        assert inspection["conflicts"] == []

        # Junction at repo/sub must reject apply even with force=True
        _make_dir_junction_or_symlink(repo / "sub", outside)
        try:
            with pytest.raises(ContractViolation) as exc_info:
                await sync_service.apply_changes(cid, force=True)
            assert exc_info.value.code == "scope_violation"
            assert not (outside / "mod.py").exists()
        finally:
            _remove_dir_junction_or_symlink(repo / "sub")

        applied = await sync_service.apply_changes(cid)
        assert applied["status"] == "applied"
        assert (repo / "sub" / "mod.py").read_text(encoding="utf-8") == "Y = 20\n"
    finally:
        await sync_service.close()


@pytest.mark.asyncio
async def test_plain_folder_after_private_git_prepare_applies_without_leaking_git(sync_service, tmp_path):
    plain = tmp_path / "plain_with_private_git"
    plain.mkdir()
    (plain / "README.md").write_text("Inicial\n", encoding="utf-8")
    project = await sync_service.runs.create_project(plain, "Pasta com Git privado", allow_plain_folder=True)

    async def step(turn, conv, prompt, cwd, emit):
        folder.prepare_git(cwd.parent)
        (cwd / "README.md").write_text("Coordenado\n", encoding="utf-8")
        (cwd / "module.py").write_text("READY = 1\n", encoding="utf-8")

    sync_service.runner.step = step
    created = await sync_service.create(
        project_id=project["id"],
        executor="codex",
        content="Coordenar pasta comum",
        access_mode="workspace-write",
        idempotency_key="plain-private-git-apply-0001",
    )
    cid = created["conversation_id"]
    await sync_service.start()
    try:
        await _wait_turn(sync_service, cid, "completed")
        applied = await sync_service.apply_changes(cid)
        assert applied["mode"] == "folder"
        assert applied["status"] == "applied"
        assert applied["applied_files"] == ["README.md", "module.py"]
        assert (plain / "README.md").read_text(encoding="utf-8") == "Coordenado\n"
        assert (plain / "module.py").read_text(encoding="utf-8") == "READY = 1\n"
        assert not (plain / ".git").exists()
    finally:
        await sync_service.close()

