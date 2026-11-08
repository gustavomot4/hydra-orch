from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict

import aiosqlite
import pytest

from hydra_orch.core.checkpointer import (
    ExecutionStore,
    IdempotencyConflictError,
    MigrationError,
    OptimisticLockError,
    StorageIntegrityError,
    StorageLockError,
    StreamCheckpointer,
    _compute_migration_checksum,
    _split_sql_statements,
)
from hydra_orch.engine.checkpointer import EngineCheckpointer
from hydra_orch.model import (
    Artifact,
    BudgetPolicy,
    CheckResult,
    CheckSpec,
    HandoffCheckpoint,
    InvalidTransitionError,
    ProcessStatus,
    ReviewDecision,
    RunSpec,
    RunStatus,
    TaskAttempt,
    TaskResult,
    TaskSpec,
    TaskStatus,
    ToolEffect,
)

BASE_SHA = "a" * 40
PATCH_SHA = "b" * 40
HASH_PATCH = "1" * 64
HASH_STDOUT = "2" * 64
HASH_STDERR = "3" * 64


def _make_run_spec(
    repo_root: str,
    *,
    run_id: str = "run-001",
    project_id: str = "proj-001",
    idempotency_key: str = "idemp-key-0001-abcd",
    objective: str = "Implement transactional store",
) -> RunSpec:
    t1 = TaskSpec(
        task_id=f"{run_id}-t1",
        run_id=run_id,
        objective="Create core schema",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="pytest-unit",
                command=("python", "-m", "pytest", "tests/test_checkpointer.py"),
            ),
        ),
        allowed_paths=("src/hydra_orch/core/checkpointer.py", "tests/test_checkpointer.py"),
    )
    t2 = TaskSpec(
        task_id=f"{run_id}-t2",
        run_id=run_id,
        objective="Verify migrations",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="pytest-mig",
                command=("python", "-m", "pytest", "tests/test_checkpointer.py"),
            ),
        ),
        allowed_paths=("migration/0001_initial_core.sql",),
        dependencies=(t1.task_id,),
    )
    return RunSpec(
        run_id=run_id,
        project_id=project_id,
        objective=objective,
        repo_root=repo_root,
        base_sha=BASE_SHA,
        base_branch="main",
        orchestration_mode="relay",
        budget_policy=BudgetPolicy(max_usd=5.0, max_tokens_in=10000, max_tokens_out=5000),
        idempotency_key=idempotency_key,
        tasks=(t1, t2),
    )


