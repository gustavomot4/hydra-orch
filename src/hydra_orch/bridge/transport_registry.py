"""T22: Certified transport registry, target validation, and redacted health checks."""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import platform
import re
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from hydra_orch.bridge.ssh_tunnel import normalize_sha256_fingerprint
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import (
    ContractViolation,
    ExecutionModel,
    Identifier,
    NonEmpty,
    UtcTimestamp,
)

TransportType = Literal["local", "ssh", "ide", "cdp", "remote"]
HealthStatus = Literal["unknown", "healthy", "degraded", "unreachable"]
SupportedPlatform = Literal["Linux", "Windows", "Darwin"]

COMMON_CERTIFICATION_CHECKS = frozenset({"target_identity", "healthcheck"})
REQUIRED_CHECKS_BY_TYPE: Dict[str, frozenset[str]] = {
    "local": COMMON_CERTIFICATION_CHECKS,
    "ssh": COMMON_CERTIFICATION_CHECKS | frozenset({"host_key_verification", "session_isolation"}),
    "ide": COMMON_CERTIFICATION_CHECKS,
    "cdp": COMMON_CERTIFICATION_CHECKS | frozenset({"target_page_validation"}),
    "remote": COMMON_CERTIFICATION_CHECKS,
}

_RAW_SECRET_PREFIXES = (
    "sk-",
    "ghp_",
    "github_pat_",
    "glpat-",
    "xoxb-",
    "xoxp-",
    "xoxa-",
    "xoxr-",
    "xoxs-",
    "akia",
    "aiza",
)
_SENSITIVE_QUERY_KEYS = (
    "token=",
    "secret=",
    "api_key=",
    "apikey=",
    "password=",
    "passwd=",
    "credential=",
    "auth=",
)
_VALID_HEALTH_STATUSES = frozenset({"unknown", "healthy", "degraded", "unreachable"})
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _validate_target_identity(value: str) -> str:
    """Reject empty strings, control chars, userinfo credentials, and embedded secrets."""
    if not isinstance(value, str):
        raise ValueError("target_identity must be a string")
    candidate = value.strip()
    if not candidate or candidate != value or _CONTROL_CHARS_RE.search(candidate):
        raise ValueError("target_identity must be a clean non-empty string without control characters")
    if any(ch.isspace() for ch in candidate):
        raise ValueError("target_identity cannot contain whitespace")
    if redact_text(candidate) != candidate:
        raise ValueError("target_identity cannot embed secrets or credentials")
    lowered = candidate.lower()
    if any(lowered.startswith(prefix) for prefix in _RAW_SECRET_PREFIXES):
        raise ValueError("target_identity cannot contain raw secret tokens")

    parsed = urlsplit(candidate)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target_identity cannot contain URL userinfo credentials")
    if "://" not in candidate and not candidate.startswith("/") and "@" in candidate:
        authority_part = candidate.split("/", 1)[0]
        if "@" in authority_part:
            authority = urlsplit(f"//{authority_part}")
            if authority.username is not None or authority.password is not None:
                raise ValueError("target_identity cannot contain userinfo credentials")
    query_lower = (parsed.query or "").lower()
    if any(marker in query_lower for marker in _SENSITIVE_QUERY_KEYS):
        raise ValueError("target_identity query cannot embed secret parameters")
    return candidate


def _normalize_url_identity(value: str) -> Optional[Tuple[str, str, str, str]]:
    if "://" not in value:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{host}{port}"
    path = parsed.path or "/"
    return scheme, netloc, path, parsed.query


def _cdp_identities_match(expected: str, observed: str) -> bool:
    """Strict CDP target comparison; never falls back to an unrelated origin or page."""
    exp_clean = expected.strip()
    obs_clean = observed.strip()
    if not exp_clean or not obs_clean:
        return False

    exp_url = _normalize_url_identity(exp_clean)
    obs_url = _normalize_url_identity(obs_clean)
    if exp_url is not None and obs_url is not None:
        exp_scheme, exp_netloc, exp_path, exp_query = exp_url
        obs_scheme, obs_netloc, obs_path, obs_query = obs_url
        if exp_scheme != obs_scheme or exp_netloc != obs_netloc:
            return False
        if exp_query and exp_query != obs_query:
            return False
        if exp_path == "/":
            return True
        if obs_path == exp_path:
            return True
        prefix = exp_path.rstrip("/") + "/"
        return obs_path.startswith(prefix)

    return exp_clean == obs_clean


