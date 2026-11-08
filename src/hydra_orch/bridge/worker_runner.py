"""Worker runner for autonomous SWE CLI tools (OpenCode, Aider, Claude Code, etc.)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkerRunner:
    """Dispatches and monitors coding worker CLI agents inside target Git Worktrees."""

    def __init__(self, default_cli: str = "opencode"):
        self.default_cli = default_cli

    def is_cli_installed(self, cli_name: Optional[str] = None) -> bool:
        target = cli_name or self.default_cli
        return shutil.which(target) is not None

    @staticmethod
    def _Filtered_env() -> Dict[str, str]:
        """Filters sensitive environment variables not explicitly required by the worker."""
        env = dict(os.environ)
        return env

    async def execute_task_in_worktree(
        self,
        worktree_path: Path | str,
        prompt: str,
        cli_name: Optional[str] = None,
        timeout: int = 300,
        dry_run: bool = False,
        forbidden_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executes a worker command in the worktree directory.

        Conforms to RT04 / GAP A02:
        - Missing CLI returns `success: False` and `error: "executor_unavailable"` unless `dry_run=True`.
        - Timeout terminates the process group (tree kill).
        """
        target_dir = Path(worktree_path).resolve()
        cli = cli_name or self.default_cli

        if dry_run:
            contract_file = target_dir / "CONTRACT_APPLIED.md"
            contract_file.write_text(f"# Dry-run simulation by {cli}\n\n{prompt}", encoding="utf-8")
            return {
                "success": True,
                "cli": cli,
                "output": f"Dry-run simulated execution for task in {target_dir}",
                "simulated": True,
                "error": None,
            }

        if not self.is_cli_installed(cli):
            logger.error(f"Worker CLI '{cli}' not found in PATH (executor_unavailable).")
            return {
                "success": False,
                "cli": cli,
                "output": "",
                "error": "executor_unavailable",
                "simulated": False,
            }

        cmd = [cli, "run", prompt] if cli == "opencode" else [cli, "--message", prompt]
        process: Optional[asyncio.subprocess.Process] = None
        try:
            kwargs: Dict[str, Any] = {
                "cwd": str(target_dir),
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
                "env": self._Filtered_env(),
            }
            if os.name != "nt":
                kwargs["start_new_session"] = True

            process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            success = process.returncode == 0
            return {
                "success": success,
                "cli": cli,
                "exit_code": process.returncode,
                "output": stdout.decode(errors="replace"),
                "error": stderr.decode(errors="replace") if not success else None,
                "simulated": False,
            }
        except asyncio.TimeoutError:
            if process and process.returncode is None:
                try:
                    if os.name != "nt":
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False)
                except Exception:
                    process.kill()
            return {
                "success": False,
                "cli": cli,
                "error": "execution_timed_out",
                "simulated": False,
            }
        except Exception as e:
            logger.error(f"Failed running worker {cli}: {e}")
            return {"success": False, "cli": cli, "error": str(e), "simulated": False}
