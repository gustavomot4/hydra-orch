import type { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import type {
  BudgetDimensionReport,
  BudgetStatus,
  CertifyTransportPayload,
  CertifyTransportResponse,
  ConsentCreatePayload,
  ConsentDecisionAction,
  ConsentPurpose,
  ConsentRecord,
  CreateSecretRefPayload,
  CreateSkillPayload,
  DiscoveredResourceRaw,
  DiscoveryScanPayload,
  ExtendBudgetPayload,
  ExtendBudgetResponse,
  ExtensionInstallItem,
  ExtensionInstallPayload,
  GovernanceRunSummary,
  GovernanceScopeType,
  McpItem,
  MemoryEntry,
  MemoryWritePayload,
  NormalizedDiscoveredResource,
  RevokeResourceResponse,
  SecretRefItem,
  SkillItem,
  TransportHealthResult,
  TransportItem,
} from './governanceTypes';

export const BASE_SKILL_PERMISSIONS = [
  'fs:read',
  'fs:write',
  'net:loopback',
  'net:external',
  'process:spawn',
] as const;

export const SSH_REQUIRED_CHECKS = [
  'host_key_verified',
  'target_identity',
  'healthcheck',
  'host_key_verification',
  'session_isolation',
] as const;

const SHA256_HEX_RE = /^[a-f0-9]{64}$/;
const SECRET_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;
const SOURCE_KEY_RE = /^[A-Za-z_][A-Za-z0-9_.:/-]{0,127}$/;

const RAW_SECRET_RULES: ReadonlyArray<{ regex: RegExp; reason: string }> = [
  {
    regex: /(?:^|[\s:=/"'])sk-[A-Za-z0-9_-]*/i,
    reason:
      'Segredo bruto bloqueado (prefixo sk-). Informe apenas referências/metadados externos.',
  },
  {
    regex: /(?:^|[\s:=/"'])sk_[A-Za-z0-9_-]{3,}/i,
    reason:
      'Segredo bruto bloqueado (prefixo sk_). Informe apenas referências/metadados externos.',
  },
  {
    regex: /\b(?:ghp_|github_pat_|glpat-|xox[baprs]-|hydra_tok_)[A-Za-z0-9_-]*/i,
    reason:
      'Token de provedor bloqueado. Esta interface aceita somente referências de metadados.',
  },
  {
    regex: /\b(?:akia|aiza)[A-Za-z0-9_-]{8,}/i,
    reason:
      'Chave de provedor bloqueada. Valores literais de segredo não são permitidos.',
  },
  {
    regex: /\bBearer\s+\S+/i,
    reason: 'Credencial Bearer bloqueada. Nunca insira tokens literais.',
  },
  {
    regex: /-----BEGIN/i,
    reason: 'Bloco de chave privada (-----BEGIN) bloqueado na interface.',
  },
  {
    regex: /\b[a-z][a-z0-9+.-]*:\/\/[^/\s@]+@/i,
    reason: 'Credenciais embutidas em URL foram bloqueadas.',
  },
  {
    regex:
      /\b(?:password|passwd|secret|api[_-]?key|client[_-]?secret|(?:access[_-]?|refresh[_-]?|oauth[_-]?)?token)\s*[:=]\s*\S+/i,
    reason: 'Atribuição de credencial detectada e bloqueada.',
  },
];

export function detectRawSecretInInput(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }
  for (const rule of RAW_SECRET_RULES) {
    if (rule.regex.test(trimmed)) {
      return rule.reason;
    }
  }
  if (
    trimmed.length >= 24 &&
    !/[_./:\s-]/.test(trimmed) &&
    /\d/.test(trimmed) &&
    /[a-z]/.test(trimmed) &&
    /[A-Z]/.test(trimmed)
  ) {
    return 'Literal de alta entropia bloqueado. Use um identificador de referência (ex.: OPENAI_API_KEY).';
  }
  return null;
}

export function validateSecretRefInput(input: {
  secret_name: string;
  source_key: string;
}): { valid: boolean; reason: string | null } {
  const name = input.secret_name.trim();
  const sourceKey = input.source_key.trim();

  const nameSecretReason = detectRawSecretInInput(name);
  if (nameSecretReason) {
    return { valid: false, reason: `secret_name inválido: ${nameSecretReason}` };
  }
  const sourceSecretReason = detectRawSecretInInput(sourceKey);
  if (sourceSecretReason) {
    return { valid: false, reason: `source_key inválido: ${sourceSecretReason}` };
  }

  if (!name) {
    return { valid: false, reason: 'Informe o nome simbólico do segredo (secret_name).' };
  }
  if (!SECRET_NAME_RE.test(name)) {
    return {
      valid: false,
      reason:
        'secret_name deve seguir o padrão de identificador de ambiente (ex.: OPENAI_API_KEY).',
    };
  }
  if (!sourceKey) {
    return { valid: false, reason: 'Informe a chave de origem externa (source_key).' };
  }
  if (!SOURCE_KEY_RE.test(sourceKey)) {
    return {
      valid: false,
      reason:
        'source_key deve ser um identificador de referência válido (ex.: OPENAI_API_KEY ou secret/data/openai).',
    };
  }
  return { valid: true, reason: null };
}

export function redactTextForUi(value: string): string {
  if (!value) {
    return value;
  }
  return value
    .replace(/-----BEGIN[\s\S]*$/gi, '[REDACTED]')
    .replace(/(?:sk-|sk_|ghp_|github_pat_|glpat-|xox[baprs]-|hydra_tok_)[A-Za-z0-9_-]*/gi, '[REDACTED]')
    .replace(/\bBearer\s+[^\s"']+/gi, 'Bearer [REDACTED]')
    .replace(/(\b[a-z][a-z0-9+.-]*:\/\/)[^/\s@]+@/gi, '$1[REDACTED]@');
}

export function isValidSha256Hex(value: string): boolean {
  return SHA256_HEX_RE.test(value.trim());
}

export function isGovernanceConflictError(error: unknown): boolean {
  if (!(error instanceof ControlPlaneApiError)) {
    return false;
  }
  if (error.status === 409) {
    return true;
  }
  return error.payload.code.toLowerCase().includes('conflict');
}

export function extractGovernanceErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ControlPlaneApiError) {
    return `${error.payload.message} (${error.payload.code})`;
  }
  if (error instanceof Error && error.message.trim().length > 0) {
    return redactTextForUi(error.message);
  }
  return fallback;
}

function unwrapArray<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) {
    return raw as T[];
  }
  if (
    raw &&
    typeof raw === 'object' &&
    'items' in raw &&
    Array.isArray((raw as { items?: unknown }).items)
  ) {
    return (raw as { items: T[] }).items;
  }
  return [];
}

export function normalizeDiscoveredResource(
  raw: DiscoveredResourceRaw,
): NormalizedDiscoveredResource {
  const resourceId = raw.resource_id ?? raw.id ?? raw.discovery_id ?? '';
  const kind = raw.resource_type ?? raw.kind ?? 'unknown';
  const path = raw.source_canonical_path ?? raw.path ?? '—';
  const hash = raw.content_hash ?? raw.checksum ?? raw.sha256 ?? raw.hash ?? '';
  const status = raw.trust_status ?? raw.status ?? 'untrusted';
  return {
    resourceId,
    kind,
    path,
    hash,
    status,
    capabilities: Array.isArray(raw.capabilities) ? raw.capabilities : [],
    discoveredAt: raw.discovered_at ?? null,
    approvedAt: raw.approved_at ?? null,
    approvedBy: raw.approved_by ?? null,
  };
}

export function formatConsentScope(consent: ConsentRecord): string {
  if (consent.scope && consent.scope.trim().length > 0) {
    return consent.scope;
  }
  const sType = consent.scope_type ?? '—';
  const sId = consent.scope_id ?? '—';
  return `${sType}:${sId}`;
}

export function formatTransportCapabilities(
  caps: string[] | Record<string, unknown> | undefined,
): string[] {
  if (!caps) {
    return [];
  }
  if (Array.isArray(caps)) {
    return caps.filter((item): item is string => typeof item === 'string');
  }
  return Object.entries(caps).map(([k, v]) => `${k}: ${String(v)}`);
}

function computeDimensionFallback(
  dimension: string,
  limit: number | null | undefined,
  current: number | null | undefined,
  knownSubtotal: number | null | undefined,
  status: string | undefined,
  alertThresholdPct: number,
): BudgetDimensionReport {
  const resolvedLimit = limit ?? null;
  const resolvedCurrent = current ?? null;
  const resolvedKnown = knownSubtotal ?? resolvedCurrent;
  const effectiveStatus = status ?? (resolvedCurrent === null ? 'unknown' : 'observed');
  const effectiveValue = resolvedCurrent ?? resolvedKnown;

  if (effectiveValue === null || effectiveStatus === 'unknown' || resolvedLimit === null) {
    return {
      dimension,
      limit: resolvedLimit,
      current: resolvedCurrent,
      known_subtotal: resolvedKnown,
      pct_used: null,
      status: effectiveStatus,
      triggered_alert: false,
      triggered_freeze: false,
    };
  }

  if (resolvedLimit <= 0) {
    return {
      dimension,
      limit: resolvedLimit,
      current: resolvedCurrent,
      known_subtotal: resolvedKnown,
      pct_used: 100,
      status: effectiveStatus,
      triggered_alert: false,
      triggered_freeze: true,
    };
  }

  const pct = (effectiveValue / resolvedLimit) * 100;
  const freeze = effectiveValue >= resolvedLimit;
  const alert = !freeze && pct >= alertThresholdPct;

  return {
    dimension,
    limit: resolvedLimit,
    current: resolvedCurrent,
    known_subtotal: resolvedKnown,
    pct_used: pct,
    status: effectiveStatus,
    triggered_alert: alert,
    triggered_freeze: freeze,
  };
}

export function evaluateBudgetSummary(budget: BudgetStatus): {
  isAlert80: boolean;
  isBlocked100: boolean;
  dimensions: BudgetDimensionReport[];
} {
  const alertPct =
    typeof budget.alert_threshold_pct === 'number' && !Number.isNaN(budget.alert_threshold_pct)
      ? budget.alert_threshold_pct
      : 80;

  const dimensions: BudgetDimensionReport[] =
    Array.isArray(budget.dimensions) && budget.dimensions.length > 0
      ? budget.dimensions.map((d) => {
          const isUnknown = d.status === 'unknown' || (d.current === null && d.known_subtotal == null);
          const pct =
            isUnknown || d.limit === null || d.limit === undefined
              ? null
              : d.pct_used ?? (d.limit > 0 && d.current !== null ? (d.current / d.limit) * 100 : null);
          const freeze =
            Boolean(d.triggered_freeze) || (pct !== null && pct >= 100);
          const alert =
            !freeze && (Boolean(d.triggered_alert) || (pct !== null && pct >= alertPct));
          return {
            ...d,
            pct_used: pct,
            triggered_alert: alert,
            triggered_freeze: freeze,
          };
        })
      : [
          computeDimensionFallback(
            'usd',
            budget.max_usd,
            budget.current_usd,
            budget.known_subtotal_usd,
            budget.usd_status,
            alertPct,
          ),
          computeDimensionFallback(
            'tokens_in',
            budget.max_tokens_in,
            budget.current_tokens_in,
            budget.known_subtotal_tokens_in,
            budget.tokens_in_status,
            alertPct,
          ),
          computeDimensionFallback(
            'tokens_out',
            budget.max_tokens_out,
            budget.current_tokens_out,
            budget.known_subtotal_tokens_out,
            budget.tokens_out_status,
            alertPct,
          ),
          computeDimensionFallback(
            'wall_seconds',
            budget.max_wall_seconds,
            budget.current_wall_seconds,
            budget.current_wall_seconds,
            budget.wall_seconds_status,
            alertPct,
          ),
        ];

  const isBlocked100 =
    budget.status === 'frozen' ||
    budget.status === 'exhausted' ||
    dimensions.some((d) => Boolean(d.triggered_freeze));

  const isAlert80 =
    !isBlocked100 &&
    (budget.status === 'alerted' || dimensions.some((d) => Boolean(d.triggered_alert)));

  return { isAlert80, isBlocked100, dimensions };
}

export async function listSkills(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<SkillItem[]> {
  const raw = await client.request<unknown>('/v1/control-plane/skills', {
    method: 'GET',
    signal,
  });
  return unwrapArray<SkillItem>(raw);
}

export async function createSkill(
  client: ControlPlaneClient,
  payload: CreateSkillPayload,
): Promise<SkillItem> {
  return client.request<SkillItem>('/v1/control-plane/skills', {
    method: 'POST',
    body: payload,
  });
}

export async function revokeSkill(
  client: ControlPlaneClient,
  skillId: string,
  reason = 'operator_revoked',
): Promise<RevokeResourceResponse> {
  return client.request<RevokeResourceResponse>(
    `/v1/control-plane/skills/${encodeURIComponent(skillId)}/revoke`,
    {
      method: 'POST',
      body: { reason },
    },
  );
}

export async function listMcps(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<McpItem[]> {
  const raw = await client.request<unknown>('/v1/control-plane/mcps', {
    method: 'GET',
    signal,
  });
  return unwrapArray<McpItem>(raw);
}

export async function revokeMcp(
  client: ControlPlaneClient,
  mcpId: string,
  reason = 'operator_revoked',
): Promise<RevokeResourceResponse> {
  return client.request<RevokeResourceResponse>(
    `/v1/control-plane/mcps/${encodeURIComponent(mcpId)}/revoke`,
    {
      method: 'POST',
      body: { reason },
    },
  );
}

export async function listDiscoveredResources(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<NormalizedDiscoveredResource[]> {
  const raw = await client.request<unknown>('/v1/control-plane/discovery/resources', {
    method: 'GET',
    signal,
  });
  return unwrapArray<DiscoveredResourceRaw>(raw).map(normalizeDiscoveredResource);
}

export async function scanDiscovery(
  client: ControlPlaneClient,
  payload: DiscoveryScanPayload,
): Promise<NormalizedDiscoveredResource[]> {
  const raw = await client.request<unknown>('/v1/control-plane/discovery/scan', {
    method: 'POST',
    body: payload,
  });
  return unwrapArray<DiscoveredResourceRaw>(raw).map(normalizeDiscoveredResource);
}

export async function approveDiscoveredResource(
  client: ControlPlaneClient,
  resourceId: string,
  expectedHash: string,
): Promise<NormalizedDiscoveredResource> {
  const raw = await client.request<DiscoveredResourceRaw>(
    `/v1/control-plane/discovery/resources/${encodeURIComponent(resourceId)}/approve`,
    {
      method: 'POST',
      body: { expected_hash: expectedHash },
    },
  );
  return normalizeDiscoveredResource(raw);
}

export async function rejectDiscoveredResource(
  client: ControlPlaneClient,
  resourceId: string,
): Promise<NormalizedDiscoveredResource> {
  const raw = await client.request<DiscoveredResourceRaw>(
    `/v1/control-plane/discovery/resources/${encodeURIComponent(resourceId)}/reject`,
    {
      method: 'POST',
      body: { action: 'rejected' },
    },
  );
  return normalizeDiscoveredResource(raw);
}

export async function listExtensions(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<ExtensionInstallItem[]> {
  const raw = await client.request<unknown>('/v1/control-plane/extensions', {
    method: 'GET',
    signal,
  });
  return unwrapArray<ExtensionInstallItem>(raw);
}

export async function installExtension(
  client: ControlPlaneClient,
  payload: ExtensionInstallPayload,
): Promise<ExtensionInstallItem> {
  return client.request<ExtensionInstallItem>('/v1/control-plane/extensions/install', {
    method: 'POST',
    body: payload,
  });
}

export async function revokeExtension(
  client: ControlPlaneClient,
  installId: string,
  reason = 'operator_quarantine',
): Promise<ExtensionInstallItem> {
  return client.request<ExtensionInstallItem>(
    `/v1/control-plane/extensions/${encodeURIComponent(installId)}/revoke`,
    {
      method: 'POST',
      body: { reason },
    },
  );
}

export async function rollbackExtension(
  client: ControlPlaneClient,
  installId: string,
): Promise<ExtensionInstallItem> {
  return client.request<ExtensionInstallItem>(
    `/v1/control-plane/extensions/${encodeURIComponent(installId)}/rollback`,
    {
      method: 'POST',
      body: {},
    },
  );
}

export async function listConsents(
  client: ControlPlaneClient,
  params: { scope_type: GovernanceScopeType; scope_id: string; purpose?: ConsentPurpose },
  signal?: AbortSignal,
): Promise<ConsentRecord[]> {
  const sp = new URLSearchParams({
    scope_type: params.scope_type,
    scope_id: params.scope_id,
  });
  if (params.purpose) {
    sp.set('purpose', params.purpose);
  }
  const raw = await client.request<unknown>(
    `/v1/control-plane/consents?${sp.toString()}`,
    { method: 'GET', signal },
  );
  return unwrapArray<ConsentRecord>(raw);
}

export async function createConsent(
  client: ControlPlaneClient,
  payload: ConsentCreatePayload,
): Promise<ConsentRecord> {
  return client.request<ConsentRecord>('/v1/control-plane/consents', {
    method: 'POST',
    body: payload,
  });
}

export async function decideConsent(
  client: ControlPlaneClient,
  consentId: string,
  action: ConsentDecisionAction,
): Promise<ConsentRecord> {
  return client.request<ConsentRecord>(
    `/v1/control-plane/consents/${encodeURIComponent(consentId)}`,
    {
      method: 'POST',
      body: { action },
    },
  );
}

export async function revokeConsent(
  client: ControlPlaneClient,
  consentId: string,
): Promise<ConsentRecord> {
  return client.request<ConsentRecord>(
    `/v1/control-plane/consents/${encodeURIComponent(consentId)}/revoke`,
    { method: 'POST' },
  );
}

export async function listMemory(
  client: ControlPlaneClient,
  params: { scope_type: GovernanceScopeType; scope_id: string; query?: string },
  signal?: AbortSignal,
): Promise<MemoryEntry[]> {
  const sp = new URLSearchParams({
    scope_type: params.scope_type,
    scope_id: params.scope_id,
    query: params.query ?? '',
  });
  const raw = await client.request<unknown>(
    `/v1/control-plane/memory?${sp.toString()}`,
    { method: 'GET', signal },
  );
  return unwrapArray<MemoryEntry>(raw);
}

export async function createMemory(
  client: ControlPlaneClient,
  payload: MemoryWritePayload,
): Promise<MemoryEntry> {
  return client.request<MemoryEntry>('/v1/control-plane/memory', {
    method: 'POST',
    body: payload,
  });
}

export async function updateMemory(
  client: ControlPlaneClient,
  memoryId: string,
  expectedVersion: number,
  payload: MemoryWritePayload,
): Promise<MemoryEntry> {
  const sp = new URLSearchParams({ expected_version: String(expectedVersion) });
  return client.request<MemoryEntry>(
    `/v1/control-plane/memory/${encodeURIComponent(memoryId)}?${sp.toString()}`,
    {
      method: 'PUT',
      body: payload,
    },
  );
}

export async function revokeMemory(
  client: ControlPlaneClient,
  memoryId: string,
): Promise<MemoryEntry> {
  return client.request<MemoryEntry>(
    `/v1/control-plane/memory/${encodeURIComponent(memoryId)}/revoke`,
    { method: 'POST' },
  );
}

export async function listSecrets(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<SecretRefItem[]> {
  const raw = await client.request<unknown>('/v1/control-plane/secrets', {
    method: 'GET',
    signal,
  });
  return unwrapArray<SecretRefItem>(raw);
}

export async function createSecretRef(
  client: ControlPlaneClient,
  payload: CreateSecretRefPayload,
): Promise<SecretRefItem> {
  return client.request<SecretRefItem>('/v1/control-plane/secrets', {
    method: 'POST',
    body: payload,
  });
}

export async function revokeSecretRef(
  client: ControlPlaneClient,
  secretId: string,
  reason = 'operator_revoked',
): Promise<RevokeResourceResponse> {
  return client.request<RevokeResourceResponse>(
    `/v1/control-plane/secrets/${encodeURIComponent(secretId)}/revoke`,
    {
      method: 'POST',
      body: { reason },
    },
  );
}

export async function listTransports(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<TransportItem[]> {
  const raw = await client.request<unknown>('/v1/control-plane/transports', {
    method: 'GET',
    signal,
  });
  return unwrapArray<TransportItem>(raw);
}

export async function getTransportHealth(
  client: ControlPlaneClient,
  transportId: string,
  refresh = true,
): Promise<TransportHealthResult> {
  const suffix = refresh ? '?refresh=true' : '';
  return client.request<TransportHealthResult>(
    `/v1/control-plane/transports/${encodeURIComponent(transportId)}/health${suffix}`,
    { method: 'GET' },
  );
}

export async function certifyTransport(
  client: ControlPlaneClient,
  transportId: string,
  payload: CertifyTransportPayload,
): Promise<CertifyTransportResponse> {
  return client.request<CertifyTransportResponse>(
    `/v1/control-plane/transports/${encodeURIComponent(transportId)}/certify`,
    {
      method: 'POST',
      body: payload,
    },
  );
}

export async function listGovernanceRuns(
  client: ControlPlaneClient,
  signal?: AbortSignal,
): Promise<GovernanceRunSummary[]> {
  const raw = await client.request<unknown>('/v1/control-plane/runs', {
    method: 'GET',
    signal,
  });
  return unwrapArray<GovernanceRunSummary>(raw);
}

export async function getRunBudget(
  client: ControlPlaneClient,
  runId: string,
  signal?: AbortSignal,
): Promise<BudgetStatus> {
  return client.request<BudgetStatus>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/budget`,
    { method: 'GET', signal },
  );
}

export async function extendRunBudget(
  client: ControlPlaneClient,
  runId: string,
  payload: ExtendBudgetPayload,
): Promise<ExtendBudgetResponse> {
  return client.request<ExtendBudgetResponse>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/budget/extend`,
    {
      method: 'POST',
      body: payload,
    },
  );
}
