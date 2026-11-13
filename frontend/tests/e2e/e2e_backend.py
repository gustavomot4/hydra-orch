"""Hermetic isolated FastAPI backend launcher for Playwright M5 E2E acceptance suite."""

from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading

import httpx
import uvicorn


_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_TINY_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Count 0 >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip()


def _create_fake_shims(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_cli = bin_dir / "fake_cli.py"
    fake_cli.write_text(
        "import sys\n"
        "tool = sys.argv[1] if len(sys.argv) > 1 else 'cli'\n"
        "print(f'HYDRA-PTY-READY:{tool}', flush=True)\n"
        "for raw in sys.stdin:\n"
        "    line = raw.rstrip('\\r\\n')\n"
        "    if line == '__exit__':\n"
        "        break\n"
        "    print(f'ECHO:{tool}:{line}', flush=True)\n",
        encoding="utf-8",
    )
    py_exe = sys.executable
    for tool in ("codex", "claude"):
        if os.name == "nt":
            shim_cmd = bin_dir / f"{tool}.cmd"
            shim_cmd.write_text(
                f'@echo off\r\n"{py_exe}" "{fake_cli}" {tool} %*\r\n',
                encoding="utf-8",
            )
        else:
            shim_sh = bin_dir / tool
            shim_sh.write_text(
                f'#!/bin/sh\nexec "{py_exe}" "{fake_cli}" {tool} "$@"\n',
                encoding="utf-8",
            )
            os.chmod(shim_sh, os.stat(shim_sh).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _init_e2e_repo(repo_dir: Path) -> str:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(repo_dir, "init", "-b", "main")
    _git(repo_dir, "config", "user.email", "hydra-e2e@example.com")
    _git(repo_dir, "config", "user.name", "Hydra E2E Harness")
    if os.name == "nt":
        _git(repo_dir, "config", "core.longpaths", "true")

    (repo_dir / "src").mkdir(parents=True, exist_ok=True)
    (repo_dir / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo_dir / "src" / "calc.py").write_text("def double(x: int) -> int:\n    return x * 2\n", encoding="utf-8")

    artifacts_dir = repo_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "report.md").write_text(
        "# Relatório E2E Hydra\n\n"
        "Conteúdo **seguro** validado sem execução XSS.\n"
        "<script>window.__xss_executed = true;</script>\n",
        encoding="utf-8",
    )
    (artifacts_dir / "diagram.png").write_bytes(base64.b64decode(_TINY_PNG_B64))
    (artifacts_dir / "spec.pdf").write_bytes(_TINY_PDF_BYTES)
    (artifacts_dir / "change.diff").write_text(
        "--- a/src/calc.py\n"
        "+++ b/src/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x: int) -> int:\n"
        "-    return x\n"
        "+    return x * 2\n",
        encoding="utf-8",
    )

    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-m", "initial e2e fixture commit")
    return _git(repo_dir, "rev-parse", "--verify", "HEAD")


def _build_omniroute_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in {"/health", "/v1/health"}:
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/usage/quota":
            return httpx.Response(
                200,
                json={
                    "claude_pro": {
                        "status": "observed",
                        "remaining_percent": 68,
                        "resets_in_seconds": 3600,
                    },
                    "chatgpt_plus": {
                        "status": "stale",
                        "remaining_percent": 42,
                    },
                    "gemini_pro": {
                        "status": "unknown",
                        "remaining_percent": None,
                    },
                },
            )
        if path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "claude/sonnet-4", "provider": "claude_pro"},
                        {"id": "codex/gpt-5", "provider": "chatgpt_plus"},
                        {"id": "agy/gemini-4-argon-high", "provider": "gemini_pro"},
                    ]
                },
            )
        if path == "/v1/accounts":
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "account_id": "acc-claude-main",
                            "provider": "claude_pro",
                            "label": "Claude Principal",
                            "status": "observed",
                            "remaining_percent": 68,
                            "resets_in_seconds": 3600,
                        },
                        {
                            "account_id": "acc-codex-backup",
                            "provider": "chatgpt_plus",
                            "label": "Codex Secundário",
                            "status": "stale",
                            "remaining_percent": 42,
                        },
                        {
                            "account_id": "acc-gemini-unknown",
                            "provider": "gemini_pro",
                            "label": "Gemini Sem Telemetria",
                            "status": "unknown",
                        },
                    ]
                },
            )
        return httpx.Response(404, json={"error": f"Unhandled mock OmniRoute route: {path}"})

    return httpx.MockTransport(handler)


