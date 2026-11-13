"""Global QuickOpen search index and honest per-host capability matrix (M5 / T31)."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from hydra_orch.bridge.pty_runner import detect_pty_backend
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.redaction import REDACTED, redact, redact_text
from hydra_orch.model import ContractViolation

_SCOPE_ALIASES: Dict[str, str] = {
    "all": "all",
    "area": "areas",
    "areas": "areas",
    "workspace": "area_workspaces",
    "workspaces": "area_workspaces",
    "area_workspaces": "area_workspaces",
    "project": "projects",
    "projects": "projects",
    "run": "runs",
    "runs": "runs",
    "session": "sessions",
    "sessions": "sessions",
    "artifact": "artifacts",
    "artifacts": "artifacts",
}

_ALL_TABLES: tuple[str, ...] = (
    "areas",
    "area_workspaces",
    "projects",
    "runs",
    "sessions",
    "artifacts",
)


def _escape_like(term: str) -> str:
    """Escape SQLite LIKE pattern metacharacters while keeping search deterministic."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_json_obj(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _sanitize_result_item(item: Dict[str, Any], query_lower: str) -> Optional[Dict[str, Any]]:
    """Apply deterministic redaction and drop empty or secret-only search hits."""
    clean = redact(item)
    title = str(clean.get("title") or "").strip()
    subtitle = str(clean.get("subtitle") or "").strip()
    if not title or title == REDACTED:
        return None
    haystack = " ".join(
        str(clean.get(field) or "")
        for field in ("id", "title", "subtitle", "workspace_id", "project_id", "run_id", "session_id")
    ).lower()
    if query_lower not in haystack:
        return None
    clean["title"] = title
    clean["subtitle"] = subtitle
    return clean


