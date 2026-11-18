"""Wave 2 Slice 2C unit & integration tests.

Covers:
- BE-08: max_attempts checked before _prepare_task_running (never strands task in running)
- BE-09: asyncio.CancelledError shielded cleanup in _execute_task_attempt_inner
- BE-10: discard_run_runtime queries SQLite workspaces table across process restarts
- BE-15: json.dumps used for provider_model_json and conflict JSON columns
- BE-16: TaskDecomposer removes duplicate openapi.json entry
- DAY-08: HYDRA_CONFIG env override and reload_config() helper
- DAY-09: RouteSelector & PersistentEngine carry OmniRoute quota_key telemetry on direct CLI routes
- DAY-10: execute_run / finalize_run_if_terminal / exhausted attempts transition run to FAILED
- DAY-11: ConflictResolver transitions run to SUCCEEDED once all conflicts are resolved & integrated
- DAY-12: Orchestrator._covers('*', '**') and WorkspaceRegistry update_repository / delete_repository
- DAY-13: RemoteLocalAdapter & ApiGatewayAdapter HTTP 429 -> LimitHitException with Retry-After
- DAY-14: SearchService indexes conversations & recent conversation_turns with redaction
- DAY-16: integrate_run idempotency on SUCCEEDED runs + optional update_target_branch fast-forward
- DAY-18: ServerConfig / HydraConfig allowed_workspace_roots synced with HYDRA_ALLOWED_WORKSPACE_ROOTS
- SEC-05: ConflictResolver rejects worktree paths outside worktree_base_dir and symlinks/junctions
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import httpx
import pytest

from hydra_orch.adapter.api_gateway import ApiGatewayAdapter
from hydra_orch.adapter.base import LimitHitException
from hydra_orch.adapter.remote_local import RemoteLocalAdapter
from hydra_orch.config import ConfigError, HydraConfig, ServerConfig, load_config, reload_config
from hydra_orch.core.agent_registry import CERTIFICATION_CHECKS, DriverCertificationReport
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.conflict_resolver import ConflictResolver
from hydra_orch.core.git_workspace import GitWorkspaceService
from hydra_orch.core.identifier import new_id
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.profile_service import ProfileDefinition
from hydra_orch.core.route_selector import RouteCandidate, RouteSelector
from hydra_orch.core.run_service import RunService
from hydra_orch.core.search_index import SearchService
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.engine.decomposer import TaskDecomposer
from hydra_orch.engine.orchestration import CommandBinding, OrchestrationPlan, Orchestrator, TaskOwnership
from hydra_orch.engine.persist import PersistentEngine
from hydra_orch.model import (
    BudgetPolicy,
    ChatMessage,
    CheckSpec,
    ContractViolation,
    IntegrationStatus,
    ProcessStatus,
    ReviewDecision,
    RunSpec,
    RunStatus,
    TaskSpec,
    TaskStatus,
)
from test_profile import profiles


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return res.stdout.strip()


@pytest.fixture
def temp_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Hydra Wave2 Test")
    _git(repo, "config", "user.email", "wave2@hydra.local")
    (repo / ".gitignore").write_text(".orchestrator/\n", encoding="utf-8")
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "app.py").write_text("VALUE = 0\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    return repo, _git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# BE-08: max_attempts checked BEFORE mutating task status to running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_be08_max_attempts_exceeded_never_strands_task_running(temp_repo: Path) -> None:
    repo, base_sha = temp_repo
    service = RunService(repo_root=repo)

    t1 = TaskSpec(
        task_id="t-cap-1",
        run_id="run-be08",
        objective="Task with max_attempts=1",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-fail", command=(sys.executable, "-c", "raise SystemExit(1)")),),
        allowed_paths=("src/**",),
    )
    t2 = TaskSpec(
        task_id="t-cap-2",
        run_id="run-be08",
        objective="Independent sibling keeping run active",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-ok", command=(sys.executable, "-c", "print('ok')")),),
        allowed_paths=("src/**",),
    )
    spec = RunSpec(
        run_id="run-be08",
        project_id="proj-be08",
        objective="Verify BE-08 max_attempts guard",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        budget_policy=BudgetPolicy(max_attempts=1),
        idempotency_key="idem-be08-max-attempts-01",
        tasks=(t1, t2),
    )
    await service.submit_run(spec)

    write_cmd = (
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 1\\n', encoding='utf-8')",
    )
    out1 = await service.execute_task_attempt("run-be08", "t-cap-1", custom_command=write_cmd)
    assert out1.result.task_status == TaskStatus.FAILED

    task_before_retry = await service.store.get_task("t-cap-1")
    assert task_before_retry is not None
    assert task_before_retry["status"] == TaskStatus.FAILED.value
    rev_before = task_before_retry["revision"]

    with pytest.raises(ContractViolation) as exc_info:
        await service.retry_task("run-be08", "t-cap-1", custom_command=write_cmd)
    assert exc_info.value.code == "max_attempts_exceeded"

    # Task must remain FAILED (never stranded in RUNNING!) with unchanged revision
    task_after_retry = await service.store.get_task("t-cap-1")
    assert task_after_retry is not None
    assert task_after_retry["status"] == TaskStatus.FAILED.value
    assert task_after_retry["revision"] == rev_before


# ---------------------------------------------------------------------------
# BE-09: asyncio.CancelledError reconciles attempt & task to CANCELLED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_be09_asyncio_cancellation_reconciles_attempt_and_task_to_cancelled(
    temp_repo: Path, tmp_path: Path
) -> None:
    repo, base_sha = temp_repo
    service = RunService(repo_root=repo)
    marker = tmp_path / "worker_started.flag"

    t_worker = TaskSpec(
        task_id="t-cancel-worker",
        run_id="run-be09",
        objective="Long-running worker to cancel via asyncio",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-ok", command=(sys.executable, "-c", "print('ok')")),),
        allowed_paths=("src/**",),
    )
    t_check = TaskSpec(
        task_id="t-cancel-check",
        run_id="run-be09",
        objective="Worker succeeds then slow acceptance check is cancelled",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk-slow",
                command=(
                    sys.executable,
                    "-c",
                    f"import pathlib, time; pathlib.Path({str(tmp_path / 'chk_started.flag')!r}).write_text('1'); time.sleep(20)",
                ),
            ),
        ),
        allowed_paths=("src/**",),
    )
    spec = RunSpec(
        run_id="run-be09",
        project_id="proj-be09",
        objective="Verify BE-09 cancellation cleanup",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        idempotency_key="idem-be09-cancel-clean-01",
        tasks=(t_worker, t_check),
    )
    await service.submit_run(spec)

    # 1. Cancel during worker execution
    slow_worker_cmd = (
        sys.executable,
        "-c",
        f"import pathlib, time; pathlib.Path({str(marker)!r}).write_text('started'); time.sleep(20)",
    )
    fut1 = asyncio.create_task(
        service.execute_task_attempt("run-be09", "t-cancel-worker", custom_command=slow_worker_cmd)
    )
    for _ in range(200):
        if marker.exists():
            break
        await asyncio.sleep(0.03)
    assert marker.exists()

    fut1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await fut1

    atts_1 = await service.store.list_attempts("t-cancel-worker")
    assert len(atts_1) == 1
    assert atts_1[0].process_status == ProcessStatus.CANCELLED
    assert atts_1[0].finished_at is not None
    assert atts_1[0].exit_reason == "asyncio_cancelled"
    task_1_rec = await service.store.get_task("t-cancel-worker")
    assert task_1_rec is not None
    assert task_1_rec["status"] == TaskStatus.CANCELLED.value

    # 2. Cancel during acceptance checks
    fast_worker_cmd = (
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 42\\n', encoding='utf-8')",
    )
    chk_flag = tmp_path / "chk_started.flag"
    fut2 = asyncio.create_task(
        service.execute_task_attempt("run-be09", "t-cancel-check", custom_command=fast_worker_cmd)
    )
    for _ in range(200):
        if chk_flag.exists():
            break
        await asyncio.sleep(0.03)
    assert chk_flag.exists()

    fut2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await fut2

    atts_2 = await service.store.list_attempts("t-cancel-check")
    assert len(atts_2) == 1
    assert atts_2[0].process_status == ProcessStatus.CANCELLED
    task_2_rec = await service.store.get_task("t-cancel-check")
    assert task_2_rec is not None
    assert task_2_rec["status"] == TaskStatus.CANCELLED.value


# ---------------------------------------------------------------------------
# BE-10: discard_run_runtime cleans SQLite workspaces from prior lifetimes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_be10_discard_run_runtime_cleans_sqlite_workspaces_across_process_restart(
    temp_repo: Path,
) -> None:
    repo, base_sha = temp_repo
    svc1 = RunService(repo_root=repo)

    t1 = TaskSpec(
        task_id="t-disc",
        run_id="run-be10",
        objective="Create preserved worktree",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-1", command=(sys.executable, "-c", "print('ok')")),),
        allowed_paths=("src/**",),
    )
    spec = RunSpec(
        run_id="run-be10",
        project_id="proj-be10",
        objective="Verify BE-10 restart worktree cleanup",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        idempotency_key="idem-be10-discard-ws-0001",
        tasks=(t1,),
    )
    await svc1.submit_run(spec)
    out = await svc1.execute_task_attempt(
        "run-be10",
        "t-disc",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 9\\n', encoding='utf-8')",
        ),
    )
    wt_path = out.workspace.canonical_path
    assert wt_path.exists()
    await svc1.cancel_run("run-be10", reason="done_testing")

    # Simulate new process lifetime with empty in-memory _workspaces cache
    svc2 = RunService(repo_root=repo)
    assert svc2.git_workspace._workspaces == {}

    discarded = await svc2.discard_run_runtime("run-be10", force=True)
    assert out.attempt.attempt_id in discarded["cleaned_worktrees"]
    assert not wt_path.exists()

    async with svc2.store._connect() as db:
        ws_row = await (
            await db.execute("SELECT status FROM workspaces WHERE attempt_id = ?", (out.attempt.attempt_id,))
        ).fetchone()
    assert ws_row is not None
    assert ws_row["status"] == "cleaned"


# ---------------------------------------------------------------------------
# DAY-10: execute_run & exhausted task failures transition runs.status -> FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day10_execute_run_and_exhausted_attempts_transition_run_to_failed(
    temp_repo: Path,
) -> None:
    repo, base_sha = temp_repo
    service = RunService(repo_root=repo)

    # Part A: execute_run with failed root task and dependent downstream task
    t_root = TaskSpec(
        task_id="t-root",
        run_id="run-day10-exec",
        objective="Fails check",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-fail", command=(sys.executable, "-c", "raise SystemExit(1)")),),
        allowed_paths=("src/app.py",),
    )
    t_dep = TaskSpec(
        task_id="t-dep",
        run_id="run-day10-exec",
        objective="Depends on t-root",
        assigned_executor="codex",
        dependencies=("t-root",),
        acceptance_criteria=(CheckSpec(check_id="chk-ok", command=(sys.executable, "-c", "print('ok')")),),
        allowed_paths=("src/dep.py",),
    )
    spec_exec = RunSpec(
        run_id="run-day10-exec",
        project_id="proj-day10",
        objective="Verify execute_run terminal failure",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        budget_policy=BudgetPolicy(max_attempts=2),
        idempotency_key="idem-day10-exec-run-0001",
        tasks=(t_root, t_dep),
    )
    await service.submit_run(spec_exec)
    final_rec = await service.execute_run(
        "run-day10-exec",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = -1\\n', encoding='utf-8')",
        ),
    )
    assert final_rec["status"] == RunStatus.FAILED.value
    dep_rec = await service.store.get_task("t-dep")
    assert dep_rec is not None
    assert dep_rec["status"] == TaskStatus.BLOCKED.value

    # Part B: step-by-step execute_task_attempt keeps run RUNNING while retries remain, then FAILED when exhausted
    t_step = TaskSpec(
        task_id="t-step",
        run_id="run-day10-step",
        objective="Step retry exhaustion",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-fail", command=(sys.executable, "-c", "raise SystemExit(1)")),),
        allowed_paths=("src/app.py",),
    )
    spec_step = RunSpec(
        run_id="run-day10-step",
        project_id="proj-day10",
        objective="Step exhaustion transitions run to failed",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        budget_policy=BudgetPolicy(max_attempts=2),
        idempotency_key="idem-day10-step-run-0002",
        tasks=(t_step,),
    )
    await service.submit_run(spec_step)
    bad_cmd = (
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 123\\n', encoding='utf-8')",
    )
    await service.execute_task_attempt("run-day10-step", "t-step", custom_command=bad_cmd)
    mid_run = await service.store.get_run("run-day10-step")
    assert mid_run is not None
    assert mid_run["status"] == RunStatus.RUNNING.value

    await service.retry_task("run-day10-step", "t-step", custom_command=bad_cmd)
    end_run = await service.store.get_run("run-day10-step")
    assert end_run is not None
    assert end_run["status"] == RunStatus.FAILED.value


# ---------------------------------------------------------------------------
# DAY-16: Idempotent integrate_run + optional update_target_branch fast-forward
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day16_integrate_run_idempotent_and_update_target_branch(temp_repo: Path) -> None:
    repo, base_sha = temp_repo
    service = RunService(repo_root=repo)

    t1 = TaskSpec(
        task_id="t-int",
        run_id="run-day16",
        objective="Update VALUE to 77",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk-77",
                command=(sys.executable, "-c", "from src.app import VALUE; assert VALUE == 77"),
            ),
        ),
        allowed_paths=("src/app.py",),
    )
    spec = RunSpec(
        run_id="run-day16",
        project_id="proj-day16",
        objective="Idempotent integration and branch fast-forward",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        idempotency_key="idem-day16-integrate-0001",
        tasks=(t1,),
    )
    await service.submit_run(spec)
    out = await service.execute_task_attempt(
        "run-day16",
        "t-int",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 77\\n', encoding='utf-8')",
        ),
    )
    await service.review_task_result(
        "run-day16",
        out.result.result_id,
        actor="operator",
        decision="accepted",
        reason="Verified",
        expected_revision=1,
    )

    first = await service.integrate_run("run-day16")
    assert first.status == IntegrationStatus.INTEGRATED
    assert first.result_sha is not None
    # Operator checkout on main untouched when update_target_branch=False
    assert _git(repo, "rev-parse", "refs/heads/main") == base_sha

    # Second call is idempotent instead of failing
    second = await service.integrate_run("run-day16")
    assert second.status == IntegrationStatus.INTEGRATED
    assert second.integration_id == first.integration_id
    assert second.result_sha == first.result_sha
    assert second.merged_result_ids == first.merged_result_ids

    # Dirty checkout blocks fast-forward of active branch
    (repo / "dirty.tmp").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(ContractViolation) as dirty_exc:
        await service.integrate_run("run-day16", update_target_branch=True)
    assert dirty_exc.value.code == "dirty_checkout"
    (repo / "dirty.tmp").unlink()

    # Clean checkout fast-forwards main when update_target_branch=True
    ff_outcome = await service.integrate_run("run-day16", update_target_branch=True)
    assert ff_outcome.result_sha == first.result_sha
    assert _git(repo, "rev-parse", "refs/heads/main") == first.result_sha


# ---------------------------------------------------------------------------
# BE-15, DAY-11 & SEC-05: ConflictResolver JSON serialization, run SUCCEEDED & path fences
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_be15_day11_and_sec05_conflict_resolver_run_succeeded_json_and_symlink_fence(
    temp_repo: Path, tmp_path: Path
) -> None:
    repo, base_sha = temp_repo
    service = RunService(repo_root=repo)

    ta = TaskSpec(
        task_id="t-conf-a",
        run_id="run-day11",
        objective="Set VALUE = 10",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-a", command=(sys.executable, "-c", "import src.app")),),
        allowed_paths=("src/app.py",),
    )
    tb = TaskSpec(
        task_id="t-conf-b",
        run_id="run-day11",
        objective="Set VALUE = 20",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="chk-b", command=(sys.executable, "-c", "import src.app")),),
        allowed_paths=("src/app.py",),
    )
    spec = RunSpec(
        run_id="run-day11",
        project_id="proj-day11",
        objective="Conflict resolution transitions run to SUCCEEDED",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="swarm",
        idempotency_key="idem-day11-conflict-0001",
        tasks=(ta, tb),
    )
    await service.submit_run(spec)

    # BE-15: special characters in provider/model must serialize as valid JSON in list_run_tasks
    out_a = await service.execute_task_attempt(
        "run-day11",
        "t-conf-a",
        provider='openai"custom\\p',
        model='gpt-5"quote\\m',
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 10\\n', encoding='utf-8')",
        ),
    )
    out_b = await service.execute_task_attempt(
        "run-day11",
        "t-conf-b",
        custom_command=(
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path('src/app.py').write_text('VALUE = 20\\n', encoding='utf-8')",
        ),
    )

    listed_tasks = await service.list_run_tasks("run-day11")
    pm_parsed = json.loads(listed_tasks[0]["attempts"][0]["provider_model_json"])
    assert pm_parsed == {"model": 'gpt-5"quote\\m', "provider": 'openai"custom\\p'}
    assert ConflictResolver._serialize_json_column({"provider": "a", "model": 'b"c'}) == '{"model": "b\\"c", "provider": "a"}'

    await service.review_task_result("run-day11", out_a.result.result_id, actor="op", decision="accepted", reason="ok", expected_revision=1)
    await service.review_task_result("run-day11", out_b.result.result_id, actor="op", decision="accepted", reason="ok", expected_revision=1)

    int_out = await service.integrate_run("run-day11")
    assert int_out.status == IntegrationStatus.CONFLICTED
    assert (await service.store.get_run("run-day11"))["status"] == RunStatus.FAILED.value

    resolver = ConflictResolver(service.store, service.git_workspace)
    report = await resolver.analyze(int_out.integration_id)

    # SEC-05: Reject operator root checkout, outside directory, and symlink/junction inside worktree_base_dir
    with pytest.raises(ContractViolation) as root_exc:
        await resolver.resolve_manual(report.conflict_id, worktree_path=repo)
    assert root_exc.value.code == "operator_checkout_protected"

    outside_dir = tmp_path / "outside_wt"
    outside_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ContractViolation) as out_exc:
        await resolver.resolve_manual(report.conflict_id, worktree_path=outside_dir)
    assert out_exc.value.code == "workspace_invalid"

    link_path = service.git_workspace.worktree_base_dir / "evil_link_wt"
    link_created = False
    if os.name == "nt":
        mk = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(outside_dir)],
            capture_output=True,
            text=True,
        )
        link_created = mk.returncode == 0
    else:
        try:
            link_path.symlink_to(outside_dir, target_is_directory=True)
            link_created = True
        except OSError:
            link_created = False

    if link_created:
        try:
            with pytest.raises(ContractViolation) as link_exc:
                await resolver.resolve_manual(report.conflict_id, worktree_path=link_path)
            assert link_exc.value.code == "workspace_invalid"
        finally:
            if os.name == "nt":
                os.rmdir(link_path)
            else:
                link_path.unlink(missing_ok=True)

    # DAY-11: Resolving the conflict cleanly transitions runs.status -> SUCCEEDED and records run.finished
    repaired = await resolver.auto_repair(
        report.conflict_id,
        repairer=lambda wt, rep, n: (wt / "src" / "app.py").write_text("VALUE = 30\n", encoding="utf-8"),
        checks=(
            CheckSpec(
                check_id="chk-merged-30",
                command=(sys.executable, "-c", "from src.app import VALUE; assert VALUE == 30"),
            ),
        ),
    )
    assert repaired.repaired is True
    run_after = await service.store.get_run("run-day11")
    assert run_after is not None
    assert run_after["status"] == RunStatus.SUCCEEDED.value

    events = await service.store.get_events("run-day11")
    assert any(e.event_type == "merge.conflict_resolved" for e in events)
    assert any(
        e.event_type == "run.finished" and e.redacted_payload.get("status") == "succeeded"
        for e in events
    )


# ---------------------------------------------------------------------------
# BE-16 & DAY-12: TaskDecomposer deduplication, _covers('*', '**'), WorkspaceRegistry CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_be16_and_day12_decomposer_covers_and_workspace_registry_crud(
    temp_repo: Path, tmp_path: Path
) -> None:
    # BE-16: No duplicate openapi.json in TaskDecomposer
    decomposer = TaskDecomposer()
    tasks_w0 = decomposer.decompose("Build multi-tenant SaaS API", include_wave_0=True)
    all_targets = [f for t in tasks_w0 for f in t.target_files]
    assert all_targets.count("openapi.json") == 1
    docs_task = next(t for t in tasks_w0 if t.role_key == "docs_and_review")
    assert "openapi.json" not in docs_task.target_files

    # DAY-12: Orchestrator._covers handles '*' and '**' for deeply nested relative paths
    assert Orchestrator._covers("*", "src/foo/bar.py") is True
    assert Orchestrator._covers("**", "src/foo/bar.py") is True
    assert Orchestrator._covers("**/*", "src/foo/bar.py") is True
    assert Orchestrator._covers("src/**", "src/foo/bar.py") is True
    assert Orchestrator._covers("src/**", "tests/foo.py") is False

    # DAY-12: WorkspaceRegistry.update_repository & delete_repository
    repo, _ = temp_repo
    (repo / "secrets").mkdir(exist_ok=True)
    (repo / "secrets" / "token.txt").write_text("placeholder\n", encoding="utf-8")

    store = ExecutionStore(tmp_path / "ws_crud.sqlite")
    reg = WorkspaceRegistry(store, allowed_roots=[tmp_path])
    area = await reg.create_area("Eng", principal_id="operator")
    ws = await reg.create_workspace(area["id"], "Core", principal_id="operator")
    proj = await reg.create_project(ws["id"], "InitialName", repo, principal_id="operator")
    registered = await reg.register_repository(
        proj["id"],
        repo,
        principal_id="operator",
        authorized_principal_id="operator",
        scopes=("read", "write", "execute"),
        allowed_paths=("src/**",),
    )

    # Cross-principal update denied
    with pytest.raises(ContractViolation) as denied:
        await reg.update_repository(registered["id"], name="Hijack", principal_id="intruder")
    assert denied.value.code == "authorization_denied"

    # Update name, allowed_paths=['*'], and forbidden_paths=['secrets/**']
    updated = await reg.update_repository(
        registered["id"],
        name="RenamedRepo",
        allowed_paths=["*"],
        forbidden_paths=["secrets/**"],
        principal_id="operator",
    )
    assert updated["name"] == "RenamedRepo"
    assert updated["allowed_paths"] == ["*"]
    assert updated["forbidden_paths"] == ["secrets/**"]
    assert updated["revision"] == 2

    # '*' now allows nested path, while forbidden_paths blocks secrets/token.txt
    resolved_ok = await reg.resolve_path(registered["id"], "src/app.py", principal_id="operator")
    assert resolved_ok == (repo / "src" / "app.py").resolve()
    with pytest.raises(ContractViolation) as forb_exc:
        await reg.resolve_path(registered["id"], "secrets/token.txt", principal_id="operator")
    assert forb_exc.value.code == "scope_violation"

    # Delete repository revokes authorization and removes registration
    deleted = await reg.delete_repository(registered["id"], principal_id="operator")
    assert deleted["deleted"] is True
    assert await reg.list_repositories(proj["id"], principal_id="operator") == []
    with pytest.raises(ContractViolation):
        await reg.resolve_repository(registered["id"], principal_id="operator")


# ---------------------------------------------------------------------------
# DAY-09: RouteSelector & PersistentEngine carry OmniRoute quota_key on direct CLI routes
# ---------------------------------------------------------------------------


class _LiveQuotaGateway:
    def __init__(self, sequence: list[dict]) -> None:
        self.sequence = list(sequence)
        self.calls = 0

    async def is_available(self) -> bool:
        return True

    async def get_quota_status(self) -> dict:
        idx = min(self.calls, len(self.sequence) - 1)
        self.calls += 1
        return self.sequence[idx]


@pytest.mark.asyncio
async def test_day09_route_selector_and_persistent_engine_poll_live_omniroute_quota_on_direct_cli(
    profiles, tmp_path: Path
) -> None:
    profiles_service, definition, repository, existing = profiles
    binary = Path(sys.executable)
    profiles_service.agents.locate = lambda _: str(binary)
    agent = await profiles_service.agents.get_agent(definition.agent_ref)

    report = DriverCertificationReport(
        agent_id=agent.agent_id,
        driver_type="codex",
        agent_version="1",
        platform=platform.system(),
        executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        capabilities=agent.declared_capabilities,
        passed_checks=tuple(CERTIFICATION_CHECKS),
        simulated=False,
        issued_at=datetime.now(timezone.utc),
    )
    cert_path = profiles_service.agents.certification_root / "codex_day09.json"
    cert_path.write_text(report.model_dump_json(), encoding="utf-8")
    await profiles_service.agents.import_certificate(agent.agent_id, cert_path, principal_id="operator")

    definition = ProfileDefinition.model_validate(
        {
            **definition.model_dump(mode="json"),
            "orchestration_mode": "persistent",
        }
    )
    await profiles_service.update_profile(definition, expected_revision=1)

    run_id = "run-day09-persist"
    task = TaskSpec(
        task_id="job-persist",
        run_id=run_id,
        objective="Write persistent output after quota resets",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk-persist",
                command=(sys.executable, "-c", "import pathlib; assert pathlib.Path('src/p.txt').read_text() == 'done'"),
            ),
        ),
        allowed_paths=("src/p.txt",),
    )
    run_spec = RunSpec.model_validate(
        {
            **existing.model_dump(mode="json"),
            "run_id": run_id,
            "orchestration_mode": "persistent",
            "idempotency_key": "idem-day09-persistent-01",
            "tasks": [task.model_dump(mode="json")],
        }
    )
    runs = RunService(repo_root=run_spec.repo_root, store=profiles_service.store)
    await runs.submit_run(run_spec)

    # Sequence: first poll -> 0% remaining (exhausted); second poll -> 88% remaining (reset!)
    gw = _LiveQuotaGateway(
        [
            {"status": "observed", "chatgpt_plus": {"status": "observed", "remaining_percent": 0.0, "resets_in_seconds": 1}},
            {"status": "observed", "chatgpt_plus": {"status": "observed", "remaining_percent": 88.0, "resets_in_seconds": 3600}},
        ]
    )
    selector = RouteSelector(
        runs.store,
        profiles_service.agents,
        MetricsService(runs.store),
        gateway=gw,  # type: ignore[arg-type]
        connection_mode="optional",
    )

    # Notice: mode='direct' and quota_key omitted on RouteCandidate -> PersistentEngine infers quota_key='codex'!
    route = RouteCandidate(
        route_id="direct-codex",
        agent_id=agent.agent_id,
        model_ref="codex/gpt-6-astra",
        mode="direct",
    )
    worker_code = "import pathlib; p = pathlib.Path('src/p.txt'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('done')"
    plan = OrchestrationPlan(
        run=run_spec,
        profile_id=definition.profile_id,
        repository_id=repository["id"],
        routes=(route,),
        commands=(CommandBinding(route_id="direct-codex", args=("-c", worker_code, "codex/gpt-6-astra")),),
        ownership=(TaskOwnership(task_id="job-persist", paths=("src/p.txt",)),),
        quota_wait_seconds=0.5,
        quota_poll_seconds=0.02,
    )

    orchestrator = Orchestrator(runs, profiles_service, selector)
    persist_engine = PersistentEngine(orchestrator)
    rep = await persist_engine.execute_persistent(
        plan,
        principal_id="operator",
        reviewer=lambda res: asyncio.sleep(
            0,
            result=ReviewDecision(
                result_id=res.result_id,
                actor="operator",
                decision="accepted",
                reason="ok",
                expected_revision=res.revision,
            ),
        ),
        integrate=True,
    )
    assert rep.status == "succeeded"
    assert gw.calls >= 2
    decisions = await selector.list_decisions(run_id)
    assert len(decisions) == 1
    audit_cand = json.loads(decisions[0]["candidates_json"])[0]
    assert audit_cand["quota_key"] == "codex"
    assert audit_cand["quota_status"] == "observed"
    assert audit_cand["remaining_percent"] == 88.0


# ---------------------------------------------------------------------------
# DAY-13: RemoteLocalAdapter & ApiGatewayAdapter HTTP 429 + Retry-After
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day13_remote_local_and_api_gateway_429_limit_hit_and_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient
    state = {"retry_after": "37", "endpoint_429": "openai"}

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Retry-After": state["retry_after"]} if state["retry_after"] is not None else {}
        if request.url.path.endswith("/chat/completions"):
            if state["endpoint_429"] == "openai":
                return httpx.Response(429, headers=headers, json={"error": "rate_limited"})
            return httpx.Response(404)
        if request.url.path.endswith("/api/chat"):
            return httpx.Response(429, headers=headers, json={"error": "ollama_busy"})
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )

    # 1. RemoteLocalAdapter on /v1/chat/completions with Retry-After: 37
    remote_adapter = RemoteLocalAdapter("ollama_local", {"base_url": "http://127.0.0.1:11434"})
    with pytest.raises(LimitHitException) as rl_exc:
        await remote_adapter.generate([ChatMessage(role="user", content="hi")])
    assert rl_exc.value.provider == "ollama_local"
    assert rl_exc.value.reset_in_seconds == 37
    assert getattr(rl_exc.value, "retry_after") == 37

    # 2. RemoteLocalAdapter fallback to /api/chat without Retry-After
    state["endpoint_429"] = "ollama"
    state["retry_after"] = None  # type: ignore[assignment]
    with pytest.raises(LimitHitException) as rl_no_hdr:
        await remote_adapter.generate([ChatMessage(role="user", content="hi")])
    assert rl_no_hdr.value.reset_in_seconds == 60
    assert getattr(rl_no_hdr.value, "retry_after") is None

    # 3. ApiGatewayAdapter with Retry-After: 19 and without Retry-After
    state["endpoint_429"] = "openai"
    state["retry_after"] = "19"
    monkeypatch.setenv("TEST_GW_KEY_DAY13", "sk-test-key")
    api_adapter = ApiGatewayAdapter(
        "openrouter",
        {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "TEST_GW_KEY_DAY13", "default_model": "m1"},
    )
    with pytest.raises(LimitHitException) as gw_exc:
        await api_adapter.generate([ChatMessage(role="user", content="hello")])
    assert gw_exc.value.provider == "openrouter"
    assert gw_exc.value.reset_in_seconds == 19
    assert getattr(gw_exc.value, "retry_after") == 19

    state["retry_after"] = None  # type: ignore[assignment]
    with pytest.raises(LimitHitException) as gw_no_hdr:
        await api_adapter.generate([ChatMessage(role="user", content="hello")])
    assert gw_no_hdr.value.reset_in_seconds == 60
    assert getattr(gw_no_hdr.value, "retry_after") is None


# ---------------------------------------------------------------------------
# DAY-14: SearchService indexes conversations & recent turns with redaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day14_search_service_indexes_conversations_and_turns_with_redaction(
    tmp_path: Path,
) -> None:
    store = ExecutionStore(tmp_path / "search_conv.sqlite")
    await store.initialize()

    secret_tok = "sk-live-secret9876543210abcdef"
    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute(
                "INSERT INTO projects (id, canonical_root, name) VALUES (?, ?, ?)",
                ("proj-conv", str(tmp_path / "repo-conv"), "Billing Core"),
            )
            await db.execute(
                "INSERT INTO conversations (id, project_id, title, executor) VALUES (?, ?, ?, ?)",
                ("conv-alpha-42", "proj-conv", "Refactor Stripe Webhook", "codex"),
            )
            await db.execute(
                """
                INSERT INTO conversation_turns (
                    id, conversation_id, ordinal, idempotency_key, request_hash, content, response, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
                """,
                (
                    "turn-1",
                    "conv-alpha-42",
                    1,
                    "idem-t1",
                    "hash-t1",
                    "Please inspect the idempotency ledger handler",
                    f"Updated ledger retry logic; rotated key {secret_tok} safely.",
                ),
            )

    svc = SearchService(store)

    # Match by conversation title in global search
    by_title = await svc.search("Stripe Webhook")
    assert any(h["kind"] == "conversation" and h["id"] == "conv-alpha-42" for h in by_title)

    # Match by conversation ID with scope="conversations"
    by_id = await svc.search("conv-alpha-42", scope="conversations")
    assert len(by_id) == 1
    assert by_id[0]["kind"] == "conversation"
    assert by_id[0]["project_id"] == "proj-conv"

    # Match by turn content & response snippet, ensuring secret is redacted
    by_turn = await svc.search("ledger retry", scope="conversation")
    assert len(by_turn) == 1
    assert "ledger retry" in by_turn[0]["subtitle"].lower()
    assert secret_tok not in json.dumps(by_turn)
    assert "[REDACTED]" in by_turn[0]["subtitle"]

    # Searching for raw secret yields empty list
    assert await svc.search(secret_tok) == []


# ---------------------------------------------------------------------------
# DAY-08 & DAY-18: HYDRA_CONFIG env override, reload_config, allowed_workspace_roots
# ---------------------------------------------------------------------------


def test_day08_and_day18_config_env_override_reload_and_allowed_workspace_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_file = tmp_path / "custom_hydra.yaml"
    ws_a = str(tmp_path / "ws_alpha")
    ws_b = str(tmp_path / "ws_beta")
    cfg_file.write_text(
        f"hydra:\n  proxy_port: 8123\nallowed_workspace_roots:\n  - {json.dumps(ws_a)}\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HYDRA_CONFIG", str(cfg_file))
    monkeypatch.delenv("HYDRA_ALLOWED_WORKSPACE_ROOTS", raising=False)

    loaded = load_config(reload=True)
    assert loaded.server.port == 8123
    assert loaded.allowed_workspace_roots == [ws_a]
    assert loaded.server.allowed_workspace_roots == [ws_a]

    # Modify file on disk -> cached load_config() returns old until reload_config() is called
    cfg_file.write_text(
        f"hydra:\n  proxy_port: 8456\nserver:\n  allowed_workspace_roots:\n    - {json.dumps(ws_b)}\n",
        encoding="utf-8",
    )
    assert load_config().server.port == 8123
    reloaded = reload_config()
    assert reloaded.server.port == 8456
    assert reloaded.allowed_workspace_roots == [ws_b]
    assert reloaded.server.allowed_workspace_roots == [ws_b]
    assert load_config().server.port == 8456

    # HYDRA_ALLOWED_WORKSPACE_ROOTS env var syncs with ServerConfig & HydraConfig
    ws_env_1 = str(tmp_path / "env_one")
    ws_env_2 = str(tmp_path / "env_two")
    monkeypatch.setenv("HYDRA_ALLOWED_WORKSPACE_ROOTS", json.dumps([ws_env_1, ws_env_2]))
    env_cfg = load_config()
    assert env_cfg.allowed_workspace_roots == [ws_env_1, ws_env_2]
    assert env_cfg.server.allowed_workspace_roots == [ws_env_1, ws_env_2]
    assert ServerConfig().allowed_workspace_roots == [ws_env_1, ws_env_2]

    # Missing HYDRA_CONFIG raises ConfigError
    monkeypatch.setenv("HYDRA_CONFIG", str(tmp_path / "does_not_exist.yaml"))
    with pytest.raises(ConfigError):
        load_config(reload=True)

    # Restore clean default cache at end of test
    monkeypatch.delenv("HYDRA_CONFIG", raising=False)
    monkeypatch.delenv("HYDRA_ALLOWED_WORKSPACE_ROOTS", raising=False)
    reload_config()
