"""T15 observed zero, absent telemetry, freshness and partial aggregation."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from pydantic import ValidationError

from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.metrics import MetricSample, MetricsService
from hydra_orch.core.run_service import RunService
from hydra_orch.core.session_service import SessionService
from hydra_orch.model import ContractViolation
from hydra_orch import server
from test_checkpointer import _make_run_spec
from test_server import _init_temp_git_repo


@pytest_asyncio.fixture
async def metrics(tmp_path):
    store = ExecutionStore(tmp_path / "metrics.sqlite")
    for run_id in ("run-a", "run-b"):
        await store.submit_run_idempotent(_make_run_spec(str(tmp_path), run_id=run_id, idempotency_key=f"metric-key-000000-{run_id}"))
    now = datetime.now(timezone.utc)
    async with store._connect() as db:
        for ordinal in (1, 2):
            await db.execute("""INSERT INTO attempts(id,task_id,run_id,ordinal,executor_id,provider_model_json,process_status,created_at,started_at,finished_at)
                VALUES (?,?,'run-a',?,'codex','{}','exited',?,?,?)""", (f"attempt-{ordinal}", "run-a-t1", ordinal,
                (now-timedelta(seconds=5)).isoformat(), (now-timedelta(seconds=3)).isoformat(), now.isoformat()))
    return MetricsService(store), now


@pytest.mark.asyncio
async def test_unknown_not_zero_explicit_zero_and_restart(metrics):
    service, now = metrics
    absent = await service.query("run-a", "attempt", "attempt-1")
    assert all(m.status == "unknown" and m.value is None and m.source == "not_reported" for m in absent)
    await service.record_usage("run-a", "attempt-1", source="provider:fixture", observed_at=now, tokens_in=0, tokens_out=3)
    restarted = MetricsService(ExecutionStore(service.store.db_path))
    samples = {m.kind:m for m in await restarted.query("run-a", "attempt", "attempt-1", now=now)}
    assert samples["tokens_in"].status == "observed" and samples["tokens_in"].value == 0
    assert samples["tokens_out"].value == 3
    assert samples["cost"].value is None and samples["cost"].status == "unknown"
    assert len(await restarted.history("run-a", "attempt", "attempt-1")) == 3


@pytest.mark.asyncio
async def test_freshness_latest_observation_and_partial_aggregates(metrics):
    service, now = metrics
    await service.record_usage("run-a", "attempt-1", source="provider:a", observed_at=now, tokens_in=7, tokens_out=0, cost_usd=1.5)
    partial = {m.kind:m for m in await service.aggregate_usage("run-a", now=now)}
    assert partial["tokens_in"].value is None and partial["tokens_in"].known_subtotal == 7
    assert partial["tokens_in"].unknown_count == 1
    await service.record_usage("run-a", "attempt-2", source="provider:b", observed_at=now, tokens_in=5, tokens_out=0, cost_usd=0)
    complete = {m.kind:m for m in await service.aggregate_usage("run-a", now=now)}
    assert complete["tokens_in"].value == 12 and complete["tokens_in"].status == "observed"
    assert complete["tokens_out"].value == 0 and complete["cost"].value == 1.5
    stale = {m.kind:m for m in await service.aggregate_usage("run-a", now=now+timedelta(seconds=301))}
    assert stale["tokens_in"].status == "stale" and stale["tokens_in"].stale_count == 2
    await service.record_usage("run-a", "attempt-2", source="provider:b-correction", observed_at=now, tokens_in=6)
    assert (await service.aggregate_usage("run-a", now=now))[0].value == 13
    empty = await service.aggregate_usage("run-b", now=now)
    assert all(m.value is None and m.known_subtotal is None and m.status == "unknown" for m in empty)


@pytest.mark.asyncio
async def test_local_timing_and_missing_precision(metrics):
    service, now = metrics
    samples = {m.kind:m for m in await service.record_local_timing("run-a", "attempt-1", now=now)}
    assert samples["queue"].value == 2 and samples["duration"].value == 3
    async with service.store._connect() as db:
        await db.execute("UPDATE attempts SET created_at='2026-01-01 00:00:00',started_at=NULL,finished_at=NULL,process_status='queued' WHERE id='attempt-2'")
    samples = await service.record_local_timing("run-a", "attempt-2", now=now)
    assert all(m.value is None and m.status == "unknown" for m in samples)
    async with service.store._connect() as db:
        await db.execute("UPDATE attempts SET created_at=?,started_at=?,finished_at=?,process_status='exited' WHERE id='attempt-2'", (now.isoformat(), (now-timedelta(seconds=1)).isoformat(), now.isoformat()))
    assert (await service.record_local_timing("run-a", "attempt-2", now=now))[0].status == "unknown"


@pytest.mark.asyncio
async def test_scopes_and_atomic_batch(metrics):
    service, now = metrics
    sessions = SessionService(service.store)
    session = await sessions.create_session("run-a")
    thread = await sessions.create_thread("run-a", session["id"])
    for scope, identifier in [("session",session["id"]),("thread",thread["id"])]:
        assert all(m.value is None for m in await service.query("run-a", scope, identifier))
        with pytest.raises(ContractViolation, match="not part"):
            await service.query("run-b", scope, identifier)
    with pytest.raises(ContractViolation):
        await service.query("run-b", "attempt", "attempt-1")
    with pytest.raises(ContractViolation):
        await service.query("run-a", "run", "run-b")
    with pytest.raises(ContractViolation):
        await service.query("missing", "run", "missing")
    first = MetricSample(run_id="run-a",scope="attempt",scope_id="attempt-1",kind="cost",value=1,unit="USD",source="fixture",observed_at=now,status="observed")
    invalid = MetricSample.model_validate({**first.model_dump(mode="json"),"sample_id":"other","scope_id":"missing"})
    before = await service.history("run-a", "attempt", "attempt-1")
    with pytest.raises(ContractViolation):
        await service.record_batch((first,invalid))
    assert await service.history("run-a", "attempt", "attempt-1") == before


@pytest.mark.parametrize("changes", [
    {"value":0,"status":"unknown"},{"value":None,"status":"observed"},{"value":float('nan')},
    {"value":-1},{"value":True},{"value":"2"},{"unit":"BRL"},{"kind":"tokens_in","unit":"tokens","value":1.5},
    {"source":"Bearer secret-value"},
])
def test_invalid_telemetry_is_rejected(changes):
    data=dict(run_id="run-a",scope="run",scope_id="run-a",kind="cost",value=1,unit="USD",source="provider",observed_at=datetime.now(timezone.utc),status="observed")
    with pytest.raises(ValidationError):
        MetricSample(**(data|changes))


@pytest.mark.asyncio
async def test_future_and_invalid_freshness_refused(metrics):
    service, now = metrics
    with pytest.raises(ContractViolation, match="Future"):
        await service.record_usage("run-a","attempt-1",source="fixture",observed_at=now+timedelta(days=1),tokens_in=1)
    with pytest.raises(ContractViolation):
        await service.query("run-a","run","run-a",max_age_seconds=-1)
    with pytest.raises(ContractViolation):
        await service.query("run-a","run","run-a",now=datetime.now())
    with pytest.raises(ContractViolation):
        await service.history("run-a","run","run-a",limit=0)


@pytest.mark.asyncio
async def test_authenticated_metric_read_models(metrics,tmp_path,monkeypatch):
    service, now = metrics
    repo,_ = _init_temp_git_repo(tmp_path)
    monkeypatch.setattr(server,"_run_service",RunService(repo_root=repo,store=service.store))
    token="metrics-test-token-0123456789abcdef"
    monkeypatch.setitem(server.app.state._state,"token_verifier",TokenVerifier.from_token(token))
    client=TestClient(server.app,headers={"Authorization":"Bearer "+token})
    response=client.get('/v1/control-plane/runs/run-a/metrics')
    assert response.status_code==200 and all(m['value'] is None for m in response.json())
    assert client.get('/v1/control-plane/runs/run-b/metrics',params={"scope":"attempt","scope_id":"attempt-1"}).status_code==403
    assert client.get('/v1/control-plane/runs/run-a/metrics/usage').status_code==200
    assert TestClient(server.app).get('/v1/control-plane/runs/run-a/metrics').status_code==401
