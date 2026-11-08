"""Contract-First Engine (Wave 0 Compilable Foundation) generating schemas and APIs before parallel coding."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List
from hydra_orch.engine.decomposer import EngineSubTask, LOCKED_DEPENDENCY_MANIFESTS

logger = logging.getLogger(__name__)


class ContractFirstEngine:
    """Generates Wave 0 architectural contracts and boundary manifests in .orchestrator/contract."""

    def __init__(self, contracts_dir: str = ".orchestrator/contract"):
        self.contracts_dir = Path(contracts_dir)

    def generate_contract_bundle(
        self,
        macro_prompt: str,
        tasks: List[EngineSubTask],
    ) -> Dict[str, str]:
        """Generates schema, OpenAPI, interfaces, and master CONTRACT.md."""
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

        # 1. Master CONTRACT.md
        contract_md_lines = [
            "# WAVE 0 COMPILABLE ARCHITECTURAL CONTRACT",
            f"**Macro Objective:** {macro_prompt}\n",
            "## Universal Invariants & Wave 1 Governance",
            "1. Wave 1 workers must NOT modify shared route paths, database schemas, or dependency manifests (`pyproject.toml`, `package.json`) directly.",
            "2. If a Wave 1 worker requires a schema or dependency change, it must emit a `ContractAmendmentRequest` (`needs_context`).",
            "3. Locked manifests in Wave 1: " + ", ".join(f"`{m}`" for m in LOCKED_DEPENDENCY_MANIFESTS) + "\n",
            "## Worktree Boundaries & Logical Allocation:",
        ]
        for task in tasks:
            contract_md_lines.append(
                f"- **{task.name}** ({task.role_key}) [Wave {task.wave} | Difficulty: {task.difficulty}/10 | Model: {task.assigned_logical_model}]:"
            )
            for path in task.target_files:
                contract_md_lines.append(f"  - `{path}`")

        contract_md = "\n".join(contract_md_lines)
        (self.contracts_dir / "CONTRACT.md").write_text(contract_md, encoding="utf-8")

        # 2. openapi.json stub
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Hydra Wave 0 Generated Contract", "version": "1.0.0"},
            "paths": {
                "/api/health": {"get": {"summary": "Healthcheck endpoint"}},
                "/api/resource": {
                    "get": {"summary": "List entities"},
                    "post": {"summary": "Create entity"},
                },
            },
        }
        (self.contracts_dir / "openapi.json").write_text(
            json.dumps(openapi_spec, indent=2), encoding="utf-8"
        )

        # 3. schema.prisma stub
        prisma_schema = (
            'datasource db {\n'
            '  provider = "sqlite"\n'
            '  url      = "file:./dev.db"\n'
            '}\n\n'
            'generator client {\n'
            '  provider = "prisma-client-js"\n'
            '}\n\n'
            'model Entity {\n'
            '  id        String   @id @default(uuid())\n'
            '  name      String\n'
            '  createdAt DateTime @default(now())\n'
            '}\n'
        )
        (self.contracts_dir / "schema.prisma").write_text(prisma_schema, encoding="utf-8")

        # 4. task_graph.json
        task_graph = [t.model_dump() for t in tasks]
        (self.contracts_dir / "task_graph.json").write_text(
            json.dumps(task_graph, indent=2), encoding="utf-8"
        )

        return {
            "contract_md": contract_md,
            "contracts_dir": str(self.contracts_dir),
        }
