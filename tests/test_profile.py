"""T13 profile validation and immutable snapshots against real SQLite/Git fixtures."""

from datetime import datetime, timezone
import hashlib
import json
import platform

import pytest
import pytest_asyncio
from pydantic import ValidationError

from hydra_orch.core.agent_registry import AgentDefinition, AgentRegistry, DriverCertificationReport, CERTIFICATION_CHECKS
from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError
from hydra_orch.core.profile_service import MemoryPolicy, ProfileDefinition, ProfileService
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.model import ContractViolation, ExecutorCapability as Capability, RunSpec, TaskSpec
from test_checkpointer import _make_run_spec
from test_server import _init_temp_git_repo


@pytest_asyncio.fixture
async def profiles(tmp_path):
    repo, sha = _init_temp_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "profiles.sqlite")
    workspaces = WorkspaceRegistry(store, allowed_roots=[tmp_path])
    area = await workspaces.create_area("Area", principal_id="operator")
    workspace = await workspaces.create_workspace(area["id"], "Workspace", principal_id="operator")
    project = await workspaces.create_project(workspace["id"], "Project", repo, principal_id="operator")
    registered = await workspaces.register_repository(project["id"], repo, principal_id="operator",
        authorized_principal_id="operator", scopes=["read", "execute"], allowed_paths=["src/**"])
    binary = tmp_path / "fake-driver"
    binary.write_bytes(b"fixture executable")
    reports = tmp_path / "certification"
    reports.mkdir()
    agents = AgentRegistry(store, certification_root=reports, executable_locator=lambda _: str(binary))
    agent = AgentDefinition(name="Fixture", version="1", driver_type="codex",
        declared_capabilities=(Capability.WORKSPACE_EXECUTION, Capability.CANCEL_PROCESS_TREE))
    await agents.register_agent(agent)
    report = DriverCertificationReport(agent_id=agent.agent_id, driver_type="codex", agent_version="1",
        platform=platform.system(), executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        capabilities=agent.declared_capabilities, passed_checks=tuple(CERTIFICATION_CHECKS), simulated=False,
        issued_at=datetime.now(timezone.utc))
    report_path = reports / "fixture.json"
    report_path.write_text(report.model_dump_json())
    await agents.import_certificate(agent.agent_id, report_path, principal_id="operator")
    service = ProfileService(store, agents, workspaces)
    definition = ProfileDefinition(name="Profile", agent_ref=agent.agent_id, executor_ref=agent.agent_id, model_ref="fixture-model")
    await service.create_profile(definition)
    base = _make_run_spec(str(repo))
    run_data = base.model_dump(mode="json")
    run_data.update(project_id=project["id"], base_sha=sha)
    run = RunSpec.model_validate(run_data)
    await store.submit_run_idempotent(run)
    return service, definition, registered, run


@pytest.mark.asyncio
async def test_snapshot_canonical_hash_immutable_after_profile_update(profiles):
    service, definition, repository, run = profiles
    snapshot = await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    assert hashlib.sha256(snapshot.effective_config_json.encode()).hexdigest() == snapshot.snapshot_hash
    changed_copy = snapshot.effective_config
    changed_copy["profile"]["name"] = "mutated"
    assert snapshot.effective_config["profile"]["name"] == "Profile"
    with pytest.raises(ValidationError):
        snapshot.snapshot_hash = "b" * 64
    changed = ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "name": "Updated", "model_ref": "new-model"})
    updated = await service.update_profile(changed, expected_revision=1)
    assert updated.revision == 2
    assert (await service.get_profile(definition.profile_id)).name == "Updated"
    repeated = await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    assert repeated == snapshot
    restarted_store = ExecutionStore(service.store.db_path)
    restarted_agents = AgentRegistry(restarted_store, certification_root=service.agents.certification_root,
        executable_locator=service.agents.locate)
    restarted_workspaces = WorkspaceRegistry(restarted_store, allowed_roots=service.workspaces.allowed_roots)
    restarted = ProfileService(restarted_store, restarted_agents, restarted_workspaces)
    assert await restarted.get_snapshot(run.run_id, principal_id="operator") == snapshot
    events = await service.store.get_events(run.run_id)
    assert sum(e.event_type == "profile.snapshot_created" for e in events) == 1


