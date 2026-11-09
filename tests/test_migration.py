"""T10: real SQLite upgrades/downgrades, legacy evidence and negative gates."""

import asyncio
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3

import aiosqlite
import pytest
import pytest_asyncio

from hydra_orch.core.checkpointer import ExecutionStore, MigrationError
from test_checkpointer import _make_run_spec

MIGRATIONS = Path(__file__).resolve().parents[1] / "migration"
EXPANSION_TABLES = {
    "areas", "area_workspaces", "repositories", "authorizations", "agent_definitions",
    "capability_declarations", "profiles", "profile_snapshots", "sessions", "threads",
    "consent_records", "memory_entries", "discovered_resources", "skill_definitions",
    "secret_refs", "mcp_definitions", "profile_skills", "profile_mcps", "extension_manifests",
    "extension_installs", "preferences", "preference_snapshots", "transport_definitions",
    "transport_health", "access_tokens", "conflict_reports",
}
pytestmark = pytest.mark.integration


def copy_migrations(tmp_path, *, baseline_only=False):
    directory = tmp_path / ("baseline" if baseline_only else "migration")
    directory.mkdir()
    shutil.copy(MIGRATIONS / "0001_initial_core.sql", directory)
    if not baseline_only:
        shutil.copy(MIGRATIONS / "0002_control_plane.sql", directory)
        shutil.copytree(MIGRATIONS / "rollback", directory / "rollback")
    return directory


def read_db(path, sql, parameters=()):
    with closing(sqlite3.connect(path)) as db:
        return db.execute(sql, parameters).fetchall()


@pytest_asyncio.fixture
async def baseline(tmp_path):
    directory = copy_migrations(tmp_path, baseline_only=True)
    path = tmp_path / "execution.sqlite"
    store = ExecutionStore(path, migrations_dir=directory)
    spec = _make_run_spec(str(tmp_path))
    await store.submit_run_idempotent(spec)
    await store.save_checkpoint("legacy-stream", "task", "provider", "prompt", "buffer", "running")
    async with store._connect() as db:
        await db.execute("""INSERT INTO attempts
            (id, task_id, ordinal, executor_id, provider_model_json, process_status)
            VALUES ('old-attempt', ?, 1, 'codex', '{}', 'exited')""", (spec.tasks[0].task_id,))
        await db.execute("""INSERT INTO workspaces
            (id, attempt_id, canonical_path, base_sha, branch, status)
            VALUES ('old-worktree', 'old-attempt', '/preserved/worktree', ?, 'worker/old', 'preserved')""",
            ("a" * 40,))
    return path, spec, store


