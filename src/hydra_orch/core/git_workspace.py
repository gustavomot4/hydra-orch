"""Isolated Git worktree service, scope validation, diff capture, and serialized integration (S05 / T05)."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Union

from hydra_orch.bridge.worker_runner import is_process_alive
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.model import (
    Artifact,
    CheckResult,
    CheckSpec,
    ContractViolation,
    FailureDetail,
    IntegrationStatus,
    TaskAttempt,
    TaskResult,
    TaskSpec,
     TaskStatus,
    assert_integrable,
    transition_status,
)

logger = logging.getLogger(__name__)

_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")

WorkspaceStatusLiteral = Literal[
    "preparing",
    "ready",
    "integrating",
    "conflicted",
    "preserved",
    "cleaned",
]


def _sanitize_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RE.sub("_", value.strip())
    return cleaned.strip("._-") or "item"


def _normalize_rel_posix(path_str: str) -> str:
    normalized = path_str.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


class GitWorkspaceError(RuntimeError):
    """Structured error raised by GitWorkspaceService carrying a typed FailureDetail and details dict."""

    def __init__(
        self,
        failure: FailureDetail,
        details: Optional[Dict[str, Any]] = None,
        stderr: str = "",
    ):
        super().__init__(f"[{failure.code}] {failure.message}")
        self.failure = failure
        self.details = dict(details or {})
        self.stderr = stderr


@dataclass(frozen=True)
class OperatorCheckoutSnapshot:
    """Immutable snapshot of the operator's root Git checkout state."""

    repo_root: str
    head_sha: str
    branch: str
    status_porcelain: Tuple[str, ...]
    staged_files: Tuple[str, ...]
    unstaged_files: Tuple[str, ...]
    untracked_files: Tuple[str, ...]


@dataclass
class WorkspaceRecord:
    """Tracked Git worktree provisioned for a specific task attempt."""

    workspace_id: str
    attempt_id: str
    run_id: str
    task_id: str
    canonical_path: Path
    base_sha: str
    branch: str
    status: WorkspaceStatusLiteral = "ready"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "attempt_id": self.attempt_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "canonical_path": str(self.canonical_path),
            "base_sha": self.base_sha,
            "branch": self.branch,
            "status": self.status,
        }


@dataclass(frozen=True)
class ScopeValidationResult:
    """Result of checking worktree changes against allowed_paths, forbidden_paths, and symlink escapes."""

    valid: bool
    changed_files: Tuple[str, ...] = ()
    violations: Tuple[str, ...] = ()
    symlink_escapes: Tuple[str, ...] = ()
    forbidden_hits: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WorktreeDiffArtifact:
    """Committed patch and SHA-256 indexed diff artifact produced from a task worktree."""

    base_sha: str
    patch_commit_sha: Optional[str]
    changed_files: Tuple[str, ...]
    artifact: Optional[Artifact]
    patch_path: Optional[Path]
    has_changes: bool

    @property
    def artifact_ref(self) -> Optional[Artifact]:
        return self.artifact


@dataclass(frozen=True)
class IntegrationOutcome:
    """Auditable outcome of a serialized integration over accepted task results."""

    integration_id: str
    run_id: str
    target_branch: str
    integration_worktree_path: Path
    expected_base_sha: str
    result_sha: Optional[str]
    status: IntegrationStatus
    merged_result_ids: Tuple[str, ...] = ()
    conflicted_files: Tuple[str, ...] = ()
    checks_executed: Tuple[CheckResult, ...] = ()
    check_artifacts: Tuple[Artifact, ...] = ()
    failure: Optional[FailureDetail] = None


