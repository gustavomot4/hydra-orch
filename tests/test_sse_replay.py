"""T14 durable hierarchy, scoped SSE replay and atomic reference-client dedup."""

import asyncio

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio

from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore, IdempotencyConflictError, OptimisticLockError, StorageIntegrityError
from hydra_orch.core.run_service import RunService
from hydra_orch.core.session_service import EventCursor, SessionService
from hydra_orch.model import ContractViolation, RunSpec
from hydra_orch import server
from test_checkpointer import _make_run_spec
from test_server import _init_temp_git_repo

TOKEN = "session-test-bearer-token-0123456789"
VERIFIER = TokenVerifier.from_token(TOKEN)


@pytest_asyncio.fixture
async def sessions(tmp_path, monkeypatch):
    repo, sha = _init_temp_git_repo(tmp_path)
    store = ExecutionStore(tmp_path / "sessions.sqlite")
    for run_id in ("run-a", "run-b"):
        spec = _make_run_spec(str(repo), run_id=run_id, idempotency_key=f"idempotency-session-{run_id}")
        spec = RunSpec.model_validate({**spec.model_dump(mode="json"), "base_sha": sha})
        await store.submit_run_idempotent(spec)
    monkeypatch.setattr(server, "_run_service", RunService(repo_root=repo, store=store))
    monkeypatch.setitem(server.app.state._state, "token_verifier", VERIFIER)
    return SessionService(store)


async def running(sessions):
    session = await sessions.create_session("run-a")
    await sessions.transition_session("run-a", session["id"], "running", expected_state="created")
    thread = await sessions.create_thread("run-a", session["id"])
    await sessions.transition_thread("run-a", session["id"], thread["id"], "running", expected_state="created")
    return session["id"], thread["id"]


@pytest.mark.asyncio
async def test_tree_restart_replay_and_redacted_idempotent_message(sessions):
    session_id, thread_id = await running(sessions)
    child = await sessions.create_thread("run-a", session_id, parent_thread_id=thread_id)
    response = await sessions.append_message("run-a", session_id, thread_id, "password=super-secret",
        idempotency_key="session-message-key-0001", expected_last_seq=0)
    restarted = SessionService(ExecutionStore(sessions.store.db_path))
    repeated = await restarted.append_message("run-a", session_id, thread_id, "password=super-secret",
        idempotency_key="session-message-key-0001", expected_last_seq=0)
    assert response == repeated
    assert len(await restarted.list_sessions("run-a")) == 1
    assert len(await restarted.list_threads("run-a", session_id)) == 2
    thread_events = await restarted.replay("run-a", thread_id=thread_id)
    assert all(event.thread_id == thread_id and event.session_id == session_id for event in thread_events)
    assert sum(event.event_type == "thread.message" for event in thread_events) == 1
    assert "super-secret" not in "".join(event.model_dump_json() for event in thread_events)
    assert await restarted.replay("run-a", after_seq=response["seq"], thread_id=thread_id) == []
    assert (await restarted.list_threads("run-a", session_id))[1]["parent_thread_id"] == thread_id


@pytest.mark.asyncio
async def test_concurrent_message_dedup_and_conflicting_payload(sessions):
    session_id, thread_id = await running(sessions)
    async def submit():
        return await sessions.append_message("run-a", session_id, thread_id, "hello",
            idempotency_key="concurrent-message-key-0001", expected_last_seq=0)
    results = await asyncio.gather(*(submit() for _ in range(5)))
    assert len({r["seq"] for r in results}) == 1
    with pytest.raises(IdempotencyConflictError):
        await sessions.append_message("run-a", session_id, thread_id, "different",
            idempotency_key="concurrent-message-key-0001", expected_last_seq=0)
    with pytest.raises(OptimisticLockError):
        await sessions.append_message("run-a", session_id, thread_id, "next",
            idempotency_key="concurrent-message-key-0002", expected_last_seq=0)


@pytest.mark.asyncio
async def test_parent_and_cross_run_scope_fences(sessions):
    first = await sessions.create_session("run-a")
    second = await sessions.create_session("run-a")
    thread = await sessions.create_thread("run-a", first["id"])
    with pytest.raises(ContractViolation, match="another run"):
        await sessions.get_session("run-b", first["id"])
    with pytest.raises(ContractViolation, match="another session"):
        await sessions.create_thread("run-a", second["id"], parent_thread_id=thread["id"])
    with pytest.raises(ContractViolation, match="another run"):
        await sessions.replay("run-b", thread_id=thread["id"])
    with pytest.raises(ContractViolation, match="does not exist"):
        await sessions.create_thread("run-a", first["id"], parent_thread_id="missing")
    with pytest.raises(ContractViolation):
        await sessions.create_session("missing")


