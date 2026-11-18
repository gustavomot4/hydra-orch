"""Safe session-scoped attachments (`AttachmentRef`) and artifact preview (`read_safe_preview`) (M5 / T31)."""

from __future__ import annotations

import base64
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PureWindowsPath
import re
import threading
from typing import Any, Dict, List, Literal, Optional, Union
import uuid

from pydantic import Field

from hydra_orch.core.git_workspace import (
    _strip_win_long_prefix,
    is_link_or_junction,
    win_long_path,
)
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact_text
from hydra_orch.model import (
    ContractViolation,
    ExecutionModel,
    Identifier,
    NonEmpty,
    RelativePath,
    Sha256,
    UtcTimestamp,
)

TransferStatus = Literal["local_ready", "pending_remote_confirm", "transferred", "failed"]
PreviewKind = Literal["markdown", "text", "diff", "image", "pdf", "unsupported"]
PreviewStatus = Literal["ok", "unsupported_media_type"]

_SAFE_MIME_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/csv",
        "text/tab-separated-values",
        "text/x-diff",
        "text/x-patch",
        "application/json",
        "text/x-python",
        "application/x-python-code",
        "application/typescript",
        "text/typescript",
        "text/x-typescript",
        "text/yaml",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "text/toml",
        "text/x-rust",
        "text/x-go",
        "text/x-java-source",
        "text/x-c",
        "text/x-c++",
    }
)

_FORBIDDEN_MIME_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
        "application/javascript",
        "text/javascript",
        "application/ecmascript",
        "application/x-javascript",
        "application/x-executable",
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-dosexec",
        "application/x-sh",
        "application/x-shellscript",
        "text/x-shellscript",
        "application/x-powershell",
        "application/x-bat",
        "application/x-csh",
        "application/wasm",
        "application/x-httpd-php",
        "text/xml",
        "application/xml",
    }
)

_FORBIDDEN_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".xhtml",
        ".svg",
        ".svgz",
        ".js",
        ".mjs",
        ".cjs",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bat",
        ".cmd",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".psm1",
        ".psd1",
        ".vbs",
        ".vbe",
        ".wsf",
        ".wsh",
        ".msi",
        ".scr",
        ".com",
        ".pif",
        ".hta",
        ".jar",
        ".app",
        ".dmg",
        ".pkg",
        ".deb",
        ".rpm",
        ".php",
        ".asp",
        ".aspx",
        ".jsp",
        ".wasm",
    }
)

_SAFE_EXT_TO_MIME: Dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".rst": "text/plain",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".sql": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".diff": "text/x-diff",
    ".patch": "text/x-patch",
    ".json": "application/json",
    ".py": "text/x-python",
    ".ts": "application/typescript",
    ".tsx": "application/typescript",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".rs": "text/x-rust",
    ".go": "text/x-go",
    ".java": "text/x-java-source",
    ".c": "text/x-c",
    ".h": "text/x-c",
    ".cpp": "text/x-c++",
    ".hpp": "text/x-c++",
}

_IMAGE_EXT_TO_MIME: Dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_TEXT_PREVIEW_EXTENSIONS = frozenset(
    {
        ".txt",
        ".log",
        ".rst",
        ".ini",
        ".cfg",
        ".sql",
        ".csv",
        ".tsv",
        ".diff",
        ".patch",
        ".json",
        ".py",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
        ".toml",
        ".rs",
        ".go",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".css",
    }
)

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)

