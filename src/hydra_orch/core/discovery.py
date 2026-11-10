"""T18 bounded opt-in discovery; files are data until explicit hash approval."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Literal

import yaml

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import ContractViolation, ExecutionModel, Identifier, Sha256, UtcTimestamp

KNOWN_CAPABILITIES = frozenset({'inference', 'workspace_execution', 'tool_execution', 'native_resume',
    'cancel_process_tree', 'filesystem_sandbox', 'network_isolation'})
NAMES = {'SKILL.md': 'skill', 'skill.json': 'skill', 'mcp.json': 'mcp', 'memory.json': 'memory',
    'session.json': 'session', 'hydra-resource.json': None}
SKIP_DIRS = frozenset({'.git', '.venv', 'node_modules', '__pycache__', '.orchestrator', 'vendor', 'dist', 'build'})


class DiscoveredResource(ExecutionModel):
    discovery_id: Identifier
    resource_type: Literal['skill', 'mcp', 'memory', 'session']
    source_canonical_path: str
    content_hash: Sha256
    capabilities: tuple[str, ...] = ()
    trust_status: Literal['untrusted', 'approved', 'active', 'rejected', 'revoked']
    discovered_at: UtcTimestamp
    approved_at: UtcTimestamp | None = None
    approved_by: str | None = None


class DiscoveryService:
    def __init__(self, store: ExecutionStore, *, allowed_roots=(), enabled=False, principal_id='operator',
                 max_entries=1000, max_bytes=262144, max_depth=16):
        if (not isinstance(enabled, bool) or not principal_id or redact(principal_id) != principal_id
                or any(type(v) is not int or v < 1 for v in (max_entries, max_bytes, max_depth))):
            raise ValueError('Explicit discovery policy and bounded positive limits are required')
        self.store, self.enabled, self.principal_id = store, enabled, principal_id
        self.max_entries, self.max_bytes, self.max_depth = max_entries, max_bytes, max_depth
        roots = []
        for value in allowed_roots:
            path = Path(value)
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('Discovery roots must be absolute without traversal')
            canonical = path.resolve(strict=True)
            if not canonical.is_dir():
                raise ValueError('Discovery roots must be directories')
            roots.append(canonical)
        self.roots = tuple(dict.fromkeys(roots))
        self.identities = {root: (root.stat().st_dev, root.stat().st_ino) for root in self.roots}
        if self.enabled and not self.roots:
            raise ValueError('Enabled discovery requires an explicit root allowlist')

    def _authorize(self, principal_id):
        if principal_id != self.principal_id:
            raise ContractViolation('authorization_denied', 'Discovery belongs to another principal')
        if not self.enabled:
            raise ContractViolation('discovery_disabled', 'Discovery requires explicit opt-in')

    def _root_for(self, path):
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts:
            raise ContractViolation('discovery_scope', 'Discovery requires an authorized absolute path')
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise ContractViolation('discovery_scope', 'Symlink or redirected resource is not allowed')
        for root in self.roots:
            if resolved == root or root in resolved.parents:
                info = root.stat()
                if self.identities[root] == (info.st_dev, info.st_ino):
                    return root
        raise ContractViolation('discovery_scope', 'Path is outside the current discovery allowlist')

    def _read(self, path):
        path = Path(path)
        root = self._root_for(path)
        descriptors = []
        try:
            if os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'):
                directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                descriptors.append(directory)
                identity = os.fstat(directory)
                if self.identities[root] != (identity.st_dev, identity.st_ino):
                    raise ContractViolation('discovery_scope', 'Discovery root changed')
                parts = path.relative_to(root).parts
                for part in parts[:-1]:
                    directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    descriptors.append(directory)
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            else:
                fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
            descriptors.append(fd)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > self.max_bytes:
                raise ContractViolation('discovery_invalid', 'Manifest must be a bounded regular file')
            data = b''
            while len(data) <= self.max_bytes:
                chunk = os.read(fd, min(65536, self.max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data += chunk
            after = os.fstat(fd)
            self._root_for(path)
            observed = path.stat()
            if (len(data) > self.max_bytes or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                    or (observed.st_dev, observed.st_ino) != (after.st_dev, after.st_ino)):
                raise ContractViolation('discovery_changed', 'Manifest changed while being read')
            return data
        finally:
            for fd in reversed(descriptors):
                os.close(fd)

    @staticmethod
    def _metadata(path, data):
        kind = NAMES.get(path.name)
        try:
            text = data.decode('utf-8')
            if path.name == 'SKILL.md':
                header = text.split('---', 2)[1] if text.startswith('---\n') and text.count('---') >= 2 else '{}'
                metadata = yaml.load(header, Loader=yaml.BaseLoader)
            else:
                metadata = json.loads(text)
            if not isinstance(metadata, dict):
                raise ValueError('Expected object')
            kind = kind or metadata.get('resource_type')
            caps = metadata.get('capabilities', [])
            if not isinstance(caps, list) or any(not isinstance(c, str) or len(c) > 128 for c in caps) or len(caps) > 32:
                raise ValueError('Invalid capabilities')
            caps = tuple(sorted(set(redact_text(c) for c in caps)))
        except (ValueError, UnicodeError, yaml.YAMLError, RecursionError):
            caps = ('unknown:invalid_manifest',)
        if not isinstance(kind, str) or kind not in {'skill', 'mcp', 'memory', 'session'}:
            raise ContractViolation('discovery_invalid', 'Unknown resource type')
        return kind, caps

    def _files(self, requested):
        self._root_for(requested)
        stack, files, visited, skipped = [(Path(requested), 0)], [], 0, 0
        while stack and visited < self.max_entries:
            directory, depth = stack.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited += 1
                    if visited > self.max_entries:
                        break
                    if entry.is_symlink():
                        skipped += 1
                    elif entry.is_dir(follow_symlinks=False):
                        if depth < self.max_depth and entry.name not in SKIP_DIRS:
                            stack.append((Path(entry.path), depth + 1))
                    elif entry.is_file(follow_symlinks=False) and entry.name in NAMES:
                        files.append(Path(entry.path))
        return sorted(files), skipped, visited >= self.max_entries

    async def _audit(self, db, event, principal_id, resource_id=None, **details):
        payload = {'event': event, 'principal_id': principal_id, 'discovery_id': resource_id, **details}
        await self.store._record_command_in_tx(db, scope='discovery', idempotency_key=new_id(),
            request_hash=self.store.compute_request_hash(payload), response_payload=redact(payload))

    @staticmethod
    def _record(row):
        return DiscoveredResource(discovery_id=row['id'], resource_type=row['resource_type'],
            source_canonical_path=row['source_canonical_path'], content_hash=row['content_hash'],
            capabilities=tuple(json.loads(row['capabilities_json'])), trust_status=row['trust_status'],
            discovered_at=row['discovered_at'], approved_at=row['approved_at'], approved_by=row['approved_by'])

    async def _owned(self, db, resource_id, principal_id):
        row = await (await db.execute("""SELECT r.* FROM discovered_resources r JOIN commands c ON
            c.scope='discovery_owner' AND c.idempotency_key=r.id WHERE r.id=?
            AND json_extract(c.response_json,'$.principal_id')=?""", (resource_id, principal_id))).fetchone()
        if row is None:
            raise ContractViolation('authorization_denied', 'Discovered resource is not owned by this principal')
        return row

    async def scan(self, authorized_root, *, principal_id):
        self._authorize(principal_id)
        await self.store.initialize()
        paths, skipped, truncated = await asyncio.to_thread(self._files, Path(authorized_root))
        found = []
        for path in paths:
            try:
                data = await asyncio.to_thread(self._read, path)
                kind, caps = self._metadata(path, data)
                if redact(str(path)) != str(path):
                    raise ContractViolation('discovery_invalid', 'Sensitive path cannot be catalogued')
            except (OSError, ContractViolation):
                skipped += 1
                continue
            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    old = await (await db.execute("""SELECT r.* FROM discovered_resources r JOIN commands c ON
                        c.scope='discovery_owner' AND c.idempotency_key=r.id WHERE r.source_canonical_path=?
                        AND json_extract(c.response_json,'$.principal_id')=? ORDER BY r.id LIMIT 1""", (str(path), principal_id))).fetchone()
                    resource_id = old['id'] if old else new_id()
                    if old is None:
                        digest = hashlib.sha256(data).hexdigest()
                        await db.execute("""INSERT INTO discovered_resources(id,resource_type,source_canonical_path,content_hash,
                            capabilities_json,trust_status,discovered_at) VALUES (?,?,?,?,?,'untrusted',?)""",
                            (resource_id, kind, str(path), digest, json.dumps(caps), datetime.now(timezone.utc).isoformat()))
                        await self.store._record_command_in_tx(db, scope='discovery_owner', idempotency_key=resource_id,
                            request_hash=digest, response_payload={'principal_id': principal_id, 'source': str(path)})
                        await self._audit(db, 'discovery.found', principal_id, resource_id, content_hash=digest)
            found.append(await self.get(resource_id, principal_id=principal_id))
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._audit(db, 'discovery.scanned', principal_id, root=str(authorized_root), skipped=skipped, truncated=truncated)
        return tuple(found)

    async def _refresh(self, resource_id, principal_id):
        self._authorize(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            old = await self._owned(db, resource_id, principal_id)
        valid, digest, caps = True, old['content_hash'], tuple(json.loads(old['capabilities_json']))
        try:
            data = await asyncio.to_thread(self._read, Path(old['source_canonical_path']))
            kind, caps = self._metadata(Path(old['source_canonical_path']), data)
            digest = hashlib.sha256(data).hexdigest()
            valid = kind == old['resource_type'] and set(caps) <= KNOWN_CAPABILITIES
        except (OSError, ContractViolation):
            valid = False
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await self._owned(db, resource_id, principal_id)
                changed = digest != row['content_hash'] or not valid
                if changed:
                    status = row['trust_status'] if row['trust_status'] in {'rejected', 'revoked'} else 'untrusted'
                    if row['content_hash'] != digest or row['trust_status'] != status or row['approved_at'] is not None:
                        await db.execute('UPDATE discovered_resources SET content_hash=?,capabilities_json=?,trust_status=?,approved_at=NULL,approved_by=NULL WHERE id=?',
                            (digest, json.dumps(caps), status, resource_id))
                        await self._audit(db, 'discovery.invalidated', principal_id, resource_id, content_hash=digest)
                    row = await self._owned(db, resource_id, principal_id)
                return self._record(row), valid

    async def get(self, resource_id, *, principal_id):
        record, _ = await self._refresh(resource_id, principal_id)
        return record

    async def list(self, *, principal_id):
        self._authorize(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            rows = await (await db.execute("SELECT idempotency_key FROM commands WHERE scope='discovery_owner' AND json_extract(response_json,'$.principal_id')=? ORDER BY idempotency_key", (principal_id,))).fetchall()
        return tuple([await self.get(row[0], principal_id=principal_id) for row in rows])

    async def approve(self, resource_id, expected_hash, *, principal_id):
        record, valid = await self._refresh(resource_id, principal_id)
        if not valid or record.content_hash != expected_hash or record.trust_status not in {'untrusted', 'approved'}:
            raise ContractViolation('discovery_untrusted', 'Approval requires an unchanged valid manifest and its reviewed hash')
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await self._owned(db, resource_id, principal_id)
                if row['content_hash'] != expected_hash or row['trust_status'] not in {'untrusted', 'approved'}:
                    raise ContractViolation('discovery_untrusted', 'Manifest changed during approval')
                await db.execute("UPDATE discovered_resources SET trust_status='approved',approved_at=?,approved_by=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), principal_id, resource_id))
                await self._audit(db, 'discovery.approved', principal_id, resource_id, content_hash=expected_hash)
                return self._record(await self._owned(db, resource_id, principal_id))

    async def require_approved(self, resource_id, *, principal_id):
        record, valid = await self._refresh(resource_id, principal_id)
        if not valid or record.trust_status not in {'approved', 'active'}:
            raise ContractViolation('component_untrusted', 'Discovered component is not approved or changed on disk')
        return record

    async def decide(self, resource_id, action: Literal['active', 'rejected', 'revoked'], *, principal_id):
        record, valid = await self._refresh(resource_id, principal_id)
        allowed = {'untrusted': {'rejected'}, 'approved': {'active', 'revoked'}, 'active': {'revoked'}}
        if (action not in allowed.get(record.trust_status, set())
                or action == 'active' and not valid):
            raise ContractViolation('discovery_untrusted', 'Discovery transition is not permitted')
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await self._owned(db, resource_id, principal_id)
                if row['content_hash'] != record.content_hash or row['trust_status'] != record.trust_status:
                    raise ContractViolation('discovery_untrusted', 'Resource changed during decision')
                await db.execute('UPDATE discovered_resources SET trust_status=? WHERE id=?', (action, resource_id))
                await self._audit(db, f'discovery.{action}', principal_id, resource_id)
                return self._record(await self._owned(db, resource_id, principal_id))
