"""Local launcher session bootstrap, single-use ticket exchange, and ephemeral desktop sessions."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import hmac
import os
from pathlib import PurePosixPath
import secrets
import sys
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

_LOOPBACK_CLIENT_IPS = frozenset({"127.0.0.1", "::1"})
_LOOPBACK_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})

UI_ROUTES = frozenset(
    {
        "chat",
        "agentes",
        "terminal",
        "workspace",
        "recursos",
        "automacoes",
        "dispositivos",
        "computador",
        "consumo",
        "configuracoes",
        "busca",
    }
)

SAFE_ROOT_STATIC_FILES = frozenset(
    {
        "/favicon.ico",
        "/favicon.svg",
        "/robots.txt",
        "/manifest.webmanifest",
    }
)

SAFE_ASSET_EXTENSIONS = frozenset(
    {
        ".js",
        ".mjs",
        ".cjs",
        ".css",
        ".woff2",
        ".woff",
        ".ttf",
        ".otf",
        ".eot",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".ico",
        ".json",
        ".wasm",
        ".map",
        ".txt",
    }
)


def _sha256_bytes(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _is_loopback_host_header(host_header: str) -> bool:
    if not isinstance(host_header, str):
        return False
    candidate = host_header.strip()
    if not candidate or any(c.isspace() for c in candidate) or "/" in candidate or "@" in candidate:
        return False
    if candidate == "::1":
        return True
    try:
        parsed = urlsplit(f"http://{candidate}")
        port = parsed.port
        if (
            parsed.hostname is None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            return False
        return parsed.hostname.lower() in _LOOPBACK_HOSTNAMES
    except ValueError:
        return False


class DesktopSessionManager:
    """In-memory manager for single-use bootstrap tickets and ephemeral desktop session tokens."""

    def __init__(
        self,
        *,
        max_tickets: int = 64,
        max_sessions: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_tickets < 1 or max_sessions < 1:
            raise ValueError("max_tickets and max_sessions must be >= 1")
        self._max_tickets = int(max_tickets)
        self._max_sessions = int(max_sessions)
        self._clock = clock
        self._lock = threading.RLock()
        self._tickets: "OrderedDict[bytes, float]" = OrderedDict()
        self._sessions: "OrderedDict[bytes, float]" = OrderedDict()

    def _prune_expired_locked(self, now: float) -> None:
        expired_tickets = [digest for digest, exp in self._tickets.items() if now >= exp]
        for digest in expired_tickets:
            self._tickets.pop(digest, None)
        expired_sessions = [digest for digest, exp in self._sessions.items() if now >= exp]
        for digest in expired_sessions:
            self._sessions.pop(digest, None)

    def issue_bootstrap_ticket(self, ttl_seconds: float = 60.0) -> str:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        nonce = secrets.token_urlsafe(32)
        nonce_digest = _sha256_bytes(nonce)
        now = self._clock()
        with self._lock:
            self._prune_expired_locked(now)
            self._tickets[nonce_digest] = now + float(ttl_seconds)
            self._tickets.move_to_end(nonce_digest)
            while len(self._tickets) > self._max_tickets:
                self._tickets.popitem(last=False)
        return nonce

    def exchange_bootstrap_ticket(self, nonce: str, ttl_seconds: float = 43200.0) -> Optional[str]:
        if (
            not isinstance(nonce, str)
            or not nonce
            or len(nonce) > 512
            or any(c.isspace() for c in nonce)
            or ttl_seconds <= 0
        ):
            return None
        candidate_digest = _sha256_bytes(nonce)
        now = self._clock()
        with self._lock:
            matched_digest: Optional[bytes] = None
            for stored_digest in list(self._tickets.keys()):
                if hmac.compare_digest(candidate_digest, stored_digest):
                    matched_digest = stored_digest
            expires_at = self._tickets.pop(matched_digest, 0.0) if matched_digest is not None else 0.0
            self._prune_expired_locked(now)
            if matched_digest is None or now >= expires_at:
                return None

            sess_tok = f"hydra_desktop_{secrets.token_urlsafe(32)}"
            sess_digest = _sha256_bytes(sess_tok)
            self._sessions[sess_digest] = now + float(ttl_seconds)
            self._sessions.move_to_end(sess_digest)
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
            return sess_tok

    def verify_session_token(self, token: str) -> bool:
        if (
            not isinstance(token, str)
            or not token.startswith("hydra_desktop_")
            or len(token) > 512
            or any(c.isspace() for c in token)
        ):
            return False
        candidate_digest = _sha256_bytes(token)
        now = self._clock()
        with self._lock:
            self._prune_expired_locked(now)
            matched = False
            for stored_digest, expires_at in self._sessions.items():
                is_hit = hmac.compare_digest(candidate_digest, stored_digest)
                if is_hit and now < expires_at:
                    matched = True
            return matched

    def revoke_session_token(self, token: str) -> bool:
        if (
            not isinstance(token, str)
            or not token.startswith("hydra_desktop_")
            or len(token) > 512
            or any(c.isspace() for c in token)
        ):
            return False
        candidate_digest = _sha256_bytes(token)
        with self._lock:
            matched_digest: Optional[bytes] = None
            for stored_digest in list(self._sessions.keys()):
                if hmac.compare_digest(candidate_digest, stored_digest):
                    matched_digest = stored_digest
            if matched_digest is None:
                return False
            self._sessions.pop(matched_digest, None)
            return True

    def clear(self) -> None:
        with self._lock:
            self._tickets.clear()
            self._sessions.clear()

    def revoke_all(self) -> None:
        self.clear()


desktop_sessions = DesktopSessionManager()


def get_desktop_session_manager(app_state: Any = None) -> DesktopSessionManager:
    if app_state is not None:
        existing = getattr(app_state, "desktop_sessions", None)
        if isinstance(existing, DesktopSessionManager):
            return existing
        try:
            setattr(app_state, "desktop_sessions", desktop_sessions)
        except Exception:
            pass
    return desktop_sessions


def reset_desktop_session_manager() -> DesktopSessionManager:
    global desktop_sessions
    desktop_sessions.clear()
    desktop_sessions = DesktopSessionManager()
    return desktop_sessions


def enabled(app_state: Any = None) -> bool:
    if os.environ.get("HYDRA_LOCAL_DESKTOP") != "1":
        return False
    if app_state is not None and getattr(app_state, "token_verifier", None) is not None:
        return True
    if os.environ.get("HYDRA_API_TOKEN") or os.environ.get("HYDRA_API_TOKEN_HASH"):
        return True
    if app_state is None:
        server_mod = sys.modules.get("hydra_orch.server")
        server_app = getattr(server_mod, "app", None) if server_mod is not None else None
        server_state = getattr(server_app, "state", None) if server_app is not None else None
        if (
            server_state is not None
            and getattr(server_state, "local_desktop_enabled", False)
            and getattr(server_state, "token_verifier", None) is not None
        ):
            return True
    return False


def loopback_request(request: Any) -> bool:
    app = getattr(request, "app", None)
    app_state = getattr(app, "state", None) if app is not None else None
    if not enabled(app_state):
        return False
    if request.client is None or request.client.host not in _LOOPBACK_CLIENT_IPS:
        return False
    hostname = (request.url.hostname or "").lower()
    if hostname not in _LOOPBACK_HOSTNAMES:
        return False
    headers = getattr(request, "headers", None)
    if headers is not None:
        host_header = headers.get("host")
        if host_header is not None and not _is_loopback_host_header(host_header):
            return False
    return True


def allow_bootstrap(request: Any) -> bool:
    if not loopback_request(request) or request.method != "POST":
        return False
    host = request.headers.get("host", "")
    if not _is_loopback_host_header(host):
        return False
    origin = request.headers.get("origin", "")
    expected = f"{request.url.scheme}://{host}"
    return (
        hmac.compare_digest(origin, expected)
        and request.headers.get("sec-fetch-site") == "same-origin"
        and request.headers.get("x-hydra-desktop") == "1"
    )


def public_frontend(request: Any) -> bool:
    if not loopback_request(request) or request.method not in {"GET", "HEAD"}:
        return False
    path = request.url.path
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or "//" in path
    ):
        return False
    segments = [seg for seg in path.split("/") if seg]
    if any(seg in {".", ".."} or seg.startswith(".") for seg in segments):
        return False
    if path == "/" or path in SAFE_ROOT_STATIC_FILES:
        return True
    if path.startswith("/assets/") and len(segments) >= 2:
        suffix = PurePosixPath(segments[-1]).suffix.lower()
        return suffix in SAFE_ASSET_EXTENSIONS
    if segments and segments[0] in UI_ROUTES:
        return True
    return False
