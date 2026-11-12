from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hydra_orch.core.checkpointer import (
    ExecutionStore,
    IdempotencyConflictError,
    OptimisticLockError,
)
from hydra_orch.core.conflict_resolver import ConflictResolver, RESOLUTION_OPTIONS
from hydra_orch.core.git_workspace import GitWorkspaceService
from hydra_orch.core.identifier import new_id
from hydra_orch.model import (
    Artifact,
    CheckResult,
    CheckSpec,
    ContractViolation,
    InvalidTransitionError,
    ProcessStatus,
    ReviewDecision,
    RunSpec,
    RunStatus,
    TaskAttempt,
    TaskResult,
    TaskSpec,
    TaskStatus,
)


def _noop_criteria(check_id: str = "chk-default") -> tuple[CheckSpec, ...]:
    return (CheckSpec(check_id=check_id, command=(sys.executable, "-c", "print('ok')")),)


def _make_check_and_artifacts(
    *,
    run_id: str,
    attempt_id: str,
    check_id: str,
    tested_sha: str,
) -> tuple[str, tuple[CheckResult, ...], tuple[Artifact, ...]]:
    patch_id = f"art-patch-{new_id()}"
    out_id = f"art-out-{new_id()}"
    err_id = f"art-err-{new_id()}"
    sha_zero = "0" * 64
    artifacts = (
        Artifact(
            artifact_id=patch_id,
            run_id=run_id,
            attempt_id=attempt_id,
            relative_path=f".orchestrator/patches/{attempt_id}.diff",
            kind="patch",
            sha256=sha_zero,
            size_bytes=0,
        ),
        Artifact(
            artifact_id=out_id,
            run_id=run_id,
            attempt_id=attempt_id,
            relative_path=f".orchestrator/logs/{check_id}.stdout.log",
            kind="check_output",
            sha256=sha_zero,
            size_bytes=0,
        ),
        Artifact(
            artifact_id=err_id,
            run_id=run_id,
            attempt_id=attempt_id,
            relative_path=f".orchestrator/logs/{check_id}.stderr.log",
            kind="check_output",
            sha256=sha_zero,
            size_bytes=0,
        ),
    )
    check = CheckResult(
        check_id=check_id,
        command=(sys.executable, "-c", "print('ok')"),
        cwd=".",
        tested_sha=tested_sha,
        exit_code=0,
        duration_seconds=0.01,
        stdout_artifact_id=out_id,
        stderr_artifact_id=err_id,
    )
    return patch_id, (check,), artifacts


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


def _init_temp_repo(tmp_path: Path) -> tuple[Path, str]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.name", "Test Operator")
    _git(repo_root, "config", "user.email", "operator@example.com")

    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "contracts").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "shared.py").write_text(
        "def compute(x: int) -> int:\n"
        "    value = x + 1\n"
        "    return value\n",
        encoding="utf-8",
    )
    (repo_root / "contracts" / "api.py").write_text(
        "API_VERSION = 1\n"
        "PAYLOAD_FIELDS = ('id', 'name')\n",
        encoding="utf-8",
    )
    (repo_root / ".gitignore").write_text(".orchestrator/\n", encoding="utf-8")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "initial base")
    base_sha = _git(repo_root, "rev-parse", "HEAD")
    return repo_root, base_sha


def _operator_snapshot(repo_root: Path) -> tuple[str, str, str, str]:
    return (
        _git(repo_root, "rev-parse", "HEAD"),
        _git(repo_root, "branch", "--show-current"),
        _git(repo_root, "status", "--porcelain"),
        (repo_root / "src" / "shared.py").read_text(encoding="utf-8"),
    )


