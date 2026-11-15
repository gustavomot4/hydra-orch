ALTER TABLE conversations ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'single' CHECK(execution_mode IN ('single','swarm'));
ALTER TABLE conversations ADD COLUMN auto_route INTEGER NOT NULL DEFAULT 0 CHECK(auto_route IN (0,1));
ALTER TABLE conversation_turns ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'single' CHECK(execution_mode IN ('single','swarm'));
ALTER TABLE conversation_turns ADD COLUMN auto_route INTEGER NOT NULL DEFAULT 0 CHECK(auto_route IN (0,1));
ALTER TABLE conversation_turns ADD COLUMN coordination_json TEXT NOT NULL DEFAULT '{}';
