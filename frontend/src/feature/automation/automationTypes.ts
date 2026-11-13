export type OverlapPolicy = 'skip' | 'queue' | 'allow';
export type MissedPolicy = 'skip' | 'run_once';
export type ScheduleMode = 'cron' | 'interval';

export type AutomationRunStatus =
  | 'pending'
  | 'dispatched'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'missed';

export interface AutomationSchedule {
  id: string;
  name: string;
  workspace_id: string | null;
  project_id: string | null;
  target_host: string;
  executor_id: string;
  prompt: string;
  cron_expr: string | null;
  interval_seconds: number | null;
  timezone: string;
  enabled: boolean;
  overlap_policy: OverlapPolicy;
  missed_policy: MissedPolicy;
  max_retries: number;
  next_run_at: string | null;
  last_run_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface AutomationCreatePayload {
  name: string;
  prompt: string;
  cron_expr?: string;
  interval_seconds?: number;
  timezone: string;
  workspace_id?: string | null;
  project_id?: string | null;
  target_host: string;
  executor_id: string;
  enabled: boolean;
  overlap_policy: OverlapPolicy;
  missed_policy: MissedPolicy;
  max_retries: number;
}

export interface AutomationUpdatePayload {
  name?: string;
  prompt?: string;
  cron_expr?: string;
  interval_seconds?: number;
  timezone?: string;
  workspace_id?: string | null;
  project_id?: string | null;
  target_host?: string;
  executor_id?: string;
  enabled?: boolean;
  overlap_policy?: OverlapPolicy;
  missed_policy?: MissedPolicy;
  max_retries?: number;
  expected_revision: number;
}

export interface AutomationStatePayload {
  expected_revision: number;
}

export interface AutomationRunRecord {
  id: string;
  schedule_id: string;
  occurrence_key: string;
  scheduled_for: string;
  run_id: string | null;
  status: AutomationRunStatus;
  attempt_count: number;
  error_detail: string | null;
  dispatched_at: string;
  finished_at: string | null;
}

export interface AutomationTriggerResult {
  automation_run_id?: string;
  id?: string;
  schedule_id: string;
  occurrence_key: string;
  scheduled_for: string;
  run_id: string | null;
  status: AutomationRunStatus;
  attempt_count: number;
  error_detail: string | null;
  dispatched_at: string;
  finished_at: string | null;
  metadata?: Record<string, unknown>;
}

export interface AutomationDeleteResult {
  deleted: boolean;
  schedule_id: string;
}

export interface AutomationFormValues {
  name: string;
  prompt: string;
  scheduleMode: ScheduleMode;
  cronExpr: string;
  intervalSeconds: string;
  timezone: string;
  targetHost: string;
  executorId: string;
  workspaceId: string;
  projectId: string;
  enabled: boolean;
  overlapPolicy: OverlapPolicy;
  missedPolicy: MissedPolicy;
  maxRetries: string;
}

export interface AutomationFormValidationResult {
  valid: boolean;
  error: string | null;
}

export const COMMON_IANA_TIMEZONES: ReadonlyArray<string> = [
  'America/Sao_Paulo',
  'UTC',
  'America/New_York',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Lisbon',
  'Asia/Tokyo',
];

export const OVERLAP_POLICY_LABELS: Record<OverlapPolicy, string> = {
  skip: 'Ignorar sobreposição (skip)',
  queue: 'Enfileirar próxima (queue)',
  allow: 'Permitir paralelo (allow)',
};

export const MISSED_POLICY_LABELS: Record<MissedPolicy, string> = {
  skip: 'Ignorar atrasadas (skip)',
  run_once: 'Executar uma vez (run_once)',
};

export const AUTOMATION_RUN_STATUS_META: Record<
  AutomationRunStatus,
  { badgeStatus: string; label: string }
> = {
  pending: { badgeStatus: 'queued', label: 'Pendente' },
  dispatched: { badgeStatus: 'running', label: 'Despachada' },
  succeeded: { badgeStatus: 'succeeded', label: 'Concluída' },
  failed: { badgeStatus: 'failed', label: 'Falhou' },
  skipped: { badgeStatus: 'cancelled', label: 'Ignorada' },
  missed: { badgeStatus: 'stale', label: 'Perdida' },
};

const CRON_SHORTCUTS = new Set([
  '@hourly',
  '@daily',
  '@midnight',
  '@weekly',
  '@monthly',
  '@yearly',
  '@annually',
]);

export function createDefaultAutomationFormValues(
  defaults?: Partial<Pick<AutomationFormValues, 'workspaceId' | 'projectId' | 'targetHost'>>,
): AutomationFormValues {
  return {
    name: '',
    prompt: '',
    scheduleMode: 'cron',
    cronExpr: '0 * * * *',
    intervalSeconds: '300',
    timezone: 'America/Sao_Paulo',
    targetHost: defaults?.targetHost?.trim() || 'local',
    executorId: 'codex',
    workspaceId: defaults?.workspaceId?.trim() ?? '',
    projectId: defaults?.projectId?.trim() ?? '',
    enabled: true,
    overlapPolicy: 'skip',
    missedPolicy: 'skip',
    maxRetries: '0',
  };
}

export function formValuesFromSchedule(schedule: AutomationSchedule): AutomationFormValues {
  const usesInterval =
    schedule.interval_seconds !== null &&
    schedule.interval_seconds !== undefined &&
    schedule.cron_expr === null;

  return {
    name: schedule.name,
    prompt: schedule.prompt,
    scheduleMode: usesInterval ? 'interval' : 'cron',
    cronExpr: schedule.cron_expr ?? '0 * * * *',
    intervalSeconds:
      schedule.interval_seconds !== null && schedule.interval_seconds !== undefined
        ? String(schedule.interval_seconds)
        : '300',
    timezone: schedule.timezone || 'UTC',
    targetHost: schedule.target_host || 'local',
    executorId: schedule.executor_id || 'codex',
    workspaceId: schedule.workspace_id ?? '',
    projectId: schedule.project_id ?? '',
    enabled: schedule.enabled,
    overlapPolicy: schedule.overlap_policy,
    missedPolicy: schedule.missed_policy,
    maxRetries: String(schedule.max_retries ?? 0),
  };
}

export function isValidIanaTimezone(timezone: string): boolean {
  const trimmed = timezone.trim();
  if (!trimmed || trimmed.length > 64 || /\s/.test(trimmed) || trimmed.includes('\0')) {
    return false;
  }
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: trimmed });
    return true;
  } catch {
    return false;
  }
}