async def _setup_conflicting_integration(
    tmp_path: Path,
    *,
    task_a_content: str = (
        "def compute(x: int) -> int:\n"
        "    value = x * 2\n"
        "    return value\n"
    ),
    task_b_content: str = (
        "def compute(x: int) -> int:\n"
        "    value = x + 100\n"
        "    return value\n"
    ),
) -> dict[str, object]:
    repo_root, base_sha = _init_temp_repo(tmp_path)
    store = ExecutionStore(tmp_path / "hydra.db")
    await store.initialize()
    git_ws = GitWorkspaceService(repo_root, store=store)

    run_id = f"run-{new_id()}"
    task_a_id = f"task-a-{new_id()}"
    task_b_id = f"task-b-{new_id()}"

    task_a = TaskSpec(
        task_id=task_a_id,
        run_id=run_id,
        objective="Implement feature A in src/shared.py",
        assigned_executor="codex",
        acceptance_criteria=_noop_criteria("chk-task-a"),
        allowed_paths=("src/shared.py",),
        dependencies=(),
    )
    task_b = TaskSpec(
        task_id=task_b_id,
        run_id=run_id,
        objective="Implement feature B in src/shared.py",
        assigned_executor="claude",
        acceptance_criteria=_noop_criteria("chk-task-b"),
        allowed_paths=("src/shared.py",),
        dependencies=(),
    )
    run_spec = RunSpec(
        run_id=run_id,
        project_id="proj-conflict",
        objective="Test 3-way merge conflict resolution",
        repo_root=str(repo_root),
        base_sha=base_sha,
        base_branch="main",
        idempotency_key=f"idem-{run_id}",
        tasks=(task_a, task_b),
    )
    await store.save_run_atomic(run_spec, initial_status=RunStatus.RUNNING)

    att_a_id = f"att-a-{new_id()}"
    att_b_id = f"att-b-{new_id()}"

    ws_a = git_ws.create_worktree(run_id, task_a_id, att_a_id, base_sha)
    (ws_a.canonical_path / "src" / "shared.py").write_text(task_a_content, encoding="utf-8")
    _git(ws_a.canonical_path, "add", "src/shared.py")
    _git(ws_a.canonical_path, "commit", "-m", "task A change")
    sha_a = _git(ws_a.canonical_path, "rev-parse", "HEAD")

    ws_b = git_ws.create_worktree(run_id, task_b_id, att_b_id, base_sha)
    (ws_b.canonical_path / "src" / "shared.py").write_text(task_b_content, encoding="utf-8")
    _git(ws_b.canonical_path, "add", "src/shared.py")
    _git(ws_b.canonical_path, "commit", "-m", "task B change")
    sha_b = _git(ws_b.canonical_path, "rev-parse", "HEAD")

    now = datetime.now(timezone.utc)
    att_a = TaskAttempt(
        attempt_id=att_a_id,
        task_id=task_a_id,
        run_id=run_id,
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=base_sha,
        workspace_path=str(ws_a.canonical_path),
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now,
        finished_at=now,
        exit_reason="completed",
    )
    att_b = TaskAttempt(
        attempt_id=att_b_id,
        task_id=task_b_id,
        run_id=run_id,
        ordinal=1,
        executor_id="claude",
        provider="anthropic",
        model="claude-sonnet",
        base_sha=base_sha,
        workspace_path=str(ws_b.canonical_path),
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now,
        finished_at=now,
        exit_reason="completed",
    )
    await store.save_attempt_atomic(att_a)
    await store.save_attempt_atomic(att_b)
    await store.update_task_status_atomic(task_a_id, TaskStatus.RUNNING, 1, "task.started")
    await store.update_task_status_atomic(task_b_id, TaskStatus.RUNNING, 1, "task.started")

    patch_a_id, checks_a, arts_a = _make_check_and_artifacts(
        run_id=run_id,
        attempt_id=att_a_id,
        check_id="chk-task-a",
        tested_sha=sha_a,
    )
    patch_b_id, checks_b, arts_b = _make_check_and_artifacts(
        run_id=run_id,
        attempt_id=att_b_id,
        check_id="chk-task-b",
        tested_sha=sha_b,
    )
    res_a = TaskResult(
        result_id=f"res-a-{new_id()}",
        attempt_id=att_a_id,
        run_id=run_id,
        base_sha=base_sha,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        task_status=TaskStatus.READY_FOR_REVIEW,
        summary="Task A completed",
        simulated=False,
        patch_commit_sha=sha_a,
        patch_artifact_id=patch_a_id,
        changed_files=("src/shared.py",),
        checks_executed=checks_a,
        artifacts=arts_a,
    )
    res_b = TaskResult(
        result_id=f"res-b-{new_id()}",
        attempt_id=att_b_id,
        run_id=run_id,
        base_sha=base_sha,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        task_status=TaskStatus.READY_FOR_REVIEW,
        summary="Task B completed",
        simulated=False,
        patch_commit_sha=sha_b,
        patch_artifact_id=patch_b_id,
        changed_files=("src/shared.py",),
        checks_executed=checks_b,
        artifacts=arts_b,
    )
    await store.save_task_result_atomic(task_a, att_a, res_a)
    await store.save_task_result_atomic(task_b, att_b, res_b)
    res_a = await store.record_review_atomic(
        task_a,
        att_a,
        ReviewDecision(
            result_id=res_a.result_id,
            actor="reviewer",
            decision=TaskStatus.ACCEPTED.value,
            reason="Verified feature A",
            expected_revision=1,
        ),
    )
    res_b = await store.record_review_atomic(
        task_b,
        att_b,
        ReviewDecision(
            result_id=res_b.result_id,
            actor="reviewer",
            decision=TaskStatus.ACCEPTED.value,
            reason="Verified feature B",
            expected_revision=1,
        ),
    )

    outcome = await git_ws.integrate_results(
        run_id=run_id,
        expected_base_sha=base_sha,
        results=(res_a, res_b),
    )
    assert outcome.status == "conflicted"

    resolver = ConflictResolver(store, git_ws, repo_root=repo_root)
    return {
        "repo_root": repo_root,
        "base_sha": base_sha,
        "sha_a": sha_a,
        "sha_b": sha_b,
        "store": store,
        "git_ws": git_ws,
        "resolver": resolver,
        "run_id": run_id,
        "task_a_id": task_a_id,
        "task_b_id": task_b_id,
        "outcome": outcome,
    }


