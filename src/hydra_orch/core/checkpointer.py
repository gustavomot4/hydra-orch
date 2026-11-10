"""Transactional execution store, migration runner, and stream checkpointer backed by SQLite WAL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union
import uuid

import aiosqlite
from pydantic import BaseModel

from hydra_orch.core.redaction import redact
from hydra_orch.model import (
    Artifact,
    CheckResult,
    ContractViolation,
    HandoffCheckpoint,
    InvalidTransitionError,
    ProcessStatus,
    ReviewDecision,
    RunEvent,
    RunSpec,
    RunStatus,
    TaskAttempt,
    TaskResult,
    TaskSpec,
    TaskStatus,
    review_result,
    transition_status,
    validate_result,
)

logger = logging.getLogger(__name__)

_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migration"


class StorageError(ContractViolation):
    """Base exception for persistence and migration errors."""


class IdempotencyConflictError(StorageError):
    """Raised when an idempotency_key is reused with a different request payload hash."""

    def __init__(self, message: str):
        super().__init__("idempotency_conflict", message)


class OptimisticLockError(StorageError):
    """Raised when expected_revision does not match the persisted entity revision."""

    def __init__(self, message: str):
        super().__init__("optimistic_lock_conflict", message)


class StorageIntegrityError(StorageError):
    """Raised when foreign key, uniqueness, or check constraints fail in SQLite."""

    def __init__(self, message: str):
        super().__init__("storage_integrity_error", message)


class StorageLockError(StorageError):
    """Raised when SQLite remains locked beyond busy_timeout."""

    def __init__(self, message: str):
        super().__init__("storage_lock_error", message)


class MigrationError(StorageError):
    """Raised when a migration file is invalid, fails to apply, or has a checksum mismatch."""

    def __init__(self, message: str):
        super().__init__("migration_error", message)


def _split_sql_statements(sql_script: str) -> List[str]:
    """Split a SQL script into complete statements using sqlite3.complete_statement."""
    statements: List[str] = []
    buffer: List[str] = []

    for raw_line in sql_script.splitlines(keepends=True):
        stripped = raw_line.strip()
        if not buffer and (not stripped or stripped.startswith("--")):
            continue
        buffer.append(raw_line)
        candidate = "".join(buffer)
        if sqlite3.complete_statement(candidate):
            stmt = candidate.strip()
            if stmt:
                statements.append(stmt)
            buffer.clear()

    remainder = "".join(buffer).strip()
    if remainder:
        non_comment = [
            line
            for line in remainder.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if non_comment:
            statements.append(remainder)

    return statements


def _compute_migration_checksum(sql_text: str) -> str:
    """Compute platform-independent SHA-256 checksum normalizing CRLF to LF."""
    normalized = sql_text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 string across Python versions (including Python 3.10 where trailing 'Z' is not accepted)."""
    clean = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class ExecutionStore:
    """Canonical SQLite WAL store for runs, tasks, attempts, results, reviews, events, and migrations."""

    def __init__(
        self,
        db_path: Union[str, Path] = ".orchestrator/checkpoints.sqlite",
        migrations_dir: Optional[Union[str, Path]] = None,
    ):
        self.db_path = str(db_path)
        if migrations_dir is not None:
            self.migrations_dir = Path(migrations_dir)
        elif _DEFAULT_MIGRATIONS_DIR.exists():
            self.migrations_dir = _DEFAULT_MIGRATIONS_DIR
        else:
            self.migrations_dir = Path("migration")
        self._initialized = False
        self._migrations_applied = False

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        try:
            async with aiosqlite.connect(self.db_path, timeout=5.0, isolation_level=None) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("PRAGMA journal_mode = WAL;")
                await db.execute("PRAGMA busy_timeout = 5000;")
                await db.execute("PRAGMA foreign_keys = ON;")
                await db.execute("PRAGMA synchronous = NORMAL;")
                yield db
        except sqlite3.OperationalError as exc:
            msg = str(exc)
            if "locked" in msg.lower() or "busy" in msg.lower():
                raise StorageLockError(f"Database locked at {self.db_path}: {msg}") from exc
            raise

    @asynccontextmanager
    async def _transaction(self, db: aiosqlite.Connection) -> AsyncIterator[aiosqlite.Connection]:
        try:
            await db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            msg = str(exc)
            if "locked" in msg.lower() or "busy" in msg.lower():
                raise StorageLockError(f"Database locked on BEGIN IMMEDIATE: {msg}") from exc
            raise

        try:
            yield db
            await db.execute("COMMIT")
        except Exception as exc:
            try:
                await db.execute("ROLLBACK")
            except Exception:
                pass
            if isinstance(exc, ContractViolation):
                raise
            if isinstance(exc, sqlite3.IntegrityError):
                raise StorageIntegrityError(str(exc)) from exc
            if isinstance(exc, sqlite3.OperationalError):
                msg = str(exc)
                if "locked" in msg.lower() or "busy" in msg.lower():
                    raise StorageLockError(f"Database lock timeout: {msg}") from exc
            raise

    async def initialize(self, apply_migrations: bool = True) -> None:
        """Initialize the SQLite WAL database, preserve legacy tables, and apply pending migrations."""
        if apply_migrations and self._migrations_applied:
            return
        if not apply_migrations and self._initialized:
            return

        async with self._connect() as db:
            if apply_migrations:
                await self._apply_migrations(db)
                self._migrations_applied = True
            else:
                await self._ensure_legacy_tables(db)

        self._initialized = True
        logger.info(f"ExecutionStore initialized at {self.db_path} (WAL mode)")

    async def _ensure_legacy_tables(self, db: aiosqlite.Connection) -> None:
        async with self._transaction(db):
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    session_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    provider TEXT,
                    prompt TEXT,
                    accumulated_content TEXT,
                    status TEXT,
                    created_at REAL,
                    updated_at REAL,
                    reset_at REAL,
                    metadata TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_limits (
                    provider TEXT PRIMARY KEY,
                    status TEXT,
                    limit_hit_at REAL,
                    resets_at REAL,
                    reason TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS active_generations (
                    session_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    model TEXT,
                    prompt TEXT,
                    accumulated_content TEXT,
                    status TEXT,
                    created_at REAL,
                    updated_at REAL,
                    reset_at REAL,
                    anchor_block TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_status (
                    model TEXT PRIMARY KEY,
                    resets_at REAL,
                    remaining_percent REAL,
                    updated_at REAL
                )
                """
            )

    async def _preserve_legacy_tables_in_tx(self, db: aiosqlite.Connection) -> None:
        """If a pre-T03 handoff_checkpoints table exists without attempt_id, rename it to legacy_handoff_checkpoints."""
        cursor = await db.execute("PRAGMA table_info(handoff_checkpoints);")
        columns = await cursor.fetchall()
        if not columns:
            return
        col_names = {row["name"] for row in columns}
        if "attempt_id" not in col_names:
            legacy_cur = await db.execute("PRAGMA table_info(legacy_handoff_checkpoints);")
            legacy_cols = await legacy_cur.fetchall()
            if not legacy_cols:
                await db.execute("ALTER TABLE handoff_checkpoints RENAME TO legacy_handoff_checkpoints;")
            else:
                await db.execute("INSERT OR IGNORE INTO legacy_handoff_checkpoints SELECT * FROM handoff_checkpoints;")
                await db.execute("DROP TABLE handoff_checkpoints;")

    def _migration_catalog(self) -> List[Dict[str, Any]]:
        if not self.migrations_dir.is_dir():
            raise MigrationError(f"Migrations directory not found: {self.migrations_dir}")
        files = sorted(self.migrations_dir.glob("*.sql"))
        if not files:
            raise MigrationError(f"No SQL migration files found in {self.migrations_dir}")
        catalog: List[Dict[str, Any]] = []
        versions = set()
        for path in files:
            version = path.stem.split("_", 1)[0]
            if len(version) != 4 or not version.isascii() or not version.isdigit() or version in versions:
                raise MigrationError(f"Invalid or duplicate migration version: {path.name}")
            versions.add(version)
            try:
                sql = path.read_text(encoding="utf-8")
                down_path = self.migrations_dir / "rollback" / path.name
                down = down_path.read_text(encoding="utf-8") if down_path.exists() else None
            except (OSError, UnicodeError) as exc:
                raise MigrationError(f"Failed to read migration {path.name}: {exc}") from exc
            if not _split_sql_statements(sql):
                raise MigrationError(f"Migration file {path.name} contains no executable SQL statements")
            catalog.append({"version": version, "name": path.name, "sql": sql,
                            "checksum": _compute_migration_checksum(sql), "down": down,
                            "rollback_checksum": _compute_migration_checksum(down) if down is not None else None})
        return catalog

    async def _ensure_migration_metadata(self, db: aiosqlite.Connection) -> None:
        async with self._transaction(db):
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            columns = {r["name"] for r in await (await db.execute("PRAGMA table_info(schema_migrations)")).fetchall()}
            if "checksum" not in columns:
                await db.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT DEFAULT ''")
            if "rollback_checksum" not in columns:
                await db.execute("ALTER TABLE schema_migrations ADD COLUMN rollback_checksum TEXT")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS migration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK (direction IN ('up','down')),
                    checksum TEXT NOT NULL,
                    backup_path TEXT,
                    status TEXT NOT NULL CHECK (status IN ('applied','failed')),
                    message TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

    async def _migration_backup(self, backup_path: Optional[Union[str, Path]] = None) -> str:
        """Snapshot committed WAL pages through SQLite's backup API, never file copy.

        The caller holds BEGIN IMMEDIATE without pending writes, so another reader
        can copy a consistent snapshot while concurrent writers remain excluded.
        """
        target = Path(backup_path) if backup_path is not None else (
            Path(self.db_path).parent / "migration_backup" / f"{uuid.uuid4().hex}.sqlite"
        )
        if target.resolve() == Path(self.db_path).resolve():
            raise MigrationError("Migration backup must not overwrite the live database")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation protects existing operator files and symlinks.
            import os
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            async with aiosqlite.connect(self.db_path) as source:
                async with aiosqlite.connect(target) as destination:
                    await source.backup(destination)
                    result = await (await destination.execute("PRAGMA integrity_check")).fetchone()
                    if result is None or result[0] != "ok":
                        raise MigrationError("Migration backup failed integrity_check")
        except (OSError, sqlite3.Error) as exc:
            raise MigrationError(f"Migration backup failed: {exc}") from exc
        return str(target.resolve())

    async def _record_migration_history(
        self, db: aiosqlite.Connection, migration: Dict[str, Any], direction: str,
        status: str, backup_path: Optional[str], message: Optional[str] = None,
    ) -> None:
        checksum = migration["checksum"] if direction == "up" else migration["rollback_checksum"]
        await db.execute("""
            INSERT INTO migration_history (version, direction, checksum, backup_path, status, message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (migration["version"], direction, checksum, backup_path, status, redact(message)))

    async def _validate_migration_state(
        self, db: aiosqlite.Connection, catalog: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        applied = {row["version"]: dict(row) for row in await (await db.execute(
            "SELECT version, name, checksum, rollback_checksum FROM schema_migrations ORDER BY version"
        )).fetchall()}
        known = {m["version"] for m in catalog}
        if set(applied) - known:
            raise MigrationError("Database contains migrations missing from this checkout")
        seen_pending = False
        for migration in catalog:
            existing = applied.get(migration["version"])
            if existing is None:
                seen_pending = True
                continue
            if seen_pending:
                raise MigrationError("Applied migration history is not a contiguous prefix")
            if existing["name"] != migration["name"] or (
                existing["checksum"] and existing["checksum"] != migration["checksum"]
            ):
                raise MigrationError(f"Checksum mismatch for applied migration {migration['version']}")
            if existing["rollback_checksum"] != migration["rollback_checksum"]:
                raise MigrationError(f"Rollback checksum mismatch for migration {migration['version']}")
        return applied

    async def _apply_migrations(self, db: aiosqlite.Connection) -> None:
        catalog = self._migration_catalog()
        await self._ensure_migration_metadata(db)
        current: Optional[Dict[str, Any]] = None
        backup = None
        try:
            # Re-read versions after acquiring the writer lock: concurrent startups
            # must not both try to apply the same migration.
            async with self._transaction(db):
                applied = await self._validate_migration_state(db, catalog)
                pending = [m for m in catalog if m["version"] not in applied]
                if pending:
                    current = pending[0]
                    backup = await self._migration_backup()
                for current in pending:
                    if current["version"] == "0001":
                        await self._preserve_legacy_tables_in_tx(db)
                    for statement in _split_sql_statements(current["sql"]):
                        await db.execute(statement)
                    violations = await (await db.execute("PRAGMA foreign_key_check")).fetchall()
                    if violations:
                        raise MigrationError("Migration leaves foreign key violations")
                    await db.execute("""
                        INSERT INTO schema_migrations (version, name, checksum, rollback_checksum)
                        VALUES (?, ?, ?, ?)
                    """, (current["version"], current["name"], current["checksum"], current["rollback_checksum"]))
                    await self._record_migration_history(db, current, "up", "applied", backup)
        except Exception as exc:
            if current is not None:
                await self._record_migration_history(db, current, "up", "failed", backup, str(exc))
            if isinstance(exc, MigrationError):
                raise
            raise MigrationError(f"Failed applying migration: {redact(str(exc))}") from exc

    async def rollback_migrations(
        self, target_version: str, *, backup_path: Optional[Union[str, Path]] = None,
    ) -> List[str]:
        """Explicit offline downgrade with backup, script integrity and refusal of data loss.

        Never initializes first: doing so would reapply a previous downgrade.
        The same store remains at the selected version; a fresh store upgrades again.
        """
        catalog = self._migration_catalog()
        if target_version not in {m["version"] for m in catalog}:
            raise MigrationError("Rollback target must be a known, applied migration")
        current: Optional[Dict[str, Any]] = None
        backup = None
        reverted: List[str] = []
        async with self._connect() as db:
            await self._ensure_migration_metadata(db)
            try:
                async with self._transaction(db):
                    applied = await self._validate_migration_state(db, catalog)
                    if target_version not in applied:
                        raise MigrationError("Rollback target is not applied")
                    pending = [m for m in reversed(catalog) if m["version"] in applied and m["version"] > target_version]
                    if any(m["down"] is None for m in pending):
                        raise MigrationError("Rollback script missing; refusing downgrade")
                    if pending:
                        current = pending[0]
                        backup = await self._migration_backup(backup_path)
                    for current in pending:
                        for statement in _split_sql_statements(current["down"]):
                            await db.execute(statement)
                        if await (await db.execute("PRAGMA foreign_key_check")).fetchall():
                            raise MigrationError("Rollback leaves foreign key violations")
                        await db.execute("DELETE FROM schema_migrations WHERE version = ?", (current["version"],))
                        await self._record_migration_history(db, current, "down", "applied", backup)
                        reverted.append(current["version"])
            except Exception as exc:
                if current is not None:
                    await self._record_migration_history(db, current, "down", "failed", backup, str(exc))
                if isinstance(exc, MigrationError):
                    raise
                raise MigrationError(f"Failed rolling back migration (data or SQL guard): {redact(str(exc))}") from exc
        self._initialized = self._migrations_applied = True
        return reverted

    async def get_migration_history(self) -> List[Dict[str, Any]]:
        """Read audit without upgrading a database deliberately downgraded offline."""
        async with self._connect() as db:
            exists = await (await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_history'"
            )).fetchone()
            if not exists:
                return []
            return [dict(r) for r in await (await db.execute("SELECT * FROM migration_history ORDER BY id")).fetchall()]

    async def get_pragmas(self) -> Dict[str, Any]:
        """Return active SQLite connection pragmas for verification."""
        await self.initialize()
        async with self._connect() as db:
            jm = await (await db.execute("PRAGMA journal_mode;")).fetchone()
            fk = await (await db.execute("PRAGMA foreign_keys;")).fetchone()
            bt = await (await db.execute("PRAGMA busy_timeout;")).fetchone()
            sync = await (await db.execute("PRAGMA synchronous;")).fetchone()
            return {
                "journal_mode": str(jm[0]).lower() if jm else "",
                "foreign_keys": int(fk[0]) if fk else 0,
                "busy_timeout": int(bt[0]) if bt else 0,
                "synchronous": int(sync[0]) if sync else 0,
            }

    async def get_applied_migrations(self) -> List[Dict[str, Any]]:
        """List all applied schema migrations in version order."""
        await self.initialize()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version ASC"
            )
            return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def compute_request_hash(payload: Union[BaseModel, Dict[str, Any], str, bytes]) -> str:
        """Compute deterministic SHA-256 hash for idempotency verification."""
        if isinstance(payload, bytes):
            raw = payload
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        elif isinstance(payload, BaseModel):
            dumped = payload.model_dump(mode="json")
            raw = json.dumps(dumped, sort_keys=True, separators=(",", ":")).encode("utf-8")
        elif isinstance(payload, dict):
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        else:
            raise TypeError(f"Unsupported payload type for hashing: {type(payload).__name__}")
        return hashlib.sha256(raw).hexdigest()

    async def _insert_event_in_tx(
        self,
        db: aiosqlite.Connection,
        *,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> RunEvent:
        if thread_id and not session_id:
            raise StorageIntegrityError("Thread events require a session")
        if session_id:
            session = await (await db.execute("SELECT run_id FROM sessions WHERE id=?", (session_id,))).fetchone()
            if session is None or session["run_id"] != run_id:
                raise StorageIntegrityError("Event session must belong to its run")
        if thread_id:
            thread = await (await db.execute("SELECT session_id FROM threads WHERE id=?", (thread_id,))).fetchone()
            if thread is None or thread["session_id"] != session_id:
                raise StorageIntegrityError("Event thread must belong to its session")
        seq_cur = await db.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM events WHERE run_id = ?",
            (run_id,),
        )
        seq_row = await seq_cur.fetchone()
        next_seq = int(seq_row["next_seq"]) if seq_row else 1

        corr_id = correlation_id or f"corr-{run_id}-{next_seq}"
        safe_payload: Dict[str, Any] = redact(json.loads(json.dumps(payload or {}, sort_keys=True)))
        event = RunEvent(
            seq=next_seq,
            run_id=run_id,
            correlation_id=corr_id,
            task_id=task_id,
            attempt_id=attempt_id,
            session_id=session_id,
            thread_id=thread_id,
            event_type=event_type,  # type: ignore[arg-type]
            redacted_payload=safe_payload,
        )
        event_id = f"evt-{run_id}-{next_seq}"
        payload_json = json.dumps(event.redacted_payload, sort_keys=True)
        created_at = event.timestamp.isoformat()

        # Keep the M1-only migration fixtures readable without expansion columns.
        if session_id:
            await db.execute("""INSERT INTO events
                (id,run_id,seq,correlation_id,task_id,attempt_id,type,payload_json,created_at,session_id,thread_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (event_id, event.run_id, event.seq, event.correlation_id,
                event.task_id, event.attempt_id, event.event_type, payload_json, created_at, session_id, thread_id))
            return event
        await db.execute(
            """
            INSERT INTO events (id, run_id, seq, correlation_id, task_id, attempt_id, type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.run_id,
                event.seq,
                event.correlation_id,
                event.task_id,
                event.attempt_id,
                event.event_type,
                payload_json,
                created_at,
            ),
        )
        return event

    async def record_command(
        self,
        idempotency_key: str,
        request_hash: str,
        run_id: Optional[str] = None,
        scope: str = "run",
        response_payload: Optional[Dict[str, Any]] = None,
        status: str = "completed",
    ) -> Tuple[bool, Optional[str]]:
        """Record an idempotent command or return (False, existing_run_id) if already recorded with the same hash."""
        await self.initialize()
        async with self._connect() as db:
            async with self._transaction(db):
                return await self._record_command_in_tx(
                    db,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    run_id=run_id,
                    scope=scope,
                    response_payload=response_payload,
                    status=status,
                )

    async def _record_command_in_tx(
        self,
        db: aiosqlite.Connection,
        *,
        idempotency_key: str,
        request_hash: str,
        run_id: Optional[str] = None,
        scope: str = "run",
        response_payload: Optional[Dict[str, Any]] = None,
        status: str = "completed",
    ) -> Tuple[bool, Optional[str]]:
        cur = await db.execute(
            "SELECT id, request_hash, run_id, response_json, status FROM commands WHERE scope = ? AND idempotency_key = ?",
            (scope, idempotency_key),
        )
        existing = await cur.fetchone()
        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise IdempotencyConflictError(
                    f"Idempotency key '{idempotency_key}' in scope '{scope}' was already used with a different request payload"
                )
            return False, existing["run_id"]

        cmd_id = f"cmd-{uuid.uuid4().hex[:16]}"
        resp_json = json.dumps(response_payload, sort_keys=True) if response_payload is not None else None
        await db.execute(
            """
            INSERT INTO commands (id, scope, idempotency_key, request_hash, run_id, response_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (cmd_id, scope, idempotency_key, request_hash, run_id, resp_json, status),
        )
        return True, run_id

    async def _save_run_in_tx(
        self,
        db: aiosqlite.Connection,
        run_spec: RunSpec,
        initial_status: RunStatus,
        correlation_id: Optional[str],
        request_hash: str,
    ) -> None:
        proj_cur = await db.execute(
            "SELECT id, canonical_root FROM projects WHERE id = ? OR canonical_root = ?",
            (run_spec.project_id, run_spec.repo_root),
        )
        proj_rows = await proj_cur.fetchall()
        if not proj_rows:
            proj_name = Path(run_spec.repo_root.rstrip("/\\")).name or run_spec.project_id
            await db.execute(
                """
                INSERT INTO projects (id, canonical_root, name, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (run_spec.project_id, run_spec.repo_root, proj_name),
            )
        else:
            for prow in proj_rows:
                if prow["id"] != run_spec.project_id or prow["canonical_root"] != run_spec.repo_root:
                    raise StorageIntegrityError(
                        f"Project conflict: ({run_spec.project_id}, {run_spec.repo_root}) conflicts with "
                        f"({prow['id']}, {prow['canonical_root']})"
                    )

        await db.execute(
            """
            INSERT INTO runs (id, project_id, spec_json, base_sha, status, revision, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
            """,
            (
                run_spec.run_id,
                run_spec.project_id,
                run_spec.model_dump_json(),
                run_spec.base_sha,
                initial_status.value,
            ),
        )

        bp = run_spec.budget_policy
        await db.execute(
            """
            INSERT INTO budget_policies (
                id, run_id, max_usd, max_tokens_in, max_tokens_out,
                max_wall_seconds, alert_threshold_pct, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'))
            """,
            (
                f"budget-{run_spec.run_id}",
                run_spec.run_id,
                bp.max_usd,
                bp.max_tokens_in,
                bp.max_tokens_out,
                bp.max_wall_seconds,
                bp.alert_threshold_pct,
            ),
        )

        for task in run_spec.tasks:
            await db.execute(
                """
                INSERT INTO tasks (id, run_id, spec_json, status, revision, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'))
                """,
                (
                    task.task_id,
                    run_spec.run_id,
                    task.model_dump_json(),
                    TaskStatus.PENDING.value,
                ),
            )

        for task in run_spec.tasks:
            for prereq_id in task.dependencies:
                await db.execute(
                    """
                    INSERT INTO task_dependencies (task_id, prerequisite_id)
                    VALUES (?, ?)
                    """,
                    (task.task_id, prereq_id),
                )

        await self._insert_event_in_tx(
            db,
            run_id=run_spec.run_id,
            event_type="run.created",
            payload={
                "status": initial_status.value,
                "project_id": run_spec.project_id,
                "orchestration_mode": run_spec.orchestration_mode,
                "task_count": len(run_spec.tasks),
            },
            correlation_id=correlation_id,
        )

        await self._record_command_in_tx(
            db,
            idempotency_key=run_spec.idempotency_key,
            request_hash=request_hash,
            run_id=run_spec.run_id,
            scope="run",
            response_payload={"run_id": run_spec.run_id, "status": initial_status.value},
            status="completed",
        )

    async def save_run_atomic(
        self,
        run_spec: RunSpec,
        initial_status: Union[RunStatus, str] = RunStatus.QUEUED,
        correlation_id: Optional[str] = None,
        request_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist project, run, budget policy, tasks, DAG dependencies, command, and run.created event atomically."""
        await self.initialize()
        status_enum = initial_status if isinstance(initial_status, RunStatus) else RunStatus(initial_status)
        req_hash = request_hash or self.compute_request_hash(run_spec)

        async with self._connect() as db:
            async with self._transaction(db):
                cur = await db.execute(
                    "SELECT request_hash, run_id FROM commands WHERE scope = 'run' AND idempotency_key = ?",
                    (run_spec.idempotency_key,),
                )
                existing_cmd = await cur.fetchone()
                if existing_cmd is not None:
                    if existing_cmd["request_hash"] != req_hash:
                        raise IdempotencyConflictError(
                            f"Idempotency key '{run_spec.idempotency_key}' already exists with a different payload"
                        )
                    raise StorageIntegrityError(
                        f"Run with idempotency_key '{run_spec.idempotency_key}' already persisted as '{existing_cmd['run_id']}'"
                    )

                await self._save_run_in_tx(
                    db,
                    run_spec=run_spec,
                    initial_status=status_enum,
                    correlation_id=correlation_id,
                    request_hash=req_hash,
                )

        run_record = await self.get_run(run_spec.run_id)
        assert run_record is not None
        return run_record

    async def submit_run_idempotent(
        self,
        run_spec: RunSpec,
        request_hash: Optional[str] = None,
        initial_status: Union[RunStatus, str] = RunStatus.QUEUED,
        correlation_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Submit a RunSpec idempotently. Returns (created, run_record) or raises IdempotencyConflictError on payload mismatch."""
        await self.initialize()
        status_enum = initial_status if isinstance(initial_status, RunStatus) else RunStatus(initial_status)
        req_hash = request_hash or self.compute_request_hash(run_spec)

        created = False
        target_run_id = run_spec.run_id

        async with self._connect() as db:
            async with self._transaction(db):
                cur = await db.execute(
                    "SELECT request_hash, run_id FROM commands WHERE scope = 'run' AND idempotency_key = ?",
                    (run_spec.idempotency_key,),
                )
                existing = await cur.fetchone()
                if existing is not None:
                    if existing["request_hash"] != req_hash:
                        raise IdempotencyConflictError(
                            f"Idempotency key '{run_spec.idempotency_key}' reused with different RunSpec payload"
                        )
                    target_run_id = existing["run_id"]
                    created = False
                else:
                    await self._save_run_in_tx(
                        db,
                        run_spec=run_spec,
                        initial_status=status_enum,
                        correlation_id=correlation_id,
                        request_hash=req_hash,
                    )
                    created = True

        run_record = await self.get_run(target_run_id)
        if run_record is None:
            raise StorageIntegrityError(f"Persisted run '{target_run_id}' could not be loaded")
        return created, run_record

    async def record_event_atomic(
        self,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> RunEvent:
        """Allocate next monotonic sequence number for run_id and persist RunEvent in a transaction."""
        await self.initialize()
        async with self._connect() as db:
            async with self._transaction(db):
                return await self._insert_event_in_tx(
                    db,
                    run_id=run_id,
                    event_type=event_type,
                    payload=payload,
                    correlation_id=correlation_id,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    session_id=session_id,
                    thread_id=thread_id,
                )

    async def _assert_no_pending_hitl_in_tx(self, db: aiosqlite.Connection, run_id: str) -> None:
        pending = await (await db.execute(
            "SELECT 1 FROM commands WHERE scope='hitl' AND status='pending' AND run_id=? LIMIT 1",
            (run_id,),
        )).fetchone()
        if pending:
            raise ContractViolation("hitl_pending", "Human intervention must be resolved before dispatch")

    async def update_run_status_atomic(
        self,
        run_id: str,
        new_status: Union[RunStatus, str],
        expected_revision: int,
        event_type: str,
        event_payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transition RunStatus with optimistic concurrency check and emit RunEvent in the same transaction."""
        await self.initialize()
        target_status = new_status if isinstance(new_status, RunStatus) else RunStatus(new_status)

        async with self._connect() as db:
            async with self._transaction(db):
                cur = await db.execute(
                    "SELECT status, revision FROM runs WHERE id = ?",
                    (run_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    raise StorageIntegrityError(f"Run '{run_id}' does not exist")

                current_revision = int(row["revision"])
                if current_revision != expected_revision:
                    raise OptimisticLockError(
                        f"Optimistic lock failed for run '{run_id}': expected revision {expected_revision}, found {current_revision}"
                    )

                if target_status == RunStatus.RUNNING:
                    await self._assert_no_pending_hitl_in_tx(db, run_id)
                current_status = RunStatus(row["status"])
                transition_status(current_status, target_status)

                update_cur = await db.execute(
                    """
                    UPDATE runs
                    SET status = ?, revision = revision + 1, updated_at = datetime('now')
                    WHERE id = ? AND revision = ?
                    """,
                    (target_status.value, run_id, expected_revision),
                )
                if update_cur.rowcount != 1:
                    raise OptimisticLockError(f"Concurrent modification detected for run '{run_id}'")

                payload = {
                    "previous_status": current_status.value,
                    "status": target_status.value,
                    "revision": expected_revision + 1,
                    **(event_payload or {}),
                }
                await self._insert_event_in_tx(
                    db,
                    run_id=run_id,
                    event_type=event_type,
                    payload=payload,
                    correlation_id=correlation_id,
                )

        updated = await self.get_run(run_id)
        assert updated is not None
        return updated

    async def update_task_status_atomic(
        self,
        task_id: str,
        new_status: Union[TaskStatus, str],
        expected_revision: int,
        event_type: str,
        event_payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transition TaskStatus with optimistic concurrency check and emit RunEvent in the same transaction."""
        await self.initialize()
        target_status = new_status if isinstance(new_status, TaskStatus) else TaskStatus(new_status)

        async with self._connect() as db:
            async with self._transaction(db):
                cur = await db.execute(
                    "SELECT run_id, status, revision FROM tasks WHERE id = ?",
                    (task_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    raise StorageIntegrityError(f"Task '{task_id}' does not exist")

                current_revision = int(row["revision"])
                if current_revision != expected_revision:
                    raise OptimisticLockError(
                        f"Optimistic lock failed for task '{task_id}': expected revision {expected_revision}, found {current_revision}"
                    )

                if target_status == TaskStatus.RUNNING:
                    await self._assert_no_pending_hitl_in_tx(db, row["run_id"])
                current_status = TaskStatus(row["status"])
                transition_status(current_status, target_status)

                update_cur = await db.execute(
                    """
                    UPDATE tasks
                    SET status = ?, revision = revision + 1, updated_at = datetime('now')
                    WHERE id = ? AND revision = ?
                    """,
                    (target_status.value, task_id, expected_revision),
                )
                if update_cur.rowcount != 1:
                    raise OptimisticLockError(f"Concurrent modification detected for task '{task_id}'")

                payload = {
                    "previous_status": current_status.value,
                    "status": target_status.value,
                    "revision": expected_revision + 1,
                    **(event_payload or {}),
                }
                await self._insert_event_in_tx(
                    db,
                    run_id=row["run_id"],
                    event_type=event_type,
                    payload=payload,
                    correlation_id=correlation_id,
                    task_id=task_id,
                    attempt_id=attempt_id,
                )

        updated = await self.get_task(task_id)
        assert updated is not None
        return updated

    async def save_attempt_atomic(
        self,
        attempt: TaskAttempt,
        event_type: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> TaskAttempt:
        """Create or update a TaskAttempt and emit its correlated RunEvent atomically."""
        await self.initialize()

        async with self._connect() as db:
            async with self._transaction(db):
                task_cur = await db.execute(
                    "SELECT run_id FROM tasks WHERE id = ?",
                    (attempt.task_id,),
                )
                task_row = await task_cur.fetchone()
                if task_row is None:
                    raise StorageIntegrityError(f"Task '{attempt.task_id}' does not exist")
                if task_row["run_id"] != attempt.run_id:
                    raise StorageIntegrityError(
                        f"Attempt run_id '{attempt.run_id}' does not match task run_id '{task_row['run_id']}'"
                    )

                if attempt.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}:
                    await self._assert_no_pending_hitl_in_tx(db, attempt.run_id)

                existing_cur = await db.execute(
                    "SELECT process_status FROM attempts WHERE id = ?",
                    (attempt.attempt_id,),
                )
                existing = await existing_cur.fetchone()

                provider_model_json = json.dumps(
                    {"provider": attempt.provider, "model": attempt.model},
                    sort_keys=True,
                )
                started_iso = attempt.started_at.isoformat() if attempt.started_at else None
                finished_iso = attempt.finished_at.isoformat() if attempt.finished_at else None
                attempt_json = attempt.model_dump_json()

                if existing is None:
                    await db.execute(
                        """
                        INSERT INTO attempts (
                            id, task_id, run_id, ordinal, executor_id, provider_model_json,
                            provider_session, base_sha, workspace_path, process_status,
                            exit_code, exit_reason, started_at, finished_at, attempt_json, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            attempt.attempt_id,
                            attempt.task_id,
                            attempt.run_id,
                            attempt.ordinal,
                            attempt.executor_id,
                            provider_model_json,
                            attempt.provider_session,
                            attempt.base_sha,
                            attempt.workspace_path,
                            attempt.process_status.value,
                            attempt.exit_code,
                            attempt.exit_reason,
                            started_iso,
                            finished_iso,
                            attempt_json,
                        ),
                    )
                    resolved_event_type = event_type or (
                        "attempt.started"
                        if attempt.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}
                        else "attempt.finished"
                    )
                else:
                    old_status = ProcessStatus(existing["process_status"])
                    transition_status(old_status, attempt.process_status)
                    await db.execute(
                        """
                        UPDATE attempts
                        SET provider_session = ?, workspace_path = ?, process_status = ?,
                            exit_code = ?, exit_reason = ?, started_at = ?, finished_at = ?, attempt_json = ?
                        WHERE id = ?
                        """,
                        (
                            attempt.provider_session,
                            attempt.workspace_path,
                            attempt.process_status.value,
                            attempt.exit_code,
                            attempt.exit_reason,
                            started_iso,
                            finished_iso,
                            attempt_json,
                            attempt.attempt_id,
                        ),
                    )
                    resolved_event_type = event_type or (
                        "attempt.started"
                        if attempt.process_status == ProcessStatus.RUNNING
                        else "attempt.finished"
                    )

                payload = {
                    "ordinal": attempt.ordinal,
                    "executor_id": attempt.executor_id,
                    "provider": attempt.provider,
                    "model": attempt.model,
                    "process_status": attempt.process_status.value,
                    **(event_payload or {}),
                }
                if attempt.exit_code is not None:
                    payload["exit_code"] = attempt.exit_code
                if attempt.exit_reason is not None:
                    payload["exit_reason"] = attempt.exit_reason

                await self._insert_event_in_tx(
                    db,
                    run_id=attempt.run_id,
                    event_type=resolved_event_type,
                    payload=payload,
                    correlation_id=correlation_id,
                    task_id=attempt.task_id,
                    attempt_id=attempt.attempt_id,
                )

        return attempt

    async def _upsert_artifact_in_tx(self, db: aiosqlite.Connection, artifact: Artifact) -> None:
        cur = await db.execute(
            "SELECT id, run_id, attempt_id, relative_path, kind, sha256, size_bytes FROM artifacts WHERE id = ?",
            (artifact.artifact_id,),
        )
        existing = await cur.fetchone()
        if existing is not None:
            if (
                existing["run_id"] != artifact.run_id
                or existing["relative_path"] != artifact.relative_path
                or existing["sha256"] != artifact.sha256
                or int(existing["size_bytes"]) != artifact.size_bytes
                or existing["kind"] != artifact.kind
            ):
                raise StorageIntegrityError(
                    f"Artifact '{artifact.artifact_id}' already exists with different metadata or sha256"
                )
            return

        await db.execute(
            """
            INSERT INTO artifacts (id, run_id, attempt_id, relative_path, kind, sha256, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                artifact.artifact_id,
                artifact.run_id,
                artifact.attempt_id,
                artifact.relative_path,
                artifact.kind,
                artifact.sha256,
                artifact.size_bytes,
            ),
        )

    async def save_artifact(
        self,
        artifact: Union[Artifact, Dict[str, Any]],
        emit_event: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Artifact:
        """Persist an Artifact record (and optional artifact.created RunEvent) atomically."""
        await self.initialize()
        art = artifact if isinstance(artifact, Artifact) else Artifact.model_validate(artifact)

        async with self._connect() as db:
            async with self._transaction(db):
                await self._upsert_artifact_in_tx(db, art)
                if emit_event:
                    await self._insert_event_in_tx(
                        db,
                        run_id=art.run_id,
                        event_type="artifact.created",
                        payload={
                            "artifact_id": art.artifact_id,
                            "relative_path": art.relative_path,
                            "kind": art.kind,
                            "sha256": art.sha256,
                            "size_bytes": art.size_bytes,
                        },
                        correlation_id=correlation_id,
                        attempt_id=art.attempt_id,
                    )

        return art

    async def save_task_result_atomic(
        self,
        task_spec: TaskSpec,
        attempt: TaskAttempt,
        result: TaskResult,
        expected_task_revision: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> TaskResult:
        """Validate attribution, persist artifacts/checks/result, update task & attempt status, and emit RunEvent atomically."""
        await self.initialize()
        require_acceptance = result.task_status in {TaskStatus.READY_FOR_REVIEW, TaskStatus.ACCEPTED}
        validate_result(task_spec, attempt, result, require_acceptance=require_acceptance)

        async with self._connect() as db:
            async with self._transaction(db):
                task_cur = await db.execute(
                    "SELECT status, revision FROM tasks WHERE id = ? AND run_id = ?",
                    (task_spec.task_id, task_spec.run_id),
                )
                task_row = await task_cur.fetchone()
                if task_row is None:
                    raise StorageIntegrityError(f"Task '{task_spec.task_id}' not found in run '{task_spec.run_id}'")

                current_task_rev = int(task_row["revision"])
                if expected_task_revision is not None and current_task_rev != expected_task_revision:
                    raise OptimisticLockError(
                        f"Task '{task_spec.task_id}' revision mismatch: expected {expected_task_revision}, found {current_task_rev}"
                    )

                current_task_status = TaskStatus(task_row["status"])
                transition_status(current_task_status, result.task_status)

                att_cur = await db.execute(
                    "SELECT process_status FROM attempts WHERE id = ? AND task_id = ?",
                    (attempt.attempt_id, task_spec.task_id),
                )
                att_row = await att_cur.fetchone()
                if att_row is None:
                    raise StorageIntegrityError(f"Attempt '{attempt.attempt_id}' not found for task '{task_spec.task_id}'")

                persisted_proc_status = ProcessStatus(att_row["process_status"])
                if persisted_proc_status != attempt.process_status:
                    transition_status(persisted_proc_status, attempt.process_status)
                    await db.execute(
                        """
                        UPDATE attempts
                        SET process_status = ?, exit_code = ?, exit_reason = ?,
                            started_at = COALESCE(?, started_at),
                            finished_at = ?, attempt_json = ?
                        WHERE id = ?
                        """,
                        (
                            attempt.process_status.value,
                            attempt.exit_code,
                            attempt.exit_reason,
                            attempt.started_at.isoformat() if attempt.started_at else None,
                            attempt.finished_at.isoformat() if attempt.finished_at else None,
                            attempt.model_dump_json(),
                            attempt.attempt_id,
                        ),
                    )

                for art in result.artifacts:
                    await self._upsert_artifact_in_tx(db, art)

                if result.task_status in {TaskStatus.READY_FOR_REVIEW, TaskStatus.ACCEPTED}:
                    outcome = "success"
                elif result.task_status == TaskStatus.NEEDS_CONTEXT:
                    outcome = "partial"
                else:
                    outcome = "failure"

                await db.execute(
                    """
                    INSERT INTO results (
                        id, attempt_id, run_id, exit_code, simulated, outcome,
                        task_status, process_status, summary, patch_commit_sha,
                        patch_artifact_id, revision, result_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        result.result_id,
                        result.attempt_id,
                        result.run_id,
                        result.exit_code,
                        1 if result.simulated else 0,
                        outcome,
                        result.task_status.value,
                        result.process_status.value,
                        result.summary,
                        result.patch_commit_sha,
                        result.patch_artifact_id,
                        result.revision,
                        result.model_dump_json(),
                    ),
                )

                for check in result.checks_executed:
                    check_row_id = f"chk-{result.result_id}-{check.check_id}"
                    await db.execute(
                        """
                        INSERT INTO check_results (
                            id, result_id, integration_id, check_id, command_json, cwd,
                            tested_sha, exit_code, duration_seconds,
                            stdout_artifact_id, stderr_artifact_id, output_artifact_id,
                            started_at, finished_at
                        )
                        VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                        """,
                        (
                            check_row_id,
                            result.result_id,
                            check.check_id,
                            json.dumps(list(check.command)),
                            check.cwd,
                            check.tested_sha,
                            check.exit_code,
                            check.duration_seconds,
                            check.stdout_artifact_id,
                            check.stderr_artifact_id,
                            check.stdout_artifact_id,
                        ),
                    )

                await db.execute(
                    """
                    UPDATE tasks
                    SET status = ?, revision = revision + 1, updated_at = datetime('now')
                    WHERE id = ? AND revision = ?
                    """,
                    (result.task_status.value, task_spec.task_id, current_task_rev),
                )

                event_type_map = {
                    TaskStatus.READY_FOR_REVIEW: "task.ready_for_review",
                    TaskStatus.NEEDS_CONTEXT: "task.needs_context",
                    TaskStatus.FAILED: "task.failed",
                    TaskStatus.BLOCKED: "task.failed",
                    TaskStatus.CANCELLED: "task.cancelled",
                }
                ev_type = event_type_map.get(result.task_status, "task.completed")
                await self._insert_event_in_tx(
                    db,
                    run_id=result.run_id,
                    event_type=ev_type,
                    payload={
                        "result_id": result.result_id,
                        "task_status": result.task_status.value,
                        "process_status": result.process_status.value,
                        "simulated": result.simulated,
                        "revision": result.revision,
                    },
                    correlation_id=correlation_id,
                    task_id=task_spec.task_id,
                    attempt_id=attempt.attempt_id,
                )

        return result

    async def record_review_atomic(
        self,
        task_spec: TaskSpec,
        attempt: TaskAttempt,
        decision: ReviewDecision,
        expected_task_revision: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> TaskResult:
        """Validate and persist an explicit ReviewDecision, updating result and task atomically."""
        await self.initialize()

        async with self._connect() as db:
            async with self._transaction(db):
                res_cur = await db.execute(
                    "SELECT revision, result_json FROM results WHERE id = ?",
                    (decision.result_id,),
                )
                res_row = await res_cur.fetchone()
                if res_row is None:
                    raise StorageIntegrityError(f"Result '{decision.result_id}' does not exist")

                current_res_rev = int(res_row["revision"])
                if current_res_rev != decision.expected_revision:
                    raise OptimisticLockError(
                        f"Optimistic lock failed for result '{decision.result_id}': "
                        f"expected revision {decision.expected_revision}, found {current_res_rev}"
                    )

                current_result = TaskResult.model_validate_json(res_row["result_json"])
                reviewed_result = review_result(task_spec, attempt, current_result, decision)

                task_cur = await db.execute(
                    "SELECT status, revision FROM tasks WHERE id = ? AND run_id = ?",
                    (task_spec.task_id, task_spec.run_id),
                )
                task_row = await task_cur.fetchone()
                if task_row is None:
                    raise StorageIntegrityError(f"Task '{task_spec.task_id}' does not exist")

                current_task_rev = int(task_row["revision"])
                if expected_task_revision is not None and current_task_rev != expected_task_revision:
                    raise OptimisticLockError(
                        f"Optimistic lock failed for task '{task_spec.task_id}': "
                        f"expected revision {expected_task_revision}, found {current_task_rev}"
                    )

                transition_status(TaskStatus(task_row["status"]), reviewed_result.task_status)

                review_id = f"rev-{decision.result_id}-{reviewed_result.revision}"
                await db.execute(
                    """
                    INSERT INTO reviews (id, result_id, actor, decision, reason, expected_revision, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        decision.result_id,
                        decision.actor,
                        decision.decision,
                        decision.reason,
                        decision.expected_revision,
                        decision.created_at.isoformat(),
                    ),
                )

                outcome = "success" if decision.decision == "accepted" else "failure"
                await db.execute(
                    """
                    UPDATE results
                    SET task_status = ?, outcome = ?, revision = ?, result_json = ?
                    WHERE id = ? AND revision = ?
                    """,
                    (
                        reviewed_result.task_status.value,
                        outcome,
                        reviewed_result.revision,
                        reviewed_result.model_dump_json(),
                        decision.result_id,
                        current_res_rev,
                    ),
                )

                await db.execute(
                    """
                    UPDATE tasks
                    SET status = ?, revision = revision + 1, updated_at = datetime('now')
                    WHERE id = ? AND revision = ?
                    """,
                    (reviewed_result.task_status.value, task_spec.task_id, current_task_rev),
                )

                ev_type = "task.accepted" if decision.decision == "accepted" else "task.rejected"
                await self._insert_event_in_tx(
                    db,
                    run_id=task_spec.run_id,
                    event_type=ev_type,
                    payload={
                        "result_id": decision.result_id,
                        "actor": decision.actor,
                        "decision": decision.decision,
                        "reason": decision.reason,
                        "result_revision": reviewed_result.revision,
                        "task_revision": current_task_rev + 1,
                    },
                    correlation_id=correlation_id,
                    task_id=task_spec.task_id,
                    attempt_id=attempt.attempt_id,
                )

        return reviewed_result

    async def save_handoff_checkpoint_atomic(
        self,
        checkpoint: HandoffCheckpoint,
        run_id: str,
        correlation_id: Optional[str] = None,
    ) -> HandoffCheckpoint:
        """Persist a canonical HandoffCheckpoint and emit attempt.handoff_created atomically."""
        await self.initialize()

        async with self._connect() as db:
            async with self._transaction(db):
                att_cur = await db.execute(
                    "SELECT task_id, run_id FROM attempts WHERE id = ?",
                    (checkpoint.attempt_id,),
                )
                att_row = await att_cur.fetchone()
                if att_row is None:
                    raise StorageIntegrityError(f"Attempt '{checkpoint.attempt_id}' does not exist")
                if att_row["run_id"] != run_id:
                    raise StorageIntegrityError(
                        f"Attempt '{checkpoint.attempt_id}' belongs to run '{att_row['run_id']}', not '{run_id}'"
                    )

                await db.execute(
                    """
                    INSERT INTO handoff_checkpoints (
                        id, attempt_id, instructions_json, git_sha, diff_artifact_ids,
                        tools_executed_json, partial_output_json, next_step, checkpoint_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        checkpoint.checkpoint_id,
                        checkpoint.attempt_id,
                        json.dumps(list(checkpoint.instructions)),
                        checkpoint.git_sha,
                        json.dumps(list(checkpoint.diff_artifact_ids)),
                        json.dumps([t.model_dump(mode="json") for t in checkpoint.tools_executed]),
                        json.dumps(
                            {
                                "partial_output": checkpoint.partial_output,
                                "git_status": checkpoint.git_status,
                                "affected_files": list(checkpoint.affected_files),
                                "check_artifact_ids": list(checkpoint.check_artifact_ids),
                                "decisions": list(checkpoint.decisions),
                            },
                            sort_keys=True,
                        ),
                        checkpoint.next_step,
                        checkpoint.model_dump_json(),
                    ),
                )

                await self._insert_event_in_tx(
                    db,
                    run_id=run_id,
                    event_type="attempt.handoff_created",
                    payload={
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "git_sha": checkpoint.git_sha,
                        "next_step": checkpoint.next_step,
                    },
                    correlation_id=correlation_id,
                    task_id=att_row["task_id"],
                    attempt_id=checkpoint.attempt_id,
                )

        return checkpoint

    async def reconcile_interrupted_attempts(
        self,
        run_id: Optional[str] = None,
        reason: str = "process_interrupted_on_restart",
    ) -> List[Dict[str, Any]]:
        """Reconcile attempts left in queued/running after crash, marking running tasks as blocked atomically."""
        await self.initialize()
        reconciled: List[Dict[str, Any]] = []

        async with self._connect() as db:
            async with self._transaction(db):
                if run_id is not None:
                    cur = await db.execute(
                        """
                        SELECT a.id AS attempt_id, a.task_id, a.run_id, a.process_status,
                               a.started_at, a.attempt_json,
                               t.status AS task_status, t.revision AS task_revision
                        FROM attempts a
                        JOIN tasks t ON t.id = a.task_id
                        WHERE a.process_status IN ('queued', 'running') AND a.run_id = ?
                        ORDER BY a.created_at ASC, a.ordinal ASC
                        """,
                        (run_id,),
                    )
                else:
                    cur = await db.execute(
                        """
                        SELECT a.id AS attempt_id, a.task_id, a.run_id, a.process_status,
                               a.started_at, a.attempt_json,
                               t.status AS task_status, t.revision AS task_revision
                        FROM attempts a
                        JOIN tasks t ON t.id = a.task_id
                        WHERE a.process_status IN ('queued', 'running')
                        ORDER BY a.created_at ASC, a.ordinal ASC
                        """
                    )

                rows = await cur.fetchall()
                now_dt = datetime.now(timezone.utc)

                for row in rows:
                    att_id = row["attempt_id"]
                    task_id = row["task_id"]
                    r_id = row["run_id"]
                    old_proc_status = ProcessStatus(row["process_status"])
                    target_proc_status = (
                        ProcessStatus.CANCELLED
                        if old_proc_status == ProcessStatus.QUEUED
                        else ProcessStatus.CRASHED
                    )
                    transition_status(old_proc_status, target_proc_status)

                    finished_dt = now_dt
                    updated_attempt_json: Optional[str] = None
                    if row["attempt_json"]:
                        att_data = json.loads(row["attempt_json"])
                        if att_data.get("started_at"):
                            started_dt = _parse_iso_datetime(att_data["started_at"])
                            if finished_dt < started_dt:
                                finished_dt = started_dt
                        att_data["process_status"] = target_proc_status.value
                        att_data["finished_at"] = finished_dt.isoformat()
                        att_data["exit_reason"] = reason
                        validated_att = TaskAttempt.model_validate(att_data)
                        updated_attempt_json = validated_att.model_dump_json()

                    finished_iso = finished_dt.isoformat()
                    await db.execute(
                        """
                        UPDATE attempts
                        SET process_status = ?, finished_at = ?, exit_reason = ?, attempt_json = COALESCE(?, attempt_json)
                        WHERE id = ?
                        """,
                        (target_proc_status.value, finished_iso, reason, updated_attempt_json, att_id),
                    )

                    await self._insert_event_in_tx(
                        db,
                        run_id=r_id,
                        event_type="attempt.finished",
                        payload={
                            "reconciled": True,
                            "previous_process_status": old_proc_status.value,
                            "process_status": target_proc_status.value,
                            "exit_reason": reason,
                        },
                        task_id=task_id,
                        attempt_id=att_id,
                    )

                    old_task_status = TaskStatus(row["task_status"])
                    new_task_status = old_task_status
                    if old_task_status in {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.NEEDS_CONTEXT}:
                        new_task_status = transition_status(old_task_status, TaskStatus.BLOCKED)
                        await db.execute(
                            """
                            UPDATE tasks
                            SET status = ?, revision = revision + 1, updated_at = datetime('now')
                            WHERE id = ?
                            """,
                            (new_task_status.value, task_id),
                        )
                        await self._insert_event_in_tx(
                            db,
                            run_id=r_id,
                            event_type="task.failed",
                            payload={
                                "reconciled": True,
                                "previous_status": old_task_status.value,
                                "status": new_task_status.value,
                                "reason": reason,
                            },
                            task_id=task_id,
                            attempt_id=att_id,
                        )

                    reconciled.append(
                        {
                            "attempt_id": att_id,
                            "task_id": task_id,
                            "run_id": r_id,
                            "previous_process_status": old_proc_status.value,
                            "process_status": target_proc_status.value,
                            "previous_task_status": old_task_status.value,
                            "task_status": new_task_status.value,
                            "exit_reason": reason,
                        }
                    )

        return reconciled

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a persisted run record with deserialized RunSpec."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT id, project_id, spec_json, base_sha, status, revision, created_at, updated_at FROM runs WHERE id = ?",
                (run_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            data = dict(row)
            data["spec"] = RunSpec.model_validate_json(data["spec_json"])
            data["status"] = RunStatus(data["status"]).value
            data["revision"] = int(data["revision"])
            return data

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a persisted task record with deserialized TaskSpec and DAG dependencies."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT id, run_id, spec_json, status, revision, created_at, updated_at FROM tasks WHERE id = ?",
                (task_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            dep_cur = await db.execute(
                "SELECT prerequisite_id FROM task_dependencies WHERE task_id = ? ORDER BY prerequisite_id ASC",
                (task_id,),
            )
            deps = tuple(r["prerequisite_id"] for r in await dep_cur.fetchall())
            data = dict(row)
            data["spec"] = TaskSpec.model_validate_json(data["spec_json"])
            data["status"] = TaskStatus(data["status"]).value
            data["revision"] = int(data["revision"])
            data["dependencies"] = deps
            return data

    async def list_tasks(self, run_id: str) -> List[Dict[str, Any]]:
        """List all tasks belonging to a run."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT id FROM tasks WHERE run_id = ? ORDER BY created_at ASC, id ASC",
                (run_id,),
            )
            task_ids = [r["id"] for r in await cur.fetchall()]
        results: List[Dict[str, Any]] = []
        for tid in task_ids:
            t = await self.get_task(tid)
            if t is not None:
                results.append(t)
        return results

    async def get_attempt(self, attempt_id: str) -> Optional[TaskAttempt]:
        """Retrieve a persisted TaskAttempt by ID."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                """
                SELECT id, task_id, run_id, ordinal, executor_id, provider_model_json,
                       provider_session, base_sha, workspace_path, process_status,
                       exit_code, exit_reason, started_at, finished_at, attempt_json
                FROM attempts WHERE id = ?
                """,
                (attempt_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            if row["attempt_json"]:
                return TaskAttempt.model_validate_json(row["attempt_json"])
            pm = json.loads(row["provider_model_json"])
            return TaskAttempt(
                attempt_id=row["id"],
                task_id=row["task_id"],
                run_id=row["run_id"],
                ordinal=int(row["ordinal"]),
                executor_id=row["executor_id"],
                provider=pm["provider"],
                model=pm["model"],
                base_sha=row["base_sha"],
                workspace_path=row["workspace_path"],
                provider_session=row["provider_session"],
                process_status=ProcessStatus(row["process_status"]),
                exit_code=row["exit_code"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                exit_reason=row["exit_reason"],
            )

    async def list_attempts(self, task_id: str) -> List[TaskAttempt]:
        """List all attempts for a task in ordinal order."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT id FROM attempts WHERE task_id = ? ORDER BY ordinal ASC",
                (task_id,),
            )
            ids = [r["id"] for r in await cur.fetchall()]
        attempts: List[TaskAttempt] = []
        for aid in ids:
            att = await self.get_attempt(aid)
            if att is not None:
                attempts.append(att)
        return attempts

    async def get_result(self, result_id: str) -> Optional[TaskResult]:
        """Retrieve a persisted TaskResult by result_id."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT result_json FROM results WHERE id = ?",
                (result_id,),
            )
            row = await cur.fetchone()
            if row is None or not row["result_json"]:
                return None
            return TaskResult.model_validate_json(row["result_json"])

    async def get_result_by_attempt(self, attempt_id: str) -> Optional[TaskResult]:
        """Retrieve a persisted TaskResult by attempt_id."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT result_json FROM results WHERE attempt_id = ?",
                (attempt_id,),
            )
            row = await cur.fetchone()
            if row is None or not row["result_json"]:
                return None
            return TaskResult.model_validate_json(row["result_json"])

    async def get_artifacts(
        self,
        run_id: str,
        attempt_id: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[Artifact]:
        """Retrieve persisted artifacts for a run (optionally filtered by attempt_id or kind)."""
        await self.initialize()
        query = "SELECT id, run_id, attempt_id, relative_path, kind, sha256, size_bytes FROM artifacts WHERE run_id = ?"
        params: List[Any] = [run_id]
        if attempt_id is not None:
            query += " AND attempt_id = ?"
            params.append(attempt_id)
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY created_at ASC, id ASC"

        async with self._connect() as db:
            cur = await db.execute(query, tuple(params))
            rows = await cur.fetchall()
            return [
                Artifact(
                    artifact_id=r["id"],
                    run_id=r["run_id"],
                    attempt_id=r["attempt_id"],
                    relative_path=r["relative_path"],
                    kind=r["kind"],
                    sha256=r["sha256"],
                    size_bytes=int(r["size_bytes"]),
                )
                for r in rows
            ]

    async def get_handoff_checkpoint(self, attempt_id: str) -> Optional[HandoffCheckpoint]:
        """Retrieve the persisted HandoffCheckpoint for an attempt."""
        await self.initialize()
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT checkpoint_json FROM handoff_checkpoints WHERE attempt_id = ?",
                (attempt_id,),
            )
            row = await cur.fetchone()
            if row is None or not row["checkpoint_json"]:
                return None
            return HandoffCheckpoint.model_validate_json(row["checkpoint_json"])

    async def get_events(
        self,
        run_id: str,
        after_seq: Optional[int] = None,
        limit: Optional[int] = None,
        *,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> List[RunEvent]:
        """Replay RunEvents in strict monotonic sequence order (for SSE Last-Event-ID or audit)."""
        await self.initialize()
        min_seq = after_seq if after_seq is not None else 0
        query = (
            "SELECT * "
            "FROM events WHERE run_id = ? AND seq > ?"
        )
        params: List[Any] = [run_id, min_seq]
        for column, value in (("session_id", session_id), ("thread_id", thread_id)):
            if value is not None:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY seq ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        async with self._connect() as db:
            cur = await db.execute(query, tuple(params))
            rows = await cur.fetchall()
            events: List[RunEvent] = []
            for r in rows:
                ts_raw = r["created_at"]
                if "T" in ts_raw:
                    ts = _parse_iso_datetime(ts_raw)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                events.append(
                    RunEvent(
                        seq=int(r["seq"]),
                        run_id=r["run_id"],
                        correlation_id=r["correlation_id"] or f"corr-{r['run_id']}-{r['seq']}",
                        task_id=r["task_id"],
                        attempt_id=r["attempt_id"],
                        session_id=r["session_id"] if "session_id" in r.keys() else None,
                        thread_id=r["thread_id"] if "thread_id" in r.keys() else None,
                        timestamp=ts,
                        event_type=r["type"],
                        redacted_payload=redact(json.loads(r["payload_json"])),
                    )
                )
            return events

    # -------------------------------------------------------------------------
    # Legacy StreamCheckpointer compatibility methods
    # -------------------------------------------------------------------------

    async def save_checkpoint(
        self,
        session_id: str,
        task_id: Optional[str],
        provider: str,
        prompt: str,
        accumulated_content: str,
        status: str = "in_progress",
        reset_at: Optional[float] = None,
        metadata: Optional[str] = None,
    ) -> None:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            async with self._transaction(db):
                await db.execute(
                    """
                    INSERT INTO checkpoints (session_id, task_id, provider, prompt, accumulated_content, status, created_at, updated_at, reset_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        accumulated_content = excluded.accumulated_content,
                        status = excluded.status,
                        provider = excluded.provider,
                        updated_at = excluded.updated_at,
                        reset_at = excluded.reset_at,
                        metadata = excluded.metadata
                    """,
                    (
                        session_id,
                        task_id or "",
                        provider,
                        prompt,
                        accumulated_content,
                        status,
                        now,
                        now,
                        reset_at or 0.0,
                        metadata or "{}",
                    ),
                )

    async def get_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM checkpoints WHERE session_id = ?", (session_id,))
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def record_provider_limit(self, provider: str, reset_in_seconds: int, reason: str = "") -> None:
        await self.initialize()
        now = time.time()
        resets_at = now + reset_in_seconds
        async with self._connect() as db:
            async with self._transaction(db):
                await db.execute(
                    """
                    INSERT INTO provider_limits (provider, status, limit_hit_at, resets_at, reason)
                    VALUES (?, 'rate_limited', ?, ?, ?)
                    ON CONFLICT(provider) DO UPDATE SET
                        status = 'rate_limited',
                        limit_hit_at = excluded.limit_hit_at,
                        resets_at = excluded.resets_at,
                        reason = excluded.reason
                    """,
                    (provider, now, resets_at, reason),
                )
        logger.warning(f"Provider {provider} marked as rate-limited until {resets_at} ({reset_in_seconds}s)")

    async def is_provider_limited(self, provider: str) -> bool:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT resets_at FROM provider_limits WHERE provider = ? AND status = 'rate_limited'",
                (provider,),
            )
            row = await cursor.fetchone()
            if row:
                resets_at = row[0]
                if now < resets_at:
                    return True
                async with self._transaction(db):
                    await db.execute("UPDATE provider_limits SET status = 'ready' WHERE provider = ?", (provider,))
        return False

    async def get_remaining_limit_seconds(self, provider: str) -> int:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT resets_at FROM provider_limits WHERE provider = ? AND status = 'rate_limited'",
                (provider,),
            )
            row = await cursor.fetchone()
            if row:
                resets_at = row[0]
                diff = int(resets_at - now)
                return max(diff, 0)
        return 0

    def build_hot_handoff_prompt(
        self,
        original_prompt: str,
        partial_output: str,
        failed_provider: str,
        git_diff: Optional[str] = None,
    ) -> str:
        """Constructs a structured handover prompt prioritizing Git/Worktree state."""
        diff_section = (
            f"\nVerified Git Diff in Worktree:\n```diff\n{git_diff}\n```\n"
            if git_diff
            else ""
        )
        return (
            f"--- [HYDRA STRUCTURED HANDOFF TRIGGERED] ---\n"
            f"The previous executor/model ({failed_provider}) hit a quota limit.\n"
            f"Original Task Objective:\n{original_prompt}\n"
            f"{diff_section}\n"
            f"Last recorded output / check state:\n"
            f"```\n{partial_output}\n```\n\n"
            f"INSTRUCTION: Inspect the current worktree state and complete the remaining "
            f"acceptance criteria without duplicating completed modifications."
        )


class StreamCheckpointer(ExecutionStore):
    """Backwards-compatible alias and subclass of ExecutionStore for stream checkpointing."""


__all__ = [
    "ExecutionStore",
    "StreamCheckpointer",
    "StorageError",
    "IdempotencyConflictError",
    "OptimisticLockError",
    "StorageIntegrityError",
    "StorageLockError",
    "MigrationError",
]
