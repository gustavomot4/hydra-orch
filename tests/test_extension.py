"""T20: hermetic tests for ExtensionHost, process isolation, consent, revocation, quarantine, and rollback."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from hydra_orch.bridge.worker_runner import is_process_alive
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.consent import ConsentService, MemoryScope
from hydra_orch.core.extension_host import (
    EXTENSION_API_VERSION,
    ExtensionHost,
    ExtensionManifest,
)
from hydra_orch.core.redaction import REDACTED
from hydra_orch.core.skill_registry import SecretResolver, SkillRegistry
from hydra_orch.model import ContractViolation


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_extension(directory: Path, name: str, source: str) -> tuple[Path, str]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path, _sha256_file(path)


async def _grant_extension_consent(
    consents: ConsentService,
    extension_name: str,
    *,
    principal_id: str = "operator",
):
    req = await consents.request(
        MemoryScope(scope_type="extension", scope_id=extension_name),
        principal_id=principal_id,
        purpose="extension",
    )
    return await consents.decide(req.consent_id, action="granted", principal_id=principal_id)


@pytest.mark.asyncio
async def test_manifest_validation(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    entry, digest = _write_extension(
        ext_dir,
        "good_ext.py",
        "def handle(method, params):\n    return {'ok': True, 'method': method}\n",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])
    consent = await _grant_extension_consent(consents, "good-ext")

    # Corrupted checksum rejected on register/install
    bad_checksum_manifest = ExtensionManifest(
        name="good-ext",
        version="1.0.0",
        entrypoint="good_ext.py",
        compatible_api_version=EXTENSION_API_VERSION,
        checksum="0" * 64,
    )
    with pytest.raises(ContractViolation) as exc:
        await host.register_manifest(bad_checksum_manifest, principal_id="operator")
    assert exc.value.code == "extension_checksum_mismatch"

    # Incompatible API version rejected
    bad_api_manifest = ExtensionManifest(
        name="good-ext",
        version="1.0.0",
        entrypoint="good_ext.py",
        compatible_api_version="2.0",
        checksum=digest,
    )
    with pytest.raises(ContractViolation) as exc:
        await host.install(bad_api_manifest, consent.consent_id, principal_id="operator")
    assert exc.value.code == "extension_incompatible_api"

    # Invalid permission and embedded raw secret rejected at manifest creation
    with pytest.raises(ValueError):
        ExtensionManifest(
            name="good-ext",
            version="1.0.0",
            entrypoint="good_ext.py",
            permissions_required=("admin:root",),
            checksum=digest,
        )
    with pytest.raises(ValueError):
        ExtensionManifest(
            name="sk-secret1234567890123456",
            version="1.0.0",
            entrypoint="good_ext.py",
            checksum=digest,
        )

    # Path traversal rejected
    with pytest.raises(ValueError):
        ExtensionManifest(
            name="good-ext",
            version="1.0.0",
            entrypoint="../outside.py",
            checksum=digest,
        )

    # Symlink escaping allowed_roots rejected (skip cleanly if OS disallows unprivileged symlinks)
    outside = tmp_path / "outside_secret_ext.py"
    outside.write_text("def handle(m, p): return {}\n", encoding="utf-8")
    symlink_path = ext_dir / "escape.py"
    try:
        symlink_path.symlink_to(outside)
    except OSError:
        symlink_supported = False
    else:
        symlink_supported = True

    if symlink_supported:
        symlink_manifest = ExtensionManifest(
            name="good-ext",
            version="1.0.1",
            entrypoint="escape.py",
            checksum=_sha256_file(outside),
        )
        with pytest.raises(ContractViolation) as exc:
            await host.register_manifest(symlink_manifest, principal_id="operator")
        assert exc.value.code == "extension_invalid_entrypoint"


@pytest.mark.asyncio
async def test_install_requires_active_extension_consent(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    _, digest = _write_extension(
        ext_dir,
        "consented.py",
        "def handle(method, params):\n    return {'ok': True}\n",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])
    manifest = ExtensionManifest(
        name="consented-ext",
        version="1.0.0",
        entrypoint="consented.py",
        checksum=digest,
    )

    # Pending (not granted) extension consent -> rejected
    pending = await consents.request(
        MemoryScope(scope_type="extension", scope_id="consented-ext"),
        principal_id="operator",
        purpose="extension",
    )
    with pytest.raises(ContractViolation) as exc:
        await host.install(manifest, pending.consent_id, principal_id="operator")
    assert exc.value.code == "consent_required"

    # Memory-purpose consent rejected for extension install
    mem_req = await consents.request(
        MemoryScope(scope_type="principal", scope_id="operator"),
        principal_id="operator",
        purpose="memory",
    )
    mem_grant = await consents.decide(mem_req.consent_id, action="granted", principal_id="operator")
    with pytest.raises(ContractViolation) as exc:
        await host.install(manifest, mem_grant.consent_id, principal_id="operator")
    assert exc.value.code == "consent_required"

    # Consent for a different extension rejected
    other_grant = await _grant_extension_consent(consents, "different-ext")
    with pytest.raises(ContractViolation) as exc:
        await host.install(manifest, other_grant.consent_id, principal_id="operator")
    assert exc.value.code == "consent_required"

    # Consent for a different principal rejected
    other_principal_grant = await _grant_extension_consent(consents, "consented-ext", principal_id="alice")
    with pytest.raises(ContractViolation) as exc:
        await host.install(manifest, other_principal_grant.consent_id, principal_id="operator")
    assert exc.value.code == "consent_required"

    # Valid granted extension consent succeeds
    valid_grant = await _grant_extension_consent(consents, "consented-ext", principal_id="operator")
    install = await host.install(manifest, valid_grant.consent_id, principal_id="operator")
    assert install.status == "active"


@pytest.mark.asyncio
async def test_process_isolation_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST_UNRELATED_SECRET", "top-secret-host-only-value")

    ext_dir = tmp_path / "extensions"
    hostile_source = """
