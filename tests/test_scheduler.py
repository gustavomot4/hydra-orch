"""T37: Hermetic tests for durable scheduler migrations, cron/TZ/DST, idempotency, and recovery."""

from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import pytest

from hydra_orch.core.checkpointer import ExecutionStore, MigrationError, OptimisticLockError
from hydra_orch.core.scheduler import (
    AutomationRunRecord,
    AutomationSchedule,
    SchedulerService,
    compute_next_occurrence,
    parse_cron_expression,
)
from hydra_orch.model import BudgetPolicy, CheckSpec, ContractViolation, RunSpec, TaskSpec

MIGRATIONS = Path(__file__).resolve().parents[1] / "migration"
BASE_SHA = "a" * 40


def copy_migrations(tmp_path: Path, *, up_to: str = "0003") -> Path:
    directory = tmp_path / "migration"
    directory.mkdir(exist_ok=True)
    shutil.copy(MIGRATIONS / "0001_initial_core.sql", directory)
    if up_to >= "0002":
        shutil.copy(MIGRATIONS / "0002_control_plane.sql", directory)
    if up_to >= "0003":
        shutil.copy(MIGRATIONS / "0003_ui_automation.sql", directory)
    if (MIGRATIONS / "rollback").is_dir():
        shutil.copytree(MIGRATIONS / "rollback", directory / "rollback")
    return directory


def read_db(path: Path, sql: str, params: tuple[Any, ...] = ()) -> List[tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as db:
        return db.execute(sql, params).fetchall()


def _build_run_spec(repo_root: str, run_id: str, project_id: str = "proj-sched") -> RunSpec:
    task = TaskSpec(
        task_id=f"{run_id}-t1",
        run_id=run_id,
        objective="Execute scheduled automation",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="check-1", command=("python", "--version")),),
        allowed_paths=("src/hydra_orch/core/scheduler.py",),
    )
    return RunSpec(
        run_id=run_id,
        project_id=project_id,
        objective="Scheduled run",
        repo_root=repo_root,
        base_sha=BASE_SHA,
        base_branch="main",
        orchestration_mode="relay",
        budget_policy=BudgetPolicy(max_usd=1.0),
        idempotency_key=f"idemp-{run_id}-0001",
        tasks=(task,),
    )


def _make_store(tmp_path: Path) -> ExecutionStore:
    mig_dir = copy_migrations(tmp_path, up_to="0003")
    return ExecutionStore(tmp_path / "scheduler.sqlite", migrations_dir=mig_dir)


