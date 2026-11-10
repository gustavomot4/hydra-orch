"""T16 deterministic, auditable route selection using certified eligibility."""

import json
import math
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import Field, model_validator

from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.core.agent_registry import AgentRegistry
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.redaction import redact
from hydra_orch.model import ContractViolation, ExecutionModel, ExecutorCapability, Identifier, NonEmpty, UtcTimestamp


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
        data=self.model_dump(mode="json")
        if redact(data)!=data:
            raise ValueError("Route references cannot contain credentials")
        return self


class RouteDecision(ExecutionModel):
    decision_id: Identifier
    run_id: Identifier
    selected_route: Identifier
    model_ref: NonEmpty
    execution_driver: NonEmpty
    reason: NonEmpty
    fallback_chain: tuple[Identifier,...]
    candidates_json: NonEmpty
    decision_source: Literal["hydra"] = "hydra"
    timestamp: UtcTimestamp


class RouteSelector:
    def __init__(self, store: ExecutionStore, agents: AgentRegistry, metrics: MetricsService, *,
                 gateway: Optional[OmniRouteClient]=None, connection_mode: Literal["disabled","optional","required"]="disabled"):
        if agents.store is not store or metrics.store is not store or connection_mode not in {"disabled","optional","required"}:
            raise ValueError("Route services require a shared store and explicit gateway mode")
        self.store,self.agents,self.metrics=store,agents,metrics
        self.gateway,self.connection_mode=gateway,connection_mode

    async def select(self, run_id: str, candidates: tuple[RouteCandidate,...], *,
                     required_capabilities: tuple[ExecutorCapability,...]=(ExecutorCapability.WORKSPACE_EXECUTION,),
                     unknown_quota: Literal["allow","reject"]="allow") -> RouteDecision:
        if not candidates or len({c.route_id for c in candidates})!=len(candidates) or unknown_quota not in {"allow","reject"}:
            raise ContractViolation("route_invalid","Unique route candidates and an explicit uncertainty policy are required")
        await self.store.initialize()
        if await self.store.get_run(run_id) is None:
            raise ContractViolation("resource_not_found","Run does not exist")
        need_gateway=self.connection_mode=="required" or any(c.enabled and c.mode=="gateway" for c in candidates)
        available=False
        quota={"status":"unknown"}
        if self.connection_mode!="disabled" and need_gateway and self.gateway is not None:
            available=await self.gateway.is_available()
            if available:
                quota=await self.gateway.get_quota_status()
        audit,eligible=[],[]
        for candidate in candidates:
            entry={"route_id":candidate.route_id,"agent_id":candidate.agent_id,"model_ref":candidate.model_ref,
                "mode":candidate.mode,"priority":candidate.priority,"eligible":False,"reason":"disabled",
                "quota_status":"unknown","remaining_percent":None,"cost_status":"unknown","duration_status":"unknown",
                "observed_cost":None,"observed_duration":None,"telemetry_attempt_id":candidate.telemetry_attempt_id}
            cost,duration=math.inf,math.inf
            if not candidate.enabled:
                audit.append(entry)
                continue
            if candidate.mode=="gateway" and (self.connection_mode=="disabled" or not available):
                entry["reason"]="gateway_unavailable"
                audit.append(entry)
                continue
            if candidate.mode=="direct" and self.connection_mode=="required":
                entry["reason"]="gateway_required"
                audit.append(entry)
                continue
            try:
                resolved=await self.agents.resolve_capabilities(candidate.agent_id,required=required_capabilities)
            except ContractViolation as exc:
                entry["reason"]=exc.code
                audit.append(entry)
                continue
            if candidate.mode=="gateway":
                observation=quota.get(candidate.quota_key,{}) if candidate.quota_key else {}
                status=observation.get("status","unknown")
                percent=observation.get("remaining_percent")
                entry.update(quota_status=status,remaining_percent=percent,quota_source=observation.get("source","not_reported"),
                    quota_observed_at=observation.get("observed_at"))
                if status=="observed" and percent==0:
                    entry["reason"]="quota_exhausted"
                    audit.append(entry)
                    continue
                if status!="observed" and unknown_quota=="reject":
                    entry["reason"]="quota_unknown"
                    audit.append(entry)
                    continue
            if candidate.telemetry_attempt_id:
                attempt=await self.store.get_attempt(candidate.telemetry_attempt_id)
                if (attempt is not None and attempt.run_id==run_id and attempt.model==candidate.model_ref
                        and attempt.executor_id in {candidate.agent_id,resolved.definition.driver_type}):
                    samples=await self.metrics.query(run_id,"attempt",candidate.telemetry_attempt_id)
                    for sample in samples:
                        if sample.kind in {"cost","duration"}:
                            entry[sample.kind+"_status"]=sample.status
                            entry[sample.kind+"_source"]=sample.source
                            entry[sample.kind+"_observed_at"]=sample.observed_at.isoformat()
                            if sample.status=="observed" and sample.value is not None:
                                entry["observed_"+sample.kind]=sample.value
                                if sample.kind=="cost":cost=sample.value
                                else:duration=sample.value
                else:
                    entry["telemetry_reason"]="uncorrelated_attempt"
            entry.update(eligible=True,reason="eligible",certificate_sha256=resolved.certificate_sha256,
                execution_driver=resolved.definition.driver_type)
            audit.append(entry)
            eligible.append(((candidate.priority,cost,duration,candidate.route_id),candidate,resolved))
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                if not eligible:
                    reason="gateway_required_unavailable" if self.connection_mode=="required" and not available else "no_eligible_route"
                    await self.store._insert_event_in_tx(db,run_id=run_id,event_type="route.rejected",payload={"reason":reason,"candidates":audit})
                else:
                    eligible.sort(key=lambda item:item[0])
                    _,selected,resolved=eligible[0]
                    decision=RouteDecision(decision_id=new_id(),run_id=run_id,selected_route=selected.route_id,
                        model_ref=selected.model_ref,execution_driver=resolved.definition.driver_type,
                        reason="Eligible routes ordered by explicit priority, observed cost/duration and stable route ID",
                        fallback_chain=tuple(item[1].route_id for item in eligible[1:]),
                        candidates_json=json.dumps(redact(audit),sort_keys=True),timestamp=datetime.now(timezone.utc))
                    await db.execute("""INSERT INTO route_decisions(id,run_id,candidates_json,selected_route,reason,fallback_chain_json,decision_source,timestamp)
                        VALUES (?,?,?,?,?,?,?,?)""",(decision.decision_id,run_id,decision.candidates_json,decision.selected_route,
                        decision.reason,json.dumps(decision.fallback_chain),decision.decision_source,decision.timestamp.isoformat()))
                    await self.store._insert_event_in_tx(db,run_id=run_id,event_type="route.selected",payload=decision.model_dump(mode="json"))
        if not eligible:
            raise ContractViolation(reason,"No route passed the configured gateway, certification, capability and quota gates")
        return decision

    async def list_decisions(self, run_id: str):
        await self.store.initialize()
        if await self.store.get_run(run_id) is None:
            raise ContractViolation("resource_not_found","Run does not exist")
        async with self.store._connect() as db:
            return tuple(dict(row) for row in await (await db.execute(
                "SELECT * FROM route_decisions WHERE run_id=? ORDER BY timestamp,id",(run_id,))).fetchall())