_EXECUTABLE_MAGICS = (b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\x00asm")

_OPEN_SCRIPT_HEAD_RE = re.compile(r"<\s*script\b", re.IGNORECASE)
_CLOSE_SCRIPT_RE = re.compile(r"<\s*/\s*script\s*>", re.IGNORECASE)
_STRAY_SCRIPT_RE = re.compile(r"<\s*/?\s*script\b(?>[^>]*>|[^>]*$)", re.IGNORECASE)

_OPEN_EMBED_HEAD_RE = re.compile(r"<\s*(?:iframe|object|embed|svg|math)\b", re.IGNORECASE)
_CLOSE_EMBED_RE = re.compile(r"<\s*/\s*(?:iframe|object|embed|svg|math)\s*>", re.IGNORECASE)
_STRAY_EMBED_RE = re.compile(r"<\s*/?\s*(?:iframe|object|embed|svg|math)\b(?>[^>]*>|[^>]*$)", re.IGNORECASE)
_STRAY_DANGEROUS_ALL_RE = re.compile(
    r"<\s*/?\s*(?:script|iframe|object|embed|svg|math)\b(?>[^>]*>|[^>]*$)",
    re.IGNORECASE,
)
_INLINE_EVENT_HANDLER_RE = re.compile(
    r"""(?i)(?<=[\s<])on[a-z]{1,32}\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>'"]+)"""
)
_DANGEROUS_URI_IN_ATTR_RE = re.compile(
    r"""(?i)((?:href|src|action|formaction|poster|xlink:href)\s*=\s*)(?:"\s*(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html\b)[^"]*"|'\s*(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html\b)[^']*'|\s*(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html\b)[^\s>'"]*)"""
)
_DANGEROUS_URI_IN_MD_LINK_RE = re.compile(
    r"""(?i)(\]\(\s*)(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html\b)[^)]*\)"""
)


class AttachmentRef(ExecutionModel):
    """Typed, scope-bound attachment metadata persisted in the local index sidecar."""

    attachment_id: Identifier = Field(default_factory=new_id)
    workspace_id: NonEmpty
    session_id: NonEmpty
    host_id: NonEmpty = "local"
    filename: NonEmpty
    mime_type: NonEmpty
    size_bytes: int = Field(ge=0, strict=True)
    sha256: Sha256
    storage_rel_path: RelativePath
    transfer_status: TransferStatus = "local_ready"
    remote_confirmed: bool = False
    created_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArtifactPreviewResult(ExecutionModel):
    """Safe, bounded preview payload returned by `read_safe_preview`."""

    rel_path: NonEmpty
    kind: PreviewKind
    render_mode: PreviewKind
    mime_type: NonEmpty
    size_bytes: int = Field(ge=0, strict=True)
    sha256: Sha256
    supported: bool
    status: PreviewStatus
    content: Optional[str] = None
    sanitized_markdown: Optional[str] = None
    content_base64: Optional[str] = None
    script_stripped: bool = False
    redacted: bool = False
    reason: Optional[str] = None


def _normalize_mime(mime_type: Optional[str]) -> str:
    if not mime_type:
        return ""
    return mime_type.split(";", 1)[0].strip().lower()


def _validate_safe_scope_id(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation("attachment_invalid", f"{field_name} must be a string")
    cleaned = value.strip()
    if (
        not cleaned
        or cleaned != value
        or "\x00" in cleaned
        or "/" in cleaned
        or "\\" in cleaned
        or ".." in cleaned
        or ":" in cleaned
        or cleaned in {".", ".."}
    ):
        raise ContractViolation("attachment_invalid", f"Invalid {field_name}: must not contain traversal characters")
    return cleaned


def _validate_attachment_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise ContractViolation("path_traversal_blocked", "Attachment filename must be a string")
    if "\x00" in filename or "/" in filename or "\\" in filename or ":" in filename:
        raise ContractViolation("path_traversal_blocked", "Attachment filename contains forbidden path separators or NUL")
    cleaned = filename.strip()
    if not cleaned or cleaned != filename or cleaned in {".", ".."} or ".." in Path(cleaned).parts:
        raise ContractViolation("path_traversal_blocked", "Attachment filename traversal is blocked")
    if any(ord(ch) < 32 for ch in cleaned):
        raise ContractViolation("path_traversal_blocked", "Attachment filename contains control characters")
    if Path(cleaned).name != cleaned:
        raise ContractViolation("path_traversal_blocked", "Attachment filename must be a plain basename")
    stem_upper = Path(cleaned).stem.upper()
    if stem_upper in _WINDOWS_RESERVED_NAMES:
        raise ContractViolation("path_traversal_blocked", "Attachment filename uses a reserved device name")
    return cleaned


def _ensure_within_root(root_dir: Path, target_path: Path) -> Path:
    """Assert `target_path` and all existing ancestors stay within `root_dir` without symlink/junction escape."""
    canon_root = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(root_dir))))
    if not win_long_path(canon_root).is_dir():
        raise ContractViolation("workspace_invalid", f"Attachment root directory does not exist: {root_dir}")
    rel_parts = target_path.relative_to(root_dir).parts if target_path.is_absolute() else target_path.parts
    cursor = canon_root
    norm_root = os.path.normcase(str(canon_root))
    for part in rel_parts:
        cursor = cursor / part
        if is_link_or_junction(cursor):
            resolved_link = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(cursor))))
            norm_link = os.path.normcase(str(resolved_link))
            if norm_link != norm_root and not norm_link.startswith(norm_root + os.sep):
                raise ContractViolation("path_traversal_blocked", "Symlink or junction escape outside allowed root directory")
    joined = canon_root.joinpath(*rel_parts)
    resolved_target = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(joined))))
    norm_target = os.path.normcase(str(resolved_target))
    if norm_target == norm_root or not norm_target.startswith(norm_root + os.sep):
        raise ContractViolation("path_traversal_blocked", "Target path resolves outside allowed root directory")
    return resolved_target