@pytest.mark.asyncio
async def test_transitions_complete_and_cancel_descendants(sessions):
    session_id, thread_id = await running(sessions)
    child = await sessions.create_thread("run-a", session_id, parent_thread_id=thread_id)
    with pytest.raises(ContractViolation, match="active threads"):
        await sessions.transition_session("run-a", session_id, "completed", expected_state="running")
    with pytest.raises(ContractViolation, match="active descendants"):
        await sessions.transition_thread("run-a", session_id, thread_id, "completed", expected_state="running")
    await sessions.transition_thread("run-a", session_id, thread_id, "cancelled", expected_state="running")
    assert {thread["state"] for thread in await sessions.list_threads("run-a", session_id)} == {"cancelled"}
    await sessions.transition_session("run-a", session_id, "completed", expected_state="running")
    assert (await sessions.get_session("run-a", session_id))["closed_at"]
    with pytest.raises(ContractViolation, match="closed"):
        await sessions.create_thread("run-a", session_id)
    with pytest.raises(ContractViolation, match="Illegal"):
        await sessions.transition_session("run-a", session_id, "running", expected_state="completed")


@pytest.mark.asyncio
async def test_session_failure_cascade_and_stale_state(sessions):
    session_id, thread_id = await running(sessions)
    await sessions.transition_session("run-a", session_id, "waiting", expected_state="running")
    with pytest.raises(OptimisticLockError):
        await sessions.transition_session("run-a", session_id, "running", expected_state="created")
    await sessions.transition_session("run-a", session_id, "failed", expected_state="waiting")
    assert (await sessions.list_threads("run-a", session_id))[0]["state"] == "failed"
    with pytest.raises(ContractViolation):
        await sessions.transition_thread("run-a", session_id, thread_id, "waiting", expected_state="failed")


@pytest.mark.asyncio
async def test_waiting_session_and_closed_thread_are_not_active(sessions):
    session_id, thread_id = await running(sessions)
    await sessions.transition_thread("run-a", session_id, thread_id, "waiting", expected_state="running")
    await sessions.transition_session("run-a", session_id, "waiting", expected_state="running")
    with pytest.raises(ContractViolation, match="Session must be running"):
        await sessions.transition_thread("run-a", session_id, thread_id, "running", expected_state="waiting")
    with pytest.raises(ContractViolation, match="running session and thread"):
        await sessions.append_message("run-a", session_id, thread_id, "hello",
            idempotency_key="waiting-message-key-0001", expected_last_seq=0)
    await sessions.transition_session("run-a", session_id, "running", expected_state="waiting")
    await sessions.transition_thread("run-a", session_id, thread_id, "cancelled", expected_state="waiting")
    with pytest.raises(ContractViolation, match="Parent thread is closed"):
        await sessions.create_thread("run-a", session_id, parent_thread_id=thread_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("parent", ["session", "thread"])
async def test_failure_cancels_children_that_never_started(sessions, parent):
    session_id, thread_id = await running(sessions)
    child = await sessions.create_thread("run-a", session_id, parent_thread_id=thread_id)
    if parent == "session":
        await sessions.transition_session("run-a", session_id, "failed", expected_state="running")
    else:
        await sessions.transition_thread("run-a", session_id, thread_id, "failed", expected_state="running")
    threads = {row["id"]: row for row in await sessions.list_threads("run-a", session_id)}
    assert threads[child["id"]]["state"] == "cancelled"


@pytest.mark.asyncio
async def test_event_transaction_rollback_and_store_scope_checks(sessions, monkeypatch):
    original = sessions.store._insert_event_in_tx
    async def fail(*args, **kwargs):
        raise RuntimeError("event unavailable")
    monkeypatch.setattr(sessions.store, "_insert_event_in_tx", fail)
    with pytest.raises(RuntimeError):
        await sessions.create_session("run-a")
    assert await sessions.list_sessions("run-a") == []
    monkeypatch.setattr(sessions.store, "_insert_event_in_tx", original)
    session_id, thread_id = await running(sessions)
    async with sessions.store._connect() as db:
        for kwargs in [{"thread_id": thread_id}, {"session_id": session_id, "thread_id": "missing"}, {"session_id": "missing"}]:
            with pytest.raises(StorageIntegrityError):
                async with sessions.store._transaction(db):
                    await sessions.store._insert_event_in_tx(db, run_id="run-a", event_type="thread.message", **kwargs)
        with pytest.raises(StorageIntegrityError):
            async with sessions.store._transaction(db):
                await sessions.store._insert_event_in_tx(db, run_id="run-b", event_type="session.created", session_id=session_id)


@pytest.mark.asyncio
async def test_cursor_paging_dedup_and_persisted_prefix_expiration(sessions):
    session_id, thread_id = await running(sessions)
    first = await sessions.replay("run-a", limit=2)
    second = await sessions.replay("run-a", after_seq=first[-1].seq)
    assert not {e.seq for e in first} & {e.seq for e in second}
    cursor = EventCursor("run-a")
    assert sum(await asyncio.gather(*(cursor.accept(first[0]) for _ in range(5)))) == 1
    assert await cursor.accept(first[1])
    assert not await cursor.accept(first[0])
    with pytest.raises(ContractViolation):
        await EventCursor("run-b").accept(first[0])
    async with sessions.store._connect() as db:
        await db.execute("DELETE FROM events WHERE run_id='run-a' AND seq<4")
    restarted = SessionService(ExecutionStore(sessions.store.db_path))
    with pytest.raises(ContractViolation) as expired:
        await restarted.replay("run-a", after_seq=1)
    assert expired.value.code == "cursor_expired"
    assert (await restarted.replay("run-a", after_seq=3))[0].seq == 4
    with pytest.raises(ContractViolation):
        await sessions.replay("run-a", after_seq=-1)


@pytest.mark.asyncio
async def test_live_sse_polls_new_sqlite_events(sessions):
    class Request:
        async def is_disconnected(self):
            return False
    response = await server.stream_run_events_endpoint(Request(), "run-a", last_event_id=None,
        after_seq=0, session_id=None, thread_id=None, follow=True, limit=1000)
    stream = response.body_iterator
    try:
        first = await asyncio.wait_for(anext(stream), 2)
        assert "event: run.created" in first
        await sessions.create_session("run-a")
        next_chunk = await asyncio.wait_for(anext(stream), 2)
        assert "event: session.created" in next_chunk
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_sse_exits_on_disconnect_and_public_event_metadata(sessions):
    session_id, thread_id = await running(sessions)
    event = await sessions.store.record_event_atomic("run-a", "thread.message", {"content": "hello"},
        session_id=session_id, thread_id=thread_id)
    assert event.session_id == session_id and event.thread_id == thread_id
    class Disconnected:
        async def is_disconnected(self):
            return True
    response = await server.stream_run_events_endpoint(Disconnected(), "run-a", last_event_id=None,
        after_seq=event.seq, session_id=None, thread_id=None, follow=True, limit=1000)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(response.body_iterator), 2)


