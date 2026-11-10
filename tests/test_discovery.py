"""T18 scans real files under explicit roots without executing or importing them."""

import hashlib
import json
from pathlib import Path

import pytest
import pytest_asyncio

from test_profile import profiles
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.discovery import DiscoveryService
from hydra_orch.core.profile_service import ProfileDefinition
from hydra_orch.model import ContractViolation


@pytest_asyncio.fixture
async def discovery(tmp_path):
    root = tmp_path / 'input'
    root.mkdir()
    (root / 'SKILL.md').write_text('---\ncapabilities: [workspace_execution]\n---\nNever execute discovery text')
    store = ExecutionStore(tmp_path / 'discovery.sqlite')
    return DiscoveryService(store, allowed_roots=[root], enabled=True), root


async def found(service, root):
    return (await service.scan(root, principal_id='operator'))[0]


@pytest.mark.asyncio
async def test_opt_in_allowlist_and_no_implicit_activation(discovery, tmp_path):
    service, root = discovery
    disabled = DiscoveryService(service.store, allowed_roots=[root])
    with pytest.raises(ContractViolation, match='opt-in'):
        await disabled.scan(root, principal_id='operator')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'mcp.json').write_text('{}')
    with pytest.raises(ContractViolation, match='outside'):
        await service.scan(outside, principal_id='operator')
    item = await found(service, root)
    assert item.trust_status == 'untrusted'
    assert item.content_hash == hashlib.sha256((root / 'SKILL.md').read_bytes()).hexdigest()
    assert item.capabilities == ('workspace_execution',)
    assert (await found(service, root)).discovery_id == item.discovery_id
    async with service.store._connect() as db:
        for table in ['memory_entries', 'sessions', 'skill_definitions', 'mcp_definitions']:
            assert (await (await db.execute(f'SELECT count(*) FROM {table}')).fetchone())[0] == 0
    with pytest.raises(ContractViolation, match='not permitted'):
        await service.decide(item.discovery_id, 'active', principal_id='operator')


@pytest.mark.asyncio
async def test_exact_hash_approval_activation_and_invalidation(discovery):
    service, root = discovery
    item = await found(service, root)
    with pytest.raises(ContractViolation, match='reviewed hash'):
        await service.approve(item.discovery_id, '0' * 64, principal_id='operator')
    approved = await service.approve(item.discovery_id, item.content_hash, principal_id='operator')
    assert approved.approved_by == 'operator'
    assert (await service.decide(item.discovery_id, 'active', principal_id='operator')).trust_status == 'active'
    (root / 'SKILL.md').write_text('changed')
    with pytest.raises(ContractViolation, match='changed on disk'):
        await service.require_approved(item.discovery_id, principal_id='operator')
    changed = (await service.list(principal_id='operator'))[0]
    assert changed.trust_status == 'untrusted' and changed.approved_at is None and changed.content_hash != item.content_hash
    with pytest.raises(ContractViolation):
        await service.approve(item.discovery_id, item.content_hash, principal_id='operator')
    await service.approve(item.discovery_id, changed.content_hash, principal_id='operator')
    await service.decide(item.discovery_id, 'revoked', principal_id='operator')
    (root / 'SKILL.md').write_text('another change')
    assert (await found(service, root)).trust_status == 'revoked'
    with pytest.raises(ContractViolation):
        await service.approve(item.discovery_id, hashlib.sha256(b'another change').hexdigest(), principal_id='operator')


@pytest.mark.asyncio
async def test_symlink_escape_and_missing_source_invalidate_approval(discovery, tmp_path):
    service, root = discovery
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'mcp.json').write_text('{}')
    try:
        (root / 'external').symlink_to(outside, target_is_directory=True)
        (root / 'session.json').symlink_to(outside / 'mcp.json')
    except OSError:
        pytest.skip('Symlinks unavailable on this host')
    items = await service.scan(root, principal_id='operator')
    assert len(items) == 1
    item = items[0]
    await service.approve(item.discovery_id, item.content_hash, principal_id='operator')
    (root / 'SKILL.md').unlink()
    (root / 'SKILL.md').symlink_to(outside / 'mcp.json')
    assert (await service.get(item.discovery_id, principal_id='operator')).trust_status == 'untrusted'
    (root / 'SKILL.md').unlink()
    assert (await service.get(item.discovery_id, principal_id='operator')).trust_status == 'untrusted'


