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
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
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
