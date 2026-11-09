-- T10: additive control-plane schema; 0001 and its data stay intact.
-- Logical workspaces use area_workspaces; workspaces remains attempt-scoped.

CREATE TABLE areas (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    owner_principal_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE area_workspaces (
    id TEXT PRIMARY KEY NOT NULL,
    area_id TEXT NOT NULL REFERENCES areas(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (area_id, name)
);
CREATE INDEX idx_area_workspaces_area ON area_workspaces(area_id);

ALTER TABLE projects ADD COLUMN workspace_id TEXT REFERENCES area_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE projects ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json));
ALTER TABLE projects ADD COLUMN base_branch TEXT;
ALTER TABLE projects ADD COLUMN base_sha TEXT;
ALTER TABLE projects ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1);
CREATE INDEX idx_projects_workspace ON projects(workspace_id);

CREATE TABLE authorizations (
    id TEXT PRIMARY KEY NOT NULL,
    area_id TEXT REFERENCES areas(id) ON DELETE RESTRICT,
    resource_ref TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    scopes_json TEXT NOT NULL CHECK (json_valid(scopes_json)),
    granted_at TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT
);
CREATE INDEX idx_authorizations_resource ON authorizations(resource_ref, principal_id);
CREATE TABLE repositories (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    root_canonical TEXT NOT NULL UNIQUE,
    base_branch TEXT NOT NULL,
    base_sha TEXT NOT NULL,
    allowed_paths_json TEXT NOT NULL CHECK (json_valid(allowed_paths_json)),
    authorization_id TEXT NOT NULL UNIQUE REFERENCES authorizations(id) ON DELETE RESTRICT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_repositories_project ON repositories(project_id);

CREATE TABLE agent_definitions (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    driver_type TEXT NOT NULL,
    declared_capabilities_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(declared_capabilities_json)),
    limitations_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(limitations_json)),
    is_certified INTEGER NOT NULL DEFAULT 0 CHECK (is_certified IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, version)
);
CREATE TABLE capability_declarations (
    id TEXT PRIMARY KEY NOT NULL,
    agent_definition_id TEXT NOT NULL REFERENCES agent_definitions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    supports_tools INTEGER NOT NULL DEFAULT 0 CHECK (supports_tools IN (0,1)),
    supports_workspace INTEGER NOT NULL DEFAULT 0 CHECK (supports_workspace IN (0,1)),
    supports_cancellation INTEGER NOT NULL DEFAULT 0 CHECK (supports_cancellation IN (0,1)),
    supports_streaming INTEGER NOT NULL DEFAULT 0 CHECK (supports_streaming IN (0,1)),
    certified_on TEXT,
    UNIQUE (agent_definition_id, name, version)
);
CREATE TABLE profiles (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    agent_ref TEXT NOT NULL REFERENCES agent_definitions(id) ON DELETE RESTRICT,
    model_ref TEXT NOT NULL,
    executor_ref TEXT NOT NULL REFERENCES agent_definitions(id) ON DELETE RESTRICT,
    skills_refs_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(skills_refs_json)),
    mcp_refs_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(mcp_refs_json)),
    memory_policy_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(memory_policy_json)),
    resource_limits_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(resource_limits_json)),
    orchestration_mode TEXT NOT NULL CHECK (orchestration_mode IN ('swarm','relay','persistent')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE profile_snapshots (
    id TEXT PRIMARY KEY NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    snapshot_hash TEXT NOT NULL CHECK (length(snapshot_hash) = 64),
    effective_config_json TEXT NOT NULL CHECK (json_valid(effective_config_json)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_profile_snapshots_profile ON profile_snapshots(profile_id);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    origin_ref TEXT,
    agent_ref TEXT REFERENCES agent_definitions(id) ON DELETE RESTRICT,
    state TEXT NOT NULL DEFAULT 'created' CHECK (state IN ('created','running','waiting','completed','failed','cancelled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT
);
CREATE INDEX idx_sessions_run ON sessions(run_id);
CREATE TABLE threads (
    id TEXT PRIMARY KEY NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
    parent_thread_id TEXT,
    agent_ref TEXT REFERENCES agent_definitions(id) ON DELETE RESTRICT,
    state TEXT NOT NULL DEFAULT 'created' CHECK (state IN ('created','running','waiting','completed','failed','cancelled')),
    last_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, id),
    FOREIGN KEY (session_id, parent_thread_id) REFERENCES threads(session_id, id) ON DELETE RESTRICT,
    CHECK (parent_thread_id IS NULL OR parent_thread_id != id)
);
CREATE INDEX idx_threads_parent ON threads(session_id, parent_thread_id);
ALTER TABLE events ADD COLUMN session_id TEXT REFERENCES sessions(id) ON DELETE RESTRICT;
ALTER TABLE events ADD COLUMN thread_id TEXT REFERENCES threads(id) ON DELETE RESTRICT;
CREATE INDEX idx_events_session_seq ON events(session_id, seq);
CREATE INDEX idx_events_thread_seq ON events(thread_id, seq);

CREATE TABLE consent_records (
    id TEXT PRIMARY KEY NOT NULL,
    principal_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','granted','revoked','denied','expired')),
    granted_at TEXT,
    revoked_at TEXT
);
CREATE TABLE memory_entries (
    id TEXT PRIMARY KEY NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    content_redacted TEXT NOT NULL,
    author_ref TEXT NOT NULL,
    consent_id TEXT NOT NULL REFERENCES consent_records(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    retention_policy_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending_consent' CHECK (status IN ('pending_consent','active','revoked','rejected','expired')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT
);
CREATE INDEX idx_memory_scope ON memory_entries(scope_type, scope_id, status);
CREATE INDEX idx_memory_consent ON memory_entries(consent_id);
CREATE TABLE discovered_resources (
    id TEXT PRIMARY KEY NOT NULL,
    resource_type TEXT NOT NULL,
    source_canonical_path TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    capabilities_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(capabilities_json)),
    trust_status TEXT NOT NULL DEFAULT 'untrusted' CHECK (trust_status IN ('untrusted','approved','active','rejected','revoked')),
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at TEXT,
    approved_by TEXT
);
CREATE INDEX idx_discovery_source ON discovered_resources(source_canonical_path);
CREATE TABLE skill_definitions (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest_ref TEXT NOT NULL,
    discovered_resource_id TEXT REFERENCES discovered_resources(id) ON DELETE RESTRICT,
    permissions_declared_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(permissions_declared_json)),
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, version)
);
CREATE TABLE secret_refs (
    id TEXT PRIMARY KEY NOT NULL,
    secret_name TEXT NOT NULL,
    provider_type TEXT NOT NULL CHECK (provider_type IN ('env','vault','keyring')),
    source_key TEXT NOT NULL
);
CREATE TABLE mcp_definitions (
    id TEXT PRIMARY KEY NOT NULL,
    server_name TEXT NOT NULL,
    transport_type TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    discovered_resource_id TEXT REFERENCES discovered_resources(id) ON DELETE RESTRICT,
    secret_ref TEXT REFERENCES secret_refs(id) ON DELETE RESTRICT,
    declared_tools_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(declared_tools_json)),
    permissions_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(permissions_json)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE profile_skills (
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skill_definitions(id) ON DELETE RESTRICT,
    PRIMARY KEY (profile_id, skill_id)
);
CREATE TABLE profile_mcps (
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    mcp_id TEXT NOT NULL REFERENCES mcp_definitions(id) ON DELETE RESTRICT,
    PRIMARY KEY (profile_id, mcp_id)
);
CREATE TABLE extension_manifests (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    entrypoint TEXT NOT NULL,
    permissions_required_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(permissions_required_json)),
    compatible_api_version TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, version)
);
CREATE TABLE extension_installs (
    id TEXT PRIMARY KEY NOT NULL,
    extension_manifest_id TEXT NOT NULL REFERENCES extension_manifests(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','consented','installed','active','disabled','quarantined','revoked','rolled_back')),
    consent_record_id TEXT NOT NULL REFERENCES consent_records(id) ON DELETE RESTRICT,
    installed_at TEXT,
    revoked_at TEXT
);
CREATE TABLE preferences (
    id TEXT PRIMARY KEY NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    source TEXT NOT NULL CHECK (source IN ('explicit','inferred_opt_in')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (scope_type, scope_id, key)
);
CREATE TABLE preference_snapshots (
    id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    preferences_hash TEXT NOT NULL CHECK (length(preferences_hash) = 64),
    resolved_preferences_json TEXT NOT NULL CHECK (json_valid(resolved_preferences_json)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE transport_definitions (
    id TEXT PRIMARY KEY NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('local','ssh','ide','cdp','remote')),
    target_identity TEXT NOT NULL,
    capabilities_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(capabilities_json)),
    is_certified INTEGER NOT NULL DEFAULT 0 CHECK (is_certified IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE transport_health (
    id TEXT PRIMARY KEY NOT NULL,
    transport_id TEXT NOT NULL REFERENCES transport_definitions(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'unknown' CHECK (status IN ('unknown','healthy','degraded','unreachable')),
    last_check_at TEXT,
    error_detail TEXT
);
CREATE INDEX idx_transport_health_transport ON transport_health(transport_id, last_check_at);
CREATE TABLE access_tokens (
    id TEXT PRIMARY KEY NOT NULL,
    token_hash TEXT NOT NULL UNIQUE CHECK (
        length(token_hash) IN (118,119)
        AND substr(token_hash,1,14) = 'pbkdf2_sha256$'
        AND substr(token_hash,15,length(token_hash)-112) NOT GLOB '*[^0-9]*'
        AND CAST(substr(token_hash,15,length(token_hash)-112) AS INTEGER) BETWEEN 600000 AND 2000000
        AND substr(token_hash,-98,1) = '$' AND substr(token_hash,-65,1) = '$'
        AND substr(token_hash,-97,32) NOT GLOB '*[^0-9a-f]*'
        AND substr(token_hash,-64) NOT GLOB '*[^0-9a-f]*'
    ),
    principal_id TEXT NOT NULL,
    scopes_json TEXT NOT NULL CHECK (json_valid(scopes_json)),
    expires_at TEXT,
    revoked_at TEXT
);
CREATE TABLE conflict_reports (
    id TEXT PRIMARY KEY NOT NULL,
    integration_id TEXT NOT NULL REFERENCES integrations(id) ON DELETE RESTRICT,
    base_sha TEXT NOT NULL,
    ours_sha TEXT NOT NULL,
    theirs_sha TEXT NOT NULL,
    conflicted_files_json TEXT NOT NULL CHECK (json_valid(conflicted_files_json)),
    resolution_options_json TEXT NOT NULL CHECK (json_valid(resolution_options_json)),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','auto_repair','manual','discarded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);
CREATE INDEX idx_conflicts_integration ON conflict_reports(integration_id);
