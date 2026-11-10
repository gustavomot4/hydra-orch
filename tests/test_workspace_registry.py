"""T11 hierarchy, explicit grants, scope fences and restart tests."""

import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError, StorageIntegrityError
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.model import ContractViolation
from test_server import _init_temp_git_repo

pytestmark = pytest.mark.security


@pytest_asyncio.fixture
async def registry(tmp_path):
    repo, sha = _init_temp_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "registry.sqlite")
    registry = WorkspaceRegistry(store, allowed_roots=[tmp_path])
    area = await registry.create_area("Area", principal_id="alice")
    workspace = await registry.create_workspace(area["id"], "Workspace", principal_id="alice")
    project = await registry.create_project(workspace["id"], "Project", repo, principal_id="alice",
        metadata={"api_key": "do-not-store"})
    return registry, repo, sha, area, workspace, project


async def register(registry, repo, project, *, scopes=("read", "write", "execute")):
    return await registry.register_repository(project["id"], repo, principal_id="alice",
        authorized_principal_id="alice", scopes=scopes, allowed_paths=["src/**"])


@pytest.mark.asyncio
async def test_hierarchy_restart_pinned_sha_and_atomic_audit(registry):
    service, repo, sha, area, workspace, project = registry
    assert uuid.UUID(area["id"]).version == 7
    registered = await register(service, repo, project)
    restarted = WorkspaceRegistry(ExecutionStore(service.store.db_path), allowed_roots=[repo.parent])
    assert (await restarted.list_areas(principal_id="alice"))[0]["id"] == area["id"]
    assert (await restarted.list_workspaces(area["id"], principal_id="alice"))[0]["id"] == workspace["id"]
    assert (await restarted.list_projects(workspace["id"], principal_id="alice"))[0]["id"] == project["id"]
    assert (await restarted.list_repositories(project["id"], principal_id="alice"))[0]["base_sha"] == sha
    assert await restarted.resolve_canonical_root(project["id"], principal_id="alice") == str(repo.resolve())
    assert await restarted.resolve_path(registered["id"], "src/new.py", principal_id="alice", scope="write") == repo / "src/new.py"
    assert "do-not-store" not in project["metadata_json"]
    async with service.store._connect() as db:
        commands = await (await db.execute("SELECT response_json FROM commands WHERE scope='registry'")).fetchall()
        assert len(commands) == 4
        assert "repository.registered" in {json.loads(c[0])["event"] for c in commands}


@pytest.mark.asyncio
async def test_no_ownership_or_secondary_repo_permission_inheritance(registry, tmp_path):
    service, repo, _, area, workspace, project = registry
    assert await service.list_areas(principal_id="bob") == []
    with pytest.raises(ContractViolation, match="not owned"):
        await service.create_workspace(area["id"], "stolen", principal_id="bob")
    with pytest.raises(ContractViolation):
        await service.list_projects(workspace["id"], principal_id="bob")
    with pytest.raises(ContractViolation):
        await service.resolve_canonical_root(project["id"], principal_id="alice")
    primary = await register(service, repo, project)
    other_dir = tmp_path / "secondary"
    other_dir.mkdir()
    secondary, _ = _init_temp_git_repo(other_dir)
    second = await service.register_repository(project["id"], secondary, principal_id="alice",
        authorized_principal_id="bob", scopes=["read"], allowed_paths=["src/**"])
    assert await service.get_authorization(primary["id"], principal_id="bob") is None
    assert await service.get_authorization(second["id"], principal_id="alice") is None
    with pytest.raises(ContractViolation, match="current grant"):
        await service.resolve_repository(second["id"], principal_id="alice")
    assert (await service.resolve_repository(second["id"], principal_id="bob"))["root_canonical"] == str(secondary)
    with pytest.raises(ContractViolation):
        await service.resolve_canonical_root(project["id"], repository_id=primary["id"], principal_id="bob")


