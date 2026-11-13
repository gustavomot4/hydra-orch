-- T37: offline-only rollback. Refuse any loss of automation schedules or history.
CREATE TEMP TABLE migration_rollback_guard (
    empty INTEGER NOT NULL CHECK (empty = 1)
);
INSERT INTO migration_rollback_guard SELECT NOT EXISTS (
    SELECT 1 FROM automation_schedules
    UNION ALL
    SELECT 1 FROM automation_runs
);
DROP TABLE migration_rollback_guard;
DROP INDEX idx_automation_runs_schedule_for;
DROP INDEX idx_automation_schedules_due;
DROP TABLE automation_runs;
DROP TABLE automation_schedules;
