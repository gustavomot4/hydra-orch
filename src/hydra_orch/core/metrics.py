"""T15 provenance-aware measurements; absent telemetry never becomes zero."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact
from hydra_orch.model import ContractViolation, ExecutionModel, Identifier, NonEmpty, UtcTimestamp

MetricKind = Literal["queue", "duration", "tokens_in", "tokens_out", "cost"]
MetricScope = Literal["run", "attempt", "session", "thread"]
MetricStatus = Literal["observed", "stale", "unknown"]
UNITS = {"queue": "seconds", "duration": "seconds", "tokens_in": "tokens", "tokens_out": "tokens", "cost": "USD"}


class MetricSample(ExecutionModel):
    sample_id: Identifier = Field(default_factory=new_id)
    run_id: Identifier
    scope: MetricScope
    scope_id: Identifier
    kind: MetricKind
    value: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    unit: NonEmpty
    source: NonEmpty
    observed_at: UtcTimestamp
    status: MetricStatus

    @field_validator("value", mode="before")
    @classmethod
    def numeric(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError("Telemetry must be numeric or explicitly absent")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if self.unit != UNITS[self.kind] or (self.status == "unknown") != (self.value is None):
            raise ValueError("Unknown metrics require NULL; known metrics require a value and canonical unit")
        if self.kind in {"tokens_in", "tokens_out"} and self.value is not None and not self.value.is_integer():
            raise ValueError("Token counts must be integers")
        data = self.model_dump(mode="json")
        if redact(data) != data:
            raise ValueError("Metric provenance cannot contain credentials")
        return self


class MetricAggregate(ExecutionModel):
    kind: MetricKind
    value: Optional[float]
    known_subtotal: Optional[float]
    unit: str
    status: MetricStatus
    scope_count: int
    observed_count: int
    stale_count: int
    unknown_count: int
    sources: tuple[str, ...]


class MetricsService:
    def __init__(self, store: ExecutionStore):
        self.store = store

    async def _scope(self, db, run_id: str, scope: MetricScope, scope_id: str):
        if await (await db.execute("SELECT 1 FROM runs WHERE id=?", (run_id,))).fetchone() is None:
            raise ContractViolation("resource_not_found", "Run does not exist")
        if scope == "run":
            valid = scope_id == run_id
        elif scope == "attempt":
            valid = await (await db.execute("SELECT 1 FROM attempts a JOIN tasks t ON t.id=a.task_id WHERE a.id=? AND t.run_id=?", (scope_id, run_id))).fetchone()
        elif scope == "session":
            valid = await (await db.execute("SELECT 1 FROM sessions WHERE id=? AND run_id=?", (scope_id, run_id))).fetchone()
        elif scope == "thread":
            valid = await (await db.execute("SELECT 1 FROM threads t JOIN sessions s ON s.id=t.session_id WHERE t.id=? AND s.run_id=?", (scope_id, run_id))).fetchone()
        else:
            valid = False
        if not valid:
            raise ContractViolation("metric_scope_mismatch", "Metric scope is not part of the selected run")

    @staticmethod
    def _sample(row):
        return MetricSample(sample_id=row["id"], run_id=row["run_id"], scope=row["scope"], scope_id=row["scope_id"],
            kind=row["kind"], value=row["value"], unit=row["unit"], source=row["source"], observed_at=row["observed_at"], status=row["status"])

    async def record_batch(self, samples: tuple[MetricSample, ...]):
        await self.store.initialize()
        now = datetime.now(timezone.utc)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                for sample in samples:
                    if (sample.observed_at - now).total_seconds() > 5:
                        raise ContractViolation("metric_invalid", "Future observations are not accepted")
                    await self._scope(db, sample.run_id, sample.scope, sample.scope_id)
                    await db.execute("""INSERT INTO metric_samples(id,run_id,scope,scope_id,kind,value,unit,source,observed_at,status)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""", (sample.sample_id, sample.run_id, sample.scope, sample.scope_id,
                        sample.kind, sample.value, sample.unit, sample.source, sample.observed_at.isoformat(), sample.status))
                    await self.store._insert_event_in_tx(db, run_id=sample.run_id, event_type="metric.sampled",
                        payload={"sample_id": sample.sample_id, "scope": sample.scope, "scope_id": sample.scope_id,
                            "kind": sample.kind, "status": sample.status, "source": sample.source})
        return samples

    async def record_usage(self, run_id: str, attempt_id: str, *, source: str, observed_at: datetime,
                           tokens_in: Optional[int] = None, tokens_out: Optional[int] = None, cost_usd: Optional[float] = None):
        values = {"tokens_in": tokens_in, "tokens_out": tokens_out, "cost": cost_usd}
        samples = tuple(MetricSample(run_id=run_id, scope="attempt", scope_id=attempt_id, kind=kind, value=value,
            unit=UNITS[kind], source=source, observed_at=observed_at,
            status="unknown" if value is None else "observed") for kind, value in values.items())
        return await self.record_batch(samples)

    async def query(self, run_id: str, scope: MetricScope, scope_id: str, *, now: Optional[datetime] = None,
                     max_age_seconds: float = 300):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or not math.isfinite(max_age_seconds) or max_age_seconds < 0:
            raise ContractViolation("metric_invalid", "Freshness requires an aware clock and nonnegative finite age")
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._scope(db, run_id, scope, scope_id)
            rows = await (await db.execute("""SELECT * FROM (
                SELECT *,ROW_NUMBER() OVER(PARTITION BY kind ORDER BY observed_at DESC,rowid DESC) AS position
                FROM metric_samples WHERE run_id=? AND scope=? AND scope_id=?) WHERE position=1""", (run_id, scope, scope_id))).fetchall()
        latest = {r["kind"]: self._sample(r) for r in rows}
        result = []
        for kind, unit in UNITS.items():
            sample = latest.get(kind)
            if sample is None:
                digest = hashlib.sha256(f"{run_id}:{scope}:{scope_id}:{kind}".encode()).hexdigest()[:32]
                sample = MetricSample(sample_id="unknown-" + digest, run_id=run_id, scope=scope, scope_id=scope_id,
                    kind=kind, value=None, unit=unit, source="not_reported", observed_at=now, status="unknown")
            elif sample.status == "observed" and (now - sample.observed_at).total_seconds() > max_age_seconds:
                sample = MetricSample.model_validate({**sample.model_dump(mode="json"), "status": "stale"})
            result.append(sample)
        return tuple(result)

    async def history(self, run_id: str, scope: MetricScope, scope_id: str, *, limit: int = 1000):
        if not 1 <= limit <= 1000:
            raise ContractViolation("metric_invalid", "History limit must be 1–1000")
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._scope(db, run_id, scope, scope_id)
            rows = await (await db.execute("SELECT * FROM metric_samples WHERE run_id=? AND scope=? AND scope_id=? ORDER BY observed_at DESC,rowid DESC LIMIT ?", (run_id, scope, scope_id, limit))).fetchall()
            return tuple(self._sample(row) for row in rows)

    async def record_local_timing(self, run_id: str, attempt_id: str, *, now: Optional[datetime] = None):
        now = now or datetime.now(timezone.utc)
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._scope(db, run_id, "attempt", attempt_id)
            row = await (await db.execute("SELECT created_at,started_at,finished_at,process_status FROM attempts WHERE id=?", (attempt_id,))).fetchone()
        def timestamp(value):
            if value is None:
                return None
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        created, started, finished = (timestamp(row[key]) for key in ("created_at", "started_at", "finished_at"))
        # Legacy SQL timestamps have only second precision and do not prove a
        # subsecond dispatch delay. Preserve unknown rather than manufacture it.
        if "T" not in row["created_at"]:
            created = None
        queue_end = started or (now if row["process_status"] == "queued" else None)
        duration_end = finished or (now if row["process_status"] == "running" else None)
        samples = []
        for kind, beginning, end in (("queue", created, queue_end), ("duration", started, duration_end)):
            value = (end - beginning).total_seconds() if beginning is not None and end is not None else None
            if value is not None and value < 0:
                value = None
            samples.append(MetricSample(run_id=run_id, scope="attempt", scope_id=attempt_id, kind=kind, value=value,
                unit=UNITS[kind], source="local_calc:timestamps", observed_at=now, status="unknown" if value is None else "observed"))
        return await self.record_batch(tuple(samples))

    async def aggregate_usage(self, run_id: str, *, now: Optional[datetime] = None, max_age_seconds: float = 300):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._scope(db, run_id, "run", run_id)
            attempts = await (await db.execute("SELECT a.id FROM attempts a JOIN tasks t ON t.id=a.task_id WHERE t.run_id=? ORDER BY a.id", (run_id,))).fetchall()
        per_attempt = [await self.query(run_id, "attempt", a["id"], now=now, max_age_seconds=max_age_seconds) for a in attempts]
        result = []
        for kind in ("tokens_in", "tokens_out", "cost"):
            samples = [next(m for m in group if m.kind == kind) for group in per_attempt]
            observed = sum(m.status == "observed" for m in samples)
            stale = sum(m.status == "stale" for m in samples)
            unknown = sum(m.status == "unknown" for m in samples)
            known = [m.value for m in samples if m.value is not None]
            subtotal = math.fsum(known) if known else None
            status = "unknown" if unknown or not samples else "stale" if stale else "observed"
            result.append(MetricAggregate(kind=kind, value=subtotal if status != "unknown" else None,
                known_subtotal=subtotal, unit=UNITS[kind], status=status, scope_count=len(samples),
                observed_count=observed, stale_count=stale, unknown_count=unknown,
                sources=tuple(sorted({m.source for m in samples}))))
        return tuple(result)