@pytest.mark.asyncio
async def test_fresh_schema_repeated_startup_and_foreign_keys(tmp_path):
    path = tmp_path / "fresh.sqlite"
    first = ExecutionStore(path)
    await first.initialize()
    versions = await first.get_applied_migrations()
    assert [v["version"] for v in versions] == ["0001", "0002"]
    assert len(versions[1]["checksum"]) == 64
    tables = {r[0] for r in read_db(path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPANSION_TABLES <= tables
    assert {"workspaces", "handoff_checkpoints", "metric_samples", "budget_policies", "pr_packages"} <= tables
    assert (await first.get_pragmas())["foreign_keys"] == 1
    assert read_db(path, "PRAGMA foreign_key_check") == []
    assert read_db(path, "PRAGMA integrity_check") == [("ok",)]
    history = await first.get_migration_history()
    await first.initialize()
    await ExecutionStore(path).initialize()
    assert await first.get_migration_history() == history
    assert all(row["status"] == "applied" for row in history)


@pytest.mark.asyncio
async def test_upgrade_preserves_core_and_legacy_rows_and_wal_backup(baseline):
    path, spec, old = baseline
    tables = [r[0] for r in read_db(path, "SELECT name FROM sqlite_master WHERE type='table'")
              if not r[0].startswith("sqlite_") and r[0] not in {"schema_migrations", "migration_history"}]
    original = {name: read_db(path, f'SELECT * FROM "{name}"') for name in tables}
    columns = {name: [r[1] for r in read_db(path, f'PRAGMA table_info("{name}")')] for name in tables}
    # Keep a WAL writer connection open: copying just the .sqlite file would lose this row.
    async with aiosqlite.connect(path) as writer:
        await writer.execute("PRAGMA wal_autocheckpoint=0")
        await writer.execute("INSERT INTO quota_status(model, remaining_percent) VALUES ('wal-marker', 17)")
        await writer.commit()
        upgraded = ExecutionStore(path)
        await upgraded.initialize()
        assert await upgraded.get_run(spec.run_id) is not None
        history = await upgraded.get_migration_history()
        backup_path = history[-1]["backup_path"]
        assert Path(backup_path).is_file()
        assert read_db(backup_path, "SELECT remaining_percent FROM quota_status WHERE model='wal-marker'") == [(17,)]
        assert read_db(backup_path, "SELECT version FROM schema_migrations") == [("0001",)]
        assert read_db(backup_path, "PRAGMA integrity_check") == [("ok",)]
        assert read_db(backup_path, "SELECT canonical_path FROM workspaces") == [("/preserved/worktree",)]
    for name in tables:
        names = ", ".join('"' + c + '"' for c in columns[name])
        rows = read_db(path, f'SELECT {names} FROM "{name}"')
        if name == "quota_status":
            rows = [r for r in rows if r[0] != "wal-marker"]
        assert rows == original[name], name
    assert read_db(path, "SELECT workspace_id, metadata_json, base_branch, base_sha FROM projects") == [(None, "{}", None, None)]


@pytest.mark.asyncio
async def test_empty_expansion_roundtrip_rollback_is_audited(baseline):
    path, spec, _ = baseline
    store = ExecutionStore(path)
    await store.initialize()
    backup = path.parent / "explicit-backup.sqlite"
    assert await store.rollback_migrations("0001", backup_path=backup) == ["0002"]
    assert [v["version"] for v in await store.get_applied_migrations()] == ["0001"]
    tables = {r[0] for r in read_db(path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not EXPANSION_TABLES & tables
    assert read_db(path, "SELECT canonical_path FROM workspaces") == [("/preserved/worktree",)]
    assert (await store.get_run(spec.run_id))["id"] == spec.run_id
    assert await store.get_checkpoint("legacy-stream") is not None
    assert read_db(path, "PRAGMA foreign_key_check") == []
    assert read_db(backup, "SELECT version FROM schema_migrations ORDER BY version") == [("0001",), ("0002",)]
    history = await store.get_migration_history()
    assert history[-1]["direction"] == "down"
    assert history[-1]["status"] == "applied"
    assert history[-1]["backup_path"] == str(backup.resolve())
    assert await store.rollback_migrations("0001") == []
    assert len(await store.get_migration_history()) == len(history)
    # A fresh startup deliberately restores the current checkout schema.
    restarted = ExecutionStore(path)
    await restarted.initialize()
    assert [v["version"] for v in await restarted.get_applied_migrations()] == ["0001", "0002"]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["area", "project", "event", "attempt"])
async def test_rollback_refuses_data_loss_or_live_attempt(baseline, data):
    path, spec, _ = baseline
    store = ExecutionStore(path)
    await store.initialize()
    async with store._connect() as db:
        if data == "area":
            await db.execute("INSERT INTO areas(id,name,owner_principal_id) VALUES ('area','Area','operator')")
        elif data == "project":
            await db.execute("UPDATE projects SET metadata_json = '{\"note\":\"preserve me\"}'")
        elif data == "event":
            await db.execute("INSERT INTO sessions(id,run_id) VALUES ('session', ?)", (spec.run_id,))
            await db.execute("UPDATE events SET session_id='session'")
        else:
            await db.execute("UPDATE attempts SET process_status='running'")
    with pytest.raises(MigrationError, match="Failed rolling back"):
        await store.rollback_migrations("0001")
    assert read_db(path, "SELECT version FROM schema_migrations ORDER BY version") == [("0001",), ("0002",)]
    audit = (await store.get_migration_history())[-1]
    assert (audit["direction"], audit["status"]) == ("down", "failed")
    assert Path(audit["backup_path"]).exists()
    assert read_db(path, "SELECT COUNT(*) FROM workspaces") == [(1,)]
    assert read_db(path, "PRAGMA foreign_key_check") == []


@pytest.mark.asyncio
async def test_failed_upgrade_rolls_back_ddl_and_metadata_then_retries(baseline, tmp_path):
    path, _, _ = baseline
    directory = copy_migrations(tmp_path)
    script = directory / "0002_control_plane.sql"
    original = script.read_text()
    script.write_text(original + "\nINVALID SQL;\n")
    store = ExecutionStore(path, migrations_dir=directory)
    with pytest.raises(MigrationError, match="Failed applying migration"):
        await store.initialize()
    assert read_db(path, "SELECT version FROM schema_migrations") == [("0001",)]
    assert read_db(path, "SELECT name FROM sqlite_master WHERE name='areas'") == []
    assert "workspace_id" not in {r[1] for r in read_db(path, "PRAGMA table_info(projects)")}
    assert (await store.get_migration_history())[-1]["status"] == "failed"
    script.write_text(original)
    await store.initialize()
    assert read_db(path, "SELECT COUNT(*) FROM workspaces") == [(1,)]


@pytest.mark.asyncio
async def test_failed_down_script_keeps_full_schema(baseline, tmp_path):
    path, _, _ = baseline
    directory = copy_migrations(tmp_path)
    script = directory / "rollback" / "0002_control_plane.sql"
    script.write_text(script.read_text() + "\nINVALID SQL;\n")
    store = ExecutionStore(path, migrations_dir=directory)
    await store.initialize()
    with pytest.raises(MigrationError, match="Failed rolling back"):
        await store.rollback_migrations("0001")
    assert read_db(path, "SELECT name FROM sqlite_master WHERE name='areas'") == [("areas",)]
    assert "workspace_id" in {r[1] for r in read_db(path, "PRAGMA table_info(projects)")}
    assert read_db(path, "SELECT version FROM schema_migrations ORDER BY version") == [("0001",), ("0002",)]


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["up", "down"])
async def test_script_tampering_rejected_without_changing_schema(tmp_path, direction):
    directory = copy_migrations(tmp_path)
    path = tmp_path / "tamper.sqlite"
    store = ExecutionStore(path, migrations_dir=directory)
    await store.initialize()
    script = directory / "0002_control_plane.sql" if direction == "up" else directory / "rollback" / "0002_control_plane.sql"
    script.write_text(script.read_text() + "\n-- tampered\n")
    with pytest.raises(MigrationError, match="[Cc]hecksum mismatch"):
        await ExecutionStore(path, migrations_dir=directory).initialize()
    with pytest.raises(MigrationError, match="[Cc]hecksum mismatch"):
        await store.rollback_migrations("0001")


@pytest.mark.asyncio
async def test_missing_unknown_and_duplicate_versions_fail_closed(tmp_path):
    directory = copy_migrations(tmp_path)
    path = tmp_path / "versions.sqlite"
    store = ExecutionStore(path, migrations_dir=directory)
    await store.initialize()
    with pytest.raises(MigrationError, match="known, applied"):
        await store.rollback_migrations("0000")
    (directory / "0002_duplicate.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="duplicate"):
        await ExecutionStore(path, migrations_dir=directory).initialize()
    (directory / "0002_duplicate.sql").unlink()
    (directory / "0002_control_plane.sql").unlink()
    with pytest.raises(MigrationError, match="missing from this checkout"):
        await ExecutionStore(path, migrations_dir=directory).initialize()


@pytest.mark.asyncio
async def test_backup_never_overwrites_operator_file(baseline):
    path, _, _ = baseline
    store = ExecutionStore(path)
    await store.initialize()
    backup = path.parent / "operator-file.sqlite"
    backup.write_bytes(b"operator data")
    with pytest.raises(MigrationError, match="backup failed"):
        await store.rollback_migrations("0001", backup_path=backup)
    assert backup.read_bytes() == b"operator data"
    with pytest.raises(MigrationError, match="live database"):
        await store.rollback_migrations("0001", backup_path=path)
    assert read_db(path, "PRAGMA integrity_check") == [("ok",)]


@pytest.mark.asyncio
async def test_concurrent_startups_apply_once(baseline):
    path, _, _ = baseline
    stores = [ExecutionStore(path) for _ in range(3)]
    await asyncio.gather(*(store.initialize() for store in stores))
    assert read_db(path, "SELECT COUNT(*) FROM schema_migrations WHERE version='0002'") == [(1,)]
    assert read_db(path, "SELECT COUNT(*) FROM migration_history WHERE version='0002' AND status='applied'") == [(1,)]


@pytest.mark.asyncio
async def test_expansion_fk_constraints_and_no_implicit_trust(baseline):
    path, spec, _ = baseline
    store = ExecutionStore(path)
    await store.initialize()
    async with store._connect() as db:
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO area_workspaces(id,area_id,name) VALUES ('w','missing','name')")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO memory_entries(id,scope_type,scope_id,content_redacted,author_ref,consent_id) VALUES ('m','run','r','text','operator','missing')")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO access_tokens(id,token_hash,principal_id,scopes_json) VALUES ('t','plaintext','operator','[]')")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO access_tokens(id,token_hash,principal_id,scopes_json) VALUES ('t','pbkdf2_sha256$plaintext','operator','[]')")
        await db.execute("INSERT INTO areas(id,name,owner_principal_id) VALUES ('a','Area','operator')")
        await db.execute("INSERT INTO area_workspaces(id,area_id,name) VALUES ('w','a','Workspace')")
        await db.execute("UPDATE projects SET workspace_id='w'")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("DELETE FROM area_workspaces WHERE id='w'")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("UPDATE projects SET metadata_json='invalid JSON'")
        await db.execute("INSERT INTO discovered_resources(id,resource_type,source_canonical_path,content_hash) VALUES ('d','skill','/opt/skill',?)", ("a" * 64,))
        assert (await (await db.execute("SELECT trust_status FROM discovered_resources")).fetchone())[0] == "untrusted"
        await db.execute("INSERT INTO agent_definitions(id,name,version,driver_type) VALUES ('agent','Codex','1','cli')")
        assert (await (await db.execute("SELECT is_certified FROM agent_definitions")).fetchone())[0] == 0
        await db.execute("INSERT INTO sessions(id,run_id) VALUES ('s1',?), ('s2',?)", (spec.run_id, spec.run_id))
        await db.execute("INSERT INTO threads(id,session_id) VALUES ('parent','s1')")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO threads(id,session_id,parent_thread_id) VALUES ('child','s2','parent')")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("UPDATE area_workspaces SET status='invented'")
    assert read_db(path, "PRAGMA foreign_key_check") == []


@pytest.mark.asyncio
async def test_profile_consent_and_extension_relations(baseline):
    from hydra_orch.core.auth import TokenVerifier

    path, spec, _ = baseline
    store = ExecutionStore(path)
    await store.initialize()
    async with store._connect() as db:
        await db.execute("INSERT INTO agent_definitions(id,name,version,driver_type) VALUES ('agent','Codex','1','cli')")
        await db.execute("INSERT INTO profiles(id,name,agent_ref,model_ref,executor_ref,orchestration_mode) VALUES ('p','Profile','agent','model','agent','persistent')")
        await db.execute("INSERT INTO profile_snapshots(id,profile_id,run_id,snapshot_hash,effective_config_json) VALUES ('snapshot','p',?,?,'{}')", (spec.run_id, "a" * 64))
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO profile_snapshots(id,profile_id,run_id,snapshot_hash,effective_config_json) VALUES ('duplicate','p',?,?,'{}')", (spec.run_id, "a" * 64))
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("DELETE FROM profiles WHERE id='p'")
        await db.execute("INSERT INTO consent_records(id,principal_id,purpose,scope,status) VALUES ('c','operator','test','project','granted')")
        await db.execute("INSERT INTO memory_entries(id,scope_type,scope_id,content_redacted,author_ref,consent_id,status) VALUES ('m','project','p','text','operator','c','active')")
        await db.execute("INSERT INTO extension_manifests(id,name,version,entrypoint,compatible_api_version,checksum) VALUES ('manifest','Plugin','1','plugin.py','v1',?)", ("a" * 64,))
        await db.execute("INSERT INTO extension_installs(id,extension_manifest_id,consent_record_id) VALUES ('install','manifest','c')")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("DELETE FROM consent_records WHERE id='c'")
        verifier = TokenVerifier.from_token("test-migration-token-0123456789abcdef")
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO access_tokens(id,token_hash,principal_id,scopes_json) VALUES ('invalid-token',?,'operator','[]')",
                (verifier.encode().replace("$600000$", "$600000a$"),))
        await db.execute("INSERT INTO access_tokens(id,token_hash,principal_id,scopes_json) VALUES ('token',?,'operator','[]')", (verifier.encode(),))
    assert read_db(path, "PRAGMA foreign_key_check") == []


