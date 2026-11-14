"""Incremental, shell-free CLI conversations. Shares worker environment and cancellation."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Awaitable, Callable

from hydra_orch.bridge.worker_runner import filter_worker_env, cancel_process_tree
from hydra_orch.bridge.pty_runner import _bundled_codex_needs_no_daemon
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import ContractViolation

Emit = Callable[[str, dict], Awaitable[None]]


class ConversationRunner:
    """Codex JSONL and Claude stream-json adapters; no interactive terminal required."""

    def __init__(self):
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self._login_cache = {}

    async def login_status(self, driver, executable):
        import time
        cached = self._login_cache.get(executable)
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        def check():
            try:
                command = [executable, "login", "status"] if driver == "codex" else [executable, "auth", "status"]
                result = subprocess.run(command, capture_output=True, timeout=8, env=filter_worker_env(),
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if driver == "claude":
                    return result.returncode == 0 and json.loads(result.stdout).get("loggedIn", False)
                return result.returncode == 0
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return False
        logged_in = await asyncio.to_thread(check)
        self._login_cache[executable] = (time.monotonic(), logged_in)
        return logged_in

    async def capabilities(self):
        result = []
        for driver, command in (("codex", "codex"), ("claude", "claude")):
            executable = shutil.which(command)
            result.append({"id": driver, "name": "Codex" if driver == "codex" else "Claude Code",
                           "available": bool(executable), "streaming": True,
                           "authenticated": await self.login_status(driver, executable) if executable else False,
                           "native_resume": True, "access_modes": ["read-only", "workspace-write"]})
        return result

    async def cancel(self, turn_id: str):
        process = self.processes.get(turn_id)
        if process and process.returncode is None:
            if not await cancel_process_tree(process.pid):
                raise ContractViolation("conversation_process_active", "O agente ainda está encerrando. Aguarde antes de continuar.")

    async def run(self, turn: dict, conversation: dict, prompt: str, cwd: Path, emit: Emit):
        driver = conversation["executor"]
        executable = shutil.which(driver)
        if not executable:
            raise ContractViolation("agent_unavailable", f"Instale {driver} e conecte sua conta antes de enviar novamente.")
        session = conversation.get("native_session_id")
        if driver == "codex":
            args = [executable]
            if await asyncio.to_thread(_bundled_codex_needs_no_daemon, executable):
                args += ["--no-daemon"]
            args += ["--cd", str(cwd), "--ask-for-approval", "never", "exec"]
            if conversation.get("workspace_kind") == "folder" and not session:
                args += ["--skip-git-repo-check"]
            # exec resume has a distinct CLI contract; sandbox is a global option.
            if session:
                args[1:1] = ["--sandbox", conversation["access_mode"]]
                args += ["resume"]
                if conversation.get("workspace_kind") == "folder":
                    args += ["--skip-git-repo-check"]
                args += ["--json", session, "-"]
            else:
                args += ["--sandbox", conversation["access_mode"], "--json", "-"]
        elif driver == "claude":
            args = [executable, "--print", "--verbose", "--output-format", "stream-json",
                    "--include-partial-messages", "--permission-mode", "dontAsk",
                    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
            # Explicit tool allowlist prevents writes in read-only chats.
            args += ["--tools", "Read,Glob,Grep" if conversation["access_mode"] == "read-only" else "Read,Glob,Grep,Edit,Write,Bash"]
            if conversation["access_mode"] == "workspace-write":
                args += ["--allowedTools", "Read,Glob,Grep,Edit,Write"]
            if session:
                args += ["--resume", session]
        else:
            raise ContractViolation("agent_unavailable", "Este agente ainda não suporta conversa. Escolha Codex ou Claude Code.")
        folder_env = {"GIT_CEILING_DIRECTORIES": str(cwd.parent)} if conversation.get("workspace_kind") == "folder" else None
        kwargs = {"cwd": str(cwd), "env": filter_worker_env(allowed_env=folder_env), "stdin": asyncio.subprocess.PIPE,
                  "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE, "limit": 2**20}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = await asyncio.create_subprocess_exec(*args, **kwargs)
        self.processes[turn["id"]] = process
        stderr = bytearray()
        text_seen = False
        partial = False

        async def read_errors():
            while chunk := await process.stderr.read(4096):
                stderr.extend(chunk)
                if len(stderr) > 32768:
                    del stderr[:-32768]

        errors_task = asyncio.create_task(read_errors())
        try:
            await emit("process.started", {"pid": process.pid})
            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            async def consume():
                nonlocal text_seen, partial
                while line := await process.stdout.readline():
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    kind = event.get("type")
                    if kind == "thread.started" or kind == "system" and event.get("subtype") == "init":
                        native_id = event.get("thread_id") or event.get("session_id")
                        if native_id:
                            await emit("session.started", {"session_id": native_id})
                    if driver == "codex":
                        if kind == "item.completed":
                            item = event.get("item", {})
                            if item.get("type") == "agent_message":
                                text_seen = True
                                await emit("text.delta", {"text": item.get("text", "") + "\n"})
                            elif item.get("type") in {"command_execution", "file_change", "mcp_tool_call", "web_search"}:
                                await emit("tool.completed", {"tool": item.get("type"), "detail": redact_text(json.dumps(item, ensure_ascii=False))[:12000]})
                        elif kind in {"error", "turn.failed"}:
                            error = event.get("message") or event.get("error", {}).get("message") or "Falha ao executar Codex. Confira o login e tente novamente."
                            raise ContractViolation("agent_failed", redact_text(str(error)))
                    else:
                        if kind == "stream_event":
                            inner = event.get("event", {})
                            delta = inner.get("delta", {})
                            if delta.get("type") == "text_delta":
                                partial = text_seen = True
                                await emit("text.delta", {"text": delta.get("text", "")})
                            if inner.get("type") == "content_block_start":
                                block = inner.get("content_block", {})
                                if block.get("type") == "tool_use":
                                    await emit("tool.started", {"tool": block.get("name", "Ferramenta")})
                        elif kind == "assistant" and not partial:
                            for block in event.get("message", {}).get("content", []):
                                if block.get("type") == "text":
                                    text_seen = True
                                    await emit("text.delta", {"text": block["text"]})
                        elif kind == "result":
                            if event.get("permission_denials"):
                                await emit("tool.permission_denied", {"tool": "Permissão necessária", "detail": "Uma ação exige permissão adicional. Revise o pedido ou use o terminal para autorizar essa operação."})
                            if event.get("is_error"):
                                raise ContractViolation("agent_failed", redact_text(str(event.get("result") or event.get("errors") or "Conecte sua conta Claude Code e tente novamente.")))
                await process.wait()
            try:
                await asyncio.wait_for(consume(), timeout=1800)
            except asyncio.TimeoutError as exc:
                raise ContractViolation("agent_timeout", "O agente atingiu o tempo máximo deste turno. Envie uma nova mensagem para continuar.") from exc
            await errors_task
            if process.returncode != 0:
                detail = redact_text(stderr.decode("utf-8", errors="replace"))[-3000:]
                raise ContractViolation("agent_failed", detail or "O agente encerrou sem responder. Confira o login e tente novamente.")
            if not text_seen:
                raise ContractViolation("agent_empty_response", "O agente encerrou sem uma resposta. Confira sua conexão e tente novamente.")
        finally:
            if process.returncode is None:
                await cancel_process_tree(process.pid)
            errors_task.cancel()
            await asyncio.gather(errors_task, return_exceptions=True)
            self.processes.pop(turn["id"], None)
