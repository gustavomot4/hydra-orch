import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '@/store/authStore';
import { useCapabilities } from '@/hook/useCapabilities';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  Area,
  ExecutorSummary,
  Project,
  RunSummary,
  SessionSummary,
  Workspace,
} from '@/type/controlPlane';

export type HierarchyNodeKind =
  | 'host'
  | 'project'
  | 'workspace'
  | 'session'
  | 'agent_group';

export interface GroupedAgentItem {
  id: string;
  label: string;
  role: 'coordinator' | 'worker';
  status: string;
  driver?: string;
}

export interface WorkspaceTreeNode {
  id: string;
  kind: HierarchyNodeKind;
  label: string;
  subtitle?: string;
  status: string;
  hostId: string;
  areaId?: string | null;
  workspaceId?: string | null;
  projectId?: string | null;
  runId?: string | null;
  sessionId?: string | null;
  agents?: GroupedAgentItem[];
  children: WorkspaceTreeNode[];
}

function parseProjectHostId(project: Project): string {
  if (!project.metadata_json) {
    return 'local';
  }
  try {
    const parsed = JSON.parse(project.metadata_json) as Record<string, unknown>;
    return typeof parsed.host_id === 'string' && parsed.host_id.trim()
      ? parsed.host_id.trim()
      : 'local';
  } catch {
    return 'local';
  }
}

export function buildWorkspaceHierarchy(params: {
  hostIds: string[];
  areas: Area[];
  workspaces: Workspace[];
  projects: Project[];
  runs: RunSummary[];
  sessions: SessionSummary[];
  executors: ExecutorSummary[];
}): WorkspaceTreeNode[] {
  const { hostIds, workspaces, projects, runs, sessions } = params;

  const workspaceById = new Map<string, Workspace>();
  for (const ws of workspaces) {
    workspaceById.set(ws.id, ws);
  }

  const allHostIds = new Set<string>(['local', ...hostIds]);
  for (const p of projects) {
    allHostIds.add(parseProjectHostId(p));
  }

  const runsByProject = new Map<string, RunSummary[]>();
  for (const run of runs) {
    const list = runsByProject.get(run.project_id) ?? [];
    list.push(run);
    runsByProject.set(run.project_id, list);
  }

  const sessionsByRun = new Map<string, SessionSummary[]>();
  for (const sess of sessions) {
    const list = sessionsByRun.get(sess.run_id) ?? [];
    list.push(sess);
    sessionsByRun.set(sess.run_id, list);
  }

  const hostNodes: WorkspaceTreeNode[] = [];

  for (const hostId of allHostIds) {
    const hostProjects = projects.filter((p) => parseProjectHostId(p) === hostId);
    const projectNodes: WorkspaceTreeNode[] = hostProjects.map((project) => {
      const ws = project.workspace_id ? workspaceById.get(project.workspace_id) : undefined;
      const projectRuns = runsByProject.get(project.id) ?? [];

      const sessionNodes: WorkspaceTreeNode[] = [];
      for (const run of projectRuns) {
        const runSessions = sessionsByRun.get(run.id) ?? [];
        if (runSessions.length > 0) {
          for (const sess of runSessions) {
            const agentName = sess.agent_ref || 'Coordenador';
            const agents: GroupedAgentItem[] = [
              {
                id: `${sess.id}:coord`,
                label: agentName,
                role: 'coordinator',
                status: sess.state,
                driver: sess.origin_ref ?? undefined,
              },
            ];
            sessionNodes.push({
              id: `session:${sess.id}`,
              kind: 'session',
              label: run.objective,
              subtitle: sess.origin_ref || run.mode,
              status: sess.state,
              hostId,
              areaId: ws?.area_id ?? null,
              workspaceId: ws?.id ?? project.workspace_id ?? null,
              projectId: project.id,
              runId: run.id,
              sessionId: sess.id,
              children: [
                {
                  id: `agents:${sess.id}`,
                  kind: 'agent_group',
                  label: `Agentes (${agents.length})`,
                  status: sess.state,
                  hostId,
                  areaId: ws?.area_id ?? null,
                  workspaceId: ws?.id ?? project.workspace_id ?? null,
                  projectId: project.id,
                  runId: run.id,
                  sessionId: sess.id,
                  agents,
                  children: [],
                },
              ],
            });
          }
        } else {
          const agents: GroupedAgentItem[] = [
            {
              id: `${run.id}:coord`,
              label: run.mode === 'swarm' ? 'Coordenador Swarm' : 'Coordenador Relay',
              role: 'coordinator',
              status: run.status,
            },
          ];
          sessionNodes.push({
            id: `run:${run.id}`,
            kind: 'session',
            label: run.objective,
            subtitle: run.mode,
            status: run.status,
            hostId,
            areaId: ws?.area_id ?? null,
            workspaceId: ws?.id ?? project.workspace_id ?? null,
            projectId: project.id,
            runId: run.id,
            sessionId: null,
            children: [
              {
                id: `agents:run:${run.id}`,
                kind: 'agent_group',
                label: `Agentes (${agents.length})`,
                status: run.status,
                hostId,
                areaId: ws?.area_id ?? null,
                workspaceId: ws?.id ?? project.workspace_id ?? null,
                projectId: project.id,
                runId: run.id,
                sessionId: null,
                agents,
                children: [],
              },
            ],
          });
        }
      }

      const workspaceNode: WorkspaceTreeNode = {
        id: `workspace:${ws?.id ?? project.id}`,
        kind: 'workspace',
        label: ws?.name ?? 'worktree principal',
        subtitle: project.base_branch ?? 'main',
        status: ws?.status ?? 'active',
        hostId,
        areaId: ws?.area_id ?? null,
        workspaceId: ws?.id ?? null,
        projectId: project.id,
        children: sessionNodes,
      };

      return {
        id: `project:${project.id}`,
        kind: 'project',
        label: project.name,
        subtitle: project.base_branch ?? 'main',
        status: projectRuns[0]?.status ?? 'ready',
        hostId,
        areaId: ws?.area_id ?? null,
        workspaceId: ws?.id ?? project.workspace_id ?? null,
        projectId: project.id,
        children: [workspaceNode],
      };
    });

    hostNodes.push({
      id: `host:${hostId}`,
      kind: 'host',
      label: hostId === 'local' ? 'Host local' : hostId,
      subtitle: hostId === 'local' ? 'Control Plane' : 'Remoto',
      status: 'connected',
      hostId,
      children: projectNodes,
    });
  }

  return hostNodes;
}

