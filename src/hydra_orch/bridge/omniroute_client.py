"""OmniRoute Gateway client for OAuth subscriptions and 5h quota monitoring."""

from __future__ import annotations

import json
import logging
import copy
import math
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from hydra_orch.config import normalize_gemini_argon_target
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
        self._last_quota: Optional[Dict[str, Any]] = None

    @staticmethod
    def normalize_model(model: str) -> str:
        """Normalize model IDs before sending to OmniRoute (e.g. Gemini 4 Argon tiers)."""
        normalized = normalize_gemini_argon_target(model.strip())
        if normalized == "antigravity/gemini-4-argon-high":
            return "agy/gemini-4-argon-high"
        return normalized

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
                    if isinstance(data, dict):
                        normalized = copy.deepcopy(unknown)
                        for name, entry in data.items():
                            if not isinstance(entry, dict):
                                continue
                            percent = entry.get("remaining_percent")
                            status = entry.get("status", data.get("status", "observed"))
                            if (isinstance(percent, bool) or not isinstance(percent, (int, float))
                                    or not math.isfinite(percent) or not 0 <= percent <= 100
                                    or status not in {"observed", "stale"}):
                                continue
                            reset = entry.get("resets_in_seconds")
                            if isinstance(reset, bool) or not isinstance(reset, (int, float)) or not math.isfinite(reset) or reset < 0:
                                reset = None
                            normalized[name] = {"status": status, "remaining_percent": percent,
                                "resets_in_seconds": reset, "observed_at": datetime.now(timezone.utc).isoformat(),
                                "source": "omniroute:quota_api"}
                        statuses = [v["status"] for v in normalized.values() if isinstance(v, dict)]
                        normalized["status"] = "observed" if "observed" in statuses else "stale" if "stale" in statuses else "unknown"
                        if normalized["status"] != "unknown":
                            self._last_quota = copy.deepcopy(normalized)
                            return normalized
        except Exception as e:
            logger.debug(f"Could not reach OmniRoute quota API: {e}")
        if self._last_quota is not None:
            stale = copy.deepcopy(self._last_quota)
            stale["status"] = "stale"
            for entry in stale.values():
                if isinstance(entry, dict) and entry.get("remaining_percent") is not None:
                    entry.update(status="stale", resets_in_seconds=None)
            return stale
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
        if not self.enabled:
            raise ConnectionError("OmniRoute is disabled")
        resolved_model = self.normalize_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
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