@pytest.mark.asyncio
async def test_checkpointer_lifecycle():
    """Backwards-compatible StreamCheckpointer test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_checkpoints.sqlite")
        cp = StreamCheckpointer(db_path=db_path)
        await cp.initialize()

        await cp.save_checkpoint(
            session_id="test-session-1",
            task_id="task-100",
            provider="claude_pro",
            prompt="Write a fastapi backend",
            accumulated_content="from fastapi import FastAPI...",
            status="in_progress",
        )

        record = await cp.get_checkpoint("test-session-1")
        assert record is not None
        assert record["session_id"] == "test-session-1"
        assert record["provider"] == "claude_pro"
        assert "from fastapi import FastAPI" in record["accumulated_content"]
        assert await cp.get_checkpoint("non-existent-session") is None

        assert await cp.is_provider_limited("claude_pro") is False
        assert await cp.get_remaining_limit_seconds("claude_pro") == 0
        await cp.record_provider_limit("claude_pro", reset_in_seconds=300, reason="5h quota reached")
        assert await cp.is_provider_limited("claude_pro") is True
        rem = await cp.get_remaining_limit_seconds("claude_pro")
        assert rem > 0

        # Expired rate limit transitions provider back to ready
        await cp.record_provider_limit("claude_pro", reset_in_seconds=-5, reason="expired")
        assert await cp.is_provider_limited("claude_pro") is False

        prompt_with_diff = cp.build_hot_handoff_prompt(
            original_prompt="Fix bug",
            partial_output="step 1 done",
            failed_provider="claude_pro",
            git_diff="+fixed line",
        )
        assert "Verified Git Diff" in prompt_with_diff
        prompt_no_diff = cp.build_hot_handoff_prompt(
            original_prompt="Fix bug",
            partial_output="step 1 done",
            failed_provider="claude_pro",
        )
        assert "Original Task Objective" in prompt_no_diff


@pytest.mark.asyncio
async def test_pragmas_and_migrations_idempotent(tmp_path: Path):
    db_path = tmp_path / "store.sqlite"
    store = ExecutionStore(db_path=db_path)

    # First initialize without migrations, then with migrations
    await store.initialize(apply_migrations=False)
    await store.initialize(apply_migrations=True)
    # Second call is a fast no-op
    await store.initialize(apply_migrations=True)

    pragmas = await store.get_pragmas()
    assert pragmas["journal_mode"] == "wal"
    assert pragmas["foreign_keys"] == 1
    assert pragmas["busy_timeout"] == 5000
    assert pragmas["synchronous"] in {1, 2}

    migrations = await store.get_applied_migrations()
    assert len(migrations) >= 1
    assert migrations[0]["version"] == "0001"
    assert migrations[0]["name"] == "0001_initial_core.sql"
    assert len(migrations[0]["checksum"]) == 64


@pytest.mark.asyncio
async def test_migration_errors_and_transactional_ddl_rollback(tmp_path: Path):
    db_path = tmp_path / "mig_err.sqlite"
    missing_dir = tmp_path / "does_not_exist"
    store_missing = ExecutionStore(db_path=db_path, migrations_dir=missing_dir)
    with pytest.raises(MigrationError) as exc_info:
        await store_missing.initialize()
    assert exc_info.value.code == "migration_error"

    empty_dir = tmp_path / "empty_mig"
    empty_dir.mkdir()
    store_empty = ExecutionStore(db_path=db_path, migrations_dir=empty_dir)
    with pytest.raises(MigrationError):
        await store_empty.initialize()

    # Empty SQL file (only comments)
    comment_only_dir = tmp_path / "comment_mig"
    comment_only_dir.mkdir()
    (comment_only_dir / "0001_empty.sql").write_text("-- only comment\n", encoding="utf-8")
    store_comment = ExecutionStore(db_path=db_path, migrations_dir=comment_only_dir)
    with pytest.raises(MigrationError, match="no executable SQL"):
        await store_comment.initialize()

    # Transactional DDL rollback: first statement creates table, second statement is invalid SQL
    broken_dir = tmp_path / "broken_mig"
    broken_dir.mkdir()
    (broken_dir / "0001_broken.sql").write_text(
        "CREATE TABLE should_rollback (id TEXT PRIMARY KEY);\n"
        "THIS IS INVALID SQL STATEMENT;\n",
        encoding="utf-8",
    )
    store_broken = ExecutionStore(db_path=db_path, migrations_dir=broken_dir)
    with pytest.raises(MigrationError, match="Failed applying migration"):
        await store_broken.initialize()

    # Verify should_rollback table was rolled back completely
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        )
        assert await cur.fetchone() is None

    # Checksum mismatch detection on already-applied migration
    valid_dir = tmp_path / "valid_mig"
    valid_dir.mkdir()
    mig_file = valid_dir / "0001_init.sql"
    mig_file.write_text("CREATE TABLE t_ok (id TEXT PRIMARY KEY);\n", encoding="utf-8")

    db_ok = tmp_path / "checksum.sqlite"
    store_ok1 = ExecutionStore(db_path=db_ok, migrations_dir=valid_dir)
    await store_ok1.initialize()

    # Modify migration file on disk and re-initialize with a fresh store instance
    mig_file.write_text("CREATE TABLE t_ok (id TEXT PRIMARY KEY, extra TEXT);\n", encoding="utf-8")
    store_ok2 = ExecutionStore(db_path=db_ok, migrations_dir=valid_dir)
    with pytest.raises(MigrationError, match="Checksum mismatch"):
        await store_ok2.initialize()


@pytest.mark.asyncio
async def test_legacy_database_preservation(tmp_path: Path):
    """Verify pre-T03 databases with legacy handoff_checkpoints and schema_migrations without checksum are preserved."""
    db_path = tmp_path / "legacy.sqlite"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE handoff_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                session_id TEXT,
                task_id TEXT,
                git_sha TEXT,
                git_diff TEXT,
                modified_files_json TEXT,
                checks_summary_json TEXT,
                next_step TEXT,
                created_at REAL
            )
            """
        )
        await db.execute(
            """
            INSERT INTO handoff_checkpoints (checkpoint_id, session_id, task_id, git_sha, next_step, created_at)
            VALUES ('legacy-cp-1', 'sess-1', 'task-1', 'abc1234', 'continue', 12345.0)
            """
        )
        await db.commit()

    store = ExecutionStore(db_path=db_path)
    await store.initialize()

    # Verify legacy table was renamed to legacy_handoff_checkpoints with data intact
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM legacy_handoff_checkpoints WHERE checkpoint_id = 'legacy-cp-1'")
        legacy_row = await cur.fetchone()
        assert legacy_row is not None
        assert legacy_row["session_id"] == "sess-1"

        # Canonical handoff_checkpoints has attempt_id column
        info_cur = await db.execute("PRAGMA table_info(handoff_checkpoints)")
        cols = {r["name"] for r in await info_cur.fetchall()}
        assert "attempt_id" in cols

    # EngineCheckpointer can also operate on the same SQLite file without conflict
    engine_cp = EngineCheckpointer(db_path=str(db_path))
    await engine_cp.initialize()
    await engine_cp.save_chunk(
        session_id="eng-sess-1",
        model="claude-sonnet",
        prompt="Test engine",
        accumulated_content="line 1\nline 2",
    )
    sess = await engine_cp.get_session("eng-sess-1")
    assert sess is not None
    assert sess["model"] == "claude-sonnet"


