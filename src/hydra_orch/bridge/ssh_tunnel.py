"""SSH and autossh tunnel manager for remote GPU models (Ollama/vLLM)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


class SshTunnelManager:
    """Manages an SSH or autossh port forwarding tunnel to a remote GPU node."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        target = config.get("ssh_target", "usuario@192.168.1.100")
        if "@" in target:
            self.user, self.host = target.split("@", 1)
        else:
            self.user = config.get("user", "hydra")
            self.host = target

        self.port: int = config.get("ssh_port", 22)
        self.key_file: Optional[str] = config.get("ssh_key")
        self.local_port: int = config.get("local_port", 11435)
        self.remote_port: int = config.get("remote_port", 11434)
        self.healthcheck_interval: int = config.get("healthcheck_interval_sec", 10)
        self._process: Optional[subprocess.Popen] = None

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    async def verify_endpoint(self) -> bool:
        """Test whether the forwarded local port is actively answering HTTP queries."""
        try:
            url = f"http://127.0.0.1:{self.local_port}/api/tags"
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                return resp.status_code in (200, 404)
        except Exception:
            return False

    def start_tunnel(self) -> bool:
        """Launches the SSH forwarding process."""
        if self.is_running():
            logger.info("SSH tunnel already running")
            return True

        binary = "autossh" if shutil.which("autossh") else "ssh"
        cmd = [
            binary,
            "-o",
            "BatchMode=yes",
            "-o",
            f"ServerAliveInterval={self.healthcheck_interval}",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-N",
            "-L",
            f"{self.local_port}:127.0.0.1:{self.remote_port}",
            f"{self.user}@{self.host}",
            "-p",
            str(self.port),
        ]

        if self.key_file:
            expanded_key = os.path.expanduser(self.key_file)
            if os.path.isfile(expanded_key):
                cmd.extend(["-i", expanded_key])

        logger.info(f"Starting SSH tunnel: {' '.join(cmd)}")
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start SSH tunnel: {e}")
            return False

    def stop_tunnel(self) -> None:
        """Stops the active tunnel process."""
        if self._process and self._process.poll() is None:
            logger.info("Terminating SSH tunnel process")
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