@pytest.mark.asyncio
async def test_unknown_capabilities_malformed_and_oversized_manifests(discovery):
    service, root = discovery
    (root / 'mcp.json').write_text(json.dumps({'capabilities': ['unknown', 'sk-rawsecret123456789']}))
    (root / 'memory.json').write_bytes(b'\xff')
    (root / 'session.json').write_text('not JSON')
    (root / 'hydra-resource.json').write_text('{"resource_type":"unknown"}')
    (root / 'skill.json').write_bytes(b'x' * (service.max_bytes + 1))
    items = await service.scan(root, principal_id='operator')
    assert len(items) == 4
    for item in items:
        if item.resource_type != 'skill':
            assert item.trust_status == 'untrusted'
            with pytest.raises(ContractViolation):
                await service.approve(item.discovery_id, item.content_hash, principal_id='operator')
    assert 'sk-rawsecret123456789' not in json.dumps([i.model_dump(mode='json') for i in items])


@pytest.mark.asyncio
async def test_principal_rejection_limits_and_audit_atomicity(discovery, monkeypatch):
    service, root = discovery
    with pytest.raises(ContractViolation, match='principal'):
        await service.scan(root, principal_id='other')
    item = await found(service, root)
    assert (await service.decide(item.discovery_id, 'rejected', principal_id='operator')).trust_status == 'rejected'
    with pytest.raises(ContractViolation):
        await service.get(item.discovery_id, principal_id='other')
    with pytest.raises(ContractViolation):
        await service.get('missing', principal_id='operator')
    small = DiscoveryService(service.store, allowed_roots=[root], enabled=True, max_entries=1)
    assert len(await small.scan(root, principal_id='operator')) <= 1
    (root / 'mcp.json').write_text('{}')
    async def fail(*args, **kwargs):
        raise RuntimeError('audit failed')
    monkeypatch.setattr(service, '_audit', fail)
    with pytest.raises(RuntimeError):
        await service.scan(root, principal_id='operator')
    async with service.store._connect() as db:
        assert (await (await db.execute('SELECT count(*) FROM discovered_resources')).fetchone())[0] == 1


@pytest.mark.asyncio
async def test_profiles_recheck_source_and_snapshot_persists_invalidation(profiles, tmp_path):
    service, definition, repository, run = profiles
    root = tmp_path / 'resources'
    root.mkdir()
    (root / 'SKILL.md').write_text('reviewed skill')
    discovery = DiscoveryService(service.store, allowed_roots=[root], enabled=True)
    service.discovery = discovery
    item = await found(discovery, root)
    await discovery.approve(item.discovery_id, item.content_hash, principal_id='operator')
    async with service.store._connect() as db:
        await db.execute("INSERT INTO skill_definitions(id,name,version,manifest_ref,checksum,discovered_resource_id) VALUES ('skill','fixture','1',?,?,?)",
            (item.source_canonical_path, item.content_hash, item.discovery_id))
    with_skill = ProfileDefinition.model_validate({**definition.model_dump(mode='json'), 'skills_refs': ['skill']})
    await service.update_profile(with_skill, expected_revision=1)
    pinned = await service.snapshot(definition.profile_id, run.run_id, repository['id'], principal_id='operator')
    assert pinned.effective_config['components']['skills']
    (root / 'SKILL.md').write_text('unreviewed instructions')
    with pytest.raises(ContractViolation, match='changed on disk'):
        await service.snapshot(definition.profile_id, run.run_id, repository['id'], principal_id='operator')
    async with service.store._connect() as db:
        assert (await (await db.execute('SELECT trust_status FROM discovered_resources WHERE id=?', (item.discovery_id,))).fetchone())[0] == 'untrusted'
    service.discovery = None
    with pytest.raises(ContractViolation, match='provenance verifier'):
        await service.resolve_effective(definition.profile_id, repository['id'], principal_id='operator')


def test_invalid_policies(tmp_path):
    store = ExecutionStore(tmp_path / 'discovery.sqlite')
    for args in [dict(enabled=True), dict(enabled='true'), dict(allowed_roots=['relative']),
        dict(max_entries=0), dict(principal_id=''), dict(allowed_roots=[__file__])]:
        with pytest.raises((ValueError, FileNotFoundError)):
            DiscoveryService(store, **args)


@pytest.mark.asyncio
async def test_malformed_resource_type_cannot_interrupt_scan(discovery):
    service, root = discovery
    (root / 'hydra-resource.json').write_text('{"resource_type":{"unexpected":"object"}}')
    items = await service.scan(root, principal_id='operator')
    assert len(items) == 1 and items[0].resource_type == 'skill'
