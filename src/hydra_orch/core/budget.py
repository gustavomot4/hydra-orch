"""T28 budget governance (RF29 / RT29): caps, 80% alert, 100% freeze, and operator extension."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import math
from typing import Any, Optional, Tuple
from pydantic import Field

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.metrics import UNITS, MetricAggregate, MetricSample, MetricStatus, MetricsService
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import (
    BudgetPolicy,
    ContractViolation,
    ExecutionModel,
    Identifier,
    NonEmpty,
    RunSpec,
    RunStatus,
    UtcTimestamp,
    transition_status,
)

BudgetPolicyState = str  # 'active' | 'alerted' | 'frozen' | 'exhausted'
_VALID_POLICY_STATES = {"active", "alerted", "frozen", "exhausted"}

# Uniform specification table for the four budget dimensions.
_DIMENSION_SPECS: Tuple[Tuple[str, str, str, bool], ...] = (
    ("usd", "max_usd", "cost", False),
    ("tokens_in", "max_tokens_in", "tokens_in", True),
    ("tokens_out", "max_tokens_out", "tokens_out", True),
    ("wall_seconds", "max_wall_seconds", "duration", False),
)


class BudgetDimensionReport(ExecutionModel):
    """Per-dimension consumption snapshot preserving unknown provenance."""

    dimension: str
    limit: Optional[float] = None
    current: Optional[float] = None
    known_subtotal: Optional[float] = None
    pct_used: Optional[float] = None
    status: MetricStatus = "unknown"
    sources: tuple[str, ...] = ()
    triggered_alert: bool = False
    triggered_freeze: bool = False


class BudgetStatus(ExecutionModel):
    """Auditable budget status for a run; absent telemetry never becomes zero."""

    policy_id: Identifier
    run_id: Identifier
    max_usd: Optional[float] = None
    max_tokens_in: Optional[int] = None
    max_tokens_out: Optional[int] = None
    max_wall_seconds: Optional[int] = None
    alert_threshold_pct: float
    current_usd: Optional[float] = None
    current_tokens_in: Optional[int] = None
    current_tokens_out: Optional[int] = None
    current_wall_seconds: Optional[float] = None
    usd_status: MetricStatus = "unknown"
    tokens_in_status: MetricStatus = "unknown"
    tokens_out_status: MetricStatus = "unknown"
    wall_seconds_status: MetricStatus = "unknown"
    known_subtotal_usd: Optional[float] = None
    known_subtotal_tokens_in: Optional[int] = None
    known_subtotal_tokens_out: Optional[int] = None
    status: str
    dimensions: tuple[BudgetDimensionReport, ...] = ()
    triggered_dimensions: tuple[str, ...] = ()
    checked_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtensionResult(ExecutionModel):
    """Outcome of an operator approval or denial for a budget extension."""

    run_id: Identifier
    approved: bool
    previous_status: str
    status: str
    actor: NonEmpty
    reason: NonEmpty
    budget_status: BudgetStatus
    resolved_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


def _evaluate_thresholds(
    effective_value: Optional[float],
    limit: Optional[float],
    alert_threshold_pct: float,
) -> Tuple[Optional[float], bool, bool]:
    """Return (pct_used, triggered_alert, triggered_freeze); unknown never triggers."""
    if effective_value is None or limit is None:
        return None, False, False
    val_dec = Decimal(str(effective_value))
    lim_dec = Decimal(str(limit))
    if lim_dec <= 0:
        return 100.0, False, True
    pct_dec = (val_dec / lim_dec) * Decimal("100")
    pct_float = float(pct_dec)
    if val_dec >= lim_dec:
        return pct_float, False, True
    if pct_dec >= Decimal(str(alert_threshold_pct)):
        return pct_float, True, False
    return pct_float, False, False


def _validate_positive_delta(name: str, value: Optional[float | int], *, integer_only: bool = False) -> Optional[float | int]:
    """Validate optional positive budget increment."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ContractViolation("budget_invalid", f"{name} cannot be boolean")
    if integer_only:
        if not isinstance(value, int) or value <= 0:
            raise ContractViolation("budget_invalid", f"{name} must be a positive integer")
        return value
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise ContractViolation("budget_invalid", f"{name} must be a positive finite number")
    return float(value)