# ---------------------------------------------------------------------------
# Migration & Rollback Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_0003_applies_cleanly_and_rolls_back_when_empty(tmp_path: Path) -> None:
    mig_dir = copy_migrations(tmp_path, up_to="0003")
    db_path = tmp_path / "mig.sqlite"
    store = ExecutionStore(db_path, migrations_dir=mig_dir)
    await store.initialize()

    versions = await store.get_applied_migrations()
    assert [v["version"] for v in versions] == ["0001", "0002", "0003"]
    tables = {r[0] for r in read_db(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"automation_schedules", "automation_runs"} <= tables
    indexes = {r[0] for r in read_db(db_path, "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_automation_schedules_due", "idx_automation_runs_schedule_for"} <= indexes
    assert read_db(db_path, "PRAGMA foreign_key_check") == []
    assert read_db(db_path, "PRAGMA integrity_check") == [("ok",)]

    reverted = await store.rollback_migrations("0002")
    assert reverted == ["0003"]
    assert [v["version"] for v in await store.get_applied_migrations()] == ["0001", "0002"]
    tables_after = {r[0] for r in read_db(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "automation_schedules" not in tables_after
    assert "automation_runs" not in tables_after
    assert read_db(db_path, "PRAGMA foreign_key_check") == []


@pytest.mark.asyncio
async def test_migration_0003_rollback_refuses_nonempty_tables_and_enforces_constraints(tmp_path: Path) -> None:
    mig_dir = copy_migrations(tmp_path, up_to="0003")
    db_path = tmp_path / "guard.sqlite"
    store = ExecutionStore(db_path, migrations_dir=mig_dir)
    await store.initialize()

    # Validate SQLite CHECK constraints directly
    async with store._connect() as db:
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                "INSERT INTO automation_schedules (id, name, prompt, interval_seconds) VALUES ('s1', 'bad', 'p', 30)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                "INSERT INTO automation_schedules (id, name, prompt) VALUES ('s2', 'bad', 'p')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                "INSERT INTO automation_schedules (id, name, prompt, cron_expr, max_retries) VALUES ('s3', 'bad', 'p', '* * * * *', 6)"
            )

    service = SchedulerService(store)
    sched = await service.create_schedule("Daily Sweep", "Run audit", cron_expr="0 3 * * *")

    with pytest.raises(MigrationError, match="Failed rolling back"):
        await store.rollback_migrations("0002")

    assert read_db(db_path, "SELECT version FROM schema_migrations ORDER BY version") == [
        ("0001",), ("0002",), ("0003",)
    ]
    assert (await service.get_schedule(sched.id)).name == "Daily Sweep"
    assert read_db(db_path, "PRAGMA foreign_key_check") == []


@pytest.mark.asyncio
async def test_schedule_fk_bindings_for_project_and_workspace_on_delete_set_null(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    await store.initialize()

    # Create a project + run, and an area + area_workspace
    spec = _build_run_spec(str(tmp_path / "repo"), "run-fk-1", project_id="proj-fk-1")
    await store.submit_run_idempotent(spec)
    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute(
                "INSERT INTO areas (id, name, owner_principal_id) VALUES ('area-1', 'Core', 'operator')"
            )
            await db.execute(
                "INSERT INTO area_workspaces (id, area_id, name) VALUES ('ws-1', 'area-1', 'Main WS')"
            )

    async def dispatch(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        return {"run_id": spec.run_id, "status": "dispatched"}

    service = SchedulerService(store, dispatcher=dispatch)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    proj_sched = await service.create_schedule(
        "Project bound", "Check project", interval_seconds=60, project_id="proj-fk-1", next_run_at=t0
    )
    ws_sched = await service.create_schedule(
        "Workspace bound", "Check ws", interval_seconds=60, workspace_id="ws-1", enabled=False
    )
    standalone = await service.create_schedule(
        "Standalone", "Check standalone", interval_seconds=60, enabled=False
    )

    assert proj_sched.project_id == "proj-fk-1" and proj_sched.workspace_id is None
    assert ws_sched.workspace_id == "ws-1" and ws_sched.project_id is None
    assert standalone.workspace_id is None and standalone.project_id is None

    await service.tick(now=t0)
    assert (await service.list_runs(proj_sched.id))[0].run_id == spec.run_id

    # Deleting project, run, and workspace sets FKs to NULL cleanly without errors
    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute("DELETE FROM runs WHERE id = ?", (spec.run_id,))
            await db.execute("DELETE FROM projects WHERE id = 'proj-fk-1'")
            await db.execute("DELETE FROM area_workspaces WHERE id = 'ws-1'")

    assert (await service.get_schedule(proj_sched.id)).project_id is None
    assert (await service.get_schedule(ws_sched.id)).workspace_id is None
    assert (await service.list_runs(proj_sched.id))[0].run_id is None
    assert read_db(Path(store.db_path), "PRAGMA foreign_key_check") == []


# ---------------------------------------------------------------------------
# Cron Parser & Validation Tests
# ---------------------------------------------------------------------------


def test_parse_cron_expression_valid_features() -> None:
    c_steps = parse_cron_expression("*/5 9-17 1,15 * 1-5")
    assert c_steps.minutes == frozenset(range(0, 60, 5))
    assert c_steps.hours == frozenset(range(9, 18))
    assert c_steps.days_of_month == frozenset({1, 15})
    assert c_steps.days_of_week == frozenset({1, 2, 3, 4, 5})

    assert parse_cron_expression("@hourly").minutes == frozenset({0})
    assert parse_cron_expression("@daily").hours == frozenset({0})
    assert parse_cron_expression("@weekly").days_of_week == frozenset({0})
    assert parse_cron_expression("0 0 * * 7").days_of_week == frozenset({0})
    assert parse_cron_expression("0 0 * * 5-7").days_of_week == frozenset({5, 6, 0})
    assert parse_cron_expression("0 0 29 2 *").days_of_month == frozenset({29})


@pytest.mark.parametrize(
    "bad_expr",
    [
        "",
        "   ",
        "* * * *",
        "* * * * * *",
        "60 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * 32 * *",
        "* * * 0 *",
        "* * * 13 *",
        "* * * * 8",
        "*/0 * * * *",
        "*/-1 * * * *",
        "*/abc * * * *",
        "5-1 * * * *",
        "1,,2 * * * *",
        ",1 * * * *",
        "0 0 31 2 *",
        "0 0 31 4 *",
        "@reboot",
        "0 0 * *\x00 *",
    ],
)
def test_parse_cron_expression_rejects_malformed(bad_expr: str) -> None:
    with pytest.raises(ContractViolation) as exc:
        parse_cron_expression(bad_expr)
    assert exc.value.code == "invalid_schedule"


def test_compute_next_occurrence_rejects_invalid_timezone() -> None:
    for tz in ("Mars/Phobos", "", "../UTC", "America/Not_A_Real_City"):
        with pytest.raises(ContractViolation) as exc:
            compute_next_occurrence("0 * * * *", timezone=tz)
        assert exc.value.code == "invalid_timezone"


# ---------------------------------------------------------------------------
# DST Transition Tests
# ---------------------------------------------------------------------------


def test_dst_spring_forward_america_new_york_2026_03_08() -> None:
    ny = ZoneInfo("America/New_York")

    # 02:30 does not exist on 2026-03-08; must skip nonexistent wall time (never silently shift to 03:30)
    before_gap = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
    occ = compute_next_occurrence("30 2 * * *", timezone="America/New_York", after=before_gap)
    assert occ == datetime(2026, 3, 9, 6, 30, tzinfo=timezone.utc)
    local = occ.astimezone(ny)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 3, 9, 2, 30)

    # Every 30 minutes across the spring-forward boundary must stay strictly monotonic without skipping 03:00
    slots: List[datetime] = []
    cursor = datetime(2026, 3, 8, 5, 45, tzinfo=timezone.utc)  # 00:45 EST
    for _ in range(5):
        cursor = compute_next_occurrence("*/30 * * * *", timezone="America/New_York", after=cursor)
        slots.append(cursor)

    assert slots == [
        datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),   # 01:00-05:00
        datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc),  # 01:30-05:00
        datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc),   # 03:00-04:00 (02:00/02:30 skipped)
        datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc),  # 03:30-04:00
        datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc),   # 04:00-04:00
    ]
    assert all(slots[i] < slots[i + 1] for i in range(len(slots) - 1))


