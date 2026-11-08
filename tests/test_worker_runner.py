"""Hermetic unit and subprocess integration tests for S04 / T04 (bridge/worker_runner.py)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
from typing import Dict

import pytest

from hydra_orch.bridge.worker_runner import (
    WorkerRunner,
    build_invocation,
    cancel_process_tree,
    filter_worker_env,
    is_process_alive,
)
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.model import (
    CheckSpec,
    ContractViolation,
    ExecutorCapability,
    ProcessStatus,
    RunSpec,
    TaskSpec,
)

BASE_SHA = "a" * 40


@pytest.mark.asyncio
async def test_cwd_resolved(tmp_path: Path):
    """Subprocess executes in the canonical resolved worktree cwd, modifies file, and produces artifacts."""
    worktree = tmp_path / "worktree_task_1"
    worktree.mkdir()
    artifacts_dir = tmp_path / "artifacts"

    script = (
        "import os, sys, pathlib\n"
        "prompt_data = sys.stdin.read()\n"
        "cwd = os.getcwd()\n"
        "pathlib.Path('modified.txt').write_text(f'{cwd}|{prompt_data}', encoding='utf-8')\n"
        "print('stdout-ok')\n"
        "sys.stderr.write('stderr-info\\n')\n"
    )

    runner = WorkerRunner(default_cli="codex")
    res = await runner.execute_task_in_worktree(
        worktree_path=worktree,
        prompt="Apply patch T04",
        cli_name="python_fake",
        custom_command=(sys.executable, "-c", script),
        attempt_id="att-cwd-1",
        task_id="task-1",
        run_id="run-1",
        base_sha=BASE_SHA,
        artifacts_dir=artifacts_dir,
        artifacts_rel_prefix="attempt/att-cwd-1",
    )

    expected_cwd = os.path.realpath(str(worktree))
    assert res["success"] is True
    assert res["simulated"] is False
    assert res["exit_code"] == 0
    assert res["process_status"] == ProcessStatus.EXITED.value
    assert res["cwd"] == expected_cwd
    assert "stdout-ok" in res["output"]
    assert "stderr-info" in res["stderr"]

    modified_file = worktree / "modified.txt"
    assert modified_file.is_file()
    content = modified_file.read_text(encoding="utf-8")
    assert content == f"{expected_cwd}|Apply patch T04"

    # Verify stdio artifacts and SHA-256 hashes
    artifacts = res["artifacts"]
    assert len(artifacts) == 2
    stdout_art, stderr_art = artifacts
    stdout_bytes = (artifacts_dir / "stdout.log").read_bytes()
    stderr_bytes = (artifacts_dir / "stderr.log").read_bytes()
    assert stdout_art.sha256 == hashlib.sha256(stdout_bytes).hexdigest()
    assert stderr_art.sha256 == hashlib.sha256(stderr_bytes).hexdigest()
    assert stdout_art.size_bytes == len(stdout_bytes)


@pytest.mark.asyncio
async def test_env_filtered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Sensitive environment variables are stripped from worker subprocesses while safe and allowed vars remain."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-openai-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-456")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_789")
    monkeypatch.setenv("MY_CUSTOM_SECRET_KEY", "top-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("UNLISTED_RANDOM_VAR", "should-not-pass")

    filtered = filter_worker_env(allowed_env={"EXPLICIT_ALLOWED_VAR": "allowed-value"})
    assert "OPENAI_API_KEY" not in filtered
    assert "ANTHROPIC_API_KEY" not in filtered
    assert "GITHUB_TOKEN" not in filtered
    assert "MY_CUSTOM_SECRET_KEY" not in filtered
    assert "DATABASE_URL" not in filtered
    assert "UNLISTED_RANDOM_VAR" not in filtered
    assert filtered["EXPLICIT_ALLOWED_VAR"] == "allowed-value"
    assert filtered["HYDRA_WORKER_ISOLATED"] == "1"
    assert filtered["GIT_TERMINAL_PROMPT"] == "0"

    # Also verify inside a real child subprocess
    script = (
        "import json, os\n"
        "print(json.dumps({\n"
        "  'has_openai': 'OPENAI_API_KEY' in os.environ,\n"
        "  'has_github': 'GITHUB_TOKEN' in os.environ,\n"
        "  'has_db': 'DATABASE_URL' in os.environ,\n"
        "  'isolated': os.environ.get('HYDRA_WORKER_ISOLATED'),\n"
        "  'allowed': os.environ.get('EXPLICIT_ALLOWED_VAR'),\n"
        "  'forbidden_files': os.environ.get('HYDRA_FORBIDDEN_FILES'),\n"
        "}))\n"
    )
    runner = WorkerRunner()
    res = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="",
        custom_command=(sys.executable, "-c", script),
        allowed_env={"EXPLICIT_ALLOWED_VAR": "allowed-value"},
        forbidden_files=["pyproject.toml", "poetry.lock"],
    )
    assert res["success"] is True
    observed: Dict[str, object] = json.loads(res["output"].strip())
    assert observed["has_openai"] is False
    assert observed["has_github"] is False
    assert observed["has_db"] is False
    assert observed["isolated"] == "1"
    assert observed["allowed"] == "allowed-value"
    assert observed["forbidden_files"] == "pyproject.toml,poetry.lock"


@pytest.mark.asyncio
async def test_fake_only_dry_run(tmp_path: Path):
    """Missing CLI with dry_run=False fails with executor_unavailable without touching disk; dry_run=True marks simulated=True."""
    runner = WorkerRunner(default_cli="nonexistent_cli_binary_xyz_999")
    assert runner.is_cli_installed() is False
    assert runner.is_cli_installed("") is False

    res_real = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="Do not fabricate success",
        dry_run=False,
    )
    assert res_real["success"] is False
    assert res_real["simulated"] is False
    assert res_real["error"] == "executor_unavailable"
    assert res_real["process_status"] == ProcessStatus.CRASHED.value
    assert res_real["failure"] is not None
    assert res_real["failure"].code == "executor_unavailable"
    assert not (tmp_path / "CONTRACT_APPLIED.md").exists()

    res_dry = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="Explicit dry run",
        dry_run=True,
    )
    assert res_dry["success"] is True
    assert res_dry["simulated"] is True
    assert res_dry["error"] is None
    assert (tmp_path / "CONTRACT_APPLIED.md").is_file()


@pytest.mark.asyncio
async def test_timeout_tree_kill(tmp_path: Path):
    """Timeout terminates both the worker process and its spawned child process (tree kill)."""
    pids_file = tmp_path / "pids.json"
    parent_script = (
        "import json, os, subprocess, sys, time, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pids_file)!r}).write_text(json.dumps({{'parent': os.getpid(), 'child': child.pid}}))\n"
        "time.sleep(60)\n"
    )

    runner = WorkerRunner()
    res = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="Long task",
        custom_command=(sys.executable, "-c", parent_script),
        timeout=0.5,
        attempt_id="att-timeout-tree",
    )

    assert res["success"] is False
    assert res["simulated"] is False
    assert res["error"] == "execution_timed_out"
    assert res["process_status"] == ProcessStatus.TIMED_OUT.value
    assert res["tree_killed"] is True

    assert pids_file.is_file(), "Parent process should have recorded its PID and child PID before timeout"
    pids = json.loads(pids_file.read_text(encoding="utf-8"))
    parent_pid = int(pids["parent"])
    child_pid = int(pids["child"])

    # Wait briefly if OS is finishing handle cleanup, then assert both parent and child are dead
    for _ in range(20):
        if not is_process_alive(parent_pid) and not is_process_alive(child_pid):
            break
        await asyncio.sleep(0.05)

    assert is_process_alive(parent_pid) is False
    assert is_process_alive(child_pid) is False


@pytest.mark.asyncio
async def test_verify_tree_kill(tmp_path: Path):
    """Direct verification of cancel_process_tree on a process tree with parent + child."""
    pids_file = tmp_path / "tree_pids.json"
    script = (
        "import json, os, subprocess, sys, time, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pids_file)!r}).write_text(json.dumps({{'parent': os.getpid(), 'child': child.pid}}))\n"
        "time.sleep(60)\n"
    )
    sub_kwargs = {}
    if os.name != "nt":
        sub_kwargs["start_new_session"] = True
    else:
        sub_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        cwd=str(tmp_path),
        **sub_kwargs,
    )

    for _ in range(50):
        if pids_file.exists():
            break
        await asyncio.sleep(0.05)

    assert pids_file.exists()
    pids = json.loads(pids_file.read_text(encoding="utf-8"))
    parent_pid = int(pids["parent"])
    child_pid = int(pids["child"])
    assert is_process_alive(parent_pid) is True
    assert is_process_alive(child_pid) is True

    killed = await cancel_process_tree(parent_pid)
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except Exception:
        pass

    assert killed is True
    for _ in range(20):
        if not is_process_alive(parent_pid) and not is_process_alive(child_pid):
            break
        await asyncio.sleep(0.05)

    assert is_process_alive(parent_pid) is False
    assert is_process_alive(child_pid) is False
    # Calling cancel_process_tree on an already dead PID or invalid PID returns True
    assert await cancel_process_tree(parent_pid) is True
    assert await cancel_process_tree(-1) is True


@pytest.mark.asyncio
async def test_cancel_idempotent(tmp_path: Path):
    """Concurrent cancel(attempt_id) kills the active worker tree and subsequent cancel() calls are idempotent."""
    ready_file = tmp_path / "worker_ready.json"
    script = (
        "import json, os, subprocess, sys, time, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(ready_file)!r}).write_text(json.dumps({{'parent': os.getpid(), 'child': child.pid}}))\n"
        "time.sleep(60)\n"
    )

    runner = WorkerRunner()
    exec_task = asyncio.create_task(
        runner.execute_task_in_worktree(
            worktree_path=tmp_path,
            prompt="Cancel me",
            custom_command=(sys.executable, "-c", script),
            timeout=30.0,
            attempt_id="att-cancel-1",
        )
    )

    for _ in range(60):
        if ready_file.exists():
            break
        await asyncio.sleep(0.05)
    assert ready_file.exists()
    pids = json.loads(ready_file.read_text(encoding="utf-8"))

    cancel_res1 = await runner.cancel("att-cancel-1", reason="user_requested_stop")
    assert cancel_res1["cancelled"] is True
    assert cancel_res1["already_terminated"] is False
    assert cancel_res1["tree_killed"] is True

    exec_res = await exec_task
    assert exec_res["success"] is False
    assert exec_res["process_status"] == ProcessStatus.CANCELLED.value
    assert exec_res["error"] == "execution_cancelled"
    assert exec_res["attempt"].exit_reason == "user_requested_stop"

    for _ in range(20):
        if not is_process_alive(int(pids["parent"])) and not is_process_alive(int(pids["child"])):
            break
        await asyncio.sleep(0.05)
    assert is_process_alive(int(pids["parent"])) is False
    assert is_process_alive(int(pids["child"])) is False

    # Second cancel on the same attempt_id is idempotent
    cancel_res2 = await runner.cancel("att-cancel-1")
    assert cancel_res2["cancelled"] is True
    assert cancel_res2["already_terminated"] is True

    # Cancel on unknown attempt_id is also idempotent
    cancel_unknown = await runner.cancel("att-never-existed")
    assert cancel_unknown["cancelled"] is True
    assert cancel_unknown["already_terminated"] is True


@pytest.mark.asyncio
async def test_dispatch_latency(tmp_path: Path):
    """RNF01: Subprocess dispatch latency is < 300ms on local fixture."""
    runner = WorkerRunner()
    res = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="",
        custom_command=(sys.executable, "-c", "print('fast')"),
        attempt_id="att-latency-1",
    )
    assert res["success"] is True
    assert res["dispatch_latency_ms"] < 300.0


def test_driver_invocations_and_capabilities():
    """Verify deterministic argv/stdin construction for all supported CLI drivers."""
    codex_plan = build_invocation("codex", "Fix bug", extra_args=("--full-auto",))
    assert codex_plan.argv == ("codex", "exec", "--sandbox", "workspace-write", "-", "--full-auto")
    assert codex_plan.stdin_bytes == b"Fix bug"
    assert ExecutorCapability.FILESYSTEM_SANDBOX in codex_plan.capabilities.capabilities

    codex_resume = build_invocation("codex", "Continue", resume_session="sess-123")
    assert codex_resume.argv[:4] == ("codex", "exec", "resume", "sess-123")

    claude_plan = build_invocation("claude_code", "Write tests", resume_session="c-sess-1")
    assert claude_plan.executable == "claude"
    assert "--resume" in claude_plan.argv
    assert claude_plan.stdin_bytes == b"Write tests"

    opencode_plan = build_invocation("opencode", "Refactor")
    assert opencode_plan.argv == ("opencode", "run", "Refactor")
    assert opencode_plan.stdin_bytes is None

    agy_plan = build_invocation("agy", "Implement UI")
    assert agy_plan.argv == ("agy", "chat", "--prompt", "Implement UI")

    gemini_plan = build_invocation("gemini_cli", "Analyze")
    assert gemini_plan.argv == ("gemini", "--prompt", "Analyze")

    aider_plan = build_invocation("aider", "Patch file")
    assert "--no-auto-commits" in aider_plan.argv

    other_plan = build_invocation("custom_cli", "Hello")
    assert other_plan.argv == ("custom_cli", "--message", "Hello")

    runner = WorkerRunner(default_cli="codex")
    caps = runner.capabilities()
    assert caps.executor_id == "codex"
    assert runner.is_cli_installed(sys.executable) is True

    with pytest.raises(ContractViolation):
        build_invocation("", "prompt")
    with pytest.raises(ContractViolation):
        build_invocation("codex", "bad\x00prompt")
    with pytest.raises(ContractViolation):
        build_invocation("codex", "ok", extra_args=("bad\x00arg",))
    with pytest.raises(ContractViolation):
        build_invocation("custom", "ok", custom_command=("",))
    with pytest.raises(ContractViolation):
        filter_worker_env(allowed_env={"BAD\x00KEY": "val"})


@pytest.mark.asyncio
async def test_nonzero_exit_invalid_cwd_and_store_integration(tmp_path: Path):
    """Verify non-zero exit code, invalid cwd handling, and integration with ExecutionStore."""
    runner = WorkerRunner()

    # Non-existent worktree_path fails before spawn with invalid_workspace_cwd
    bad_cwd_res = await runner.execute_task_in_worktree(
        worktree_path=tmp_path / "does_not_exist_dir",
        prompt="test",
    )
    assert bad_cwd_res["success"] is False
    assert bad_cwd_res["error"] == "invalid_workspace_cwd"
    assert bad_cwd_res["process_status"] == ProcessStatus.CRASHED.value

    nul_cwd_res = await runner.execute_task_in_worktree(
        worktree_path="",
        prompt="test",
    )
    assert nul_cwd_res["error"] == "invalid_workspace_cwd"

    # Non-zero exit code from real subprocess preserves stdout, stderr, and exit_code
    fail_script = "import sys; sys.stdout.write('partial out\\n'); sys.stderr.write('syntax error\\n'); sys.exit(2)"
    nz_res = await runner.execute_task_in_worktree(
        worktree_path=tmp_path,
        prompt="",
        custom_command=(sys.executable, "-c", fail_script),
        attempt_id="att-nz-1",
        task_id="t1",
        run_id="r1",
        base_sha=BASE_SHA,
    )
    assert nz_res["success"] is False
    assert nz_res["exit_code"] == 2
    assert nz_res["process_status"] == ProcessStatus.EXITED.value
    assert "partial out" in nz_res["output"]
    assert "syntax error" in nz_res["stderr"]
    assert nz_res["failure"] is not None
    assert nz_res["failure"].code == "worker_nonzero_exit"

    # Persist the attempt and artifacts produced by WorkerRunner into ExecutionStore
    store = ExecutionStore(db_path=tmp_path / "runner_store.sqlite")
    run_spec = RunSpec(
        run_id="r1",
        project_id="p1",
        objective="Test runner + store integration",
        repo_root=str(tmp_path),
        base_sha=BASE_SHA,
        base_branch="main",
        idempotency_key="idemp-runner-store-0001",
        tasks=(
            TaskSpec(
                task_id="t1",
                run_id="r1",
                objective="Run subprocess",
                assigned_executor="custom",
                acceptance_criteria=(CheckSpec(check_id="c1", command=("python", "-V")),),
                allowed_paths=("out.txt",),
            ),
        ),
    )
    await store.save_run_atomic(run_spec)
    await store.save_attempt_atomic(nz_res["attempt"])
    loaded_att = await store.get_attempt("att-nz-1")
    assert loaded_att is not None
    assert loaded_att.exit_code == 2
    assert loaded_att.process_status == ProcessStatus.EXITED
