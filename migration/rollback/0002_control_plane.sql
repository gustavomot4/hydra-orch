-- T10: offline-only rollback. Refuse any loss of expansion data or live attempts.
CREATE TEMP TABLE migration_rollback_guard (
    empty INTEGER NOT NULL CHECK (empty = 1)
);
INSERT INTO migration_rollback_guard SELECT NOT EXISTS (
SELECT 1 FROM areas
UNION ALL
SELECT 1 FROM area_workspaces
UNION ALL
SELECT 1 FROM authorizations
UNION ALL
SELECT 1 FROM repositories
UNION ALL
SELECT 1 FROM agent_definitions
UNION ALL
SELECT 1 FROM capability_declarations
UNION ALL
SELECT 1 FROM profiles
UNION ALL
SELECT 1 FROM profile_snapshots
UNION ALL
SELECT 1 FROM sessions
UNION ALL
SELECT 1 FROM threads
UNION ALL
SELECT 1 FROM consent_records
UNION ALL
SELECT 1 FROM memory_entries
UNION ALL
SELECT 1 FROM discovered_resources
UNION ALL
SELECT 1 FROM skill_definitions
UNION ALL
SELECT 1 FROM secret_refs
UNION ALL
SELECT 1 FROM mcp_definitions
UNION ALL
SELECT 1 FROM profile_skills
UNION ALL
SELECT 1 FROM profile_mcps
UNION ALL
SELECT 1 FROM extension_manifests
UNION ALL
SELECT 1 FROM extension_installs
UNION ALL
SELECT 1 FROM preferences
UNION ALL
SELECT 1 FROM preference_snapshots
UNION ALL
SELECT 1 FROM transport_definitions
UNION ALL
SELECT 1 FROM transport_health
UNION ALL
SELECT 1 FROM access_tokens
UNION ALL
SELECT 1 FROM conflict_reports
UNION ALL SELECT 1 FROM projects WHERE workspace_id IS NOT NULL OR metadata_json != '{}' OR base_branch IS NOT NULL OR base_sha IS NOT NULL OR revision != 1
UNION ALL SELECT 1 FROM events WHERE session_id IS NOT NULL OR thread_id IS NOT NULL
UNION ALL SELECT 1 FROM attempts WHERE process_status IN ('queued','running')
);
DROP TABLE migration_rollback_guard;
DROP INDEX idx_events_thread_seq;
DROP INDEX idx_events_session_seq;
ALTER TABLE events DROP COLUMN thread_id;
ALTER TABLE events DROP COLUMN session_id;
DROP INDEX idx_projects_workspace;
ALTER TABLE projects DROP COLUMN workspace_id;
ALTER TABLE projects DROP COLUMN metadata_json;
ALTER TABLE projects DROP COLUMN base_branch;
ALTER TABLE projects DROP COLUMN base_sha;
ALTER TABLE projects DROP COLUMN revision;
DROP TABLE conflict_reports;
DROP TABLE access_tokens;
DROP TABLE transport_health;
DROP TABLE transport_definitions;
DROP TABLE preference_snapshots;
DROP TABLE preferences;
DROP TABLE extension_installs;
DROP TABLE extension_manifests;
DROP TABLE profile_mcps;
DROP TABLE profile_skills;
DROP TABLE mcp_definitions;
DROP TABLE secret_refs;
DROP TABLE skill_definitions;
DROP TABLE discovered_resources;
DROP TABLE memory_entries;
DROP TABLE consent_records;
DROP TABLE threads;
DROP TABLE sessions;
DROP TABLE profile_snapshots;
DROP TABLE profiles;
DROP TABLE capability_declarations;
DROP TABLE agent_definitions;
DROP TABLE repositories;
DROP TABLE authorizations;
DROP TABLE area_workspaces;
DROP TABLE areas;
