import { z } from 'zod';

export const ApiErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  run_id: z.string().nullable().optional().default(null),
  retryable: z.boolean().optional().default(false),
  details: z.unknown().optional(),
});

export type ApiError = z.infer<typeof ApiErrorSchema>;

export class ControlPlaneApiError extends Error {
  readonly status: number;
  readonly payload: ApiError;

  constructor(status: number, payload: ApiError) {
    super(payload.message);
    this.name = 'ControlPlaneApiError';
    this.status = status;
    this.payload = payload;
  }
}

export type CapabilityStatus = 'available' | 'degraded' | 'unavailable';

export interface PtyCapability {
  status: CapabilityStatus;
  supported: boolean;
  certified: boolean;
  backend_kind: string;
  platform?: string;
  reason?: string | null;
}

export interface AttachmentsCapability {
  status: 'available' | 'unavailable';
  supported: boolean;
  certified: boolean;
  max_bytes?: number;
  remote_confirm_required?: boolean;
  reason?: string | null;
}

export interface BasicCapability {
  status: 'available' | 'unavailable';
  supported: boolean;
  certified: boolean;
  reason?: string | null;
}

export interface PreviewCapability extends BasicCapability {
  max_bytes?: number;
  supported_kinds?: string[];
}

export interface DictationCapability {
  status: 'available' | 'unavailable';
  supported: boolean;
  certified: boolean;
  available_modes: string[];
  duplex_voice_enabled: boolean;
  requires_review_before_send?: boolean;
}

export interface MobileEmulatorCapability extends BasicCapability {
  transport_id?: string;
  platforms?: {
    ios: string;
    android: string;
  };
}

export interface ComputerUseCapability extends BasicCapability {
  transport_id?: string;
}

export interface HostCapabilitiesMap {
  pty: PtyCapability;
  attachments: AttachmentsCapability;
  quickopen: BasicCapability;
  preview: PreviewCapability;
  scheduler: BasicCapability;
  dictation_stt: DictationCapability;
  mobile_emulator: MobileEmulatorCapability;
  computer_use: ComputerUseCapability;
}

export interface HostEntry {
  host_id: string;
  transport_id?: string;
  transport_type: string;
  target_identity?: string;
  platform?: string;
  certified: boolean;
  capabilities: HostCapabilitiesMap;
}

export interface HostCapabilities {
  schema_version: string;
  default_host: string;
  platform: string;
  integrations: {
    omniroute_enabled: boolean;
    omniroute_connection_mode: string;
    ssh_gpu_enabled: boolean;
    visual_interface_enabled: boolean;
  };
  hosts: Record<string, HostEntry>;
}

export interface CapabilitiesEndpointResponse {
  known_capabilities: string[];
  executor_capabilities: string[];
  certification_checks: string[];
  drivers: string[];
  agents: Array<{
    id: string;
    agent_id: string;
    driver: string;
    driver_type: string;
    version: string;
    is_certified: boolean;
    capabilities: string[];
  }>;
  host_capabilities: HostCapabilities;
}

export interface BootstrapData {
  api_version: string;
  product: string;
  ui: {
    enabled: boolean;
    host: string;
    port: number;
    api_base_path: string;
    features: {
      projects: boolean;
      runs: boolean;
      worktrees: boolean;
      diffs: boolean;
      quota: boolean;
    };
  };
  integrations: {
    omniroute: {
      enabled: boolean;
      connection_mode: string;
      configured: boolean;
    };
    ssh_gpu: {
      enabled: boolean;
    };
  };
  capabilities: HostCapabilities;
  implemented_read_models: Record<string, boolean>;
}

export interface Area {
  id: string;
  name: string;
  description: string | null;
  owner_principal_id: string;
  revision: number;
  created_at: string;
}

export interface Workspace {
  id: string;
  area_id: string;
  name: string;
  status: 'active' | 'archived';
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  project_id?: string;
  canonical_root: string;
  name: string;
  workspace_id?: string | null;
  metadata_json?: string;
  base_branch?: string | null;
  base_sha?: string | null;
  revision?: number;
  created_at: string;
  updated_at: string;
}

