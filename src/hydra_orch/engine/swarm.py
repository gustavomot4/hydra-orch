"""Multi-Session Swarm Engine with Two-Wave execution (Wave 0 Foundation + Wave 1 Parallel Worktrees)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import AsyncIterator, List, Optional
from hydra_orch.engine.decomposer import TaskDecomposer, EngineSubTask
from hydra_orch.engine.contract import ContractFirstEngine
from hydra_orch.engine.healer import SelfHealer
from hydra_orch.bridge.worker_runner import WorkerRunner
from hydra_orch.bridge.omniroute_client import OmniRouteClient

logger = logging.getLogger(__name__)


class MultiSessionSwarmEngine:
    """Orchestrates Wave 0 compilable foundation, Wave 1 Git Worktree isolation, parallel dispatch and merge."""

    def __init__(
        self,
        repo_root: str = ".",
        worktree_base_dir: str = ".orchestrator/worktree",
        contracts_dir: str = ".orchestrator/contract",
        symlink_dirs: Optional[List[str]] = None,
        test_command: str = "pytest",
        max_parallel_worktrees: int = 4,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.worktree_base_dir = self.repo_root / worktree_base_dir
        self.symlink_dirs = symlink_dirs or ["node_modules", ".venv", "vendor"]
        self.max_parallel_worktrees = max_parallel_worktrees
        self.decomposer = TaskDecomposer()
        self.contract_engine = ContractFirstEngine(contracts_dir=contracts_dir)
        self.worker_runner = WorkerRunner()
        self.omniroute = OmniRouteClient()
        self.healer = SelfHealer(test_command=test_command, omniroute_client=self.omniroute)

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        target_dir = str(cwd or self.repo_root)
        return subprocess.run(
            ["git"] + args,
            cwd=target_dir,
            capture_output=True,
            text=True,
        )

    def create_worktree(self, task: EngineSubTask, base_branch: str = "main", allow_fallback_dir: bool = False) -> Path:
        """Provisions an isolated Git Worktree with symlinks to shared directories (read-only manifests in Wave 1)."""
        branch_name = f"hydra/{task.name}-{task.id}"
        worktree_path = self.worktree_base_dir / f"{task.name}_{task.id}"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        task.worktree_name = branch_name

        # Create git worktree
        res = self._run_git(["worktree", "add", "-b", branch_name, str(worktree_path), base_branch])
        if res.returncode != 0:
            res = self._run_git(["worktree", "add", str(worktree_path), branch_name])
            if res.returncode != 0:
                if allow_fallback_dir:
                    worktree_path.mkdir(parents=True, exist_ok=True)
                else:
                    raise RuntimeError(
                        f"Failed to create real Git worktree at {worktree_path} (GAP A06): {res.stderr.strip()}"
                    )

        # Create symlinks for node_modules, .venv, etc. (Wave 1 tasks forbid modifying dependency manifests)
        for sdir in self.symlink_dirs:
            src_link = self.repo_root / sdir
            dst_link = worktree_path / sdir
            if src_link.exists() and not dst_link.exists():
                try:
                    os.symlink(src_link, dst_link, target_is_directory=True)
                except (OSError, NotImplementedError):
                    pass

        return worktree_path

    def cleanup_worktree(self, worktree_path: Path, branch_name: Optional[str] = None) -> None:
        """Removes worktree directory and prunes git records."""
        if worktree_path.exists():
            self._run_git(["worktree", "remove", "--force", str(worktree_path)])
            self._run_git(["worktree", "prune"])
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)

    async def execute_swarm(
        self,
        macro_prompt: str,
        base_branch: str = "main",
        dry_run: bool = False,
    ) -> AsyncIterator[str]:
        """Complete Two-Wave (Wave 0 Foundation + Wave 1 Parallel Swarm) workflow execution."""
        yield "--- [HYDRA TWO-WAVE CONTRACT-FIRST SWARM INITIATED] ---\n\n"

        # 1. Decompose macro prompt into Wave 0 + Wave 1
        tasks = self.decomposer.decompose(macro_prompt, include_wave_0=True)
        wave_0_tasks = [t for t in tasks if t.wave == 0]
        wave_1_tasks = [t for t in tasks if t.wave == 1]

        yield f"**Wave 0 (Compilable Foundation):** {len(wave_0_tasks)} task(s)\n"
        yield f"**Wave 1 (Parallel Swarm):** {len(wave_1_tasks)} task(s) (Concurrency cap: {self.max_parallel_worktrees})\n"
        for t in wave_1_tasks:
            yield f"- [{t.name}] (Difficulty {t.difficulty}/10) ➡️ Model: `{t.assigned_logical_model}`\n"

        # 2. Generate Wave 0 Base Contract Bundle
        contract_info = self.contract_engine.generate_contract_bundle(macro_prompt, tasks)
        yield f"\n**Generated Wave 0 Contract Bundle in `{contract_info['contracts_dir']}`.**\n\n"

        # 3. Provision Worktrees and dispatch Wave 1 workers with concurrency semaphore
        yield "**Wave 1: Provisioning Git Worktrees and dispatching parallel workers...**\n"
        semaphore = asyncio.Semaphore(self.max_parallel_worktrees)
        worktree_records = []

        async def run_worker_task(subtask: EngineSubTask) -> bool:
            async with semaphore:
                wt_path = self.create_worktree(subtask, base_branch=base_branch, allow_fallback_dir=dry_run)
                worktree_records.append((subtask, wt_path, subtask.worktree_name))

                worker_prompt = (
                    f"Worktree: {wt_path.name}\n"
                    f"Task: {subtask.description}\n"
                    f"Contract Rules: Invariants strictly defined in .orchestrator/contract/CONTRACT.md\n"
                    f"Forbidden Files (Wave 1 Lock): {', '.join(subtask.forbidden_files)}\n"
                    f"Assigned Model: {subtask.assigned_logical_model}\n"
                )

                res = await self.worker_runner.execute_task_in_worktree(
                    wt_path, worker_prompt, dry_run=dry_run
                )
                is_ok = bool(res.get("success")) and not bool(res.get("simulated") and not dry_run)
                subtask.status = "completed" if is_ok else "failed"
                return is_ok

        await asyncio.gather(*[run_worker_task(t) for t in wave_1_tasks], return_exceptions=True)
        yield "Parallel worker execution completed across all worktrees.\n\n"

        # 4. Auto-Merge only verified tasks and preserve failed worktrees
        yield "**Integration Phase: Validating task outcomes and executing serialized merge...**\n"
        for subtask, wt_path, branch in worktree_records:
            if subtask.status == "completed" and branch:
                merge_res = self._run_git(["merge", "--no-ff", branch, "-m", f"feat(swarm): merge {branch}"])
                if merge_res.returncode == 0:
                    self.cleanup_worktree(wt_path, branch)
                else:
                    self._run_git(["merge", "--abort"])
                    yield f"- Conflict merging `{branch}`; preserving worktree at `{wt_path}`.\n"
            else:
                yield f"- Skipping merge for `{subtask.name}` (status={subtask.status}); worktree preserved.\n"

        test_res = self.healer.run_tests(self.repo_root)
        if test_res.get("success"):
            yield "All post-merge integration tests passed successfully (100%).\n"
        else:
            yield "Post-merge test reported failures; preserving artifacts for inspection/repair.\n"

        yield "\n--- [HYDRA SWARM COMPLETED ALL WORKFLOWS] ---\n"
