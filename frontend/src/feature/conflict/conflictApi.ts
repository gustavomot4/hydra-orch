import type { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';

export type ReviewDecision = 'accepted' | 'rejected' | 'needs_repair';
export type ConflictResolutionOption = 'auto_repair' | 'manual' | 'discarded';
export type ConflictStatus = 'open' | 'auto_repair' | 'manual' | 'discarded';

export interface RunTaskCheck {
  check_id: string;
  exit_code: number;
  duration_seconds: number;
  tested_sha?: string;
}

export interface RunTaskFailure {
  code: string;
  message: string;
  retryable?: boolean;
}

export interface RunTaskResult {
  id: string;
  result_id: string;
  attempt_id: string;
  exit_code: number | null;
  simulated: boolean;
  outcome: 'success' | 'partial' | 'failure' | string;
  task_status: string;
  revision: number;
  summary: string;
  patch_commit_sha: string | null;
  patch_artifact_id: string | null;
  changed_files: string[];
  checks: RunTaskCheck[];
  failures: RunTaskFailure[];
}

export interface RunTaskAttempt {
  id: string;
  attempt_id: string;
  task_id: string;
  ordinal: number;
  executor_id: string;
  provider: string;
  model: string;
  process_status: string;
  exit_code: number | null;
  result: RunTaskResult | null;
}

export interface RunTaskSpec {
  task_id?: string;
  title?: string;
  description?: string;
  assigned_executor?: string;
  [key: string]: unknown;
}

export interface RunTaskItem {
  id: string;
  task_id: string;
  run_id: string;
  spec: RunTaskSpec;
  status: string;
  revision: number;
  dependencies: string[];
  current_attempt: RunTaskAttempt | null;
  attempts: RunTaskAttempt[];
  created_at: string;
  updated_at: string;
}

export interface ReviewPayload {
  decision: ReviewDecision;
  reason: string;
  expected_revision: number;
  actor?: string;
  result_id?: string | null;
  expected_task_revision?: number | null;
}

export interface ReviewResponse {
  review_id: string;
  result_id: string;
  task_id: string;
  run_id: string;
  decision: string;
  task_status: string;
  revision: number;
  created_at: string;
}

export interface ConflictedFileDetail {
  path: string;
  base_content: string | null;
  ours_content: string | null;
  theirs_content: string | null;
  merged_preview: string;
  hunks: string[];
}

export interface ConflictReport {
  conflict_id: string;
  integration_id: string;
  run_id: string;
  base_sha: string;
  ours_sha: string;
  theirs_sha: string;
  conflicted_files: string[];
  file_details: ConflictedFileDetail[];
  resolution_options: ConflictResolutionOption[];
  status: ConflictStatus;
  repair_attempts_used: number;
  max_repair_attempts: number;
  repair_worktree_path: string | null;
  repair_branch: string | null;
  resolved_sha: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

export interface ConflictAutoRepairPayload {
  max_repair_attempts?: number;
  repair_command?: string[];
  allowed_paths?: string[];
  forbidden_paths?: string[];
  idempotency_key?: string;
}

export interface ConflictManualPayload {
  finalize?: boolean;
  worktree_path?: string;
  commit_message?: string;
  idempotency_key?: string;
}

export interface ConflictDiscardPayload {
  reason?: string;
  idempotency_key?: string;
}

export interface RepairResult {
  conflict_id: string;
  integration_id: string;
  run_id: string;
  option: ConflictResolutionOption;
  status: ConflictStatus;
  repaired: boolean;
  attempt_number: number;
  repair_attempt_id?: string | null;
  repair_worktree_path: string | null;
  repair_branch: string | null;
  resolved_sha: string | null;
  checks_executed: Array<Record<string, unknown>>;
  failures: Array<Record<string, unknown>>;
  resolved_at: string | null;
  prompt_context?: Record<string, unknown> | null;
}

export interface IntegratePayload {
  force?: boolean;
  target_branch?: string | null;
  cleanup_on_success?: boolean;
}

export interface IntegrateResponse {
  integration_id: string;
  status: 'succeeded' | 'conflicted' | string;
  integration_status?: string;
  result_sha?: string | null;
  target_branch?: string | null;
  conflicted_files?: string[];
  conflict_report_id: string | null;
}

export interface PRPackageDiffFile {
  path: string;
  insertions: number | null;
  deletions: number | null;
}

export interface PRPackageCheckSummary {
  total: number;
  passed: number;
  failed: number;
  checks: Array<Record<string, unknown>>;
}

export interface PRPackageDiffSummary {
  files_changed: number;
  insertions: number | null;
  deletions: number | null;
  files: PRPackageDiffFile[];
}

export interface PRPackage {
  package_id: string;
  run_id: string;
  pr_branch: string;
  base_branch: string;
  base_sha: string;
  head_sha: string;
  description_markdown: string;
  commits: Array<Record<string, unknown>>;
  checks_summary: PRPackageCheckSummary;
  diff_summary: PRPackageDiffSummary;
  metrics: Record<string, unknown>;
  review_decisions: Array<Record<string, unknown>>;
  artifact_id: string | null;
  artifact_path: string | null;
  artifact_sha256: string | null;
  created_at: string;
}

export interface PRPackageBuildPayload {
  pr_branch?: string | null;
  create_git_branch?: boolean;
}

export interface PRPackagePublishPayload {
  authorized: boolean;
  policy_authorized?: boolean | null;
  remote?: string;
}

export interface PublishResult {
  package_id: string;
  run_id: string;
  pr_branch: string;
  remote: string;
  pushed_sha: string;
  published: boolean;
  published_at: string;
}

export function generateIdempotencyKey(prefix = 'hydra-conflict'): string {
  const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 18) || 'hydra';
  const rand =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID().replace(/-/g, '')
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`;
  const combined = `${safePrefix}-${rand}`;
  return combined.slice(0, 64).padEnd(20, '0');
}

export function extractConflictedFilesFromError(error: unknown): string[] {
  if (!(error instanceof ControlPlaneApiError)) {
    return [];
  }
  const details = error.payload.details;
  if (details && typeof details === 'object' && 'conflicted_files' in details) {
    const files = (details as { conflicted_files?: unknown }).conflicted_files;
    if (Array.isArray(files)) {
      return files.filter((item): item is string => typeof item === 'string');
    }
  }
  return [];
}

export function formatNullableMetric(value: number | null | undefined, unknownLabel = '—'): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return unknownLabel;
  }
  return String(value);
}

export async function listRunTasks(
  client: ControlPlaneClient,
  runId: string,
  signal?: AbortSignal,
): Promise<RunTaskItem[]> {
  return client.request<RunTaskItem[]>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/tasks`,
    { method: 'GET', signal },
  );
}

