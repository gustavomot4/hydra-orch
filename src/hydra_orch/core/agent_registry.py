"""T12: declared agent capabilities and explicit, platform-specific certification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import shutil
from typing import Callable, Literal, Optional

from pydantic import Field, field_validator

from hydra_orch.bridge.worker_runner import build_invocation
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.model import (
    ContractViolation, ExecutionModel, ExecutorCapabilities, ExecutorCapability,
    Identifier, NonEmpty, Sha256, UtcTimestamp,
)

DRIVERS = {"codex", "claude_code", "gemini", "opencode", "aider", "agy"}
CERTIFICATION_CHECKS = {"cwd", "scope", "timeout", "cancel_process_tree", "artifact_hash"}


def canonical_driver(value: str) -> str:
    driver = {"claude-code": "claude_code", "claude": "claude_code", "gemini_cli": "gemini"}.get(value, value)
    if driver not in DRIVERS:
        raise ValueError("Unsupported agent CLI driver")
    return driver


class AgentDefinition(ExecutionModel):
    agent_id: Identifier = Field(default_factory=new_id)
    name: NonEmpty
    version: NonEmpty
    driver_type: str
    declared_capabilities: tuple[ExecutorCapability, ...]
    limitations: tuple[NonEmpty, ...] = ()

    _canonical_driver = field_validator("driver_type")(canonical_driver)

    @field_validator("declared_capabilities")
    @classmethod
    def unique_capabilities(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Capabilities must be unique")
        return values


class DriverCertificationReport(ExecutionModel):
    agent_id: Identifier
    driver_type: str
    agent_version: NonEmpty
    platform: Literal["Linux", "Windows", "Darwin"]
    executable_sha256: Sha256
    capabilities: tuple[ExecutorCapability, ...]
    passed_checks: tuple[NonEmpty, ...]
    simulated: Literal[False]
    issued_at: UtcTimestamp


class ResolvedAgent(ExecutionModel):
    definition: AgentDefinition
    executable: NonEmpty
    platform: str
    capabilities: ExecutorCapabilities
    certificate_sha256: Sha256


class AgentRegistry:
    """Registration never grants certification and never runs an agent process.

    Certificate import is an explicit operator attestation: validate the evidence
    structure and hashes here; producing truthful certification evidence remains
    the external certification job's responsibility.
    """

    def __init__(self, store: ExecutionStore, *, certification_root: Optional[Path] = None,
                 executable_locator: Callable[[str], Optional[str]] = shutil.which):
        self.store = store
        self.certification_root = Path(certification_root or Path(store.db_path).parent / "certification").resolve()
        self.locate = executable_locator

    @staticmethod
    def _definition(row) -> AgentDefinition:
        return AgentDefinition(agent_id=row["id"], name=row["name"], version=row["version"],
            driver_type=row["driver_type"], declared_capabilities=tuple(json.loads(row["declared_capabilities_json"])),
            limitations=tuple(json.loads(row["limitations_json"])))

    async def register_agent(self, definition: AgentDefinition) -> AgentDefinition:
        # Existing runner capabilities are an upper bound, not proof of external driver support.
        build_invocation(definition.driver_type, "").capabilities.require(definition.declared_capabilities)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute("""INSERT INTO agent_definitions
                    (id,name,version,driver_type,declared_capabilities_json,limitations_json,is_certified)
                    VALUES (?,?,?,?,?,?,0)""", (definition.agent_id, definition.name, definition.version,
                    definition.driver_type, json.dumps([c.value for c in definition.declared_capabilities]), json.dumps(definition.limitations)))
                for cap in definition.declared_capabilities:
                    await db.execute("""INSERT INTO capability_declarations
                        (id,agent_definition_id,name,version,supports_tools,supports_workspace,supports_cancellation)
                        VALUES (?,?,?,?,?,?,?)""", (new_id(), definition.agent_id, cap.value, definition.version,
                        int(cap == ExecutorCapability.TOOL_EXECUTION), int(cap == ExecutorCapability.WORKSPACE_EXECUTION),
                        int(cap == ExecutorCapability.CANCEL_PROCESS_TREE)))
                await self.store._record_command_in_tx(db, scope="agent_registry", idempotency_key=new_id(),
                    request_hash=self.store.compute_request_hash(definition),
                    response_payload={"event": "agent.registered", "agent_id": definition.agent_id})
        return definition

    async def get_agent(self, agent_id: str) -> AgentDefinition:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM agent_definitions WHERE id=?", (agent_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Agent definition does not exist")
        return self._definition(row)

    async def list_agents(self) -> tuple[AgentDefinition, ...]:
        await self.store.initialize()
        async with self.store._connect() as db:
            return tuple(self._definition(r) for r in await (await db.execute("SELECT * FROM agent_definitions ORDER BY id")).fetchall())

    def _executable(self, definition: AgentDefinition) -> Path:
        executable = self.locate(build_invocation(definition.driver_type, "").executable)
        if executable is None or not Path(executable).is_file():
            raise ContractViolation("executor_unavailable", "Agent CLI executable is unavailable")
        return Path(executable).resolve()

    def _report(self, path: Path):
        candidate = Path(path).resolve()
        if self.certification_root not in candidate.parents:
            raise ContractViolation("certification_invalid", "Report must be inside the explicit certification root")
        try:
            if candidate.stat().st_size > 1_000_000:
                raise ValueError("Report too large")
            data = candidate.read_bytes()
            report = DriverCertificationReport.model_validate_json(data)
        except (OSError, ValueError):
            raise ContractViolation("certification_invalid", "Certification report is missing or malformed") from None
        return report, hashlib.sha256(data).hexdigest(), candidate

    async def import_certificate(self, agent_id: str, report_path: Path, *, principal_id: str) -> str:
        if not principal_id.strip():
            raise ContractViolation("authorization_denied", "Explicit operator attestation is required")
        definition = await self.get_agent(agent_id)
        report, report_hash, path = self._report(report_path)
        executable = self._executable(definition)
        if (report.agent_id != agent_id or report.driver_type != definition.driver_type
                or report.agent_version != definition.version
                or not CERTIFICATION_CHECKS <= set(report.passed_checks)
                or set(report.capabilities) != set(definition.declared_capabilities)
                or hashlib.sha256(executable.read_bytes()).hexdigest() != report.executable_sha256):
            raise ContractViolation("certification_invalid", "Report does not attest this driver, version, checks and executable")
        certificate_id = new_id()
        payload = {"event": "agent.certified", "agent_id": agent_id, "principal_id": principal_id,
            "report_path": str(path), "report_sha256": report_hash,
            "executable_sha256": report.executable_sha256, "capabilities": [c.value for c in report.capabilities]}
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute("DELETE FROM capability_declarations WHERE agent_definition_id=? AND name='certification' AND version=?", (agent_id, report.platform))
                await db.execute("""INSERT INTO capability_declarations(id,agent_definition_id,name,version,certified_on)
                    VALUES (?,?,'certification',?,?)""", (certificate_id, agent_id, report.platform, report.issued_at.isoformat()))
                await db.execute("UPDATE agent_definitions SET is_certified=1 WHERE id=?", (agent_id,))
                await self.store._record_command_in_tx(db, scope="agent_certificate", idempotency_key=certificate_id,
                    request_hash=report_hash, response_payload=payload)
        return certificate_id

    async def revoke_certification(self, agent_id: str, platform_name: str, *, principal_id: str):
        if not principal_id.strip():
            raise ContractViolation("authorization_denied", "Explicit operator is required")
        await self.get_agent(agent_id)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute("DELETE FROM capability_declarations WHERE agent_definition_id=? AND name='certification' AND version=?", (agent_id, platform_name))
                await db.execute("""UPDATE agent_definitions SET is_certified=EXISTS(
                    SELECT 1 FROM capability_declarations WHERE agent_definition_id=? AND name='certification') WHERE id=?""", (agent_id, agent_id))
                await self.store._record_command_in_tx(db, scope="agent_registry", idempotency_key=new_id(),
                    request_hash=self.store.compute_request_hash({"agent_id": agent_id, "platform": platform_name}),
                    response_payload={"event": "agent.certification_revoked", "agent_id": agent_id, "principal_id": principal_id})

    async def resolve_capabilities(self, agent_id: str, *, required: tuple[ExecutorCapability, ...] = (),
                                    platform_name: Optional[str] = None) -> ResolvedAgent:
        definition = await self.get_agent(agent_id)
        os_name = platform_name or platform.system()
        if os_name != platform.system():
            raise ContractViolation("platform_mismatch", "Local execution requires certification for the current OS")
        declared = ExecutorCapabilities(executor_id=agent_id, capabilities=definition.declared_capabilities)
        declared.require(required)
        executable = self._executable(definition)
        async with self.store._connect() as db:
            row = await (await db.execute("""SELECT c.response_json FROM capability_declarations d
                JOIN commands c ON c.scope='agent_certificate' AND c.idempotency_key=d.id
                WHERE d.agent_definition_id=? AND d.name='certification' AND d.version=?""", (agent_id, os_name))).fetchone()
        if row is None:
            raise ContractViolation("driver_not_certified", "Driver has no current certificate for this OS")
        metadata = json.loads(row["response_json"])
        report, digest, _ = self._report(Path(metadata["report_path"]))
        if (digest != metadata["report_sha256"] or report.platform != os_name
                or report.agent_id != agent_id or report.agent_version != definition.version
                or report.driver_type != definition.driver_type
                or set(report.capabilities) != set(definition.declared_capabilities)
                or hashlib.sha256(executable.read_bytes()).hexdigest() != metadata["executable_sha256"]):
            raise ContractViolation("certification_stale", "Certification evidence or executable changed")
        return ResolvedAgent(definition=definition, executable=str(executable), platform=os_name,
            capabilities=declared, certificate_sha256=digest)

    async def get_certified_agents(self, *, platform_name: Optional[str] = None):
        results = []
        for definition in await self.list_agents():
            try:
                results.append(await self.resolve_capabilities(definition.agent_id, platform_name=platform_name))
            except ContractViolation:
                continue
        return tuple(results)

    async def validate_driver(self, agent_id: str, *, required: tuple[ExecutorCapability, ...] = ()) -> bool:
        await self.resolve_capabilities(agent_id, required=required)
        return True
