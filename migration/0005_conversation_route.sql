-- Route defaults may change; a confirmed turn always keeps its original snapshot.
ALTER TABLE conversations ADD COLUMN route_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE conversations ADD COLUMN route_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversation_turns ADD COLUMN route_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE conversation_turns ADD COLUMN route_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversation_turns ADD COLUMN native_session_id TEXT;
ALTER TABLE conversation_turns ADD COLUMN context_checkpoint_json TEXT NOT NULL DEFAULT '{}';
CREATE TABLE conversation_route_commands (
 conversation_id TEXT NOT NULL REFERENCES conversations(id),
 idempotency_key TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 response_json TEXT NOT NULL,
 PRIMARY KEY(conversation_id,idempotency_key)
);
CREATE TABLE conversation_route_certificates (
 certificate_key TEXT PRIMARY KEY,
 evidence_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
