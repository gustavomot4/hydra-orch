"""Safe session-scoped attachments (`AttachmentRef`) and artifact preview (`read_safe_preview`) (M5 / T31)."""

from __future__ import annotations

import base64
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

_SCRIPT_BLOCK_RE = re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_STRAY_SCRIPT_TAG_RE = re.compile(r"<\s*/?\s*script\b[^>]*>", re.IGNORECASE)
_DANGEROUS_EMBED_RE = re.compile(
    r"<\s*(?:iframe|object|embed|svg|math)\b[^>]*>.*?<\s*/\s*(?:iframe|object|embed|svg|math)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SELF_CLOSING_EMBED_RE = re.compile(r"<\s*/?\s*(?:iframe|object|embed|svg|math)\b[^>]*>", re.IGNORECASE)
_INLINE_EVENT_HANDLER_RE = re.compile(
    r"""(?i)(?<=[\s<])on[a-z]{1,32}\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)"""
)
_DANGEROUS_URI_IN_ATTR_RE = re.compile(
    r"""(?i)((?:href|src|action|formaction|poster|xlink:href)\s*=\s*)(["']?)\s*(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html\b)[^"'>\s]*\2"""
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
    """Assert `target_path` and all existing ancestors stay within `root_dir` without symlink escape."""
    canon_root = root_dir.resolve(strict=True)
    rel_parts = target_path.relative_to(root_dir).parts if target_path.is_absolute() else target_path.parts
    cursor = canon_root
    for part in rel_parts:
        cursor = cursor / part
        if cursor.is_symlink():
            resolved_link = Path(os.path.realpath(cursor))
            if resolved_link != canon_root and canon_root not in resolved_link.parents:
                raise ContractViolation("path_traversal_blocked", "Symlink escape outside allowed root directory")
    resolved_target = Path(os.path.realpath(canon_root.joinpath(*rel_parts)))
    if resolved_target == canon_root or canon_root not in resolved_target.parents:
        raise ContractViolation("path_traversal_blocked", "Target path resolves outside allowed root directory")
    return resolved_target


def _atomic_write_bytes(target_path: Path, data: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp_path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, target_path)


def _has_executable_magic(data: bytes) -> bool:
    return any(data.startswith(magic) for magic in _EXECUTABLE_MAGICS)


def _looks_like_active_web_markup(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith((b"<svg", b"<!doctype html", b"<html", b"<script", b"<?xml"))


def sanitize_markdown_content(raw_markdown: str) -> tuple[str, bool, bool]:
    """Redact secrets and strip active script/XSS payloads from Markdown text."""
    redacted_text = redact_text(raw_markdown)
    redacted_flag = redacted_text != raw_markdown

    sanitized = _SCRIPT_BLOCK_RE.sub("", redacted_text)
    sanitized = _STRAY_SCRIPT_TAG_RE.sub("", sanitized)
    sanitized = _DANGEROUS_EMBED_RE.sub("", sanitized)
    sanitized = _SELF_CLOSING_EMBED_RE.sub("", sanitized)
    sanitized = _INLINE_EVENT_HANDLER_RE.sub("", sanitized)
    sanitized = _DANGEROUS_URI_IN_ATTR_RE.sub(r"\1\2#blocked-uri\2", sanitized)
    sanitized = _DANGEROUS_URI_IN_MD_LINK_RE.sub(r"\1#blocked-uri)", sanitized)
    script_stripped = sanitized != redacted_text
    return sanitized, script_stripped, redacted_flag


class AttachmentService:
    """Session-scoped attachment storage with strict MIME/size/traversal guards and restart-safe JSON index."""

    def __init__(self, root_dir: Union[Path, str], *, max_bytes: int = 10 * 1024 * 1024) -> None:
        if max_bytes <= 0:
            raise ContractViolation("attachment_invalid", "max_bytes must be positive")
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_bytes)
        self._index_path = self.root_dir / "_index.json"
        self._lock = threading.RLock()
        self._records: Dict[str, AttachmentRef] = {}
        self._load_index()

    def _load_index(self) -> None:
        with self._lock:
            if not self._index_path.exists():
                self._records = {}
                return
            try:
                payload = json.loads(self._index_path.read_text(encoding="utf-8"))
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

        if ext == ".txt" and normalized_mime == "text/plain" and b"\x00" in content:
            raise ContractViolation(
                "unsupported_attachment_type",
                "Binary NUL bytes rejected in text/plain attachment",
            )

        return normalized_mime

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
        rel_path = f"files/{sess_id}/{att_id}_{safe_filename}"
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
        if not target_path.is_file():
            raise ContractViolation("resource_not_found", f"Attachment payload missing for '{attachment_id}'")
        data = target_path.read_bytes()
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

    try:
        canon_base = Path(base_dir).resolve(strict=True)
    except OSError as exc:
        raise ContractViolation("workspace_invalid", f"Preview base directory does not exist: {base_dir}") from exc
    if not canon_base.is_dir():
        raise ContractViolation("workspace_invalid", f"Preview base path is not a directory: {canon_base}")

    cursor = canon_base
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            link_target = Path(os.path.realpath(cursor))
            if link_target != canon_base and canon_base not in link_target.parents:
                raise ContractViolation("path_traversal_blocked", "Symlink escapes preview base directory")

    resolved_target = Path(os.path.realpath(canon_base.joinpath(*parts)))
    if resolved_target == canon_base or canon_base not in resolved_target.parents:
        raise ContractViolation("path_traversal_blocked", "Preview target escapes base directory")

    if not resolved_target.exists() or not resolved_target.is_file():
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
    stat_size = target_path.stat().st_size
    if stat_size > max_bytes:
        raise ContractViolation(
            "preview_too_large",
            f"Artifact size {stat_size} exceeds safe preview limit of {max_bytes} bytes",
        )

    with open(target_path, "rb") as handle:
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
