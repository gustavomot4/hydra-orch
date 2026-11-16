"""Route changes preserve immutable sends, canonical context and workspace state."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from test_conversation import service, create, wait_state
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.bridge.omniroute_transport import function_request
from hydra_orch.core.conversation_context import prepare_context
from hydra_orch.core.conversation_route import ConversationRoutes
from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError, IdempotencyConflictError, MigrationError
from hydra_orch.model import ContractViolation


def target(name):
    return {'executor': 'codex', 'connection_mode': 'direct', 'target_kind': 'model', 'target_ref': name}


@pytest.mark.asyncio
async def test_switch_during_execution_keeps_queued_routes_and_a_b_a_context(service):
    cid, _ = await create(service)
    service.runner.release.clear()
    await service.start()
    try:
        await asyncio.wait_for(service.runner.started.wait(), 5)
        a = await service.snapshot(cid)
        await service.send(cid, content='Decisão: manter a cor verde.', idempotency_key='queued-under-a-000001', expected_last_seq=a['last_seq'])
        changed = await service.change_route(cid, route=target('model-b'), expected_revision=0, idempotency_key='change-to-b-00000001')
        b = await service.snapshot(cid)
        assert b['route_revision'] == 1
        assert b['turns'][1]['route']['target_ref'] == ''
        with pytest.raises(OptimisticLockError):
            await service.send(cid, content='Outra janela', idempotency_key='stale-send-key-00001', expected_last_seq=b['last_seq'])
        await service.send(cid, content='Continue em B', idempotency_key='new-under-b-0000001', expected_last_seq=b['last_seq'], expected_route_revision=1)
        service.runner.release.set()
        await wait_state(service, cid, 'completed', 3)
        assert service.runner.calls[0][1]['route']['target_ref'] == ''
        assert service.runner.calls[1][1]['route']['target_ref'] == ''
        assert service.runner.calls[2][1]['route']['target_ref'] == 'model-b'
        assert service.runner.calls[2][1]['native_session_id'] is None
        assert 'manter a cor verde' in service.runner.calls[2][2]
        same = await service.change_route(cid, route=target('model-b'), expected_revision=0, idempotency_key='change-to-b-00000001')
        assert same == changed
        with pytest.raises(IdempotencyConflictError):
            await service.change_route(cid, route=target('other'), expected_revision=0, idempotency_key='change-to-b-00000001')
        with pytest.raises(OptimisticLockError):
            await service.change_route(cid, route=target(''), expected_revision=0, idempotency_key='stale-route-00000001')
        await service.change_route(cid, route=target(''), expected_revision=1, idempotency_key='return-to-a-00000001')
        b = await service.snapshot(cid)
        await service.send(cid, content='Retome o trabalho feito em B', idempotency_key='return-send-00000001', expected_last_seq=b['last_seq'], expected_route_revision=2)
        done = await wait_state(service, cid, 'completed', 4)
        assert service.runner.calls[3][1]['native_session_id'] is None
        assert 'Continue em B' in service.runner.calls[3][2]
        assert len({c[3] for c in service.runner.calls}) == 1
        assert done['turns'][3]['context_checkpoint']['through_ordinal'] == 3
        assert '.orchestrator/chat_context' not in done['turns'][3]['diff']
        assert done['id'] == cid
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_failed_change_preserves_selection_and_rollback_refuses_history(service):
    cid, _ = await create(service)
    with pytest.raises(ContractViolation):
        await service.change_route(cid, route={**target(''), 'connection_mode': 'omniroute'}, expected_revision=0, idempotency_key='bad-change-000000001')
    assert (await service.snapshot(cid))['route_revision'] == 0
    await service.change_route(cid, route=target(''), expected_revision=0, idempotency_key='good-change-00000001')
    with pytest.raises(MigrationError):
        await service.store.rollback_migrations('0004')


def test_context_archive_is_complete_when_inline_budget_is_small(tmp_path):
    turns = [{'ordinal': i, 'state': 'completed', 'content': f'Decisão {i} ' + 'x'*800,
              'response': 'resposta', 'attachments': [], 'route': target('a')} for i in range(1, 30)]
    text, checkpoint = prepare_context({'id': 'conversation-test'}, turns, {'ordinal': 30}, tmp_path, budget_chars=2000)
    index = tmp_path / '.orchestrator/chat_context/indice.json'
    manifest = json.loads(index.read_text(encoding='utf-8'))
    assert checkpoint['history_count'] == 29
    assert checkpoint['inline_turns'] < 29
    assert len(manifest['entries']) == 29
    assert 'Decisão 1 ' in Path(manifest['entries'][0]['file']).read_text(encoding='utf-8')
    assert str(index) in text
    assert len(text) < 3000


@pytest.mark.asyncio
async def test_catalog_is_sanitized_and_recursive_compatibility_is_conservative(tmp_path):
    definition = {'id': 'id-a', 'name': 'Combo com espaço', 'strategy': 'priority',
                  'models': [{'model': 'claude/claude-sonnet-test', 'label': 'private@example.com', 'apiKey': 'private-secret'}]}
    nested = {'id': 'id-b', 'name': 'Aninhado', 'strategy': 'priority', 'models': [{'kind': 'combo-ref', 'comboName': definition['name']}]}
    data = {'combos': [definition, nested, {'name': 'Circular', 'models': [{'kind': 'combo-ref', 'comboName': 'Circular'}]}]}
    def handler(request):
        if request.url.path == '/api/health':return httpx.Response(200, json={'status': 'ok'})
        if request.url.path == '/api/combos':return httpx.Response(200, json=data)
        return httpx.Response(200, json={'data': [{'id': 'claude/claude-sonnet-test'}]})
    gateway = OmniRouteClient(api_key='test-gateway-key', transport=httpx.MockTransport(handler))
    routes = ConversationRoutes(ExecutionStore(tmp_path/'state.sqlite'), gateway)
    routes._versions = {'codex': 'test-version', 'claude': 'test-version'}
    out = await routes.catalog('claude')
    assert out['status'] == 'connected'
    assert out['combos'][0]['compatibility'] == 'unverified'
    assert out['combos'][2]['compatibility'] == 'unsupported'
    assert 'private' not in json.dumps(out)
    selection = {'executor': 'claude', 'connection_mode': 'omniroute', 'target_kind': 'combo', 'target_ref': nested['name']}
    first = await routes.describe(selection)
    data['combos'].append({'name': 'Outro', 'models': ['codex/model']})
    assert (await routes.describe(selection, refresh=True))['fingerprint'] == first['fingerprint']
    definition['models'].append({'model': 'codex/model'})
    changed=await routes.describe(selection, refresh=True)
    assert changed['compatibility']=='unverified'
    assert 'sem suporte oficial' in changed['reason']
    assert changed['fingerprint']!=first['fingerprint']


def test_gateway_function_profile_cannot_change_target_or_interpret_text_as_tools():
    body = {'model': 'dev-test', 'input': [], 'tools': [{'type': 'function', 'name': 'exec_command'},
            {'type': 'custom', 'name': 'apply_patch'}, {'type': 'web_search'}], 'client_metadata': {'ignored': True}}
    request = function_request(body, 'dev-test')
    assert request['tools'] == [{'type': 'function', 'name': 'exec_command'}]
    assert 'client_metadata' not in request
    with pytest.raises(ValueError):function_request(body, 'different')
    with pytest.raises(ValueError):function_request({**body, 'tools': []}, 'dev-test')
    # The CLI may compact or answer without tools after the initial tool
    # profile was admitted. Keep the target lock on those requests too.
    assert function_request({'model':'dev-test','input':[]},'dev-test',tools_admitted=True)['tools']==[]
    with pytest.raises(ValueError):function_request({'model':'other'},'dev-test',tools_admitted=True)


@pytest.mark.asyncio
async def test_combo_discovery_skips_model_request_and_batches_certificate_reads(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    requested = []
    def handler(request):
        requested.append(request.url.path)
        if request.url.path == '/api/health':
            return httpx.Response(200, json={'status': 'ok'})
        if request.url.path == '/api/combos':
            return httpx.Response(200, json={'combos': [
                {'name': f'Combo {i}', 'models': ['codex/model']} for i in range(20)]})
        raise AssertionError('Combo discovery must not wait for the model inventory')
    store = ExecutionStore(tmp_path / 'catalog.sqlite')
    routes = ConversationRoutes(store, OmniRouteClient(api_key='fixture-key', transport=httpx.MockTransport(handler)))
    routes._versions = {'codex': 'fixture-version'}
    routes._settings_loaded = True
    initialize = AsyncMock(wraps=store.initialize)
    monkeypatch.setattr(store, 'initialize', initialize)
    result = await routes.catalog(include_models=False)
    assert len(result['combos']) == 20 and result['models'] == []
    assert initialize.await_count == 1
    assert '/v1/models' not in requested
    info = await routes.describe({'executor': 'codex', 'connection_mode': 'omniroute', 'target_kind': 'combo', 'target_ref': 'Combo 0'})
    assert info['compatibility'] == 'unverified'
    assert '/v1/models' not in requested


@pytest.mark.asyncio
async def test_catalog_preserves_certification_and_invalidates_changed_definitions(tmp_path):
    combo = {'name': 'Fixture combo', 'models': ['codex/model-a']}
    def handler(request):
        if request.url.path == '/api/health': return httpx.Response(200, json={})
        if request.url.path == '/api/combos': return httpx.Response(200, json={'combos': [combo]})
        return httpx.Response(200, json={'data': []})
    store = ExecutionStore(tmp_path / 'certificate.sqlite')
    routes = ConversationRoutes(store, OmniRouteClient(api_key='fixture-key', transport=httpx.MockTransport(handler)))
    routes._versions = {'codex': 'fixture-version'}
    selection = {'executor': 'codex', 'connection_mode': 'omniroute', 'target_kind': 'combo', 'target_ref': combo['name']}
    info = await routes.describe(selection)
    async with store._connect() as db:
        await db.execute('INSERT INTO conversation_route_certificates (certificate_key, evidence_json) VALUES (?, ?)',
                         (info['fingerprint'], '{}'))
        await db.commit()
    assert (await routes.catalog(include_models=False))['combos'][0]['compatibility'] == 'verified'
    combo['models'] = ['codex/model-b']
    assert (await routes.catalog(refresh=True, include_models=False))['combos'][0]['compatibility'] == 'unverified'


@pytest.mark.asyncio
async def test_connection_settings_are_reversible_persisted_non_secret_and_conflict_checked(tmp_path):
    store = ExecutionStore(tmp_path/'state.sqlite')
    route = ConversationRoutes(store, OmniRouteClient(api_key='fixture-only-credential', enabled=False))
    first = await route.settings()
    assert first['version'] == 0 and first['credential_available']
    saved = await route.save_settings(base_url='http://127.0.0.1:20128/v1', enabled=True, expected_version=0, idempotency_key='connection-setting-0001')
    assert saved['enabled'] and saved['version'] == 1
    restarted = ConversationRoutes(store, OmniRouteClient(api_key='different-runtime-secret', enabled=False))
    assert (await restarted.settings())['enabled']
    with pytest.raises(OptimisticLockError):
        await route.save_settings(base_url='http://127.0.0.1:20128/v1', enabled=False, expected_version=0, idempotency_key='connection-stale-00001')
    with pytest.raises(ContractViolation):
        await route.save_settings(base_url='http://user:password@127.0.0.1:20128/v1', enabled=False, expected_version=1, idempotency_key='connection-bad-000001')
    async with store._connect() as db:
        row = await (await db.execute("SELECT value_json FROM preferences WHERE key='integration.omniroute'")).fetchone()
        assert 'credential' not in row[0] and 'secret' not in row[0]


@pytest.mark.asyncio
async def test_version_probe_does_not_inherit_open_launcher_stdin(tmp_path):
    import os
    import sys
    import subprocess
    from hydra_orch.bridge.worker_runner import cancel_process_tree
    script=tmp_path/'probe.py'
    script.write_text('import sys\nassert sys.stdin.read()==""\nprint("controlled-version-1")\n')
    shim=tmp_path/('codex.cmd' if os.name=='nt' else 'codex')
    if os.name=='nt':
        shim.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n')
    else:
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        shim.chmod(0o755)
    parent='''import asyncio,sys
import hydra_orch.core.conversation_route as mod
mod.shutil.which=lambda _:sys.argv[1]
routes=mod.ConversationRoutes(None,None)
print(asyncio.run(routes.version('codex')),flush=True)
'''
    process=await asyncio.create_subprocess_exec(sys.executable,'-c',parent,str(shim),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        **({'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}))
    try:
        # Deliberately leave the launcher's input pipe open.
        output=await asyncio.wait_for(process.stdout.readline(),5)
        assert output.strip()==b'controlled-version-1'
        await asyncio.wait_for(process.wait(),3)
        assert process.returncode==0
    finally:
        if process.returncode is None:
            await cancel_process_tree(process.pid)


@pytest.mark.asyncio
async def test_route_api_requires_auth_and_keeps_revision_on_same_conversation(service, monkeypatch):
    from hydra_orch import server
    from hydra_orch.core.auth import TokenVerifier
    token = 'route-test-bearer-0123456789012345'
    monkeypatch.setitem(server.app.state._state, 'token_verifier', TokenVerifier.from_token(token))
    monkeypatch.setattr(server, 'get_conversation_service', lambda: service)
    routes = ConversationRoutes(service.store, OmniRouteClient(enabled=False))
    monkeypatch.setattr(server, 'get_conversation_routes', lambda: routes)
    cid, _ = await create(service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://testserver') as client:
        assert (await client.get('/v1/control-plane/conversation-routes/connection')).status_code == 401
        assert (await client.post('/v1/control-plane/conversation-routes/verify', json=target(''))).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + token
        result = await client.patch(f'/v1/control-plane/conversations/{cid}/route', json={
            'route': target('model-b'), 'expected_revision': 0, 'idempotency_key': 'http-route-change-0001'})
        assert result.status_code == 200, result.text
        snapshot = (await client.get(f'/v1/control-plane/conversations/{cid}')).json()
        assert snapshot['id'] == cid and snapshot['route_revision'] == 1
        stale = await client.post(f'/v1/control-plane/conversations/{cid}/messages', json={
            'content': 'Não perder o rascunho', 'expected_last_seq': snapshot['last_seq'], 'idempotency_key': 'http-route-stale-0001'})
        assert stale.status_code == 409
        assert len((await service.snapshot(cid))['turns']) == 1


@pytest.mark.asyncio
async def test_gateway_launch_uses_scoped_delegate_and_preserves_sandbox(tmp_path, monkeypatch):
    import sys
    import hydra_orch.bridge.conversation_runner as module
    import hydra_orch.bridge.codex_catalog as catalog
    script = tmp_path/'fake.py'
    script.write_text('import json,sys\nsys.stdin.read()\nprint(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"fixture"}}))\n', encoding='utf-8')
    real_spawn = asyncio.create_subprocess_exec
    captured = {}
    async def spawn(*args, **kwargs):
        captured['args'], captured['env'] = args, kwargs['env']
        return await real_spawn(sys.executable, str(script), **kwargs)
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(module.shutil, 'which', lambda _: sys.executable)
    monkeypatch.setattr(catalog, 'gateway_catalog', lambda exe, target, home: tmp_path/'catalog.json')
    monkeypatch.setenv('HYDRA_API_TOKEN', 'never-inherit-this-server-token')
    async def emit(*a):pass
    await module.ConversationRunner().run({'id':'fixture'}, {'executor':'codex','access_mode':'read-only',
        'route':{'connection_mode':'omniroute','target_ref':'Combo A'}, '_gateway_base_url':'http://127.0.0.1:20128/v1',
        '_gateway_token':'never-send-upstream-key-to-cli'}, 'fixture', tmp_path, emit)
    assert captured['env']['OMNIROUTE_API_KEY'] != 'never-send-upstream-key-to-cli'
    assert 'HYDRA_API_TOKEN' not in captured['env']
    assert 'read-only' in captured['args']
    assert not any('never-send' in a for a in captured['args'])
