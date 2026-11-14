"""Hermetic tests for T31: PtyRunner, AttachmentService, read_safe_preview, SearchService, and HostCapabilities."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import List

import pytest

from hydra_orch.bridge.pty_runner import PtyChunk, PtyRunner, detect_pty_backend
from hydra_orch.bridge.transport_registry import TransportDefinition
from hydra_orch.bridge.worker_runner import is_process_alive
from hydra_orch.config import HydraConfig
from hydra_orch.core.attachments import AttachmentRef, AttachmentService, read_safe_preview
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.search_index import SearchService, build_host_capabilities
from hydra_orch.model import ContractViolation


async def _wait_for_dead(pids: List[int], *, attempts: int = 80, interval: float = 0.05) -> None:
    for _ in range(attempts):
        if all(not is_process_alive(pid) for pid in pids):
            return
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# PtyRunner tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pty_interactive_echo_ansi_unicode_redaction_and_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak-env-12345678")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_leak_env_99999999")

    script = (
        "import os, sys\n"
        "env_clean = 'OPENAI_API_KEY' not in os.environ and 'GITHUB_TOKEN' not in os.environ\n"
        "allowed = os.environ.get('HYDRA_TEST_ALLOWED', '')\n"
        "print(f'BOOT env_clean={env_clean} allowed={allowed}', flush=True)\n"
        "line = sys.stdin.readline().strip()\n"
        "print(f'\\x1b[36mECHO:{line}\\x1b[0m token=sk-inline-secret-123456', flush=True)\n"
    )
    runner = PtyRunner()
    expected_backend, expected_certified = detect_pty_backend()
    assert runner.backend_kind == expected_backend
    assert runner.pty_certified is expected_certified
    assert runner.backend_info == (expected_backend, expected_certified)

    try:
        info = await runner.open_session(
            [sys.executable, "-u", "-c", script],
            cwd=tmp_path,
            session_id="pty-echo-1",
            workspace_id="ws-1",
            allowed_env={"HYDRA_TEST_ALLOWED": "ok-42"},
        )
        assert info.status == "running"
        assert info.backend_kind == expected_backend
        assert info.pty_certified is expected_certified
        assert info.cwd == os.path.realpath(str(tmp_path))

        # Wait for boot output
        for _ in range(60):
            chunks = runner.read_output("pty-echo-1", after_seq=0)
            if any("BOOT" in c.text for c in chunks):
                break
            await asyncio.sleep(0.05)

        boot_text = "".join(c.text for c in runner.read_output("pty-echo-1"))
        assert "env_clean=True" in boot_text
        assert "allowed=ok-42" in boot_text

        await runner.write_input("pty-echo-1", "olá hydra 🚀\n")
        final_info = await runner.wait("pty-echo-1", timeout=5.0)
        assert final_info.status == "exited"
        assert final_info.exit_code == 0

        all_chunks = runner.read_output("pty-echo-1", after_seq=0)
        combined = "".join(c.text for c in all_chunks)
        if expected_backend == "windows_conpty":
            # ConPTY re-renders VT frames: SGR reset normalizes (`ESC[0m` -> `ESC[m`), may pad cells or wrap cursor CRLF.
            assert re.search(r"\x1b\[36m(?:\r?\n)?ECHO:olá hydra 🚀 *\x1b\[0?m", combined), repr(combined)
        else:
            assert "\x1b[36mECHO:olá hydra 🚀\x1b[0m" in combined
        assert "sk-inline-secret-123456" not in combined
        assert "[REDACTED]" in combined
    finally:
        await runner.close_all()


@pytest.mark.asyncio
async def test_pty_invalid_cwd_rejected(tmp_path: Path) -> None:
    runner = PtyRunner()
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(ContractViolation) as exc_missing:
        await runner.open_session([sys.executable, "-c", "print(1)"], cwd=missing_dir)
    assert exc_missing.value.code == "invalid_workspace_cwd"

    with pytest.raises(ContractViolation) as exc_nul:
        await runner.open_session([sys.executable, "-c", "print(1)"], cwd=f"{tmp_path}\x00bad")
    assert exc_nul.value.code == "invalid_workspace_cwd"


@pytest.mark.asyncio
async def test_pty_after_seq_reconnect_and_buffer_eviction(tmp_path: Path) -> None:
    script = (
        "import sys, time\n"
        "for i in range(1, 7):\n"
        "    print(f'LINE-{i}', flush=True)\n"
        "    time.sleep(0.03)\n"
    )
    runner = PtyRunner(max_scrollback_chunks=100, max_scrollback_bytes=64 * 1024)
    try:
        info = await runner.open_session([sys.executable, "-u", "-c", script], cwd=tmp_path)
        await runner.wait(info.session_id, timeout=5.0)

        chunks_all = runner.read_output(info.session_id, after_seq=0)
        assert len(chunks_all) >= 2
        seqs = [c.seq for c in chunks_all]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)

        pivot = chunks_all[0].seq
        replayed = runner.read_output(info.session_id, after_seq=pivot)
        assert [c.seq for c in replayed] == [c.seq for c in chunks_all if c.seq > pivot]

        streamed: List[PtyChunk] = []
        async for chunk in runner.stream(info.session_id, after_seq=pivot):
            streamed.append(chunk)
        assert [c.seq for c in streamed] == [c.seq for c in replayed]
    finally:
        await runner.close_all()

    # Verify bounded ring buffer eviction triggers cursor_expired
    small_runner = PtyRunner(max_scrollback_chunks=2, max_scrollback_bytes=4096)
    try:
        burst_script = (
            "import time\n"
            "for i in range(6):\n"
            "    print(f'BURST-{i}', flush=True)\n"
            "    time.sleep(0.03)\n"
        )
        info2 = await small_runner.open_session([sys.executable, "-u", "-c", burst_script], cwd=tmp_path)
        done2 = await small_runner.wait(info2.session_id, timeout=5.0)
        assert done2.last_seq >= 4
        with pytest.raises(ContractViolation) as exc_exp:
            small_runner.read_output(done2.session_id, after_seq=1)
        assert exc_exp.value.code == "cursor_expired"
        tail = small_runner.read_output(done2.session_id, after_seq=0)
        assert len(tail) <= 2
    finally:
        await small_runner.close_all()


@pytest.mark.asyncio
async def test_pty_resize_and_interrupt(tmp_path: Path) -> None:
    script = (
        "import time\n"
        "print('READY', flush=True)\n"
        "time.sleep(30)\n"
    )
    runner = PtyRunner()
    try:
        info = await runner.open_session(
            [sys.executable, "-u", "-c", script],
            cwd=tmp_path,
            cols=80,
            rows=24,
        )
        for _ in range(60):
            if any("READY" in c.text for c in runner.read_output(info.session_id)):
                break
            await asyncio.sleep(0.05)

        resized = await runner.resize(info.session_id, cols=132, rows=40)
        assert resized.cols == 132
        assert resized.rows == 40

        with pytest.raises(ContractViolation) as exc_dim:
            await runner.resize(info.session_id, cols=0, rows=24)
        assert exc_dim.value.code == "invalid_pty_dimensions"

        await runner.interrupt(info.session_id)
        done = await runner.wait(info.session_id, timeout=5.0)
        assert done.status == "exited"
        assert done.exit_code is not None
        assert done.exit_code != 0
        if done.pid:
            await _wait_for_dead([done.pid])
            assert is_process_alive(done.pid) is False
    finally:
        await runner.close_all()


@pytest.mark.asyncio
async def test_pty_detach_keep_running_then_tree_kill(tmp_path: Path) -> None:
    pids_file = tmp_path / "pty_pids.json"
    marker_file = tmp_path / "emit_after_detach.flag"
    script = (
        "import json, os, pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pids_file)!r}).write_text(json.dumps({{'parent': os.getpid(), 'child': child.pid}}), encoding='utf-8')\n"
        "print('PHASE-1', flush=True)\n"
        f"flag = pathlib.Path({str(marker_file)!r})\n"
        "while not flag.exists():\n"
        "    time.sleep(0.03)\n"
        "print('PHASE-2-WHILE-DETACHED', flush=True)\n"
        "time.sleep(60)\n"
    )
    runner = PtyRunner()
    try:
        info = await runner.open_session(
            [sys.executable, "-u", "-c", script],
            cwd=tmp_path,
            session_id="pty-tree-1",
        )

        observed_live: List[PtyChunk] = []

        async def _consume() -> None:
            async for chunk in runner.stream("pty-tree-1", after_seq=0):
                observed_live.append(chunk)

        consumer_task = asyncio.create_task(_consume())

        for _ in range(80):
            if pids_file.exists() and any("PHASE-1" in c.text for c in observed_live):
                break
            await asyncio.sleep(0.05)

        assert pids_file.exists()
        pids = json.loads(pids_file.read_text(encoding="utf-8"))
        parent_pid = int(pids["parent"])
        child_pid = int(pids["child"])
        assert is_process_alive(parent_pid) is True
        assert is_process_alive(child_pid) is True

        last_seen_seq = observed_live[-1].seq
        # Detach UI stream while keeping process running
        detached_info = await runner.close_session("pty-tree-1", keep_running=True)
        await asyncio.wait_for(consumer_task, timeout=2.0)
        assert detached_info.status == "running"
        assert detached_info.detached is True
        assert is_process_alive(parent_pid) is True

        # Trigger PHASE-2 output while detached
        marker_file.write_text("go", encoding="utf-8")
        for _ in range(60):
            missed = runner.read_output("pty-tree-1", after_seq=last_seen_seq)
            if any("PHASE-2-WHILE-DETACHED" in c.text for c in missed):
                break
            await asyncio.sleep(0.05)

        missed_text = "".join(c.text for c in runner.read_output("pty-tree-1", after_seq=last_seen_seq))
        assert "PHASE-2-WHILE-DETACHED" in missed_text

        # Close with keep_running=False -> full process tree kill
        closed_info = await runner.close_session("pty-tree-1", keep_running=False)
        assert closed_info.status == "cancelled"
        assert closed_info.detached is False

        await _wait_for_dead([parent_pid, child_pid])
        assert is_process_alive(parent_pid) is False
        assert is_process_alive(child_pid) is False

        # Verify close_all() shuts down a detached session cleanly
        detached_sess = await runner.open_session(
            [sys.executable, "-u", "-c", "import time; print('up', flush=True); time.sleep(60)"],
            cwd=tmp_path,
            session_id="pty-close-all",
        )
        assert detached_sess.pid is not None
        await runner.close_session("pty-close-all", keep_running=True)
        await runner.close_all()
        await _wait_for_dead([detached_sess.pid])
        assert is_process_alive(detached_sess.pid) is False
        assert runner.get_session("pty-close-all").status == "cancelled"
    finally:
        await runner.close_all()


# ---------------------------------------------------------------------------
# AttachmentService & read_safe_preview tests
# ---------------------------------------------------------------------------


def test_attachment_service_upload_persistence_scope_and_remote_confirm(tmp_path: Path) -> None:
    store_dir = tmp_path / "attachments"
    svc = AttachmentService(store_dir, max_bytes=1024)

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"data" * 10
    local_ref = svc.save_attachment(
        workspace_id="ws-alpha",
        session_id="sess-1",
        filename="diagram.png",
        content=png_bytes,
        mime_type="image/png",
        host_id="local",
    )
    assert isinstance(local_ref, AttachmentRef)
    assert local_ref.transfer_status == "local_ready"
    assert local_ref.remote_confirmed is False
    assert local_ref.size_bytes == len(png_bytes)
    assert local_ref.sha256 == hashlib.sha256(png_bytes).hexdigest()

    remote_ref = svc.save_attachment(
        workspace_id="ws-alpha",
        session_id="sess-1",
        filename="notes.md",
        content=b"# Notes\nHello",
        mime_type="text/markdown",
        host_id="ssh-gpu-1",
    )
    assert remote_ref.transfer_status == "pending_remote_confirm"
    assert remote_ref.remote_confirmed is False

    # Cross-session access must raise forbidden_scope
    with pytest.raises(ContractViolation) as exc_scope:
        svc.get_attachment(local_ref.attachment_id, session_id="sess-2")
    assert exc_scope.value.code == "forbidden_scope"

    with pytest.raises(ContractViolation) as exc_confirm_scope:
        svc.confirm_remote_transfer(remote_ref.attachment_id, session_id="sess-2")
    assert exc_confirm_scope.value.code == "forbidden_scope"

    assert svc.list_attachments("sess-2") == []

    # Confirm remote transfer under owning session
    confirmed = svc.confirm_remote_transfer(remote_ref.attachment_id, session_id="sess-1")
    assert confirmed.remote_confirmed is True
    assert confirmed.transfer_status == "transferred"

    # Restart AttachmentService and verify index + payload survived
    restarted = AttachmentService(store_dir, max_bytes=1024)
    listed = restarted.list_attachments("sess-1")
    assert [a.attachment_id for a in listed] == [local_ref.attachment_id, remote_ref.attachment_id]
    fetched_remote = restarted.get_attachment(remote_ref.attachment_id, session_id="sess-1")
    assert fetched_remote.transfer_status == "transferred"
    assert fetched_remote.remote_confirmed is True
    assert restarted.read_attachment_bytes(local_ref.attachment_id, session_id="sess-1") == png_bytes


def test_attachment_service_rejects_traversal_size_and_dangerous_types(tmp_path: Path) -> None:
    svc = AttachmentService(tmp_path / "att", max_bytes=64)

    for bad_name in ("../escape.txt", "sub/file.txt", "sub\\file.txt", "..", "C:evil.txt", "bad\x00.txt"):
        with pytest.raises(ContractViolation) as exc_trav:
            svc.save_attachment("ws-1", "sess-1", bad_name, b"hi", mime_type="text/plain")
        assert exc_trav.value.code == "path_traversal_blocked"

    with pytest.raises(ContractViolation) as exc_size:
        svc.save_attachment("ws-1", "sess-1", "big.txt", b"a" * 65, mime_type="text/plain")
    assert exc_size.value.code == "attachment_too_large"

    bad_cases = [
        ("page.html", "text/html", b"<html><script>alert(1)</script></html>"),
        ("icon.svg", "image/svg+xml", b"<svg onload=alert(1)></svg>"),
        ("app.js", "application/javascript", b"alert(1);"),
        ("run.exe", "application/octet-stream", b"MZ\x90\x00"),
        ("setup.bat", "text/plain", b"@echo off\r\ncalc.exe"),
        ("script.sh", "text/plain", b"#!/bin/sh\nid"),
        ("run.ps1", "text/plain", b"Write-Host hi"),
        ("fake.txt", "text/plain", b"MZ\x90\x00disguised"),
        ("fake.png", "image/png", b"<svg onload=alert(1)></svg>"),
    ]
    for fname, mime, payload in bad_cases:
        with pytest.raises(ContractViolation) as exc_type:
            svc.save_attachment("ws-1", "sess-1", fname, payload, mime_type=mime)
        assert exc_type.value.code == "unsupported_attachment_type"


def test_read_safe_preview_formats_and_security_guards(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("TOP_SECRET", encoding="utf-8")

    base = tmp_path / "workspace"
    base.mkdir()

    # Path traversal & missing
    for bad_rel in ("../outside.txt", "sub/../../outside.txt", "/etc/passwd", "C:\\Windows\\win.ini", "."):
        with pytest.raises(ContractViolation) as exc_trav:
            read_safe_preview(base, bad_rel)
        assert exc_trav.value.code == "path_traversal_blocked"

    # Symlink escape test when OS grants symlink creation
    escape_link = base / "link_outside.txt"
    try:
        escape_link.symlink_to(outside)
    except OSError:
        escape_link = None
    if escape_link is not None:
        with pytest.raises(ContractViolation) as exc_sym:
            read_safe_preview(base, "link_outside.txt")
        assert exc_sym.value.code == "path_traversal_blocked"

    with pytest.raises(ContractViolation) as exc_missing:
        read_safe_preview(base, "missing.md")
    assert exc_missing.value.code == "resource_not_found"

    # Size limit
    big_file = base / "large.txt"
    big_file.write_bytes(b"x" * 2048)
    with pytest.raises(ContractViolation) as exc_large:
        read_safe_preview(base, "large.txt", max_bytes=1024)
    assert exc_large.value.code == "preview_too_large"

    # Markdown sanitization + redaction
    md_file = base / "report.md"
    md_file.write_text(
        "# Report\n"
        "Token: sk-secret-preview-123456\n"
        "<script>alert('xss')</script>\n"
        "<img src=\"x\" onerror=\"alert(2)\" />\n"
        "[bad](javascript:alert(3))\n"
        "[bad2](data:text/html;base64,PHNjcmlwdD4=)\n",
        encoding="utf-8",
    )
    md_prev = read_safe_preview(base, "report.md")
    assert md_prev["supported"] is True
    assert md_prev["status"] == "ok"
    assert md_prev["render_mode"] == "markdown"
    assert md_prev["script_stripped"] is True
    assert md_prev["redacted"] is True
    assert "sk-secret-preview-123456" not in md_prev["sanitized_markdown"]
    assert "<script" not in md_prev["sanitized_markdown"].lower()
    assert "onerror=" not in md_prev["sanitized_markdown"].lower()
    assert "javascript:" not in md_prev["sanitized_markdown"].lower()
    assert "data:text/html" not in md_prev["sanitized_markdown"].lower()
    assert "[REDACTED]" in md_prev["sanitized_markdown"]

    # HTML and SVG must NEVER be returned as executable content
    (base / "evil.html").write_text("<html><script>alert(1)</script></html>", encoding="utf-8")
    html_prev = read_safe_preview(base, "evil.html")
    assert html_prev["supported"] is False
    assert html_prev["status"] == "unsupported_media_type"
    assert html_prev["content"] is None
    assert html_prev["content_base64"] is None

    (base / "vector.svg").write_text("<svg onload='alert(1)'></svg>", encoding="utf-8")
    svg_prev = read_safe_preview(base, "vector.svg")
    assert svg_prev["supported"] is False
    assert svg_prev["status"] == "unsupported_media_type"
    assert svg_prev["content"] is None

    # PNG and PDF safe previews
    png_raw = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    (base / "shot.png").write_bytes(png_raw)
    png_prev = read_safe_preview(base, "shot.png")
    assert png_prev["supported"] is True
    assert png_prev["render_mode"] == "image"
    assert png_prev["mime_type"] == "image/png"
    assert png_prev["sha256"] == hashlib.sha256(png_raw).hexdigest()
    assert base64.b64decode(png_prev["content_base64"]) == png_raw

    pdf_raw = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    (base / "spec.pdf").write_bytes(pdf_raw)
    pdf_prev = read_safe_preview(base, "spec.pdf")
    assert pdf_prev["supported"] is True
    assert pdf_prev["render_mode"] == "pdf"
    assert pdf_prev["mime_type"] == "application/pdf"
    assert pdf_prev["sha256"] == hashlib.sha256(pdf_raw).hexdigest()
    assert base64.b64decode(pdf_prev["content_base64"]) == pdf_raw


# ---------------------------------------------------------------------------
# SearchService & build_host_capabilities tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_service_queries_all_scopes_redacts_and_blocks_sqli(tmp_path: Path) -> None:
    store = ExecutionStore(tmp_path / "search.sqlite")
    await store.initialize()

    async with store._connect() as db:
        async with store._transaction(db):
            await db.execute(
                "INSERT INTO areas (id, name, description, owner_principal_id) VALUES (?, ?, ?, ?)",
                ("area-1", "Core Auth Area", "Handles identity", "operator"),
            )
            await db.execute(
                "INSERT INTO area_workspaces (id, area_id, name, status) VALUES (?, ?, ?, ?)",
                ("ws-1", "area-1", "Auth Workspace", "active"),
            )
            await db.execute(
                "INSERT INTO projects (id, canonical_root, name, workspace_id, base_branch, base_sha) VALUES (?, ?, ?, ?, ?, ?)",
                ("proj-1", str(tmp_path / "repo-auth"), "Auth Service", "ws-1", "main", "a" * 40),
            )
            await db.execute(
                "INSERT INTO runs (id, project_id, spec_json, base_sha, status) VALUES (?, ?, ?, ?, ?)",
                (
                    "run-1",
                    "proj-1",
                    json.dumps({"objective": "Fix Auth login token sk-secret-db-99999999"}),
                    "a" * 40,
                    "running",
                ),
            )
            await db.execute(
                "INSERT INTO sessions (id, run_id, origin_ref, agent_ref, state) VALUES (?, ?, ?, ?, ?)",
                ("sess-1", "run-1", "pty-auth-shell", None, "running"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, run_id, attempt_id, relative_path, kind, sha256, size_bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("art-1", "run-1", None, "reports/auth_audit.md", "report", "b" * 64, 128),
            )

    svc = SearchService(store)
    hits = await svc.search("Auth")
    kinds = {h["kind"] for h in hits}
    assert {"area", "workspace", "project", "run", "session", "artifact"} <= kinds

    run_hit = next(h for h in hits if h["kind"] == "run")
    assert run_hit["run_id"] == "run-1"
    assert run_hit["project_id"] == "proj-1"
    assert run_hit["workspace_id"] == "ws-1"
    assert run_hit["host_id"] == "local"
    assert "sk-secret-db-99999999" not in run_hit["title"]
    assert "[REDACTED]" in run_hit["title"]

    sess_hit = next(h for h in hits if h["kind"] == "session")
    assert sess_hit["session_id"] == "sess-1"
    assert sess_hit["tab_hint"] == "terminal"

    # Searching directly for a secret token must return empty
    assert await svc.search("sk-secret-db-99999999") == []

    # Scoped search
    proj_only = await svc.search("Auth", scope="projects")
    assert len(proj_only) == 1
    assert proj_only[0]["kind"] == "project"

    # SQL injection and LIKE wildcard escaping must treat inputs as literal text
    sqli_hits = await svc.search("'; DROP TABLE projects; --")
    assert sqli_hits == []
    assert await svc.search("%") == []
    assert len(await svc.search("Auth", scope="projects")) == 1

    # Remote host without indexed projects returns empty rather than faking local data
    assert await svc.search("Auth", host_id="remote-gpu-9") == []


def test_build_host_capabilities_honest_defaults_and_certification_gate() -> None:
    cfg = HydraConfig()
    uncertified_remote = TransportDefinition(
        transport_id="tr-uncert-1",
        type="remote",
        target_identity="remote.local:9000",
        capabilities=("mobile_emulator", "computer_use", "pty"),
        is_certified=False,
    )
    certified_remote = TransportDefinition(
        transport_id="tr-cert-1",
        type="remote",
        target_identity="device-lab.local:9001",
        capabilities=("mobile_emulator", "computer_use", "pty"),
        is_certified=True,
    )

    caps = build_host_capabilities(cfg, transports=(uncertified_remote, certified_remote))
    local_caps = caps["hosts"]["local"]["capabilities"]

    expected_backend, expected_pty_cert = detect_pty_backend()
    assert local_caps["pty"]["backend_kind"] == expected_backend
    assert local_caps["pty"]["certified"] is expected_pty_cert

    assert local_caps["dictation_stt"]["available_modes"] == ["browser_optional_text_draft"]
    assert local_caps["dictation_stt"]["duplex_voice_enabled"] is False

    assert local_caps["mobile_emulator"]["status"] == "unavailable"
    assert local_caps["mobile_emulator"]["certified"] is False
    assert local_caps["mobile_emulator"]["reason"] == "uncertified_parking_lot_bridge"

    assert local_caps["computer_use"]["status"] == "unavailable"
    assert local_caps["computer_use"]["certified"] is False
    assert local_caps["computer_use"]["reason"] == "uncertified_parking_lot_bridge"

    # Uncertified transport claiming mobile_emulator/computer_use must remain unavailable
    uncert_caps = caps["hosts"]["tr-uncert-1"]["capabilities"]
    assert uncert_caps["mobile_emulator"]["status"] == "unavailable"
    assert uncert_caps["mobile_emulator"]["certified"] is False
    assert uncert_caps["mobile_emulator"]["reason"] == "uncertified_parking_lot_bridge"
    assert uncert_caps["computer_use"]["status"] == "unavailable"
    assert uncert_caps["computer_use"]["certified"] is False

    # Explicitly certified transport enables declared capabilities
    cert_caps = caps["hosts"]["tr-cert-1"]["capabilities"]
    assert cert_caps["mobile_emulator"]["status"] == "available"
    assert cert_caps["mobile_emulator"]["certified"] is True
    assert cert_caps["computer_use"]["status"] == "available"
    assert cert_caps["computer_use"]["certified"] is True
    assert cert_caps["pty"]["status"] == "available"
    assert cert_caps["pty"]["certified"] is True