@pytest.mark.asyncio
async def test_history_read_does_not_initialize_schema(tmp_path):
    path = tmp_path / "empty.sqlite"
    assert await ExecutionStore(path).get_migration_history() == []
    assert read_db(path, "SELECT name FROM sqlite_master WHERE type='table'") == []


@pytest.mark.asyncio
async def test_missing_down_script_and_unapplied_target(tmp_path):
    directory = copy_migrations(tmp_path)
    (directory / "rollback" / "0002_control_plane.sql").unlink()
    path = tmp_path / "missing-down.sqlite"
    store = ExecutionStore(path, migrations_dir=directory)
    await store.initialize()
    with pytest.raises(MigrationError, match="script missing"):
        await store.rollback_migrations("0001")
    assert read_db(path, "SELECT version FROM schema_migrations ORDER BY version") == [("0001",), ("0002",)]
    empty = ExecutionStore(tmp_path / "not-applied.sqlite", migrations_dir=directory)
    with pytest.raises(MigrationError, match="target is not applied"):
        await empty.rollback_migrations("0001")


@pytest.mark.asyncio
async def test_foreign_key_violation_in_migration_rolls_back(baseline, tmp_path):
    path, _, _ = baseline
    directory = copy_migrations(tmp_path)
    script = directory / "0002_control_plane.sql"
    script.write_text(script.read_text() + """
CREATE TABLE bad_fk (id TEXT PRIMARY KEY, parent TEXT REFERENCES areas(id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO bad_fk VALUES ('bad', 'missing');
""")
    store = ExecutionStore(path, migrations_dir=directory)
    with pytest.raises(MigrationError, match="foreign key violations"):
        await store.initialize()
    assert read_db(path, "SELECT name FROM sqlite_master WHERE name='bad_fk'") == []
    assert (await store.get_migration_history())[-1]["status"] == "failed"
