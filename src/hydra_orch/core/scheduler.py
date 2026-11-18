"""T37: Durable backend scheduler (AutomationSchedule) with stdlib cron, IANA/DST, and run history."""

from __future__ import annotations

import asyncio
import calendar
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_timezone
import hashlib
import inspect
import json
import logging
import math
import re
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Literal, Optional, Tuple, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from hydra_orch.core.budget import (
    RECURRING_BUDGET_REQUIRED_MESSAGE,
    BudgetGovernor,
    _policy_has_finite_cap,
)
from hydra_orch.core.checkpointer import (
    ExecutionStore,
    OptimisticLockError,
    StorageIntegrityError,
)
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import (
    BudgetPolicy,
    ContractViolation,
    ExecutionModel,
    Identifier,
    NonEmpty,
    UtcTimestamp,
)

logger = logging.getLogger(__name__)

OverlapPolicy = Literal["skip", "queue", "allow"]
MissedPolicy = Literal["skip", "run_once"]
AutomationRunStatus = Literal["pending", "dispatched", "succeeded", "failed", "skipped", "missed"]
DispatcherFn = Callable[
    ["AutomationSchedule", str],
    Union[Optional[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
]
RunnerFn = Callable[
    ["AutomationSchedule", "AutomationRunRecord", Dict[str, Any]],
    Union[Optional[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
]

_OVERLAP_POLICIES = frozenset({"skip", "queue", "allow"})

__all__ = [
    "AutomationRunRecord",
    "AutomationRunStatus",
    "AutomationSchedule",
    "CronExpression",
    "DispatcherFn",
    "MissedPolicy",
    "OverlapPolicy",
    "RunnerFn",
    "SchedulerService",
    "compute_next_occurrence",
    "compute_previous_occurrence",
    "parse_cron_expression",
    "validate_timezone",
]
_MISSED_POLICIES = frozenset({"skip", "run_once"})
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_UNSET: Any = object()
_QUEUED_MARKER = "Queued due to active overlapping run"
_CALENDAR_RANGE_MSG = "Schedule occurrence exceeds supported calendar range"
_STALE_LEASE_ERROR_TEXT = "Interrupted automation run reconciled after stale lease timeout"

_CRON_SHORTCUTS: Dict[str, str] = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}

_MONTH_ALIASES: Dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DOW_ALIASES: Dict[str, int] = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}

_MAX_DAYS_IN_MONTH: Dict[int, int] = {
    1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


def _reject_nul(value: Optional[str], field_name: str) -> None:
    if value is not None and "\x00" in value:
        raise ContractViolation("invalid_schedule", f"{field_name} cannot contain NUL bytes")


def _clean_text(value: str, field_name: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str):
        raise ContractViolation("invalid_schedule", f"{field_name} must be a string")
    _reject_nul(value, field_name)
    cleaned = redact_text(value.strip())
    if not cleaned or len(cleaned) > max_length:
        raise ContractViolation(
            "invalid_schedule",
            f"{field_name} must be non-empty and at most {max_length} characters",
        )
    return cleaned


def _clean_optional_identifier(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractViolation("invalid_schedule", f"{field_name} must be a string")
    _reject_nul(value, field_name)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ContractViolation("invalid_schedule", f"Invalid {field_name} identifier")
    return value


def _ensure_utc(value: Union[datetime, str]) -> datetime:
    if isinstance(value, str):
        _reject_nul(value, "timestamp")
        clean = value.strip()
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(clean)
        except ValueError as exc:
            raise ContractViolation("invalid_schedule", f"Invalid timestamp: {value}") from exc
    elif isinstance(value, datetime):
        dt = value
    else:
        raise ContractViolation("invalid_schedule", "Expected a datetime or ISO timestamp")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def _utc_iso(dt: datetime) -> str:
    return _ensure_utc(dt).isoformat(timespec="microseconds")


def validate_timezone(tz_name: str) -> ZoneInfo:
    """Validate an IANA timezone key using stdlib zoneinfo."""
    if not isinstance(tz_name, str):
        raise ContractViolation("invalid_timezone", "Timezone must be a string")
    if "\x00" in tz_name or not tz_name.strip() or tz_name != tz_name.strip():
        raise ContractViolation("invalid_timezone", f"Invalid timezone: {tz_name!r}")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError) as exc:
        raise ContractViolation("invalid_timezone", f"Unknown IANA timezone '{tz_name}'") from exc


@dataclass(frozen=True)
class CronExpression:
    """Parsed 5-field standard cron expression."""

    raw: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]
    dom_wildcard: bool
    dow_wildcard: bool

    @property
    def hour_wildcard(self) -> bool:
        return len(self.hours) == 24

    def matches_date(self, candidate: date) -> bool:
        if candidate.month not in self.months:
            return False
        cron_dow = (candidate.weekday() + 1) % 7  # 0=Sunday .. 6=Saturday
        dom_match = candidate.day in self.days_of_month
        dow_match = cron_dow in self.days_of_week
        if self.dom_wildcard and self.dow_wildcard:
            return True
        if self.dom_wildcard:
            return dow_match
        if self.dow_wildcard:
            return dom_match
        return dom_match or dow_match


def _parse_cron_atom(
    token: str,
    *,
    min_val: int,
    max_val: int,
    aliases: Optional[Dict[str, int]] = None,
) -> int:
    lowered = token.lower()
    if aliases and lowered in aliases:
        return aliases[lowered]
    if not token.isascii() or not token.isdigit():
        raise ContractViolation("invalid_schedule", f"Invalid cron token '{token}'")
    value = int(token)
    if value < min_val or value > max_val:
        raise ContractViolation(
            "invalid_schedule",
            f"Cron value {value} out of range [{min_val}, {max_val}]",
        )
    return value


def _parse_cron_field(
    field_text: str,
    *,
    field_name: str,
    min_val: int,
    max_val: int,
    aliases: Optional[Dict[str, int]] = None,
    is_dow: bool = False,
) -> Tuple[frozenset[int], bool]:
    if not field_text:
        raise ContractViolation("invalid_schedule", f"Empty cron {field_name} field")
    wildcard = field_text == "*"
    values: set[int] = set()

    for segment in field_text.split(","):
        if not segment:
            raise ContractViolation("invalid_schedule", f"Empty item in cron {field_name}: '{field_text}'")
        parts = segment.split("/")
        if len(parts) > 2:
            raise ContractViolation("invalid_schedule", f"Invalid step syntax in cron {field_name}: '{segment}'")
        range_part = parts[0]
        step = 1
        if len(parts) == 2:
            step_str = parts[1]
            if not step_str or not step_str.isascii() or not step_str.isdigit():
                raise ContractViolation("invalid_schedule", f"Invalid cron step '{step_str}' in {field_name}")
            step = int(step_str)
            if step <= 0:
                raise ContractViolation("invalid_schedule", f"Cron step must be >= 1 in {field_name}")

        if range_part == "*":
            end_bound = 6 if is_dow else max_val
            values.update(range(min_val, end_bound + 1, step))
        elif "-" in range_part:
            bounds = range_part.split("-")
            if len(bounds) != 2 or not bounds[0] or not bounds[1]:
                raise ContractViolation("invalid_schedule", f"Invalid cron range '{range_part}' in {field_name}")
            start = _parse_cron_atom(bounds[0], min_val=min_val, max_val=max_val, aliases=aliases)
            end = _parse_cron_atom(bounds[1], min_val=min_val, max_val=max_val, aliases=aliases)
            if start > end:
                raise ContractViolation("invalid_schedule", f"Inverted cron range '{range_part}' in {field_name}")
            values.update(range(start, end + 1, step))
        else:
            start = _parse_cron_atom(range_part, min_val=min_val, max_val=max_val, aliases=aliases)
            if len(parts) == 2:
                end_bound = 6 if (is_dow and start <= 6) else max_val
                values.update(range(start, end_bound + 1, step))
            else:
                values.add(start)

    if is_dow:
        values = {0 if item == 7 else item for item in values}
    if not values:
        raise ContractViolation("invalid_schedule", f"Cron {field_name} produced no matching values")
    return frozenset(values), wildcard


def parse_cron_expression(expr: str) -> CronExpression:
    """Parse and validate a 5-field cron expression or standard @shortcut."""
    if not isinstance(expr, str):
        raise ContractViolation("invalid_schedule", "Cron expression must be a string")
    _reject_nul(expr, "cron_expr")
    stripped = expr.strip()
    if not stripped:
        raise ContractViolation("invalid_schedule", "Cron expression cannot be empty")

    expanded = _CRON_SHORTCUTS.get(stripped.lower(), stripped)
    if expanded.startswith("@"):
        raise ContractViolation("invalid_schedule", f"Unsupported cron shortcut '{stripped}'")

    fields = expanded.split()
    if len(fields) != 5:
        raise ContractViolation(
            "invalid_schedule",
            f"Cron expression must have exactly 5 fields, got {len(fields)}",
        )

    minute_f, hour_f, dom_f, mon_f, dow_f = fields
    minutes, _ = _parse_cron_field(minute_f, field_name="minute", min_val=0, max_val=59)
    hours, _ = _parse_cron_field(hour_f, field_name="hour", min_val=0, max_val=23)
    doms, dom_wildcard = _parse_cron_field(dom_f, field_name="day_of_month", min_val=1, max_val=31)
    months, _ = _parse_cron_field(
        mon_f, field_name="month", min_val=1, max_val=12, aliases=_MONTH_ALIASES
    )
    dows, dow_wildcard = _parse_cron_field(
        dow_f, field_name="day_of_week", min_val=0, max_val=7, aliases=_DOW_ALIASES, is_dow=True
    )

    if dow_wildcard and not any(d <= _MAX_DAYS_IN_MONTH[m] for m in months for d in doms):
        raise ContractViolation(
            "invalid_schedule",
            f"Cron expression '{stripped}' never matches any calendar date",
        )

    return CronExpression(
        raw=stripped,
        minutes=minutes,
        hours=hours,
        days_of_month=doms,
        months=months,
        days_of_week=dows,
        dom_wildcard=dom_wildcard,
        dow_wildcard=dow_wildcard,
    )


def _safe_date_sub_days(current: date, days: int) -> date:
    target_ord = current.toordinal() - days
    if target_ord < 1:
        return date.min
    return date.fromordinal(target_ord)


def _safe_date_add_days(current: date, days: int) -> date:
    max_ord = date.max.toordinal()
    target_ord = current.toordinal() + days
    if target_ord > max_ord:
        return date.max
    return date.fromordinal(target_ord)


def _advance_next_matching_month(current: date, allowed_months: frozenset[int]) -> date:
    if not allowed_months:
        raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
    year = current.year
    month = current.month
    while True:
        month += 1
        if month > 12:
            month = 1
            year += 1
        if year > date.max.year:
            raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
        if month in allowed_months:
            return date(year, month, 1)


def _step_prev_matching_month(current: date, allowed_months: frozenset[int]) -> date:
    if not allowed_months:
        raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
    year = current.year
    month = current.month
    while True:
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        if year < date.min.year:
            raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
        if month in allowed_months:
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, last_day)


def _valid_utc_instants_for_day(
    cron: CronExpression,
    tz: ZoneInfo,
    day: date,
) -> List[datetime]:
    """Compute all valid UTC instants for `day` in `tz` without DST gap/fold bugs."""
    folds = (0, 1) if cron.hour_wildcard else (0,)
    instants: List[datetime] = []
    for hour in cron.hours:
        for minute in cron.minutes:
            for fold in folds:
                try:
                    local_dt = datetime(day.year, day.month, day.day, hour, minute, 0, 0, tzinfo=tz, fold=fold)
                    cand_utc = local_dt.astimezone(dt_timezone.utc)
                    rt = cand_utc.astimezone(tz)
                except (OverflowError, ValueError):
                    continue
                if (rt.year, rt.month, rt.day, rt.hour, rt.minute, rt.fold) == (
                    day.year, day.month, day.day, hour, minute, fold
                ):
                    instants.append(cand_utc)
    return instants


def _validate_schedule_timing(
    cron_expr: Optional[Union[str, CronExpression]],
    interval_seconds: Optional[int],
    timezone: str,
) -> Tuple[Optional[CronExpression], Optional[int], ZoneInfo]:
    tz = validate_timezone(timezone)
    has_cron = cron_expr is not None
    has_interval = interval_seconds is not None
    if has_cron == has_interval:
        raise ContractViolation(
            "invalid_schedule",
            "Schedule requires exactly one of cron_expr or interval_seconds",
        )
    parsed_cron: Optional[CronExpression] = None
    if cron_expr is not None:
        parsed_cron = cron_expr if isinstance(cron_expr, CronExpression) else parse_cron_expression(cron_expr)
    if interval_seconds is not None:
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int) or interval_seconds < 60:
            raise ContractViolation("invalid_schedule", "interval_seconds must be an integer >= 60")
    return parsed_cron, interval_seconds, tz


