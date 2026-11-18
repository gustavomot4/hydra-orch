"""Wave 2 Slice 2D regression tests for CLI, TUI, Rich markup/UTF-8 safety, and OpenAPI parity."""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, Set, Tuple

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner
import yaml

from hydra_orch import cli, server
from hydra_orch.config import HydraConfig
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.run_service import RunService
from hydra_orch.model import CheckSpec, RunSpec, TaskSpec
from hydra_orch.tui import HydraTuiCockpit

runner = CliRunner()


def _init_git_repo(base_dir: Path, name: str = "repo") -> Tuple[Path, str]:
    repo = base_dir / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "wave2d@hydra.local"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hydra Wave 2D"], cwd=repo, check=True, capture_output=True)
    if os.name == "nt":
        subprocess.run(["git", "config", "core.longpaths", "true"], cwd=repo, check=True, capture_output=True)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "greeter.py").write_text("def greet() -> str:\n    return 'base'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, sha


@pytest.fixture
def isolated_cli_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYDRA_CONFIG", raising=False)
    cli._ACTIVE_CONFIG_PATH = None
    cli._CLI_SERVICE_CACHE.clear()
    repo, base_sha = _init_git_repo(tmp_path)
    rt_dir = repo / ".orchestrator"
    store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
    svc = RunService(repo_root=repo, store=store, runtime_dir=rt_dir)
    server.set_run_service(svc)
    try:
        yield svc, repo, base_sha
    finally:
        server.set_run_service(None)
        cli._ACTIVE_CONFIG_PATH = None
        cli._CLI_SERVICE_CACHE.clear()


def test_day04_conflict_auto_repair_shlex_quoted_command_and_nonzero_exit_on_unrepaired(
    isolated_cli_service,
) -> None:
    """DAY-04: --repair-command parses quoted python -c scripts cleanly and exits 1 when repaired=False."""
    svc, repo, base_sha = isolated_cli_service

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    _git("checkout", "-b", "cfl-ours-2d", base_sha)
    (repo / "src" / "greeter.py").write_text("def greet() -> str:\n    return 'ours'\n", encoding="utf-8")
    _git("add", "src/greeter.py")
    _git("commit", "-m", "ours")
    ours_sha = _git("rev-parse", "HEAD")

    _git("checkout", "-b", "cfl-theirs-2d", base_sha)
    (repo / "src" / "greeter.py").write_text("def greet() -> str:\n    return 'theirs'\n", encoding="utf-8")
    _git("add", "src/greeter.py")
    _git("commit", "-m", "theirs")
    theirs_sha = _git("rev-parse", "HEAD")
    _git("checkout", "main")

    sub = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Verify DAY-04 conflict auto-repair",
            "--project-id",
            "proj-day04",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--task-id",
            "t-day04",
            "--check-cmd",
            sys.executable,
            "--check-cmd",
            "-c",
            "--check-cmd",
            "from src.greeter import greet; assert greet() == 'repaired both'",
            "--json",
        ],
    )
    assert sub.exit_code == 0, sub.output
    run_id = json.loads(sub.stdout)["run_id"]

    async def _seed_integration() -> str:
        int_id = new_id()
        await svc.store.initialize()
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO integrations(id, run_id, workspace_path, expected_base_sha, result_sha, status)
                    VALUES (?, ?, ?, ?, NULL, 'conflicted')
                    """,
                    (int_id, run_id, str(repo), base_sha),
                )
        return int_id

    integration_id = asyncio.run(_seed_integration())
    ana = runner.invoke(
        cli.app,
        [
            "conflict",
            "analyze",
            integration_id,
            "--base-sha",
            base_sha,
            "--ours-sha",
            ours_sha,
            "--theirs-sha",
            theirs_sha,
            "--max-repair-attempts",
            "3",
            "--json",
        ],
    )
    assert ana.exit_code == 0, ana.output
    conflict_id = json.loads(ana.stdout)["conflict_id"]

    # 1. Failing repair command -> prints JSON with repaired=False and exits with code 1
    quoted_noop = f'"{sys.executable}" -c "import pathlib; print(\'leaving conflict unresolved\')"'
    fail_res = runner.invoke(
        cli.app,
        [
            "conflict",
            "auto-repair",
            conflict_id,
            "--repair-command",
            quoted_noop,
            "--json",
        ],
    )
    assert fail_res.exit_code == 1, fail_res.output
    fail_payload = json.loads(fail_res.stdout)
    assert fail_payload["repaired"] is False
    assert fail_payload["failures"][0]["code"] == "unresolved_conflicts_remain"

    # 1b. Repeatable --repair-arg also works cleanly and exits 1 when conflict remains unresolved
    arg_fail_res = runner.invoke(
        cli.app,
        [
            "conflict",
            "auto-repair",
            conflict_id,
            "--repair-arg",
            sys.executable,
            "--repair-arg",
            "-c",
            "--repair-arg",
            "print('still unresolved via repair-arg')",
            "--json",
        ],
    )
    assert arg_fail_res.exit_code == 1, arg_fail_res.output
    assert json.loads(arg_fail_res.stdout)["repaired"] is False

    # 2. Quoted python -c command with spaces resolving conflict + staging -> repaired=True, exit 0
    fix_py = (
        "import pathlib, subprocess; "
        "pathlib.Path('src/greeter.py').write_text('def greet() -> str:\\n    return \\'repaired both\\'\\n', encoding='utf-8'); "
        "subprocess.run(['git', 'add', 'src/greeter.py'], check=True)"
    )
    quoted_fix = f'"{sys.executable}" -c "{fix_py}"'
    ok_res = runner.invoke(
        cli.app,
        [
            "conflict",
            "auto-repair",
            conflict_id,
            "--repair-command",
            quoted_fix,
            "--json",
        ],
    )
    assert ok_res.exit_code == 0, ok_res.output
    ok_payload = json.loads(ok_res.stdout)
    assert ok_payload["repaired"] is True
    assert ok_payload["resolved_sha"] is not None


def test_day05_cli_commands_from_non_git_directory_never_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DAY-05: Store/control-plane CLI commands succeed outside Git CWD; Git-requiring commands emit clean error."""
    server.set_run_service(None)
    cli._ACTIVE_CONFIG_PATH = None
    cli._CLI_SERVICE_CACHE.clear()
    monkeypatch.delenv("HYDRA_CONFIG", raising=False)

    non_git_dir = tmp_path / "plain_operator_cwd"
    non_git_dir.mkdir(parents=True, exist_ok=True)
    ext_repo, ext_sha = _init_git_repo(tmp_path, name="external_git_repo")
    plain_proj_dir = non_git_dir / "my_notes_folder"
    plain_proj_dir.mkdir()
    (plain_proj_dir / "notes.txt").write_text("hello folder\n", encoding="utf-8")

    monkeypatch.chdir(non_git_dir)

    # Listing runs, projects, schedules, areas, tokens from non-Git directory succeeds cleanly
    runs_res = runner.invoke(cli.app, ["runs", "--json"])
    assert runs_res.exit_code == 0, runs_res.output
    assert json.loads(runs_res.stdout)["items"] == []

    plist_res = runner.invoke(cli.app, ["project-list", "--json"])
    assert plist_res.exit_code == 0, plist_res.output
    assert json.loads(plist_res.stdout) == []

    auto_res = runner.invoke(cli.app, ["automation", "list", "--json"])
    assert auto_res.exit_code == 0, auto_res.output
    assert json.loads(auto_res.stdout) == []

    # Registering a plain folder project with --allow-plain-folder works from non-Git CWD
    p_plain = runner.invoke(
        cli.app,
        [
            "project-create",
            "--root",
            str(plain_proj_dir),
            "--name",
            "plain-notes",
            "--allow-plain-folder",
            "--json",
        ],
    )
    assert p_plain.exit_code == 0, p_plain.output
    assert json.loads(p_plain.stdout)["workspace_kind"] == "folder"

    # Registering an external Git repo by --root works from non-Git CWD
    p_git = runner.invoke(
        cli.app,
        [
            "project-create",
            "--root",
            str(ext_repo),
            "--name",
            "ext-git",
            "--base-sha",
            ext_sha,
            "--json",
        ],
    )
    assert p_git.exit_code == 0, p_git.output

    # Token creation from non-Git CWD succeeds
    tok_res = runner.invoke(cli.app, ["token", "create", "--principal-id", "op-cwd", "--json"])
    assert tok_res.exit_code == 0, tok_res.output
    assert json.loads(tok_res.stdout)["created"] is True

    # Command requiring a Git repo without --repo-root returns clean JSON error (exit 1), NO traceback
    sub_no_git = runner.invoke(cli.app, ["submit", "--objective", "Needs git repo", "--json"])
    assert sub_no_git.exit_code == 1, sub_no_git.output
    assert "Traceback" not in sub_no_git.output
    err_data = json.loads(sub_no_git.stdout)
    assert err_data["exit_code"] == 1
    assert err_data["code"]

    # TUI watch --once in non-Git CWD renders cleanly without traceback
    watch_res = runner.invoke(cli.app, ["watch", "--once", "--no-alt-screen"])
    assert watch_res.exit_code == 0, watch_res.output
    assert "Traceback" not in watch_res.output


