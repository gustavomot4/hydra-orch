"""Comprehensive tests for Task T30: Interactive Orchestration CLI / TUI Cockpit."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from hydra_orch import cli, server
from hydra_orch.config import HydraConfig
from hydra_orch.core.agent_registry import AgentRegistry
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.conflict_resolver import ConflictResolver
from hydra_orch.core.hitl import HITLService
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.packaging import PRPackager
from hydra_orch.core.route_selector import RouteSelector
from hydra_orch.core.run_service import RunService
from hydra_orch.model import CheckSpec, ContractViolation, RunSpec, TaskSpec
from hydra_orch.tui import (
    HttpRunBackend,
    HydraTuiCockpit,
    LocalRunBackend,
    compute_task_waves,
    format_quota_entry,
    parse_sse_events,
    resolve_api_token,
    run_cockpit,
    sanitize_api_url,
)


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip()


def _init_git_repo_with_remote(tmp_path: Path) -> Tuple[Path, Path, str, str]:
    """Create a real git repository with a bare 'origin' remote for integration and PR tests."""
    bare = tmp_path / "remote.git"
    bare.mkdir(parents=True, exist_ok=True)
    _git(bare, "init", "--bare")

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "hydra-tui@example.com")
    _git(repo, "config", "user.name", "Hydra TUI Test")
    if os.name == "nt":
        _git(repo, "config", "core.longpaths", "true")

    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "app.py").write_text("VALUE = 'initial'\nLINE2 = 'clean'\n", encoding="utf-8")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    default_branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "main"
    base_sha = _git(repo, "rev-parse", "--verify", "HEAD")

    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", default_branch)
    return repo, bare, base_sha, default_branch


def _make_run_service(tmp_path: Path, repo: Path) -> RunService:
    rt_dir = tmp_path / "orchestrator_rt"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    return RunService(repo_root=repo, store=store, runtime_dir=rt_dir)


def _ok_check(check_id: str = "unit-ok") -> CheckSpec:
    return CheckSpec(check_id=check_id, command=[sys.executable, "-c", "print('ok')"])


def _fail_check(check_id: str = "unit-fail", secret: Optional[str] = None) -> CheckSpec:
    msg = f"failure leak {secret}" if secret else "check failed"
    return CheckSpec(
        check_id=check_id,
        command=[sys.executable, "-c", f"import sys; print({msg!r}, file=sys.stderr); sys.exit(1)"],
    )


def _python_write_cmd(rel_path: str, content: str) -> List[str]:
    script = (
        "from pathlib import Path\n"
        f"p = Path({rel_path!r})\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_text({content!r}, encoding='utf-8')\n"
    )
    return [sys.executable, "-c", script]


class _FakeOmniRouteHandler(httpx.AsyncBaseTransport):
    """Mock OmniRoute transport returning controlled known and unknown quotas."""

    def __init__(self, *, available: bool = True, quota_payload: Optional[Dict[str, Any]] = None) -> None:
        self.available = available
        self.quota_payload = quota_payload or {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self.available:
            raise httpx.ConnectError("gateway offline", request=request)
        path = request.url.path
        if path in {"/health", "/v1/health"}:
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/usage/quota":
            return httpx.Response(200, json=self.quota_payload)
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "gpt-5.4", "owned_by": "openai"}]})
        if path == "/api/accounts":
            return httpx.Response(
                200,
                json={"accounts": [{"id": "acct-primary", "provider": "openai", "status": "ok"}]},
            )
        return httpx.Response(404, json={"error": "not_found"})


def test_tui_rendering_swarm_relay_persistent_redaction_and_unknown_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Swarm Wave 0/1, Relay/Persist modes, secret redaction, and unknown quota/cost formatting."""
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *args, **kwargs: HydraConfig())
    repo, _, base_sha, default_branch = _init_git_repo_with_remote(tmp_path)
    svc = _make_run_service(tmp_path, repo)

    secret_obj = "sk-live-secret-1234567890abcdef"
    secret_chk = "sk-test-token-abcdef123456"

    async def _setup() -> Tuple[str, str, str]:
        swarm_spec = RunSpec(
            run_id="run_tui_swarm_01",
            project_id="proj-tui",
            objective=f"Build Wave 0 & Wave 1 with token {secret_obj}",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="swarm",
            idempotency_key="tui-swarm-idem-0001",
            tasks=(
                TaskSpec(
                    task_id="t-core",
                    run_id="run_tui_swarm_01",
                    objective="Foundation module",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check("core-check"),),
                    allowed_paths=("src/**",),
                ),
                TaskSpec(
                    task_id="t-api",
                    run_id="run_tui_swarm_01",
                    objective="Worker depending on foundation",
                    assigned_executor="claude",
                    dependencies=("t-core",),
                    acceptance_criteria=(_fail_check("api-check", secret=secret_chk),),
                    allowed_paths=("src/**",),
                ),
            ),
        )
        await svc.submit_run(swarm_spec)
        core_out = await svc.execute_task_attempt(
            run_id=swarm_spec.run_id,
            task_id="t-core",
            model="gpt-5.4",
            provider="openai",
            custom_command=_python_write_cmd("src/core_mod.py", "CORE = 1\n"),
        )
        await svc.review_task_result(
            run_id=swarm_spec.run_id,
            result_id=core_out.result.result_id,
            actor="operator",
            decision="accepted",
            reason="Wave 0 foundation verified",
            expected_revision=core_out.result.revision,
        )
        await svc.execute_task_attempt(
            run_id=swarm_spec.run_id,
            task_id="t-api",
            model="claude-sonnet-4",
            provider="anthropic",
            custom_command=_python_write_cmd("src/api_mod.py", "API = 2\n"),
        )

        relay_spec = RunSpec(
            run_id="run_tui_relay_01",
            project_id="proj-tui",
            objective="Sequential relay verification",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="relay",
            idempotency_key="tui-relay-idem-0001",
            tasks=(
                TaskSpec(
                    task_id="r-1",
                    run_id="run_tui_relay_01",
                    objective="Step 1",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("*",),
                ),
                TaskSpec(
                    task_id="r-2",
                    run_id="run_tui_relay_01",
                    objective="Step 2",
                    assigned_executor="codex",
                    dependencies=("r-1",),
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("*",),
                ),
            ),
        )
        await svc.submit_run(relay_spec)

        persist_spec = RunSpec(
            run_id="run_tui_persist_01",
            project_id="proj-tui",
            objective="Persistent worker verification",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="persistent",
            idempotency_key="tui-persist-idem-01",
            tasks=(
                TaskSpec(
                    task_id="p-1",
                    run_id="run_tui_persist_01",
                    objective="Long-lived session",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("*",),
                ),
            ),
        )
        await svc.submit_run(persist_spec)
        return swarm_spec.run_id, relay_spec.run_id, persist_spec.run_id

    swarm_id, relay_id, persist_id = asyncio.run(_setup())

    assert format_quota_entry({"status": "unknown", "remaining_percent": None}) == "— (unknown)"
    assert format_quota_entry({"status": "ok", "remaining_percent": 65, "resets_in_seconds": 90}) == "65% (ok, reset 90s)"

    cockpit_swarm = HydraTuiCockpit(
        run_service=svc,
        omniroute_transport=_FakeOmniRouteHandler(available=False),
        run_id=swarm_id,
        once=True,
    )
    asyncio.run(cockpit_swarm.refresh())
    asyncio.run(cockpit_swarm.execute_command("inspect-checks t-api"))
    rendered_swarm = cockpit_swarm.render_text(width=240)

    assert "SWARM" in rendered_swarm
    assert "Wave 0" in rendered_swarm
    assert "Foundation" in rendered_swarm
    assert "Wave 1" in rendered_swarm
    assert "Parallel Workers" in rendered_swarm
    assert "t-core" in rendered_swarm
    assert "t-api" in rendered_swarm
    assert "codex" in rendered_swarm
    assert "gpt-5.4" in rendered_swarm
    assert "claude-sonnet-4" in rendered_swarm
    assert "pass" in rendered_swarm
    assert "fail" in rendered_swarm
    assert cockpit_swarm.state.snapshot is not None
    assert cockpit_swarm.state.snapshot["tasks"][0]["current_attempt"]["workspace_path"]
    assert "orchestrator_rt" in rendered_swarm

    # Unknown metrics & quotas MUST NEVER appear as 0%, 100%, or $0
    assert "— (unknown)" in rendered_swarm
    assert "Telemetry Cost: unknown" in rendered_swarm
    assert "0%" not in rendered_swarm
    assert "100%" not in rendered_swarm
    assert "$0" not in rendered_swarm

    # Secret strings MUST NEVER appear unredacted
    assert secret_obj not in rendered_swarm
    assert secret_chk not in rendered_swarm
    assert "[REDACTED]" in rendered_swarm

    # Relay mode rendering
    cockpit_relay = HydraTuiCockpit(run_service=svc, run_id=relay_id, once=True)
    asyncio.run(cockpit_relay.refresh())
    rendered_relay = cockpit_relay.render_text(width=240)
    assert "RELAY" in rendered_relay
    assert "Relay #1" in rendered_relay
    assert "Relay #2" in rendered_relay

    # Persistent mode rendering
    cockpit_persist = HydraTuiCockpit(run_service=svc, run_id=persist_id, once=True)
    asyncio.run(cockpit_persist.refresh())
    rendered_persist = cockpit_persist.render_text(width=240)
    assert "PERSISTENT" in rendered_persist
    assert "Persist #1" in rendered_persist

    waves = compute_task_waves(
        [
            {"task_id": "a", "dependencies": []},
            {"task_id": "b", "dependencies": ["a"]},
            {"task_id": "c", "dependencies": ["b"]},
        ],
        "swarm",
    )
    assert waves["a"] == (0, "Wave 0 (Foundation)")
    assert waves["b"] == (1, "Wave 1 (Worker)")
    assert waves["c"] == (2, "Wave 2 (Worker)")


