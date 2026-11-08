"""Resilience and stream checkpointer backed by SQLite WAL."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
import aiosqlite

logger = logging.getLogger(__name__)


class StreamCheckpointer:
    """Tracks LLM streaming progress, worktree handoff state, limits, and recovery state in SQLite WAL."""

    def __init__(self, db_path: str = ".orchestrator/checkpoints.sqlite"):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if not existing and enforce WAL + foreign_keys + busy_timeout."""
        if self._initialized:
            return

        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=5000;")
            await db.execute("PRAGMA foreign_keys=ON;")
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
                CREATE TABLE IF NOT EXISTS handoff_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    task_id TEXT,
                    git_sha TEXT,
                    git_diff TEXT,
                    modified_files_json TEXT,
                    checks_summary_json TEXT,
                    next_step TEXT,
                    created_at REAL
                )
                """
            )
            await db.commit()

        self._initialized = True
        logger.info(f"StreamCheckpointer initialized at {self.db_path} (WAL mode)")

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
        async with aiosqlite.connect(self.db_path) as db:
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
            await db.commit()

    async def get_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM checkpoints WHERE session_id = ?", (session_id,))
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def record_provider_limit(self, provider: str, reset_in_seconds: int, reason: str = "") -> None:
        await self.initialize()
        now = time.time()
        resets_at = now + reset_in_seconds
        async with aiosqlite.connect(self.db_path) as db:
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
            await db.commit()
        logger.warning(f"Provider {provider} marked as rate-limited until {resets_at} ({reset_in_seconds}s)")

    async def is_provider_limited(self, provider: str) -> bool:
        await self.initialize()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT resets_at FROM provider_limits WHERE provider = ? AND status = 'rate_limited'",
                (provider,),
            )
            row = await cursor.fetchone()
            if row:
                resets_at = row[0]
                if now < resets_at:
                    return True
                else:
                    await db.execute("UPDATE provider_limits SET status = 'ready' WHERE provider = ?", (provider,))
                    await db.commit()
        return False

    async def get_remaining_limit_seconds(self, provider: str) -> int:
        await self.initialize()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
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
