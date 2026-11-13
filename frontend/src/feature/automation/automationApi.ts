import type { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  AutomationCreatePayload,
  AutomationDeleteResult,
  AutomationFormValues,
  AutomationRunRecord,
  AutomationSchedule,
  AutomationTriggerResult,
  AutomationUpdatePayload,
} from './automationTypes';

export interface ListAutomationsParams {
  workspace_id?: string;
  project_id?: string;
  enabled?: boolean;
}

function unwrapArrayResponse<T>(raw: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(raw)) {
    return raw;
  }
  if (raw && typeof raw === 'object' && Array.isArray(raw.items)) {
    return raw.items;
  }
  return [];
}

function buildCreateTiming(
  values: AutomationFormValues,
): Pick<AutomationCreatePayload, 'cron_expr'> | Pick<AutomationCreatePayload, 'interval_seconds'> {
  if (values.scheduleMode === 'interval') {
    const parsed = Math.trunc(Number(values.intervalSeconds.trim()));
    return { interval_seconds: parsed };
  }
  return { cron_expr: values.cronExpr.trim() };
}

export function buildCreateAutomationPayload(
  values: AutomationFormValues,
): AutomationCreatePayload {
  const workspaceId = values.workspaceId.trim();
  const projectId = values.projectId.trim();
  const retries = Math.trunc(Number(values.maxRetries.trim() === '' ? '0' : values.maxRetries.trim()));
  const timing = buildCreateTiming(values);

  const payload: AutomationCreatePayload = {
    name: values.name.trim(),
    prompt: values.prompt.trim(),
    ...timing,
    timezone: values.timezone.trim(),
    target_host: values.targetHost.trim() || 'local',
    executor_id: values.executorId.trim() || 'codex',
    enabled: values.enabled,
    overlap_policy: values.overlapPolicy,
    missed_policy: values.missedPolicy,
    max_retries: retries,
  };

  if (workspaceId.length > 0) {
    payload.workspace_id = workspaceId;
  }
  if (projectId.length > 0) {
    payload.project_id = projectId;
  }

  return payload;
}

export function buildUpdateAutomationPayload(
  values: AutomationFormValues,
  expectedRevision: number,
): AutomationUpdatePayload {
  const workspaceId = values.workspaceId.trim();
  const projectId = values.projectId.trim();
  const retries = Math.trunc(Number(values.maxRetries.trim() === '' ? '0' : values.maxRetries.trim()));
  const timing = buildCreateTiming(values);

  return {
    name: values.name.trim(),
    prompt: values.prompt.trim(),
    ...timing,
    timezone: values.timezone.trim(),
    workspace_id: workspaceId.length > 0 ? workspaceId : null,
    project_id: projectId.length > 0 ? projectId : null,
    target_host: values.targetHost.trim() || 'local',
    executor_id: values.executorId.trim() || 'codex',
    enabled: values.enabled,
    overlap_policy: values.overlapPolicy,
    missed_policy: values.missedPolicy,
    max_retries: retries,
    expected_revision: expectedRevision,
  };
}

function assertExclusiveTiming(payload: {
  cron_expr?: string;
  interval_seconds?: number;
}): void {
  const hasCron = typeof payload.cron_expr === 'string' && payload.cron_expr.trim().length > 0;
  const hasInterval = typeof payload.interval_seconds === 'number';
  if (hasCron && hasInterval) {
    throw new Error('Contrato inválido: envie apenas cron_expr ou interval_seconds, nunca ambos.');
  }
}

export function isOptimisticLockConflict(error: unknown): boolean {
  return error instanceof ControlPlaneApiError && error.status === 409;
}

