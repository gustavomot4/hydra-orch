"""T13: validated execution profiles and immutable, canonical snapshots per run."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, model_validator

from hydra_orch.core.agent_registry import AgentRegistry
from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.model import (
    BudgetPolicy, ContractViolation, ExecutionModel, ExecutorCapability,
    Identifier, NonEmpty, Sha256, UtcTimestamp,
)


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class MemoryPolicy(ExecutionModel):
    enabled: bool = False
    consent_id: Optional[Identifier] = None

    @model_validator(mode="after")
    def consistent(self):
        if self.enabled != (self.consent_id is not None):
            raise ValueError("Memory policy requires explicit consent exactly when enabled")
        return self


class ProfileDefinition(ExecutionModel):
    profile_id: Identifier = Field(default_factory=new_id)
    name: NonEmpty
    agent_ref: Identifier
    executor_ref: Identifier
    model_ref: NonEmpty
    skills_refs: tuple[Identifier, ...] = ()
    mcp_refs: tuple[Identifier, ...] = ()
    memory_policy: MemoryPolicy = Field(default_factory=MemoryPolicy)
    resource_limits: BudgetPolicy = Field(default_factory=BudgetPolicy)
    required_capabilities: tuple[ExecutorCapability, ...] = (
        ExecutorCapability.WORKSPACE_EXECUTION, ExecutorCapability.CANCEL_PROCESS_TREE,
    )
    orchestration_mode: Literal["swarm", "relay", "persistent"] = "relay"
    revision: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode="after")
    def valid(self):
        if any(len(values) != len(set(values)) for values in (self.skills_refs, self.mcp_refs, self.required_capabilities)):
            raise ValueError("Profile component references must be unique")
        if "\x00" in self.model_ref or any(c.isspace() for c in self.model_ref):
            raise ValueError("Model reference cannot contain whitespace or NUL")
        data = self.model_dump(mode="json")
        if redact(data) != data:
            raise ValueError("Profile values cannot contain raw credentials")
        return self


class ProfileSnapshot(ExecutionModel):
    snapshot_id: Identifier
    profile_id: Identifier
    run_id: Identifier
    snapshot_hash: Sha256
    effective_config_json: NonEmpty
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def verify(self):
        data = json.loads(self.effective_config_json)
        if (canonical_json(data) != self.effective_config_json
                or hashlib.sha256(self.effective_config_json.encode()).hexdigest() != self.snapshot_hash
                or not isinstance(data, dict) or not isinstance(data.get("profile"), dict)
                or data["profile"].get("profile_id") != self.profile_id):
            raise ValueError("Profile snapshot integrity mismatch")
        return self

    @property
    def effective_config(self):
        # A fresh value prevents mutation through nested dicts in a frozen DTO.
        return json.loads(self.effective_config_json)


class ProfileService:
    def __init__(self, store: ExecutionStore, agents: AgentRegistry, workspaces: WorkspaceRegistry):
        if agents.store is not store or workspaces.store is not store:
            raise ValueError("Profile services must share the same canonical store")
        self.store, self.agents, self.workspaces = store, agents, workspaces

    async def _components(self, db, definition: ProfileDefinition):
        for reference in (definition.agent_ref, definition.executor_ref):
            if await (await db.execute("SELECT 1 FROM agent_definitions WHERE id=?", (reference,))).fetchone() is None:
                raise ContractViolation("resource_not_found", "Profile agent or executor is not registered")
        for table, references in (("skill_definitions", definition.skills_refs), ("mcp_definitions", definition.mcp_refs)):
            for reference in references:
                if await (await db.execute(f"SELECT 1 FROM {table} WHERE id=?", (reference,))).fetchone() is None:
                    raise ContractViolation("resource_not_found", "Profile component is not registered")

    async def _write(self, db, definition: ProfileDefinition):
        await self._components(db, definition)
        limits = definition.resource_limits.model_dump(mode="json")
        limits["required_capabilities"] = [c.value for c in definition.required_capabilities]
        values = (definition.name, definition.agent_ref, definition.model_ref, definition.executor_ref,
            canonical_json(definition.skills_refs), canonical_json(definition.mcp_refs),
            definition.memory_policy.model_dump_json(), canonical_json(limits), definition.orchestration_mode)
        return values

    async def _links(self, db, definition: ProfileDefinition):
        for table, column, references in (("profile_skills", "skill_id", definition.skills_refs), ("profile_mcps", "mcp_id", definition.mcp_refs)):
            await db.execute(f"DELETE FROM {table} WHERE profile_id=?", (definition.profile_id,))
            for reference in references:
                await db.execute(f"INSERT INTO {table}(profile_id,{column}) VALUES (?,?)", (definition.profile_id, reference))
        await self.store._record_command_in_tx(db, scope="profile", idempotency_key=new_id(),
            request_hash=self.store.compute_request_hash(definition),
            response_payload={"event": "profile.saved", "profile_id": definition.profile_id, "revision": definition.revision})

    async def create_profile(self, definition: ProfileDefinition) -> ProfileDefinition:
        if definition.revision != 1:
            raise ContractViolation("profile_invalid", "New profiles start at revision 1")
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                values = await self._write(db, definition)
                await db.execute("""INSERT INTO profiles(name,agent_ref,model_ref,executor_ref,skills_refs_json,
                    mcp_refs_json,memory_policy_json,resource_limits_json,orchestration_mode,id)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", (*values, definition.profile_id))
                await self._links(db, definition)
        return definition

    async def get_profile(self, profile_id: str) -> ProfileDefinition:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", "Profile does not exist")
            limits = json.loads(row["resource_limits_json"])
            required = limits.pop("required_capabilities")
            definition = ProfileDefinition(profile_id=row["id"], name=row["name"], agent_ref=row["agent_ref"],
                executor_ref=row["executor_ref"], model_ref=row["model_ref"], skills_refs=json.loads(row["skills_refs_json"]),
                mcp_refs=json.loads(row["mcp_refs_json"]), memory_policy=json.loads(row["memory_policy_json"]),
                resource_limits=limits, required_capabilities=required, orchestration_mode=row["orchestration_mode"], revision=row["revision"])
            for table, column, refs in (("profile_skills", "skill_id", definition.skills_refs), ("profile_mcps", "mcp_id", definition.mcp_refs)):
                actual = {r[0] for r in await (await db.execute(f"SELECT {column} FROM {table} WHERE profile_id=?", (profile_id,))).fetchall()}
                if actual != set(refs):
                    raise ContractViolation("profile_integrity", "Profile relational and declarative references differ")
            return definition

    async def update_profile(self, definition: ProfileDefinition, *, expected_revision: int) -> ProfileDefinition:
        updated = ProfileDefinition.model_validate({**definition.model_dump(mode="json"), "revision": expected_revision + 1})
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT revision FROM profiles WHERE id=?", (definition.profile_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", "Profile does not exist")
                if row["revision"] != expected_revision:
                    raise OptimisticLockError("Profile revision changed")
                values = await self._write(db, updated)
                await db.execute("""UPDATE profiles SET name=?,agent_ref=?,model_ref=?,executor_ref=?,skills_refs_json=?,
                    mcp_refs_json=?,memory_policy_json=?,resource_limits_json=?,orchestration_mode=?,revision=?,updated_at=datetime('now')
                    WHERE id=?""", (*values, updated.revision, updated.profile_id))
                await self._links(db, updated)
        return updated

    async def resolve_effective(self, profile_id: str, repository_id: str, *, principal_id: str):
        profile = await self.get_profile(profile_id)
        repository = await self.workspaces.resolve_repository(repository_id, principal_id=principal_id, scope="execute")
        agent = await self.agents.resolve_capabilities(profile.agent_ref)
        executor = await self.agents.resolve_capabilities(profile.executor_ref, required=profile.required_capabilities)
        components = {"skills": [], "mcps": []}
        async with self.store._connect() as db:
            for table, refs, key in (("skill_definitions", profile.skills_refs, "skills"), ("mcp_definitions", profile.mcp_refs, "mcps")):
                for ref in refs:
                    row = dict(await (await db.execute(f"SELECT * FROM {table} WHERE id=?", (ref,))).fetchone())
                    resource_id = row.get("discovered_resource_id")
                    if resource_id:
                        resource = await (await db.execute("SELECT trust_status FROM discovered_resources WHERE id=?", (resource_id,))).fetchone()
                        if resource is None or resource[0] not in {"approved", "active"}:
                            raise ContractViolation("component_untrusted", "Discovered profile component is not approved")
                    components[key].append(row)
            if profile.memory_policy.enabled:
                consent = await (await db.execute("SELECT * FROM consent_records WHERE id=?", (profile.memory_policy.consent_id,))).fetchone()
                if (consent is None or consent["status"] != "granted" or consent["revoked_at"] is not None
                        or consent["principal_id"] != principal_id or consent["purpose"] != "memory"
                        or consent["scope"] != f"project:{repository['project_id']}"):
                    raise ContractViolation("consent_required", "Memory requires active matching principal/project consent")
        result = {"schema_version": "1.0", "profile": profile.model_dump(mode="json"),
            "repository": repository, "agent": agent.model_dump(mode="json"),
            "executor": executor.model_dump(mode="json"), "components": components}
        if redact(result) != result:
            raise ContractViolation("secret_in_profile", "Profile components cannot embed raw credentials")
        return result

    @staticmethod
    def _snapshot(row):
        try:
            return ProfileSnapshot(snapshot_id=row["id"], profile_id=row["profile_id"], run_id=row["run_id"],
                snapshot_hash=row["snapshot_hash"], effective_config_json=row["effective_config_json"], created_at=row["created_at"])
        except (ValueError, KeyError, TypeError):
            raise ContractViolation("profile_integrity", "Stored profile snapshot failed integrity verification") from None

    async def snapshot(self, profile_id: str, run_id: str, repository_id: str, *, principal_id: str) -> ProfileSnapshot:
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                run = await (await db.execute("SELECT * FROM runs WHERE id=?", (run_id,))).fetchone()
                if run is None:
                    raise ContractViolation("resource_not_found", "Run does not exist")
                repository = await self.workspaces.resolve_repository(repository_id, principal_id=principal_id, scope="execute")
                run_root = json.loads(run["spec_json"])["repo_root"]
                if run["project_id"] != repository["project_id"] or Path(run_root).resolve() != Path(repository["root_canonical"]):
                    raise ContractViolation("profile_scope_mismatch", "Run and selected repository must belong to the same project/root")
                existing = await (await db.execute("SELECT * FROM profile_snapshots WHERE run_id=?", (run_id,))).fetchone()
                if existing:
                    if existing["profile_id"] != profile_id:
                        raise ContractViolation("profile_snapshot_conflict", "Run already has a different immutable profile")
                    return self._snapshot(existing)
                has_attempt = await (await db.execute("""SELECT 1 FROM attempts a JOIN tasks t ON t.id=a.task_id
                    WHERE t.run_id=? LIMIT 1""", (run_id,))).fetchone()
                if run["status"] != "queued" or has_attempt:
                    raise ContractViolation("profile_snapshot_late", "Profile must be pinned before starting any attempt")
                effective = await self.resolve_effective(profile_id, repository_id, principal_id=principal_id)
                data = canonical_json(effective)
                snapshot_id, created_at = new_id(), datetime.now(timezone.utc).isoformat()
                digest = hashlib.sha256(data.encode()).hexdigest()
                await db.execute("INSERT INTO profile_snapshots(id,profile_id,run_id,snapshot_hash,effective_config_json,created_at) VALUES (?,?,?,?,?,?)",
                    (snapshot_id, profile_id, run_id, digest, data, created_at))
                await self.store._insert_event_in_tx(db, run_id=run_id, event_type="profile.snapshot_created",
                    payload={"profile_snapshot_id": snapshot_id, "snapshot_hash": digest})
                row = await (await db.execute("SELECT * FROM profile_snapshots WHERE id=?", (snapshot_id,))).fetchone()
                return self._snapshot(row)

    async def get_snapshot(self, run_id: str, *, principal_id: str) -> ProfileSnapshot:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM profile_snapshots WHERE run_id=?", (run_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Profile snapshot does not exist")
        snapshot = self._snapshot(row)
        await self.workspaces.resolve_repository(snapshot.effective_config["repository"]["id"], principal_id=principal_id)
        return snapshot
