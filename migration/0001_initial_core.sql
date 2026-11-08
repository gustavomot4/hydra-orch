-- migration/0001_initial_core.sql
-- hydra-orch: Esquema Relacional Canônico do Núcleo (V0 / M1)
-- Base: PRD Técnico §3.6.6 e MER (doc/d_mer/mer.md)

-- Tabela de controle de migrações
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tabela base: projects
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    canonical_root TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Runs
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    spec_json TEXT NOT NULL,           -- RunSpec completo com schema_version
    base_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','waiting','reviewing','succeeded','failed','cancelled')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),  -- concorrência otimista
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    spec_json TEXT NOT NULL,           -- TaskSpec completo
    status TEXT NOT NULL CHECK (status IN ('pending','running','needs_context','blocked','failed','ready_for_review','accepted','rejected','cancelled')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(run_id, status);

-- Task Dependencies (DAG edges)
CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    prerequisite_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, prerequisite_id),
    CHECK (task_id != prerequisite_id)
);

-- Attempts
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),          -- 1, 2, 3...
    executor_id TEXT NOT NULL,
    provider_model_json TEXT NOT NULL,
    provider_session TEXT,
    base_sha TEXT,
    workspace_path TEXT,
    process_status TEXT NOT NULL DEFAULT 'queued' CHECK (process_status IN ('queued','running','exited','timed_out','cancelled','crashed')),
    exit_code INTEGER,
    exit_reason TEXT,
    started_at TEXT,
    finished_at TEXT,
    attempt_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (task_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_attempts_task ON attempts(task_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_attempts_active_task ON attempts(task_id) WHERE process_status IN ('queued', 'running');

-- Workspaces (por tentativa)
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
    canonical_path TEXT NOT NULL UNIQUE,
    base_sha TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('preparing','ready','integrating','conflicted','preserved','cleaned'))
);

-- Artifacts (definido antes de results e check_results por causa das FKs)
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    relative_path TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('patch','check_output','log','handoff','export','report','pr_package')),
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_attempt ON artifacts(attempt_id);

-- Results
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    exit_code INTEGER,
    simulated BOOLEAN NOT NULL DEFAULT 0,
    outcome TEXT CHECK (outcome IN ('success','failure','partial')),
    task_status TEXT CHECK (task_status IN ('pending','running','needs_context','blocked','failed','ready_for_review','accepted','rejected','cancelled')),
    process_status TEXT CHECK (process_status IN ('queued','running','exited','timed_out','cancelled','crashed')),
    summary TEXT,
    patch_commit_sha TEXT,
    patch_artifact_id TEXT REFERENCES artifacts(id) ON DELETE SET NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Integrations (definido antes de check_results e integration_items)
CREATE TABLE IF NOT EXISTS integrations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    workspace_path TEXT NOT NULL,
    expected_base_sha TEXT NOT NULL,
    result_sha TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','not_integrated','integrating','integrated','conflicted','failed','discarded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_integrations_run_status ON integrations(run_id, status);

-- Integration Items (ordem de merge)
CREATE TABLE IF NOT EXISTS integration_items (
    integration_id TEXT NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    result_id TEXT NOT NULL REFERENCES results(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 1),
    PRIMARY KEY (integration_id, position),
    UNIQUE (integration_id, result_id)
);

-- Check Results
CREATE TABLE IF NOT EXISTS check_results (
    id TEXT PRIMARY KEY,
    result_id TEXT REFERENCES results(id) ON DELETE CASCADE,
    integration_id TEXT REFERENCES integrations(id) ON DELETE CASCADE,
    check_id TEXT,
    command_json TEXT NOT NULL,
    cwd TEXT,
    tested_sha TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    duration_seconds REAL DEFAULT 0.0,
    stdout_artifact_id TEXT REFERENCES artifacts(id) ON DELETE SET NULL,
    stderr_artifact_id TEXT REFERENCES artifacts(id) ON DELETE SET NULL,
    output_artifact_id TEXT REFERENCES artifacts(id) ON DELETE SET NULL,
    started_at TEXT,
    finished_at TEXT,
    CHECK (result_id IS NOT NULL OR integration_id IS NOT NULL),
    CHECK (result_id IS NULL OR integration_id IS NULL)
);