export function formatAutomationApiError(error: unknown, fallback: string): string {
  if (error instanceof ControlPlaneApiError) {
    return `${error.payload.message} (${error.payload.code})`;
  }
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

export async function listAutomations(
  client: ControlPlaneClient,
  params?: ListAutomationsParams,
  signal?: AbortSignal,
): Promise<AutomationSchedule[]> {
  const sp = new URLSearchParams();
  if (params?.workspace_id) {
    sp.set('workspace_id', params.workspace_id);
  }
  if (params?.project_id) {
    sp.set('project_id', params.project_id);
  }
  if (typeof params?.enabled === 'boolean') {
    sp.set('enabled', String(params.enabled));
  }
  const suffix = sp.toString() ? `?${sp.toString()}` : '';
  const raw = await client.request<AutomationSchedule[] | { items?: AutomationSchedule[] }>(
    `/v1/control-plane/automations${suffix}`,
    { method: 'GET', signal },
  );
  return unwrapArrayResponse(raw);
}

export async function createAutomation(
  client: ControlPlaneClient,
  payload: AutomationCreatePayload,
): Promise<AutomationSchedule> {
  assertExclusiveTiming(payload);
  const body: AutomationCreatePayload = { ...payload };
  if (body.cron_expr === undefined) {
    delete body.cron_expr;
  }
  if (body.interval_seconds === undefined) {
    delete body.interval_seconds;
  }
  return client.request<AutomationSchedule>('/v1/control-plane/automations', {
    method: 'POST',
    body,
  });
}

export async function updateAutomation(
  client: ControlPlaneClient,
  scheduleId: string,
  payload: AutomationUpdatePayload,
): Promise<AutomationSchedule> {
  assertExclusiveTiming(payload);
  const body: AutomationUpdatePayload = { ...payload };
  if (body.cron_expr === undefined) {
    delete body.cron_expr;
  }
  if (body.interval_seconds === undefined) {
    delete body.interval_seconds;
  }
  return client.request<AutomationSchedule>(
    `/v1/control-plane/automations/${encodeURIComponent(scheduleId)}`,
    {
      method: 'PUT',
      body,
    },
  );
}

export async function deleteAutomation(
  client: ControlPlaneClient,
  scheduleId: string,
): Promise<AutomationDeleteResult> {
  return client.request<AutomationDeleteResult>(
    `/v1/control-plane/automations/${encodeURIComponent(scheduleId)}`,
    {
      method: 'DELETE',
    },
  );
}

export async function pauseAutomation(
  client: ControlPlaneClient,
  scheduleId: string,
  expectedRevision: number,
): Promise<AutomationSchedule> {
  return client.request<AutomationSchedule>(
    `/v1/control-plane/automations/${encodeURIComponent(scheduleId)}/pause`,
    {
      method: 'POST',
      body: { expected_revision: expectedRevision },
    },
  );
}

export async function resumeAutomation(
  client: ControlPlaneClient,
  scheduleId: string,
  expectedRevision: number,
): Promise<AutomationSchedule> {
  return client.request<AutomationSchedule>(
    `/v1/control-plane/automations/${encodeURIComponent(scheduleId)}/resume`,
    {
      method: 'POST',
      body: { expected_revision: expectedRevision },
    },
  );
}

export async function triggerAutomation(
  client: ControlPlaneClient,
  scheduleId: string,
): Promise<AutomationTriggerResult> {
  return client.request<AutomationTriggerResult>(
    `/v1/control-plane/automations/${encodeURIComponent(scheduleId)}/trigger`,
    {
      method: 'POST',
    },
  );
}

export async function listAutomationRuns(
  client: ControlPlaneClient,
  scheduleId: string,
  limit = 100,
  signal?: AbortSignal,
): Promise<AutomationRunRecord[]> {
  const raw = await client.request<AutomationRunRecord[] | { items?: AutomationRunRecord[] }>(
    `/v1/control-plane/automations/${encodeURIComponent(scheduleId)}/runs?limit=${encodeURIComponent(String(limit))}`,
    { method: 'GET', signal },
  );
  return unwrapArrayResponse(raw);
}