def _ssh_identities_match(expected: str, observed: str) -> bool:
    exp_clean = expected.strip()
    obs_clean = observed.strip()
    if exp_clean.startswith("SHA256:") or obs_clean.startswith("SHA256:"):
        try:
            return normalize_sha256_fingerprint(exp_clean) == normalize_sha256_fingerprint(obs_clean)
        except ContractViolation:
            return False
    return exp_clean.lower() == obs_clean.lower()


def _generic_identities_match(expected: str, observed: str) -> bool:
    exp_clean = expected.strip()
    obs_clean = observed.strip()
    exp_url = _normalize_url_identity(exp_clean)
    obs_url = _normalize_url_identity(obs_clean)
    if exp_url is not None and obs_url is not None:
        return exp_url == obs_url
    return exp_clean == obs_clean


class TransportDefinition(ExecutionModel):
    """Registered transport endpoint metadata (always starts uncertified)."""

    transport_id: Identifier = Field(default_factory=new_id)
    type: TransportType
    target_identity: NonEmpty
    capabilities: Union[Tuple[NonEmpty, ...], Dict[str, Any]] = ()
    is_certified: bool = False
    created_at: Optional[UtcTimestamp] = None

    @property
    def id(self) -> str:
        return self.transport_id

    @field_validator("target_identity")
    @classmethod
    def check_target_identity(cls, value: str) -> str:
        return _validate_target_identity(value)

    @model_validator(mode="after")
    def check_capabilities_clean(self) -> TransportDefinition:
        if isinstance(self.capabilities, tuple):
            if len(set(self.capabilities)) != len(self.capabilities):
                raise ValueError("Transport capabilities must be unique")
        data = self.model_dump(mode="json")
        if redact(data) != data:
            raise ValueError("TransportDefinition cannot embed raw credentials")
        return self