def compute_next_occurrence(
    cron_expr: Optional[Union[str, CronExpression, "AutomationSchedule"]] = None,
    *,
    interval_seconds: Optional[int] = None,
    timezone: str = "UTC",
    after: Optional[datetime] = None,
    inclusive: bool = False,
) -> datetime:
    """Compute the next valid UTC occurrence for a cron or interval schedule across DST transitions."""
    if isinstance(cron_expr, AutomationSchedule):
        interval_seconds = cron_expr.interval_seconds
        timezone = cron_expr.timezone
        cron_expr = cron_expr.cron_expr

    parsed_cron, valid_interval, tz = _validate_schedule_timing(cron_expr, interval_seconds, timezone)
    after_utc = _ensure_utc(after or datetime.now(dt_timezone.utc))

    if valid_interval is not None:
        if inclusive:
            return after_utc
        try:
            return after_utc + timedelta(seconds=valid_interval)
        except (OverflowError, ValueError) as exc:
            raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG) from exc

    assert parsed_cron is not None
    base = after_utc.replace(second=0, microsecond=0)
    try:
        if inclusive:
            start_utc = base if base >= after_utc else base + timedelta(minutes=1)
        else:
            start_utc = base + timedelta(minutes=1)
    except (OverflowError, ValueError) as exc:
        raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG) from exc

    try:
        start_local_date = start_utc.astimezone(tz).date()
    except (OverflowError, ValueError) as exc:
        if start_utc.year <= date.min.year:
            start_local_date = date.min
        else:
            raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG) from exc

    cursor_day = _safe_date_sub_days(start_local_date, 1)
    max_day = _safe_date_add_days(start_local_date, 366 * 9)

    while cursor_day <= max_day:
        if cursor_day.month not in parsed_cron.months:
            cursor_day = _advance_next_matching_month(cursor_day, parsed_cron.months)
            continue
        if not parsed_cron.matches_date(cursor_day):
            if cursor_day >= date.max:
                raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
            cursor_day += timedelta(days=1)
            continue
        candidates = [c for c in _valid_utc_instants_for_day(parsed_cron, tz, cursor_day) if c >= start_utc]
        if candidates:
            return min(candidates)
        if cursor_day >= date.max:
            raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
        cursor_day += timedelta(days=1)

    if max_day >= date.max:
        raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG)
    raise ContractViolation("invalid_schedule", "Cron expression produced no occurrence within search horizon")


def compute_previous_occurrence(
    cron_expr: Optional[Union[str, CronExpression, "AutomationSchedule"]] = None,
    *,
    interval_seconds: Optional[int] = None,
    timezone: str = "UTC",
    at_or_before: Optional[datetime] = None,
    min_bound: Optional[datetime] = None,
) -> Optional[datetime]:
    """Compute the latest valid UTC occurrence <= `at_or_before` (optionally >= `min_bound`)."""
    if isinstance(cron_expr, AutomationSchedule):
        interval_seconds = cron_expr.interval_seconds
        timezone = cron_expr.timezone
        cron_expr = cron_expr.cron_expr

    parsed_cron, valid_interval, tz = _validate_schedule_timing(cron_expr, interval_seconds, timezone)
    upper_utc = _ensure_utc(at_or_before or datetime.now(dt_timezone.utc))
    lower_utc = _ensure_utc(min_bound) if min_bound is not None else None

    if valid_interval is not None:
        if lower_utc is None:
            return upper_utc
        if upper_utc < lower_utc:
            return None
        delta = upper_utc - lower_utc
        total_us = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        steps = total_us // (valid_interval * 1_000_000)
        try:
            return lower_utc + timedelta(seconds=steps * valid_interval)
        except (OverflowError, ValueError) as exc:
            raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG) from exc

    assert parsed_cron is not None
    end_utc = upper_utc.replace(second=0, microsecond=0)
    try:
        end_local_date = end_utc.astimezone(tz).date()
    except (OverflowError, ValueError):
        if end_utc.year <= date.min.year:
            return None
        end_local_date = date.max

    cursor_day = _safe_date_add_days(end_local_date, 1)
    if lower_utc is not None:
        try:
            lower_local_date = lower_utc.astimezone(tz).date()
            min_day = _safe_date_sub_days(lower_local_date, 1)
        except (OverflowError, ValueError):
            if lower_utc.year <= date.min.year:
                min_day = date.min
            else:
                return None
    else:
        min_day = _safe_date_sub_days(end_local_date, 366 * 9)

    while cursor_day >= min_day:
        if cursor_day.month not in parsed_cron.months:
            try:
                cursor_day = _step_prev_matching_month(cursor_day, parsed_cron.months)
            except ContractViolation:
                return None
            continue
        if not parsed_cron.matches_date(cursor_day):
            if cursor_day <= date.min:
                break
            cursor_day -= timedelta(days=1)
            continue
        candidates = [
            c
            for c in _valid_utc_instants_for_day(parsed_cron, tz, cursor_day)
            if c <= upper_utc and (lower_utc is None or c >= lower_utc)
        ]
        if candidates:
            return max(candidates)
        if cursor_day <= date.min:
            break
        cursor_day -= timedelta(days=1)
    return None


