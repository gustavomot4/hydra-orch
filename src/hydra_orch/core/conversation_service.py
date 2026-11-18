"""Durable conversation turns, transactional outbox, leases, replay and isolated workspaces."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import filecmp
import json
import os
from pathlib import Path
import time
import uuid

from hydra_orch.bridge.conversation_runner import ConversationRunner
from hydra_orch.bridge.worker_runner import is_process_alive
from hydra_orch.core.checkpointer import IdempotencyConflictError, OptimisticLockError
from hydra_orch.core import folder_workspace
from hydra_orch.core.git_workspace import GitWorkspaceError, is_link_or_junction, win_long_path
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.core.conversation_route import ConversationRoute, route_from
from hydra_orch.core.conversation_context import prepare_context
from hydra_orch.core.model_selection import observed_identity
from hydra_orch.model import ContractViolation


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def _split_nul_paths(raw: bytes) -> list[str]:
    items: list[str] = []
    for chunk in raw.split(b"\0"):
        if not chunk:
            continue
        norm = chunk.decode("utf-8", errors="surrogateescape").replace("\\", "/").strip("/")
        if norm:
            items.append(norm)
    return items


def _batch_git_blob_shas(ws, root: Path, rel_paths: list[str]) -> dict[str, str]:
    if not rel_paths:
        return {}
    if all('"' not in p and "\n" not in p and "\r" not in p for p in rel_paths):
        stdin_data = ("\n".join(rel_paths) + "\n").encode("utf-8")
        res = ws._run_git_bytes(["hash-object", "--stdin-paths"], cwd=root, input_bytes=stdin_data)
        if res.returncode == 0:
            lines = [
                ln.strip().lower()
                for ln in res.stdout.decode("ascii", errors="replace").splitlines()
                if ln.strip()
            ]
            if len(lines) == len(rel_paths):
                return dict(zip(rel_paths, lines))
    out: dict[str, str] = {}
    for rel_posix in rel_paths:
        res = ws._run_git(["hash-object", "--path", rel_posix, "--", rel_posix], cwd=root)
        if res.returncode != 0:
            raise ContractViolation("git_command_failed", f"Não foi possível inspecionar '{rel_posix}'.")
        out[rel_posix] = res.stdout.strip().lower()
    return out


class ConversationService:
    _sync_locks: dict[str, asyncio.Lock] = {}

    def __init__(self, run_service, *, runner=None, attachments=None, routes=None, worker_timeout_seconds=300):
        self.runs = run_service
        self.store = run_service.store
        self.runner = runner or ConversationRunner()
        self.attachments = attachments
        self.routes = routes
        self.worker_timeout_seconds = worker_timeout_seconds
        self.coordinator = None
        self.owner = new_id("consumer")
        self.worker = None
        self.active = {}

    async def start(self):
        await self.store.initialize()
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._consume(), name="hydra-conversations")

    async def close(self):
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        for task in self.active.values():
            task.cancel()
        await asyncio.gather(*self.active.values(), return_exceptions=True)
        self.active.clear()

    @staticmethod
    async def _conversation(db, conversation_id):
        row = await (await db.execute("SELECT c.*,p.name AS project_name FROM conversations c JOIN projects p ON p.id=c.project_id WHERE c.id=?", (conversation_id,))).fetchone()
        if not row:
            raise ContractViolation("conversation_not_found", "Conversa não encontrada.")
        return dict(row)

    @staticmethod
    async def _event(db, cid, tid, kind, payload):
        cursor = await db.execute("INSERT INTO conversation_events(conversation_id,turn_id,type,payload_json) VALUES(?,?,?,?)",
                                  (cid, tid, kind, json.dumps(redact(payload), ensure_ascii=False)))
        await db.execute("UPDATE conversations SET last_seq=?,updated_at=datetime('now') WHERE id=?", (cursor.lastrowid, cid))
        return cursor.lastrowid

    def _promote(self, cid, project_id, draft_session_id, attachment_ids):
        refs = []
        if not attachment_ids:
            return refs
        if not self.attachments or draft_session_id not in {f"draft-{project_id}", cid}:
            raise ContractViolation("attachment_scope_mismatch", "Os anexos pertencem a outro projeto ou conversa.")
        for aid in attachment_ids:
            ref = self.attachments.get_attachment(aid, session_id=draft_session_id)
            if ref.transfer_status not in {"local_ready", "transferred"} or ref.host_id != "local":
                raise ContractViolation("attachment_not_ready", "Aguarde o envio do anexo antes de continuar.")
            content = self.attachments.read_attachment_bytes(aid, session_id=draft_session_id)
            copied = self.attachments.save_attachment(project_id, cid, ref.filename, content,
                                                     mime_type=ref.mime_type)
            refs.append(copied.model_dump(mode="json"))
        return refs

    async def create(self, *, project_id, executor, content, idempotency_key, access_mode="read-only",
                     draft_session_id=None, attachment_ids=(), route=None, execution_mode='single', auto_route=False):
        await self.store.initialize()
        project = await self.runs.get_project(project_id)
        if not project:
            raise ContractViolation("project_not_found", "Selecione um projeto cadastrado.")
        if executor not in {"codex", "claude"}:
            raise ContractViolation("agent_unavailable", "Escolha um agente compatível com conversa.")
        if access_mode not in {"read-only", "workspace-write"}:
            raise ContractViolation("invalid_access_mode", "Escolha o acesso ao projeto.")
        self._validate(content, idempotency_key)
        if execution_mode not in {'single', 'swarm'} or not isinstance(auto_route, bool):
            raise ContractViolation('route_invalid', 'Escolha um modo de trabalho válido.')
        selection = ConversationRoute.model_validate(route or {'executor': executor}).checked().model_dump()
        if selection['executor'] != executor:
            raise ContractViolation('route_invalid', 'A configuração precisa usar o mesmo agente escolhido.')
        request_hash = self.store.compute_request_hash({"project": project_id, "executor": executor,
            "content": content, "access": access_mode, "draft": draft_session_id, "attachments": list(attachment_ids),
            **({'route': selection} if route is not None else {}),
            **({'execution_mode': execution_mode, 'auto_route': auto_route} if execution_mode != 'single' or auto_route else {})})
        async with self.store._connect() as db:
            previous = await (await db.execute('SELECT * FROM conversation_commands WHERE idempotency_key=?', (idempotency_key,))).fetchone()
            if previous and previous['request_hash'] == request_hash:
                return {'conversation_id': previous['conversation_id'], 'created': False}
        selected = await self._validate_route(selection)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                previous = await (await db.execute("SELECT * FROM conversation_commands WHERE idempotency_key=?", (idempotency_key,))).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise IdempotencyConflictError("Este envio já foi usado para outro pedido.")
                    return {"conversation_id": previous["conversation_id"], "created": False}
                cid = new_id("conversation")
                refs = await asyncio.to_thread(self._promote, cid, project_id, draft_session_id, attachment_ids)
                await db.execute("INSERT INTO conversations(id,project_id,title,executor,access_mode,route_json,execution_mode,auto_route) VALUES(?,?,?,?,?,?,?,?)",
                                 (cid, project_id, content.strip()[:90], executor, access_mode, json.dumps(selected), execution_mode, int(auto_route)))
                await self._insert_turn(db, cid, content, idempotency_key, request_hash, refs, selected, 0, execution_mode, auto_route)
                await db.execute("INSERT INTO conversation_commands VALUES(?,?,?)", (idempotency_key, request_hash, cid))
        return {"conversation_id": cid, "created": True}

    @staticmethod
    def _validate(content, key):
        if not isinstance(content, str) or not content.strip() or len(content) > 100000 or "\x00" in content:
            raise ContractViolation("message_invalid", "Escreva uma mensagem de até 100 mil caracteres.")
        if not isinstance(key, str) or not 16 <= len(key) <= 100:
            raise ContractViolation("message_invalid", "O envio precisa de uma chave de identificação válida.")

    async def _validate_route(self, route, refresh=False):
        if self.routes:
            info = await self.routes.validate(route, refresh=refresh)
            return {k: info[k] for k in ('executor', 'connection_mode', 'target_kind', 'target_ref', 'fingerprint', 'cli_version', 'protocol', 'compatibility') if k in info}
        value = ConversationRoute.model_validate(route).checked().model_dump()
        if value['connection_mode'] != 'direct':
            raise ContractViolation('gateway_unavailable', 'A conexão OmniRoute não está configurada.')
        return value

    async def change_route(self, cid, *, route, expected_revision, idempotency_key, execution_mode=None, auto_route=None):
        self._validate('Configuração', idempotency_key)
        await self.store.initialize()
        selection = ConversationRoute.model_validate(route).checked().model_dump()
        if execution_mode is not None and execution_mode not in {'single', 'swarm'}:
            raise ContractViolation('route_invalid', 'Escolha um modo de trabalho válido.')
        request_hash = self.store.compute_request_hash({'route': selection, 'revision': expected_revision,
            **({'execution_mode': execution_mode} if execution_mode is not None else {}), **({'auto_route':auto_route} if auto_route is not None else {})})
        async with self.store._connect() as db:
            old = await (await db.execute('SELECT * FROM conversation_route_commands WHERE conversation_id=? AND idempotency_key=?', (cid, idempotency_key))).fetchone()
            if old:
                if old['request_hash'] != request_hash:
                    raise IdempotencyConflictError('Esta mudança já foi usada para outra configuração.')
                return json.loads(old['response_json'])
        selected = await self._validate_route(selection, refresh=True)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                old = await (await db.execute('SELECT * FROM conversation_route_commands WHERE conversation_id=? AND idempotency_key=?', (cid, idempotency_key))).fetchone()
                if old:
                    if old['request_hash'] != request_hash:
                        raise IdempotencyConflictError('Esta mudança já foi usada para outra configuração.')
                    return json.loads(old['response_json'])
                conv = await self._conversation(db, cid)
                if conv['route_revision'] != expected_revision:
                    raise OptimisticLockError('A configuração mudou em outra janela. Atualize e tente novamente.')
                revision = expected_revision + 1
                # Capture the original attribution before changing a legacy chat's
                # executor. An older backend may have persisted turns without a route.
                await db.execute("UPDATE conversation_turns SET route_json=? WHERE conversation_id=? AND route_json='{}'",
                                 (json.dumps(ConversationRoute(executor=conv['executor']).model_dump()), cid))
                await db.execute('UPDATE conversations SET route_json=?,route_revision=?,executor=?,native_session_id=NULL,execution_mode=?,auto_route=? WHERE id=?',
                                 (json.dumps(selected), revision, selected['executor'], execution_mode or conv['execution_mode'],
                                  int(auto_route) if auto_route is not None else conv['auto_route'], cid))
                await self._event(db, cid, None, 'conversation.route.updated', {'route': selected, 'revision': revision})
                result = {'route': selected, 'route_revision': revision}
                await db.execute('INSERT INTO conversation_route_commands VALUES(?,?,?,?)', (cid, idempotency_key, request_hash, json.dumps(result)))
                return result

    async def _insert_turn(self, db, cid, content, key, request_hash, attachments, route=None, revision=0, execution_mode='single', auto_route=False):
        ordinal = (await (await db.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM conversation_turns WHERE conversation_id=?", (cid,))).fetchone())[0]
        tid = new_id("turn")
        await db.execute("""INSERT INTO conversation_turns(id,conversation_id,ordinal,idempotency_key,request_hash,content,attachment_json,route_json,route_revision,execution_mode,auto_route)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (tid, cid, ordinal, key, request_hash, redact_text(content), json.dumps(attachments), json.dumps(route or {}), revision, execution_mode, int(auto_route)))
        seq = await self._event(db, cid, tid, "turn.queued", {"content": content, "ordinal": ordinal})
        return {"conversation_id": cid, "turn_id": tid, "seq": seq}

    async def send(self, cid, *, content, idempotency_key, expected_last_seq, draft_session_id=None, attachment_ids=(), expected_route_revision=None):
        self._validate(content, idempotency_key)
        await self.store.initialize()
        request_hash = self.store.compute_request_hash({"content": content, "seq": expected_last_seq,
            "draft": draft_session_id, "attachments": list(attachment_ids),
            **({'route_revision': expected_route_revision} if expected_route_revision is not None else {})})
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                conv = await self._conversation(db, cid)
                prior = await (await db.execute("SELECT * FROM conversation_turns WHERE conversation_id=? AND idempotency_key=?", (cid, idempotency_key))).fetchone()
                if prior:
                    if prior["request_hash"] != request_hash:
                        raise IdempotencyConflictError("Este envio já foi usado para outra mensagem.")
                    return {"conversation_id": cid, "turn_id": prior["id"], "seq": conv["last_seq"]}
                selected_route = route_from(conv)
                if ((expected_route_revision is None and (conv['route_revision'] != 0 or selected_route['target_ref'] or selected_route['connection_mode'] != 'direct'))
                        or expected_route_revision is not None and expected_route_revision != conv['route_revision']):
                    raise OptimisticLockError('A configuração da conversa mudou. Atualize antes de enviar; sua mensagem foi preservada.')
                latest_message = (await (await db.execute("SELECT COALESCE(MAX(seq),0) FROM conversation_events WHERE conversation_id=? AND type='turn.queued'", (cid,))).fetchone())[0]
                # Streaming output must not make the composer stale. Only a newer user send conflicts.
                if expected_last_seq > conv["last_seq"] or latest_message > expected_last_seq:
                    raise OptimisticLockError("A conversa mudou. Atualize e envie sua mensagem novamente.")
                pending = (await (await db.execute("SELECT COUNT(*) FROM conversation_turns WHERE conversation_id=? AND state='queued'", (cid,))).fetchone())[0]
                if pending >= 10:
                    raise ContractViolation("conversation_queue_full", "Aguarde as mensagens pendentes antes de enviar outra.")
                refs = await asyncio.to_thread(self._promote, cid, conv["project_id"], draft_session_id, attachment_ids)
                return await self._insert_turn(db, cid, content, idempotency_key, request_hash, refs, route_from(conv), conv['route_revision'], conv['execution_mode'], bool(conv['auto_route']))

    async def list(self, project_id=None, offset=0, limit=30, q=None):
        await self.store.initialize()
        async with self.store._connect() as db:
            clauses, params = [], []
            if project_id:
                clauses.append("project_id=?")
                params.append(project_id)
            if q:
                await db.create_function("hydra_casefold", 1, lambda value: str(value).casefold())
                clauses.append("instr(hydra_casefold(title),hydra_casefold(?))>0")
                params.append(q)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            rows = await (await db.execute(f"SELECT * FROM conversations {where} ORDER BY updated_at DESC,id LIMIT ? OFFSET ?", (*params, limit, offset))).fetchall()
            total = (await (await db.execute(f"SELECT COUNT(*) FROM conversations {where}", params)).fetchone())[0]
            return {"items": [dict(r) for r in rows], "total": total}

    async def snapshot(self, cid):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                conv = await self._conversation(db, cid)
                conv['route'] = route_from(conv)
                conv['auto_route'] = bool(conv['auto_route'])
                turns = await (await db.execute("SELECT * FROM conversation_turns WHERE conversation_id=? ORDER BY ordinal", (cid,))).fetchall()
                events = await (await db.execute("SELECT * FROM conversation_events WHERE conversation_id=? AND type LIKE 'tool.%' ORDER BY seq DESC LIMIT 50", (cid,))).fetchall()
                conv["turns"] = [self._public_turn(dict(t)) for t in turns]
                conv["tools"] = [{**dict(e), "payload": json.loads(e["payload_json"])} for e in reversed(events)]
                agent_rows = await (await db.execute("SELECT turn_id,payload_json FROM conversation_events WHERE conversation_id=? AND type='agent.observed' ORDER BY seq DESC LIMIT 1000", (cid,))).fetchall()
                agents = {}
                for event in reversed(agent_rows):
                    payload = json.loads(event['payload_json'])
                    agent = {**payload, 'turn_id': event['turn_id']}
                    identity = observed_identity(payload.get('model'), 'cli', {})
                    if identity:
                        agent['identity'] = identity
                    agents[(event['turn_id'], payload['id'])] = agent
                conv['agents'] = list(agents.values())
                return conv

    @staticmethod
    def _public_turn(turn):
        for key in ("lease_owner", "lease_until", "process_pid", "request_hash", "idempotency_key"):
            turn.pop(key, None)
        turn["attachments"] = json.loads(turn.pop("attachment_json"))
        turn['route'] = json.loads(turn.pop('route_json', '{}'))
        turn['context_checkpoint'] = json.loads(turn.pop('context_checkpoint_json', '{}'))
        execution = turn['context_checkpoint'].get('execution', {})
        turn['identity'] = execution.get('identity') or turn['context_checkpoint'].get('observed_model')
        if not turn['identity'] and execution.get('model_source') == 'omniroute.responses':
            for model in reversed(execution.get('models', [])):
                turn['identity'] = observed_identity(model, execution['model_source'], turn['route'])
                if turn['identity']:
                    break
        turn['effective_route'] = turn['context_checkpoint'].get('effective_route')
        turn['coordination'] = json.loads(turn.pop('coordination_json', '{}'))
        turn['auto_route'] = bool(turn['auto_route'])
        return turn

    async def events(self, cid, after=0):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._conversation(db, cid)
            rows = await (await db.execute("SELECT * FROM conversation_events WHERE conversation_id=? AND seq>? ORDER BY seq LIMIT 200", (cid, after))).fetchall()
            return [{"seq": r["seq"], "turn_id": r["turn_id"], "type": r["type"], "payload": json.loads(r["payload_json"])} for r in rows]

    async def cancel(self, cid, tid):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._conversation(db, cid)
                turn = await (await db.execute("SELECT * FROM conversation_turns WHERE id=? AND conversation_id=?", (tid, cid))).fetchone()
                if not turn:
                    raise ContractViolation("turn_not_found", "Mensagem não encontrada.")
                state = turn["state"]
                if state in {"queued", "running"}:
                    target = "cancelled" if state == "queued" else "stopping"
                    await db.execute("UPDATE conversation_turns SET state=? WHERE id=?", (target, tid))
                    await self._event(db, cid, tid, f"turn.{target}", {})
        # The lease owner observes stopping and kills its own process, even in another server.
        if tid in self.active:
            await self.runner.cancel(tid)
        return {"state": "stopping" if state == "running" else "cancelled" if state == "queued" else state}

    @classmethod
    def _get_sync_lock(cls, source_root: Path) -> asyncio.Lock:
        key = os.path.normcase(os.path.abspath(str(source_root)))
        lock = cls._sync_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._sync_locks[key] = lock
        return lock

    async def _load_conversation_for_sync(self, db, conversation_id: str) -> dict:
        row = await (await db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,))).fetchone()
        if not row:
            raise ContractViolation("resource_not_found", "Conversa não encontrada.")
        conv = dict(row)
        if conv["access_mode"] != "workspace-write":
            raise ContractViolation(
                "workspace_readonly",
                "Esta conversa está em modo somente leitura e não possui alterações para aplicar.",
            )
        busy = await (
            await db.execute(
                "SELECT 1 FROM conversation_turns WHERE conversation_id=? AND state IN ('running','stopping') LIMIT 1",
                (conversation_id,),
            )
        ).fetchone()
        if busy:
            raise ContractViolation(
                "conversation_busy",
                "Aguarde o término do turno atual antes de aplicar alterações ao projeto.",
            )
        if not conv.get("workspace_path"):
            raise ContractViolation(
                "workspace_readonly",
                "Esta conversa está em modo somente leitura e não possui alterações para aplicar.",
            )
        return conv

    def _resolve_sync_target(self, conv: dict, project: dict) -> tuple[str, Path, Path]:
        source_root = Path(project["canonical_root"])
        raw_ws_path = Path(conv["workspace_path"])
        folder_dir = self.runs.runtime_dir / "folder_workspace" / conv["id"]
        folder_work = folder_dir / "work"
        is_folder_mode = project.get("workspace_kind") == "folder" or (
            not is_link_or_junction(raw_ws_path)
            and not is_link_or_junction(folder_work)
            and raw_ws_path.resolve(strict=False) == folder_work.resolve(strict=False)
        )
        if is_folder_mode:
            if is_link_or_junction(raw_ws_path) or raw_ws_path.resolve(strict=False) != folder_work.resolve(strict=False):
                raise ContractViolation("workspace_invalid", "A pasta desta conversa mudou. Abra um novo chat.")
            return "folder", source_root, folder_dir
        return "git", source_root, raw_ws_path

    def _inspect_git_worktree_sync(self, source_root: Path, raw_ws_path: Path, base_sha_hint: str | None):
        if is_link_or_junction(source_root):
            raise ContractViolation("scope_violation", "O repositório original contém um link que exige revisão.")
        try:
            ws = self.runs._get_git_workspace(source_root)
        except GitWorkspaceError as exc:
            raise ContractViolation(exc.failure.code, exc.failure.message) from exc

        if is_link_or_junction(raw_ws_path):
            raise ContractViolation("scope_violation", "A cópia isolada contém um link que exige revisão.")
        cwd_candidate = raw_ws_path.resolve(strict=False)
        if (
            not cwd_candidate.is_relative_to(ws.worktree_base_dir.resolve())
            or not win_long_path(cwd_candidate).is_dir()
            or not win_long_path(cwd_candidate / ".git").exists()
        ):
            raise ContractViolation(
                "workspace_missing",
                "A pasta desta conversa não está disponível. Restaure-a antes de continuar.",
            )
        try:
            cwd_real = ws._verify_worktree_git_file(cwd_candidate)
            base_sha = ws.resolve_commit_sha(base_sha_hint if base_sha_hint else "HEAD", cwd=cwd_real)
        except GitWorkspaceError as exc:
            raise ContractViolation(exc.failure.code, exc.failure.message) from exc

        folder_workspace.assert_no_links_in_tree(cwd_real)

        runtime_rel_prefix: str | None = None
        try:
            rel_rt = self.runs.runtime_dir.resolve().relative_to(ws.repo_root.resolve())
            runtime_rel_prefix = rel_rt.as_posix().strip("/")
        except ValueError:
            runtime_rel_prefix = None

        def skip_rel(rel_posix: str) -> bool:
            if folder_workspace.is_ignored_rel_path(rel_posix):
                return True
            if runtime_rel_prefix and (
                rel_posix == runtime_rel_prefix or rel_posix.startswith(f"{runtime_rel_prefix}/")
            ):
                return True
            return False

        ls_res = ws._run_git_bytes(["ls-tree", "-r", "-z", base_sha], cwd=cwd_real)
        if ls_res.returncode != 0:
            raise ContractViolation("workspace_invalid", "Não foi possível ler a revisão base da conversa.")
        base_blobs: dict[str, str] = {}
        for entry in ls_res.stdout.split(b"\0"):
            if not entry or b"\t" not in entry:
                continue
            meta_raw, path_raw = entry.split(b"\t", 1)
            rel_posix = path_raw.decode("utf-8", errors="surrogateescape").replace("\\", "/").strip("/")
            if not rel_posix or skip_rel(rel_posix):
                continue
            parts = meta_raw.decode("ascii", errors="replace").split()
            if len(parts) >= 3:
                base_blobs[rel_posix] = parts[2].lower()

        cwd_diff = ws._run_git_bytes(["diff", "--name-only", "--no-renames", "-z", base_sha], cwd=cwd_real)
        cwd_untracked = ws._run_git_bytes(["ls-files", "--others", "--exclude-standard", "-z"], cwd=cwd_real)
        if cwd_diff.returncode != 0 or cwd_untracked.returncode != 0:
            raise ContractViolation("git_command_failed", "Não foi possível inspecionar as alterações da conversa.")

        cwd_candidates = sorted(
            {
                p
                for p in (_split_nul_paths(cwd_diff.stdout) + _split_nul_paths(cwd_untracked.stdout))
                if not skip_rel(p)
            }
        )
        cwd_hash_targets: list[str] = []
        for rel_posix in cwd_candidates:
            rel_path = folder_workspace.validate_sync_rel_path(rel_posix)
            if folder_workspace.has_link_on_rel_path(cwd_real, rel_path):
                raise ContractViolation(
                    "scope_violation",
                    "A cópia contém um link que exige revisão. Os arquivos foram preservados.",
                )
            if rel_posix in base_blobs and win_long_path(cwd_real / rel_posix).is_file():
                cwd_hash_targets.append(rel_posix)

        cwd_shas = _batch_git_blob_shas(ws, cwd_real, cwd_hash_targets)
        agent_added: list[str] = []
        agent_modified: list[str] = []
        agent_deleted: list[str] = []
        for rel_posix in cwd_candidates:
            in_base = rel_posix in base_blobs
            in_work = win_long_path(cwd_real / rel_posix).is_file()
            if not in_base and in_work:
                agent_added.append(rel_posix)
            elif in_base and not in_work:
                agent_deleted.append(rel_posix)
            elif in_base and in_work and cwd_shas[rel_posix] != base_blobs[rel_posix]:
                agent_modified.append(rel_posix)

        agent_changed_set = set(agent_added) | set(agent_modified) | set(agent_deleted)
        agent_present_set = set(agent_added) | set(agent_modified)

        src_diff = ws._run_git_bytes(["diff", "--name-only", "--no-renames", "-z", base_sha], cwd=ws.repo_root)
        src_untracked = ws._run_git_bytes(["ls-files", "--others", "--exclude-standard", "-z"], cwd=ws.repo_root)
        if src_diff.returncode != 0 or src_untracked.returncode != 0:
            raise ContractViolation("git_command_failed", "Não foi possível inspecionar o estado do repositório.")

        src_candidates = sorted(
            {
                p
                for p in (_split_nul_paths(src_diff.stdout) + _split_nul_paths(src_untracked.stdout))
                if not skip_rel(p)
            }
            | agent_changed_set
        )

        src_hash_targets: list[str] = []
        for rel_posix in src_candidates:
            if folder_workspace.has_link_on_rel_path(ws.repo_root, Path(rel_posix)):
                continue
            if (rel_posix in base_blobs or rel_posix in agent_present_set) and win_long_path(
                ws.repo_root / rel_posix
            ).is_file():
                src_hash_targets.append(rel_posix)

        src_shas = _batch_git_blob_shas(ws, ws.repo_root, src_hash_targets)
        added_work_shas = _batch_git_blob_shas(
            ws,
            cwd_real,
            [p for p in agent_added if p in src_shas],
        )

        external_changed: list[str] = []
        conflicts_set: set[str] = set()
        link_hazards: list[str] = []

        for rel_posix in src_candidates:
            rel_path = Path(rel_posix)
            if folder_workspace.has_link_on_rel_path(ws.repo_root, rel_path):
                external_changed.append(rel_posix)
                if rel_posix in agent_changed_set:
                    link_hazards.append(rel_posix)
                    conflicts_set.add(rel_posix)
                continue

            in_base = rel_posix in base_blobs
            src_target = ws.repo_root / rel_path
            in_src = win_long_path(src_target).is_file()
            ext_diff = False
            if not in_base and in_src:
                ext_diff = True
            elif in_base and not in_src:
                ext_diff = True
            elif in_base and in_src and src_shas[rel_posix] != base_blobs[rel_posix]:
                ext_diff = True

            if ext_diff:
                external_changed.append(rel_posix)

            if rel_posix in agent_changed_set:
                if rel_posix in agent_present_set:
                    if win_long_path(src_target).is_dir():
                        conflicts_set.add(rel_posix)
                        continue
                    parent_rel = rel_path.parent
                    collision = False
                    while parent_rel != Path("."):
                        if win_long_path(ws.repo_root / parent_rel).is_file():
                            collision = True
                            break
                        parent_rel = parent_rel.parent
                    if collision:
                        conflicts_set.add(rel_posix)
                        continue

                if ext_diff:
                    in_work = rel_posix in agent_present_set
                    if not in_work and not in_src:
                        pass
                    elif in_work and in_src:
                        work_sha = cwd_shas.get(rel_posix) or added_work_shas.get(rel_posix)
                        same_bytes = filecmp.cmp(
                            win_long_path(cwd_real / rel_posix),
                            win_long_path(src_target),
                            shallow=False,
                        ) or (work_sha is not None and work_sha == src_shas.get(rel_posix))
                        if not same_bytes:
                            conflicts_set.add(rel_posix)
                    else:
                        conflicts_set.add(rel_posix)

        conflicts = sorted(conflicts_set)
        has_agent_changes = bool(agent_added or agent_modified or agent_deleted)
        status = {
            "has_agent_changes": has_agent_changes,
            "clean_to_apply": len(conflicts) == 0,
            "agent_added": agent_added,
            "agent_modified": agent_modified,
            "agent_deleted": agent_deleted,
            "external_changed": sorted(set(external_changed)),
            "conflicts": conflicts,
        }
        return ws, cwd_real, base_sha, link_hazards, status

    def _apply_git_worktree_sync(
        self,
        source_root: Path,
        raw_ws_path: Path,
        base_sha_hint: str | None,
        *,
        force: bool = False,
    ) -> tuple[dict, str]:
        ws, cwd_real, base_sha, link_hazards, status = self._inspect_git_worktree_sync(
            source_root, raw_ws_path, base_sha_hint
        )
        if link_hazards:
            raise ContractViolation(
                "scope_violation",
                "O caminho de destino no repositório contém um link que exige revisão.",
            )

        repo_resolved = ws.repo_root.resolve()
        all_targets = [*status["agent_added"], *status["agent_modified"], *status["agent_deleted"]]
        for rel_posix in all_targets:
            rel_path = folder_workspace.validate_sync_rel_path(rel_posix)
            if folder_workspace.has_link_on_rel_path(ws.repo_root, rel_path) or folder_workspace.has_link_on_rel_path(
                cwd_real, rel_path
            ):
                raise ContractViolation(
                    "scope_violation",
                    "O caminho de destino no repositório contém um link que exige revisão.",
                )
            if not (ws.repo_root / rel_path).resolve(strict=False).is_relative_to(repo_resolved):
                raise ContractViolation(
                    "scope_violation",
                    "O caminho de destino sai do repositório original do projeto.",
                )

        if status["conflicts"] and not force:
            exc = ContractViolation(
                "workspace_sync_conflict",
                f"Conflito ao aplicar alterações: o repositório original foi modificado externamente em {', '.join(status['conflicts'][:5])}.",
            )
            exc.conflicts = list(status["conflicts"])
            raise exc

        applied_files = sorted(status["agent_added"] + status["agent_modified"])
        deleted_files = list(status["agent_deleted"])

        for rel_posix in deleted_files:
            src_target = ws.repo_root / rel_posix
            if win_long_path(src_target).is_dir():
                raise ContractViolation(
                    "workspace_sync_conflict",
                    f"Conflito ao aplicar alterações: '{rel_posix}' tornou-se uma pasta no repositório.",
                )
            win_long_path(src_target).unlink(missing_ok=True)
            folder_workspace.prune_empty_parents(src_target, ws.repo_root)

        for rel_posix in applied_files:
            src_target = ws.repo_root / rel_posix
            if win_long_path(src_target).is_dir():
                raise ContractViolation(
                    "workspace_sync_conflict",
                    f"Conflito ao aplicar alterações: '{rel_posix}' é uma pasta no repositório.",
                )
            folder_workspace.atomic_copy_file(cwd_real / rel_posix, src_target)

        new_base_sha = base_sha
        all_synced = sorted(set(applied_files) | set(deleted_files))
        if all_synced:
            add_res = ws._run_git(["add", "-A", "--", *all_synced], cwd=cwd_real)
            if add_res.returncode != 0:
                raise ContractViolation("git_command_failed", "Não foi possível atualizar o índice da cópia isolada.")
            cached_diff = ws._run_git(["diff", "--cached", "--quiet"], cwd=cwd_real)
            if cached_diff.returncode != 0:
                git_env = {
                    "GIT_AUTHOR_NAME": ws.git_author_name,
                    "GIT_AUTHOR_EMAIL": ws.git_author_email,
                    "GIT_COMMITTER_NAME": ws.git_author_name,
                    "GIT_COMMITTER_EMAIL": ws.git_author_email,
                }
                commit_res = ws._run_git(
                    ["commit", "--no-verify", "-m", "chore: checkpoint applied conversation changes"],
                    cwd=cwd_real,
                    extra_env=git_env,
                )
                if commit_res.returncode != 0:
                    raise ContractViolation(
                        "git_command_failed",
                        "Não foi possível registrar a revisão aplicada na cópia isolada.",
                    )
            new_base_sha = ws.resolve_commit_sha("HEAD", cwd=cwd_real)

        has_changes = bool(applied_files or deleted_files)
        result = {
            "status": "applied" if has_changes else "noop",
            "applied_files": applied_files,
            "deleted_files": deleted_files,
            "conflicts": list(status["conflicts"]),
        }
        return result, new_base_sha

    async def inspect_changes(self, conversation_id: str, *, path: str | None = None, include_context: bool = False) -> dict:
        await self.store.initialize()
        async with self.store._connect() as db:
            conv = await self._load_conversation_for_sync(db, conversation_id)
        project = await self.runs.get_project(conv["project_id"])
        if not project:
            raise ContractViolation("resource_not_found", "Projeto da conversa não encontrado.")
        mode, source_root, ws_target = self._resolve_sync_target(conv, project)
        def review():
            if mode == "folder":
                status = folder_workspace.inspect_sync_status(source_root, ws_target)
            else:
                ws, working, baseline, _, status = self._inspect_git_worktree_sync(source_root, ws_target, conv.get('base_sha'))
            result = {"mode": mode, **status}
            if include_context:
                result.update(project_name=project['name'], title=conv['title'])
            if path is None:
                return result
            if path not in (*status['agent_added'], *status['agent_modified'], *status['agent_deleted']):
                raise ContractViolation('resource_not_found', 'O arquivo não está na revisão atual.')
            if mode == 'folder':
                patch = folder_workspace.diff(ws_target / 'base', ws_target / 'work', path=Path(path))
            else:
                work = working / path
                version = ws._run_git(['cat-file', '-s', f'{baseline}:{path}'], cwd=working)
                before_size = int(version.stdout.strip()) if version.returncode == 0 and version.stdout.strip().isdigit() else 0
                after_size = win_long_path(work).stat().st_size if win_long_path(work).is_file() else 0
                if max(before_size, after_size) > 100000:
                    patch = 'Arquivo grande. A alteração pode ser aplicada ao projeto.'
                else:
                    patch = ws._run_git(['diff', '--no-ext-diff', '--no-textconv', baseline, '--', f':(literal){path}'], cwd=working).stdout
                    if not patch and path in status['agent_added']:
                        patch = ws._run_git(['diff', '--no-index', '--no-ext-diff', '--no-textconv', '--', os.devnull, path], cwd=working).stdout
            return {**result, 'path': path, 'diff': redact_text(patch)[:200000]}
        async with self._get_sync_lock(source_root):
            return await asyncio.to_thread(review)

    async def apply_changes(self, conversation_id: str, *, force: bool = False) -> dict:
        await self.store.initialize()
        async with self.store._connect() as db:
            conv = await self._load_conversation_for_sync(db, conversation_id)
        project = await self.runs.get_project(conv["project_id"])
        if not project:
            raise ContractViolation("resource_not_found", "Projeto da conversa não encontrado.")
        mode, source_root, ws_target = self._resolve_sync_target(conv, project)
        sync_lock = self._get_sync_lock(source_root)
        async with sync_lock:
            async with self.store._connect() as db:
                conv = await self._load_conversation_for_sync(db, conversation_id)
            mode, source_root, ws_target = self._resolve_sync_target(conv, project)
            new_base_sha: str | None = None
            if mode == "folder":
                result = await asyncio.to_thread(
                    folder_workspace.apply_to_source, source_root, ws_target, force=force
                )
            else:
                result, new_base_sha = await asyncio.to_thread(
                    self._apply_git_worktree_sync,
                    source_root,
                    ws_target,
                    conv.get("base_sha"),
                    force=force,
                )

            event_payload = {
                "mode": mode,
                "status": result["status"],
                "applied_files": result["applied_files"],
                "deleted_files": result["deleted_files"],
            }
            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    if new_base_sha is not None and new_base_sha != conv.get("base_sha"):
                        await db.execute(
                            "UPDATE conversations SET base_sha=? WHERE id=?",
                            (new_base_sha, conversation_id),
                        )
                    seq = await self._event(db, conversation_id, None, "conversation.applied", event_payload)
            return {"mode": mode, **result, "seq": seq}

    async def claim(self):
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("""SELECT t.* FROM conversation_turns t
                    WHERE t.state='queued' AND NOT EXISTS(SELECT 1 FROM conversation_turns a
                    WHERE a.conversation_id=t.conversation_id AND (a.state IN ('running','stopping') OR (a.state='queued' AND a.ordinal<t.ordinal)))
                    ORDER BY t.created_at,t.ordinal LIMIT 1""")).fetchone()
                if not row:
                    return None
                turn = dict(row)
                await db.execute("UPDATE conversation_turns SET state='running',lease_owner=?,lease_until=? WHERE id=?", (self.owner, time.time()+60, turn["id"]))
                await self._event(db, turn["conversation_id"], turn["id"], "turn.running", {})
                return turn

    async def reconcile(self):
        """Never automatically replay a claimed prompt after a crash or uncertain process exit."""
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                rows = await (await db.execute("SELECT * FROM conversation_turns WHERE state IN ('running','stopping') AND lease_until<?", (time.time(),))).fetchall()
                for row in rows:
                    if row["process_pid"] and is_process_alive(row["process_pid"]):
                        # Fail closed: PID may have been reused; don't kill an unrelated process.
                        await db.execute("UPDATE conversation_turns SET state='stopping',error=? WHERE id=?", ("Conexão com o agente perdida. Aguardando confirmar seu encerramento.", row["id"]))
                        continue
                    message = "A execução foi interrompida. O pedido não foi reenviado automaticamente; envie uma nova mensagem para continuar."
                    await db.execute("UPDATE conversation_turns SET state='failed',error=?,finished_at=datetime('now') WHERE id=?", (message, row["id"]))
                    await self._event(db, row["conversation_id"], row["id"], "turn.failed", {"error": message})

    async def _consume(self):
        while True:
            try:
                await self.reconcile()
                for tid, task in list(self.active.items()):
                    if task.done():
                        await asyncio.gather(task, return_exceptions=True)
                        del self.active[tid]
                if len(self.active) < 2:
                    turn = await self.claim()
                    if turn:
                        self.active[turn["id"]] = asyncio.create_task(self._execute(turn))
                        continue
            except asyncio.CancelledError:
                raise
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Conversation queue reconciliation failed")
            await asyncio.sleep(.25)

    async def _emit(self, turn, kind, payload):
        cid, tid = turn["conversation_id"], turn["id"]
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT state,lease_owner FROM conversation_turns WHERE id=?", (tid,))).fetchone()
                if row["lease_owner"] != self.owner or row["state"] not in {"running", "stopping"}:
                    raise ContractViolation("turn_lease_lost", "A execução perdeu a conexão com o servidor.")
                if kind == "text.delta":
                    text = redact_text(payload["text"])
                    await db.execute("UPDATE conversation_turns SET response=response || ? WHERE id=?", (text, tid))
                elif kind == "session.started":
                    await db.execute('UPDATE conversation_turns SET native_session_id=? WHERE id=?', (payload['session_id'], tid))
                    await db.execute("UPDATE conversations SET native_session_id=? WHERE id=? AND route_revision=?", (payload["session_id"], cid, turn['route_revision']))
                elif kind == "process.started":
                    await db.execute("UPDATE conversation_turns SET process_pid=? WHERE id=?", (payload["pid"], tid))
                elif kind == 'execution.metrics':
                    await db.execute("UPDATE conversation_turns SET context_checkpoint_json=json_set(context_checkpoint_json,'$.execution',json(?)) WHERE id=?",
                                     (json.dumps(redact(payload)), tid))
                elif kind == 'execution.model':
                    await db.execute("UPDATE conversation_turns SET context_checkpoint_json=json_set(context_checkpoint_json,'$.observed_model',json(?)) WHERE id=?",
                                     (json.dumps(redact(payload)), tid))
                elif kind in ('execution.route', 'coordinator.route'):
                    await db.execute("UPDATE conversation_turns SET context_checkpoint_json=json_set(context_checkpoint_json,'$.effective_route',json(?),'$.route_reason',?) WHERE id=?",
                                     (json.dumps(redact(payload['route'])), redact_text(payload['reason']), tid))
                elif kind.startswith('coordinator.'):
                    if kind == 'coordinator.plan':
                        await db.execute("UPDATE conversation_turns SET coordination_json=json_set(coordination_json,'$.plan',json(?),'$.run_id',?) WHERE id=?", (json.dumps(redact(payload['plan'])),payload['run_id'],tid))
                    elif kind == 'coordinator.run':
                        await db.execute("UPDATE conversation_turns SET coordination_json=json_set(coordination_json,'$.phase',?,'$.run_id',?) WHERE id=?", (payload['phase'],payload['run_id'],tid))
                    elif kind == 'coordinator.task':
                        await db.execute("UPDATE conversation_turns SET coordination_json=json_set(coordination_json,?,json(?)) WHERE id=?", ('$.tasks.'+payload['task_id'],json.dumps(redact(payload)),tid))
                await self._event(db, cid, tid, kind, payload)
        if kind == "process.started" and row["state"] == "stopping":
            raise ContractViolation("turn_cancelled", "A execução foi interrompida antes do envio ao agente.")

    async def _heartbeat(self, tid):
        while True:
            async with self.store._connect() as db:
                row = await (await db.execute("SELECT state,lease_owner FROM conversation_turns WHERE id=?", (tid,))).fetchone()
                if row["lease_owner"] != self.owner:
                    if self.coordinator and tid in self.coordinator.active:
                        self.coordinator.active[tid].cancel()
                    else:
                        await self.runner.cancel(tid)
                    return
                await db.execute("UPDATE conversation_turns SET lease_until=? WHERE id=? AND lease_owner=?", (time.time()+60, tid, self.owner))
                if row["state"] == "stopping":
                    if self.coordinator and tid in self.coordinator.active:
                        self.coordinator.active[tid].cancel()
                    else:
                        await self.runner.cancel(tid)
            await asyncio.sleep(.5)

    async def _workspace(self, conv):
        project = await self.runs.get_project(conv["project_id"])
        conv["workspace_kind"] = project.get("workspace_kind", "git")
        if conv["workspace_kind"] == "folder":
            from hydra_orch.core.folder_workspace import snapshot
            directory = self.runs.runtime_dir / "folder_workspace" / conv["id"]
            path = await asyncio.to_thread(snapshot, Path(project["canonical_root"]), directory)
            if conv["workspace_path"] and Path(conv["workspace_path"]).resolve() != path.resolve():
                raise ContractViolation("workspace_invalid", "A pasta desta conversa mudou. Abra um novo chat.")
            async with self.store._connect() as db:
                await db.execute("UPDATE conversations SET workspace_path=? WHERE id=?", (str(path), conv["id"]))
            conv["workspace_path"] = str(path)
            return None, path
        ws = self.runs._get_git_workspace(project["canonical_root"])
        if conv["workspace_path"]:
            path = Path(conv["workspace_path"]).resolve()
            if not path.is_relative_to(ws.worktree_base_dir.resolve()) or not path.is_dir() or not (path / ".git").exists():
                raise ContractViolation("workspace_missing", "A pasta desta conversa não está disponível. Restaure-a antes de continuar.")
            return ws, path
        base = await asyncio.to_thread(ws.resolve_commit_sha, "HEAD")
        record = await asyncio.to_thread(ws.create_worktree, conv["id"], "chat", conv["id"], base,
                                        branch_name=f"codex/chat-{conv['id'].split('-')[-1][:16]}")
        async with self.store._connect() as db:
            await db.execute("UPDATE conversations SET workspace_path=?,base_sha=? WHERE id=?", (str(record.canonical_path), base, conv["id"]))
        conv["workspace_path"], conv["base_sha"] = str(record.canonical_path), base
        return ws, record.canonical_path

    def _prepare_prompt(self, conv, turns, turn, cwd):
        refs = json.loads(turn["attachment_json"])
        attachment_lines = []
        if refs:
            directory = cwd / ".orchestrator" / "chat_attachment" / turn["id"]
            if not directory.resolve().is_relative_to(cwd.resolve()):
                raise ContractViolation("attachment_path_escape", "A pasta de anexos está fora do projeto.")
            directory.mkdir(parents=True, exist_ok=True)
            for ref in refs:
                data = self.attachments.read_attachment_bytes(ref["attachment_id"], session_id=conv["id"])
                target = directory / (ref["attachment_id"] + Path(ref["filename"]).suffix)
                if is_link_or_junction(target):
                    raise ContractViolation("attachment_path_escape", "O destino do anexo não é seguro.")
                target.write_bytes(data)
                attachment_lines.append(f"{ref['filename']}: {target}")
        preamble = "Responda em português. Trabalhe somente nesta pasta isolada. Não faça commit, push ou integração. "
        preamble += "O modo desta conversa é " + conv["access_mode"] + ".\n"
        history, checkpoint = prepare_context(conv, turns, turn, cwd)
        conv['_context_checkpoint'] = checkpoint
        if not conv.get("native_session_id"):
            preamble += "Histórico da conversa:\n" + history + "\n\n"
        return preamble + "Pedido atual:\n" + turn["content"] + ("\nAnexos disponíveis para leitura:\n" + "\n".join(attachment_lines) if refs else "")

    async def _execute(self, turn):
        cid, tid = turn["conversation_id"], turn["id"]
        heartbeat = asyncio.create_task(self._heartbeat(tid))
        state, error, diff = "completed", None, ""
        try:
            conv = await self.snapshot(cid)
            stored_turn = next(t for t in conv['turns'] if t['id'] == tid)
            selection = stored_turn['route'] or ConversationRoute(executor=conv['executor']).model_dump()
            conv['executor'] = selection['executor']
            conv['route'] = selection
            conv['execution_mode'] = stored_turn['execution_mode']
            conv['auto_route'] = stored_turn['auto_route']
            conv['_image_input'] = any(ref.get('mime_type', '').startswith('image/') for ref in stored_turn['attachments'])
            agent_state = self.runs.runtime_dir / 'conversation_agent' / cid
            if not agent_state.resolve().is_relative_to(self.runs.runtime_dir.resolve()):
                raise ContractViolation('context_path_escape', 'O diretório do agente não é válido.')
            conv['_agent_state_dir'] = str(agent_state)
            previous = [t for t in conv['turns'] if t['ordinal'] < turn['ordinal']]
            last = previous[-1] if previous else None
            native = last.get('native_session_id') if last and last.get('route') == selection and last.get('execution_mode') == 'single' and stored_turn['execution_mode'] == 'single' else None
            conv['native_session_id'] = native
            if selection.get('connection_mode') == 'omniroute':
                checked = await self._validate_route({k: selection[k] for k in ('executor', 'connection_mode', 'target_kind', 'target_ref')}, refresh=True)
                if checked.get('fingerprint') != selection.get('fingerprint'):
                    raise ContractViolation('route_changed', 'O combo mudou após o envio. Revise a configuração e envie novamente; o histórico foi preservado.')
                conv['_gateway_base_url'] = self.routes.gateway.base_url
                conv['_gateway_token'] = self.routes.gateway._resolve_api_key()
            route_reason = None
            if conv['auto_route'] and stored_turn['execution_mode'] == 'single' and self.routes:
                quota = await self.routes.gateway.get_quota_status() if selection['connection_mode'] == 'omniroute' else {}
                selected, route_reason = await self.routes.choose(
                    {key: selection[key] for key in ('executor', 'connection_mode', 'target_kind', 'target_ref')},
                    category='ui' if conv['_image_input'] else 'code', image=conv['_image_input'], quota=quota,
                    context=(len(turn['content']) + sum(len(t['content']) + len(t['response']) for t in previous) + 2) // 3,
                )
                conv['route'] = await self._validate_route(selected)
                conv['native_session_id'] = last.get('native_session_id') if last and last.get('effective_route') == conv['route'] and last.get('execution_mode') == 'single' else None
            ws, cwd = await self._workspace(conv)
            async with self.store._connect() as db:
                rows = await (await db.execute("""SELECT e.turn_id,e.seq,e.type,e.payload_json FROM conversation_events e
                    JOIN conversation_turns t ON t.id=e.turn_id
                    WHERE e.conversation_id=? AND t.ordinal<? AND e.type LIKE 'tool.%' ORDER BY e.seq""", (cid, turn['ordinal']))).fetchall()
                conv['_context_tools'] = {}
                for row in rows:
                    conv['_context_tools'].setdefault(row['turn_id'], []).append({'seq': row['seq'], 'type': row['type'], 'payload': json.loads(row['payload_json'])})
            prompt = await asyncio.to_thread(self._prepare_prompt, conv, conv["turns"], turn, cwd)
            async with self.store._connect() as db:
                await db.execute("UPDATE conversation_turns SET context_strategy=?,context_checkpoint_json=? WHERE id=?", ("native" if conv.get("native_session_id") else "referenced_history", json.dumps(conv['_context_checkpoint']), tid))
            emit = lambda kind, payload: self._emit(turn, kind, payload)
            if route_reason:
                await emit('execution.route', {'route': conv['route'], 'reason': route_reason})
            if stored_turn['execution_mode'] == 'swarm':
                if self.coordinator is None:
                    from hydra_orch.core.conversation_coordinator import ConversationCoordinator
                    self.coordinator = ConversationCoordinator(self.runs, self.runner, self.routes,
                                                              worker_timeout_seconds=self.worker_timeout_seconds)
                await self.coordinator.run(turn, conv, prompt, cwd, emit)
            else:
                await self.runner.run(turn, conv, prompt, cwd, emit)
            if ws is None:
                from hydra_orch.core.folder_workspace import diff as folder_diff
                diff = await asyncio.to_thread(folder_diff, cwd.parent / "base", cwd)
                return
            # A textual answer is a successful result; a patch is optional.
            scope = await asyncio.to_thread(ws.validate_worktree_scope, cwd, base_sha=conv["base_sha"], allowed_paths=("*",))
            if not scope.valid:
                raise ContractViolation("scope_violation", "O agente alterou um caminho que exige revisão. A pasta foi preservada.")
            result = await asyncio.to_thread(ws._run_git, ["diff", "--no-ext-diff", conv["base_sha"]], cwd=cwd)
            diff = redact_text(result.stdout)[:200000]
            untracked = await asyncio.to_thread(ws._run_git, ["ls-files", "--others", "--exclude-standard"], cwd=cwd)
            for name in untracked.stdout.splitlines():
                if name.startswith((".orchestrator/chat_attachment/", ".orchestrator/chat_context/")):
                    continue
                path = (cwd / name).resolve()
                if path.is_relative_to(cwd.resolve()) and path.is_file() and path.stat().st_size <= 100000:
                    added = await asyncio.to_thread(ws._run_git, ["diff", "--no-index", "--no-ext-diff", "--", os.devnull, name], cwd=cwd)
                    diff = (diff + redact_text(added.stdout))[:200000]
        except asyncio.CancelledError:
            state, error = "cancelled", "Execução interrompida pelo servidor."
            raise
        except Exception as exc:
            state, error = "failed", redact_text(str(exc))[:4000]
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            with suppress(Exception):
                await self.runner.cancel(tid)
                async with self.store._connect() as db:
                    async with self.store._transaction(db):
                        row = await (await db.execute("SELECT state,lease_owner FROM conversation_turns WHERE id=?", (tid,))).fetchone()
                        if row["lease_owner"] == self.owner:
                            if row["state"] == "stopping":
                                state, error = "cancelled", None
                            await db.execute("UPDATE conversation_turns SET state=?,error=?,diff=?,process_pid=NULL,finished_at=datetime('now'),lease_until=NULL WHERE id=?", (state, error, diff, tid))
                            await self._event(db, cid, tid, f"turn.{state}", {"error": error, "has_changes": bool(diff)})
