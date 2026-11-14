-- Durable chats are independent of run lifecycle. Legacy sessions retain their IDs.
CREATE TABLE conversations (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES projects(id),
 title TEXT NOT NULL,
 executor TEXT NOT NULL,
 access_mode TEXT NOT NULL DEFAULT 'read-only' CHECK(access_mode IN ('read-only','workspace-write')),
 workspace_path TEXT,
 base_sha TEXT,
 native_session_id TEXT,
 legacy_run_id TEXT REFERENCES runs(id),
 legacy_session_id TEXT UNIQUE REFERENCES sessions(id),
 last_seq INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE conversation_turns (
 id TEXT PRIMARY KEY,
 conversation_id TEXT NOT NULL REFERENCES conversations(id),
 ordinal INTEGER NOT NULL,
 idempotency_key TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 content TEXT NOT NULL,
 response TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','stopping','completed','failed','cancelled')),
 context_strategy TEXT NOT NULL DEFAULT 'transcript',
 attachment_json TEXT NOT NULL DEFAULT '[]',
 error TEXT,
 lease_owner TEXT,
 lease_until REAL,
 process_pid INTEGER,
 diff TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 finished_at TEXT,
 UNIQUE(conversation_id,idempotency_key),
 UNIQUE(conversation_id,ordinal)
);
CREATE UNIQUE INDEX idx_conversation_active ON conversation_turns(conversation_id)
 WHERE state IN ('running','stopping');
CREATE INDEX idx_conversation_queue ON conversation_turns(state,created_at);
CREATE TABLE conversation_events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT,
 conversation_id TEXT NOT NULL REFERENCES conversations(id),
 turn_id TEXT REFERENCES conversation_turns(id),
 type TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_conversation_event_replay ON conversation_events(conversation_id,seq);
CREATE TABLE conversation_commands (
 idempotency_key TEXT PRIMARY KEY,
 request_hash TEXT NOT NULL,
 conversation_id TEXT NOT NULL REFERENCES conversations(id)
);
INSERT INTO conversations(id,project_id,title,executor,legacy_run_id,legacy_session_id,created_at)
 SELECT 'conversation-' || s.id,r.project_id,
 COALESCE(json_extract(r.spec_json,'$.objective'),'Conversa anterior'),
 CASE WHEN s.origin_ref IN ('codex','claude','claude_code') THEN s.origin_ref ELSE 'codex' END,
 r.id,s.id,s.created_at FROM sessions s JOIN runs r ON r.id=s.run_id;
-- Preserve messages as historical completed turns, without automatically executing them.
INSERT INTO conversation_turns(id,conversation_id,ordinal,idempotency_key,request_hash,content,state,created_at,finished_at)
 SELECT 'legacy-message-' || e.id,'conversation-' || e.session_id,
 row_number() OVER (PARTITION BY e.session_id ORDER BY e.seq),
 'legacy-' || e.id,'legacy',json_extract(e.payload_json,'$.content'),'completed',e.created_at,e.created_at
 FROM events e WHERE e.type='thread.message' AND e.session_id IS NOT NULL;
