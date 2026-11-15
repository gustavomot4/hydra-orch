CREATE TEMP TABLE conversation_coordination_rollback_guard (empty INTEGER CHECK(empty=1));
INSERT INTO conversation_coordination_rollback_guard
 SELECT NOT EXISTS(SELECT 1 FROM conversations WHERE execution_mode<>'single' OR auto_route<>0)
 AND NOT EXISTS(SELECT 1 FROM conversation_turns WHERE execution_mode<>'single' OR auto_route<>0 OR coordination_json<>'{}');
DROP TABLE conversation_coordination_rollback_guard;
ALTER TABLE conversation_turns DROP COLUMN coordination_json;
ALTER TABLE conversation_turns DROP COLUMN auto_route;
ALTER TABLE conversation_turns DROP COLUMN execution_mode;
ALTER TABLE conversations DROP COLUMN auto_route;
ALTER TABLE conversations DROP COLUMN execution_mode;
