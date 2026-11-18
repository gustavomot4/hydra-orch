export interface ConversationAgent {
  id: 'codex' | 'claude';
  name: string;
  available: boolean;
  authenticated?: boolean;
}

export interface ConversationRoute {
  executor: 'codex' | 'claude';
  connection_mode: 'direct' | 'omniroute';
  target_kind: 'model' | 'combo';
  target_ref: string;
}

export function defaultRoute(executor: 'codex' | 'claude' = 'codex'): ConversationRoute {
  return { executor, connection_mode: 'direct', target_kind: 'model', target_ref: '' };
}

export function routeSelection(value: ConversationRoute): ConversationRoute {
  const { executor, connection_mode, target_kind, target_ref } = value;
  return { executor, connection_mode, target_kind, target_ref };
}

export interface CoordinationCheck {
  check_id: string;
  command: string[];
  cwd?: string | null;
  exit_code: number;
  duration_seconds: number;
  output?: string;
}

export interface CoordinationTask {
  id: string;
  title: string;
  paths: string[];
  operation?: 'edit' | 'validate';
}

export interface CoordinationProgress {
  title: string;
  state: string;
  operation?: 'edit' | 'validate';
  reason?: string;
  review?: string;
  summary?: string;
  checks?: CoordinationCheck[];
  route?: ConversationRoute;
}

export interface ConversationTurn {
  id: string;
  ordinal: number;
  content: string;
  response: string;
  state: 'queued' | 'running' | 'stopping' | 'completed' | 'failed' | 'cancelled';
  error: string | null;
  diff: string;
  attachments: { filename: string; attachment_id: string }[];
  route?: ConversationRoute;
  route_revision?: number;
  execution_mode?: 'single' | 'swarm';
  coordination?: {
    plan?: { objective: string; tasks: CoordinationTask[] };
    run_id?: string | null;
    phase?: string;
    tasks?: Record<string, CoordinationProgress>;
  };
}

export interface ConversationSnapshot {
  id: string;
  title: string;
  project_id: string;
  project_name?: string;
  executor: string;
  access_mode: string;
  last_seq: number;
  legacy_run_id?: string | null;
  turns: ConversationTurn[];
  route?: ConversationRoute;
  route_revision?: number;
  execution_mode?: 'single' | 'swarm';
  auto_route?: boolean;
  tools: {
    seq: number;
    turn_id: string;
    type: string;
    payload: { tool?: string; detail?: string };
  }[];
  agents?: {
    id: string;
    parent_id: string;
    turn_id: string;
    title: string;
    state: string;
    executor: string;
    model: string;
    summary: string;
    source: 'cli';
  }[];
}

// A network retry or a remount must retain the identity of the same send.
export function pendingSendKey(scope: string, payload: unknown): string {
  const slot = `hydra:pending-send:${scope}`;
  const signature = JSON.stringify(payload);
  try {
    const saved = JSON.parse(localStorage.getItem(slot) || 'null');
    if (saved?.signature === signature) return saved.key;
  } catch {
    /* Storage may be disabled. */
  }
  const key = `chat-${crypto.randomUUID()}`;
  try {
    localStorage.setItem(slot, JSON.stringify({ signature, key }));
  } catch {
    /* Optional persistence. */
  }
  return key;
}

export function pendingMessage(
  scope: string,
  payload: { expected_last_seq: number; [key: string]: unknown },
) {
  const { expected_last_seq, ...content } = payload;
  const key = pendingSendKey(scope, content);
  const slot = `hydra:pending-sequence:${scope}`;
  try {
    const saved = JSON.parse(localStorage.getItem(slot) || 'null');
    if (saved?.key === key)
      return { ...payload, expected_last_seq: saved.sequence, idempotency_key: key };
    localStorage.setItem(slot, JSON.stringify({ key, sequence: expected_last_seq }));
  } catch {
    /* Optional persistence. */
  }
  return { ...payload, idempotency_key: key };
}

export function clearPendingSend(scope: string) {
  try {
    localStorage.removeItem(`hydra:pending-send:${scope}`);
    localStorage.removeItem(`hydra:pending-sequence:${scope}`);
  } catch {
    /* Optional persistence. */
  }
}
