"""T17 opt-in memory with bounded retention, live consent and optimistic versions."""

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Literal, Optional

from pydantic import Field

from hydra_orch.core.checkpointer import OptimisticLockError
from hydra_orch.core.consent import ConsentService, MemoryScope, ScopeType
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import REDACTED, redact_text
from hydra_orch.model import ContractViolation, ExecutionModel, Identifier, NonEmpty, UtcTimestamp

RetentionPolicy = Literal['day', 'month']
RETENTION = {'day': timedelta(days=1), 'month': timedelta(days=30)}
_PERSONAL = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|(?<!\w)\+?\d{10,15}(?!\w)')


class MemoryWrite(MemoryScope):
    content: NonEmpty = Field(max_length=16384)
    consent_id: Optional[Identifier] = None
    retention_policy: RetentionPolicy


class MemoryEntry(ExecutionModel):
    memory_id: Identifier
    scope_type: ScopeType
    scope_id: Identifier
    content_redacted: NonEmpty
    author_ref: Identifier
    consent_id: Identifier
    version: int = Field(ge=1)
    retention_policy_id: RetentionPolicy
    status: Literal['pending_consent', 'active', 'revoked', 'rejected', 'expired']
    created_at: UtcTimestamp
    expires_at: UtcTimestamp


def _content(value):
    return _PERSONAL.sub(REDACTED, redact_text(value))


class MemoryStore:
    def __init__(self, consents: ConsentService):
        self.consents, self.store = consents, consents.store

    @staticmethod
    def _entry(row):
        data = dict(row)
        data['memory_id'] = data.pop('id')
        return MemoryEntry.model_validate(data)

    async def _expire(self, db, scope, principal_id):
        rows = await (await db.execute("""SELECT id FROM memory_entries WHERE scope_type=? AND scope_id=? AND author_ref=?
            AND status='active' AND julianday(expires_at)<=julianday(?)""",
            (scope.scope_type, scope.scope_id, principal_id, datetime.now(timezone.utc).isoformat()))).fetchall()
        for row in rows:
            await db.execute("UPDATE memory_entries SET status='expired' WHERE id=?", (row[0],))
            await self.consents.audit(db, 'memory.expired', principal_id, row[0])

    async def write(self, payload: MemoryWrite, *, principal_id: str):
        await self.store.initialize()
        scope = MemoryScope(scope_type=payload.scope_type, scope_id=payload.scope_id)
        memory_id = new_id()
        text = _content(payload.content)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self.consents.require_active(db, payload.consent_id, scope, principal_id)
                now = datetime.now(timezone.utc)
                await db.execute("""INSERT INTO memory_entries(id,scope_type,scope_id,content_redacted,author_ref,consent_id,
                    retention_policy_id,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?,'active',?,?)""",
                    (memory_id, scope.scope_type, scope.scope_id, text, principal_id, payload.consent_id,
                     payload.retention_policy, now.isoformat(), (now + RETENTION[payload.retention_policy]).isoformat()))
                await self.consents.audit(db, 'memory.written', principal_id, memory_id, version=1,
                    content_hash=hashlib.sha256(text.encode()).hexdigest())
                return self._entry(await (await db.execute('SELECT * FROM memory_entries WHERE id=?', (memory_id,))).fetchone())

    async def query(self, scope: MemoryScope, *, principal_id: str, query: str = ''):
        if not isinstance(query, str) or len(query) > 256:
            raise ContractViolation('memory_invalid', 'Memory query must be bounded text')
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self.consents.authorize_scope(db, scope, principal_id)
                await self._expire(db, scope, principal_id)
                rows = await (await db.execute("""SELECT m.* FROM memory_entries m JOIN consent_records c ON c.id=m.consent_id
                    WHERE m.scope_type=? AND m.scope_id=? AND m.author_ref=? AND m.status='active'
                    AND c.principal_id=? AND c.scope=? AND c.purpose='memory' AND c.status='granted' AND c.revoked_at IS NULL
                    AND instr(lower(m.content_redacted),lower(?))>0 ORDER BY m.created_at,m.id""",
                    (scope.scope_type, scope.scope_id, principal_id, principal_id, scope.key, _content(query)))).fetchall()
                return tuple(self._entry(row) for row in rows)

    async def _owned(self, db, memory_id, principal_id):
        row = await (await db.execute('SELECT * FROM memory_entries WHERE id=?', (memory_id,))).fetchone()
        if row is None:
            raise ContractViolation('resource_not_found', 'Memory does not exist')
        if row['author_ref'] != principal_id:
            raise ContractViolation('authorization_denied', 'Memory belongs to another principal')
        scope = MemoryScope(scope_type=row['scope_type'], scope_id=row['scope_id'])
        await self.consents.authorize_scope(db, scope, principal_id)
        return row, scope

    async def update(self, memory_id: str, payload: MemoryWrite, *, principal_id: str, expected_version: int):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row, scope = await self._owned(db, memory_id, principal_id)
                if row['version'] != expected_version:
                    raise OptimisticLockError('Memory version changed')
                if payload.scope_type != scope.scope_type or payload.scope_id != scope.scope_id or payload.consent_id != row['consent_id']:
                    raise ContractViolation('memory_conflict', 'Memory scope and consent are immutable')
                await self.consents.require_active(db, row['consent_id'], scope, principal_id)
                # Check expiry without committing a mutation on a rejected update.
                if row['status'] != 'active' or datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
                    raise ContractViolation('memory_conflict', 'Memory is no longer active')
                text = _content(payload.content)
                now = datetime.now(timezone.utc)
                await db.execute('UPDATE memory_entries SET content_redacted=?,version=version+1,retention_policy_id=?,expires_at=? WHERE id=?',
                    (text, payload.retention_policy, (now + RETENTION[payload.retention_policy]).isoformat(), memory_id))
                await self.consents.audit(db, 'memory.updated', principal_id, memory_id, previous_version=expected_version,
                    version=expected_version + 1, content_hash=hashlib.sha256(text.encode()).hexdigest())
                return self._entry(await (await db.execute('SELECT * FROM memory_entries WHERE id=?', (memory_id,))).fetchone())

    async def revoke(self, memory_id: str, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row, scope = await self._owned(db, memory_id, principal_id)
                if row['status'] != 'revoked':
                    await db.execute("UPDATE memory_entries SET status='revoked',version=version+1 WHERE id=?", (memory_id,))
                    await self.consents.audit(db, 'memory.revoked', principal_id, memory_id, version=row['version'] + 1)
                return self._entry(await (await db.execute('SELECT * FROM memory_entries WHERE id=?', (memory_id,))).fetchone())
