export interface SkillItem {
  skill_id: string;
  name: string;
  version: string;
  manifest_ref: string;
  discovered_resource_id?: string | null;
  permissions_declared: string[];
  checksum: string;
  revoked: boolean;
  created_at?: string | null;
}

export interface CreateSkillPayload {
  name: string;
  version: string;
  manifest_ref: string;
  permissions_declared: string[];
  checksum: string;
}

export interface RevokeResourceResponse {
  skill_id?: string;
  mcp_id?: string;
  secret_id?: string;
  revoked: boolean;
  reason: string;
}

export type McpTransportType = 'stdio' | 'sse' | 'websocket';

export interface McpDeclaredTool {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown>;
}

export interface McpItem {
  mcp_id: string;
  server_name: string;
  transport_type: McpTransportType | string;
  endpoint: string;
  discovered_resource_id?: string | null;
  secret_ref?: string | null;
  declared_tools: McpDeclaredTool[];
  permissions: string[];
  revoked: boolean;
  created_at?: string | null;
}

export type DiscoveryTrustStatus = 'untrusted' | 'approved' | 'active' | 'rejected' | 'revoked';

export interface DiscoveredResourceRaw {
  resource_id?: string;
  id?: string;
  discovery_id?: string;
  kind?: string;
  resource_type?: string;
  path?: string;
  source_canonical_path?: string;
  sha256?: string;
  checksum?: string;
  hash?: string;
  content_hash?: string;
  status?: string;
  trust_status?: string;
  capabilities?: string[];
  discovered_at?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
}

export interface NormalizedDiscoveredResource {
  resourceId: string;
  kind: string;
  path: string;
  hash: string;
  status: string;
  capabilities: string[];
  discoveredAt: string | null;
  approvedAt: string | null;
  approvedBy: string | null;
}

export interface DiscoveryScanPayload {
  authorized_root: string;
  opt_in: true;
}

export interface DiscoveryApprovePayload {
  expected_hash: string;
}

export interface DiscoveryRejectPayload {
  action: 'rejected';
}

export type ExtensionInstallStatus =
  | 'proposed'
  | 'consented'
  | 'installed'
  | 'active'
  | 'disabled'
  | 'quarantined'
  | 'revoked'
  | 'rolled_back';

export interface ExtensionInstallItem {
  install_id: string;
  extension_manifest_id: string;
  name?: string | null;
  version?: string | null;
  status: ExtensionInstallStatus | string;
  consent_record_id: string;
  installed_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ExtensionInstallPayload {
  manifest_id: string;
  consent_id: string;
  activate: true;
}

export type GovernanceScopeType =
  | 'principal'
  | 'user'
  | 'area'
  | 'workspace'
  | 'project'
  | 'run'
  | 'session'
  | 'extension';

export type ConsentPurpose = 'memory' | 'extension';

export type ConsentStatus = 'requested' | 'granted' | 'denied' | 'revoked' | 'expired';

export type ConsentDecisionAction = 'granted' | 'denied';

export interface ConsentRecord {
  consent_id: string;
  principal_id?: string;
  scope_type?: GovernanceScopeType;
  scope_id?: string;
  scope?: string;
  purpose: ConsentPurpose | string;
  status: ConsentStatus | string;
  created_at?: string | null;
  granted_at?: string | null;
  revoked_at?: string | null;
}

export interface ConsentCreatePayload {
  scope_type: GovernanceScopeType;
  scope_id: string;
  purpose: ConsentPurpose;
}

export type RetentionPolicy = 'day' | 'month';

export type MemoryStatus = 'pending_consent' | 'active' | 'revoked' | 'rejected' | 'expired';

export interface MemoryEntry {
  memory_id: string;
  scope_type: GovernanceScopeType;
  scope_id: string;
  content_redacted: string;
  author_ref: string;
  consent_id: string;
  version: number;
  retention_policy_id: RetentionPolicy;
  status: MemoryStatus | string;
  created_at: string;
  expires_at: string;
}

export interface MemoryWritePayload {
  scope_type: GovernanceScopeType;
  scope_id: string;
  content: string;
  consent_id?: string;
  retention_policy: RetentionPolicy;
}

export type SecretProviderType = 'env' | 'vault' | 'keyring';

export interface SecretRefItem {
  secret_id: string;
  secret_name: string;
  provider_type: SecretProviderType | string;
  source_key: string;
  revoked: boolean;
}

export interface CreateSecretRefPayload {
  secret_name: string;
  provider_type: SecretProviderType;
  source_key: string;
}

export type TransportType = 'local' | 'ssh' | 'ide' | 'cdp' | 'remote';

export type SupportedPlatform = 'Linux' | 'Windows' | 'Darwin';

export type TransportHealthStatus = 'unknown' | 'healthy' | 'degraded' | 'unreachable';

export interface TransportItem {
  transport_id: string;
  type: TransportType | string;
  target_identity: string;
  is_certified: boolean;
  capabilities: string[] | Record<string, unknown>;
  created_at?: string | null;
}

export interface TransportHealthResult {
  health_id?: string;
  transport_id: string;
  status: TransportHealthStatus | string;
  last_check_at?: string | null;
  error_detail?: string | null;
}

export interface CertifyTransportPayload {
  transport_id: string;
  transport_type: TransportType | string;
  platform: SupportedPlatform;
  version: string;
  target_identity: string;
  fingerprint?: string;
  passed_checks: string[];
  simulated: false;
}

export interface CertifyTransportResponse {
  certificate_id: string;
  transport_id: string;
  certified: boolean;
}

export type BudgetMetricStatus = 'observed' | 'partial' | 'stale' | 'unknown';

export interface BudgetDimensionReport {
  dimension: string;
  limit: number | null;
  current: number | null;
  known_subtotal?: number | null;
  pct_used: number | null;
  status: BudgetMetricStatus | string;
  sources?: string[];
  triggered_alert?: boolean;
  triggered_freeze?: boolean;
}

export interface BudgetStatus {
  policy_id: string;
  run_id: string;
  max_usd?: number | null;
  max_tokens_in?: number | null;
  max_tokens_out?: number | null;
  max_wall_seconds?: number | null;
  alert_threshold_pct: number;
  current_usd?: number | null;
  current_tokens_in?: number | null;
  current_tokens_out?: number | null;
  current_wall_seconds?: number | null;
  usd_status?: BudgetMetricStatus | string;
  tokens_in_status?: BudgetMetricStatus | string;
  tokens_out_status?: BudgetMetricStatus | string;
  wall_seconds_status?: BudgetMetricStatus | string;
  known_subtotal_usd?: number | null;
  known_subtotal_tokens_in?: number | null;
  known_subtotal_tokens_out?: number | null;
  status: 'active' | 'alerted' | 'frozen' | 'exhausted' | string;
  dimensions?: BudgetDimensionReport[];
  triggered_dimensions?: string[];
  checked_at?: string | null;
}

export interface ExtendBudgetPayload {
  additional_usd?: number;
  additional_tokens_in?: number;
  additional_tokens_out?: number;
  additional_wall_seconds?: number;
  reason: string;
  approved: true;
}

export interface ExtendBudgetResponse {
  run_id: string;
  approved: boolean;
  previous_status: string;
  status: string;
  actor: string;
  reason: string;
  budget_status: BudgetStatus;
  resolved_at?: string;
}

export interface GovernanceRunSummary {
  id: string;
  run_id?: string;
  status?: string;
  objective?: string;
  created_at?: string;
}
