"""T17 explicit, scoped and auditable memory consent."""

from datetime import datetime, timezone
from typing import Literal, Optional

from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.model import ContractViolation, ExecutionModel, Identifier, UtcTimestamp

ScopeType = Literal['principal', 'area', 'workspace', 'project']


class MemoryScope(ExecutionModel):
    scope_type: ScopeType
    scope_id: Identifier

    @property
    def key(self):
        return f'{self.scope_type}:{self.scope_id}'


class ConsentRecord(ExecutionModel):
    consent_id: Identifier
    principal_id: Identifier
    purpose: Literal['memory']
    scope: str
    status: Literal['requested', 'granted', 'denied', 'revoked', 'expired']
    granted_at: Optional[UtcTimestamp] = None
    revoked_at: Optional[UtcTimestamp] = None


class ConsentService:
    def __init__(self, store: ExecutionStore, workspaces: WorkspaceRegistry):
        if workspaces.store is not store:
            raise ValueError('Consent and registry must share the canonical store')
        self.store, self.workspaces = store, workspaces

    async def authorize_scope(self, db, scope: MemoryScope, principal_id: str):
        if not principal_id or redact(principal_id) != principal_id:
            raise ContractViolation('authorization_denied', 'A valid authenticated principal is required')
        if scope.scope_type == 'principal':
            if scope.scope_id != principal_id:
                raise ContractViolation('authorization_denied', 'Principal scope belongs to another operator')
        elif scope.scope_type == 'area':
            await self.workspaces._area(db, scope.scope_id, principal_id)
        elif scope.scope_type == 'workspace':
            await self.workspaces._workspace(db, scope.scope_id, principal_id)
        else:
            await self.workspaces._project(db, scope.scope_id, principal_id)

    async def audit(self, db, event, principal_id, resource_id, **detail):
        data = {'event': event, 'principal_id': principal_id, 'resource_id': resource_id, **detail}
        await self.store._record_command_in_tx(db, scope='consent_memory', idempotency_key=new_id(),
            request_hash=self.store.compute_request_hash(data), response_payload=data)

    @staticmethod
    def _record(row):
        return ConsentRecord(consent_id=row['id'], principal_id=row['principal_id'], purpose=row['purpose'],
            scope=row['scope'], status=row['status'], granted_at=row['granted_at'], revoked_at=row['revoked_at'])

    async def _owned(self, db, consent_id, principal_id):
        row = await (await db.execute('SELECT * FROM consent_records WHERE id=?', (consent_id,))).fetchone()
        if row is None:
            raise ContractViolation('resource_not_found', 'Consent does not exist')
        if row['principal_id'] != principal_id:
            raise ContractViolation('authorization_denied', 'Consent belongs to another principal')
        kind, _, scope_id = row['scope'].partition(':')
        scope = MemoryScope(scope_type=kind, scope_id=scope_id)
        await self.authorize_scope(db, scope, principal_id)
        return row

    async def require_active(self, db, consent_id, scope, principal_id):
        row = await (await db.execute('SELECT * FROM consent_records WHERE id=?', (consent_id,))).fetchone()
        if row is None or row['status'] != 'granted' or row['revoked_at'] is not None:
            raise ContractViolation('consent_required', 'An active consent is required for memory')
        if row['principal_id'] != principal_id or row['purpose'] != 'memory' or row['scope'] != scope.key:
            raise ContractViolation('consent_required', 'Consent principal, purpose and scope must match memory')
        await self.authorize_scope(db, scope, principal_id)
        return row

    async def request(self, scope: MemoryScope, *, principal_id: str):
        await self.store.initialize()
        consent_id = new_id()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self.authorize_scope(db, scope, principal_id)
                await db.execute("INSERT INTO consent_records(id,principal_id,purpose,scope) VALUES (?,?,'memory',?)",
                    (consent_id, principal_id, scope.key))
                await self.audit(db, 'consent.requested', principal_id, consent_id, scope=scope.key)
                return self._record(await self._owned(db, consent_id, principal_id))

    async def get(self, consent_id: str, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            return self._record(await self._owned(db, consent_id, principal_id))

    async def list(self, scope: MemoryScope, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self.authorize_scope(db, scope, principal_id)
            rows = await (await db.execute("SELECT * FROM consent_records WHERE principal_id=? AND purpose='memory' AND scope=? ORDER BY id", (principal_id, scope.key))).fetchall()
            return tuple(self._record(r) for r in rows)

    async def decide(self, consent_id: str, action: Literal['granted', 'denied', 'revoked', 'expired'], *, principal_id: str):
        allowed = {'requested': {'granted', 'denied'}, 'granted': {'revoked', 'expired'}}
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await self._owned(db, consent_id, principal_id)
                if row['status'] == action:
                    return self._record(row)
                if action not in allowed.get(row['status'], set()):
                    raise ContractViolation('consent_conflict', 'Consent transition is not permitted')
                now = datetime.now(timezone.utc).isoformat()
                await db.execute('UPDATE consent_records SET status=?,granted_at=COALESCE(granted_at,?),revoked_at=? WHERE id=?',
                    (action, now if action == 'granted' else None, now if action == 'revoked' else None, consent_id))
                if action in {'revoked', 'expired'}:
                    await db.execute("UPDATE memory_entries SET status=? WHERE consent_id=? AND status='active'", (action, consent_id))
                await self.audit(db, f'consent.{action}', principal_id, consent_id, previous_status=row['status'])
                return self._record(await self._owned(db, consent_id, principal_id))
