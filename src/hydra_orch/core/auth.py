"""Local Bearer authentication, PBKDF2 verifier caching, scoped sub-tokens, and host/CORS guards."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import os
import posixpath
import re
import secrets
import threading
import time
from typing import Callable, Mapping, Optional, Sequence
from urllib.parse import unquote, urlsplit

ITERATIONS = 600_000
VERIFIER_CACHE_TTL_SECONDS = 300.0
VERIFIER_CACHE_MAX_ENTRIES = 512
PBKDF2_MAX_CONCURRENCY = 4
PBKDF2_ACQUIRE_TIMEOUT_SECONDS = 5.0

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DEV_CORS_PORTS = (3000, 5173, 5177, 5197)
_SCOPED_TOKEN_RE = re.compile(r"^hydra_tok_([0-9a-f]{32})_([^\s]+)$")

_VERIFIER_CACHE_LOCK = threading.Lock()
_VERIFIER_FAST_CACHE: "OrderedDict[tuple[int, bytes, bytes], tuple[bytes, float]]" = OrderedDict()
_PBKDF2_SEMAPHORE = threading.BoundedSemaphore(PBKDF2_MAX_CONCURRENCY)


def _monotonic() -> float:
    return time.monotonic()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_sha256_bytes(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _token_sha256_hex(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_cached_verifier_digest(cache_key: tuple[int, bytes, bytes], now: float) -> Optional[bytes]:
    with _VERIFIER_CACHE_LOCK:
        entry = _VERIFIER_FAST_CACHE.get(cache_key)
        if entry is None:
            return None
        cached_sha256, expires_at = entry
        if now >= expires_at:
            _VERIFIER_FAST_CACHE.pop(cache_key, None)
            return None
        _VERIFIER_FAST_CACHE.move_to_end(cache_key)
        return cached_sha256


def _put_cached_verifier_digest(
    cache_key: tuple[int, bytes, bytes],
    token_sha256: bytes,
    expires_at: float,
) -> None:
    with _VERIFIER_CACHE_LOCK:
        _VERIFIER_FAST_CACHE[cache_key] = (token_sha256, expires_at)
        _VERIFIER_FAST_CACHE.move_to_end(cache_key)
        while len(_VERIFIER_FAST_CACHE) > VERIFIER_CACHE_MAX_ENTRIES:
            _VERIFIER_FAST_CACHE.popitem(last=False)


def clear_verifier_cache() -> None:
    """Clear the internal SHA-256 fast-path cache for TokenVerifier instances."""
    with _VERIFIER_CACHE_LOCK:
        _VERIFIER_FAST_CACHE.clear()


@dataclass(frozen=True)
class AuthPrincipal:
    """Authenticated caller identity and effective authorization scopes."""

    principal_id: str
    scopes: tuple[str, ...]
    token_id: Optional[str] = None
    expires_at: Optional[str] = None
    is_master: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scopes, tuple):
            object.__setattr__(self, "scopes", tuple(self.scopes))

    def allows(self, *, method: str, path: str) -> bool:
        if self.is_master:
            return True
        return scope_allows(self.scopes, method=method, path=path)


def _parse_utc_timestamp(value: str) -> Optional[datetime]:
    try:
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def _is_expired_utc(expires_at: Optional[str], now_utc: datetime) -> bool:
    if expires_at is None:
        return False
    parsed = _parse_utc_timestamp(expires_at)
    if parsed is None:
        return True
    return parsed <= now_utc


class VerifiedTokenCache:
    """Thread-safe bounded LRU+TTL cache of verified tokens keyed solely by SHA-256 hex digest."""

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_entries: int = 512,
        *,
        clock: Callable[[], float] = _monotonic,
        utc_now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._clock = clock
        self._utc_now = utc_now
        self._lock = threading.RLock()
        self._entries: "OrderedDict[str, tuple[AuthPrincipal, float]]" = OrderedDict()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get(self, token: str) -> Optional[AuthPrincipal]:
        if not isinstance(token, str) or not token or len(token) > 4096 or any(c.isspace() for c in token):
            return None
        key = _token_sha256_hex(token)
        now_mono = self._clock()
        now_utc = self._utc_now()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            principal, expires_mono = entry
            if now_mono >= expires_mono or _is_expired_utc(principal.expires_at, now_utc):
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return principal

    def put(self, token: str, principal: AuthPrincipal) -> None:
        if not isinstance(token, str) or not token or len(token) > 4096 or any(c.isspace() for c in token):
            return
        key = _token_sha256_hex(token)
        now_mono = self._clock()
        now_utc = self._utc_now()
        with self._lock:
            if self._ttl_seconds == 0.0 or _is_expired_utc(principal.expires_at, now_utc):
                self._entries.pop(key, None)
                return
            self._entries[key] = (principal, now_mono + self._ttl_seconds)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate_token_id(self, token_id: str) -> None:
        if not isinstance(token_id, str) or not token_id:
            return
        with self._lock:
            stale_keys = [
                key
                for key, (principal, _) in self._entries.items()
                if principal.token_id == token_id
            ]
            for key in stale_keys:
                self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


@dataclass(frozen=True)
class TokenVerifier:
    salt: bytes
    digest: bytes
    iterations: int = ITERATIONS

    @classmethod
    def from_token(cls, token: str) -> "TokenVerifier":
        if not 32 <= len(token) <= 4096 or any(c.isspace() for c in token):
            raise ValueError("API token must contain 32–4096 non-whitespace characters")
        salt = secrets.token_bytes(16)
        return cls(salt, hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, ITERATIONS))

    def encode(self) -> str:
        return f"pbkdf2_sha256${self.iterations}${self.salt.hex()}${self.digest.hex()}"

    @classmethod
    def decode(cls, encoded: str) -> "TokenVerifier":
        try:
            algorithm, count, salt, digest = encoded.split("$")
            iterations = int(count)
            salt_bytes, digest_bytes = bytes.fromhex(salt), bytes.fromhex(digest)
            if (
                algorithm != "pbkdf2_sha256"
                or not ITERATIONS <= iterations <= 2_000_000
                or len(salt_bytes) != 16
                or len(digest_bytes) != 32
            ):
                raise ValueError
            return cls(salt_bytes, digest_bytes, iterations)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid PBKDF2 API token verifier") from None

    def verify(self, token: str) -> bool:
        if not isinstance(token, str) or not token or len(token) > 4096 or any(c.isspace() for c in token):
            return False
        token_bytes = token.encode("utf-8")
        candidate_sha256 = hashlib.sha256(token_bytes).digest()
        cache_key = (self.iterations, self.salt, self.digest)
        now = _monotonic()
        cached_sha256 = _get_cached_verifier_digest(cache_key, now)
        if cached_sha256 is not None and hmac.compare_digest(candidate_sha256, cached_sha256):
            return True

        if not _PBKDF2_SEMAPHORE.acquire(timeout=PBKDF2_ACQUIRE_TIMEOUT_SECONDS):
            return False
        try:
            rechecked_sha256 = _get_cached_verifier_digest(cache_key, _monotonic())
            if rechecked_sha256 is not None and hmac.compare_digest(candidate_sha256, rechecked_sha256):
                return True
            derived = hashlib.pbkdf2_hmac("sha256", token_bytes, self.salt, self.iterations)
            matched = hmac.compare_digest(derived, self.digest)
            if matched:
                _put_cached_verifier_digest(
                    cache_key,
                    candidate_sha256,
                    _monotonic() + VERIFIER_CACHE_TTL_SECONDS,
                )
            return matched
        finally:
            _PBKDF2_SEMAPHORE.release()


def mint_scoped_token(token_id: str) -> str:
    """Mint a prefixed scoped token embedding compact UUID hex for O(1) primary-key lookup."""
    if not isinstance(token_id, str) or not token_id.strip() or any(c.isspace() for c in token_id):
        raise ValueError("token_id must be a non-empty non-whitespace string")
    compact = token_id.replace("-", "")
    if len(compact) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in compact):
        compact = compact.lower()
    return f"hydra_tok_{compact}_{secrets.token_urlsafe(32)}"


def extract_scoped_token_id(token: str) -> Optional[str]:
    """Extract canonical 8-4-4-4-12 UUID from a `hydra_tok_<32hex>_<secret>` sub-token."""
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None
    match = _SCOPED_TOKEN_RE.match(token)
    if match is None:
        return None
    raw_hex = match.group(1)
    return f"{raw_hex[0:8]}-{raw_hex[8:12]}-{raw_hex[12:16]}-{raw_hex[16:20]}-{raw_hex[20:32]}"


def _normalize_request_path(path: str) -> str:
    raw = unquote((path or "/").split("?", 1)[0].split("#", 1)[0].strip()).replace("\\", "/")
    raw = "/" + raw.lstrip("/")
    collapsed = posixpath.normpath(raw)
    return "/" + collapsed.lstrip("/")


def _matches_route_prefix(norm_path: str, prefix: str) -> bool:
    clean_prefix = prefix.rstrip("/")
    return norm_path == clean_prefix or norm_path.startswith(clean_prefix + "/")


def scope_allows(scopes: Sequence[str], *, method: str, path: str) -> bool:
    """Evaluate whether a token's scope list authorizes the given HTTP method and route."""
    scope_set = {s.strip().lower() for s in scopes if isinstance(s, str) and s.strip()}
    if not scope_set:
        return False
    if "admin" in scope_set or "*" in scope_set:
        return True

    norm_method = (method or "").strip().upper()
    norm_path = _normalize_request_path(path)

    if norm_method in {"GET", "HEAD", "OPTIONS"}:
        return bool(scope_set & {"read", "write"})

    if norm_method in {"POST", "PUT", "PATCH", "DELETE"}:
        if _matches_route_prefix(norm_path, "/v1/control-plane/tokens"):
            return "tokens:write" in scope_set
        if _matches_route_prefix(norm_path, "/v1/control-plane/pty"):
            return ("write" in scope_set and "pty" in scope_set) or "pty:write" in scope_set
        if _matches_route_prefix(norm_path, "/v1/control-plane/extensions"):
            return False
        if _matches_route_prefix(norm_path, "/v1/launcher"):
            return False
        return "write" in scope_set

    return False


