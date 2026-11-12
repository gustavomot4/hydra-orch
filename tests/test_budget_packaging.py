"""T28 hermetic tests for BudgetGovernor (RF29/RT29) and PRPackager (RF30/RT30)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hydra_orch.core.budget import BudgetGovernor
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.metrics import MetricSample, MetricsService
from hydra_orch.core.packaging import PRPackager
from hydra_orch.core.redaction import REDACTED, redaction_scope
from hydra_orch.core.run_service import RunService
from hydra_orch.model import (
    BudgetPolicy,
    CheckSpec,
    ContractViolation,
    ProcessStatus,
    RunSpec,
    RunStatus,
    TaskAttempt,
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


def _init_git_repo(tmp_path: Path, name: str = "repo") -> tuple[Path, str]:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Hydra Test Operator")
    _git(repo, "config", "user.email", "operator@hydra.local")
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "app.py").write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore: initial commit")
    sha = _git(repo, "rev-parse", "HEAD")
    return repo, sha


def _make_run_spec(
    repo: Path,
    base_sha: str,
    *,
    run_id: str,
    objective: str = "Deliver tested feature",
    budget_policy: BudgetPolicy | None = None,
    check_expr: str = "from src.app import value; assert value() == 2",
) -> RunSpec:
    task = TaskSpec(
        task_id=f"{run_id}-t1",
        run_id=run_id,
        objective=objective,
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(
                check_id="chk_main",
                command=(sys.executable, "-c", check_expr),
            ),
        ),
        allowed_paths=("src/**",),
    )
    return RunSpec(
        run_id=run_id,
        project_id="proj-budget-pkg",
        objective=objective,
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        orchestration_mode="relay",
        budget_policy=budget_policy or BudgetPolicy(),
        idempotency_key=f"idem-{run_id}-0000000001",
        tasks=(task,),
    )


async def _seed_attempt(store: ExecutionStore, run_spec: RunSpec, attempt_id: str = "att-1", ordinal: int = 1) -> None:
    now = datetime.now(timezone.utc)
    attempt = TaskAttempt(
        attempt_id=attempt_id,
        task_id=run_spec.tasks[0].task_id,
        run_id=run_spec.run_id,
        ordinal=ordinal,
        executor_id="codex",
        provider="fixture",
        model="fixture-model",
        base_sha=run_spec.base_sha,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now - timedelta(seconds=2),
        finished_at=now,
        exit_reason="completed",
    )
    await store.save_attempt_atomic(attempt)


@pytest.mark.asyncio
async def test_budget_alert_80_freeze_100_and_restart(tmp_path: Path) -> None:
    repo, sha = _init_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "budget.sqlite")
    spec = _make_run_spec(
        repo,
        sha,
        run_id="run-budget-1",
        budget_policy=BudgetPolicy(max_usd=2.0, alert_threshold_pct=80.0, max_wall_seconds=1800),
    )
    await store.submit_run_idempotent(spec)
    await _seed_attempt(store, spec, "att-1", 1)

    metrics = MetricsService(store)
    governor = BudgetGovernor(store, metrics)
    now = datetime.now(timezone.utc)

    # 50% -> remains active
    await metrics.record_usage("run-budget-1", "att-1", source="provider:fixture", observed_at=now, cost_usd=1.0)
    st_50 = await governor.check("run-budget-1", now=now)
    assert st_50.status == "active"
    assert st_50.current_usd == pytest.approx(1.0)

    # 80% ($1.60 / $2.00) -> transitions active -> alerted and emits budget.alerted once
    await metrics.record_usage("run-budget-1", "att-1", source="provider:fixture", observed_at=now, cost_usd=1.60)
    st_80 = await governor.check("run-budget-1", now=now)
    assert st_80.status == "alerted"
    assert "usd" in st_80.triggered_dimensions
    st_80_again = await governor.check("run-budget-1", now=now)
    assert st_80_again.status == "alerted"

    events_after_alert = await store.get_events("run-budget-1")
    assert sum(e.event_type == "budget.alerted" for e in events_after_alert) == 1

    # 100% ($2.00 / $2.00) -> transitions alerted -> frozen, pauses run, blocks dispatch
    await metrics.record_usage("run-budget-1", "att-1", source="provider:fixture", observed_at=now, cost_usd=2.00)
    st_100 = await governor.check("run-budget-1", now=now)
    assert st_100.status == "frozen"
    assert "usd" in st_100.triggered_dimensions

    run_rec = await store.get_run("run-budget-1")
    assert run_rec is not None and run_rec["status"] == RunStatus.WAITING.value

    events_after_freeze = await store.get_events("run-budget-1")
    assert sum(e.event_type == "budget.frozen" for e in events_after_freeze) == 1
    assert any(
        e.event_type == "run.waiting" and e.redacted_payload.get("reason") == "budget_frozen"
        for e in events_after_freeze
    )

    # Restart simulation: fresh ExecutionStore + BudgetGovernor still blocks dispatch
    restarted_gov = BudgetGovernor(ExecutionStore(store.db_path))
    with pytest.raises(ContractViolation) as exc_info:
        await restarted_gov.assert_dispatchable("run-budget-1")
    assert exc_info.value.code == "budget_frozen"


@pytest.mark.asyncio
async def test_budget_extend_approve_resumes_and_deny_exhausts(tmp_path: Path) -> None:
    repo, sha = _init_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "extend.sqlite")
    metrics = MetricsService(store)
    governor = BudgetGovernor(store, metrics)
    now = datetime.now(timezone.utc)

    # Run A: frozen -> approved extension -> active + resumed
    spec_a = _make_run_spec(
        repo,
        sha,
        run_id="run-ext-approve",
        budget_policy=BudgetPolicy(max_usd=1.0, max_tokens_in=100, alert_threshold_pct=80.0),
    )
    await store.submit_run_idempotent(spec_a)
    await _seed_attempt(store, spec_a, "att-a1", 1)
    await metrics.record_usage(
        "run-ext-approve",
        "att-a1",
        source="provider:fixture",
        observed_at=now,
        tokens_in=100,
        tokens_out=20,
        cost_usd=1.0,
    )
    assert (await governor.check("run-ext-approve", now=now)).status == "frozen"

    ext = await governor.extend(
        "run-ext-approve",
        additional_usd=1.5,
        additional_tokens_in=200,
        approved=True,
        actor="operator",
        reason="Approved extra budget for tests",
    )
    assert ext.approved is True
    assert ext.previous_status == "frozen"
    assert ext.status == "active"
    assert ext.budget_status.max_usd == pytest.approx(2.5)
    assert ext.budget_status.max_tokens_in == 300
    assert (await store.get_run("run-ext-approve"))["status"] == RunStatus.RUNNING.value

    events_a = await store.get_events("run-ext-approve")
    assert any(e.event_type == "budget.extended" and e.redacted_payload.get("actor") == "operator" for e in events_a)
    assert any(e.event_type == "run.resumed" and e.redacted_payload.get("reason") == "budget_extended" for e in events_a)
    assert (await governor.assert_dispatchable("run-ext-approve", now=now)).status == "active"

    # Run B: frozen -> denied extension -> budget_exhausted, preserves evidence, blocks future work
    spec_b = _make_run_spec(
        repo,
        sha,
        run_id="run-ext-deny",
        budget_policy=BudgetPolicy(max_tokens_out=50, alert_threshold_pct=80.0),
    )
    await store.submit_run_idempotent(spec_b)
    await _seed_attempt(store, spec_b, "att-b1", 1)
    await metrics.record_usage(
        "run-ext-deny",
        "att-b1",
        source="provider:fixture",
        observed_at=now,
        tokens_in=10,
        tokens_out=50,
        cost_usd=0.25,
    )
    assert (await governor.check("run-ext-deny", now=now)).status == "frozen"

    denied = await governor.extend(
        "run-ext-deny",
        approved=False,
        actor="operator",
        reason="Too expensive",
    )
    assert denied.approved is False
    assert denied.previous_status == "frozen"
    assert denied.status == "exhausted"
    assert (await store.get_run("run-ext-deny"))["status"] == RunStatus.FAILED.value
    # Prior attempt evidence is preserved
    assert len(await store.list_attempts("run-ext-deny-t1")) == 1

    events_b = await store.get_events("run-ext-deny")
    assert any(e.event_type == "budget.exhausted" for e in events_b)
    assert any(
        e.event_type == "run.finished" and e.redacted_payload.get("reason") == "budget_exhausted"
        for e in events_b
    )

    with pytest.raises(ContractViolation) as exc_disp:
        await governor.assert_dispatchable("run-ext-deny", now=now)
    assert exc_disp.value.code == "budget_exhausted"

    with pytest.raises(ContractViolation) as exc_ext:
        await governor.extend("run-ext-deny", additional_tokens_out=100, approved=True, actor="op", reason="retry")
    assert exc_ext.value.code == "budget_exhausted"


@pytest.mark.asyncio
async def test_unknown_metrics_never_become_zero_and_never_false_freeze(tmp_path: Path) -> None:
    repo, sha = _init_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "unknown.sqlite")
    metrics = MetricsService(store)
    governor = BudgetGovernor(store, metrics)
    now = datetime.now(timezone.utc)

    # Even with max_usd=0.0, unknown telemetry must stay None and must NOT trigger freeze
    spec = _make_run_spec(
        repo,
        sha,
        run_id="run-unknown",
        budget_policy=BudgetPolicy(max_usd=0.0, max_tokens_in=0, max_tokens_out=0, max_wall_seconds=1),
    )
    await store.submit_run_idempotent(spec)
    await _seed_attempt(store, spec, "att-u1", 1)
    await metrics.record_usage("run-unknown", "att-u1", source="worker:not_reported", observed_at=now)

    status = await governor.check("run-unknown", now=now)
    assert status.status == "active"
    assert status.current_usd is None and status.usd_status == "unknown"
    assert status.current_tokens_in is None and status.tokens_in_status == "unknown"
    assert status.current_tokens_out is None and status.tokens_out_status == "unknown"
    assert status.current_wall_seconds is None and status.wall_seconds_status == "unknown"
    assert status.triggered_dimensions == ()

    events = await store.get_events("run-unknown")
    assert not any(e.event_type in {"budget.alerted", "budget.frozen"} for e in events)

    # Partial observation: att-u1 unknown, att-u2 observed $0.50 under $1.00 cap -> current_usd stays None, no false freeze
    await governor.configure("run-unknown", max_usd=1.0, max_tokens_in=None, max_tokens_out=None, max_wall_seconds=1800)
    await _seed_attempt(store, spec, "att-u2", 2)
    await metrics.record_usage("run-unknown", "att-u2", source="provider:fixture", observed_at=now, cost_usd=0.50)
    partial = await governor.check("run-unknown", now=now)
    assert partial.current_usd is None
    assert partial.usd_status == "unknown"
    assert partial.known_subtotal_usd == pytest.approx(0.50)
    assert partial.status == "active"

    # Explicit observed zero against a zero cap DOES freeze (proving observed 0 != unknown)
    spec_zero = _make_run_spec(
        repo,
        sha,
        run_id="run-observed-zero",
        budget_policy=BudgetPolicy(max_usd=0.0),
    )
    await store.submit_run_idempotent(spec_zero)
    await _seed_attempt(store, spec_zero, "att-z1", 1)
    await metrics.record_usage("run-observed-zero", "att-z1", source="provider:fixture", observed_at=now, cost_usd=0.0)
    assert (await governor.check("run-observed-zero", now=now)).status == "frozen"


@pytest.mark.asyncio
async def test_run_service_budget_gate_blocks_dispatch_and_allows_retry_after_extension(tmp_path: Path) -> None:
    repo, sha = _init_git_repo(tmp_path)
    service = RunService(repo_root=repo)
    spec = _make_run_spec(
        repo,
        sha,
        run_id="run-svc-budget",
        budget_policy=BudgetPolicy(max_usd=1.0, max_attempts=3, alert_threshold_pct=80.0),
    )
    await service.submit_run(spec)

    # First attempt fails acceptance check (still leaves value() == 1)
    fail_cmd = (
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('src/app.py').write_text('def value() -> int:\\n    return 99\\n', encoding='utf-8')",
    )
    out1 = await service.execute_task_attempt("run-svc-budget", "run-svc-budget-t1", custom_command=fail_cmd)
    assert out1.result.task_status == TaskStatus.FAILED

    # Record observed cost hitting 100% of cap
    metrics = MetricsService(service.store)
    await metrics.record_usage(
        "run-svc-budget",
        out1.attempt.attempt_id,
        source="provider:fixture",
        observed_at=datetime.now(timezone.utc),
        cost_usd=1.0,
    )

    # retry_task must be blocked with budget_frozen BEFORE creating attempt 2
    with pytest.raises(ContractViolation) as blocked:
        await service.retry_task("run-svc-budget", "run-svc-budget-t1", custom_command=fail_cmd)
    assert blocked.value.code == "budget_frozen"
    assert len(await service.store.list_attempts("run-svc-budget-t1")) == 1

    # get_run_detail reflects frozen status and observed current_usd
    detail_frozen = await service.get_run_detail("run-svc-budget")
    assert detail_frozen is not None
    assert detail_frozen["budget"]["status"] == "frozen"
    assert detail_frozen["budget"]["current_usd"] == pytest.approx(1.0)

    # Approve extension -> retry_task succeeds
    await service.budget_governor.extend(
        "run-svc-budget",
        additional_usd=2.0,
        approved=True,
        actor="operator",
        reason="Allow repair attempt",
    )
    fix_cmd = (
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('src/app.py').write_text('def value() -> int:\\n    return 2\\n', encoding='utf-8')",
    )
    out2 = await service.retry_task("run-svc-budget", "run-svc-budget-t1", custom_command=fix_cmd)
    assert out2.result.task_status == TaskStatus.READY_FOR_REVIEW
    assert len(await service.store.list_attempts("run-svc-budget-t1")) == 2


@pytest.mark.asyncio
async def test_pr_packager_full_description_redaction_and_gated_publish(tmp_path: Path) -> None:
    repo, sha = _init_git_repo(tmp_path, "main_repo")
    bare_remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", str(bare_remote))
    _git(repo, "remote", "add", "origin", str(bare_remote))

    service = RunService(repo_root=repo)
    snap_before = service.git_workspace.snapshot_operator_checkout()

    secret_literal = "SUPERSECRET-LITERAL-9876"
    objective = "Implement feature with token=sk-live-secret1234567890abcd and api_key=my_secret_key_val"
    spec = _make_run_spec(
        repo,
        sha,
        run_id="run-pr-pkg",
        objective=objective,
        budget_policy=BudgetPolicy(max_usd=5.0, max_tokens_in=10000, max_tokens_out=5000),
    )
    await service.submit_run(spec)

    worker_cmd = (
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('src/app.py').write_text('def value() -> int:\\n    return 2\\n', encoding='utf-8')",
    )
    outcome = await service.execute_task_attempt("run-pr-pkg", "run-pr-pkg-t1", custom_command=worker_cmd)
    assert outcome.result.task_status == TaskStatus.READY_FOR_REVIEW

    # Record observed usage metrics on the attempt
    metrics = MetricsService(service.store)
    await metrics.record_usage(
        "run-pr-pkg",
        outcome.attempt.attempt_id,
        source="provider:fixture",
        observed_at=datetime.now(timezone.utc),
        tokens_in=1200,
        tokens_out=450,
        cost_usd=0.42,
    )

    await service.review_task_result(
        "run-pr-pkg",
        outcome.result.result_id,
        actor="operator",
        decision="accepted",
        reason=f"Verified checks passed; Bearer tokensecret123 {secret_literal}",
        expected_revision=1,
    )
    int_outcome = await service.integrate_run("run-pr-pkg")
    assert int_outcome.result_sha is not None

    packager = PRPackager(service.store)
    with redaction_scope([secret_literal]):
        pkg = await packager.build("run-pr-pkg")
        exported = await packager.export(pkg.package_id, output_path=tmp_path / "exported_pr.md")

    # Operator working checkout must remain untouched
    service.git_workspace.assert_operator_checkout_intact(snap_before)

    # Branch pr/<run_id> exists locally pointing at integrated SHA
    assert pkg.pr_branch == "pr/run-pr-pkg"
    branch_sha = _git(repo, "rev-parse", f"refs/heads/{pkg.pr_branch}")
    assert branch_sha == int_outcome.result_sha

    # Description contains all required sections
    md = pkg.description_markdown
    assert "## Objective" in md
    assert "## Commits" in md
    assert "## Checks Summary" in md
    assert "## Diff Summary" in md
    assert "## Metrics (Provenance & Status)" in md
    assert "## Review Decisions" in md
    assert "chk_main" in md
    assert "src/app.py" in md
    assert "1200" in md and "0.42" in md
    assert "observed" in md
    assert "accepted" in md and "operator" in md

    # Redaction applied across DB, Markdown, Artifact on disk, Event, and Export
    for leak in ("sk-live-secret1234567890abcd", "my_secret_key_val", "tokensecret123", secret_literal):
        assert leak not in md
        assert leak not in exported.markdown
        assert leak not in json.dumps(pkg.review_decisions)
    assert REDACTED in md

    assert pkg.artifact_id is not None and pkg.artifact_path is not None and pkg.artifact_sha256 is not None
    artifact_disk = repo / pkg.artifact_path
    assert artifact_disk.exists()
    disk_bytes = artifact_disk.read_bytes()
    assert hashlib.sha256(disk_bytes).hexdigest() == pkg.artifact_sha256
    for leak in ("sk-live-secret1234567890abcd", "my_secret_key_val", "tokensecret123", secret_literal):
        assert leak.encode("utf-8") not in disk_bytes

    events = await service.store.get_events("run-pr-pkg")
    assert any(
        e.event_type == "pr_package.created" and e.redacted_payload.get("package_id") == pkg.package_id
        for e in events
    )

    # Duplicate build rejected
    with pytest.raises(ContractViolation) as dup_exc:
        await packager.build("run-pr-pkg")
    assert dup_exc.value.code == "pr_package_exists"

    # Publish MUST fail when unauthorized (default or explicit False or policy denied)
    with pytest.raises(ContractViolation) as unauth1:
        await packager.publish(pkg.package_id)
    assert unauth1.value.code == "publish_not_authorized"

    with pytest.raises(ContractViolation) as unauth2:
        await packager.publish(pkg.package_id, authorized=True, policy_authorized=False)
    assert unauth2.value.code == "publish_not_authorized"

    assert _git(bare_remote, "branch", "--list") == ""

    # Authorized publish with injected function
    captured: list[tuple[str, str]] = []
    res_fn = await packager.publish(
        pkg.package_id,
        authorized=True,
        remote="origin",
        push_fn=lambda *, remote, pr_branch, **_: captured.append((remote, pr_branch)),
    )
    assert res_fn.published is True
    assert captured == [("origin", "pr/run-pr-pkg")]

    # Authorized publish to local bare repository in tmp_path (hermetic, zero network)
    res_git = await packager.publish(pkg.package_id, authorized=True, remote="origin")
    assert res_git.published is True
    assert res_git.pushed_sha == int_outcome.result_sha
    remote_sha = _git(bare_remote, "rev-parse", f"refs/heads/{pkg.pr_branch}")
    assert remote_sha == int_outcome.result_sha

    # Tampered artifact detection on export
    artifact_disk.write_text("tampered", encoding="utf-8")
    with pytest.raises(ContractViolation) as tamper_exc:
        await packager.export(pkg.package_id)
    assert tamper_exc.value.code == "artifact_tampered"


@pytest.mark.asyncio
async def test_wall_seconds_stale_alerted_extend_and_pr_unknown_metrics(tmp_path: Path) -> None:
    repo, sha = _init_git_repo(tmp_path, "wall_repo")
    store = ExecutionStore(tmp_path / "wall.sqlite")
    metrics = MetricsService(store)
    governor = BudgetGovernor(store, metrics)
    now = datetime.now(timezone.utc)

    spec = _make_run_spec(
        repo,
        sha,
        run_id="run-wall-1",
        budget_policy=BudgetPolicy(max_usd=10.0, max_wall_seconds=10, alert_threshold_pct=80.0),
    )
    await store.submit_run_idempotent(spec)
    await _seed_attempt(store, spec, "att-w1", 1)

    # Record 8s duration (80% of 10s wall cap) and $5.00 USD (50%)
    await metrics.record_batch(
        (
            MetricSample(
                run_id="run-wall-1",
                scope="attempt",
                scope_id="att-w1",
                kind="duration",
                value=8.0,
                unit="seconds",
                source="local_calc:timestamps",
                observed_at=now,
                status="observed",
            ),
            MetricSample(
                run_id="run-wall-1",
                scope="attempt",
                scope_id="att-w1",
                kind="cost",
                value=5.0,
                unit="USD",
                source="provider:fixture",
                observed_at=now,
                status="observed",
            ),
        )
    )
    st_alert = await governor.check("run-wall-1", now=now)
    assert st_alert.status == "alerted"
    assert st_alert.triggered_dimensions == ("wall_seconds",)

    # Stale timestamp (+301s) preserves stale provenance and value
    st_stale = await governor.get_status("run-wall-1", now=now + timedelta(seconds=301))
    assert st_stale.usd_status == "stale"
    assert st_stale.wall_seconds_status == "stale"
    assert st_stale.current_usd == pytest.approx(5.0)

    # Extend directly from alerted -> active
    ext = await governor.extend(
        "run-wall-1",
        additional_wall_seconds=10,
        approved=True,
        actor="operator",
        reason="Add wall time",
    )
    assert ext.previous_status == "alerted"
    assert ext.status == "active"
    assert ext.budget_status.max_wall_seconds == 20

    # PRPackager with unknown tokens preserves 'unknown' and never fabricates 0
    packager = PRPackager(store, metrics)
    pkg = await packager.build("run-wall-1", create_git_branch=False)
    assert pkg.metrics["usage"]["tokens_in"]["value"] is None
    assert pkg.metrics["usage"]["tokens_in"]["status"] == "unknown"
    assert "`unknown` tokens (status=`unknown`" in pkg.description_markdown