-- Reviews
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL REFERENCES results(id) ON DELETE CASCADE,
    actor TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted','rejected')),
    reason TEXT,
    expected_revision INTEGER NOT NULL CHECK (expected_revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Events (SSE + auditoria)
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),              -- monotônico por run
    correlation_id TEXT NOT NULL DEFAULT 'corr-default',
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,        -- redigido
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);

-- Handoff Checkpoints
CREATE TABLE IF NOT EXISTS handoff_checkpoints (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
    instructions_json TEXT NOT NULL,
    git_sha TEXT NOT NULL,
    diff_artifact_ids TEXT NOT NULL,   -- JSON array
    tools_executed_json TEXT NOT NULL,
    partial_output_json TEXT,
    next_step TEXT,
    checkpoint_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_handoff_attempt ON handoff_checkpoints(attempt_id);

-- Commands (Idempotência RT03)
CREATE TABLE IF NOT EXISTS commands (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    response_json TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (scope, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_commands_key ON commands(scope, idempotency_key);

-- Budget Policies
CREATE TABLE IF NOT EXISTS budget_policies (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    max_usd REAL,
    max_tokens_in INTEGER,
    max_tokens_out INTEGER,
    max_wall_seconds INTEGER,
    alert_threshold_pct REAL NOT NULL DEFAULT 80.0 CHECK (alert_threshold_pct >= 50.0 AND alert_threshold_pct <= 99.0),
    status TEXT NOT NULL CHECK (status IN ('active','alerted','frozen','exhausted')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_budget_run_status ON budget_policies(run_id, status);

-- Metric Samples
CREATE TABLE IF NOT EXISTS metric_samples (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('run','attempt','session','thread')),
    scope_id TEXT NOT NULL,            -- attempt_id, session_id, etc.
    kind TEXT NOT NULL CHECK (kind IN ('queue','duration','tokens_in','tokens_out','cost')),
    value REAL,                        -- NULL = unknown
    unit TEXT NOT NULL,
    source TEXT NOT NULL,              -- ex: 'omniroute', 'local_calc', 'provider_api'
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('observed','stale','unknown')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_run ON metric_samples(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_scope ON metric_samples(run_id, scope, scope_id);

-- Route Decisions
CREATE TABLE IF NOT EXISTS route_decisions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    candidates_json TEXT NOT NULL,
    selected_route TEXT NOT NULL,
    reason TEXT NOT NULL,
    fallback_chain_json TEXT NOT NULL,
    decision_source TEXT NOT NULL CHECK (decision_source IN ('hydra','omnirouter','operator')),
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_route_decisions_run ON route_decisions(run_id);

-- PR Packages
CREATE TABLE IF NOT EXISTS pr_packages (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    pr_branch TEXT NOT NULL,
    description_markdown TEXT NOT NULL,
    commits_json TEXT NOT NULL,
    checks_summary_json TEXT NOT NULL,
    diff_summary_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pr_packages_run ON pr_packages(run_id);

-- Tabelas legadas de streaming preservadas (compatibilidade retroativa)
CREATE TABLE IF NOT EXISTS checkpoints (
    session_id TEXT PRIMARY KEY,
    task_id TEXT,
    provider TEXT,
    prompt TEXT,
    accumulated_content TEXT,
    status TEXT,
    created_at REAL,
    updated_at REAL,
    reset_at REAL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS provider_limits (
    provider TEXT PRIMARY KEY,
    status TEXT,
    limit_hit_at REAL,
    resets_at REAL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS active_generations (
    session_id TEXT PRIMARY KEY,
    task_id TEXT,
    model TEXT,
    prompt TEXT,
    accumulated_content TEXT,
    status TEXT,
    created_at REAL,
    updated_at REAL,
    reset_at REAL,
    anchor_block TEXT
);

CREATE TABLE IF NOT EXISTS quota_status (
    model TEXT PRIMARY KEY,
    resets_at REAL,
    remaining_percent REAL,
    updated_at REAL
);