class TransportHealth(ExecutionModel):
    """Typed healthcheck sample stored in transport_health."""

    health_id: Identifier = Field(default_factory=new_id)
    transport_id: Identifier
    status: HealthStatus = "unknown"
    last_check_at: Optional[UtcTimestamp] = None
    error_detail: Optional[str] = None

    @property
    def id(self) -> str:
        return self.health_id

    @field_validator("error_detail")
    @classmethod
    def sanitize_error_detail(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return redact_text(value)


class TransportCertificationReport(ExecutionModel):
    """Explicit operator attestation report validating transport type, OS, version, target/fingerprint, and checks."""

    transport_id: Identifier
    transport_type: TransportType
    platform: SupportedPlatform
    version: NonEmpty
    target_identity: NonEmpty
    fingerprint: Optional[NonEmpty] = None
    passed_checks: Tuple[NonEmpty, ...]
    simulated: Literal[False] = False
    issued_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("target_identity")
    @classmethod
    def check_target_identity(cls, value: str) -> str:
        return _validate_target_identity(value)

    @field_validator("fingerprint")
    @classmethod
    def check_fingerprint(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return normalize_sha256_fingerprint(value)


class TargetValidation(ExecutionModel):
    """Typed confirmation that an observed endpoint matches the registered transport target."""

    transport_id: Identifier
    transport_type: TransportType
    expected_identity: NonEmpty
    observed_identity: NonEmpty
    matched: Literal[True] = True
    validated_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    clean = value.replace("Z", "+00:00")
    if " " in clean and "T" not in clean:
        clean = clean.replace(" ", "T", 1)
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TransportRegistry:
    """Persistent registry for transport definitions, explicit certifications, target checks, and health samples."""

    def __init__(self, store: ExecutionStore):
        self.store = store

    @staticmethod
    def _row_to_definition(row: Any) -> TransportDefinition:
        raw_caps = json.loads(row["capabilities_json"])
        capabilities: Union[Tuple[str, ...], Dict[str, Any]]
        if isinstance(raw_caps, list):
            capabilities = tuple(raw_caps)
        elif isinstance(raw_caps, dict):
            capabilities = raw_caps
        else:
            capabilities = ()
        return TransportDefinition(
            transport_id=row["id"],
            type=row["type"],
            target_identity=row["target_identity"],
            capabilities=capabilities,
            is_certified=bool(row["is_certified"]),
            created_at=_parse_iso_timestamp(row["created_at"]),
        )

    @staticmethod
    def _row_to_health(row: Any) -> TransportHealth:
        return TransportHealth(
            health_id=row["id"],
            transport_id=row["transport_id"],
            status=row["status"],
            last_check_at=_parse_iso_timestamp(row["last_check_at"]),
            error_detail=row["error_detail"],
        )

    async def register_transport(self, definition: TransportDefinition) -> TransportDefinition:
        """Persist a new TransportDefinition always starting uncertified (is_certified=False)."""
        _validate_target_identity(definition.target_identity)
        created_at = definition.created_at or datetime.now(timezone.utc)
        persisted = TransportDefinition(
            transport_id=definition.transport_id,
            type=definition.type,
            target_identity=definition.target_identity,
            capabilities=definition.capabilities,
            is_certified=False,
            created_at=created_at,
        )
        caps_payload = (
            list(persisted.capabilities)
            if isinstance(persisted.capabilities, tuple)
            else persisted.capabilities
        )
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO transport_definitions
                        (id, type, target_identity, capabilities_json, is_certified, created_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                    """,
                    (
                        persisted.transport_id,
                        persisted.type,
                        persisted.target_identity,
                        json.dumps(caps_payload, sort_keys=True),
                        created_at.isoformat(),
                    ),
                )
                await self.store._record_command_in_tx(
                    db,
                    scope="transport",
                    idempotency_key=f"register:{persisted.transport_id}:{new_id()}",
                    request_hash=self.store.compute_request_hash(persisted),
                    response_payload=redact(
                        {
                            "event": "transport.registered",
                            "transport_id": persisted.transport_id,
                            "type": persisted.type,
                            "target_identity": persisted.target_identity,
                            "is_certified": False,
                        }
                    ),
                )
        return persisted

    async def register(self, definition: TransportDefinition) -> TransportDefinition:
        """Alias for register_transport matching the class-diagram interface."""
        return await self.register_transport(definition)

    async def get_transport(self, transport_id: str) -> TransportDefinition:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute("SELECT * FROM transport_definitions WHERE id = ?", (transport_id,))
            ).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", f"Transport '{transport_id}' does not exist")
        return self._row_to_definition(row)

    async def list_transports(self, *, certified_only: bool = False) -> Tuple[TransportDefinition, ...]:
        await self.store.initialize()
        query = "SELECT * FROM transport_definitions"
        if certified_only:
            query += " WHERE is_certified = 1"
        query += " ORDER BY id ASC"
        async with self.store._connect() as db:
            rows = await (await db.execute(query)).fetchall()
        return tuple(self._row_to_definition(row) for row in rows)

    async def certify_transport(
        self,
        transport_id: str,
        report: TransportCertificationReport,
        *,
        principal_id: str,
        platform_name: Optional[str] = None,
    ) -> str:
        """Explicitly certify a transport from a validated non-simulated report with audit logging."""
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ContractViolation("authorization_denied", "Explicit operator attestation is required")
        definition = await self.get_transport(transport_id)

        if report.simulated is not False:
            raise ContractViolation("certification_invalid", "Simulated reports cannot certify transports")
        if report.transport_id != definition.transport_id or report.transport_type != definition.type:
            raise ContractViolation(
                "certification_invalid",
                "Certification report does not match transport ID and type",
            )
        if report.target_identity != definition.target_identity:
            raise ContractViolation(
                "certification_invalid",
                "Certification report target_identity does not match registered transport",
            )

        expected_os = platform_name or platform.system()
        if report.platform != expected_os:
            raise ContractViolation(
                "certification_invalid",
                f"Certification report platform '{report.platform}' does not match expected OS '{expected_os}'",
            )

        required_checks = REQUIRED_CHECKS_BY_TYPE[definition.type]
        if not required_checks <= set(report.passed_checks):
            missing = sorted(required_checks - set(report.passed_checks))
            raise ContractViolation(
                "certification_invalid",
                f"Certification report is missing required checks for '{definition.type}': {missing}",
            )

        if definition.type == "ssh":
            if report.fingerprint is None:
                raise ContractViolation(
                    "certification_invalid",
                    "SSH transport certification requires a canonical SHA256 host key fingerprint",
                )
            if definition.target_identity.startswith("SHA256:"):
                if normalize_sha256_fingerprint(definition.target_identity) != report.fingerprint:
                    raise ContractViolation(
                        "certification_invalid",
                        "SSH report fingerprint diverges from registered target_identity fingerprint",
                    )

        certificate_id = new_id()
        audit_payload = redact(
            {
                "event": "transport.certified",
                "certificate_id": certificate_id,
                "transport_id": definition.transport_id,
                "transport_type": definition.type,
                "platform": report.platform,
                "version": report.version,
                "target_identity": definition.target_identity,
                "fingerprint": report.fingerprint,
                "passed_checks": list(report.passed_checks),
                "principal_id": principal_id.strip(),
                "issued_at": report.issued_at.isoformat(),
            }
        )
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE transport_definitions SET is_certified = 1 WHERE id = ?",
                    (definition.transport_id,),
                )
                await self.store._record_command_in_tx(
                    db,
                    scope="transport",
                    idempotency_key=f"certify:{certificate_id}",
                    request_hash=self.store.compute_request_hash(report),
                    response_payload=audit_payload,
                )
        return certificate_id

    async def revoke_certification(
        self,
        transport_id: str,
        *,
        principal_id: str,
        reason: str = "revoked_by_operator",
    ) -> str:
        """Revoke transport certification immediately and write an immutable audit entry."""
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ContractViolation("authorization_denied", "Explicit operator principal_id is required")
        definition = await self.get_transport(transport_id)
        revocation_id = new_id()
        audit_payload = redact(
            {
                "event": "transport.certification_revoked",
                "revocation_id": revocation_id,
                "transport_id": definition.transport_id,
                "transport_type": definition.type,
                "principal_id": principal_id.strip(),
                "reason": redact_text(reason.strip() or "revoked_by_operator"),
            }
        )
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    "UPDATE transport_definitions SET is_certified = 0 WHERE id = ?",
                    (definition.transport_id,),
                )
                await self.store._record_command_in_tx(
                    db,
                    scope="transport",
                    idempotency_key=f"revoke:{revocation_id}",
                    request_hash=self.store.compute_request_hash(
                        {"transport_id": definition.transport_id, "reason": reason}
                    ),
                    response_payload=audit_payload,
                )
        return revocation_id

    async def _latest_certification_event(self, transport_id: str) -> Optional[Dict[str, Any]]:
        async with self.store._connect() as db:
            rows = await (
                await db.execute(
                    "SELECT response_json FROM commands WHERE scope = 'transport' ORDER BY rowid DESC"
                )
            ).fetchall()
        for row in rows:
            raw = row["response_json"]
            if not raw:
                continue
            payload = json.loads(raw)
            if payload.get("transport_id") != transport_id:
                continue
            event = payload.get("event")
            if event in {"transport.certified", "transport.certification_revoked"}:
                return payload
        return None

    async def require_certified(
        self,
        transport_id: str,
        *,
        strict: bool = True,
        production_mode: bool = True,
        platform_name: Optional[str] = None,
    ) -> TransportDefinition:
        """Verify that a transport is explicitly certified for production/strict execution."""
        definition = await self.get_transport(transport_id)
        if not strict and not production_mode:
            return definition

        if not definition.is_certified:
            raise ContractViolation(
                "transport_uncertified",
                f"Transport '{transport_id}' ({definition.type}) is not certified",
            )

        expected_os = platform_name or platform.system()
        latest = await self._latest_certification_event(transport_id)
        if (
            latest is None
            or latest.get("event") != "transport.certified"
            or latest.get("transport_type") != definition.type
            or latest.get("target_identity") != definition.target_identity
            or latest.get("platform") != expected_os
        ):
            raise ContractViolation(
                "transport_uncertified",
                f"Transport '{transport_id}' lacks a valid certification audit record for '{expected_os}'",
            )
        return definition

    async def assert_target(
        self,
        transport_id: str,
        observed_identity: str,
        *,
        strict: bool = False,
        production_mode: bool = False,
        platform_name: Optional[str] = None,
    ) -> TargetValidation:
        """Fail observably with transport_target_mismatch when observed target diverges."""
        definition = await self.get_transport(transport_id)
        if strict or production_mode:
            await self.require_certified(
                transport_id,
                strict=strict,
                production_mode=production_mode,
                platform_name=platform_name,
            )

        if not isinstance(observed_identity, str) or not observed_identity.strip():
            raise ContractViolation(
                "transport_target_mismatch",
                f"Observed target for transport '{transport_id}' is empty",
            )
        obs = observed_identity.strip()
        if definition.type == "cdp":
            matched = _cdp_identities_match(definition.target_identity, obs)
        elif definition.type == "ssh":
            matched = _ssh_identities_match(definition.target_identity, obs)
        else:
            matched = _generic_identities_match(definition.target_identity, obs)

        if not matched:
            raise ContractViolation(
                "transport_target_mismatch",
                redact_text(
                    f"Target mismatch for transport '{transport_id}' ({definition.type}): "
                    f"expected '{definition.target_identity}', observed '{obs}'"
                ),
            )
        return TargetValidation(
            transport_id=definition.transport_id,
            transport_type=definition.type,
            expected_identity=definition.target_identity,
            observed_identity=obs,
        )

    @staticmethod
    def select_cdp_target(
        expected_target: str,
        pages: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        """Select a CDP page strictly matching expected_target; never picks a random fallback page."""
        if not isinstance(expected_target, str) or not expected_target.strip():
            raise ContractViolation(
                "transport_target_mismatch",
                "CDP target selection requires an explicit non-empty expected_target",
            )
        for page in pages:
            if page.get("type") != "page":
                continue
            ws_url = page.get("webSocketDebuggerUrl")
            page_url = page.get("url")
            if not ws_url or not isinstance(page_url, str):
                continue
            if _cdp_identities_match(expected_target, page_url):
                return page
        raise ContractViolation(
            "transport_target_mismatch",
            redact_text(f"No CDP page matched expected target '{expected_target}'"),
        )

    async def select_cdp_target_for(
        self,
        transport_id: str,
        pages: Sequence[Mapping[str, Any]],
        *,
        strict: bool = False,
        production_mode: bool = False,
        platform_name: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Select a matching CDP page for a registered CDP transport without random fallback."""
        definition = await self.get_transport(transport_id)
        if definition.type != "cdp":
            raise ContractViolation(
                "transport_type_mismatch",
                f"Transport '{transport_id}' has type '{definition.type}', expected 'cdp'",
            )
        if strict or production_mode:
            await self.require_certified(
                transport_id,
                strict=strict,
                production_mode=production_mode,
                platform_name=platform_name,
            )
        return self.select_cdp_target(definition.target_identity, pages)

    async def check_health(
        self,
        transport_id: str,
        *,
        probe: Optional[Callable[[TransportDefinition], Any]] = None,
    ) -> TransportHealth:
        """Execute an optional probe and persist a typed, redacted sample in transport_health."""
        definition = await self.get_transport(transport_id)
        checked_at = datetime.now(timezone.utc)
        status: HealthStatus = "unknown"
        error_detail: Optional[str] = None

        if probe is None:
            status = "unknown"
            error_detail = "No health probe provided"
        else:
            try:
                raw_result = probe(definition)
                if inspect.isawaitable(raw_result):
                    raw_result = await raw_result
                status, error_detail = self._interpret_probe_result(raw_result)
            except Exception as exc:
                status = "unreachable"
                detail = redact_text(str(exc))
                error_detail = detail or type(exc).__name__

        sample = TransportHealth(
            health_id=new_id(),
            transport_id=definition.transport_id,
            status=status,
            last_check_at=checked_at,
            error_detail=redact_text(error_detail) if error_detail is not None else None,
        )
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO transport_health (id, transport_id, status, last_check_at, error_detail)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        sample.health_id,
                        sample.transport_id,
                        sample.status,
                        checked_at.isoformat(),
                        sample.error_detail,
                    ),
                )
        return sample

    @staticmethod
    def _interpret_probe_result(result: Any) -> Tuple[HealthStatus, Optional[str]]:
        if isinstance(result, TransportHealth):
            return result.status, result.error_detail
        if isinstance(result, bool):
            return ("healthy", None) if result else ("unreachable", "Health probe returned False")
        if isinstance(result, str):
            if result in _VALID_HEALTH_STATUSES:
                return result, None  # type: ignore[return-value]
            return "unknown", f"Unsupported health status '{redact_text(result)}'"
        if isinstance(result, Mapping):
            raw_status = result.get("status", "unknown")
            raw_error = result.get("error_detail")
            err = redact_text(str(raw_error)) if raw_error is not None else None
            if raw_status in _VALID_HEALTH_STATUSES:
                return raw_status, err  # type: ignore[return-value]
            return "unknown", err or f"Unsupported health status '{redact_text(str(raw_status))}'"
        return "unknown", f"Unsupported health probe result type: {type(result).__name__}"

    async def get_latest_health(self, transport_id: str) -> Optional[TransportHealth]:
        await self.get_transport(transport_id)
        async with self.store._connect() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM transport_health WHERE transport_id = ? ORDER BY rowid DESC LIMIT 1",
                    (transport_id,),
                )
            ).fetchone()
        return self._row_to_health(row) if row is not None else None

    async def list_health_history(self, transport_id: str) -> Tuple[TransportHealth, ...]:
        await self.get_transport(transport_id)
        async with self.store._connect() as db:
            rows = await (
                await db.execute(
                    "SELECT * FROM transport_health WHERE transport_id = ? ORDER BY rowid ASC",
                    (transport_id,),
                )
            ).fetchall()
        return tuple(self._row_to_health(row) for row in rows)