export function useWorkspaceHierarchy() {
  const token = useAuthStore((state) => state.token);
  const client = useControlPlaneClient();
  const { hosts } = useCapabilities();

  const areasQuery = useQuery({
    queryKey: ['control-plane', 'areas'],
    queryFn: () => client.listAreas(),
    enabled: Boolean(token),
    staleTime: 30_000,
  });

  const workspacesQuery = useQuery({
    queryKey: ['control-plane', 'workspaces'],
    queryFn: () => client.listWorkspaces(),
    enabled: Boolean(token),
    staleTime: 30_000,
  });

  const projectsQuery = useQuery({
    queryKey: ['control-plane', 'projects'],
    queryFn: () => client.listProjects(),
    enabled: Boolean(token),
    staleTime: 30_000,
  });

  const runsQuery = useQuery({
    queryKey: ['control-plane', 'runs'],
    queryFn: () => client.listRuns({ page: 1, size: 50 }),
    enabled: Boolean(token),
    staleTime: 15_000,
  });

  const sessionsQuery = useQuery({
    queryKey: ['control-plane', 'sessions'],
    queryFn: () => client.listSessions(),
    enabled: Boolean(token),
    staleTime: 15_000,
  });

  const executorsQuery = useQuery({
    queryKey: ['control-plane', 'executors'],
    queryFn: () => client.listExecutors(),
    enabled: Boolean(token),
    staleTime: 30_000,
  });

  const tree = useMemo(
    () =>
      buildWorkspaceHierarchy({
        hostIds: hosts.map((h) => h.host_id),
        areas: areasQuery.data ?? [],
        workspaces: workspacesQuery.data ?? [],
        projects: projectsQuery.data ?? [],
        runs: runsQuery.data?.items ?? [],
        sessions: sessionsQuery.data ?? [],
        executors: executorsQuery.data ?? [],
      }),
    [
      hosts,
      areasQuery.data,
      workspacesQuery.data,
      projectsQuery.data,
      runsQuery.data,
      sessionsQuery.data,
      executorsQuery.data,
    ],
  );

  const isLoading =
    areasQuery.isLoading ||
    workspacesQuery.isLoading ||
    projectsQuery.isLoading ||
    runsQuery.isLoading ||
    sessionsQuery.isLoading;

  return {
    tree,
    areas: areasQuery.data ?? [],
    workspaces: workspacesQuery.data ?? [],
    projects: projectsQuery.data ?? [],
    runs: runsQuery.data?.items ?? [],
    sessions: sessionsQuery.data ?? [],
    executors: executorsQuery.data ?? [],
    isLoading,
    refetchAll: () => {
      void areasQuery.refetch();
      void workspacesQuery.refetch();
      void projectsQuery.refetch();
      void runsQuery.refetch();
      void sessionsQuery.refetch();
      void executorsQuery.refetch();
    },
  };
}
