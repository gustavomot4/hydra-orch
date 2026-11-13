import { useMemo } from 'react';
import { useAuthStore } from '@/store/authStore';
import {
  ApiErrorSchema,
  Area,
  BootstrapData,
  CapabilitiesEndpointResponse,
  ControlPlaneApiError,
  ExecutorSummary,
  Preference,
  PreferenceRevertPayload,
  PreferenceScopeType,
  PreferenceSetPayload,
  Project,
  QuotaInventory,
  QuotaStatusPayload,
  RunListResponse,
  SessionSummary,
  ThreadSummary,
  TokenCreatePayload,
  TokenListResult,
  TokenMetadata,
  TokenMetadataSchema,
  Workspace,
} from '@/type/controlPlane';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export interface ControlPlaneClient {
  request: <T>(path: string, options?: RequestOptions) => Promise<T>;
  getBootstrap: () => Promise<BootstrapData>;
  getCapabilities: () => Promise<CapabilitiesEndpointResponse>;
  getQuota: () => Promise<QuotaStatusPayload>;
  getOmniRouteInventory: (scopeId?: string) => Promise<QuotaInventory>;
  listAreas: () => Promise<Area[]>;
  listWorkspaces: (areaId?: string) => Promise<Workspace[]>;
  listProjects: () => Promise<Project[]>;
  listRuns: (params?: { project_id?: string; status?: string; page?: number; size?: number }) => Promise<RunListResponse>;
  listSessions: (runId?: string) => Promise<SessionSummary[]>;
  listSessionThreads: (sessionId: string) => Promise<ThreadSummary[]>;
  listExecutors: () => Promise<ExecutorSummary[]>;
  listPreferences: (scopeType?: PreferenceScopeType, scopeId?: string) => Promise<Preference[]>;
  setPreference: (payload: PreferenceSetPayload) => Promise<Preference>;
  revertPreference: (payload: PreferenceRevertPayload) => Promise<{ reverted: boolean; preference: Preference | null }>;
  listTokens: () => Promise<TokenListResult>;
  createToken: (payload: TokenCreatePayload) => Promise<TokenMetadata>;
  revokeToken: (tokenId: string) => Promise<TokenMetadata>;
}

function sanitizeTokenRecord(raw: unknown): TokenMetadata | null {
  const parsed = TokenMetadataSchema.safeParse(raw);
  if (!parsed.success) {
    return null;
  }
  return {
    id: parsed.data.id,
    principal_id: parsed.data.principal_id,
    scopes: parsed.data.scopes,
    expires_at: parsed.data.expires_at,
    revoked_at: parsed.data.revoked_at,
  };
}