import os
import pathlib
import socket
import subprocess

def handle(method, params):
    if method == "whoami":
        return {
            "pid": os.getpid(),
            "host_secret_seen": "HOST_UNRELATED_SECRET" in os.environ,
            "cwd": os.getcwd(),
        }
    if method == "touch_db":
        db_path = params["db_path"]
        try:
            with open(db_path, "rb") as fh:
                return {"read_bytes": len(fh.read(16))}
        except Exception as exc:
            # Even if caught in user code, audit hook still flags anomaly!
            return {"caught": type(exc).__name__, "detail": str(exc)}
    if method == "write_wal":
        try:
            pathlib.Path(params["wal_path"]).write_text("tamper", encoding="utf-8")
            return {"wrote": True}
        except Exception as exc:
            return {"caught": type(exc).__name__}
    if method == "read_outside":
        try:
            return {"text": pathlib.Path(params["path"]).read_text(encoding="utf-8")}
        except Exception as exc:
            return {"caught": type(exc).__name__}
    if method == "try_net":
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.close()
            return {"opened": True}
        except Exception as exc:
            return {"caught": type(exc).__name__}
    if method == "try_spawn":
        try:
            subprocess.run(["python", "--version"], check=False)
            return {"spawned": True}
        except Exception as exc:
            return {"caught": type(exc).__name__}
    return {"unknown": method}
