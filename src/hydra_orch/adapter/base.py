"""Base adapter definitions for Hydra Orchestrator connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from hydra_orch.model import ChatMessage


class LimitHitException(Exception):
    """Raised when a provider hits rate limits, quota limits (e.g. Claude 5h limit) or context exhaustion."""

    def __init__(self, provider: str, message: str, reset_in_seconds: Optional[int] = None):
        super().__init__(f"Limit reached for {provider}: {message}")
        self.provider = provider
        self.message = message
        self.reset_in_seconds = reset_in_seconds


class BaseAdapter(ABC):
    """Abstract base class for all provider adapters."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.is_healthy = True
        self.last_error: Optional[str] = None
        self.limit_reset_timestamp: Optional[float] = None

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider connection is alive and ready to receive requests."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Stream generation tokens as string chunks.
        
        Must raise LimitHitException if provider hits quota or token limit.
        """
        pass

    async def generate(
        self,
        messages: List[ChatMessage],
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Helper for non-streaming response."""
        full_text = []
        async for chunk in self.generate_stream(messages, options):
            full_text.append(chunk)
        return "".join(full_text)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status for this adapter."""
        return {
            "name": self.name,
            "type": self.__class__.__name__,
            "healthy": self.is_healthy,
            "last_error": self.last_error,
            "limit_reset_timestamp": self.limit_reset_timestamp,
        }
