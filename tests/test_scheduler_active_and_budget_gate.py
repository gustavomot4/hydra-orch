"""Wave 2B tests for BE-17, BE-11, DAY-03, and DAY-17 in scheduler.py and budget.py."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from hydra_orch.core.budget import (
    RECURRING_BUDGET_REQUIRED_MESSAGE,
    BudgetGovernor,
)
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.preferences import PreferenceService
from hydra_orch.core.scheduler import (
    AutomationRunRecord,
    AutomationSchedule,
    SchedulerService,
    _advance_next_matching_month,
    _step_prev_matching_month,
    compute_next_occurrence,
    compute_previous_occurrence,
)
from hydra_orch.model import (
    BudgetPolicy,
    CheckSpec,
    ContractViolation,
    ProcessStatus,
    RunSpec,
    RunStatus,
    TaskAttempt,
    TaskSpec,
)

BASE_SHA = "b" * 40


def _make_store(tmp_path: Path, name: str = "wave2b.sqlite") -> ExecutionStore:
    return ExecutionStore(tmp_path / name)


def _make_run_spec(
    tmp_path: Path,
    run_id: str,
    *,
    project_id: str = "proj-w2b",
    budget_policy: Optional[BudgetPolicy] = None,
) -> RunSpec:
    task = TaskSpec(
        task_id=f"{run_id}-t1",
        run_id=run_id,
        objective="Execute recurring automation",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-1", command=("python", "--version")),),
        allowed_paths=("src/**",),
    )
    return RunSpec(
        run_id=run_id,
        project_id=project_id,
        objective="Recurring automation run",
        repo_root=str(tmp_path / "repo"),
        base_sha=BASE_SHA,
        base_branch="main",
        orchestration_mode="relay",
        budget_policy=budget_policy or BudgetPolicy(),
        idempotency_key=f"idem-{run_id}-000001",
        tasks=(task,),
    )


# ---------------------------------------------------------------------------
# BE-17: Calendar Boundary Overflow Protection (date.min / date.max)
# ---------------------------------------------------------------------------


def test_be17_month_stepping_helpers_guard_year_bounds() -> None:
    with pytest.raises(ContractViolation) as exc_next:
        _advance_next_matching_month(date(9999, 12, 15), frozenset({1}))
    assert exc_next.value.code == "invalid_schedule"
    assert "calendar range" in str(exc_next.value)

    with pytest.raises(ContractViolation) as exc_prev:
        _step_prev_matching_month(date(1, 1, 15), frozenset({12}))
    assert exc_prev.value.code == "invalid_schedule"
    assert "calendar range" in str(exc_prev.value)

    # Stepping back into December of year 9998 or any month near max never overflows year + 1
    assert _step_prev_matching_month(date(9999, 1, 10), frozenset({12})) == date(9998, 12, 31)
    assert _advance_next_matching_month(date(9999, 11, 20), frozenset({12})) == date(9999, 12, 1)


def test_be17_compute_next_occurrence_near_date_min_and_date_max() -> None:
    # Near date.min (year 1): start_local.date() - timedelta(days=1) must clamp safely to date.min
    min_dt = datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc)
    occ_incl = compute_next_occurrence("0 0 * * *", after=min_dt, inclusive=True)
    assert occ_incl == min_dt

    occ_after = compute_next_occurrence("0 0 * * *", after=min_dt, inclusive=False)
    assert occ_after == datetime(1, 1, 2, 0, 0, tzinfo=timezone.utc)

    # Negative and positive UTC offsets at year 1 boundary must never raise OverflowError
    occ_ny = compute_next_occurrence("0 12 * * *", timezone="America/New_York", after=min_dt)
    assert occ_ny > min_dt

    occ_tokyo = compute_next_occurrence("0 12 * * *", timezone="Asia/Tokyo", after=min_dt)
    assert occ_tokyo > min_dt

    # Within 9 years of date.max: start_local.date() + timedelta(days=366 * 9) clamps to date.max
    near_max = datetime(9995, 6, 15, 10, 0, tzinfo=timezone.utc)
    assert compute_next_occurrence("0 12 * * *", after=near_max) == datetime(
        9995, 6, 15, 12, 0, tzinfo=timezone.utc
    )

    last_day_morning = datetime(9999, 12, 31, 10, 0, tzinfo=timezone.utc)
    assert compute_next_occurrence("0 12 * * *", after=last_day_morning) == datetime(
        9999, 12, 31, 12, 0, tzinfo=timezone.utc
    )

    # Past date.max ceiling: must translate overflow into ContractViolation("invalid_schedule", ...)
    for bad_after, kwargs in (
        (datetime(9999, 12, 31, 12, 0, tzinfo=timezone.utc), {"cron_expr": "0 0 * * *"}),
        (datetime(9999, 12, 31, 23, 59, 30, tzinfo=timezone.utc), {"cron_expr": "* * * * *"}),
        (datetime(9999, 7, 1, 0, 0, tzinfo=timezone.utc), {"cron_expr": "0 0 1 6 *"}),
        (datetime(9999, 12, 31, 23, 30, tzinfo=timezone.utc), {"interval_seconds": 3600}),
        (datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), {"interval_seconds": 10**15}),
    ):
        with pytest.raises(ContractViolation) as exc_info:
            compute_next_occurrence(after=bad_after, **kwargs)
        assert exc_info.value.code == "invalid_schedule"
        assert str(exc_info.value) == "Schedule occurrence exceeds supported calendar range"


def test_be17_compute_previous_occurrence_near_date_min_and_date_max() -> None:
    # Exact match on 0001-01-01 00:00Z
    min_dt = datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert compute_previous_occurrence("0 0 * * *", at_or_before=min_dt) == min_dt

    # Before first valid occurrence in year 1 -> returns None cleanly (zero OverflowError)
    assert (
        compute_previous_occurrence(
            "30 12 * * *",
            at_or_before=datetime(1, 1, 1, 5, 0, tzinfo=timezone.utc),
        )
        is None
    )
    assert (
        compute_previous_occurrence(
            "0 0 1 6 *",
            at_or_before=datetime(1, 3, 1, 0, 0, tzinfo=timezone.utc),
        )
        is None
    )
    assert (
        compute_previous_occurrence(
            "0 12 * * *",
            timezone="America/New_York",
            at_or_before=min_dt,
        )
        is None
    )

    # Near date.max: cursor_day = end_local.date() + timedelta(days=1) clamps safely to date.max
    max_dt = datetime(9999, 12, 31, 23, 59, tzinfo=timezone.utc)
    assert compute_previous_occurrence("0 12 * * *", at_or_before=max_dt) == datetime(
        9999, 12, 31, 12, 0, tzinfo=timezone.utc
    )
    assert compute_previous_occurrence(
        interval_seconds=3600,
        at_or_before=max_dt,
        min_bound=datetime(9999, 12, 31, 20, 0, tzinfo=timezone.utc),
    ) == datetime(9999, 12, 31, 23, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# BE-11: Block trigger_now() on Disabled Schedules Unless force=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_be11_trigger_now_blocks_disabled_schedule_unless_forced(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    dispatched: List[str] = []

    async def dispatcher(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        dispatched.append(occ_key)
        return {"status": "succeeded"}

    service = SchedulerService(store, dispatcher=dispatcher)
    t0 = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)

    sched = await service.create_schedule(
        "Paused Audit",
        "Check workspace health",
        interval_seconds=300,
        enabled=False,
        now=t0,
    )
    assert sched.enabled is False

    with pytest.raises(ContractViolation) as blocked:
        await service.trigger_now(sched.id, now=t0)
    assert blocked.value.code == "schedule_disabled"
    assert sched.id in str(blocked.value)
    assert dispatched == []
    assert await service.list_runs(sched.id) == []

    # Explicit force=True overrides disabled state without flipping enabled=True
    forced = await service.trigger_now(sched.id, now=t0 + timedelta(seconds=5), force=True)
    assert forced["status"] == "succeeded"
    assert forced["occurrence_key"].startswith("manual:")
    assert len(dispatched) == 1
    assert (await service.get_schedule(sched.id)).enabled is False

    # Resuming allows normal trigger_now(force=False); pausing blocks again
    await service.set_enabled(sched.id, True, now=t0 + timedelta(seconds=10))
    normal = await service.trigger_now(sched.id, now=t0 + timedelta(seconds=15))
    assert normal["status"] == "succeeded"

    await service.set_enabled(sched.id, False, now=t0 + timedelta(seconds=20))
    with pytest.raises(ContractViolation) as blocked_again:
        await service.trigger_now(sched.id, now=t0 + timedelta(seconds=25))
    assert blocked_again.value.code == "schedule_disabled"


# ---------------------------------------------------------------------------
# DAY-17: Explicit Budget Gate for Recurring Inference
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day17_budget_governor_and_scheduler_budget_gate(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    governor = BudgetGovernor(store)
    prefs = PreferenceService(store)
    t0 = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

    # Unconfigured or wall-time-only / zero caps do NOT satisfy recurring budget requirement
    assert await governor.has_configured_budget(project_id="proj-no-budget") is False
    assert await governor.has_configured_budget(budget_policy={}) is False
    assert await governor.has_configured_budget(budget_policy={"max_usd": 0.0}) is False
    assert await governor.has_configured_budget(budget_policy={"max_wall_seconds": 600}) is False

    with pytest.raises(ContractViolation) as gov_err:
        await governor.validate_recurring_budget(project_id="proj-no-budget")
    assert gov_err.value.code == "budget_required"
    assert str(gov_err.value) == RECURRING_BUDGET_REQUIRED_MESSAGE

    # Direct finite caps (max_usd, max_tokens_in, max_tokens_out) satisfy budget requirement
    assert await governor.has_configured_budget(budget_policy={"max_usd": 1.25}) is True
    assert await governor.has_configured_budget(budget_policy={"max_tokens_in": 5000}) is True
    assert await governor.has_configured_budget(budget_policy=BudgetPolicy(max_tokens_out=2000)) is True

    # SchedulerService with require_budget=True blocks enabling recurring inference without budget
    service = SchedulerService(
        store,
        dispatcher=lambda _s, _k: {"status": "succeeded"},
        require_budget=True,
    )

    with pytest.raises(ContractViolation) as create_blocked:
        await service.create_schedule(
            "Unbudgeted Cron",
            "Run inference",
            cron_expr="0 * * * *",
            enabled=True,
            now=t0,
        )
    assert create_blocked.value.code == "budget_required"
    assert str(create_blocked.value) == RECURRING_BUDGET_REQUIRED_MESSAGE

    # Creating a disabled draft schedule without budget succeeds, but resuming or force-triggering is blocked
    draft = await service.create_schedule(
        "Draft Cron",
        "Run inference once budgeted",
        cron_expr="0 * * * *",
        enabled=False,
        now=t0,
    )
    assert draft.enabled is False
    assert draft.budget_policy is None

    with pytest.raises(ContractViolation) as resume_blocked:
        await service.set_enabled(draft.id, True, now=t0)
    assert resume_blocked.value.code == "budget_required"

    with pytest.raises(ContractViolation) as force_trig_blocked:
        await service.trigger_now(draft.id, now=t0, force=True)
    assert force_trig_blocked.value.code == "budget_required"

    # Attaching budget_policy via update_schedule persists in preferences and unblocks activation
    enabled_sched = await service.update_schedule(
        draft.id,
        budget_policy={"max_usd": 3.5, "max_tokens_in": 20000},
        enabled=True,
        now=t0,
    )
    assert enabled_sched.enabled is True
    assert enabled_sched.budget_policy == {"max_tokens_in": 20000, "max_usd": 3.5}

    fetched = await service.get_schedule(draft.id)
    assert fetched.budget_policy == {"max_tokens_in": 20000, "max_usd": 3.5}
    listed = await service.list_schedules()
    assert listed[0].budget_policy == {"max_tokens_in": 20000, "max_usd": 3.5}

    # Stored preference must remain compatible with PreferenceService.list_preferences()
    all_prefs = await prefs.list_preferences()
    assert any(p.scope_id == f"schedule:{draft.id}" and p.key == "budget_policy" for p in all_prefs)

    # Clearing budget_policy while enabled=True is rejected
    with pytest.raises(ContractViolation) as clear_blocked:
        await service.update_schedule(draft.id, budget_policy=None, now=t0)
    assert clear_blocked.value.code == "budget_required"

    # Project-level run budget in SQLite also satisfies require_budget without per-schedule budget_policy
    await store.submit_run_idempotent(
        _make_run_spec(
            tmp_path,
            "run-proj-budget",
            project_id="proj-funded",
            budget_policy=BudgetPolicy(max_tokens_out=4096),
        )
    )
    proj_sched = await service.create_schedule(
        "Project Funded Cron",
        "Run against funded project",
        interval_seconds=120,
        project_id="proj-funded",
        enabled=True,
        next_run_at=t0,
        now=t0,
    )
    tick_out = await service.tick(now=t0)
    assert len(tick_out) == 1
    assert tick_out[0]["schedule_id"] == proj_sched.id
    assert tick_out[0]["status"] == "succeeded"

    # User-level preference budget also satisfies require_budget; deleting schedule cleans up its preference
    await service.delete_schedule(draft.id)
    assert not any(
        p.scope_id == f"schedule:{draft.id}" for p in await prefs.list_preferences()
    )

    await prefs.set_preference("user", "operator", "budget_policy", {"max_usd": 10.0})
    user_funded = await service.create_schedule(
        "User Pref Funded",
        "Run with operator cap",
        interval_seconds=300,
        enabled=True,
        now=t0,
    )
    assert user_funded.enabled is True


@pytest.mark.asyncio
async def test_day17_tick_blocks_legacy_unbudgeted_schedule_when_require_budget_enabled(
    tmp_path: Path,
) -> None:
    store = _make_store(tmp_path)
    t0 = datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc)

    # Created while require_budget=False, then evaluated by a scheduler with require_budget=True
    legacy_svc = SchedulerService(store, dispatcher=lambda _s, _k: {"status": "succeeded"})
    legacy_sched = await legacy_svc.create_schedule(
        "Legacy Unbudgeted",
        "Should be blocked on gated tick",
        interval_seconds=60,
        next_run_at=t0,
        now=t0,
    )

    gated_svc = SchedulerService(
        store,
        dispatcher=lambda _s, _k: {"status": "succeeded"},
        require_budget=True,
    )
    with pytest.raises(ContractViolation) as tick_err:
        await gated_svc.tick(now=t0)
    assert tick_err.value.code == "budget_required"
    assert await gated_svc.list_runs(legacy_sched.id) == []


# ---------------------------------------------------------------------------
# DAY-03: Active Background Loop, Supervised Runner Completion, & Crash Recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day03_background_loop_and_supervised_runner_complete_and_drain_queue(
    tmp_path: Path,
) -> None:
    store = _make_store(tmp_path)
    runner_events: List[tuple[str, str]] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_done = asyncio.Event()
    seq = 0

    async def dispatcher(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        nonlocal seq
        seq += 1
        run_id = f"run-sup-{seq}"
        await store.submit_run_idempotent(_make_run_spec(tmp_path, run_id))
        return {"run_id": run_id, "status": "dispatched"}

    async def runner(
        sched: AutomationSchedule,
        run_record: AutomationRunRecord,
        dispatch_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        runner_events.append(("start", dispatch_result["run_id"]))
        if sched.name == "Failing Supervised":
            raise RuntimeError("worker crashed with sk-secret999999999999")
        if dispatch_result["run_id"] == "run-sup-1":
            first_started.set()
            await release_first.wait()
        runner_events.append(("finish", dispatch_result["run_id"]))
        if dispatch_result["run_id"] == "run-sup-2":
            second_done.set()
        return {"status": "succeeded", "run_id": dispatch_result["run_id"]}

    service = SchedulerService(store, dispatcher=dispatcher, runner=runner)
    past_due = datetime.now(timezone.utc) - timedelta(seconds=5)

    q_sched = await service.create_schedule(
        "Queued Supervised",
        "Run supervised job",
        interval_seconds=3600,
        overlap_policy="queue",
        next_run_at=past_due,
    )

    await service.start_background_loop(interval_seconds=0.05, stale_lease_seconds=1800.0)
    try:
        assert service.is_running is True
        await asyncio.wait_for(first_started.wait(), timeout=3.0)
        assert len(service._active_tasks) == 1

        # Triggering while run-sup-1 is executing queues a second pending run
        queued_res = await service.trigger_now(q_sched.id)
        assert queued_res["status"] == "pending"

        # Releasing run-sup-1 completes it in finally AND drains queued run-sup-2 automatically
        release_first.set()
        await asyncio.wait_for(second_done.wait(), timeout=3.0)
        await service.wait_for_active_tasks(timeout=3.0)

        q_runs = await service.list_runs(q_sched.id)
        assert len(q_runs) == 2
        assert all(r.status == "succeeded" and r.finished_at is not None for r in q_runs)

        # Runner exception must still mark automation_run failed in finally with secret redaction
        fail_sched = await service.create_schedule(
            "Failing Supervised",
            "Will raise inside runner",
            interval_seconds=3600,
            enabled=True,
        )
        await service.trigger_now(fail_sched.id)
        await service.wait_for_active_tasks(timeout=3.0)

        fail_runs = await service.list_runs(fail_sched.id)
        assert len(fail_runs) == 1
        assert fail_runs[0].status == "failed"
        assert fail_runs[0].finished_at is not None
        assert "sk-secret999999999999" not in (fail_runs[0].error_detail or "")
        assert "[REDACTED]" in (fail_runs[0].error_text or "")
    finally:
        await service.stop_background_loop()
        assert service.is_running is False
        assert len(service._active_tasks) == 0


@pytest.mark.asyncio
async def test_day03_reconcile_stale_runs_breaks_schedule_overlap_and_syncs_linked_runs(
    tmp_path: Path,
) -> None:
    store = _make_store(tmp_path)
    t0 = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
    run_counter = 0

    async def dispatcher(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        nonlocal run_counter
        run_counter += 1
        if sched.name == "Orphan No Run":
            return {"status": "dispatched"}
        run_id = f"run-rec-{run_counter}"
        await store.submit_run_idempotent(_make_run_spec(tmp_path, run_id))
        return {"run_id": run_id, "status": "dispatched"}

    crashed_svc = SchedulerService(store, dispatcher=dispatcher)
    s_orphan = await crashed_svc.create_schedule(
        "Orphan No Run", "p", interval_seconds=300, overlap_policy="skip", next_run_at=t0, now=t0
    )
    s_succ = await crashed_svc.create_schedule(
        "Linked Succeeded", "p", interval_seconds=300, overlap_policy="skip", next_run_at=t0, now=t0
    )
    s_canc = await crashed_svc.create_schedule(
        "Linked Cancelled", "p", interval_seconds=300, overlap_policy="skip", next_run_at=t0, now=t0
    )
    s_active_att = await crashed_svc.create_schedule(
        "Fresh Running Attempt", "p", interval_seconds=300, overlap_policy="skip", next_run_at=t0, now=t0
    )

    dispatched = await crashed_svc.tick(now=t0)
    by_sched = {d["schedule_id"]: d for d in dispatched}
    assert all(d["status"] == "dispatched" for d in dispatched)

    # Simulate crash deadlock: trigger_now fails with schedule_overlap while stuck in 'dispatched'
    restarted_svc = SchedulerService(store, dispatcher=dispatcher)
    with pytest.raises(ContractViolation) as ov_err:
        await restarted_svc.trigger_now(s_orphan.id, now=t0 + timedelta(seconds=30))
    assert ov_err.value.code == "schedule_overlap"

    # Update underlying SQLite runs states to simulate finished/cancelled vs fresh running attempt
    succ_run_id = by_sched[s_succ.id]["run_id"]
    canc_run_id = by_sched[s_canc.id]["run_id"]
    fresh_run_id = by_sched[s_active_att.id]["run_id"]

    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute("UPDATE runs SET status = ? WHERE id = ?", (RunStatus.SUCCEEDED.value, succ_run_id))
            await db.execute("UPDATE runs SET status = ? WHERE id = ?", (RunStatus.CANCELLED.value, canc_run_id))
            await db.execute("UPDATE runs SET status = ? WHERE id = ?", (RunStatus.RUNNING.value, fresh_run_id))

    fresh_attempt = TaskAttempt(
        attempt_id="att-fresh-1",
        task_id=f"{fresh_run_id}-t1",
        run_id=fresh_run_id,
        ordinal=1,
        executor_id="codex",
        provider="fixture",
        model="fixture-model",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.RUNNING,
        started_at=t0 + timedelta(seconds=1750),
    )
    await store.save_attempt_atomic(fresh_attempt)

    # Before max_age_seconds (at t0 + 60s < 1800s), nothing is considered stale yet
    assert await restarted_svc.reconcile_stale_runs(max_age_seconds=1800.0, now=t0 + timedelta(seconds=60)) == []

    # Past max_age_seconds (at t0 + 1805s):
    # - s_orphan -> failed with stale lease timeout message
    # - s_succ -> succeeded (synced from runs.status == 'succeeded')
    # - s_canc -> failed (synced from runs.status == 'cancelled')
    # - s_active_att -> preserved in 'dispatched' because att-fresh-1 started only 55s ago!
    reconciled = await restarted_svc.reconcile_stale_runs(
        max_age_seconds=1800.0,
        now=t0 + timedelta(seconds=1805),
    )
    rec_by_sched = {r.schedule_id: r for r in reconciled}
    assert set(rec_by_sched.keys()) == {s_orphan.id, s_succ.id, s_canc.id}

    assert rec_by_sched[s_orphan.id].status == "failed"
    assert (
        rec_by_sched[s_orphan.id].error_detail
        == "Interrupted automation run reconciled after stale lease timeout"
    )
    assert rec_by_sched[s_succ.id].status == "succeeded"
    assert rec_by_sched[s_succ.id].error_detail is None
    assert rec_by_sched[s_canc.id].status == "failed"

    # s_active_att is still 'dispatched' while its attempt is fresh
    assert (await restarted_svc.list_runs(s_active_att.id))[0].status == "dispatched"

    # schedule_overlap deadlock is broken: s_orphan can now trigger_now() cleanly!
    resumed_trig = await restarted_svc.trigger_now(s_orphan.id, now=t0 + timedelta(seconds=1810))
    assert resumed_trig["status"] == "dispatched"