def test_http_sessions_scoped_sse_and_message_idempotency(sessions):
    client = TestClient(server.app, headers={"Authorization": "Bearer " + TOKEN})
    base = "/v1/control-plane/runs/run-a/sessions"
    response = client.post(base, json={})
    assert response.status_code == 201
    session = response.json()
    assert client.get(base).json()[0]["id"] == session["id"]
    assert client.get(base + "/" + session["id"]).status_code == 200
    assert client.get("/v1/control-plane/runs/run-b/sessions/" + session["id"]).status_code == 403
    session_url = base + "/" + session["id"]
    assert client.post(session_url + "/state", json={"state": "running", "expected_state": "created"}).status_code == 200
    thread = client.post(session_url + "/threads", json={}).json()
    thread_url = session_url + "/threads/" + thread["id"]
    assert client.post(thread_url + "/state", json={"state": "running", "expected_state": "created"}).status_code == 200
    body = {"content": "hello", "expected_last_seq": 0}
    headers = {"Idempotency-Key": "http-message-key-00001"}
    first = client.post(thread_url + "/messages", json=body, headers=headers)
    assert first.status_code == 200
    assert client.post(thread_url + "/messages", json=body, headers=headers).json() == first.json()
    replay = client.get("/v1/control-plane/runs/run-a/events", params={"thread_id": thread["id"]},
        headers={"Last-Event-ID": str(first.json()["seq"] - 1)})
    assert replay.status_code == 200 and "event: thread.message" in replay.text
    assert "session_id" in replay.text and "thread_id" in replay.text
    assert client.get(session_url + "/threads").status_code == 200
    assert client.post(thread_url + "/state", json={"state": "created", "expected_state": "running"}).status_code == 409
    assert TestClient(server.app).get(base).status_code == 401
    assert client.get(base + "/missing").status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,key",
    [("", "a" * 16), ("text", "short"), ("x" * 100001, "a" * 16)],
    ids=["empty_content", "short_key", "oversized_content"],
)
async def test_invalid_message_does_not_emit(sessions, content, key):
    session_id, thread_id = await running(sessions)
    before = await sessions.replay("run-a")
    with pytest.raises(ContractViolation):
        await sessions.append_message("run-a", session_id, thread_id, content, idempotency_key=key, expected_last_seq=0)
    assert await sessions.replay("run-a") == before
