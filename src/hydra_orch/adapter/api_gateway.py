"""API Gateway Adapter for direct OpenAI-compatible APIs (OpenRouter, DeepSeek, etc.)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional
import httpx

from hydra_orch.adapter.base import BaseAdapter, LimitHitException
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


def _parse_retry_after(headers: Optional[Mapping[str, str]]) -> Optional[int]:
    """Parse integer seconds from an HTTP Retry-After header when present."""
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        raw = headers.get("retry-after")
    if raw is None:
        return None
    cleaned = str(raw).strip()
    if not cleaned:
        return None
    try:
        parsed = int(cleaned)
    except ValueError:
        try:
            parsed = int(float(cleaned))
        except (ValueError, OverflowError):
            return None
    return parsed if parsed >= 0 else None


def _build_limit_hit_exception(
    provider: str,
    message: str,
    headers: Optional[Mapping[str, str]] = None,
    default_reset_seconds: int = 60,
) -> LimitHitException:
    retry_after = _parse_retry_after(headers)
    reset_secs = retry_after if retry_after is not None else default_reset_seconds
    exc = LimitHitException(
        provider=provider,
        message=message,
        reset_in_seconds=reset_secs,
    )
    exc.retry_after = retry_after  # type: ignore[attr-defined]
    return exc


class ApiGatewayAdapter(BaseAdapter):
    """Adapter for remote OpenAI-compatible API providers."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.base_url: str = config.get("base_url", "").rstrip("/")
        self.api_key_env: str = config.get("api_key_env", "")
        self.default_model: str = config.get("default_model", "")
        self.timeout: float = config.get("timeout_seconds", 120.0)

    @property
    def api_key(self) -> Optional[str]:
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return self.config.get("api_key")

    async def is_available(self) -> bool:
        """Check if API key is present and endpoint responds."""
        if not self.api_key:
            self.last_error = f"Missing API key for {self.name} (checked env {self.api_key_env})"
            self.is_healthy = False
            return False

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=headers)
                self.is_healthy = resp.status_code in (200, 401, 403)
                if resp.status_code in (401, 403):
                    self.last_error = f"Authentication error on {self.name}: {resp.status_code}"
                return resp.status_code == 200
        except Exception as e:
            self.last_error = f"API connection error: {e}"
            self.is_healthy = False
            return False

    async def generate_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        opts = options or {}
        model = opts.get("model") or self.default_model
        key = self.api_key

        if not key:
            raise ValueError(f"API key not set for {self.name} (expected env {self.api_key_env})")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        
        # Add OpenRouter specific headers if applicable
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://github.com/hydra-orch"
            headers["X-Title"] = "hydra-orch"

        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "stream": True,
            "temperature": opts.get("temperature", 0.7),
        }
        if opts.get("max_tokens"):
            payload["max_tokens"] = opts["max_tokens"]

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code == 429:
                        raise _build_limit_hit_exception(
                            provider=self.name,
                            message=f"Rate limit / credit exhausted on {self.name}",
                            headers=response.headers,
                            default_reset_seconds=60,
                        )

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
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise _build_limit_hit_exception(
                    provider=self.name,
                    message="API quota or rate limit exceeded",
                    headers=e.response.headers,
                    default_reset_seconds=60,
                ) from e
            self.last_error = str(e)
            raise
        except Exception as e:
            self.last_error = str(e)
            raise