@pytest.mark.asyncio
async def test_3way_report(tmp_path: Path) -> None:
    ctx = await _setup_conflicting_integration(tmp_path)
    repo_root: Path = ctx["repo_root"]  # type: ignore[assignment]
    store: ExecutionStore = ctx["store"]  # type: ignore[assignment]
    resolver: ConflictResolver = ctx["resolver"]  # type: ignore[assignment]
    outcome = ctx["outcome"]
    before = _operator_snapshot(repo_root)

    report = await resolver.analyze(
        outcome.integration_id,
        idempotency_key="analyze-1",
    )

    assert report.integration_id == outcome.integration_id
    assert report.run_id == ctx["run_id"]
    assert report.base_sha == ctx["base_sha"]
    assert report.ours_sha == outcome.ours_sha
    assert report.theirs_sha == outcome.theirs_sha
    assert report.theirs_sha == ctx["sha_b"]
    assert _git(repo_root, "show", f"{report.ours_sha}:src/shared.py") == _git(
        repo_root, "show", f"{ctx['sha_a']}:src/shared.py"
    )
    assert report.conflicted_files == ("src/shared.py",)
    assert report.resolution_options == RESOLUTION_OPTIONS
    assert report.status == "open"
    assert report.resolved_at is None
    assert len(report.file_details) == 1

    detail = report.file_details[0]
    assert detail.path == "src/shared.py"
    assert "value = x + 1" in (detail.base_content or "")
    assert "value = x * 2" in (detail.ours_content or "")
    assert "value = x + 100" in (detail.theirs_content or "")
    assert "<<<<<<<" in detail.merged_preview
    assert ">>>>>>>" in detail.merged_preview
    assert len(detail.hunks) >= 1
    assert any("=======" in hunk for hunk in detail.hunks)

    # Idempotent replay returns identical report
    replay = await resolver.analyze(outcome.integration_id, idempotency_key="analyze-1")
    assert replay.conflict_id == report.conflict_id

    # Verify SQLite persistence in conflict_reports, events, and commands
    async with store._connect() as db:
        row = await (
            await db.execute("SELECT * FROM conflict_reports WHERE id = ?", (report.conflict_id,))
        ).fetchone()
        assert row is not None
        assert row["status"] == "open"
        assert row["resolved_at"] is None
        assert row["base_sha"] == ctx["base_sha"]
        assert row["ours_sha"] == outcome.ours_sha
        assert row["theirs_sha"] == outcome.theirs_sha
        assert json.loads(row["conflicted_files_json"]) == ["src/shared.py"]
        assert tuple(json.loads(row["resolution_options_json"])) == RESOLUTION_OPTIONS

        cmd_row = await (
            await db.execute(
                "SELECT scope, status FROM commands WHERE scope = 'conflict_resolver' AND idempotency_key = ?",
                ("analyze-1",),
            )
        ).fetchone()
        assert cmd_row is not None
        assert cmd_row["status"] == "completed"

    events = await store.get_events(str(ctx["run_id"]))
    assert any(ev.event_type == "merge.conflict_analyzed" for ev in events)

    listed = await resolver.list_reports(integration_id=outcome.integration_id)
    assert [r.conflict_id for r in listed] == [report.conflict_id]
    fetched = await resolver.get_report(report.conflict_id)
    assert fetched.conflict_id == report.conflict_id
    assert _operator_snapshot(repo_root) == before


