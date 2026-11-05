import pytest
import os
import tempfile
from hydra_orch.core.checkpointer import StreamCheckpointer


@pytest.mark.asyncio
async def test_checkpointer_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_checkpoints.sqlite")
        cp = StreamCheckpointer(db_path=db_path)
        await cp.initialize()

        # Save checkpoint
        await cp.save_checkpoint(
            session_id="test-session-1",
            task_id="task-100",
            provider="claude_pro",
            prompt="Write a fastapi backend",
            accumulated_content="from fastapi import FastAPI...",
            status="in_progress",
        )

        record = await cp.get_checkpoint("test-session-1")
        assert record is not None
        assert record["session_id"] == "test-session-1"
        assert record["provider"] == "claude_pro"
        assert "from fastapi import FastAPI" in record["accumulated_content"]

        # Test rate limit tracking
        assert await cp.is_provider_limited("claude_pro") is False
        await cp.record_provider_limit("claude_pro", reset_in_seconds=300, reason="5h quota reached")
        assert await cp.is_provider_limited("claude_pro") is True
        rem = await cp.get_remaining_limit_seconds("claude_pro")
        assert rem > 0
