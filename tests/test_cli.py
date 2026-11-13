"""Offline CLI checks for configuration policy and M1 Control Plane commands (T01 / T07)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Tuple

import httpx
import pytest
from typer.testing import CliRunner

from hydra_orch import cli
from hydra_orch.config import HydraConfig
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.run_service import RunService
from hydra_orch.server import set_run_service


def _init_temp_git_repo(base_dir: Path) -> Tuple[Path, str]:
    repo = base_dir / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "cli@hydra.local"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra CLI Test"], cwd=repo, check=True, capture_output=True)
    if os.name == "nt":
        subprocess.run(["git", "config", "core.longpaths", "true"], cwd=repo, check=True, capture_output=True)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "greeter.py").write_text("def greet() -> str:\n    return 'hi'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, sha


@pytest.fixture
def cli_run_service(tmp_path: Path):
    repo, base_sha = _init_temp_git_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    set_run_service(svc)
    try:
        yield svc, repo, base_sha
    finally:
        set_run_service(None)


def test_missing_inference_route_returns_nonzero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: HydraConfig())
    result = CliRunner().invoke(cli.app, ["run", "test", "--mode", "relay"])
    assert result.exit_code == 1
    assert "provider_unavailable" in result.output


def test_disabled_quota_displays_unknown_without_network(monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda: HydraConfig())

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled gateway cannot make HTTP calls")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    result = CliRunner().invoke(cli.app, ["quota"])
    assert result.exit_code == 0
    assert "unknown" in result.output
    assert "100%" not in result.output


def test_cli_submit_inspect_review_integrate_same_service(cli_run_service, tmp_path: Path):
    svc, repo, base_sha = cli_run_service
    runner = CliRunner()
    out_file = tmp_path / "submit_out.json"

    # 1. Submit run via CLI with --json and --output
    sub_res = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Update greeter to return hello hydra",
            "--project-id",
            "proj-cli",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--task-id",
            "t-greet",
            "--check-cmd",
            sys.executable,
            "--check-cmd",
            "-c",
            "--check-cmd",
            "from src.greeter import greet; assert greet() == 'hello hydra'",
            "--idempotency-key",
            "cli-idem-greet-001",
            "--json",
            "--output",
            str(out_file),
        ],
    )
    assert sub_res.exit_code == 0
    assert out_file.exists()
    sub_data = json.loads(sub_res.stdout)
    run_id = sub_data["run_id"]
    assert sub_data["created"] is True

    # 2. Execute attempt via shared RunService (modifying src/greeter.py in isolated worktree)
    worker_py = (
        "from pathlib import Path\n"
        "Path('src/greeter.py').write_text(\"def greet() -> str:\\n    return 'hello hydra'\\n\", encoding='utf-8')\n"
    )
    asyncio.run(
        svc.execute_task_attempt(
            run_id=run_id,
            task_id="t-greet",
            custom_command=[sys.executable, "-c", worker_py],
        )
    )

    # 3. Inspect run via CLI
    insp_res = runner.invoke(cli.app, ["inspect", run_id, "--json"])
    assert insp_res.exit_code == 0
    insp_data = json.loads(insp_res.stdout)
    assert insp_data["status"] == "reviewing"
    assert insp_data["tasks"][0]["status"] == "ready_for_review"

    # 4. Review with stale expected_revision -> exit_code == 3
    bad_rev = runner.invoke(
        cli.app,
        [
            "review",
            run_id,
            "t-greet",
            "--decision",
            "accepted",
            "--reason",
            "stale rev",
            "--expected-revision",
            "99",
            "--json",
        ],
    )
    assert bad_rev.exit_code == 3
    assert json.loads(bad_rev.stdout)["code"] == "optimistic_lock_conflict"

    # 5. Review with valid expected_revision -> exit_code == 0
    ok_rev = runner.invoke(
        cli.app,
        [
            "review",
            run_id,
            "t-greet",
            "--decision",
            "accepted",
            "--reason",
            "Verified greeting output",
            "--expected-revision",
            "1",
            "--json",
        ],
    )
    assert ok_rev.exit_code == 0
    assert json.loads(ok_rev.stdout)["task_status"] == "accepted"

    # 6. Integrate via CLI -> exit_code == 0
    int_res = runner.invoke(cli.app, ["integrate", run_id, "--json"])
    assert int_res.exit_code == 0
    int_data = json.loads(int_res.stdout)
    assert int_data["status"] == "integrated"
    assert int_data["target_branch"] == f"integrate/{run_id}"
    assert int_data["result_sha"] is not None


def test_cli_idempotency_conflict_and_cancel_exit_codes(cli_run_service):
    svc, repo, base_sha = cli_run_service
    runner = CliRunner()

    r1 = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Original CLI objective",
            "--project-id",
            "proj-cli-2",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--idempotency-key",
            "cli-idem-conflict-01",
            "--json",
        ],
    )
    assert r1.exit_code == 0
    run_id = json.loads(r1.stdout)["run_id"]

    # Reusing key with different objective -> exit_code == 3
    r_conflict = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Different CLI objective with same key",
            "--project-id",
            "proj-cli-2",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--idempotency-key",
            "cli-idem-conflict-01",
            "--json",
        ],
    )
    assert r_conflict.exit_code == 3
    assert json.loads(r_conflict.stdout)["code"] == "idempotency_conflict"

    # Cancel run -> exit_code == 0
    c1 = runner.invoke(cli.app, ["cancel", run_id, "--json"])
    assert c1.exit_code == 0
    assert json.loads(c1.stdout)["status"] == "cancelled"

    # Cancel already cancelled run -> exit_code == 3
    c2 = runner.invoke(cli.app, ["cancel", run_id, "--json"])
    assert c2.exit_code == 3
    assert json.loads(c2.stdout)["code"] == "invalid_run_state"


runner = CliRunner()


def test_cli_help_and_m1_project_and_runs_commands(cli_run_service, tmp_path: Path):
    svc, repo, base_sha = cli_run_service
    groups = [
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
    ]
    root_help = runner.invoke(cli.app, ["--help"])
    assert root_help.exit_code == 0
    for grp in groups:
        assert grp in root_help.stdout
        res = runner.invoke(cli.app, [grp, "--help"])
        assert res.exit_code == 0, f"{grp} --help failed: {res.stdout}"

    out_file = tmp_path / "m1-project.json"
    p_create = runner.invoke(
        cli.app,
        [
            "project-create",
            "--root",
            str(repo),
            "--name",
            "m1-cli-proj",
            "--base-branch",
            "main",
            "--base-sha",
            base_sha,
            "--project-id",
            "proj-m1-cli",
            "--json",
            "--output",
            str(out_file),
        ],
    )
    assert p_create.exit_code == 0, p_create.stdout
    assert json.loads(out_file.read_text(encoding="utf-8"))["id"] == "proj-m1-cli"

    p_list = runner.invoke(cli.app, ["project-list", "--json"])
    assert p_list.exit_code == 0
    assert any(p["id"] == "proj-m1-cli" for p in json.loads(p_list.stdout))

    sub = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Verify M1 runs listing",
            "--project-id",
            "proj-m1-cli",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--json",
        ],
    )
    assert sub.exit_code == 0

    runs_res = runner.invoke(cli.app, ["runs", "--project-id", "proj-m1-cli", "--json"])
    assert runs_res.exit_code == 0
    assert json.loads(runs_res.stdout)["total"] >= 1


def test_cli_area_workspace_project_repo_and_traversal_exit_1(cli_run_service, tmp_path: Path):
    svc, repo, base_sha = cli_run_service

    r_area = runner.invoke(
        cli.app,
        ["area", "create", "--name", "eng", "--principal-id", "op-1", "--json"],
    )
    assert r_area.exit_code == 0, r_area.stdout
    area_id = json.loads(r_area.stdout)["id"]

    assert len(json.loads(runner.invoke(cli.app, ["area", "list", "--principal-id", "op-1", "--json"]).stdout)) == 1

    r_ws = runner.invoke(
        cli.app,
        ["workspace", "create", "--area-id", area_id, "--name", "core", "--principal-id", "op-1", "--json"],
    )
    assert r_ws.exit_code == 0, r_ws.stdout
    ws_id = json.loads(r_ws.stdout)["id"]
    assert len(json.loads(runner.invoke(cli.app, ["workspace", "list", "--area-id", area_id, "--principal-id", "op-1", "--json"]).stdout)) == 1

    r_proj = runner.invoke(
        cli.app,
        [
            "project",
            "create",
            "--workspace-id",
            ws_id,
            "--name",
            "scoped-proj",
            "--root",
            str(repo),
            "--base-sha",
            base_sha,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert r_proj.exit_code == 0, r_proj.stdout
    project_id = json.loads(r_proj.stdout)["id"]
    assert len(json.loads(runner.invoke(cli.app, ["project", "list", "--workspace-id", ws_id, "--principal-id", "op-1", "--json"]).stdout)) == 1

    # Register legacy project inside allowed root and adopt it into workspace
    legacy_repo, _ = _init_temp_git_repo(repo / "_legacy_adopt")
    leg = runner.invoke(
        cli.app,
        ["project-create", "--root", str(legacy_repo), "--name", "legacy-p", "--project-id", "leg-1", "--json"],
    )
    assert leg.exit_code == 0, leg.stdout
    adopt = runner.invoke(
        cli.app,
        [
            "project",
            "adopt",
            "leg-1",
            "--workspace-id",
            ws_id,
            "--expected-revision",
            "1",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert adopt.exit_code == 0, adopt.stdout
    assert json.loads(adopt.stdout)["workspace_id"] == ws_id

    # Repo register + traversal check -> exit_code == 1
    outside = tmp_path / "outside-secret-dir"
    outside.mkdir()
    r_trav = runner.invoke(
        cli.app,
        [
            "repo",
            "register",
            "--project-id",
            project_id,
            "--root",
            str(outside),
            "--allowed-paths",
            "README.md",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert r_trav.exit_code == 1

    r_repo = runner.invoke(
        cli.app,
        [
            "repo",
            "register",
            "--project-id",
            project_id,
            "--root",
            str(repo),
            "--allowed-paths",
            "README.md",
            "--base-sha",
            base_sha,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert r_repo.exit_code == 0, r_repo.stdout
    repo_id = json.loads(r_repo.stdout)["id"]
    assert len(json.loads(runner.invoke(cli.app, ["repo", "list", "--project-id", project_id, "--principal-id", "op-1", "--json"]).stdout)) == 1

    r_grant = runner.invoke(
        cli.app,
        [
            "repo",
            "grant",
            repo_id,
            "--authorized-principal",
            "op-2",
            "--scopes",
            "read",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert r_grant.exit_code == 0, r_grant.stdout
    auth_id = json.loads(r_grant.stdout)["authorization_id"]

    r_rev = runner.invoke(cli.app, ["repo", "revoke", auth_id, "--principal-id", "op-1", "--json"])
    assert r_rev.exit_code == 0
    assert json.loads(r_rev.stdout)["revoked"] is True

    # Archive workspace -> exit 0, stale revision -> exit 3
    arch_bad = runner.invoke(
        cli.app,
        ["workspace", "archive", ws_id, "--expected-revision", "99", "--principal-id", "op-1", "--json"],
    )
    assert arch_bad.exit_code == 3
    arch_ok = runner.invoke(
        cli.app,
        ["workspace", "archive", ws_id, "--expected-revision", "1", "--principal-id", "op-1", "--json"],
    )
    assert arch_ok.exit_code == 0


def test_cli_agent_profile_session_and_metrics(cli_run_service, tmp_path: Path, monkeypatch):
    import hashlib
    import platform
    from datetime import datetime, timezone
    from hydra_orch.core.agent_registry import AgentRegistry

    svc, repo, base_sha = cli_run_service

    # Setup area -> workspace -> project -> repo
    area_id = json.loads(runner.invoke(cli.app, ["area", "create", "--name", "a1", "--principal-id", "op-1", "--json"]).stdout)["id"]
    ws_id = json.loads(runner.invoke(cli.app, ["workspace", "create", "--area-id", area_id, "--name", "w1", "--principal-id", "op-1", "--json"]).stdout)["id"]
    proj_id = json.loads(
        runner.invoke(
            cli.app,
            ["project", "create", "--workspace-id", ws_id, "--name", "p1", "--root", str(repo), "--base-sha", base_sha, "--principal-id", "op-1", "--json"],
        ).stdout
    )["id"]
    repo_reg = runner.invoke(
        cli.app,
        ["repo", "register", "--project-id", proj_id, "--root", str(repo), "--scopes", "read,write,execute", "--allowed-paths", "README.md", "--base-sha", base_sha, "--principal-id", "op-1", "--json"],
    )
    assert repo_reg.exit_code == 0, repo_reg.stdout
    repo_id = json.loads(repo_reg.stdout)["id"]

    # Fake executable and certification report inside default certification root
    fake_exe = tmp_path / "fake-codex.exe"
    fake_exe.write_bytes(b"codex-binary-v1")
    exe_sha = hashlib.sha256(fake_exe.read_bytes()).hexdigest()
    monkeypatch.setattr("shutil.which", lambda _name: str(fake_exe))

    ag = runner.invoke(
        cli.app,
        [
            "agent",
            "register",
            "--name",
            "codex-local",
            "--version",
            "1.0.0",
            "--driver-type",
            "codex",
            "--capabilities",
            "workspace_execution,cancel_process_tree",
            "--json",
        ],
    )
    assert ag.exit_code == 0, ag.stdout
    agent_id = json.loads(ag.stdout)["agent_id"]
    assert len(json.loads(runner.invoke(cli.app, ["agent", "list", "--json"]).stdout)) == 1

    cert_dir = Path(svc.store.db_path).parent / "certification"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_report = cert_dir / "agent-cert.json"
    cert_report.write_text(
        json.dumps(
            {
                "agent_id": agent_id,
                "driver_type": "codex",
                "agent_version": "1.0.0",
                "platform": platform.system(),
                "executable_sha256": exe_sha,
                "capabilities": ["workspace_execution", "cancel_process_tree"],
                "passed_checks": ["cwd", "scope", "timeout", "cancel_process_tree", "artifact_hash"],
                "simulated": False,
                "issued_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    cert_res = runner.invoke(
        cli.app,
        ["agent", "certify", agent_id, "--report", str(cert_report), "--principal-id", "op-1", "--json"],
    )
    assert cert_res.exit_code == 0, cert_res.stdout

    resolved = runner.invoke(
        cli.app,
        ["agent", "resolve", agent_id, "--required", "workspace_execution", "--json"],
    )
    assert resolved.exit_code == 0, resolved.stdout

    # Profile create, get, resolve, snapshot
    prof = runner.invoke(
        cli.app,
        [
            "profile",
            "create",
            "--name",
            "default-prof",
            "--agent-ref",
            agent_id,
            "--executor-ref",
            agent_id,
            "--model-ref",
            "gpt-5-codex",
            "--required-capabilities",
            "workspace_execution",
            "--json",
        ],
    )
    assert prof.exit_code == 0, prof.stdout
    profile_id = json.loads(prof.stdout)["profile_id"]
    assert runner.invoke(cli.app, ["profile", "get", profile_id, "--json"]).exit_code == 0
    assert runner.invoke(
        cli.app,
        ["profile", "resolve", profile_id, "--repository-id", repo_id, "--principal-id", "op-1", "--json"],
    ).exit_code == 0

    run_id = json.loads(
        runner.invoke(
            cli.app,
            ["submit", "--objective", "Session & profile run", "--project-id", proj_id, "--repo-root", str(repo), "--base-sha", base_sha, "--json"],
        ).stdout
    )["run_id"]

    snap = runner.invoke(
        cli.app,
        ["profile", "snapshot", profile_id, "--run-id", run_id, "--repository-id", repo_id, "--principal-id", "op-1", "--json"],
    )
    assert snap.exit_code == 0, snap.stdout

    # Revoke agent cert
    rev_cert = runner.invoke(
        cli.app,
        ["agent", "revoke-cert", agent_id, "--platform", platform.system(), "--principal-id", "op-1", "--json"],
    )
    assert rev_cert.exit_code == 0

    # Session create, list, threads, transition & conflict (exit 3)
    sess_res = runner.invoke(cli.app, ["session", "create", run_id, "--agent-ref", agent_id, "--json"])
    assert sess_res.exit_code == 0, sess_res.stdout
    sess_id = json.loads(sess_res.stdout)["id"]
    assert len(json.loads(runner.invoke(cli.app, ["session", "list", run_id, "--json"]).stdout)) == 1

    tr_bad = runner.invoke(
        cli.app,
        ["session", "transition", run_id, sess_id, "--target", "running", "--expected-state", "completed", "--json"],
    )
    assert tr_bad.exit_code == 3

    tr_ok = runner.invoke(
        cli.app,
        ["session", "transition", run_id, sess_id, "--target", "running", "--expected-state", "created", "--json"],
    )
    assert tr_ok.exit_code == 0, tr_ok.stdout

    th_create = runner.invoke(cli.app, ["session", "threads", run_id, sess_id, "--create", "--json"])
    assert th_create.exit_code == 0, th_create.stdout
    assert len(json.loads(runner.invoke(cli.app, ["session", "threads", run_id, sess_id, "--json"]).stdout)) == 1

    # Metrics query & usage
    m_q = runner.invoke(cli.app, ["metrics", "query", run_id, "--scope", "run", "--json"])
    assert m_q.exit_code == 0, m_q.stdout
    m_u = runner.invoke(cli.app, ["metrics", "usage", run_id, "--json"])
    assert m_u.exit_code == 0, m_u.stdout


def test_cli_consent_and_memory_lifecycle(cli_run_service, tmp_path: Path):
    svc, repo, base_sha = cli_run_service
    area_id = json.loads(runner.invoke(cli.app, ["area", "create", "--name", "m-area", "--principal-id", "op-1", "--json"]).stdout)["id"]
    ws_id = json.loads(runner.invoke(cli.app, ["workspace", "create", "--area-id", area_id, "--name", "m-ws", "--principal-id", "op-1", "--json"]).stdout)["id"]

    # Memory write without consent -> exit_code == 3
    no_consent = runner.invoke(
        cli.app,
        [
            "memory",
            "write",
            "--scope-type",
            "workspace",
            "--scope-id",
            ws_id,
            "--content",
            "pytest runs fast",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert no_consent.exit_code == 3, no_consent.stdout
    assert json.loads(no_consent.stdout)["code"] == "consent_required"

    c_req = runner.invoke(
        cli.app,
        ["consent", "request", "--scope-type", "workspace", "--scope-id", ws_id, "--principal-id", "op-1", "--json"],
    )
    assert c_req.exit_code == 0, c_req.stdout
    consent_id = json.loads(c_req.stdout)["consent_id"]

    assert len(json.loads(runner.invoke(cli.app, ["consent", "list", "--scope-type", "workspace", "--scope-id", ws_id, "--principal-id", "op-1", "--json"]).stdout)) == 1

    c_dec = runner.invoke(
        cli.app,
        ["consent", "decide", consent_id, "--action", "granted", "--principal-id", "op-1", "--json"],
    )
    assert c_dec.exit_code == 0
    assert json.loads(c_dec.stdout)["status"] == "granted"

    out_mem = tmp_path / "memory-write.json"
    m_write = runner.invoke(
        cli.app,
        [
            "memory",
            "write",
            "--scope-type",
            "workspace",
            "--scope-id",
            ws_id,
            "--consent-id",
            consent_id,
            "--content",
            "repo uses pytest",
            "--principal-id",
            "op-1",
            "--json",
            "--output",
            str(out_mem),
        ],
    )
    assert m_write.exit_code == 0, m_write.stdout
    memory_id = json.loads(out_mem.read_text(encoding="utf-8"))["memory_id"]

    m_query = runner.invoke(
        cli.app,
        ["memory", "query", "--scope-type", "workspace", "--scope-id", ws_id, "--query", "pytest", "--principal-id", "op-1", "--json"],
    )
    assert m_query.exit_code == 0
    assert len(json.loads(m_query.stdout)) == 1

    m_rev = runner.invoke(cli.app, ["memory", "revoke", memory_id, "--principal-id", "op-1", "--json"])
    assert m_rev.exit_code == 0
    assert json.loads(m_rev.stdout)["status"] == "revoked"

    c_rev = runner.invoke(cli.app, ["consent", "revoke", consent_id, "--principal-id", "op-1", "--json"])
    assert c_rev.exit_code == 0
    assert json.loads(c_rev.stdout)["status"] == "revoked"


def test_cli_discovery_skill_mcp_and_secret_hygiene(cli_run_service, monkeypatch):
    import hashlib

    svc, repo, base_sha = cli_run_service

    # Place skill and mcp files under repo_root for discovery
    skills_dir = repo / ".hydra" / "skills"
    skills_dir.mkdir(parents=True)
    skill_file = skills_dir / "SKILL.md"
    skill_file.write_text("---\nname: lint-skill\n---\n# Lint skill\nRun linter safely.\n", encoding="utf-8")
    skill_hash = hashlib.sha256(skill_file.read_bytes()).hexdigest()

    mcp_file = repo / "mcp.json"
    mcp_file.write_text(json.dumps({"mcpServers": {"local": {"command": "python"}}}), encoding="utf-8")

    scan = runner.invoke(cli.app, ["discovery", "scan", "--root", str(repo), "--principal-id", "op-1", "--json"])
    assert scan.exit_code == 0, scan.stdout
    items = json.loads(runner.invoke(cli.app, ["discovery", "list", "--principal-id", "op-1", "--json"]).stdout)
    assert len(items) >= 2

    skill_res_item = next(i for i in items if str(i["source_canonical_path"]).endswith("SKILL.md"))
    mcp_res_item = next(i for i in items if str(i["source_canonical_path"]).endswith("mcp.json"))

    app_skill = runner.invoke(
        cli.app,
        ["discovery", "approve", skill_res_item["discovery_id"], "--expected-hash", skill_hash, "--principal-id", "op-1", "--json"],
    )
    assert app_skill.exit_code == 0, app_skill.stdout

    rej_mcp = runner.invoke(
        cli.app,
        ["discovery", "reject", mcp_res_item["discovery_id"], "--principal-id", "op-1", "--json"],
    )
    assert rej_mcp.exit_code == 0, rej_mcp.stdout
    assert json.loads(rej_mcp.stdout)["trust_status"] == "rejected"

    # Secret refuses literals -> exit_code == 1
    bad_secret = runner.invoke(
        cli.app,
        [
            "secret",
            "register",
            "--name",
            "openai_key",
            "--provider",
            "env",
            "--source-key",
            "sk-1234567890abcdef1234567890abcdef",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert bad_secret.exit_code == 1, bad_secret.stdout

    secret_val = "REAL_TOP_SECRET_VALUE_999999999999"
    monkeypatch.setenv("HYDRA_CLI_TEST_SECRET", secret_val)
    ok_secret = runner.invoke(
        cli.app,
        [
            "secret",
            "register",
            "--name",
            "test_api_key",
            "--provider",
            "env",
            "--source-key",
            "HYDRA_CLI_TEST_SECRET",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert ok_secret.exit_code == 0, ok_secret.stdout
    secret_id = json.loads(ok_secret.stdout)["secret_id"]

    get_secret = runner.invoke(cli.app, ["secret", "get", secret_id, "--json"])
    assert get_secret.exit_code == 0
    assert secret_val not in get_secret.stdout
    assert json.loads(get_secret.stdout)["source_key"] == "HYDRA_CLI_TEST_SECRET"

    # Register skill & revoke
    sk_reg = runner.invoke(
        cli.app,
        [
            "skill",
            "register",
            "--name",
            "lint-skill",
            "--manifest-ref",
            str(skill_file),
            "--checksum",
            skill_hash,
            "--discovered-resource-id",
            skill_res_item["discovery_id"],
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert sk_reg.exit_code == 0, sk_reg.stdout
    skill_id = json.loads(sk_reg.stdout)["skill_id"]
    assert runner.invoke(cli.app, ["skill", "get", skill_id, "--json"]).exit_code == 0
    assert runner.invoke(cli.app, ["skill", "revoke", skill_id, "--principal-id", "op-1", "--json"]).exit_code == 0

    # Register standalone MCP with matching secret permission & revoke
    mcp_reg = runner.invoke(
        cli.app,
        [
            "mcp",
            "register",
            "--server-name",
            "local-mcp",
            "--transport-type",
            "stdio",
            "--endpoint",
            "python -m mcp_srv",
            "--secret-ref",
            secret_id,
            "--permissions",
            f"secret:{secret_id}",
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert mcp_reg.exit_code == 0, mcp_reg.stdout
    mcp_id = json.loads(mcp_reg.stdout)["mcp_id"]
    assert runner.invoke(cli.app, ["mcp", "get", mcp_id, "--json"]).exit_code == 0
    assert runner.invoke(cli.app, ["mcp", "revoke", mcp_id, "--principal-id", "op-1", "--json"]).exit_code == 0
    assert runner.invoke(cli.app, ["secret", "revoke", secret_id, "--principal-id", "op-1", "--json"]).exit_code == 0


def test_cli_extension_lifecycle_and_rollback(cli_run_service, tmp_path: Path):
    import hashlib

    svc, repo, _base_sha = cli_run_service
    ext_dir = repo / "extensions"
    ext_dir.mkdir()
    ep1 = ext_dir / "ext_v1.py"
    ep1.write_text("print('v1')\n", encoding="utf-8")
    cs1 = hashlib.sha256(ep1.read_bytes()).hexdigest()

    ep2 = ext_dir / "ext_v2.py"
    ep2.write_text("print('v2')\n", encoding="utf-8")
    cs2 = hashlib.sha256(ep2.read_bytes()).hexdigest()

    ext_id = "ext-cli-01"
    reg1 = runner.invoke(
        cli.app,
        [
            "extension",
            "register",
            "--extension-id",
            ext_id,
            "--name",
            "cli-ext",
            "--version",
            "1.0.0",
            "--entrypoint",
            str(ep1),
            "--checksum",
            cs1,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert reg1.exit_code == 0, reg1.stdout

    # Traversal outside repo -> exit_code == 1
    outside_ep = tmp_path / "evil.py"
    outside_ep.write_text("print('evil')\n", encoding="utf-8")
    reg_bad = runner.invoke(
        cli.app,
        [
            "extension",
            "register",
            "--name",
            "evil-ext",
            "--version",
            "1.0.0",
            "--entrypoint",
            str(outside_ep),
            "--checksum",
            hashlib.sha256(outside_ep.read_bytes()).hexdigest(),
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert reg_bad.exit_code == 1, reg_bad.stdout

    # Consent for extension (scoped by manifest name so v1 and v2 share consent)
    c_req = json.loads(
        runner.invoke(
            cli.app,
            ["consent", "request", "--scope-type", "extension", "--scope-id", "cli-ext", "--purpose", "extension", "--principal-id", "op-1", "--json"],
        ).stdout
    )
    consent_id = c_req["consent_id"]
    runner.invoke(cli.app, ["consent", "decide", consent_id, "--action", "granted", "--principal-id", "op-1", "--json"])

    inst1 = runner.invoke(
        cli.app,
        [
            "extension",
            "install",
            "--extension-id",
            ext_id,
            "--name",
            "cli-ext",
            "--version",
            "1.0.0",
            "--entrypoint",
            str(ep1),
            "--checksum",
            cs1,
            "--consent-id",
            consent_id,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert inst1.exit_code == 0, inst1.stdout
    install_id = json.loads(inst1.stdout)["install_id"]

    assert len(json.loads(runner.invoke(cli.app, ["extension", "list", "--json"]).stdout)) == 1

    # Upgrade to v1.1.0 with distinct manifest ID then rollback to v1.0.0
    ext_id_v2 = "ext-cli-02"
    reg2 = runner.invoke(
        cli.app,
        [
            "extension",
            "register",
            "--extension-id",
            ext_id_v2,
            "--name",
            "cli-ext",
            "--version",
            "1.1.0",
            "--entrypoint",
            str(ep2),
            "--checksum",
            cs2,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert reg2.exit_code == 0, reg2.stdout
    inst2 = runner.invoke(
        cli.app,
        [
            "extension",
            "install",
            "--extension-id",
            ext_id_v2,
            "--name",
            "cli-ext",
            "--version",
            "1.1.0",
            "--entrypoint",
            str(ep2),
            "--checksum",
            cs2,
            "--consent-id",
            consent_id,
            "--principal-id",
            "op-1",
            "--json",
        ],
    )
    assert inst2.exit_code == 0, inst2.stdout
    install_id_v2 = json.loads(inst2.stdout)["install_id"]

    dis = runner.invoke(cli.app, ["extension", "disable", install_id_v2, "--principal-id", "op-1", "--json"])
    assert dis.exit_code == 0, dis.stdout
    assert json.loads(dis.stdout)["status"] == "disabled"

    act = runner.invoke(cli.app, ["extension", "activate", install_id_v2, "--principal-id", "op-1", "--json"])
    assert act.exit_code == 0, act.stdout
    assert json.loads(act.stdout)["status"] == "active"

    rb = runner.invoke(cli.app, ["extension", "rollback", install_id_v2, "--principal-id", "op-1", "--json"])
    assert rb.exit_code == 0, rb.stdout
    assert json.loads(rb.stdout)["status"] == "active"

    rev = runner.invoke(cli.app, ["extension", "revoke", install_id, "--principal-id", "op-1", "--json"])
    assert rev.exit_code == 0, rev.stdout
    assert json.loads(rev.stdout)["status"] == "revoked"


def test_cli_preference_transport_and_token(cli_run_service, tmp_path: Path, monkeypatch):
    import asyncio
    import platform
    import sqlite3

    svc, repo, base_sha = cli_run_service
    run_id = json.loads(
        runner.invoke(
            cli.app,
            ["submit", "--objective", "Prefs run", "--project-id", "proj-pref", "--repo-root", str(repo), "--base-sha", base_sha, "--json"],
        ).stdout
    )["run_id"]

    # Preferences: set, adaptive precedence conflict (exit 3), list, resolve, revert, snapshot
    p1 = runner.invoke(
        cli.app,
        ["preference", "set", "--scope-type", "user", "--scope-id", "u1", "--key", "theme", "--value", '"dark"', "--json"],
    )
    assert p1.exit_code == 0, p1.stdout
    p2 = runner.invoke(
        cli.app,
        ["preference", "set", "--scope-type", "user", "--scope-id", "u1", "--key", "theme", "--value", '"light"', "--json"],
    )
    assert p2.exit_code == 0

    adaptive_conflict = runner.invoke(
        cli.app,
        ["preference", "set", "--scope-type", "user", "--scope-id", "u1", "--key", "theme", "--value", '"solarized"', "--source", "inferred_opt_in", "--opt-in", "--json"],
    )
    assert adaptive_conflict.exit_code == 3, adaptive_conflict.stdout

    assert len(json.loads(runner.invoke(cli.app, ["preference", "list", "--scope-type", "user", "--scope-id", "u1", "--json"]).stdout)) == 1
    resolved = runner.invoke(cli.app, ["preference", "resolve", "--user-id", "u1", "--json"])
    assert resolved.exit_code == 0
    assert json.loads(resolved.stdout)["theme"] == "light"

    rev = runner.invoke(
        cli.app,
        ["preference", "revert", "--scope-type", "user", "--scope-id", "u1", "--key", "theme", "--json"],
    )
    assert rev.exit_code == 0, rev.stdout
    assert json.loads(json.loads(rev.stdout)["preference"]["value_json"]) == "dark"

    snap = runner.invoke(cli.app, ["preference", "snapshot", run_id, "--user-id", "u1", "--json"])
    assert snap.exit_code == 0, snap.stdout
    assert json.loads(json.loads(snap.stdout)["resolved_preferences_json"])["preferences"]["theme"] == "dark"

    # Transport: register, list, certify, health, simulated report rejection (exit 1)
    tr_reg = runner.invoke(
        cli.app,
        ["transport", "register", "--type", "ssh", "--target-identity", "build-box.local:22", "--capabilities", "remote_exec", "--json"],
    )
    assert tr_reg.exit_code == 0, tr_reg.stdout
    transport_id = json.loads(tr_reg.stdout)["transport_id"]
    assert len(json.loads(runner.invoke(cli.app, ["transport", "list", "--json"]).stdout)) == 1

    sim_report = tmp_path / "sim-tr.json"
    sim_report.write_text(
        json.dumps(
            {
                "transport_id": transport_id,
                "transport_type": "ssh",
                "platform": platform.system(),
                "version": "1.0.0",
                "target_identity": "build-box.local:22",
                "passed_checks": ["handshake", "host_key"],
                "simulated": True,
            }
        ),
        encoding="utf-8",
    )
    assert runner.invoke(cli.app, ["transport", "certify", transport_id, "--report", str(sim_report), "--json"]).exit_code == 1

    ok_report = tmp_path / "ok-tr.json"
    ok_report.write_text(
        json.dumps(
            {
                "transport_id": transport_id,
                "transport_type": "ssh",
                "platform": platform.system(),
                "version": "1.0.0",
                "target_identity": "build-box.local:22",
                "fingerprint": "SHA256:abcdef123456",
                "passed_checks": ["healthcheck", "host_key_verification", "session_isolation", "target_identity"],
                "simulated": False,
            }
        ),
        encoding="utf-8",
    )
    cert = runner.invoke(cli.app, ["transport", "certify", transport_id, "--report", str(ok_report), "--principal-id", "op-1", "--json"])
    assert cert.exit_code == 0, cert.stdout
    assert len(json.loads(runner.invoke(cli.app, ["transport", "list", "--certified-only", "--json"]).stdout)) == 1
    health = runner.invoke(cli.app, ["transport", "health", transport_id, "--json"])
    assert health.exit_code == 0, health.stdout

    # Token create & revoke: hashes via PBKDF2-SHA256, never persists or prints plaintext
    raw_tok = "hydra_cli_test_token_value_32_characters_long_001"
    monkeypatch.setenv("HYDRA_CLI_RAW_TOKEN", raw_tok)
    bad_tok = runner.invoke(cli.app, ["token", "create", "--principal-id", "op-1", "--token", "too-short", "--json"])
    assert bad_tok.exit_code == 1

    tok_res = runner.invoke(
        cli.app,
        ["token", "create", "--principal-id", "op-1", "--scopes", "read,write", "--token-env", "HYDRA_CLI_RAW_TOKEN", "--json"],
    )
    assert tok_res.exit_code == 0, tok_res.stdout
    assert raw_tok not in tok_res.stdout
    tok_id = json.loads(tok_res.stdout)["token_id"]

    # Confirm DB has hashed token and ZERO plaintext
    async def _fetch_tok():
        async with svc.store._connect() as db:
            return await (await db.execute("SELECT token_hash, revoked_at FROM access_tokens WHERE id = ?", (tok_id,))).fetchone()

    row = asyncio.run(_fetch_tok())
    assert row is not None
    assert row["token_hash"].startswith("pbkdf2_sha256$600000$")
    assert raw_tok not in row["token_hash"]
    assert row["revoked_at"] is None

    rev_tok = runner.invoke(cli.app, ["token", "revoke", tok_id, "--json"])
    assert rev_tok.exit_code == 0
    assert json.loads(rev_tok.stdout)["revoked"] is True
    row_after = asyncio.run(_fetch_tok())
    assert row_after["revoked_at"] is not None

    assert runner.invoke(cli.app, ["token", "revoke", "missing-tok-id", "--json"]).exit_code == 1


def test_cli_budget_pr_package_and_conflict(cli_run_service, tmp_path: Path):
    import asyncio
    import subprocess
    from hydra_orch.core.identifier import new_id

    svc, repo, base_sha = cli_run_service

    # Setup bare remote for authorized PR publish test
    remote_bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_bare)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote_bare)], check=True, capture_output=True)

    submit = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Budget & packaging CLI test",
            "--project-id",
            "proj-bp",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--task-id",
            "t-pr",
            "--json",
        ],
    )
    assert submit.exit_code == 0, submit.stdout
    run_id = json.loads(submit.stdout)["run_id"]

    # Budget status & extend (with --output check)
    budget_out = tmp_path / "budget-status.json"
    b_stat = runner.invoke(cli.app, ["budget", "status", run_id, "--json", "--output", str(budget_out)])
    assert b_stat.exit_code == 0, b_stat.stdout
    assert budget_out.exists()
    b_ext = runner.invoke(
        cli.app,
        ["budget", "extend", run_id, "--additional-usd", "3.5", "--actor", "op-1", "--reason", "more verification", "--json"],
    )
    assert b_ext.exit_code == 0, b_ext.stdout
    assert json.loads(b_ext.stdout)["approved"] is True

    # Execute task attempt, review & integrate so PRPackage build succeeds
    worker_py = (
        "from pathlib import Path\n"
        "Path('src/greeter.py').write_text(\"def greet() -> str:\\n    return 'hello pkg'\\n\", encoding='utf-8')\n"
    )
    asyncio.run(
        svc.execute_task_attempt(
            run_id=run_id,
            task_id="t-pr",
            custom_command=[sys.executable, "-c", worker_py],
        )
    )
    assert runner.invoke(cli.app, ["review", run_id, "t-pr", "--decision", "accepted", "--reason", "ok", "--json"]).exit_code == 0
    assert runner.invoke(cli.app, ["integrate", run_id, "--json"]).exit_code == 0

    pkg_build = runner.invoke(cli.app, ["pr-package", "build", run_id, "--json"])
    assert pkg_build.exit_code == 0, pkg_build.stdout
    package_id = json.loads(pkg_build.stdout)["package_id"]

    # Publish without --authorized -> exit_code == 3
    pub_denied = runner.invoke(cli.app, ["pr-package", "publish", package_id, "--json"])
    assert pub_denied.exit_code == 3, pub_denied.stdout
    assert json.loads(pub_denied.stdout)["code"] == "publish_not_authorized"

    # Publish with --authorized -> exit_code == 0 (pushes to local bare remote)
    pub_ok = runner.invoke(cli.app, ["pr-package", "publish", package_id, "--authorized", "--remote", "origin", "--json"])
    assert pub_ok.exit_code == 0, pub_ok.stdout
    assert json.loads(pub_ok.stdout)["published"] is True

    # Conflict commands: create two genuine conflicting commits on branches, seed a conflict integration on a fresh run, and run analyze -> auto-repair -> manual -> discard
    def _git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    _git("checkout", "-b", "cfl-ours", base_sha)
    (repo / "src" / "greeter.py").write_text("def greet() -> str:\n    return 'ours'\n", encoding="utf-8")
    _git("add", "src/greeter.py")
    _git("commit", "-m", "ours conflict")
    ours_sha = _git("rev-parse", "HEAD")

    _git("checkout", "-b", "cfl-theirs", base_sha)
    (repo / "src" / "greeter.py").write_text("def greet() -> str:\n    return 'theirs'\n", encoding="utf-8")
    _git("add", "src/greeter.py")
    _git("commit", "-m", "theirs conflict")
    theirs_sha = _git("rev-parse", "HEAD")
    _git("checkout", "main")

    sub2 = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Conflict CLI test",
            "--project-id",
            "proj-bp",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--task-id",
            "t-cfl",
            "--json",
        ],
    )
    assert sub2.exit_code == 0, sub2.stdout
    run_id_2 = json.loads(sub2.stdout)["run_id"]

    async def _seed_conflict_integration() -> str:
        int_id = new_id()
        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO integrations(id, run_id, workspace_path, expected_base_sha, result_sha, status)
                    VALUES (?, ?, ?, ?, NULL, 'conflicted')
                    """,
                    (int_id, run_id_2, str(repo), base_sha),
                )
        return int_id

    integration_id = asyncio.run(_seed_conflict_integration())
    c_ana = runner.invoke(
        cli.app,
        ["conflict", "analyze", integration_id, "--base-sha", base_sha, "--ours-sha", ours_sha, "--theirs-sha", theirs_sha, "--json"],
    )
    assert c_ana.exit_code == 0, c_ana.stdout
    conflict_id = json.loads(c_ana.stdout)["conflict_id"]

    c_auto = runner.invoke(cli.app, ["conflict", "auto-repair", conflict_id, "--max-repair-attempts", "1", "--json"])
    assert c_auto.exit_code == 0, c_auto.stdout

    c_man = runner.invoke(cli.app, ["conflict", "manual", conflict_id, "--actor", "op-1", "--json"])
    assert c_man.exit_code == 0, c_man.stdout

    c_disc = runner.invoke(cli.app, ["conflict", "discard", conflict_id, "--actor", "op-1", "--json"])
    assert c_disc.exit_code == 0, c_disc.stdout
    assert json.loads(c_disc.stdout)["status"] == "discarded"

    # Re-discarding resolved/discarded conflict -> exit_code == 3
    c_disc2 = runner.invoke(cli.app, ["conflict", "discard", conflict_id, "--actor", "op-1", "--json"])
    assert c_disc2.exit_code == 3
