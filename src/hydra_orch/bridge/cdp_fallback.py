"""Optional Chrome DevTools Protocol fallback bridge for web apps without CLI OAuth."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional
from hydra_orch.adapter.ui_cdp import UiCdpAdapter
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


class CdpFallbackBridge:
    """Provides fallback web CDP connections when OmniRoute CLI OAuth is unavailable."""

    def __init__(self, cdp_port: int = 9222, target_url: str = ""):
        self.adapter = UiCdpAdapter(
            name="cdp_fallback",
            config={"cdp_port": cdp_port, "target_url": target_url},
        )

    async def is_available(self) -> bool:
        return await self.adapter.is_available()

    async def generate_stream(
        self, messages: List[ChatMessage], options: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[str]:
        async for chunk in self.adapter.generate_stream(messages, options):
            yield chunk