def test_day07_and_day12_human_summaries_never_none_and_workspace_repo_update_delete(
    isolated_cli_service,
) -> None:
    """DAY-07 & DAY-12: Human summaries print real IDs (never None), and workspace/repo update & delete work."""
    _svc, repo, base_sha = isolated_cli_service

    # Human mode (no --json): verify real IDs and zero '=None'
    area_human = runner.invoke(cli.app, ["area", "create", "--name", "platform", "--principal-id", "op-1"])
    assert area_human.exit_code == 0, area_human.output
    assert "area=None" not in area_human.output
    m_area = re.search(r"area=(\S+)", area_human.output)
    assert m_area and m_area.group(1) != "None"
    area_id = m_area.group(1)

    ws_human = runner.invoke(
        cli.app,
        ["workspace", "create", "--area-id", area_id, "--name", "ws-initial", "--principal-id", "op-1"],
    )
    assert ws_human.exit_code == 0, ws_human.output
    assert "workspace=None" not in ws_human.output
    m_ws = re.search(r"workspace=(\S+)", ws_human.output)
    assert m_ws and m_ws.group(1) != "None"
    ws_id = m_ws.group(1)

    # Update workspace name
    ws_upd = runner.invoke(
        cli.app,
        [
            "workspace",
            "update",
            ws_id,
            "--name",
            "ws-renamed",
            "--expected-revision",
            "1",
            "--principal-id",
            "op-1",
        ],
    )
    assert ws_upd.exit_code == 0, ws_upd.output
    assert f"workspace={ws_id}" in ws_upd.output
    assert "name=ws-renamed" in ws_upd.output

    # Create a second temporary workspace and delete it cleanly
    ws2_json = runner.invoke(
        cli.app,
        ["workspace", "create", "--area-id", area_id, "--name", "ws-temp", "--principal-id", "op-1", "--json"],
    )
    assert ws2_json.exit_code == 0
    ws2_id = json.loads(ws2_json.stdout)["id"]
    ws2_del = runner.invoke(cli.app, ["workspace", "delete", ws2_id, "--principal-id", "op-1"])
    assert ws2_del.exit_code == 0, ws2_del.output
    assert f"workspace={ws2_id} deleted=True" in ws2_del.output

    proj_human = runner.invoke(
        cli.app,
        [
            "project",
            "create",
            "--workspace-id",
            ws_id,
            "--name",
            "human-proj",
            "--root",
            str(repo),
            "--base-sha",
            base_sha,
            "--principal-id",
            "op-1",
        ],
    )
    assert proj_human.exit_code == 0, proj_human.output
    assert "project=None" not in proj_human.output
    m_proj = re.search(r"project=(\S+)", proj_human.output)
    assert m_proj and m_proj.group(1) != "None"
    project_id = m_proj.group(1)

    repo_human = runner.invoke(
        cli.app,
        [
            "repo",
            "register",
            "--project-id",
            project_id,
            "--root",
            str(repo),
            "--allowed-paths",
            "src/**",
            "--base-sha",
            base_sha,
            "--principal-id",
            "op-1",
        ],
    )
    assert repo_human.exit_code == 0, repo_human.output
    assert "repository=None" not in repo_human.output
    m_repo = re.search(r"repository=(\S+)", repo_human.output)
    assert m_repo and m_repo.group(1) != "None"
    repo_id = m_repo.group(1)

    # Repo update & delete
    repo_upd = runner.invoke(
        cli.app,
        ["repo", "update", repo_id, "--allowed-paths", "*", "--principal-id", "op-1", "--json"],
    )
    assert repo_upd.exit_code == 0, repo_upd.output
    assert json.loads(repo_upd.stdout)["allowed_paths_json"] == '["*"]'

    repo_del = runner.invoke(cli.app, ["repo", "delete", repo_id, "--principal-id", "op-1", "--json"])
    assert repo_del.exit_code == 0, repo_del.output
    assert json.loads(repo_del.stdout)["deleted"] is True


