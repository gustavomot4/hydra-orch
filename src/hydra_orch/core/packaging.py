"""T28 PR packaging and gated publication (RF30 / RT30)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Optional, Sequence, Tuple, Union
import uuid

from pydantic import Field

from hydra_orch.core.budget import BudgetGovernor
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.identifier import new_id
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import (
    Artifact,
    ContractViolation,
    ExecutionModel,
    GitSha,
    Identifier,
    NonEmpty,
    RelativePath,
    RunSpec,
    Sha256,
    UtcTimestamp,
)

_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_REMOTE_URL_SCHEME_RE = re.compile(r"^(?:https?://|ssh://|git://|git@)", re.I)


def _sanitize_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RE.sub("_", value.strip())
    return cleaned.strip("._-") or "item"


def _write_bytes_atomic(target_path: Path, data: bytes) -> Tuple[str, int]:
    """Write bytes atomically via temp file + fsync + os.replace; return (sha256, size_bytes)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp_path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, target_path)
    return hashlib.sha256(data).hexdigest(), len(data)


def _run_git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class PRPackage(ExecutionModel):
    """Structured, redacted pull request dossier persisted in SQLite and retained as an Artifact."""

    package_id: Identifier
    run_id: Identifier
    pr_branch: NonEmpty
    base_branch: NonEmpty
    base_sha: GitSha
    head_sha: Optional[GitSha] = None
    description_markdown: NonEmpty
    commits: tuple[dict[str, Any], ...] = ()
    checks_summary: dict[str, Any] = Field(default_factory=dict)
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    review_decisions: tuple[dict[str, Any], ...] = ()
    artifact_id: Optional[Identifier] = None
    artifact_path: Optional[RelativePath] = None
    artifact_sha256: Optional[Sha256] = None
    created_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublishResult(ExecutionModel):
    """Auditable outcome of an authorized PR branch push."""

    package_id: Identifier
    run_id: Identifier
    pr_branch: NonEmpty
    remote: NonEmpty
    pushed_sha: Optional[GitSha] = None
    published: bool
    published_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExportResult(ExecutionModel):
    """Redacted offline export of a PR package."""

    package_id: Identifier
    run_id: Identifier
    export_path: Optional[NonEmpty] = None
    sha256: Sha256
    size_bytes: int = Field(ge=0, strict=True)
    markdown: NonEmpty


