"""T21: hermetic tests for scoped, reversible preferences and immutable run snapshots."""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from hydra_orch.core.checkpointer import (
    ExecutionStore,
    IdempotencyConflictError,
    OptimisticLockError,
)
from hydra_orch.core.preferences import PreferenceService, PreferenceSnapshot, canonical_json
from hydra_orch.model import CheckSpec, ContractViolation, RunSpec, TaskSpec

BASE_SHA = "a" * 40


def _make_run_spec(
    repo_root: str,
    *,
    run_id: str = "run-pref-001",
    project_id: str = "proj-pref-001",
    idempotency_key: str = "pref-run-idemp-0001",
) -> RunSpec:
    task = TaskSpec(
        task_id=f"{run_id}-t1",
        run_id=run_id,
        objective="Verify preference snapshot behavior",
        assigned_executor="codex",
        acceptance_criteria=(
            CheckSpec(check_id="unit", command=("python", "-m", "pytest", "tests/test_preferences.py")),
        ),
        allowed_paths=("src/hydra_orch/core/preferences.py",),
    )
    return RunSpec(
        run_id=run_id,
        project_id=project_id,
        objective="Preference snapshot test run",
        repo_root=repo_root,
        base_sha=BASE_SHA,
        base_branch="main",
        orchestration_mode="relay",
        idempotency_key=idempotency_key,
        tasks=(task,),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scoped_reversible(tmp_path):
    store = ExecutionStore(tmp_path / "prefs.sqlite")
    service = PreferenceService(store)

    # Scoped precedence: project > area > user
    user_pref = await service.set_preference("user", "operator", "ui.theme", "light", source="explicit")
    assert user_pref.version == 1
    assert user_pref.value == "light"

    await service.set_preference("area", "area-1", "ui.theme", "high-contrast", source="explicit")
    await service.set_preference("project", "proj-1", "ui.theme", "dark", source="explicit")
    await service.set_preference("user", "operator", "a11y.reduce_motion", True, source="explicit")

    effective = await service.resolve_effective(
        user_id="operator",
        area_id="area-1",
        project_id="proj-1",
    )
    assert effective == {
        "a11y.reduce_motion": True,
        "ui.theme": "dark",
    }

    # Update project preference to v2 and v3, then test optimistic lock
    v2 = await service.set_preference(
        "project",
        "proj-1",
        "ui.theme",
        "solarized",
        source="explicit",
        expected_version=1,
    )
    assert v2.version == 2
    assert v2.value == "solarized"

    with pytest.raises(OptimisticLockError):
        await service.set_preference(
            "project",
            "proj-1",
            "ui.theme",
            "nord",
            source="explicit",
            expected_version=1,
        )

    v3 = await service.set_preference(
        "project",
        "proj-1",
        "ui.theme",
        "nord",
        source="explicit",
        expected_version=2,
    )
    assert v3.version == 3

    # Revert v3 -> restores v2 value ("solarized") with monotonic version 4
    reverted = await service.revert_preference("project", "proj-1", "ui.theme", expected_version=3)
    assert reverted is not None
    assert reverted.version == 4
    assert reverted.value == "solarized"
    assert reverted.source == "explicit"

    # Revert explicitly to target_version=1 -> restores "dark" at version 5
    reverted_v1 = await service.revert_preference("project", "proj-1", "ui.theme", target_version=1)
    assert reverted_v1 is not None
    assert reverted_v1.version == 5
    assert reverted_v1.value == "dark"

    # Reverting an initial v1 preference removes it and records audit
    removed = await service.revert_preference("user", "operator", "a11y.reduce_motion")
    assert removed is None
    assert await service.get_preference("user", "operator", "a11y.reduce_motion") is None

    # Restart persistence & audit trail in commands(scope='preferences')
    restarted = PreferenceService(ExecutionStore(tmp_path / "prefs.sqlite"))
    persisted = await restarted.get_preference("project", "proj-1", "ui.theme")
    assert persisted is not None
    assert persisted.value == "dark"
    assert persisted.version == 5

    history = await restarted.get_history("project", "proj-1", "ui.theme")
    assert [item["action"] for item in history] == ["set", "set", "set", "reverted", "reverted"]

    async with restarted.store._connect() as db:
        cmd_count = (
            await (await db.execute("SELECT COUNT(*) FROM commands WHERE scope = 'preferences'")).fetchone()
        )[0]
    assert cmd_count == 9


@pytest.mark.unit
@pytest.mark.asyncio
async def test_snapshot_immutable(tmp_path):
    repo_root = str((tmp_path / "repo").resolve())
    store = ExecutionStore(tmp_path / "snapshots.sqlite")
    run_spec = _make_run_spec(repo_root)
    await store.save_run_atomic(run_spec)

    service = PreferenceService(store)
    await service.set_preference("user", "operator", "ui.theme", "dark", source="explicit")
    await service.set_preference("area", "area-1", "ui.font_size", 14, source="explicit")
    await service.set_preference("project", run_spec.project_id, "a11y.reduce_motion", True, source="explicit")

    snapshot = await service.snapshot_for_run(
        run_spec.run_id,
        user_id="operator",
        area_id="area-1",
        project_id=run_spec.project_id,
    )
    assert isinstance(snapshot, PreferenceSnapshot)
    assert len(snapshot.preferences_hash) == 64
    assert (
        hashlib.sha256(snapshot.resolved_preferences_json.encode("utf-8")).hexdigest()
        == snapshot.preferences_hash
    )
    assert canonical_json(snapshot.resolved_preferences) == snapshot.resolved_preferences_json
    assert snapshot.preferences == {
        "a11y.reduce_motion": True,
        "ui.font_size": 14,
        "ui.theme": "dark",
    }

    # Frozen DTO & fresh dict copy cannot mutate snapshot
    copy = snapshot.resolved_preferences
    copy["preferences"]["ui.theme"] = "tampered"
    assert snapshot.preferences["ui.theme"] == "dark"
    with pytest.raises(ValidationError):
        snapshot.preferences_hash = "0" * 64  # type: ignore[misc]

    # Event preference.snapshot_created emitted in the same transaction
    events = await store.get_events(run_spec.run_id)
    snap_events = [e for e in events if e.event_type == "preference.snapshot_created"]
    assert len(snap_events) == 1
    assert snap_events[0].redacted_payload["preferences_hash"] == snapshot.preferences_hash

    # Idempotent call before any preference changes returns the exact same snapshot without duplicating events
    repeated = await service.snapshot_for_run(
        run_spec.run_id,
        user_id="operator",
        area_id="area-1",
        project_id=run_spec.project_id,
    )
    assert repeated == snapshot
    events_after = await store.get_events(run_spec.run_id)
    assert sum(e.event_type == "preference.snapshot_created" for e in events_after) == 1

    # Subsequent preference mutations do not affect the existing run snapshot
    await service.set_preference("project", run_spec.project_id, "ui.theme", "light", source="explicit")
    assert await service.get_snapshot(run_spec.run_id) == snapshot

    # Attempting to overwrite existing snapshot with divergent configuration fails
    with pytest.raises(ContractViolation) as exc_info:
        await service.snapshot_for_run(
            run_spec.run_id,
            user_id="operator",
            area_id="area-1",
            project_id=run_spec.project_id,
        )
    assert exc_info.value.code == "preference_snapshot_conflict"
    assert await service.get_snapshot(run_spec.run_id) == snapshot


@pytest.mark.negative
@pytest.mark.asyncio
async def test_snapshot_atomicity_and_tampering_detection(tmp_path, monkeypatch):
    repo_root = str((tmp_path / "repo").resolve())
    store = ExecutionStore(tmp_path / "atomicity.sqlite")
    run_spec = _make_run_spec(repo_root, run_id="run-pref-002", idempotency_key="pref-run-idemp-0002")
    await store.save_run_atomic(run_spec)
    service = PreferenceService(store)
    await service.set_preference("user", "operator", "ui.theme", "dark", source="explicit")

    async def fail_event(*args, **kwargs):
        raise RuntimeError("event store failure")

    original_insert = store._insert_event_in_tx
    monkeypatch.setattr(store, "_insert_event_in_tx", fail_event)
    with pytest.raises(RuntimeError, match="event store failure"):
        await service.snapshot_for_run(run_spec.run_id, user_id="operator")

    # Transaction rolled back: no snapshot persisted
    with pytest.raises(ContractViolation) as missing_exc:
        await service.get_snapshot(run_spec.run_id)
    assert missing_exc.value.code == "resource_not_found"

    monkeypatch.setattr(store, "_insert_event_in_tx", original_insert)
    await service.snapshot_for_run(run_spec.run_id, user_id="operator")

    # DB tampering triggers preference_integrity
    async with store._connect() as db:
        await db.execute(
            "UPDATE preference_snapshots SET preferences_hash = ? WHERE run_id = ?",
            ("f" * 64, run_spec.run_id),
        )
    with pytest.raises(ContractViolation) as integrity_exc:
        await service.get_snapshot(run_spec.run_id)
    assert integrity_exc.value.code == "preference_integrity"

    # Missing run rejected
    with pytest.raises(ContractViolation) as not_found_exc:
        await service.snapshot_for_run("missing-run", user_id="operator")
    assert not_found_exc.value.code == "resource_not_found"


@pytest.mark.negative
@pytest.mark.asyncio
async def test_inferred_preference_never_overrides_explicit(tmp_path):
    store = ExecutionStore(tmp_path / "precedence.sqlite")
    service = PreferenceService(store)

    # Inferred preference requires explicit opt_in=True
    with pytest.raises(ContractViolation) as opt_in_exc:
        await service.set_preference("user", "operator", "ui.theme", "neon", source="inferred_opt_in")
    assert opt_in_exc.value.code == "opt_in_required"
    assert await service.get_preference("user", "operator", "ui.theme") is None

    # Opt-in inferred works when no explicit preference exists at that scope
    inferred = await service.set_preference(
        "project",
        "proj-1",
        "ui.compact",
        True,
        source="inferred_opt_in",
        opt_in=True,
    )
    assert inferred.source == "inferred_opt_in"

    # Explicit preference at user scope still wins over inferred_opt_in at project scope
    await service.set_preference("user", "operator", "ui.compact", False, source="explicit")
    effective = await service.resolve_effective(user_id="operator", project_id="proj-1")
    assert effective["ui.compact"] is False

    # Same-scope overwrite of explicit by inferred_opt_in is strictly blocked
    with pytest.raises(ContractViolation) as precedence_exc:
        await service.set_preference(
            "user",
            "operator",
            "ui.compact",
            True,
            source="inferred_opt_in",
            opt_in=True,
        )
    assert precedence_exc.value.code == "explicit_preference_precedence"
    current = await service.get_preference("user", "operator", "ui.compact")
    assert current is not None
    assert current.source == "explicit"
    assert current.value is False
    assert current.version == 1


@pytest.mark.negative
@pytest.mark.asyncio
async def test_secrets_rejected_and_idempotency_enforced(tmp_path):
    store = ExecutionStore(tmp_path / "secrets.sqlite")
    service = PreferenceService(store)

    secret_payloads = [
        "sk-1234567890abcdef1234",
        "Bearer my-secret-bearer-token",
        "https://alice:hunter2@example.com/repo.git",
        {"api_key": "raw-key-value"},
        {"token": "[REDACTED]"},
    ]
    for bad_value in secret_payloads:
        with pytest.raises(ContractViolation) as exc_info:
            await service.set_preference("user", "operator", "ui.custom", bad_value, source="explicit")
        assert exc_info.value.code == "secret_in_preference"

    with pytest.raises(ContractViolation) as nan_exc:
        await service.set_preference("user", "operator", "ui.scale", float("nan"), source="explicit")
    assert nan_exc.value.code == "preference_invalid"
    assert await service.list_preferences(scope_type="user", scope_id="operator") == ()

    # Idempotency check
    first = await service.set_preference(
        "user",
        "operator",
        "ui.theme",
        "dark",
        idempotency_key="pref-idemp-key-0001",
    )
    second = await service.set_preference(
        "user",
        "operator",
        "ui.theme",
        "dark",
        idempotency_key="pref-idemp-key-0001",
    )
    assert second == first

    with pytest.raises(IdempotencyConflictError):
        await service.set_preference(
            "user",
            "operator",
            "ui.theme",
            "light",
            idempotency_key="pref-idemp-key-0001",
        )