class GitWorkspaceService:
    """Centralized Git worktree and serialized integration manager (RT05 / S05 / T05)."""

    _repo_locks: Dict[str, asyncio.Lock] = {}

    def __init__(
        self,
        repo_root: Union[str, Path] = ".",
        runtime_dir: Union[str, Path] = ".orchestrator",
        worktree_subdir: str = "worktree",
        store: Optional[ExecutionStore] = None,
        git_author_name: str = "Hydra Orchestrator",
        git_author_email: str = "hydra-orch@localhost",
    ):
        self.repo_root = self.resolve_repo_root(repo_root)
        runtime_candidate = Path(runtime_dir)
        if not runtime_candidate.is_absolute():
            runtime_candidate = self.repo_root / runtime_candidate
        self.runtime_dir = Path(os.path.realpath(runtime_candidate))
        self.worktree_base_dir = self.runtime_dir / worktree_subdir
        self.lock_dir = self.runtime_dir / "lock"
        self.store = store
        self.git_author_name = git_author_name
        self.git_author_email = git_author_email
        self._workspaces: Dict[str, WorkspaceRecord] = {}

    @classmethod
    def _get_repo_lock(cls, canonical_repo_root: Path) -> asyncio.Lock:
        key = os.path.normcase(os.path.realpath(canonical_repo_root))
        lock = cls._repo_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._repo_locks[key] = lock
        return lock

    @staticmethod
    def _run_git_cmd(
        args: Sequence[str],
        cwd: Union[str, Path],
        extra_env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _run_git(
        self,
        args: Sequence[str],
        cwd: Optional[Union[str, Path]] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._run_git_cmd(args, cwd=cwd or self.repo_root, extra_env=extra_env)

    @classmethod
    def resolve_repo_root(cls, repo_root: Union[str, Path]) -> Path:
        """Resolve and validate that repo_root is the canonical root of a real Git repository."""
        raw_path = Path(repo_root)
        if not raw_path.exists() or not raw_path.is_dir():
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Repository root '{repo_root}' does not exist or is not a directory",
                    retryable=False,
                ),
                details={"repo_root": str(repo_root)},
            )

        real_candidate = Path(os.path.realpath(raw_path))
        res = cls._run_git_cmd(["rev-parse", "--show-toplevel"], cwd=real_candidate)
        if res.returncode != 0:
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Directory '{real_candidate}' is not a valid Git repository",
                    retryable=False,
                ),
                details={
                    "repo_root": str(real_candidate),
                    "stderr": res.stderr.strip(),
                },
                stderr=res.stderr,
            )

        git_toplevel = Path(os.path.realpath(res.stdout.strip()))
        if os.path.normcase(str(git_toplevel)) != os.path.normcase(str(real_candidate)):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Path '{real_candidate}' is a subdirectory, not the canonical repository root '{git_toplevel}'",
                    retryable=False,
                ),
                details={
                    "requested_path": str(real_candidate),
                    "git_toplevel": str(git_toplevel),
                },
            )
        return git_toplevel

    def resolve_commit_sha(self, ref: str = "HEAD", cwd: Optional[Union[str, Path]] = None) -> str:
        """Resolve a Git reference or commit SHA to a verified 40-hex commit SHA."""
        clean_ref = ref.strip()
        if not clean_ref:
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message="Git reference cannot be empty",
                    retryable=False,
                )
            )
        res = self._run_git(["rev-parse", "--verify", f"{clean_ref}^{{commit}}"], cwd=cwd)
        sha = res.stdout.strip().lower()
        if res.returncode != 0 or not _COMMIT_SHA_RE.match(sha):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Git commit reference '{clean_ref}' could not be resolved in '{cwd or self.repo_root}'",
                    retryable=False,
                ),
                details={"ref": clean_ref, "stderr": res.stderr.strip()},
                stderr=res.stderr,
            )
        return sha

    def get_current_branch(self, cwd: Optional[Union[str, Path]] = None) -> str:
        """Return the current symbolic branch name or 'HEAD' if detached."""
        res = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        if res.returncode != 0:
            raise GitWorkspaceError(
                FailureDetail(
                    code="git_operation_failed",
                    message="Failed to inspect current branch",
                    retryable=False,
                ),
                details={"stderr": res.stderr.strip()},
                stderr=res.stderr,
            )
        return res.stdout.strip()

    def snapshot_operator_checkout(self) -> OperatorCheckoutSnapshot:
        """Capture an immutable snapshot of the operator's root checkout (branch, HEAD, staged, unstaged, untracked)."""
        head_sha = self.resolve_commit_sha("HEAD", cwd=self.repo_root)
        branch = self.get_current_branch(cwd=self.repo_root)
        status_res = self._run_git(
            ["status", "--porcelain=v1", "-uall"],
            cwd=self.repo_root,
        )
        if status_res.returncode != 0:
            raise GitWorkspaceError(
                FailureDetail(
                    code="git_operation_failed",
                    message="Failed to read git status on operator checkout",
                    retryable=False,
                ),
                details={"stderr": status_res.stderr.strip()},
                stderr=status_res.stderr,
            )

        runtime_rel_prefix: Optional[str] = None
        try:
            rel_rt = self.runtime_dir.relative_to(self.repo_root)
            runtime_rel_prefix = _normalize_rel_posix(str(rel_rt))
        except ValueError:
            runtime_rel_prefix = None

        porcelain_lines: List[str] = []
        staged: List[str] = []
        unstaged: List[str] = []
        untracked: List[str] = []

        for raw_line in status_res.stdout.splitlines():
            if not raw_line.strip():
                continue
            xy = raw_line[:2]
            raw_file = raw_line[3:].strip()
            if " -> " in raw_file:
                raw_file = raw_file.split(" -> ", 1)[1].strip()
            norm_file = _normalize_rel_posix(raw_file.strip('"'))
            if runtime_rel_prefix and (
                norm_file == runtime_rel_prefix
                or norm_file.startswith(f"{runtime_rel_prefix}/")
            ):
                continue

            porcelain_lines.append(f"{xy} {norm_file}")
            if xy == "??":
                untracked.append(norm_file)
            else:
                if xy[0] != " ":
                    staged.append(norm_file)
                if xy[1] != " ":
                    unstaged.append(norm_file)

        return OperatorCheckoutSnapshot(
            repo_root=str(self.repo_root),
            head_sha=head_sha,
            branch=branch,
            status_porcelain=tuple(sorted(porcelain_lines)),
            staged_files=tuple(sorted(staged)),
            unstaged_files=tuple(sorted(unstaged)),
            untracked_files=tuple(sorted(untracked)),
        )

    def assert_operator_checkout_intact(
        self,
        before: OperatorCheckoutSnapshot,
        after: Optional[OperatorCheckoutSnapshot] = None,
    ) -> OperatorCheckoutSnapshot:
        """Verify that the operator's root checkout branch, HEAD, and working tree files are untouched."""
        current = after or self.snapshot_operator_checkout()
        if (
            current.head_sha != before.head_sha
            or current.branch != before.branch
            or current.status_porcelain != before.status_porcelain
        ):
            raise GitWorkspaceError(
                FailureDetail(
                    code="operator_checkout_mutated",
                    message="Operator checkout was unexpectedly modified during workspace operation",
                    retryable=False,
                ),
                details={
                    "before_branch": before.branch,
                    "after_branch": current.branch,
                    "before_head": before.head_sha,
                    "after_head": current.head_sha,
                    "before_status": list(before.status_porcelain),
                    "after_status": list(current.status_porcelain),
                },
            )
        return current

    def create_worktree(
        self,
        run_id: str,
        task_id: str,
        attempt_id: str,
        base_sha: str,
        branch_name: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> WorkspaceRecord:
        """
        Provision an isolated Git worktree anchored to a fixed 40-hex base_sha.
        Never falls back to creating a plain directory if `git worktree add` fails (GAP A06).
        """
        verified_sha = self.resolve_commit_sha(base_sha, cwd=self.repo_root)
        if verified_sha != base_sha.strip().lower():
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"base_sha must be an exact 40-hex commit SHA, got '{base_sha}'",
                    retryable=False,
                ),
                details={"base_sha": base_sha, "resolved_sha": verified_sha},
            )

        safe_run = _sanitize_token(run_id)
        safe_task = _sanitize_token(task_id)
        safe_attempt = _sanitize_token(attempt_id)

        raw_wt_name = f"{safe_run}_{safe_task}_{safe_attempt}"
        if len(raw_wt_name) > 44:
            digest = hashlib.sha256(f"{run_id}:{task_id}:{attempt_id}".encode("utf-8")).hexdigest()[:8]
            wt_dir_name = f"{safe_run[:12]}_{safe_task[:12]}_{digest}"
        else:
            wt_dir_name = raw_wt_name

        if branch_name:
            branch = branch_name
        else:
            raw_branch = f"hydra/{safe_run}/{safe_task}/{safe_attempt}"
            if len(raw_branch) > 48:
                digest = hashlib.sha256(f"{run_id}:{task_id}:{attempt_id}".encode("utf-8")).hexdigest()[:8]
                branch = f"hydra/{safe_run[:12]}/{safe_task[:12]}/{digest}"
            else:
                branch = raw_branch

        ws_id = workspace_id or f"ws_{wt_dir_name}"

        if os.name == "nt":
            self._run_git(["config", "core.longpaths", "true"], cwd=self.repo_root)

        self.worktree_base_dir.mkdir(parents=True, exist_ok=True)
        worktree_path = self.worktree_base_dir / wt_dir_name

        if worktree_path.exists():
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Worktree path '{worktree_path}' already exists",
                    retryable=False,
                ),
                details={"worktree_path": str(worktree_path)},
            )

        res = self._run_git(
            ["worktree", "add", "-b", branch, str(worktree_path), verified_sha],
            cwd=self.repo_root,
        )
        if res.returncode != 0:
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Failed to create real Git worktree at '{worktree_path}': {res.stderr.strip()}",
                    retryable=False,
                ),
                details={
                    "worktree_path": str(worktree_path),
                    "branch": branch,
                    "base_sha": verified_sha,
                    "stderr": res.stderr.strip(),
                },
                stderr=res.stderr,
            )

        git_marker = worktree_path / ".git"
        if not worktree_path.is_dir() or not git_marker.exists():
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Created path '{worktree_path}' is missing .git worktree link",
                    retryable=False,
                ),
                details={"worktree_path": str(worktree_path)},
            )

        wt_head = self.resolve_commit_sha("HEAD", cwd=worktree_path)
        if wt_head != verified_sha:
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Worktree HEAD '{wt_head}' does not match requested base_sha '{verified_sha}'",
                    retryable=False,
                ),
                details={"worktree_head": wt_head, "base_sha": verified_sha},
            )

        canonical_wt = Path(os.path.realpath(worktree_path))
        record = WorkspaceRecord(
            workspace_id=ws_id,
            attempt_id=attempt_id,
            run_id=run_id,
            task_id=task_id,
            canonical_path=canonical_wt,
            base_sha=verified_sha,
            branch=branch,
            status="ready",
        )
        self._workspaces[attempt_id] = record
        return record

    async def save_workspace_record(self, record: WorkspaceRecord) -> WorkspaceRecord:
        """Persist or update a WorkspaceRecord in ExecutionStore if configured."""
        if self.store is None:
            return record
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO workspaces (id, attempt_id, canonical_path, base_sha, branch, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(attempt_id) DO UPDATE SET
                        canonical_path = excluded.canonical_path,
                        base_sha = excluded.base_sha,
                        branch = excluded.branch,
                        status = excluded.status
                    """,
                    (
                        record.workspace_id,
                        record.attempt_id,
                        str(record.canonical_path),
                        record.base_sha,
                        record.branch,
                        record.status,
                    ),
                )
        return record

    def list_changed_files(
        self,
        worktree_path: Union[str, Path],
        base_sha: Optional[str] = None,
    ) -> Tuple[str, ...]:
        """Return sorted POSIX-normalized relative paths of all modified/added/deleted/untracked files in worktree."""
        wt_real = Path(os.path.realpath(worktree_path))
        changed: set[str] = set()

        if base_sha:
            diff_res = self._run_git(["diff", "--name-only", base_sha], cwd=wt_real)
            if diff_res.returncode == 0:
                for line in diff_res.stdout.splitlines():
                    norm = _normalize_rel_posix(line)
                    if norm:
                        changed.add(norm)

        status_res = self._run_git(["status", "--porcelain=v1", "-uall"], cwd=wt_real)
        if status_res.returncode != 0:
            raise GitWorkspaceError(
                FailureDetail(
                    code="git_operation_failed",
                    message=f"Failed to inspect status of worktree '{wt_real}'",
                    retryable=False,
                ),
                details={"stderr": status_res.stderr.strip()},
                stderr=status_res.stderr,
            )

        for raw_line in status_res.stdout.splitlines():
            if not raw_line.strip():
                continue
            entry = raw_line[3:].strip()
            if " -> " in entry:
                old_p, new_p = entry.split(" -> ", 1)
                old_norm = _normalize_rel_posix(old_p.strip('"'))
                new_norm = _normalize_rel_posix(new_p.strip('"'))
                if old_norm:
                    changed.add(old_norm)
                if new_norm:
                    changed.add(new_norm)
            else:
                norm = _normalize_rel_posix(entry.strip('"'))
                if norm:
                    changed.add(norm)

        return tuple(sorted(changed))

    @staticmethod
    def _matches_any_pattern(rel_posix_path: str, patterns: Iterable[str]) -> bool:
        pure_path = PurePosixPath(rel_posix_path)
        for raw_pat in patterns:
            pat = _normalize_rel_posix(raw_pat)
            if not pat:
                continue
            if pat in {"**/*", "**", "*"}:
                return True
            if fnmatch.fnmatchcase(rel_posix_path, pat) or pure_path.match(pat):
                return True
            if pat.endswith("/**"):
                prefix = pat[:-3].rstrip("/")
                if rel_posix_path == prefix or rel_posix_path.startswith(f"{prefix}/"):
                    return True
            if "/" not in pat and fnmatch.fnmatchcase(pure_path.name, pat):
                return True
        return False

    def validate_worktree_scope(
        self,
        worktree_path: Union[str, Path],
        base_sha: str,
        allowed_paths: Sequence[str] = ("**/*",),
        forbidden_paths: Sequence[str] = (),
    ) -> ScopeValidationResult:
        """Validate changed files in worktree against allowed_paths, forbidden_paths, and symlink escapes."""
        wt_real = Path(os.path.realpath(worktree_path))
        wt_norm = os.path.normcase(str(wt_real))
        changed = self.list_changed_files(wt_real, base_sha=base_sha)

        violations: List[str] = []
        symlink_escapes: List[str] = []
        forbidden_hits: List[str] = []

        candidates_to_check = set(changed)
        for root, dirs, files in os.walk(wt_real, followlinks=False):
            if ".git" in dirs:
                dirs.remove(".git")
            root_path = Path(root)
            for entry_name in [*dirs, *files]:
                full_entry = root_path / entry_name
                if full_entry.is_symlink():
                    rel_sym = _normalize_rel_posix(str(full_entry.relative_to(wt_real)))
                    candidates_to_check.add(rel_sym)

        for rel_path in sorted(candidates_to_check):
            candidate = wt_real / Path(rel_path)
            resolved_target = Path(os.path.realpath(candidate))
            resolved_norm = os.path.normcase(str(resolved_target))
            if not (
                resolved_norm == wt_norm
                or resolved_norm.startswith(wt_norm + os.sep)
            ):
                symlink_escapes.append(rel_path)
                violations.append(rel_path)
                continue

            if rel_path in changed:
                if forbidden_paths and self._matches_any_pattern(rel_path, forbidden_paths):
                    forbidden_hits.append(rel_path)
                    violations.append(rel_path)
                    continue
                if not self._matches_any_pattern(rel_path, allowed_paths):
                    violations.append(rel_path)

        unique_violations = tuple(sorted(set(violations)))
        return ScopeValidationResult(
            valid=len(unique_violations) == 0,
            changed_files=changed,
            violations=unique_violations,
            symlink_escapes=tuple(sorted(set(symlink_escapes))),
            forbidden_hits=tuple(sorted(set(forbidden_hits))),
        )

    def capture_and_commit_patch(
        self,
        record: WorkspaceRecord,
        commit_message: str,
        allowed_paths: Sequence[str] = ("**/*",),
        forbidden_paths: Sequence[str] = (),
        artifact_id: Optional[str] = None,
    ) -> WorktreeDiffArtifact:
        """
        Validate scope, commit all worktree changes to the task branch, and write a SHA-256 patch artifact.
        Preserves the worktree and raises GitWorkspaceError(code='scope_violation') if scope validation fails.
        """
        scope_res = self.validate_worktree_scope(
            record.canonical_path,
            base_sha=record.base_sha,
            allowed_paths=allowed_paths,
            forbidden_paths=forbidden_paths,
        )
        if not scope_res.valid:
            record.status = "preserved"
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=(
                        f"Worktree '{record.canonical_path}' modified files outside allowed scope: "
                        f"{', '.join(scope_res.violations)}"
                    ),
                    retryable=False,
                ),
                details={
                    "violations": list(scope_res.violations),
                    "symlink_escapes": list(scope_res.symlink_escapes),
                    "forbidden_hits": list(scope_res.forbidden_hits),
                },
            )

        status_res = self._run_git(
            ["status", "--porcelain=v1", "-uall"],
            cwd=record.canonical_path,
        )
        has_uncommitted = bool(status_res.stdout.strip())

        if has_uncommitted:
            add_res = self._run_git(["add", "-A"], cwd=record.canonical_path)
            if add_res.returncode != 0:
                raise GitWorkspaceError(
                    FailureDetail(
                        code="git_operation_failed",
                        message=f"git add -A failed in worktree '{record.canonical_path}'",
                        retryable=False,
                    ),
                    details={"stderr": add_res.stderr.strip()},
                    stderr=add_res.stderr,
                )

            git_env = {
                "GIT_AUTHOR_NAME": self.git_author_name,
                "GIT_AUTHOR_EMAIL": self.git_author_email,
                "GIT_COMMITTER_NAME": self.git_author_name,
                "GIT_COMMITTER_EMAIL": self.git_author_email,
            }
            commit_res = self._run_git(
                ["commit", "-m", commit_message.strip() or f"feat({record.task_id}): apply task changes"],
                cwd=record.canonical_path,
                extra_env=git_env,
            )
            if commit_res.returncode != 0:
                raise GitWorkspaceError(
                    FailureDetail(
                        code="git_operation_failed",
                        message=f"git commit failed in worktree '{record.canonical_path}': {commit_res.stderr.strip()}",
                        retryable=False,
                    ),
                    details={"stderr": commit_res.stderr.strip()},
                    stderr=commit_res.stderr,
                )

        head_after = self.resolve_commit_sha("HEAD", cwd=record.canonical_path)
        if head_after == record.base_sha and not scope_res.changed_files:
            return WorktreeDiffArtifact(
                base_sha=record.base_sha,
                patch_commit_sha=None,
                changed_files=(),
                artifact=None,
                patch_path=None,
                has_changes=False,
            )

        diff_res = self._run_git(
            ["diff", "--binary", f"{record.base_sha}..{head_after}"],
            cwd=record.canonical_path,
        )
        if diff_res.returncode != 0:
            raise GitWorkspaceError(
                FailureDetail(
                    code="git_operation_failed",
                    message=f"git diff failed between '{record.base_sha}' and '{head_after}'",
                    retryable=False,
                ),
                details={"stderr": diff_res.stderr.strip()},
                stderr=diff_res.stderr,
            )

        safe_run = _sanitize_token(record.run_id)
        safe_attempt = _sanitize_token(record.attempt_id)
        patches_dir = self.runtime_dir / "run" / safe_run / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)

        patch_file = patches_dir / f"{safe_attempt}.patch"
        patch_bytes = diff_res.stdout.encode("utf-8")
        temp_patch = patches_dir / f".{safe_attempt}.patch.tmp"
        temp_patch.write_bytes(patch_bytes)
        temp_patch.replace(patch_file)

        sha256_hex = hashlib.sha256(patch_bytes).hexdigest()
        try:
            rel_path = _normalize_rel_posix(str(patch_file.relative_to(self.repo_root)))
        except ValueError:
            rel_path = f".orchestrator/run/{safe_run}/patches/{safe_attempt}.patch"

        art_obj = Artifact(
            artifact_id=artifact_id or f"art_patch_{safe_attempt}",
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            kind="patch",
            relative_path=rel_path,
            sha256=sha256_hex,
            size_bytes=len(patch_bytes),
        )
        return WorktreeDiffArtifact(
            base_sha=record.base_sha,
            patch_commit_sha=head_after,
            changed_files=scope_res.changed_files,
            artifact=art_obj,
            patch_path=patch_file,
            has_changes=True,
        )

    def has_unpreserved_changes(self, worktree_path: Union[str, Path], base_sha: str) -> bool:
        """Return True if the worktree has uncommitted changes."""
        wt_real = Path(os.path.realpath(worktree_path))
        if not wt_real.exists():
            return False
        status_res = self._run_git(["status", "--porcelain=v1", "-uall"], cwd=wt_real)
        if status_res.returncode != 0 or status_res.stdout.strip():
            return True
        return False

    def cleanup_worktree(
        self,
        record: WorkspaceRecord,
        force_discard: bool = False,
        delete_branch: bool = False,
    ) -> WorkspaceRecord:
        """
        Safely remove a task worktree inside worktree_base_dir.
        Refuses to delete a dirty worktree with uncommitted changes unless force_discard=True (GAP A05).
        """
        wt_real = Path(os.path.realpath(record.canonical_path))
        base_norm = os.path.normcase(str(os.path.realpath(self.worktree_base_dir)))
        wt_norm = os.path.normcase(str(wt_real))

        if not wt_norm.startswith(base_norm + os.sep):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Refusing to clean worktree '{wt_real}' outside worktree_base_dir '{self.worktree_base_dir}'",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real)},
            )

        if wt_real.exists():
            status_res = self._run_git(["status", "--porcelain=v1", "-uall"], cwd=wt_real)
            is_dirty = status_res.returncode != 0 or bool(status_res.stdout.strip())
            if is_dirty and not force_discard:
                record.status = "preserved"
                raise GitWorkspaceError(
                    FailureDetail(
                        code="dirty_worktree_preserved",
                        message=(
                            f"Worktree '{wt_real}' has uncommitted changes and force_discard=False; "
                            "preserving worktree to prevent data loss"
                        ),
                        retryable=False,
                    ),
                    details={
                        "worktree_path": str(wt_real),
                        "status_porcelain": status_res.stdout.splitlines(),
                    },
                )

            rm_args = ["worktree", "remove"]
            if force_discard:
                rm_args.append("--force")
            rm_args.append(str(wt_real))
            rm_res = self._run_git(rm_args, cwd=self.repo_root)
            if rm_res.returncode != 0 and force_discard and wt_real.exists():
                shutil.rmtree(wt_real, ignore_errors=True)
            elif rm_res.returncode != 0:
                record.status = "preserved"
                raise GitWorkspaceError(
                    FailureDetail(
                        code="dirty_worktree_preserved",
                        message=f"git worktree remove refused for '{wt_real}': {rm_res.stderr.strip()}",
                        retryable=False,
                    ),
                    details={"stderr": rm_res.stderr.strip()},
                    stderr=rm_res.stderr,
                )

            self._run_git(["worktree", "prune"], cwd=self.repo_root)

        if delete_branch and record.branch:
            branch_flag = "-D" if force_discard else "-d"
            self._run_git(["branch", branch_flag, record.branch], cwd=self.repo_root)

        record.status = "cleaned"
        return record

    def create_lock_file(self, lock_name: str, pid: Optional[int] = None) -> Path:
        """Create a PID-stamped lock file inside .orchestrator/lock/."""
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _sanitize_token(lock_name)
        lock_path = self.lock_dir / f"{safe_name}.lock"
        payload = {
            "pid": pid if pid is not None else os.getpid(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo_root": str(self.repo_root),
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        return lock_path

    def cleanup_stale_locks(self) -> Tuple[Path, ...]:
        """
        Inspect .orchestrator/lock/*.lock and .git/worktrees/*/locked, removing stale locks
        owned by dead processes and pruning stale worktree metadata.
        """
        removed: List[Path] = []
        if self.lock_dir.exists():
            for lock_file in sorted(self.lock_dir.glob("*.lock")):
                should_remove = False
                try:
                    data = json.loads(lock_file.read_text(encoding="utf-8"))
                    lock_pid = int(data.get("pid", -1))
                    if lock_pid <= 0 or not is_process_alive(lock_pid):
                        should_remove = True
                except Exception:
                    should_remove = True

                if should_remove:
                    try:
                        lock_file.unlink()
                        removed.append(lock_file)
                    except OSError:
                        pass

        git_worktrees_admin = self.repo_root / ".git" / "worktrees"
        if git_worktrees_admin.exists():
            for wt_admin in sorted(git_worktrees_admin.iterdir()):
                if not wt_admin.is_dir():
                    continue
                gitdir_file = wt_admin / "gitdir"
                locked_file = wt_admin / "locked"
                if locked_file.exists() and gitdir_file.exists():
                    try:
                        target_git = Path(gitdir_file.read_text(encoding="utf-8").strip())
                        if not target_git.exists():
                            locked_file.unlink()
                            removed.append(locked_file)
                    except OSError:
                        pass

        self._run_git(["worktree", "prune"], cwd=self.repo_root)
        return tuple(removed)

    def restore_attempt_state(self, source: Path, target: WorkspaceRecord, *,
                              allowed_paths: Sequence[str], forbidden_paths: Sequence[str] = ()) -> None:
        """Copy verified tracked/untracked changes to a new worktree; keep the source intact."""
        source = self.resolve_repo_root(source)
        scope = self.validate_worktree_scope(source, base_sha=target.base_sha,
            allowed_paths=allowed_paths, forbidden_paths=forbidden_paths)
        if not scope.valid:
            raise ContractViolation("handoff_scope_violation", "Unsafe source state requires manual reconciliation")
        patch = subprocess.run(["git", "diff", "--binary", "--no-ext-diff", target.base_sha],
            cwd=source, capture_output=True, check=True).stdout
        if patch:
            applied = subprocess.run(["git", "apply", "--binary", "-"], cwd=target.canonical_path,
                input=patch, capture_output=True)
            if applied.returncode:
                raise ContractViolation("handoff_conflict", "Cannot restore partial patch; both worktrees are preserved")
        untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=source, capture_output=True, check=True).stdout
        for raw in untracked.split(b"\0"):
            if not raw:
                continue
            relative = raw.decode("utf-8")
            src, dest = source / relative, target.canonical_path / relative
            if src.is_symlink() or not src.is_file() or dest.exists():
                raise ContractViolation("handoff_conflict", "Untracked state cannot be restored safely")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        restored = self.validate_worktree_scope(target.canonical_path, base_sha=target.base_sha,
            allowed_paths=allowed_paths, forbidden_paths=forbidden_paths)
        if not restored.valid:
            raise ContractViolation("handoff_scope_violation", "Restored state is outside the task scope")

    @staticmethod
    def _validate_integrable_result(
        result: TaskResult,
        expected_base_sha: str,
        task_spec: Optional[TaskSpec] = None,
        attempt: Optional[TaskAttempt] = None,
        verified_base_shas: Sequence[str] = (),
    ) -> None:
        if task_spec is not None and attempt is not None:
            assert_integrable(task_spec, attempt, result)
        if result.task_status != TaskStatus.ACCEPTED or result.simulated:
            raise ContractViolation(
                "result_not_accepted",
                f"Result '{result.result_id}' must be accepted and non-simulated before integration",
            )
        if result.base_sha not in {expected_base_sha, *verified_base_shas}:
            raise ContractViolation(
                "base_sha_mismatch",
                f"Result '{result.result_id}' base_sha '{result.base_sha}' does not match expected '{expected_base_sha}'",
            )
        if not result.patch_commit_sha or result.patch_commit_sha == expected_base_sha:
            raise ContractViolation(
                "missing_patch_commit",
                f"Result '{result.result_id}' has no distinct patch_commit_sha to integrate",
            )

    async def integrate_results(
        self,
        run_id: str,
        expected_base_sha: str,
        results: Sequence[TaskResult],
        target_branch: Optional[str] = None,
        integration_id: Optional[str] = None,
        post_merge_checks: Sequence[CheckSpec] = (),
        verified_base_shas: Sequence[str] = (),
        check_runner: Optional[Callable[[Path, str, Sequence[CheckSpec]], Tuple[CheckResult, ...]]] = None,
    ) -> IntegrationOutcome:
        """
        Serialize integration of accepted TaskResults into a dedicated integration worktree/branch
        (`integrate/<run_id>`), never checking out or mutating the operator's root checkout.
        Preserves worktrees on conflict or check failure.
        """
        repo_lock = self._get_repo_lock(self.repo_root)
        async with repo_lock:
            self.cleanup_stale_locks()
            lock_file = self.create_lock_file(f"integrate_{_sanitize_token(run_id)}")
            try:
                return await self._integrate_results_locked(
                    run_id=run_id,
                    expected_base_sha=expected_base_sha,
                    results=results,
                    target_branch=target_branch,
                    integration_id=integration_id,
                    post_merge_checks=post_merge_checks,
                    check_runner=check_runner,
                    verified_base_shas=verified_base_shas,
                )
            finally:
                try:
                    if lock_file.exists():
                        lock_file.unlink()
                except OSError:
                    pass

    async def _integrate_results_locked(
        self,
        run_id: str,
        expected_base_sha: str,
        results: Sequence[TaskResult],
        target_branch: Optional[str] = None,
        integration_id: Optional[str] = None,
        post_merge_checks: Sequence[CheckSpec] = (),
        verified_base_shas: Sequence[str] = (),
        check_runner: Optional[Callable[[Path, str, Sequence[CheckSpec]], Tuple[CheckResult, ...]]] = None,
    ) -> IntegrationOutcome:
        verified_base = self.resolve_commit_sha(expected_base_sha, cwd=self.repo_root)
        safe_run = _sanitize_token(run_id)
        int_id = integration_id or f"int_{safe_run}"
        branch = target_branch or (f"integrate/{safe_run}-{_sanitize_token(int_id)}" if integration_id else f"integrate/{safe_run}")
        int_wt_path = self.worktree_base_dir / f"integrate_{safe_run[:32]}_{hashlib.sha256(int_id.encode()).hexdigest()[:12]}"

        for allowed_base in verified_base_shas:
            if self.store is None:
                raise ContractViolation("base_sha_mismatch", "Nonoriginal bases require a canonical integration record")
            async with self.store._connect() as db:
                proof = await (await db.execute("SELECT 1 FROM integrations WHERE run_id=? AND result_sha=? AND status='integrated'", (run_id, allowed_base))).fetchone()
            ancestor = self._run_git(["merge-base", "--is-ancestor", verified_base, allowed_base])
            if not proof or ancestor.returncode != 0:
                raise ContractViolation("base_sha_mismatch", "Execution base is not a verified integration of this run")
        for result in results:
            self._validate_integrable_result(result, expected_base_sha=verified_base, verified_base_shas=verified_base_shas)

        self.worktree_base_dir.mkdir(parents=True, exist_ok=True)
        if int_wt_path.exists():
            raise ContractViolation("integration_workspace_exists", "Prior integration evidence is preserved; choose a new integration ID")
        existing_branch = self._run_git(["show-ref", "--verify", f"refs/heads/{branch}"])
        if existing_branch.returncode == 0:
            raise ContractViolation("integration_branch_exists", "Integration branch already exists; never overwrite it implicitly")
        add_res = self._run_git(
            ["worktree", "add", "-b", branch, str(int_wt_path), verified_base],
            cwd=self.repo_root,
        )
        if add_res.returncode != 0:
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Failed to create integration worktree at '{int_wt_path}': {add_res.stderr.strip()}",
                    retryable=False,
                ),
                details={"stderr": add_res.stderr.strip()},
                stderr=add_res.stderr,
            )

        int_wt_real = Path(os.path.realpath(int_wt_path))
        status = transition_status(IntegrationStatus.NOT_INTEGRATED, IntegrationStatus.INTEGRATING)
        merged_ids: List[str] = []
        git_env = {
            "GIT_AUTHOR_NAME": self.git_author_name,
            "GIT_AUTHOR_EMAIL": self.git_author_email,
            "GIT_COMMITTER_NAME": self.git_author_name,
            "GIT_COMMITTER_EMAIL": self.git_author_email,
        }

        for result in results:
            ws_record = self._workspaces.get(result.attempt_id)
            if ws_record is not None:
                ws_record.status = "integrating"

            assert result.patch_commit_sha is not None
            merge_res = self._run_git(
                [
                    "merge",
                    "--no-ff",
                    result.patch_commit_sha,
                    "-m",
                    f"feat(integrate): merge result {result.result_id} attempt {result.attempt_id}",
                ],
                cwd=int_wt_real,
                extra_env=git_env,
            )
            if merge_res.returncode != 0:
                conflict_res = self._run_git(
                    ["diff", "--name-only", "--diff-filter=U"],
                    cwd=int_wt_real,
                )
                conflicted_files = tuple(
                    sorted(
                        _normalize_rel_posix(line)
                        for line in conflict_res.stdout.splitlines()
                        if line.strip()
                    )
                )
                self._run_git(["merge", "--abort"], cwd=int_wt_real)
                if ws_record is not None:
                    ws_record.status = "conflicted"

                status = transition_status(status, IntegrationStatus.CONFLICTED)
                failure = FailureDetail(
                    code="merge_conflict",
                    message=(
                        f"Merge conflict while integrating result '{result.result_id}' "
                        f"(commit {result.patch_commit_sha})"
                    ),
                    retryable=False,
                )
                outcome = IntegrationOutcome(
                    integration_id=int_id,
                    run_id=run_id,
                    target_branch=branch,
                    integration_worktree_path=int_wt_real,
                    expected_base_sha=verified_base,
                    result_sha=None,
                    status=status,
                    merged_result_ids=tuple(merged_ids),
                    conflicted_files=conflicted_files,
                    failure=failure,
                )
                await self._persist_integration_outcome(outcome, results)
                return outcome

            merged_ids.append(result.result_id)
            if ws_record is not None:
                ws_record.status = "preserved"

        final_sha = self.resolve_commit_sha("HEAD", cwd=int_wt_real)
        executed_checks: Tuple[CheckResult, ...] = ()
        check_artifacts: Tuple[Artifact, ...] = ()
        if post_merge_checks and check_runner is not None:
            raw_check_out = check_runner(int_wt_real, final_sha, post_merge_checks)
            if asyncio.iscoroutine(raw_check_out):
                raw_check_out = await raw_check_out
            if (
                isinstance(raw_check_out, tuple)
                and len(raw_check_out) == 2
                and isinstance(raw_check_out[0], (tuple, list))
                and (not raw_check_out[0] or isinstance(raw_check_out[0][0], CheckResult))
                and isinstance(raw_check_out[1], (tuple, list))
            ):
                executed_checks = tuple(raw_check_out[0])
                check_artifacts = tuple(raw_check_out[1])
            else:
                executed_checks = tuple(raw_check_out)

            failed_checks = [c for c in executed_checks if c.exit_code != 0]
            if failed_checks:
                status = transition_status(status, IntegrationStatus.FAILED)
                failure = FailureDetail(
                    code="post_merge_check_failed",
                    message=f"Post-merge checks failed on integration branch '{branch}'",
                    retryable=False,
                )
                outcome = IntegrationOutcome(
                    integration_id=int_id,
                    run_id=run_id,
                    target_branch=branch,
                    integration_worktree_path=int_wt_real,
                    expected_base_sha=verified_base,
                    result_sha=final_sha,
                    status=status,
                    merged_result_ids=tuple(merged_ids),
                    checks_executed=executed_checks,
                    check_artifacts=check_artifacts,
                    failure=failure,
                )
                await self._persist_integration_outcome(outcome, results)
                return outcome

        status = transition_status(status, IntegrationStatus.INTEGRATED)
        outcome = IntegrationOutcome(
            integration_id=int_id,
            run_id=run_id,
            target_branch=branch,
            integration_worktree_path=int_wt_real,
            expected_base_sha=verified_base,
            result_sha=final_sha,
            status=status,
            merged_result_ids=tuple(merged_ids),
            checks_executed=executed_checks,
            check_artifacts=check_artifacts,
            failure=None,
        )
        await self._persist_integration_outcome(outcome, results)
        return outcome

    async def _persist_integration_outcome(
        self,
        outcome: IntegrationOutcome,
        results: Sequence[TaskResult],
    ) -> None:
        if self.store is None:
            return
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    """
                    INSERT INTO integrations (id, run_id, workspace_path, expected_base_sha, result_sha, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        workspace_path = excluded.workspace_path,
                        result_sha = excluded.result_sha,
                        status = excluded.status
                    """,
                    (
                        outcome.integration_id,
                        outcome.run_id,
                        str(outcome.integration_worktree_path),
                        outcome.expected_base_sha,
                        outcome.result_sha,
                        outcome.status.value,
                    ),
                )
                for art in outcome.check_artifacts:
                    await self.store._upsert_artifact_in_tx(db, art)
                for chk in outcome.checks_executed:
                    chk_row_id = f"chk-{outcome.integration_id}-{chk.check_id}"
                    cur_art = await db.execute(
                        "SELECT id FROM artifacts WHERE id = ?",
                        (chk.stdout_artifact_id,),
                    )
                    stdout_id = chk.stdout_artifact_id if await cur_art.fetchone() is not None else None
                    cur_err = await db.execute(
                        "SELECT id FROM artifacts WHERE id = ?",
                        (chk.stderr_artifact_id,),
                    )
                    stderr_id = chk.stderr_artifact_id if await cur_err.fetchone() is not None else None
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO check_results (
                            id, result_id, integration_id, check_id, command_json, cwd,
                            tested_sha, exit_code, duration_seconds,
                            stdout_artifact_id, stderr_artifact_id, output_artifact_id,
                            started_at, finished_at
                        )
                        VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                        """,
                        (
                            chk_row_id,
                            outcome.integration_id,
                            chk.check_id,
                            json.dumps(list(chk.command)),
                            chk.cwd,
                            chk.tested_sha,
                            chk.exit_code,
                            chk.duration_seconds,
                            stdout_id,
                            stderr_id,
                            stdout_id,
                        ),
                    )
                for pos, res in enumerate(results, start=1):
                    cur = await db.execute("SELECT 1 FROM results WHERE id = ?", (res.result_id,))
                    if await cur.fetchone() is not None:
                        await db.execute(
                            """
                            INSERT OR IGNORE INTO integration_items (integration_id, result_id, position)
                            VALUES (?, ?, ?)
                            """,
                            (outcome.integration_id, res.result_id, pos),
                        )
                ev_type = (
                    "merge.completed"
                    if outcome.status == IntegrationStatus.INTEGRATED
                    else "merge.conflicted"
                    if outcome.status == IntegrationStatus.CONFLICTED
                    else "check.finished"
                )
                await self.store._insert_event_in_tx(
                    db,
                    run_id=outcome.run_id,
                    event_type=ev_type,
                    payload={
                        "integration_id": outcome.integration_id,
                        "status": outcome.status.value,
                        "target_branch": outcome.target_branch,
                        "expected_base_sha": outcome.expected_base_sha,
                        "result_sha": outcome.result_sha,
                        "merged_result_ids": list(outcome.merged_result_ids),
                        "conflicted_files": list(outcome.conflicted_files),
                    },
                )
