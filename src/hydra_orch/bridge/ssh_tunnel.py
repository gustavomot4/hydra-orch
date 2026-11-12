"""SSH and autossh tunnel manager with strict host key pinning and session isolation."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import httpx

from hydra_orch.model import ContractViolation

logger = logging.getLogger(__name__)


def _redact_text(text: str) -> str:
    # core.__init__ re-exports SshTunnelManager; defer redaction import to avoid circular import.
    from hydra_orch.core.redaction import redact_text

    return redact_text(text)

_SHA256_FP_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]+={0,2}$")
_HASHED_HOST_RE = re.compile(r"^\|1\|([^|]+)\|([^|]+)$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAX_BUFFER_LINES = 4096


class TransportSecurityError(ContractViolation):
    """Raised when transport security invariants (host key, TLS/pinning, strict mode) fail."""

    def __init__(self, code: str, message: str):
        super().__init__(code, _redact_text(message))


def normalize_sha256_fingerprint(fingerprint: str) -> str:
    """Validate and normalize an OpenSSH SHA-256 host key fingerprint."""
    if not isinstance(fingerprint, str):
        raise TransportSecurityError("ssh_invalid_fingerprint", "SSH host key fingerprint must be a string")
    candidate = fingerprint.strip()
    if not _SHA256_FP_RE.fullmatch(candidate):
        raise TransportSecurityError(
            "ssh_invalid_fingerprint",
            "SSH host key fingerprint must use canonical 'SHA256:<base64>' format",
        )
    prefix, body = candidate.split(":", 1)
    return f"{prefix}:{body.rstrip('=')}"


def compute_ssh_host_key_fingerprint(key_base64: str) -> str:
    """Compute the OpenSSH SHA-256 fingerprint from a base64-encoded public key blob."""
    try:
        raw = base64.b64decode(key_base64.strip(), validate=True)
    except Exception as exc:
        raise TransportSecurityError(
            "ssh_known_hosts_invalid",
            "Invalid base64 public key in known_hosts",
        ) from exc
    if not raw:
        raise TransportSecurityError("ssh_known_hosts_invalid", "Empty public key in known_hosts")
    digest = hashlib.sha256(raw).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


@dataclass(frozen=True)
class KnownHostEntry:
    """Parsed entry from an OpenSSH known_hosts file."""

    patterns: Tuple[str, ...]
    key_type: str
    fingerprint: str
    marker: Optional[str] = None
    line_number: int = 0


@dataclass(frozen=True)
class HostKeyVerificationResult:
    """Result of offline or probed SSH host key verification."""

    host: str
    port: int
    fingerprint: str
    verified_against: str
    known_hosts_file: Optional[str] = None


def _match_host_pattern(pattern: str, candidates: Tuple[str, ...]) -> bool:
    """Match an OpenSSH known_hosts pattern (plain, [host]:port, or |1|salt|hash)."""
    hashed = _HASHED_HOST_RE.fullmatch(pattern)
    if hashed:
        salt_b64, expected_hash_b64 = hashed.groups()
        try:
            salt = base64.b64decode(salt_b64, validate=True)
            expected_digest = base64.b64decode(expected_hash_b64, validate=True)
        except Exception:
            return False
        for candidate in candidates:
            actual_digest = hmac.new(salt, candidate.encode("utf-8"), hashlib.sha1).digest()
            if hmac.compare_digest(actual_digest, expected_digest):
                return True
        return False
    return any(candidate == pattern for candidate in candidates)


def _entry_matches_target(patterns: Tuple[str, ...], host: str, port: int) -> bool:
    """Evaluate OpenSSH known_hosts comma-separated host patterns including negations."""
    normalized_host = host.strip().lower()
    if port == 22:
        candidates = (normalized_host, f"[{normalized_host}]:22")
    else:
        candidates = (f"[{normalized_host}]:{port}",)

    matched = False
    for raw_pattern in patterns:
        pat = raw_pattern.strip()
        if not pat:
            continue
        if pat.startswith("!"):
            if _match_host_pattern(pat[1:].lower() if not pat[1:].startswith("|1|") else pat[1:], candidates):
                return False
            continue
        target_pat = pat if pat.startswith("|1|") else pat.lower()
        if _match_host_pattern(target_pat, candidates):
            matched = True
    return matched


def parse_known_hosts(content: str) -> Tuple[KnownHostEntry, ...]:
    """Parse an OpenSSH known_hosts text block into typed entries."""
    entries: List[KnownHostEntry] = []
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        marker: Optional[str] = None
        if parts[0].startswith("@"):
            marker = parts[0].lower()
            parts = parts[1:]
        if len(parts) < 3:
            raise TransportSecurityError(
                "ssh_known_hosts_invalid",
                f"Malformed known_hosts entry on line {line_no}",
            )
        hosts_field, key_type, key_b64 = parts[0], parts[1], parts[2]
        patterns = tuple(p for p in hosts_field.split(",") if p)
        if not patterns:
            raise TransportSecurityError(
                "ssh_known_hosts_invalid",
                f"Missing host pattern in known_hosts on line {line_no}",
            )
        fingerprint = compute_ssh_host_key_fingerprint(key_b64)
        entries.append(
            KnownHostEntry(
                patterns=patterns,
                key_type=key_type,
                fingerprint=fingerprint,
                marker=marker,
                line_number=line_no,
            )
        )
    return tuple(entries)


@dataclass
class SessionTunnelHandle:
    """Isolated runtime state and output buffers for a single concurrent SSH tunnel session."""

    session_id: str
    host: str
    port: int
    local_port: int
    remote_port: int
    status: str = "allocated"
    process: Optional[Any] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _stdout_lines: List[str] = field(default_factory=list, repr=False, compare=False)
    _stderr_lines: List[str] = field(default_factory=list, repr=False, compare=False)

    def append_stdout(self, text: str) -> None:
        if not text:
            return
        sanitized = _redact_text(text)
        with self._lock:
            self._stdout_lines.append(sanitized)
            if len(self._stdout_lines) > _MAX_BUFFER_LINES:
                del self._stdout_lines[: len(self._stdout_lines) - _MAX_BUFFER_LINES]

    def append_stderr(self, text: str) -> None:
        if not text:
            return
        sanitized = _redact_text(text)
        with self._lock:
            self._stderr_lines.append(sanitized)
            if len(self._stderr_lines) > _MAX_BUFFER_LINES:
                del self._stderr_lines[: len(self._stderr_lines) - _MAX_BUFFER_LINES]

    def get_stdout(self) -> str:
        with self._lock:
            return "".join(self._stdout_lines)

    def get_stderr(self) -> str:
        with self._lock:
            return "".join(self._stderr_lines)

    def get_logs(self) -> Dict[str, str]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "stdout": "".join(self._stdout_lines),
                "stderr": "".join(self._stderr_lines),
            }


def _validate_strict_host_key_checking(value: Any) -> str:
    if not isinstance(value, str):
        raise TransportSecurityError(
            "ssh_insecure_host_key_checking",
            "StrictHostKeyChecking must be explicitly set to 'yes'",
        )
    normalized = value.strip().lower()
    if normalized != "yes":
        raise TransportSecurityError(
            "ssh_insecure_host_key_checking",
            f"Refusing insecure StrictHostKeyChecking='{value}'; only 'yes' is permitted",
        )
    return "yes"


def _validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        raise ContractViolation(
            "invalid_session_id",
            "session_id must be a safe non-empty identifier without whitespace or traversal",
        )
    return session_id


class SshTunnelManager:
    """Manages hardened SSH/autossh tunnels with strict host key verification and session isolation."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        host_key_verifier: Optional[Callable[[str, int], Union[str, bool]]] = None,
    ):
        self.config = dict(config)
        target = config.get("ssh_target")
        if target and "@" in target:
            self.user, default_host = target.split("@", 1)
        else:
            self.user = config.get("user", "hydra")
            default_host = target or "localhost"

        self.host: str = config.get("host") or default_host
        self.port: int = int(config.get("port") or config.get("ssh_port", 22))
        self.key_file: Optional[str] = config.get("ssh_key") or config.get("key_file")
        self.local_port: int = int(config.get("local_port") or config.get("local_bind_port", 11435))
        self.local_bind_port: int = self.local_port
        self.remote_port: int = int(config.get("remote_port", 11434))
        self.healthcheck_interval: int = int(config.get("healthcheck_interval_sec", 10))
        self.use_autossh: bool = bool(config.get("use_autossh", True))

        raw_strict = config.get("strict_host_key_checking", "yes")
        self.strict_host_key_checking: str = _validate_strict_host_key_checking(raw_strict)

        raw_known_hosts = config.get("known_hosts_file")
        self.known_hosts_file: Optional[str] = (
            str(Path(os.path.expanduser(str(raw_known_hosts)))) if raw_known_hosts else None
        )
        raw_fp = config.get("expected_host_key_fingerprint")
        self.expected_host_key_fingerprint: Optional[str] = (
            normalize_sha256_fingerprint(raw_fp) if raw_fp else None
        )
        self._host_key_verifier = host_key_verifier

        self._process: Optional[subprocess.Popen] = None
        self._session_lock = threading.Lock()
        self._allocated_ports: set[int] = set()
        self._sessions: Dict[str, SessionTunnelHandle] = {}

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    async def verify_endpoint(self, local_port: Optional[int] = None) -> bool:
        """Test whether the forwarded local port is actively answering HTTP queries."""
        port_to_check = self.local_port if local_port is None else local_port
        try:
            url = f"http://127.0.0.1:{port_to_check}/api/tags"
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                return resp.status_code in (200, 404)
        except Exception:
            return False

    def verify_host_key(
        self,
        observed_fingerprint: Optional[str] = None,
        *,
        known_hosts_file: Optional[Union[str, Path]] = None,
        expected_fingerprint: Optional[str] = None,
    ) -> HostKeyVerificationResult:
        """Verify the remote SSH host key offline against known_hosts and/or expected SHA-256 fingerprint.

        Aborts immediately with TransportSecurityError if strict checking is violated,
        known_hosts is missing/unreadable, the host is absent or revoked, or the host key
        fingerprint diverges from the pinned value. Never performs a silent bypass.
        """
        _validate_strict_host_key_checking(self.strict_host_key_checking)

        kh_path_str = str(known_hosts_file) if known_hosts_file is not None else self.known_hosts_file
        expected_fp = (
            normalize_sha256_fingerprint(expected_fingerprint)
            if expected_fingerprint is not None
            else self.expected_host_key_fingerprint
        )

        probed_fp: Optional[str] = None
        if observed_fingerprint is not None:
            probed_fp = normalize_sha256_fingerprint(observed_fingerprint)
        elif self._host_key_verifier is not None:
            probe_result = self._host_key_verifier(self.host, self.port)
            if probe_result is False:
                raise TransportSecurityError(
                    "ssh_host_key_mismatch",
                    f"Host key verifier rejected SSH target {self.host}:{self.port}",
                )
            if isinstance(probe_result, str):
                probed_fp = normalize_sha256_fingerprint(probe_result)
            elif probe_result is not True:
                raise TransportSecurityError(
                    "ssh_host_key_verification_failed",
                    "Host key verifier returned an unsupported result",
                )

        pinned_fingerprints: set[str] = set()
        resolved_kh: Optional[str] = None
        if kh_path_str is not None:
            kh_path = Path(os.path.expanduser(kh_path_str))
            if not kh_path.is_file():
                raise TransportSecurityError(
                    "ssh_known_hosts_missing",
                    f"Configured known_hosts file does not exist: {kh_path}",
                )
            resolved_kh = str(kh_path)
            try:
                content = kh_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise TransportSecurityError(
                    "ssh_known_hosts_unreadable",
                    f"Unable to read known_hosts file: {exc}",
                ) from exc

            entries = parse_known_hosts(content)
            matching_entries = [
                entry for entry in entries if _entry_matches_target(entry.patterns, self.host, self.port)
            ]
            if not matching_entries:
                raise TransportSecurityError(
                    "ssh_host_key_unknown",
                    f"Host '{self.host}:{self.port}' is not present in known_hosts; refusing unpinned connection",
                )

            revoked = {entry.fingerprint for entry in matching_entries if entry.marker == "@revoked"}
            valid_entries = [entry for entry in matching_entries if entry.marker != "@revoked"]
            pinned_fingerprints = {entry.fingerprint for entry in valid_entries} - revoked

            if not pinned_fingerprints:
                raise TransportSecurityError(
                    "ssh_host_key_revoked",
                    f"Host key for '{self.host}:{self.port}' is revoked in known_hosts",
                )
            if probed_fp is not None and probed_fp in revoked:
                raise TransportSecurityError(
                    "ssh_host_key_revoked",
                    f"Observed host key {probed_fp} for '{self.host}:{self.port}' is revoked",
                )

        if not pinned_fingerprints and expected_fp is None and probed_fp is None and self._host_key_verifier is None:
            raise TransportSecurityError(
                "ssh_known_hosts_required",
                "StrictHostKeyChecking=yes requires known_hosts_file or an explicit host_key_verifier",
            )

        if expected_fp is not None and pinned_fingerprints and expected_fp not in pinned_fingerprints:
            raise TransportSecurityError(
                "ssh_host_key_mismatch",
                f"Host key in known_hosts for '{self.host}:{self.port}' does not match expected {expected_fp}",
            )

        if probed_fp is not None:
            if pinned_fingerprints and probed_fp not in pinned_fingerprints:
                raise TransportSecurityError(
                    "ssh_host_key_mismatch",
                    f"Host key verification failed for '{self.host}:{self.port}': "
                    f"observed {probed_fp} not in known_hosts",
                )
            if expected_fp is not None and probed_fp != expected_fp:
                raise TransportSecurityError(
                    "ssh_host_key_mismatch",
                    f"Host key verification failed for '{self.host}:{self.port}': "
                    f"expected {expected_fp}, got {probed_fp}",
                )
            verified_fp = probed_fp
            source = "probe+known_hosts" if pinned_fingerprints else "probe"
        elif expected_fp is not None:
            verified_fp = expected_fp
            source = "expected+known_hosts" if pinned_fingerprints else "expected"
        elif pinned_fingerprints:
            verified_fp = sorted(pinned_fingerprints)[0]
            source = "known_hosts"
        else:
            raise TransportSecurityError(
                "ssh_host_key_verification_failed",
                f"Unable to establish verified host key fingerprint for '{self.host}:{self.port}'",
            )

        return HostKeyVerificationResult(
            host=self.host,
            port=self.port,
            fingerprint=verified_fp,
            verified_against=source,
            known_hosts_file=resolved_kh,
        )

    def build_ssh_command(self, *, local_port: Optional[int] = None) -> List[str]:
        """Build the hardened SSH/autossh command line with StrictHostKeyChecking=yes."""
        _validate_strict_host_key_checking(self.strict_host_key_checking)
        bind_port = self.local_port if local_port is None else int(local_port)
        binary = "autossh" if (self.use_autossh and shutil.which("autossh")) else "ssh"
        cmd = [
            binary,
            "-o",
            "BatchMode=yes",
            "-o",
            f"ServerAliveInterval={self.healthcheck_interval}",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "StrictHostKeyChecking=yes",
        ]
        if self.known_hosts_file:
            cmd.extend([
                "-o",
                f"UserKnownHostsFile={self.known_hosts_file}",
                "-o",
                "GlobalKnownHostsFile=none",
            ])

        cmd.extend([
            "-N",
            "-L",
            f"127.0.0.1:{bind_port}:127.0.0.1:{self.remote_port}",
            f"{self.user}@{self.host}",
            "-p",
            str(self.port),
        ])

        if self.key_file:
            expanded_key = os.path.expanduser(self.key_file)
            if os.path.isfile(expanded_key):
                cmd.extend(["-o", "IdentitiesOnly=yes", "-i", expanded_key])
        return cmd

    def allocate_session_port(
        self,
        session_id: str,
        *,
        preferred_port: Optional[int] = None,
    ) -> int:
        """Allocate a distinct local loopback port for a concurrent session."""
        sid = _validate_session_id(session_id)
        with self._session_lock:
            existing = self._sessions.get(sid)
            if existing is not None and existing.status != "stopped":
                if preferred_port is not None and preferred_port != existing.local_port:
                    raise ContractViolation(
                        "port_conflict",
                        f"Session '{sid}' already holds local port {existing.local_port}",
                    )
                return existing.local_port

            if preferred_port is not None:
                port = int(preferred_port)
                if port < 1 or port > 65535:
                    raise ContractViolation("invalid_port", f"Port out of range: {port}")
                if port in self._allocated_ports:
                    raise ContractViolation(
                        "port_conflict",
                        f"Local port {port} is already allocated to another active session",
                    )
                self._allocated_ports.add(port)
                return port

            port = self._pick_unused_loopback_port_locked()
            self._allocated_ports.add(port)
            return port

    def _pick_unused_loopback_port_locked(self) -> int:
        for _ in range(32):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("127.0.0.1", 0))
                    candidate = int(sock.getsockname()[1])
                if candidate not in self._allocated_ports and candidate > 0:
                    return candidate
            except OSError:
                break
        for candidate in range(20000, 60000):
            if candidate not in self._allocated_ports:
                return candidate
        raise ContractViolation("port_exhausted", "No free local port available for SSH session")

    def open_session(
        self,
        session_id: str,
        *,
        observed_fingerprint: Optional[str] = None,
        preferred_port: Optional[int] = None,
        process_factory: Optional[Callable[[List[str], SessionTunnelHandle], Any]] = None,
    ) -> SessionTunnelHandle:
        """Verify host key, allocate an isolated port, and register an isolated session handle."""
        sid = _validate_session_id(session_id)
        self.verify_host_key(observed_fingerprint=observed_fingerprint)
        local_port = self.allocate_session_port(sid, preferred_port=preferred_port)

        with self._session_lock:
            handle = self._sessions.get(sid)
            if handle is None or handle.status == "stopped":
                handle = SessionTunnelHandle(
                    session_id=sid,
                    host=self.host,
                    port=self.port,
                    local_port=local_port,
                    remote_port=self.remote_port,
                    status="allocated",
                )
                self._sessions[sid] = handle

        if process_factory is not None:
            cmd = self.build_ssh_command(local_port=local_port)
            try:
                handle.process = process_factory(cmd, handle)
                handle.status = "running"
            except Exception as exc:
                handle.append_stderr(str(exc))
                handle.status = "failed"
                self.close_session(sid, keep_logs=True)
                raise
        return handle

    def get_session(self, session_id: str) -> SessionTunnelHandle:
        sid = _validate_session_id(session_id)
        with self._session_lock:
            handle = self._sessions.get(sid)
        if handle is None:
            raise ContractViolation("resource_not_found", f"SSH session '{sid}' does not exist")
        return handle

    def append_session_output(
        self,
        session_id: str,
        *,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        handle = self.get_session(session_id)
        if stdout:
            handle.append_stdout(stdout)
        if stderr:
            handle.append_stderr(stderr)

    def get_session_logs(self, session_id: str) -> Dict[str, str]:
        return self.get_session(session_id).get_logs()

    def close_session(self, session_id: str, *, keep_logs: bool = True) -> None:
        sid = _validate_session_id(session_id)
        with self._session_lock:
            handle = self._sessions.get(sid)
            if handle is None:
                return
            proc = handle.process
            if proc is not None and hasattr(proc, "poll") and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            handle.process = None
            handle.status = "stopped"
            self._allocated_ports.discard(handle.local_port)
            if not keep_logs:
                self._sessions.pop(sid, None)

    def start_tunnel(self, *, observed_fingerprint: Optional[str] = None) -> bool:
        """Verify host key and launch the hardened SSH forwarding process."""
        if self.is_running():
            logger.info("SSH tunnel already running")
            return True

        self.verify_host_key(observed_fingerprint=observed_fingerprint)
        cmd = self.build_ssh_command(local_port=self.local_port)
        logger.info(_redact_text(f"Starting SSH tunnel: {' '.join(cmd)}"))
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True
        except Exception as exc:
            logger.error(_redact_text(f"Failed to start SSH tunnel: {exc}"))
            return False

    def stop_tunnel(self) -> None:
        """Stop the active tunnel process and any open session tunnels."""
        if self._process and self._process.poll() is None:
            logger.info("Terminating SSH tunnel process")
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        with self._session_lock:
            session_ids = list(self._sessions.keys())
        for sid in session_ids:
            self.close_session(sid, keep_logs=True)