class SearchService:
    """Parameterized, redaction-aware SQLite QuickOpen search across control-plane entities."""

    def __init__(self, store: ExecutionStore, *, default_host_id: str = "local") -> None:
        self.store = store
        self.default_host_id = default_host_id

    async def search(
        self,
        query: str,
        *,
        scope: Optional[str] = None,
        host_id: str = "local",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search areas, workspaces, projects, runs, sessions, and artifacts without SQL injection or secret leaks."""
        if not isinstance(query, str) or "\x00" in query:
            raise ContractViolation("invalid_search_query", "Search query must be a clean string")
        if not isinstance(host_id, str) or not host_id.strip() or "\x00" in host_id:
            raise ContractViolation("invalid_search_host", "host_id must be a non-empty string")
        if type(limit) is not int or limit < 1 or limit > 200:
            raise ContractViolation("invalid_search_limit", "Search limit must be an integer between 1 and 200")

        norm_scope: Optional[str] = None
        if scope is not None:
            key = str(scope).strip().lower()
            norm_scope = _SCOPE_ALIASES.get(key)
            if norm_scope is None:
                raise ContractViolation("invalid_search_scope", f"Unsupported search scope: '{scope}'")

        cleaned_query = query.strip()
        if not cleaned_query:
            return []
        if redact_text(cleaned_query) != cleaned_query:
            return []

        tables = _ALL_TABLES if norm_scope in (None, "all") else (norm_scope,)
        like_pattern = f"%{_escape_like(cleaned_query)}%"
        query_lower = cleaned_query.lower()

        await self.store.initialize()
        results: List[Dict[str, Any]] = []

        async with self.store._connect() as db:
            if "areas" in tables and host_id == self.default_host_id and len(results) < limit:
                rows = await (
                    await db.execute(
                        """
                        SELECT id, name, description
                        FROM areas
                        WHERE id LIKE ? ESCAPE '\\'
                           OR name LIKE ? ESCAPE '\\'
                           OR COALESCE(description, '') LIKE ? ESCAPE '\\'
                        ORDER BY created_at DESC, id ASC
                        LIMIT ?
                        """,
                        (like_pattern, like_pattern, like_pattern, limit),
                    )
                ).fetchall()
                for row in rows:
                    item = _sanitize_result_item(
                        {
                            "kind": "area",
                            "id": row["id"],
                            "title": row["name"],
                            "subtitle": row["description"] or f"Area ({row['id'][:8]})",
                            "host_id": self.default_host_id,
                            "workspace_id": None,
                            "project_id": None,
                            "run_id": None,
                            "session_id": None,
                            "tab_hint": "workspace",
                        },
                        query_lower,
                    )
                    if item is not None:
                        results.append(item)
                        if len(results) >= limit:
                            return results

            if "area_workspaces" in tables and host_id == self.default_host_id and len(results) < limit:
                rows = await (
                    await db.execute(
                        """
                        SELECT id, area_id, name, status
                        FROM area_workspaces
                        WHERE id LIKE ? ESCAPE '\\'
                           OR name LIKE ? ESCAPE '\\'
                           OR status LIKE ? ESCAPE '\\'
                        ORDER BY updated_at DESC, id ASC
                        LIMIT ?
                        """,
                        (like_pattern, like_pattern, like_pattern, limit),
                    )
                ).fetchall()
                for row in rows:
                    item = _sanitize_result_item(
                        {
                            "kind": "workspace",
                            "id": row["id"],
                            "title": row["name"],
                            "subtitle": f"Workspace · {row['status']}",
                            "host_id": self.default_host_id,
                            "workspace_id": row["id"],
                            "project_id": None,
                            "run_id": None,
                            "session_id": None,
                            "tab_hint": "workspace",
                        },
                        query_lower,
                    )
                    if item is not None:
                        results.append(item)
                        if len(results) >= limit:
                            return results

            if "projects" in tables and len(results) < limit:
                rows = await (
                    await db.execute(
                        """
                        SELECT id, workspace_id, name, canonical_root, base_branch, metadata_json
                        FROM projects
                        WHERE id LIKE ? ESCAPE '\\'
                           OR name LIKE ? ESCAPE '\\'
                           OR canonical_root LIKE ? ESCAPE '\\'
                           OR COALESCE(base_branch, '') LIKE ? ESCAPE '\\'
                        ORDER BY updated_at DESC, id ASC
                        LIMIT ?
                        """,
                        (like_pattern, like_pattern, like_pattern, like_pattern, limit),
                    )
                ).fetchall()
                for row in rows:
                    meta = _parse_json_obj(row["metadata_json"])
                    row_host = str(meta.get("host_id") or self.default_host_id)
                    if row_host != host_id:
                        continue
                    item = _sanitize_result_item(
                        {
                            "kind": "project",
                            "id": row["id"],
                            "title": row["name"],
                            "subtitle": row["base_branch"] or row["canonical_root"],
                            "host_id": row_host,
                            "workspace_id": row["workspace_id"],
                            "project_id": row["id"],
                            "run_id": None,
                            "session_id": None,
                            "tab_hint": "workspace",
                        },
                        query_lower,
                    )
                    if item is not None:
                        results.append(item)
                        if len(results) >= limit:
                            return results

            if "runs" in tables and len(results) < limit:
                rows = await (
                    await db.execute(
                        """
                        SELECT r.id, r.project_id, r.status, r.spec_json,
                               p.name AS project_name, p.workspace_id, p.metadata_json
                        FROM runs r
                        LEFT JOIN projects p ON r.project_id = p.id
                        WHERE r.id LIKE ? ESCAPE '\\'
                           OR r.status LIKE ? ESCAPE '\\'
                           OR COALESCE(json_extract(r.spec_json, '$.objective'), '') LIKE ? ESCAPE '\\'
                           OR COALESCE(p.name, '') LIKE ? ESCAPE '\\'
                        ORDER BY r.updated_at DESC, r.id ASC
                        LIMIT ?
                        """,
                        (like_pattern, like_pattern, like_pattern, like_pattern, limit),
                    )
                ).fetchall()
                for row in rows:
                    meta = _parse_json_obj(row["metadata_json"])
                    row_host = str(meta.get("host_id") or self.default_host_id)
                    if row_host != host_id:
                        continue
                    spec = _parse_json_obj(row["spec_json"])
                    objective = str(spec.get("objective") or "").strip() or f"Run {row['id']}"
                    proj_label = row["project_name"] or row["project_id"]
                    item = _sanitize_result_item(
                        {
                            "kind": "run",
                            "id": row["id"],
                            "title": objective,
                            "subtitle": f"{proj_label} · {row['status']}",
                            "host_id": row_host,
                            "workspace_id": row["workspace_id"],
                            "project_id": row["project_id"],
                            "run_id": row["id"],
                            "session_id": None,
                            "tab_hint": "chat",
                        },
                        query_lower,
                    )
                    if item is not None:
                        results.append(item)
                        if len(results) >= limit:
                            return results

            if "sessions" in tables and len(results) < limit:
                rows = await (
                    await db.execute(
                        """
                        SELECT s.id, s.run_id, s.origin_ref, s.agent_ref, s.state,
                               r.project_id, p.workspace_id, p.metadata_json
                        FROM sessions s
                        LEFT JOIN runs r ON s.run_id = r.id
                        LEFT JOIN projects p ON r.project_id = p.id
                        WHERE s.id LIKE ? ESCAPE '\\'
                           OR COALESCE(s.origin_ref, '') LIKE ? ESCAPE '\\'
                           OR COALESCE(s.agent_ref, '') LIKE ? ESCAPE '\\'
                           OR s.state LIKE ? ESCAPE '\\'
                        ORDER BY s.created_at DESC, s.id ASC
                        LIMIT ?
                        """,
                        (like_pattern, like_pattern, like_pattern, like_pattern, limit),
                    )
                ).fetchall()
                for row in rows:
                    meta = _parse_json_obj(row["metadata_json"])
                    row_host = str(meta.get("host_id") or self.default_host_id)
                    if row_host != host_id:
                        continue
                    origin_ref = str(row["origin_ref"] or "").strip()
                    agent_ref = str(row["agent_ref"] or "").strip()
                    title = origin_ref or agent_ref or f"Session {row['id']}"
                    tab_hint = "terminal" if origin_ref.lower().startswith(("pty", "terminal")) else "chat"
                    item = _sanitize_result_item(
                        {
                            "kind": "session",
                            "id": row["id"],
                            "title": title,
                            "subtitle": f"Session · {row['state']}",
                            "host_id": row_host,
                            "workspace_id": row["workspace_id"],
                            "project_id": row["project_id"],
                            "run_id": row["run_id"],
                            "session_id": row["id"],
                            "tab_hint": tab_hint,
                        },
                        query_lower,
                    )
                    if item is not None:
                        results.append(item)
                        if len(results) >= limit:
                            return results

            if "artifacts" in tables and len(results) < limit:
                rows = await (
                    await db.execute(
                        """
                        SELECT a.id, a.run_id, a.relative_path, a.kind,
                               r.project_id, p.workspace_id, p.metadata_json
                        FROM artifacts a
                        LEFT JOIN runs r ON a.run_id = r.id
                        LEFT JOIN projects p ON r.project_id = p.id
                        WHERE a.id LIKE ? ESCAPE '\\'
                           OR a.relative_path LIKE ? ESCAPE '\\'
                           OR a.kind LIKE ? ESCAPE '\\'
                        ORDER BY a.created_at DESC, a.id ASC
                        LIMIT ?
                        """,
                        (like_pattern, like_pattern, like_pattern, limit),
                    )
                ).fetchall()
                for row in rows:
                    meta = _parse_json_obj(row["metadata_json"])
                    row_host = str(meta.get("host_id") or self.default_host_id)
                    if row_host != host_id:
                        continue
                    rel = str(row["relative_path"] or "")
                    title = Path(rel).name or rel
                    item = _sanitize_result_item(
                        {
                            "kind": "artifact",
                            "id": row["id"],
                            "title": title,
                            "subtitle": f"{row['kind']} · {rel}",
                            "host_id": row_host,
                            "workspace_id": row["workspace_id"],
                            "project_id": row["project_id"],
                            "run_id": row["run_id"],
                            "session_id": None,
                            "tab_hint": "artifact",
                        },
                        query_lower,
                    )
                    if item is not None:
                        results.append(item)
                        if len(results) >= limit:
                            return results

        return results


def _extract_capability_names(raw_caps: Any) -> Set[str]:
    if isinstance(raw_caps, dict):
        return {str(k) for k, v in raw_caps.items() if v}
    if isinstance(raw_caps, (list, tuple, set, frozenset)):
        return {str(item) for item in raw_caps if item}
    return set()


def _cfg_flag(config: Any, path: Sequence[str], default: Any = False) -> Any:
    current = config
    for key in path:
        if current is None:
            return default
        if isinstance(current, Mapping):
            current = current.get(key, None)
        else:
            current = getattr(current, key, None)
    return default if current is None else current


def build_host_capabilities(
    config: Any = None,
    transports: Iterable[Any] = (),
) -> Dict[str, Any]:
    """Build an honest capability map for `local` and all registered transports.

    Uncertified bridges (`F06` voice duplex, `F07` computer_use, mobile_emulator)
    default explicitly to `status="unavailable"`, `certified=False`,
    `reason="uncertified_parking_lot_bridge"`.
    """
    backend_kind, pty_certified = detect_pty_backend()
    system_name = platform.system()

    local_capabilities: Dict[str, Dict[str, Any]] = {
        "pty": {
            "status": "available" if pty_certified else "degraded",
            "supported": True,
            "certified": pty_certified,
            "backend_kind": backend_kind,
            "platform": system_name,
            "reason": None if pty_certified else "windows_conpty_uncertified_using_pipe_bridge",
        },
        "attachments": {
            "status": "available",
            "supported": True,
            "certified": True,
            "max_bytes": 10 * 1024 * 1024,
            "remote_confirm_required": True,
        },
        "quickopen": {
            "status": "available",
            "supported": True,
            "certified": True,
        },
        "preview": {
            "status": "available",
            "supported": True,
            "certified": True,
            "max_bytes": 512 * 1024,
            "supported_kinds": ["markdown", "text", "diff", "image", "pdf"],
        },
        "scheduler": {
            "status": "available",
            "supported": True,
            "certified": True,
        },
        "dictation_stt": {
            "status": "available",
            "supported": True,
            "certified": False,
            "available_modes": ["browser_optional_text_draft"],
            "duplex_voice_enabled": False,
            "requires_review_before_send": True,
        },
        "mobile_emulator": {
            "status": "unavailable",
            "supported": False,
            "certified": False,
            "reason": "uncertified_parking_lot_bridge",
            "platforms": {"ios": "unavailable", "android": "unavailable"},
        },
        "computer_use": {
            "status": "unavailable",
            "supported": False,
            "certified": False,
            "reason": "uncertified_parking_lot_bridge",
        },
    }

    hosts: Dict[str, Dict[str, Any]] = {
        "local": {
            "host_id": "local",
            "transport_type": "local",
            "platform": system_name,
            "certified": True,
            "capabilities": local_capabilities,
        }
    }

    for transport in transports or ():
        if isinstance(transport, Mapping):
            t_id = str(transport.get("transport_id") or transport.get("id") or "")
            t_type = str(transport.get("type") or "remote")
            target_identity = str(transport.get("target_identity") or "")
            is_certified = bool(transport.get("is_certified", False))
            raw_caps = transport.get("capabilities", ())
        else:
            t_id = str(getattr(transport, "transport_id", getattr(transport, "id", "")))
            t_type = str(getattr(transport, "type", "remote"))
            target_identity = str(getattr(transport, "target_identity", ""))
            is_certified = bool(getattr(transport, "is_certified", False))
            raw_caps = getattr(transport, "capabilities", ())

        if not t_id:
            continue
        cap_names = _extract_capability_names(raw_caps)

        has_mobile = is_certified and ("mobile_emulator" in cap_names)
        has_computer_use = is_certified and ("computer_use" in cap_names)
        has_pty = is_certified and (t_type == "local" or "pty" in cap_names or "remote_exec" in cap_names)

        if t_type == "local" and is_certified:
            if has_mobile:
                local_capabilities["mobile_emulator"] = {
                    "status": "available",
                    "supported": True,
                    "certified": True,
                    "transport_id": t_id,
                }
            if has_computer_use:
                local_capabilities["computer_use"] = {
                    "status": "available",
                    "supported": True,
                    "certified": True,
                    "transport_id": t_id,
                }

        hosts[t_id] = {
            "host_id": t_id,
            "transport_id": t_id,
            "transport_type": t_type,
            "target_identity": redact_text(target_identity),
            "certified": is_certified,
            "capabilities": {
                "pty": {
                    "status": "available" if has_pty else "unavailable",
                    "supported": has_pty,
                    "certified": has_pty,
                    "backend_kind": backend_kind if t_type == "local" else f"{t_type}_bridge",
                    "reason": None if has_pty else ("transport_uncertified" if not is_certified else "pty_capability_not_declared"),
                },
                "attachments": {
                    "status": "available" if is_certified else "unavailable",
                    "supported": is_certified,
                    "certified": is_certified,
                    "remote_confirm_required": t_type != "local",
                    "reason": None if is_certified else "transport_uncertified",
                },
                "quickopen": {
                    "status": "available" if is_certified else "unavailable",
                    "supported": is_certified,
                    "certified": is_certified,
                    "reason": None if is_certified else "transport_uncertified",
                },
                "preview": {
                    "status": "available" if is_certified else "unavailable",
                    "supported": is_certified,
                    "certified": is_certified,
                    "reason": None if is_certified else "transport_uncertified",
                },
                "scheduler": {
                    "status": "available" if (is_certified and "scheduler" in cap_names) else "unavailable",
                    "supported": is_certified and "scheduler" in cap_names,
                    "certified": is_certified and "scheduler" in cap_names,
                    "reason": None if (is_certified and "scheduler" in cap_names) else "local_control_plane_only",
                },
                "dictation_stt": {
                    "status": "unavailable",
                    "supported": False,
                    "certified": False,
                    "available_modes": ["browser_optional_text_draft"],
                    "duplex_voice_enabled": False,
                },
                "mobile_emulator": (
                    {
                        "status": "available",
                        "supported": True,
                        "certified": True,
                        "transport_id": t_id,
                    }
                    if has_mobile
                    else {
                        "status": "unavailable",
                        "supported": False,
                        "certified": False,
                        "reason": "uncertified_parking_lot_bridge",
                    }
                ),
                "computer_use": (
                    {
                        "status": "available",
                        "supported": True,
                        "certified": True,
                        "transport_id": t_id,
                    }
                    if has_computer_use
                    else {
                        "status": "unavailable",
                        "supported": False,
                        "certified": False,
                        "reason": "uncertified_parking_lot_bridge",
                    }
                ),
            },
        }

    return {
        "schema_version": "1.0",
        "default_host": "local",
        "platform": system_name,
        "integrations": {
            "omniroute_enabled": bool(_cfg_flag(config, ("omniroute", "enabled"), False)),
            "omniroute_connection_mode": str(_cfg_flag(config, ("omniroute", "connection_mode"), "disabled")),
            "ssh_gpu_enabled": bool(_cfg_flag(config, ("remote_ssh_gpu", "enabled"), False)),
            "visual_interface_enabled": bool(_cfg_flag(config, ("visual_interface", "enabled"), False)),
        },
        "hosts": hosts,
    }


__all__ = [
    "SearchService",
    "build_host_capabilities",
]