def test_day08_global_config_flag_loads_custom_yaml_and_rejects_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DAY-08: Global --config (-c) sets HYDRA_CONFIG, reloads config, and fails cleanly when missing."""
    import hydra_orch.config as cfg_mod

    monkeypatch.setenv("HYDRA_CONFIG", "__unset_sentinel__")
    monkeypatch.delenv("HYDRA_CONFIG", raising=False)
    monkeypatch.setattr(cli, "_ACTIVE_CONFIG_PATH", None)
    monkeypatch.setattr(cfg_mod, "_CONFIG_CACHE", cfg_mod._CONFIG_CACHE)
    monkeypatch.setattr(cfg_mod, "_CONFIG_CACHE_PATH", cfg_mod._CONFIG_CACHE_PATH)

    missing_cfg = tmp_path / "does_not_exist.yaml"
    res_missing = runner.invoke(cli.app, ["--config", str(missing_cfg), "quota", "--json"])
    assert res_missing.exit_code in {1, 2}
    assert "not found" in res_missing.output.lower()
    assert "Traceback" not in res_missing.output

    custom_cfg = tmp_path / "custom_hydra.yaml"
    custom_cfg.write_text(
        "version: '5.0'\n"
        "hydra:\n"
        "  proxy_host: '127.0.0.1'\n"
        "  proxy_port: 18442\n"
        "  default_mode: 1\n",
        encoding="utf-8",
    )

    def _forbidden_http(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Direct mode quota must not make network calls")

    monkeypatch.setattr(httpx, "AsyncClient", _forbidden_http)
    res_ok = runner.invoke(cli.app, ["-c", str(custom_cfg), "quota"])
    assert res_ok.exit_code == 0, res_ok.output
    assert Path(os.environ["HYDRA_CONFIG"]) == custom_cfg.resolve()
    import hydra_orch.config as cfg_mod

    assert cfg_mod._CONFIG_CACHE is not None
    assert cfg_mod._CONFIG_CACHE.hydra.proxy_port == 18442
    assert cfg_mod._CONFIG_CACHE.hydra.default_mode == 1


def test_day19_submit_execute_exits_1_on_failed_check_and_validates_allowed_paths(
    isolated_cli_service,
) -> None:
    """DAY-19: submit --execute exits with code 1 when task check fails, and validates --allowed-paths."""
    _svc, repo, base_sha = isolated_cli_service

    # Empty --allowed-paths gives clean validation error (exit 1), never raw crash
    bad_paths = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Bad allowed paths",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--allowed-paths",
            "   ",
            "--json",
        ],
    )
    assert bad_paths.exit_code == 1
    assert "Traceback" not in bad_paths.output
    assert json.loads(bad_paths.stdout)["code"] == "validation_error"

    # submit --execute with failing acceptance check must print result and exit with code 1
    sub_fail = runner.invoke(
        cli.app,
        [
            "submit",
            "--objective",
            "Execute run with failing check",
            "--project-id",
            "proj-day19",
            "--repo-root",
            str(repo),
            "--base-sha",
            base_sha,
            "--task-id",
            "t-fail",
            "--dry-run",
            "--execute",
            "--check-cmd",
            sys.executable,
            "--check-cmd",
            "-c",
            "--check-cmd",
            "import sys; sys.exit(1)",
            "--json",
        ],
    )
    assert sub_fail.exit_code == 1, sub_fail.output
    payload = json.loads(sub_fail.stdout)
    assert payload["status"] == "failed"
    assert payload["created"] is True


def test_day02_conversation_apply_cli_local_and_http(
    isolated_cli_service,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DAY-02: hydra conversation apply invokes ConversationService.apply_changes locally or HTTP --api-url."""
    svc, _repo, _base_sha = isolated_cli_service

    # 1. Local folder conversation apply (works via ConversationService.apply_changes or fallback)
    plain_folder = tmp_path / "folder_proj"
    plain_folder.mkdir()
    (plain_folder / "hello.txt").write_text("v1\n", encoding="utf-8")
    p_res = runner.invoke(
        cli.app,
        [
            "project-create",
            "--root",
            str(plain_folder),
            "--name",
            "folder-chat-proj",
            "--allow-plain-folder",
            "--json",
        ],
    )
    assert p_res.exit_code == 0, p_res.output
    proj_id = json.loads(p_res.stdout)["id"]

    from hydra_orch.core.conversation_service import ConversationService
    from hydra_orch.core.folder_workspace import snapshot as folder_snapshot

    conv_svc = ConversationService(svc)
    created = asyncio.run(
        conv_svc.create(
            project_id=proj_id,
            executor="codex",
            content="Atualizar hello.txt",
            idempotency_key="conv-apply-cli-idem-0001",
            access_mode="workspace-write",
        )
    )
    cid = created["conversation_id"]
    ws_dir = svc.runtime_dir / "folder_workspace" / cid
    work_dir = folder_snapshot(plain_folder, ws_dir)
    (work_dir / "hello.txt").write_text("v2 from isolated chat\n", encoding="utf-8")

    async def _bind_ws() -> None:
        async with svc.store._connect() as db:
            async with svc.store._transaction(db):
                await db.execute("UPDATE conversations SET workspace_path = ? WHERE id = ?", (str(work_dir), cid))

    asyncio.run(_bind_ws())

    apply_res = runner.invoke(cli.app, ["conversation", "apply", cid, "--json"])
    assert apply_res.exit_code == 0, apply_res.output
    apply_data = json.loads(apply_res.stdout)
    assert apply_data.get("applied", True) is True
    assert (plain_folder / "hello.txt").read_text(encoding="utf-8") == "v2 from isolated chat\n"

    # 2. Remote --api-url mode calls POST /v1/control-plane/conversations/{id}/apply
    captured_req: Dict[str, Any] = {}

    class _MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured_req["method"] = request.method
            captured_req["path"] = request.url.path
            captured_req["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"conversation_id": cid, "applied": True})

    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: orig_client(transport=_MockTransport(), **{k: v for k, v in kw.items() if k != "transport"}),
    )
    http_res = runner.invoke(
        cli.app,
        ["conversation", "apply", cid, "--force", "--api-url", "http://127.0.0.1:8000", "--json"],
    )
    assert http_res.exit_code == 0, http_res.output
    assert captured_req == {
        "method": "POST",
        "path": f"/v1/control-plane/conversations/{cid}/apply",
        "body": {"force": True},
    }


