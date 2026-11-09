"""Conservative, deterministic redaction at evidence and logging boundaries."""

from __future__ import annotations

import logging
import re
from typing import Any

REDACTED = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"^(?:authorization|(?:api[_-]?|access[_-]?|refresh[_-]?|id[_-]?)?token|"
    r"(?:api|client|private)[_-]?key|(?:client[_-]?)?secret|password|passwd|"
    r"credential|oauth[_-]?(?:token|secret))$", re.I
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----.*?"
    r"(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|$)", re.S
)
_PROVIDER_TOKEN = re.compile(
    r"\b(?:sk-|ghp_|github_pat_|glpat-|xox[baprs]-)[A-Za-z0-9_-]{8,}"
)
_BEARER = re.compile(r"\bBearer\s+[^\s\"'<>;,]+", re.I)
_ASSIGNMENT = re.compile(
    r"(?P<label>\b(?:password|passwd|secret|api[_-]?key|client[_-]?secret|"
    r"(?:access[_-]?|refresh[_-]?|oauth[_-]?)?token)\b[\"']?\s*[:=]\s*)"
    r"(?:\[REDACTED\]|\"[^\"]*\"|'[^']*'|[^\s,;&\}\]]+)", re.I
)
_URL_CREDENTIAL = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/\s@]+@", re.I)


def redact_text(text: str) -> str:
    text = _PRIVATE_KEY.sub(REDACTED, text)
    text = _PROVIDER_TOKEN.sub(REDACTED, text)
    text = _BEARER.sub("Bearer " + REDACTED, text)
    text = _ASSIGNMENT.sub(lambda m: m["label"] + REDACTED, text)
    return _URL_CREDENTIAL.sub(lambda m: m[1] + REDACTED + "@", text)


def redact(value: Any) -> Any:
    """Return a new JSON-compatible structure without mutating domain inputs."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            redact_text(str(key)): REDACTED if _SECRET_KEY.fullmatch(str(key)) else redact(item)
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
