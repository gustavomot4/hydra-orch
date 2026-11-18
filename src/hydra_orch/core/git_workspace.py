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
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Union


def _strip_win_long_prefix(path_str: str) -> str:
    if path_str.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path_str[8:]
    if path_str.startswith("\\\\?\\"):
        return path_str[4:]
    return path_str


def win_long_path(p: Path) -> Path:
    """Return a `\\\\?\\`-prefixed Path on Windows when the resolved path length is >= 240."""
    if os.name != "nt":
        return p
    raw = str(p)
    if raw.startswith("\\\\?\\"):
        return p
    abs_str = os.path.abspath(raw)
    needs_prefix = len(abs_str) >= 240
    if not needs_prefix:
        try:
            resolved_str = _strip_win_long_prefix(str(p.resolve(strict=False)))
            needs_prefix = len(resolved_str) >= 240
        except OSError:
            needs_prefix = False
    if not needs_prefix:
        return p
    if abs_str.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + abs_str[2:])
    return Path("\\\\?\\" + abs_str)


def is_link_or_junction(path: Union[Path, os.DirEntry[str], str]) -> bool:
    """Return True if `path` is a symbolic link or an NTFS junction point."""
    try:
        if isinstance(path, os.DirEntry):
            if path.is_symlink():
                return True
            is_junc_entry = getattr(path, "is_junction", None)
            if callable(is_junc_entry) and is_junc_entry():
                return True
            p = Path(path.path)
        else:
            p = path if isinstance(path, Path) else Path(path)
        lp = win_long_path(p)
        if lp.is_symlink():
            return True
        is_junc = getattr(lp, "is_junction", None)
        if callable(is_junc) and is_junc():
            return True
        return False
    except OSError:
        return False


def ensure_empty_git_hooks_dir(preferred_dir: Optional[Path] = None) -> Path:
    """Ensure and return a verified, empty directory for `core.hooksPath`."""
    candidate = preferred_dir
    if candidate is not None and os.name == "nt" and len(os.path.abspath(str(candidate))) >= 220:
        candidate = None
    if candidate is None:
        candidate = Path(tempfile.gettempdir()) / f"hydra_orch_empty_git_hooks_{os.getpid()}"
    if is_link_or_junction(candidate):
        raise RuntimeError(f"Refusing symlink/junction git hooks directory: {candidate}")
    lp = win_long_path(candidate)
    lp.mkdir(parents=True, exist_ok=True)
    with os.scandir(lp) as entries:
        for entry in entries:
            entry_p = win_long_path(candidate / entry.name)
            if is_link_or_junction(entry):
                try:
                    entry_p.unlink()
                except OSError:
                    os.rmdir(entry_p)
            elif entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry_p, ignore_errors=True)
            else:
                entry_p.unlink(missing_ok=True)
    return Path(_strip_win_long_prefix(os.path.realpath(lp)))


def build_hardened_git_prefix(hooks_dir: Path) -> Tuple[str, ...]:
    """Global hardened `git -c ...` options disabling hooks, fsmonitor, and `file://` transport."""
    return (
        "-c",
        f"core.hooksPath={hooks_dir.as_posix()}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "core.longpaths=true",
    )


