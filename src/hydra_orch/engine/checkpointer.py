"""Engine checkpointer and worktree/code handoff helpers."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
import aiosqlite

logger = logging.getLogger(__name__)


def stitch_code_blocks(part1: str, part2: str, max_check_lines: int = 15) -> str:
    """Seamlessly concatenates two partial code blocks, eliminating exact overlapping lines
    while strictly preserving indentation."""
    if not part1:
        return part2
    if not part2:
        return part1

    lines1 = part1.splitlines(keepends=True)
    lines2 = part2.splitlines(keepends=True)

    max_overlap = min(len(lines1), len(lines2), max_check_lines)
    best_overlap = 0

    for k in range(max_overlap, 0, -1):
        suffix = [l.rstrip("\r\n") for l in lines1[-k:]]
        prefix = [l.rstrip("\r\n") for l in lines2[:k]]
        if suffix == prefix:
            best_overlap = k
            break

    if best_overlap > 0:
        return "".join(lines1) + "".join(lines2[best_overlap:])
    return "".join(lines1) + ("\n" if not part1.endswith("\n") else "") + "".join(lines2)


class EngineCheckpointer:
    """Persists real-time execution checkpoints and worktree handoff state in .orchestrator/checkpoints.sqlite."""

    def __init__(self, db_path: str = ".orchestrator/checkpoints.sqlite"):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=5000;")
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
            await db.commit()

        self._initialized = True
        logger.info(f"EngineCheckpointer initialized at {self.db_path}")

    async def save_chunk(
        self,
        session_id: str,
        model: str,
        prompt: str,
        accumulated_content: str,
        status: str = "in_progress",
        reset_at: Optional[float] = None,
    ) -> None:
        await self.initialize()
        now = time.time()

        lines = accumulated_content.splitlines()
        anchor = "\n".join(lines[-15:]) if lines else ""

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO active_generations (session_id, task_id, model, prompt, accumulated_content, status, created_at, updated_at, reset_at, anchor_block)
                VALUES (?, '', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    accumulated_content = excluded.accumulated_content,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    reset_at = excluded.reset_at,
                    anchor_block = excluded.anchor_block
                """,
                (session_id, model, prompt, accumulated_content, status, now, now, reset_at or 0.0, anchor),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM active_generations WHERE session_id = ?", (session_id,))
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    def build_resume_prompt(
        self,
        anchor_block: str,
        target_file: Optional[str] = None,
        git_diff: Optional[str] = None,
    ) -> str:
        """Constructs a continuation prompt combining worktree state and anchor context."""
        file_hint = f" for file `{target_file}`" if target_file else ""
        diff_block = f"\nCurrent Worktree Diff:\n```diff\n{git_diff}\n```\n" if git_diff else ""
        return (
            f"The previous generation{file_hint} was interrupted during execution.{diff_block}\n"
            f"Continue completing the implementation starting from the state below without repeating "
            f"already applied lines:\n\n"
            f"```\n{anchor_block}\n```"
        )