def test_tui_incremental_event_replay_dedup_and_410_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify monotonic Last-Event-ID event deduplication, SSE parsing, and cursor_expired reset recovery."""
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *args, **kwargs: HydraConfig())
    repo, _, base_sha, default_branch = _init_git_repo_with_remote(tmp_path)
    svc = _make_run_service(tmp_path, repo)

    async def _create_run() -> str:
        spec = RunSpec(
            run_id="run_tui_events_01",
            project_id="proj-events",
            objective="Incremental replay test",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="relay",
            idempotency_key="tui-events-idem-001",
            tasks=(
                TaskSpec(
                    task_id="t-ev",
                    run_id="run_tui_events_01",
                    objective="Run step 1",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("*",),
                ),
                TaskSpec(
                    task_id="t-ev2",
                    run_id="run_tui_events_01",
                    objective="Run step 2",
                    assigned_executor="codex",
                    dependencies=("t-ev",),
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("*",),
                ),
            ),
        )
        await svc.submit_run(spec)
        await svc.execute_task_attempt(
            run_id=spec.run_id,
            task_id="t-ev",
            custom_command=_python_write_cmd("src/ev.py", "EV = 1\n"),
        )
        return spec.run_id

    run_id = asyncio.run(_create_run())

    cockpit = HydraTuiCockpit(run_service=svc, run_id=run_id, once=True)
    asyncio.run(cockpit.refresh())
    first_seq = cockpit.state.last_seq
    first_count = len(cockpit.state.events)
    assert first_seq > 0
    assert first_count > 0
    assert len({ev["seq"] for ev in cockpit.state.events}) == first_count

    # Second poll with no new events must NOT duplicate any event rows
    asyncio.run(cockpit.refresh())
    assert cockpit.state.last_seq == first_seq
    assert len(cockpit.state.events) == first_count

    # Emit a new HITL event -> third poll appends strictly new seq > first_seq
    asyncio.run(
        HITLService(svc.store).request(
            run_id,
            kind="needs_approval",
            question="Proceed to step 2?",
            idempotency_key="tui-hitl-evt-0001",
        )
    )
    asyncio.run(cockpit.refresh())
    assert cockpit.state.last_seq > first_seq
    assert len(cockpit.state.events) > first_count
    seqs = [ev["seq"] for ev in cockpit.state.events]
    assert seqs == sorted(set(seqs))

    # Simulate cursor_expired (reset_required=True once on stale cursor)
    inner_backend = cockpit.backend
    assert isinstance(inner_backend, LocalRunBackend)
    expired_once = {"triggered": False}
    orig_replay = inner_backend.replay_events

    async def _wrapped_replay(rid: str, *, after_seq: int = 0, limit: int = 200):
        if after_seq > 0 and not expired_once["triggered"]:
            expired_once["triggered"] = True
            return [], True
        return await orig_replay(rid, after_seq=after_seq, limit=limit)

    monkeypatch.setattr(inner_backend, "replay_events", _wrapped_replay)
    asyncio.run(cockpit.refresh())
    assert expired_once["triggered"] is True
    assert cockpit.state.last_seq >= first_seq
    assert len({ev["seq"] for ev in cockpit.state.events}) == len(cockpit.state.events)

    raw_sse = (
        ": keepalive\n\n"
        "id: 10\n"
        "event: heartbeat\n"
        "data: {}\n\n"
        "id: 11\n"
        "event: task_finished\n"
        'data: {"seq": 11, "run_id": "r1", "type": "task_finished", "token": "ghp_secret1234567890abcd"}\n\n'
    )
    parsed_sse = parse_sse_events(raw_sse)
    assert len(parsed_sse) == 1
    assert parsed_sse[0]["seq"] == 11
    assert parsed_sse[0]["event_type"] == "task_finished"
    assert "ghp_secret1234567890abcd" not in json.dumps(parsed_sse)


def test_tui_scripted_operator_flow_over_real_git_repo_and_run_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full end-to-end deterministic operator workflow: inspect -> route -> HITL -> review -> integrate -> PR."""
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *args, **kwargs: HydraConfig())
    repo, bare, base_sha, default_branch = _init_git_repo_with_remote(tmp_path)
    svc = _make_run_service(tmp_path, repo)

    async def _prepare_wave0() -> Tuple[str, str]:
        spec = RunSpec(
            run_id="run_tui_e2e_01",
            project_id="proj-e2e",
            objective="Implement base and dependent feature modules",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="swarm",
            idempotency_key="tui-e2e-idem-00001",
            tasks=(
                TaskSpec(
                    task_id="t-base",
                    run_id="run_tui_e2e_01",
                    objective="Create base module",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check("check-base"),),
                    allowed_paths=("src/**",),
                ),
                TaskSpec(
                    task_id="t-feature",
                    run_id="run_tui_e2e_01",
                    objective="Create feature module",
                    assigned_executor="claude",
                    dependencies=("t-base",),
                    acceptance_criteria=(_ok_check("check-feat"),),
                    allowed_paths=("src/**",),
                ),
            ),
        )
        await svc.submit_run(spec)
        await svc.execute_task_attempt(
            run_id=spec.run_id,
            task_id="t-base",
            model="gpt-5.4",
            provider="openai",
            custom_command=_python_write_cmd("src/base_mod.py", "BASE_READY = True\n"),
        )
        # Coordinator intervention checkpoint before Wave 1 dispatch
        hitl = await HITLService(svc.store).request(
            spec.run_id,
            kind="needs_approval",
            question="Confirm Wave 1 feature rollout?",
            idempotency_key="tui-hitl-e2e-0001",
        )
        return spec.run_id, hitl.request_id

    run_id, hitl_id = asyncio.run(_prepare_wave0())
    secret_override = "sk-forbidden-override-9876543210"

    phase1_cmds = [
        "runs",
        f"select-run {run_id}",
        "inspect-diff t-base",
        "inspect-checks t-base",
        "route-inventory",
        f"select-account openai {secret_override} {run_id}",
        f"select-account openai acct-prod-2 {run_id}",
        "hitl-list",
        f"hitl-reply {hitl_id} approved Verified Wave 0 gate",
        "review t-base accepted Wave 0 base passes",
    ]
    phase2_cmds = [
        "inspect-diff t-feature",
        "inspect-checks t-feature",
        "review t-feature accepted Wave 1 feature passes",
        "integrate",
        "pr-build",
        "pr-publish",
        "pr-publish --authorized",
        "unknown-command-xyz",
        "quit",
    ]

    cockpit = HydraTuiCockpit(
        run_service=svc,
        run_id=run_id,
        principal_id="tui-operator",
        no_alt_screen=True,
    )

    outcomes1: List[Tuple[str, bool, Optional[str]]] = []

    async def _drive_phase1() -> None:
        await cockpit.refresh()
        for cmd in phase1_cmds:
            out = await cockpit.execute_command(cmd)
            outcomes1.append((out.command, out.ok, out.error_code))

    asyncio.run(_drive_phase1())

    assert all(item[1] for item in outcomes1[:5])
    assert outcomes1[5] == ("select-account", False, "secret_in_account_override")
    assert all(item[1] for item in outcomes1[6:10])

    # Dispatch Wave 1 after HITL approval and Wave 0 acceptance
    asyncio.run(
        svc.execute_task_attempt(
            run_id=run_id,
            task_id="t-feature",
            model="claude-sonnet-4",
            provider="anthropic",
            custom_command=_python_write_cmd("src/feat_mod.py", "FEAT_READY = True\n"),
        )
    )

    outcomes2: List[Tuple[str, bool, Optional[str]]] = []
    outcomes2_data: List[Any] = []

    async def _drive_phase2() -> None:
        await cockpit.refresh()
        for cmd in phase2_cmds:
            out = await cockpit.execute_command(cmd)
            outcomes2.append((out.command, out.ok, out.error_code))
            outcomes2_data.append(out.data)
            if out.should_quit:
                break

    asyncio.run(_drive_phase2())

    # 0 inspect-diff, 1 inspect-checks, 2 review feature, 3 integrate, 4 pr-build
    assert all(item[1] for item in outcomes2[:5])
    # 5 unauthorized pr-publish blocked cleanly
    assert outcomes2[5] == ("pr-publish", False, "publish_not_authorized")
    # 6 authorized pr-publish succeeds
    assert outcomes2[6][1] is True
    assert outcomes2_data[6]["published"] is True
    assert outcomes2_data[6]["remote"] == "origin"
    # 7 unknown command captured in error banner without crash
    assert outcomes2[7] == ("unknown-command-xyz", False, "unknown_command")
    # 8 quit exits cleanly
    assert outcomes2[8][1] is True

    async def _verify_store() -> None:
        detail = await svc.get_run_detail(run_id)
        assert detail is not None
        assert detail["status"] == "succeeded"
        assert {t["task_id"]: t["status"] for t in detail["tasks"]} == {
            "t-base": "accepted",
            "t-feature": "accepted",
        }
        hitl_final = await HITLService(svc.store).get_request(run_id, hitl_id)
        assert hitl_final.state == "answered"
        assert hitl_final.actor == "tui-operator"

        rs = RouteSelector(svc.store, AgentRegistry(svc.store), MetricsService(svc.store))
        overrides = await rs.get_next_account_overrides(run_id)
        assert overrides["openai"]["account_id"] == "acct-prod-2"
        assert overrides["openai"]["applies_to"] == "next_run"

        pkg = await PRPackager(svc.store).get_package(run_id)
        assert pkg is not None
        assert pkg.head_sha
        assert pkg.pr_branch in _git(bare, "branch", "--list", pkg.pr_branch)

    asyncio.run(_verify_store())
    final_render = cockpit.render_text(width=200)
    assert secret_override not in final_render