def _atomic_write_bytes(target_path: Path, data: bytes) -> None:
    win_long_path(target_path.parent).mkdir(parents=True, exist_ok=True)
    short_name = target_path.name[:24]
    tmp_path = target_path.with_name(f".{short_name}.{uuid.uuid4().hex[:8]}.tmp")
    lp_tmp = win_long_path(tmp_path)
    with open(lp_tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(lp_tmp, win_long_path(target_path))


def _has_executable_magic(data: bytes) -> bool:
    return any(data.startswith(magic) for magic in _EXECUTABLE_MAGICS)


def _looks_like_active_web_markup(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith((b"<svg", b"<!doctype html", b"<html", b"<script", b"<?xml"))


def _strip_tag_family(
    text: str,
    open_head_re: re.Pattern[str],
    close_re: re.Pattern[str],
    stray_re: re.Pattern[str],
) -> str:
    if "</" not in text:
        return stray_re.sub("", text)
    if close_re.search(text) is None:
        return stray_re.sub("", text)

    pieces: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        m_open = open_head_re.search(text, pos)
        if m_open is None:
            pieces.append(stray_re.sub("", text[pos:]))
            break
        if m_open.start() > pos:
            pieces.append(stray_re.sub("", text[pos:m_open.start()]))
        gt = text.find(">", m_open.end())
        if gt == -1:
            break
        if gt > m_open.end() and text[gt - 1] == "/":
            pos = gt + 1
            continue
        m_close = close_re.search(text, gt + 1)
        if m_close is None:
            pieces.append(stray_re.sub("", text[gt + 1:]))
            break
        pos = m_close.end()
    return "".join(pieces)


def _strip_dangerous_html_tags(text: str) -> str:
    """Linear O(N) C-accelerated removal of closed and orphaned dangerous HTML/SVG/MathML tags."""
    if "<" not in text:
        return text
    if "</" not in text:
        return _STRAY_DANGEROUS_ALL_RE.sub("", text)
    text = _strip_tag_family(text, _OPEN_SCRIPT_HEAD_RE, _CLOSE_SCRIPT_RE, _STRAY_SCRIPT_RE)
    if "<" in text:
        text = _strip_tag_family(text, _OPEN_EMBED_HEAD_RE, _CLOSE_EMBED_RE, _STRAY_EMBED_RE)
    return text


def _replace_dangerous_attr_uri(match: re.Match[str]) -> str:
    prefix = match.group(1)
    full = match.group(0)
    rhs = full[len(prefix):]
    if rhs.startswith('"'):
        return f'{prefix}"#blocked-uri"'
    if rhs.startswith("'"):
        return f"{prefix}'#blocked-uri'"
    return f"{prefix}#blocked-uri"


def sanitize_markdown_content(raw_markdown: str) -> tuple[str, bool, bool]:
    """Redact secrets and strip active script/XSS payloads from Markdown text in O(N) time."""
    redacted_text = redact_text(raw_markdown)
    redacted_flag = redacted_text != raw_markdown

    sanitized = _strip_dangerous_html_tags(redacted_text)
    if "=" in sanitized:
        sanitized = _INLINE_EVENT_HANDLER_RE.sub("", sanitized)
        sanitized = _DANGEROUS_URI_IN_ATTR_RE.sub(_replace_dangerous_attr_uri, sanitized)
    if "](" in sanitized:
        sanitized = _DANGEROUS_URI_IN_MD_LINK_RE.sub(r"\1#blocked-uri)", sanitized)
    script_stripped = sanitized != redacted_text
    return sanitized, script_stripped, redacted_flag


class AttachmentService:
    """Session-scoped attachment storage with strict MIME/size/traversal guards and restart-safe JSON index."""

    def __init__(self, root_dir: Union[Path, str], *, max_bytes: int = 10 * 1024 * 1024) -> None:
        if max_bytes <= 0:
            raise ContractViolation("attachment_invalid", "max_bytes must be positive")
        raw_root = Path(root_dir)
        win_long_path(raw_root).mkdir(parents=True, exist_ok=True)
        self.root_dir = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(raw_root))))
        self.max_bytes = int(max_bytes)
        self._index_path = self.root_dir / "_index.json"
        self._lock = threading.RLock()
        self._records: Dict[str, AttachmentRef] = {}
        self._index_mtime_ns: Optional[int] = None
        self._load_index()

    def _sync_index_if_changed(self) -> None:
        with self._lock:
            lp_index = win_long_path(self._index_path)
            if not lp_index.exists():
                if self._index_mtime_ns is not None:
                    self._records = {}
                    self._index_mtime_ns = None
                return
            try:
                current_mtime = lp_index.stat().st_mtime_ns
            except OSError:
                return
            if self._index_mtime_ns != current_mtime:
                self._load_index()

    def _load_index(self) -> None:
        with self._lock:
            lp_index = win_long_path(self._index_path)
            if not lp_index.exists():
                self._records = {}
                self._index_mtime_ns = None
                return
            try:
                stat_res = lp_index.stat()
                payload = json.loads(lp_index.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractViolation("attachment_index_corrupt", f"Cannot read attachment index: {exc}") from exc
            raw_items = payload.get("attachments", {}) if isinstance(payload, dict) else {}
            if not isinstance(raw_items, dict):
                raise ContractViolation("attachment_index_corrupt", "Invalid attachment index format")
            loaded: Dict[str, AttachmentRef] = {}
            for att_id, item in raw_items.items():
                ref = AttachmentRef.model_validate(item)
                loaded[att_id] = ref
            self._records = loaded
            self._index_mtime_ns = stat_res.st_mtime_ns

    def _persist_index(self) -> None:
        payload = {
            "schema_version": "1.0",
            "attachments": {
                att_id: ref.model_dump(mode="json")
                for att_id, ref in sorted(self._records.items())
            },
        }
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        _atomic_write_bytes(self._index_path, data)
        with suppress(OSError):
            self._index_mtime_ns = win_long_path(self._index_path).stat().st_mtime_ns

    @staticmethod
    def _validate_mime_and_extension(filename: str, mime_type: Optional[str], content: bytes) -> str:
        ext = Path(filename).suffix.lower()
        normalized_mime = _normalize_mime(mime_type)

        if ext in _FORBIDDEN_EXTENSIONS or normalized_mime in _FORBIDDEN_MIME_TYPES:
            raise ContractViolation(
                "unsupported_attachment_type",
                f"Active web or executable attachment type is rejected: {filename} ({normalized_mime or ext})",
            )

        if _has_executable_magic(content):
            raise ContractViolation(
                "unsupported_attachment_type",
                f"Executable binary signature rejected for attachment '{filename}'",
            )

        if ext and ext not in _SAFE_EXT_TO_MIME:
            raise ContractViolation(
                "unsupported_attachment_type",
                f"Attachment extension '{ext}' is not on the safe allowlist",
            )

        inferred_mime = _SAFE_EXT_TO_MIME.get(ext)
        if not normalized_mime:
            if inferred_mime is not None:
                normalized_mime = inferred_mime
            else:
                guessed, _ = mimetypes.guess_type(filename)
                normalized_mime = _normalize_mime(guessed) or "text/plain"

        if normalized_mime not in _SAFE_MIME_TYPES:
            raise ContractViolation(
                "unsupported_attachment_type",
                f"MIME type '{normalized_mime}' is not on the safe attachment allowlist",
            )

        if ext in _IMAGE_EXT_TO_MIME or ext == ".pdf":
            if _looks_like_active_web_markup(content):
                raise ContractViolation(
                    "unsupported_attachment_type",
                    f"Active HTML/SVG markup disguised as '{filename}' is rejected",
                )

        if ext == ".pdf" or normalized_mime == "application/pdf":
            if not content.startswith(b"%PDF-"):
                raise ContractViolation(
                    "unsupported_attachment_type",
                    f"Invalid PDF magic header for attachment '{filename}'",
                )

        if ext == ".txt" and normalized_mime == "text/plain" and b"\x00" in content:
            raise ContractViolation(
                "unsupported_attachment_type",
                "Binary NUL bytes rejected in text/plain attachment",
            )

        return normalized_mime

    @staticmethod
    def _build_short_storage_rel_path(session_id: str, attachment_id: str, safe_filename: str) -> str:
        ext = re.sub(r"[^A-Za-z0-9.]+", "", Path(safe_filename).suffix)[:12]
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(safe_filename).stem).strip("._-")[:16] or "file"
        short_name = f"{stem}{ext}"
        sha12 = hashlib.sha256(
            f"{session_id}:{attachment_id}:{safe_filename}".encode("utf-8")
        ).hexdigest()[:12]
        return f"att/{sha12}_{short_name}"

    def save_attachment(
        self,
        workspace_id: str,
        session_id: str,
        filename: str,
        content: bytes,
        *,
        mime_type: Optional[str] = None,
        host_id: str = "local",
        attachment_id: Optional[str] = None,
    ) -> AttachmentRef:
        """Validate, atomically store, hash, and index a session-scoped attachment."""
        ws_id = _validate_safe_scope_id(workspace_id, "workspace_id")
        sess_id = _validate_safe_scope_id(session_id, "session_id")
        safe_host = _validate_safe_scope_id(host_id, "host_id")
        safe_filename = _validate_attachment_filename(filename)

        if not isinstance(content, (bytes, bytearray)):
            raise ContractViolation("attachment_invalid", "Attachment content must be bytes")
        raw_bytes = bytes(content)
        if len(raw_bytes) > self.max_bytes:
            raise ContractViolation(
                "attachment_too_large",
                f"Attachment size {len(raw_bytes)} exceeds maximum {self.max_bytes} bytes",
            )

        resolved_mime = self._validate_mime_and_extension(safe_filename, mime_type, raw_bytes)
        att_id = _validate_safe_scope_id(attachment_id, "attachment_id") if attachment_id else new_id()
        rel_path = self._build_short_storage_rel_path(sess_id, att_id, safe_filename)
        digest = hashlib.sha256(raw_bytes).hexdigest()

        is_local = safe_host == "local"
        transfer_status: TransferStatus = "local_ready" if is_local else "pending_remote_confirm"

        ref = AttachmentRef(
            attachment_id=att_id,
            workspace_id=ws_id,
            session_id=sess_id,
            host_id=safe_host,
            filename=safe_filename,
            mime_type=resolved_mime,
            size_bytes=len(raw_bytes),
            sha256=digest,
            storage_rel_path=rel_path,
            transfer_status=transfer_status,
            remote_confirmed=False,
        )

        with self._lock:
            self._sync_index_if_changed()
            if att_id in self._records:
                raise ContractViolation("attachment_conflict", f"Attachment '{att_id}' already exists")
            target_path = _ensure_within_root(self.root_dir, self.root_dir / rel_path)
            _atomic_write_bytes(target_path, raw_bytes)
            self._records[att_id] = ref
            self._persist_index()
        return ref

    def list_attachments(self, session_id: str) -> List[AttachmentRef]:
        """List all attachments owned by `session_id` in chronological/ID order."""
        sess_id = _validate_safe_scope_id(session_id, "session_id")
        with self._lock:
            self._sync_index_if_changed()
            return [
                ref
                for ref in sorted(self._records.values(), key=lambda item: (item.created_at, item.attachment_id))
                if ref.session_id == sess_id
            ]

    def get_attachment(self, attachment_id: str, *, session_id: str) -> AttachmentRef:
        """Fetch an attachment record while strictly enforcing session ownership."""
        sess_id = _validate_safe_scope_id(session_id, "session_id")
        with self._lock:
            ref = self._records.get(attachment_id)
            if ref is None:
                self._load_index()
                ref = self._records.get(attachment_id)
            if ref is None:
                raise ContractViolation("resource_not_found", f"Attachment '{attachment_id}' does not exist")
            if ref.session_id != sess_id:
                raise ContractViolation(
                    "forbidden_scope",
                    f"Attachment '{attachment_id}' does not belong to session '{sess_id}'",
                )
            return ref

    def read_attachment_bytes(self, attachment_id: str, *, session_id: str) -> bytes:
        """Read attachment bytes after verifying session scope and SHA-256 integrity."""
        ref = self.get_attachment(attachment_id, session_id=session_id)
        target_path = _ensure_within_root(self.root_dir, self.root_dir / ref.storage_rel_path)
        lp_target = win_long_path(target_path)
        if not lp_target.is_file():
            raise ContractViolation("resource_not_found", f"Attachment payload missing for '{attachment_id}'")
        data = lp_target.read_bytes()
        if hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ContractViolation("artifact_tampered", f"Attachment '{attachment_id}' failed SHA-256 verification")
        return data

    def confirm_remote_transfer(self, attachment_id: str, *, session_id: str) -> AttachmentRef:
        """Confirm that a remote-host attachment has been safely transferred to the target host."""
        sess_id = _validate_safe_scope_id(session_id, "session_id")
        with self._lock:
            ref = self.get_attachment(attachment_id, session_id=sess_id)
            if ref.host_id == "local":
                raise ContractViolation(
                    "attachment_not_remote",
                    f"Attachment '{attachment_id}' targets local host and does not require remote transfer",
                )
            updated = ref.model_copy(
                update={
                    "remote_confirmed": True,
                    "transfer_status": "transferred",
                }
            )
            self._records[attachment_id] = updated
            self._persist_index()
            return updated

    def fail_remote_transfer(self, attachment_id: str, *, session_id: str) -> AttachmentRef:
        """Record explicit remote transfer failure for an attachment."""
        sess_id = _validate_safe_scope_id(session_id, "session_id")
        with self._lock:
            ref = self.get_attachment(attachment_id, session_id=sess_id)
            updated = ref.model_copy(
                update={
                    "remote_confirmed": False,
                    "transfer_status": "failed",
                }
            )
            self._records[attachment_id] = updated
            self._persist_index()
            return updated