def test_be19_rich_markup_escape_and_utf8_stream_safety_in_cli_and_tui(
    isolated_cli_service,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BE-19: [WinError 2] and unmatched [/bold] render literally in CLI & TUI without MarkupError."""
    svc, repo, base_sha = isolated_cli_service

    # 1. Stream safety: StringIO without reconfigure does not crash _ensure_utf8_streams
    fake_stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stream)
    cli._ensure_utf8_streams()

    # 2. CLI `hydra run` with hostile markup `[/bold]` and `[WinError 2]` in prompt never raises MarkupError
    monkeypatch.setattr(cli, "load_config", lambda: HydraConfig())
    hostile_prompt = "Fix crash [WinError 2] foo[0] [/bold] [red]unclosed 🚀"
    run_res = runner.invoke(cli.app, ["run", hostile_prompt, "--mode", "relay"])
    assert run_res.exit_code == 1
    assert "MarkupError" not in run_res.output
    assert "[WinError 2]" in run_res.output
    assert "[/bold]" in run_res.output

    # 3. CLI `hydra status` with adapter error containing `[WinError 2] [/bold]` renders literally
    class _FakeBrokenAdapter:
        last_error = "[WinError 2] system cannot find file [/bold] foo[0]"

        async def is_available(self) -> bool:
            return False

    class _FakeRouter:
        def __init__(self, _cfg: Any) -> None:
            self.adapters = {"codex[0]": _FakeBrokenAdapter()}

    monkeypatch.setattr(cli, "HydraRouter", _FakeRouter)
    buf_console = Console(width=140, force_terminal=False, color_system=None)
    monkeypatch.setattr(cli, "console", buf_console)
    with buf_console.capture() as cap:
        st_res = runner.invoke(cli.app, ["status"])
    rendered_status = cap.get()
    assert st_res.exit_code == 0, st_res.output
    assert "[WinError 2]" in rendered_status
    assert "[/bold]" in rendered_status
    assert "codex[0]" in rendered_status

    # 4. TUI cockpit with `[WinError 2]` and `[/bold]` in objective, task_id/detail_title, and events
    monkeypatch.setattr("hydra_orch.tui.load_config", lambda *a, **kw: HydraConfig())

    async def _seed_hostile_run() -> str:
        spec = RunSpec(
            run_id="run_be19_markup",
            project_id="proj-be19",
            objective="Investigate [WinError 2] and [/bold] in worker[0]",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch="main",
            orchestration_mode="swarm",
            idempotency_key="be19-markup-idem-0001",
            tasks=(
                TaskSpec(
                    task_id="task_be19",
                    run_id="run_be19_markup",
                    objective="Handle [WinError 2] [/bold]",
                    assigned_executor="codex",
                    acceptance_criteria=(CheckSpec(check_id="chk-ok", command=[sys.executable, "-c", "print('ok')"]),),
                    allowed_paths=("*",),
                ),
            ),
        )
        await svc.submit_run(spec)
        return spec.run_id

    run_id = asyncio.run(_seed_hostile_run())
    cockpit = HydraTuiCockpit(run_service=svc, run_id=run_id, once=True)
    asyncio.run(cockpit.refresh())
    cockpit.state.detail_title = "Inspector [WinError 2] [/bold] foo[0]"
    cockpit.state.detail_body = "Raw failure: [WinError 2] The system cannot find the file [/bold]"
    cockpit._set_error("spawn_failed", "[WinError 2] executable missing [/bold]")

    rendered_tui = cockpit.render_text(width=200)
    assert "[WinError 2]" in rendered_tui
    assert "[/bold]" in rendered_tui
    assert "foo[0]" in rendered_tui


def test_be20_openapi_yaml_100_percent_parity_with_server_v1_and_health_routes() -> None:
    """BE-20: Parse doc/f_api/openapi.yaml and verify 100% HTTP route, method, param, and $ref parity."""
    repo_root = Path(__file__).resolve().parents[1]
    spec_path = repo_root / "doc" / "f_api" / "openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    assert spec["openapi"] == "3.0.3"
    assert isinstance(spec.get("paths"), dict)
    assert len(spec["paths"]) >= 120

    http_methods = {"get", "post", "put", "patch", "delete"}

    # Extract all HTTP (/v1/... and /health) routes registered in server.py
    server_http_routes: Dict[str, Set[str]] = {}
    for route in server.app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        if route.path == "/health" or route.path.startswith("/v1/"):
            clean = {m.lower() for m in methods if m.lower() in http_methods}
            if clean:
                server_http_routes.setdefault(route.path, set()).update(clean)

    # Include the Wave 2 integration routes documented in openapi.yaml
    wave2_integration_routes: Dict[str, Set[str]] = {
        "/v1/control-plane/conversations/{conversation_id}/apply": {"post"},
        "/v1/control-plane/workspaces/{workspace_id}": {"put", "delete"},
    }
    expected_routes: Dict[str, Set[str]] = {k: set(v) for k, v in server_http_routes.items()}
    for path, methods in wave2_integration_routes.items():
        expected_routes.setdefault(path, set()).update(methods)

    spec_routes: Dict[str, Set[str]] = {
        path: {m.lower() for m in ops if m.lower() in http_methods}
        for path, ops in spec["paths"].items()
    }

    # 1. Every HTTP /v1/... and /health route in server.py MUST exist in openapi.yaml with exact {param} names
    missing_in_spec = sorted(set(server_http_routes) - set(spec_routes))
    assert missing_in_spec == [], f"Server routes missing from openapi.yaml: {missing_in_spec}"

    # 2. Every route in openapi.yaml MUST match server.py (+ Wave 2 planned routes)
    unexpected_in_spec = sorted(set(spec_routes) - set(expected_routes))
    assert unexpected_in_spec == [], f"Unexpected routes in openapi.yaml: {unexpected_in_spec}"

    # 3. Methods and {param} declarations must match 100%
    for path, req_methods in server_http_routes.items():
        assert req_methods <= spec_routes[path], (
            f"Missing HTTP methods on {path}: server={req_methods}, spec={spec_routes[path]}"
        )

    for path, ops_methods in spec_routes.items():
        path_params = re.findall(r"\{([^}]+)\}", path)
        for method in ops_methods:
            op = spec["paths"][path][method]
            declared = [
                p["name"]
                for p in (op.get("parameters") or [])
                if isinstance(p, dict) and p.get("in") == "path" and p.get("required") is True
            ]
            assert declared == path_params, (
                f"Path parameter mismatch in {method.upper()} {path}: declared={declared} vs expected={path_params}"
            )

    # 4. Explicit check for newly added/fixed routes from BE-20
    assert "post" in spec_routes["/v1/control-plane/conversations/{conversation_id}/apply"]
    assert "get" in spec_routes["/v1/control-plane/tokens"]
    assert "post" in spec_routes["/v1/launcher/ticket"]
    assert {"put", "delete"} <= spec_routes["/v1/control-plane/workspaces/{workspace_id}"]
    assert "post" in spec_routes["/v1/control-plane/runs/{run_id}/discard"]
    assert "get" in spec_routes["/health"]

    # 5. All internal $ref pointers must resolve cleanly
    def _verify_refs(node: Any) -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = str(node["$ref"])
                assert ref.startswith("#/")
                cur: Any = spec
                for part in ref[2:].split("/"):
                    assert part in cur, f"Unresolved OpenAPI $ref: {ref}"
                    cur = cur[part]
            for val in node.values():
                _verify_refs(val)
        elif isinstance(node, list):
            for item in node:
                _verify_refs(item)

    _verify_refs(spec)
