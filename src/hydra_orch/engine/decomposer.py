"""Task Decomposer evaluating complexity (1-10) and allocating logical models."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EngineSubTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    role_key: str
    name: str
    description: str
    difficulty: int  # 1 to 10
    estimated_tokens: int = 4000
    assigned_logical_model: str = "architect_heavy"
    target_files: List[str] = Field(default_factory=list)
    worktree_name: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed, failed


class TaskDecomposer:
    """Analyzes user macro prompts and decomposes them into prioritized sub-tasks."""

    def __init__(self, logical_roles: Optional[Dict[str, str]] = None):
        self.logical_roles = logical_roles or {
            "backend_core": "architect_heavy",
            "frontend_ui": "fullstack_coder",
            "db_and_tests": "database_and_tests",
            "docs_and_review": "context_and_docs",
        }

    def decompose(self, macro_prompt: str) -> List[EngineSubTask]:
        """Decomposes a macro prompt into 4 distinct, parallelizable engineering fronts."""
        summary = macro_prompt.strip()[:100]

        tasks = [
            EngineSubTask(
                role_key="backend_core",
                name="wt-backend",
                description=f"Core business logic, security rules, and domain services for: {summary}",
                difficulty=9,
                estimated_tokens=8000,
                assigned_logical_model=self.logical_roles.get("backend_core", "architect_heavy"),
                target_files=["src/domain/", "src/services/", "src/api/"],
            ),
            EngineSubTask(
                role_key="frontend_ui",
                name="wt-frontend",
                description=f"UI components, user flows, state management, and screens for: {summary}",
                difficulty=7,
                estimated_tokens=6000,
                assigned_logical_model=self.logical_roles.get("frontend_ui", "fullstack_coder"),
                target_files=["src/ui/", "src/components/", "src/views/"],
            ),
            EngineSubTask(
                role_key="db_and_tests",
                name="wt-db-tests",
                description=f"Database schemas, migrations, seeds, unit and integration tests for: {summary}",
                difficulty=5,
                estimated_tokens=5000,
                assigned_logical_model=self.logical_roles.get("db_and_tests", "database_and_tests"),
                target_files=["prisma/", "migrations/", "tests/"],
            ),
            EngineSubTask(
                role_key="docs_and_review",
                name="wt-docs",
                description=f"Technical OpenAPI/Swagger docs, user manual, and contract verification for: {summary}",
                difficulty=4,
                estimated_tokens=3000,
                assigned_logical_model=self.logical_roles.get("docs_and_review", "context_and_docs"),
                target_files=["doc/", "README.md", "openapi.json"],
            ),
        ]
        return tasks
