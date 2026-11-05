"""Swarm mode orchestrator with Git Worktree isolation and parallel session distribution."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    description: str
    complexity: int  # 1 to 10
    target_files: List[str] = Field(default_factory=list)
    preferred_provider: Optional[str] = None
    branch_name: Optional[str] = None
    worktree_path: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    result_summary: Optional[str] = None


class BaseContract(BaseModel):
    """Immutable contract shared among all swarm worktrees."""
    api_schemas: str = ""
    file_boundaries: Dict[str, List[str]] = Field(default_factory=dict)
    rules: List[str] = Field(default_factory=list)


class SwarmOrchestrator:
    """Manages macro task decomposition, Git Worktree isolation, parallel LLM execution and merge."""

    def __init__(
        self,
        repo_root: str = ".",
        worktrees_base_dir: str = ".orchestrator/worktree",
        contract_path: str = ".orchestrator/CONTRACT.md",
        test_command: str = "pytest",
    ):
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_base_dir = self.repo_root / worktrees_base_dir
        self.contract_path = self.repo_root / contract_path
        self.test_command = test_command

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        target_dir = str(cwd or self.repo_root)
        return subprocess.run(
            ["git"] + args,
            cwd=target_dir,
            capture_output=True,
            text=True,
        )

    def is_git_repo(self) -> bool:
        res = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return res.returncode == 0

    def decompose_prompt(self, macro_prompt: str) -> List[SubTask]:
        """Decomposes a macro prompt into parallelizable sub-tasks categorized by complexity."""
        # Baseline heuristic decomposition (can also be enhanced via an LLM call)
        tasks = [
            SubTask(
                name="models_and_schemas",
                description=f"Define core data models, DB schemas, and typed contracts for: {macro_prompt[:120]}",
                complexity=8,
                target_files=["src/models.py", "src/schemas.py"],
            ),
            SubTask(
                name="core_backend_logic",
                description=f"Implement backend services, business logic and API endpoints for: {macro_prompt[:120]}",
                complexity=7,
                target_files=["src/services.py", "src/api.py"],
            ),
            SubTask(
                name="frontend_or_cli_interface",
                description=f"Build presentation layer / CLI / UI components for: {macro_prompt[:120]}",
                complexity=5,
                target_files=["src/ui.py", "src/cli.py"],
            ),
            SubTask(
                name="test_suite_and_docs",
                description=f"Write comprehensive automated unit/integration tests and docs for: {macro_prompt[:120]}",
                complexity=4,
                target_files=["tests/test_app.py", "README.md"],
            ),
        ]
        return tasks

    def generate_base_contract(self, macro_prompt: str, subtasks: List[SubTask]) -> str:
        """Creates an immutable architectural contract file that each worktree must respect."""
        self.contract_path.parent.mkdir(parents=True, exist_ok=True)
        content = [
            "# IMMUTABLE SWARM CONTRACT",
            f"**Macro Objective:** {macro_prompt}\n",
            "## Architecture & Boundary Invariants",
            "- Do not alter shared schemas without coordination.",
            "- Stay strictly within assigned target files to avoid merge conflicts.\n",
            "## Assigned Worktree Boundaries:",
        ]
        for task in subtasks:
            content.append(f"- **{task.name}** (Complexity: {task.complexity}/10):")
            for f in task.target_files:
                content.append(f"  - `{f}`")

        contract_str = "\n".join(content)
        self.contract_path.write_text(contract_str, encoding="utf-8")
        return contract_str

    def create_worktree(self, task: SubTask, base_branch: str = "main") -> Path:
        """Creates an isolated git worktree for a subtask."""
        branch_name = f"swarm/{task.name}-{task.id}"
        worktree_path = self.worktrees_base_dir / f"{task.name}_{task.id}"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        task.branch_name = branch_name
        task.worktree_path = str(worktree_path)

        # Ensure base repo has at least one commit
        status_res = self._run_git(["rev-parse", "HEAD"])
        if status_res.returncode != 0:
            # Create initial commit if repo is empty
            self._run_git(["commit", "--allow-empty", "-m", "chore: initialize repository for hydra swarm"])

        # Create worktree
        res = self._run_git(["worktree", "add", "-b", branch_name, str(worktree_path), base_branch])
        if res.returncode != 0:
            # Fallback if branch already exists
            res = self._run_git(["worktree", "add", str(worktree_path), branch_name])
            if res.returncode != 0:
                raise RuntimeError(f"Failed to create git worktree: {res.stderr}")

        logger.info(f"Created worktree for {task.name} at {worktree_path}")
        return worktree_path

    def run_tests(self, cwd: Path) -> bool:
        """Executes test suite in the target directory."""
        try:
            res = subprocess.run(
                self.test_command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return res.returncode == 0
        except Exception as e:
            logger.warning(f"Test run failed: {e}")
            return False

    def merge_worktree_branch(self, task: SubTask, target_branch: str = "main") -> bool:
        """Merges subtask branch into target branch."""
        if not task.branch_name:
            return False

        # Switch to target branch in main repo
        self._run_git(["checkout", target_branch])
        
        # Merge with non-fast-forward
        res = self._run_git(["merge", "--no-ff", task.branch_name, "-m", f"feat(swarm): merge {task.name}"])
        if res.returncode != 0:
            logger.error(f"Merge conflict merging {task.branch_name}: {res.stderr}")
            self._run_git(["merge", "--abort"])
            return False

        return True

    def cleanup_worktree(self, task: SubTask) -> None:
        """Removes the worktree and prunes git records."""
        if task.worktree_path and Path(task.worktree_path).exists():
            self._run_git(["worktree", "remove", "--force", task.worktree_path])
            self._run_git(["worktree", "prune"])
            if Path(task.worktree_path).exists():
                shutil.rmtree(task.worktree_path, ignore_errors=True)
            logger.info(f"Cleaned up worktree for {task.name}")