@pytest.mark.asyncio
async def test_auto_repair_merge_repair(tmp_path: Path) -> None:
    # Part 1: Successful isolated merge_repair + mandatory checks
    ctx = await _setup_conflicting_integration(tmp_path / "ok")
    repo_root: Path = ctx["repo_root"]  # type: ignore[assignment]
    store: ExecutionStore = ctx["store"]  # type: ignore[assignment]
    resolver: ConflictResolver = ctx["resolver"]  # type: ignore[assignment]
    outcome = ctx["outcome"]
    before = _operator_snapshot(repo_root)

    report = await resolver.analyze(outcome.integration_id)
    observed_worktrees: list[Path] = []

    def _valid_repairer(wt_path: Path, rep, attempt_num: int) -> None:
        observed_worktrees.append(wt_path)
        assert attempt_num == 1
        assert rep.conflict_id == report.conflict_id
        # Isolated worktree has actual conflict markers before repair
        raw = (wt_path / "src" / "shared.py").read_text(encoding="utf-8")
        assert "<<<<<<<" in raw
        (wt_path / "src" / "shared.py").write_text(
            "def compute(x: int) -> int:\n"
            "    value = (x * 2) + 100\n"
            "    return value\n",
            encoding="utf-8",
        )

    pass_check = CheckSpec(
        check_id="verify-compute",
        command=(
            sys.executable,
            "-c",
            "import pathlib; ns = {}; exec(pathlib.Path('src/shared.py').read_text(), ns); assert ns['compute'](5) == 110",
        ),
    )

    repaired = await resolver.auto_repair(
        report.conflict_id,
        repairer=_valid_repairer,
        checks=(pass_check,),
        allowed_paths=("src/shared.py",),
        idempotency_key="repair-ok-1",
    )

    assert repaired.repaired is True
    assert repaired.status == "auto_repair"
    assert repaired.attempt_number == 1
    assert repaired.resolved_sha is not None
    assert repaired.resolved_at is not None
    assert repaired.repair_worktree_path is not None
    assert Path(repaired.repair_worktree_path).resolve() == observed_worktrees[0].resolve()
    assert Path(repaired.repair_worktree_path).resolve() != repo_root.resolve()
    assert (repaired.repair_branch or "").startswith("merge_repair/")
    assert len(repaired.checks_executed) == 1
    assert repaired.checks_executed[0].exit_code == 0
    assert _operator_snapshot(repo_root) == before

    # Resolved commit tree contains the merged code
    resolved_src = _git(repo_root, "show", f"{repaired.resolved_sha}:src/shared.py")
    assert "value = (x * 2) + 100" in resolved_src

    async with store._connect() as db:
        row = await (
            await db.execute("SELECT status, resolved_at FROM conflict_reports WHERE id = ?", (report.conflict_id,))
        ).fetchone()
        assert row is not None
        assert row["status"] == "auto_repair"
        assert row["resolved_at"] is not None

        int_row = await (
            await db.execute("SELECT status, result_sha FROM integrations WHERE id = ?", (outcome.integration_id,))
        ).fetchone()
        assert int_row is not None
        assert int_row["status"] == "integrated"
        assert int_row["result_sha"] == repaired.resolved_sha

    # Part 2: Failure (check failure + unresolved markers) and repair budget cap
    ctx_fail = await _setup_conflicting_integration(tmp_path / "fail")
    repo_fail: Path = ctx_fail["repo_root"]  # type: ignore[assignment]
    store_fail: ExecutionStore = ctx_fail["store"]  # type: ignore[assignment]
    res_fail: ConflictResolver = ctx_fail["resolver"]  # type: ignore[assignment]
    out_fail = ctx_fail["outcome"]
    before_fail = _operator_snapshot(repo_fail)

    rep_fail = await res_fail.analyze(out_fail.integration_id, max_repair_attempts=1)

    def _bad_repairer(wt_path: Path, rep, attempt_num: int) -> None:
        (wt_path / "src" / "shared.py").write_text(
            "def compute(x: int) -> int:\n"
            "    return 0\n",
            encoding="utf-8",
        )

    failing_check = CheckSpec(
        check_id="must-not-be-zero",
        command=(
            sys.executable,
            "-c",
            "import pathlib; ns = {}; exec(pathlib.Path('src/shared.py').read_text(), ns); assert ns['compute'](5) == 110",
        ),
    )

    failed = await res_fail.auto_repair(
        rep_fail.conflict_id,
        repairer=_bad_repairer,
        checks=(failing_check,),
        allowed_paths=("src/shared.py",),
    )
    assert failed.repaired is False
    assert failed.status == "open"
    assert failed.resolved_sha is None
    assert failed.resolved_at is None
    assert any(f.code == "post_repair_check_failed" for f in failed.failures)
    assert _operator_snapshot(repo_fail) == before_fail

    # Repair worktree aborted MERGE_HEAD cleanly on failure
    assert failed.repair_worktree_path is not None
    merge_head_exists = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        cwd=failed.repair_worktree_path,
        capture_output=True,
    )
    assert merge_head_exists.returncode != 0

    # Budget exhausted on 2nd attempt
    with pytest.raises(ContractViolation) as exc_info:
        await res_fail.auto_repair(
            rep_fail.conflict_id,
            repairer=_bad_repairer,
            checks=(failing_check,),
        )
    assert exc_info.value.code == "repair_budget_exhausted"

    async with store_fail._connect() as db:
        row = await (
            await db.execute("SELECT status, resolved_at FROM conflict_reports WHERE id = ?", (rep_fail.conflict_id,))
        ).fetchone()
        assert row is not None
        assert row["status"] == "open"
        assert row["resolved_at"] is None


