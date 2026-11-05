"""UI / Chrome DevTools Protocol (CDP) Adapter for browser/PWA subscriptions (Claude Pro, ChatGPT, Gemini)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx
import websockets

from hydra_orch.adapters.base import BaseAdapter, LimitHitException
from hydra_orch.models import ChatMessage

logger = logging.getLogger(__name__)


class UiCdpAdapter(BaseAdapter):
    """Adapter for interacting with browser PWAs via Chrome DevTools Protocol (CDP).
    
    Reads and drives DOM directly over WebSocket without stealing OS window focus.
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.cdp_port: int = config.get("cdp_port", 9222)
        self.target_url: str = config.get("target_url", "")
        self.session_timeout: int = config.get("session_timeout_seconds", 300)
        self.rate_limit_reset_hours: float = config.get("rate_limit_reset_hours", 5.0)

    async def _get_websocket_url(self) -> Optional[str]:
        """Fetch active target tab websocket debugger URL from CDP endpoint."""
        url = f"http://127.0.0.1:{self.cdp_port}/json"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    targets = resp.json()
                    # Filter page targets matching target_url
                    for target in targets:
                        if target.get("type") == "page":
                            page_url = target.get("url", "")
                            if not self.target_url or self.target_url in page_url:
                                return target.get("webSocketDebuggerUrl")
                    # If target url not matched specifically, return first valid page
                    for target in targets:
                        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                            return target.get("webSocketDebuggerUrl")
        except Exception as e:
            self.last_error = f"CDP connection failed on port {self.cdp_port}: {e}"
        return None

    async def is_available(self) -> bool:
        """Check if CDP port is open and browser tab is discoverable."""
        ws_url = await self._get_websocket_url()
        self.is_healthy = ws_url is not None
        return self.is_healthy

    async def _send_cdp_command(
        self, ws: websockets.WebSocketClientProtocol, cmd_id: int, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = {"id": cmd_id, "method": method, "params": params}
        await ws.send(json.dumps(payload))
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == cmd_id:
                return msg

    async def _evaluate_script(
        self, ws: websockets.WebSocketClientProtocol, cmd_id: int, script: str
    ) -> Any:
        resp = await self._send_cdp_command(
            ws,
            cmd_id,
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        result = resp.get("result", {}).get("result", {})
        return result.get("value")

    def _get_provider_dom_script(self, prompt: str) -> str:
        """Generates JS to inject prompt into UI and initiate submission."""
        escaped_prompt = json.dumps(prompt)
        
        if "claude" in self.name.lower():
            return f"""
            (() => {{
                // Claude Pro web DOM injection
                const editor = document.querySelector('div[contenteditable="true"]') || document.querySelector('textarea');
                if (!editor) return {{ success: false, error: 'Input field not found' }};
                
                editor.focus();
                if (editor.tagName === 'TEXTAREA') {{
                    editor.value = {escaped_prompt};
                    editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }} else {{
                    editor.innerText = {escaped_prompt};
                    editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                
                // Find and click send button
                setTimeout(() => {{
                    const sendBtn = document.querySelector('button[aria-label*="Send"], button[aria-label*="Enviar"], button.send-button');
                    if (sendBtn && !sendBtn.disabled) {{
                        sendBtn.click();
                    }} else {{
                        // Fallback enter keydown
                        editor.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                    }}
                }}, 150);

                return {{ success: true }};
            }})();
            """
        elif "chatgpt" in self.name.lower():
            return f"""
            (() => {{
                const editor = document.querySelector('#prompt-textarea');
                if (!editor) return {{ success: false, error: 'ChatGPT textarea not found' }};
                editor.value = {escaped_prompt};
                editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                
                setTimeout(() => {{
                    const btn = document.querySelector('button[data-testid="send-button"]') || document.querySelector('button[aria-label*="Send"]');
                    if (btn) btn.click();
                }}, 150);
                return {{ success: true }};
            }})();
            """
        else:
            # Generic PWA / Gemini injection
            return f"""
            (() => {{
                const editor = document.querySelector('rich-textarea, textarea, div[contenteditable="true"]');
                if (!editor) return {{ success: false, error: 'Generic input not found' }};
                editor.innerText = {escaped_prompt};
                editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                return {{ success: true }};
            }})();
            """

    def _get_response_scraper_script(self) -> str:
        """Generates JS to poll the latest assistant response bubble and check limit notices."""
        return """
        (() => {
            // Check for rate limit or quota banners
            const bodyText = document.body.innerText || "";
            const isLimitHit = (
                bodyText.includes("You are out of messages") ||
                bodyText.includes("resets at") ||
                bodyText.includes("limit reached") ||
                bodyText.includes("You've reached your usage cap") ||
                bodyText.includes("Please wait until")
            );

            // Scrape last assistant response text
            let lastMessageText = "";
            let isGenerating = false;

            // Claude Pro selector
            const claudeMessages = document.querySelectorAll('div[data-is-streaming="true"], div.font-claude-message, div[data-testid="message"]');
            if (claudeMessages.length > 0) {
                const last = claudeMessages[claudeMessages.length - 1];
                lastMessageText = last.innerText || "";
                isGenerating = document.querySelector('button[aria-label*="Stop"]') !== null;
            }

            // ChatGPT selector
            if (!lastMessageText) {
                const gptMessages = document.querySelectorAll('div[data-message-author-role="assistant"]');
                if (gptMessages.length > 0) {
                    const last = gptMessages[gptMessages.length - 1];
                    lastMessageText = last.innerText || "";
                    isGenerating = document.querySelector('button[data-testid="stop-button"]') !== null;
                }
            }

            return {
                text: lastMessageText,
                is_limit_hit: isLimitHit,
                is_generating: isGenerating
            };
        })();
        """

    async def generate_stream(
        self,
        messages: List[ChatMessage],
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        ws_url = await self._get_websocket_url()
        if not ws_url:
            raise ConnectionError(f"Cannot connect to CDP browser on port {self.cdp_port}")

        # Combine messages or pick the latest user query
        full_prompt = "\n".join([f"{m.role.upper()}: {m.content}" for m in messages])

        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
            cmd_id = 1
            # Enable Runtime domain
            await self._send_cdp_command(ws, cmd_id, "Runtime.enable", {})
            cmd_id += 1

            # Inject prompt into DOM
            inject_js = self._get_provider_dom_script(full_prompt)
            inj_result = await self._evaluate_script(ws, cmd_id, inject_js)
            cmd_id += 1

            if isinstance(inj_result, dict) and not inj_result.get("success", False):
                logger.warning(f"Injection issue on {self.name}: {inj_result.get('error')}")

            # Stream response diffs by polling DOM state
            last_yielded_len = 0
            start_time = time.time()
            stagnant_cycles = 0

            while time.time() - start_time < self.session_timeout:
                await asyncio.sleep(0.4)
                status = await self._evaluate_script(ws, cmd_id, self._get_response_scraper_script())
                cmd_id += 1

                if not isinstance(status, dict):
                    continue

                if status.get("is_limit_hit"):
                    # Quota hit: Claude 5h limit or GPT cap
                    reset_seconds = int(self.rate_limit_reset_hours * 3600)
                    self.limit_reset_timestamp = time.time() + reset_seconds
                    raise LimitHitException(
                        provider=self.name,
                        message="Subscription quota or token cap reached in UI",
                        reset_in_seconds=reset_seconds,
                    )

                text = status.get("text", "")
                is_generating = status.get("is_generating", False)

                if len(text) > last_yielded_len:
                    chunk = text[last_yielded_len:]
                    last_yielded_len = len(text)
                    stagnant_cycles = 0
                    yield chunk
                else:
                    stagnant_cycles += 1

                # If generation stopped and no new text arrived for 3 cycles (~1.2s), finish
                if not is_generating and stagnant_cycles >= 3 and last_yielded_len > 0:
                    break
