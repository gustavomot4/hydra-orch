"""Hermetic integration tests for RunService, CheckRunner, WorkerRunner, GitWorkspaceService, and ExecutionStore (S05 / T06)."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from hydra_orch.core.checkpointer import OptimisticLockError
from hydra_orch.core.run_service import RunService
from hydra_orch.model import (
    BudgetPolicy,
    CheckSpec,
    ContractViolation,
    IntegrationStatus,
    InvalidTransitionError,
    ProcessStatus,
    RunSpec,
    RunStatus,
    TaskSpec,
    TaskStatus,
)


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "integration_repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Hydra Test Operator")
    _git(repo, "config", "user.email", "operator@hydra.local")
    (repo / "README.md").write_text("# Integration Repo\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return 0\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore: initial project structure")
    return repo


@pytest.mark.asyncio
async def test_executor_real_subprocess(temp_git_repo: Path) -> None:
    """Verify real subprocess worker edits worktree, commits patch, runs checks, and reaches READY_FOR_REVIEW."""
    service = RunService(repo_root=temp_git_repo)
    base_sha = service.git_workspace.resolve_commit_sha("HEAD")
    snap_before = service.git_workspace.snapshot_operator_checkout()

    task_spec = TaskSpec(
        task_id="task_fix_add",
        run_id="run_subproc_01",
        objective="Implement add(a, b) in src/calculator.py",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_add",
                command=(
                    sys.executable,
                    "-c",
                    "from src.calculator import add; assert add(2, 3) == 5; print('ADD_OK')",
                ),
            ),
        ),
        allowed_paths=("src/**",),
    )
    run_spec = RunSpec(
        run_id="run_subproc_01",
        project_id="proj_calc",
        objective="Fix calculator addition",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="relay",
        idempotency_key="idem_test_executor_real_subproc_01",
        tasks=(task_spec,),
    )

    created, run_rec = await service.submit_run(run_spec)
    assert created is True
    assert run_rec["status"] == RunStatus.QUEUED.value

    # Duplicate submission with same idempotency_key returns existing run without re-creating
    created_dup, _ = await service.submit_run(run_spec)
    assert created_dup is False

    worker_cmd = (
        sys.executable,
        "-c",
        (
            "import pathlib; "
            "pathlib.Path('src/calculator.py').write_text("
            "'def add(a: int, b: int) -> int:\\n    return a + b\\n', encoding='utf-8')"
        ),
    )
    outcome = await service.execute_task_attempt(
        "run_subproc_01",
        "task_fix_add",
        custom_command=worker_cmd,
    )

    assert outcome.attempt.process_status == ProcessStatus.EXITED
    assert outcome.attempt.exit_code == 0
    assert outcome.result.task_status == TaskStatus.READY_FOR_REVIEW
    assert outcome.result.simulated is False
    assert outcome.result.patch_commit_sha is not None
    assert outcome.result.patch_commit_sha != base_sha
    assert outcome.result.changed_files == ("src/calculator.py",)
    assert len(outcome.result.checks_executed) == 1
    assert outcome.result.checks_executed[0].exit_code == 0
    assert outcome.result.checks_executed[0].tested_sha == outcome.result.patch_commit_sha

    from hydra_orch.core.metrics import MetricsService
    metrics = {m.kind: m for m in await MetricsService(service.store).query(
        "run_subproc_01", "attempt", outcome.attempt.attempt_id)}
    assert metrics["duration"].status == "observed" and metrics["duration"].value >= 0
    assert metrics["tokens_in"].value is None and metrics["cost"].value is None
    assert metrics["cost"].source == "worker:not_reported"

    # Verify artifacts on disk match recorded SHA-256 digests
    for art in outcome.result.artifacts:
        art_path = temp_git_repo / art.relative_path
        assert art_path.is_file()
        assert hashlib.sha256(art_path.read_bytes()).hexdigest() == art.sha256

    # Run transitions automatically to REVIEWING once all tasks are READY_FOR_REVIEW
    updated_run = await service.store.get_run("run_subproc_01")
    assert updated_run is not None
    assert updated_run["status"] == RunStatus.REVIEWING.value

    # Operator checkout remains untouched
    service.git_workspace.assert_operator_checkout_intact(snap_before)


@pytest.mark.asyncio
async def test_integrate_accepted_results(temp_git_repo: Path) -> None:
    """Verify full lifecycle: submit -> execute 2 tasks -> review accept -> serialized integrate with combined checks."""
    service = RunService(repo_root=temp_git_repo)
    base_sha = service.git_workspace.resolve_commit_sha("HEAD")
    snap_before = service.git_workspace.snapshot_operator_checkout()

    task_a = TaskSpec(
        task_id="task_add_mod",
        run_id="run_int_ok_01",
        objective="Create src/adder.py",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_adder",
                command=(sys.executable, "-c", "from src.adder import plus; assert plus(4, 5) == 9"),
            ),
        ),
        allowed_paths=("src/adder.py",),
    )
    task_b = TaskSpec(
        task_id="task_mul_mod",
        run_id="run_int_ok_01",
        objective="Create src/multiplier.py",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_multiplier",
                command=(sys.executable, "-c", "from src.multiplier import times; assert times(4, 5) == 20"),
            ),
        ),
        allowed_paths=("src/multiplier.py",),
        dependencies=("task_add_mod",),
    )
    run_spec = RunSpec(
        run_id="run_int_ok_01",
        project_id="proj_calc",
        objective="Add adder and multiplier modules",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        idempotency_key="idem_test_integrate_accepted_001",
        tasks=(task_a, task_b),
    )
    await service.submit_run(run_spec)

    out_a = await service.execute_task_attempt(
        "run_int_ok_01",
        "task_add_mod",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/adder.py').write_text('def plus(a, b):\\n    return a + b\\n')",
        ),
    )
    out_b = await service.execute_task_attempt(
        "run_int_ok_01",
        "task_mul_mod",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/multiplier.py').write_text('def times(a, b):\\n    return a * b\\n')",
        ),
    )
    assert out_a.result.task_status == TaskStatus.READY_FOR_REVIEW
    assert out_b.result.task_status == TaskStatus.READY_FOR_REVIEW

    # Integrating before both tasks are accepted must fail
    with pytest.raises(ContractViolation) as exc_unaccepted:
        await service.integrate_run("run_int_ok_01")
    assert exc_unaccepted.value.code == "result_not_accepted"

    rev_a = await service.review_task_result(
        "run_int_ok_01",
        out_a.result.result_id,
        actor="lead-reviewer",
        decision="accepted",
        reason="Adder verified",
        expected_revision=1,
    )
    rev_b = await service.review_task_result(
        "run_int_ok_01",
        out_b.result.result_id,
        actor="lead-reviewer",
        decision="accepted",
        reason="Multiplier verified",
        expected_revision=1,
    )
    assert rev_a.task_status == TaskStatus.ACCEPTED
    assert rev_b.task_status == TaskStatus.ACCEPTED

    int_outcome = await service.integrate_run("run_int_ok_01")
    assert int_outcome.status == IntegrationStatus.INTEGRATED
    assert int_outcome.result_sha is not None
    assert int_outcome.result_sha != base_sha
    assert int_outcome.merged_result_ids == (out_a.result.result_id, out_b.result.result_id)
    assert len(int_outcome.checks_executed) == 2
    assert all(c.exit_code == 0 and c.tested_sha == int_outcome.result_sha for c in int_outcome.checks_executed)
    assert (int_outcome.integration_worktree_path / "src" / "adder.py").is_file()
    assert (int_outcome.integration_worktree_path / "src" / "multiplier.py").is_file()

    # Task worktrees were safely cleaned up after successful integration
    assert not out_a.workspace.canonical_path.exists()
    assert not out_b.workspace.canonical_path.exists()

    final_run = await service.store.get_run("run_int_ok_01")
    assert final_run is not None
    assert final_run["status"] == RunStatus.SUCCEEDED.value

    # Operator checkout on main is still untouched
    service.git_workspace.assert_operator_checkout_intact(snap_before)


@pytest.mark.asyncio
async def test_integrate_conflict(temp_git_repo: Path) -> None:
    """Verify conflicting accepted tasks block integration, mark run FAILED, and preserve all worktrees."""
    service = RunService(repo_root=temp_git_repo)
    base_sha = service.git_workspace.resolve_commit_sha("HEAD")
    snap_before = service.git_workspace.snapshot_operator_checkout()

    t1 = TaskSpec(
        task_id="task_conf_1",
        run_id="run_int_conflict_01",
        objective="Update calculator version 1",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_c1",
                command=(sys.executable, "-c", "from src.calculator import add; assert add(1, 2) == 3"),
            ),
        ),
        allowed_paths=("src/calculator.py",),
    )
    t2 = TaskSpec(
        task_id="task_conf_2",
        run_id="run_int_conflict_01",
        objective="Update calculator version 2",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_c2",
                command=(sys.executable, "-c", "from src.calculator import add; assert add(1, 2) == 3"),
            ),
        ),
        allowed_paths=("src/calculator.py",),
    )
    run_spec = RunSpec(
        run_id="run_int_conflict_01",
        project_id="proj_calc",
        objective="Concurrent conflicting edits to src/calculator.py",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        idempotency_key="idem_test_integrate_conflict_001",
        tasks=(t1, t2),
    )
    await service.submit_run(run_spec)

    out1 = await service.execute_task_attempt(
        "run_int_conflict_01",
        "task_conf_1",
        custom_command=(
            sys.executable,
            "-c",
            (
                "import pathlib; pathlib.Path('src/calculator.py').write_text("
                "'VARIANT = \"alpha\"\\ndef add(a: int, b: int) -> int:\\n    return a + b\\n')"
            ),
        ),
    )
    out2 = await service.execute_task_attempt(
        "run_int_conflict_01",
        "task_conf_2",
        custom_command=(
            sys.executable,
            "-c",
            (
                "import pathlib; pathlib.Path('src/calculator.py').write_text("
                "'VARIANT = \"omega\"\\ndef add(a: int, b: int) -> int:\\n    return b + a\\n')"
            ),
        ),
    )

    await service.review_task_result(
        "run_int_conflict_01",
        out1.result.result_id,
        actor="lead-reviewer",
        decision="accepted",
        reason="Task 1 accepted",
        expected_revision=1,
    )
    await service.review_task_result(
        "run_int_conflict_01",
        out2.result.result_id,
        actor="lead-reviewer",
        decision="accepted",
        reason="Task 2 accepted",
        expected_revision=1,
    )

    int_outcome = await service.integrate_run("run_int_conflict_01")
    assert int_outcome.status == IntegrationStatus.CONFLICTED
    assert "src/calculator.py" in int_outcome.conflicted_files
    assert int_outcome.failure is not None
    assert int_outcome.failure.code == "merge_conflict"

    # Both task worktrees and integration worktree remain preserved for inspection/repair
    assert out1.workspace.canonical_path.exists()
    assert out2.workspace.canonical_path.exists()
    assert int_outcome.integration_worktree_path.exists()

    final_run = await service.store.get_run("run_int_conflict_01")
    assert final_run is not None
    assert final_run["status"] == RunStatus.FAILED.value

    service.git_workspace.assert_operator_checkout_intact(snap_before)


@pytest.mark.asyncio
async def test_scope_violation_and_empty_patch_block_review(temp_git_repo: Path) -> None:
    """Verify out-of-scope file edits and zero-diff exits result in TaskStatus.FAILED and preserve evidence."""
    service = RunService(repo_root=temp_git_repo)
    base_sha = service.git_workspace.resolve_commit_sha("HEAD")

    task_scope = TaskSpec(
        task_id="task_scope_viol",
        run_id="run_neg_01",
        objective="Attempt out-of-scope modification",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(check_id="chk_noop", command=(sys.executable, "-c", "print('ok')")),
        ),
        allowed_paths=("src/**",),
    )
    task_empty = TaskSpec(
        task_id="task_empty_diff",
        run_id="run_neg_01",
        objective="Exit 0 without touching files",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(check_id="chk_noop", command=(sys.executable, "-c", "print('ok')")),
        ),
        allowed_paths=("src/**",),
    )
    run_spec = RunSpec(
        run_id="run_neg_01",
        project_id="proj_calc",
        objective="Negative validation run",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        idempotency_key="idem_test_scope_and_empty_patch_01",
        tasks=(task_scope, task_empty),
    )
    await service.submit_run(run_spec)

    # 1. Worker modifies README.md which is outside allowed_paths=("src/**",)
    out_scope = await service.execute_task_attempt(
        "run_neg_01",
        "task_scope_viol",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('README.md').write_text('# Unauthorized edit\\n')",
        ),
    )
    assert out_scope.result.task_status == TaskStatus.FAILED
    assert out_scope.result.failures[0].code == "scope_violation"
    assert out_scope.workspace.canonical_path.exists()

    # 2. Worker exits with 0 and prints DONE but makes no file changes
    out_empty = await service.execute_task_attempt(
        "run_neg_01",
        "task_empty_diff",
        custom_command=(sys.executable, "-c", "print('DONE: everything looks great')"),
    )
    assert out_empty.result.task_status == TaskStatus.FAILED
    assert out_empty.result.failures[0].code == "empty_patch"


@pytest.mark.asyncio
async def test_failed_check_and_simulated_dry_run_block_acceptance_and_integration(
    temp_git_repo: Path,
) -> None:
    """Verify failed acceptance check or dry_run simulated execution cannot be accepted or integrated."""
    service = RunService(repo_root=temp_git_repo)
    base_sha = service.git_workspace.resolve_commit_sha("HEAD")

    task_bad_chk = TaskSpec(
        task_id="task_failing_check",
        run_id="run_neg_02",
        objective="Edit file but fail acceptance check",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_must_equal_5",
                command=(
                    sys.executable,
                    "-c",
                    "from src.calculator import add; assert add(2, 3) == 5",
                ),
            ),
        ),
        allowed_paths=("src/calculator.py",),
    )
    task_sim = TaskSpec(
        task_id="task_dry_run_sim",
        run_id="run_neg_02",
        objective="Run in dry-run simulation mode",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(check_id="chk_sim", command=(sys.executable, "-c", "print('ok')")),
        ),
        allowed_paths=("**/*",),
    )
    run_spec = RunSpec(
        run_id="run_neg_02",
        project_id="proj_calc",
        objective="Negative checks and dry-run isolation",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        idempotency_key="idem_test_failed_check_and_sim_02",
        tasks=(task_bad_chk, task_sim),
    )
    await service.submit_run(run_spec)

    # Worker writes buggy implementation (a - b instead of a + b), so check exits non-zero
    out_bad = await service.execute_task_attempt(
        "run_neg_02",
        "task_failing_check",
        custom_command=(
            sys.executable,
            "-c",
            (
                "import pathlib; pathlib.Path('src/calculator.py').write_text("
                "'def add(a: int, b: int) -> int:\\n    return a - b\\n')"
            ),
        ),
    )
    assert out_bad.result.task_status == TaskStatus.FAILED
    assert out_bad.result.failures[0].code == "acceptance_check_failed"
    assert len(out_bad.result.checks_executed) == 1
    assert out_bad.result.checks_executed[0].exit_code != 0

    # Attempting to review a FAILED result as accepted raises InvalidTransitionError
    with pytest.raises(InvalidTransitionError):
        await service.review_task_result(
            "run_neg_02",
            out_bad.result.result_id,
            actor="lead-reviewer",
            decision="accepted",
            reason="Trying to force accept failed check",
            expected_revision=1,
        )

    # Dry-run simulated execution is marked simulated=True and FAILED (not integrable)
    out_sim = await service.execute_task_attempt(
        "run_neg_02",
        "task_dry_run_sim",
        dry_run=True,
    )
    assert out_sim.result.simulated is True
    assert out_sim.result.task_status == TaskStatus.FAILED
    assert out_sim.result.failures[0].code == "simulated_execution"


@pytest.mark.asyncio
async def test_optimistic_review_retry_and_cancel_flow(temp_git_repo: Path) -> None:
    """Verify optimistic concurrency on review, task retry (ordinal 2), and run cancellation."""
    service = RunService(repo_root=temp_git_repo)
    base_sha = service.git_workspace.resolve_commit_sha("HEAD")

    task_spec = TaskSpec(
        task_id="task_retryable",
        run_id="run_retry_01",
        objective="Implement add(a, b) with retry after rejection",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_add_retry",
                command=(sys.executable, "-c", "from src.calculator import add; assert add(2, 3) == 5"),
            ),
        ),
        allowed_paths=("src/calculator.py",),
    )
    run_spec = RunSpec(
        run_id="run_retry_01",
        project_id="proj_calc",
        objective="Retry and review concurrency flow",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="relay",
        budget_policy=BudgetPolicy(max_attempts=3),
        idempotency_key="idem_test_retry_and_cancel_flow_01",
        tasks=(task_spec,),
    )
    await service.submit_run(run_spec)

    # Attempt 1 passes check, reaches READY_FOR_REVIEW
    out1 = await service.execute_task_attempt(
        "run_retry_01",
        "task_retryable",
        custom_command=(
            sys.executable,
            "-c",
            (
                "import pathlib; pathlib.Path('src/calculator.py').write_text("
                "'def add(a: int, b: int) -> int:\\n    return a + b  # v1\\n')"
            ),
        ),
    )
    assert out1.attempt.ordinal == 1
    assert out1.result.task_status == TaskStatus.READY_FOR_REVIEW

    # Stale expected_revision raises OptimisticLockError
    with pytest.raises(OptimisticLockError):
        await service.review_task_result(
            "run_retry_01",
            out1.result.result_id,
            actor="lead-reviewer",
            decision="accepted",
            reason="Wrong revision",
            expected_revision=99,
        )

    # Reviewer rejects attempt 1
    rejected = await service.review_task_result(
        "run_retry_01",
        out1.result.result_id,
        actor="lead-reviewer",
        decision="rejected",
        reason="Please add docstring in v2",
        expected_revision=1,
    )
    assert rejected.task_status == TaskStatus.REJECTED
    assert rejected.revision == 2

    # Retry creates Attempt 2 (ordinal=2) in a new worktree while preserving Attempt 1
    out2 = await service.retry_task(
        "run_retry_01",
        "task_retryable",
        custom_command=(
            sys.executable,
            "-c",
            (
                "import pathlib; pathlib.Path('src/calculator.py').write_text("
                "'def add(a: int, b: int) -> int:\\n    \"\"\"Add two integers.\"\"\"\\n    return a + b\\n')"
            ),
        ),
    )
    assert out2.attempt.ordinal == 2
    assert out2.attempt.attempt_id != out1.attempt.attempt_id
    assert out2.result.task_status == TaskStatus.READY_FOR_REVIEW

    accepted = await service.review_task_result(
        "run_retry_01",
        out2.result.result_id,
        actor="lead-reviewer",
        decision="accepted",
        reason="v2 with docstring looks good",
        expected_revision=1,
    )
    assert accepted.task_status == TaskStatus.ACCEPTED

    int_outcome = await service.integrate_run("run_retry_01")
    assert int_outcome.status == IntegrationStatus.INTEGRATED

    # Also test cancel_run on a second queued run
    cancel_task = TaskSpec(
        task_id="task_to_cancel",
        run_id="run_cancel_01",
        objective="Task to be cancelled",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(check_id="chk_c", command=(sys.executable, "-c", "print('ok')")),
        ),
        allowed_paths=("src/**",),
    )
    cancel_spec = RunSpec(
        run_id="run_cancel_01",
        project_id="proj_calc",
        objective="Run cancellation test",
        repo_root=str(temp_git_repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="relay",
        idempotency_key="idem_test_cancel_run_flow_00001",
        tasks=(cancel_task,),
    )
    await service.submit_run(cancel_spec)
    cancelled_run = await service.cancel_run("run_cancel_01", reason="operator_aborted")
    assert cancelled_run["status"] == RunStatus.CANCELLED.value
    cancelled_task_rec = await service.store.get_task("task_to_cancel")
    assert cancelled_task_rec is not None
    assert cancelled_task_rec["status"] == TaskStatus.CANCELLED.value