def _resolve_preview_target(base_dir: Union[Path, str], rel_path: str) -> tuple[Path, str]:
    if not isinstance(rel_path, str) or not rel_path.strip() or "\x00" in rel_path:
        raise ContractViolation("path_traversal_blocked", "Preview path cannot be empty or contain NUL bytes")

    normalized_rel = rel_path.replace("\\", "/")
    if (
        normalized_rel.startswith("/")
        or Path(rel_path).is_absolute()
        or PureWindowsPath(rel_path).drive
        or ":" in normalized_rel
    ):
        raise ContractViolation("path_traversal_blocked", "Absolute or drive-qualified preview paths are blocked")

    parts = [p for p in normalized_rel.split("/") if p]
    if not parts or normalized_rel in {".", "./"} or any(part in {".", ".."} for part in parts):
        raise ContractViolation("path_traversal_blocked", "Path traversal segments are blocked in preview")
    for part in parts:
        if part.split(".", 1)[0].strip().upper() in _WINDOWS_RESERVED_NAMES:
            raise ContractViolation("path_traversal_blocked", "Reserved Windows device names are blocked in preview")

    raw_base = Path(base_dir)
    if not win_long_path(raw_base).exists():
        raise ContractViolation("workspace_invalid", f"Preview base directory does not exist: {base_dir}")
    canon_base = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(raw_base))))
    if not win_long_path(canon_base).is_dir():
        raise ContractViolation("workspace_invalid", f"Preview base path is not a directory: {canon_base}")

    norm_base = os.path.normcase(str(canon_base))
    cursor = canon_base
    for part in parts:
        cursor = cursor / part
        if is_link_or_junction(cursor):
            link_target = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(cursor))))
            norm_link = os.path.normcase(str(link_target))
            if norm_link != norm_base and not norm_link.startswith(norm_base + os.sep):
                raise ContractViolation("path_traversal_blocked", "Symlink or junction escapes preview base directory")

    joined_target = canon_base.joinpath(*parts)
    resolved_target = Path(_strip_win_long_prefix(os.path.realpath(win_long_path(joined_target))))
    norm_target = os.path.normcase(str(resolved_target))
    if norm_target == norm_base or not norm_target.startswith(norm_base + os.sep):
        raise ContractViolation("path_traversal_blocked", "Preview target escapes base directory")

    lp_resolved = win_long_path(resolved_target)
    if not lp_resolved.exists() or not lp_resolved.is_file():
        raise ContractViolation("resource_not_found", f"Preview target does not exist: {normalized_rel}")

    return resolved_target, "/".join(parts)


