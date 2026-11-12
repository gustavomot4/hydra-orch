"""T21: scoped reversible preferences, immutable run snapshots, and WCAG AA accessibility contract."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Annotated, Any, Literal, Mapping, Optional, Union

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from hydra_orch.core.checkpointer import (
    ExecutionStore,
    IdempotencyConflictError,
    OptimisticLockError,
)
from hydra_orch.core.identifier import new_id
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.model import (
    ContractViolation,
    ExecutionModel,
    Identifier,
    NonEmpty,
    Sha256,
    UtcTimestamp,
)

ScopeType = Literal["user", "area", "project"]
PreferenceSource = Literal["explicit", "inferred_opt_in"]

SCOPE_PRECEDENCE: dict[ScopeType, int] = {
    "user": 1,
    "area": 2,
    "project": 3,
}

SOURCE_PRECEDENCE: dict[PreferenceSource, int] = {
    "inferred_opt_in": 1,
    "explicit": 2,
}

WCAG_AA_NORMAL_TEXT_RATIO = 4.5
WCAG_AA_LARGE_TEXT_RATIO = 3.0
WCAG_AA_UI_COMPONENT_RATIO = 3.0

ALLOWED_SEMANTIC_ROLES = frozenset(
    {
        "alert",
        "alertdialog",
        "application",
        "article",
        "banner",
        "button",
        "checkbox",
        "combobox",
        "complementary",
        "contentinfo",
        "dialog",
        "form",
        "grid",
        "gridcell",
        "heading",
        "img",
        "link",
        "list",
        "listbox",
        "listitem",
        "log",
        "main",
        "menu",
        "menubar",
        "menuitem",
        "navigation",
        "option",
        "progressbar",
        "radio",
        "radiogroup",
        "region",
        "search",
        "separator",
        "slider",
        "spinbutton",
        "status",
        "switch",
        "tab",
        "table",
        "tablist",
        "tabpanel",
        "textbox",
        "toolbar",
        "tooltip",
        "tree",
        "treeitem",
    }
)

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_PREFERENCE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def canonical_json(value: Any) -> str:
    """Serialize value as deterministic UTF-8 canonical JSON without NaN/Infinity."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _contains_secret_key_or_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_str = str(key)
            if redact({key_str: "probe_secret_value"}) != {key_str: "probe_secret_value"}:
                return True
            if _contains_secret_key_or_value(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_key_or_value(item) for item in value)
    return False


def _validate_preference_value(value: Any) -> str:
    try:
        serialized = canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ContractViolation(
            "preference_invalid",
            f"Preference value must be finite JSON-serializable data: {exc}",
        ) from exc
    if redact(value) != value or redact_text(serialized) != serialized or _contains_secret_key_or_value(value):
        raise ContractViolation(
            "secret_in_preference",
            "Preference values cannot contain secrets or credentials",
        )
    return serialized


def _validate_safe_identifier(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not _PREFERENCE_KEY_RE.fullmatch(value)
        or redact(value) != value
        or redact_text(value) != value
    ):
        raise ContractViolation(
            "preference_invalid",
            f"Invalid {field_name}: must be a clean identifier without secrets",
        )
    return value


def _validate_actor(actor: str) -> str:
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or redact(actor) != actor
        or redact_text(actor) != actor
    ):
        raise ContractViolation(
            "preference_invalid",
            "Actor must be a non-empty identifier without credentials",
        )
    return actor.strip()


class Preference(ExecutionModel):
    preference_id: Identifier
    scope_type: ScopeType
    scope_id: Identifier
    key: Identifier
    value_json: NonEmpty
    source: PreferenceSource
    version: int = Field(default=1, ge=1, strict=True)
    created_at: Optional[UtcTimestamp] = None
    updated_at: Optional[UtcTimestamp] = None

    @model_validator(mode="after")
    def validate_payload(self) -> Preference:
        try:
            parsed = json.loads(self.value_json)
        except ValueError as exc:
            raise ValueError("Preference value_json must be valid JSON") from exc
        if canonical_json(parsed) != self.value_json:
            raise ValueError("Preference value_json must be canonical JSON")
        if redact(parsed) != parsed or _contains_secret_key_or_value(parsed):
            raise ValueError("Preference values cannot contain raw credentials")
        return self

    @property
    def value(self) -> Any:
        """Return a fresh decoded JSON value to preserve frozen DTO immutability."""
        return json.loads(self.value_json)


