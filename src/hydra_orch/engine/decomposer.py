"""Task Decomposer evaluating complexity (1-10) and structuring Two-Wave Swarm DAG (Wave 0 + Wave 1)."""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Manifests locked during Wave 1 parallel execution to prevent shared symlink corruption
LOCKED_DEPENDENCY_MANIFESTS = [
    "pyproject.toml",
    "poetry.lock",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "Cargo.toml",
]


class EngineSubTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    role_key: str
    name: str
    description: str
    difficulty: int  # 1 to 10
    wave: int = 1  # 0: Wave 0 Foundation, 1: Wave 1 Parallel Swarm
    dependencies: List[str] = Field(default_factory=list)
    estimated_tokens: int = 4000
    assigned_logical_model: str = "architect_heavy"
    target_files: List[str] = Field(default_factory=list)
    forbidden_files: List[str] = Field(default_factory=list)
    worktree_name: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed, failed


class TaskDecomposer:
    """Analyzes user macro prompts and decomposes them into Wave 0 (Foundation) + Wave 1 (Parallel Swarm)."""

    def __init__(self, logical_roles: Optional[Dict[str, str]] = None):
        self.logical_roles = logical_roles or {
            "backend_core": "architect_heavy",
            "frontend_ui": "fullstack_coder",
            "db_and_tests": "database_and_tests",
            "docs_and_review": "context_and_docs",
        }

    def decompose(self, macro_prompt: str, include_wave_0: bool = False) -> List[EngineSubTask]:
        """Decomposes a macro prompt into parallelizable engineering fronts.

         notice: migration/ is strictly singular per taxonomia_file_system.md.
        """
        summary = macro_prompt.strip()[:100]
        wave_0_id = f"w0-{uuid.uuid4().hex[:6]}"
        tasks: List[EngineSubTask] = []

        if include_wave_0:
            tasks.append(
                EngineSubTask(
                    id=wave_0_id,
                    role_key="foundation_contract",
                    name="wt-foundation",
                    description=f"Wave 0 Compilable Foundation (schemas, types, stubs, dependencies) for: {summary}",
                    difficulty=9,
                    wave=0,
                    dependencies=[],
                    estimated_tokens=5000,
                    assigned_logical_model=self.logical_roles.get("backend_core", "architect_heavy"),
                    target_files=["src/model.py", "openapi.json", "pyproject.toml", "package.json"],
                    forbidden_files=[],
                )
            )

        deps = [wave_0_id] if include_wave_0 else []

        tasks.extend([
            EngineSubTask(
                role_key="backend_core",
                name="wt-backend",
                description=f"Core business logic, security rules, and domain services for: {summary}",
                difficulty=9,
                wave=1,
                dependencies=list(deps),
                estimated_tokens=8000,
                assigned_logical_model=self.logical_roles.get("backend_core", "architect_heavy"),
                target_files=["src/domain/", "src/service/", "src/api/"],
                forbidden_files=list(LOCKED_DEPENDENCY_MANIFESTS),
            ),
            EngineSubTask(
                role_key="frontend_ui",
                name="wt-frontend",
                description=f"UI components, user flows, state management, and screens for: {summary}",
                difficulty=7,
                wave=1,
                dependencies=list(deps),
                estimated_tokens=6000,
                assigned_logical_model=self.logical_roles.get("frontend_ui", "fullstack_coder"),
                target_files=["src/ui/", "src/component/", "src/view/"],
                forbidden_files=list(LOCKED_DEPENDENCY_MANIFESTS),
            ),
            EngineSubTask(
                role_key="db_and_tests",
                name="wt-db-tests",
                description=f"Database schemas, migration scripts, seeds, unit and integration tests for: {summary}",
                difficulty=5,
                wave=1,
                dependencies=list(deps),
                estimated_tokens=5000,
                assigned_logical_model=self.logical_roles.get("db_and_tests", "database_and_tests"),
                target_files=["prisma/", "migration/", "tests/"],
                forbidden_files=list(LOCKED_DEPENDENCY_MANIFESTS),
            ),
            EngineSubTask(
                role_key="docs_and_review",
                name="wt-docs",
                description=f"Technical OpenAPI/Swagger docs, user manual, and contract verification for: {summary}",
                difficulty=4,
                wave=1,
                dependencies=list(deps),
                estimated_tokens=3000,
                assigned_logical_model=self.logical_roles.get("docs_and_review", "context_and_docs"),
                target_files=["doc/", "README.md", "openapi.json"],
                forbidden_files=list(LOCKED_DEPENDENCY_MANIFESTS),
            ),
        ])
        return tasks
