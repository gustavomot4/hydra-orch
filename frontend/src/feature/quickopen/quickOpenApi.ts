import { z } from 'zod';
import { ControlPlaneClient } from '@/hook/useControlPlaneClient';

export type QuickOpenItemKind =
  | 'area'
  | 'workspace'
  | 'project'
  | 'run'
  | 'session'
  | 'artifact';

export type QuickOpenTabHint = 'workspace' | 'chat' | 'terminal' | 'artifact';

export type QuickOpenScope =
  | 'all'
  | 'areas'
  | 'workspaces'
  | 'projects'
  | 'runs'
  | 'sessions'
  | 'artifacts';

export interface QuickOpenScopeTab {
  id: QuickOpenScope;
  label: string;
}

export const QUICK_OPEN_SCOPES: readonly QuickOpenScopeTab[] = [
  { id: 'all', label: 'Tudo' },
  { id: 'areas', label: 'Áreas' },
  { id: 'workspaces', label: 'Workspaces' },
  { id: 'projects', label: 'Projetos' },
  { id: 'runs', label: 'Runs' },
  { id: 'sessions', label: 'Sessões' },
  { id: 'artifacts', label: 'Artefatos' },
];

export const QUICK_OPEN_KIND_LABELS: Record<QuickOpenItemKind, string> = {
  area: 'Área',
  workspace: 'Workspace',
  project: 'Projeto',
  run: 'Run',
  session: 'Sessão',
  artifact: 'Artefato',
};

export const QUICK_OPEN_TAB_HINT_LABELS: Record<QuickOpenTabHint, string> = {
  workspace: 'Workspace',
  chat: 'Chat',
  terminal: 'Terminal',
  artifact: 'Artefato',
};

export const QuickOpenSearchItemSchema = z.object({
  kind: z.enum(['area', 'workspace', 'project', 'run', 'session', 'artifact']),
  id: z.string(),
  title: z.string(),
  subtitle: z.string().optional().default(''),
  host_id: z.string().optional().default('local'),
  workspace_id: z.string().nullable().optional().default(null),
  project_id: z.string().nullable().optional().default(null),
  run_id: z.string().nullable().optional().default(null),
  session_id: z.string().nullable().optional().default(null),
  tab_hint: z.enum(['workspace', 'chat', 'terminal', 'artifact']).optional().default('workspace'),
});

export type QuickOpenSearchItem = z.infer<typeof QuickOpenSearchItemSchema>;

export const QuickOpenSearchResponseSchema = z.object({
  query: z.string().optional().default(''),
  scope: z.string().nullable().optional().default(null),
  items: z.array(QuickOpenSearchItemSchema),
});

export type QuickOpenSearchResponse = z.infer<typeof QuickOpenSearchResponseSchema>;

export interface QuickOpenSearchParams {
  query: string;
  scope?: QuickOpenScope;
  hostId?: string;
  limit?: number;
}

export function buildSearchQueryUrl(params: QuickOpenSearchParams): string {
  const sp = new URLSearchParams();
  sp.set('q', params.query);
  sp.set('scope', params.scope ?? 'all');
  sp.set('host_id', params.hostId ?? 'local');
  sp.set('limit', String(params.limit ?? 25));
  return `/v1/control-plane/search?${sp.toString()}`;
}

export async function searchControlPlane(
  client: ControlPlaneClient,
  params: QuickOpenSearchParams,
  options?: { signal?: AbortSignal },
): Promise<QuickOpenSearchResponse> {
  const path = buildSearchQueryUrl(params);
  const raw = await client.request<unknown>(path, { signal: options?.signal });
  const parsed = QuickOpenSearchResponseSchema.safeParse(raw);
  if (parsed.success) {
    return parsed.data;
  }
  if (Array.isArray(raw)) {
    const items = raw
      .map((entry) => QuickOpenSearchItemSchema.safeParse(entry))
      .filter((res): res is { success: true; data: QuickOpenSearchItem } => res.success)
      .map((res) => res.data);
    return {
      query: params.query,
      scope: params.scope ?? null,
      items,
    };
  }
  return {
    query: params.query,
    scope: params.scope ?? null,
    items: [],
  };
}