class PreferenceSnapshot(ExecutionModel):
    snapshot_id: Identifier
    run_id: Identifier
    preferences_hash: Sha256
    resolved_preferences_json: NonEmpty
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def verify_integrity(self) -> PreferenceSnapshot:
        try:
            data = json.loads(self.resolved_preferences_json)
        except ValueError as exc:
            raise ValueError("Preference snapshot payload must be valid JSON") from exc
        if (
            canonical_json(data) != self.resolved_preferences_json
            or hashlib.sha256(self.resolved_preferences_json.encode("utf-8")).hexdigest() != self.preferences_hash
            or not isinstance(data, dict)
            or not isinstance(data.get("preferences"), dict)
        ):
            raise ValueError("Preference snapshot integrity mismatch")
        return self

    @property
    def resolved_preferences(self) -> dict[str, Any]:
        """Return a fresh copy of the full canonical snapshot payload."""
        return json.loads(self.resolved_preferences_json)

    @property
    def preferences(self) -> dict[str, Any]:
        """Return a fresh copy of the effective key-value map."""
        return json.loads(self.resolved_preferences_json)["preferences"]


class PreferenceService:
    """Manages scoped, versioned, reversible preferences and immutable run snapshots."""

    def __init__(self, store: ExecutionStore):
        self.store = store

    @staticmethod
    def _from_row(row: Any) -> Preference:
        return Preference(
            preference_id=row["id"],
            scope_type=row["scope_type"],
            scope_id=row["scope_id"],
            key=row["key"],
            value_json=row["value_json"],
            source=row["source"],
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _snapshot_from_row(row: Any) -> PreferenceSnapshot:
        try:
            return PreferenceSnapshot(
                snapshot_id=row["id"],
                run_id=row["run_id"],
                preferences_hash=row["preferences_hash"],
                resolved_preferences_json=row["resolved_preferences_json"],
                created_at=row["created_at"],
            )
        except (ValueError, KeyError, TypeError):
            raise ContractViolation(
                "preference_integrity",
                "Stored preference snapshot failed integrity verification",
            ) from None

    async def set_preference(
        self,
        scope_type: ScopeType,
        scope_id: str,
        key: str,
        value: Any,
        *,
        source: PreferenceSource = "explicit",
        opt_in: bool = False,
        actor: str = "operator",
        expected_version: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Preference:
        if scope_type not in SCOPE_PRECEDENCE:
            raise ContractViolation("preference_invalid", f"Unsupported preference scope_type: {scope_type}")
        if source not in SOURCE_PRECEDENCE:
            raise ContractViolation("preference_invalid", f"Unsupported preference source: {source}")
        if source == "inferred_opt_in" and opt_in is not True:
            raise ContractViolation(
                "opt_in_required",
                "Inferred preferences require explicit opt_in=True",
            )
        clean_scope_id = _validate_safe_identifier(scope_id, "scope_id")
        clean_key = _validate_safe_identifier(key, "key")
        clean_actor = _validate_actor(actor)
        value_json = _validate_preference_value(value)

        request_hash = self.store.compute_request_hash(
            {
                "op": "set_preference",
                "scope_type": scope_type,
                "scope_id": clean_scope_id,
                "key": clean_key,
                "value_json": value_json,
                "source": source,
                "opt_in": opt_in,
                "actor": clean_actor,
                "expected_version": expected_version,
            }
        )

        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                if idempotency_key is not None:
                    existing_cmd = await (
                        await db.execute(
                            "SELECT request_hash, response_json FROM commands WHERE scope = 'preferences' AND idempotency_key = ?",
                            (idempotency_key,),
                        )
                    ).fetchone()
                    if existing_cmd is not None:
                        if existing_cmd["request_hash"] != request_hash:
                            raise IdempotencyConflictError(
                                f"Idempotency key '{idempotency_key}' in scope 'preferences' was already used with a different payload"
                            )
                        recorded = json.loads(existing_cmd["response_json"])
                        row = await (
                            await db.execute(
                                "SELECT * FROM preferences WHERE id = ?",
                                (recorded["preference_id"],),
                            )
                        ).fetchone()
                        if row is not None:
                            return self._from_row(row)

                existing = await (
                    await db.execute(
                        "SELECT * FROM preferences WHERE scope_type = ? AND scope_id = ? AND key = ?",
                        (scope_type, clean_scope_id, clean_key),
                    )
                ).fetchone()

                now_iso = datetime.now(timezone.utc).isoformat()
                if existing is None:
                    if expected_version is not None and expected_version != 0:
                        raise OptimisticLockError(
                            f"Expected version {expected_version} for missing preference '{clean_key}'"
                        )
                    pref_id = new_id()
                    await db.execute(
                        """
                        INSERT INTO preferences (id, scope_type, scope_id, key, value_json, source, version, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (pref_id, scope_type, clean_scope_id, clean_key, value_json, source, now_iso, now_iso),
                    )
                    audit_payload = {
                        "action": "set",
                        "preference_id": pref_id,
                        "scope_type": scope_type,
                        "scope_id": clean_scope_id,
                        "key": clean_key,
                        "actor": clean_actor,
                        "previous_state": None,
                        "new_state": {
                            "value_json": value_json,
                            "source": source,
                            "version": 1,
                        },
                    }
                else:
                    if existing["source"] == "explicit" and source == "inferred_opt_in":
                        raise ContractViolation(
                            "explicit_preference_precedence",
                            f"Inferred preference cannot overwrite explicit preference '{clean_key}'",
                        )
                    current_version = int(existing["version"])
                    if expected_version is not None and current_version != expected_version:
                        raise OptimisticLockError(
                            f"Preference '{clean_key}' version changed: expected {expected_version}, found {current_version}"
                        )
                    pref_id = existing["id"]
                    new_version = current_version + 1
                    await db.execute(
                        """
                        UPDATE preferences
                        SET value_json = ?, source = ?, version = ?, updated_at = ?
                        WHERE id = ? AND version = ?
                        """,
                        (value_json, source, new_version, now_iso, pref_id, current_version),
                    )
                    audit_payload = {
                        "action": "set",
                        "preference_id": pref_id,
                        "scope_type": scope_type,
                        "scope_id": clean_scope_id,
                        "key": clean_key,
                        "actor": clean_actor,
                        "previous_state": {
                            "value_json": existing["value_json"],
                            "source": existing["source"],
                            "version": current_version,
                        },
                        "new_state": {
                            "value_json": value_json,
                            "source": source,
                            "version": new_version,
                        },
                    }

                await self.store._record_command_in_tx(
                    db,
                    scope="preferences",
                    idempotency_key=idempotency_key or new_id(),
                    request_hash=request_hash,
                    response_payload=audit_payload,
                )
                saved = await (await db.execute("SELECT * FROM preferences WHERE id = ?", (pref_id,))).fetchone()
                return self._from_row(saved)

    async def get_preference(self, scope_type: ScopeType, scope_id: str, key: str) -> Optional[Preference]:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM preferences WHERE scope_type = ? AND scope_id = ? AND key = ?",
                    (scope_type, scope_id, key),
                )
            ).fetchone()
        return self._from_row(row) if row is not None else None

    async def list_preferences(
        self,
        *,
        scope_type: Optional[ScopeType] = None,
        scope_id: Optional[str] = None,
    ) -> tuple[Preference, ...]:
        await self.store.initialize()
        query = "SELECT * FROM preferences WHERE 1=1"
        params: list[Any] = []
        if scope_type is not None:
            query += " AND scope_type = ?"
            params.append(scope_type)
        if scope_id is not None:
            query += " AND scope_id = ?"
            params.append(scope_id)
        query += " ORDER BY scope_type ASC, scope_id ASC, key ASC"
        async with self.store._connect() as db:
            rows = await (await db.execute(query, tuple(params))).fetchall()
        return tuple(self._from_row(row) for row in rows)

    async def get_history(self, scope_type: ScopeType, scope_id: str, key: str) -> list[dict[str, Any]]:
        await self.store.initialize()
        async with self.store._connect() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT id, idempotency_key, response_json, created_at
                    FROM commands
                    WHERE scope = 'preferences'
                      AND json_extract(response_json, '$.scope_type') = ?
                      AND json_extract(response_json, '$.scope_id') = ?
                      AND json_extract(response_json, '$.key') = ?
                    ORDER BY rowid ASC
                    """,
                    (scope_type, scope_id, key),
                )
            ).fetchall()
        return [
            {
                "command_id": row["id"],
                "idempotency_key": row["idempotency_key"],
                "created_at": row["created_at"],
                **json.loads(row["response_json"]),
            }
            for row in rows
        ]

    async def revert_preference(
        self,
        scope_type: ScopeType,
        scope_id: str,
        key: str,
        *,
        target_version: Optional[int] = None,
        actor: str = "operator",
        expected_version: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[Preference]:
        clean_actor = _validate_actor(actor)
        request_hash = self.store.compute_request_hash(
            {
                "op": "revert_preference",
                "scope_type": scope_type,
                "scope_id": scope_id,
                "key": key,
                "target_version": target_version,
                "actor": clean_actor,
                "expected_version": expected_version,
            }
        )
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                if idempotency_key is not None:
                    existing_cmd = await (
                        await db.execute(
                            "SELECT request_hash, response_json FROM commands WHERE scope = 'preferences' AND idempotency_key = ?",
                            (idempotency_key,),
                        )
                    ).fetchone()
                    if existing_cmd is not None:
                        if existing_cmd["request_hash"] != request_hash:
                            raise IdempotencyConflictError(
                                f"Idempotency key '{idempotency_key}' in scope 'preferences' was already used with a different payload"
                            )
                        recorded = json.loads(existing_cmd["response_json"])
                        if recorded.get("new_state") is None:
                            return None
                        row = await (
                            await db.execute(
                                "SELECT * FROM preferences WHERE id = ?",
                                (recorded["preference_id"],),
                            )
                        ).fetchone()
                        return self._from_row(row) if row is not None else None

                current = await (
                    await db.execute(
                        "SELECT * FROM preferences WHERE scope_type = ? AND scope_id = ? AND key = ?",
                        (scope_type, scope_id, key),
                    )
                ).fetchone()
                if current is None:
                    raise ContractViolation("resource_not_found", f"Preference '{key}' does not exist")

                current_version = int(current["version"])
                if expected_version is not None and current_version != expected_version:
                    raise OptimisticLockError(
                        f"Preference '{key}' version changed: expected {expected_version}, found {current_version}"
                    )

                history_rows = await (
                    await db.execute(
                        """
                        SELECT response_json
                        FROM commands
                        WHERE scope = 'preferences'
                          AND json_extract(response_json, '$.scope_type') = ?
                          AND json_extract(response_json, '$.scope_id') = ?
                          AND json_extract(response_json, '$.key') = ?
                        ORDER BY rowid DESC
                        """,
                        (scope_type, scope_id, key),
                    )
                ).fetchall()
                history = [json.loads(r["response_json"]) for r in history_rows]

                restore_state: Optional[dict[str, Any]] = None
                reverted_to_version: int
                if target_version is None:
                    matched = next(
                        (
                            entry
                            for entry in history
                            if isinstance(entry.get("new_state"), dict)
                            and entry["new_state"].get("version") == current_version
                        ),
                        None,
                    )
                    if matched is None:
                        raise ContractViolation(
                            "preference_revert_unavailable",
                            f"No audit entry found for preference '{key}' version {current_version}",
                        )
                    restore_state = matched.get("previous_state")
                    reverted_to_version = 0 if restore_state is None else int(restore_state["version"])
                else:
                    if target_version < 1 or target_version >= current_version:
                        raise ContractViolation(
                            "preference_revert_unavailable",
                            f"Invalid target_version {target_version} for preference at version {current_version}",
                        )
                    matched = next(
                        (
                            entry
                            for entry in history
                            if isinstance(entry.get("new_state"), dict)
                            and entry["new_state"].get("version") == target_version
                        ),
                        None,
                    )
                    if matched is None:
                        raise ContractViolation(
                            "preference_revert_unavailable",
                            f"Target version {target_version} not found in audit history for '{key}'",
                        )
                    restore_state = matched["new_state"]
                    reverted_to_version = target_version

                previous_snapshot = {
                    "value_json": current["value_json"],
                    "source": current["source"],
                    "version": current_version,
                }
                now_iso = datetime.now(timezone.utc).isoformat()

                if restore_state is None:
                    await db.execute(
                        "DELETE FROM preferences WHERE id = ? AND version = ?",
                        (current["id"], current_version),
                    )
                    audit_payload = {
                        "action": "reverted",
                        "preference_id": current["id"],
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "key": key,
                        "actor": clean_actor,
                        "reverted_to_version": 0,
                        "previous_state": previous_snapshot,
                        "new_state": None,
                    }
                    await self.store._record_command_in_tx(
                        db,
                        scope="preferences",
                        idempotency_key=idempotency_key or new_id(),
                        request_hash=request_hash,
                        response_payload=audit_payload,
                    )
                    return None

                new_version = current_version + 1
                await db.execute(
                    """
                    UPDATE preferences
                    SET value_json = ?, source = ?, version = ?, updated_at = ?
                    WHERE id = ? AND version = ?
                    """,
                    (
                        restore_state["value_json"],
                        restore_state["source"],
                        new_version,
                        now_iso,
                        current["id"],
                        current_version,
                    ),
                )
                audit_payload = {
                    "action": "reverted",
                    "preference_id": current["id"],
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "key": key,
                    "actor": clean_actor,
                    "reverted_to_version": reverted_to_version,
                    "previous_state": previous_snapshot,
                    "new_state": {
                        "value_json": restore_state["value_json"],
                        "source": restore_state["source"],
                        "version": new_version,
                    },
                }
                await self.store._record_command_in_tx(
                    db,
                    scope="preferences",
                    idempotency_key=idempotency_key or new_id(),
                    request_hash=request_hash,
                    response_payload=audit_payload,
                )
                updated = await (
                    await db.execute("SELECT * FROM preferences WHERE id = ?", (current["id"],))
                ).fetchone()
                return self._from_row(updated)

    async def _resolve_in_db(
        self,
        db: Any,
        *,
        user_id: Optional[str],
        area_id: Optional[str],
        project_id: Optional[str],
    ) -> dict[str, Preference]:
        clauses: list[str] = []
        params: list[str] = []
        for scope_type, scope_id in (("user", user_id), ("area", area_id), ("project", project_id)):
            if scope_id is not None:
                clauses.append("(scope_type = ? AND scope_id = ?)")
                params.extend((scope_type, scope_id))
        if not clauses:
            return {}
        rows = await (
            await db.execute(
                f"SELECT * FROM preferences WHERE {' OR '.join(clauses)}",
                tuple(params),
            )
        ).fetchall()
        winners: dict[str, Preference] = {}
        for row in rows:
            pref = self._from_row(row)
            existing = winners.get(pref.key)
            if existing is None:
                winners[pref.key] = pref
                continue
            cand_rank = (SOURCE_PRECEDENCE[pref.source], SCOPE_PRECEDENCE[pref.scope_type])
            curr_rank = (SOURCE_PRECEDENCE[existing.source], SCOPE_PRECEDENCE[existing.scope_type])
            if cand_rank > curr_rank:
                winners[pref.key] = pref
        return dict(sorted(winners.items()))

    async def resolve_effective_entries(
        self,
        *,
        user_id: Optional[str] = None,
        area_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> dict[str, Preference]:
        await self.store.initialize()
        async with self.store._connect() as db:
            return await self._resolve_in_db(db, user_id=user_id, area_id=area_id, project_id=project_id)

    async def resolve_effective(
        self,
        *,
        user_id: Optional[str] = None,
        area_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Resolve effective preferences with precedence explicit > inferred_opt_in and project > area > user."""
        winners = await self.resolve_effective_entries(
            user_id=user_id,
            area_id=area_id,
            project_id=project_id,
        )
        return {key: pref.value for key, pref in winners.items()}

    async def snapshot_for_run(
        self,
        run_id: str,
        *,
        user_id: Optional[str] = None,
        area_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> PreferenceSnapshot:
        """Compute canonical UTF-8 JSON + SHA-256 hash and persist an immutable PreferenceSnapshot."""
        await self.store.initialize()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                run = await (await db.execute("SELECT id, status FROM runs WHERE id = ?", (run_id,))).fetchone()
                if run is None:
                    raise ContractViolation("resource_not_found", f"Run '{run_id}' does not exist")

                winners = await self._resolve_in_db(
                    db,
                    user_id=user_id,
                    area_id=area_id,
                    project_id=project_id,
                )
                payload = {
                    "schema_version": "1.0",
                    "scopes": {
                        "user_id": user_id,
                        "area_id": area_id,
                        "project_id": project_id,
                    },
                    "preferences": {key: pref.value for key, pref in winners.items()},
                    "provenance": {
                        key: {
                            "preference_id": pref.preference_id,
                            "scope_type": pref.scope_type,
                            "scope_id": pref.scope_id,
                            "source": pref.source,
                            "version": pref.version,
                        }
                        for key, pref in winners.items()
                    },
                }
                encoded_json = canonical_json(payload)
                digest = hashlib.sha256(encoded_json.encode("utf-8")).hexdigest()

                existing = await (
                    await db.execute("SELECT * FROM preference_snapshots WHERE run_id = ?", (run_id,))
                ).fetchone()
                if existing is not None:
                    existing_snap = self._snapshot_from_row(existing)
                    if existing_snap.preferences_hash != digest:
                        raise ContractViolation(
                            "preference_snapshot_conflict",
                            f"Run '{run_id}' already has an immutable preference snapshot with divergent configuration",
                        )
                    return existing_snap

                if run["status"] not in {"queued", "running", "waiting"}:
                    raise ContractViolation(
                        "preference_snapshot_late",
                        f"Cannot create preference snapshot for run in terminal status '{run['status']}'",
                    )

                snapshot_id = new_id()
                created_at = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    """
                    INSERT INTO preference_snapshots (id, run_id, preferences_hash, resolved_preferences_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, run_id, digest, encoded_json, created_at),
                )
                await self.store._insert_event_in_tx(
                    db,
                    run_id=run_id,
                    event_type="preference.snapshot_created",
                    payload={
                        "preference_snapshot_id": snapshot_id,
                        "preferences_hash": digest,
                    },
                )
                row = await (
                    await db.execute("SELECT * FROM preference_snapshots WHERE id = ?", (snapshot_id,))
                ).fetchone()
                return self._snapshot_from_row(row)

    async def get_snapshot(self, run_id: str) -> PreferenceSnapshot:
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (
                await db.execute("SELECT * FROM preference_snapshots WHERE run_id = ?", (run_id,))
            ).fetchone()
        if row is None:
            raise ContractViolation("resource_not_found", f"Preference snapshot for run '{run_id}' does not exist")
        return self._snapshot_from_row(row)


# ---------------------------------------------------------------------------
# Verifiable WCAG AA Accessibility Contract & UI Authority Guard (RF23 / RT23)
# ---------------------------------------------------------------------------


def parse_hex_color(color: str) -> tuple[int, int, int]:
    """Parse #RGB or #RRGGBB hex color into 8-bit (r, g, b) channels."""
    if not isinstance(color, str) or not _HEX_COLOR_RE.fullmatch(color.strip()):
        raise ValueError(f"Expected #RGB or #RRGGBB hex color, got {color!r}")
    digits = color.strip()[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _linearize_channel(channel_8bit: int) -> float:
    srgb = channel_8bit / 255.0
    if srgb <= 0.04045:
        return srgb / 12.92
    return ((srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """Compute WCAG 2.1 relative luminance in [0.0, 1.0] for an sRGB hex color."""
    r, g, b = parse_hex_color(color)
    return (
        0.2126 * _linearize_channel(r)
        + 0.7152 * _linearize_channel(g)
        + 0.0722 * _linearize_channel(b)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    """Compute WCAG 2.1 contrast ratio in [1.0, 21.0] between two hex colors."""
    lum_fg = relative_luminance(foreground)
    lum_bg = relative_luminance(background)
    lighter = max(lum_fg, lum_bg)
    darker = min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


class ColorTokenPair(ExecutionModel):
    name: NonEmpty
    foreground: str
    background: str
    kind: Literal["normal_text", "large_text", "ui_component"] = "normal_text"

    @field_validator("foreground", "background")
    @classmethod
    def check_hex(cls, value: str) -> str:
        parse_hex_color(value)
        return value.strip().lower()

    @property
    def min_ratio(self) -> float:
        return WCAG_AA_NORMAL_TEXT_RATIO if self.kind == "normal_text" else WCAG_AA_LARGE_TEXT_RATIO

    @property
    def ratio(self) -> float:
        return contrast_ratio(self.foreground, self.background)

    @property
    def passes_wcag_aa(self) -> bool:
        return self.ratio >= self.min_ratio


class ControlA11yDescriptor(ExecutionModel):
    control_id: Identifier
    role: NonEmpty
    label: NonEmpty
    keyboard_accessible: bool = True
    tab_index: Optional[int] = Field(default=0, strict=True)
    focus_visible: bool = True
    has_status_indicator: bool = False
    status_text: Optional[str] = None
    animated: bool = False
    respects_reduce_motion: bool = True


def _default_color_pairs() -> tuple[ColorTokenPair, ...]:
    return (
        ColorTokenPair(name="primary_text", foreground="#eeeeee", background="#141414", kind="normal_text"),
        ColorTokenPair(name="secondary_text", foreground="#b0b0b0", background="#202020", kind="normal_text"),
        ColorTokenPair(name="large_heading", foreground="#eeeeee", background="#292929", kind="large_text"),
        ColorTokenPair(name="focus_ring", foreground="#60a5fa", background="#141414", kind="ui_component"),
    )


class AccessibilitySettings(ExecutionModel):
    keyboard_navigation: bool = True
    focus_visible: bool = True
    focus_outline_px: int = Field(default=2, ge=0, strict=True)
    semantic_roles: bool = True
    textual_status_labels: bool = True
    reduce_motion: bool = False
    respects_prefers_reduced_motion: bool = True
    zoom_support_pct: int = Field(default=200, ge=100, strict=True)
    color_pairs: tuple[ColorTokenPair, ...] = Field(default_factory=_default_color_pairs)
    controls: tuple[ControlA11yDescriptor, ...] = ()


class AccessibilityCheckItem(ExecutionModel):
    criterion: Literal[
        "keyboard_navigation",
        "focus_visible",
        "semantic_roles",
        "textual_status_labels",
        "contrast_wcag_aa",
        "reduce_motion",
    ]
    passed: bool
    detail: NonEmpty


class AccessibilityChecklist(ExecutionModel):
    wcag_level: Literal["AA"] = "AA"
    passed: bool
    items: tuple[AccessibilityCheckItem, ...]
    violations: tuple[str, ...] = ()
    contrast_results: dict[str, float]
    reduce_motion_active: bool
    effective_animation_ms: int = Field(ge=0, strict=True)


def validate_a11y_contract(
    settings: AccessibilitySettings,
    *,
    raise_on_failure: bool = True,
) -> AccessibilityChecklist:
    """Validate WCAG AA accessibility requirements and return a structured checklist."""
    violations: list[str] = []
    items: list[AccessibilityCheckItem] = []

    # 1. Keyboard navigation
    kb_failures = [
        ctrl.control_id
        for ctrl in settings.controls
        if not ctrl.keyboard_accessible or (ctrl.tab_index is not None and ctrl.tab_index < -1)
    ]
    kb_ok = settings.keyboard_navigation and not kb_failures
    kb_detail = (
        "All interactive controls reachable via keyboard"
        if kb_ok
        else f"Keyboard navigation disabled or unreachable controls: {kb_failures}"
    )
    items.append(AccessibilityCheckItem(criterion="keyboard_navigation", passed=kb_ok, detail=kb_detail))
    if not kb_ok:
        violations.append(kb_detail)

    # 2. Visible focus indicator
    focus_failures = [ctrl.control_id for ctrl in settings.controls if not ctrl.focus_visible]
    focus_ok = settings.focus_visible and settings.focus_outline_px >= 1 and not focus_failures
    focus_detail = (
        f"Focus indicator visible ({settings.focus_outline_px}px)"
        if focus_ok
        else f"Visible focus requirement failed (outline={settings.focus_outline_px}px, controls={focus_failures})"
    )
    items.append(AccessibilityCheckItem(criterion="focus_visible", passed=focus_ok, detail=focus_detail))
    if not focus_ok:
        violations.append(focus_detail)

    # 3. Semantic roles & accessible names
    role_failures = [
        f"{ctrl.control_id}:{ctrl.role}"
        for ctrl in settings.controls
        if ctrl.role.strip().lower() not in ALLOWED_SEMANTIC_ROLES
    ]
    roles_ok = settings.semantic_roles and not role_failures
    roles_detail = (
        "Valid semantic ARIA roles and accessible labels present"
        if roles_ok
        else f"Semantic roles disabled or invalid roles: {role_failures}"
    )
    items.append(AccessibilityCheckItem(criterion="semantic_roles", passed=roles_ok, detail=roles_detail))
    if not roles_ok:
        violations.append(roles_detail)

    # 4. Textual status labels (never rely on color alone)
    status_failures = [
        ctrl.control_id
        for ctrl in settings.controls
        if ctrl.has_status_indicator and (not ctrl.status_text or not ctrl.status_text.strip())
    ]
    status_ok = settings.textual_status_labels and not status_failures
    status_detail = (
        "Status communicated via explicit text labels beyond color"
        if status_ok
        else f"Color-only status detected without textual label: {status_failures}"
    )
    items.append(AccessibilityCheckItem(criterion="textual_status_labels", passed=status_ok, detail=status_detail))
    if not status_ok:
        violations.append(status_detail)

    # 5. WCAG AA contrast ratios
    contrast_results: dict[str, float] = {}
    contrast_failures: list[str] = []
    for pair in settings.color_pairs:
        ratio = round(pair.ratio, 4)
        contrast_results[pair.name] = ratio
        if pair.ratio < pair.min_ratio:
            contrast_failures.append(f"{pair.name}={ratio:.2f}:1 (<{pair.min_ratio:.1f}:1)")
    contrast_ok = bool(settings.color_pairs) and not contrast_failures
    contrast_detail = (
        "All color pairs meet WCAG AA contrast thresholds"
        if contrast_ok
        else f"WCAG AA contrast violations: {', '.join(contrast_failures) or 'no color pairs defined'}"
    )
    items.append(AccessibilityCheckItem(criterion="contrast_wcag_aa", passed=contrast_ok, detail=contrast_detail))
    if not contrast_ok:
        violations.append(contrast_detail)

    # 6. Reduce motion
    motion_failures = [
        ctrl.control_id
        for ctrl in settings.controls
        if settings.reduce_motion and ctrl.animated and not ctrl.respects_reduce_motion
    ]
    motion_ok = settings.respects_prefers_reduced_motion and not motion_failures
    effective_animation_ms = 0 if (settings.reduce_motion and motion_ok) else 150
    motion_detail = (
        f"Reduced motion honored (reduce_motion={settings.reduce_motion}, animation_ms={effective_animation_ms})"
        if motion_ok
        else f"Reduced motion preference ignored by controls: {motion_failures}"
    )
    items.append(AccessibilityCheckItem(criterion="reduce_motion", passed=motion_ok, detail=motion_detail))
    if not motion_ok:
        violations.append(motion_detail)

    checklist = AccessibilityChecklist(
        passed=not violations,
        items=tuple(items),
        violations=tuple(violations),
        contrast_results=contrast_results,
        reduce_motion_active=settings.reduce_motion,
        effective_animation_ms=effective_animation_ms,
    )
    if violations and raise_on_failure:
        raise ContractViolation("a11y_contract_violation", "; ".join(violations))
    return checklist


class UiCommandEnvelope(ExecutionModel):
    command_id: Identifier
    command_version: Literal["1.0"] = "1.0"
    action: Literal[
        "accept_task",
        "reject_task",
        "approve_hitl",
        "update_preference",
        "revert_preference",
    ]
    actor: NonEmpty
    idempotency_key: Annotated[str, StringConstraints(min_length=16, max_length=64)]
    expected_revision: Optional[int] = Field(default=None, ge=1, strict=True)
    payload: dict[str, Any] = Field(default_factory=dict)


def assert_ui_command_authorized(
    command: Optional[Union[UiCommandEnvelope, Mapping[str, Any]]],
    *,
    action: str = "accept_task",
    authenticated_actor: Optional[str] = None,
) -> UiCommandEnvelope:
    """Enforce that UI cannot accept tasks or mutate state without an explicit versioned command."""
    if command is None:
        raise ContractViolation(
            "ui_command_required",
            "UI cannot approve or accept state without an explicit versioned command",
        )
    if isinstance(command, UiCommandEnvelope):
        envelope = command
    elif isinstance(command, Mapping):
        if "command_version" not in command or "command_id" not in command or "idempotency_key" not in command:
            raise ContractViolation(
                "ui_command_invalid",
                "UI state mutation rejected: missing versioned command envelope fields",
            )
        try:
            envelope = UiCommandEnvelope.model_validate(dict(command))
        except ValidationError as exc:
            raise ContractViolation(
                "ui_command_invalid",
                f"Invalid UI command envelope: {exc}",
            ) from exc
    else:
        raise ContractViolation(
            "ui_command_invalid",
            "UI command must be a UiCommandEnvelope or mapping",
        )

    if envelope.action != action:
        raise ContractViolation(
            "ui_command_invalid",
            f"Expected UI command action '{action}', got '{envelope.action}'",
        )
    if authenticated_actor is not None and envelope.actor != authenticated_actor:
        raise ContractViolation(
            "authorization_denied",
            "UI command actor does not match authenticated principal",
        )
    if envelope.action in {"accept_task", "reject_task"}:
        if envelope.expected_revision is None:
            raise ContractViolation(
                "ui_command_invalid",
                f"UI command '{envelope.action}' requires explicit expected_revision",
            )
        result_id = envelope.payload.get("result_id")
        reason = envelope.payload.get("reason")
        if not isinstance(result_id, str) or not result_id.strip() or not isinstance(reason, str) or not reason.strip():
            raise ContractViolation(
                "ui_command_invalid",
                f"UI command '{envelope.action}' requires non-empty result_id and reason",
            )
    dumped = envelope.model_dump(mode="json")
    if redact(dumped) != dumped or _contains_secret_key_or_value(dumped):
        raise ContractViolation(
            "secret_in_command",
            "UI command cannot embed raw credentials",
        )
    return envelope


__all__ = [
    "ALLOWED_SEMANTIC_ROLES",
    "AccessibilityCheckItem",
    "AccessibilityChecklist",
    "AccessibilitySettings",
    "ColorTokenPair",
    "ControlA11yDescriptor",
    "Preference",
    "PreferenceService",
    "PreferenceSnapshot",
    "PreferenceSource",
    "SCOPE_PRECEDENCE",
    "SOURCE_PRECEDENCE",
    "ScopeType",
    "UiCommandEnvelope",
    "WCAG_AA_LARGE_TEXT_RATIO",
    "WCAG_AA_NORMAL_TEXT_RATIO",
    "WCAG_AA_UI_COMPONENT_RATIO",
    "assert_ui_command_authorized",
    "canonical_json",
    "contrast_ratio",
    "parse_hex_color",
    "relative_luminance",
    "validate_a11y_contract",
]