class AutomationSchedule(ExecutionModel):
    """Persisted durable schedule definition."""

    id: Identifier
    name: NonEmpty
    workspace_id: Optional[Identifier] = None
    project_id: Optional[Identifier] = None
    target_host: NonEmpty = "local"
    executor_id: NonEmpty = "codex"
    prompt: NonEmpty
    cron_expr: Optional[str] = None
    interval_seconds: Optional[int] = Field(default=None, ge=60, strict=True)
    timezone: NonEmpty = "UTC"
    enabled: bool = True
    overlap_policy: OverlapPolicy = "skip"
    missed_policy: MissedPolicy = "skip"
    max_retries: int = Field(default=0, ge=0, le=5, strict=True)
    budget_policy: Optional[Dict[str, Any]] = None
    next_run_at: Optional[UtcTimestamp] = None
    last_run_at: Optional[UtcTimestamp] = None
    revision: int = Field(default=1, ge=1, strict=True)
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    @model_validator(mode="after")
    def _validate_schedule_contract(self) -> AutomationSchedule:
        for val in (self.name, self.target_host, self.executor_id, self.prompt, self.cron_expr, self.timezone):
            if val is not None and "\x00" in val:
                raise ValueError("Schedule fields cannot contain NUL bytes")
        if (self.cron_expr is None) == (self.interval_seconds is None):
            raise ValueError("Schedule must define exactly one of cron_expr or interval_seconds")
        validate_timezone(self.timezone)
        if self.cron_expr is not None:
            parse_cron_expression(self.cron_expr)
        return self


class AutomationRunRecord(ExecutionModel):
    """Persisted history record for a scheduled or manually triggered occurrence."""

    id: Identifier
    schedule_id: Identifier
    occurrence_key: NonEmpty
    scheduled_for: UtcTimestamp
    run_id: Optional[Identifier] = None
    status: AutomationRunStatus
    attempt_count: int = Field(default=1, ge=1, strict=True)
    error_detail: Optional[str] = None
    dispatched_at: UtcTimestamp
    finished_at: Optional[UtcTimestamp] = None

    @property
    def error_text(self) -> Optional[str]:
        return self.error_detail

    @property
    def started_at(self) -> datetime:
        return self.dispatched_at


def _schedule_pref_scope_id(schedule_id: str) -> str:
    candidate = f"schedule:{schedule_id}"
    if len(candidate) <= 128:
        return candidate
    digest = hashlib.sha256(schedule_id.encode("utf-8")).hexdigest()
    return f"schedule:{digest}"


