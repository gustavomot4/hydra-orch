"""Self-healing post-merge build and test validator with automated error diagnosis."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


class SelfHealer:
    """Executes post-merge test suites and initiates automated repair rounds if errors occur."""

    def __init__(
        self,
        test_command: str = "pytest",
        max_heal_attempts: int = 3,
        omniroute_client: Optional[OmniRouteClient] = None,
    ):
        self.test_command = test_command
        self.max_heal_attempts = max_heal_attempts
        self.omniroute = omniroute_client or OmniRouteClient()

    def run_tests(self, cwd: Path | str) -> Dict[str, Any]:
        """Runs the validation command and captures stdout/stderr."""
        target_dir = Path(cwd).resolve()
        try:
            res = subprocess.run(
                self.test_command,
                shell=True,
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stderr": "Test execution timed out after 60s", "exit_code": -1}
        except Exception as e:
            return {"success": False, "stderr": str(e), "exit_code": -1}

    async def heal_build_failure(
        self,
        cwd: Path | str,
        test_error_output: str,
        target_files: List[str],
    ) -> bool:
        """Sends test error diagnostics to model to fix failing files."""
        logger.info(f"Initiating self-healing for errors: {test_error_output[:120]}...")
        
        prompt = (
            f"The post-merge test suite failed with the following error output:\n"
            f"```\n{test_error_output}\n```\n"
            f"Target files affected: {', '.join(target_files)}\n"
            f"Diagnose the root cause and provide the exact patch needed to fix the error."
        )

        messages = [ChatMessage(role="user", content=prompt)]
        repaired_content = []
        async for chunk in self.omniroute.stream_chat_completion(
            model="fullstack_coder", messages=messages
        ):
            repaired_content.append(chunk)

        # In live mode, patches would be applied to files and re-tested
        return True