def build_safe_preview(
    base_dir: Union[Path, str],
    rel_path: str,
    *,
    max_bytes: int = 512 * 1024,
) -> ArtifactPreviewResult:
    """Resolve `rel_path` safely under `base_dir` and return a typed `ArtifactPreviewResult`."""
    if max_bytes <= 0:
        raise ContractViolation("preview_invalid", "max_bytes must be positive")

    target_path, clean_rel = _resolve_preview_target(base_dir, rel_path)
    lp_target = win_long_path(target_path)
    stat_size = lp_target.stat().st_size
    if stat_size > max_bytes:
        raise ContractViolation(
            "preview_too_large",
            f"Artifact size {stat_size} exceeds safe preview limit of {max_bytes} bytes",
        )

    with open(lp_target, "rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ContractViolation(
            "preview_too_large",
            f"Artifact size exceeds safe preview limit of {max_bytes} bytes",
        )

    digest = hashlib.sha256(raw).hexdigest()
    size_bytes = len(raw)
    ext = target_path.suffix.lower()

    if ext in _FORBIDDEN_EXTENSIONS:
        guessed_mime, _ = mimetypes.guess_type(target_path.name)
        mime = _normalize_mime(guessed_mime) or (
            "image/svg+xml" if ext in {".svg", ".svgz"} else "text/html" if ext in {".html", ".htm", ".xhtml"} else "application/octet-stream"
        )
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="unsupported",
            render_mode="unsupported",
            mime_type=mime,
            size_bytes=size_bytes,
            sha256=digest,
            supported=False,
            status="unsupported_media_type",
            reason="active_web_or_executable_media_blocked",
        )

    if _has_executable_magic(raw):
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="unsupported",
            render_mode="unsupported",
            mime_type="application/octet-stream",
            size_bytes=size_bytes,
            sha256=digest,
            supported=False,
            status="unsupported_media_type",
            reason="executable_binary_blocked",
        )

    if ext in _IMAGE_EXT_TO_MIME:
        if _looks_like_active_web_markup(raw):
            return ArtifactPreviewResult(
                rel_path=clean_rel,
                kind="unsupported",
                render_mode="unsupported",
                mime_type="image/svg+xml",
                size_bytes=size_bytes,
                sha256=digest,
                supported=False,
                status="unsupported_media_type",
                reason="disguised_active_markup_blocked",
            )
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="image",
            render_mode="image",
            mime_type=_IMAGE_EXT_TO_MIME[ext],
            size_bytes=size_bytes,
            sha256=digest,
            supported=True,
            status="ok",
            content_base64=base64.b64encode(raw).decode("ascii"),
        )

    if ext == ".pdf":
        if _looks_like_active_web_markup(raw):
            return ArtifactPreviewResult(
                rel_path=clean_rel,
                kind="unsupported",
                render_mode="unsupported",
                mime_type="text/html",
                size_bytes=size_bytes,
                sha256=digest,
                supported=False,
                status="unsupported_media_type",
                reason="disguised_active_markup_blocked",
            )
        if not raw.startswith(b"%PDF-"):
            return ArtifactPreviewResult(
                rel_path=clean_rel,
                kind="unsupported",
                render_mode="unsupported",
                mime_type="application/octet-stream",
                size_bytes=size_bytes,
                sha256=digest,
                supported=False,
                status="unsupported_media_type",
                reason="invalid_pdf_magic",
            )
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="pdf",
            render_mode="pdf",
            mime_type="application/pdf",
            size_bytes=size_bytes,
            sha256=digest,
            supported=True,
            status="ok",
            content_base64=base64.b64encode(raw).decode("ascii"),
        )

    if ext in {".md", ".markdown"}:
        raw_text = raw.decode("utf-8", errors="replace")
        sanitized, script_stripped, redacted_flag = sanitize_markdown_content(raw_text)
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="markdown",
            render_mode="markdown",
            mime_type="text/markdown",
            size_bytes=size_bytes,
            sha256=digest,
            supported=True,
            status="ok",
            content=sanitized,
            sanitized_markdown=sanitized,
            script_stripped=script_stripped,
            redacted=redacted_flag,
        )

    if b"\x00" in raw:
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="unsupported",
            render_mode="unsupported",
            mime_type="application/octet-stream",
            size_bytes=size_bytes,
            sha256=digest,
            supported=False,
            status="unsupported_media_type",
            reason="binary_media_unsupported",
        )

    if ext in _TEXT_PREVIEW_EXTENSIONS:
        raw_text = raw.decode("utf-8", errors="replace")
        redacted_val = redact_text(raw_text)
        kind: PreviewKind = "diff" if ext in {".diff", ".patch"} else "text"
        mime = _SAFE_EXT_TO_MIME.get(ext, "text/plain")
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind=kind,
            render_mode=kind,
            mime_type=mime,
            size_bytes=size_bytes,
            sha256=digest,
            supported=True,
            status="ok",
            content=redacted_val,
            redacted=(redacted_val != raw_text),
        )

    # Extensionless or unknown extension: only preview if strict UTF-8 and not active HTML/SVG markup
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="unsupported",
            render_mode="unsupported",
            mime_type="application/octet-stream",
            size_bytes=size_bytes,
            sha256=digest,
            supported=False,
            status="unsupported_media_type",
            reason="binary_media_unsupported",
        )

    if _looks_like_active_web_markup(raw):
        return ArtifactPreviewResult(
            rel_path=clean_rel,
            kind="unsupported",
            render_mode="unsupported",
            mime_type="text/html",
            size_bytes=size_bytes,
            sha256=digest,
            supported=False,
            status="unsupported_media_type",
            reason="active_web_or_executable_media_blocked",
        )

    redacted_val = redact_text(decoded)
    return ArtifactPreviewResult(
        rel_path=clean_rel,
        kind="text",
        render_mode="text",
        mime_type="text/plain",
        size_bytes=size_bytes,
        sha256=digest,
        supported=True,
        status="ok",
        content=redacted_val,
        redacted=(redacted_val != decoded),
    )


def read_safe_preview(
    base_dir: Union[Path, str],
    rel_path: str,
    *,
    max_bytes: int = 512 * 1024,
) -> Dict[str, Any]:
    """Read a bounded, traversal-proof, script-safe artifact preview dictionary."""
    return build_safe_preview(base_dir, rel_path, max_bytes=max_bytes).model_dump(mode="json")


__all__ = [
    "ArtifactPreviewResult",
    "AttachmentRef",
    "AttachmentService",
    "PreviewKind",
    "PreviewStatus",
    "TransferStatus",
    "build_safe_preview",
    "read_safe_preview",
    "sanitize_markdown_content",
]
