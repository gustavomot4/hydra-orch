"""Comprehensive tests for Wave 1D: Git scope/hooks hardening, NTFS junctions, Windows longpaths, and ReDoS-free redaction."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Tuple

import pytest
from pydantic import TypeAdapter, ValidationError

from hydra_orch.core.attachments import (
    AttachmentService,
    read_safe_preview,
    sanitize_markdown_content,
)
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.discovery import DiscoveryService
from hydra_orch.core.document_check import check as check_documents
from hydra_orch.core.git_workspace import (
    GitWorkspaceError,
    GitWorkspaceService,
    is_link_or_junction,
    win_long_path,
)
from hydra_orch.core.packaging import PRPackager
from hydra_orch.core.redaction import (
    REDACTED,
    StreamingRedactor,
    _URL_CREDENTIAL,
    redact,
    redact_text,
    redaction_scope,
)
from hydra_orch.core.workspace_registry import WorkspaceRegistry
from hydra_orch.model import (
    Artifact,
    BudgetPolicy,
    CheckResult,
    CheckSpec,
    ContractViolation,
    IntegrationStatus,
    ProcessStatus,
    RelativePath,
    ReviewDecision,
    RunSpec,
    TaskAttempt,
    TaskResult,
    TaskSpec,
    TaskStatus,
    _validate_relative_path,
    review_result,
)


def _raw_git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.longpaths=true", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(repo_dir: Path) -> Tuple[Path, str]:
    win_long_path(repo_dir).mkdir(parents=True, exist_ok=True)
    _raw_git(repo_dir, "init", "-b", "main")
    _raw_git(repo_dir, "config", "user.name", "Hydra Test")
    _raw_git(repo_dir, "config", "user.email", "test@hydra.local")
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    (repo_dir / "src").mkdir(exist_ok=True)
    (repo_dir / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _raw_git(repo_dir, "add", ".")
    _raw_git(repo_dir, "commit", "-m", "chore: init")
    return repo_dir, _raw_git(repo_dir, "rev-parse", "HEAD")


def _create_ntfs_junction(link_path: Path, target_dir: Path) -> None:
    if os.name != "nt":
        pytest.skip("NTFS junctions are Windows-specific")
    res = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"mklink /J failed: {res.stdout} {res.stderr}"


# ---------------------------------------------------------------------------
# 1. SEC-03 & SEC-13: Git env scrubbing, hooks neutralized, .git integrity, ref safety
# ---------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.asyncio
async def test_git_hooks_blocked_and_host_secrets_stripped_across_workspace_and_packaging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, base_sha = _init_repo(tmp_path / "repo")
    bare_remote = tmp_path / "remote.git"
    _raw_git(tmp_path, "init", "--bare", str(bare_remote))
    _raw_git(repo, "remote", "add", "origin", str(bare_remote))

    secret_api_tok = "hydra_tok_host_secret_value_0123456789abcdef"
    secret_openai = "sk-proj-hostsecret9876543210abcdef"
    monkeypatch.setenv("HYDRA_API_TOKEN", secret_api_tok)
    monkeypatch.setenv("OPENAI_API_KEY", secret_openai)

    # Plant malicious hooks in repo/.git/hooks that write marker files and dump leaked env vars
    marker_file = tmp_path / "hook_pwned.txt"
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_body = (
        "#!/bin/sh\n"
        f"echo \"HOOK_RAN:$HYDRA_API_TOKEN:$OPENAI_API_KEY\" >> \"{marker_file.as_posix()}\"\n"
        "exit 1\n"
    )
    for hook_name in ("pre-commit", "commit-msg", "post-commit", "pre-merge-commit", "post-merge", "pre-push"):
        hp = hooks_dir / hook_name
        hp.write_text(hook_body, encoding="utf-8")
        try:
            hp.chmod(0o755)
        except OSError:
            pass

    store = ExecutionStore(tmp_path / "store.sqlite")
    await store.initialize()
    svc = GitWorkspaceService(repo_root=repo, store=store)

    # Verify hardened git config is active inside GitWorkspaceService._run_git and PRPackager._run_git
    for runner_fn in (
        lambda a: svc._run_git(a, cwd=repo),
        lambda a: PRPackager._run_git(a, repo),
    ):
        cfg_hooks = runner_fn(["config", "--get", "core.hooksPath"]).stdout.strip()
        assert cfg_hooks
        assert Path(cfg_hooks).is_dir()
        assert list(Path(cfg_hooks).iterdir()) == []
        assert runner_fn(["config", "--get", "core.fsmonitor"]).stdout.strip() == "false"
        assert runner_fn(["config", "--get", "protocol.file.allow"]).stdout.strip() == "never"
        assert runner_fn(["config", "--get", "core.longpaths"]).stdout.strip() == "true"

    # Verify host env secrets are NOT inherited by git subprocesses
    alias_res = svc._run_git(
        ["-c", "alias.envcheck=!sh -c 'printf \"%s|%s\" \"$HYDRA_API_TOKEN\" \"$OPENAI_API_KEY\"'", "envcheck"],
        cwd=repo,
    )
    assert secret_api_tok not in alias_res.stdout
    assert secret_openai not in alias_res.stdout
    assert alias_res.stdout.strip() == "|"

    # Execute worktree creation, commit, merge, repair worktree, and PR package build + publish
    ws = svc.create_worktree("run_sec03", "t1", "att1", base_sha)
    (ws.canonical_path / "src" / "app.py").write_text("VALUE = 99\n", encoding="utf-8")
    diff_art = svc.capture_and_commit_patch(ws, "feat: update value", allowed_paths=("src/**",))
    assert diff_art.has_changes and diff_art.patch_commit_sha is not None

    task_spec = TaskSpec(
        task_id="t1",
        run_id="run_sec03",
        objective="Update app.py",
        assigned_executor="codex",
        acceptance_criteria=(CheckSpec(check_id="c1", command=("python", "-c", "print(1)")),),
        allowed_paths=("src/**",),
    )
    now = datetime.now(timezone.utc)
    att = TaskAttempt(
        attempt_id="att1",
        task_id="t1",
        run_id="run_sec03",
        ordinal=1,
        executor_id="codex",
        provider="openai",
        model="gpt-5",
        base_sha=base_sha,
        workspace_path=str(ws.canonical_path),
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        started_at=now,
        finished_at=now,
        exit_reason="completed",
    )
    out_art = Artifact(
        artifact_id="art_out",
        run_id="run_sec03",
        attempt_id="att1",
        relative_path=".orchestrator/logs/out.log",
        kind="check_output",
        sha256=hashlib.sha256(b"1\n").hexdigest(),
        size_bytes=2,
    )
    err_art = Artifact(
        artifact_id="art_err",
        run_id="run_sec03",
        attempt_id="att1",
        relative_path=".orchestrator/logs/err.log",
        kind="check_output",
        sha256=hashlib.sha256(b"").hexdigest(),
        size_bytes=0,
    )
    assert diff_art.artifact is not None
    ready = TaskResult(
        result_id="res1",
        attempt_id="att1",
        run_id="run_sec03",
        base_sha=base_sha,
        process_status=ProcessStatus.EXITED,
        exit_code=0,
        task_status=TaskStatus.READY_FOR_REVIEW,
        summary="Updated app.py",
        patch_commit_sha=diff_art.patch_commit_sha,
        patch_artifact_id=diff_art.artifact.artifact_id,
        changed_files=("src/app.py",),
        checks_executed=(
            CheckResult(
                check_id="c1",
                command=("python", "-c", "print(1)"),
                tested_sha=diff_art.patch_commit_sha,
                exit_code=0,
                duration_seconds=0.01,
                stdout_artifact_id="art_out",
                stderr_artifact_id="art_err",
            ),
        ),
        artifacts=(diff_art.artifact, out_art, err_art),
    )
    accepted = review_result(
        task_spec,
        att,
        ready,
        ReviewDecision(result_id="res1", actor="op", decision="accepted", reason="ok", expected_revision=1),
    )
    run_spec = RunSpec(
        run_id="run_sec03",
        project_id="proj1",
        objective="Test hooks",
        repo_root=str(repo),
        base_sha=base_sha,
        base_branch="main",
        idempotency_key="idem_sec03_hooks_0001",
        budget_policy=BudgetPolicy(max_wall_seconds=300),
        tasks=(task_spec,),
    )
    await store.save_run_atomic(run_spec)
    await store.save_attempt_atomic(att)

    int_outcome = await svc.integrate_results("run_sec03", base_sha, (accepted,))
    assert int_outcome.status == IntegrationStatus.INTEGRATED

    packager = PRPackager(store)
    pkg = await packager.build("run_sec03")
    pub = await packager.publish(pkg.package_id, authorized=True, remote="origin")
    assert pub.published is True

    assert not marker_file.exists(), "Git hook should never have executed!"


@pytest.mark.security
def test_worktree_dot_git_tampering_detected(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path / "repo")
    svc = GitWorkspaceService(repo_root=repo)

    # Case 1: worker replaces wt/.git file with a directory
    ws1 = svc.create_worktree("run_tamp", "t1", "att1", base_sha)
    dot_git_1 = ws1.canonical_path / ".git"
    dot_git_1.unlink()
    dot_git_1.mkdir()
    (dot_git_1 / "config").write_text("[core]\nfsmonitor = evil\n", encoding="utf-8")

    with pytest.raises(GitWorkspaceError) as exc1:
        svc.validate_worktree_scope(ws1.canonical_path, base_sha=base_sha)
    assert exc1.value.failure.code == "scope_violation"

    with pytest.raises(GitWorkspaceError) as exc1b:
        svc.capture_and_commit_patch(ws1, "tampered commit")
    assert exc1b.value.failure.code == "scope_violation"
    assert ws1.status == "preserved"

    # Case 2: worker rewrites wt/.git gitdir pointer outside repo/.git/worktrees
    ws2 = svc.create_worktree("run_tamp", "t2", "att2", base_sha)
    rogue_gitdir = tmp_path / "rogue_gitdir"
    rogue_gitdir.mkdir()
    dot_git_2 = ws2.canonical_path / ".git"
    dot_git_2.unlink()
    dot_git_2.write_text(f"gitdir: {rogue_gitdir.as_posix()}\n", encoding="utf-8")

    with pytest.raises(GitWorkspaceError) as exc2:
        svc.validate_worktree_scope(ws2.canonical_path, base_sha=base_sha)
    assert exc2.value.failure.code == "scope_violation"

    with pytest.raises(GitWorkspaceError) as exc2b:
        svc.capture_and_commit_patch(ws2, "rogue gitdir")
    assert exc2b.value.failure.code == "scope_violation"
    assert ws2.status == "preserved"


@pytest.mark.security
@pytest.mark.asyncio
async def test_branch_and_ref_argument_injection_rejected(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path / "repo")
    svc = GitWorkspaceService(repo_root=repo)

    for bad_ref in ("--all", "-n", "--output=/tmp/pwn", "", "   ", "HEAD with space", "bad\x00ref"):
        with pytest.raises(GitWorkspaceError) as exc_ref:
            svc.resolve_commit_sha(bad_ref)
        assert exc_ref.value.failure.code == "workspace_invalid"

    for bad_branch in (
        "-b",
        "--upload-pack=evil",
        "/leading",
        "trailing/",
        "a..b",
        "feat.lock",
        "HEAD",
        "@",
        "feat@{0}",
        "feat~1",
        "feat^2",
        "feat:ref",
    ):
        with pytest.raises(GitWorkspaceError) as exc_br:
            svc.create_worktree("run_ref", "t1", "att1", base_sha, branch_name=bad_branch)
        assert exc_br.value.failure.code == "workspace_invalid"

        with pytest.raises(GitWorkspaceError) as exc_int:
            await svc.integrate_results("run_ref", base_sha, (), target_branch=bad_branch)
        assert exc_int.value.failure.code == "workspace_invalid"

        with pytest.raises(ContractViolation) as exc_pkg:
            PRPackager._validate_branch_name(bad_branch)
        assert exc_pkg.value.code == "packaging_invalid"


# ---------------------------------------------------------------------------
# 2. SEC-04: NTFS Junctions (`mklink /J`) & Windows Case-Insensitivity
# ---------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.asyncio
async def test_ntfs_junction_detection_across_worktree_registry_discovery_and_preview(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("NTFS junctions (`mklink /J`) require Windows")

    outside_dir = tmp_path / "outside_secret_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("TOP_SECRET_DATA", encoding="utf-8")
    (outside_dir / "SKILL.md").write_text("---\ncapabilities: [workspace_execution]\n---\nevil", encoding="utf-8")

    repo, base_sha = _init_repo(tmp_path / "repo")
    svc = GitWorkspaceService(repo_root=repo)

    # 1. GitWorkspaceService worktree junction escape
    ws = svc.create_worktree("run_junc", "t1", "att1", base_sha)
    wt_junc = ws.canonical_path / "src" / "junc_out"
    _create_ntfs_junction(wt_junc, outside_dir)
    try:
        assert wt_junc.is_symlink() is False  # Python 3.12 behavior on Windows
        assert is_link_or_junction(wt_junc) is True

        scope_res = svc.validate_worktree_scope(ws.canonical_path, base_sha=base_sha, allowed_paths=("src/**",))
        assert scope_res.valid is False
        assert any("junc_out" in p for p in scope_res.symlink_escapes)

        with pytest.raises(GitWorkspaceError) as exc_commit:
            svc.capture_and_commit_patch(ws, "should fail junction", allowed_paths=("src/**",))
        assert exc_commit.value.failure.code == "scope_violation"
    finally:
        os.rmdir(wt_junc)

    # 2. WorkspaceRegistry.resolve_path junction escape (both external and intermediate internal)
    store = ExecutionStore(tmp_path / "reg.sqlite")
    reg = WorkspaceRegistry(store, allowed_roots=[tmp_path])
    area = await reg.create_area("Area", principal_id="alice")
    wspace = await reg.create_workspace(area["id"], "WS", principal_id="alice")
    proj = await reg.create_project(wspace["id"], "Proj", repo, principal_id="alice")
    registered = await reg.register_repository(
        proj["id"],
        repo,
        principal_id="alice",
        authorized_principal_id="alice",
        scopes=["read", "write"],
        allowed_paths=["src/**"],
    )

    repo_junc_ext = repo / "src" / "ext_junc"
    _create_ntfs_junction(repo_junc_ext, outside_dir)
    private_in_repo = repo / "private_dir"
    private_in_repo.mkdir()
    (private_in_repo / "key.pem").write_text("secret", encoding="utf-8")
    repo_junc_int = repo / "src" / "int_junc"
    _create_ntfs_junction(repo_junc_int, private_in_repo)
    try:
        with pytest.raises(ContractViolation) as exc_reg_ext:
            await reg.resolve_path(registered["id"], "src/ext_junc/secret.txt", principal_id="alice")
        assert exc_reg_ext.value.code == "scope_violation"

        with pytest.raises(ContractViolation) as exc_reg_int:
            await reg.resolve_path(registered["id"], "src/int_junc/key.pem", principal_id="alice")
        assert exc_reg_int.value.code == "scope_violation"
    finally:
        os.rmdir(repo_junc_ext)
        os.rmdir(repo_junc_int)

    # 3. DiscoveryService skips NTFS junctions and invalidates if replaced by junction
    disc_root = tmp_path / "disc_root"
    disc_root.mkdir()
    (disc_root / "sub").mkdir()
    (disc_root / "sub" / "SKILL.md").write_text(
        "---\ncapabilities: [workspace_execution]\n---\nsafe",
        encoding="utf-8",
    )
    disc_junc = disc_root / "junc_outside"
    _create_ntfs_junction(disc_junc, outside_dir)
    try:
        disc = DiscoveryService(store, allowed_roots=[disc_root], enabled=True)
        found = await disc.scan(disc_root, principal_id="operator")
        assert len(found) == 1
        assert "junc_outside" not in found[0].source_canonical_path

        await disc.approve(found[0].discovery_id, found[0].content_hash, principal_id="operator")
        shutil.rmtree(disc_root / "sub")
        _create_ntfs_junction(disc_root / "sub", outside_dir)
        try:
            refreshed = await disc.get(found[0].discovery_id, principal_id="operator")
            assert refreshed.trust_status == "untrusted"
        finally:
            os.rmdir(disc_root / "sub")
    finally:
        os.rmdir(disc_junc)

    # 4. read_safe_preview blocks NTFS junction escape
    prev_base = tmp_path / "prev_base"
    prev_base.mkdir()
    prev_junc = prev_base / "junc"
    _create_ntfs_junction(prev_junc, outside_dir)
    try:
        with pytest.raises(ContractViolation) as exc_prev:
            read_safe_preview(prev_base, "junc/secret.txt")
        assert exc_prev.value.code == "path_traversal_blocked"
    finally:
        os.rmdir(prev_junc)


@pytest.mark.security
@pytest.mark.asyncio
async def test_case_insensitive_scope_matching_on_windows(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path / "repo")
    svc = GitWorkspaceService(repo_root=repo)
    ws = svc.create_worktree("run_case", "t1", "att1", base_sha)
    (ws.canonical_path / "SECRET_FILE.TXT").write_text("leak", encoding="utf-8")

    res = svc.validate_worktree_scope(
        ws.canonical_path,
        base_sha=base_sha,
        allowed_paths=("**/*",),
        forbidden_paths=("secret_file.txt",),
    )
    if os.name == "nt":
        assert res.valid is False
        assert "SECRET_FILE.TXT" in res.forbidden_hits

    store = ExecutionStore(tmp_path / "case_reg.sqlite")
    reg = WorkspaceRegistry(store, allowed_roots=[tmp_path])
    area = await reg.create_area("Area", principal_id="alice")
    wspace = await reg.create_workspace(area["id"], "WS", principal_id="alice")
    proj = await reg.create_project(wspace["id"], "Proj", repo, principal_id="alice")
    registered = await reg.register_repository(
        proj["id"],
        repo,
        principal_id="alice",
        authorized_principal_id="alice",
        scopes=["read"],
        allowed_paths=["src/**"],
    )
    if os.name == "nt":
        resolved = await reg.resolve_path(registered["id"], "SRC/APP.PY", principal_id="alice")
        assert resolved.name.lower() == "app.py"


# ---------------------------------------------------------------------------
# 3. BE-07 & DAY-06: Windows Longpaths (>260 chars) in Worktrees & Attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_windows_longpaths_worktree_commit_integrate_repair_and_attachments(tmp_path: Path) -> None:
    # Build a base path > 120 characters while keeping repo/.git within Git's internal $GIT_DIR 260-char buffer
    if len(str(tmp_path)) < 125:
        pad = max(8, 130 - len(str(tmp_path)))
        long_base = tmp_path / ("b_" + "x" * pad)
    else:
        long_base = tmp_path
    assert len(str(long_base)) > 120

    try:
        repo_dir = long_base / "repo"
        repo, base_sha = _init_repo(repo_dir)
        store = ExecutionStore(win_long_path(tmp_path / "lp_store.sqlite"))
        await store.initialize()
        svc = GitWorkspaceService(repo_root=repo, store=store)

        long_run_id = "run_" + "r" * 48
        long_attempt_id = "attempt_" + "a" * 48
        ws = svc.create_worktree(long_run_id, "task_longpath", long_attempt_id, base_sha)
        assert svc._run_git(["config", "--get", "core.longpaths"], cwd=ws.canonical_path).stdout.strip() == "true"

        deep_rel = f"src/{'pkg_' + 'd' * 75}/{'mod_' + 'm' * 75}/deep_feature_module.py"
        deep_target = ws.canonical_path / deep_rel
        assert len(str(deep_target)) > 290  # Exceeds Windows 260 MAX_PATH!

        lp_target = win_long_path(deep_target)
        if os.name == "nt":
            assert str(lp_target).startswith("\\\\?\\")
        lp_target.parent.mkdir(parents=True, exist_ok=True)
        lp_target.write_text("DEEP_OK = True\n", encoding="utf-8")

        diff_art = svc.capture_and_commit_patch(
            ws,
            "feat: add deep longpath file",
            allowed_paths=("src/**",),
        )
        assert diff_art.has_changes is True
        assert diff_art.patch_commit_sha is not None
        assert diff_art.patch_path is not None
        assert win_long_path(diff_art.patch_path).is_file()

        # Verify serialized integration on >260 char file path
        task_spec = TaskSpec(
            task_id="task_longpath",
            run_id=long_run_id,
            objective="Support Windows MAX_PATH > 260",
            assigned_executor="codex",
            acceptance_criteria=(CheckSpec(check_id="c1", command=("python", "-c", "print(1)")),),
            allowed_paths=("src/**",),
        )
        now = datetime.now(timezone.utc)
        att = TaskAttempt(
            attempt_id=long_attempt_id,
            task_id="task_longpath",
            run_id=long_run_id,
            ordinal=1,
            executor_id="codex",
            provider="openai",
            model="gpt-5",
            base_sha=base_sha,
            workspace_path=str(ws.canonical_path),
            process_status=ProcessStatus.EXITED,
            exit_code=0,
            started_at=now,
            finished_at=now,
            exit_reason="completed",
        )
        out_art = Artifact(
            artifact_id="art_lp_out",
            run_id=long_run_id,
            attempt_id=long_attempt_id,
            relative_path=".orchestrator/logs/out.log",
            kind="check_output",
            sha256=hashlib.sha256(b"1\n").hexdigest(),
            size_bytes=2,
        )
        err_art = Artifact(
            artifact_id="art_lp_err",
            run_id=long_run_id,
            attempt_id=long_attempt_id,
            relative_path=".orchestrator/logs/err.log",
            kind="check_output",
            sha256=hashlib.sha256(b"").hexdigest(),
            size_bytes=0,
        )
        assert diff_art.artifact is not None
        ready = TaskResult(
            result_id="res_lp_1",
            attempt_id=long_attempt_id,
            run_id=long_run_id,
            base_sha=base_sha,
            process_status=ProcessStatus.EXITED,
            exit_code=0,
            task_status=TaskStatus.READY_FOR_REVIEW,
            summary="Added deep module",
            patch_commit_sha=diff_art.patch_commit_sha,
            patch_artifact_id=diff_art.artifact.artifact_id,
            changed_files=(deep_rel,),
            checks_executed=(
                CheckResult(
                    check_id="c1",
                    command=("python", "-c", "print(1)"),
                    tested_sha=diff_art.patch_commit_sha,
                    exit_code=0,
                    duration_seconds=0.01,
                    stdout_artifact_id="art_lp_out",
                    stderr_artifact_id="art_lp_err",
                ),
            ),
            artifacts=(diff_art.artifact, out_art, err_art),
        )
        accepted = review_result(
            task_spec,
            att,
            ready,
            ReviewDecision(result_id="res_lp_1", actor="op", decision="accepted", reason="ok", expected_revision=1),
        )
        run_spec = RunSpec(
            run_id=long_run_id,
            project_id="proj_lp",
            objective="Longpaths integration",
            repo_root=str(repo),
            base_sha=base_sha,
            base_branch="main",
            idempotency_key="idem_longpath_be07_0001",
            budget_policy=BudgetPolicy(max_wall_seconds=300),
            tasks=(task_spec,),
        )
        await store.save_run_atomic(run_spec)
        await store.save_attempt_atomic(att)

        outcome = await svc.integrate_results(long_run_id, base_sha, (accepted,))
        assert outcome.status == IntegrationStatus.INTEGRATED
        merged_deep = outcome.integration_worktree_path / deep_rel
        assert win_long_path(merged_deep).read_text(encoding="utf-8") == "DEEP_OK = True\n"
        assert (
            svc._run_git(["config", "--get", "core.longpaths"], cwd=outcome.integration_worktree_path).stdout.strip()
            == "true"
        )

        # Verify merge_repair worktree also configures core.longpaths=true
        repair_ws = svc.create_merge_repair_worktree(
            long_run_id,
            "conflict_longpath_01",
            1,
            base_sha,
            populate_conflict=False,
        )
        assert (
            svc._run_git(["config", "--get", "core.longpaths"], cwd=repair_ws.canonical_path).stdout.strip()
            == "true"
        )

        # DAY-06: AttachmentService inside long root with long filename & session_id
        att_root = long_base / ("attachments_storage_" + ("z" * 60))
        att_svc = AttachmentService(att_root)
        long_filename = ("relatorio_arquitetura_detalhada_" * 4) + "final.pdf"
        pdf_payload = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
        long_sess = "draft-session-" + ("s" * 60)

        saved_ref = att_svc.save_attachment(
            workspace_id="ws-long-" + ("w" * 40),
            session_id=long_sess,
            filename=long_filename,
            content=pdf_payload,
            mime_type="application/pdf",
        )
        assert saved_ref.storage_rel_path.startswith("att/")
        assert len(saved_ref.storage_rel_path) <= 50
        assert saved_ref.filename == long_filename
        assert saved_ref.session_id == long_sess
        assert att_svc.read_attachment_bytes(saved_ref.attachment_id, session_id=long_sess) == pdf_payload

        reloaded_att_svc = AttachmentService(att_root)
        assert reloaded_att_svc.get_attachment(saved_ref.attachment_id, session_id=long_sess).filename == long_filename
    finally:
        shutil.rmtree(win_long_path(long_base), ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. SEC-12 & SEC-14: Document Check Traversal Oracle, Windows Device Names, PDF Magic
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_document_check_blocks_external_links_without_existence_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_outside = tmp_path / "outside_exists.md"
    existing_outside.write_text("# secret outside\n", encoding="utf-8")

    repo, _ = _init_repo(tmp_path / "docs_repo")
    doc = repo / "README.md"
    doc.write_text(
        "[leak_exist](../outside_exists.md)\n"
        "[leak_missing](../outside_does_not_exist_999.md)\n",
        encoding="utf-8",
    )
    _raw_git(repo, "add", "README.md")
    _raw_git(repo, "commit", "-m", "docs: links")

    orig_exists = Path.exists
    probed_outside: list[str] = []

    def _guarded_exists(self: Path) -> bool:
        norm = str(self).replace("\\\\?\\", "")
        if "outside_exists.md" in norm or "outside_does_not_exist_999.md" in norm:
            probed_outside.append(norm)
        return orig_exists(self)

    monkeypatch.setattr(Path, "exists", _guarded_exists)
    errors = check_documents(["README.md"], repo)

    assert probed_outside == [], "document_check must NOT call .exists() on external paths!"
    outside_errs = [e for e in errors if "outside repository" in e]
    assert len(outside_errs) == 2
    assert any("../outside_exists.md" in e for e in outside_errs)
    assert any("../outside_does_not_exist_999.md" in e for e in outside_errs)


@pytest.mark.security
@pytest.mark.parametrize(
    "bad_path",
    [
        "CON",
        "con",
        "PRN",
        "AUX",
        "aux.txt",
        "NUL",
        "src/nul.md",
        "COM1",
        "dir/com9.log",
        "LPT1",
        "nested/lpt9.tar.gz",
    ],
)
def test_windows_reserved_device_names_blocked_in_relative_path(bad_path: str) -> None:
    with pytest.raises(ValueError):
        _validate_relative_path(bad_path)
    with pytest.raises(ValidationError):
        TypeAdapter(RelativePath).validate_python(bad_path)


def test_benign_non_device_relative_paths_allowed() -> None:
    for ok_path in ("src/config.py", "src/console.ts", "tests/null_case.py", "docs/com10.md", "src/auxiliary.py"):
        assert TypeAdapter(RelativePath).validate_python(ok_path) == ok_path


@pytest.mark.security
def test_pdf_magic_header_enforced_in_preview_and_attachments(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"NOT_A_REAL_PDF_HEADER_AT_ALL")

    prev_fake = read_safe_preview(tmp_path, "fake.pdf")
    assert prev_fake["supported"] is False
    assert prev_fake["status"] == "unsupported_media_type"
    assert prev_fake["reason"] == "invalid_pdf_magic"
    assert prev_fake["content_base64"] is None

    real_pdf = tmp_path / "real.pdf"
    real_pdf.write_bytes(b"%PDF-1.5\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    prev_real = read_safe_preview(tmp_path, "real.pdf")
    assert prev_real["supported"] is True
    assert prev_real["status"] == "ok"
    assert prev_real["kind"] == "pdf"

    svc = AttachmentService(tmp_path / "att_pdf")
    with pytest.raises(ContractViolation) as exc_att:
        svc.save_attachment("ws1", "sess1", "fake.pdf", b"NOT_PDF", mime_type="application/pdf")
    assert exc_att.value.code == "unsupported_attachment_type"


# ---------------------------------------------------------------------------
# 5. SEC-08, SEC-09 & BE-01: ReDoS Elimination, Expanded Redaction & StreamingRedactor
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_redaction_and_markdown_sanitizer_linear_time_no_redos() -> None:
    # SEC-08: URL credential ReDoS payloads
    payload_dots = "a." * 20000
    t0 = time.perf_counter()
    assert redact_text(payload_dots) == payload_dots
    elapsed_redact_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_redact_ms < 20.0, f"redact_text ReDoS regression: {elapsed_redact_ms:.2f}ms"

    t1 = time.perf_counter()
    assert _URL_CREDENTIAL.sub(r"\1[REDACTED]@", payload_dots) == payload_dots
    elapsed_raw_regex_ms = (time.perf_counter() - t1) * 1000
    assert elapsed_raw_regex_ms < 20.0, f"_URL_CREDENTIAL ReDoS regression: {elapsed_raw_regex_ms:.2f}ms"

    payload_mixed = "https://alice:topsecret@example.com/v1 " + payload_dots
    t2 = time.perf_counter()
    out_mixed = redact_text(payload_mixed)
    elapsed_mixed_ms = (time.perf_counter() - t2) * 1000
    assert "topsecret" not in out_mixed
    assert "https://[REDACTED]@example.com/v1" in out_mixed
    assert elapsed_mixed_ms < 20.0, f"Mixed URL + dots ReDoS regression: {elapsed_mixed_ms:.2f}ms"

    # SEC-08: Markdown unclosed dangerous tag payloads (~52 KB each)
    for tag_payload in ("<script>" * 6500, "<iframe>" * 6500, "<object>" * 6500, "<script src='x' " * 3200):
        tm = time.perf_counter()
        sanitized, stripped, _ = sanitize_markdown_content(tag_payload)
        elapsed_md_ms = (time.perf_counter() - tm) * 1000
        assert stripped is True
        assert "<script" not in sanitized.lower()
        assert "<iframe" not in sanitized.lower()
        assert "<object" not in sanitized.lower()
        assert elapsed_md_ms < 20.0, f"sanitize_markdown_content ReDoS regression: {elapsed_md_ms:.2f}ms"


@pytest.mark.security
def test_expanded_secret_redaction_and_benign_preservation() -> None:
    # _ASSIGNMENT compound env vars & flags vs benign metrics
    env_sample = (
        "HYDRA_API_TOKEN=my_hydra_secret_123 "
        "OMNIROUTE_API_KEY=omni_secret_456 "
        "DB_PASSWORD='super_db_password' "
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
        "max_tokens=100 prompt_tokens=50 completion_tokens=20 total_tokens=70"
    )
    scrubbed_env = redact_text(env_sample)
    for secret_val in (
        "my_hydra_secret_123",
        "omni_secret_456",
        "super_db_password",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    ):
        assert secret_val not in scrubbed_env
    for metric_pair in ("max_tokens=100", "prompt_tokens=50", "completion_tokens=20", "total_tokens=70"):
        assert metric_pair in scrubbed_env

    # _PROVIDER_TOKEN expanded formats
    provider_tokens = [
        "hydra_tok_abcdefghijklmnop123456",
        "hydra_desktop_1234567890abcdefghij",
        "AIza" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r",
        "AKIAIOSFODNN7EXAMPLE",
        "ASIAIOSFODNN7EXAMPLE",
        "ghp_0123456789abcdefghij012345",
        "gho_0123456789abcdefghij012345",
        "ghu_0123456789abcdefghij012345",
        "ghs_0123456789abcdefghij012345",
        "ghr_0123456789abcdefghij012345",
    ]
    for tok in provider_tokens:
        out = redact_text(f"auth {tok} end")
        assert tok not in out
        assert REDACTED in out

    # _SECRET_KEY dictionary redaction vs benign keys & BE-01 type preservation
    raw_dict = {
        "hydra_api_token": "tok-val-1",
        "openai_api_key": "key-val-2",
        "jwt_secret": "jwt-val-3",
        "db_password": "pwd-val-4",
        "client_secret": "cli-val-5",
        "access_token": "acc-val-6",
        "refresh_token": "ref-val-7",
        "optional_empty_token": None,
        "has_token": True,
        "secrets": True,
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
        "max_tokens": 4096,
        "max_tokens_in": 2000,
        "max_tokens_out": 1000,
        "redact_token": "keep_me",
        "token_id": "tok_id_001",
        "secret_name": "MY_ENV_SECRET",
        "secret_ref": "secref_001",
        "token_count": 3,
    }
    redacted_dict = redact(raw_dict)
    for skey in (
        "hydra_api_token",
        "openai_api_key",
        "jwt_secret",
        "db_password",
        "client_secret",
        "access_token",
        "refresh_token",
    ):
        assert redacted_dict[skey] == REDACTED

    assert redacted_dict["optional_empty_token"] is None
    assert redacted_dict["has_token"] is True
    assert redacted_dict["secrets"] is True
    assert redacted_dict["prompt_tokens"] == 120
    assert redacted_dict["completion_tokens"] == 45
    assert redacted_dict["total_tokens"] == 165
    assert redacted_dict["max_tokens"] == 4096
    assert redacted_dict["max_tokens_in"] == 2000
    assert redacted_dict["max_tokens_out"] == 1000
    assert redacted_dict["redact_token"] == "keep_me"
    assert redacted_dict["token_id"] == "tok_id_001"
    assert redacted_dict["secret_name"] == "MY_ENV_SECRET"
    assert redacted_dict["secret_ref"] == "secref_001"
    assert redacted_dict["token_count"] == 3


@pytest.mark.security
def test_streaming_redactor_handles_split_secrets_across_chunk_boundaries() -> None:
    secret_sk = "sk-proj-1234567890abcdefXYZ987654"
    prefix = " normal log line " * 12

    # Split right inside `sk-proj-...` (both before min-length and mid-token!)
    for split_at in (3, 7, 16, 24):
        sr = StreamingRedactor(holdback=96)
        c1 = prefix + secret_sk[:split_at]
        c2 = secret_sk[split_at:] + " trailing safe text\n"
        combined = sr.feed(c1) + sr.feed(c2) + sr.flush()
        assert secret_sk not in combined
        assert "abcdefXYZ987654" not in combined
        assert REDACTED in combined
        assert combined.endswith(" trailing safe text\n")

    # Even with small holdback=12, live-edge match holdback prevents slicing long tokens
    sr_small = StreamingRedactor(holdback=12)
    out_small = (
        sr_small.feed("header " + ("x " * 40) + secret_sk[:20])
        + sr_small.feed(secret_sk[20:] + " done")
        + sr_small.flush()
    )
    assert "XYZ987654" not in out_small
    assert out_small.endswith(f"{REDACTED} done")

    # Character-by-character streaming with multiple secret kinds + redaction_scope literal
    full_stream = (
        "Start HYDRA_API_TOKEN=my_split_secret_token_999 middle "
        "https://admin:splitpass123@db.internal:5432/app "
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0123456789\n-----END RSA PRIVATE KEY-----\n"
        "Literal=CUSTOM_SENTINEL_XYZ end."
    )
    with redaction_scope(["CUSTOM_SENTINEL_XYZ"]):
        sr_char = StreamingRedactor(holdback=96)
        pieces = [sr_char.feed(ch) for ch in full_stream]
        pieces.append(sr_char.flush())
        streamed_result = "".join(pieces)
        expected = redact_text(full_stream)

    assert streamed_result == expected
    for forbidden in ("my_split_secret_token_999", "splitpass123", "MIIEpAIBAAKCAQEA0123456789", "CUSTOM_SENTINEL_XYZ"):
        assert forbidden not in streamed_result
