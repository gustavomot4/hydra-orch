"""Stream checkpointer and code stitcher with string overlap elimination."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite

logger = logging.getLogger(__name__)


def stitch_code_blocks(part1: str, part2: str, max_check_lines: int = 15) -> str:
    """Seamlessly concatenates two partial code blocks, eliminating overlapping lines."""
    if not part1:
        return part2
    if not part2:
        return part1

    lines1 = part1.splitlines(keepends=True)
    lines2 = part2.splitlines(keepends=True)

    # Check for identical overlapping lines at the boundary
    max_overlap = min(len(lines1), len(lines2), max_check_lines)
    best_overlap = 0

    for k in range(max_overlap, 0, -1):
        suffix = lines1[-k:]
        prefix = lines2[:k]
        if [l.strip() for l in suffix] == [l.strip() for l in prefix]:
            best_overlap = k
            break

    if best_overlap > 0:
        # Discard the overlapping prefix from part2
        stitched = "".join(lines1) + "".join(lines2[best_overlap:])
    else:
        stitched = "".join(lines1) + "\n" + "".join(lines2)

    return stitched


class EngineCheckpointer:
    """Persists real-time token streaming checkpoints and manages seamless auto-resumes."""

    def __init__(self, db_path: str = ".hydra/state.db"):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
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
        
        # Compute last 15 lines as anchor block
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

    def build_resume_prompt(self, anchor_block: str, target_file: Optional[str] = None) -> str:
        """Constructs anchor continuation prompt per PRD v5.0 specification."""
        file_hint = f" for file `{target_file}`" if target_file else ""
        return (
            f"The previous generation{file_hint} was interrupted during streaming. "
            f"Continue writing the code exactly starting from the last line of the anchor block below. "
            f"DO NOT repeat the anchor block lines and DO NOT add conversational markdown explanations:\n\n"
            f"```\n{anchor_block}\n```"
        )