@pytest.mark.asyncio
async def test_manual_discard_options(tmp_path: Path) -> None:
    # Option A: manual workflow -> preserve worktree -> reject unresolved markers -> finalize after check
    ctx_manual = await _setup_conflicting_integration(tmp_path / "manual")
    repo_m: Path = ctx_manual["repo_root"]  # type: ignore[assignment]
    store_m: ExecutionStore = ctx_manual["store"]  # type: ignore[assignment]
    res_m: ConflictResolver = ctx_manual["resolver"]  # type: ignore[assignment]
    out_m = ctx_manual["outcome"]
    before_m = _operator_snapshot(repo_m)

    rep_m = await res_m.analyze(out_m.integration_id)
    manual_open = await res_m.resolve_manual(rep_m.conflict_id, actor="dev-alice", finalize=False)
    assert manual_open.status == "manual"
    assert manual_open.repaired is False
    assert manual_open.resolved_at is None
    assert manual_open.repair_worktree_path is not None
    wt_path = Path(manual_open.repair_worktree_path)
    assert wt_path.exists()
    assert "<<<<<<<" in (wt_path / "src" / "shared.py").read_text(encoding="utf-8")

    # Trying to finalize before removing markers fails without mutating operator branch
    with pytest.raises(ContractViolation) as unresolved_exc:
        await res_m.finalize_manual(rep_m.conflict_id, actor="dev-alice")
    assert unresolved_exc.value.code == "unresolved_conflicts_remain"
    assert _operator_snapshot(repo_m) == before_m

    # Developer resolves file in preserved worktree and finalizes with checks
    (wt_path / "src" / "shared.py").write_text(
        "def compute(x: int) -> int:\n"
        "    return (x * 2) + 100\n",
        encoding="utf-8",
    )
    check = CheckSpec(
        check_id="manual-check",
        command=(
            sys.executable,
            "-c",
            "import pathlib; ns = {}; exec(pathlib.Path('src/shared.py').read_text(), ns); assert ns['compute'](3) == 106",
        ),
    )
    manual_done = await res_m.finalize_manual(
        rep_m.conflict_id,
        actor="dev-alice",
        checks=(check,),
    )
    assert manual_done.status == "manual"
    assert manual_done.repaired is True
    assert manual_done.resolved_sha is not None
    assert manual_done.resolved_at is not None
    assert _operator_snapshot(repo_m) == before_m

    async with store_m._connect() as db:
        row = await (
            await db.execute("SELECT status, resolved_at FROM conflict_reports WHERE id = ?", (rep_m.conflict_id,))
        ).fetchone()
        assert row["status"] == "manual"
        assert row["resolved_at"] is not None

    # Option B: discard workflow
    ctx_disc = await _setup_conflicting_integration(tmp_path / "discard")
    repo_d: Path = ctx_disc["repo_root"]  # type: ignore[assignment]
    store_d: ExecutionStore = ctx_disc["store"]  # type: ignore[assignment]
    res_d: ConflictResolver = ctx_disc["resolver"]  # type: ignore[assignment]
    out_d = ctx_disc["outcome"]
    before_d = _operator_snapshot(repo_d)

    rep_d = await res_d.analyze(out_d.integration_id)
    discarded = await res_d.discard(rep_d.conflict_id, actor="dev-bob", reason="superseded_by_replan")
    assert discarded.status == "discarded"
    assert discarded.repaired is False
    assert discarded.resolved_at is not None
    assert _operator_snapshot(repo_d) == before_d

    async with store_d._connect() as db:
        row_d = await (
            await db.execute("SELECT status, resolved_at FROM conflict_reports WHERE id = ?", (rep_d.conflict_id,))
        ).fetchone()
        assert row_d["status"] == "discarded"
        assert row_d["resolved_at"] is not None

    # Terminal state rejects subsequent repair or discard transitions
    with pytest.raises((InvalidTransitionError, ContractViolation)):
        await res_d.auto_repair(rep_d.conflict_id, repairer=lambda p, r, n: None)
    with pytest.raises((InvalidTransitionError, ContractViolation)):
        await res_d.discard(rep_d.conflict_id, actor="dev-bob")