class BudgetGovernor:
    """Enforces run budget caps (USD, tokens, wall time) with 80% alert and 100% freeze."""

    def __init__(self, store: ExecutionStore, metrics: Optional[MetricsService] = None):
        if metrics is not None and metrics.store is not store:
            raise ValueError("BudgetGovernor requires MetricsService backed by the same ExecutionStore")
        self.store = store
        self.metrics = metrics or MetricsService(store)

    async def _ensure_policy_row(self, db: Any, run_id: str) -> dict[str, Any]:
        run_row = await (await db.execute("SELECT id, spec_json, status FROM runs WHERE id = ?", (run_id,))).fetchone()
        if run_row is None:
            raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
        policy_row = await (
            await db.execute("SELECT * FROM budget_policies WHERE run_id = ?", (run_id,))
        ).fetchone()
        if policy_row is not None:
            return dict(policy_row)

        run_spec = RunSpec.model_validate_json(run_row["spec_json"])
        bp = run_spec.budget_policy
        policy_id = f"budget-{run_id}"
        await db.execute(
            """
            INSERT INTO budget_policies (
                id, run_id, max_usd, max_tokens_in, max_tokens_out,
                max_wall_seconds, alert_threshold_pct, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'))
            """,
            (
                policy_id,
                run_id,
                bp.max_usd,
                bp.max_tokens_in,
                bp.max_tokens_out,
                bp.max_wall_seconds,
                bp.alert_threshold_pct,
            ),
        )
        created = await (
            await db.execute("SELECT * FROM budget_policies WHERE run_id = ?", (run_id,))
        ).fetchone()
        assert created is not None
        return dict(created)

    async def _collect_dimension_telemetry(
        self,
        run_id: str,
        *,
        now: datetime,
        max_age_seconds: float,
    ) -> dict[str, dict[str, Any]]:
        """Collect provenance-aware telemetry per metric kind without converting unknown to zero."""
        usage_aggs = {
            agg.kind: agg
            for agg in await self.metrics.aggregate_usage(run_id, now=now, max_age_seconds=max_age_seconds)
        }
        run_samples = {
            sample.kind: sample
            for sample in await self.metrics.query(run_id, "run", run_id, now=now, max_age_seconds=max_age_seconds)
        }

        async with self.store._connect() as db:
            attempt_rows = await (
                await db.execute(
                    "SELECT a.id FROM attempts a JOIN tasks t ON t.id = a.task_id WHERE t.run_id = ? ORDER BY a.id",
                    (run_id,),
                )
            ).fetchall()
        duration_samples: list[MetricSample] = []
        for att_row in attempt_rows:
            att_samples = await self.metrics.query(
                run_id, "attempt", att_row["id"], now=now, max_age_seconds=max_age_seconds
            )
            dur = next((s for s in att_samples if s.kind == "duration"), None)
            if dur is not None:
                duration_samples.append(dur)

        # Build an aggregate for duration matching MetricsService.aggregate_usage semantics.
        dur_known = [s.value for s in duration_samples if s.value is not None]
        dur_observed = sum(s.status == "observed" for s in duration_samples)
        dur_stale = sum(s.status == "stale" for s in duration_samples)
        dur_unknown = sum(s.status == "unknown" for s in duration_samples)
        dur_subtotal = math.fsum(dur_known) if dur_known else None
        dur_status: MetricStatus = (
            "unknown" if dur_unknown or not duration_samples else "stale" if dur_stale else "observed"
        )
        duration_agg = MetricAggregate(
            kind="duration",
            value=dur_subtotal if dur_status != "unknown" else None,
            known_subtotal=dur_subtotal,
            unit=UNITS["duration"],
            status=dur_status,
            scope_count=len(duration_samples),
            observed_count=dur_observed,
            stale_count=dur_stale,
            unknown_count=dur_unknown,
            sources=tuple(sorted({s.source for s in duration_samples})),
        )
        all_aggs = {**usage_aggs, "duration": duration_agg}

        collected: dict[str, dict[str, Any]] = {}
        for _, _, metric_kind, is_int in _DIMENSION_SPECS:
            agg = all_aggs[metric_kind]
            run_sample = run_samples[metric_kind]

            if agg.scope_count > 0 and agg.known_subtotal is not None:
                current_val = agg.value
                known_val = agg.known_subtotal
                status = agg.status
                sources = agg.sources
            elif run_sample.status != "unknown" and run_sample.value is not None:
                current_val = run_sample.value
                known_val = run_sample.value
                status = run_sample.status
                sources = (run_sample.source,)
            else:
                current_val = None
                known_val = None
                status = "unknown"
                sources = agg.sources or (run_sample.source,)

            if is_int:
                if current_val is not None:
                    current_val = int(round(current_val))
                if known_val is not None:
                    known_val = int(round(known_val))

            collected[metric_kind] = {
                "current": current_val,
                "known_subtotal": known_val,
                "status": status,
                "sources": sources,
            }
        return collected

    def _build_status(
        self,
        policy: dict[str, Any],
        telemetry: dict[str, dict[str, Any]],
        now: datetime,
    ) -> tuple[BudgetStatus, str, list[str]]:
        alert_pct = float(policy["alert_threshold_pct"])
        dim_reports: list[BudgetDimensionReport] = []
        alert_dims: list[str] = []
        freeze_dims: list[str] = []

        for dim_name, col_name, metric_kind, _ in _DIMENSION_SPECS:
            limit_raw = policy.get(col_name)
            limit_val = float(limit_raw) if limit_raw is not None else None
            info = telemetry[metric_kind]
            current_val = info["current"]
            known_val = info["known_subtotal"]
            # Use exact total when fully known, or proven known_subtotal when partial;
            # when telemetry is wholly unknown (None), effective_val stays None.
            effective_val = current_val if current_val is not None else known_val
            pct_used, trig_alert, trig_freeze = _evaluate_thresholds(effective_val, limit_val, alert_pct)
            if trig_freeze:
                freeze_dims.append(dim_name)
            elif trig_alert:
                alert_dims.append(dim_name)

            dim_reports.append(
                BudgetDimensionReport(
                    dimension=dim_name,
                    limit=limit_val,
                    current=float(current_val) if current_val is not None else None,
                    known_subtotal=float(known_val) if known_val is not None else None,
                    pct_used=pct_used,
                    status=info["status"],
                    sources=tuple(info["sources"]),
                    triggered_alert=trig_alert,
                    triggered_freeze=trig_freeze,
                )
            )

        needed = "frozen" if freeze_dims else ("alerted" if alert_dims else "active")
        triggered = freeze_dims if freeze_dims else alert_dims

        status_obj = BudgetStatus(
            policy_id=policy["id"],
            run_id=policy["run_id"],
            max_usd=policy.get("max_usd"),
            max_tokens_in=policy.get("max_tokens_in"),
            max_tokens_out=policy.get("max_tokens_out"),
            max_wall_seconds=policy.get("max_wall_seconds"),
            alert_threshold_pct=alert_pct,
            current_usd=telemetry["cost"]["current"],
            current_tokens_in=telemetry["tokens_in"]["current"],
            current_tokens_out=telemetry["tokens_out"]["current"],
            current_wall_seconds=telemetry["duration"]["current"],
            usd_status=telemetry["cost"]["status"],
            tokens_in_status=telemetry["tokens_in"]["status"],
            tokens_out_status=telemetry["tokens_out"]["status"],
            wall_seconds_status=telemetry["duration"]["status"],
            known_subtotal_usd=telemetry["cost"]["known_subtotal"],
            known_subtotal_tokens_in=telemetry["tokens_in"]["known_subtotal"],
            known_subtotal_tokens_out=telemetry["tokens_out"]["known_subtotal"],
            status=policy["status"],
            dimensions=tuple(dim_reports),
            triggered_dimensions=tuple(triggered),
            checked_at=now,
        )
        return status_obj, needed, triggered

    async def configure(
        self,
        run_id: str,
        *,
        max_usd: Optional[float] = None,
        max_tokens_in: Optional[int] = None,
        max_tokens_out: Optional[int] = None,
        max_wall_seconds: Optional[int] = None,
        alert_threshold_pct: float = 80.0,
    ) -> BudgetStatus:
        """Configure or update the budget policy caps for a run."""
        validated = BudgetPolicy(
            max_usd=max_usd,
            max_tokens_in=max_tokens_in,
            max_tokens_out=max_tokens_out,
            max_wall_seconds=max_wall_seconds if max_wall_seconds is not None else 1800,
            alert_threshold_pct=alert_threshold_pct,
        )
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                policy = await self._ensure_policy_row(db, run_id)
                if policy["status"] == "exhausted":
                    raise ContractViolation("budget_exhausted", "Exhausted budget policy cannot be reconfigured")
                await db.execute(
                    """
                    UPDATE budget_policies
                    SET max_usd = ?, max_tokens_in = ?, max_tokens_out = ?,
                        max_wall_seconds = ?, alert_threshold_pct = ?
                    WHERE run_id = ?
                    """,
                    (
                        validated.max_usd,
                        validated.max_tokens_in,
                        validated.max_tokens_out,
                        max_wall_seconds,
                        validated.alert_threshold_pct,
                        run_id,
                    ),
                )
        return await self.get_status(run_id)

    async def get_status(
        self,
        run_id: str,
        *,
        now: Optional[datetime] = None,
        max_age_seconds: float = 300.0,
    ) -> BudgetStatus:
        """Read-only provenance-aware budget snapshot without mutating policy state."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ContractViolation("budget_invalid", "Budget inspection requires a timezone-aware clock")
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                policy = await self._ensure_policy_row(db, run_id)
        telemetry = await self._collect_dimension_telemetry(run_id, now=now, max_age_seconds=max_age_seconds)
        status_obj, _, _ = self._build_status(policy, telemetry, now)
        return status_obj

    async def _pause_run_for_freeze_in_tx(
        self,
        db: Any,
        run_id: str,
        *,
        correlation_id: Optional[str],
        triggered: list[str],
    ) -> None:
        run_row = await (await db.execute("SELECT status FROM runs WHERE id = ?", (run_id,))).fetchone()
        if run_row is None:
            return
        cur_status = RunStatus(run_row["status"])
        if cur_status == RunStatus.QUEUED:
            transition_status(cur_status, RunStatus.RUNNING)
            await db.execute(
                "UPDATE runs SET status = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                (RunStatus.RUNNING.value, run_id),
            )
            await self.store._insert_event_in_tx(
                db,
                run_id=run_id,
                event_type="run.started",
                payload={"reason": "budget_check"},
                correlation_id=correlation_id,
            )
            cur_status = RunStatus.RUNNING
        if cur_status == RunStatus.RUNNING:
            transition_status(cur_status, RunStatus.WAITING)
            await db.execute(
                "UPDATE runs SET status = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                (RunStatus.WAITING.value, run_id),
            )
            await self.store._insert_event_in_tx(
                db,
                run_id=run_id,
                event_type="run.waiting",
                payload={"reason": "budget_frozen", "triggered_dimensions": triggered},
                correlation_id=correlation_id,
            )

    async def check(
        self,
        run_id: str,
        *,
        now: Optional[datetime] = None,
        max_age_seconds: float = 300.0,
        correlation_id: Optional[str] = None,
    ) -> BudgetStatus:
        """Evaluate run consumption against caps and emit alert/freeze transitions atomically."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ContractViolation("budget_invalid", "Budget check requires a timezone-aware clock")
        await self.store.initialize()
        telemetry = await self._collect_dimension_telemetry(run_id, now=now, max_age_seconds=max_age_seconds)

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                policy = await self._ensure_policy_row(db, run_id)
                status_obj, needed, triggered = self._build_status(policy, telemetry, now)
                current_state = policy["status"]

                if current_state in {"frozen", "exhausted"}:
                    return status_obj

                if current_state == "active" and needed == "alerted":
                    await db.execute(
                        "UPDATE budget_policies SET status = 'alerted' WHERE run_id = ?",
                        (run_id,),
                    )
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="budget.alerted",
                        payload={
                            "policy_id": policy["id"],
                            "previous_status": current_state,
                            "status": "alerted",
                            "alert_threshold_pct": status_obj.alert_threshold_pct,
                            "triggered_dimensions": triggered,
                            "current_usd": status_obj.current_usd,
                            "current_tokens_in": status_obj.current_tokens_in,
                            "current_tokens_out": status_obj.current_tokens_out,
                            "current_wall_seconds": status_obj.current_wall_seconds,
                        },
                        correlation_id=correlation_id,
                    )
                    policy["status"] = "alerted"
                    return status_obj.model_copy(update={"status": "alerted"})

                if current_state in {"active", "alerted"} and needed == "frozen":
                    await db.execute(
                        "UPDATE budget_policies SET status = 'frozen' WHERE run_id = ?",
                        (run_id,),
                    )
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="budget.frozen",
                        payload={
                            "policy_id": policy["id"],
                            "previous_status": current_state,
                            "status": "frozen",
                            "triggered_dimensions": triggered,
                            "current_usd": status_obj.current_usd,
                            "current_tokens_in": status_obj.current_tokens_in,
                            "current_tokens_out": status_obj.current_tokens_out,
                            "current_wall_seconds": status_obj.current_wall_seconds,
                        },
                        correlation_id=correlation_id,
                    )
                    await self._pause_run_for_freeze_in_tx(
                        db,
                        run_id,
                        correlation_id=correlation_id,
                        triggered=triggered,
                    )
                    return status_obj.model_copy(update={"status": "frozen"})

                return status_obj

    async def alert(
        self,
        run_id: str,
        *,
        now: Optional[datetime] = None,
        max_age_seconds: float = 300.0,
        correlation_id: Optional[str] = None,
    ) -> BudgetStatus:
        """Evaluate budget thresholds and return the resulting BudgetStatus."""
        return await self.check(
            run_id,
            now=now,
            max_age_seconds=max_age_seconds,
            correlation_id=correlation_id,
        )

    async def freeze(
        self,
        run_id: str,
        *,
        reason: str = "operator_frozen",
        correlation_id: Optional[str] = None,
    ) -> BudgetStatus:
        """Explicitly freeze an active or alerted budget policy."""
        clean_reason = redact_text(reason.strip())
        if not clean_reason:
            raise ContractViolation("budget_invalid", "Freeze reason cannot be empty")
        await self.store.initialize()
        now = datetime.now(timezone.utc)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                policy = await self._ensure_policy_row(db, run_id)
                cur_state = policy["status"]
                if cur_state == "exhausted":
                    raise ContractViolation("budget_exhausted", f"Run '{run_id}' budget is already exhausted")
                if cur_state != "frozen":
                    await db.execute(
                        "UPDATE budget_policies SET status = 'frozen' WHERE run_id = ?",
                        (run_id,),
                    )
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="budget.frozen",
                        payload={
                            "policy_id": policy["id"],
                            "previous_status": cur_state,
                            "status": "frozen",
                            "reason": clean_reason,
                        },
                        correlation_id=correlation_id,
                    )
                    await self._pause_run_for_freeze_in_tx(
                        db,
                        run_id,
                        correlation_id=correlation_id,
                        triggered=[clean_reason],
                    )
        return await self.get_status(run_id, now=now)

    async def assert_dispatchable(
        self,
        run_id: str,
        *,
        now: Optional[datetime] = None,
        max_age_seconds: float = 300.0,
        correlation_id: Optional[str] = None,
    ) -> BudgetStatus:
        """Guard task/attempt dispatch against frozen or exhausted budgets."""
        status = await self.check(
            run_id,
            now=now,
            max_age_seconds=max_age_seconds,
            correlation_id=correlation_id,
        )
        if status.status == "exhausted":
            raise ContractViolation(
                "budget_exhausted",
                f"Run '{run_id}' budget is exhausted; no further attempts may be dispatched",
            )
        if status.status == "frozen":
            raise ContractViolation(
                "budget_frozen",
                f"Run '{run_id}' budget is frozen ({', '.join(status.triggered_dimensions) or 'limit reached'}); "
                "extend budget before dispatching new attempts",
            )
        return status

    async def extend(
        self,
        run_id: str,
        additional_usd: Optional[float] = None,
        *,
        additional_tokens_in: Optional[int] = None,
        additional_tokens_out: Optional[int] = None,
        additional_wall_seconds: Optional[int] = None,
        approved: bool = True,
        actor: str = "operator",
        reason: str = "operator_budget_decision",
        correlation_id: Optional[str] = None,
    ) -> ExtensionResult:
        """Approve a budget limit extension (returning to active) or deny it (exhausting the run)."""
        clean_actor = redact_text(actor.strip())
        clean_reason = redact_text(reason.strip())
        if not clean_actor or not clean_reason:
            raise ContractViolation("budget_invalid", "Actor and reason are required for budget extension decisions")

        delta_usd = _validate_positive_delta("additional_usd", additional_usd, integer_only=False)
        delta_in = _validate_positive_delta("additional_tokens_in", additional_tokens_in, integer_only=True)
        delta_out = _validate_positive_delta("additional_tokens_out", additional_tokens_out, integer_only=True)
        delta_wall = _validate_positive_delta("additional_wall_seconds", additional_wall_seconds, integer_only=True)

        if approved and all(v is None for v in (delta_usd, delta_in, delta_out, delta_wall)):
            raise ContractViolation(
                "budget_invalid",
                "Approved budget extension requires at least one positive cap increase",
            )

        await self.store.initialize()
        now = datetime.now(timezone.utc)

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                policy = await self._ensure_policy_row(db, run_id)
                prev_status = policy["status"]
                if prev_status == "exhausted":
                    raise ContractViolation(
                        "budget_exhausted",
                        f"Run '{run_id}' budget is exhausted and cannot be extended",
                    )

                run_row = await (await db.execute("SELECT status FROM runs WHERE id = ?", (run_id,))).fetchone()
                assert run_row is not None
                run_status = RunStatus(run_row["status"])

                if approved:
                    new_usd = (
                        (float(policy["max_usd"]) + float(delta_usd))
                        if (policy["max_usd"] is not None and delta_usd is not None)
                        else (float(delta_usd) if delta_usd is not None else policy["max_usd"])
                    )
                    new_in = (
                        (int(policy["max_tokens_in"]) + int(delta_in))
                        if (policy["max_tokens_in"] is not None and delta_in is not None)
                        else (int(delta_in) if delta_in is not None else policy["max_tokens_in"])
                    )
                    new_out = (
                        (int(policy["max_tokens_out"]) + int(delta_out))
                        if (policy["max_tokens_out"] is not None and delta_out is not None)
                        else (int(delta_out) if delta_out is not None else policy["max_tokens_out"])
                    )
                    new_wall = (
                        (int(policy["max_wall_seconds"]) + int(delta_wall))
                        if (policy["max_wall_seconds"] is not None and delta_wall is not None)
                        else (int(delta_wall) if delta_wall is not None else policy["max_wall_seconds"])
                    )

                    await db.execute(
                        """
                        UPDATE budget_policies
                        SET max_usd = ?, max_tokens_in = ?, max_tokens_out = ?,
                            max_wall_seconds = ?, status = 'active'
                        WHERE run_id = ?
                        """,
                        (new_usd, new_in, new_out, new_wall, run_id),
                    )
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="budget.extended",
                        payload={
                            "policy_id": policy["id"],
                            "previous_status": prev_status,
                            "status": "active",
                            "actor": clean_actor,
                            "reason": clean_reason,
                            "additional_usd": delta_usd,
                            "additional_tokens_in": delta_in,
                            "additional_tokens_out": delta_out,
                            "additional_wall_seconds": delta_wall,
                            "max_usd": new_usd,
                            "max_tokens_in": new_in,
                            "max_tokens_out": new_out,
                            "max_wall_seconds": new_wall,
                        },
                        correlation_id=correlation_id,
                    )
                    if run_status == RunStatus.WAITING:
                        transition_status(run_status, RunStatus.RUNNING)
                        await db.execute(
                            "UPDATE runs SET status = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                            (RunStatus.RUNNING.value, run_id),
                        )
                        await self.store._insert_event_in_tx(
                            db,
                            run_id=run_id,
                            event_type="run.resumed",
                            payload={"reason": "budget_extended", "actor": clean_actor},
                            correlation_id=correlation_id,
                        )
                    target_state = "active"
                else:
                    await db.execute(
                        "UPDATE budget_policies SET status = 'exhausted' WHERE run_id = ?",
                        (run_id,),
                    )
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="budget.exhausted",
                        payload={
                            "policy_id": policy["id"],
                            "previous_status": prev_status,
                            "status": "exhausted",
                            "actor": clean_actor,
                            "reason": clean_reason,
                        },
                        correlation_id=correlation_id,
                    )
                    if run_status in {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING, RunStatus.REVIEWING}:
                        transition_status(run_status, RunStatus.FAILED)
                        await db.execute(
                            "UPDATE runs SET status = ?, revision = revision + 1, updated_at = datetime('now') WHERE id = ?",
                            (RunStatus.FAILED.value, run_id),
                        )
                        await self.store._insert_event_in_tx(
                            db,
                            run_id=run_id,
                            event_type="run.finished",
                            payload={"reason": "budget_exhausted", "actor": clean_actor, "detail": clean_reason},
                            correlation_id=correlation_id,
                        )
                    target_state = "exhausted"

        refreshed = await self.get_status(run_id, now=now)
        return ExtensionResult(
            run_id=run_id,
            approved=approved,
            previous_status=prev_status,
            status=target_state,
            actor=clean_actor,
            reason=clean_reason,
            budget_status=refreshed,
            resolved_at=now,
        )


__all__ = [
    "BudgetDimensionReport",
    "BudgetGovernor",
    "BudgetStatus",
    "ExtensionResult",
]
