"""T17 consent, redaction, isolation and revocation against real SQLite."""

import asyncio
from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from test_profile import profiles
from hydra_orch import server
from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError
from hydra_orch.core.consent import ConsentService, MemoryScope
from hydra_orch.core.memory_store import MemoryStore, MemoryWrite
from hydra_orch.core.profile_service import ProfileDefinition
from hydra_orch.model import ContractViolation


def memory(profiles):
    service = profiles[0]
    return MemoryStore(ConsentService(service.store, service.workspaces))


def scope(profiles):
    return MemoryScope(scope_type='project', scope_id=profiles[3].project_id)


async def grant(mem, target):
    consent = await mem.consents.request(target, principal_id='operator')
    return await mem.consents.decide(consent.consent_id, 'granted', principal_id='operator')


def payload(target, consent_id=None, **changes):
    return MemoryWrite(scope_type=target.scope_type, scope_id=target.scope_id, consent_id=consent_id,
        content=changes.get('content', 'Prefere tarefas pequenas'), retention_policy=changes.get('retention_policy', 'day'))


@pytest.mark.asyncio
async def test_no_consent_no_write_and_wrong_consent_scope(profiles):
    mem, target = memory(profiles), scope(profiles)
    for consent_id in (None, 'missing'):
        with pytest.raises(ContractViolation, match='active consent'):
            await mem.write(payload(target, consent_id), principal_id='operator')
    requested = await mem.consents.request(target, principal_id='operator')
    with pytest.raises(ContractViolation):
        await mem.write(payload(target, requested.consent_id), principal_id='operator')
    consent = await grant(mem, MemoryScope(scope_type='principal', scope_id='operator'))
    with pytest.raises(ContractViolation, match='must match'):
        await mem.write(payload(target, consent.consent_id), principal_id='operator')
    async with mem.store._connect() as db:
        assert (await (await db.execute('SELECT count(*) FROM memory_entries')).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_scoped_versioned_redacted_memory_and_revoke(profiles):
    mem, target = memory(profiles), scope(profiles)
    consent = await grant(mem, target)
    assert (await mem.consents.get(consent.consent_id, principal_id='operator')).status == 'granted'
    assert len(await mem.consents.list(target, principal_id='operator')) == 1
    secret = 'sk-memorytoken123456789'
    raw = f'Prefere Python. token={secret}; email=ana@example.com CPF 123.456.789-00 telefone +5511999999999'
    entry = await mem.write(payload(target, consent.consent_id, content=raw), principal_id='operator')
    assert entry.version == 1 and entry.author_ref == 'operator'
    assert secret not in entry.content_redacted and 'ana@example.com' not in entry.content_redacted
    assert '123.456.789-00' not in entry.content_redacted and '5511999999999' not in entry.content_redacted
    assert entry.expires_at - entry.created_at == timedelta(days=1)
    assert len(await mem.query(target, principal_id='operator', query='PYTHON')) == 1
    updated = await mem.update(entry.memory_id, payload(target, consent.consent_id, content='Prefere Git', retention_policy='month'),
        principal_id='operator', expected_version=1)
    assert updated.version == 2 and updated.retention_policy_id == 'month'
    with pytest.raises(OptimisticLockError):
        await mem.update(entry.memory_id, payload(target, consent.consent_id), principal_id='operator', expected_version=1)
    assert not await mem.query(target, principal_id='operator', query='Python')
    revoked = await mem.revoke(entry.memory_id, principal_id='operator')
    assert revoked.status == 'revoked' and revoked.version == 3
    assert await mem.revoke(entry.memory_id, principal_id='operator') == revoked
    assert not await mem.query(target, principal_id='operator')
    with pytest.raises(ContractViolation, match='no longer active'):
        await mem.update(entry.memory_id, payload(target, consent.consent_id), principal_id='operator', expected_version=3)
    async with mem.store._connect() as db:
        rows = await (await db.execute("SELECT response_json FROM commands WHERE scope='consent_memory'")).fetchall()
    assert secret not in json.dumps([r[0] for r in rows]) and raw not in json.dumps([r[0] for r in rows])


@pytest.mark.asyncio
async def test_revocation_blocks_reads_writes_and_profile_in_new_runs(profiles):
    mem, target = memory(profiles), scope(profiles)
    consent = await grant(mem, target)
    entry = await mem.write(payload(target, consent.consent_id), principal_id='operator')
    service, definition, repository, run = profiles
    definition = ProfileDefinition.model_validate({**definition.model_dump(mode='json'), 'memory_policy': {'enabled': True, 'consent_id': consent.consent_id}})
    await service.update_profile(definition, expected_revision=1)
    await service.resolve_effective(definition.profile_id, repository['id'], principal_id='operator')
    revoked = await mem.consents.decide(consent.consent_id, 'revoked', principal_id='operator')
    assert revoked.revoked_at is not None
    assert (await mem.consents.decide(consent.consent_id, 'revoked', principal_id='operator')) == revoked
    assert not await mem.query(target, principal_id='operator')
    with pytest.raises(ContractViolation, match='active consent'):
        await mem.write(payload(target, consent.consent_id), principal_id='operator')
    with pytest.raises(ContractViolation, match='Memory requires'):
        await service.resolve_effective(definition.profile_id, repository['id'], principal_id='operator')
    with pytest.raises(ContractViolation, match='not permitted'):
        await mem.consents.decide(consent.consent_id, 'granted', principal_id='operator')
    async with mem.store._connect() as db:
        assert (await (await db.execute('SELECT status FROM memory_entries WHERE id=?', (entry.memory_id,))).fetchone())[0] == 'revoked'


@pytest.mark.asyncio
async def test_expiration_and_consent_denial(profiles):
    mem, target = memory(profiles), scope(profiles)
    consent = await grant(mem, target)
    entry = await mem.write(payload(target, consent.consent_id), principal_id='operator')
    async with mem.store._connect() as db:
        await db.execute('UPDATE memory_entries SET expires_at=? WHERE id=?', ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), entry.memory_id))
    assert not await mem.query(target, principal_id='operator')
    expired = await mem.consents.decide(consent.consent_id, 'expired', principal_id='operator')
    assert expired.status == 'expired'
    denied = await mem.consents.request(target, principal_id='operator')
    assert (await mem.consents.decide(denied.consent_id, 'denied', principal_id='operator')).status == 'denied'
    with pytest.raises(ContractViolation):
        await mem.consents.decide(denied.consent_id, 'granted', principal_id='operator')


