"""Incremental, shell-free CLI conversations. Shares worker environment and cancellation."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from contextlib import ExitStack
from typing import Awaitable, Callable

from hydra_orch.bridge.worker_runner import filter_worker_env, cancel_process_tree
from hydra_orch.bridge.pty_runner import _bundled_codex_needs_no_daemon
from hydra_orch.bridge.agent_executable import resolve_agent_executable
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
                result = subprocess.run(command, capture_output=True, timeout=8, env=filter_worker_env(), stdin=subprocess.DEVNULL,
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
            executable = await asyncio.to_thread(resolve_agent_executable, command)
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

    async def invocation(self, conversation: dict, cwd: Path):
        """Build a scoped CLI invocation; caller must close the returned transport.

        Also used by the canonical WorkerRunner for coordinated task attempts.
        """
        transport = ExitStack()
        try:
            driver = conversation["executor"]
            executable = await asyncio.to_thread(resolve_agent_executable, driver)
            if not executable:
                raise ContractViolation("agent_unavailable", f"O executável de {driver} não foi encontrado no ambiente do backend. "
                                        "Se o agente já está instalado, reinicie o Hydra para atualizar o PATH. "
                                        "A autenticação ainda não foi verificada; o histórico foi preservado.")
            session = conversation.get("native_session_id")
            route = conversation.get('route') or {}
            target = route.get('target_ref', '')
            allowed_env = {}
            gateway_args = []
            observed = {}
            if route.get('connection_mode') == 'omniroute':
                base_url = conversation['_gateway_base_url']
                token = conversation['_gateway_token']
                if not token:
                    raise ContractViolation('gateway_credential_missing', 'Configure a credencial do OmniRoute no backend.')
                if driver == 'codex':
                    from hydra_orch.bridge.codex_catalog import gateway_catalog
                    from hydra_orch.bridge.omniroute_transport import codex_transport
                    import hashlib
                    state_root = Path(conversation.get('_agent_state_dir') or cwd.parent / '.hydra_agent_state' / hashlib.sha256(str(cwd).encode()).hexdigest()[:24]).absolute()
                    home = state_root / 'codex_home'
                    if home.is_symlink() or state_root.is_symlink():
                        raise ContractViolation('context_path_escape', 'O diretório do agente não é seguro.')
                    # A fresh Windows sandbox grants access to its writable temp
                    # root. Inheriting the user's entire TEMP makes each isolated
                    # worker walk that shared tree, delaying even its first tool.
                    # Keep this root small, private to the agent and stable on resume.
                    private_temp = state_root / 'tmp'
                    if private_temp.is_symlink() or (private_temp.exists() and not private_temp.is_dir()):
                        raise ContractViolation('context_path_escape', 'O diretório temporário do agente não é seguro.')
                    private_temp.mkdir(parents=True, exist_ok=True)
                    catalog = await asyncio.to_thread(gateway_catalog, executable, target, home)
                    base_url, token, observed = transport.enter_context(codex_transport(base_url, token, target))
                    provider = {'name': 'OmniRoute', 'base_url': base_url, 'env_key': 'OMNIROUTE_API_KEY',
                                'wire_api': 'responses', 'requires_openai_auth': False}
                    inline = '{' + ','.join(f'{k}={json.dumps(v)}' for k, v in provider.items()) + '}'
                    gateway_args = ['-c', 'model_provider="hydra_omni"', '-c', 'model_providers.hydra_omni=' + inline,
                                    '-c', 'model_catalog_json=' + json.dumps(str(catalog).replace('\\', '/')),
                                    '-c', 'web_search="disabled"', '-c', 'features.incremental_tools=false',
                                    '-c', 'features.apps=false', '-c', 'features.plugins=false',
                                    '-c', 'features.goals=false', '-c', 'features.multi_agent=false']
                    if os.name == 'nt':
                        # An isolated CODEX_HOME must still select the supported Windows
                        # sandbox implementation; --sandbox remains the user's access mode.
                        gateway_args += ['-c', 'windows.sandbox="unelevated"']
                    allowed_env.update(OMNIROUTE_API_KEY=token, CODEX_HOME=str(home),
                                       TEMP=str(private_temp), TMP=str(private_temp), TMPDIR=str(private_temp))
                else:
                    import hashlib
                    state_root = Path(conversation.get('_agent_state_dir') or cwd.parent / '.hydra_agent_state' / hashlib.sha256(str(cwd).encode()).hexdigest()[:24])
                    home = state_root / 'claude_home'
                    if home.is_symlink() or state_root.is_symlink():
                        raise ContractViolation('context_path_escape', 'O diretório do agente não é seguro.')
                    home.mkdir(parents=True,exist_ok=True)
                    allowed_env.update(ANTHROPIC_BASE_URL=base_url.removesuffix('/v1'), ANTHROPIC_AUTH_TOKEN=token,
                                       ANTHROPIC_MODEL=target, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',CLAUDE_CONFIG_DIR=str(home),
                                       ANTHROPIC_DEFAULT_OPUS_MODEL=target,ANTHROPIC_DEFAULT_SONNET_MODEL=target,
                                       ANTHROPIC_DEFAULT_HAIKU_MODEL=target,ANTHROPIC_SMALL_FAST_MODEL=target,CLAUDE_CODE_SUBAGENT_MODEL=target)
            if driver == "codex":
                args = [executable]
                if await asyncio.to_thread(_bundled_codex_needs_no_daemon, executable):
                    args += ["--no-daemon"]
                args += gateway_args
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
                if target:
                    args += ['--model', target]
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
                if target:
                    args += ['--model', target]
            else:
                raise ContractViolation("agent_unavailable", "Este agente ainda não suporta conversa. Escolha Codex ou Claude Code.")
            if conversation.get("workspace_kind") == "folder":
                allowed_env['GIT_CEILING_DIRECTORIES'] = str(cwd.parent)
            return args, filter_worker_env(allowed_env=allowed_env), transport, observed
        except BaseException:
            await asyncio.to_thread(transport.close)
            raise

    async def run(self, turn: dict, conversation: dict, prompt: str, cwd: Path, emit: Emit):
        started = time.monotonic()
        metrics = {'first_text_seconds': None, 'tool_events': 0, 'usage_status': 'unknown'}
        original_emit = emit
        async def emit(kind, payload):
            if kind == 'text.delta' and metrics['first_text_seconds'] is None:
                metrics['first_text_seconds'] = round(time.monotonic() - started, 3)
            if kind == 'tool.completed':
                metrics['tool_events'] += 1
            await original_emit(kind, payload)
        driver = conversation["executor"]
        args, environment, transport, observed = await self.invocation(conversation, cwd)
        kwargs = {"cwd": str(cwd), "env": environment, "stdin": asyncio.subprocess.PIPE,
                  "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE, "limit": 2**20}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = await asyncio.create_subprocess_exec(*args, **kwargs)
        except BaseException:
            await asyncio.to_thread(transport.close)
            raise
        self.processes[turn["id"]] = process
        stderr = bytearray()
        text_seen = False
        partial = False
        observed_agents = {}

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
                    from hydra_orch.bridge.agent_observation import observations
                    for agent in observations(driver, event, observed_agents):
                        if agent['id'] in observed_agents or len(observed_agents) < 128:
                            observed_agents[agent['id']] = agent
                            await emit('agent.observed', agent)
                    if kind == "thread.started" or kind == "system" and event.get("subtype") == "init":
                        native_id = event.get("thread_id") or event.get("session_id")
                        if native_id:
                            await emit("session.started", {"session_id": native_id})
                    if driver == "codex":
                        if kind == 'turn.completed' and isinstance(event.get('usage'), dict):
                            usage = {k: v for k, v in event['usage'].items() if k in {'input_tokens', 'cached_input_tokens', 'output_tokens'} and isinstance(v, int) and v >= 0}
                            if usage:
                                metrics.update(usage=usage, usage_status='observed', usage_source='codex_cli')
                        if kind in {"item.started", "item.completed"}:
                            item = event.get("item", {})
                            if item.get("type") == "agent_message" and kind == "item.completed":
                                text_seen = True
                                await emit("text.delta", {"text": item.get("text", "") + "\n"})
                            elif item.get("type") in {"command_execution", "file_change", "mcp_tool_call", "web_search"}:
                                await emit("tool.started" if kind == "item.started" else "tool.completed", {"tool": item.get("type"), "detail": redact_text(json.dumps(item, ensure_ascii=False))[:12000]})
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
            await asyncio.to_thread(transport.close)
            if process.returncode is None:
                await cancel_process_tree(process.pid)
            errors_task.cancel()
            await asyncio.gather(errors_task, return_exceptions=True)
            self.processes.pop(turn["id"], None)
            metrics['duration_seconds'] = round(time.monotonic() - started, 3)
            if observed.get('request_error'):
                metrics['request_error']=observed['request_error']
            if observed.get('models'):
                metrics['models'] = observed['models']
                metrics['model_source'] = observed['source']
            # Metrics must never mask cancellation or the original process failure.
            from contextlib import suppress
            with suppress(Exception):
                await emit('execution.metrics', metrics)
