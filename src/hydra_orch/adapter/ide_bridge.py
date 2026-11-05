"""IDE Bridge Adapter for Agentic IDEs (Antigravity & Cursor)."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from hydra_orch.adapter.base import BaseAdapter, LimitHitException
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


class IdeBridgeAdapter(BaseAdapter):
    """Bridge adapter connecting to Antigravity and Cursor agentic runtime servers."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.bridge_url: str = config.get("bridge_url", "http://127.0.0.1:9330").rstrip("/")
        self.timeout: float = config.get("timeout_seconds", 120.0)

    async def is_available(self) -> bool:
        """Check if IDE agentic bridge server is listening."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.bridge_url}/health")
                self.is_healthy = resp.status_code == 200
                return self.is_healthy
        except Exception as e:
            self.last_error = f"IDE bridge connection failed: {e}"
            self.is_healthy = False
            return False

    async def generate_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        payload = {
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "options": options or {},
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.bridge_url}/v1/chat/agent", json=payload) as response:
                    if response.status_code == 429:
                        raise LimitHitException(
                            provider=self.name,
                            message="IDE agent rate limit or token quota exceeded",
                            reset_in_seconds=300,
                        )

                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            raw_data = line[len("data: ") :].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                data = json.loads(raw_data)
                                text_chunk = data.get("content") or data.get("delta", {}).get("content", "")
                                if text_chunk:
                                    yield text_chunk
                            except json.JSONDecodeError:
                                yield raw_data
                        else:
                            yield line
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise LimitHitException(
                    provider=self.name,
                    message="IDE agent rate limit hit",
                    reset_in_seconds=300,
                )
            self.last_error = str(e)
            raise
        except Exception as e:
            self.last_error = str(e)
            raise
