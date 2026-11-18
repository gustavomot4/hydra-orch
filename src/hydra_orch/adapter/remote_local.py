"""Remote / Local Model Adapter for Ollama / vLLM / Local GPUs."""

from __future__ import annotations

import json
import logging
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


class RemoteLocalAdapter(BaseAdapter):
    """Adapter for Ollama, vLLM, or remote GPU hosts exposed locally or via SSH tunnel."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        # If base_url not specified, compute from local_bind_port
        bind_port = config.get("local_bind_port")
        default_base = f"http://127.0.0.1:{bind_port}" if bind_port else "http://127.0.0.1:11434"
        self.base_url: str = config.get("base_url", default_base).rstrip("/")
        self.default_model: str = config.get("default_model", "qwen2.5-coder:32b")
        self.timeout: float = config.get("timeout_seconds", 180.0)

    async def is_available(self) -> bool:
        """Check if local or forwarded endpoint is responding."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                # Try Ollama /api/tags or OpenAI /v1/models
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    self.is_healthy = True
                    return True
                
                resp2 = await client.get(f"{self.base_url}/v1/models")
                self.is_healthy = resp2.status_code == 200
                return self.is_healthy
        except Exception as e:
            self.last_error = f"Local/SSH model connection failed: {e}"
            self.is_healthy = False
            return False

    async def generate_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        opts = options or {}
        model = opts.get("model") or self.default_model

        # Attempt OpenAI-compatible endpoint first, fallback to Ollama native /api/chat
        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "stream": True,
            "options": {
                "temperature": opts.get("temperature", 0.7),
            },
        }

        openai_url = f"{self.base_url}/v1/chat/completions"
        ollama_url = f"{self.base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # First try standard /v1/chat/completions
                try:
                    async with client.stream("POST", openai_url, json=payload) as response:
                        if response.status_code == 429:
                            raise _build_limit_hit_exception(
                                provider=self.name,
                                message=f"Rate limit / capacity exhausted on {self.name}",
                                headers=response.headers,
                                default_reset_seconds=60,
                            )
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    raw = line[len("data: ") :].strip()
                                    if raw == "[DONE]":
                                        return
                                    try:
                                        data = json.loads(raw)
                                        content = data["choices"][0]["delta"].get("content", "")
                                        if content:
                                            yield content
                                    except Exception:
                                        continue
                            return
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        raise _build_limit_hit_exception(
                            provider=self.name,
                            message=f"Rate limit / capacity exhausted on {self.name}",
                            headers=e.response.headers,
                            default_reset_seconds=60,
                        ) from e
                except httpx.HTTPError:
                    pass

                # Fallback to Ollama native /api/chat
                ollama_payload = {
                    "model": model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "stream": True,
                }
                async with client.stream("POST", ollama_url, json=ollama_payload) as response:
                    if response.status_code == 429:
                        raise _build_limit_hit_exception(
                            provider=self.name,
                            message=f"Rate limit / capacity exhausted on {self.name}",
                            headers=response.headers,
                            default_reset_seconds=60,
                        )
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            msg = data.get("message", {})
                            content = msg.get("content", "")
                            if content:
                                yield content
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                exc = _build_limit_hit_exception(
                    provider=self.name,
                    message=f"Rate limit / capacity exhausted on {self.name}",
                    headers=e.response.headers,
                    default_reset_seconds=60,
                )
                self.last_error = str(exc)
                raise exc from e
            self.last_error = str(e)
            raise
        except Exception as e:
            self.last_error = str(e)
            raise
