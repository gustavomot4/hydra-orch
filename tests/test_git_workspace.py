"""Hermetic tests for GitWorkspaceService (S05 / T05)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.git_workspace import (
    GitWorkspaceError,
    GitWorkspaceService,
)
from hydra_orch.model import (
    Artifact,
    BudgetPolicy,
    CheckResult,
    CheckSpec,
    IntegrationStatus,
    ProcessStatus,
    ReviewDecision,
    RunSpec,
    TaskAttempt,
    TaskResult,
    TaskSpec,
    TaskStatus,
    review_result,
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
    repo = tmp_path / "sample_repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test Operator")
    _git(repo, "config", "user.email", "operator@example.com")
    (repo / "README.md").write_text("# Sample Repo\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore: initial commit")
    return repo


def _make_accepted_result(
    svc: GitWorkspaceService,
    run_id: str,
    task_id: str,
    attempt_id: str,
    result_id: str,
    base_sha: str,
    file_rel_path: str,
    content: str,
) -> tuple[TaskSpec, TaskAttempt, TaskResult]:
    record = svc.create_worktree(
        run_id=run_id,
        task_id=task_id,
        attempt_id=attempt_id,
        base_sha=base_sha,
    )
    target_file = record.canonical_path / file_rel_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")

    diff_art = svc.capture_and_commit_patch(
        record,
        commit_message=f"feat({task_id}): update {file_rel_path}",
        allowed_paths=(file_rel_path,),
    )
    assert diff_art.has_changes is True
    assert diff_art.patch_commit_sha is not None
    assert diff_art.artifact is not None

    task_spec = TaskSpec(
        task_id=task_id,
        run_id=run_id,
        objective=f"Update {file_rel_path} safely",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_unit",
                command=("python", "-c", "print('ok')"),
            ),
        ),
        allowed_paths=(file_rel_path,),
    )
    now_utc = datetime.now(timezone.utc)
    attempt = TaskAttempt(
        attempt_id=attempt_id,
        task_id=task_id,
        run_id=run_id,
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=base_sha,
        workspace_path=str(record.canonical_path),
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now_utc,
        finished_at=now_utc,
        exit_reason="completed",
    )
    stdout_art = Artifact(
        artifact_id=f"art_stdout_{attempt_id}",
        run_id=run_id,
        attempt_id=attempt_id,
        relative_path=f".orchestrator/run/{run_id}/logs/{attempt_id}.stdout.log",
        kind="check_output",
        sha256=hashlib.sha256(b"ok\n").hexdigest(),
        size_bytes=3,
    )
    stderr_art = Artifact(
        artifact_id=f"art_stderr_{attempt_id}",
        run_id=run_id,
        attempt_id=attempt_id,
        relative_path=f".orchestrator/run/{run_id}/logs/{attempt_id}.stderr.log",
        kind="check_output",
        sha256=hashlib.sha256(b"").hexdigest(),
        size_bytes=0,
    )
    ready_result = TaskResult(
        result_id=result_id,
        attempt_id=attempt_id,
         run_id=run_id,
        base_sha=base_sha,
        process_status=ProcessStatus.EXITED,
        task_status=TaskStatus.READY_FOR_REVIEW,
        exit_code=0,
        simulated=False,
        patch_commit_sha=diff_art.patch_commit_sha,
        patch_artifact_id=diff_art.artifact.artifact_id,
        changed_files=(file_rel_path,),
        checks_executed=(
            CheckResult(
                check_id="chk_unit",
                command=("python", "-c", "print('ok')"),
                tested_sha=diff_art.patch_commit_sha,
                exit_code=0,
                duration_seconds=0.05,
                stdout_artifact_id=stdout_art.artifact_id,
                stderr_artifact_id=stderr_art.artifact_id,
            ),
        ),
        artifacts=(diff_art.artifact, stdout_art, stderr_art),
        summary=f"Updated {file_rel_path}",
    )
    accepted_result = review_result(
        task_spec,
        attempt,
        ready_result,
        ReviewDecision(
            result_id=result_id,
            actor="lead-operator",
            decision="accepted",
            reason="Verified diff and checks",
            expected_revision=1,
        ),
    )
    return task_spec, attempt, accepted_result


def test_create_real_worktree_pinned_base_sha_and_no_fallback_dir(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """Verify real Git worktree creation anchored to fixed base_sha and no fallback directory on failure (GAP A06)."""
    non_git_dir = tmp_path / "plain_folder"
    non_git_dir.mkdir()
    with pytest.raises(GitWorkspaceError) as exc_non_git:
        GitWorkspaceService(repo_root=non_git_dir)
    assert exc_non_git.value.failure.code == "workspace_invalid"

    # Subdirectory of a git repo must also be rejected as non-canonical root
    with pytest.raises(GitWorkspaceError) as exc_subdir:
        GitWorkspaceService(repo_root=temp_git_repo / "src")
    assert exc_subdir.value.failure.code == "workspace_invalid"

    svc = GitWorkspaceService(repo_root=temp_git_repo)
    pinned_base_sha = svc.resolve_commit_sha("HEAD")

    # Advance operator main branch AFTER capturing pinned_base_sha
    (temp_git_repo / "README.md").write_text("# Updated on main\n", encoding="utf-8")
    _git(temp_git_repo, "add", "README.md")
    _git(temp_git_repo, "commit", "-m", "docs: advance main beyond base_sha")
    new_main_sha = svc.resolve_commit_sha("HEAD")
    assert new_main_sha != pinned_base_sha

    record = svc.create_worktree(
        run_id="run_t05",
        task_id="task_pin",
        attempt_id="att_1",
        base_sha=pinned_base_sha,
    )
    assert record.canonical_path.is_dir()
    assert (record.canonical_path / ".git").exists()
    assert svc.resolve_commit_sha("HEAD", cwd=record.canonical_path) == pinned_base_sha
    assert (record.canonical_path / "README.md").read_text(encoding="utf-8") == "# Sample Repo\n"

    # Invalid base_sha or duplicate branch must fail and NEVER leave a plain directory behind (GAP A06)
    failed_wt_path = svc.worktree_base_dir / "run_t05_task_bad_att_bad"
    with pytest.raises(GitWorkspaceError) as exc_bad_sha:
        svc.create_worktree(
            run_id="run_t05",
            task_id="task_bad",
            attempt_id="att_bad",
            base_sha="deadbeef" * 5,
        )
    assert exc_bad_sha.value.failure.code == "workspace_invalid"
    assert not failed_wt_path.exists()

    # Reusing an existing branch name for another worktree fails git worktree add and cleans up
    dup_branch_wt = svc.worktree_base_dir / "run_t05_task_dup_att_2"
    with pytest.raises(GitWorkspaceError) as exc_dup_branch:
        svc.create_worktree(
            run_id="run_t05",
            task_id="task_dup",
            attempt_id="att_2",
            base_sha=pinned_base_sha,
            branch_name=record.branch,
        )
    assert exc_dup_branch.value.failure.code == "workspace_invalid"
    assert not dup_branch_wt.exists()


def test_operator_checkout_intact_staged_unstaged_untracked(temp_git_repo: Path) -> None:
    """Verify operator branch, HEAD, staged, unstaged, and untracked files remain intact (RT05 / GAP A05)."""
    svc = GitWorkspaceService(repo_root=temp_git_repo)
    base_sha = svc.resolve_commit_sha("HEAD")

    # Operator creates staged, unstaged, and untracked changes in their main checkout
    (temp_git_repo / "staged_note.txt").write_text("staged content\n", encoding="utf-8")
    _git(temp_git_repo, "add", "staged_note.txt")
    (temp_git_repo / "README.md").write_text("# Unstaged operator edit\n", encoding="utf-8")
    (temp_git_repo / "untracked_scratch.txt").write_text("operator scratch\n", encoding="utf-8")

    snap_before = svc.snapshot_operator_checkout()
    assert snap_before.branch == "main"
    assert snap_before.staged_files == ("staged_note.txt",)
    assert snap_before.unstaged_files == ("README.md",)
    assert snap_before.untracked_files == ("untracked_scratch.txt",)

    record = svc.create_worktree(
        run_id="run_op",
        task_id="task_iso",
        attempt_id="att_iso",
        base_sha=base_sha,
    )
    (record.canonical_path / "src" / "app.py").write_text("VALUE = 42\n", encoding="utf-8")
    diff_art = svc.capture_and_commit_patch(
        record,
        commit_message="feat: set VALUE to 42",
        allowed_paths=("src/**",),
    )
    assert diff_art.has_changes is True
    assert diff_art.patch_commit_sha != base_sha

    svc.cleanup_worktree(record, force_discard=False)
    snap_after = svc.assert_operator_checkout_intact(snap_before)
    assert snap_after == snap_before
    assert (temp_git_repo / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_scope_validation_and_forbidden_paths_and_symlink_escape(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """Verify allowed_paths, forbidden_paths, and external symlink detection in validate_worktree_scope."""
    svc = GitWorkspaceService(repo_root=temp_git_repo)
    base_sha = svc.resolve_commit_sha("HEAD")
    record = svc.create_worktree(
        run_id="run_scope",
        task_id="task_scope",
        attempt_id="att_scope",
        base_sha=base_sha,
    )

    # 1. Allowed modification passes
    (record.canonical_path / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    res_ok = svc.validate_worktree_scope(
        record.canonical_path,
        base_sha=base_sha,
        allowed_paths=("src/**",),
        forbidden_paths=("pyproject.toml",),
    )
    assert res_ok.valid is True
    assert res_ok.changed_files == ("src/app.py",)

    # 2. Out-of-scope file fails
    (record.canonical_path / "README.md").write_text("# Forbidden edit\n", encoding="utf-8")
    res_out = svc.validate_worktree_scope(
        record.canonical_path,
        base_sha=base_sha,
        allowed_paths=("src/**",),
    )
    assert res_out.valid is False
    assert "README.md" in res_out.violations

    with pytest.raises(GitWorkspaceError) as exc_scope:
        svc.capture_and_commit_patch(
            record,
            commit_message="should fail scope",
            allowed_paths=("src/**",),
        )
    assert exc_scope.value.failure.code == "scope_violation"
    assert record.status == "preserved"

    # Restore README.md, test forbidden_paths hit (e.g. Wave 1 dependency manifest lock)
    _git(record.canonical_path, "checkout", "--", "README.md")
    (record.canonical_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    res_forbid = svc.validate_worktree_scope(
        record.canonical_path,
        base_sha=base_sha,
        allowed_paths=("**/*",),
        forbidden_paths=("pyproject.toml", "package.json"),
    )
    assert res_forbid.valid is False
    assert "pyproject.toml" in res_forbid.forbidden_hits

    (record.canonical_path / "pyproject.toml").unlink()

    # 3. Symlink escaping worktree_path is detected if OS privileges allow symlink creation
    outside_secret = tmp_path / "outside_secret.txt"
    outside_secret.write_text("top-secret", encoding="utf-8")
    symlink_path = record.canonical_path / "src" / "escape_link.txt"
    try:
        os.symlink(outside_secret, symlink_path)
    except (OSError, NotImplementedError):
        pass
    else:
        res_sym = svc.validate_worktree_scope(
            record.canonical_path,
            base_sha=base_sha,
            allowed_paths=("src/**",),
        )
        assert res_sym.valid is False
        assert "src/escape_link.txt" in res_sym.symlink_escapes


def test_cleanup_worktree_preserves_dirty_and_cleans_stale_locks(temp_git_repo: Path) -> None:
    """Verify dirty worktrees are preserved unless force_discard=True and stale locks are cleaned up (GAP A05)."""
    svc = GitWorkspaceService(repo_root=temp_git_repo)
    base_sha = svc.resolve_commit_sha("HEAD")
    record = svc.create_worktree(
        run_id="run_clean",
        task_id="task_dirty",
        attempt_id="att_dirty",
        base_sha=base_sha,
    )
    (record.canonical_path / "src" / "uncommitted.py").write_text("x = 99\n", encoding="utf-8")

    with pytest.raises(GitWorkspaceError) as exc_dirty:
        svc.cleanup_worktree(record, force_discard=False)
    assert exc_dirty.value.failure.code == "dirty_worktree_preserved"
    assert record.status == "preserved"
    assert record.canonical_path.exists()

    # Explicit force_discard=True removes the dirty worktree when authorized
    svc.cleanup_worktree(record, force_discard=True, delete_branch=True)
    assert record.status == "cleaned"
    assert not record.canonical_path.exists()

    # Create a stale lock with a dead PID and an active lock with current PID
    stale_lock = svc.create_lock_file("stale_integration", pid=99999999)
    live_lock = svc.create_lock_file("live_integration", pid=os.getpid())
    removed = svc.cleanup_stale_locks()
    assert stale_lock in removed
    assert not stale_lock.exists()
    assert live_lock.exists()
    live_lock.unlink()


@pytest.mark.asyncio
async def test_merge_serialized(temp_git_repo: Path, tmp_path: Path) -> None:
    """Verify serialized integration of accepted TaskResults into dedicated branch without touching operator checkout."""
    db_path = tmp_path / "checkpoints.sqlite"
    store = ExecutionStore(db_path=db_path)
    await store.initialize()

    svc = GitWorkspaceService(repo_root=temp_git_repo, store=store)
    base_sha = svc.resolve_commit_sha("HEAD")
    snap_before = svc.snapshot_operator_checkout()

    t1_spec, t1_att, t1_res = _make_accepted_result(
        svc,
        run_id="run_merge_01",
        task_id="task_mod_a",
        attempt_id="att_m1",
        result_id="res_m1",
        base_sha=base_sha,
        file_rel_path="src/mod_a.py",
        content="A = 'alpha'\n",
    )
    t2_spec, t2_att, t2_res = _make_accepted_result(
        svc,
        run_id="run_merge_01",
        task_id="task_mod_b",
        attempt_id="att_m2",
        result_id="res_m2",
        base_sha=base_sha,
        file_rel_path="src/mod_b.py",
        content="B = 'beta'\n",
    )

    run_spec = RunSpec(
        run_id="run_merge_01",
        project_id="proj_git",
        objective="Test serialized merge of two tasks",
        repo_root=str(temp_git_repo),
        base_branch="main",
        base_sha=base_sha,
        orchestration_mode="swarm",
        idempotency_key="idem_git_merge_serialized_0001",
        budget_policy=BudgetPolicy(max_wall_seconds=300),
        tasks=(t1_spec, t2_spec),
    )
    await store.save_run_atomic(run_spec)
    await store.save_attempt_atomic(t1_att)
    await store.save_attempt_atomic(t2_att)
    await svc.save_workspace_record(svc._workspaces["att_m1"])
    await svc.save_workspace_record(svc._workspaces["att_m2"])

    post_check = CheckSpec(
        check_id="chk_combined",
        command=("python", "-c", "import pathlib; assert pathlib.Path('src/mod_a.py').exists()"),
    )

    def _run_combined_checks(
        wt_path: Path, tested_sha: str, checks: tuple[CheckSpec, ...]
    ) -> tuple[CheckResult, ...]:
        results = []
        for chk in checks:
            proc = subprocess.run(chk.command, cwd=str(wt_path), capture_output=True, text=True)
            results.append(
                CheckResult(
                    check_id=chk.check_id,
                    command=chk.command,
                    tested_sha=tested_sha,
                    exit_code=proc.returncode,
                    duration_seconds=0.05,
                    stdout_artifact_id="art_chk_stdout",
                    stderr_artifact_id="art_chk_stderr",
                )
            )
        return tuple(results)

    # Dispatch two concurrent integrate_results calls to prove serialization via repo lock
    outcome_a, outcome_b = await asyncio.gather(
        svc.integrate_results(
            run_id="run_merge_01",
            expected_base_sha=base_sha,
            results=(t1_res, t2_res),
            integration_id="int_run_merge_01_a",
            post_merge_checks=(post_check,),
            check_runner=_run_combined_checks,
        ),
        svc.integrate_results(
            run_id="run_merge_01",
            expected_base_sha=base_sha,
            results=(t1_res, t2_res),
            integration_id="int_run_merge_01_b",
            post_merge_checks=(post_check,),
            check_runner=_run_combined_checks,
        ),
    )

    for outcome in (outcome_a, outcome_b):
        assert outcome.status == IntegrationStatus.INTEGRATED
        assert outcome.result_sha is not None
        assert outcome.result_sha != base_sha
        assert outcome.merged_result_ids == ("res_m1", "res_m2")
        assert len(outcome.checks_executed) == 1
        assert outcome.checks_executed[0].exit_code == 0
        assert (outcome.integration_worktree_path / "src" / "mod_a.py").exists()
        assert (outcome.integration_worktree_path / "src" / "mod_b.py").exists()

    # Operator checkout must still be on main at base_sha without src/mod_a.py or src/mod_b.py
    svc.assert_operator_checkout_intact(snap_before)
    assert not (temp_git_repo / "src" / "mod_a.py").exists()
    assert not (temp_git_repo / "src" / "mod_b.py").exists()

    events = await store.get_events("run_merge_01", after_seq=0)
    assert any(ev.event_type == "merge.completed" for ev in events)


@pytest.mark.asyncio
async def test_conflict_preserves_worktree(temp_git_repo: Path, tmp_path: Path) -> None:
    """Verify merge conflict marks status CONFLICTED, preserves worktrees, and leaves operator checkout intact."""
    db_path = tmp_path / "checkpoints_conflict.sqlite"
    store = ExecutionStore(db_path=db_path)
    await store.initialize()

    svc = GitWorkspaceService(repo_root=temp_git_repo, store=store)
    base_sha = svc.resolve_commit_sha("HEAD")
    snap_before = svc.snapshot_operator_checkout()

    t1_spec, t1_att, t1_res = _make_accepted_result(
        svc,
        run_id="run_conflict_01",
        task_id="task_c1",
        attempt_id="att_c1",
        result_id="res_c1",
        base_sha=base_sha,
        file_rel_path="src/app.py",
        content="VALUE = 100\nMODE = 'first'\n",
    )
    t2_spec, t2_att, t2_res = _make_accepted_result(
        svc,
        run_id="run_conflict_01",
        task_id="task_c2",
        attempt_id="att_c2",
        result_id="res_c2",
        base_sha=base_sha,
        file_rel_path="src/app.py",
        content="VALUE = 200\nMODE = 'second'\n",
    )

    run_spec = RunSpec(
        run_id="run_conflict_01",
        project_id="proj_git",
        objective="Test conflict preservation on shared file",
        repo_root=str(temp_git_repo),
        base_branch="main",
        base_sha=base_sha,
        orchestration_mode="swarm",
        idempotency_key="idem_git_conflict_preserve_01",
        budget_policy=BudgetPolicy(max_wall_seconds=300),
        tasks=(t1_spec, t2_spec),
    )
    await store.save_run_atomic(run_spec)
    await store.save_attempt_atomic(t1_att)
    await store.save_attempt_atomic(t2_att)

    outcome = await svc.integrate_results(
        run_id="run_conflict_01",
        expected_base_sha=base_sha,
        results=(t1_res, t2_res),
    )
    assert outcome.status == IntegrationStatus.CONFLICTED
    assert outcome.result_sha is None
    assert outcome.merged_result_ids == ("res_c1",)
    assert "src/app.py" in outcome.conflicted_files
    assert outcome.failure is not None
    assert outcome.failure.code == "merge_conflict"

    # Both task worktrees and the integration worktree must remain preserved on disk
    assert svc._workspaces["att_c1"].canonical_path.exists()
    assert svc._workspaces["att_c2"].canonical_path.exists()
    assert svc._workspaces["att_c2"].status == "conflicted"
    assert outcome.integration_worktree_path.exists()

    # Operator checkout remains completely untouched
    svc.assert_operator_checkout_intact(snap_before)
    assert (temp_git_repo / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    events = await store.get_events("run_conflict_01", after_seq=0)
    assert any(ev.event_type == "merge.conflicted" for ev in events)