@pytest.mark.asyncio
async def test_contract_amendment_revalidates_dependents(tmp_path: Path) -> None:
    repo_root, base_sha = _init_temp_repo(tmp_path)
    store = ExecutionStore(tmp_path / "amend.db")
    await store.initialize()
    git_ws = GitWorkspaceService(repo_root, store=store)
    resolver = ConflictResolver(store, git_ws, repo_root=repo_root)
    before = _operator_snapshot(repo_root)

    run_id = f"run-{new_id()}"
    w0_id = "w0-contracts"
    w1_running_id = "w1-consumer-a"
    w1_pending_id = "w1-consumer-b"
    w1_ready_id = "w1-consumer-c"
    w_unrel_id = "w1-independent"

    w0_task = TaskSpec(
        task_id=w0_id,
        run_id=run_id,
        objective="Wave 0 shared contracts",
        assigned_executor="codex",
        acceptance_criteria=_noop_criteria("chk-w0"),
        allowed_paths=("contracts/api.py",),
        dependencies=(),
    )
    w1_running = TaskSpec(
        task_id=w1_running_id,
        run_id=run_id,
        objective="Wave 1 consumer A",
        assigned_executor="claude",
        acceptance_criteria=_noop_criteria("chk-w1a"),
        allowed_paths=("src/consumer_a.py",),
        dependencies=(w0_id,),
    )
    w1_pending = TaskSpec(
        task_id=w1_pending_id,
        run_id=run_id,
        objective="Wave 1 consumer B",
        assigned_executor="codex",
        acceptance_criteria=_noop_criteria("chk-w1b"),
        allowed_paths=("src/consumer_b.py",),
        dependencies=(w1_running_id,),
    )
    w1_ready = TaskSpec(
        task_id=w1_ready_id,
        run_id=run_id,
        objective="Wave 1 consumer C",
        assigned_executor="gemini",
        acceptance_criteria=_noop_criteria("chk-w1c"),
        allowed_paths=("src/consumer_c.py",),
        dependencies=(w0_id,),
    )
    w_unrel = TaskSpec(
        task_id=w_unrel_id,
        run_id=run_id,
        objective="Unrelated task",
        assigned_executor="codex",
        acceptance_criteria=_noop_criteria("chk-unrel"),
        allowed_paths=("src/other.py",),
        dependencies=(),
    )

    run_spec = RunSpec(
        run_id=run_id,
        project_id="proj-amend",
        objective="Wave 0 contract amendment test",
        repo_root=str(repo_root),
        base_sha=base_sha,
        base_branch="main",
        idempotency_key=f"idem-{run_id}",
        tasks=(w0_task, w1_running, w1_pending, w1_ready, w_unrel),
    )
    await store.save_run_atomic(run_spec, initial_status=RunStatus.RUNNING)

    # Wave 0 completed/accepted; Wave 1 tasks in distinct active states
    await store.update_task_status_atomic(w0_id, TaskStatus.RUNNING, 1, "task.started")
    await store.update_task_status_atomic(w0_id, TaskStatus.READY_FOR_REVIEW, 2, "task.ready_for_review")
    await store.update_task_status_atomic(w0_id, TaskStatus.ACCEPTED, 3, "task.accepted")

    await store.update_task_status_atomic(w1_running_id, TaskStatus.RUNNING, 1, "task.started")
    await store.update_task_status_atomic(w1_ready_id, TaskStatus.RUNNING, 1, "task.started")
    await store.update_task_status_atomic(w1_ready_id, TaskStatus.READY_FOR_REVIEW, 2, "task.ready_for_review")

    # Active Wave 1 worktrees: one non-conflicting (clean rebase), one conflicting on contracts/api.py
    wt_clean = git_ws.create_worktree(run_id, w1_running_id, f"att-{new_id()}", base_sha)
    (wt_clean.canonical_path / "src" / "consumer_a.py").write_text("CONSUMER = True\n", encoding="utf-8")
    _git(wt_clean.canonical_path, "add", "src/consumer_a.py")
    _git(wt_clean.canonical_path, "commit", "-m", "wave1 clean work")

    wt_conflict = git_ws.create_worktree(run_id, w1_ready_id, f"att-{new_id()}", base_sha)
    (wt_conflict.canonical_path / "contracts" / "api.py").write_text(
        "API_VERSION = 999\nPAYLOAD_FIELDS = ('id', 'legacy')\n",
        encoding="utf-8",
    )
    _git(wt_conflict.canonical_path, "add", "contracts/api.py")
    _git(wt_conflict.canonical_path, "commit", "-m", "wave1 touching contract")

    # Seed valid area and authorization in control-plane tables
    area_id = f"area-{new_id()}"
    auth_id = f"auth-{new_id()}"
    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute(
                """
                INSERT INTO areas (id, name, owner_principal_id, revision, created_at)
                VALUES (?, ?, ?, 1, datetime('now'))
                """,
                (area_id, "wave0", "lead-architect"),
            )
            await db.execute(
                """
                INSERT INTO authorizations (id, area_id, resource_ref, principal_id, scopes_json, granted_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'), NULL)
                """,
                (auth_id, area_id, "contracts/api.py", "lead-architect", json.dumps(["write", "integrate"])),
            )

    proposal = await resolver.propose_contract_amendment(
        run_id,
        w0_id,
        reason="Need additional 'tenant_id' field in API payload",
        target_files=("contracts/api.py",),
        summary="Bump API_VERSION to 2 with tenant_id",
        actor="lead-architect",
        expected_run_revision=1,
        requested_by_task_id=w1_running_id,
        authorized_actors=("lead-architect",),
        authorization_id=auth_id,
        transition_requester_needs_context=True,
        idempotency_key="propose-amend-1",
    )
    assert proposal.status == "proposed"
    assert set(proposal.affected_wave1_task_ids) == {w1_running_id, w1_pending_id, w1_ready_id}
    assert w_unrel_id not in proposal.affected_wave1_task_ids

    w1_running_after_prop = await store.get_task(w1_running_id)
    assert w1_running_after_prop is not None
    assert w1_running_after_prop["status"] == TaskStatus.NEEDS_CONTEXT.value

    amend_check = CheckSpec(
        check_id="contract-v2-check",
        command=(
            sys.executable,
            "-c",
            "import pathlib; ns = {}; exec(pathlib.Path('contracts/api.py').read_text(), ns); assert ns['API_VERSION'] == 2 and 'tenant_id' in ns['PAYLOAD_FIELDS']",
        ),
    )

    applied = await resolver.apply_contract_amendment(
        proposal.amendment_id,
        actor="lead-architect",
        expected_run_revision=1,
        patch_files={
            "contracts/api.py": "API_VERSION = 2\nPAYLOAD_FIELDS = ('id', 'name', 'tenant_id')\n",
        },
        checks=(amend_check,),
        authorized_actors=("lead-architect",),
        authorization_id=auth_id,
        active_worktrees=(wt_clean, wt_conflict),
        idempotency_key="apply-amend-1",
    )

    assert applied.status == "applied"
    assert applied.base_sha_after is not None
    assert applied.base_sha_after != base_sha
    assert applied.run_revision_after == 2
    assert str(wt_clean.canonical_path) in applied.revalidated_worktrees
    assert str(wt_conflict.canonical_path) in applied.conflicted_worktrees
    assert _operator_snapshot(repo_root) == before

    # Run record updated atomically with new base_sha and revision
    run_after = await store.get_run(run_id)
    assert run_after is not None
    assert run_after["base_sha"] == applied.base_sha_after
    assert run_after["revision"] == 2

    # Wave 1 dependents transitioned to require revalidation; unrelated task untouched
    assert (await store.get_task(w1_running_id))["status"] == TaskStatus.BLOCKED.value
    assert (await store.get_task(w1_pending_id))["status"] == TaskStatus.BLOCKED.value
    assert (await store.get_task(w1_ready_id))["status"] == TaskStatus.REJECTED.value
    assert (await store.get_task(w_unrel_id))["status"] == TaskStatus.PENDING.value

    pending = await resolver.get_pending_revalidations(run_id)
    assert set(pending) == {w1_running_id, w1_pending_id, w1_ready_id}

    rem_after_one = await resolver.mark_task_revalidated(
        run_id,
        w1_running_id,
        tested_sha=applied.base_sha_after,
    )
    assert w1_running_id not in rem_after_one
    for tid in (w1_pending_id, w1_ready_id):
        rem_after_one = await resolver.mark_task_revalidated(
            run_id,
            tid,
            tested_sha=applied.base_sha_after,
        )
    assert rem_after_one == ()
    assert await resolver.get_pending_revalidations(run_id) == ()


