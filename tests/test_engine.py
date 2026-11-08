"""Unit tests for hydra_orch.engine and hydra_orch.bridge components."""

import os
import tempfile
import pytest
from hydra_orch.engine.decomposer import TaskDecomposer, LOCKED_DEPENDENCY_MANIFESTS
from hydra_orch.engine.contract import ContractFirstEngine
from hydra_orch.engine.checkpointer import EngineCheckpointer, stitch_code_blocks
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.bridge.worker_runner import WorkerRunner


def test_task_decomposer_and_two_wave_dag():
    decomposer = TaskDecomposer()
    macro = "Build a complete barbershop app with scheduling, payments and dashboard"
    tasks = decomposer.decompose(macro)

    assert len(tasks) == 4
    names = [t.name for t in tasks]
    assert "wt-backend" in names
    assert "wt-frontend" in names
    assert "wt-db-tests" in names
    assert "wt-docs" in names
    assert all(1 <= t.difficulty <= 10 for t in tasks)
    # Verify singular taxonomy 'migration/' and locked dependency manifests in Wave 1
    db_task = [t for t in tasks if t.name == "wt-db-tests"][0]
    assert "migration/" in db_task.target_files
    assert "migrations/" not in db_task.target_files
    assert "pyproject.toml" in db_task.forbidden_files

    # Verify Wave 0 + Wave 1 decomposition
    two_wave_tasks = decomposer.decompose(macro, include_wave_0=True)
    assert len(two_wave_tasks) == 5
    w0 = [t for t in two_wave_tasks if t.wave == 0]
    w1 = [t for t in two_wave_tasks if t.wave == 1]
    assert len(w0) == 1
    assert len(w1) == 4
    assert all(w0[0].id in t.dependencies for t in w1)


def test_contract_first_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        contracts_dir = os.path.join(tmpdir, "contract")
        engine = ContractFirstEngine(contracts_dir=contracts_dir)
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("Test app", include_wave_0=True)

        bundle = engine.generate_contract_bundle("Test app", tasks)
        assert os.path.isfile(os.path.join(contracts_dir, "CONTRACT.md"))
        assert os.path.isfile(os.path.join(contracts_dir, "openapi.json"))
        assert os.path.isfile(os.path.join(contracts_dir, "schema.prisma"))
        assert os.path.isfile(os.path.join(contracts_dir, "task_graph.json"))
        assert "ContractAmendmentRequest" in bundle["contract_md"]


def test_code_stitcher_overlap_elimination_and_indentation():
    part1 = "def authenticate(user, password):\n    check_credentials(user)\n    token = generate_jwt(user)\n"
    part2 = "    check_credentials(user)\n    token = generate_jwt(user)\n    return token\n"

    stitched = stitch_code_blocks(part1, part2, max_check_lines=5)
    assert stitched.count("check_credentials(user)") == 1
    assert stitched.count("token = generate_jwt(user)") == 1
    assert "return token" in stitched


@pytest.mark.asyncio
async def test_engine_checkpointer_and_anchor():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "checkpoints.sqlite")
        cp = EngineCheckpointer(db_path=db_path)
        await cp.initialize()

        sample_code = "\n".join([f"line_{i} = {i}" for i in range(30)])
        await cp.save_chunk(
            session_id="sess_101",
            model="architect_heavy",
            prompt="Write math functions",
            accumulated_content=sample_code,
        )

        sess = await cp.get_session("sess_101")
        assert sess is not None
        assert sess["model"] == "architect_heavy"
        assert "line_29 = 29" in sess["anchor_block"]

        resume_prompt = cp.build_resume_prompt(
            sess["anchor_block"], target_file="src/math.py", git_diff="+line_29 = 29"
        )
        assert "src/math.py" in resume_prompt
        assert "line_29" in resume_prompt
        assert "+line_29 = 29" in resume_prompt


@pytest.mark.asyncio
async def test_omniroute_client_quota_unknown_when_offline(monkeypatch):
    import httpx
    async def offline(*args, **kwargs):
        raise httpx.ConnectError("offline fixture")
    monkeypatch.setattr(httpx.AsyncClient, "get", offline)
    client = OmniRouteClient(quota_api_url="http://127.0.0.1:59999/api/usage/quota")
    quota = await client.get_quota_status()
    assert quota["status"] == "unknown"
    assert "claude_pro" in quota
    assert quota["claude_pro"]["status"] == "unknown"
    assert quota["claude_pro"]["remaining_percent"] is None


@pytest.mark.asyncio
async def test_worker_runner_missing_cli_vs_dry_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = WorkerRunner(default_cli="nonexistent_mock_cli_xyz")
        assert not runner.is_cli_installed("nonexistent_mock_cli_xyz")

        # Real execution with missing CLI must fail with executor_unavailable (GAP A02)
        res_real = await runner.execute_task_in_worktree(tmpdir, "Implement feature", dry_run=False)
        assert res_real["success"] is False
        assert res_real["error"] == "executor_unavailable"
        assert res_real["simulated"] is False

        # Explicit dry_run=True succeeds as marked simulation
        res_dry = await runner.execute_task_in_worktree(tmpdir, "Implement feature", dry_run=True)
        assert res_dry["success"] is True
        assert res_dry["simulated"] is True
