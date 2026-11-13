-- T37: durable automation schedules and execution run history.

CREATE TABLE automation_schedules (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    workspace_id TEXT REFERENCES area_workspaces(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    target_host TEXT NOT NULL DEFAULT 'local',
    executor_id TEXT NOT NULL DEFAULT 'codex',
    prompt TEXT NOT NULL,
    cron_expr TEXT,
    interval_seconds INTEGER CHECK (interval_seconds IS NULL OR interval_seconds >= 60),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    overlap_policy TEXT NOT NULL DEFAULT 'skip' CHECK (overlap_policy IN ('skip', 'queue', 'allow')),
    missed_policy TEXT NOT NULL DEFAULT 'skip' CHECK (missed_policy IN ('skip', 'run_once')),
    max_retries INTEGER NOT NULL DEFAULT 0 CHECK (max_retries >= 0 AND max_retries <= 5),
    next_run_at TEXT,
    last_run_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (cron_expr IS NOT NULL OR interval_seconds IS NOT NULL)
);

CREATE TABLE automation_runs (
    id TEXT PRIMARY KEY NOT NULL,
    schedule_id TEXT NOT NULL REFERENCES automation_schedules(id) ON DELETE CASCADE,
    occurrence_key TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'dispatched', 'succeeded', 'failed', 'skipped', 'missed')),
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
    error_detail TEXT,
    dispatched_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    UNIQUE (schedule_id, occurrence_key)
);

CREATE INDEX idx_automation_schedules_due ON automation_schedules(enabled, next_run_at);
CREATE INDEX idx_automation_runs_schedule_for ON automation_runs(schedule_id, scheduled_for);
