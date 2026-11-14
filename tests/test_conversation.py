"""Conversation acceptance: durable sends, recovery, context, cancellation and CLI protocols."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from hydra_orch.core.checkpointer import ExecutionStore, IdempotencyConflictError, OptimisticLockError, MigrationError
from hydra_orch.core.conversation_service import ConversationService
from hydra_orch.core.run_service import RunService
from hydra_orch.core.attachments import AttachmentService
from hydra_orch.bridge.conversation_runner import ConversationRunner
from hydra_orch.model import ContractViolation


class ControlledRunner:
    def __init__(self):
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.cancelled = asyncio.Event()

    async def capabilities(self):
        return [{"id": "codex", "name": "Codex", "available": True}]

    async def run(self, turn, conv, prompt, cwd, emit):
        self.calls.append((turn, conv, prompt, cwd))
        await emit("session.started", {"session_id": "native-context-test"})
        await emit("text.delta", {"text": "Primeiro trecho. "})
        self.started.set()
        await self.release.wait()
        if self.cancelled.is_set():
            raise ContractViolation("cancelled", "Interrompido")
        await emit("text.delta", {"text": "Resposta concluída."})

    async def cancel(self, tid):
        if not self.release.is_set():
            self.cancelled.set()
            self.release.set()


@pytest.fixture
def service(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init", "-b", "main"), ("config", "user.email", "test@hydra.local"), ("config", "user.name", "Hydra Test")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Projeto teste\n1. Instale.\n2. Inicie.\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".orchestrator/\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
    runs = RunService(repo, store=ExecutionStore(tmp_path / "state.sqlite"), runtime_dir=tmp_path / "runtime")
    runner = ControlledRunner()
    return ConversationService(runs, runner=runner, attachments=AttachmentService(tmp_path / "attachment"))


async def create(service, **kwargs):
    project = await service.runs.create_project(service.runs.repo_root, "Projeto teste")
    result = await service.create(project_id=project["id"], executor="codex", content="Leia o README", idempotency_key="first-message-key-0001", **kwargs)
    return result["conversation_id"], project


async def wait_state(service, cid, state, ordinal=1):
    for _ in range(100):
        snapshot = await service.snapshot(cid)
        if len(snapshot["turns"]) >= ordinal and snapshot["turns"][ordinal-1]["state"] == state:
            return snapshot
        await asyncio.sleep(.05)
    raise AssertionError(await service.snapshot(cid))


@pytest.mark.asyncio
async def test_chat_executes_two_turns_streams_reopens_and_preserves_workspace(service):
    cid, _ = await create(service)
    service.runner.release.clear()
    await service.start()
    try:
        await asyncio.wait_for(service.runner.started.wait(), 5)
        partial = await service.snapshot(cid)
        assert partial["turns"][0]["response"] == "Primeiro trecho. "
        assert partial["turns"][0]["state"] == "running"
        cursor = partial["last_seq"]
        service.runner.release.set()
        completed = await wait_state(service, cid, "completed")
        assert completed["turns"][0]["diff"] == ""  # read-only answers succeed
        assert await service.events(cid, cursor)
        assert all(e["seq"] > cursor for e in await service.events(cid, cursor))
        await service.send(cid, content="Detalhe o segundo passo", idempotency_key="second-message-key-0001", expected_last_seq=completed["last_seq"])
        await wait_state(service, cid, "completed", 2)
        assert len(service.runner.calls) == 2
        assert service.runner.calls[0][3] == service.runner.calls[1][3]
        assert service.runner.calls[0][3] != service.runs.repo_root
        assert service.runner.calls[1][1]["native_session_id"] == "native-context-test"
        reopened = ConversationService(service.runs)
        assert len((await reopened.snapshot(cid))["turns"]) == 2
        assert subprocess.run(["git", "status", "--short"], cwd=service.runs.repo_root, capture_output=True, text=True).stdout == ""
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_create_and_send_idempotence_and_single_consumer_claim(service):
    cid, project = await create(service)
    again = await service.create(project_id=project["id"], executor="codex", content="Leia o README", idempotency_key="first-message-key-0001")
    assert again == {"conversation_id": cid, "created": False}
    with pytest.raises(IdempotencyConflictError):
        await service.create(project_id=project["id"], executor="codex", content="Outro pedido", idempotency_key="first-message-key-0001")
    snap = await service.snapshot(cid)
    payload = dict(content="Continuação", idempotency_key="second-message-key-0002", expected_last_seq=snap["last_seq"])
    results = await asyncio.gather(service.send(cid, **payload), service.send(cid, **payload))
    assert results[0]["turn_id"] == results[1]["turn_id"]
    with pytest.raises(OptimisticLockError):
        await service.send(cid, content="Stale", idempotency_key="third-message-key-0003", expected_last_seq=0)
    other = ConversationService(service.runs)
    claims = await asyncio.gather(service.claim(), other.claim())
    assert sum(c is not None for c in claims) == 1
    assert len((await service.snapshot(cid))["turns"]) == 2


@pytest.mark.asyncio
async def test_cancel_active_preserves_partial_and_cancels_pending(service):
    cid, _ = await create(service)
    service.runner.release.clear()
    await service.start()
    try:
        await asyncio.wait_for(service.runner.started.wait(), 5)
        snap = await service.snapshot(cid)
        pending = await service.send(cid, content="Depois", idempotency_key="queued-message-key-0002", expected_last_seq=snap["last_seq"])
        await service.cancel(cid, pending["turn_id"])
        await service.cancel(cid, snap["turns"][0]["id"])
        final = await wait_state(service, cid, "cancelled")
        assert final["turns"][0]["response"] == "Primeiro trecho. "
        assert final["turns"][1]["state"] == "cancelled"
        assert len(service.runner.calls) == 1
        service.runner.cancelled.clear()
        await service.send(cid, content="Continue depois da interrupção", idempotency_key="after-cancel-message-0003", expected_last_seq=final["last_seq"])
        await wait_state(service, cid, "completed", 3)
        assert len(service.runner.calls) == 2
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_expired_lease_never_replays_uncertain_process(service):
    cid, _ = await create(service)
    turn = await service.claim()
    async with service.store._connect() as db:
        await db.execute("UPDATE conversation_turns SET lease_until=?,process_pid=? WHERE id=?", (time.time()-1, os.getpid(), turn["id"]))
    await service.reconcile()
    assert (await service.snapshot(cid))["turns"][0]["state"] == "stopping"
    assert await service.claim() is None
    async with service.store._connect() as db:
        await db.execute("UPDATE conversation_turns SET process_pid=NULL WHERE id=?", (turn["id"],))
    await service.reconcile()
    assert (await service.snapshot(cid))["turns"][0]["state"] == "failed"
    assert service.runner.calls == []


@pytest.mark.asyncio
async def test_rollback_refuses_to_discard_conversation_history(service):
    cid, _ = await create(service)
    with pytest.raises(MigrationError):
        await service.store.rollback_migrations("0003")
    assert (await service.snapshot(cid))["turns"][0]["content"] == "Leia o README"


@pytest.mark.asyncio
async def test_ordinary_folder_registration_persists_and_chat_edits_are_isolated(service, tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "README.md").write_text("Original\n", encoding="utf-8")
    (folder / ".env").write_text("LOCAL_ONLY=value", encoding="utf-8")
    (folder / "node_modules").mkdir()
    (folder / "node_modules" / "cache").write_text("cache")
    with pytest.raises(ContractViolation):
        await service.runs.create_project(folder, "Sem Git")
    project = await service.runs.create_project(folder, "Sem Git", allow_plain_folder=True)
    reopened = RunService(service.runs.repo_root, store=service.store)
    assert (await reopened.get_project(project["id"]))["workspace_kind"] == "folder"
    assert (await reopened.get_project(project["id"]))["base_sha"] is None
    original = service.runner.run
    async def editing(turn, conv, prompt, cwd, emit):
        assert conv["workspace_kind"] == "folder"
        assert not (cwd / ".git").exists()
        assert not (cwd / ".env").exists()
        assert not (cwd / "node_modules").exists()
        (cwd / "README.md").write_text("Alterado\n", encoding="utf-8")
        (cwd / "new.txt").write_text("Novo\n", encoding="utf-8")
        await original(turn, conv, prompt, cwd, emit)
    service.runner.run = editing
    result = await service.create(project_id=project["id"], executor="codex", content="Edite o README", access_mode="workspace-write", idempotency_key="plain-folder-message-0001")
    await service.start()
    try:
        snap = await wait_state(service, result["conversation_id"], "completed")
        assert "Alterado" in snap["turns"][0]["diff"]
        assert "new.txt" in snap["turns"][0]["diff"]
        assert (folder / "README.md").read_text() == "Original\n"
        assert not (folder / ".git").exists()
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_history_search_finds_unicode_title_beyond_first_page(service):
    cid, project = await create(service)
    for index in range(12):
        await service.create(project_id=project["id"], executor="codex", content=f"Conversa {index}", idempotency_key=f"history-search-message-{index:04}")
    await service.create(project_id=project["id"], executor="codex", content="ANÁLISE DA ENTREGA", idempotency_key="history-search-unicode-001")
    result = await service.list(limit=10, q="análise")
    assert result["total"] == 1
    assert result["items"][0]["title"] == "ANÁLISE DA ENTREGA"


@pytest.mark.asyncio
async def test_attachment_promotion_context_and_edit_diff(service):
    project = await service.runs.create_project(service.runs.repo_root, "Teste")
    ref = service.attachments.save_attachment(project["id"], f"draft-{project['id']}", "brief.txt", b"Requisito do teste")
    result = await service.create(project_id=project["id"], executor="codex", content="Leia o anexo", access_mode="workspace-write", idempotency_key="attached-message-key-0001", draft_session_id=f"draft-{project['id']}", attachment_ids=[ref.attachment_id])
    cid = result["conversation_id"]
    original = service.runner.run
    async def editing(turn, conv, prompt, cwd, emit):
        assert "brief.txt" in prompt
        assert list((cwd / ".orchestrator" / "chat_attachment" / turn["id"]).iterdir())[0].read_bytes() == b"Requisito do teste"
        (cwd / "README.md").write_text("# Revisado\n", encoding="utf-8")
        (cwd / "new.txt").write_text("Novo arquivo\n", encoding="utf-8")
        await original(turn, conv, prompt, cwd, emit)
    service.runner.run = editing
    await service.start()
    try:
        snap = await wait_state(service, cid, "completed")
        assert "Revisado" in snap["turns"][0]["diff"]
        assert "Novo arquivo" in snap["turns"][0]["diff"]
        assert "Revisado" not in (service.runs.repo_root / "README.md").read_text()
        assert snap["turns"][0]["attachments"][0]["session_id"] == cid
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("driver", ["codex", "claude"])
async def test_real_subprocess_protocol_parsing_and_native_resume(tmp_path, monkeypatch, driver):
    from hydra_orch.bridge import conversation_runner as module
    script = tmp_path / "protocol.py"
    if driver == "codex":
        events = [{"type": "thread.started", "thread_id": "native-123"}, {"type": "item.completed", "item": {"type": "agent_message", "text": "Resposta"}}]
    else:
        events = [{"type": "system", "subtype": "init", "session_id": "native-123"}, {"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "Resposta"}}}, {"type": "assistant", "message": {"content": [{"type": "text", "text": "Resposta"}]}}, {"type": "result", "is_error": False}]
    script.write_text("import sys,json\nsys.stdin.read()\n" + "\n".join(f"print({json.dumps(json.dumps(e))}, flush=True)" for e in events), encoding="utf-8")
    real_spawn = asyncio.create_subprocess_exec
    argv = []
    async def spawn(*args, **kwargs):
        argv.extend(args)
        return await real_spawn(sys.executable, str(script), **kwargs)
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(module.shutil, "which", lambda _: sys.executable)
    seen = []
    async def emit(kind, payload):
        seen.append((kind, payload))
    await ConversationRunner().run({"id": "turn-test"}, {"executor": driver, "native_session_id": "native-previous", "access_mode": "read-only"}, "Continue", tmp_path, emit)
    assert "native-previous" in argv
    assert any(kind == "session.started" and payload["session_id"] == "native-123" for kind, payload in seen)
    assert "".join(p["text"] for k, p in seen if k == "text.delta").strip() == "Resposta"


@pytest.mark.asyncio
async def test_migration_preserves_legacy_session_and_message(service, tmp_path):
    from hydra_orch.core.session_service import SessionService
    from hydra_orch.model import RunSpec, TaskSpec, CheckSpec
    old_migrations = tmp_path / "old_migration"
    old_migrations.mkdir()
    shutil.copytree(Path("migration/rollback"), old_migrations / "rollback")
    for path in Path("migration").glob("000[123]_*.sql"):
        shutil.copy(path, old_migrations)
    store = ExecutionStore(tmp_path / "old.sqlite", migrations_dir=old_migrations)
    runs = RunService(service.runs.repo_root, store=store)
    project = await runs.create_project(service.runs.repo_root, "Antigo")
    sha = runs.git_workspace.resolve_commit_sha("HEAD")
    spec = RunSpec(run_id="legacy-run", project_id=project["id"], repo_root=str(runs.repo_root), base_branch="main", base_sha=sha, objective="Histórico", tasks=(TaskSpec(task_id="legacy-task", run_id="legacy-run", objective="Histórico", allowed_paths=("*",), acceptance_criteria=(CheckSpec(check_id="status", command=("git", "status")),), assigned_executor="codex"),), idempotency_key="legacy-create-key-0001")
    await runs.submit_run(spec)
    sessions = SessionService(store)
    session = await sessions.create_session("legacy-run")
    await sessions.transition_session("legacy-run", session["id"], "running", expected_state="created")
    thread = await sessions.create_thread("legacy-run", session["id"])
    await sessions.transition_thread("legacy-run", session["id"], thread["id"], "running", expected_state="created")
    await sessions.append_message("legacy-run", session["id"], thread["id"], "Mensagem antiga", idempotency_key="legacy-message-key-0001", expected_last_seq=0)
    migrated = ExecutionStore(tmp_path / "old.sqlite")
    runs.store = migrated
    chat = await ConversationService(runs).snapshot(f"conversation-{session['id']}")
    assert chat["legacy_run_id"] == "legacy-run"
    assert chat["turns"][0]["content"] == "Mensagem antiga"
    assert chat["turns"][0]["state"] == "completed"


@pytest.mark.asyncio
async def test_http_send_is_authenticated_quick_idempotent_and_conflicts_preserve_draft(service, monkeypatch):
    import httpx
    from hydra_orch import server
    from hydra_orch.core.auth import TokenVerifier
    token = "conversation-test-bearer-0123456789012345"
    monkeypatch.setitem(server.app.state._state, "token_verifier", TokenVerifier.from_token(token))
    monkeypatch.setattr(server, "get_conversation_service", lambda: service)
    project = await service.runs.create_project(service.runs.repo_root, "HTTP teste")
    service.runner.release.clear()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {"project_id": project["id"], "executor": "codex", "content": "Leia o README", "idempotency_key": "http-message-create-0001"}
        assert (await client.post("/v1/control-plane/conversations", json=payload)).status_code == 401
        client.headers["Authorization"] = f"Bearer {token}"
        try:
            response = await client.post("/v1/control-plane/conversations", json=payload)
            assert response.status_code == 202
            cid = response.json()["conversation_id"]
            replay = await client.post("/v1/control-plane/conversations", json=payload)
            assert replay.json()["conversation_id"] == cid
            await asyncio.wait_for(service.runner.started.wait(), 5)
            snap = (await client.get(f"/v1/control-plane/conversations/{cid}")).json()
            assert snap["turns"][0]["response"]
            message = {"content": "Detalhe o segundo passo", "expected_last_seq": snap["last_seq"], "idempotency_key": "http-message-followup-0002"}
            followup = await client.post(f"/v1/control-plane/conversations/{cid}/messages", json=message)
            assert followup.status_code == 202
            assert (await client.post(f"/v1/control-plane/conversations/{cid}/messages", json=message)).json()["turn_id"] == followup.json()["turn_id"]
            message.update(content="Outra janela", idempotency_key="http-message-stale-0003")
            assert (await client.post(f"/v1/control-plane/conversations/{cid}/messages", json=message)).status_code == 409
            assert (await client.get("/v1/control-plane/conversations/missing")).status_code == 404
        finally:
            await service.close()
