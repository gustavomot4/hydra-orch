"""Durable conversation turns, transactional outbox, leases, replay and isolated workspaces."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import time
import uuid

from hydra_orch.bridge.conversation_runner import ConversationRunner
from hydra_orch.bridge.worker_runner import is_process_alive
from hydra_orch.core.checkpointer import IdempotencyConflictError, OptimisticLockError
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import ContractViolation


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


class ConversationService:
    def __init__(self, run_service, *, runner=None, attachments=None):
        self.runs = run_service
        self.store = run_service.store
        self.runner = runner or ConversationRunner()
        self.attachments = attachments
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
                     draft_session_id=None, attachment_ids=()):
        await self.store.initialize()
        project = await self.runs.get_project(project_id)
        if not project:
            raise ContractViolation("project_not_found", "Selecione um projeto cadastrado.")
        if executor not in {"codex", "claude"}:
            raise ContractViolation("agent_unavailable", "Escolha um agente compatível com conversa.")
        if access_mode not in {"read-only", "workspace-write"}:
            raise ContractViolation("invalid_access_mode", "Escolha o acesso ao projeto.")
        self._validate(content, idempotency_key)
        request_hash = self.store.compute_request_hash({"project": project_id, "executor": executor,
            "content": content, "access": access_mode, "draft": draft_session_id, "attachments": list(attachment_ids)})
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                previous = await (await db.execute("SELECT * FROM conversation_commands WHERE idempotency_key=?", (idempotency_key,))).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise IdempotencyConflictError("Este envio já foi usado para outro pedido.")
                    return {"conversation_id": previous["conversation_id"], "created": False}
                cid = new_id("conversation")
                refs = await asyncio.to_thread(self._promote, cid, project_id, draft_session_id, attachment_ids)
                await db.execute("INSERT INTO conversations(id,project_id,title,executor,access_mode) VALUES(?,?,?,?,?)",
                                 (cid, project_id, content.strip()[:90], executor, access_mode))
                await self._insert_turn(db, cid, content, idempotency_key, request_hash, refs)
                await db.execute("INSERT INTO conversation_commands VALUES(?,?,?)", (idempotency_key, request_hash, cid))
        return {"conversation_id": cid, "created": True}

    @staticmethod
    def _validate(content, key):
        if not isinstance(content, str) or not content.strip() or len(content) > 100000 or "\x00" in content:
            raise ContractViolation("message_invalid", "Escreva uma mensagem de até 100 mil caracteres.")
        if not isinstance(key, str) or not 16 <= len(key) <= 100:
            raise ContractViolation("message_invalid", "O envio precisa de uma chave de identificação válida.")

    async def _insert_turn(self, db, cid, content, key, request_hash, attachments):
        ordinal = (await (await db.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM conversation_turns WHERE conversation_id=?", (cid,))).fetchone())[0]
        tid = new_id("turn")
        await db.execute("""INSERT INTO conversation_turns(id,conversation_id,ordinal,idempotency_key,request_hash,content,attachment_json)
                           VALUES(?,?,?,?,?,?,?)""", (tid, cid, ordinal, key, request_hash, redact_text(content), json.dumps(attachments)))
        seq = await self._event(db, cid, tid, "turn.queued", {"content": content, "ordinal": ordinal})
        return {"conversation_id": cid, "turn_id": tid, "seq": seq}

    async def send(self, cid, *, content, idempotency_key, expected_last_seq, draft_session_id=None, attachment_ids=()):
        self._validate(content, idempotency_key)
        await self.store.initialize()
        request_hash = self.store.compute_request_hash({"content": content, "seq": expected_last_seq,
            "draft": draft_session_id, "attachments": list(attachment_ids)})
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                conv = await self._conversation(db, cid)
                prior = await (await db.execute("SELECT * FROM conversation_turns WHERE conversation_id=? AND idempotency_key=?", (cid, idempotency_key))).fetchone()
                if prior:
                    if prior["request_hash"] != request_hash:
                        raise IdempotencyConflictError("Este envio já foi usado para outra mensagem.")
                    return {"conversation_id": cid, "turn_id": prior["id"], "seq": conv["last_seq"]}
                latest_message = (await (await db.execute("SELECT COALESCE(MAX(seq),0) FROM conversation_events WHERE conversation_id=? AND type='turn.queued'", (cid,))).fetchone())[0]
                # Streaming output must not make the composer stale. Only a newer user send conflicts.
                if expected_last_seq > conv["last_seq"] or latest_message > expected_last_seq:
                    raise OptimisticLockError("A conversa mudou. Atualize e envie sua mensagem novamente.")
                pending = (await (await db.execute("SELECT COUNT(*) FROM conversation_turns WHERE conversation_id=? AND state='queued'", (cid,))).fetchone())[0]
                if pending >= 10:
                    raise ContractViolation("conversation_queue_full", "Aguarde as mensagens pendentes antes de enviar outra.")
                refs = await asyncio.to_thread(self._promote, cid, conv["project_id"], draft_session_id, attachment_ids)
                return await self._insert_turn(db, cid, content, idempotency_key, request_hash, refs)

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
                turns = await (await db.execute("SELECT * FROM conversation_turns WHERE conversation_id=? ORDER BY ordinal", (cid,))).fetchall()
                events = await (await db.execute("SELECT * FROM conversation_events WHERE conversation_id=? AND type LIKE 'tool.%' ORDER BY seq DESC LIMIT 50", (cid,))).fetchall()
                conv["turns"] = [self._public_turn(dict(t)) for t in turns]
                conv["tools"] = [{**dict(e), "payload": json.loads(e["payload_json"])} for e in reversed(events)]
                return conv

    @staticmethod
    def _public_turn(turn):
        for key in ("lease_owner", "lease_until", "process_pid", "request_hash", "idempotency_key"):
            turn.pop(key, None)
        turn["attachments"] = json.loads(turn.pop("attachment_json"))
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
                    await db.execute("UPDATE conversations SET native_session_id=? WHERE id=?", (payload["session_id"], cid))
                elif kind == "process.started":
                    await db.execute("UPDATE conversation_turns SET process_pid=? WHERE id=?", (payload["pid"], tid))
                await self._event(db, cid, tid, kind, payload)
        if kind == "process.started" and row["state"] == "stopping":
            raise ContractViolation("turn_cancelled", "A execução foi interrompida antes do envio ao agente.")

    async def _heartbeat(self, tid):
        while True:
            async with self.store._connect() as db:
                row = await (await db.execute("SELECT state,lease_owner FROM conversation_turns WHERE id=?", (tid,))).fetchone()
                if row["lease_owner"] != self.owner:
                    await self.runner.cancel(tid)
                    return
                await db.execute("UPDATE conversation_turns SET lease_until=? WHERE id=? AND lease_owner=?", (time.time()+60, tid, self.owner))
                if row["state"] == "stopping":
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
                if target.is_symlink():
                    raise ContractViolation("attachment_path_escape", "O destino do anexo não é seguro.")
                target.write_bytes(data)
                attachment_lines.append(f"{ref['filename']}: {target}")
        preamble = "Responda em português. Trabalhe somente nesta pasta isolada. Não faça commit, push ou integração. "
        preamble += "O modo desta conversa é " + conv["access_mode"] + ".\n"
        if not conv.get("native_session_id"):
            transcript = []
            for item in turns:
                if item["ordinal"] < turn["ordinal"] and (item["state"] == "completed" or item["response"]):
                    transcript.append(f"Usuário: {item['content']}\nAssistente: {item['response']}")
            history = "\n\n".join(transcript)
            if len(history) > 120000:
                raise ContractViolation("context_limit", "Esta conversa atingiu o limite de contexto. Abra um novo chat para continuar.")
            preamble += "Histórico da conversa:\n" + history + "\n\n"
        return preamble + "Pedido atual:\n" + turn["content"] + ("\nAnexos disponíveis para leitura:\n" + "\n".join(attachment_lines) if refs else "")

    async def _execute(self, turn):
        cid, tid = turn["conversation_id"], turn["id"]
        heartbeat = asyncio.create_task(self._heartbeat(tid))
        state, error, diff = "completed", None, ""
        try:
            conv = await self.snapshot(cid)
            ws, cwd = await self._workspace(conv)
            prompt = await asyncio.to_thread(self._prepare_prompt, conv, conv["turns"], turn, cwd)
            async with self.store._connect() as db:
                await db.execute("UPDATE conversation_turns SET context_strategy=? WHERE id=?", ("native" if conv.get("native_session_id") else "transcript", tid))
            await self.runner.run(turn, conv, prompt, cwd, lambda kind, payload: self._emit(turn, kind, payload))
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
                if name.startswith(".orchestrator/chat_attachment/"):
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
