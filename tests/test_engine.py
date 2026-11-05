"""Unit tests for hydra_orch.engine and hydra_orch.bridge components."""

import os
import tempfile
import pytest
from hydra_orch.engine.decomposer import TaskDecomposer
from hydra_orch.engine.contract import ContractFirstEngine
from hydra_orch.engine.checkpointer import EngineCheckpointer, stitch_code_blocks
from hydra_orch.engine.healer import SelfHealer
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.bridge.worker_runner import WorkerRunner


def test_task_decomposer():
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


def test_contract_first_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        contracts_dir = os.path.join(tmpdir, "contracts")
        engine = ContractFirstEngine(contracts_dir=contracts_dir)
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("Test app")

        bundle = engine.generate_contract_bundle("Test app", tasks)
        assert os.path.isfile(os.path.join(contracts_dir, "CONTRACT.md"))
        assert os.path.isfile(os.path.join(contracts_dir, "openapi.json"))
        assert os.path.isfile(os.path.join(contracts_dir, "schema.prisma"))
        assert os.path.isfile(os.path.join(contracts_dir, "task_graph.json"))


def test_code_stitcher_overlap_elimination():
    # Part 1 ending with lines
    part1 = "def authenticate(user, password):\n    check_credentials(user)\n    token = generate_jwt(user)\n"
    # Part 2 repeating the last 2 lines
    part2 = "    check_credentials(user)\n    token = generate_jwt(user)\n    return token\n"

    stitched = stitch_code_blocks(part1, part2, max_check_lines=5)
    # Ensure check_credentials and token are not duplicated
    assert stitched.count("check_credentials(user)") == 1
    assert stitched.count("token = generate_jwt(user)") == 1
    assert "return token" in stitched


@pytest.mark.asyncio
async def test_engine_checkpointer_and_anchor():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "state.db")
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

        resume_prompt = cp.build_resume_prompt(sess["anchor_block"], target_file="src/math.py")
        assert "src/math.py" in resume_prompt
        assert "line_29" in resume_prompt


@pytest.mark.asyncio
async def test_omniroute_client_quota():
    client = OmniRouteClient()
    quota = await client.get_quota_status()
    assert "claude_pro" in quota
    assert quota["claude_pro"]["remaining_percent"] >= 0


def test_worker_runner_simulation():
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = WorkerRunner(default_cli="nonexistent_mock_cli")
        assert not runner.is_cli_installed("nonexistent_mock_cli")