@pytest.mark.asyncio
async def test_idempotent_submission_and_conflict(tmp_path: Path):
    db_path = tmp_path / "idemp.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))

    created1, run1 = await store.submit_run_idempotent(spec)
    assert created1 is True
    assert run1["id"] == "run-001"
    assert run1["status"] == "queued"
    assert run1["revision"] == 1

    # Second submission with identical RunSpec returns existing run without duplicating events
    created2, run2 = await store.submit_run_idempotent(spec)
    assert created2 is False
    assert run2["id"] == "run-001"

    events = await store.get_events("run-001")
    assert len(events) == 1
    assert events[0].event_type == "run.created"
    assert events[0].seq == 1

    # Reusing the same idempotency_key with a different payload raises IdempotencyConflictError
    conflicting_spec = _make_run_spec(
        str(tmp_path),
        run_id="run-002",
        idempotency_key=spec.idempotency_key,
        objective="Different objective payload",
    )
    with pytest.raises(IdempotencyConflictError) as exc_info:
        await store.submit_run_idempotent(conflicting_spec)
    assert exc_info.value.code == "idempotency_conflict"
    assert await store.get_run("run-002") is None

    # Direct record_command across scopes
    is_new, cmd_run_id = await store.record_command(
        idempotency_key="cmd-key-1234567890",
        request_hash="hash-aaa",
        run_id="run-001",
        scope="cancel",
        response_payload={"cancelled": True},
    )
    assert is_new is True
    assert cmd_run_id == "run-001"

    is_new_again, same_cmd_run_id = await store.record_command(
        idempotency_key="cmd-key-1234567890",
        request_hash="hash-aaa",
        run_id="run-001",
        scope="cancel",
    )
    assert is_new_again is False
    assert same_cmd_run_id == "run-001"

    with pytest.raises(IdempotencyConflictError):
        await store.record_command(
            idempotency_key="cmd-key-1234567890",
            request_hash="hash-different",
            run_id="run-001",
            scope="cancel",
        )


