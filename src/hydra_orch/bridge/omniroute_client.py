"""OmniRoute Gateway client for OAuth subscriptions and 5h quota monitoring."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


class OmniRouteClient:
    """HTTP and SSE client connecting to local OmniRoute daemon (:20128)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:20128/v1",
        quota_api_url: str = "http://127.0.0.1:20128/api/usage/quota",
        timeout: float = 120.0,
        enabled: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.quota_api_url = quota_api_url
        self.timeout = timeout
        self.enabled = enabled

    async def is_available(self) -> bool:
        """Check if OmniRoute daemon is active and listening."""
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False

    async def get_quota_status(self) -> Dict[str, Any]:
        """Fetch current 5h quota windows and token usage from OmniRoute.

        Conforms to RT09 / RT17 (GAP A03): When OmniRoute is offline, marks status as 'unknown'
        rather than claiming 100% observed availability.
        """
        unknown = {
            "status": "unknown",
            **{name: {"status": "unknown", "remaining_percent": None, "resets_in_seconds": None}
               for name in ("claude_pro", "chatgpt_plus", "gemini_pro")},
        }
        if not self.enabled:
            return unknown
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(self.quota_api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    data.setdefault("status", "observed")
                    return data
        except Exception as e:
            logger.debug(f"Could not reach OmniRoute quota API: {e}")
        return unknown

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        allow_offline_mock: bool = False,
    ) -> AsyncIterator[str]:
        """Stream tokens from OmniRoute gateway via standard SSE."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 429:
                        raise RuntimeError(f"OmniRoute 429 Quota Exhausted for model {model}")
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            raw = line[len("data: ") :].strip()
                            if raw == "[DONE]":
                                break
                            try:
                                data = json.loads(raw)
                                choices = data.get("choices", [])
                                if choices:
                                    content = choices[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except httpx.ConnectError as e:
            if allow_offline_mock:
                logger.warning("OmniRoute daemon not reachable on :20128. Yielding dry-run simulated response.")
                yield f"[OmniRoute Dry-Run Mode: Simulated response for {model}]\n"
            else:
                raise ConnectionError(f"OmniRoute daemon unreachable at {self.base_url}") from e
