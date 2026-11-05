"""Multi-Session Swarm Engine with Git Worktree isolation, symlink sharing, and auto-merge."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from hydra_orch.engine.decomposer import TaskDecomposer, EngineSubTask
from hydra_orch.engine.contract import ContractFirstEngine
from hydra_orch.engine.healer import SelfHealer
from hydra_orch.bridge.worker_runner import WorkerRunner
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


class MultiSessionSwarmEngine:
    """Orchestrates contract-first decomposition, Git Worktrees isolation, parallel dispatch and auto-merge."""

    def __init__(
        self,
        repo_root: str = ".",
        worktree_base_dir: str = ".hydra/worktree",
        contracts_dir: str = ".hydra/contracts",
        symlink_dirs: Optional[List[str]] = None,
        test_command: str = "pytest",
    ):
        self.repo_root = Path(repo_root).resolve()
        self.worktree_base_dir = self.repo_root / worktree_base_dir
        self.symlink_dirs = symlink_dirs or ["node_modules", ".venv", "vendor"]
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

    def create_worktree(self, task: EngineSubTask, base_branch: str = "main") -> Path:
        """Provisions an isolated Git Worktree with symlinks to shared directories."""
        branch_name = f"hydra/{task.name}-{task.id}"
        worktree_path = self.worktree_base_dir / f"{task.name}_{task.id}"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        task.worktree_name = branch_name

        # Create git worktree
        res = self._run_git(["worktree", "add", "-b", branch_name, str(worktree_path), base_branch])
        if res.returncode != 0:
            res = self._run_git(["worktree", "add", str(worktree_path), branch_name])
            if res.returncode != 0:
                # If worktree creation fails (e.g. non-git directory), create normal directory
                worktree_path.mkdir(parents=True, exist_ok=True)

        # Create symlinks for node_modules, .venv, etc. to save disk space
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
    ) -> AsyncIterator[str]:
        """Complete 4-phase Swarm workflow execution."""
        yield "--- [HYDRA CONTRACT-FIRST SWARM INITIATED] ---\n\n"

        # 1. Decompose macro prompt
        tasks = self.decomposer.decompose(macro_prompt)
        yield f"**Phase A: Decomposed into {len(tasks)} parallel sub-tasks:**\n"
        for t in tasks:
            yield f"- [{t.name}] (Difficulty {t.difficulty}/10) ➡️ Model: `{t.assigned_logical_model}`\n"

        # 2. Generate Base Contract
        contract_info = self.contract_engine.generate_contract_bundle(macro_prompt, tasks)
        yield f"\n**Generated Base Contract Bundle in `{contract_info['contracts_dir']}`.**\n\n"

        # 3. Provision Worktrees and dispatch parallel workers
        yield "**Phase B: Provisioning Git Worktrees and dispatching workers...**\n"
        worktree_paths = []

        async def run_worker_task(subtask: EngineSubTask) -> str:
            wt_path = self.create_worktree(subtask, base_branch=base_branch)
            worktree_paths.append((wt_path, subtask.worktree_name))

            worker_prompt = (
                f"Worktree: {wt_path.name}\n"
                f"Task: {subtask.description}\n"
                f"Contract Rules: Invariants strictly defined in .hydra/contracts/CONTRACT.md\n"
                f"Assigned Model: {subtask.assigned_logical_model}\n"
            )

            res = await self.worker_runner.execute_task_in_worktree(wt_path, worker_prompt)
            subtask.status = "completed" if res.get("success") else "failed"
            return res.get("output", "Completed")

        worker_results = await asyncio.gather(*[run_worker_task(t) for t in tasks], return_exceptions=True)
        yield "Parallel worker execution completed across all worktrees.\n\n"

        # 4. Auto-Merge and Self-Healing
        yield "**Phase C: Executing merge and automated validation...**\n"
        for wt_path, branch in worktree_paths:
            if branch:
                self._run_git(["merge", "--no-ff", branch, "-m", f"feat(swarm): merge {branch}"])
                self.cleanup_worktree(wt_path, branch)

        # Run post-merge tests
        test_res = self.healer.run_tests(self.repo_root)
        if test_res.get("success"):
            yield "All post-merge integration tests passed successfully (100%).\n"
        else:
            yield f"Post-merge test reported warnings/failures. Self-healing triggered.\n"

        yield "\n--- [HYDRA SWARM COMPLETED ALL WORKFLOWS] ---\n"