def _normalize_schedule_budget_policy(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, BudgetPolicy):
        clean_map: Dict[str, Any] = {
            k: v
            for k, v in raw.model_dump(exclude={"schema_version"}).items()
            if v is not None
        }
    elif isinstance(raw, Mapping):
        _policy_has_finite_cap(raw, strict=True)
        clean_map = {str(k): v for k, v in raw.items()}
    else:
        raise ContractViolation("budget_invalid", "budget_policy must be a mapping or BudgetPolicy")

    try:
        serialized = json.dumps(
            clean_map,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractViolation("budget_invalid", f"budget_policy must be finite JSON-serializable data: {exc}") from exc

    if "\x00" in serialized:
        raise ContractViolation("budget_invalid", "budget_policy cannot contain NUL bytes")
    if redact(clean_map) != clean_map or redact_text(serialized) != serialized:
        raise ContractViolation("budget_invalid", "budget_policy cannot contain secrets or credentials")
    return json.loads(serialized)


async def _load_schedule_budgets_in_db(db: Any, schedule_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    ids = list(dict.fromkeys(schedule_ids))
    if not ids:
        return {}
    scope_to_sid = {_schedule_pref_scope_id(sid): sid for sid in ids}
    placeholders = ", ".join("?" for _ in scope_to_sid)
    rows = await (
        await db.execute(
            f"SELECT scope_id, value_json FROM preferences "
            f"WHERE scope_type = 'project' AND key = 'budget_policy' AND scope_id IN ({placeholders})",
            tuple(scope_to_sid.keys()),
        )
    ).fetchall()
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sid = scope_to_sid.get(row["scope_id"])
        if sid is None:
            continue
        try:
            parsed = json.loads(row["value_json"])
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            result[sid] = parsed
    return result


async def _save_schedule_budget_in_tx(
    db: Any,
    schedule_id: str,
    budget_policy: Optional[Dict[str, Any]],
    now_utc: datetime,
) -> None:
    scope_id = _schedule_pref_scope_id(schedule_id)
    if budget_policy is None:
        await db.execute(
            "DELETE FROM preferences WHERE scope_type = 'project' AND scope_id = ? AND key = 'budget_policy'",
            (scope_id,),
        )
        return
    value_json = json.dumps(
        budget_policy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    now_iso = _utc_iso(now_utc)
    existing = await (
        await db.execute(
            "SELECT id, version FROM preferences WHERE scope_type = 'project' AND scope_id = ? AND key = 'budget_policy'",
            (scope_id,),
        )
    ).fetchone()
    if existing is None:
        await db.execute(
            """
            INSERT INTO preferences (id, scope_type, scope_id, key, value_json, source, version, created_at, updated_at)
            VALUES (?, 'project', ?, 'budget_policy', ?, 'explicit', 1, ?, ?)
            """,
            (new_id(), scope_id, value_json, now_iso, now_iso),
        )
    else:
        await db.execute(
            """
            UPDATE preferences
            SET value_json = ?, source = 'explicit', version = ?, updated_at = ?
            WHERE id = ?
            """,
            (value_json, int(existing["version"]) + 1, now_iso, existing["id"]),
        )


def _row_to_schedule(row: Any, *, budget_policy: Optional[Dict[str, Any]] = None) -> AutomationSchedule:
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    for key in ("next_run_at", "last_run_at", "created_at", "updated_at"):
        if data.get(key) is not None:
            data[key] = _ensure_utc(data[key])
    if budget_policy is not None:
        data["budget_policy"] = budget_policy
    return AutomationSchedule.model_validate(data)


def _row_to_run(row: Any) -> AutomationRunRecord:
    data = dict(row)
    for key in ("scheduled_for", "dispatched_at", "finished_at"):
        if data.get(key) is not None:
            data[key] = _ensure_utc(data[key])
    if data.get("error_detail") is not None:
        data["error_detail"] = redact_text(str(data["error_detail"]))
    return AutomationRunRecord.model_validate(data)


def _run_record_to_result(record: AutomationRunRecord, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "automation_run_id": record.id,
        "schedule_id": record.schedule_id,
        "occurrence_key": record.occurrence_key,
        "scheduled_for": record.scheduled_for.isoformat(),
        "run_id": record.run_id,
        "status": record.status,
        "attempt_count": record.attempt_count,
        "error_detail": redact_text(record.error_detail) if record.error_detail is not None else None,
        "dispatched_at": record.dispatched_at.isoformat(),
        "finished_at": record.finished_at.isoformat() if record.finished_at is not None else None,
    }
    if metadata:
        payload["metadata"] = redact(metadata)
    return payload


class SchedulerService:
    """Durable SQLite-backed scheduler with idempotent occurrence dispatch and run history."""

    def __init__(
        self,
        store: ExecutionStore,
        dispatcher: Optional[DispatcherFn] = None,
        *,
        runner: Optional[RunnerFn] = None,
        retry_backoff_seconds: float = 0.0,
        require_budget: bool = False,
    ) -> None:
        self.store = store
        self.dispatcher = dispatcher
        self.runner = runner
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.require_budget = bool(require_budget)
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._running_automation_run_ids: set[str] = set()
        self._loop_task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None

    @property
    def is_running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    @staticmethod
    def _validate_policies(overlap_policy: str, missed_policy: str, max_retries: int) -> None:
        _reject_nul(overlap_policy, "overlap_policy")
        _reject_nul(missed_policy, "missed_policy")
        if overlap_policy not in _OVERLAP_POLICIES:
            raise ContractViolation("invalid_schedule", f"Invalid overlap_policy '{overlap_policy}'")
        if missed_policy not in _MISSED_POLICIES:
            raise ContractViolation("invalid_schedule", f"Invalid missed_policy '{missed_policy}'")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not (0 <= max_retries <= 5):
            raise ContractViolation("invalid_schedule", "max_retries must be an integer in [0, 5]")

    async def _assert_budget_gate_in_db(
        self,
        db: Any,
        *,
        project_id: Optional[str],
        workspace_id: Optional[str],
        budget_policy: Optional[Dict[str, Any]],
        schedule_id: Optional[str] = None,
    ) -> None:
        governor = BudgetGovernor(self.store)
        configured = await governor._has_configured_budget_in_db(
            db,
            project_id=project_id,
            budget_policy=budget_policy,
            schedule_id=schedule_id,
            workspace_id=workspace_id,
        )
        if not configured:
            raise ContractViolation("budget_required", RECURRING_BUDGET_REQUIRED_MESSAGE)

    async def create_schedule(
        self,
        name: str,
        prompt: str,
        *,
        cron_expr: Optional[str] = None,
        interval_seconds: Optional[int] = None,
        timezone: str = "UTC",
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        target_host: str = "local",
        executor_id: str = "codex",
        enabled: bool = True,
        overlap_policy: OverlapPolicy = "skip",
        missed_policy: MissedPolicy = "skip",
        max_retries: int = 0,
        budget_policy: Optional[Union[Dict[str, Any], BudgetPolicy]] = None,
        require_budget: bool = False,
        schedule_id: Optional[str] = None,
        next_run_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> AutomationSchedule:
        """Create and persist a new AutomationSchedule."""
        sid = _clean_optional_identifier(schedule_id, "schedule_id") or new_id()
        clean_name = _clean_text(name, "name", max_length=256)
        clean_prompt = _clean_text(prompt, "prompt", max_length=65536)
        clean_host = _clean_text(target_host, "target_host", max_length=256)
        clean_exec = _clean_text(executor_id, "executor_id", max_length=128)
        clean_ws = _clean_optional_identifier(workspace_id, "workspace_id")
        clean_proj = _clean_optional_identifier(project_id, "project_id")
        _reject_nul(timezone, "timezone")
        _reject_nul(cron_expr, "cron_expr")
        self._validate_policies(overlap_policy, missed_policy, max_retries)
        clean_bp = _normalize_schedule_budget_policy(budget_policy)

        parsed_cron, valid_interval, _ = _validate_schedule_timing(cron_expr, interval_seconds, timezone)
        clean_cron = parsed_cron.raw if parsed_cron is not None else None
        ref_now = _ensure_utc(now or datetime.now(dt_timezone.utc))

        if next_run_at is not None:
            computed_next: Optional[datetime] = _ensure_utc(next_run_at)
        elif enabled:
            computed_next = compute_next_occurrence(
                parsed_cron if parsed_cron is not None else None,
                interval_seconds=valid_interval,
                timezone=timezone,
                after=ref_now,
            )
        else:
            computed_next = None

        effective_require_budget = bool(self.require_budget or require_budget)
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                if enabled and effective_require_budget:
                    await self._assert_budget_gate_in_db(
                        db,
                        project_id=clean_proj,
                        workspace_id=clean_ws,
                        budget_policy=clean_bp,
                    )
                await db.execute(
                    """
                    INSERT INTO automation_schedules (
                        id, name, workspace_id, project_id, target_host, executor_id, prompt,
                        cron_expr, interval_seconds, timezone, enabled, overlap_policy, missed_policy,
                        max_retries, next_run_at, last_run_at, revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?, ?)
                    """,
                    (
                        sid, clean_name, clean_ws, clean_proj, clean_host, clean_exec, clean_prompt,
                        clean_cron, valid_interval, timezone, 1 if enabled else 0, overlap_policy,
                        missed_policy, max_retries,
                        _utc_iso(computed_next) if computed_next is not None else None,
                        _utc_iso(ref_now), _utc_iso(ref_now),
                    ),
                )
                if clean_bp is not None:
                    await _save_schedule_budget_in_tx(db, sid, clean_bp, ref_now)
                row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (sid,))).fetchone()
                assert row is not None
                return _row_to_schedule(row, budget_policy=clean_bp)

    async def get_schedule(self, schedule_id: str) -> AutomationSchedule:
        """Fetch an AutomationSchedule by ID or raise resource_not_found."""
        _reject_nul(schedule_id, "schedule_id")
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
            if row is None:
                raise ContractViolation("resource_not_found", f"AutomationSchedule '{schedule_id}' does not exist")
            bp_map = await _load_schedule_budgets_in_db(db, (schedule_id,))
        return _row_to_schedule(row, budget_policy=bp_map.get(schedule_id))

    async def list_schedules(
        self,
        *,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> List[AutomationSchedule]:
        """List schedules filtered optionally by workspace, project, or enabled flag."""
        clauses: List[str] = []
        params: List[Any] = []
        if workspace_id is not None:
            _reject_nul(workspace_id, "workspace_id")
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if project_id is not None:
            _reject_nul(project_id, "project_id")
            clauses.append("project_id = ?")
            params.append(project_id)
        if enabled is not None:
            clauses.append("enabled = ?")
            params.append(1 if enabled else 0)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        await self.store.initialize()
        async with self.store._connect() as db:
            rows = await (
                await db.execute(f"SELECT * FROM automation_schedules {where} ORDER BY created_at ASC, id ASC", params)
            ).fetchall()
            bp_map = await _load_schedule_budgets_in_db(db, (row["id"] for row in rows))
        return [_row_to_schedule(row, budget_policy=bp_map.get(row["id"])) for row in rows]

    async def update_schedule(
        self,
        schedule_id: str,
        *,
        name: Optional[str] = None,
        workspace_id: Any = _UNSET,
        project_id: Any = _UNSET,
        target_host: Optional[str] = None,
        executor_id: Optional[str] = None,
        prompt: Optional[str] = None,
        cron_expr: Any = _UNSET,
        interval_seconds: Any = _UNSET,
        timezone: Optional[str] = None,
        enabled: Optional[bool] = None,
        overlap_policy: Optional[OverlapPolicy] = None,
        missed_policy: Optional[MissedPolicy] = None,
        max_retries: Optional[int] = None,
        budget_policy: Any = _UNSET,
        require_budget: bool = False,
        next_run_at: Any = _UNSET,
        expected_revision: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> AutomationSchedule:
        """Update mutable fields of a schedule with validation and optional optimistic concurrency."""
        _reject_nul(schedule_id, "schedule_id")
        ref_now = _ensure_utc(now or datetime.now(dt_timezone.utc))
        new_bp_explicit = (
            _UNSET if budget_policy is _UNSET else _normalize_schedule_budget_policy(budget_policy)
        )
        effective_require_budget = bool(self.require_budget or require_budget)

        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"AutomationSchedule '{schedule_id}' does not exist")
                bp_map = await _load_schedule_budgets_in_db(db, (schedule_id,))
                current = _row_to_schedule(row, budget_policy=bp_map.get(schedule_id))
                if expected_revision is not None and current.revision != expected_revision:
                    raise OptimisticLockError("AutomationSchedule revision changed")

                new_name = _clean_text(name, "name", max_length=256) if name is not None else current.name
                new_prompt = _clean_text(prompt, "prompt", max_length=65536) if prompt is not None else current.prompt
                new_host = _clean_text(target_host, "target_host", max_length=256) if target_host is not None else current.target_host
                new_exec = _clean_text(executor_id, "executor_id", max_length=128) if executor_id is not None else current.executor_id
                new_ws = current.workspace_id if workspace_id is _UNSET else _clean_optional_identifier(workspace_id, "workspace_id")
                new_proj = current.project_id if project_id is _UNSET else _clean_optional_identifier(project_id, "project_id")
                new_tz = timezone if timezone is not None else current.timezone
                _reject_nul(new_tz, "timezone")
                new_enabled = current.enabled if enabled is None else bool(enabled)
                new_overlap = overlap_policy if overlap_policy is not None else current.overlap_policy
                new_missed = missed_policy if missed_policy is not None else current.missed_policy
                new_retries = max_retries if max_retries is not None else current.max_retries
                self._validate_policies(new_overlap, new_missed, new_retries)
                new_bp = current.budget_policy if new_bp_explicit is _UNSET else new_bp_explicit

                if cron_expr is not _UNSET and interval_seconds is not _UNSET:
                    new_cron_raw = cron_expr
                    new_interval = interval_seconds
                elif cron_expr is not _UNSET:
                    new_cron_raw = cron_expr
                    new_interval = None if cron_expr is not None else current.interval_seconds
                elif interval_seconds is not _UNSET:
                    new_interval = interval_seconds
                    new_cron_raw = None if interval_seconds is not None else current.cron_expr
                else:
                    new_cron_raw = current.cron_expr
                    new_interval = current.interval_seconds

                _reject_nul(new_cron_raw, "cron_expr")
                parsed_cron, valid_interval, _ = _validate_schedule_timing(new_cron_raw, new_interval, new_tz)
                new_cron = parsed_cron.raw if parsed_cron is not None else None

                if new_enabled and effective_require_budget:
                    await self._assert_budget_gate_in_db(
                        db,
                        project_id=new_proj,
                        workspace_id=new_ws,
                        budget_policy=new_bp,
                    )

                timing_changed = (
                    new_cron != current.cron_expr
                    or valid_interval != current.interval_seconds
                    or new_tz != current.timezone
                )

                if next_run_at is not _UNSET:
                    new_next_run: Optional[datetime] = _ensure_utc(next_run_at) if next_run_at is not None else None
                elif not new_enabled:
                    new_next_run = None
                elif timing_changed or (not current.enabled and new_enabled) or current.next_run_at is None:
                    new_next_run = compute_next_occurrence(
                        parsed_cron if parsed_cron is not None else None,
                        interval_seconds=valid_interval,
                        timezone=new_tz,
                        after=ref_now,
                    )
                else:
                    new_next_run = current.next_run_at

                await db.execute(
                    """
                    UPDATE automation_schedules
                    SET name = ?, workspace_id = ?, project_id = ?, target_host = ?, executor_id = ?,
                        prompt = ?, cron_expr = ?, interval_seconds = ?, timezone = ?, enabled = ?,
                        overlap_policy = ?, missed_policy = ?, max_retries = ?, next_run_at = ?,
                        revision = revision + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_name, new_ws, new_proj, new_host, new_exec, new_prompt,
                        new_cron, valid_interval, new_tz, 1 if new_enabled else 0,
                        new_overlap, new_missed, new_retries,
                        _utc_iso(new_next_run) if new_next_run is not None else None,
                        _utc_iso(ref_now), schedule_id,
                    ),
                )
                if new_bp_explicit is not _UNSET:
                    await _save_schedule_budget_in_tx(db, schedule_id, new_bp, ref_now)
                updated = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
                assert updated is not None
                return _row_to_schedule(updated, budget_policy=new_bp)

    async def set_enabled(
        self,
        schedule_id: str,
        enabled: bool,
        *,
        expected_revision: Optional[int] = None,
        now: Optional[datetime] = None,
        require_budget: bool = False,
    ) -> AutomationSchedule:
        """Pause (enabled=False) or resume (enabled=True) an existing schedule."""
        return await self.update_schedule(
            schedule_id,
            enabled=bool(enabled),
            expected_revision=expected_revision,
            now=now,
            require_budget=require_budget,
        )

    async def delete_schedule(self, schedule_id: str) -> None:
        """Delete a schedule and cascade-delete its automation_runs history."""
        _reject_nul(schedule_id, "schedule_id")
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                cursor = await db.execute("DELETE FROM automation_schedules WHERE id = ?", (schedule_id,))
                if cursor.rowcount == 0:
                    raise ContractViolation("resource_not_found", f"AutomationSchedule '{schedule_id}' does not exist")
                await _save_schedule_budget_in_tx(db, schedule_id, None, datetime.now(dt_timezone.utc))

    async def list_runs(self, schedule_id: str, *, limit: int = 100) -> List[AutomationRunRecord]:
        """List historical automation runs for a schedule, newest first."""
        _reject_nul(schedule_id, "schedule_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 1000):
            raise ContractViolation("invalid_schedule", "limit must be an integer in [1, 1000]")
        await self.store.initialize()
        async with self.store._connect() as db:
            exists = await (await db.execute("SELECT 1 FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
            if exists is None:
                raise ContractViolation("resource_not_found", f"AutomationSchedule '{schedule_id}' does not exist")
            rows = await (
                await db.execute(
                    """
                    SELECT * FROM automation_runs
                    WHERE schedule_id = ?
                    ORDER BY scheduled_for DESC, dispatched_at DESC, id DESC
                    LIMIT ?
                    """,
                    (schedule_id, limit),
                )
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    async def complete_run(
        self,
        automation_run_id: str,
        *,
        status: Literal["succeeded", "failed"] = "succeeded",
        run_id: Optional[str] = None,
        error_detail: Optional[str] = None,
        error_text: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> AutomationRunRecord:
        """Mark an active pending/dispatched automation run as succeeded or failed."""
        _reject_nul(automation_run_id, "automation_run_id")
        if status not in {"succeeded", "failed"}:
            raise ContractViolation("invalid_schedule", f"Invalid completion status '{status}'")
        ref_now = _ensure_utc(now or datetime.now(dt_timezone.utc))
        effective_error = error_detail if error_detail is not None else error_text
        safe_error = redact_text(effective_error) if effective_error is not None else None
        clean_run_id = _clean_optional_identifier(run_id, "run_id")

        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM automation_runs WHERE id = ?", (automation_run_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"AutomationRun '{automation_run_id}' does not exist")
                if row["status"] not in {"pending", "dispatched"}:
                    raise ContractViolation(
                        "invalid_transition",
                        f"AutomationRun '{automation_run_id}' is already terminal ({row['status']})",
                    )
                await db.execute(
                    """
                    UPDATE automation_runs
                    SET status = ?, run_id = COALESCE(?, run_id), error_detail = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (status, clean_run_id, safe_error, _utc_iso(ref_now), automation_run_id),
                )
                updated = await (await db.execute("SELECT * FROM automation_runs WHERE id = ?", (automation_run_id,))).fetchone()
                assert updated is not None
                return _row_to_run(updated)

    async def reconcile_stale_runs(
        self,
        *,
        max_age_seconds: float = 1800.0,
        now: Optional[datetime] = None,
    ) -> List[AutomationRunRecord]:
        """Reconcile orphaned or completed pending/dispatched automation_runs past max_age_seconds."""
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, (int, float))
            or math.isnan(float(max_age_seconds))
            or float(max_age_seconds) < 0.0
        ):
            raise ContractViolation("invalid_schedule", "max_age_seconds must be a non-negative number")

        now_utc = _ensure_utc(now or datetime.now(dt_timezone.utc))
        if math.isinf(float(max_age_seconds)):
            cutoff_utc = datetime.min.replace(tzinfo=dt_timezone.utc)
        else:
            try:
                cutoff_utc = now_utc - timedelta(seconds=float(max_age_seconds))
            except (OverflowError, ValueError):
                cutoff_utc = datetime.min.replace(tzinfo=dt_timezone.utc)

        await self.store.initialize()
        reconciled: List[AutomationRunRecord] = []

        async with self.store._connect() as db:
            async with self.store._transaction(db):
                candidates = await (
                    await db.execute(
                        """
                        SELECT * FROM automation_runs
                        WHERE status IN ('pending', 'dispatched')
                        ORDER BY scheduled_for ASC, dispatched_at ASC, id ASC
                        """
                    )
                ).fetchall()

                for row in candidates:
                    auto_run_id = str(row["id"])
                    if auto_run_id in self._running_automation_run_ids:
                        continue

                    ts_raw = row["dispatched_at"] or row["scheduled_for"]
                    lease_started = _ensure_utc(ts_raw)
                    if lease_started > cutoff_utc:
                        continue

                    linked_run_id = row["run_id"]
                    new_status: Literal["succeeded", "failed"] = "failed"
                    new_error: Optional[str] = _STALE_LEASE_ERROR_TEXT

                    if linked_run_id is not None:
                        run_row = await (
                            await db.execute("SELECT status FROM runs WHERE id = ?", (linked_run_id,))
                        ).fetchone()
                        if run_row is not None:
                            run_state = str(run_row["status"])
                            if run_state == "succeeded":
                                new_status = "succeeded"
                                new_error = None
                            elif run_state in {"failed", "cancelled"}:
                                new_status = "failed"
                                new_error = (
                                    str(row["error_detail"])
                                    if row["error_detail"]
                                    else f"Linked run '{linked_run_id}' terminated with status '{run_state}'"
                                )
                            else:
                                att_rows = await (
                                    await db.execute(
                                        """
                                        SELECT started_at, created_at
                                        FROM attempts
                                        WHERE run_id = ? AND process_status = 'running'
                                        """,
                                        (linked_run_id,),
                                    )
                                ).fetchall()
                                has_fresh_attempt = False
                                for att in att_rows:
                                    att_ts_raw = att["started_at"] or att["created_at"]
                                    if att_ts_raw is not None and _ensure_utc(att_ts_raw) > cutoff_utc:
                                        has_fresh_attempt = True
                                        break
                                if has_fresh_attempt:
                                    continue

                    safe_err = redact_text(new_error) if new_error is not None else None
                    await db.execute(
                        """
                        UPDATE automation_runs
                        SET status = ?, error_detail = ?, finished_at = ?
                        WHERE id = ? AND status IN ('pending', 'dispatched')
                        """,
                        (new_status, safe_err, _utc_iso(now_utc), auto_run_id),
                    )
                    updated = await (
                        await db.execute("SELECT * FROM automation_runs WHERE id = ?", (auto_run_id,))
                    ).fetchone()
                    if updated is not None:
                        reconciled.append(_row_to_run(updated))

        return reconciled

    async def _advance_next_run_if_stale(self, schedule_id: str, next_future: datetime, now_utc: datetime) -> None:
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
                if row is None or not row["enabled"] or row["next_run_at"] is None:
                    return
                if _ensure_utc(row["next_run_at"]) <= now_utc:
                    await db.execute(
                        "UPDATE automation_schedules SET next_run_at = ?, updated_at = ? WHERE id = ?",
                        (_utc_iso(next_future), _utc_iso(now_utc), schedule_id),
                    )

    @staticmethod
    def _compute_slot_plan(
        schedule: AutomationSchedule,
        scheduled_slot: datetime,
        now_utc: datetime,
    ) -> Tuple[Optional[str], datetime, datetime]:
        """Determine (skip_or_missed_status, effective_slot, next_future) for a due schedule."""
        slot_after = compute_next_occurrence(schedule, after=scheduled_slot)
        if slot_after <= now_utc:
            latest = compute_previous_occurrence(schedule, at_or_before=now_utc, min_bound=scheduled_slot)
            anchor = latest or scheduled_slot
            if schedule.interval_seconds is not None:
                try:
                    next_future = anchor + timedelta(seconds=schedule.interval_seconds)
                except (OverflowError, ValueError) as exc:
                    raise ContractViolation("invalid_schedule", _CALENDAR_RANGE_MSG) from exc
            else:
                next_future = compute_next_occurrence(schedule, after=now_utc)
            if schedule.missed_policy == "skip":
                return "missed", scheduled_slot, next_future
            return None, anchor, next_future
        return None, scheduled_slot, slot_after

    @staticmethod
    async def _insert_run_in_tx(
        db: Any,
        *,
        schedule_id: str,
        occurrence_key: str,
        scheduled_for: datetime,
        status: AutomationRunStatus,
        dispatched_at: datetime,
        error_detail: Optional[str] = None,
        finished_at: Optional[datetime] = None,
    ) -> AutomationRunRecord:
        auto_run_id = new_id()
        safe_error = redact_text(error_detail) if error_detail is not None else None
        await db.execute(
            """
            INSERT INTO automation_runs (
                id, schedule_id, occurrence_key, scheduled_for, run_id,
                status, attempt_count, error_detail, dispatched_at, finished_at
            ) VALUES (?, ?, ?, ?, NULL, ?, 1, ?, ?, ?)
            """,
            (
                auto_run_id,
                schedule_id,
                occurrence_key,
                _utc_iso(scheduled_for),
                status,
                safe_error,
                _utc_iso(dispatched_at),
                _utc_iso(finished_at) if finished_at is not None else None,
            ),
        )
        rec = await (await db.execute("SELECT * FROM automation_runs WHERE id = ?", (auto_run_id,))).fetchone()
        assert rec is not None
        return _row_to_run(rec)

    async def _claim_due_occurrence(
        self,
        schedule_id: str,
        now_utc: datetime,
        *,
        require_budget: bool = False,
    ) -> Optional[Tuple[str, AutomationSchedule, Optional[AutomationRunRecord]]]:
        """Claim a due scheduled occurrence inside a transaction.

        Returns ("dispatch", schedule, claim_record), ("terminal", schedule, record), or None if skipped/not due.
        """
        hit_duplicate = False
        effective_require_budget = bool(self.require_budget or require_budget)
        async with self.store._connect() as db:
            try:
                async with self.store._transaction(db):
                    row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
                    if row is None or not row["enabled"] or row["next_run_at"] is None:
                        return None
                    bp_map = await _load_schedule_budgets_in_db(db, (schedule_id,))
                    schedule = _row_to_schedule(row, budget_policy=bp_map.get(schedule_id))
                    assert schedule.next_run_at is not None
                    if schedule.next_run_at > now_utc:
                        return None

                    if effective_require_budget:
                        await self._assert_budget_gate_in_db(
                            db,
                            project_id=schedule.project_id,
                            workspace_id=schedule.workspace_id,
                            budget_policy=schedule.budget_policy,
                            schedule_id=schedule.id,
                        )

                    missed_status, effective_slot, next_future = self._compute_slot_plan(
                        schedule, schedule.next_run_at, now_utc
                    )
                    occ_key = f"{schedule.id}:{effective_slot.isoformat()}"

                    if missed_status == "missed":
                        record = await self._insert_run_in_tx(
                            db,
                            schedule_id=schedule.id,
                            occurrence_key=occ_key,
                            scheduled_for=effective_slot,
                            status="missed",
                            dispatched_at=now_utc,
                            error_detail="Skipped missed occurrence window",
                            finished_at=now_utc,
                        )
                        await db.execute(
                            "UPDATE automation_schedules SET next_run_at = ?, updated_at = ? WHERE id = ?",
                            (_utc_iso(next_future), _utc_iso(now_utc), schedule.id),
                        )
                        return ("terminal", schedule, record)

                    active_rows = await (
                        await db.execute(
                            "SELECT id, status FROM automation_runs WHERE schedule_id = ? AND status IN ('pending', 'dispatched')",
                            (schedule.id,),
                        )
                    ).fetchall()

                    if active_rows and schedule.overlap_policy == "skip":
                        record = await self._insert_run_in_tx(
                            db,
                            schedule_id=schedule.id,
                            occurrence_key=occ_key,
                            scheduled_for=effective_slot,
                            status="skipped",
                            dispatched_at=now_utc,
                            error_detail="Skipped due to active overlapping run",
                            finished_at=now_utc,
                        )
                        await db.execute(
                            "UPDATE automation_schedules SET next_run_at = ?, updated_at = ? WHERE id = ?",
                            (_utc_iso(next_future), _utc_iso(now_utc), schedule.id),
                        )
                        return ("terminal", schedule, record)

                    if active_rows and schedule.overlap_policy == "queue":
                        record = await self._insert_run_in_tx(
                            db,
                            schedule_id=schedule.id,
                            occurrence_key=occ_key,
                            scheduled_for=effective_slot,
                            status="pending",
                            dispatched_at=now_utc,
                            error_detail=_QUEUED_MARKER,
                            finished_at=None,
                        )
                        await db.execute(
                            "UPDATE automation_schedules SET next_run_at = ?, updated_at = ? WHERE id = ?",
                            (_utc_iso(next_future), _utc_iso(now_utc), schedule.id),
                        )
                        return ("terminal", schedule, record)

                    record = await self._insert_run_in_tx(
                        db,
                        schedule_id=schedule.id,
                        occurrence_key=occ_key,
                        scheduled_for=effective_slot,
                        status="pending",
                        dispatched_at=now_utc,
                        error_detail=None,
                        finished_at=None,
                    )
                    await db.execute(
                        "UPDATE automation_schedules SET next_run_at = ?, last_run_at = ?, updated_at = ? WHERE id = ?",
                        (_utc_iso(next_future), _utc_iso(now_utc), _utc_iso(now_utc), schedule.id),
                    )
                    return ("dispatch", schedule, record)
            except StorageIntegrityError:
                hit_duplicate = True

        if hit_duplicate:
            # Duplicate (schedule_id, occurrence_key) from concurrent tick or restart race.
            with suppress(ContractViolation):
                sched = await self.get_schedule(schedule_id)
                if sched.enabled and sched.next_run_at is not None and sched.next_run_at <= now_utc:
                    next_future = compute_next_occurrence(sched, after=now_utc)
                    await self._advance_next_run_if_stale(schedule_id, next_future, now_utc)
        return None

    async def _claim_queued_run(
        self,
        schedule_id: str,
        now_utc: datetime,
        *,
        require_budget: bool = False,
    ) -> Optional[Tuple[AutomationSchedule, AutomationRunRecord]]:
        """Atomically claim the oldest queued run for `schedule_id` if no active run is in flight."""
        effective_require_budget = bool(self.require_budget or require_budget)
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
                if row is None or not row["enabled"]:
                    return None
                bp_map = await _load_schedule_budgets_in_db(db, (schedule_id,))
                schedule = _row_to_schedule(row, budget_policy=bp_map.get(schedule_id))
                if schedule.overlap_policy != "queue":
                    return None
                busy = await (
                    await db.execute(
                        """
                        SELECT 1 FROM automation_runs
                        WHERE schedule_id = ?
                          AND (status = 'dispatched' OR (status = 'pending' AND COALESCE(error_detail, '') != ?))
                        LIMIT 1
                        """,
                        (schedule_id, _QUEUED_MARKER),
                    )
                ).fetchone()
                if busy is not None:
                    return None
                queued = await (
                    await db.execute(
                        """
                        SELECT * FROM automation_runs
                        WHERE schedule_id = ? AND status = 'pending' AND error_detail = ?
                        ORDER BY scheduled_for ASC, dispatched_at ASC, id ASC
                        LIMIT 1
                        """,
                        (schedule_id, _QUEUED_MARKER),
                    )
                ).fetchone()
                if queued is None:
                    return None

                if effective_require_budget:
                    await self._assert_budget_gate_in_db(
                        db,
                        project_id=schedule.project_id,
                        workspace_id=schedule.workspace_id,
                        budget_policy=schedule.budget_policy,
                        schedule_id=schedule.id,
                    )

                cur = await db.execute(
                    """
                    UPDATE automation_runs
                    SET error_detail = NULL, dispatched_at = ?
                    WHERE id = ? AND status = 'pending' AND error_detail = ?
                    """,
                    (_utc_iso(now_utc), queued["id"], _QUEUED_MARKER),
                )
                if cur.rowcount != 1:
                    return None
                await db.execute(
                    "UPDATE automation_schedules SET last_run_at = ?, updated_at = ? WHERE id = ?",
                    (_utc_iso(now_utc), _utc_iso(now_utc), schedule_id),
                )
                updated = await (await db.execute("SELECT * FROM automation_runs WHERE id = ?", (queued["id"],))).fetchone()
                assert updated is not None
                return schedule, _row_to_run(updated)

    async def _persist_run_outcome(
        self,
        automation_run_id: str,
        *,
        status: AutomationRunStatus,
        attempt_count: int,
        run_id: Optional[str] = None,
        error_detail: Optional[str] = None,
        finished_at: Optional[datetime] = None,
    ) -> AutomationRunRecord:
        safe_error = redact_text(error_detail) if error_detail is not None else None
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                await db.execute(
                    """
                    UPDATE automation_runs
                    SET status = ?, attempt_count = ?, run_id = ?, error_detail = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        attempt_count,
                        run_id,
                        safe_error,
                        _utc_iso(finished_at) if finished_at is not None else None,
                        automation_run_id,
                    ),
                )
                row = await (await db.execute("SELECT * FROM automation_runs WHERE id = ?", (automation_run_id,))).fetchone()
                assert row is not None
                return _row_to_run(row)

    def _spawn_runner_task(
        self,
        schedule: AutomationSchedule,
        run_record: AutomationRunRecord,
        dispatch_result: Dict[str, Any],
    ) -> asyncio.Task[None]:
        self._running_automation_run_ids.add(run_record.id)
        task = asyncio.create_task(
            self._run_supervised(schedule, run_record, dict(dispatch_result)),
            name=f"hydra-sched-run-{run_record.id}",
        )
        self._active_tasks.add(task)

        def _cleanup(done_task: asyncio.Task[Any]) -> None:
            self._active_tasks.discard(done_task)
            self._running_automation_run_ids.discard(run_record.id)

        task.add_done_callback(_cleanup)
        return task

    async def _run_supervised(
        self,
        schedule: AutomationSchedule,
        run_record: AutomationRunRecord,
        dispatch_result: Dict[str, Any],
    ) -> None:
        assert self.runner is not None
        final_status: Literal["succeeded", "failed"] = "failed"
        final_run_id: Optional[str] = run_record.run_id
        error_text: Optional[str] = None
        try:
            outcome = self.runner(schedule, run_record, dispatch_result)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if isinstance(outcome, dict):
                if outcome.get("run_id") is not None:
                    with suppress(ContractViolation):
                        final_run_id = _clean_optional_identifier(str(outcome["run_id"]), "run_id")
                out_status = outcome.get("status")
                out_ok = outcome.get("ok")
                raw_err = outcome.get("error_text") or outcome.get("error_detail") or outcome.get("error")
                if out_ok is False or out_status in {"failed", "error", "cancelled"}:
                    final_status = "failed"
                    error_text = str(raw_err) if raw_err else f"Runner reported status '{out_status}'"
                else:
                    final_status = "succeeded"
                    if raw_err:
                        error_text = str(raw_err)
            else:
                final_status = "succeeded"
        except asyncio.CancelledError:
            final_status = "failed"
            error_text = "Automation runner task was cancelled"
            raise
        except Exception as exc:
            final_status = "failed"
            error_text = redact_text(f"{type(exc).__name__}: {exc}") or type(exc).__name__
        finally:
            self._running_automation_run_ids.discard(run_record.id)
            try:
                await asyncio.shield(
                    self.complete_run(
                        run_record.id,
                        status=final_status,
                        run_id=final_run_id,
                        error_text=error_text,
                    )
                )
            except ContractViolation as exc:
                if exc.code not in {"invalid_transition", "resource_not_found"}:
                    logger.exception("Failed completing supervised automation run %s", run_record.id)
            except Exception:
                logger.exception("Failed completing supervised automation run %s", run_record.id)

            if not (self._stop_event is not None and self._stop_event.is_set()):
                try:
                    now_drain = datetime.now(dt_timezone.utc)
                    claimed_pair = await self._claim_queued_run(schedule.id, now_drain)
                    if claimed_pair is not None:
                        next_sched, queued_rec = claimed_pair
                        await self._execute_claimed_run(next_sched, queued_rec, now_drain)
                except Exception:
                    logger.exception("Failed draining queued automation run for schedule %s", schedule.id)

    async def _execute_claimed_run(
        self,
        schedule: AutomationSchedule,
        claimed: AutomationRunRecord,
        now_utc: datetime,
    ) -> Dict[str, Any]:
        if self.dispatcher is None:
            if self.runner is not None:
                dispatch_payload: Dict[str, Any] = {"status": "dispatched", "run_id": None}
                record = await self._persist_run_outcome(
                    claimed.id,
                    status="dispatched",
                    attempt_count=1,
                    run_id=None,
                    error_detail=None,
                    finished_at=None,
                )
                self._spawn_runner_task(schedule, record, dispatch_payload)
                return _run_record_to_result(record, dispatch_payload)

            record = await self._persist_run_outcome(
                claimed.id,
                status="failed",
                attempt_count=1,
                run_id=None,
                error_detail="no_dispatcher_configured",
                finished_at=now_utc,
            )
            return _run_record_to_result(record)

        max_attempts = 1 + schedule.max_retries
        last_error: Optional[str] = None

        for attempt in range(1, max_attempts + 1):
            try:
                raw_result = self.dispatcher(schedule, claimed.occurrence_key)
                if inspect.isawaitable(raw_result):
                    raw_result = await raw_result
            except Exception as exc:
                last_error = redact_text(f"{type(exc).__name__}: {exc}") or type(exc).__name__
                if attempt < max_attempts:
                    await self._persist_run_outcome(
                        claimed.id,
                        status="pending",
                        attempt_count=attempt + 1,
                        run_id=None,
                        error_detail=last_error,
                        finished_at=None,
                    )
                    if self.retry_backoff_seconds > 0:
                        await asyncio.sleep(self.retry_backoff_seconds)
                    continue
                record = await self._persist_run_outcome(
                    claimed.id,
                    status="failed",
                    attempt_count=attempt,
                    run_id=None,
                    error_detail=last_error,
                    finished_at=now_utc,
                )
                return _run_record_to_result(record)

            if not isinstance(raw_result, dict):
                record = await self._persist_run_outcome(
                    claimed.id,
                    status="failed",
                    attempt_count=attempt,
                    run_id=None,
                    error_detail="Dispatcher returned no dispatch result",
                    finished_at=now_utc,
                )
                return _run_record_to_result(record)

            reported_status = raw_result.get("status")
            reported_ok = raw_result.get("ok")
            raw_error = raw_result.get("error") or raw_result.get("error_detail")
            if reported_ok is False or reported_status in {"failed", "error", "cancelled"}:
                err_msg = str(raw_error) if raw_error else f"Dispatcher reported status '{reported_status}'"
                record = await self._persist_run_outcome(
                    claimed.id,
                    status="failed",
                    attempt_count=attempt,
                    run_id=None,
                    error_detail=err_msg,
                    finished_at=now_utc,
                )
                return _run_record_to_result(record, raw_result)

            run_id_val = raw_result.get("run_id")
            if run_id_val is not None:
                try:
                    run_id_val = _clean_optional_identifier(str(run_id_val), "run_id")
                except ContractViolation as exc:
                    record = await self._persist_run_outcome(
                        claimed.id,
                        status="failed",
                        attempt_count=attempt,
                        run_id=None,
                        error_detail=str(exc),
                        finished_at=now_utc,
                    )
                    return _run_record_to_result(record)

            if run_id_val is None and reported_status not in {"dispatched", "succeeded"}:
                record = await self._persist_run_outcome(
                    claimed.id,
                    status="failed",
                    attempt_count=attempt,
                    run_id=None,
                    error_detail="Dispatcher returned neither run_id nor valid status",
                    finished_at=now_utc,
                )
                return _run_record_to_result(record, raw_result)

            final_status: AutomationRunStatus = "succeeded" if reported_status == "succeeded" else "dispatched"
            finished = now_utc if final_status == "succeeded" else None
            try:
                record = await self._persist_run_outcome(
                    claimed.id,
                    status=final_status,
                    attempt_count=attempt,
                    run_id=run_id_val,
                    error_detail=None,
                    finished_at=finished,
                )
                if final_status == "dispatched" and self.runner is not None:
                    self._spawn_runner_task(schedule, record, raw_result)
                return _run_record_to_result(record, raw_result)
            except StorageIntegrityError as exc:
                record = await self._persist_run_outcome(
                    claimed.id,
                    status="failed",
                    attempt_count=attempt,
                    run_id=None,
                    error_detail=f"Failed persisting dispatched run_id: {exc}",
                    finished_at=now_utc,
                )
                return _run_record_to_result(record)

        # Unreachable safeguard
        record = await self._persist_run_outcome(
            claimed.id,
            status="failed",
            attempt_count=max_attempts,
            run_id=None,
            error_detail=last_error or "Dispatch exhausted retries",
            finished_at=now_utc,
        )
        return _run_record_to_result(record)

    async def tick(
        self,
        *,
        now: Optional[datetime] = None,
        require_budget: bool = False,
    ) -> List[Dict[str, Any]]:
        """Evaluate all enabled schedules due at `now` and dispatch idempotently."""
        now_utc = _ensure_utc(now or datetime.now(dt_timezone.utc))
        await self.store.initialize()

        async with self.store._connect() as db:
            sched_rows = await (
                await db.execute(
                    """
                    SELECT * FROM automation_schedules
                    WHERE enabled = 1 AND next_run_at IS NOT NULL
                    ORDER BY next_run_at ASC, id ASC
                    """
                )
            ).fetchall()
            queued_sched_rows = await (
                await db.execute(
                    """
                    SELECT DISTINCT s.id FROM automation_schedules s
                    JOIN automation_runs r ON r.schedule_id = s.id
                    WHERE s.enabled = 1 AND s.overlap_policy = 'queue'
                      AND r.status = 'pending' AND r.error_detail = ?
                    ORDER BY s.id ASC
                    """,
                    (_QUEUED_MARKER,),
                )
            ).fetchall()

        results: List[Dict[str, Any]] = []
        due_ids = [
            row["id"]
            for row in sched_rows
            if _ensure_utc(row["next_run_at"]) <= now_utc
        ]
        queued_ids = [row["id"] for row in queued_sched_rows]
        deferred_budget_err: Optional[ContractViolation] = None

        for sid in queued_ids:
            try:
                claimed_pair = await self._claim_queued_run(sid, now_utc, require_budget=require_budget)
            except ContractViolation as exc:
                if exc.code == "budget_required":
                    if deferred_budget_err is None:
                        deferred_budget_err = exc
                    continue
                raise
            if claimed_pair is not None:
                sched, queued_rec = claimed_pair
                results.append(await self._execute_claimed_run(sched, queued_rec, now_utc))

        for sid in due_ids:
            try:
                claim = await self._claim_due_occurrence(sid, now_utc, require_budget=require_budget)
            except ContractViolation as exc:
                if exc.code == "budget_required":
                    if deferred_budget_err is None:
                        deferred_budget_err = exc
                    continue
                raise
            if claim is None:
                continue
            action, schedule, record = claim
            assert record is not None
            if action == "terminal":
                results.append(_run_record_to_result(record))
            else:
                results.append(await self._execute_claimed_run(schedule, record, now_utc))

        if deferred_budget_err is not None:
            raise deferred_budget_err
        return results

    async def trigger_now(
        self,
        schedule_id: str,
        *,
        now: Optional[datetime] = None,
        force: bool = False,
        require_budget: bool = False,
    ) -> Dict[str, Any]:
        """Manually trigger a schedule immediately with a unique manual:<uuid> occurrence_key."""
        _reject_nul(schedule_id, "schedule_id")
        now_utc = _ensure_utc(now or datetime.now(dt_timezone.utc))
        effective_require_budget = bool(self.require_budget or require_budget)
        await self.store.initialize()

        queued_immediately = False
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                row = await (await db.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,))).fetchone()
                if row is None:
                    raise ContractViolation("resource_not_found", f"AutomationSchedule '{schedule_id}' does not exist")
                bp_map = await _load_schedule_budgets_in_db(db, (schedule_id,))
                schedule = _row_to_schedule(row, budget_policy=bp_map.get(schedule_id))

                if not schedule.enabled and not force:
                    raise ContractViolation(
                        "schedule_disabled",
                        f"Schedule '{schedule_id}' is disabled; resume it or pass force=True to trigger",
                    )

                if effective_require_budget:
                    await self._assert_budget_gate_in_db(
                        db,
                        project_id=schedule.project_id,
                        workspace_id=schedule.workspace_id,
                        budget_policy=schedule.budget_policy,
                        schedule_id=schedule.id,
                    )

                active_rows = await (
                    await db.execute(
                        "SELECT id, status FROM automation_runs WHERE schedule_id = ? AND status IN ('pending', 'dispatched')",
                        (schedule.id,),
                    )
                ).fetchall()

                if active_rows and schedule.overlap_policy == "skip":
                    raise ContractViolation(
                        "schedule_overlap",
                        f"AutomationSchedule '{schedule.id}' already has an active run",
                    )

                occ_key = f"manual:{new_id()}"

                if active_rows and schedule.overlap_policy == "queue":
                    queued_immediately = True
                    claimed = await self._insert_run_in_tx(
                        db,
                        schedule_id=schedule.id,
                        occurrence_key=occ_key,
                        scheduled_for=now_utc,
                        status="pending",
                        dispatched_at=now_utc,
                        error_detail=_QUEUED_MARKER,
                        finished_at=None,
                    )
                else:
                    claimed = await self._insert_run_in_tx(
                        db,
                        schedule_id=schedule.id,
                        occurrence_key=occ_key,
                        scheduled_for=now_utc,
                        status="pending",
                        dispatched_at=now_utc,
                        error_detail=None,
                        finished_at=None,
                    )
                    await db.execute(
                        "UPDATE automation_schedules SET last_run_at = ?, updated_at = ? WHERE id = ?",
                        (_utc_iso(now_utc), _utc_iso(now_utc), schedule.id),
                    )

        if queued_immediately:
            return _run_record_to_result(claimed)
        return await self._execute_claimed_run(schedule, claimed, now_utc)

    async def wait_for_active_tasks(self, *, timeout: Optional[float] = None) -> None:
        """Await all currently tracked supervised runner tasks."""
        while True:
            pending = [t for t in list(self._active_tasks) if not t.done()]
            if not pending:
                return
            if timeout is not None:
                await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
            else:
                await asyncio.gather(*pending, return_exceptions=True)

    async def _background_loop(
        self,
        stop_event: asyncio.Event,
        *,
        interval_seconds: float,
        stale_lease_seconds: float,
    ) -> None:
        while not stop_event.is_set():
            try:
                await self.reconcile_stale_runs(max_age_seconds=stale_lease_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler background stale-run reconciliation failed")

            if stop_event.is_set():
                break

            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler background tick failed")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                break
            except asyncio.TimeoutError:
                continue

    async def start_background_loop(
        self,
        *,
        interval_seconds: float = 5.0,
        stale_lease_seconds: float = 1800.0,
    ) -> None:
        """Start the periodic reconcile_stale_runs() + tick() background loop."""
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(float(interval_seconds))
            or float(interval_seconds) <= 0.0
        ):
            raise ContractViolation("invalid_schedule", "interval_seconds for background loop must be > 0")
        if (
            isinstance(stale_lease_seconds, bool)
            or not isinstance(stale_lease_seconds, (int, float))
            or math.isnan(float(stale_lease_seconds))
            or float(stale_lease_seconds) < 0.0
        ):
            raise ContractViolation("invalid_schedule", "stale_lease_seconds must be >= 0")

        if self._loop_task is not None and not self._loop_task.done():
            return

        stop_event = asyncio.Event()
        self._stop_event = stop_event
        self._loop_task = asyncio.create_task(
            self._background_loop(
                stop_event,
                interval_seconds=float(interval_seconds),
                stale_lease_seconds=float(stale_lease_seconds),
            ),
            name="hydra-scheduler-loop",
        )

    async def stop_background_loop(self) -> None:
        """Stop the periodic scheduler loop and cancel/await any in-flight tasks."""
        if self._stop_event is not None:
            self._stop_event.set()
        loop_task = self._loop_task
        self._loop_task = None
        if loop_task is not None:
            if not loop_task.done():
                loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await loop_task

        active = [t for t in list(self._active_tasks) if not t.done()]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        self._active_tasks.clear()
        self._running_automation_run_ids.clear()
        self._stop_event = None
