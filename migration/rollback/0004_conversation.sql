-- Offline rollback refuses to discard any conversation, including imported history.
CREATE TEMP TABLE conversation_rollback_guard (empty INTEGER CHECK(empty=1));
INSERT INTO conversation_rollback_guard SELECT NOT EXISTS(SELECT 1 FROM conversations);
DROP TABLE conversation_rollback_guard;
DROP TABLE conversation_commands;
DROP TABLE conversation_events;
DROP TABLE conversation_turns;
DROP TABLE conversations;