def _extract_host_candidate(hostname: str) -> Optional[str]:
    candidate = hostname.strip()
    if not candidate or any(c.isspace() for c in candidate) or "/" in candidate or "@" in candidate:
        return None
    if candidate.startswith("["):
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
                return None
            return parsed.hostname.lower()
        except ValueError:
            return None
    if ":" in candidate:
        try:
            ip_obj = ipaddress.ip_address(candidate)
            return ip_obj.compressed.lower()
        except ValueError:
            pass
        if candidate.count(":") == 1:
            try:
                parsed = urlsplit(f"http://{candidate}")
                port = parsed.port
                if (
                    parsed.hostname is None
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                    or port is None
                    or not 1 <= port <= 65535
                ):
                    return None
                return parsed.hostname.lower()
            except ValueError:
                return None
        return None
    return candidate.lower()


def _load_extra_allowed_hosts(env: Optional[Mapping[str, str]] = None) -> set[str]:
    source = os.environ if env is None else env
    raw = source.get("HYDRA_ALLOWED_HOSTS", "").strip()
    if not raw:
        return set()
    items: list[str] = []
    if raw.startswith("["):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        if not isinstance(decoded, list):
            return set()
        items = [entry for entry in decoded if isinstance(entry, str)]
    else:
        items = raw.split(",")

    allowed: set[str] = set()
    for item in items:
        stripped = item.strip()
        if not stripped or stripped == "*":
            continue
        parsed_host = _extract_host_candidate(stripped)
        if parsed_host:
            allowed.add(parsed_host)
    return allowed