def test_cli_route_and_automation_wave12(cli_run_service):
    _svc, _repo, _base_sha = cli_run_service
    inv = runner.invoke(cli.app, ["route", "inventory", "--json"])
    assert inv.exit_code == 0, inv.stdout
    assert "connection_mode" in json.loads(inv.stdout)

    sel = runner.invoke(cli.app, ["route", "select-account", "--provider", "codex", "--account-id", "acct-cli", "--json"])
    assert sel.exit_code == 0, sel.stdout
    assert json.loads(sel.stdout)["account_id"] == "acct-cli"

    cr = runner.invoke(
        cli.app,
        [
            "automation",
            "create",
            "--name",
            "CLI Schedule",
            "--prompt",
            "Check repo",
            "--interval-seconds",
            "1800",
            "--timezone",
            "UTC",
            "--json",
        ],
    )
    assert cr.exit_code == 0, cr.stdout
    sched_id = json.loads(cr.stdout)["id"]

    ls = runner.invoke(cli.app, ["automation", "list", "--json"])
    assert ls.exit_code == 0
    assert any(item["id"] == sched_id for item in json.loads(ls.stdout))

    ps = runner.invoke(cli.app, ["automation", "pause", sched_id, "--json"])
    assert ps.exit_code == 0
    assert json.loads(ps.stdout)["enabled"] is False

    rs = runner.invoke(cli.app, ["automation", "resume", sched_id, "--json"])
    assert rs.exit_code == 0
    assert json.loads(rs.stdout)["enabled"] is True

    tk = runner.invoke(cli.app, ["automation", "tick", "--json"])
    assert tk.exit_code == 0

    hs = runner.invoke(cli.app, ["automation", "history", sched_id, "--json"])
    assert hs.exit_code == 0

    dl = runner.invoke(cli.app, ["automation", "delete", sched_id, "--json"])
    assert dl.exit_code == 0
    assert json.loads(dl.stdout)["deleted"] is True
