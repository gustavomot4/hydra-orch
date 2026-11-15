import pytest
from hydra_orch.bridge.agent_observation import observations
from tests.test_conversation import service, create


def test_codex_spawn_call_completion_is_not_child_completion_and_wait_updates_same_child():
    spawn = {'type': 'item.completed', 'item': {'type': 'collab_tool_call', 'tool': 'spawn_agent', 'sender_thread_id': 'root', 'receiver_thread_ids': ['child'], 'prompt': 'Revisar API', 'status': 'completed', 'agents_states': {'child': {'status': 'running'}}}}
    [agent] = observations('codex', spawn, {})
    assert agent['id'] == 'child' and agent['parent_id'] == 'root'
    assert agent['state'] == 'running'
    wait = {'type': 'item.updated', 'item': {'type': 'collab_tool_call', 'tool': 'wait', 'receiver_thread_ids': ['child'], 'agents_states': {'child': {'status': 'completed', 'message': 'Revisão pronta'}}}}
    [updated] = observations('codex', wait, {'child': agent})
    assert updated['title'] == 'Revisar API'
    assert updated['state'] == 'completed' and updated['summary'] == 'Revisão pronta'
    assert observations('codex', {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Chamei outro agente'}}, {}) == []


def test_claude_only_agent_tasks_become_cards_not_shell_or_ambient_tasks():
    event = {'type': 'system', 'subtype': 'task_started', 'task_id': 'child', 'task_type': 'local_agent', 'description': 'Revisar testes', 'parent_task_id': 'parent'}
    [agent] = observations('claude', event, {})
    assert agent['parent_id'] == 'parent' and agent['state'] == 'running'
    assert observations('claude', {**event, 'task_type': 'local_bash'}, {}) == []
    assert observations('claude', {**event, 'ambient': True}, {}) == []
    [ended] = observations('claude', {'type': 'system', 'subtype': 'task_notification', 'task_id': 'child', 'status': 'completed', 'summary': 'Testes revisados'}, {'child': agent})
    assert ended['state'] == 'completed'
    assert ended['summary'] == 'Testes revisados'


@pytest.mark.asyncio
async def test_delegation_reaches_durable_snapshot_and_event_replay(service):
    cid, _ = await create(service)
    turn = await service.claim()
    agent = {'id': 'child', 'parent_id': 'root', 'title': 'Revisar testes', 'executor': 'codex', 'model': 'Não informado pela CLI', 'state': 'running', 'summary': 'Criação observada', 'source': 'cli'}
    await service._emit(turn, 'agent.observed', agent)
    snapshot = await service.snapshot(cid)
    assert snapshot['agents'] == [{**agent, 'turn_id': turn['id']}]
    await service._emit(turn, 'agent.observed', {**agent, 'state': 'completed', 'summary': 'Feito'})
    assert len((await service.snapshot(cid))['agents']) == 1
    assert (await service.snapshot(cid))['agents'][0]['state'] == 'completed'
    replay = await service.events(cid)
    assert len([event for event in replay if event['type'] == 'agent.observed']) == 2