async def _seed_control_plane(svc, workspace_root: Path, repo_dir: Path, base_sha: str, principal_id: str) -> None:
    from hydra_orch.core.hitl import HITLService
    from hydra_orch.core.session_service import SessionService
    from hydra_orch.core.workspace_registry import WorkspaceRegistry
    from hydra_orch.model import Artifact, CheckSpec, RunSpec, TaskSpec

    await svc.store.initialize()
    reg = WorkspaceRegistry(svc.store, allowed_roots=[workspace_root, repo_dir])
    area = await reg.create_area("Engenharia E2E", principal_id=principal_id, description="Área hermética E2E")
    ws = await reg.create_workspace(area["id"], "Workspace E2E", principal_id=principal_id)
    proj = await reg.create_project(
        ws["id"],
        "hydra-e2e-repo",
        repo_dir,
        principal_id=principal_id,
        base_branch="main",
        base_sha=base_sha,
    )

    run_id = "run-e2e-swarm"
    chk = CheckSpec(check_id="chk-e2e", command=("python", "-c", "print('e2e-ok')"), description="Check unitário E2E")
    spec = RunSpec(
        run_id=run_id,
        project_id=proj["id"],
        repo_root=str(repo_dir),
        base_branch="main",
        base_sha=base_sha,
        objective="Auditoria E2E M5 multi-agente",
        orchestration_mode="swarm",
        idempotency_key="idem-e2e-swarm-0001",
        tasks=(
            TaskSpec(
                task_id="task-wave0",
                run_id=run_id,
                objective="Analisar arquitetura e gerar relatório",
                assigned_executor="codex",
                acceptance_criteria=(chk,),
                allowed_paths=("src/**", "artifacts/**"),
            ),
            TaskSpec(
                task_id="task-wave1",
                run_id=run_id,
                objective="Executar verificação integrada",
                assigned_executor="claude",
                dependencies=("task-wave0",),
                acceptance_criteria=(chk,),
                allowed_paths=("src/**",),
            ),
        ),
    )
    await svc.submit_run(spec)

    async with svc.store._connect() as db:
        async with svc.store._transaction(db):
            await db.execute(
                "UPDATE runs SET status='running', revision=revision+1 WHERE id=?",
                (run_id,),
            )
            await svc.store._insert_event_in_tx(
                db,
                run_id=run_id,
                event_type="run.started",
                payload={"message": "Plano swarm com 2 ondas gerado."},
            )
            await svc.store._insert_event_in_tx(
                db,
                run_id=run_id,
                event_type="task.started",
                task_id="task-wave0",
                payload={"message": "Worker Wave 0 iniciado com codex."},
            )
            await svc.store._insert_event_in_tx(
                db,
                run_id=run_id,
                event_type="thread.message",
                task_id="task-wave0",
                payload={"content": "Leitura concluída e artefatos preparados."},
            )

    hitl = HITLService(svc.store)
    await hitl.request(
        run_id,
        "needs_approval",
        "Aprovar aplicação do patch da Onda 1?",
        idempotency_key="hitl-e2e-req-0001",
        timeout_seconds=600,
        task_id="task-wave1",
    )

    sessions = SessionService(svc.store)
    session = await sessions.create_session(run_id, origin_ref="e2e-ui", agent_ref=None)
    await sessions.create_thread(run_id, session["id"], agent_ref=None)

    artifact_specs = [
        ("art-e2e-md", "artifacts/report.md", "report"),
        ("art-e2e-png", "artifacts/diagram.png", "export"),
        ("art-e2e-pdf", "artifacts/spec.pdf", "export"),
        ("art-e2e-diff", "artifacts/change.diff", "patch"),
    ]
    for art_id, rel_path, kind in artifact_specs:
        raw_bytes = (repo_dir / rel_path).read_bytes()
        await svc.store.save_artifact(
            Artifact(
                artifact_id=art_id,
                run_id=run_id,
                relative_path=rel_path,
                kind=kind,  # type: ignore[arg-type]
                sha256=hashlib.sha256(raw_bytes).hexdigest(),
                size_bytes=len(raw_bytes),
            ),
            emit_event=True,
        )


def main() -> None:
    backend_port = int(os.environ.get("HYDRA_E2E_BACKEND_PORT", "18421"))
    ui_port = int(os.environ.get("HYDRA_E2E_UI_PORT", "15173"))
    token = os.environ.get("HYDRA_API_TOKEN") or "hydra-e2e-hermetic-local-token-0123456789"

    os.environ.pop("HYDRA_API_TOKEN_HASH", None)
    os.environ["HYDRA_API_TOKEN"] = token
    os.environ["HYDRA_CORS_ALLOW_ORIGINS"] = json.dumps(
        [
            f"http://127.0.0.1:{ui_port}",
            f"http://localhost:{ui_port}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    tmpdir = Path(tempfile.mkdtemp(prefix="hydra_e2e_")).resolve()
    try:
        bin_dir = tmpdir / "bin"
        _create_fake_shims(bin_dir)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

        repo_dir = tmpdir / "repo"
        base_sha = _init_e2e_repo(repo_dir)
        rt_dir = tmpdir / "orchestrator_rt"

        from hydra_orch import server
        from hydra_orch.core.checkpointer import ExecutionStore
        from hydra_orch.core.run_service import RunService

        store = ExecutionStore(db_path=rt_dir / "checkpoints.sqlite")
        svc = RunService(repo_root=repo_dir, store=store, runtime_dir=rt_dir)
        server.set_run_service(svc)
        server.app.state.workspace_allowed_roots = [str(tmpdir), str(repo_dir)]
        server.app.state.attachment_root_dir = str(rt_dir / "attachments")
        server.app.state.omniroute_transport = _build_omniroute_transport()
        server.app.state.omniroute_connection_mode = "optional"
        server.config.omniroute.enabled = True
        server.config.omniroute.connection_mode = "optional"

        asyncio.run(
            _seed_control_plane(
                svc,
                tmpdir,
                repo_dir,
                base_sha,
                getattr(server.app.state, "local_principal_id", "operator"),
            )
        )

        uv_config = uvicorn.Config(
            server.app,
            host="127.0.0.1",
            port=backend_port,
            log_level="warning",
        )
        uv_server = uvicorn.Server(uv_config)

        def _watch_stdin_eof() -> None:
            with suppress(Exception):
                sys.stdin.read()
            uv_server.should_exit = True

        watcher = threading.Thread(target=_watch_stdin_eof, name="hydra-e2e-stdin-watch", daemon=True)
        watcher.start()

        uv_server.run()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