def test_dst_fall_back_america_new_york_2026_11_01() -> None:
    ny = ZoneInfo("America/New_York")

    # Daily job at 01:30 must fire once at fold=0 (05:30Z), never duplicate on fold=1 (06:30Z)
    start = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)  # 00:00 EDT
    occ1 = compute_next_occurrence("30 1 * * *", timezone="America/New_York", after=start)
    assert occ1 == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    assert occ1.astimezone(ny).fold == 0

    occ2 = compute_next_occurrence("30 1 * * *", timezone="America/New_York", after=occ1)
    assert occ2 == datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)

    # Even starting during the ambiguous fold hour (01:15 EST, fold=1 = 06:15Z), never jump backward to 05:30Z
    in_fold = datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc)
    occ3 = compute_next_occurrence("30 1 * * *", timezone="America/New_York", after=in_fold)
    assert occ3 > in_fold
    assert occ3 == datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)

    # Sub-hourly job (*/30 * * * *) must run monotonically through both folds without skipping 01:00/01:30 EST
    sub_slots: List[datetime] = []
    cur = datetime(2026, 11, 1, 4, 45, tzinfo=timezone.utc)  # 00:45 EDT
    for _ in range(5):
        cur = compute_next_occurrence("*/30 * * * *", timezone="America/New_York", after=cur)
        sub_slots.append(cur)

    assert sub_slots == [
        datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc),   # 01:00-04:00 (fold=0)
        datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc),  # 01:30-04:00 (fold=0)
        datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc),   # 01:00-05:00 (fold=1)
        datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc),  # 01:30-05:00 (fold=1)
        datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc),   # 02:00-05:00
    ]