"""
    _, digest = _write_extension(ext_dir, "hostile.py", hostile_source)
    outside_file = tmp_path / "secret_notes.txt"
    outside_file.write_text("private-host-file", encoding="utf-8")

    db_path = tmp_path / "core.sqlite"
    store = ExecutionStore(db_path)
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])

    for idx, probe in enumerate(
        (
            ("touch_db", {"db_path": str(db_path)}),
            ("write_wal", {"wal_path": f"{db_path}-wal"}),
            ("read_outside", {"path": str(outside_file)}),
            ("try_net", {}),
            ("try_spawn", {}),
        )
    ):
        method, payload = probe
        ext_name = f"hostile-ext-{idx}"
        grant = await _grant_extension_consent(consents, ext_name)
        manifest = ExtensionManifest(
            name=ext_name,
            version="1.0.0",
            entrypoint="hostile.py",
            permissions_required=(),
            checksum=digest,
        )
        install = await host.install(manifest, grant.consent_id, principal_id="operator")

        if idx == 0:
            info = await host.execute(install.install_id, "whoami", principal_id="operator")
            assert info.status == "succeeded"
            assert info.output["pid"] != os.getpid()
            assert info.output["host_secret_seen"] is False

        with pytest.raises(ContractViolation) as exc:
            await host.execute(install.install_id, method, payload, principal_id="operator")
        assert exc.value.code == "extension_quarantined"

        updated = await host.get_install(install.install_id)
        assert updated.status == "quarantined"
        assert host.get_running_pid(install.install_id) is None

    # Original DB & outside file remain untouched
    assert outside_file.read_text(encoding="utf-8") == "private-host-file"
    assert not Path(f"{db_path}-wal").exists() or "tamper" not in Path(f"{db_path}-wal").read_text(errors="ignore")


@pytest.mark.asyncio
async def test_revocation_immediate_block(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    _, digest = _write_extension(
        ext_dir,
        "worker_ext.py",
        "import os\ndef handle(method, params):\n    return {'pid': os.getpid(), 'ok': True}\n",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])

    grant = await _grant_extension_consent(consents, "revocable-ext")
    manifest = ExtensionManifest(
        name="revocable-ext",
        version="1.0.0",
        entrypoint="worker_ext.py",
        checksum=digest,
    )
    install = await host.install(manifest, grant.consent_id, principal_id="operator")

    res = await host.execute(install.install_id, "ping", principal_id="operator")
    assert res.output["ok"] is True
    worker_pid = res.output["pid"]
    assert worker_pid != os.getpid()
    assert is_process_alive(worker_pid)

    # Immediate revocation stops process tree synchronously
    revoked = await host.revoke(install.install_id, principal_id="operator", reason="security_incident")
    assert revoked.status == "revoked"
    assert revoked.revoked_at is not None
    assert host.get_running_pid(install.install_id) is None
    assert not is_process_alive(worker_pid)

    # Subsequent calls fail closed with extension_revoked + audit entry
    with pytest.raises(ContractViolation) as exc:
        await host.execute(install.install_id, "ping", principal_id="operator")
    assert exc.value.code == "extension_revoked"

    async with store._connect() as db:
        blocked = await (
            await db.execute(
                "SELECT json_extract(response_json, '$.event') AS ev FROM commands "
                "WHERE scope='extension' AND json_extract(response_json, '$.resource_id')=? "
                "AND json_extract(response_json, '$.event')='extension.call_blocked'",
                (install.install_id,),
            )
        ).fetchone()
        assert blocked is not None

    # Consent revocation cascades into extension_installs immediately
    grant2 = await _grant_extension_consent(consents, "consent-cascade-ext")
    manifest2 = ExtensionManifest(
        name="consent-cascade-ext",
        version="1.0.0",
        entrypoint="worker_ext.py",
        checksum=digest,
    )
    install2 = await host.install(manifest2, grant2.consent_id, principal_id="operator")
    res2 = await host.execute(install2.install_id, "ping", principal_id="operator")
    pid2 = res2.output["pid"]
    assert is_process_alive(pid2)

    await consents.decide(grant2.consent_id, action="revoked", principal_id="operator")
    after_consent_revoke = await host.get_install(install2.install_id)
    assert after_consent_revoke.status == "revoked"
    with pytest.raises(ContractViolation) as exc2:
        await host.execute(install2.install_id, "ping", principal_id="operator")
    assert exc2.value.code == "extension_revoked"
    await host._stop_runner(install2.install_id)
    assert not is_process_alive(pid2)


@pytest.mark.asyncio
async def test_execute_happy_path_secret_ref_and_redaction(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    sentinel = "OPAQUE_EXT_SECRET_VALUE_77331"
    _, digest = _write_extension(
        ext_dir,
        "echo_secret.py",
        """
