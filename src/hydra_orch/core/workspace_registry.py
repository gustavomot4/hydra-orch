"""T11: persistent hierarchy and explicitly authorized repository resolution."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union
import uuid

from pydantic import TypeAdapter, ValidationError

from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError
from hydra_orch.core.git_workspace import GitWorkspaceService
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact
from hydra_orch.model import AbsolutePath, ContractViolation, GitSha, RelativePath

logger = logging.getLogger(__name__)
SCOPES = frozenset({"read", "write", "execute", "integrate"})


def _text(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or "\x00" in value:
        raise ContractViolation("registry_invalid", "Expected a nonempty bounded identifier or name")
    return value.strip()


def _scopes(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, str) or not values or not set(values) <= SCOPES:
        raise ContractViolation("authorization_invalid", "Explicit known repository scopes are required")
    return tuple(sorted(set(values)))


class WorkspaceRegistry:
    """Local service; principals are supplied by an authenticated caller, never inferred.

    Organizational ownership allows administration. Repository use always needs
    a separate unrevoked grant, even for the area owner and secondary repositories.
    """

    def __init__(self, store: ExecutionStore, *, allowed_roots: Sequence[Union[str, Path]]):
        self.store = store
        try:
            self.allowed_roots = tuple(self._absolute(root).resolve(strict=True) for root in allowed_roots)
        except OSError:
            raise ContractViolation("workspace_invalid", "Configured allowlist roots must exist") from None
        if not self.allowed_roots or any(not root.is_dir() for root in self.allowed_roots):
            raise ContractViolation("workspace_invalid", "Configure existing root directories explicitly")

    @staticmethod
    def _absolute(value: Union[str, Path]) -> Path:
        try:
            return Path(TypeAdapter(AbsolutePath).validate_python(str(value)))
        except ValidationError:
            logger.warning("Registry rejected a noncanonical or traversal path")
            raise ContractViolation("workspace_invalid", "Expected an absolute path without traversal") from None

    def _canonical_root(self, value: Union[str, Path]) -> Path:
        candidate = self._absolute(value).resolve()
        if not any(candidate == root or root in candidate.parents for root in self.allowed_roots):
            logger.warning("Registry rejected a repository outside the root allowlist")
            raise ContractViolation("authorization_denied", "Repository is outside the root allowlist")
        return GitWorkspaceService.resolve_repo_root(candidate)

    async def _git_identity(self, root: Union[str, Path], branch: str, sha: Optional[str]):
        branch = _text(branch)
        if branch.startswith("-") or any(c.isspace() for c in branch):
            raise ContractViolation("workspace_invalid", "Invalid base branch")
        if sha is not None:
            try:
                TypeAdapter(GitSha).validate_python(sha)
            except ValidationError:
                raise ContractViolation("workspace_invalid", "Invalid base commit SHA") from None
        canonical = await asyncio.to_thread(self._canonical_root, root)
        service = await asyncio.to_thread(GitWorkspaceService, canonical)
        # A named branch must actually exist; an invalid branch never silently becomes HEAD.
        await asyncio.to_thread(service.resolve_commit_sha, branch)
        base = await asyncio.to_thread(service.resolve_commit_sha, sha or branch)
        return canonical, base

    async def _area(self, db, area_id: str, principal_id: str):
        principal_id = _text(principal_id)
        row = await (await db.execute("SELECT * FROM areas WHERE id=?", (area_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Area does not exist")
        if row["owner_principal_id"] != principal_id:
            logger.warning("Registry refused cross-principal area access")
            raise ContractViolation("authorization_denied", "Area is not owned by this principal")
        return row

    async def _workspace(self, db, workspace_id: str, principal_id: str):
        row = await (await db.execute("SELECT * FROM area_workspaces WHERE id=?", (workspace_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Workspace does not exist")
        await self._area(db, row["area_id"], principal_id)
        if row["status"] != "active":
            raise ContractViolation("workspace_archived", "Workspace is archived")
        return row

    async def _project(self, db, project_id: str, principal_id: str):
        row = await (await db.execute("SELECT * FROM projects WHERE id=?", (project_id,))).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Project does not exist")
        if row["workspace_id"] is None:
            raise ContractViolation("authorization_denied", "Legacy project has no organizational ownership")
        workspace = await self._workspace(db, row["workspace_id"], principal_id)
        return row, workspace

    async def _audit(self, db, action: str, principal_id: str, resource_id: str):
        payload = {"event": action, "principal_id": principal_id, "resource_id": resource_id}
        await self.store._record_command_in_tx(db, scope="registry", idempotency_key=uuid.uuid4().hex,
            request_hash=self.store.compute_request_hash(payload), response_payload=redact(payload))

    async def create_area(self, name: str, *, principal_id: str, description: Optional[str] = None):
        principal_id, name = _text(principal_id), _text(name)
        area_id = new_id()
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute("INSERT INTO areas(id,name,description,owner_principal_id) VALUES (?,?,?,?)",
                    (area_id, name, redact(description), principal_id))
                await self._audit(db, "area.created", principal_id, area_id)
            return dict(await self._area(db, area_id, principal_id))

    async def list_areas(self, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            return [dict(r) for r in await (await db.execute(
                "SELECT * FROM areas WHERE owner_principal_id=? ORDER BY id", (_text(principal_id),))).fetchall()]

    async def create_workspace(self, area_id: str, name: str, *, principal_id: str):
        name = _text(name)
        workspace_id = new_id()
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._area(db, area_id, principal_id)
                await db.execute("INSERT INTO area_workspaces(id,area_id,name) VALUES (?,?,?)", (workspace_id, area_id, name))
                await self._audit(db, "workspace.created", principal_id, workspace_id)
            return dict(await self._workspace(db, workspace_id, principal_id))

    async def list_workspaces(self, area_id: str, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._area(db, area_id, principal_id)
            return [dict(r) for r in await (await db.execute(
                "SELECT * FROM area_workspaces WHERE area_id=? ORDER BY id", (area_id,))).fetchall()]

    async def archive_workspace(self, workspace_id: str, *, principal_id: str, expected_revision: int):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await self._workspace(db, workspace_id, principal_id)
                if row["revision"] != expected_revision:
                    raise OptimisticLockError("Workspace revision changed")
                await db.execute("UPDATE area_workspaces SET status='archived',revision=revision+1,updated_at=datetime('now') WHERE id=?", (workspace_id,))
                await self._audit(db, "workspace.archived", principal_id, workspace_id)

    async def create_project(self, workspace_id: str, name: str, canonical_root: Union[str, Path], *,
                             principal_id: str, base_branch: str = "main", base_sha: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None):
        name = _text(name)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._workspace(db, workspace_id, principal_id)
                root, sha = await self._git_identity(canonical_root, base_branch, base_sha)
                project_id = new_id()
                await db.execute("""INSERT INTO projects
                    (id,canonical_root,name,workspace_id,metadata_json,base_branch,base_sha)
                    VALUES (?,?,?,?,?,?,?)""",
                    (project_id, str(root), name, workspace_id, json.dumps(redact(metadata or {}), sort_keys=True), base_branch, sha))
                await self._audit(db, "project.created", principal_id, project_id)
            return dict((await self._project(db, project_id, principal_id))[0])

    async def list_projects(self, workspace_id: str, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._workspace(db, workspace_id, principal_id)
            return [dict(r) for r in await (await db.execute(
                "SELECT * FROM projects WHERE workspace_id=? ORDER BY id", (workspace_id,))).fetchall()]

    async def adopt_legacy_project(self, project_id: str, workspace_id: str, *, principal_id: str,
                                   expected_revision: int, base_branch: str = "main"):
        """Explicitly attach an unowned M1 project, without granting repository use."""
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._workspace(db, workspace_id, principal_id)
                row = await (await db.execute("SELECT * FROM projects WHERE id=?", (project_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", "Project does not exist")
                if row["workspace_id"] is not None:
                    raise ContractViolation("registry_conflict", "Only unowned legacy projects may be adopted")
                if row["revision"] != expected_revision:
                    raise OptimisticLockError("Project revision changed")
                root, sha = await self._git_identity(row["canonical_root"], base_branch, None)
                await db.execute("""UPDATE projects SET workspace_id=?,base_branch=?,base_sha=?,
                    revision=revision+1,updated_at=datetime('now') WHERE id=?""",
                    (workspace_id, base_branch, sha, project_id))
                await self._audit(db, "project.adopted", principal_id, project_id)
            return dict((await self._project(db, project_id, principal_id))[0])

    async def register_repository(self, project_id: str, root_canonical: Union[str, Path], *,
                                  principal_id: str, authorized_principal_id: str, scopes: Sequence[str],
                                  allowed_paths: Sequence[str], base_branch: str = "main", base_sha: Optional[str] = None):
        grant_scopes, grantee = _scopes(scopes), _text(authorized_principal_id)
        if isinstance(allowed_paths, str) or not allowed_paths:
            raise ContractViolation("scope_violation", "Explicit repository file scope is required")
        try:
            patterns = tuple(TypeAdapter(RelativePath).validate_python(p) for p in allowed_paths)
        except ValidationError:
            raise ContractViolation("scope_violation", "File scopes must be relative without traversal") from None
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                _, workspace = await self._project(db, project_id, principal_id)
                root, sha = await self._git_identity(root_canonical, base_branch, base_sha)
                repository_id, authorization_id = new_id(), new_id()
                await db.execute("""INSERT INTO authorizations(id,area_id,resource_ref,principal_id,scopes_json)
                    VALUES (?,?,?,?,?)""", (authorization_id, workspace["area_id"], f"repository:{repository_id}", grantee, json.dumps(grant_scopes)))
                await db.execute("""INSERT INTO repositories
                    (id,project_id,root_canonical,base_branch,base_sha,allowed_paths_json,authorization_id)
                    VALUES (?,?,?,?,?,?,?)""", (repository_id, project_id, str(root), base_branch, sha, json.dumps(patterns), authorization_id))
                await self._audit(db, "repository.registered", principal_id, repository_id)
            return dict(await (await db.execute("SELECT * FROM repositories WHERE id=?", (repository_id,))).fetchone())

    async def list_repositories(self, project_id: str, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            await self._project(db, project_id, principal_id)
            return [dict(r) for r in await (await db.execute(
                "SELECT * FROM repositories WHERE project_id=? ORDER BY id", (project_id,))).fetchall()]

    async def grant_repository(self, repository_id: str, *, principal_id: str,
                               authorized_principal_id: str, scopes: Sequence[str]):
        grantee, grant_scopes = _text(authorized_principal_id), _scopes(scopes)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                repo = await (await db.execute("SELECT * FROM repositories WHERE id=?", (repository_id,))).fetchone()
                if repo is None:
                    raise ContractViolation("resource_not_found", "Repository does not exist")
                _, workspace = await self._project(db, repo["project_id"], principal_id)
                authorization_id = new_id()
                await db.execute("INSERT INTO authorizations(id,area_id,resource_ref,principal_id,scopes_json) VALUES (?,?,?,?,?)",
                    (authorization_id, workspace["area_id"], f"repository:{repository_id}", grantee, json.dumps(grant_scopes)))
                await self._audit(db, "authorization.granted", principal_id, authorization_id)
        return authorization_id

    async def get_authorization(self, repository_id: str, *, principal_id: str, scope: str = "read"):
        _scopes((scope,))
        await self.store.initialize()
        async with self.store._connect() as db:
            # Reading grant state and workspace state together avoids stale permission caches.
            rows = await (await db.execute("""SELECT a.* FROM authorizations a
                JOIN repositories r ON a.resource_ref = 'repository:' || r.id
                JOIN projects p ON p.id=r.project_id
                JOIN area_workspaces w ON w.id=p.workspace_id AND w.area_id=a.area_id
                WHERE r.id=? AND a.principal_id=? AND a.revoked_at IS NULL AND w.status='active'
                ORDER BY a.id""", (repository_id, _text(principal_id)))).fetchall()
            return next((dict(r) for r in rows if scope in json.loads(r["scopes_json"])), None)

    async def revoke_authorization(self, authorization_id: str, *, principal_id: str):
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM authorizations WHERE id=?", (authorization_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", "Authorization does not exist")
                await self._area(db, row["area_id"], principal_id)
                await db.execute("UPDATE authorizations SET revoked_at=COALESCE(revoked_at,datetime('now')) WHERE id=?", (authorization_id,))
                await self._audit(db, "authorization.revoked", principal_id, authorization_id)

    async def resolve_repository(self, repository_id: str, *, principal_id: str, scope: str = "read"):
        if await self.get_authorization(repository_id, principal_id=principal_id, scope=scope) is None:
            logger.warning("Registry refused repository use without a current scoped grant")
            raise ContractViolation("authorization_denied", "No current grant for repository and scope")
        async with self.store._connect() as db:
            row = dict(await (await db.execute("SELECT * FROM repositories WHERE id=?", (repository_id,))).fetchone())
        root, _ = await self._git_identity(row["root_canonical"], row["base_branch"], row["base_sha"])
        if os.path.normcase(str(root)) != os.path.normcase(row["root_canonical"]):
            raise ContractViolation("workspace_invalid", "Registered repository root was redirected")
        # Recheck after filesystem/Git inspection; revocation during inspection wins.
        if await self.get_authorization(repository_id, principal_id=principal_id, scope=scope) is None:
            raise ContractViolation("authorization_denied", "Repository grant was revoked")
        return row

    async def resolve_canonical_root(self, project_id: str, *, principal_id: str, repository_id: Optional[str] = None):
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("""SELECT r.id FROM repositories r JOIN projects p ON p.id=r.project_id
                WHERE p.id=? AND (? IS NULL AND r.root_canonical=p.canonical_root OR r.id=?)""",
                (project_id, repository_id, repository_id))).fetchone()
        if row is None:
            raise ContractViolation("authorization_denied", "Project repository has no explicit registration")
        return (await self.resolve_repository(row["id"], principal_id=principal_id))["root_canonical"]

    async def resolve_path(self, repository_id: str, relative_path: str, *, principal_id: str, scope: str = "read"):
        try:
            relative = TypeAdapter(RelativePath).validate_python(relative_path)
        except ValidationError:
            raise ContractViolation("scope_violation", "Expected a relative path without traversal") from None
        repo = await self.resolve_repository(repository_id, principal_id=principal_id, scope=scope)
        root = Path(repo["root_canonical"])
        candidate = (root / relative).resolve()
        if root not in candidate.parents or not any(fnmatch.fnmatchcase(relative, p) for p in json.loads(repo["allowed_paths_json"])):
            logger.warning("Registry refused file scope or symlink escape")
            raise ContractViolation("scope_violation", "Path escapes the repository or its declared file scope")
        return candidate