@pytest.mark.asyncio
async def test_other_principal_and_contexts_are_isolated(profiles):
    mem, target = memory(profiles), scope(profiles)
    consent = await grant(mem, target)
    entry = await mem.write(payload(target, consent.consent_id), principal_id='operator')
    for call in [mem.query(target, principal_id='intruder'), mem.consents.get(consent.consent_id, principal_id='intruder'),
        mem.revoke(entry.memory_id, principal_id='intruder'),
        mem.consents.request(MemoryScope(scope_type='principal', scope_id='operator'), principal_id='intruder')]:
        with pytest.raises(ContractViolation, match='[Pp]rincipal|owned'):
            await call
    assert not await mem.query(MemoryScope(scope_type='principal', scope_id='operator'), principal_id='operator')
    with pytest.raises(ContractViolation):
        await mem.update(entry.memory_id, payload(MemoryScope(scope_type='principal', scope_id='operator'), consent.consent_id),
            principal_id='operator', expected_version=1)


@pytest.mark.asyncio
async def test_checkpoints_do_not_implicitly_create_memory(profiles):
    mem = memory(profiles)
    await mem.store.save_checkpoint('session', 'task', 'provider', 'prompt', 'buffer', 'running')
    assert not await mem.query(scope(profiles), principal_id='operator')
    consent = await grant(mem, scope(profiles))
    await mem.write(payload(scope(profiles), consent.consent_id), principal_id='operator')
    checkpoint = await mem.store.get_checkpoint('session')
    assert checkpoint is not None
    await mem.consents.decide(consent.consent_id, 'revoked', principal_id='operator')
    assert await mem.store.get_checkpoint('session') == checkpoint


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_consent_and_memory(profiles, monkeypatch):
    mem, target = memory(profiles), scope(profiles)
    consent = await grant(mem, target)
    async def fail(*args, **kwargs):
        raise RuntimeError('audit failed')
    monkeypatch.setattr(mem.consents, 'audit', fail)
    with pytest.raises(RuntimeError):
        await mem.write(payload(target, consent.consent_id), principal_id='operator')
    assert not await mem.query(target, principal_id='operator')
    with pytest.raises(RuntimeError):
        await mem.consents.decide(consent.consent_id, 'revoked', principal_id='operator')
    assert (await mem.consents.get(consent.consent_id, principal_id='operator')).status == 'granted'


