import { RunStatus } from '@/type/controlPlane';

export type ChatTimelineState =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'paused_hitl'
  | 'reviewing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'stale_cursor';

export interface TimelineStateMeta {
  state: ChatTimelineState;
  label: string;
  badgeStatus: string;
  description: string;
}

export const CHAT_TIMELINE_STATE_META: Record<ChatTimelineState, TimelineStateMeta> = {
  idle: {
    state: 'idle',
    label: 'Ocioso',
    badgeStatus: 'queued',
    description: 'Linha do tempo aguardando conexão ou eventos.',
  },
  connecting: {
    state: 'connecting',
    label: 'Conectando',
    badgeStatus: 'running',
    description: 'Estabelecendo stream SSE autenticado.',
  },
  streaming: {
    state: 'streaming',
    label: 'Transmitindo',
    badgeStatus: 'running',
    description: 'Recebendo eventos duráveis em tempo real.',
  },
  paused_hitl: {
    state: 'paused_hitl',
    label: 'Aguardando HITL',
    badgeStatus: 'waiting',
    description: 'Execução pausada aguardando aprovação ou contexto humano.',
  },
  reviewing: {
    state: 'reviewing',
    label: 'Em revisão',
    badgeStatus: 'reviewing',
    description: 'Coordenador revisando alterações e evidências.',
  },
  completed: {
    state: 'completed',
    label: 'Concluído',
    badgeStatus: 'completed',
    description: 'Execução finalizada com estado terminal do backend.',
  },
  failed: {
    state: 'failed',
    label: 'Falhou',
    badgeStatus: 'failed',
    description: 'Execução encerrada com falha verificada.',
  },
  cancelled: {
    state: 'cancelled',
    label: 'Cancelado',
    badgeStatus: 'cancelled',
    description: 'Execução cancelada pelo operador.',
  },
  stale_cursor: {
    state: 'stale_cursor',
    label: 'Cursor expirado',
    badgeStatus: 'stale',
    description: 'Cursor SSE expirou (HTTP 410); sincronizando snapshot HTTP.',
  },
};

export type CheckStatus = 'passed' | 'failed' | 'pending' | 'unknown';

export interface BackendCheckSpec {
  check_id: string;
  command: string[];
  cwd?: string | null;
  description?: string;
}

export interface BackendCheckResult {
  check_id: string;
  command: string[];
  cwd?: string | null;
  tested_sha?: string;
  exit_code: number;
  duration_seconds: number;
  stdout_artifact_id?: string;
  stderr_artifact_id?: string;
  status?: CheckStatus;
}

export interface BackendFailureDetail {
  code: string;
  message: string;
  retryable?: boolean;
}

export interface BackendAttemptResult {
  id?: string;
  result_id: string;
  attempt_id: string;
  exit_code: number | null;
  simulated?: boolean;
  outcome?: 'success' | 'partial' | 'failure';
  task_status: string;
  revision: number;
  summary: string;
  patch_commit_sha?: string | null;
  patch_artifact_id?: string | null;
  changed_files?: string[];
  checks?: BackendCheckResult[];
  failures?: BackendFailureDetail[];
}

export interface BackendTaskAttempt {
  id?: string;
  attempt_id: string;
  task_id: string;
  ordinal: number;
  executor_id: string;
  provider: string;
  model: string;
  provider_session?: string | null;
  process_status: string;
  exit_code: number | null;
  started_at: string | null;
  finished_at: string | null;
  workspace_path?: string | null;
  result?: BackendAttemptResult | null;
}

export interface BackendTask {
  id: string;
  task_id: string;
  run_id: string;
  spec: {
    task_id: string;
    objective: string;
    assigned_executor: string;
    acceptance_criteria?: BackendCheckSpec[];
    allowed_paths?: string[];
    dependencies?: string[];
  };
  status: string;
  revision: number;
  dependencies: string[];
  current_attempt: BackendTaskAttempt | null;
  attempts: BackendTaskAttempt[];
  created_at: string;
  updated_at: string;
  wave?: number;
  worktree_path?: string | null;
}

