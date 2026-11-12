"""T20: isolated extension host with versioned manifests, consent, revocation, quarantine, and rollback."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Literal, Mapping, Optional, Sequence, Union

from pydantic import Field, model_validator

from hydra_orch.bridge.extension_runner import ExtensionAnomalyError, ExtensionPolicy, ExtensionRunner
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.consent import ConsentService, MemoryScope
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.core.skill_registry import SecretBundle, SecretResolver, validate_permission
from hydra_orch.model import ContractViolation, ExecutionModel, Identifier, NonEmpty, Sha256, UtcTimestamp

EXTENSION_API_VERSION = "1.0"
_SUPPORTED_API_MAJOR = 1
_SEMVER_PREFIX_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

InstallStatus = Literal[
    "proposed",
    "consented",
    "installed",
    "active",
    "disabled",
    "quarantined",
    "revoked",
    "rolled_back",
]

_INSTALL_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"consented", "revoked"}),
    "consented": frozenset({"installed", "revoked"}),
    "installed": frozenset({"active", "revoked"}),
    "active": frozenset({"disabled", "quarantined", "revoked", "rolled_back"}),
    "disabled": frozenset({"active", "revoked", "rolled_back"}),
    "quarantined": frozenset({"revoked", "rolled_back"}),
    "revoked": frozenset(),
    "rolled_back": frozenset(),
}


def is_compatible_api_version(version: str) -> bool:
    if not isinstance(version, str):
        return False
    match = _SEMVER_PREFIX_RE.fullmatch(version.strip())
    if not match:
        return False
    return int(match.group(1)) == _SUPPORTED_API_MAJOR


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


class ExtensionManifest(ExecutionModel):
    extension_id: Identifier = Field(default_factory=new_id)
    name: NonEmpty
    version: NonEmpty
    entrypoint: NonEmpty
    permissions_required: tuple[str, ...] = ()
    compatible_api_version: NonEmpty = EXTENSION_API_VERSION
    checksum: Sha256
    created_at: Optional[UtcTimestamp] = None

    @model_validator(mode="after")
    def validate_manifest(self):
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError("Extension name must be an identifier without whitespace or traversal")
        if any(c.isspace() or c == "\x00" for c in self.version) or ".." in self.version:
            raise ValueError("Extension version cannot contain whitespace, NUL, or traversal")
        if ".." in Path(self.entrypoint).parts or "\x00" in self.entrypoint:
            raise ValueError("Extension entrypoint cannot contain traversal or NUL")
        for perm in self.permissions_required:
            validate_permission(perm)
        if len(set(self.permissions_required)) != len(self.permissions_required):
            raise ValueError("Extension permissions_required must be unique")
        data = self.model_dump(mode="json")
        data["permissions_required"] = [
            "secret_ref" if isinstance(p, str) and p.startswith("secret:") else p
            for p in data.get("permissions_required", [])
        ]
        if redact(data) != data:
            raise ValueError("Extension manifest cannot embed raw credentials")
        return self


class ExtensionInstall(ExecutionModel):
    install_id: Identifier
    extension_manifest_id: Identifier
    status: InstallStatus
    consent_record_id: Identifier
    installed_at: Optional[UtcTimestamp] = None
    revoked_at: Optional[UtcTimestamp] = None


class CallResult(ExecutionModel):
    call_id: Identifier
    install_id: Identifier
    status: Literal["succeeded", "failed", "blocked", "quarantined"]
    output: Any = None
    error_code: Optional[str] = None
    quarantined: bool = False


class ExtensionHost:
    """Lifecycle manager and isolated IPC broker for extensions and plugins."""

    def __init__(
        self,
        store: ExecutionStore,
        consents: ConsentService,
        *,
        allowed_roots: Sequence[Union[str, Path]],
        runtime_dir: Optional[Union[str, Path]] = None,
        secret_resolver: Optional[SecretResolver] = None,
        timeout_seconds: float = 10.0,
        max_message_bytes: int = 1024 * 1024,
    ):
        if consents.store is not store:
            raise ValueError("ExtensionHost and ConsentService must share the canonical store")
        if secret_resolver is not None and secret_resolver.registry.store is not store:
            raise ValueError("ExtensionHost and SecretResolver must share the canonical store")
        if not allowed_roots:
            raise ValueError("ExtensionHost requires explicit allowed_roots")

        resolved_roots: list[Path] = []
        for item in allowed_roots:
            p = Path(item)
            if not p.is_absolute() or ".." in p.parts:
                raise ValueError("Extension allowed_roots must be absolute without traversal")
            canon = p.resolve(strict=True)
            if not canon.is_dir():
                raise ValueError("Extension allowed_roots must be existing directories")
            resolved_roots.append(canon)

        self.store = store
        self.consents = consents
        self.allowed_roots = tuple(dict.fromkeys(resolved_roots))
        if runtime_dir is not None:
            self.runtime_dir = Path(runtime_dir).resolve()
        else:
            db_p = Path(str(store.db_path))
            base = db_p.resolve().parent if str(store.db_path) != ":memory:" else self.allowed_roots[0]
            self.runtime_dir = base / ".extensions_runtime"
        self.secret_resolver = secret_resolver
        self.timeout_seconds = float(timeout_seconds)
        self.max_message_bytes = int(max_message_bytes)
        self._runners: dict[str, ExtensionRunner] = {}

    @staticmethod
    def _authorize_principal(principal_id: str) -> None:
        if not principal_id or redact_text(principal_id) != principal_id:
            raise ContractViolation("authorization_denied", "Valid authenticated principal_id is required")

    def _forbidden_db_paths(self) -> tuple[Path, ...]:
        db_str = str(self.store.db_path)
        if db_str == ":memory:":
            return ()
        db_file = Path(db_str).resolve()
        return (
            db_file,
            Path(f"{db_file}-wal"),
            Path(f"{db_file}-shm"),
            Path(f"{db_file}-journal"),
        )

    def _resolve_entrypoint(self, entrypoint: str, expected_checksum: str) -> Path:
        raw = Path(entrypoint)
        if ".." in raw.parts or "\x00" in entrypoint:
            raise ContractViolation("extension_invalid_entrypoint", "Entrypoint cannot contain traversal")
        candidates: list[Path]
        if raw.is_absolute():
            candidates = [raw]
        else:
            candidates = [root / raw for root in self.allowed_roots]

        chosen: Optional[Path] = None
        for cand in candidates:
            if cand.exists() or cand.is_symlink():
                chosen = cand
                break
        if chosen is None:
            raise ContractViolation("extension_entrypoint_missing", f"Extension entrypoint '{entrypoint}' not found")

        if chosen.is_symlink():
            target = chosen.resolve(strict=True)
            if not any(self._is_within(target, root) for root in self.allowed_roots):
                raise ContractViolation("extension_invalid_entrypoint", "Symlink entrypoint escapes allowed_roots")
            resolved = target
        else:
            resolved = chosen.resolve(strict=True)

        if not any(self._is_within(resolved, root) for root in self.allowed_roots):
            raise ContractViolation("extension_invalid_entrypoint", "Entrypoint is outside allowed_roots")
        if not resolved.is_file():
            raise ContractViolation("extension_invalid_entrypoint", "Entrypoint must be a regular file")

        actual_checksum = _file_sha256(resolved)
        if actual_checksum != expected_checksum:
            raise ContractViolation(
                "extension_checksum_mismatch",
                f"Extension checksum mismatch: expected {expected_checksum}, got {actual_checksum}",
            )
        return resolved

    @staticmethod
    def _is_within(target: Path, root: Path) -> bool:
        t_norm = os.path.normcase(str(target))
        r_norm = os.path.normcase(str(root))
        if t_norm == r_norm:
            return True
        if not r_norm.endswith(os.sep):
            r_norm += os.sep
        return t_norm.startswith(r_norm)

    async def _audit(self, db, event: str, principal_id: str, resource_id: str, **details: Any) -> None:
        payload = {"event": event, "principal_id": principal_id, "resource_id": resource_id, **details}
        await self.store._record_command_in_tx(
            db,
            scope="extension",
            idempotency_key=new_id(),
            request_hash=self.store.compute_request_hash(payload),
            response_payload=payload,
        )

    @staticmethod
    def _manifest_from_row(row) -> ExtensionManifest:
        return ExtensionManifest(
            extension_id=row["id"],
            name=row["name"],
            version=row["version"],
            entrypoint=row["entrypoint"],
            permissions_required=tuple(json.loads(row["permissions_required_json"])),
            compatible_api_version=row["compatible_api_version"],
            checksum=row["checksum"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _install_from_row(row) -> ExtensionInstall:
        return ExtensionInstall(
            install_id=row["id"],
            extension_manifest_id=row["extension_manifest_id"],
            status=row["status"],
            consent_record_id=row["consent_record_id"],
            installed_at=row["installed_at"],
            revoked_at=row["revoked_at"],
        )

    async def _require_extension_consent(self, db, consent_id: str, manifest: ExtensionManifest, principal_id: str):
        row = await (await db.execute("SELECT * FROM consent_records WHERE id=?", (consent_id,))).fetchone()
        if row is None or row["status"] != "granted" or row["revoked_at"] is not None:
            raise ContractViolation("consent_required", "An active consent is required for extension")
        if row["principal_id"] != principal_id or row["purpose"] != "extension":
            raise ContractViolation("consent_required", "Consent principal and purpose must match extension")
        allowed_scopes = {
            MemoryScope(scope_type="extension", scope_id=manifest.name).key,
            MemoryScope(scope_type="extension", scope_id=manifest.extension_id).key,
        }
        if row["scope"] not in allowed_scopes:
            raise ContractViolation("consent_required", "Consent scope does not cover this extension")
        return row

    async def _validate_secret_refs(self, db, permissions: Sequence[str]) -> None:
        for perm in permissions:
            if perm.startswith("secret:"):
                sec_id = perm[7:]
                row = await (await db.execute("SELECT id FROM secret_refs WHERE id=?", (sec_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"SecretRef '{sec_id}' does not exist")
                revoked = await (
                    await db.execute(
                        "SELECT 1 FROM commands WHERE scope='skill_registry' "
                        "AND json_extract(response_json,'$.event')='secret_ref.revoked' "
                        "AND json_extract(response_json,'$.resource_id')=? LIMIT 1",
                        (sec_id,),
                    )
                ).fetchone()
                if revoked is not None:
                    raise ContractViolation("component_revoked", f"SecretRef '{sec_id}' is revoked")

    async def register_manifest(self, manifest: ExtensionManifest, *, principal_id: str) -> ExtensionManifest:
        self._authorize_principal(principal_id)
        if not is_compatible_api_version(manifest.compatible_api_version):
            raise ContractViolation(
                "extension_incompatible_api",
                f"Extension API version '{manifest.compatible_api_version}' is incompatible with '{EXTENSION_API_VERSION}'",
            )
        self._resolve_entrypoint(manifest.entrypoint, manifest.checksum)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._validate_secret_refs(db, manifest.permissions_required)
                existing = await (
                    await db.execute(
                        "SELECT * FROM extension_manifests WHERE name=? AND version=?",
                        (manifest.name, manifest.version),
                    )
                ).fetchone()
                if existing is not None:
                    loaded = self._manifest_from_row(existing)
                    if (
                        loaded.checksum != manifest.checksum
                        or loaded.compatible_api_version != manifest.compatible_api_version
                        or loaded.permissions_required != manifest.permissions_required
                        or loaded.entrypoint != manifest.entrypoint
                    ):
                        raise ContractViolation(
                            "extension_manifest_conflict",
                            f"Manifest {manifest.name}@{manifest.version} already registered with different definition",
                        )
                    return loaded
                created_at = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    """INSERT INTO extension_manifests(
                           id, name, version, entrypoint, permissions_required_json,
                           compatible_api_version, checksum, created_at
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        manifest.extension_id,
                        manifest.name,
                        manifest.version,
                        manifest.entrypoint,
                        json.dumps(list(manifest.permissions_required)),
                        manifest.compatible_api_version,
                        manifest.checksum,
                        created_at,
                    ),
                )
                await self._audit(
                    db,
                    "extension.manifest_registered",
                    principal_id,
                    manifest.extension_id,
                    name=manifest.name,
                    version=manifest.version,
                    checksum=manifest.checksum,
                )
                return ExtensionManifest.model_validate({**manifest.model_dump(mode="json"), "created_at": created_at})

    async def install(
        self,
        manifest: ExtensionManifest,
        consent_id: str,
        *,
        principal_id: str,
        activate: bool = True,
    ) -> ExtensionInstall:
        self._authorize_principal(principal_id)
        if not is_compatible_api_version(manifest.compatible_api_version):
            raise ContractViolation(
                "extension_incompatible_api",
                f"Extension API version '{manifest.compatible_api_version}' is incompatible with '{EXTENSION_API_VERSION}'",
            )
        self._resolve_entrypoint(manifest.entrypoint, manifest.checksum)
        await self.store.initialize()

        superseded_ids: list[str] = []
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._validate_secret_refs(db, manifest.permissions_required)
                existing_m = await (
                    await db.execute(
                        "SELECT * FROM extension_manifests WHERE name=? AND version=?",
                        (manifest.name, manifest.version),
                    )
                ).fetchone()
                if existing_m is not None:
                    persisted_manifest = self._manifest_from_row(existing_m)
                    if (
                        persisted_manifest.checksum != manifest.checksum
                        or persisted_manifest.compatible_api_version != manifest.compatible_api_version
                        or persisted_manifest.permissions_required != manifest.permissions_required
                        or persisted_manifest.entrypoint != manifest.entrypoint
                    ):
                        raise ContractViolation(
                            "extension_manifest_conflict",
                            f"Manifest {manifest.name}@{manifest.version} already registered with different definition",
                        )
                else:
                    created_at = datetime.now(timezone.utc).isoformat()
                    await db.execute(
                        """INSERT INTO extension_manifests(
                               id, name, version, entrypoint, permissions_required_json,
                               compatible_api_version, checksum, created_at
                           ) VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            manifest.extension_id,
                            manifest.name,
                            manifest.version,
                            manifest.entrypoint,
                            json.dumps(list(manifest.permissions_required)),
                            manifest.compatible_api_version,
                            manifest.checksum,
                            created_at,
                        ),
                    )
                    persisted_manifest = ExtensionManifest.model_validate(
                        {**manifest.model_dump(mode="json"), "created_at": created_at}
                    )

                await self._require_extension_consent(db, consent_id, persisted_manifest, principal_id)

                if activate:
                    prior_active = await (
                        await db.execute(
                            """SELECT ei.id FROM extension_installs ei
                               JOIN extension_manifests em ON em.id = ei.extension_manifest_id
                               WHERE em.name=? AND ei.status='active'""",
                            (persisted_manifest.name,),
                        )
                    ).fetchall()
                    for row in prior_active:
                        superseded_ids.append(row["id"])
                        await db.execute("UPDATE extension_installs SET status='disabled' WHERE id=?", (row["id"],))
                        await self._audit(db, "extension.disabled", principal_id, row["id"], reason="superseded_by_upgrade")

                install_id = new_id()
                now = datetime.now(timezone.utc).isoformat()
                final_status: InstallStatus = "active" if activate else "installed"
                await db.execute(
                    """INSERT INTO extension_installs(
                           id, extension_manifest_id, status, consent_record_id, installed_at
                       ) VALUES (?,?,?,?,?)""",
                    (install_id, persisted_manifest.extension_id, final_status, consent_id, now),
                )
                await self._audit(
                    db,
                    "extension.installed",
                    principal_id,
                    install_id,
                    extension_manifest_id=persisted_manifest.extension_id,
                    status=final_status,
                    checksum=persisted_manifest.checksum,
                )
                row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
                install_obj = self._install_from_row(row)

        for old_id in superseded_ids:
            await self._stop_runner(old_id)
        return install_obj

    async def get_install(self, install_id: str) -> ExtensionInstall:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"ExtensionInstall '{install_id}' does not exist")
            return self._install_from_row(row)

    async def list_installs(self) -> tuple[ExtensionInstall, ...]:
        await self.store.initialize()
        async with self.store._connect() as db:
            rows = await (await db.execute("SELECT * FROM extension_installs ORDER BY id")).fetchall()
            return tuple(self._install_from_row(r) for r in rows)

    async def _stop_runner(self, install_id: str) -> None:
        runner = self._runners.pop(install_id, None)
        if runner is not None:
            await runner.stop()

    def get_running_pid(self, install_id: str) -> Optional[int]:
        runner = self._runners.get(install_id)
        if runner is None or not runner.is_running:
            return None
        return runner.pid

    async def _resolve_secret_bundle(
        self,
        manifest: ExtensionManifest,
        *,
        principal_id: str,
    ) -> Optional[SecretBundle]:
        secret_ids = [p[7:] for p in manifest.permissions_required if p.startswith("secret:")]
        if not secret_ids:
            return None
        if self.secret_resolver is None:
            raise ContractViolation("secret_unavailable", "SecretResolver is required for extensions declaring secret:<id>")
        return await self.secret_resolver.resolve(secret_ids, principal_id=principal_id)

    def _build_policy(self, install_id: str, manifest: ExtensionManifest, entrypoint: Path) -> ExtensionPolicy:
        perms = set(manifest.permissions_required)
        workdir = self.runtime_dir / install_id / "work"
        return ExtensionPolicy(
            entrypoint=entrypoint,
            sandbox_workdir=workdir,
            forbidden_paths=self._forbidden_db_paths(),
            allowed_read_roots=self.allowed_roots if "fs:read" in perms else (),
            allowed_write_roots=self.allowed_roots if "fs:write" in perms else (),
            allow_net_loopback=("net:loopback" in perms or "net:external" in perms),
            allow_net_external=("net:external" in perms),
            allow_spawn=("process:spawn" in perms),
            api_version=manifest.compatible_api_version,
        )

    async def _transition(
        self,
        install_id: str,
        target: InstallStatus,
        *,
        principal_id: str,
        reason: str = "",
    ) -> ExtensionInstall:
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"ExtensionInstall '{install_id}' does not exist")
                current = row["status"]
                if target not in _INSTALL_TRANSITIONS.get(current, frozenset()):
                    raise ContractViolation(
                        "invalid_transition",
                        f"Extension transition '{current}' -> '{target}' is not permitted",
                    )
                now = datetime.now(timezone.utc).isoformat()
                revoked_at = now if target == "revoked" else row["revoked_at"]
                await db.execute(
                    "UPDATE extension_installs SET status=?, revoked_at=? WHERE id=?",
                    (target, revoked_at, install_id),
                )
                await self._audit(
                    db,
                    f"extension.{target}",
                    principal_id,
                    install_id,
                    previous_status=current,
                    reason=redact_text(reason) if reason else None,
                )
                updated = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
                return self._install_from_row(updated)

    async def start(self, install_id: str, *, principal_id: str) -> ExtensionRunner:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            inst_row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
            if inst_row is None:
                raise ContractViolation("resource_not_found", f"ExtensionInstall '{install_id}' does not exist")
            man_row = await (
                await db.execute("SELECT * FROM extension_manifests WHERE id=?", (inst_row["extension_manifest_id"],))
            ).fetchone()
            manifest = self._manifest_from_row(man_row)
            if inst_row["status"] == "revoked":
                raise ContractViolation("extension_revoked", "Revoked extension cannot start")
            if inst_row["status"] == "quarantined":
                raise ContractViolation("extension_quarantined", "Quarantined extension cannot start")
            if inst_row["status"] != "active":
                raise ContractViolation("extension_not_active", f"Extension in status '{inst_row['status']}' cannot start")
            try:
                await self._require_extension_consent(db, inst_row["consent_record_id"], manifest, principal_id)
            except ContractViolation:
                await self._stop_runner(install_id)
                await self._transition(install_id, "revoked", principal_id=principal_id, reason="consent_inactive")
                raise ContractViolation("extension_revoked", "Extension consent is no longer active")
            await self._validate_secret_refs(db, manifest.permissions_required)

        if not is_compatible_api_version(manifest.compatible_api_version):
            raise ContractViolation("extension_incompatible_api", "Extension API version is incompatible")

        try:
            entrypoint = self._resolve_entrypoint(manifest.entrypoint, manifest.checksum)
        except ContractViolation as exc:
            if exc.code in {"extension_checksum_mismatch", "extension_entrypoint_missing", "extension_invalid_entrypoint"}:
                await self._stop_runner(install_id)
                await self._transition(install_id, "quarantined", principal_id=principal_id, reason=exc.code)
            raise

        runner = self._runners.get(install_id)
        if runner is not None and runner.is_running:
            return runner

        bundle = await self._resolve_secret_bundle(manifest, principal_id=principal_id)
        policy = self._build_policy(install_id, manifest, entrypoint)
        runner = ExtensionRunner(
            policy,
            allowed_env=bundle.as_allowed_env() if bundle is not None else None,
            timeout_seconds=self.timeout_seconds,
            max_message_bytes=self.max_message_bytes,
        )
        try:
            await runner.start()
        except ExtensionAnomalyError as exc:
            await runner.stop()
            await self._transition(install_id, "quarantined", principal_id=principal_id, reason=str(exc))
            raise ContractViolation("extension_quarantined", str(exc)) from exc
        self._runners[install_id] = runner
        return runner

    async def execute(
        self,
        install_id: str,
        method: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        principal_id: str,
        required_permissions: Sequence[str] = (),
    ) -> CallResult:
        self._authorize_principal(principal_id)
        if params is not None and redact(dict(params)) != dict(params):
            raise ContractViolation("secret_in_payload", "Extension call parameters cannot embed raw credentials")

        await self.store.initialize()
        async with self.store._connect() as db:
            inst_row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
            if inst_row is None:
                raise ContractViolation("resource_not_found", f"ExtensionInstall '{install_id}' does not exist")
            status = inst_row["status"]
            if status == "revoked":
                async with self.store._transaction(db):
                    await self._audit(db, "extension.call_blocked", principal_id, install_id, status="revoked", method=method)
                raise ContractViolation("extension_revoked", "Extension has been revoked")
            if status == "quarantined":
                async with self.store._transaction(db):
                    await self._audit(db, "extension.call_blocked", principal_id, install_id, status="quarantined", method=method)
                raise ContractViolation("extension_quarantined", "Extension is quarantined")
            if status != "active":
                raise ContractViolation("extension_not_active", f"Extension status '{status}' is not active")

            man_row = await (
                await db.execute("SELECT * FROM extension_manifests WHERE id=?", (inst_row["extension_manifest_id"],))
            ).fetchone()
            manifest = self._manifest_from_row(man_row)

            missing_perms = [p for p in required_permissions if p not in set(manifest.permissions_required)]
            if missing_perms:
                async with self.store._transaction(db):
                    await self._audit(
                        db,
                        "extension.call_blocked",
                        principal_id,
                        install_id,
                        reason="permission_denied",
                        missing=missing_perms,
                    )
                raise ContractViolation("extension_permission_denied", f"Extension lacks permissions: {missing_perms}")

        runner = await self.start(install_id, principal_id=principal_id)
        bundle = await self._resolve_secret_bundle(manifest, principal_id=principal_id)
        scope_cm = bundle.redaction_scope() if bundle is not None else nullcontext()
        call_id = new_id()
        with scope_cm:
            try:
                raw_output = await runner.call(method, params)
            except ExtensionAnomalyError as exc:
                await self._stop_runner(install_id)
                await self._transition(install_id, "quarantined", principal_id=principal_id, reason=str(exc))
                raise ContractViolation("extension_quarantined", str(exc)) from exc
            sanitized_output = redact(raw_output)

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await self._audit(db, "extension.called", principal_id, install_id, call_id=call_id, method=method)
        return CallResult(call_id=call_id, install_id=install_id, status="succeeded", output=sanitized_output)

    async def disable(self, install_id: str, *, principal_id: str, reason: str = "operator_disabled") -> ExtensionInstall:
        self._authorize_principal(principal_id)
        await self._stop_runner(install_id)
        return await self._transition(install_id, "disabled", principal_id=principal_id, reason=reason)

    async def activate(self, install_id: str, *, principal_id: str) -> ExtensionInstall:
        self._authorize_principal(principal_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            inst_row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
            if inst_row is None:
                raise ContractViolation("resource_not_found", f"ExtensionInstall '{install_id}' does not exist")
            man_row = await (
                await db.execute("SELECT * FROM extension_manifests WHERE id=?", (inst_row["extension_manifest_id"],))
            ).fetchone()
            manifest = self._manifest_from_row(man_row)
            await self._require_extension_consent(db, inst_row["consent_record_id"], manifest, principal_id)
            await self._validate_secret_refs(db, manifest.permissions_required)
        self._resolve_entrypoint(manifest.entrypoint, manifest.checksum)
        return await self._transition(install_id, "active", principal_id=principal_id)

    async def revoke(self, install_id: str, *, principal_id: str, reason: str = "operator_revoked") -> ExtensionInstall:
        self._authorize_principal(principal_id)
        await self._stop_runner(install_id)
        current = await self.get_install(install_id)
        if current.status == "revoked":
            return current
        return await self._transition(install_id, "revoked", principal_id=principal_id, reason=reason)

    async def rollback(self, install_id: str, *, principal_id: str) -> ExtensionInstall:
        self._authorize_principal(principal_id)
        await self._stop_runner(install_id)
        await self.store.initialize()
        async with self.store._connect() as db:
            cur_row = await (await db.execute("SELECT * FROM extension_installs WHERE id=?", (install_id,))).fetchone()
            if cur_row is None:
                raise ContractViolation("resource_not_found", f"ExtensionInstall '{install_id}' does not exist")
            if "rolled_back" not in _INSTALL_TRANSITIONS.get(cur_row["status"], frozenset()):
                raise ContractViolation(
                    "invalid_transition",
                    f"Extension in status '{cur_row['status']}' cannot be rolled back",
                )
            cur_man = await (
                await db.execute("SELECT * FROM extension_manifests WHERE id=?", (cur_row["extension_manifest_id"],))
            ).fetchone()
            candidates = await (
                await db.execute(
                    """SELECT ei.*, em.name, em.version, em.entrypoint, em.permissions_required_json,
                              em.compatible_api_version, em.checksum, em.created_at
                       FROM extension_installs ei
                       JOIN extension_manifests em ON em.id = ei.extension_manifest_id
                       WHERE em.name=? AND ei.id != ? AND ei.status IN ('disabled', 'installed')
                       ORDER BY ei.installed_at DESC, ei.id DESC""",
                    (cur_man["name"], install_id),
                )
            ).fetchall()

            target_row = None
            target_manifest = None
            for cand in candidates:
                man = ExtensionManifest(
                    extension_id=cand["extension_manifest_id"],
                    name=cand["name"],
                    version=cand["version"],
                    entrypoint=cand["entrypoint"],
                    permissions_required=tuple(json.loads(cand["permissions_required_json"])),
                    compatible_api_version=cand["compatible_api_version"],
                    checksum=cand["checksum"],
                    created_at=cand["created_at"],
                )
                try:
                    if not is_compatible_api_version(man.compatible_api_version):
                        continue
                    self._resolve_entrypoint(man.entrypoint, man.checksum)
                    await self._require_extension_consent(db, cand["consent_record_id"], man, principal_id)
                    await self._validate_secret_refs(db, man.permissions_required)
                    target_row = cand
                    target_manifest = man
                    break
                except ContractViolation:
                    continue

            if target_row is None or target_manifest is None:
                raise ContractViolation("rollback_unavailable", "No valid prior approved extension version for rollback")

            async with self.store._transaction(db):
                await db.execute("UPDATE extension_installs SET status='rolled_back' WHERE id=?", (install_id,))
                await db.execute("UPDATE extension_installs SET status='active' WHERE id=?", (target_row["id"],))
                await self._audit(
                    db,
                    "extension.rolled_back",
                    principal_id,
                    install_id,
                    restored_install_id=target_row["id"],
                    restored_version=target_manifest.version,
                )
                restored = await (
                    await db.execute("SELECT * FROM extension_installs WHERE id=?", (target_row["id"],))
                ).fetchone()
                return self._install_from_row(restored)