@pytest.mark.asyncio
async def test_invalid_capabilities_and_revocations_prevent_snapshot(profiles):
    service, definition, repository, run = profiles
    unsupported = ProfileDefinition.model_validate({**definition.model_dump(mode="json"),
        "required_capabilities": [Capability.NETWORK_ISOLATION.value]})
    await service.update_profile(unsupported, expected_revision=1)
    with pytest.raises(ContractViolation) as error:
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    assert error.value.code == "capability_mismatch"
    with pytest.raises(ContractViolation):
        await service.get_snapshot(run.run_id, principal_id="operator")
    await service.update_profile(definition, expected_revision=2)
    await service.agents.revoke_certification(definition.agent_ref, platform.system(), principal_id="operator")
    with pytest.raises(ContractViolation, match="certificate"):
        await service.resolve_effective(definition.profile_id, repository["id"], principal_id="operator")
    await service.workspaces.revoke_authorization(repository["authorization_id"], principal_id="operator")
    with pytest.raises(ContractViolation, match="current grant"):
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")


@pytest.mark.asyncio
async def test_optimistic_update_and_missing_refs(profiles):
    service, definition, repository, run = profiles
    with pytest.raises(OptimisticLockError):
        await service.update_profile(definition, expected_revision=9)
    with pytest.raises(ContractViolation):
        await service.get_profile("missing")
    missing = ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "profile_id": "missing"})
    with pytest.raises(ContractViolation):
        await service.update_profile(missing, expected_revision=1)
    for extra in [{"agent_ref": "missing"}, {"skills_refs": ["missing"]}, {"mcp_refs": ["missing"]}]:
        data = {**definition.model_dump(mode="json"), "profile_id": "new-profile", **extra}
        with pytest.raises(ContractViolation, match="not registered"):
            await service.create_profile(ProfileDefinition.model_validate(data))
    with pytest.raises(ContractViolation, match="revision 1"):
        await service.create_profile(ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "revision": 2}))


@pytest.mark.asyncio
async def test_scope_and_late_snapshot_blocked(profiles):
    service, definition, repository, run = profiles
    with pytest.raises(ContractViolation):
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="other")
    with pytest.raises(ContractViolation, match="Run does not exist"):
        await service.snapshot(definition.profile_id, "missing", repository["id"], principal_id="operator")
    async with service.store._connect() as db:
        await db.execute("UPDATE runs SET project_id=(SELECT id FROM projects LIMIT 1),spec_json=json_set(spec_json,'$.repo_root','/wrong') WHERE id=?", (run.run_id,))
    with pytest.raises(ContractViolation, match="same project/root"):
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    async with service.store._connect() as db:
        await db.execute("UPDATE runs SET spec_json=?,status='running' WHERE id=?", (run.model_dump_json(), run.run_id))
    task = await service.store.get_task(run.tasks[0].task_id)
    await service.store.update_task_status_atomic(run.tasks[0].task_id, 'running', task['revision'], 'task.started')
    with pytest.raises(ContractViolation, match="before starting"):
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")


@pytest.mark.asyncio
async def test_snapshot_conflict_tampering_and_event_atomicity(profiles, monkeypatch):
    service, definition, repository, run = profiles
    async def fail(*args, **kwargs):
        raise RuntimeError("event unavailable")
    original = service.store._insert_event_in_tx
    monkeypatch.setattr(service.store, "_insert_event_in_tx", fail)
    with pytest.raises(RuntimeError):
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    with pytest.raises(ContractViolation, match="snapshot does not exist"):
        await service.get_snapshot(run.run_id, principal_id="operator")
    monkeypatch.setattr(service.store, "_insert_event_in_tx", original)
    await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    with pytest.raises(ContractViolation, match="different immutable profile"):
        await service.snapshot("other-profile", run.run_id, repository["id"], principal_id="operator")
    async with service.store._connect() as db:
        await db.execute("UPDATE profile_snapshots SET snapshot_hash=? WHERE run_id=?", ("b" * 64, run.run_id))
    with pytest.raises(ContractViolation, match="integrity"):
        await service.get_snapshot(run.run_id, principal_id="operator")


