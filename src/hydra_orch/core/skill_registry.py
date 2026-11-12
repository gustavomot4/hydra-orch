"""T19: registry of skills, MCP servers, and external secret references."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Literal, Mapping, Optional, Sequence
from urllib.parse import urlparse

from pydantic import Field, model_validator

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.discovery import DiscoveryService
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text, redaction_scope
from hydra_orch.model import ContractViolation, ExecutionModel, ExecutorCapability, Identifier, NonEmpty, Sha256, UtcTimestamp

BASE_PERMISSIONS = frozenset({
    "fs:read",
    "fs:write",
    "net:loopback",
    "net:external",
    "process:spawn",
})
_SOURCE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]{0,127}$")
_SECRET_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_PERM_SECRET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_RAW_SECRET_PREFIXES = ("sk-", "ghp_", "github_pat_", "glpat-", "xoxb-", "xoxp-", "xoxa-", "xoxr-", "xoxs-", "akia", "aiza")
_RESERVED_RUNTIME_ENV = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LANG", "LC_ALL",
    "TERM", "SHELL", "PWD", "TMPDIR", "PYTHONUNBUFFERED", "GIT_TERMINAL_PROMPT",
    "HYDRA_WORKER_ISOLATED", "HYDRA_API_TOKEN", "HYDRA_API_TOKEN_HASH",
})
_SENSITIVE_QUERY_KEYS = ("token=", "secret=", "api_key=", "apikey=", "password=", "passwd=", "credential=")


def validate_permission(permission: str) -> str:
    if not isinstance(permission, str) or not permission:
        raise ValueError("Permission must be a non-empty string")
    if permission in BASE_PERMISSIONS:
        return permission
    if permission.startswith("secret:"):
        ref_id = permission[7:]
        if _PERM_SECRET_ID_RE.fullmatch(ref_id):
            return permission
    raise ValueError(f"Unsupported permission '{permission}'")


def validate_source_key(value: str) -> str:
    if not isinstance(value, str) or not _SOURCE_KEY_RE.fullmatch(value):
        raise ValueError("secret_value_rejected: source_key must be an external reference identifier")
    lowered = value.lower()
    if any(lowered.startswith(prefix) for prefix in _RAW_SECRET_PREFIXES):
        raise ValueError("secret_value_rejected: raw secret token prefix is not allowed in source_key")
    if redact_text(value) != value:
        raise ValueError("secret_value_rejected: source_key looks like a raw credential")
    if (
        len(value) >= 24
        and "_" not in value
        and "." not in value
        and any(c.isdigit() for c in value)
        and any(c.islower() for c in value)
        and any(c.isupper() for c in value)
    ):
        raise ValueError("secret_value_rejected: high-entropy literal cannot be used as source_key")
    return value


def _validate_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip() or "\x00" in endpoint:
        raise ValueError("Endpoint must be a non-empty string without NUL")
    if redact_text(endpoint) != endpoint:
        raise ValueError("Endpoint cannot contain embedded credentials")
    parsed = urlparse(endpoint)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Endpoint cannot embed userinfo credentials")
    query_lower = (parsed.query or "").lower()
    if any(marker in query_lower for marker in _SENSITIVE_QUERY_KEYS):
        raise ValueError("Endpoint query cannot embed secret parameters")
    return endpoint


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SecretRef(ExecutionModel):
    secret_id: Identifier = Field(default_factory=new_id)
    secret_name: NonEmpty
    provider_type: Literal["env", "vault", "keyring"]
    source_key: NonEmpty

    @model_validator(mode="after")
    def validate_ref(self):
        if not _SECRET_NAME_RE.fullmatch(self.secret_name):
            raise ValueError("secret_name must be a valid environment identifier")
        validate_source_key(self.source_key)
        return self


class DeclaredTool(ExecutionModel):
    name: NonEmpty
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})

    @model_validator(mode="after")
    def no_secrets(self):
        data = self.model_dump(mode="json")
        if redact(data) != data:
            raise ValueError("Declared tool cannot contain raw credentials")
        return self


class SkillDefinition(ExecutionModel):
    skill_id: Identifier = Field(default_factory=new_id)
    name: NonEmpty
    version: NonEmpty
    manifest_ref: NonEmpty
    discovered_resource_id: Optional[Identifier] = None
    permissions_declared: tuple[str, ...] = ()
    checksum: Sha256
    created_at: Optional[UtcTimestamp] = None

    @model_validator(mode="after")
    def validate_skill(self):
        for perm in self.permissions_declared:
            validate_permission(perm)
        if len(set(self.permissions_declared)) != len(self.permissions_declared):
            raise ValueError("Declared permissions must be unique")
        data = self.model_dump(mode="json")
        data["permissions_declared"] = [
            "secret_ref" if isinstance(p, str) and p.startswith("secret:") else p
            for p in data.get("permissions_declared", [])
        ]
        if redact(data) != data:
            raise ValueError("Skill definition cannot contain raw credentials")
        return self


class McpDefinition(ExecutionModel):
    mcp_id: Identifier = Field(default_factory=new_id)
    server_name: NonEmpty
    transport_type: Literal["stdio", "sse", "websocket"]
    endpoint: NonEmpty
    discovered_resource_id: Optional[Identifier] = None
    secret_ref: Optional[Identifier] = None
    declared_tools: tuple[DeclaredTool, ...] = ()
    permissions: tuple[str, ...] = ()
    created_at: Optional[UtcTimestamp] = None

    @model_validator(mode="after")
    def validate_mcp(self):
        _validate_endpoint(self.endpoint)
        for perm in self.permissions:
            validate_permission(perm)
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("MCP permissions must be unique")
        tool_names = [t.name for t in self.declared_tools]
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("Declared MCP tool names must be unique")
        if self.secret_ref is not None and f"secret:{self.secret_ref}" not in self.permissions:
            raise ValueError("MCP referencing secret_ref must declare matching secret:<id> permission")
        data = self.model_dump(mode="json")
        data["permissions"] = [
            "secret_ref" if isinstance(p, str) and p.startswith("secret:") else p
            for p in data.get("permissions", [])
        ]
        if redact(data) != data:
            raise ValueError("MCP definition cannot contain raw credentials")
        return self


class SecretBundle:
    """In-memory resolved secret values scoped strictly to subprocess spawn."""

    __slots__ = ("_values", "_secret_ids")

    def __init__(self, values: Mapping[str, str], secret_ids: Sequence[str]):
        self._values: dict[str, str] = dict(values)
        self._secret_ids: tuple[str, ...] = tuple(secret_ids)

    def __repr__(self) -> str:
        return f"<SecretBundle count={len(self._values)} [REDACTED]>"

    def __str__(self) -> str:
        return self.__repr__()

    def __reduce__(self):
        raise TypeError("SecretBundle cannot be serialized")

    @property
    def secret_ids(self) -> tuple[str, ...]:
        return self._secret_ids

    def as_allowed_env(self) -> dict[str, str]:
        return dict(self._values)

    def literals(self) -> tuple[str, ...]:
        return tuple(v for v in self._values.values() if v)

    def redaction_scope(self):
        return redaction_scope(self.literals())

    def contains_secret_in_text(self, text: str) -> bool:
        if not text:
            return False
        return any(len(val) >= 4 and val in text for val in self._values.values())


class SkillRegistry:
    """Persistent registry for SecretRef, SkillDefinition, and McpDefinition."""

    def __init__(self, store: ExecutionStore, *, discovery: Optional[DiscoveryService] = None):
        if discovery is not None and discovery.store is not store:
            raise ValueError("SkillRegistry and DiscoveryService must share the canonical store")
        self.store = store
        self.discovery = discovery

    @staticmethod
    def _authorize_principal(principal_id: str) -> None:
        if not principal_id or redact_text(principal_id) != principal_id:
            raise ContractViolation("authorization_denied", "Valid principal_id is required")

    async def _audit(self, db, event: str, principal_id: str, resource_id: str, **details: Any) -> None:
        payload = {"event": event, "principal_id": principal_id, "resource_id": resource_id, **details}
        await self.store._record_command_in_tx(
            db,
            scope="skill_registry",
            idempotency_key=new_id(),
            request_hash=self.store.compute_request_hash(payload),
            response_payload=payload,
        )

    async def _is_revoked(self, db, kind: str, resource_id: str) -> bool:
        row = await (
            await db.execute(
                """SELECT 1 FROM commands
                   WHERE scope='skill_registry'
                     AND json_extract(response_json, '$.event')=?
                     AND json_extract(response_json, '$.resource_id')=?
                   LIMIT 1""",
                (f"{kind}.revoked", resource_id),
            )
        ).fetchone()
        return row is not None

    async def _validate_secret_permissions(self, db, permissions: Sequence[str]) -> None:
        for perm in permissions:
            if perm.startswith("secret:"):
                ref_id = perm[7:]
                row = await (await db.execute("SELECT id FROM secret_refs WHERE id=?", (ref_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"Referenced SecretRef '{ref_id}' does not exist")
                if await self._is_revoked(db, "secret_ref", ref_id):
                    raise ContractViolation("component_revoked", f"Referenced SecretRef '{ref_id}' is revoked")

    async def register_secret_ref(self, ref: SecretRef, *, principal_id: str) -> SecretRef:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "INSERT INTO secret_refs(id, secret_name, provider_type, source_key) VALUES (?,?,?,?)",
                    (ref.secret_id, ref.secret_name, ref.provider_type, ref.source_key),
                )
                await self._audit(
                    db,
                    "secret_ref.registered",
                    principal_id,
                    ref.secret_id,
                    secret_name=ref.secret_name,
                    provider_type=ref.provider_type,
                    ref_hash=_hash_payload(ref.model_dump(mode="json")),
                )
        return ref

    async def create_secret_ref(
        self,
        *,
        secret_name: str,
        provider_type: Literal["env", "vault", "keyring"],
        source_key: str,
        principal_id: str,
        secret_id: Optional[str] = None,
    ) -> SecretRef:
        try:
            ref = SecretRef(
                secret_id=secret_id or new_id(),
                secret_name=secret_name,
                provider_type=provider_type,
                source_key=source_key,
            )
        except ValueError as exc:
            msg = str(exc)
            code = "secret_value_rejected" if "secret_value_rejected" in msg else "invalid_secret_ref"
            raise ContractViolation(code, msg) from exc
        return await self.register_secret_ref(ref, principal_id=principal_id)

    async def get_secret_ref(self, secret_id: str) -> SecretRef:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM secret_refs WHERE id=?", (secret_id,))).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"SecretRef '{secret_id}' does not exist")
            return SecretRef(
                secret_id=row["id"],
                secret_name=row["secret_name"],
                provider_type=row["provider_type"],
                source_key=row["source_key"],
            )

    async def revoke_secret_ref(self, secret_id: str, *, principal_id: str, reason: str = "operator_revoked") -> None:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT id FROM secret_refs WHERE id=?", (secret_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"SecretRef '{secret_id}' does not exist")
                if not await self._is_revoked(db, "secret_ref", secret_id):
                    await self._audit(db, "secret_ref.revoked", principal_id, secret_id, reason=redact_text(reason))

    async def register_skill(self, skill: SkillDefinition, *, principal_id: str) -> SkillDefinition:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        if skill.discovered_resource_id is not None:
            if self.discovery is None:
                raise ContractViolation("component_untrusted", "Discovered skills require an explicit DiscoveryService")
            discovered = await self.discovery.require_approved(skill.discovered_resource_id, principal_id=principal_id)
            if discovered.resource_type != "skill":
                raise ContractViolation("component_untrusted", "Discovered resource type does not match 'skill'")
            if discovered.content_hash != skill.checksum:
                raise ContractViolation("component_untrusted", "Skill checksum does not match approved discovery hash")
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._validate_secret_permissions(db, skill.permissions_declared)
                created_at = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    """INSERT INTO skill_definitions(
                           id, name, version, manifest_ref, discovered_resource_id,
                           permissions_declared_json, checksum, created_at
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        skill.skill_id,
                        skill.name,
                        skill.version,
                        skill.manifest_ref,
                        skill.discovered_resource_id,
                        json.dumps(list(skill.permissions_declared)),
                        skill.checksum,
                        created_at,
                    ),
                )
                await self._audit(
                    db,
                    "skill.registered",
                    principal_id,
                    skill.skill_id,
                    checksum=skill.checksum,
                    discovered_resource_id=skill.discovered_resource_id,
                )
                return SkillDefinition.model_validate({**skill.model_dump(mode="json"), "created_at": created_at})

    async def get_skill(self, skill_id: str) -> SkillDefinition:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM skill_definitions WHERE id=?", (skill_id,))).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"Skill '{skill_id}' does not exist")
            return SkillDefinition(
                skill_id=row["id"],
                name=row["name"],
                version=row["version"],
                manifest_ref=row["manifest_ref"],
                discovered_resource_id=row["discovered_resource_id"],
                permissions_declared=tuple(json.loads(row["permissions_declared_json"])),
                checksum=row["checksum"],
                created_at=row["created_at"],
            )

    async def revoke_skill(self, skill_id: str, *, principal_id: str, reason: str = "operator_revoked") -> None:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT id FROM skill_definitions WHERE id=?", (skill_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"Skill '{skill_id}' does not exist")
                if not await self._is_revoked(db, "skill", skill_id):
                    await self._audit(db, "skill.revoked", principal_id, skill_id, reason=redact_text(reason))

    async def register_mcp(self, mcp: McpDefinition, *, principal_id: str) -> McpDefinition:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        if mcp.discovered_resource_id is not None:
            if self.discovery is None:
                raise ContractViolation("component_untrusted", "Discovered MCPs require an explicit DiscoveryService")
            discovered = await self.discovery.require_approved(mcp.discovered_resource_id, principal_id=principal_id)
            if discovered.resource_type != "mcp":
                raise ContractViolation("component_untrusted", "Discovered resource type does not match 'mcp'")
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._validate_secret_permissions(db, mcp.permissions)
                created_at = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    """INSERT INTO mcp_definitions(
                           id, server_name, transport_type, endpoint, discovered_resource_id,
                           secret_ref, declared_tools_json, permissions_json, created_at
                       ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        mcp.mcp_id,
                        mcp.server_name,
                        mcp.transport_type,
                        mcp.endpoint,
                        mcp.discovered_resource_id,
                        mcp.secret_ref,
                        json.dumps([t.model_dump(mode="json") for t in mcp.declared_tools]),
                        json.dumps(list(mcp.permissions)),
                        created_at,
                    ),
                )
                await self._audit(
                    db,
                    "mcp.registered",
                    principal_id,
                    mcp.mcp_id,
                    transport_type=mcp.transport_type,
                    discovered_resource_id=mcp.discovered_resource_id,
                    def_hash=_hash_payload(mcp.model_dump(mode="json")),
                )
                return McpDefinition.model_validate({**mcp.model_dump(mode="json"), "created_at": created_at})

    async def get_mcp(self, mcp_id: str) -> McpDefinition:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM mcp_definitions WHERE id=?", (mcp_id,))).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"MCP '{mcp_id}' does not exist")
            return McpDefinition(
                mcp_id=row["id"],
                server_name=row["server_name"],
                transport_type=row["transport_type"],
                endpoint=row["endpoint"],
                discovered_resource_id=row["discovered_resource_id"],
                secret_ref=row["secret_ref"],
                declared_tools=tuple(DeclaredTool.model_validate(t) for t in json.loads(row["declared_tools_json"])),
                permissions=tuple(json.loads(row["permissions_json"])),
                created_at=row["created_at"],
            )

    async def revoke_mcp(self, mcp_id: str, *, principal_id: str, reason: str = "operator_revoked") -> None:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT id FROM mcp_definitions WHERE id=?", (mcp_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"MCP '{mcp_id}' does not exist")
                if not await self._is_revoked(db, "mcp", mcp_id):
                    await self._audit(db, "mcp.revoked", principal_id, mcp_id, reason=redact_text(reason))

    async def verify_skill_active(self, skill_id: str, *, principal_id: str) -> SkillDefinition:
        skill = await self.get_skill(skill_id)
        async with self.store._connect() as db:
            if await self._is_revoked(db, "skill", skill_id):
                raise ContractViolation("component_revoked", f"Skill '{skill_id}' has been revoked")
            await self._validate_secret_permissions(db, skill.permissions_declared)
        if skill.discovered_resource_id is not None:
            if self.discovery is None:
                raise ContractViolation("component_untrusted", "Discovered skills require an explicit DiscoveryService")
            discovered = await self.discovery.require_approved(skill.discovered_resource_id, principal_id=principal_id)
            if discovered.content_hash != skill.checksum:
                raise ContractViolation("component_untrusted", "Skill checksum no longer matches approved discovery hash")
        return skill

    async def verify_mcp_active(self, mcp_id: str, *, principal_id: str) -> McpDefinition:
        mcp = await self.get_mcp(mcp_id)
        async with self.store._connect() as db:
            if await self._is_revoked(db, "mcp", mcp_id):
                raise ContractViolation("component_revoked", f"MCP '{mcp_id}' has been revoked")
            await self._validate_secret_permissions(db, mcp.permissions)
        if mcp.discovered_resource_id is not None:
            if self.discovery is None:
                raise ContractViolation("component_untrusted", "Discovered MCPs require an explicit DiscoveryService")
            await self.discovery.require_approved(mcp.discovered_resource_id, principal_id=principal_id)
        return mcp

    async def verify_secret_ref_active(self, secret_id: str) -> SecretRef:
        ref = await self.get_secret_ref(secret_id)
        async with self.store._connect() as db:
            if await self._is_revoked(db, "secret_ref", secret_id):
                raise ContractViolation("component_revoked", f"SecretRef '{secret_id}' has been revoked")
        return ref


class SecretResolver:
    """Resolves SecretRef references exclusively in memory right before subprocess spawn."""

    def __init__(self, registry: SkillRegistry, *, env_source: Optional[Mapping[str, str]] = None):
        self.registry = registry
        self._env_source = env_source

    async def resolve(self, secret_ids: Sequence[str], *, principal_id: str) -> SecretBundle:
        SkillRegistry._authorize_principal(principal_id)
        unique_ids = tuple(dict.fromkeys(secret_ids))
        resolved: dict[str, str] = {}
        env_map = os.environ if self._env_source is None else self._env_source
        for secret_id in unique_ids:
            ref = await self.registry.verify_secret_ref_active(secret_id)
            if ref.secret_name.upper() in _RESERVED_RUNTIME_ENV or ref.secret_name.upper().startswith(("LC_", "XDG_")):
                raise ContractViolation(
                    "invalid_env_var",
                    f"Secret target variable '{ref.secret_name}' collides with reserved runtime environment",
                )
            if ref.provider_type in ("vault", "keyring"):
                raise ContractViolation(
                    "secret_provider_unavailable",
                    f"Secret provider '{ref.provider_type}' is not available in this runtime",
                )
            if ref.source_key not in env_map:
                raise ContractViolation(
                    "secret_unavailable",
                    f"Referenced environment secret '{ref.source_key}' is not available",
                )
            resolved[ref.secret_name] = str(env_map[ref.source_key])
        return SecretBundle(resolved, unique_ids)


async def validate_profile_component(
    db,
    *,
    kind: Literal["skill", "mcp"],
    ref: str,
    row: Mapping[str, Any],
    required_capabilities: Sequence[Any],
) -> None:
    """Validate that a skill or MCP row is not revoked, its SecretRefs are active, and permissions fit."""
    revoked = await (
        await db.execute(
            "SELECT 1 FROM commands WHERE scope='skill_registry' "
            "AND json_extract(response_json,'$.event')=? "
            "AND json_extract(response_json,'$.resource_id')=? LIMIT 1",
            (f"{kind}.revoked", ref),
        )
    ).fetchone()
    if revoked is not None:
        raise ContractViolation("component_revoked", f"Profile {kind} '{ref}' has been revoked")

    perm_col = "permissions_declared_json" if kind == "skill" else "permissions_json"
    perms = json.loads(row[perm_col] or "[]")
    if "net:external" in perms and ExecutorCapability.NETWORK_ISOLATION in required_capabilities:
        raise ContractViolation(
            "capability_mismatch",
            f"Component '{ref}' requires net:external under network_isolation",
        )
    for perm in perms:
        if isinstance(perm, str) and perm.startswith("secret:"):
            sec_id = perm[7:]
            sec_rev = await (
                await db.execute(
                    "SELECT 1 FROM commands WHERE scope='skill_registry' "
                    "AND json_extract(response_json,'$.event')='secret_ref.revoked' "
                    "AND json_extract(response_json,'$.resource_id')=? LIMIT 1",
                    (sec_id,),
                )
            ).fetchone()
            if sec_rev is not None:
                raise ContractViolation(
                    "component_revoked",
                    f"SecretRef '{sec_id}' referenced by {kind} '{ref}' has been revoked",
                )
    if kind == "mcp" and row["secret_ref"]:
        sec_rev = await (
            await db.execute(
                "SELECT 1 FROM commands WHERE scope='skill_registry' "
                "AND json_extract(response_json,'$.event')='secret_ref.revoked' "
                "AND json_extract(response_json,'$.resource_id')=? LIMIT 1",
                (row["secret_ref"],),
            )
        ).fetchone()
        if sec_rev is not None:
            raise ContractViolation(
                "component_revoked",
                f"SecretRef '{row['secret_ref']}' referenced by mcp '{ref}' has been revoked",
            )
