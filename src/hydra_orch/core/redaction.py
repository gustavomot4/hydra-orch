"""Conservative, deterministic redaction at evidence and logging boundaries."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import re
from typing import Any, Iterable, Iterator

REDACTED = "[REDACTED]"
_ACTIVE_LITERALS: ContextVar[tuple[str, ...]] = ContextVar("hydra_active_literals", default=())
_REGISTERED_LITERALS: tuple[str, ...] = ()


def register_secret(*literals: str) -> None:
    """Register process-wide secret literals so they are always scrubbed across tasks and threads."""
    global _REGISTERED_LITERALS
    merged = set(_REGISTERED_LITERALS)
    for item in literals:
        if isinstance(item, str) and len(item) >= 8 and item != REDACTED:
            merged.add(item)
    _REGISTERED_LITERALS = tuple(sorted(merged, key=len, reverse=True))

_BENIGN_TOKEN_PREFIX = (
    r"(?:redact|has|is|cancel|cancellation|page|next[_-]?page|sync|continuation|"
    r"max|min|stop|bos|eos|pad|unk)"
)

_SECRET_KEY = re.compile(
    r"^_*("
    r"(?:proxy[_-]?)?authorization"
    r"|(?:[a-z0-9]+[_-])*(?:password|passwd|passphrase|pwd|secret|credentials?)"
    r"|(?:db|user|client|jwt|app|oauth|webhook|cookie|hmac|admin|root|master|redis|smtp|postgres|mysql|mongo|api|auth)[a-z0-9]*(?:password|passwd|passphrase|secret|credentials?)"
    r"|(?:[a-z0-9]+[_-])*(?:api|access|private|secret|client|session|signing|auth|master|encryption|webhook|service|ssh)[_-]?key"
    r"|[a-z0-9]*(?:api|access|private|secret|client|session|signing|auth|master|encryption|webhook|service|ssh)key"
    r"|(?!(?:[a-z0-9]+[_-])*" + _BENIGN_TOKEN_PREFIX + r"[_-]?token$)(?:[a-z0-9]+[_-])*token"
    r"|(?:access|refresh|id|api|auth|oauth|bearer|session|csrf|jwt|bot|client|user|service|gateway|hydra)token"
    r")$",
    re.I,
)

_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?>[A-Z0-9]+ ){0,8}PRIVATE KEY-----.*?"
    r"(?:-----END (?>[A-Z0-9]+ ){0,8}PRIVATE KEY-----|$)",
    re.S,
)

_PROVIDER_TOKEN = re.compile(
    r"\b(?:"
    r"hydra_tok_[A-Za-z0-9_-]{16,}"
    r"|hydra_desktop_[A-Za-z0-9_-]{16,}"
    r"|AIza[0-9A-Za-z_-]{35,}"
    r"|(?:AKIA|ASIA)[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|(?:sk-|gh[pousr]_|github_pat_|glpat-|xox[baprs]-)[A-Za-z0-9_-]{8,}"
    r")"
)

_BEARER = re.compile(r"\bBearer\s+(?>[^\s\"'<>;,]+)", re.I)

_ASSIGNMENT = re.compile(
    r"(?P<label>(?P<kw>password|passwd|passphrase|secret|credentials?|key|token)\b[\"']?\s*[:=]\s*)"
    r"(?:\[REDACTED\]|\"[^\"]*\"|'[^']*'|[^\s,;&\}\]]+)",
    re.I,
)
_KEY_PREFIX_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:api|access|private|secret|client|session|signing|auth|master|encryption|webhook|service)[_-]?$",
    re.I,
)
_BENIGN_TOKEN_BEFORE_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])" + _BENIGN_TOKEN_PREFIX + r"[_-]?$",
    re.I,
)
_CAMEL_TOKEN_BEFORE_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:access|refresh|id|api|auth|oauth|bearer|session|client|hydra|gateway)$",
    re.I,
)
_CAMEL_SECRET_BEFORE_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:client|jwt|oauth|app|webhook)$",
    re.I,
)
_CAMEL_PASSWORD_BEFORE_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:db|user|admin|root)$",
    re.I,
)

_URL_CREDENTIAL = re.compile(
    r"((?<![a-z0-9+.-])(?>[a-z][a-z0-9+.-]*)://)(?>[^/\s@]+)@",
    re.I,
)


def _is_valid_assignment_match(text: str, match: re.Match[str]) -> bool:
    kw = match["kw"].lower()
    before = text[max(0, match.start() - 36):match.start()]
    if kw == "key":
        return bool(_KEY_PREFIX_RE.search(before))
    if kw == "token":
        if _BENIGN_TOKEN_BEFORE_RE.search(before):
            return False
        if before and before[-1].isalnum() and not _CAMEL_TOKEN_BEFORE_RE.search(before):
            return False
        return True
    if kw == "secret":
        if before and before[-1].isalnum() and not _CAMEL_SECRET_BEFORE_RE.search(before):
            return False
        return True
    if kw in ("password", "passwd", "passphrase"):
        if before and before[-1].isalnum() and not _CAMEL_PASSWORD_BEFORE_RE.search(before):
            return False
        return True
    if before and before[-1].isalnum():
        return False
    return True


def _sub_assignments(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        if not _is_valid_assignment_match(text, match):
            return match[0]
        return match["label"] + REDACTED

    return _ASSIGNMENT.sub(_repl, text)


def redact_text(text: str) -> str:
    if not text:
        return text
    if "PRIVATE KEY-----" in text:
        text = _PRIVATE_KEY.sub(REDACTED, text)
    text = _PROVIDER_TOKEN.sub(REDACTED, text)
    if "://" in text and "@" in text:
        text = _URL_CREDENTIAL.sub(lambda m: m[1] + REDACTED + "@", text)
    lower = text.lower()
    if "bearer" in lower:
        text = _BEARER.sub("Bearer " + REDACTED, text)
    if ("=" in text or ":" in text) and any(
        w in lower for w in ("token", "key", "secret", "pass", "cred")
    ):
        text = _sub_assignments(text)
    for literal in (*_REGISTERED_LITERALS, *_ACTIVE_LITERALS.get()):
        if literal in text:
            text = text.replace(literal, REDACTED)
    return text


def _collect_match_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    if "PRIVATE KEY-----" in text:
        spans.extend(m.span() for m in _PRIVATE_KEY.finditer(text))
    spans.extend(m.span() for m in _PROVIDER_TOKEN.finditer(text))
    lower = text.lower()
    if "bearer" in lower:
        spans.extend(m.span() for m in _BEARER.finditer(text))
    if ("=" in text or ":" in text) and any(
        w in lower for w in ("token", "key", "secret", "pass", "cred")
    ):
        for m in _ASSIGNMENT.finditer(text):
            if _is_valid_assignment_match(text, m):
                start = m.start()
                while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_-"):
                    start -= 1
                spans.append((start, m.end()))
    if "://" in text and "@" in text:
        spans.extend(m.span() for m in _URL_CREDENTIAL.finditer(text))
    for literal in (*_REGISTERED_LITERALS, *_ACTIVE_LITERALS.get()):
        start = 0
        while True:
            idx = text.find(literal, start)
            if idx == -1:
                break
            spans.append((idx, idx + len(literal)))
            start = idx + len(literal)
    return spans


class StreamingRedactor:
    """Chunk-safe streaming redactor that prevents splitting secrets across chunk boundaries."""

    def __init__(self, holdback: int = 96) -> None:
        if isinstance(holdback, bool) or not isinstance(holdback, int) or holdback < 0:
            raise ValueError("holdback must be a non-negative integer")
        self.holdback = holdback
        self._max_buffer = max(holdback * 16, 16384)
        self._buffer = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buffer += chunk
        buf_len = len(self._buffer)

        # Hold unclosed PEM private key blocks up to _max_buffer so the full block is scrubbed.
        begin_idx = self._buffer.rfind("-----BEGIN ")
        if begin_idx != -1 and "-----END " not in self._buffer[begin_idx:] and buf_len <= self._max_buffer:
            if begin_idx == 0:
                return ""
            safe_cut = min(begin_idx, max(0, buf_len - self.holdback))
            if safe_cut == 0:
                return ""
        else:
            if buf_len <= self.holdback:
                return ""
            safe_cut = buf_len - self.holdback

        for start, end in _collect_match_spans(self._buffer):
            if end > safe_cut and start < safe_cut:
                if end == buf_len and buf_len <= self._max_buffer:
                    safe_cut = min(safe_cut, start)
                elif start > 0:
                    safe_cut = min(safe_cut, start)
                else:
                    safe_cut = max(safe_cut, end)

        # Also avoid splitting a continuous non-whitespace token that touches the end of buffer.
        if 0 < safe_cut < buf_len and buf_len <= self._max_buffer:
            tail_ws = max(
                self._buffer.rfind(" ", 0, buf_len),
                self._buffer.rfind("\n", 0, buf_len),
                self._buffer.rfind("\r", 0, buf_len),
                self._buffer.rfind("\t", 0, buf_len),
            )
            if tail_ws == -1:
                return ""
            if tail_ws < safe_cut:
                safe_cut = tail_ws + 1

        if safe_cut <= 0:
            return ""

        emit_raw = self._buffer[:safe_cut]
        self._buffer = self._buffer[safe_cut:]
        return redact_text(emit_raw)

    def flush(self) -> str:
        if not self._buffer:
            return ""
        remaining = self._buffer
        self._buffer = ""
        return redact_text(remaining)


@contextmanager
def redaction_scope(literals: Iterable[str]) -> Iterator[None]:
    """Temporarily register resolved secret literals for scrubbing in the current context."""
    current = set(_ACTIVE_LITERALS.get())
    for item in literals:
        if isinstance(item, str) and len(item) >= 4 and item != REDACTED:
            current.add(item)
    ordered = tuple(sorted(current, key=len, reverse=True))
    token = _ACTIVE_LITERALS.set(ordered)
    try:
        yield
    finally:
        _ACTIVE_LITERALS.reset(token)


def redact(value: Any) -> Any:
    """Return a new JSON-compatible structure without mutating domain inputs."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            redact_text(str(key)): (
                REDACTED
                if (
                    _SECRET_KEY.fullmatch(str(key))
                    and item is not None
                    and not isinstance(item, bool)
                )
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def install_log_redaction() -> None:
    """Sanitize records before any handler, including exception and stack text."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_hydra_redaction", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        if not isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, dict):
            record.args = redact(record.args)
        elif record.args:
            record.args = tuple(redact(arg) for arg in record.args)
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return record

    factory._hydra_redaction = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


__all__ = [
    "REDACTED",
    "StreamingRedactor",
    "install_log_redaction",
    "redact",
    "redact_text",
    "redaction_scope",
    "register_secret",
]
