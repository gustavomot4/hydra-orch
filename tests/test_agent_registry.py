"""T12 certification gates with explicit synthetic operator reports, no real LLM."""

from datetime import datetime, timezone
import hashlib
import json
import platform

import pytest
import pytest_asyncio
from pydantic import ValidationError

from hydra_orch.bridge.worker_runner import build_invocation
from hydra_orch.core.agent_registry import (
    AgentDefinition, AgentRegistry, CERTIFICATION_CHECKS, DriverCertificationReport,
)
from hydra_orch.core.checkpointer import ExecutionStore, StorageIntegrityError
from hydra_orch.model import ContractViolation, ExecutorCapability as Capability


@pytest_asyncio.fixture
async def catalog(tmp_path):
    binary = tmp_path / "fake-driver"
    binary.write_bytes(b"synthetic fixture executable")
    reports = tmp_path / "certification"
    reports.mkdir()
    registry = AgentRegistry(ExecutionStore(tmp_path / "catalog.sqlite"), certification_root=reports,
        executable_locator=lambda _: str(binary))
    definition = AgentDefinition(name="Fixture Codex", version="test-1", driver_type="codex",
        declared_capabilities=(Capability.WORKSPACE_EXECUTION, Capability.CANCEL_PROCESS_TREE))
    await registry.register_agent(definition)
    report = DriverCertificationReport(agent_id=definition.agent_id, driver_type="codex", agent_version="test-1",
        platform=platform.system(), executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        capabilities=definition.declared_capabilities, passed_checks=tuple(sorted(CERTIFICATION_CHECKS)),
        simulated=False, issued_at=datetime.now(timezone.utc))
    report_path = reports / "report.json"
    report_path.write_text(report.model_dump_json())
    return registry, definition, binary, report_path


@pytest.mark.asyncio
async def test_registration_not_certification_and_restart(catalog):
    registry, definition, binary, report = catalog
    assert await registry.get_agent(definition.agent_id) == definition
    assert await registry.list_agents() == (definition,)
    assert await registry.get_certified_agents() == ()
    with pytest.raises(ContractViolation) as error:
        await registry.validate_driver(definition.agent_id)
    assert error.value.code == "driver_not_certified"
    await registry.import_certificate(definition.agent_id, report, principal_id="operator")
    resolved = await registry.resolve_capabilities(definition.agent_id,
        required=(Capability.WORKSPACE_EXECUTION,))
    assert resolved.definition == definition
    assert resolved.executable == str(binary)
    assert await registry.validate_driver(definition.agent_id)
    restarted = AgentRegistry(ExecutionStore(registry.store.db_path), certification_root=report.parent,
        executable_locator=lambda _: str(binary))
    assert len(await restarted.get_certified_agents()) == 1
    await restarted.revoke_certification(definition.agent_id, platform.system(), principal_id="operator")
    assert await registry.get_certified_agents() == ()
    async with registry.store._connect() as db:
        assert (await (await db.execute("SELECT is_certified FROM agent_definitions")).fetchone())[0] == 0
        assert (await (await db.execute("SELECT COUNT(*) FROM commands WHERE scope='agent_certificate'")).fetchone())[0] == 1


@pytest.mark.asyncio
async def test_missing_cli_and_capability_mismatch_are_explicit(catalog):
    registry, definition, _, report = catalog
    with pytest.raises(ContractViolation) as mismatch:
        await registry.resolve_capabilities(definition.agent_id, required=(Capability.FILESYSTEM_SANDBOX,))
    assert mismatch.value.code == "capability_mismatch"
    registry.locate = lambda _: None
    with pytest.raises(ContractViolation) as missing:
        await registry.resolve_capabilities(definition.agent_id)
    assert missing.value.code == "executor_unavailable"
    with pytest.raises(ContractViolation):
        await registry.import_certificate(definition.agent_id, report, principal_id="operator")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["report", "binary", "report_removed"])
async def test_changed_evidence_invalidates_selection(catalog, change):
    registry, definition, binary, report = catalog
    await registry.import_certificate(definition.agent_id, report, principal_id="operator")
    if change == "binary":
        binary.write_bytes(b"changed executable")
    elif change == "report":
        report.write_text(report.read_text() + "\n")
    else:
        report.unlink()
    with pytest.raises(ContractViolation):
        await registry.resolve_capabilities(definition.agent_id)
    assert await registry.get_certified_agents() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("agent_id", "another-agent"), ("agent_version", "other"), ("driver_type", "aider"),
    ("passed_checks", []), ("capabilities", []), ("executable_sha256", "a" * 64), ("simulated", True),
])
async def test_report_mismatch_never_certifies(catalog, field, value):
    registry, definition, _, report = catalog
    data = json.loads(report.read_text())
    data[field] = value
    report.write_text(json.dumps(data))
    with pytest.raises(ContractViolation) as error:
        await registry.import_certificate(definition.agent_id, report, principal_id="operator")
    assert error.value.code == "certification_invalid"
    assert await registry.get_certified_agents() == ()


@pytest.mark.asyncio
async def test_report_boundary_operator_and_platform(catalog, tmp_path):
    registry, definition, _, report = catalog
    other = tmp_path / "outside.json"
    other.write_text(report.read_text())
    with pytest.raises(ContractViolation, match="explicit certification root"):
        await registry.import_certificate(definition.agent_id, other, principal_id="operator")
    with pytest.raises(ContractViolation, match="attestation"):
        await registry.import_certificate(definition.agent_id, report, principal_id="")
    with pytest.raises(ContractViolation, match="operator"):
        await registry.revoke_certification(definition.agent_id, platform.system(), principal_id="")
    await registry.import_certificate(definition.agent_id, report, principal_id="operator")
    foreign = "Windows" if platform.system() != "Windows" else "Linux"
    with pytest.raises(ContractViolation, match="current OS"):
        await registry.resolve_capabilities(definition.agent_id, platform_name=foreign)
    report.write_text("invalid JSON")
    with pytest.raises(ContractViolation, match="malformed"):
        await registry.import_certificate(definition.agent_id, report, principal_id="operator")


@pytest.mark.asyncio
async def test_invalid_declarations_duplicates_and_unknown_agent(catalog):
    registry, definition, _, _ = catalog
    with pytest.raises(StorageIntegrityError):
        await registry.register_agent(definition)
    with pytest.raises(ContractViolation):
        await registry.get_agent("unknown")
    with pytest.raises(ValidationError):
        AgentDefinition(name="a", version="1", driver_type="unknown", declared_capabilities=())
    with pytest.raises(ValidationError):
        AgentDefinition(name="a", version="1", driver_type="codex",
            declared_capabilities=(Capability.INFERENCE, Capability.INFERENCE))
    exaggerated = AgentDefinition(name="unsupported", version="1", driver_type="aider",
        declared_capabilities=(Capability.NETWORK_ISOLATION,))
    with pytest.raises(ContractViolation, match="lacks required"):
        await registry.register_agent(exaggerated)


def test_config_driver_alias_reuses_claude_invocation():
    plan = build_invocation("claude-code", "test")
    assert plan.driver == "claude_code"
    assert plan.executable == "claude"
    assert plan.argv[1] == "--print"