import os

def handle(method, params):
    val = os.environ.get("EXT_TOKEN", "")
    return {
        "has_token": bool(val),
        "echo_leaked_token": val,
        "arg": (params or {}).get("message", ""),
    }
""",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    skill_reg = SkillRegistry(store)
    sec_ref = await skill_reg.create_secret_ref(
        secret_name="EXT_TOKEN",
        provider_type="env",
        source_key="HYDRA_TEST_EXT_TOKEN",
        principal_id="operator",
    )
    resolver = SecretResolver(skill_reg, env_source={"HYDRA_TEST_EXT_TOKEN": sentinel})
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir], secret_resolver=resolver)

    grant = await _grant_extension_consent(consents, "secret-ext")
    manifest = ExtensionManifest(
        name="secret-ext",
        version="1.0.0",
        entrypoint="echo_secret.py",
        permissions_required=(f"secret:{sec_ref.secret_id}",),
        checksum=digest,
    )
    install = await host.install(manifest, grant.consent_id, principal_id="operator")

    # Missing required_permissions raises extension_permission_denied
    with pytest.raises(ContractViolation) as exc:
        await host.execute(
            install.install_id,
            "run",
            {"message": "hello"},
            principal_id="operator",
            required_permissions=("net:external",),
        )
    assert exc.value.code == "extension_permission_denied"

    result = await host.execute(
        install.install_id,
        "run",
        {"message": "hello"},
        principal_id="operator",
        required_permissions=(f"secret:{sec_ref.secret_id}",),
    )
    assert result.status == "succeeded"
    assert result.output["has_token"] is True
    assert result.output["echo_leaked_token"] == REDACTED
    assert result.output["arg"] == "hello"
    assert sentinel not in repr(result)

    # Confirm sentinel never persisted anywhere in SQLite
    async with store._connect() as db:
        for table in ("commands", "extension_manifests", "extension_installs", "secret_refs"):
            rows = await (await db.execute(f"SELECT * FROM {table}")).fetchall()
            for row in rows:
                assert sentinel not in repr(dict(row))

    await host.disable(install.install_id, principal_id="operator")


@pytest.mark.asyncio
async def test_checksum_tampering_on_disk_quarantines(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    entry_path, digest = _write_extension(
        ext_dir,
        "tamper_target.py",
        "def handle(method, params):\n    return {'v': 1}\n",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])
    grant = await _grant_extension_consent(consents, "tamper-ext")
    manifest = ExtensionManifest(
        name="tamper-ext",
        version="1.0.0",
        entrypoint="tamper_target.py",
        checksum=digest,
    )
    install = await host.install(manifest, grant.consent_id, principal_id="operator")

    # Mutate extension code on disk after install
    entry_path.write_text("def handle(method, params):\n    return {'v': 'evil'}\n", encoding="utf-8")

    with pytest.raises(ContractViolation) as exc:
        await host.execute(install.install_id, "ping", principal_id="operator")
    assert exc.value.code == "extension_checksum_mismatch"

    updated = await host.get_install(install.install_id)
    assert updated.status == "quarantined"


@pytest.mark.asyncio
async def test_rollback_restores_previous_approved_version(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    _, digest_v1 = _write_extension(
        ext_dir,
        "plugin_v1.py",
        "def handle(method, params):\n    return {'version': '1.0.0'}\n",
    )
    _, digest_v2 = _write_extension(
        ext_dir,
        "plugin_v2.py",
        "def handle(method, params):\n    return {'version': '2.0.0'}\n",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])
    grant = await _grant_extension_consent(consents, "upgradable-plugin")

    man_v1 = ExtensionManifest(
        name="upgradable-plugin",
        version="1.0.0",
        entrypoint="plugin_v1.py",
        checksum=digest_v1,
    )
    install_v1 = await host.install(man_v1, grant.consent_id, principal_id="operator")

    # No prior version yet -> rollback_unavailable
    with pytest.raises(ContractViolation) as exc:
        await host.rollback(install_v1.install_id, principal_id="operator")
    assert exc.value.code == "rollback_unavailable"

    man_v2 = ExtensionManifest(
        name="upgradable-plugin",
        version="2.0.0",
        entrypoint="plugin_v2.py",
        checksum=digest_v2,
    )
    install_v2 = await host.install(man_v2, grant.consent_id, principal_id="operator")
    assert (await host.get_install(install_v1.install_id)).status == "disabled"
    assert (await host.get_install(install_v2.install_id)).status == "active"

    res_v2 = await host.execute(install_v2.install_id, "ver", principal_id="operator")
    assert res_v2.output["version"] == "2.0.0"
    v2_pid = res_v2.output.get("pid")
    assert host.get_running_pid(install_v2.install_id) is not None

    restored = await host.rollback(install_v2.install_id, principal_id="operator")
    assert restored.install_id == install_v1.install_id
    assert restored.status == "active"
    assert (await host.get_install(install_v2.install_id)).status == "rolled_back"
    assert host.get_running_pid(install_v2.install_id) is None

    res_v1 = await host.execute(restored.install_id, "ver", principal_id="operator")
    assert res_v1.output["version"] == "1.0.0"

    await host.disable(restored.install_id, principal_id="operator")


@pytest.mark.asyncio
async def test_state_machine_invalid_transitions_and_audit_atomicity(tmp_path: Path):
    ext_dir = tmp_path / "extensions"
    _, digest = _write_extension(
        ext_dir,
        "sm_ext.py",
        "def handle(method, params):\n    return {'ok': True}\n",
    )

    store = ExecutionStore(tmp_path / "core.sqlite")
    consents = ConsentService(store)
    host = ExtensionHost(store, consents, allowed_roots=[ext_dir])
    grant = await _grant_extension_consent(consents, "sm-ext")
    manifest = ExtensionManifest(
        name="sm-ext",
        version="1.0.0",
        entrypoint="sm_ext.py",
        checksum=digest,
    )
    install = await host.install(manifest, grant.consent_id, principal_id="operator", activate=False)
    assert install.status == "installed"

    # Cannot execute while merely installed (not active)
    with pytest.raises(ContractViolation) as exc:
        await host.execute(install.install_id, "ping", principal_id="operator")
    assert exc.value.code == "extension_not_active"

    active = await host.activate(install.install_id, principal_id="operator")
    assert active.status == "active"

    revoked = await host.revoke(install.install_id, principal_id="operator")
    assert revoked.status == "revoked"

    # Revoked is terminal: activate, disable, and rollback must fail with invalid_transition
    with pytest.raises(ContractViolation) as exc:
        await host.activate(install.install_id, principal_id="operator")
    assert exc.value.code == "invalid_transition"

    with pytest.raises(ContractViolation) as exc:
        await host.disable(install.install_id, principal_id="operator")
    assert exc.value.code == "invalid_transition"

    with pytest.raises(ContractViolation) as exc:
        await host.rollback(install.install_id, principal_id="operator")
    assert exc.value.code == "invalid_transition"

    assert (await host.get_install(install.install_id)).status == "revoked"

    async with store._connect() as db:
        rows = await (
            await db.execute(
                "SELECT json_extract(response_json, '$.event') AS ev FROM commands "
                "WHERE scope='extension' ORDER BY created_at ASC"
            )
        ).fetchall()
        events = [r["ev"] for r in rows]
        assert "extension.manifest_registered" not in events  # install() registers directly
        assert "extension.installed" in events
        assert "extension.active" in events
        assert "extension.revoked" in events