class PRPackager:
    """Builds redacted, auditable PR packages and gates remote publication on explicit authorization."""

    def __init__(self, store: ExecutionStore, metrics: Optional[MetricsService] = None):
        if metrics is not None and metrics.store is not store:
            raise ValueError("PRPackager requires MetricsService backed by the same ExecutionStore")
        self.store = store
        self.metrics = metrics or MetricsService(store)

    @staticmethod
    def _validate_branch_name(branch: str) -> str:
        clean = branch.strip()
        if (
            not clean
            or clean.startswith("-")
            or clean.startswith("/")
            or clean.endswith("/")
            or ".." in clean
            or any(ch.isspace() or ch == "\x00" for ch in clean)
        ):
            raise ContractViolation("packaging_invalid", f"Invalid PR branch name: '{branch}'")
        return clean

    async def _collect_git_details(
        self,
        repo_root: Path,
        base_sha: str,
        head_sha: Optional[str],
        pr_branch: str,
        create_git_branch: bool,
    ) -> Tuple[list[dict[str, Any]], dict[str, Any]]:
        commits: list[dict[str, Any]] = []
        diff_summary: dict[str, Any] = {
            "files_changed": 0,
            "insertions": None,
            "deletions": None,
            "files": [],
        }

        is_git_repo = repo_root.exists() and (repo_root / ".git").exists()
        if not is_git_repo:
            return commits, diff_summary

        target_sha = head_sha or base_sha
        if head_sha and head_sha != base_sha:
            log_res = _run_git(
                ["log", "--reverse", "--format=%H%x00%s%x00%an%x00%aI", f"{base_sha}..{head_sha}"],
                repo_root,
            )
            if log_res.returncode == 0:
                for line in log_res.stdout.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split("\x00", 3)
                    if len(parts) == 4:
                        commits.append(
                            {
                                "sha": parts[0],
                                "message": redact_text(parts[1]),
                                "author": redact_text(parts[2]),
                                "timestamp": parts[3],
                            }
                        )

            stat_res = _run_git(["diff", "--numstat", f"{base_sha}..{head_sha}"], repo_root)
            if stat_res.returncode == 0:
                total_ins = 0
                total_del = 0
                files_list: list[dict[str, Any]] = []
                for line in stat_res.stdout.splitlines():
                    if not line.strip():
                        continue
                    cols = line.split("\t", 2)
                    if len(cols) == 3:
                        ins = int(cols[0]) if cols[0].isdigit() else 0
                        dels = int(cols[1]) if cols[1].isdigit() else 0
                        total_ins += ins
                        total_del += dels
                        files_list.append(
                            {
                                "path": cols[2],
                                "insertions": ins,
                                "deletions": dels,
                            }
                        )
                diff_summary = {
                    "files_changed": len(files_list),
                    "insertions": total_ins,
                    "deletions": total_del,
                    "files": files_list,
                }

        if create_git_branch:
            head_branch_res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
            if head_branch_res.returncode == 0 and head_branch_res.stdout.strip() == pr_branch:
                raise ContractViolation(
                    "packaging_branch_conflict",
                    f"PR branch '{pr_branch}' cannot overwrite currently checked-out operator branch",
                )
            branch_res = _run_git(["branch", "-f", pr_branch, target_sha], repo_root)
            if branch_res.returncode != 0:
                raise ContractViolation(
                    "packaging_git_failed",
                    f"Failed to create PR branch '{pr_branch}' at '{target_sha}': {branch_res.stderr.strip()}",
                )

        return commits, diff_summary

    @staticmethod
    def _render_markdown(
        *,
        run_spec: RunSpec,
        pr_branch: str,
        head_sha: Optional[str],
        commits: Sequence[dict[str, Any]],
        checks_summary: dict[str, Any],
        diff_summary: dict[str, Any],
        metrics: dict[str, Any],
        review_decisions: Sequence[dict[str, Any]],
    ) -> str:
        lines: list[str] = [
            f"# Pull Request Package — `{run_spec.run_id}`",
            "",
            "## Objective",
            redact_text(run_spec.objective),
            "",
            f"- **Project:** `{run_spec.project_id}`",
            f"- **Mode:** `{run_spec.orchestration_mode}`",
            f"- **Base Branch / SHA:** `{run_spec.base_branch}` (`{run_spec.base_sha}`)",
            f"- **PR Branch / Head SHA:** `{pr_branch}` (`{head_sha or run_spec.base_sha}`)",
            "",
            "## Commits",
        ]
        if commits:
            for item in commits:
                lines.append(f"- `{item['sha'][:12]}` {item['message']}")
        else:
            lines.append("- _No commits recorded beyond base SHA._")

        lines.extend(
            [
                "",
                "## Checks Summary",
                f"- **Total:** {checks_summary.get('total', 0)} | "
                f"**Passed:** {checks_summary.get('passed', 0)} | "
                f"**Failed:** {checks_summary.get('failed', 0)}",
            ]
        )
        for chk in checks_summary.get("checks", ()):
            cmd_str = " ".join(str(part) for part in chk.get("command", ()))
            lines.append(
                f"- `{chk['check_id']}` ({chk['scope']}): exit=`{chk['exit_code']}`, "
                f"duration=`{chk['duration_seconds']:.3f}s`, sha=`{str(chk['tested_sha'])[:12]}`, "
                f"cmd=`{cmd_str}`"
            )

        ins = diff_summary.get("insertions")
        dels = diff_summary.get("deletions")
        stat_text = f"+{ins}/-{dels}" if ins is not None and dels is not None else "line stats unavailable"
        lines.extend(
            [
                "",
                "## Diff Summary",
                f"- **Files Changed:** {diff_summary.get('files_changed', 0)} ({stat_text})",
            ]
        )
        for fentry in diff_summary.get("files", ()):
            if isinstance(fentry, dict):
                f_ins = fentry.get("insertions")
                f_del = fentry.get("deletions")
                suffix = f" (+{f_ins}/-{f_del})" if f_ins is not None and f_del is not None else ""
                lines.append(f"- `{fentry['path']}`{suffix}")
            else:
                lines.append(f"- `{fentry}`")

        lines.extend(["", "## Metrics (Provenance & Status)"])
        usage_map = metrics.get("usage", {})
        for kind in ("tokens_in", "tokens_out", "cost"):
            entry = usage_map.get(kind, {})
            val = entry.get("value")
            val_str = str(val) if val is not None else "unknown"
            sources = ", ".join(entry.get("sources", ())) or "not_reported"
            lines.append(
                f"- **{kind}:** `{val_str}` {entry.get('unit', '')} "
                f"(status=`{entry.get('status', 'unknown')}`, sources=`{sources}`)"
            )
        budget_info = metrics.get("budget", {})
        if budget_info:
            lines.append(f"- **Budget Status:** `{budget_info.get('status', 'active')}`")

        lines.extend(["", "## Review Decisions"])
        if review_decisions:
            for rv in review_decisions:
                lines.append(
                    f"- Task `{rv['task_id']}` (result `{rv['result_id']}`, rev `{rv['expected_revision']}`): "
                    f"**{rv['decision']}** by `{rv['actor']}` — {rv['reason']}"
                )
        else:
            lines.append("- _No explicit review decisions recorded._")

        return redact_text("\n".join(lines).strip() + "\n")

    async def _row_to_package(self, db: Any, row: Any) -> PRPackage:
        run_row = await (await db.execute("SELECT spec_json FROM runs WHERE id = ?", (row["run_id"],))).fetchone()
        assert run_row is not None
        run_spec = RunSpec.model_validate_json(run_row["spec_json"])

        safe_run = _sanitize_token(row["run_id"])
        safe_pkg = _sanitize_token(row["id"])
        expected_rel = f".orchestrator/run/{safe_run}/pr_package/{safe_pkg}.json"
        art_row = await (
            await db.execute(
                "SELECT id, relative_path, sha256 FROM artifacts WHERE run_id = ? AND kind = 'pr_package' AND relative_path = ?",
                (row["run_id"], expected_rel),
            )
        ).fetchone()

        metrics_data = json.loads(row["metrics_json"])
        commits_data = json.loads(row["commits_json"])
        checks_data = json.loads(row["checks_summary_json"])
        diff_data = json.loads(row["diff_summary_json"])

        created_raw = str(row["created_at"])
        clean_ts = created_raw.replace("Z", "+00:00")
        created_dt = datetime.fromisoformat(clean_ts) if "T" in clean_ts else datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)

        return PRPackage(
            package_id=row["id"],
            run_id=row["run_id"],
            pr_branch=row["pr_branch"],
            base_branch=run_spec.base_branch,
            base_sha=run_spec.base_sha,
            head_sha=metrics_data.get("head_sha"),
            description_markdown=row["description_markdown"],
            commits=tuple(commits_data),
            checks_summary=checks_data,
            diff_summary=diff_data,
            metrics=metrics_data,
            review_decisions=tuple(metrics_data.get("review_decisions", ())),
            artifact_id=art_row["id"] if art_row else None,
            artifact_path=art_row["relative_path"] if art_row else None,
            artifact_sha256=art_row["sha256"] if art_row else None,
            created_at=created_dt,
        )

    async def get_package(self, run_id: str) -> Optional[PRPackage]:
        """Retrieve the persisted PRPackage for a run, if built."""
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute("SELECT * FROM pr_packages WHERE run_id = ?", (run_id,))
            ).fetchone()
            if row is None:
                return None
            return await self._row_to_package(db, row)

    async def get_package_by_id(self, package_id: str) -> Optional[PRPackage]:
        """Retrieve a persisted PRPackage by package_id."""
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute("SELECT * FROM pr_packages WHERE id = ?", (package_id,))
            ).fetchone()
            if row is None:
                return None
            return await self._row_to_package(db, row)

    async def build(
        self,
        run_id: str,
        *,
        pr_branch: Optional[str] = None,
        create_git_branch: bool = True,
        runtime_dir: Optional[Union[str, Path]] = None,
        correlation_id: Optional[str] = None,
    ) -> PRPackage:
        """Compile, redact, and persist a PRPackage plus an atomic Artifact(kind='pr_package')."""
        await self.store.initialize()
        run_rec = await self.store.get_run(run_id)
        if run_rec is None:
            raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")
        run_spec: RunSpec = run_rec["spec"]

        target_branch = self._validate_branch_name(pr_branch or f"pr/{_sanitize_token(run_id)}")

        async with self.store._connect() as db:
            existing = await (
                await db.execute("SELECT id FROM pr_packages WHERE run_id = ?", (run_id,))
            ).fetchone()
            if existing is not None:
                raise ContractViolation(
                    "pr_package_exists",
                    f"PR package already exists for run '{run_id}' (package_id={existing['id']})",
                )

            int_row = await (
                await db.execute(
                    """
                    SELECT id, result_sha
                    FROM integrations
                    WHERE run_id = ? AND status = 'integrated'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (run_id,),
                )
            ).fetchone()

            result_rows = await (
                await db.execute(
                    """
                    SELECT r.id, r.attempt_id, r.patch_commit_sha, r.summary, r.task_status, r.result_json
                    FROM results r
                    JOIN attempts a ON a.id = r.attempt_id
                    WHERE r.run_id = ?
                    ORDER BY a.created_at ASC, a.ordinal ASC, r.id ASC
                    """,
                    (run_id,),
                )
            ).fetchall()

            review_rows = await (
                await db.execute(
                    """
                    SELECT rv.id, rv.result_id, rv.actor, rv.decision, rv.reason, rv.expected_revision, rv.created_at,
                           a.task_id
                    FROM reviews rv
                    JOIN results r ON r.id = rv.result_id
                    JOIN attempts a ON a.id = r.attempt_id
                    WHERE r.run_id = ?
                    ORDER BY rv.created_at ASC, rv.id ASC
                    """,
                    (run_id,),
                )
            ).fetchall()

            checks_list: list[dict[str, Any]] = []
            if int_row is not None:
                int_checks = await (
                    await db.execute(
                        "SELECT check_id, command_json, cwd, tested_sha, exit_code, duration_seconds "
                        "FROM check_results WHERE integration_id = ? ORDER BY id ASC",
                        (int_row["id"],),
                    )
                ).fetchall()
                for chk in int_checks:
                    checks_list.append(
                        {
                            "check_id": chk["check_id"],
                            "scope": "integration",
                            "command": json.loads(chk["command_json"]),
                            "cwd": chk["cwd"],
                            "tested_sha": chk["tested_sha"],
                            "exit_code": int(chk["exit_code"]),
                            "duration_seconds": float(chk["duration_seconds"] or 0.0),
                        }
                    )

            for rrow in result_rows:
                if rrow["task_status"] not in {"accepted", "ready_for_review"}:
                    continue
                res_checks = await (
                    await db.execute(
                        "SELECT check_id, command_json, cwd, tested_sha, exit_code, duration_seconds "
                        "FROM check_results WHERE result_id = ? ORDER BY id ASC",
                        (rrow["id"],),
                    )
                ).fetchall()
                for chk in res_checks:
                    checks_list.append(
                        {
                            "check_id": chk["check_id"],
                            "scope": "task",
                            "command": json.loads(chk["command_json"]),
                            "cwd": chk["cwd"],
                            "tested_sha": chk["tested_sha"],
                            "exit_code": int(chk["exit_code"]),
                            "duration_seconds": float(chk["duration_seconds"] or 0.0),
                        }
                    )

        head_sha: Optional[str] = int_row["result_sha"] if int_row and int_row["result_sha"] else None
        if head_sha is None:
            for rrow in reversed(result_rows):
                if rrow["task_status"] in {"accepted", "ready_for_review"} and rrow["patch_commit_sha"]:
                    head_sha = rrow["patch_commit_sha"]
                    break

        repo_root = Path(run_spec.repo_root)
        commits, diff_summary = await self._collect_git_details(
            repo_root,
            run_spec.base_sha,
            head_sha,
            target_branch,
            create_git_branch=create_git_branch,
        )

        if not commits:
            for rrow in result_rows:
                if rrow["task_status"] in {"accepted", "ready_for_review"} and rrow["patch_commit_sha"]:
                    commits.append(
                        {
                            "sha": rrow["patch_commit_sha"],
                            "message": redact_text(rrow["summary"] or ""),
                        }
                    )

        if diff_summary["files_changed"] == 0 and result_rows:
            changed_set: list[str] = []
            seen_files: set[str] = set()
            for rrow in result_rows:
                if rrow["task_status"] in {"accepted", "ready_for_review"} and rrow["result_json"]:
                    parsed = json.loads(rrow["result_json"])
                    for fpath in parsed.get("changed_files", ()):
                        if fpath not in seen_files:
                            seen_files.add(fpath)
                            changed_set.append(fpath)
            if changed_set:
                diff_summary["files_changed"] = len(changed_set)
                diff_summary["files"] = [{"path": p, "insertions": None, "deletions": None} for p in changed_set]

        review_decisions = [
            {
                "review_id": rv["id"],
                "result_id": rv["result_id"],
                "task_id": rv["task_id"],
                "actor": redact_text(rv["actor"]),
                "decision": rv["decision"],
                "reason": redact_text(rv["reason"] or ""),
                "expected_revision": int(rv["expected_revision"]),
                "created_at": rv["created_at"],
            }
            for rv in review_rows
        ]

        checks_summary = redact(
            {
                "total": len(checks_list),
                "passed": sum(1 for c in checks_list if c["exit_code"] == 0),
                "failed": sum(1 for c in checks_list if c["exit_code"] != 0),
                "checks": checks_list,
            }
        )

        usage_aggs = await self.metrics.aggregate_usage(run_id)
        budget_status = await BudgetGovernor(self.store, self.metrics).get_status(run_id)
        metrics_payload = redact(
            {
                "head_sha": head_sha,
                "usage": {
                    agg.kind: {
                        "value": agg.value,
                        "known_subtotal": agg.known_subtotal,
                        "unit": agg.unit,
                        "status": agg.status,
                        "scope_count": agg.scope_count,
                        "observed_count": agg.observed_count,
                        "stale_count": agg.stale_count,
                        "unknown_count": agg.unknown_count,
                        "sources": list(agg.sources),
                    }
                    for agg in usage_aggs
                },
                "budget": {
                    "status": budget_status.status,
                    "max_usd": budget_status.max_usd,
                    "current_usd": budget_status.current_usd,
                    "usd_status": budget_status.usd_status,
                    "max_tokens_in": budget_status.max_tokens_in,
                    "current_tokens_in": budget_status.current_tokens_in,
                    "tokens_in_status": budget_status.tokens_in_status,
                    "max_tokens_out": budget_status.max_tokens_out,
                    "current_tokens_out": budget_status.current_tokens_out,
                    "tokens_out_status": budget_status.tokens_out_status,
                    "max_wall_seconds": budget_status.max_wall_seconds,
                    "current_wall_seconds": budget_status.current_wall_seconds,
                    "wall_seconds_status": budget_status.wall_seconds_status,
                },
                "review_decisions": review_decisions,
            }
        )

        redacted_commits = redact(commits)
        redacted_diff = redact(diff_summary)
        description_md = self._render_markdown(
            run_spec=run_spec,
            pr_branch=target_branch,
            head_sha=head_sha,
            commits=redacted_commits,
            checks_summary=checks_summary,
            diff_summary=redacted_diff,
            metrics=metrics_payload,
            review_decisions=review_decisions,
        )

        package_id = f"prpkg-{new_id()}"
        created_at = datetime.now(timezone.utc)
        safe_run = _sanitize_token(run_id)
        safe_pkg = _sanitize_token(package_id)

        if runtime_dir is not None:
            rt_base = Path(runtime_dir)
        elif repo_root.exists():
            rt_base = repo_root / ".orchestrator"
        else:
            rt_base = Path(self.store.db_path).parent / ".orchestrator"

        rel_path = f".orchestrator/run/{safe_run}/pr_package/{safe_pkg}.json"
        artifact_file = rt_base / "run" / safe_run / "pr_package" / f"{safe_pkg}.json"
        artifact_doc = redact(
            {
                "package_id": package_id,
                "run_id": run_id,
                "pr_branch": target_branch,
                "base_branch": run_spec.base_branch,
                "base_sha": run_spec.base_sha,
                "head_sha": head_sha,
                "description_markdown": description_md,
                "commits": redacted_commits,
                "checks_summary": checks_summary,
                "diff_summary": redacted_diff,
                "metrics": metrics_payload,
                "review_decisions": review_decisions,
                "created_at": created_at.isoformat(),
            }
        )
        artifact_bytes = json.dumps(artifact_doc, indent=2, sort_keys=True).encode("utf-8")
        art_sha256, art_size = _write_bytes_atomic(artifact_file, artifact_bytes)

        artifact = Artifact(
            artifact_id=f"art-prpkg-{safe_pkg}",
            run_id=run_id,
            attempt_id=None,
            relative_path=rel_path,
            kind="pr_package",
            sha256=art_sha256,
            size_bytes=art_size,
        )

        try:
            async with self.store._connect() as db:
                async with self.store._transaction(db):
                    await db.execute(
                        """
                        INSERT INTO pr_packages (
                            id, run_id, pr_branch, description_markdown,
                            commits_json, checks_summary_json, diff_summary_json,
                            metrics_json, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            package_id,
                            run_id,
                            target_branch,
                            description_md,
                            json.dumps(redacted_commits, sort_keys=True),
                            json.dumps(checks_summary, sort_keys=True),
                            json.dumps(redacted_diff, sort_keys=True),
                            json.dumps(metrics_payload, sort_keys=True),
                            created_at.isoformat(),
                        ),
                    )
                    await self.store._upsert_artifact_in_tx(db, artifact)
                    await self.store._insert_event_in_tx(
                        db,
                        run_id=run_id,
                        event_type="pr_package.created",
                        payload={
                            "package_id": package_id,
                            "pr_branch": target_branch,
                            "head_sha": head_sha,
                            "artifact_id": artifact.artifact_id,
                            "artifact_sha256": artifact.sha256,
                            "commits_count": len(redacted_commits),
                            "checks_total": checks_summary["total"],
                        },
                        correlation_id=correlation_id,
                    )
        except Exception:
            if artifact_file.exists():
                try:
                    artifact_file.unlink()
                except OSError:
                    pass
            raise

        return PRPackage(
            package_id=package_id,
            run_id=run_id,
            pr_branch=target_branch,
            base_branch=run_spec.base_branch,
            base_sha=run_spec.base_sha,
            head_sha=head_sha,
            description_markdown=description_md,
            commits=tuple(redacted_commits),
            checks_summary=checks_summary,
            diff_summary=redacted_diff,
            metrics=metrics_payload,
            review_decisions=tuple(review_decisions),
            artifact_id=artifact.artifact_id,
            artifact_path=artifact.relative_path,
            artifact_sha256=artifact.sha256,
            created_at=created_at,
        )

    async def publish(
        self,
        package_id: str,
        *,
        authorized: bool = False,
        policy_authorized: Optional[bool] = None,
        remote: str = "origin",
        push_fn: Optional[Callable[..., Any]] = None,
        actor: str = "operator",
    ) -> PublishResult:
        """Push the PR branch only when publication is explicitly authorized."""
        if not authorized or policy_authorized is False:
            raise ContractViolation(
                "publish_not_authorized",
                "PR package publication requires explicit authorization",
            )

        clean_remote = remote.strip()
        if not clean_remote or clean_remote.startswith("-") or "\x00" in clean_remote:
            raise ContractViolation("packaging_invalid", f"Invalid git remote '{remote}'")

        pkg = await self.get_package_by_id(package_id)
        if pkg is None:
            raise ContractViolation("resource_not_found", f"PR package '{package_id}' does not exist")

        run_rec = await self.store.get_run(pkg.run_id)
        assert run_rec is not None
        run_spec: RunSpec = run_rec["spec"]
        repo_root = Path(run_spec.repo_root)

        pushed_sha = pkg.head_sha
        if push_fn is not None:
            outcome = push_fn(
                repo_root=repo_root,
                remote=clean_remote,
                pr_branch=pkg.pr_branch,
                package_id=pkg.package_id,
            )
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if isinstance(outcome, str) and len(outcome) in (40, 64):
                pushed_sha = outcome
        else:
            if not repo_root.exists() or not (repo_root / ".git").exists():
                raise ContractViolation(
                    "workspace_invalid",
                    f"Cannot push PR branch '{pkg.pr_branch}': '{repo_root}' is not a Git repository",
                )
            remote_url_res = _run_git(["remote", "get-url", clean_remote], repo_root)
            resolved_url = remote_url_res.stdout.strip() if remote_url_res.returncode == 0 else clean_remote
            if os.environ.get("HYDRA_OFFLINE_CI") == "1" and _REMOTE_URL_SCHEME_RE.match(resolved_url):
                raise ContractViolation(
                    "publish_not_authorized",
                    "External network git push is disabled under HYDRA_OFFLINE_CI=1",
                )
            rev_res = _run_git(["rev-parse", "--verify", f"refs/heads/{pkg.pr_branch}^{{commit}}"], repo_root)
            if rev_res.returncode != 0:
                raise ContractViolation(
                    "packaging_git_failed",
                    f"Local PR branch '{pkg.pr_branch}' does not exist in '{repo_root}'",
                )
            pushed_sha = rev_res.stdout.strip()
            push_res = _run_git(
                ["push", clean_remote, f"refs/heads/{pkg.pr_branch}:refs/heads/{pkg.pr_branch}"],
                repo_root,
            )
            if push_res.returncode != 0:
                raise ContractViolation(
                    "packaging_git_failed",
                    f"git push to '{clean_remote}' failed: {push_res.stderr.strip()}",
                )

        now = datetime.now(timezone.utc)
        audit_key = f"publish-{pkg.package_id}-{uuid.uuid4().hex[:12]}"
        audit_payload = {
            "package_id": pkg.package_id,
            "run_id": pkg.run_id,
            "pr_branch": pkg.pr_branch,
            "remote": redact_text(clean_remote),
            "pushed_sha": pushed_sha,
            "actor": redact_text(actor.strip() or "operator"),
            "published_at": now.isoformat(),
        }
        await self.store.record_command(
            idempotency_key=audit_key,
            request_hash=self.store.compute_request_hash(audit_payload),
            run_id=pkg.run_id,
            scope="pr_publish",
            response_payload=audit_payload,
            status="completed",
        )
        return PublishResult(
            package_id=pkg.package_id,
            run_id=pkg.run_id,
            pr_branch=pkg.pr_branch,
            remote=redact_text(clean_remote),
            pushed_sha=pushed_sha,
            published=True,
            published_at=now,
        )

    async def export(
        self,
        package_id: str,
        *,
        output_path: Optional[Union[str, Path]] = None,
    ) -> ExportResult:
        """Export a redacted Markdown dossier of a PR package, optionally writing atomically to disk."""
        pkg = await self.get_package_by_id(package_id)
        if pkg is None:
            raise ContractViolation("resource_not_found", f"PR package '{package_id}' does not exist")

        run_rec = await self.store.get_run(pkg.run_id)
        if run_rec is not None and pkg.artifact_path and pkg.artifact_sha256:
            art_file = Path(run_rec["spec"].repo_root) / pkg.artifact_path
            if art_file.exists():
                actual_sha = hashlib.sha256(art_file.read_bytes()).hexdigest()
                if actual_sha != pkg.artifact_sha256:
                    raise ContractViolation(
                        "artifact_tampered",
                        f"Retained PR package artifact '{pkg.artifact_id}' failed SHA-256 verification",
                    )

        redacted_md = redact_text(pkg.description_markdown)
        md_bytes = redacted_md.encode("utf-8")
        if output_path is not None:
            target = Path(output_path)
            sha256_hex, size_bytes = _write_bytes_atomic(target, md_bytes)
            exp_path: Optional[str] = str(target)
        else:
            sha256_hex = hashlib.sha256(md_bytes).hexdigest()
            size_bytes = len(md_bytes)
            exp_path = None

        return ExportResult(
            package_id=pkg.package_id,
            run_id=pkg.run_id,
            export_path=exp_path,
            sha256=sha256_hex,
            size_bytes=size_bytes,
            markdown=redacted_md,
        )


__all__ = [
    "ExportResult",
    "PRPackage",
    "PRPackager",
    "PublishResult",
]