def test_timezone_america_sao_paulo_and_historical_dst() -> None:
    # Current BRT (UTC-3): 22:00 Friday in Sao Paulo -> 01:00 UTC Saturday; next weekday Mon 22:00 -> Tue 01:00Z
    friday_evening_utc = datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)  # 20:00 BRT Friday
    occ1 = compute_next_occurrence("0 22 * * 1-5", timezone="America/Sao_Paulo", after=friday_evening_utc)
    assert occ1 == datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
    occ2 = compute_next_occurrence("0 22 * * 1-5", timezone="America/Sao_Paulo", after=occ1)
    assert occ2 == datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)  # Mon 22:00 BRT

    # Historical Sao Paulo spring-forward 2018-11-04 00:00->01:00
    pre_sp_dst = datetime(2018, 11, 3, 12, 0, tzinfo=timezone.utc)
    occ_sp = compute_next_occurrence("0 0 * * *", timezone="America/Sao_Paulo", after=pre_sp_dst)
    assert occ_sp == datetime(2018, 11, 5, 2, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CRUD, Validation, Redaction & Pause/Resume Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crud_validation_redaction_and_pause_resume(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    service = SchedulerService(store)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)

    # Reject NUL bytes, invalid timing, invalid policies, invalid TZ
    with pytest.raises(ContractViolation) as exc:
        await service.create_schedule("bad\x00name", "prompt", interval_seconds=60)
    assert exc.value.code == "invalid_schedule"

    with pytest.raises(ContractViolation) as exc:
        await service.create_schedule("both", "prompt", cron_expr="* * * * *", interval_seconds=60)
    assert exc.value.code == "invalid_schedule"

    with pytest.raises(ContractViolation) as exc:
        await service.create_schedule("neither", "prompt")
    assert exc.value.code == "invalid_schedule"

    with pytest.raises(ContractViolation) as exc:
        await service.create_schedule("too-fast", "prompt", interval_seconds=59)
    assert exc.value.code == "invalid_schedule"

    with pytest.raises(ContractViolation) as exc:
        await service.create_schedule("bad-tz", "prompt", cron_expr="0 * * * *", timezone="Unknown/Zone")
    assert exc.value.code == "invalid_timezone"

    # Secrets in prompt/name are redacted
    sched = await service.create_schedule(
        "Nightly Bearer secret_tok_123456",
        "Audit repo with sk-proj1234567890abcdef",
        cron_expr="0 * * * *",
        timezone="UTC",
        now=t0,
    )
    assert "secret_tok_123456" not in sched.name
    assert "sk-proj1234567890abcdef" not in sched.prompt
    assert "[REDACTED]" in sched.prompt
    assert sched.next_run_at == datetime(2026, 11, 13, 11, 0, tzinfo=timezone.utc)
    assert sched.revision == 1

    # Pause clears next_run_at; resume recomputes from `now`
    paused = await service.set_enabled(sched.id, False, expected_revision=1, now=t0 + timedelta(minutes=5))
    assert paused.enabled is False
    assert paused.next_run_at is None
    assert paused.revision == 2

    with pytest.raises(OptimisticLockError):
        await service.update_schedule(sched.id, name="Stale", expected_revision=1)

    resumed = await service.set_enabled(sched.id, True, expected_revision=2, now=t0 + timedelta(hours=3, minutes=10))
    assert resumed.enabled is True
    assert resumed.next_run_at == datetime(2026, 11, 13, 14, 0, tzinfo=timezone.utc)
    assert resumed.revision == 3

    # Switch from cron to interval
    switched = await service.update_schedule(resumed.id, interval_seconds=120, now=t0)
    assert switched.cron_expr is None
    assert switched.interval_seconds == 120
    assert switched.next_run_at == t0 + timedelta(seconds=120)

    assert len(await service.list_schedules(enabled=True)) == 1
    assert await service.list_schedules(enabled=False) == []

    await service.delete_schedule(sched.id)
    with pytest.raises(ContractViolation) as not_found:
        await service.get_schedule(sched.id)
    assert not_found.value.code == "resource_not_found"


# ---------------------------------------------------------------------------
# Restart Idempotency & Concurrency Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_idempotency_and_concurrent_tick_race(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    dispatched_calls: List[tuple[str, str]] = []
    counter = 0

    async def dispatcher(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        nonlocal counter
        counter += 1
        run_id = f"run-idemp-{counter}"
        await store.submit_run_idempotent(_build_run_spec(str(tmp_path / "repo"), run_id))
        dispatched_calls.append((sched.id, occ_key))
        return {"run_id": run_id, "status": "dispatched"}

    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    sched_svc_1 = SchedulerService(store, dispatcher=dispatcher)
    sched = await sched_svc_1.create_schedule(
        "Idempotent Cron",
        "Run checks",
        cron_expr="* * * * *",
        next_run_at=t0,
    )

    first = await sched_svc_1.tick(now=t0)
    assert len(first) == 1
    assert first[0]["status"] == "dispatched"
    assert first[0]["run_id"] == "run-idemp-1"

    # Simulate server restart with a brand new SchedulerService instance on the same store
    sched_svc_2 = SchedulerService(store, dispatcher=dispatcher)
    second = await sched_svc_2.tick(now=t0 + timedelta(seconds=5))
    assert second == []
    assert len(dispatched_calls) == 1

    # Mark first run completed, then verify even if next_run_at in DB was stale/reverted to T0 after a crash,
    # UNIQUE(schedule_id, occurrence_key) blocks double dispatch
    await sched_svc_2.complete_run(first[0]["automation_run_id"], status="succeeded", now=t0 + timedelta(seconds=6))
    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute(
                "UPDATE automation_schedules SET next_run_at = ? WHERE id = ?",
                (t0.isoformat(timespec="microseconds"), sched.id),
            )
    third = await sched_svc_2.tick(now=t0 + timedelta(seconds=10))
    assert third == []
    assert len(dispatched_calls) == 1
    assert (await sched_svc_2.get_schedule(sched.id)).next_run_at > t0 + timedelta(seconds=10)

    # Concurrent ticks racing on the next slot T0+60s must also dispatch strictly once
    t1 = t0 + timedelta(minutes=1)
    sched_svc_a = SchedulerService(store, dispatcher=dispatcher)
    sched_svc_b = SchedulerService(store, dispatcher=dispatcher)
    res_a, res_b = await asyncio.gather(sched_svc_a.tick(now=t1), sched_svc_b.tick(now=t1))
    assert len(res_a) + len(res_b) == 1
    assert len(dispatched_calls) == 2
    combined = res_a + res_b
    assert combined[0]["status"] == "dispatched"
    assert combined[0]["occurrence_key"] == f"{sched.id}:{t1.isoformat()}"


# ---------------------------------------------------------------------------
# Offline / Missed Recovery Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["cron", "interval"])
async def test_missed_policy_skip_vs_run_once(tmp_path: Path, mode: str) -> None:
    store = _make_store(tmp_path)
    dispatches: List[tuple[str, str]] = []
    counter = 0

    async def dispatcher(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        nonlocal counter
        counter += 1
        run_id = f"run-missed-{counter}"
        await store.submit_run_idempotent(_build_run_spec(str(tmp_path / "repo"), run_id))
        dispatches.append((sched.name, occ_key))
        return {"run_id": run_id, "status": "succeeded"}

    service = SchedulerService(store, dispatcher=dispatcher)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    timing_kwargs: Dict[str, Any] = (
        {"cron_expr": "*/5 * * * *"} if mode == "cron" else {"interval_seconds": 300}
    )

    skip_sched = await service.create_schedule(
        "Skip Missed", "Prompt", missed_policy="skip", next_run_at=t0, **timing_kwargs
    )
    once_sched = await service.create_schedule(
        "Run Once Missed", "Prompt", missed_policy="run_once", next_run_at=t0, **timing_kwargs
    )

    # Machine offline for 22 minutes (missed 10:00, 10:05, 10:10, 10:15, 10:20)
    now = datetime(2026, 11, 13, 10, 22, tzinfo=timezone.utc)
    results = await service.tick(now=now)

    by_sched = {item["schedule_id"]: item for item in results}
    assert by_sched[skip_sched.id]["status"] == "missed"
    assert by_sched[skip_sched.id]["run_id"] is None

    expected_latest = datetime(2026, 11, 13, 10, 20, tzinfo=timezone.utc)
    expected_next = datetime(2026, 11, 13, 10, 25, tzinfo=timezone.utc)

    assert by_sched[once_sched.id]["status"] == "succeeded"
    assert by_sched[once_sched.id]["occurrence_key"] == f"{once_sched.id}:{expected_latest.isoformat()}"
    assert len(dispatches) == 1
    assert dispatches[0][0] == "Run Once Missed"

    assert (await service.get_schedule(skip_sched.id)).next_run_at == expected_next
    assert (await service.get_schedule(once_sched.id)).next_run_at == expected_next


# ---------------------------------------------------------------------------
# Overlap Protection & Manual Trigger Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overlap_policies_skip_queue_allow_and_trigger_now(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    counter = 0

    async def dispatcher(sched: AutomationSchedule, occ_key: str) -> Dict[str, Any]:
        nonlocal counter
        counter += 1
        run_id = f"run-ov-{counter}"
        await store.submit_run_idempotent(_build_run_spec(str(tmp_path / "repo"), run_id))
        return {"run_id": run_id, "status": "dispatched"}

    service = SchedulerService(store, dispatcher=dispatcher)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)

    s_skip = await service.create_schedule(
        "Overlap Skip", "p", interval_seconds=60, overlap_policy="skip", next_run_at=t0
    )
    s_queue = await service.create_schedule(
        "Overlap Queue", "p", interval_seconds=60, overlap_policy="queue", next_run_at=t0
    )
    s_allow = await service.create_schedule(
        "Overlap Allow", "p", interval_seconds=60, overlap_policy="allow", next_run_at=t0
    )

    # First tick: all 3 dispatch (leaving all 3 in 'dispatched')
    r1 = await service.tick(now=t0)
    assert [item["status"] for item in r1] == ["dispatched", "dispatched", "dispatched"]
    first_by_id = {item["schedule_id"]: item for item in r1}

    # Manual trigger while active
    with pytest.raises(ContractViolation) as exc:
        await service.trigger_now(s_skip.id, now=t0 + timedelta(seconds=10))
    assert exc.value.code == "schedule_overlap"

    manual_allow = await service.trigger_now(s_allow.id, now=t0 + timedelta(seconds=10))
    assert manual_allow["occurrence_key"].startswith("manual:")
    assert manual_allow["status"] == "dispatched"

    # Second tick at t0 + 60s while active
    t1 = t0 + timedelta(seconds=60)
    r2 = await service.tick(now=t1)
    by_id_2 = {item["schedule_id"]: item for item in r2}
    assert by_id_2[s_skip.id]["status"] == "skipped"
    assert by_id_2[s_skip.id]["run_id"] is None
    assert by_id_2[s_queue.id]["status"] == "pending"
    assert by_id_2[s_queue.id]["run_id"] is None
    assert by_id_2[s_allow.id]["status"] == "dispatched"

    # Complete active run for s_queue -> next tick before t2 drains the queued pending run
    await service.complete_run(first_by_id[s_queue.id]["automation_run_id"], status="succeeded", now=t1 + timedelta(seconds=5))
    r3 = await service.tick(now=t1 + timedelta(seconds=10))
    assert len(r3) == 1
    assert r3[0]["schedule_id"] == s_queue.id
    assert r3[0]["status"] == "dispatched"
    assert r3[0]["run_id"] is not None


# ---------------------------------------------------------------------------
# Failure Propagation, Missing Dispatcher & Retry Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_dispatcher_and_failing_results_never_claim_success(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)

    no_disp = SchedulerService(store, dispatcher=None)
    sched = await no_disp.create_schedule("No Disp", "Prompt", interval_seconds=60, next_run_at=t0)

    res = await no_disp.tick(now=t0)
    assert len(res) == 1
    assert res[0]["status"] == "failed"
    assert res[0]["run_id"] is None
    assert res[0]["error_detail"] == "no_dispatcher_configured"

    # Returning None or failure dict never invents a fake run_id and redacts secrets
    async def bad_dispatcher(s: AutomationSchedule, occ: str) -> Any:
        if occ.startswith("manual:"):
            return {"status": "failed", "error": "Auth failed Bearer topsecret_token_999"}
        return None

    bad_svc = SchedulerService(store, dispatcher=bad_dispatcher)
    manual_res = await bad_svc.trigger_now(sched.id, now=t0 + timedelta(seconds=5))
    assert manual_res["status"] == "failed"
    assert manual_res["run_id"] is None
    assert "topsecret_token_999" not in (manual_res["error_detail"] or "")
    assert "[REDACTED]" in (manual_res["error_detail"] or "")

    tick_none = await bad_svc.tick(now=t0 + timedelta(seconds=60))
    assert tick_none[0]["status"] == "failed"
    assert tick_none[0]["run_id"] is None

    runs = await bad_svc.list_runs(sched.id)
    assert len(runs) == 3
    assert all(r.status == "failed" and r.run_id is None for r in runs)


@pytest.mark.asyncio
async def test_dispatcher_exception_retries_up_to_max_retries_and_redacts(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    attempts_by_occ: Dict[str, int] = {}

    async def flaky_dispatcher(sched: AutomationSchedule, occ: str) -> Dict[str, Any]:
        attempts_by_occ[occ] = attempts_by_occ.get(occ, 0) + 1
        if sched.name == "Flaky Succeeds" and attempts_by_occ[occ] < 3:
            raise RuntimeError("transient gateway error api_key=sk-live1234567890")
        if sched.name == "Always Fails":
            raise RuntimeError("fatal error sk-alwaysfail12345678")
        run_id = f"run-retry-{attempts_by_occ[occ]}"
        await store.submit_run_idempotent(_build_run_spec(str(tmp_path / "repo"), run_id))
        return {"run_id": run_id, "status": "succeeded"}

    service = SchedulerService(store, dispatcher=flaky_dispatcher)
    s_ok = await service.create_schedule("Flaky Succeeds", "p", interval_seconds=60, max_retries=2, next_run_at=t0)
    s_fail = await service.create_schedule("Always Fails", "p", interval_seconds=60, max_retries=2, next_run_at=t0)

    results = await service.tick(now=t0)
    by_sched = {r["schedule_id"]: r for r in results}

    assert by_sched[s_ok.id]["status"] == "succeeded"
    assert by_sched[s_ok.id]["attempt_count"] == 3
    assert by_sched[s_ok.id]["run_id"] == "run-retry-3"
    assert by_sched[s_ok.id]["error_detail"] is None

    assert by_sched[s_fail.id]["status"] == "failed"
    assert by_sched[s_fail.id]["attempt_count"] == 3
    assert by_sched[s_fail.id]["run_id"] is None
    err = by_sched[s_fail.id]["error_detail"] or ""
    assert "sk-alwaysfail12345678" not in err
    assert "[REDACTED]" in err