export interface RunDetailSnapshot {
  id: string;
  run_id: string;
  project_id: string;
  objective: string;
  mode: 'swarm' | 'relay' | 'persistent';
  status: RunStatus;
  revision: number;
  base_sha: string;
  tasks: BackendTask[];
  budget?: {
    max_usd: number | null;
    max_tokens_in: number | null;
    max_tokens_out: number | null;
    max_wall_seconds: number;
    alert_threshold_pct: number;
    current_usd: number;
    current_tokens_in: number;
    current_tokens_out: number;
    status: string;
  };
  created_at: string;
  updated_at: string;
}

export type HitlKind = 'needs_context' | 'needs_approval';
export type HitlState = 'pending' | 'answered' | 'denied' | 'expired' | 'cancelled';

export interface HitlRequestItem {
  request_id: string;
  run_id: string;
  task_id: string | null;
  kind: HitlKind;
  question: string;
  state: HitlState;
  revision: number;
  created_at: string;
  deadline: string;
  response: string | null;
  actor: string | null;
  resolved_at: string | null;
}

export interface HitlRespondPayload {
  response: string;
  actor: string;
  expected_revision: number;
  approved: boolean;
}

export interface RunSseEvent {
  id?: string;
  run_id: string;
  seq: number;
  type: string;
  correlation_id?: string | null;
  task_id?: string | null;
  attempt_id?: string | null;
  session_id?: string | null;
  thread_id?: string | null;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface CheckBadgeItem {
  checkId: string;
  taskId: string | null;
  label: string;
  commandText: string;
  status: CheckStatus;
  exitCode: number | null;
  durationSeconds: number | null;
  testedSha: string | null;
  source: 'backend_check' | 'acceptance_spec';
}

export interface TimelineStepItem {
  id: string;
  seq: number | null;
  eventType: string;
  title: string;
  detail: string | null;
  timestamp: string;
  taskId: string | null;
}

export type TimelineRenderItem =
  | {
      kind: 'message';
      id: string;
      seq: number | null;
      role: 'user' | 'coordinator' | 'worker' | 'system';
      author: string;
      content: string;
      timestamp: string;
      taskId: string | null;
      hasUnverifiedCompletionClaim: boolean;
    }
  | {
      kind: 'step_group';
      id: string;
      title: string;
      timestamp: string;
      steps: TimelineStepItem[];
    };

export interface WorkerTraceRow {
  id: string;
  seq: number | null;
  timestamp: string;
  eventType: string;
  summary: string;
  detail?: string;
}

export interface WorkerCardModel {
  taskId: string;
  objective: string;
  status: string;
  mode: 'swarm' | 'relay' | 'persistent';
  wave: number;
  executorId: string;
  provider: string | null;
  model: string | null;
  worktreePath: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  durationSeconds: number | null;
  attemptOrdinal: number | null;
  checks: CheckBadgeItem[];
  traceRows: WorkerTraceRow[];
  canRetry: boolean;
  summary: string | null;
  failures: BackendFailureDetail[];
}

export function createIdempotencyKey(prefix = 'ui-req'): string {
  const cleanPrefix = prefix.replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 16) || 'ui-req';
  const timePart = Date.now().toString(36);
  let randPart = '';
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function') {
    randPart = globalThis.crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  } else {
    randPart = `${Math.random().toString(36).slice(2, 10)}${Math.random().toString(36).slice(2, 10)}`;
  }
  const key = `${cleanPrefix}-${timePart}-${randPart}`;
  return key.slice(0, 64).padEnd(20, '0');
}

export function computeTaskWave(task: BackendTask, allTasks: BackendTask[]): number {
  if (typeof task.wave === 'number' && Number.isFinite(task.wave) && task.wave >= 0) {
    return Math.floor(task.wave);
  }
  const byId = new Map<string, BackendTask>();
  for (const t of allTasks) {
    byId.set(t.task_id || t.id, t);
  }
  const visiting = new Set<string>();
  const memo = new Map<string, number>();

  function resolveDepth(taskId: string): number {
    const cached = memo.get(taskId);
    if (cached !== undefined) {
      return cached;
    }
    if (visiting.has(taskId)) {
      return 0;
    }
    visiting.add(taskId);
    const current = byId.get(taskId);
    const deps = current?.dependencies ?? current?.spec?.dependencies ?? [];
    let maxParent = -1;
    for (const depId of deps) {
      if (byId.has(depId)) {
        maxParent = Math.max(maxParent, resolveDepth(depId));
      }
    }
    visiting.delete(taskId);
    const depth = maxParent + 1;
    memo.set(taskId, depth);
    return depth;
  }

  return resolveDepth(task.task_id || task.id);
}