export function createControlPlaneClient(
  token: string | null,
  options?: {
    baseUrl?: string;
    onUnauthorized?: () => void;
    fetchImpl?: typeof fetch;
  },
): ControlPlaneClient {
  const baseUrl = (options?.baseUrl ?? '').replace(/\/+$/, '');
  const fetchFn = options?.fetchImpl ?? globalThis.fetch.bind(globalThis);

  async function request<T>(path: string, reqOpts: RequestOptions = {}): Promise<T> {
    const method = reqOpts.method ?? 'GET';
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(reqOpts.headers ?? {}),
    };
    if (token && token.trim().length > 0) {
      headers.Authorization = `Bearer ${token.trim()}`;
    }
    let body: string | undefined;
    if (reqOpts.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(reqOpts.body);
    }

    // Never retry mutations or put credentials into URL query parameters.
    const response = await fetchFn(`${baseUrl}${path}`, {
      method,
      headers,
      body,
      signal: reqOpts.signal,
    });

    const text = await response.text();
    let parsedJson: unknown = null;
    if (text.length > 0) {
      try {
        parsedJson = JSON.parse(text);
      } catch {
        parsedJson = null;
      }
    }

    if (!response.ok) {
      const parsedErr = ApiErrorSchema.safeParse(parsedJson);
      const apiError = parsedErr.success
        ? parsedErr.data
        : {
            code: response.status === 401 ? 'unauthorized' : 'http_error',
            message: `Falha na requisição (${response.status})`,
            run_id: null,
            retryable: false,
          };

      if (response.status === 401) {
        options?.onUnauthorized?.();
      }
      throw new ControlPlaneApiError(response.status, apiError);
    }

    return parsedJson as T;
  }

  return {
    request,
    getBootstrap: () => request<BootstrapData>('/v1/control-plane/bootstrap'),
    getCapabilities: () => request<CapabilitiesEndpointResponse>('/v1/control-plane/capabilities'),
    getQuota: () => request<QuotaStatusPayload>('/v1/quota'),
    getOmniRouteInventory: (scopeId = 'default') =>
      request<QuotaInventory>(
        `/v1/control-plane/omniroute/inventory?scope_id=${encodeURIComponent(scopeId)}`,
      ),
    listAreas: () => request<Area[]>('/v1/control-plane/areas'),
    listWorkspaces: (areaId?: string) => {
      const qs = areaId ? `?area_id=${encodeURIComponent(areaId)}` : '';
      return request<Workspace[]>(`/v1/control-plane/workspaces${qs}`);
    },
    listProjects: () => request<Project[]>('/v1/control-plane/projects'),
    listRuns: (params) => {
      const sp = new URLSearchParams();
      if (params?.project_id) sp.set('project_id', params.project_id);
      if (params?.status) sp.set('status', params.status);
      if (params?.page) sp.set('page', String(params.page));
      if (params?.size) sp.set('size', String(params.size));
      const suffix = sp.toString() ? `?${sp.toString()}` : '';
      return request<RunListResponse>(`/v1/control-plane/runs${suffix}`);
    },
    listSessions: (runId?: string) => {
      const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
      return request<SessionSummary[]>(`/v1/control-plane/sessions${qs}`);
    },
    listSessionThreads: (sessionId: string) =>
      request<ThreadSummary[]>(`/v1/control-plane/sessions/${encodeURIComponent(sessionId)}/threads`),
    listExecutors: () => request<ExecutorSummary[]>('/v1/control-plane/executors'),
    listPreferences: (scopeType?: PreferenceScopeType, scopeId?: string) => {
      const sp = new URLSearchParams();
      if (scopeType) sp.set('scope_type', scopeType);
      if (scopeId) sp.set('scope_id', scopeId);
      const suffix = sp.toString() ? `?${sp.toString()}` : '';
      return request<Preference[]>(`/v1/control-plane/preferences${suffix}`);
    },
    setPreference: (payload) =>
      request<Preference>('/v1/control-plane/preferences', {
        method: 'PUT',
        body: payload,
        headers: payload.idempotency_key ? { 'Idempotency-Key': payload.idempotency_key } : undefined,
      }),
    revertPreference: (payload) =>
      request<{ reverted: boolean; preference: Preference | null }>(
        '/v1/control-plane/preferences/revert',
        {
          method: 'POST',
          body: payload,
          headers: payload.idempotency_key
            ? { 'Idempotency-Key': payload.idempotency_key }
            : undefined,
        },
      ),
    listTokens: async (): Promise<TokenListResult> => {
      try {
        const raw = await request<unknown[]>('/v1/control-plane/tokens');
        const items = Array.isArray(raw)
          ? raw.map(sanitizeTokenRecord).filter((entry): entry is TokenMetadata => entry !== null)
          : [];
        return { supported: true, items };
      } catch (err) {
        if (err instanceof ControlPlaneApiError && (err.status === 404 || err.status === 405)) {
          return { supported: false, items: [] };
        }
        throw err;
      }
    },
    createToken: async (payload) => {
      const raw = await request<unknown>('/v1/control-plane/tokens', {
        method: 'POST',
        body: { ...payload, redact_token: true },
      });
      const clean = sanitizeTokenRecord(raw);
      if (!clean) {
        throw new ControlPlaneApiError(500, {
          code: 'invalid_token_metadata',
          message: 'Resposta inválida de metadados de token',
          run_id: null,
          retryable: false,
        });
      }
      return clean;
    },
    revokeToken: async (tokenId) => {
      const raw = await request<unknown>(
        `/v1/control-plane/tokens/${encodeURIComponent(tokenId)}/revoke`,
        { method: 'POST' },
      );
      const clean = sanitizeTokenRecord(raw);
      if (!clean) {
        throw new ControlPlaneApiError(500, {
          code: 'invalid_token_metadata',
          message: 'Resposta inválida de revogação de token',
          run_id: null,
          retryable: false,
        });
      }
      return clean;
    },
  };
}

export function useControlPlaneClient(): ControlPlaneClient {
  const token = useAuthStore((state) => state.token);
  const lock = useAuthStore((state) => state.lock);

  return useMemo(
    () =>
      createControlPlaneClient(token, {
        onUnauthorized: () => lock('Sessão expirada ou token inválido (HTTP 401).'),
      }),
    [token, lock],
  );
}