@pytest.mark.asyncio
async def test_grant_scope_revocation_and_archive(registry):
    service, repo, _, _, workspace, project = registry
    registered = await register(service, repo, project, scopes=["read"])
    with pytest.raises(ContractViolation):
        await service.resolve_repository(registered["id"], principal_id="alice", scope="execute")
    grant = await service.grant_repository(registered["id"], principal_id="alice",
        authorized_principal_id="bob", scopes=["read"])
    assert await service.get_authorization(registered["id"], principal_id="bob") is not None
    with pytest.raises(ContractViolation):
        await service.revoke_authorization(grant, principal_id="bob")
    await service.revoke_authorization(grant, principal_id="alice")
    await service.revoke_authorization(grant, principal_id="alice")
    assert await service.get_authorization(registered["id"], principal_id="bob") is None
    with pytest.raises(OptimisticLockError):
        await service.archive_workspace(workspace["id"], principal_id="alice", expected_revision=10)
    await service.archive_workspace(workspace["id"], principal_id="alice", expected_revision=1)
    assert (await service.list_workspaces(workspace["area_id"], principal_id="alice"))[0]["status"] == "archived"
    assert await service.get_authorization(registered["id"], principal_id="alice") is None
    with pytest.raises(ContractViolation, match="archived"):
        await service.list_projects(workspace["id"], principal_id="alice")


@pytest.mark.asyncio
@pytest.mark.parametrize("relative", ["../secret", "src/../../secret", "src\\..\\secret", "/etc/passwd", "C:\\temp\\file", "src//file", "src/./file", "src/\x00file"])
async def test_relative_traversal_rejected(registry, relative):
    service, repo, _, _, _, project = registry
    registered = await register(service, repo, project)
    with pytest.raises(ContractViolation):
        await service.resolve_path(registered["id"], relative, principal_id="alice")


@pytest.mark.asyncio
async def test_outside_allowlist_rejected_before_git(registry, tmp_path, monkeypatch):
    service, _, _, _, workspace, project = registry
    restricted = WorkspaceRegistry(service.store, allowed_roots=[tmp_path / "repo"])
    def forbidden(*args, **kwargs):
        pytest.fail("Outside root must be rejected before Git is started")
    monkeypatch.setattr("hydra_orch.core.workspace_registry.GitWorkspaceService.resolve_repo_root", forbidden)
    with pytest.raises(ContractViolation, match="allowlist"):
        await restricted.create_project(workspace["id"], "outside", tmp_path, principal_id="alice")
    with pytest.raises(ContractViolation, match="traversal"):
        await service.create_project(workspace["id"], "bad", str(tmp_path / "repo" / ".."), principal_id="alice")