@pytest.mark.asyncio
async def test_component_trust_relational_refs_and_memory_consent(profiles):
    service, definition, repository, run = profiles
    async with service.store._connect() as db:
        await db.execute("INSERT INTO discovered_resources(id,resource_type,source_canonical_path,content_hash) VALUES ('discovered','skill','/fixture',?)", ("a" * 64,))
        await db.execute("INSERT INTO skill_definitions(id,name,version,manifest_ref,checksum,discovered_resource_id) VALUES ('skill','fixture','1','fixture.json',?,'discovered')", ("a" * 64,))
    with_skill = ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "skills_refs": ["skill"]})
    await service.update_profile(with_skill, expected_revision=1)
    with pytest.raises(ContractViolation, match="not approved"):
        await service.resolve_effective(definition.profile_id, repository["id"], principal_id="operator")
    async with service.store._connect() as db:
        await db.execute("UPDATE discovered_resources SET trust_status='approved'")
    assert (await service.resolve_effective(definition.profile_id, repository["id"], principal_id="operator"))["components"]["skills"]
    async with service.store._connect() as db:
        await db.execute("DELETE FROM profile_skills WHERE profile_id=?", (definition.profile_id,))
    with pytest.raises(ContractViolation, match="references differ"):
        await service.get_profile(definition.profile_id)
    with_memory = ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "memory_policy": {"enabled": True, "consent_id": "consent"}})
    await service.update_profile(with_memory, expected_revision=2)
    with pytest.raises(ContractViolation, match="Memory requires"):
        await service.resolve_effective(definition.profile_id, repository["id"], principal_id="operator")
    async with service.store._connect() as db:
        await db.execute("INSERT INTO consent_records(id,principal_id,purpose,scope,status) VALUES ('consent','operator','memory',?,'granted')", (f"project:{run.project_id}",))
    assert (await service.resolve_effective(definition.profile_id, repository["id"], principal_id="operator"))["profile"]["memory_policy"]["enabled"]


def test_profile_input_validation_and_store_identity(tmp_path):
    with pytest.raises(ValidationError):
        MemoryPolicy(enabled=True)
    for fields in [{"model_ref": "bad model"}, {"model_ref": "sk-secretabcdef"},
        {"skills_refs": ["a", "a"]}, {"resource_limits": {"max_usd": -1}}]:
        with pytest.raises(ValidationError):
            ProfileDefinition(name="p", agent_ref="a", executor_ref="a", **({"model_ref": "model"} | fields))
    one, two = ExecutionStore(tmp_path / "one.sqlite"), ExecutionStore(tmp_path / "two.sqlite")
    with pytest.raises(ValueError, match="same canonical store"):
        ProfileService(one, AgentRegistry(two), WorkspaceRegistry(one, allowed_roots=[tmp_path]))


@pytest.mark.asyncio
async def test_component_raw_credentials_rejected_without_snapshot(profiles):
    service, definition, repository, run = profiles
    async with service.store._connect() as db:
        await db.execute("INSERT INTO mcp_definitions(id,server_name,transport_type,endpoint) VALUES ('mcp','unsafe','http','https://user:password@example.com')")
    with_mcp = ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "mcp_refs": ["mcp"]})
    await service.update_profile(with_mcp, expected_revision=1)
    with pytest.raises(ContractViolation, match="raw credentials"):
        await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    with pytest.raises(ContractViolation, match="snapshot does not exist"):
        await service.get_snapshot(run.run_id, principal_id="operator")


@pytest.mark.asyncio
async def test_profile_can_pin_after_pre_execution_human_approval(profiles):
    from hydra_orch.core.hitl import HITLService
    service, definition, repository, run = profiles
    hitl = HITLService(service.store)
    pending = await hitl.request(run.run_id, 'needs_approval', 'Approve preparation',
        idempotency_key='profile-preflight-request-001', task_id=run.tasks[0].task_id)
    await hitl.respond(run.run_id, pending.request_id, 'Approved', actor='operator', expected_revision=1,
        idempotency_key='profile-preflight-response-001')
    snapshot = await service.snapshot(definition.profile_id, run.run_id, repository['id'], principal_id='operator')
    assert snapshot.run_id == run.run_id