@pytest.mark.asyncio
async def test_atomic_rollback_on_injected_event_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prove that if event insertion fails after updating state, the state update rolls back completely."""
    db_path = tmp_path / "rollback.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))
    await store.save_run_atomic(spec)

    orig_insert_event = store._insert_event_in_tx

    async def failing_insert_event(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Injected crash before event commit")

    monkeypatch.setattr(store, "_insert_event_in_tx", failing_insert_event)

    with pytest.raises(RuntimeError, match="Injected crash"):
        await store.update_run_status_atomic(
            run_id="run-001",
            new_status=RunStatus.RUNNING,
            expected_revision=1,
            event_type="run.started",
        )

    with pytest.raises(RuntimeError, match="Injected crash"):
        await store.update_task_status_atomic(
            task_id="run-001-t1",
            new_status=TaskStatus.RUNNING,
            expected_revision=1,
            event_type="task.started",
        )

    monkeypatch.setattr(store, "_insert_event_in_tx", orig_insert_event)

    # Verify both run and task remained at their original status and revision=1
    run_after = await store.get_run("run-001")
    assert run_after is not None
    assert run_after["status"] == "queued"
    assert run_after["revision"] == 1

    task_after = await store.get_task("run-001-t1")
    assert task_after is not None
    assert task_after["status"] == "pending"
    assert task_after["revision"] == 1

    events = await store.get_events("run-001")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_optimistic_locking_and_invalid_transitions(tmp_path: Path):
    db_path = tmp_path / "locks.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))
    await store.save_run_atomic(spec)

    # Invalid transition: queued -> succeeded
    with pytest.raises(InvalidTransitionError):
        await store.update_run_status_atomic(
            run_id="run-001",
            new_status=RunStatus.SUCCEEDED,
            expected_revision=1,
            event_type="run.finished",
        )

    # Valid transition: queued -> running (revision 1 -> 2)
    updated_run = await store.update_run_status_atomic(
        run_id="run-001",
        new_status=RunStatus.RUNNING,
        expected_revision=1,
        event_type="run.started",
    )
    assert updated_run["status"] == "running"
    assert updated_run["revision"] == 2

    # Stale revision (1 instead of 2) raises OptimisticLockError
    with pytest.raises(OptimisticLockError) as exc_info:
        await store.update_run_status_atomic(
            run_id="run-001",
            new_status=RunStatus.WAITING,
            expected_revision=1,
            event_type="run.waiting",
        )
    assert exc_info.value.code == "optimistic_lock_conflict"

    # Task optimistic lock & invalid transition
    with pytest.raises(InvalidTransitionError):
        await store.update_task_status_atomic(
            task_id="run-001-t1",
            new_status=TaskStatus.ACCEPTED,
            expected_revision=1,
            event_type="task.accepted",
        )

    updated_task = await store.update_task_status_atomic(
        task_id="run-001-t1",
        new_status=TaskStatus.RUNNING,
        expected_revision=1,
        event_type="task.started",
    )
    assert updated_task["status"] == "running"
    assert updated_task["revision"] == 2

    with pytest.raises(OptimisticLockError):
        await store.update_task_status_atomic(
            task_id="run-001-t1",
            new_status=TaskStatus.CANCELLED,
            expected_revision=1,
            event_type="task.cancelled",
        )

    # Non-existent entities raise StorageIntegrityError
    with pytest.raises(StorageIntegrityError):
        await store.update_run_status_atomic(
            run_id="no-such-run",
            new_status=RunStatus.RUNNING,
            expected_revision=1,
            event_type="run.started",
        )
    with pytest.raises(StorageIntegrityError):
        await store.update_task_status_atomic(
            task_id="no-such-task",
            new_status=TaskStatus.RUNNING,
            expected_revision=1,
            event_type="task.started",
        )


@pytest.mark.asyncio
async def test_foreign_keys_and_single_active_attempt_constraint(tmp_path: Path):
    db_path = tmp_path / "fk_attempts.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))
    await store.save_run_atomic(spec)

    now = datetime.now(timezone.utc)

    # Attempt referencing non-existent task fails
    orphan_attempt = TaskAttempt(
        attempt_id="att-orphan",
        task_id="task-does-not-exist",
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.QUEUED,
    )
    with pytest.raises(StorageIntegrityError):
        await store.save_attempt_atomic(orphan_attempt)

    # First active attempt (queued) succeeds
    att1_queued = TaskAttempt(
        attempt_id="att-1",
        task_id="run-001-t1",
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.QUEUED,
    )
    await store.save_attempt_atomic(att1_queued)

    # Second concurrent active attempt on the same task is rejected by idx_attempts_active_task
    att2_concurrent = TaskAttempt(
        attempt_id="att-2",
        task_id="run-001-t1",
        run_id="run-001",
        ordinal=2,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.RUNNING,
        started_at=now,
    )
    with pytest.raises(StorageIntegrityError) as exc_info:
        await store.save_attempt_atomic(att2_concurrent)
    assert exc_info.value.code == "storage_integrity_error"

    # Transition att-1: queued -> running -> cancelled
    att1_running = TaskAttempt(
        attempt_id="att-1",
        task_id="run-001-t1",
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.RUNNING,
        started_at=now,
    )
    await store.save_attempt_atomic(att1_running)

    att1_cancelled = TaskAttempt(
        attempt_id="att-1",
        task_id="run-001-t1",
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.CANCELLED,
        started_at=now,
        finished_at=now,
        exit_reason="user_cancelled",
    )
    await store.save_attempt_atomic(att1_cancelled)

    # Now att-2 (ordinal 2) on the same task is allowed!
    await store.save_attempt_atomic(att2_concurrent)
    attempts = await store.list_attempts("run-001-t1")
    assert [a.attempt_id for a in attempts] == ["att-1", "att-2"]


@pytest.mark.asyncio
async def test_full_execution_lifecycle_review_restart_and_replay(tmp_path: Path):
    db_path = tmp_path / "full_lifecycle.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))
    task1_spec = spec.tasks[0]

    await store.save_run_atomic(spec)
    await store.update_run_status_atomic("run-001", RunStatus.RUNNING, expected_revision=1, event_type="run.started")
    await store.update_task_status_atomic(
        task1_spec.task_id,
        TaskStatus.RUNNING,
        expected_revision=1,
        event_type="task.started",
    )

    now = datetime.now(timezone.utc)
    att1_running = TaskAttempt(
        attempt_id="att-101",
        task_id=task1_spec.task_id,
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        workspace_path=str(tmp_path / "wt1"),
        provider_session="sess-xyz",
        process_status=ProcessStatus.RUNNING,
        started_at=now,
    )
    await store.save_attempt_atomic(att1_running)

    # Save handoff checkpoint on att-101
    checkpoint = HandoffCheckpoint(
        checkpoint_id="hcp-101",
        attempt_id="att-101",
        objective=task1_spec.objective,
        instructions=("Keep WAL enabled", "Preserve foreign keys"),
        decisions=("Use BEGIN IMMEDIATE",),
        git_sha=BASE_SHA,
        git_status="M src/hydra_orch/core/checkpointer.py",
        affected_files=("src/hydra_orch/core/checkpointer.py",),
        diff_artifact_ids=("art-patch-1",),
        check_artifact_ids=("art-stdout-1",),
        tools_executed=(
            ToolEffect(
                tool="edit_file",
                summary="Updated checkpointer.py",
                status="confirmed",
                artifact_ids=("art-patch-1",),
            ),
        ),
        partial_output="50% complete",
        next_step="Run pytest",
    )
    await store.save_handoff_checkpoint_atomic(checkpoint, run_id="run-001")

    # Prepare artifacts and completed attempt/result
    art_patch = Artifact(
        artifact_id="art-patch-1",
        run_id="run-001",
        attempt_id="att-101",
        relative_path="artifacts/att-101/diff.patch",
        kind="patch",
        sha256=HASH_PATCH,
        size_bytes=512,
    )
    art_stdout = Artifact(
        artifact_id="art-stdout-1",
        run_id="run-001",
        attempt_id="att-101",
        relative_path="artifacts/att-101/pytest.stdout.log",
        kind="check_output",
        sha256=HASH_STDOUT,
        size_bytes=256,
    )
    art_stderr = Artifact(
        artifact_id="art-stderr-1",
        run_id="run-001",
        attempt_id="att-101",
        relative_path="artifacts/att-101/pytest.stderr.log",
        kind="check_output",
        sha256=HASH_STDERR,
        size_bytes=0,
    )
    await store.save_artifact(art_patch, emit_event=True)
    # Saving identical artifact again is idempotent; different sha256 fails
    await store.save_artifact(art_patch, emit_event=False)
    with pytest.raises(StorageIntegrityError):
        await store.save_artifact(
            Artifact(
                artifact_id="art-patch-1",
                run_id="run-001",
                attempt_id="att-101",
                relative_path="artifacts/att-101/diff.patch",
                kind="patch",
                sha256="9" * 64,
                size_bytes=512,
            )
        )

    att1_exited = TaskAttempt(
        attempt_id="att-101",
        task_id=task1_spec.task_id,
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        workspace_path=str(tmp_path / "wt1"),
        provider_session="sess-xyz",
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now,
        finished_at=now,
        exit_reason="completed",
    )

    result1 = TaskResult(
        result_id="res-101",
        attempt_id="att-101",
        run_id="run-001",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        task_status=TaskStatus.READY_FOR_REVIEW,
        summary="Implemented and verified ExecutionStore",
        simulated=False,
        revision=1,
        patch_commit_sha=PATCH_SHA,
        patch_artifact_id="art-patch-1",
        changed_files=("src/hydra_orch/core/checkpointer.py", "tests/test_checkpointer.py"),
        checks_executed=(
            CheckResult(
                check_id="pytest-unit",
                command=("python", "-m", "pytest", "tests/test_checkpointer.py"),
                tested_sha=PATCH_SHA,
                exit_code=0,
                duration_seconds=1.25,
                stdout_artifact_id="art-stdout-1",
                stderr_artifact_id="art-stderr-1",
            ),
        ),
        artifacts=(art_patch, art_stdout, art_stderr),
        risk_level="low",
    )

    await store.save_task_result_atomic(
        task_spec=task1_spec,
        attempt=att1_exited,
        result=result1,
        expected_task_revision=2,
    )

    # Stale review revision is rejected with OptimisticLockError
    stale_decision = ReviewDecision(
        result_id="res-101",
        actor="lead-engineer",
        decision="accepted",
        reason="LGTM",
        expected_revision=99,
    )
    with pytest.raises(OptimisticLockError):
        await store.record_review_atomic(task1_spec, att1_exited, stale_decision)

    valid_decision = ReviewDecision(
        result_id="res-101",
        actor="lead-engineer",
        decision="accepted",
        reason="All checks green and WAL verified",
        expected_revision=1,
    )
    reviewed = await store.record_review_atomic(
        task_spec=task1_spec,
        attempt=att1_exited,
        decision=valid_decision,
        expected_task_revision=3,
    )
    assert reviewed.task_status == TaskStatus.ACCEPTED
    assert reviewed.revision == 2

    # Simulate process restart by instantiating a brand new ExecutionStore over the same file
    restarted_store = ExecutionStore(db_path=db_path)
    loaded_run = await restarted_store.get_run("run-001")
    assert loaded_run is not None
    assert loaded_run["status"] == "running"
    assert loaded_run["spec"].run_id == "run-001"

    loaded_tasks = await restarted_store.list_tasks("run-001")
    assert len(loaded_tasks) == 2
    t1_loaded = await restarted_store.get_task(task1_spec.task_id)
    assert t1_loaded is not None
    assert t1_loaded["status"] == "accepted"
    assert t1_loaded["revision"] == 4
    t2_loaded = await restarted_store.get_task(spec.tasks[1].task_id)
    assert t2_loaded is not None
    assert t2_loaded["dependencies"] == (task1_spec.task_id,)

    loaded_att = await restarted_store.get_attempt("att-101")
    assert loaded_att is not None
    assert loaded_att.process_status == ProcessStatus.EXITED
    assert loaded_att.exit_code == 0

    loaded_res = await restarted_store.get_result("res-101")
    assert loaded_res is not None
    assert loaded_res.task_status == TaskStatus.ACCEPTED
    assert loaded_res.revision == 2
    assert loaded_res.review is not None
    assert loaded_res.review.actor == "lead-engineer"

    loaded_res_by_att = await restarted_store.get_result_by_attempt("att-101")
    assert loaded_res_by_att == loaded_res

    loaded_arts = await restarted_store.get_artifacts("run-001", attempt_id="att-101", kind="patch")
    assert len(loaded_arts) == 1
    assert loaded_arts[0].artifact_id == "art-patch-1"

    loaded_hcp = await restarted_store.get_handoff_checkpoint("att-101")
    assert loaded_hcp == checkpoint

    # Verify event sequence continuity and SSE replay by after_seq cursor
    all_events = await restarted_store.get_events("run-001")
    assert [e.seq for e in all_events] == list(range(1, len(all_events) + 1))
    assert all_events[0].event_type == "run.created"
    assert all_events[-1].event_type == "task.accepted"

    replay_from_3 = await restarted_store.get_events("run-001", after_seq=3, limit=2)
    assert [e.seq for e in replay_from_3] == [4, 5]

    # Verify payload isolation from in-memory dict mutation
    mutable_payload: Dict[str, Any] = {"nested": {"count": 1}}
    ev = await restarted_store.record_event_atomic("run-001", "heartbeat", payload=mutable_payload)
    mutable_payload["nested"]["count"] = 999
    reloaded_tail = await restarted_store.get_events("run-001", after_seq=ev.seq - 1)
    assert reloaded_tail[0].redacted_payload["nested"]["count"] == 1


@pytest.mark.asyncio
async def test_post_crash_reconciliation(tmp_path: Path):
    """Verify interrupted attempts (queued or running) are reconciled on restart without blind retry."""
    db_path = tmp_path / "crash_reconcile.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))
    await store.save_run_atomic(spec)

    t1_id = spec.tasks[0].task_id
    t2_id = spec.tasks[1].task_id

    await store.update_task_status_atomic(t1_id, TaskStatus.RUNNING, expected_revision=1, event_type="task.started")

    now = datetime.now(timezone.utc)
    # t1 has a RUNNING attempt when process crashes
    await store.save_attempt_atomic(
        TaskAttempt(
            attempt_id="att-running-crash",
            task_id=t1_id,
            run_id="run-001",
            ordinal=1,
            executor_id="codex",
            provider="openai",
            model="gpt-5",
            base_sha=BASE_SHA,
            process_status=ProcessStatus.RUNNING,
            started_at=now,
        )
    )
    # t2 has a QUEUED attempt when process crashes
    await store.save_attempt_atomic(
        TaskAttempt(
            attempt_id="att-queued-crash",
            task_id=t2_id,
            run_id="run-001",
            ordinal=1,
            executor_id="codex",
            provider="openai",
            model="gpt-5",
            base_sha=BASE_SHA,
            process_status=ProcessStatus.QUEUED,
        )
    )

    # New store instance after restart reconciles interrupted attempts
    recovered_store = ExecutionStore(db_path=db_path)
    reconciled = await recovered_store.reconcile_interrupted_attempts(
        run_id="run-001",
        reason="worker_crash_on_restart",
    )
    assert len(reconciled) == 2

    att_r = await recovered_store.get_attempt("att-running-crash")
    assert att_r is not None
    assert att_r.process_status == ProcessStatus.CRASHED
    assert att_r.exit_reason == "worker_crash_on_restart"
    assert att_r.finished_at is not None

    att_q = await recovered_store.get_attempt("att-queued-crash")
    assert att_q is not None
    assert att_q.process_status == ProcessStatus.CANCELLED
    assert att_q.exit_reason == "worker_crash_on_restart"
    assert att_q.finished_at is not None

    # Both tasks are marked blocked so they require explicit reconciliation/retry
    t1_state = await recovered_store.get_task(t1_id)
    t2_state = await recovered_store.get_task(t2_id)
    assert t1_state is not None and t1_state["status"] == "blocked"
    assert t2_state is not None and t2_state["status"] == "blocked"

    # Re-running reconciliation is idempotent (0 active attempts left)
    assert await recovered_store.reconcile_interrupted_attempts() == []

    # After reconciliation, a new attempt (ordinal=2) can be scheduled on t1
    new_att = TaskAttempt(
        attempt_id="att-retry-2",
        task_id=t1_id,
        run_id="run-001",
        ordinal=2,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.QUEUED,
    )
    await recovered_store.save_attempt_atomic(new_att)
    assert len(await recovered_store.list_attempts(t1_id)) == 2


@pytest.mark.asyncio
async def test_concurrent_connections_monotonic_events(tmp_path: Path):
    """Two ExecutionStore instances writing concurrently to WAL produce strictly contiguous sequence numbers."""
    db_path = tmp_path / "concurrent.sqlite"
    store_a = ExecutionStore(db_path=db_path)
    store_b = ExecutionStore(db_path=db_path)

    spec = _make_run_spec(str(tmp_path))
    await store_a.save_run_atomic(spec)

    async def emit_batch(store: ExecutionStore, worker_tag: str) -> None:
        for idx in range(5):
            await store.record_event_atomic(
                run_id="run-001",
                event_type="heartbeat",
                payload={"worker": worker_tag, "idx": idx},
            )

    await asyncio.gather(emit_batch(store_a, "A"), emit_batch(store_b, "B"))

    events = await store_a.get_events("run-001")
    # 1 initial run.created + 10 heartbeats = 11 events with seq 1..11
    assert len(events) == 11
    assert [e.seq for e in events] == list(range(1, 12))


def test_sql_helpers_and_hashing():
    sql = "-- comment\nCREATE TABLE a (id INT);\n/* block */\nINSERT INTO a VALUES (1)"
    stmts = _split_sql_statements(sql)
    assert len(stmts) == 2
    assert _compute_migration_checksum("a\r\nb\n") == _compute_migration_checksum("a\nb\n")

    assert ExecutionStore.compute_request_hash(b"abc") == ExecutionStore.compute_request_hash("abc")
    assert ExecutionStore.compute_request_hash({"b": 1, "a": 2}) == ExecutionStore.compute_request_hash({"a": 2, "b": 1})
    with pytest.raises(TypeError):
        ExecutionStore.compute_request_hash(12345)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_additional_edge_cases_and_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "edges.sqlite"
    store = ExecutionStore(db_path=db_path)
    spec = _make_run_spec(str(tmp_path))
    await store.save_run_atomic(spec)

    # Duplicate save_run_atomic with same payload -> StorageIntegrityError; different payload -> IdempotencyConflictError
    with pytest.raises(StorageIntegrityError):
        await store.save_run_atomic(spec)
    with pytest.raises(IdempotencyConflictError):
        await store.save_run_atomic(
            _make_run_spec(
                str(tmp_path),
                run_id="run-diff",
                idempotency_key=spec.idempotency_key,
                objective="Changed objective",
            )
        )

    # Project conflict: same project_id with different repo_root
    other_root = tmp_path / "other_repo"
    other_root.mkdir()
    conflicting_proj_spec = _make_run_spec(
        str(other_root),
        run_id="run-proj-conflict",
        project_id=spec.project_id,
        idempotency_key="idemp-proj-conflict-1234",
    )
    with pytest.raises(StorageIntegrityError, match="Project conflict"):
        await store.save_run_atomic(conflicting_proj_spec)

    # Queries for missing IDs return None
    assert await store.get_run("missing-run") is None
    assert await store.get_task("missing-task") is None
    assert await store.get_attempt("missing-attempt") is None
    assert await store.get_result("missing-result") is None
    assert await store.get_result_by_attempt("missing-attempt") is None
    assert await store.get_handoff_checkpoint("missing-attempt") is None

    t1_spec = spec.tasks[0]
    t2_spec = spec.tasks[1]
    now = datetime.now(timezone.utc)

    # Attempt with mismatched run_id
    bad_run_att = TaskAttempt(
        attempt_id="att-bad-run",
        task_id=t1_spec.task_id,
        run_id="other-run",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.QUEUED,
    )
    with pytest.raises(StorageIntegrityError, match="does not match task run_id"):
        await store.save_attempt_atomic(bad_run_att)

    # Handoff checkpoint for missing attempt or wrong run_id
    hcp = HandoffCheckpoint(
        checkpoint_id="hcp-edge",
        attempt_id="att-missing",
        objective="Test",
        instructions=("inst",),
        git_sha=BASE_SHA,
        git_status="",
        next_step="next",
    )
    with pytest.raises(StorageIntegrityError, match="does not exist"):
        await store.save_handoff_checkpoint_atomic(hcp, run_id="run-001")

    # Reject flow & needs_context / failed result outcomes
    await store.update_task_status_atomic(t1_spec.task_id, TaskStatus.RUNNING, expected_revision=1, event_type="task.started")
    att_t1 = TaskAttempt(
        attempt_id="att-t1-1",
        task_id=t1_spec.task_id,
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.EXITED,
        exit_code=1,
        started_at=now,
        finished_at=now,
        exit_reason="check_failed",
    )
    await store.save_attempt_atomic(att_t1)

    # Handoff checkpoint with wrong run_id raises StorageIntegrityError
    hcp_t1 = HandoffCheckpoint(
        checkpoint_id="hcp-t1",
        attempt_id="att-t1-1",
        objective="Test",
        instructions=("inst",),
        git_sha=BASE_SHA,
        git_status="",
        next_step="next",
    )
    with pytest.raises(StorageIntegrityError, match="belongs to run"):
        await store.save_handoff_checkpoint_atomic(hcp_t1, run_id="wrong-run")

    res_failed = TaskResult(
        result_id="res-fail-1",
        attempt_id="att-t1-1",
        run_id="run-001",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.EXITED,
        exit_code=1,
        task_status=TaskStatus.NEEDS_CONTEXT,
        summary="Needs clarification on schema",
        simulated=False,
    )
    # Wrong expected_task_revision raises OptimisticLockError
    with pytest.raises(OptimisticLockError):
        await store.save_task_result_atomic(t1_spec, att_t1, res_failed, expected_task_revision=99)

    await store.save_task_result_atomic(t1_spec, att_t1, res_failed, expected_task_revision=2)
    t1_after = await store.get_task(t1_spec.task_id)
    assert t1_after is not None and t1_after["status"] == "needs_context"

    # Test rejection review flow on t2
    await store.update_task_status_atomic(t2_spec.task_id, TaskStatus.RUNNING, expected_revision=1, event_type="task.started")
    att_t2 = TaskAttempt(
        attempt_id="att-t2-1",
        task_id=t2_spec.task_id,
        run_id="run-001",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now,
        finished_at=now,
        exit_reason="done",
    )
    await store.save_attempt_atomic(att_t2)
    art_p2 = Artifact(
        artifact_id="art-p2",
        run_id="run-001",
        attempt_id="att-t2-1",
        relative_path="artifacts/att-t2-1/diff.patch",
        kind="patch",
        sha256=HASH_PATCH,
        size_bytes=100,
    )
    art_o2 = Artifact(
        artifact_id="art-o2",
        run_id="run-001",
        attempt_id="att-t2-1",
        relative_path="artifacts/att-t2-1/out.log",
        kind="check_output",
        sha256=HASH_STDOUT,
        size_bytes=50,
    )
    art_e2 = Artifact(
        artifact_id="art-e2",
        run_id="run-001",
        attempt_id="att-t2-1",
        relative_path="artifacts/att-t2-1/err.log",
        kind="check_output",
        sha256=HASH_STDERR,
        size_bytes=0,
    )
    res_t2 = TaskResult(
        result_id="res-t2-1",
        attempt_id="att-t2-1",
        run_id="run-001",
        base_sha=BASE_SHA,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        task_status=TaskStatus.READY_FOR_REVIEW,
        summary="Ready",
        simulated=False,
        patch_commit_sha=PATCH_SHA,
        patch_artifact_id="art-p2",
        changed_files=("migration/0001_initial_core.sql",),
        checks_executed=(
            CheckResult(
                check_id="pytest-mig",
                command=("python", "-m", "pytest", "tests/test_checkpointer.py"),
                tested_sha=PATCH_SHA,
                exit_code=0,
                duration_seconds=0.5,
                stdout_artifact_id="art-o2",
                stderr_artifact_id="art-e2",
            ),
        ),
        artifacts=(art_p2, art_o2, art_e2),
    )
    await store.save_task_result_atomic(t2_spec, att_t2, res_t2)

    reject_decision = ReviewDecision(
        result_id="res-t2-1",
        actor="reviewer",
        decision="rejected",
        reason="Missing index",
        expected_revision=1,
    )
    with pytest.raises(OptimisticLockError):
        await store.record_review_atomic(t2_spec, att_t2, reject_decision, expected_task_revision=99)

    rejected_res = await store.record_review_atomic(t2_spec, att_t2, reject_decision, expected_task_revision=3)
    assert rejected_res.task_status == TaskStatus.REJECTED

    # Missing result in record_review_atomic raises StorageIntegrityError
    missing_decision = ReviewDecision(
        result_id="res-does-not-exist",
        actor="reviewer",
        decision="rejected",
        reason="Missing",
        expected_revision=1,
    )
    with pytest.raises(StorageIntegrityError):
        await store.record_review_atomic(t2_spec, att_t2, missing_decision)

    # Fallback deserialization when attempt_json is NULL in attempts table
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE attempts SET attempt_json = NULL WHERE id = 'att-t2-1'")
        await db.commit()
    att_t2_fallback = await store.get_attempt("att-t2-1")
    assert att_t2_fallback is not None
    assert att_t2_fallback.attempt_id == "att-t2-1"

    # StorageLockError mapping when sqlite raises OperationalError('database is locked')
    orig_insert = store._insert_event_in_tx

    async def locked_error(*args: Any, **kwargs: Any) -> Any:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "_insert_event_in_tx", locked_error)
    with pytest.raises(StorageLockError) as lock_exc:
        await store.record_event_atomic("run-001", "heartbeat")
    assert lock_exc.value.code == "storage_lock_error"
    monkeypatch.setattr(store, "_insert_event_in_tx", orig_insert)
