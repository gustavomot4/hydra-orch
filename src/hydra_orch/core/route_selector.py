"""T16/T29 deterministic, auditable route selection, OmniRoute inventory, and next-run account overrides."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import Field, ValidationError, model_validator

from hydra_orch.bridge.omniroute_client import OmniRouteClient, _unknown_quota_payload
from hydra_orch.core.agent_registry import AgentRegistry
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import ContractViolation, ExecutionModel, ExecutorCapability, Identifier, NonEmpty, UtcTimestamp

_NEXT_ACCOUNT_SCOPE_TYPE = "omniroute_next_account"


def _contains_secret_token_or_key(value: str) -> bool:
    return redact_text(value) != value or redact({value: "probe"}) != {value: "probe"}


class RouteCandidate(ExecutionModel):
    route_id: Identifier
    agent_id: Identifier
    model_ref: NonEmpty
    mode: Literal["direct", "gateway"] = "direct"
    priority: int = Field(default=100, ge=0, strict=True)
    enabled: bool = True
    quota_key: Optional[Identifier] = None
    telemetry_attempt_id: Optional[Identifier] = None

    @model_validator(mode="after")
    def safe(self):
        data = self.model_dump(mode="json")
        if redact(data) != data:
            raise ValueError("Route references cannot contain credentials")
        return self


class AccountOverride(ExecutionModel):
    scope_id: NonEmpty
    provider: NonEmpty
    account_id: NonEmpty
    selected_by: NonEmpty
    selected_at: UtcTimestamp
    applies_to: Literal["next_run"] = "next_run"

    @model_validator(mode="after")
    def validate_no_secrets(self) -> AccountOverride:
        data = self.model_dump(mode="json")
        if redact(data) != data:
            raise ValueError("Account overrides cannot contain credentials")
        for field_name in ("scope_id", "provider", "account_id", "selected_by"):
            if _contains_secret_token_or_key(getattr(self, field_name)):
                raise ValueError(f"Account override '{field_name}' cannot contain credentials")
        return self


class RouteDecision(ExecutionModel):
    decision_id: Identifier
    run_id: Identifier
    selected_route: Identifier
    model_ref: NonEmpty
    execution_driver: NonEmpty
    reason: NonEmpty
    fallback_chain: tuple[Identifier, ...]
    candidates_json: NonEmpty
    decision_source: Literal["hydra"] = "hydra"
    timestamp: UtcTimestamp


class RouteSelector:
    def __init__(
        self,
        store: ExecutionStore,
        agents: AgentRegistry,
        metrics: MetricsService,
        *,
        gateway: Optional[OmniRouteClient] = None,
        connection_mode: Literal["disabled", "optional", "required"] = "disabled",
    ):
        if agents.store is not store or metrics.store is not store or connection_mode not in {"disabled", "optional", "required"}:
            raise ValueError("Route services require a shared store and explicit gateway mode")
        self.store, self.agents, self.metrics = store, agents, metrics
        self.gateway, self.connection_mode = gateway, connection_mode

    _QUOTA_KEY_ALIASES: Dict[str, Tuple[str, ...]] = {
        "claude_pro": ("claude_pro", "claude", "anthropic", "claude-code", "claude_code"),
        "claude": ("claude", "claude_pro", "anthropic"),
        "anthropic": ("anthropic", "claude_pro", "claude"),
        "claude-code": ("claude-code", "claude_pro", "claude"),
        "chatgpt_plus": ("chatgpt_plus", "codex", "openai", "chatgpt"),
        "codex": ("codex", "chatgpt_plus", "openai", "chatgpt"),
        "openai": ("openai", "chatgpt_plus", "codex"),
        "chatgpt": ("chatgpt", "chatgpt_plus", "codex"),
        "gemini_pro": ("gemini_pro", "gemini", "agy", "antigravity", "google", "gemini-cli"),
        "gemini": ("gemini", "gemini_pro", "agy", "antigravity", "google"),
        "agy": ("agy", "gemini_pro", "gemini", "antigravity", "google"),
        "antigravity": ("antigravity", "gemini_pro", "agy", "gemini", "google"),
        "google": ("google", "gemini_pro", "gemini", "agy", "antigravity"),
    }

    @classmethod
    def _lookup_quota_observation(
        cls, quota: Dict[str, Any], quota_key: Optional[str]
    ) -> Dict[str, Any]:
        if not quota_key or not isinstance(quota, dict):
            return {}
        direct = quota.get(quota_key)
        if isinstance(direct, dict):
            return direct
        for alias in cls._QUOTA_KEY_ALIASES.get(quota_key.strip().lower(), ()):
            candidate = quota.get(alias)
            if isinstance(candidate, dict):
                return candidate
        return {}

    @classmethod
    def _match_account_override(
        cls,
        candidate: RouteCandidate,
        driver_type: str,
        overrides: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not overrides:
            return None
        model_prefix = candidate.model_ref.split("/", 1)[0] if "/" in candidate.model_ref else None
        for key in (candidate.quota_key, model_prefix, driver_type, candidate.agent_id):
            if not key:
                continue
            if key in overrides:
                return overrides[key]
            for alias in cls._QUOTA_KEY_ALIASES.get(key.strip().lower(), ()):
                if alias in overrides:
                    return overrides[alias]
        return None

    async def select_next_account(
        self,
        scope_id: str,
        provider: str,
        account_id: str,
        *,
        principal_id: str = "operator",
        available_account_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Persist a per-provider account override for future runs without mutating active attempts."""
        for label, raw in (
            ("scope_id", scope_id),
            ("provider", provider),
            ("account_id", account_id),
            ("principal_id", principal_id),
        ):
            if not isinstance(raw, str) or not raw.strip():
                raise ContractViolation("invalid_account_override", f"{label} must be a non-empty string")
            if _contains_secret_token_or_key(raw.strip()):
                raise ContractViolation("secret_in_account_override", f"{label} cannot contain credentials or secrets")

        try:
            override = AccountOverride(
                scope_id=scope_id.strip(),
                provider=provider.strip(),
                account_id=account_id.strip(),
                selected_by=principal_id.strip(),
                selected_at=datetime.now(timezone.utc),
                applies_to="next_run",
            )
        except ValidationError as exc:
            raise ContractViolation("invalid_account_override", f"Invalid account override: {exc}") from exc

        if available_account_ids is not None and override.account_id not in set(available_account_ids):
            raise ContractViolation(
                "account_not_available",
                f"Account '{override.account_id}' is not available for provider '{override.provider}'",
            )

        payload = override.model_dump(mode="json")
        value_json = json.dumps(payload, sort_keys=True)
        now_iso = override.selected_at.isoformat()

        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                existing = await (
                    await db.execute(
                        "SELECT id, version FROM preferences WHERE scope_type = ? AND scope_id = ? AND key = ?",
                        (_NEXT_ACCOUNT_SCOPE_TYPE, override.scope_id, override.provider),
                    )
                ).fetchone()
                if existing is None:
                    version = 1
                    await db.execute(
                        """
                        INSERT INTO preferences (id, scope_type, scope_id, key, value_json, source, version, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 'explicit', 1, ?, ?)
                        """,
                        (
                            new_id(),
                            _NEXT_ACCOUNT_SCOPE_TYPE,
                            override.scope_id,
                            override.provider,
                            value_json,
                            now_iso,
                            now_iso,
                        ),
                    )
                else:
                    version = int(existing["version"]) + 1
                    await db.execute(
                        """
                        UPDATE preferences
                        SET value_json = ?, source = 'explicit', version = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (value_json, version, now_iso, existing["id"]),
                    )

                run_row = await (
                    await db.execute("SELECT id FROM runs WHERE id = ?", (override.scope_id,))
                ).fetchone()
                await self.store._record_command_in_tx(
                    db,
                    scope=_NEXT_ACCOUNT_SCOPE_TYPE,
                    idempotency_key=new_id(),
                    request_hash=self.store.compute_request_hash(payload),
                    run_id=override.scope_id if run_row is not None else None,
                    response_payload={**payload, "version": version},
                )
                if run_row is not None:
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=override.scope_id,
                        event_type="route.selected",
                        payload={"action": "next_account_selected", **payload},
                    )

        return payload

    async def get_next_account_overrides(self, scope_id: str = "default") -> Dict[str, Dict[str, Any]]:
        """Read persisted next-run account overrides for scope_id with 'default' fallback."""
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise ContractViolation("invalid_account_override", "scope_id must be a non-empty string")
        clean_scope = scope_id.strip()
        await self.store.initialize()
        async with self.store._connect() as db:
            if clean_scope == "default":
                rows = await (
                    await db.execute(
                        "SELECT scope_id, key, value_json FROM preferences WHERE scope_type = ? AND scope_id = ? ORDER BY key ASC",
                        (_NEXT_ACCOUNT_SCOPE_TYPE, "default"),
                    )
                ).fetchall()
            else:
                rows = await (
                    await db.execute(
                        """
                        SELECT scope_id, key, value_json
                        FROM preferences
                        WHERE scope_type = ? AND scope_id IN ('default', ?)
                        ORDER BY CASE WHEN scope_id = 'default' THEN 0 ELSE 1 END ASC, key ASC
                        """,
                        (_NEXT_ACCOUNT_SCOPE_TYPE, clean_scope),
                    )
                ).fetchall()

        overrides: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            parsed = AccountOverride.model_validate(json.loads(row["value_json"]))
            overrides[row["key"]] = redact(parsed.model_dump(mode="json"))
        return overrides

    async def gateway_inventory(self, scope_id: str = "default") -> Dict[str, Any]:
        """Return non-secret OmniRoute gateway inventory, quota status, and next-run overrides."""
        overrides = await self.get_next_account_overrides(scope_id)
        unknown_quota = _unknown_quota_payload()
        if self.connection_mode == "disabled" or self.gateway is None:
            return {
                "connection_mode": self.connection_mode,
                "direct_mode_supported": True,
                "available": False,
                "models": [],
                "accounts": [],
                "quota": unknown_quota,
                "next_account_overrides": overrides,
            }

        available = bool(await self.gateway.is_available())
        models: List[Dict[str, Any]] = []
        accounts: List[Dict[str, Any]] = []
        quota: Dict[str, Any] = unknown_quota

        if available:
            raw_quota = await self.gateway.get_quota_status()
            if isinstance(raw_quota, dict):
                quota = redact(raw_quota)
            if hasattr(self.gateway, "list_models"):
                models_resp = await self.gateway.list_models()
                if isinstance(models_resp, dict) and isinstance(models_resp.get("models"), list):
                    models = redact(models_resp["models"])
            if hasattr(self.gateway, "list_accounts"):
                accounts_resp = await self.gateway.list_accounts()
                if isinstance(accounts_resp, dict) and isinstance(accounts_resp.get("accounts"), list):
                    accounts = redact(accounts_resp["accounts"])

        return {
            "connection_mode": self.connection_mode,
            "direct_mode_supported": True,
            "available": available,
            "models": models,
            "accounts": accounts,
            "quota": quota,
            "next_account_overrides": overrides,
        }

    async def select(
        self,
        run_id: str,
        candidates: tuple[RouteCandidate, ...],
        *,
        required_capabilities: tuple[ExecutorCapability, ...] = (ExecutorCapability.WORKSPACE_EXECUTION,),
        unknown_quota: Literal["allow", "reject"] = "allow",
    ) -> RouteDecision:
        if not candidates or len({c.route_id for c in candidates}) != len(candidates) or unknown_quota not in {"allow", "reject"}:
            raise ContractViolation("route_invalid", "Unique route candidates and an explicit uncertainty policy are required")
        await self.store.initialize()
        if await self.store.get_run(run_id) is None:
            raise ContractViolation("resource_not_found", "Run does not exist")
        account_overrides = await self.get_next_account_overrides(run_id)
        need_gateway = self.connection_mode == "required" or any(c.enabled and c.mode == "gateway" for c in candidates)
        available = False
        quota = {"status": "unknown"}
        if self.connection_mode != "disabled" and need_gateway and self.gateway is not None:
            available = await self.gateway.is_available()
            if available:
                quota = await self.gateway.get_quota_status()
        audit, eligible = [], []
        for candidate in candidates:
            entry = {
                "route_id": candidate.route_id,
                "agent_id": candidate.agent_id,
                "model_ref": candidate.model_ref,
                "mode": candidate.mode,
                "priority": candidate.priority,
                "eligible": False,
                "reason": "disabled",
                "quota_status": "unknown",
                "remaining_percent": None,
                "cost_status": "unknown",
                "duration_status": "unknown",
                "observed_cost": None,
                "observed_duration": None,
                "telemetry_attempt_id": candidate.telemetry_attempt_id,
            }
            cost, duration = math.inf, math.inf
            if not candidate.enabled:
                audit.append(entry)
                continue
            if candidate.mode == "gateway" and (self.connection_mode == "disabled" or not available):
                entry["reason"] = "gateway_unavailable"
                audit.append(entry)
                continue
            if candidate.mode == "direct" and self.connection_mode == "required":
                entry["reason"] = "gateway_required"
                audit.append(entry)
                continue
            try:
                resolved = await self.agents.resolve_capabilities(candidate.agent_id, required=required_capabilities)
            except ContractViolation as exc:
                entry["reason"] = exc.code
                audit.append(entry)
                continue
            if candidate.mode == "gateway":
                observation = self._lookup_quota_observation(quota, candidate.quota_key)
                status = observation.get("status", "unknown")
                percent = observation.get("remaining_percent")
                entry.update(
                    quota_status=status,
                    remaining_percent=percent,
                    quota_source=observation.get("source", "not_reported"),
                    quota_observed_at=observation.get("observed_at"),
                )
                if status == "observed" and percent == 0:
                    entry["reason"] = "quota_exhausted"
                    audit.append(entry)
                    continue
                if status != "observed" and unknown_quota == "reject":
                    entry["reason"] = "quota_unknown"
                    audit.append(entry)
                    continue
            if candidate.telemetry_attempt_id:
                attempt = await self.store.get_attempt(candidate.telemetry_attempt_id)
                if (
                    attempt is not None
                    and attempt.run_id == run_id
                    and attempt.model == candidate.model_ref
                    and attempt.executor_id in {candidate.agent_id, resolved.definition.driver_type}
                ):
                    samples = await self.metrics.query(run_id, "attempt", candidate.telemetry_attempt_id)
                    for sample in samples:
                        if sample.kind in {"cost", "duration"}:
                            entry[sample.kind + "_status"] = sample.status
                            entry[sample.kind + "_source"] = sample.source
                            entry[sample.kind + "_observed_at"] = sample.observed_at.isoformat()
                            if sample.status == "observed" and sample.value is not None:
                                entry["observed_" + sample.kind] = sample.value
                                if sample.kind == "cost":
                                    cost = sample.value
                                else:
                                    duration = sample.value
                else:
                    entry["telemetry_reason"] = "uncorrelated_attempt"
            matched_override = self._match_account_override(
                candidate, resolved.definition.driver_type, account_overrides
            )
            if matched_override is not None:
                entry["selected_account_id"] = matched_override["account_id"]
            entry.update(
                eligible=True,
                reason="eligible",
                certificate_sha256=resolved.certificate_sha256,
                execution_driver=resolved.definition.driver_type,
            )
            audit.append(entry)
            eligible.append(((candidate.priority, cost, duration, candidate.route_id), candidate, resolved))
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                if not eligible:
                    reason = "gateway_required_unavailable" if self.connection_mode == "required" and not available else "no_eligible_route"
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="route.rejected",
                        payload={"reason": reason, "candidates": audit},
                    )
                else:
                    eligible.sort(key=lambda item: item[0])
                    _, selected, resolved = eligible[0]
                    decision = RouteDecision(
                        decision_id=new_id(),
                        run_id=run_id,
                        selected_route=selected.route_id,
                        model_ref=selected.model_ref,
                        execution_driver=resolved.definition.driver_type,
                        reason="Eligible routes ordered by explicit priority, observed cost/duration and stable route ID",
                        fallback_chain=tuple(item[1].route_id for item in eligible[1:]),
                        candidates_json=json.dumps(redact(audit), sort_keys=True),
                        timestamp=datetime.now(timezone.utc),
                    )
                    await db.execute(
                        """INSERT INTO route_decisions(id,run_id,candidates_json,selected_route,reason,fallback_chain_json,decision_source,timestamp)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            decision.decision_id,
                            run_id,
                            decision.candidates_json,
                            decision.selected_route,
                            decision.reason,
                            json.dumps(decision.fallback_chain),
                            decision.decision_source,
                            decision.timestamp.isoformat(),
                        ),
                    )
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="route.selected",
                        payload=decision.model_dump(mode="json"),
                    )
        if not eligible:
            raise ContractViolation(reason, "No route passed the configured gateway, certification, capability and quota gates")
        return decision

    async def list_decisions(self, run_id: str):
        await self.store.initialize()
        if await self.store.get_run(run_id) is None:
            raise ContractViolation("resource_not_found", "Run does not exist")
        async with self.store._connect() as db:
            return tuple(
                dict(row)
                for row in await (
                    await db.execute("SELECT * FROM route_decisions WHERE run_id=? ORDER BY timestamp,id", (run_id,))
                ).fetchall()
            )