def test_tui_needs_repair_review_and_conflict_manual_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify review 'needs_repair' mapping plus conflict-list / conflict-manual / conflict-manual --finalize."""
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *args, **kwargs: HydraConfig())
    repo, _, base_sha, default_branch = _init_git_repo_with_remote(tmp_path)
    svc = _make_run_service(tmp_path, repo)

    async def _setup_conflict_run() -> str:
        spec = RunSpec(
            run_id="run_tui_cfl_01",
            project_id="proj-cfl",
            objective="Two parallel tasks editing same line trigger merge conflict",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="swarm",
            idempotency_key="tui-cfl-idem-00001",
            tasks=(
                TaskSpec(
                    task_id="t-left",
                    run_id="run_tui_cfl_01",
                    objective="Modify shared app.py left",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("src/**",),
                ),
                TaskSpec(
                    task_id="t-right",
                    run_id="run_tui_cfl_01",
                    objective="Modify shared app.py right",
                    assigned_executor="claude",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("src/**",),
                ),
            ),
        )
        await svc.submit_run(spec)
        await svc.execute_task_attempt(
            run_id=spec.run_id,
            task_id="t-left",
            custom_command=_python_write_cmd("src/app.py", "VALUE = 'left'\nLINE2 = 'clean'\n"),
        )
        await svc.execute_task_attempt(
            run_id=spec.run_id,
            task_id="t-right",
            custom_command=_python_write_cmd("src/app.py", "VALUE = 'right'\nLINE2 = 'clean'\n"),
        )
        return spec.run_id

    run_id = asyncio.run(_setup_conflict_run())
    cockpit = HydraTuiCockpit(run_service=svc, run_id=run_id, once=True)

    async def _exercise() -> None:
        await cockpit.refresh()

        rep_out = await cockpit.execute_command("review t-left needs_repair Missing type hint")
        assert rep_out.ok is True
        assert rep_out.data["decision"] == "rejected"
        assert rep_out.data["requested_decision"] == "needs_repair"

        await svc.execute_task_attempt(
            run_id=run_id,
            task_id="t-left",
            allow_retry_from_terminal=True,
            custom_command=_python_write_cmd("src/app.py", "VALUE = 'left'\nLINE2 = 'clean'\n"),
        )
        assert (await cockpit.execute_command("review t-left accepted Fixed")).ok is True
        assert (await cockpit.execute_command("review t-right accepted Ready")).ok is True

        integ_out = await cockpit.execute_command("integrate")
        assert integ_out.ok is False
        assert integ_out.error_code == "merge_conflict"

        # Generate ConflictReport from the conflicted integration, then resolve manually in cockpit
        report = await ConflictResolver(svc.store).analyze(integ_out.data["integration_id"])

        cfl_list = await cockpit.execute_command("conflict-list")
        assert cfl_list.ok is True
        assert len(cfl_list.data) >= 1
        assert cfl_list.data[0]["conflict_id"] == report.conflict_id

        auto_out = await cockpit.execute_command(f"conflict-auto {report.conflict_id} --max-repair-attempts 1")
        assert auto_out.ok is True
        assert auto_out.data["conflict_id"] == report.conflict_id

        manual_open = await cockpit.execute_command(f"conflict-manual {report.conflict_id}")
        assert manual_open.ok is True
        wt_path = Path(manual_open.data["repair_worktree_path"])
        assert wt_path.exists()
        (wt_path / "src" / "app.py").write_text("VALUE = 'merged_both'\nLINE2 = 'clean'\n", encoding="utf-8")

        manual_done = await cockpit.execute_command(f"conflict-manual {report.conflict_id} --finalize")
        assert manual_done.ok is True
        assert manual_done.data["status"] == "manual"
        assert manual_done.data["repaired"] is True
        assert manual_done.data["resolved_sha"]

    asyncio.run(_exercise())


def test_tui_http_sse_mode_with_bearer_auth_and_url_security(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify REST + SSE HTTP mode over FastAPI ASGI app with Bearer auth never leaking tokens."""
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *args, **kwargs: HydraConfig())
    repo, _, base_sha, default_branch = _init_git_repo_with_remote(tmp_path)
    svc = _make_run_service(tmp_path, repo)

    secret_token = "hydra-test-bearer-secret-9876543210"

    with pytest.raises(ContractViolation) as bad_url:
        sanitize_api_url("https://user:pass@localhost:8000")
    assert bad_url.value.code == "invalid_api_url"
    with pytest.raises(ContractViolation):
        sanitize_api_url("ftp://localhost:8000")
    assert sanitize_api_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"

    monkeypatch.setenv("HYDRA_TEST_TUI_TOKEN", secret_token)
    assert resolve_api_token(api_token_env="HYDRA_TEST_TUI_TOKEN") == secret_token
    assert resolve_api_token(api_token_env="MISSING_ENV", interactive=True, prompt_fn=lambda _: "  p-tok ") == "p-tok"

    async def _prep() -> str:
        spec = RunSpec(
            run_id="run_tui_http_01",
            project_id="proj-http",
            objective=f"HTTP cockpit smoke test token={secret_token}",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="swarm",
            idempotency_key="tui-http-idem-0001",
            tasks=(
                TaskSpec(
                    task_id="t-http",
                    run_id="run_tui_http_01",
                    objective="Update app",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("src/**",),
                ),
            ),
        )
        await svc.submit_run(spec)
        await svc.execute_task_attempt(
            run_id=spec.run_id,
            task_id="t-http",
            custom_command=_python_write_cmd("src/http_mod.py", "HTTP_OK = True\n"),
        )
        return spec.run_id

    run_id = asyncio.run(_prep())

    class _ExactVerifier:
        def verify(self, token: str) -> bool:
            return hmac.compare_digest(token, secret_token)

    orig_verifier = server.app.state.token_verifier
    orig_pr_dir = getattr(server.app.state, "pr_package_runtime_dir", None)
    server.set_run_service(svc)
    server.app.state.token_verifier = _ExactVerifier()
    server.app.state.pr_package_runtime_dir = str(svc.runtime_dir)

    try:
        transport = httpx.ASGITransport(app=server.app)
        buf = Console(width=160, force_terminal=False, color_system=None)
        with buf.capture() as cap:
            state = run_cockpit(
                api_url="http://testserver",
                api_token_env="HYDRA_TEST_TUI_TOKEN",
                http_transport=transport,
                run_id=run_id,
                console=buf,
                no_alt_screen=True,
                command_queue=[
                    "refresh",
                    "route-inventory",
                    "inspect-diff t-http",
                    "inspect-checks t-http",
                    "review t-http accepted HTTP review pass",
                    "integrate",
                    "pr-build",
                    "quit",
                ],
            )
        captured_output = cap.get()
        assert state.connection_mode == "http"
        assert state.active_run_id == run_id
        assert state.last_seq > 0
        assert state.snapshot is not None
        assert state.snapshot["status"] == "succeeded"
        assert state.pr_package is not None
        assert secret_token not in captured_output
        assert "[REDACTED]" in captured_output

        async def _test_http_410() -> None:
            backend = HttpRunBackend("http://testserver", api_token=secret_token, transport=transport)
            cockpit_http = HydraTuiCockpit(backend=backend, run_id=run_id, once=True)
            await cockpit_http.refresh()
            assert cockpit_http.state.last_seq > 0
            server.app.state.expired_cursors[run_id] = 999
            await cockpit_http.refresh()
            server.app.state.expired_cursors.pop(run_id, None)
            await backend.aclose()

        asyncio.run(_test_http_410())
    finally:
        server.app.state.expired_cursors.pop(run_id, None)
        server.app.state.token_verifier = orig_verifier
        server.app.state.pr_package_runtime_dir = orig_pr_dir
        server.set_run_service(None)