@pytest.mark.asyncio
async def test_concurrent_updates_have_one_winner(profiles):
    mem, target = memory(profiles), scope(profiles)
    consent = await grant(mem, target)
    entry = await mem.write(payload(target, consent.consent_id), principal_id='operator')
    outcomes = await asyncio.gather(*(mem.update(entry.memory_id, payload(target, consent.consent_id, content=f'v-{i}'),
        principal_id='operator', expected_version=1) for i in range(2)), return_exceptions=True)
    assert sum(isinstance(x, OptimisticLockError) for x in outcomes) == 1
    assert (await mem.query(target, principal_id='operator'))[0].version == 2


@pytest.mark.asyncio
async def test_http_missing_consent_conflicts_and_authenticated_flow(profiles, monkeypatch):
    from hydra_orch.core.run_service import RunService
    mem, target = memory(profiles), scope(profiles)
    runs = RunService(repo_root=profiles[3].repo_root, store=mem.store)
    monkeypatch.setattr(server, '_run_service', runs)
    token = 'memory-local-token-12345678901234567890'
    monkeypatch.setitem(server.app.state._state, 'token_verifier', TokenVerifier.from_token(token))
    prefix = '/v1/control-plane'
    client = TestClient(server.app)
    try:
        headers = {'Authorization': f'Bearer {token}'}
        assert client.get(f'{prefix}/memory', params=target.model_dump()).status_code == 401
        raw = payload(target).model_dump(mode='json')
        assert client.post(f'{prefix}/memory', json=raw, headers=headers).status_code == 409
        response = client.post(f'{prefix}/consents', json=target.model_dump(mode='json'), headers=headers)
        assert response.status_code == 201
        consent_id = response.json()['consent_id']
        assert client.post(f'{prefix}/consents/{consent_id}', json={'action': 'granted'}, headers=headers).status_code == 200
        assert len(client.get(f'{prefix}/consents', params={'scope_type': target.scope_type, 'scope_id': target.scope_id}, headers=headers).json()) == 1
        raw['consent_id'] = consent_id
        response = client.post(f'{prefix}/memory', json=raw, headers=headers)
        assert response.status_code == 201
        memory_id = response.json()['memory_id']
        assert client.put(f'{prefix}/memory/{memory_id}', json=raw, params={'expected_version': 1}, headers=headers).json()['version'] == 2
        assert client.put(f'{prefix}/memory/{memory_id}', json=raw, params={'expected_version': 1}, headers=headers).status_code == 409
        assert client.post(f'{prefix}/memory/{memory_id}/revoke', headers=headers).status_code == 200
        assert client.post(f'{prefix}/consents/{consent_id}/revoke', headers=headers).status_code == 200
        assert not client.get(f'{prefix}/memory', params={'scope_type': target.scope_type, 'scope_id': target.scope_id}, headers=headers).json()
    finally:
        client.close()


def test_memory_schema_rejects_execution_checkpoint_payloads():
    for fields in [dict(scope_type='run', scope_id='run'), dict(scope_type='principal', scope_id='operator', partial_output='checkpoint')]:
        with pytest.raises(ValidationError):
            MemoryWrite(content='explicit', retention_policy='day', **fields)


@pytest.mark.asyncio
async def test_area_workspace_scopes_and_invalid_inputs(profiles, tmp_path):
    mem = memory(profiles)
    async with mem.store._connect() as db:
        workspace = await (await db.execute('SELECT id,area_id FROM area_workspaces LIMIT 1')).fetchone()
    for target in [MemoryScope(scope_type='workspace', scope_id=workspace['id']), MemoryScope(scope_type='area', scope_id=workspace['area_id'])]:
        consent = await grant(mem, target)
        entry = await mem.write(payload(target, consent.consent_id), principal_id='operator')
        assert (await mem.query(target, principal_id='operator'))[0].memory_id == entry.memory_id
    with pytest.raises(ContractViolation):
        await mem.query(scope(profiles), principal_id='operator', query='q' * 257)
    with pytest.raises(ContractViolation):
        await mem.consents.request(scope(profiles), principal_id='')
    with pytest.raises(ContractViolation, match='does not exist'):
        await mem.revoke('missing', principal_id='operator')
    with pytest.raises(ContractViolation, match='does not exist'):
        await mem.consents.get('missing', principal_id='operator')
    from hydra_orch.core.workspace_registry import WorkspaceRegistry
    other = WorkspaceRegistry(ExecutionStore(tmp_path / 'other.sqlite'), allowed_roots=[tmp_path])
    with pytest.raises(ValueError):
        ConsentService(mem.store, other)