@pytest.mark.asyncio
async def test_conflict_resolution_flow(tmp_path: Path) -> None:
    ctx = await _setup_conflicting_integration(tmp_path)
    repo_root: Path = ctx["repo_root"]  # type: ignore[assignment]
    store: ExecutionStore = ctx["store"]  # type: ignore[assignment]
    resolver: ConflictResolver = ctx["resolver"]  # type: ignore[assignment]
    outcome = ctx["outcome"]
    before = _operator_snapshot(repo_root)

    # Step 1: Analyze conflict
    report = await resolver.analyze(outcome.integration_id)
    assert report.status == "open"
    assert report.repair_attempts_used == 0

    check = CheckSpec(
        check_id="flow-check",
        command=(
            sys.executable,
            "-c",
            "import pathlib; ns = {}; exec(pathlib.Path('src/shared.py').read_text(), ns); assert ns['compute'](4) == 108",
        ),
    )

    # Step 2: First repair attempt leaves wrong logic -> check fails -> returns to open
    attempt_1 = await resolver.auto_repair(
        report.conflict_id,
        repairer=lambda wt, rep, n: (wt / "src" / "shared.py").write_text(
            "def compute(x: int) -> int:\n    return x + 1\n",
            encoding="utf-8",
        ),
        checks=(check,),
        max_repair_attempts=2,
    )
    assert attempt_1.repaired is False
    assert attempt_1.status == "open"
    assert attempt_1.attempt_number == 1

    # Step 3: Second repair attempt fixes both behaviors -> check passes -> auto_repair resolved
    attempt_2 = await resolver.auto_repair(
        report.conflict_id,
        repairer=lambda wt, rep, n: (wt / "src" / "shared.py").write_text(
            "def compute(x: int) -> int:\n    return (x * 2) + 100\n",
            encoding="utf-8",
        ),
        checks=(check,),
        max_repair_attempts=2,
    )
    assert attempt_2.repaired is True
    assert attempt_2.status == "auto_repair"
    assert attempt_2.attempt_number == 2
    assert attempt_2.resolved_sha is not None
    assert attempt_2.resolved_at is not None

    events = await store.get_events(str(ctx["run_id"]))
    event_types = [ev.event_type for ev in events]
    assert "merge.conflict_analyzed" in event_types
    assert "merge.conflict_repair_started" in event_types
    assert "merge.conflict_repair_failed" in event_types
    assert "merge.conflict_resolved" in event_types
    assert _operator_snapshot(repo_root) == before