@pytest.mark.asyncio
async def test_symlink_file_escape_and_scope_denial(registry, tmp_path):
    service, repo, _, _, _, project = registry
    registered = await register(service, repo, project)
    outside = tmp_path / "secret"
    outside.write_text("outside")
    try:
        (repo / "src" / "escape").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable on this OS")
    with pytest.raises(ContractViolation, match="escapes"):
        await service.resolve_path(registered["id"], "src/escape", principal_id="alice")
    with pytest.raises(ContractViolation, match="escapes"):
        await service.resolve_path(registered["id"], "README.md", principal_id="alice")


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,patterns", [([], ["src/**"]), (["admin"], ["src/**"]), ("read", ["src/**"]), (["read"], []), (["read"], "src/**"), (["read"], ["../*"])])
async def test_invalid_registration_does_not_grant(registry, scope, patterns):
    service, repo, _, _, _, project = registry
    with pytest.raises(ContractViolation):
        await service.register_repository(project["id"], repo, principal_id="alice",
            authorized_principal_id="alice", scopes=scope, allowed_paths=patterns)
    assert await service.list_repositories(project["id"], principal_id="alice") == []


@pytest.mark.asyncio
async def test_duplicate_registration_rolls_back_grant_and_audit(registry):
    service, repo, _, _, _, project = registry
    await register(service, repo, project)
    async with service.store._connect() as db:
        before = (await (await db.execute("SELECT COUNT(*) FROM authorizations")).fetchone())[0]
        audit_before = (await (await db.execute("SELECT COUNT(*) FROM commands WHERE scope='registry'")).fetchone())[0]
    with pytest.raises(StorageIntegrityError):
        await register(service, repo, project)
    async with service.store._connect() as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM authorizations")).fetchone())[0] == before
        assert (await (await db.execute("SELECT COUNT(*) FROM commands WHERE scope='registry'")).fetchone())[0] == audit_before


@pytest.mark.asyncio
async def test_unknown_entities_and_invalid_references(registry):
    service, repo, _, _, workspace, project = registry
    for operation in [
        service.create_workspace("missing", "name", principal_id="alice"),
        service.list_projects("missing", principal_id="alice"),
        service.list_repositories("missing", principal_id="alice"),
        service.grant_repository("missing", principal_id="alice", authorized_principal_id="alice", scopes=["read"]),
        service.revoke_authorization("missing", principal_id="alice"),
    ]:
        with pytest.raises(ContractViolation, match="does not exist"):
            await operation
    for branch, sha in [("missing-branch", None), ("--bad", None), ("bad branch", None), ("main", "bad-sha")]:
        with pytest.raises((ContractViolation, RuntimeError)):
            await service.create_project(workspace["id"], "bad", repo, principal_id="alice", base_branch=branch, base_sha=sha)
    with pytest.raises(ContractViolation):
        await service.create_area(" ", principal_id="alice")
    with pytest.raises(ContractViolation):
        WorkspaceRegistry(service.store, allowed_roots=[])


@pytest.mark.asyncio
async def test_revocation_during_inspection_wins(registry, monkeypatch):
    service, repo, _, _, _, project = registry
    registered = await register(service, repo, project)
    original = service._git_identity
    async def revoke_during_inspection(*args, **kwargs):
        result = await original(*args, **kwargs)
        await service.revoke_authorization(registered["authorization_id"], principal_id="alice")
        return result
    monkeypatch.setattr(service, "_git_identity", revoke_during_inspection)
    with pytest.raises(ContractViolation, match="revoked"):
        await service.resolve_repository(registered["id"], principal_id="alice")


@pytest.mark.asyncio
async def test_legacy_adoption_requires_explicit_action_and_no_implicit_grant(registry):
    service, repo, _, _, workspace, project = registry
    async with service.store._connect() as db:
        await db.execute("UPDATE projects SET workspace_id=NULL WHERE id=?", (project["id"],))
    with pytest.raises(ContractViolation, match="Legacy project"):
        await service.list_repositories(project["id"], principal_id="alice")
    with pytest.raises(OptimisticLockError):
        await service.adopt_legacy_project(project["id"], workspace["id"], principal_id="alice", expected_revision=9)
    result = await service.adopt_legacy_project(project["id"], workspace["id"], principal_id="alice", expected_revision=1)
    assert result["workspace_id"] == workspace["id"] and result["revision"] == 2
    with pytest.raises(ContractViolation, match="explicit registration"):
        await service.resolve_canonical_root(project["id"], principal_id="alice")
    with pytest.raises(ContractViolation, match="Only unowned"):
        await service.adopt_legacy_project(project["id"], workspace["id"], principal_id="alice", expected_revision=2)
    with pytest.raises(ContractViolation, match="does not exist"):
        await service.adopt_legacy_project("missing", workspace["id"], principal_id="alice", expected_revision=1)


@pytest.mark.asyncio
async def test_rollback_of_registry_mutation_when_audit_fails(registry, monkeypatch):
    service, _, _, _, _, _ = registry
    before = await service.list_areas(principal_id="alice")
    async def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(service, "_audit", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.create_area("must rollback", principal_id="alice")
    assert await service.list_areas(principal_id="alice") == before


def test_uuid7_fallback_is_versioned_and_unique(monkeypatch):
    from hydra_orch.core.identifier import new_id
    monkeypatch.delattr(uuid, "uuid7", raising=False)
    ids = [uuid.UUID(new_id()) for _ in range(100)]
    assert len(set(ids)) == 100
    assert all(value.version == 7 for value in ids)
