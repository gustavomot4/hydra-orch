"""T11: persistent hierarchy and explicitly authorized repository resolution."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import uuid

from pydantic import TypeAdapter, ValidationError

from hydra_orch.core.checkpointer import ExecutionStore, OptimisticLockError
from hydra_orch.core.git_workspace import (
    GitWorkspaceService,
    is_link_or_junction,
    win_long_path,
)
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


def _matches_allowed_scope(rel_posix: str, patterns: Sequence[str]) -> bool:
    norm_path = rel_posix.replace("\\", "/").strip("/")
    check_path = norm_path.casefold() if os.name == "nt" else norm_path
    for raw_pat in patterns:
        pat = raw_pat.replace("\\", "/").strip("/")
        if not pat:
            continue
        if os.name == "nt":
            pat = pat.casefold()
        if pat in {"**/*", "**", "*"}:
            return True
        if fnmatch.fnmatchcase(check_path, pat):
            return True
        if pat.endswith("/**"):
            prefix = pat[:-3].rstrip("/")
            if check_path == prefix or check_path.startswith(f"{prefix}/"):
                return True
    return False


class WorkspaceRegistry:
    """Local service; principals are supplied by an authenticated caller, never inferred.

    Organizational ownership allows administration. Repository use always needs
    a separate unrevoked grant, even for the area owner and secondary repositories.
    """

    def __init__(self, store: ExecutionStore, *, allowed_roots: Sequence[Union[str, Path]]):
        self.store = store
        resolved_roots = []
        for root in allowed_roots:
            abs_root = self._absolute(root)
            if is_link_or_junction(abs_root):
                raise ContractViolation("workspace_invalid", "Configured allowlist roots must not be symlinks or junctions")
            try:
                resolved_roots.append(abs_root.resolve(strict=True))
            except OSError:
                raise ContractViolation("workspace_invalid", "Configured allowlist roots must exist") from None
        self.allowed_roots = tuple(resolved_roots)
        if not self.allowed_roots or any(not win_long_path(root).is_dir() for root in self.allowed_roots):
            raise ContractViolation("workspace_invalid", "Configure existing root directories explicitly")

    @staticmethod
    def _absolute(value: Union[str, Path]) -> Path:
        try:
            return Path(TypeAdapter(AbsolutePath).validate_python(str(value)))
        except ValidationError:
            logger.warning("Registry rejected a noncanonical or traversal path")
            raise ContractViolation("workspace_invalid", "Expected an absolute path without traversal") from None

    def _canonical_root(self, value: Union[str, Path]) -> Path:
        raw_path = self._absolute(value)
        if is_link_or_junction(raw_path):
            logger.warning("Registry rejected a symlink or junction repository root")
            raise ContractViolation("authorization_denied", "Repository root cannot be a symlink or junction")
        candidate = raw_path.resolve()
        matched_roots = [root for root in self.allowed_roots if candidate == root or root in candidate.parents]
        if not matched_roots:
            logger.warning("Registry rejected a repository outside the root allowlist")
            raise ContractViolation("authorization_denied", "Repository is outside the root allowlist")
        for allowed_root in matched_roots:
            try:
                rel_parts = raw_path.relative_to(allowed_root).parts
            except ValueError:
                continue
            cursor = allowed_root
            for part in rel_parts:
                cursor = cursor / part
                if is_link_or_junction(cursor):
                    logger.warning("Registry rejected a repository traversing a symlink or junction")
                    raise ContractViolation("authorization_denied", "Repository path traverses a symlink or junction")
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

    async def update_workspace(
        self,
        workspace_id: str,
        name: str,
        *,
        principal_id: str,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        clean_name = _text(name)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await self._workspace(db, workspace_id, principal_id)
                if expected_revision is not None and row["revision"] != expected_revision:
                    raise OptimisticLockError("Workspace revision changed")
                await db.execute(
                    "UPDATE area_workspaces SET name=?, revision=revision+1, updated_at=datetime('now') WHERE id=?",
                    (clean_name, workspace_id),
                )
                await self._audit(db, "workspace.updated", principal_id, workspace_id)
                updated = await (
                    await db.execute("SELECT * FROM area_workspaces WHERE id=?", (workspace_id,))
                ).fetchone()
                return dict(updated)

    async def delete_workspace(
        self,
        workspace_id: str,
        *,
        principal_id: str,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._area_check_for_delete(db, workspace_id, principal_id, expected_revision)
                linked = await (
                    await db.execute("SELECT 1 FROM projects WHERE workspace_id=? LIMIT 1", (workspace_id,))
                ).fetchone()
                if linked is not None:
                    raise ContractViolation(
                        "registry_conflict",
                        f"Workspace '{workspace_id}' still has linked projects",
                    )
                await db.execute("DELETE FROM area_workspaces WHERE id=?", (workspace_id,))
                await self._audit(db, "workspace.deleted", principal_id, workspace_id)
                return {"deleted": True, "workspace_id": workspace_id}

    async def _area_check_for_delete(
        self,
        db: Any,
        workspace_id: str,
        principal_id: str,
        expected_revision: Optional[int],
    ) -> None:
        row = await (
            await db.execute("SELECT * FROM area_workspaces WHERE id=?", (_text(workspace_id),))
        ).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", "Workspace does not exist")
        await self._area(db, row["area_id"], principal_id)
        if expected_revision is not None and row["revision"] != expected_revision:
            raise OptimisticLockError("Workspace revision changed")

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
            proj, _ = await self._project(db, project_id, principal_id)
            meta = json.loads(proj["metadata_json"]) if proj["metadata_json"] else {}
            repo_meta_map = meta.get("repository_meta", {}) if isinstance(meta, dict) else {}
            rows = await (await db.execute(
                "SELECT * FROM repositories WHERE project_id=? ORDER BY id", (project_id,))).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                rm = repo_meta_map.get(d["id"], {}) if isinstance(repo_meta_map, dict) else {}
                if isinstance(rm, dict):
                    if "name" in rm:
                        d["name"] = rm["name"]
                    if "forbidden_paths" in rm:
                        d["forbidden_paths"] = list(rm["forbidden_paths"])
                out.append(d)
            return out

    async def update_repository(
        self,
        workspace_id: str = "",
        *,
        repository_id: Optional[str] = None,
        name: Optional[str] = None,
        allowed_paths: Optional[List[str]] = None,
        forbidden_paths: Optional[List[str]] = None,
        principal_id: str = "operator",
    ) -> Dict[str, Any]:
        target_id = _text(workspace_id or repository_id or "")
        clean_name = _text(name) if name is not None else None
        validated_allowed: Optional[tuple[str, ...]] = None
        if allowed_paths is not None:
            if isinstance(allowed_paths, str) or not allowed_paths:
                raise ContractViolation("scope_violation", "Explicit repository file scope is required")
            try:
                validated_allowed = tuple(TypeAdapter(RelativePath).validate_python(p) for p in allowed_paths)
            except ValidationError:
                raise ContractViolation("scope_violation", "File scopes must be relative without traversal") from None

        validated_forbidden: Optional[tuple[str, ...]] = None
        if forbidden_paths is not None:
            if isinstance(forbidden_paths, str):
                raise ContractViolation("scope_violation", "Forbidden file scopes must be a sequence of relative paths")
            try:
                validated_forbidden = tuple(TypeAdapter(RelativePath).validate_python(p) for p in forbidden_paths)
            except ValidationError:
                raise ContractViolation("scope_violation", "Forbidden scopes must be relative without traversal") from None

        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                repo = await (await db.execute("SELECT * FROM repositories WHERE id=?", (target_id,))).fetchone()
                if repo is None:
                    repo = await (
                        await db.execute("SELECT * FROM repositories WHERE project_id=? ORDER BY id LIMIT 1", (target_id,))
                    ).fetchone()
                if repo is not None:
                    repo_id = repo["id"]
                    proj, _ = await self._project(db, repo["project_id"], principal_id)
                    canonical_checked = await asyncio.to_thread(self._canonical_root, repo["root_canonical"])
                    if os.path.normcase(str(canonical_checked)) != os.path.normcase(repo["root_canonical"]):
                        raise ContractViolation("workspace_invalid", "Registered repository root was redirected")

                    meta = json.loads(proj["metadata_json"]) if proj["metadata_json"] else {}
                    if not isinstance(meta, dict):
                        meta = {}
                    repo_meta_map = dict(meta.get("repository_meta") or {})
                    cur_rm = dict(repo_meta_map.get(repo_id) or {})
                    if clean_name is not None:
                        cur_rm["name"] = clean_name
                    if validated_forbidden is not None:
                        cur_rm["forbidden_paths"] = list(validated_forbidden)
                    repo_meta_map[repo_id] = cur_rm
                    meta["repository_meta"] = repo_meta_map

                    is_primary = os.path.normcase(repo["root_canonical"]) == os.path.normcase(proj["canonical_root"])
                    if is_primary and validated_forbidden is not None:
                        meta["forbidden_paths"] = list(validated_forbidden)

                    new_proj_name = clean_name if (clean_name is not None and is_primary) else proj["name"]
                    await db.execute(
                        """UPDATE projects
                           SET name=?, metadata_json=?, revision=revision+1, updated_at=datetime('now')
                           WHERE id=?""",
                        (new_proj_name, json.dumps(redact(meta), sort_keys=True), proj["id"]),
                    )

                    new_allowed_json = (
                        json.dumps(validated_allowed) if validated_allowed is not None else repo["allowed_paths_json"]
                    )
                    await db.execute(
                        """UPDATE repositories
                           SET allowed_paths_json=?, revision=revision+1, updated_at=datetime('now')
                           WHERE id=?""",
                        (new_allowed_json, repo_id),
                    )
                    await self._audit(db, "repository.updated", principal_id, repo_id)
                    updated = dict(await (await db.execute("SELECT * FROM repositories WHERE id=?", (repo_id,))).fetchone())
                    updated["name"] = cur_rm.get("name", new_proj_name)
                    updated["allowed_paths"] = json.loads(updated["allowed_paths_json"])
                    updated["forbidden_paths"] = list(cur_rm.get("forbidden_paths", ()))
                    return updated

                proj_only = await (await db.execute("SELECT * FROM projects WHERE id=?", (target_id,))).fetchone()
                if proj_only is not None:
                    if proj_only["workspace_id"] is not None:
                        await self._project(db, target_id, principal_id)
                    else:
                        _text(principal_id)
                    await asyncio.to_thread(self._canonical_root, proj_only["canonical_root"])
                    meta = json.loads(proj_only["metadata_json"]) if proj_only["metadata_json"] else {}
                    if not isinstance(meta, dict):
                        meta = {}
                    if validated_allowed is not None:
                        meta["allowed_paths"] = list(validated_allowed)
                    if validated_forbidden is not None:
                        meta["forbidden_paths"] = list(validated_forbidden)
                    new_name = clean_name if clean_name is not None else proj_only["name"]
                    await db.execute(
                        """UPDATE projects
                           SET name=?, metadata_json=?, revision=revision+1, updated_at=datetime('now')
                           WHERE id=?""",
                        (new_name, json.dumps(redact(meta), sort_keys=True), target_id),
                    )
                    await self._audit(db, "repository.updated", principal_id, target_id)
                    updated_proj = dict(await (await db.execute("SELECT * FROM projects WHERE id=?", (target_id,))).fetchone())
                    updated_proj["allowed_paths"] = list(meta.get("allowed_paths", ()))
                    updated_proj["forbidden_paths"] = list(meta.get("forbidden_paths", ()))
                    return updated_proj

                ws_only = await (await db.execute("SELECT * FROM area_workspaces WHERE id=?", (target_id,))).fetchone()
                if ws_only is not None:
                    await self._workspace(db, target_id, principal_id)
                    new_ws_name = clean_name if clean_name is not None else ws_only["name"]
                    await db.execute(
                        "UPDATE area_workspaces SET name=?, revision=revision+1, updated_at=datetime('now') WHERE id=?",
                        (new_ws_name, target_id),
                    )
                    await self._audit(db, "workspace.updated", principal_id, target_id)
                    return dict(await self._workspace(db, target_id, principal_id))

                raise ContractViolation("resource_not_found", "Repository does not exist")

    async def delete_repository(
        self,
        workspace_id: str = "",
        *,
        repository_id: Optional[str] = None,
        principal_id: str = "operator",
    ) -> Dict[str, Any]:
        target_id = _text(workspace_id or repository_id or "")
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                repo = await (await db.execute("SELECT * FROM repositories WHERE id=?", (target_id,))).fetchone()
                if repo is None:
                    repo = await (
                        await db.execute("SELECT * FROM repositories WHERE project_id=? ORDER BY id LIMIT 1", (target_id,))
                    ).fetchone()
                if repo is not None:
                    repo_id = repo["id"]
                    proj, _ = await self._project(db, repo["project_id"], principal_id)
                    meta = json.loads(proj["metadata_json"]) if proj["metadata_json"] else {}
                    if isinstance(meta, dict) and isinstance(meta.get("repository_meta"), dict):
                        rm_map = dict(meta["repository_meta"])
                        if repo_id in rm_map:
                            rm_map.pop(repo_id, None)
                            meta["repository_meta"] = rm_map
                            await db.execute(
                                "UPDATE projects SET metadata_json=?, updated_at=datetime('now') WHERE id=?",
                                (json.dumps(redact(meta), sort_keys=True), proj["id"]),
                            )
                    await db.execute("DELETE FROM repositories WHERE id=?", (repo_id,))
                    await db.execute(
                        "UPDATE authorizations SET revoked_at=COALESCE(revoked_at,datetime('now')) WHERE resource_ref=?",
                        (f"repository:{repo_id}",),
                    )
                    await self._audit(db, "repository.deleted", principal_id, repo_id)
                    return {
                        "id": repo_id,
                        "repository_id": repo_id,
                        "project_id": repo["project_id"],
                        "deleted": True,
                    }

                proj_only = await (await db.execute("SELECT * FROM projects WHERE id=?", (target_id,))).fetchone()
                if proj_only is not None:
                    if proj_only["workspace_id"] is not None:
                        await self._project(db, target_id, principal_id)
                    else:
                        _text(principal_id)
                    has_runs = await (await db.execute("SELECT 1 FROM runs WHERE project_id=? LIMIT 1", (target_id,))).fetchone()
                    has_convs = None
                    has_conv_tbl = await (
                        await db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'")
                    ).fetchone()
                    if has_conv_tbl is not None:
                        has_convs = await (
                            await db.execute("SELECT 1 FROM conversations WHERE project_id=? LIMIT 1", (target_id,))
                        ).fetchone()
                    if has_runs is not None or has_convs is not None:
                        raise ContractViolation(
                            "resource_in_use",
                            "Cannot delete project while runs or conversations reference it",
                        )
                    await db.execute("DELETE FROM projects WHERE id=?", (target_id,))
                    await self._audit(db, "repository.deleted", principal_id, target_id)
                    return {"id": target_id, "project_id": target_id, "deleted": True}

                raise ContractViolation("resource_not_found", "Repository does not exist")

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
        raw_root = Path(repo["root_canonical"])
        if is_link_or_junction(raw_root):
            logger.warning("Registry refused redirected repository root")
            raise ContractViolation("scope_violation", "Path escapes the repository or its declared file scope")
        root = raw_root.resolve()

        cursor = root
        for part in Path(relative).parts:
            cursor = cursor / part
            if is_link_or_junction(cursor):
                logger.warning("Registry refused symlink or junction component in path")
                raise ContractViolation("scope_violation", "Path escapes the repository or its declared file scope")

        candidate = (root / relative).resolve(strict=False)
        if candidate == root or not candidate.is_relative_to(root):
            logger.warning("Registry refused file scope or symlink escape")
            raise ContractViolation("scope_violation", "Path escapes the repository or its declared file scope")

        resolved_rel = candidate.relative_to(root).as_posix()
        allowed_patterns = json.loads(repo["allowed_paths_json"])
        if not (
            _matches_allowed_scope(relative, allowed_patterns)
            and _matches_allowed_scope(resolved_rel, allowed_patterns)
        ):
            logger.warning("Registry refused file scope or symlink escape")
            raise ContractViolation("scope_violation", "Path escapes the repository or its declared file scope")

        async with self.store._connect() as db:
            proj_row = await (await db.execute("SELECT metadata_json FROM projects WHERE id=?", (repo["project_id"],))).fetchone()
        if proj_row is not None and proj_row["metadata_json"]:
            meta = json.loads(proj_row["metadata_json"])
            if isinstance(meta, dict):
                rm = (meta.get("repository_meta") or {}).get(repository_id) or {}
                forbidden_patterns = rm.get("forbidden_paths") or ()
                if forbidden_patterns and (
                    _matches_allowed_scope(relative, forbidden_patterns)
                    or _matches_allowed_scope(resolved_rel, forbidden_patterns)
                ):
                    logger.warning("Registry refused forbidden path in repository scope")
                    raise ContractViolation("scope_violation", "Path escapes the repository or its declared file scope")
        return candidate