def is_trusted_host(hostname: Optional[str], *, client_host: Optional[str] = None) -> bool:
    """Protect against DNS rebinding by accepting loopback (plus explicit HYDRA_ALLOWED_HOSTS)."""
    if not isinstance(hostname, str) or not hostname:
        return False
    normalized = _extract_host_candidate(hostname)
    if normalized is None:
        return False
    if normalized in _LOOPBACK_HOSTS:
        return True
    if normalized == "testserver":
        return client_host == "testclient" or normalized in _load_extra_allowed_hosts()
    return normalized in _load_extra_allowed_hosts()


def default_cors_origins(port: int = 8000) -> list[str]:
    """Return strict same-port loopback origins by default; opt-in dev Vite ports via HYDRA_DEV_CORS=1."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Port must be an integer between 1 and 65535")
    origins = [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    ]
    if os.environ.get("HYDRA_DEV_CORS") == "1":
        for dev_port in _DEV_CORS_PORTS:
            origins.append(f"http://127.0.0.1:{dev_port}")
            origins.append(f"http://localhost:{dev_port}")
    return list(dict.fromkeys(origins))


def load_token_verifier(env: Optional[Mapping[str, str]] = None) -> Optional[TokenVerifier]:
    """Read external configuration; callers retain only the derived verifier."""
    source = os.environ if env is None else env
    hashed, raw = source.get("HYDRA_API_TOKEN_HASH"), source.get("HYDRA_API_TOKEN")
    if hashed and raw:
        raise ValueError("Configure only HYDRA_API_TOKEN_HASH or HYDRA_API_TOKEN")
    if hashed:
        return TokenVerifier.decode(hashed)
    return TokenVerifier.from_token(raw) if raw else None


def validate_cors_origins(origins: list[str]) -> list[str]:
    """Only explicit loopback HTTP(S) origins can receive browser credentials."""
    if not isinstance(origins, list):
        raise ValueError("CORS allowlist must be a list")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            port = parsed.port
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or (port is not None and not 1 <= port <= 65535)
                or origin != f"{parsed.scheme}://{parsed.netloc}"
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("CORS requires explicit loopback HTTP(S) origins") from None
    return list(dict.fromkeys(origins))


def load_cors_origins(default: list[str]) -> list[str]:
    """Optional JSON environment allowlist, validated before middleware creation."""
    encoded = os.environ.get("HYDRA_CORS_ALLOW_ORIGINS")
    try:
        origins = json.loads(encoded) if encoded is not None else default
    except json.JSONDecodeError:
        raise ValueError("HYDRA_CORS_ALLOW_ORIGINS must be a JSON list") from None
    return validate_cors_origins(origins)
