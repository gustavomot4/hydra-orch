"""OmniRoute Gateway client for OAuth subscriptions and 5h quota monitoring."""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union
from urllib.parse import urlsplit

import httpx

from hydra_orch.config import normalize_gemini_argon_target
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)

_QUOTA_PROVIDERS = ("claude_pro", "chatgpt_plus", "gemini_pro")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SENSITIVE_ACCOUNT_KEYS = {
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "providerspecificdata",
    "email",
    "displayname",
}
_INACTIVE_STATUSES = {
    "expired",
    "invalid",
    "error",
    "disabled",
    "revoked",
    "inactive",
    "unauthorized",
}
_CANONICAL_QUOTA_KEY: Dict[str, str] = {
    "claude_pro": "claude_pro",
    "claude": "claude_pro",
    "anthropic": "claude_pro",
    "claude-code": "claude_pro",
    "claude_code": "claude_pro",
    "chatgpt_plus": "chatgpt_plus",
    "codex": "chatgpt_plus",
    "openai": "chatgpt_plus",
    "chatgpt": "chatgpt_plus",
    "gemini_pro": "gemini_pro",
    "gemini": "gemini_pro",
    "agy": "gemini_pro",
    "antigravity": "gemini_pro",
    "google": "gemini_pro",
    "gemini-cli": "gemini_pro",
}