export type RunStatus =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'reviewing'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export interface RunSummary {
  id: string;
  run_id: string;
  project_id: string;
  objective: string;
  mode: 'swarm' | 'relay' | 'persistent';
  status: RunStatus;
  revision: number;
  base_sha: string;
  created_at: string;
  updated_at: string;
}

export interface RunListResponse {
  items: RunSummary[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export type SessionState =
  | 'created'
  | 'running'
  | 'waiting'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface SessionSummary {
  id: string;
  run_id: string;
  origin_ref: string | null;
  agent_ref: string | null;
  state: SessionState;
  created_at: string;
  closed_at: string | null;
}

export interface ThreadSummary {
  id: string;
  session_id: string;
  parent_thread_id: string | null;
  agent_ref: string | null;
  state: SessionState;
  last_seq: number;
  created_at: string;
}

export interface ExecutorSummary {
  id: string;
  agent_id?: string;
  name: string;
  version?: string;
  driver: string;
  driver_type: string;
  executable: string | null;
  executable_found: boolean;
  is_certified: boolean;
  status: string;
  reason?: string | null;
  capabilities: string[];
  platform: string | null;
}

export type QuotaMetricStatus = 'observed' | 'stale' | 'unknown';

export interface ProviderQuotaEntry {
  status: QuotaMetricStatus;
  remaining_percent: number | null;
  resets_in_seconds: number | null;
  observed_at?: string;
  source?: string;
}

export interface QuotaStatusPayload {
  status: QuotaMetricStatus;
  claude_pro?: ProviderQuotaEntry;
  chatgpt_plus?: ProviderQuotaEntry;
  gemini_pro?: ProviderQuotaEntry;
  [key: string]: QuotaMetricStatus | ProviderQuotaEntry | undefined;
}

export interface OmniRouteModelItem {
  id: string;
  provider: string;
  owned_by: string;
}

export interface OmniRouteAccountItem {
  account_id: string;
  provider: string;
  label: string;
  quota_key: string | null;
  status: QuotaMetricStatus;
  remaining_percent: number | null;
  resets_in_seconds: number | null;
  observed_at: string | null;
  source: string;
}

export interface AccountOverride {
  scope_id: string;
  provider: string;
  account_id: string;
  selected_by: string;
  selected_at: string;
  applies_to: 'next_run';
}

export interface QuotaInventory {
  connection_mode: string;
  direct_mode_supported: boolean;
  available: boolean;
  models: OmniRouteModelItem[];
  accounts: OmniRouteAccountItem[];
  quota: QuotaStatusPayload;
  next_account_overrides: Record<string, AccountOverride>;
}

export type PreferenceScopeType = 'user' | 'area' | 'project';
export type PreferenceSource = 'explicit' | 'inferred_opt_in';

export interface Preference {
  preference_id: string;
  scope_type: PreferenceScopeType;
  scope_id: string;
  key: string;
  value_json: string;
  source: PreferenceSource;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PreferenceSetPayload {
  scope_type: PreferenceScopeType;
  scope_id: string;
  key: string;
  value: unknown;
  source?: PreferenceSource;
  opt_in?: boolean;
  expected_version?: number;
  idempotency_key?: string;
}

export interface PreferenceRevertPayload {
  scope_type: PreferenceScopeType;
  scope_id: string;
  key: string;
  target_version?: number;
  expected_version?: number;
  idempotency_key?: string;
}

export const TokenMetadataSchema = z.object({
  id: z.string(),
  principal_id: z.string(),
  scopes: z.array(z.string()),
  expires_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
});

export type TokenMetadata = z.infer<typeof TokenMetadataSchema>;

export interface TokenCreatePayload {
  principal_id: string;
  scopes: string[];
  expires_at: string;
  redact_token?: boolean;
}

export interface TokenListResult {
  supported: boolean;
  items: TokenMetadata[];
}
