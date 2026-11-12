"""T22 hermetic offline tests for certified transports, SSH host-key hardening, and session isolation."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import platform
import subprocess

from pydantic import ValidationError
import pytest
import pytest_asyncio

from hydra_orch.bridge.ssh_tunnel import (
    SessionTunnelHandle,
    SshTunnelManager,
    TransportSecurityError,
    compute_ssh_host_key_fingerprint,
)
from hydra_orch.bridge.transport_registry import (
    REQUIRED_CHECKS_BY_TYPE,
    TransportCertificationReport,
    TransportDefinition,
    TransportHealth,
    TransportRegistry,
)
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.model import ContractViolation


def _make_ssh_key_blob(seed: bytes) -> tuple[str, str]:
    raw_key = b"\x00\x00\x00\x0bssh-ed25519" + hashlib.sha256(seed).digest()
    b64 = base64.b64encode(raw_key).decode("ascii")
    return b64, compute_ssh_host_key_fingerprint(b64)


def _make_hashed_known_hosts_line(host: str, key_b64: str, salt: bytes = b"0123456789abcdef0123") -> str:
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(hmac.new(salt, host.encode("utf-8"), hashlib.sha1).digest()).decode("ascii")
    return f"|1|{salt_b64}|{digest_b64} ssh-ed25519 {key_b64}\n"


@pytest_asyncio.fixture
async def transport_registry(tmp_path):
    store = ExecutionStore(tmp_path / "transports.sqlite")
    await store.initialize()
    return TransportRegistry(store)


def test_ssh_host_key_verification(tmp_path):
    key_b64, expected_fp = _make_ssh_key_blob(b"gpu-node-primary")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"[gpu-node.local]:2222 ssh-ed25519 {key_b64}\n", encoding="utf-8")

    manager = SshTunnelManager(
        {
            "host": "gpu-node.local",
            "port": 2222,
            "user": "hydra",
            "known_hosts_file": str(known_hosts),
            "expected_host_key_fingerprint": expected_fp,
        },
        host_key_verifier=lambda host, port: expected_fp,
    )
    assert manager.strict_host_key_checking == "yes"
    verified = manager.verify_host_key()
    assert verified.host == "gpu-node.local"
    assert verified.port == 2222
    assert verified.fingerprint == expected_fp
    assert verified.verified_against == "probe+known_hosts"

    cmd = manager.build_ssh_command(local_port=15001)
    assert "StrictHostKeyChecking=yes" in cmd
    assert f"UserKnownHostsFile={known_hosts}" in cmd
    assert "GlobalKnownHostsFile=none" in cmd
    assert "127.0.0.1:15001:127.0.0.1:11434" in cmd


@pytest.mark.parametrize("policy", ["no", "off", "accept-new", "ask", "false", ""])
def test_ssh_insecure_host_key_policies_rejected(policy):
    with pytest.raises(TransportSecurityError) as exc_info:
        SshTunnelManager(
            {
                "host": "gpu-node.local",
                "port": 22,
                "strict_host_key_checking": policy,
            }
        )
    assert isinstance(exc_info.value, ContractViolation)
    assert exc_info.value.code == "ssh_insecure_host_key_checking"


def test_ssh_host_key_changed_aborts(tmp_path, monkeypatch):
    pinned_b64, pinned_fp = _make_ssh_key_blob(b"pinned-key")
    _, rotated_fp = _make_ssh_key_blob(b"attacker-mitm-key")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"gpu-node.local ssh-ed25519 {pinned_b64}\n", encoding="utf-8")

    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        raise AssertionError("subprocess.Popen must never be invoked when host key diverges")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    # 1. Host key verifier returns a changed fingerprint -> aborts immediately.
    manager = SshTunnelManager(
        {
            "host": "gpu-node.local",
            "port": 22,
            "known_hosts_file": str(known_hosts),
            "expected_host_key_fingerprint": pinned_fp,
        },
        host_key_verifier=lambda _h, _p: rotated_fp,
    )
    with pytest.raises(TransportSecurityError) as err:
        manager.start_tunnel()
    assert err.value.code == "ssh_host_key_mismatch"
    assert popen_calls == []

    # 2. Expected fingerprint does not match known_hosts -> aborts.
    manager_bad_pin = SshTunnelManager(
        {
            "host": "gpu-node.local",
            "port": 22,
            "known_hosts_file": str(known_hosts),
            "expected_host_key_fingerprint": rotated_fp,
        }
    )
    with pytest.raises(TransportSecurityError) as err_pin:
        manager_bad_pin.open_session("sess-mitm")
    assert err_pin.value.code == "ssh_host_key_mismatch"
    assert popen_calls == []

    # 3. Host missing from known_hosts -> aborts without silent bypass.
    manager_unknown = SshTunnelManager(
        {
            "host": "unlisted-node.local",
            "port": 22,
            "known_hosts_file": str(known_hosts),
        }
    )
    with pytest.raises(TransportSecurityError) as err_unknown:
        manager_unknown.start_tunnel()
    assert err_unknown.value.code == "ssh_host_key_unknown"
    assert popen_calls == []


def test_ssh_revoked_or_missing_known_hosts_aborts(tmp_path):
    key_b64, key_fp = _make_ssh_key_blob(b"revoked-host-key")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"@revoked gpu-node.local ssh-ed25519 {key_b64}\n", encoding="utf-8")

    manager_revoked = SshTunnelManager(
        {
            "host": "gpu-node.local",
            "port": 22,
            "known_hosts_file": str(known_hosts),
        }
    )
    with pytest.raises(TransportSecurityError) as err_rev:
        manager_revoked.verify_host_key(observed_fingerprint=key_fp)
    assert err_rev.value.code == "ssh_host_key_revoked"

    manager_missing_file = SshTunnelManager(
        {
            "host": "gpu-node.local",
            "port": 22,
            "known_hosts_file": str(tmp_path / "does_not_exist"),
        }
    )
    with pytest.raises(TransportSecurityError) as err_missing:
        manager_missing_file.verify_host_key()
    assert err_missing.value.code == "ssh_known_hosts_missing"

    manager_unpinned = SshTunnelManager({"host": "gpu-node.local", "port": 22})
    with pytest.raises(TransportSecurityError) as err_unpinned:
        manager_unpinned.start_tunnel()
    assert err_unpinned.value.code == "ssh_known_hosts_required"


def test_ssh_hashed_known_hosts_and_negation(tmp_path):
    key_b64, key_fp = _make_ssh_key_blob(b"hashed-key")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        _make_hashed_known_hosts_line("[gpu-hashed.local]:2222", key_b64)
        + f"*.internal.local,!blocked.internal.local ssh-ed25519 {key_b64}\n",
        encoding="utf-8",
    )

    manager = SshTunnelManager(
        {
            "host": "gpu-hashed.local",
            "port": 2222,
            "known_hosts_file": str(known_hosts),
        }
    )
    result = manager.verify_host_key()
    assert result.fingerprint == key_fp

    blocked_mgr = SshTunnelManager(
        {
            "host": "blocked.internal.local",
            "port": 22,
            "known_hosts_file": str(known_hosts),
        }
    )
    with pytest.raises(TransportSecurityError) as err_blocked:
        blocked_mgr.verify_host_key()
    assert err_blocked.value.code == "ssh_host_key_unknown"


@pytest.mark.asyncio
async def test_healthcheck_typed(transport_registry):
    definition = await transport_registry.register_transport(
        TransportDefinition(
            type="ssh",
            target_identity="gpu-node.local:22",
            capabilities=("tunnel", "remote_exec"),
        )
    )

    # 1. No probe -> truthful unknown (never fabricated healthy)
    sample_unknown = await transport_registry.check_health(definition.transport_id)
    assert isinstance(sample_unknown, TransportHealth)
    assert sample_unknown.status == "unknown"
    assert sample_unknown.last_check_at is not None

    # 2. Healthy async probe
    async def healthy_probe(defn: TransportDefinition):
        assert defn.transport_id == definition.transport_id
        return {"status": "healthy"}

    sample_healthy = await transport_registry.check_health(definition.transport_id, probe=healthy_probe)
    assert sample_healthy.status == "healthy"
    assert sample_healthy.error_detail is None

    # 3. Degraded probe
    sample_degraded = await transport_registry.check_health(
        definition.transport_id,
        probe=lambda _d: {"status": "degraded", "error_detail": "high latency 450ms"},
    )
    assert sample_degraded.status == "degraded"
    assert sample_degraded.error_detail == "high latency 450ms"

    # 4. Failing probe with embedded secrets -> unreachable + redacted error_detail
    def failing_probe(_d):
        raise ConnectionError(
            "Handshake failed for https://alice:supersecret@gpu.local "
            "with Authorization Bearer sk-secretkey1234567890 and password=hunter2"
        )

    sample_unreachable = await transport_registry.check_health(definition.transport_id, probe=failing_probe)
    assert sample_unreachable.status == "unreachable"
    assert sample_unreachable.error_detail is not None
    assert "supersecret" not in sample_unreachable.error_detail
    assert "sk-secretkey1234567890" not in sample_unreachable.error_detail
    assert "hunter2" not in sample_unreachable.error_detail
    assert "[REDACTED]" in sample_unreachable.error_detail

    # 5. Verify SQLite persistence and redaction
    latest = await transport_registry.get_latest_health(definition.transport_id)
    assert latest == sample_unreachable
    history = await transport_registry.list_health_history(definition.transport_id)
    assert [h.status for h in history] == ["unknown", "healthy", "degraded", "unreachable"]


@pytest.mark.asyncio
async def test_concurrent_sessions_isolated(tmp_path):
    key_b64, expected_fp = _make_ssh_key_blob(b"concurrent-host")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"gpu-cluster.local ssh-ed25519 {key_b64}\n", encoding="utf-8")

    manager = SshTunnelManager(
        {
            "host": "gpu-cluster.local",
            "port": 22,
            "known_hosts_file": str(known_hosts),
            "expected_host_key_fingerprint": expected_fp,
        }
    )

    session_ids = [f"session-{i}" for i in range(6)]

    async def launch_session(idx: int) -> SessionTunnelHandle:
        sid = session_ids[idx]
        handle = manager.open_session(sid)
        for line_no in range(5):
            await asyncio.sleep(0)
            manager.append_session_output(
                sid,
                stdout=f"[{sid}] out-{line_no}\n",
                stderr=f"[{sid}] err-{line_no} token=secret-{idx}\n",
            )
        return handle

    handles = await asyncio.gather(*(launch_session(i) for i in range(len(session_ids))))
    ports = [h.local_port for h in handles]
    assert len(set(ports)) == len(session_ids)

    for sid in session_ids:
        logs = manager.get_session_logs(sid)
        assert logs["session_id"] == sid
        stdout_lines = logs["stdout"].strip().splitlines()
        stderr_lines = logs["stderr"].strip().splitlines()
        assert len(stdout_lines) == 5
        assert len(stderr_lines) == 5
        assert all(f"[{sid}]" in line for line in stdout_lines)
        assert all(f"[{sid}]" in line for line in stderr_lines)
        # Ensure zero cross-session contamination and deterministic secret redaction.
        other_ids = [other for other in session_ids if other != sid]
        for other in other_ids:
            assert other not in logs["stdout"]
            assert other not in logs["stderr"]
        assert "secret-" not in logs["stderr"]
        assert "[REDACTED]" in logs["stderr"]

    # Explicit port conflict between two active sessions is rejected.
    with pytest.raises(ContractViolation) as port_err:
        manager.allocate_session_port("session-conflict", preferred_port=handles[0].local_port)
    assert port_err.value.code == "port_conflict"

    # Closing one session frees its port while leaving other sessions intact.
    freed_port = handles[0].local_port
    manager.close_session(session_ids[0])
    reused_handle = manager.open_session("session-reused", preferred_port=freed_port)
    assert reused_handle.local_port == freed_port
    assert manager.get_session(session_ids[1]).status == "allocated"


@pytest.mark.asyncio
async def test_cdp_target_validation(transport_registry):
    cdp_def = await transport_registry.register_transport(
        TransportDefinition(
            type="cdp",
            target_identity="https://claude.ai/chat",
            capabilities=("streaming",),
        )
    )

    # Matching URL (exact and sub-path on same origin) succeeds.
    ok_exact = await transport_registry.assert_target(cdp_def.transport_id, "https://claude.ai/chat")
    assert ok_exact.matched is True
    ok_sub = await transport_registry.assert_target(cdp_def.transport_id, "https://claude.ai/chat/abc-123")
    assert ok_sub.matched is True

    # Divergent host/origin/path fails observably with transport_target_mismatch.
    for wrong_url in (
        "https://chatgpt.com/",
        "https://claude.ai.evil.com/chat",
        "http://claude.ai/chat",
        "https://claude.ai:8443/chat",
        "https://claude.ai/settings",
        "",
    ):
        with pytest.raises(ContractViolation) as mismatch:
            await transport_registry.assert_target(cdp_def.transport_id, wrong_url)
        assert mismatch.value.code == "transport_target_mismatch"

    # CDP page selection NEVER picks an unrelated first page when expected target is absent.
    pages_without_target = [
        {"type": "page", "url": "https://news.ycombinator.com/", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/1"},
        {"type": "page", "url": "https://claude.ai/login", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/2"},
    ]
    with pytest.raises(ContractViolation) as no_match:
        await transport_registry.select_cdp_target_for(cdp_def.transport_id, pages_without_target)
    assert no_match.value.code == "transport_target_mismatch"

    # When expected target is present among multiple pages, selects only the matching target.
    pages_with_target = [
        {"type": "page", "url": "https://news.ycombinator.com/", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/1"},
        {"type": "service_worker", "url": "https://claude.ai/chat", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/sw"},
        {"type": "page", "url": "https://claude.ai/chat/session-9", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/3"},
    ]
    selected = await transport_registry.select_cdp_target_for(cdp_def.transport_id, pages_with_target)
    assert selected["webSocketDebuggerUrl"] == "ws://127.0.0.1:9222/3"


@pytest.mark.asyncio
async def test_uncertified_transport_blocked(transport_registry):
    # Even if caller passes is_certified=True, registration always persists is_certified=False.
    registered = await transport_registry.register_transport(
        TransportDefinition(
            type="ssh",
            target_identity="gpu-prod.local:22",
            capabilities=("tunnel", "workspace_execution"),
            is_certified=True,
        )
    )
    assert registered.is_certified is False
    persisted = await transport_registry.get_transport(registered.transport_id)
    assert persisted.is_certified is False

    # Production / strict mode blocks uncertified transport.
    with pytest.raises(ContractViolation) as blocked:
        await transport_registry.require_certified(registered.transport_id, strict=True, production_mode=True)
    assert blocked.value.code == "transport_uncertified"

    with pytest.raises(ContractViolation) as blocked_target:
        await transport_registry.assert_target(
            registered.transport_id,
            "gpu-prod.local:22",
            strict=True,
            production_mode=True,
        )
    assert blocked_target.value.code == "transport_uncertified"

    # Non-strict mode allows lookup without fabricating certification.
    dev_def = await transport_registry.require_certified(
        registered.transport_id,
        strict=False,
        production_mode=False,
    )
    assert dev_def.is_certified is False

    # Explicit certification via validated report records audit in commands(scope='transport').
    _, key_fp = _make_ssh_key_blob(b"prod-ssh-key")
    report = TransportCertificationReport(
        transport_id=registered.transport_id,
        transport_type="ssh",
        platform=platform.system(),
        version="OpenSSH_9.6",
        target_identity="gpu-prod.local:22",
        fingerprint=key_fp,
        passed_checks=tuple(sorted(REQUIRED_CHECKS_BY_TYPE["ssh"])),
        simulated=False,
        issued_at=datetime.now(timezone.utc),
    )
    cert_id = await transport_registry.certify_transport(
        registered.transport_id,
        report,
        principal_id="operator",
    )
    assert cert_id
    certified = await transport_registry.require_certified(registered.transport_id)
    assert certified.is_certified is True

    # Restart persistence preserves certification state and audit log.
    restarted_registry = TransportRegistry(ExecutionStore(transport_registry.store.db_path))
    assert (await restarted_registry.require_certified(registered.transport_id)).is_certified is True
    assert len(await restarted_registry.list_transports(certified_only=True)) == 1

    # Revocation immediately blocks strict/production execution again.
    await restarted_registry.revoke_certification(
        registered.transport_id,
        principal_id="operator",
        reason="key_rotation",
    )
    with pytest.raises(ContractViolation) as revoked_err:
        await restarted_registry.require_certified(registered.transport_id)
    assert revoked_err.value.code == "transport_uncertified"

    async with transport_registry.store._connect() as db:
        rows = await (
            await db.execute(
                "SELECT scope, response_json FROM commands WHERE scope = 'transport' ORDER BY rowid ASC"
            )
        ).fetchall()
    events = [json.loads(r["response_json"])["event"] for r in rows]
    assert events == [
        "transport.registered",
        "transport.certified",
        "transport.certification_revoked",
    ]


@pytest.mark.parametrize(
    "bad_identity",
    [
        "",
        "   ",
        "http://user:pass@127.0.0.1:9222",
        "https://alice@claude.ai/chat",
        "ssh://hydra:secret@gpu.local:22",
        "hydra:password123@gpu.local",
        "hydra@gpu.local",
        "https://127.0.0.1:9222/?token=abc123456",
        "sk-1234567890abcdef1234",
        "password=mysecretvalue",
        "gpu.local\nssh",
    ],
)
def test_transport_definition_rejects_secrets_and_userinfo(bad_identity):
    with pytest.raises(ValidationError):
        TransportDefinition(type="ssh", target_identity=bad_identity, capabilities=("tunnel",))


@pytest.mark.asyncio
async def test_certification_negative_cases_and_unknown_transport(transport_registry):
    ssh_def = await transport_registry.register_transport(
        TransportDefinition(
            type="ssh",
            target_identity="gpu-neg.local:22",
            capabilities={"tunnel": True},
        )
    )
    _, fp = _make_ssh_key_blob(b"neg-key")
    foreign_os = "Windows" if platform.system() != "Windows" else "Linux"

    # Simulated report rejected by schema.
    with pytest.raises(ValidationError):
        TransportCertificationReport(
            transport_id=ssh_def.transport_id,
            transport_type="ssh",
            platform=platform.system(),
            version="OpenSSH_9.6",
            target_identity="gpu-neg.local:22",
            fingerprint=fp,
            passed_checks=tuple(sorted(REQUIRED_CHECKS_BY_TYPE["ssh"])),
            simulated=True,  # type: ignore[arg-type]
        )

    valid_report = TransportCertificationReport(
        transport_id=ssh_def.transport_id,
        transport_type="ssh",
        platform=platform.system(),
        version="OpenSSH_9.6",
        target_identity="gpu-neg.local:22",
        fingerprint=fp,
        passed_checks=tuple(sorted(REQUIRED_CHECKS_BY_TYPE["ssh"])),
        simulated=False,
    )

    # Empty principal_id refused.
    with pytest.raises(ContractViolation) as auth_err:
        await transport_registry.certify_transport(ssh_def.transport_id, valid_report, principal_id="  ")
    assert auth_err.value.code == "authorization_denied"

    # Missing required checks refused.
    missing_checks = TransportCertificationReport(
        transport_id=ssh_def.transport_id,
        transport_type="ssh",
        platform=platform.system(),
        version="OpenSSH_9.6",
        target_identity="gpu-neg.local:22",
        fingerprint=fp,
        passed_checks=("healthcheck",),
        simulated=False,
    )
    with pytest.raises(ContractViolation) as chk_err:
        await transport_registry.certify_transport(ssh_def.transport_id, missing_checks, principal_id="operator")
    assert chk_err.value.code == "certification_invalid"

    # Missing SSH fingerprint refused.
    no_fp = TransportCertificationReport(
        transport_id=ssh_def.transport_id,
        transport_type="ssh",
        platform=platform.system(),
        version="OpenSSH_9.6",
        target_identity="gpu-neg.local:22",
        fingerprint=None,
        passed_checks=tuple(sorted(REQUIRED_CHECKS_BY_TYPE["ssh"])),
        simulated=False,
    )
    with pytest.raises(ContractViolation) as fp_err:
        await transport_registry.certify_transport(ssh_def.transport_id, no_fp, principal_id="operator")
    assert fp_err.value.code == "certification_invalid"

    # Wrong OS refused.
    wrong_os = TransportCertificationReport(
        transport_id=ssh_def.transport_id,
        transport_type="ssh",
        platform=foreign_os,
        version="OpenSSH_9.6",
        target_identity="gpu-neg.local:22",
        fingerprint=fp,
        passed_checks=tuple(sorted(REQUIRED_CHECKS_BY_TYPE["ssh"])),
        simulated=False,
    )
    with pytest.raises(ContractViolation) as os_err:
        await transport_registry.certify_transport(ssh_def.transport_id, wrong_os, principal_id="operator")
    assert os_err.value.code == "certification_invalid"

    # Unknown transport_id fails with resource_not_found.
    with pytest.raises(ContractViolation) as nf_err:
        await transport_registry.get_transport("missing-transport-id")
    assert nf_err.value.code == "resource_not_found"