def _scrub_emails(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    if isinstance(value, list):
        return [_scrub_emails(item) for item in value]
    if isinstance(value, dict):
        return {k: _scrub_emails(v) for k, v in value.items()}
    return value


def _redact(value: Any) -> Any:
    # core.__init__ eagerly imports router -> omniroute_client; defer core.redaction import.
    from hydra_orch.core.redaction import redact

    return _scrub_emails(redact(value))


def _origin_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url.rstrip("/")


def _canonical_quota_key(provider: str) -> str:
    norm = provider.strip().lower()
    return _CANONICAL_QUOTA_KEY.get(norm, norm)


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_reset(value: Any, now: datetime) -> Tuple[Optional[str], Optional[int]]:
    dt = _parse_iso_datetime(value)
    if dt is None:
        return None, None
    return dt.isoformat(), max(0, int((dt - now).total_seconds()))


def _unknown_quota_payload() -> Dict[str, Any]:
    return {
        "status": "unknown",
        **{
            name: {"status": "unknown", "remaining_percent": None, "resets_in_seconds": None}
            for name in _QUOTA_PROVIDERS
        },
    }


def _parse_quota_metrics(
    entry: Dict[str, Any], *, default_status: str = "observed"
) -> Optional[Tuple[str, Union[int, float], Optional[Union[int, float]]]]:
    percent = entry.get("remaining_percent")
    status = entry.get("status", default_status)
    if (
        isinstance(percent, bool)
        or not isinstance(percent, (int, float))
        or not math.isfinite(percent)
        or not 0 <= percent <= 100
        or status not in {"observed", "stale"}
    ):
        return None
    reset = entry.get("resets_in_seconds")
    if isinstance(reset, bool) or not isinstance(reset, (int, float)) or not math.isfinite(reset) or reset < 0:
        reset = None
    return status, percent, reset


def _strip_sensitive_account_fields(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: v
        for k, v in entry.items()
        if str(k).strip().lower().replace("-", "_") not in _SENSITIVE_ACCOUNT_KEYS
    }


def _is_entry_inactive(entry: Dict[str, Any]) -> bool:
    if entry.get("isActive") is False or entry.get("active") is False:
        return True
    for key in ("testStatus", "test_status", "tokenStatus", "token_status"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip().lower() in _INACTIVE_STATUSES:
            return True
    if entry.get("errorCode"):
        return True
    return False


def _parse_provider_limits_cache(
    cache_entry: Dict[str, Any],
    now: datetime,
    now_iso: str,
) -> Optional[Dict[str, Any]]:
    """Extract honest quota telemetry from one /api/usage/provider-limits cache entry."""
    if not isinstance(cache_entry, dict) or _is_entry_inactive(cache_entry):
        return None
    quotas = cache_entry.get("quotas")
    if not isinstance(quotas, dict) or not quotas:
        return None

    # Tuple layout: (pct, is_short_window, resets_in_seconds, reset_at_iso, window_name)
    finite_entries: List[Tuple[float, bool, Optional[int], Optional[str], str]] = []
    saw_unlimited = False

    for raw_name, raw_window in quotas.items():
        if not isinstance(raw_window, dict):
            continue
        win_name = str(raw_name).strip().lower()
        pct: Optional[float] = None
        rem_pct = raw_window.get("remainingPercentage")
        if rem_pct is None:
            rem_pct = raw_window.get("remaining_percent")
        if _is_finite_number(rem_pct):
            cand = float(rem_pct)
            if 0.0 <= cand <= 100.0:
                pct = cand
        if pct is None:
            total = raw_window.get("total")
            remaining = raw_window.get("remaining")
            used = raw_window.get("used")
            if _is_finite_number(total) and float(total) > 0:
                total_f = float(total)
                if _is_finite_number(remaining):
                    pct = max(0.0, min(100.0, (float(remaining) / total_f) * 100.0))
                elif _is_finite_number(used):
                    pct = max(0.0, min(100.0, ((total_f - float(used)) / total_f) * 100.0))

        if pct is None:
            if raw_window.get("unlimited") is True:
                saw_unlimited = True
            continue

        reset_at_iso, resets_in = _parse_iso_reset(
            raw_window.get("resetAt") or raw_window.get("reset_at"), now
        )
        win_sec = raw_window.get("windowSeconds")
        is_short = (
            win_name in {"session", "5h", "five_hour"}
            or (_is_finite_number(win_sec) and 0 < float(win_sec) <= 28800.0)
        )
        finite_entries.append((round(pct, 2), is_short, resets_in, reset_at_iso, win_name))

    if not finite_entries:
        if saw_unlimited and not cache_entry.get("error"):
            fetched_dt = _parse_iso_datetime(cache_entry.get("fetchedAt") or cache_entry.get("updatedAt"))
            return {
                "status": "observed",
                "remaining_percent": 100.0,
                "resets_in_seconds": None,
                "observed_at": fetched_dt.isoformat() if fetched_dt else now_iso,
                "source": "omniroute:provider_limits_api",
            }
        return None

    exhausted = [item for item in finite_entries if item[0] <= 0.0]
    short_entries = [item for item in finite_entries if item[1]]
    if exhausted:
        # Exhausted finite quota blocks usage even if another window still has headroom.
        chosen = min(exhausted, key=lambda item: (0 if item[1] else 1, item[2] if item[2] is not None else 10**9))
    elif short_entries:
        # Prefer the 5h/session window over longer weekly limits when capacity remains.
        chosen = min(short_entries, key=lambda item: (item[0], item[2] if item[2] is not None else 10**9))
    else:
        chosen = min(finite_entries, key=lambda item: (item[0], item[2] if item[2] is not None else 10**9))

    chosen_pct, _, chosen_resets_in, chosen_reset_at, _ = chosen
    fetched_dt = _parse_iso_datetime(cache_entry.get("fetchedAt") or cache_entry.get("updatedAt"))
    result: Dict[str, Any] = {
        "status": "observed",
        "remaining_percent": chosen_pct,
        "resets_in_seconds": chosen_resets_in,
        "observed_at": fetched_dt.isoformat() if fetched_dt else now_iso,
        "source": "omniroute:provider_limits_api",
    }
    if chosen_reset_at is not None:
        result["reset_at"] = chosen_reset_at
    return result


def _parse_real_quota_provider_item(
    entry: Dict[str, Any],
    now: datetime,
    now_iso: str,
) -> Optional[Dict[str, Any]]:
    """Parse one item from OmniRoute v3 /api/usage/quota {"providers": [...]}, rejecting placeholders."""
    if not isinstance(entry, dict) or _is_entry_inactive(entry) or entry.get("error"):
        return None

    raw_pct = entry.get("percentRemaining")
    if raw_pct is None:
        raw_pct = entry.get("remaining_percent")
    if not _is_finite_number(raw_pct):
        return None
    pct = float(raw_pct)
    if not 0.0 <= pct <= 100.0:
        return None

    quota_total = entry.get("quotaTotal")
    quota_used = entry.get("quotaUsed")
    raw_reset = entry.get("resetAt") or entry.get("reset_at")
    reset_at_iso, resets_in = _parse_iso_reset(raw_reset, now)
    if resets_in is None and _is_finite_number(entry.get("resets_in_seconds")) and float(entry["resets_in_seconds"]) >= 0:
        resets_in = int(float(entry["resets_in_seconds"]))

    # OmniRoute v3 /api/usage/quota emits synthetic quotaTotal=null, quotaUsed=0, percentRemaining=100,
    # resetAt=null for unmeasured or expired providers. Treat uncorroborated placeholders as unknown.
    has_total = _is_finite_number(quota_total) and float(quota_total) > 0
    has_used = _is_finite_number(quota_used) and float(quota_used) > 0
    has_measurement = has_total or has_used or reset_at_iso is not None or pct < 100.0
    if not has_measurement:
        return None

    result: Dict[str, Any] = {
        "status": "observed",
        "remaining_percent": round(pct, 2),
        "resets_in_seconds": resets_in,
        "observed_at": now_iso,
        "source": "omniroute:quota_api",
    }
    if reset_at_iso is not None:
        result["reset_at"] = reset_at_iso
    return result


class OmniRouteClient:
    """HTTP and SSE client connecting to local OmniRoute daemon (:20128)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:20128/v1",
        quota_api_url: str = "http://127.0.0.1:20128/api/usage/quota",
        timeout: float = 120.0,
        enabled: bool = True,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = "OMNIROUTE_API_KEY",
    ):
        self.base_url = base_url.rstrip("/")
        self.quota_api_url = quota_api_url
        self.timeout = timeout
        self.enabled = enabled
        self._transport = transport
        self._explicit_api_key = api_key
        self.api_key_env = api_key_env
        self._last_quota: Optional[Dict[str, Any]] = None
        self._last_connection_quotas: Dict[str, Dict[str, Any]] = {}

    @property
    def _health_url(self) -> str:
        return f"{_origin_url(self.base_url)}/api/health"

    @property
    def _providers_url(self) -> str:
        return f"{_origin_url(self.base_url)}/api/providers"

    @property
    def _provider_limits_url(self) -> str:
        stripped = self.quota_api_url.rstrip("/")
        if stripped.endswith("/api/usage/quota"):
            return f"{stripped[:-len('/quota')]}/provider-limits"
        return f"{_origin_url(self.quota_api_url)}/api/usage/provider-limits"

    def _resolve_api_key(self) -> Optional[str]:
        if isinstance(self._explicit_api_key, str) and self._explicit_api_key.strip():
            return self._explicit_api_key.strip()
        if isinstance(self.api_key_env, str) and self.api_key_env.strip():
            env_val = os.environ.get(self.api_key_env.strip())
            if isinstance(env_val, str) and env_val.strip():
                return env_val.strip()
        return None

    def _build_client(self, timeout: Union[float, httpx.Timeout]) -> httpx.AsyncClient:
        headers: Dict[str, str] = {}
        token = self._resolve_api_key()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        kwargs: Dict[str, Any] = {"timeout": timeout, "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def normalize_model(model: str) -> str:
        """Normalize model IDs before sending to OmniRoute (e.g. Gemini 4 Argon tiers)."""
        normalized = normalize_gemini_argon_target(model.strip())
        if normalized == "antigravity/gemini-4-argon-high":
            return "agy/gemini-4-argon-high"
        return normalized

    async def is_available(self) -> bool:
        """Check if OmniRoute daemon is active, authenticated, and listening."""
        if not self.enabled:
            return False
        try:
            async with self._build_client(httpx.Timeout(8.0, connect=2.0)) as client:
                resp = await client.get(f"{self.base_url}/models")
                if resp.status_code == 200:
                    return True
                if resp.status_code in {401, 403}:
                    return False
                if resp.status_code == 503:
                    # Cold catalog warmup in OmniRoute returns 503 catalog_build_timeout while /api/health is ok.
                    health = await client.get(self._health_url)
                    if health.status_code == 200:
                        body = health.json()
                        return isinstance(body, dict) and str(body.get("status", "")).lower() in {"ok", "healthy"}
                return False
        except Exception:
            return False

    async def _fetch_provider_limits_map(
        self, client: httpx.AsyncClient, now: datetime, now_iso: str
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        """Fetch per-connection limit telemetry from /api/usage/provider-limits."""
        by_connection: Dict[str, Dict[str, Any]] = {}
        conn_providers: Dict[str, str] = {}
        try:
            resp = await client.get(self._provider_limits_url)
            if resp.status_code != 200:
                return by_connection, conn_providers
            payload = resp.json()
        except Exception:
            return by_connection, conn_providers

        caches = payload.get("caches") if isinstance(payload, dict) else None
        if not isinstance(caches, dict):
            return by_connection, conn_providers

        for conn_id, cache_entry in caches.items():
            if not isinstance(conn_id, str) or not conn_id.strip() or not isinstance(cache_entry, dict):
                continue
            cid = conn_id.strip()
            raw_provider = cache_entry.get("provider")
            if isinstance(raw_provider, str) and raw_provider.strip():
                conn_providers[cid] = raw_provider.strip().lower()
            parsed = _parse_provider_limits_cache(cache_entry, now, now_iso)
            if parsed is not None:
                by_connection[cid] = parsed
        return by_connection, conn_providers

    @staticmethod
    def _merge_canonical_quota(
        target: Dict[str, Dict[str, Any]], canonical_key: str, candidate: Dict[str, Any]
    ) -> None:
        existing = target.get(canonical_key)
        if existing is None or existing.get("status") == "unknown":
            target[canonical_key] = copy.deepcopy(candidate)
            return
        cur_pct = existing.get("remaining_percent")
        new_pct = candidate.get("remaining_percent")
        if _is_finite_number(new_pct) and (not _is_finite_number(cur_pct) or float(new_pct) > float(cur_pct)):
            # Across multiple active connections for the same canonical provider, report usable headroom.
            target[canonical_key] = copy.deepcopy(candidate)

    async def get_quota_status(self) -> Dict[str, Any]:
        """Fetch current 5h quota windows and token usage from OmniRoute.

        Conforms to RT09 / RT17 (GAP A03): When OmniRoute is offline or an account is
        expired/unmeasured, marks status as 'unknown' rather than fabricating 100% availability.
        """
        unknown = _unknown_quota_payload()
        if not self.enabled:
            self._last_connection_quotas = {}
            return unknown
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        try:
            async with self._build_client(httpx.Timeout(6.0, connect=2.0)) as client:
                resp = await client.get(self.quota_api_url)
                data: Any = resp.json() if resp.status_code == 200 else None
                normalized = copy.deepcopy(unknown)
                conn_quotas: Dict[str, Dict[str, Any]] = {}

                if isinstance(data, dict) and isinstance(data.get("providers"), list):
                    # Real OmniRoute v3 /api/usage/quota + /api/usage/provider-limits envelope.
                    limits_by_cid, limit_providers = await self._fetch_provider_limits_map(client, now, now_iso)
                    consolidated: Dict[str, Dict[str, Any]] = {}

                    for entry in data["providers"]:
                        if not isinstance(entry, dict):
                            continue
                        raw_provider = entry.get("provider")
                        if not isinstance(raw_provider, str) or not raw_provider.strip():
                            continue
                        provider_name = str(_redact(raw_provider.strip().lower()))
                        canonical = _canonical_quota_key(provider_name)
                        raw_cid = entry.get("connectionId") or entry.get("connection_id") or entry.get("id")
                        cid = raw_cid.strip() if isinstance(raw_cid, str) and raw_cid.strip() else None

                        metric: Optional[Dict[str, Any]] = None
                        if cid and cid in limits_by_cid:
                            metric = limits_by_cid[cid]
                        elif not _is_entry_inactive(entry):
                            metric = _parse_real_quota_provider_item(entry, now, now_iso)

                        if metric is not None:
                            if cid:
                                conn_quotas[cid] = copy.deepcopy(metric)
                            self._merge_canonical_quota(consolidated, canonical, metric)

                    for cid, metric in limits_by_cid.items():
                        if cid not in conn_quotas:
                            conn_quotas[cid] = copy.deepcopy(metric)
                        raw_prov = limit_providers.get(cid)
                        if raw_prov:
                            self._merge_canonical_quota(consolidated, _canonical_quota_key(raw_prov), metric)

                    for key, metric in consolidated.items():
                        safe_key = str(_redact(key))
                        normalized[safe_key] = metric

                elif isinstance(data, dict):
                    # Legacy flat dict shape {"claude_pro": {"remaining_percent": ...}, ...}.
                    default_status = str(data.get("status", "observed"))
                    for name, entry in data.items():
                        if not isinstance(entry, dict):
                            continue
                        parsed = _parse_quota_metrics(entry, default_status=default_status)
                        if parsed is None:
                            continue
                        status, percent, reset = parsed
                        safe_name = str(_redact(str(name)))
                        normalized[safe_name] = {
                            "status": status,
                            "remaining_percent": percent,
                            "resets_in_seconds": reset,
                            "observed_at": now_iso,
                            "source": "omniroute:quota_api",
                        }

                elif resp.status_code == 404:
                    limits_by_cid, limit_providers = await self._fetch_provider_limits_map(client, now, now_iso)
                    consolidated = {}
                    for cid, metric in limits_by_cid.items():
                        conn_quotas[cid] = copy.deepcopy(metric)
                        raw_prov = limit_providers.get(cid)
                        if raw_prov:
                            self._merge_canonical_quota(consolidated, _canonical_quota_key(raw_prov), metric)
                    for key, metric in consolidated.items():
                        normalized[str(_redact(key))] = metric

                self._last_connection_quotas = copy.deepcopy(conn_quotas)
                statuses = [v["status"] for v in normalized.values() if isinstance(v, dict)]
                normalized["status"] = "observed" if "observed" in statuses else "stale" if "stale" in statuses else "unknown"
                if normalized["status"] != "unknown":
                    self._last_quota = copy.deepcopy(normalized)
                    return normalized
                if resp.status_code == 200:
                    return normalized
        except Exception as e:
            logger.debug(f"Could not reach OmniRoute quota API: {e}")

        self._last_connection_quotas = {}
        if self._last_quota is not None:
            stale = copy.deepcopy(self._last_quota)
            stale["status"] = "stale"
            for entry in stale.values():
                if isinstance(entry, dict) and entry.get("remaining_percent") is not None:
                    entry.update(status="stale", resets_in_seconds=None)
                    entry.pop("reset_at", None)
            return stale
        return unknown

    async def list_models(self) -> Dict[str, Any]:
        """Discover active model inventory from OmniRoute without fabricating offline entries."""
        if not self.enabled:
            return {"status": "unavailable", "source": "omniroute:disabled", "models": []}
        try:
            async with self._build_client(httpx.Timeout(10.0, connect=2.0)) as client:
                resp = await client.get(f"{self.base_url}/models")
                if resp.status_code != 200:
                    return {"status": "unavailable", "source": "omniroute:models_api", "models": []}
                payload = resp.json()
        except Exception as e:
            logger.debug(f"Could not list OmniRoute models: {e}")
            return {"status": "unavailable", "source": "omniroute:models_api", "models": []}

        raw_models: Any = None
        if isinstance(payload, dict):
            if "data" in payload:
                raw_models = payload.get("data")
            elif "models" in payload:
                raw_models = payload.get("models")
        elif isinstance(payload, list):
            raw_models = payload

        if not isinstance(raw_models, list):
            return {"status": "unavailable", "source": "omniroute:models_api", "models": []}

        models: List[Dict[str, str]] = []
        seen_ids: set[str] = set()
        for entry in raw_models:
            if isinstance(entry, str):
                model_id = entry.strip()
                if not model_id:
                    continue
                provider = model_id.split("/", 1)[0] if "/" in model_id else "unknown"
                owned_by = provider
            elif isinstance(entry, dict):
                raw_id = entry.get("id") or entry.get("model") or entry.get("name")
                if not isinstance(raw_id, str) or not raw_id.strip():
                    continue
                model_id = raw_id.strip()
                inferred = model_id.split("/", 1)[0] if "/" in model_id else ""
                raw_provider = entry.get("provider")
                raw_owned_by = entry.get("owned_by")
                provider = (
                    raw_provider.strip()
                    if isinstance(raw_provider, str) and raw_provider.strip()
                    else (
                        inferred
                        or (raw_owned_by.strip() if isinstance(raw_owned_by, str) and raw_owned_by.strip() else "unknown")
                    )
                )
                owned_by = (
                    raw_owned_by.strip()
                    if isinstance(raw_owned_by, str) and raw_owned_by.strip()
                    else provider
                )
            else:
                continue

            normalized_item = _redact({"id": model_id, "provider": provider, "owned_by": owned_by})
            if normalized_item["id"] in seen_ids:
                continue
            seen_ids.add(normalized_item["id"])
            models.append(normalized_item)

        return {
            "status": "available",
            "source": "omniroute:models_api",
            "models": models,
        }

    @staticmethod
    def _normalize_account_item(
        entry: Dict[str, Any],
        quota: Dict[str, Any],
        now_iso: str,
    ) -> Optional[Dict[str, Any]]:
        scrubbed = _redact(_strip_sensitive_account_fields(entry))
        raw_id = scrubbed.get("account_id") or scrubbed.get("connectionId") or scrubbed.get("id") or scrubbed.get("name")
        if not isinstance(raw_id, str) or not raw_id.strip():
            return None
        account_id = raw_id.strip()

        raw_provider = scrubbed.get("provider") or scrubbed.get("vendor") or scrubbed.get("quota_key")
        provider = (
            raw_provider.strip()
            if isinstance(raw_provider, str) and raw_provider.strip()
            else "unknown"
        )
        raw_label = scrubbed.get("label") or scrubbed.get("name") or account_id
        label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else account_id

        raw_quota_key = scrubbed.get("quota_key")
        canonical_provider = _canonical_quota_key(provider)
        if isinstance(raw_quota_key, str) and raw_quota_key.strip():
            quota_key: Optional[str] = raw_quota_key.strip()
        elif isinstance(quota.get(provider), dict):
            quota_key = provider
        elif isinstance(quota.get(canonical_provider), dict):
            quota_key = canonical_provider
        else:
            quota_key = None

        inline_quota = _parse_quota_metrics(scrubbed)
        quota_lookup = (
            quota.get(quota_key)
            if quota_key and isinstance(quota.get(quota_key), dict)
            else quota.get(provider)
            if isinstance(quota.get(provider), dict)
            else None
        )
        fallback_quota = (
            _parse_quota_metrics(quota_lookup, default_status=str(quota_lookup.get("status", "unknown")))
            if isinstance(quota_lookup, dict)
            else None
        )

        if inline_quota is not None:
            status, percent, reset = inline_quota
            observed_at = scrubbed.get("observed_at") if isinstance(scrubbed.get("observed_at"), str) else now_iso
            source = (
                scrubbed.get("source")
                if isinstance(scrubbed.get("source"), str) and scrubbed.get("source").strip()
                else "omniroute:accounts_api"
            )
            remaining_percent: Optional[float] = float(percent)
        elif fallback_quota is not None and not _is_entry_inactive(entry):
            status, percent, reset = fallback_quota
            observed_at = quota_lookup.get("observed_at") if isinstance(quota_lookup, dict) else None
            source = (
                str(quota_lookup.get("source", "omniroute:quota_api"))
                if isinstance(quota_lookup, dict)
                else "omniroute:quota_api"
            )
            remaining_percent = float(percent)
        else:
            status = "unknown"
            remaining_percent = None
            reset = None
            observed_at = None
            source = "omniroute:accounts_api"

        return _redact(
            {
                "account_id": account_id,
                "provider": provider,
                "label": label,
                "quota_key": quota_key,
                "status": status,
                "remaining_percent": remaining_percent,
                "resets_in_seconds": reset,
                "observed_at": observed_at,
                "source": source,
            }
        )

    @staticmethod
    def _normalize_provider_connection(
        entry: Dict[str, Any],
        quota: Dict[str, Any],
        conn_quotas: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Normalize an OmniRoute v3 /api/providers connection without ever copying PII or credentials."""
        raw_id = entry.get("id") or entry.get("connectionId") or entry.get("account_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            return None
        account_id = raw_id.strip()

        raw_provider = entry.get("provider") or entry.get("vendor")
        provider = (
            raw_provider.strip().lower()
            if isinstance(raw_provider, str) and raw_provider.strip()
            else "unknown"
        )
        canonical_key = _canonical_quota_key(provider)
        quota_key: Optional[str] = (
            canonical_key
            if isinstance(quota.get(canonical_key), dict) or canonical_key in _QUOTA_PROVIDERS
            else provider
        )

        auth_type = str(entry.get("authType") or entry.get("auth_type") or "").strip().lower()
        inactive = _is_entry_inactive(entry)
        test_status = str(entry.get("testStatus") or entry.get("test_status") or "").strip().lower()
        short_id = account_id[:8]
        label = f"{provider} ({auth_type}) · {short_id}" if auth_type else f"{provider} · {short_id}"
        if inactive:
            tag = test_status if test_status in _INACTIVE_STATUSES else "inactive"
            label = f"{label} [{tag}]"

        conn_metric = conn_quotas.get(account_id)
        if not inactive and isinstance(conn_metric, dict):
            parsed = _parse_quota_metrics(conn_metric, default_status=str(conn_metric.get("status", "unknown")))
            metric_src = conn_metric
        elif not inactive and isinstance(quota.get(canonical_key), dict):
            parsed = _parse_quota_metrics(
                quota[canonical_key],
                default_status=str(quota[canonical_key].get("status", "unknown")),
            )
            metric_src = quota[canonical_key]
        else:
            parsed = None
            metric_src = None

        if parsed is not None and metric_src is not None:
            status, percent, reset = parsed
            remaining_percent: Optional[float] = float(percent)
            observed_at = metric_src.get("observed_at")
            source = str(metric_src.get("source", "omniroute:providers_api"))
        else:
            status = "unknown"
            remaining_percent = None
            reset = None
            observed_at = None
            source = "omniroute:providers_api"

        return _redact(
            {
                "account_id": account_id,
                "provider": provider,
                "label": label,
                "quota_key": quota_key,
                "status": status,
                "remaining_percent": remaining_percent,
                "resets_in_seconds": reset,
                "observed_at": observed_at,
                "source": source,
            }
        )

    async def list_accounts(self) -> Dict[str, Any]:
        """List discovered OmniRoute accounts merged with quota telemetry without leaking credentials or PII."""
        if not self.enabled:
            return {"status": "unknown", "source": "omniroute:disabled", "accounts": []}

        raw_accounts: Optional[List[Any]] = None
        raw_connections: Optional[List[Any]] = None
        try:
            async with self._build_client(httpx.Timeout(6.0, connect=2.0)) as client:
                resp = await client.get(f"{self.base_url}/accounts")
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, list):
                        raw_accounts = payload
                    elif isinstance(payload, dict):
                        if isinstance(payload.get("accounts"), list):
                            raw_accounts = payload["accounts"]
                        elif isinstance(payload.get("data"), list):
                            raw_accounts = payload["data"]
                if raw_accounts is None:
                    prov_resp = await client.get(self._providers_url)
                    if prov_resp.status_code == 200:
                        prov_payload = prov_resp.json()
                        if isinstance(prov_payload, dict) and isinstance(prov_payload.get("connections"), list):
                            raw_connections = prov_payload["connections"]
        except Exception as e:
            logger.debug(f"Could not reach OmniRoute accounts API: {e}")

        quota = await self.get_quota_status()
        conn_quotas = copy.deepcopy(self._last_connection_quotas)
        now_iso = datetime.now(timezone.utc).isoformat()
        accounts: List[Dict[str, Any]] = []
        source = "omniroute:accounts_api"

        if raw_accounts is not None:
            seen_accounts: set[Tuple[str, str]] = set()
            for entry in raw_accounts:
                if not isinstance(entry, dict):
                    continue
                normalized = self._normalize_account_item(entry, quota, now_iso)
                if normalized is None:
                    continue
                identity = (normalized["provider"], normalized["account_id"])
                if identity in seen_accounts:
                    continue
                seen_accounts.add(identity)
                accounts.append(normalized)
        elif raw_connections is not None:
            source = "omniroute:providers_api"
            seen_connections: set[Tuple[str, str]] = set()
            for entry in raw_connections:
                if not isinstance(entry, dict):
                    continue
                normalized = self._normalize_provider_connection(entry, quota, conn_quotas)
                if normalized is None:
                    continue
                identity = (normalized["provider"], normalized["account_id"])
                if identity in seen_connections:
                    continue
                seen_connections.add(identity)
                accounts.append(normalized)
        else:
            for quota_key, entry in quota.items():
                if not isinstance(entry, dict):
                    continue
                parsed = _parse_quota_metrics(entry, default_status=str(entry.get("status", "unknown")))
                if parsed is None:
                    continue
                status, percent, reset = parsed
                accounts.append(
                    _redact(
                        {
                            "account_id": str(quota_key),
                            "provider": str(quota_key),
                            "label": str(quota_key),
                            "quota_key": str(quota_key),
                            "status": status,
                            "remaining_percent": float(percent),
                            "resets_in_seconds": reset,
                            "observed_at": entry.get("observed_at"),
                            "source": str(entry.get("source", "omniroute:quota_api")),
                        }
                    )
                )
            if accounts:
                source = "omniroute:quota_api"

        statuses = [acc["status"] for acc in accounts]
        overall = (
            "observed"
            if "observed" in statuses
            else "stale"
            if "stale" in statuses
            else "unknown"
        )
        return {
            "status": overall,
            "source": source,
            "accounts": accounts,
        }

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        allow_offline_mock: bool = False,
    ) -> AsyncIterator[str]:
        """Stream tokens from OmniRoute gateway via standard SSE."""
        if not self.enabled:
            raise ConnectionError("OmniRoute is disabled")
        resolved_model = self.normalize_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        try:
            async with self._build_client(self.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 429:
                        raise RuntimeError(f"OmniRoute 429 Quota Exhausted for model {model}")
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            raw = line[len("data: ") :].strip()
                            if raw == "[DONE]":
                                break
                            try:
                                data = json.loads(raw)
                                choices = data.get("choices", [])
                                if choices:
                                    content = choices[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except httpx.ConnectError as e:
            if allow_offline_mock:
                logger.warning("OmniRoute daemon not reachable on :20128. Yielding dry-run simulated response.")
                yield f"[OmniRoute Dry-Run Mode: Simulated response for {model}]\n"
            else:
                raise ConnectionError(f"OmniRoute daemon unreachable at {self.base_url}") from e