from hydra_orch.bridge.worker_runner import filter_worker_env, is_process_alive
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
class ThreeWayFileConflict:
    """Three-way content and conflict hunk snapshot for a single conflicted path."""

    path: str
    base_content: Optional[str] = None
    ours_content: Optional[str] = None
    theirs_content: Optional[str] = None
    merged_preview: str = ""
    hunks: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ThreeWayInspection:
    """Non-destructive 3-way conflict inspection result computed without mutating checkouts."""

    base_sha: str
    ours_sha: str
    theirs_sha: str
    has_conflicts: bool
    conflicted_files: Tuple[str, ...] = ()
    file_conflicts: Tuple[ThreeWayFileConflict, ...] = ()


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
    ours_sha: Optional[str] = None
    theirs_sha: Optional[str] = None


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
        self.runtime_dir = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(runtime_candidate))))
        self.worktree_base_dir = self.runtime_dir / worktree_subdir
        self.lock_dir = self.runtime_dir / "lock"
        self.empty_hooks_dir = self.runtime_dir / "empty_git_hooks"
        self.store = store
        self.git_author_name = git_author_name
        self.git_author_email = git_author_email
        self._workspaces: Dict[str, WorkspaceRecord] = {}

    @classmethod
    def _get_repo_lock(cls, canonical_repo_root: Path) -> asyncio.Lock:
        key = os.path.normcase(_strip_win_long_prefix(os.path.realpath(win_long_path(canonical_repo_root))))
        lock = cls._repo_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._repo_locks[key] = lock
        return lock

    @staticmethod
    def _validate_branch_name(branch: str) -> str:
        if not isinstance(branch, str):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message="Git branch name must be a string",
                    retryable=False,
                ),
                details={"branch": str(branch)},
            )
        clean = branch.strip()
        parts = clean.split("/") if clean else []
        if (
            not clean
            or clean != branch
            or clean in {"@", "HEAD"}
            or clean.startswith(("-", "/", "."))
            or clean.endswith(("/", ".", ".lock"))
            or ".." in clean
            or "//" in clean
            or "@{" in clean
            or "\\" in clean
            or any(ch in clean for ch in ("~", "^", ":", "?", "*", "[", "\x00"))
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in clean)
            or any(not seg or seg.startswith(".") or seg.endswith(".lock") for seg in parts)
        ):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Invalid Git branch name: '{branch}'",
                    retryable=False,
                ),
                details={"branch": branch},
            )
        return clean

    @staticmethod
    def _run_git_cmd(
        args: Sequence[str],
        cwd: Union[str, Path],
        extra_env: Optional[Dict[str, str]] = None,
        *,
        hooks_dir: Optional[Path] = None,
    ) -> subprocess.CompletedProcess[str]:
        managed_hooks = ensure_empty_git_hooks_dir(hooks_dir)
        env = filter_worker_env(allowed_env=extra_env)
        env["GIT_TERMINAL_PROMPT"] = "0"
        prefix = build_hardened_git_prefix(managed_hooks)
        return subprocess.run(
            ["git", *prefix, *args],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
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
        return self._run_git_cmd(
            args,
            cwd=cwd or self.repo_root,
            extra_env=extra_env,
            hooks_dir=self.empty_hooks_dir,
        )

    def _run_git_bytes(
        self,
        args: Sequence[str],
        cwd: Union[str, Path],
        *,
        input_bytes: Optional[bytes] = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        managed_hooks = ensure_empty_git_hooks_dir(self.empty_hooks_dir)
        env = filter_worker_env()
        env["GIT_TERMINAL_PROMPT"] = "0"
        prefix = build_hardened_git_prefix(managed_hooks)
        return subprocess.run(
            ["git", *prefix, *args],
            cwd=str(cwd),
            env=env,
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            capture_output=True,
            check=check,
        )

    def _resolve_git_common_dir(self) -> Path:
        """Resolve the trusted repository's common Git directory (supports standard repos, nested worktrees, and --separate-git-dir)."""
        repo_dot_git = self.repo_root / ".git"
        lp_repo_dot_git = win_long_path(repo_dot_git)
        if lp_repo_dot_git.is_dir():
            return repo_dot_git
        if lp_repo_dot_git.is_file():
            try:
                raw = lp_repo_dot_git.read_text(encoding="utf-8", errors="strict").strip()
            except (OSError, UnicodeDecodeError):
                return repo_dot_git
            if raw.startswith("gitdir:"):
                ptr_raw = raw[len("gitdir:"):].strip()
                gitdir = Path(ptr_raw) if Path(ptr_raw).is_absolute() else (self.repo_root / ptr_raw)
                commondir_file = win_long_path(gitdir / "commondir")
                if commondir_file.is_file():
                    try:
                        common_rel = commondir_file.read_text(encoding="utf-8", errors="strict").strip()
                        if common_rel:
                            return Path(common_rel) if Path(common_rel).is_absolute() else (gitdir / common_rel)
                    except (OSError, UnicodeDecodeError):
                        pass
                return gitdir
        return repo_dot_git

    def _verify_worktree_git_file(self, worktree_path: Union[str, Path]) -> Path:
        """Verify `wt / '.git'` is an untampered regular gitdir pointer into `repo_root/.git/worktrees`."""
        raw_wt = Path(worktree_path)
        if is_link_or_junction(raw_wt):
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree path '{raw_wt}' was replaced with a symlink or NTFS junction",
                    retryable=False,
                ),
                details={"worktree_path": str(raw_wt)},
            )

        wt_real = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(raw_wt))))
        dot_git = wt_real / ".git"
        lp_dot_git = win_long_path(dot_git)
        if is_link_or_junction(dot_git):
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree .git entry at '{dot_git}' is a symlink or NTFS junction",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real), "dot_git": str(dot_git)},
            )

        try:
            st = os.lstat(lp_dot_git)
        except OSError as exc:
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree .git file missing or inaccessible in '{wt_real}'",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real), "error": str(exc)},
            ) from exc

        if not stat.S_ISREG(st.st_mode) or st.st_size <= 0 or st.st_size > 4096:
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree .git entry at '{dot_git}' is not a valid regular gitdir file",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real), "dot_git": str(dot_git)},
            )

        try:
            raw_text = lp_dot_git.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree .git file at '{dot_git}' could not be decoded safely",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real)},
            ) from exc

        stripped = raw_text.strip()
        if (
            "\x00" in raw_text
            or "\n" in stripped
            or "\r" in stripped
            or not stripped.startswith("gitdir:")
        ):
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree .git file at '{dot_git}' has tampered gitdir content",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real)},
            )

        gitdir_raw = stripped[len("gitdir:"):].strip()
        if not gitdir_raw:
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree .git file at '{dot_git}' has empty gitdir pointer",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real)},
            )

        candidate_gitdir = Path(gitdir_raw) if Path(gitdir_raw).is_absolute() else (wt_real / gitdir_raw)
        if is_link_or_junction(candidate_gitdir):
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=f"Worktree gitdir target '{candidate_gitdir}' is a symlink or NTFS junction",
                    retryable=False,
                ),
                details={"worktree_path": str(wt_real), "gitdir": str(candidate_gitdir)},
            )

        admin_root = self._resolve_git_common_dir() / "worktrees"
        resolved_admin_root = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(admin_root))))
        resolved_gitdir = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(candidate_gitdir))))
        norm_admin_root = os.path.normcase(str(resolved_admin_root))
        norm_gitdir = os.path.normcase(str(resolved_gitdir))

        if (
            not win_long_path(resolved_admin_root).is_dir()
            or not win_long_path(resolved_gitdir).is_dir()
            or norm_gitdir == norm_admin_root
            or not norm_gitdir.startswith(norm_admin_root + os.sep)
        ):
            raise GitWorkspaceError(
                FailureDetail(
                    code="scope_violation",
                    message=(
                        f"Worktree .git pointer '{resolved_gitdir}' escapes authorized "
                        f"worktrees admin directory '{resolved_admin_root}'"
                    ),
                    retryable=False,
                ),
                details={
                    "worktree_path": str(wt_real),
                    "resolved_gitdir": str(resolved_gitdir),
                    "expected_admin_root": str(resolved_admin_root),
                },
            )

        return wt_real

    @classmethod
    def resolve_repo_root(cls, repo_root: Union[str, Path]) -> Path:
        """Resolve and validate that repo_root is the canonical root of a real Git repository."""
        raw_path = Path(repo_root)
        lp_raw = win_long_path(raw_path)
        if not lp_raw.exists() or not lp_raw.is_dir():
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Repository root '{repo_root}' does not exist or is not a directory",
                    retryable=False,
                ),
                details={"repo_root": str(repo_root)},
            )

        real_candidate = Path(_strip_win_long_prefix(os.path.realpath(lp_raw)))
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

        git_toplevel = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(Path(res.stdout.strip())))))
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
        if not isinstance(ref, str):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message="Git reference must be a string",
                    retryable=False,
                )
            )
        clean_ref = ref.strip()
        if (
            not clean_ref
            or clean_ref.startswith("-")
            or "\x00" in clean_ref
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in clean_ref)
        ):
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Invalid or unsafe Git reference '{ref}'",
                    retryable=False,
                ),
                details={"ref": ref},
            )
        res = self._run_git(
            ["rev-parse", "--verify", "--end-of-options", f"{clean_ref}^{{commit}}"],
            cwd=cwd,
        )
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
        digest = hashlib.sha256(f"{run_id}:{task_id}:{attempt_id}".encode("utf-8")).hexdigest()[:8]
        if len(raw_wt_name) > 44:
            wt_dir_name = f"{safe_run[:12]}_{safe_task[:12]}_{digest}"
        else:
            wt_dir_name = raw_wt_name

        if os.name == "nt":
            if len(str(self.repo_root)) > 165:
                wt_dir_name = f"w{digest[:6]}"
            elif len(str(self.worktree_base_dir)) + 1 + len(wt_dir_name) > 210:
                wt_dir_name = f"wt_{digest}"

        if branch_name is not None:
            branch = self._validate_branch_name(branch_name)
        else:
            raw_branch = f"hydra/{safe_run}/{safe_task}/{safe_attempt}"
            if len(raw_branch) > 48:
                branch = f"hydra/{safe_run[:12]}/{safe_task[:12]}/{digest}"
            else:
                branch = raw_branch
            branch = self._validate_branch_name(branch)

        ws_id = workspace_id or f"ws_{wt_dir_name}"

        self._run_git(["config", "core.longpaths", "true"], cwd=self.repo_root)

        win_long_path(self.worktree_base_dir).mkdir(parents=True, exist_ok=True)
        worktree_path = self.worktree_base_dir / wt_dir_name

        if win_long_path(worktree_path).exists():
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
            if win_long_path(worktree_path).exists():
                shutil.rmtree(win_long_path(worktree_path), ignore_errors=True)
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
        if not win_long_path(worktree_path).is_dir() or not win_long_path(git_marker).exists():
            if win_long_path(worktree_path).exists():
                shutil.rmtree(win_long_path(worktree_path), ignore_errors=True)
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Created path '{worktree_path}' is missing .git worktree link",
                    retryable=False,
                ),
                details={"worktree_path": str(worktree_path)},
            )

        self._run_git(["config", "core.longpaths", "true"], cwd=worktree_path)

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

        canonical_wt = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(worktree_path))))
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
        check_path = rel_posix_path.casefold() if os.name == "nt" else rel_posix_path
        pure_path = PurePosixPath(check_path)
        for raw_pat in patterns:
            pat = _normalize_rel_posix(raw_pat)
            if not pat:
                continue
            if os.name == "nt":
                pat = pat.casefold()
            if pat in {"**/*", "**", "*"}:
                return True
            if fnmatch.fnmatchcase(check_path, pat) or pure_path.match(pat):
                return True
            if pat.endswith("/**"):
                prefix = pat[:-3].rstrip("/")
                if check_path == prefix or check_path.startswith(f"{prefix}/"):
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
        """Validate changed files in worktree against allowed_paths, forbidden_paths, and symlink/junction escapes."""
        wt_real = self._verify_worktree_git_file(worktree_path)
        wt_norm = os.path.normcase(str(wt_real))
        changed = self.list_changed_files(wt_real, base_sha=base_sha)

        violations: List[str] = []
        symlink_escapes: List[str] = []
        forbidden_hits: List[str] = []

        candidates_to_check = set(changed)
        walk_root = win_long_path(wt_real)
        for root, dirs, files in os.walk(walk_root, followlinks=False):
            if ".git" in dirs:
                dirs.remove(".git")
            clean_root = Path(_strip_win_long_prefix(str(root)))
            for dir_name in list(dirs):
                full_dir = clean_root / dir_name
                if is_link_or_junction(full_dir):
                    rel_sym = _normalize_rel_posix(str(full_dir.relative_to(wt_real)))
                    candidates_to_check.add(rel_sym)
                    dirs.remove(dir_name)
            for file_name in files:
                full_file = clean_root / file_name
                if is_link_or_junction(full_file):
                    rel_sym = _normalize_rel_posix(str(full_file.relative_to(wt_real)))
                    candidates_to_check.add(rel_sym)

        for rel_path in sorted(candidates_to_check):
            cursor = wt_real
            escaped_via_link = False
            traversed_link = False
            for part in Path(rel_path).parts:
                cursor = cursor / part
                if is_link_or_junction(cursor):
                    traversed_link = True
                    link_target = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(cursor))))
                    link_norm = os.path.normcase(str(link_target))
                    if not (link_norm == wt_norm or link_norm.startswith(wt_norm + os.sep)):
                        escaped_via_link = True
                        break

            candidate = wt_real / Path(rel_path)
            resolved_target = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(candidate))))
            resolved_norm = os.path.normcase(str(resolved_target))
            if escaped_via_link or not (
                resolved_norm == wt_norm
                or resolved_norm.startswith(wt_norm + os.sep)
            ):
                symlink_escapes.append(rel_path)
                violations.append(rel_path)
                continue

            resolved_rel: Optional[str] = None
            if traversed_link and resolved_norm != wt_norm:
                try:
                    resolved_rel = _normalize_rel_posix(str(resolved_target.relative_to(wt_real)))
                except ValueError:
                    symlink_escapes.append(rel_path)
                    violations.append(rel_path)
                    continue

            if rel_path in changed or traversed_link:
                if forbidden_paths and (
                    self._matches_any_pattern(rel_path, forbidden_paths)
                    or (resolved_rel is not None and self._matches_any_pattern(resolved_rel, forbidden_paths))
                ):
                    forbidden_hits.append(rel_path)
                    violations.append(rel_path)
                    continue
                if not self._matches_any_pattern(rel_path, allowed_paths) or (
                    resolved_rel is not None and not self._matches_any_pattern(resolved_rel, allowed_paths)
                ):
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
        try:
            self._verify_worktree_git_file(record.canonical_path)
        except GitWorkspaceError:
            record.status = "preserved"
            raise

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
                [
                    "commit",
                    "--no-verify",
                    "-m",
                    commit_message.strip() or f"feat({record.task_id}): apply task changes",
                ],
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
        win_long_path(patches_dir).mkdir(parents=True, exist_ok=True)

        patch_file = patches_dir / f"{safe_attempt}.patch"
        patch_bytes = diff_res.stdout.encode("utf-8")
        temp_patch = patches_dir / f".{safe_attempt}.patch.tmp"
        win_long_path(temp_patch).write_bytes(patch_bytes)
        os.replace(win_long_path(temp_patch), win_long_path(patch_file))

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
        wt_real = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(record.canonical_path))))
        base_norm = os.path.normcase(_strip_win_long_prefix(os.path.realpath(win_long_path(self.worktree_base_dir))))
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

        if win_long_path(wt_real).exists():
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
            if rm_res.returncode != 0 and force_discard and win_long_path(wt_real).exists():
                shutil.rmtree(win_long_path(wt_real), ignore_errors=True)
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
        win_long_path(self.lock_dir).mkdir(parents=True, exist_ok=True)
        safe_name = _sanitize_token(lock_name)
        lock_path = self.lock_dir / f"{safe_name}.lock"
        payload = {
            "pid": pid if pid is not None else os.getpid(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo_root": str(self.repo_root),
        }
        win_long_path(lock_path).write_text(json.dumps(payload), encoding="utf-8")
        return lock_path

    def cleanup_stale_locks(self) -> Tuple[Path, ...]:
        """
        Inspect .orchestrator/lock/*.lock and .git/worktrees/*/locked, removing stale locks
        owned by dead processes and pruning stale worktree metadata.
        """
        removed: List[Path] = []
        lp_lock_dir = win_long_path(self.lock_dir)
        if lp_lock_dir.exists():
            for lock_entry in sorted(lp_lock_dir.glob("*.lock")):
                lock_file = self.lock_dir / lock_entry.name
                should_remove = False
                try:
                    data = json.loads(lock_entry.read_text(encoding="utf-8"))
                    lock_pid = int(data.get("pid", -1))
                    if lock_pid <= 0 or not is_process_alive(lock_pid):
                        should_remove = True
                except Exception:
                    should_remove = True

                if should_remove:
                    try:
                        lock_entry.unlink()
                        removed.append(lock_file)
                    except OSError:
                        pass

        git_worktrees_admin = self.repo_root / ".git" / "worktrees"
        lp_admin = win_long_path(git_worktrees_admin)
        if lp_admin.exists():
            for wt_admin_entry in sorted(lp_admin.iterdir()):
                if not wt_admin_entry.is_dir():
                    continue
                wt_admin = git_worktrees_admin / wt_admin_entry.name
                gitdir_file = wt_admin_entry / "gitdir"
                locked_file = wt_admin_entry / "locked"
                if locked_file.exists() and gitdir_file.exists():
                    try:
                        target_git = Path(gitdir_file.read_text(encoding="utf-8").strip())
                        if not win_long_path(target_git).exists():
                            locked_file.unlink()
                            removed.append(wt_admin / "locked")
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
        patch = self._run_git_bytes(
            ["diff", "--binary", "--no-ext-diff", target.base_sha],
            cwd=source,
            check=True,
        ).stdout
        if patch:
            applied = self._run_git_bytes(
                ["apply", "--binary", "-"],
                cwd=target.canonical_path,
                input_bytes=patch,
            )
            if applied.returncode:
                raise ContractViolation("handoff_conflict", "Cannot restore partial patch; both worktrees are preserved")
        untracked = self._run_git_bytes(
            ["ls-files", "--others", "--exclude-standard", "-z"],
            cwd=source,
            check=True,
        ).stdout
        for raw in untracked.split(b"\0"):
            if not raw:
                continue
            relative = raw.decode("utf-8")
            src, dest = source / relative, target.canonical_path / relative
            src_cursor = source
            dest_cursor = target.canonical_path
            has_link_parent = False
            for part in Path(relative).parts:
                src_cursor = src_cursor / part
                dest_cursor = dest_cursor / part
                if is_link_or_junction(src_cursor) or is_link_or_junction(dest_cursor):
                    has_link_parent = True
                    break
            if (
                has_link_parent
                or is_link_or_junction(src)
                or not win_long_path(src).is_file()
                or win_long_path(dest).exists()
            ):
                raise ContractViolation("handoff_conflict", "Untracked state cannot be restored safely")
            win_long_path(dest.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy2(win_long_path(src), win_long_path(dest))
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
        raw_branch = target_branch if target_branch is not None else (
            f"integrate/{safe_run}-{_sanitize_token(int_id)}" if integration_id else f"integrate/{safe_run}"
        )
        branch = self._validate_branch_name(raw_branch)
        int_hash = hashlib.sha256(int_id.encode()).hexdigest()[:12]
        int_dir_name = f"integrate_{safe_run[:32]}_{int_hash}"
        if os.name == "nt" and len(str(self.worktree_base_dir)) + 1 + len(int_dir_name) > 210:
            int_dir_name = f"int_{int_hash[:10]}"
        int_wt_path = self.worktree_base_dir / int_dir_name

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

        self._run_git(["config", "core.longpaths", "true"], cwd=self.repo_root)

        win_long_path(self.worktree_base_dir).mkdir(parents=True, exist_ok=True)
        if win_long_path(int_wt_path).exists():
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

        int_wt_real = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(int_wt_path))))
        self._run_git(["config", "core.longpaths", "true"], cwd=int_wt_real)
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
                    "--no-verify",
                    "--no-ff",
                    result.patch_commit_sha,
                    "-m",
                    f"feat(integrate): merge result {result.result_id} attempt {result.attempt_id}",
                ],
                cwd=int_wt_real,
                extra_env=git_env,
            )
            if merge_res.returncode != 0:
                ours_head_sha = self.resolve_commit_sha("HEAD", cwd=int_wt_real)
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
                    ours_sha=ours_head_sha,
                    theirs_sha=result.patch_commit_sha,
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
                        "ours_sha": outcome.ours_sha,
                        "theirs_sha": outcome.theirs_sha,
                    },
                )

    def _read_blob_text(self, commit_sha: str, rel_path: str) -> Optional[str]:
        norm = _normalize_rel_posix(rel_path)
        res = self._run_git(["show", f"{commit_sha}:{norm}"], cwd=self.repo_root)
        if res.returncode != 0:
            return None
        return res.stdout

    @staticmethod
    def _extract_conflict_hunks(merged_preview: str) -> Tuple[str, ...]:
        hunks: List[str] = []
        active: Optional[List[str]] = None
        for line in merged_preview.splitlines(keepends=True):
            if line.startswith("<<<<<<<"):
                active = [line]
            elif active is not None:
                active.append(line)
                if line.startswith(">>>>>>>"):
                    hunks.append("".join(active))
                    active = None
        if active is not None:
            hunks.append("".join(active))
        return tuple(hunks)

    def inspect_three_way(
        self,
        ours_sha: str,
        theirs_sha: str,
        *,
        base_sha: Optional[str] = None,
    ) -> ThreeWayInspection:
        """Inspect a 3-way merge between ours_sha and theirs_sha without mutating any checkout."""
        ours_resolved = self.resolve_commit_sha(ours_sha, cwd=self.repo_root)
        theirs_resolved = self.resolve_commit_sha(theirs_sha, cwd=self.repo_root)

        used_explicit_base = base_sha is not None
        if base_sha is not None:
            base_resolved = self.resolve_commit_sha(base_sha, cwd=self.repo_root)
        else:
            mb_res = self._run_git(["merge-base", ours_resolved, theirs_resolved], cwd=self.repo_root)
            base_resolved = (
                self.resolve_commit_sha(mb_res.stdout.strip(), cwd=self.repo_root)
                if mb_res.returncode == 0 and mb_res.stdout.strip()
                else ours_resolved
            )

        mt_args = ["merge-tree", "--write-tree", "--name-only"]
        if used_explicit_base or base_resolved != ours_resolved:
            mt_args.append(f"--merge-base={base_resolved}")
        mt_args.extend([ours_resolved, theirs_resolved])

        mt_res = self._run_git(mt_args, cwd=self.repo_root)
        if mt_res.returncode == 0:
            return ThreeWayInspection(
                base_sha=base_resolved,
                ours_sha=ours_resolved,
                theirs_sha=theirs_resolved,
                has_conflicts=False,
            )

        lines = mt_res.stdout.splitlines()
        conflicted: List[str] = []
        for raw_line in lines[1:]:
            if not raw_line.strip():
                break
            conflicted.append(_normalize_rel_posix(raw_line))
        conflicted_files = tuple(sorted(set(p for p in conflicted if p)))

        details: List[ThreeWayFileConflict] = []
        with tempfile.TemporaryDirectory(prefix="hydra_3way_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            for idx, rel_path in enumerate(conflicted_files):
                base_txt = self._read_blob_text(base_resolved, rel_path)
                ours_txt = self._read_blob_text(ours_resolved, rel_path)
                theirs_txt = self._read_blob_text(theirs_resolved, rel_path)

                if ours_txt is None or theirs_txt is None:
                    ours_view = ours_txt if ours_txt is not None else "[deleted in ours]\n"
                    base_view = base_txt if base_txt is not None else "[absent in base]\n"
                    theirs_view = theirs_txt if theirs_txt is not None else "[deleted in theirs]\n"
                    merged_preview = (
                        f"<<<<<<< ours\n{ours_view}"
                        f"||||||| base\n{base_view}"
                        f"=======\n{theirs_view}"
                        f">>>>>>> theirs\n"
                    )
                else:
                    ours_f = tmp_path / f"{idx}_ours.txt"
                    base_f = tmp_path / f"{idx}_base.txt"
                    theirs_f = tmp_path / f"{idx}_theirs.txt"
                    ours_f.write_text(ours_txt, encoding="utf-8")
                    base_f.write_text(base_txt or "", encoding="utf-8")
                    theirs_f.write_text(theirs_txt, encoding="utf-8")
                    mf_res = self._run_git(
                        [
                            "merge-file",
                            "-p",
                            "--diff3",
                            "-L",
                            "ours",
                            "-L",
                            "base",
                            "-L",
                            "theirs",
                            str(ours_f),
                            str(base_f),
                            str(theirs_f),
                        ],
                        cwd=self.repo_root,
                    )
                    merged_preview = mf_res.stdout

                hunks = self._extract_conflict_hunks(merged_preview)
                if not hunks and merged_preview:
                    hunks = (merged_preview,)

                details.append(
                    ThreeWayFileConflict(
                        path=rel_path,
                        base_content=base_txt,
                        ours_content=ours_txt,
                        theirs_content=theirs_txt,
                        merged_preview=merged_preview,
                        hunks=hunks,
                    )
                )

        return ThreeWayInspection(
            base_sha=base_resolved,
            ours_sha=ours_resolved,
            theirs_sha=theirs_resolved,
            has_conflicts=bool(conflicted_files),
            conflicted_files=conflicted_files,
            file_conflicts=tuple(details),
        )

    def create_merge_repair_worktree(
        self,
        run_id: str,
        conflict_id: str,
        attempt_ordinal: int,
        ours_sha: str,
        theirs_sha: Optional[str] = None,
        *,
        populate_conflict: bool = True,
        branch_name: Optional[str] = None,
        prefix: str = "repair",
    ) -> WorkspaceRecord:
        """Create an isolated merge_repair worktree anchored at ours_sha without mutating operator checkout."""
        ours_resolved = self.resolve_commit_sha(ours_sha, cwd=self.repo_root)
        theirs_resolved = (
            self.resolve_commit_sha(theirs_sha, cwd=self.repo_root)
            if theirs_sha is not None
            else None
        )

        safe_run = _sanitize_token(run_id)
        safe_conflict = _sanitize_token(conflict_id)
        safe_prefix = _sanitize_token(prefix)
        digest = hashlib.sha256(
            f"{run_id}:{conflict_id}:{attempt_ordinal}:{prefix}".encode("utf-8")
        ).hexdigest()[:8]

        wt_dir_name = f"{safe_prefix}_{safe_conflict[:12]}_{attempt_ordinal}_{digest}"
        if os.name == "nt" and len(str(self.worktree_base_dir)) + 1 + len(wt_dir_name) > 210:
            wt_dir_name = f"rp_{digest}"
        raw_branch = (
            branch_name
            if branch_name is not None
            else f"merge_repair/{safe_run[:16]}/{safe_conflict[:12]}/att_{attempt_ordinal}_{digest}"
        )
        branch = self._validate_branch_name(raw_branch)
        attempt_id = f"{safe_prefix}_{safe_conflict[:16]}_{attempt_ordinal}_{digest}"
        ws_id = f"ws_{wt_dir_name}"

        self._run_git(["config", "core.longpaths", "true"], cwd=self.repo_root)

        win_long_path(self.worktree_base_dir).mkdir(parents=True, exist_ok=True)
        worktree_path = self.worktree_base_dir / wt_dir_name
        if win_long_path(worktree_path).exists():
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Repair worktree path '{worktree_path}' already exists",
                    retryable=False,
                ),
                details={"worktree_path": str(worktree_path)},
            )

        res = self._run_git(
            ["worktree", "add", "-b", branch, str(worktree_path), ours_resolved],
            cwd=self.repo_root,
        )
        if res.returncode != 0:
            if win_long_path(worktree_path).exists():
                shutil.rmtree(win_long_path(worktree_path), ignore_errors=True)
            raise GitWorkspaceError(
                FailureDetail(
                    code="workspace_invalid",
                    message=f"Failed to create merge_repair worktree at '{worktree_path}': {res.stderr.strip()}",
                    retryable=False,
                ),
                details={"worktree_path": str(worktree_path), "stderr": res.stderr.strip()},
                stderr=res.stderr,
            )

        canonical_wt = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(worktree_path))))
        self._run_git(["config", "core.longpaths", "true"], cwd=canonical_wt)
        ws_status: WorkspaceStatusLiteral = "ready"
        if populate_conflict and theirs_resolved is not None:
            git_env = {
                "GIT_AUTHOR_NAME": self.git_author_name,
                "GIT_AUTHOR_EMAIL": self.git_author_email,
                "GIT_COMMITTER_NAME": self.git_author_name,
                "GIT_COMMITTER_EMAIL": self.git_author_email,
            }
            merge_res = self._run_git(
                ["merge", "--no-verify", "--no-commit", "--no-ff", theirs_resolved],
                cwd=canonical_wt,
                extra_env=git_env,
            )
            if merge_res.returncode != 0:
                ws_status = "conflicted"

        record = WorkspaceRecord(
            workspace_id=ws_id,
            attempt_id=attempt_id,
            run_id=run_id,
            task_id=f"merge_repair_{safe_conflict}",
            canonical_path=canonical_wt,
            base_sha=ours_resolved,
            branch=branch,
            status=ws_status,
        )
        self._workspaces[attempt_id] = record
        return record

    def inspect_worktree_conflicts(
        self,
        worktree_path: Union[str, Path],
        candidate_files: Sequence[str] = (),
        *,
        require_staged: bool = False,
    ) -> Tuple[str, ...]:
        """Return any paths still having unresolved conflict markers or unmerged index entries."""
        wt_real = Path(os.path.realpath(worktree_path))
        conflicted: set[str] = set()

        unmerged_res = self._run_git(["diff", "--name-only", "--diff-filter=U"], cwd=wt_real)
        unmerged_paths: set[str] = set()
        if unmerged_res.returncode == 0:
            for line in unmerged_res.stdout.splitlines():
                norm = _normalize_rel_posix(line)
                if norm:
                    unmerged_paths.add(norm)

        paths_to_check = unmerged_paths | {
            _normalize_rel_posix(p) for p in candidate_files if _normalize_rel_posix(p)
        }
        for norm in paths_to_check:
            target = wt_real / norm
            lp_target = win_long_path(target)
            has_markers = False
            readable_text = False
            if lp_target.is_file():
                try:
                    raw_bytes = lp_target.read_bytes()
                    if b"\x00" not in raw_bytes:
                        content = raw_bytes.decode("utf-8", errors="replace")
                        readable_text = True
                        lines = content.splitlines()
                        has_left = any(ln.startswith("<<<<<<<") for ln in lines)
                        has_mid = any(ln.startswith("=======") for ln in lines)
                        has_right = any(ln.startswith(">>>>>>>") for ln in lines)
                        has_markers = has_left and has_mid and has_right
                except OSError:
                    readable_text = False

            if has_markers:
                conflicted.add(norm)
            elif norm in unmerged_paths and (require_staged or not readable_text):
                conflicted.add(norm)

        return tuple(sorted(conflicted))

    def commit_resolved_worktree(
        self,
        worktree_path: Union[str, Path],
        commit_message: str,
        *,
        candidate_files: Sequence[str] = (),
    ) -> str:
        """Verify conflicts are resolved, stage, commit in the isolated worktree, and return HEAD SHA."""
        wt_real = self._verify_worktree_git_file(worktree_path)
        remaining = self.inspect_worktree_conflicts(wt_real, candidate_files=candidate_files)
        if remaining:
            raise GitWorkspaceError(
                FailureDetail(
                    code="merge_conflict",
                    message=f"Unresolved conflicts remain in worktree '{wt_real}': {', '.join(remaining)}",
                    retryable=False,
                ),
                details={"conflicted_files": list(remaining)},
            )

        status_res = self._run_git(["status", "--porcelain=v1", "-uall"], cwd=wt_real)
        merge_head_res = self._run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=wt_real)
        has_merge_head = merge_head_res.returncode == 0

        if status_res.stdout.strip() or has_merge_head:
            add_res = self._run_git(["add", "-A"], cwd=wt_real)
            if add_res.returncode != 0:
                raise GitWorkspaceError(
                    FailureDetail(
                        code="git_operation_failed",
                        message=f"git add -A failed in '{wt_real}': {add_res.stderr.strip()}",
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
                ["commit", "--no-verify", "-m", commit_message.strip() or "fix(merge): resolve conflict"],
                cwd=wt_real,
                extra_env=git_env,
            )
            if commit_res.returncode != 0:
                raise GitWorkspaceError(
                    FailureDetail(
                        code="git_operation_failed",
                        message=f"git commit failed in '{wt_real}': {commit_res.stderr.strip()}",
                        retryable=False,
                    ),
                    details={"stderr": commit_res.stderr.strip()},
                    stderr=commit_res.stderr,
                )

        return self.resolve_commit_sha("HEAD", cwd=wt_real)

    def update_worktree_base(
        self,
        worktree_path: Union[str, Path],
        new_base_sha: str,
    ) -> Tuple[bool, str, Tuple[str, ...]]:
        """Rebase an isolated worktree onto new_base_sha; aborts cleanly on conflict without mutating repo_root."""
        wt_real = Path(os.path.realpath(worktree_path))
        target_sha = self.resolve_commit_sha(new_base_sha, cwd=self.repo_root)
        current_head = self.resolve_commit_sha("HEAD", cwd=wt_real)

        git_env = {
            "GIT_AUTHOR_NAME": self.git_author_name,
            "GIT_AUTHOR_EMAIL": self.git_author_email,
            "GIT_COMMITTER_NAME": self.git_author_name,
            "GIT_COMMITTER_EMAIL": self.git_author_email,
        }
        rebase_res = self._run_git(["rebase", target_sha], cwd=wt_real, extra_env=git_env)
        if rebase_res.returncode != 0:
            conflict_res = self._run_git(["diff", "--name-only", "--diff-filter=U"], cwd=wt_real)
            conflicted = tuple(
                sorted(
                    _normalize_rel_posix(line)
                    for line in conflict_res.stdout.splitlines()
                    if line.strip()
                )
            )
            self._run_git(["rebase", "--abort"], cwd=wt_real)
            return False, current_head, conflicted

        new_head = self.resolve_commit_sha("HEAD", cwd=wt_real)
        return True, new_head, ()