export function computeDurationSeconds(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): number | null {
  if (!startedAt || !finishedAt) {
    return null;
  }
  const startMs = Date.parse(startedAt);
  const endMs = Date.parse(finishedAt);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
    return null;
  }
  return Math.max(0, Math.round((endMs - startMs) / 1000));
}

function normalizeCheckStatus(rawStatus: unknown, exitCode: number | null): CheckStatus {
  if (exitCode !== null && Number.isFinite(exitCode)) {
    return exitCode === 0 ? 'passed' : 'failed';
  }
  if (rawStatus === 'passed' || rawStatus === 'succeeded') {
    return 'passed';
  }
  if (rawStatus === 'failed' || rawStatus === 'error') {
    return 'failed';
  }
  if (rawStatus === 'pending' || rawStatus === 'running' || rawStatus === 'queued') {
    return 'pending';
  }
  return 'unknown';
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Extracts canonical backend check badges strictly from persisted task/attempt results
 * and structured check events. Assistant/worker text messages NEVER mark a check passed.
 */
export function extractCanonicalChecks(
  snapshot: RunDetailSnapshot | null,
  events: RunSseEvent[],
): CheckBadgeItem[] {
  const byKey = new Map<string, CheckBadgeItem>();

  if (snapshot) {
    for (const task of snapshot.tasks) {
      const tid = task.task_id || task.id;
      for (const spec of task.spec.acceptance_criteria ?? []) {
        const key = `${tid}:${spec.check_id}`;
        byKey.set(key, {
          checkId: spec.check_id,
          taskId: tid,
          label: spec.description || spec.check_id,
          commandText: spec.command.join(' '),
          status: 'pending',
          exitCode: null,
          durationSeconds: null,
          testedSha: null,
          source: 'acceptance_spec',
        });
      }
      const attemptList =
        task.attempts.length > 0
          ? task.attempts
          : task.current_attempt
            ? [task.current_attempt]
            : [];
      for (const att of attemptList) {
        const checks = att.result?.checks ?? [];
        for (const chk of checks) {
          const key = `${tid}:${chk.check_id}`;
          const existing = byKey.get(key);
          byKey.set(key, {
            checkId: chk.check_id,
            taskId: tid,
            label: existing?.label ?? chk.check_id,
            commandText: chk.command.join(' '),
            status: normalizeCheckStatus(chk.status, chk.exit_code),
            exitCode: chk.exit_code,
            durationSeconds: chk.duration_seconds,
            testedSha: chk.tested_sha ?? null,
            source: 'backend_check',
          });
        }
      }
    }
  }

  for (const ev of events) {
    if (ev.type !== 'check.started' && ev.type !== 'check.finished') {
      continue;
    }
    const payload = asRecord(ev.payload);
    const checkId = asString(payload.check_id) ?? asString(payload.id);
    if (!checkId) {
      continue;
    }
    const tid = ev.task_id ?? asString(payload.task_id) ?? 'run';
    const key = `${tid}:${checkId}`;
    const existing = byKey.get(key);
    const exitCode = asNumber(payload.exit_code);
    const rawCmd = Array.isArray(payload.command)
      ? payload.command.filter((c): c is string => typeof c === 'string').join(' ')
      : asString(payload.command) ?? existing?.commandText ?? '';

    const status: CheckStatus =
      ev.type === 'check.started'
        ? existing?.source === 'backend_check'
          ? existing.status
          : 'pending'
        : normalizeCheckStatus(payload.status, exitCode);

    byKey.set(key, {
      checkId,
      taskId: ev.task_id ?? existing?.taskId ?? null,
      label: existing?.label ?? checkId,
      commandText: rawCmd,
      status,
      exitCode: exitCode ?? existing?.exitCode ?? null,
      durationSeconds: asNumber(payload.duration_seconds) ?? existing?.durationSeconds ?? null,
      testedSha: asString(payload.tested_sha) ?? existing?.testedSha ?? null,
      source: ev.type === 'check.finished' ? 'backend_check' : existing?.source ?? 'acceptance_spec',
    });
  }

  return Array.from(byKey.values());
}

const COMPLETION_CLAIM_REGEX =
  /\b(all tests passed|tests passed|checks passed|pronto para revis[aã]o|conclu[ií]do com sucesso|tudo passou|passes all checks)\b/i;

export function detectUnverifiedCompletionClaim(
  text: string,
  checks: CheckBadgeItem[],
): boolean {
  if (!text || !COMPLETION_CLAIM_REGEX.test(text)) {
    return false;
  }
  if (checks.length === 0) {
    return true;
  }
  return checks.some((chk) => chk.status === 'failed' || chk.status === 'pending' || chk.status === 'unknown');
}

function summarizeEvent(ev: RunSseEvent): string {
  const payload = asRecord(ev.payload);
  const explicit =
    asString(payload.summary) ??
    asString(payload.message) ??
    asString(payload.reason) ??
    asString(payload.action);

  if (ev.type === 'check.finished') {
    const chkId = asString(payload.check_id) ?? 'check';
    const exitCode = asNumber(payload.exit_code);
    return exitCode === 0
      ? `Check ${chkId} aprovado (exit 0)`
      : `Check ${chkId} falhou (exit ${exitCode ?? '?'})`;
  }
  if (ev.type === 'check.started') {
    const chkId = asString(payload.check_id) ?? 'check';
    return `Iniciando check ${chkId}`;
  }
  if (ev.type === 'hitl.requested') {
    return asString(payload.question) ?? 'Intervenção humana solicitada';
  }
  if (ev.type === 'hitl.resolved') {
    const state = asString(payload.state) ?? 'resolved';
    return `HITL resolvido (${state})`;
  }
  if (explicit) {
    return explicit;
  }
  return ev.type;
}

export function buildWorkerCards(
  snapshot: RunDetailSnapshot | null,
  events: RunSseEvent[],
): WorkerCardModel[] {
  if (!snapshot) {
    return [];
  }
  const allChecks = extractCanonicalChecks(snapshot, events);
  const eventsByTask = new Map<string, RunSseEvent[]>();
  for (const ev of events) {
    if (!ev.task_id) {
      continue;
    }
    const list = eventsByTask.get(ev.task_id) ?? [];
    list.push(ev);
    eventsByTask.set(ev.task_id, list);
  }

  return snapshot.tasks.map((task) => {
    const tid = task.task_id || task.id;
    const taskEvents = eventsByTask.get(tid) ?? [];
    const current = task.current_attempt;

    let worktreePath: string | null =
      current?.workspace_path ?? task.worktree_path ?? null;
    if (!worktreePath) {
      for (const ev of taskEvents) {
        const p = asRecord(ev.payload);
        const candidate = asString(p.workspace_path) ?? asString(p.worktree_path);
        if (candidate) {
          worktreePath = candidate;
        }
      }
    }

    const durationSeconds = computeDurationSeconds(current?.started_at, current?.finished_at);
    const taskChecks = allChecks.filter((chk) => chk.taskId === tid);

    const traceRows: WorkerTraceRow[] = taskEvents.map((ev, idx) => {
      const payload = asRecord(ev.payload);
      const detail =
        asString(payload.detail) ??
        asString(payload.command) ??
        asString(payload.reason) ??
        undefined;
      return {
        id: `${tid}-trace-${ev.seq || idx}`,
        seq: Number.isFinite(ev.seq) && ev.seq > 0 ? ev.seq : null,
        timestamp: ev.timestamp,
        eventType: ev.type,
        summary: summarizeEvent(ev),
        detail,
      };
    });

    const status = task.status;
    const canRetry = status === 'failed' || status === 'cancelled' || status === 'rejected';

    return {
      taskId: tid,
      objective: task.spec.objective,
      status,
      mode: snapshot.mode,
      wave: computeTaskWave(task, snapshot.tasks),
      executorId: current?.executor_id ?? task.spec.assigned_executor,
      provider: current?.provider ?? null,
      model: current?.model ?? null,
      worktreePath,
      startedAt: current?.started_at ?? null,
      finishedAt: current?.finished_at ?? null,
      durationSeconds,
      attemptOrdinal: current?.ordinal ?? null,
      checks: taskChecks,
      traceRows,
      canRetry,
      summary: current?.result?.summary ?? null,
      failures: current?.result?.failures ?? [],
    };
  });
}

function isMessageEvent(ev: RunSseEvent): {
  role: 'user' | 'coordinator' | 'worker' | 'system';
  author: string;
  content: string;
} | null {
  const payload = asRecord(ev.payload);
  const content =
    asString(payload.content) ??
    asString(payload.text) ??
    asString(payload.message);

  if (
    ev.type === 'thread.message_appended' ||
    ev.type === 'message.created' ||
    ev.type === 'chat.message'
  ) {
    if (!content) {
      return null;
    }
    const rawRole = asString(payload.role) ?? asString(payload.sender);
    const role: 'user' | 'coordinator' | 'worker' | 'system' =
      rawRole === 'user' || rawRole === 'operator'
        ? 'user'
        : rawRole === 'worker' || Boolean(ev.task_id)
          ? 'worker'
          : rawRole === 'system'
            ? 'system'
            : 'coordinator';
    const author =
      asString(payload.author) ??
      asString(payload.agent_ref) ??
      (role === 'user'
        ? 'Operador'
        : role === 'worker'
          ? `Worker (${ev.task_id ?? 'subagent'})`
          : 'Coordenador');
    return { role, author, content };
  }

  if (ev.type === 'assistant.message' || ev.type === 'coordinator.message' || ev.type === 'worker.message') {
    if (!content) {
      return null;
    }
    const role = ev.type === 'worker.message' ? 'worker' : 'coordinator';
    return {
      role,
      author: asString(payload.author) ?? (role === 'worker' ? `Worker (${ev.task_id ?? 'subagent'})` : 'Coordenador'),
      content,
    };
  }

  return null;
}

export function buildCoordinatorTimeline(
  snapshot: RunDetailSnapshot | null,
  events: RunSseEvent[],
): TimelineRenderItem[] {
  const items: TimelineRenderItem[] = [];
  const canonicalChecks = extractCanonicalChecks(snapshot, events);

  if (snapshot?.objective) {
    items.push({
      kind: 'message',
      id: `run-objective-${snapshot.run_id}`,
      seq: 0,
      role: 'user',
      author: 'Operador',
      content: snapshot.objective,
      timestamp: snapshot.created_at,
      taskId: null,
      hasUnverifiedCompletionClaim: false,
    });
  }

  let pendingSteps: TimelineStepItem[] = [];

  const flushSteps = () => {
    if (pendingSteps.length === 0) {
      return;
    }
    const first = pendingSteps[0];
    items.push({
      kind: 'step_group',
      id: `step-group-${first.id}`,
      title: `Passos de coordenação (${pendingSteps.length})`,
      timestamp: first.timestamp,
      steps: pendingSteps,
    });
    pendingSteps = [];
  };

  for (let i = 0; i < events.length; i += 1) {
    const ev = events[i];
    const msg = isMessageEvent(ev);
    if (msg) {
      flushSteps();
      const relevantChecks = ev.task_id
        ? canonicalChecks.filter((c) => c.taskId === ev.task_id)
        : canonicalChecks;
      items.push({
        kind: 'message',
        id: `msg-${ev.seq || i}-${ev.id ?? 'ev'}`,
        seq: ev.seq > 0 ? ev.seq : null,
        role: msg.role,
        author: msg.author,
        content: msg.content,
        timestamp: ev.timestamp,
        taskId: ev.task_id ?? null,
        hasUnverifiedCompletionClaim:
          (msg.role === 'coordinator' || msg.role === 'worker') &&
          detectUnverifiedCompletionClaim(msg.content, relevantChecks),
      });
    } else {
      const payload = asRecord(ev.payload);
      const detail =
        asString(payload.detail) ??
        asString(payload.reason) ??
        asString(payload.command) ??
        null;
      pendingSteps.push({
        id: `step-${ev.seq || i}-${ev.type}`,
        seq: ev.seq > 0 ? ev.seq : null,
        eventType: ev.type,
        title: summarizeEvent(ev),
        detail,
        timestamp: ev.timestamp,
        taskId: ev.task_id ?? null,
      });
    }
  }

  flushSteps();
  return items;
}
