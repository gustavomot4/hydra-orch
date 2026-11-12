"""T19: isolated stdio MCP client with declared-tool and permission enforcement."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from typing import Any, Mapping, Optional, Sequence

from hydra_orch.bridge.worker_runner import cancel_process_tree, filter_worker_env
from hydra_orch.core.redaction import redact
from hydra_orch.core.skill_registry import McpDefinition, SecretBundle
from hydra_orch.model import ContractViolation


def _resolve_stdio_argv(endpoint: str, extra_args: Sequence[str] = ()) -> list[str]:
    if not endpoint or "\x00" in endpoint:
        raise ContractViolation("mcp_invalid_endpoint", "MCP stdio endpoint must be non-empty without NUL")
    if os.path.exists(endpoint):
        argv = [endpoint]
    else:
        argv = shlex.split(endpoint, posix=(os.name != "nt"))
    if not argv:
        raise ContractViolation("mcp_invalid_endpoint", "MCP stdio endpoint produced empty command")
    for arg in extra_args:
        if "\x00" in str(arg):
            raise ContractViolation("mcp_invalid_endpoint", "MCP argument cannot contain NUL")
        argv.append(str(arg))
    return argv


class McpClient:
    """Line-delimited JSON-RPC 2.0 client for authorized stdio MCP servers."""

    def __init__(
        self,
        definition: McpDefinition,
        *,
        secret_bundle: Optional[SecretBundle] = None,
        granted_permissions: Optional[Sequence[str]] = None,
        timeout_seconds: float = 10.0,
        max_message_bytes: int = 1024 * 1024,
        cwd: Optional[str] = None,
        extra_args: Sequence[str] = (),
    ):
        self.definition = definition
        self._secret_bundle = secret_bundle
        self._granted_permissions = tuple(granted_permissions) if granted_permissions is not None else None
        self.timeout_seconds = float(timeout_seconds)
        self.max_message_bytes = int(max_message_bytes)
        self.cwd = cwd
        self.extra_args = tuple(extra_args)
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id = 1
        self._verified_tools: dict[str, dict[str, Any]] = {}
        self.ignored_undeclared_tools: tuple[str, ...] = ()

    @property
    def verified_tools(self) -> tuple[str, ...]:
        return tuple(self._verified_tools.keys())

    async def __aenter__(self) -> "McpClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def _check_permissions(self) -> None:
        if self._granted_permissions is None:
            return
        granted = set(self._granted_permissions)
        missing = [p for p in self.definition.permissions if p not in granted]
        if missing:
            raise ContractViolation(
                "mcp_permission_denied",
                f"Profile lacks required permissions for MCP '{self.definition.server_name}': {missing}",
            )

    async def connect(self) -> dict[str, Any]:
        if self.definition.transport_type != "stdio":
            raise ContractViolation(
                "mcp_transport_uncertified",
                f"MCP transport '{self.definition.transport_type}' is not certified; only 'stdio' is supported",
            )
        self._check_permissions()
        argv = _resolve_stdio_argv(self.definition.endpoint, self.extra_args)
        allowed_env = self._secret_bundle.as_allowed_env() if self._secret_bundle is not None else None
        env = filter_worker_env(allowed_env=allowed_env)

        popen_kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": env,
            "cwd": self.cwd,
            "limit": self.max_message_bytes,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            self._proc = await asyncio.create_subprocess_exec(*argv, **popen_kwargs)
        except OSError as exc:
            raise ContractViolation("mcp_spawn_failed", f"Failed to spawn MCP server: {exc}") from exc

        try:
            init_resp = await self._rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "hydra-orch", "version": "0.1.0"},
                },
            )
            await self._notify("notifications/initialized", {})
            tools_resp = await self._rpc("tools/list", {})
        except Exception:
            await self.close()
            raise

        listed = tools_resp.get("tools", []) if isinstance(tools_resp, dict) else []
        by_name = {
            item["name"]: item
            for item in listed
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        declared_names = {t.name for t in self.definition.declared_tools}
        missing = sorted(declared_names - set(by_name.keys()))
        if missing:
            await self.close()
            raise ContractViolation(
                "mcp_tools_mismatch",
                f"MCP server '{self.definition.server_name}' did not advertise declared tools: {missing}",
            )
        self.ignored_undeclared_tools = tuple(sorted(set(by_name.keys()) - declared_names))
        self._verified_tools = {name: by_name[name] for name in sorted(declared_names)}
        return redact(init_resp)

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        granted_permissions: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        if granted_permissions is not None:
            granted = set(granted_permissions)
            missing = [p for p in self.definition.permissions if p not in granted]
            if missing:
                raise ContractViolation(
                    "mcp_permission_denied",
                    f"Caller lacks required MCP permissions: {missing}",
                )
        else:
            self._check_permissions()

        if name not in self._verified_tools:
            raise ContractViolation(
                "mcp_permission_denied",
                f"Tool '{name}' is not declared on MCP '{self.definition.server_name}'",
            )
        result = await self._rpc("tools/call", {"name": name, "arguments": dict(arguments or {})})
        return redact(result)

    async def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise ContractViolation("mcp_not_connected", "MCP client is not connected")
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": dict(params)}, separators=(",", ":"))
        self._proc.stdin.write((payload + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _rpc(self, method: str, params: Mapping[str, Any]) -> Any:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise ContractViolation("mcp_not_connected", "MCP client is not connected")
        req_id = self._next_id
        self._next_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": dict(params)},
            separators=(",", ":"),
        )
        encoded = (payload + "\n").encode("utf-8")
        if len(encoded) > self.max_message_bytes:
            raise ContractViolation("mcp_message_too_large", "MCP request exceeds max_message_bytes")
        self._proc.stdin.write(encoded)
        await self._proc.stdin.drain()

        async def _read_matching() -> Any:
            assert self._proc is not None and self._proc.stdout is not None
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    raise ContractViolation("mcp_eof", f"MCP server closed stdout during '{method}'")
                if len(line) > self.max_message_bytes:
                    raise ContractViolation("mcp_message_too_large", "MCP response exceeds max_message_bytes")
                msg = json.loads(line.decode("utf-8"))
                if not isinstance(msg, dict):
                    continue
                if msg.get("id") != req_id:
                    continue
                if "error" in msg and msg["error"] is not None:
                    raise ContractViolation("mcp_rpc_error", redact(str(msg["error"])))
                return msg.get("result")

        try:
            return await asyncio.wait_for(_read_matching(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            await self.close()
            raise ContractViolation("mcp_timeout", f"MCP request '{method}' timed out after {self.timeout_seconds}s") from exc
        except (ValueError, UnicodeError) as exc:
            await self.close()
            raise ContractViolation("mcp_protocol_error", f"Invalid MCP JSON-RPC response: {exc}") from exc

    async def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
        except OSError:
            pass
        if proc.returncode is None:
            await cancel_process_tree(proc.pid)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