def test_cli_watch_and_ui_help_once_script_and_subcommands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify hydra --help, watch, ui, --once, --script, and preservation of all existing commands/groups."""
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *args, **kwargs: HydraConfig())
    runner = CliRunner()

    help_root = runner.invoke(cli.app, ["--help"])
    assert help_root.exit_code == 0
    for expected_cmd in [
        "serve",
        "run",
        "submit",
        "inspect",
        "review",
        "integrate",
        "cancel",
        "retry",
        "status",
        "quota",
        "project-create",
        "project-list",
        "runs",
        "area",
        "workspace",
        "project",
        "repo",
        "agent",
        "profile",
        "session",
        "metrics",
        "consent",
        "memory",
        "discovery",
        "skill",
        "mcp",
        "secret",
        "extension",
        "preference",
        "transport",
        "token",
        "conflict",
        "budget",
        "pr-package",
        "route",
        "automation",
        "watch",
        "ui",
    ]:
        assert expected_cmd in help_root.output

    help_watch = runner.invoke(cli.app, ["watch", "--help"])
    assert help_watch.exit_code == 0
    for flag in ["--run-id", "--api-url", "--refresh-seconds", "--once", "--script", "--no-alt-screen"]:
        assert flag in help_watch.output

    help_ui = runner.invoke(cli.app, ["ui", "--help"])
    assert help_ui.exit_code == 0
    for flag in ["--run-id", "--api-url", "--refresh-seconds", "--once", "--script", "--no-alt-screen"]:
        assert flag in help_ui.output

    repo, _, base_sha, default_branch = _init_git_repo_with_remote(tmp_path)
    svc = _make_run_service(tmp_path, repo)

    async def _prep() -> str:
        spec = RunSpec(
            run_id="run_tui_cli_01",
            project_id="proj-cli-tui",
            objective="CLI watch and ui verification",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch=default_branch,
            orchestration_mode="swarm",
            idempotency_key="tui-cli-idem-00001",
            tasks=(
                TaskSpec(
                    task_id="t-cli",
                    run_id="run_tui_cli_01",
                    objective="Write cli file",
                    assigned_executor="codex",
                    acceptance_criteria=(_ok_check(),),
                    allowed_paths=("src/**",),
                ),
            ),
        )
        await svc.submit_run(spec)
        return spec.run_id

    run_id = asyncio.run(_prep())

    server.set_run_service(svc)
    try:
        res_watch = runner.invoke(cli.app, ["watch", "--once", "--no-alt-screen", "--run-id", run_id])
        assert res_watch.exit_code == 0
        assert run_id in res_watch.output
        assert "proj-cli-tui" in res_watch.output

        res_ui = runner.invoke(cli.app, ["ui", "--once", "--no-alt-screen", "--run-id", run_id])
        assert res_ui.exit_code == 0
        assert run_id in res_ui.output

        script_file = tmp_path / "cockpit_commands.txt"
        script_file.write_text(
            "# Deterministic TUI script\n"
            "runs\n"
            "route-inventory\n"
            "help\n"
            "quit\n",
            encoding="utf-8",
        )
        res_script = runner.invoke(
            cli.app,
            ["watch", "--run-id", run_id, "--script", str(script_file), "--no-alt-screen"],
        )
        assert res_script.exit_code == 0
        assert "Cockpit exited cleanly" in res_script.output

        res_bad_url = runner.invoke(
            cli.app,
            ["watch", "--once", "--api-url", "http://alice:supersecret999@127.0.0.1:8000"],
        )
        assert res_bad_url.exit_code == 1
        assert "invalid_api_url" in res_bad_url.output
        assert "supersecret999" not in res_bad_url.output
    finally:
        server.set_run_service(None)
