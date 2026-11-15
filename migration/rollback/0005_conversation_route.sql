-- Refuse to discard route choices, execution evidence or certificates.
CREATE TEMP TABLE conversation_route_rollback_guard (empty INTEGER CHECK(empty=1));
INSERT INTO conversation_route_rollback_guard
 SELECT NOT EXISTS(SELECT 1 FROM conversation_route_commands)
 AND NOT EXISTS(SELECT 1 FROM conversation_route_certificates)
 AND NOT EXISTS(SELECT 1 FROM conversations WHERE route_revision<>0 OR route_json<>'{}')
 AND NOT EXISTS(SELECT 1 FROM conversation_turns WHERE route_json<>'{}' OR context_checkpoint_json<>'{}');
DROP TABLE conversation_route_rollback_guard;
DROP TABLE conversation_route_commands;
DROP TABLE conversation_route_certificates;
ALTER TABLE conversation_turns DROP COLUMN context_checkpoint_json;
ALTER TABLE conversation_turns DROP COLUMN native_session_id;
ALTER TABLE conversation_turns DROP COLUMN route_revision;
ALTER TABLE conversation_turns DROP COLUMN route_json;
ALTER TABLE conversations DROP COLUMN route_revision;
ALTER TABLE conversations DROP COLUMN route_json;