export function validateAutomationForm(
  values: AutomationFormValues,
): AutomationFormValidationResult {
  const name = values.name.trim();
  if (!name || name.length > 128 || name.includes('\0')) {
    return {
      valid: false,
      error: 'Informe um nome válido para a automação (entre 1 e 128 caracteres).',
    };
  }

  const prompt = values.prompt.trim();
  if (!prompt || prompt.length > 10_000 || prompt.includes('\0')) {
    return {
      valid: false,
      error: 'Informe um prompt válido para a execução (até 10.000 caracteres).',
    };
  }

  if (!isValidIanaTimezone(values.timezone)) {
    return {
      valid: false,
      error: `Fuso horário IANA inválido: "${values.timezone}". Exemplos válidos: America/Sao_Paulo, UTC.`,
    };
  }

  if (values.scheduleMode === 'cron') {
    const cron = values.cronExpr.trim();
    if (!cron || cron.includes('\0')) {
      return { valid: false, error: 'Informe uma expressão cron válida.' };
    }
    const lower = cron.toLowerCase();
    if (!CRON_SHORTCUTS.has(lower)) {
      const fields = cron.split(/\s+/);
      if (fields.length !== 5) {
        return {
          valid: false,
          error: 'A expressão cron deve conter 5 campos (min hora dia mês dia_semana) ou um atalho padrão (@hourly, @daily).',
        };
      }
    }
  } else {
    const parsedInterval = Number(values.intervalSeconds.trim());
    if (!Number.isInteger(parsedInterval) || parsedInterval < 60) {
      return {
        valid: false,
        error: 'O intervalo deve ser um número inteiro maior ou igual a 60 segundos.',
      };
    }
  }

  const host = values.targetHost.trim();
  if (!host || host.length > 64 || host.includes('\0')) {
    return { valid: false, error: 'Selecione um host alvo válido.' };
  }

  const executor = values.executorId.trim();
  if (!executor || executor.length > 64 || executor.includes('\0')) {
    return { valid: false, error: 'Selecione um executor válido.' };
  }

  const retries = Number(values.maxRetries.trim() === '' ? '0' : values.maxRetries.trim());
  if (!Number.isInteger(retries) || retries < 0 || retries > 5) {
    return {
      valid: false,
      error: 'O máximo de retentativas deve ser um inteiro entre 0 e 5.',
    };
  }

  return { valid: true, error: null };
}

export function formatScheduleTiming(schedule: AutomationSchedule): string {
  if (schedule.cron_expr) {
    return `Cron: ${schedule.cron_expr}`;
  }
  if (schedule.interval_seconds !== null && schedule.interval_seconds !== undefined) {
    const secs = schedule.interval_seconds;
    if (secs % 3600 === 0) {
      return `Intervalo: ${secs}s (${secs / 3600}h)`;
    }
    if (secs % 60 === 0) {
      return `Intervalo: ${secs}s (${secs / 60}min)`;
    }
    return `Intervalo: ${secs}s`;
  }
  return 'Agendamento não definido';
}

export function formatAutomationTimestamp(
  value: string | null | undefined,
  emptyLabel = '—',
): string {
  if (!value || typeof value !== 'string' || value.trim().length === 0) {
    return emptyLabel;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(parsed);
  } catch {
    return value;
  }
}
