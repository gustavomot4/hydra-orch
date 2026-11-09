"""Local Bearer authentication using salted PBKDF2 verifiers only."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import secrets
from typing import Mapping, Optional
from urllib.parse import urlsplit

ITERATIONS = 600_000


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
        return cls(salt, hashlib.pbkdf2_hmac("sha256", token.encode(), salt, ITERATIONS))

    def encode(self) -> str:
        return f"pbkdf2_sha256${self.iterations}${self.salt.hex()}${self.digest.hex()}"

    @classmethod
    def decode(cls, encoded: str) -> "TokenVerifier":
        try:
            algorithm, count, salt, digest = encoded.split("$")
            iterations = int(count)
            salt_bytes, digest_bytes = bytes.fromhex(salt), bytes.fromhex(digest)
            if (algorithm != "pbkdf2_sha256" or not ITERATIONS <= iterations <= 2_000_000
                    or len(salt_bytes) != 16 or len(digest_bytes) != 32):
                raise ValueError
            return cls(salt_bytes, digest_bytes, iterations)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid PBKDF2 API token verifier") from None

    def verify(self, token: str) -> bool:
        if not token or len(token) > 4096 or any(c.isspace() for c in token):
            return False
        digest = hashlib.pbkdf2_hmac("sha256", token.encode(), self.salt, self.iterations)
        return hmac.compare_digest(digest, self.digest)


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
            if (parsed.scheme not in {"http", "https"}
                    or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path or parsed.query or parsed.fragment
                    or (port is not None and not 1 <= port <= 65535)
                    or origin != f"{parsed.scheme}://{parsed.netloc}"):
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