export async function reviewTask(
  client: ControlPlaneClient,
  runId: string,
  taskId: string,
  payload: ReviewPayload,
): Promise<ReviewResponse> {
  return client.request<ReviewResponse>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(taskId)}/review`,
    {
      method: 'POST',
      body: payload,
    },
  );
}

export async function listRunConflicts(
  client: ControlPlaneClient,
  runId: string,
  signal?: AbortSignal,
): Promise<ConflictReport[]> {
  return client.request<ConflictReport[]>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/conflicts`,
    { method: 'GET', signal },
  );
}

export async function autoRepairConflict(
  client: ControlPlaneClient,
  runId: string,
  conflictId: string,
  payload: ConflictAutoRepairPayload = {},
): Promise<RepairResult> {
  const body: ConflictAutoRepairPayload = {
    ...payload,
    idempotency_key: payload.idempotency_key ?? generateIdempotencyKey('auto-repair'),
  };
  return client.request<RepairResult>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/conflicts/${encodeURIComponent(conflictId)}/auto-repair`,
    {
      method: 'POST',
      body,
    },
  );
}

export async function manualResolveConflict(
  client: ControlPlaneClient,
  runId: string,
  conflictId: string,
  payload: ConflictManualPayload = {},
): Promise<RepairResult> {
  const body: ConflictManualPayload = {
    ...payload,
    idempotency_key: payload.idempotency_key ?? generateIdempotencyKey('manual-res'),
  };
  return client.request<RepairResult>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/conflicts/${encodeURIComponent(conflictId)}/manual`,
    {
      method: 'POST',
      body,
    },
  );
}

export async function discardConflict(
  client: ControlPlaneClient,
  runId: string,
  conflictId: string,
  payload: ConflictDiscardPayload = {},
): Promise<RepairResult> {
  const body: ConflictDiscardPayload = {
    ...payload,
    idempotency_key: payload.idempotency_key ?? generateIdempotencyKey('discard-cnf'),
  };
  return client.request<RepairResult>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/conflicts/${encodeURIComponent(conflictId)}/discard`,
    {
      method: 'POST',
      body,
    },
  );
}

export async function integrateRun(
  client: ControlPlaneClient,
  runId: string,
  payload: IntegratePayload = {},
): Promise<IntegrateResponse> {
  return client.request<IntegrateResponse>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/integrate`,
    {
      method: 'POST',
      body: payload,
    },
  );
}

export async function getPrPackage(
  client: ControlPlaneClient,
  runId: string,
  signal?: AbortSignal,
): Promise<PRPackage | null> {
  try {
    return await client.request<PRPackage>(
      `/v1/control-plane/runs/${encodeURIComponent(runId)}/pr-package`,
      { method: 'GET', signal },
    );
  } catch (error) {
    if (error instanceof ControlPlaneApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function buildPrPackage(
  client: ControlPlaneClient,
  runId: string,
  payload: PRPackageBuildPayload = {},
): Promise<PRPackage> {
  return client.request<PRPackage>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/pr-package`,
    {
      method: 'POST',
      body: payload,
    },
  );
}

export async function publishPrPackage(
  client: ControlPlaneClient,
  runId: string,
  payload: PRPackagePublishPayload,
): Promise<PublishResult> {
  return client.request<PublishResult>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/pr-package/publish`,
    {
      method: 'POST',
      body: payload,
    },
  );
}