@pytest.mark.asyncio
async def test_conflict_negative_cases(tmp_path: Path) -> None:
    # 1. Analyzing unknown or non-conflicted integration fails
    repo_root, base_sha = _init_temp_repo(tmp_path / "nonconflict")
    store = ExecutionStore(tmp_path / "nonconflict.db")
    await store.initialize()
    git_ws = GitWorkspaceService(repo_root, store=store)
    resolver = ConflictResolver(store, git_ws, repo_root=repo_root)

    with pytest.raises(ContractViolation) as missing_int:
        await resolver.analyze("missing-integration")
    assert missing_int.value.code == "resource_not_found"

    with pytest.raises(ContractViolation) as missing_rep:
        await resolver.get_report("missing-conflict")
    assert missing_rep.value.code == "resource_not_found"

    # Successful clean integration cannot be analyzed as a conflict
    run_id = f"run-{new_id()}"
    t1 = TaskSpec(
        task_id="t-clean",
        run_id=run_id,
        objective="Clean task",
        assigned_executor="codex",
        acceptance_criteria=_noop_criteria("chk-clean"),
        allowed_paths=("src/new.py",),
    )
    w0 = TaskSpec(
        task_id="w0-base",
        run_id=run_id,
        objective="Base contract",
        assigned_executor="codex",
        acceptance_criteria=_noop_criteria("chk-w0-neg"),
        allowed_paths=("contracts/api.py",),
    )
    await store.save_run_atomic(
        RunSpec(
            run_id=run_id,
            project_id="proj-neg",
            objective="Negatives",
            repo_root=str(repo_root),
            base_sha=base_sha,
            base_branch="main",
            idempotency_key=f"idem-{run_id}",
            tasks=(w0, t1),
        ),
        initial_status=RunStatus.RUNNING,
    )
    att1_id = f"att-{new_id()}"
    wt1 = git_ws.create_worktree(run_id, "t-clean", att1_id, base_sha)
    (wt1.canonical_path / "src" / "new.py").write_text("X = 1\n", encoding="utf-8")
    _git(wt1.canonical_path, "add", "src/new.py")
    _git(wt1.canonical_path, "commit", "-m", "add new.py")
    sha1 = _git(wt1.canonical_path, "rev-parse", "HEAD")

    now = datetime.now(timezone.utc)
    att1 = TaskAttempt(
        attempt_id=att1_id,
        task_id="t-clean",
        run_id=run_id,
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=base_sha,
        workspace_path=str(wt1.canonical_path),
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now,
        finished_at=now,
        exit_reason="completed",
    )
    await store.save_attempt_atomic(att1)
    await store.update_task_status_atomic("t-clean", TaskStatus.RUNNING, 1, "task.started")
    patch_1_id, checks_1, arts_1 = _make_check_and_artifacts(
        run_id=run_id,
        attempt_id=att1.attempt_id,
        check_id="chk-clean",
        tested_sha=sha1,
    )
    res1 = TaskResult(
        result_id=f"res-{new_id()}",
        attempt_id=att1.attempt_id,
        run_id=run_id,
        base_sha=base_sha,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        task_status=TaskStatus.READY_FOR_REVIEW,
        summary="Clean",
        simulated=False,
        patch_commit_sha=sha1,
        patch_artifact_id=patch_1_id,
        changed_files=("src/new.py",),
        checks_executed=checks_1,
        artifacts=arts_1,
    )
    await store.save_task_result_atomic(t1, att1, res1)
    res1 = await store.record_review_atomic(
        t1,
        att1,
        ReviewDecision(
            result_id=res1.result_id,
            actor="reviewer",
            decision=TaskStatus.ACCEPTED.value,
            reason="Verified clean change",
            expected_revision=1,
        ),
    )
    clean_out = await git_ws.integrate_results(run_id, base_sha, (res1,))
    assert clean_out.status == "integrated"

    with pytest.raises(ContractViolation) as not_conflicted:
        await resolver.analyze(clean_out.integration_id)
    assert not_conflicted.value.code == "conflict_not_applicable"

    # 2. Scope violation during auto_repair (writing outside allowed_paths) fails and reverts to open
    ctx_scope = await _setup_conflicting_integration(tmp_path / "scope")
    res_scope: ConflictResolver = ctx_scope["resolver"]  # type: ignore[assignment]
    out_scope = ctx_scope["outcome"]
    rep_scope = await res_scope.analyze(out_scope.integration_id)

    def _scope_violating_repairer(wt_path: Path, rep, n: int) -> None:
        (wt_path / "src" / "shared.py").write_text("def compute(x: int) -> int:\n    return x\n", encoding="utf-8")
        (wt_path / "contracts" / "api.py").write_text("TAMPERED = True\n", encoding="utf-8")

    scope_res = await res_scope.auto_repair(
        rep_scope.conflict_id,
        repairer=_scope_violating_repairer,
        allowed_paths=("src/shared.py",),
    )
    assert scope_res.repaired is False
    assert scope_res.status == "open"
    assert any(f.code == "scope_violation" for f in scope_res.failures)

    # 3. Contract amendment authorization, idempotency conflict, stale revision, and failed Wave 0 check rejections
    with pytest.raises(ContractViolation) as auth_denied:
        await resolver.propose_contract_amendment(
            run_id,
            "w0-base",
            reason="Unauthorized attempt",
            target_files=("contracts/api.py",),
            summary="Should fail",
            actor="rogue-agent",
            expected_run_revision=1,
            authorized_actors=("lead-architect",),
        )
    assert auth_denied.value.code == "authorization_denied"

    prop = await resolver.propose_contract_amendment(
        run_id,
        "w0-base",
        reason="Authorized proposal",
        target_files=("contracts/api.py",),
        summary="Update contract",
        actor="lead-architect",
        expected_run_revision=1,
        authorized_actors=("lead-architect",),
        idempotency_key="idem-prop-k",
    )

    with pytest.raises(IdempotencyConflictError):
        await resolver.propose_contract_amendment(
            run_id,
            "w0-base",
            reason="Authorized proposal",
            target_files=("contracts/api.py",),
            summary="Conflicting different summary",
            actor="lead-architect",
            expected_run_revision=1,
            authorized_actors=("lead-architect",),
            idempotency_key="idem-prop-k",
        )

    with pytest.raises(OptimisticLockError):
        await resolver.apply_contract_amendment(
            prop.amendment_id,
            actor="lead-architect",
            expected_run_revision=999,
            patch_files={"contracts/api.py": "API_VERSION = 2\n"},
            authorized_actors=("lead-architect",),
        )

    failing_amend_check = CheckSpec(
        check_id="reject-amend",
        command=(sys.executable, "-c", "raise SystemExit(1)"),
    )
    with pytest.raises(ContractViolation) as amend_chk_fail:
        await resolver.apply_contract_amendment(
            prop.amendment_id,
            actor="lead-architect",
            expected_run_revision=1,
            patch_files={"contracts/api.py": "API_VERSION = 2\n"},
            checks=(failing_amend_check,),
            authorized_actors=("lead-architect",),
        )
    assert amend_chk_fail.value.code == "amendment_check_failed"
    run_after_fail = await store.get_run(run_id)
    assert run_after_fail is not None
    assert run_after_fail["revision"] == 1
    assert run_after_fail["base_sha"] == base_sha
