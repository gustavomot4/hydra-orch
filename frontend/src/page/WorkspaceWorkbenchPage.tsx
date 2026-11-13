import { useEffect, useState } from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import { useQuery } from '@tanstack/react-query';
import { FileCode2, FolderGit2, GitMerge, Package, RefreshCw } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { ArtifactViewer } from '@/feature/artifact';
import { ConflictWorkbench, PrPackagePanel } from '@/feature/conflict';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useLayoutStore } from '@/store/layoutStore';
import { RunListResponse, RunSummary } from '@/type/controlPlane';

export type WorkbenchSection = 'conflicts' | 'artifacts' | 'pr';

export interface WorkspaceWorkbenchPageProps {
  initialSection?: WorkbenchSection;
  initialRunId?: string | null;
}

export function WorkspaceWorkbenchPage({
  initialSection = 'conflicts',
  initialRunId = null,
}: WorkspaceWorkbenchPageProps) {
  const client = useControlPlaneClient();
  const selectedRunId = useLayoutStore((s) => s.selectedRunId);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);
  const openTab = useLayoutStore((s) => s.openTab);

  const [section, setSection] = useState<WorkbenchSection>(initialSection);
  const [explicitRunId, setExplicitRunId] = useState<string | null>(initialRunId);

  const runsQuery = useQuery<RunListResponse>({
    queryKey: ['control-plane', 'workbench-runs', selectedProjectId ?? 'all'],
    queryFn: () => client.listRuns({ page: 1, size: 50 }),
    retry: false,
    staleTime: 10_000,
  });

  const runs: RunSummary[] = runsQuery.data?.items ?? [];
  const resolvedRunId =
    explicitRunId ??
    selectedRunId ??
    runs.find((r) => !selectedProjectId || r.project_id === selectedProjectId)?.id ??
    runs[0]?.id ??
    null;

  useEffect(() => {
    if (initialRunId) {
      setExplicitRunId(initialRunId);
    }
  }, [initialRunId]);

  const activeRun = runs.find((r) => r.id === resolvedRunId) ?? null;

  return (
    <div
      data-testid="workspace-workbench-page"
      className="mx-auto flex min-h-full w-full max-w-6xl flex-col gap-4 p-4 text-[#E8E8E8] md:p-6"
    >
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#303030] bg-[#202020] p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <FolderGit2 aria-hidden="true" className="h-4 w-4 text-[#E8E8E8]" />
            <h1 className="text-lg font-semibold text-[#E8E8E8]">
              Workspaces, artefatos e conflitos
            </h1>
            {activeRun ? <StatusBadge status={activeRun.status} compact /> : null}
          </div>
          <p className="text-xs text-[#969696]">
            Inspecione diffs, previews seguros, revisões de tarefa, resolução de conflitos 3-way e empacotamento de PR.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="workbench-run-select" className="text-xs text-[#969696]">
            Run selecionada
          </label>
          <select
            id="workbench-run-select"
            value={resolvedRunId ?? ''}
            onChange={(e) => {
              const next = e.target.value || null;
              setExplicitRunId(next);
              if (next) {
                selectHierarchy({ runId: next });
              }
            }}
            className="min-w-[220px] rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8]"
          >
            {runs.length === 0 ? (
              <option value="">Nenhuma run disponível</option>
            ) : (
              runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.id} · {run.status}
                </option>
              ))
            )}
          </select>

          <button
            type="button"
            onClick={() => {
              void runsQuery.refetch();
            }}
            aria-label="Atualizar lista de runs"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#181818] px-3 py-1.5 text-xs text-[#E8E8E8] hover:bg-[#282828]"
          >
            <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Atualizar</span>
          </button>
        </div>
      </header>

      {!resolvedRunId ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[#303030] bg-[#1C1C1C] p-8 text-center">
          <p className="text-sm font-medium text-[#E8E8E8]">
            Nenhuma run selecionada para revisão ou inspeção de artefatos
          </p>
          <p className="max-w-md text-xs text-[#969696]">
            Inicie uma nova execução ou selecione uma conversa existente na barra lateral para revisar diffs, conflitos e gerar pacote de PR.
          </p>
          <button
            type="button"
            onClick={() =>
              openTab({
                id: 'tab:new-chat',
                kind: 'new_chat',
                title: 'Novo chat',
                route: '/',
                closable: false,
              })
            }
            className="rounded-lg bg-[#E8E8E8] px-4 py-1.5 text-xs font-medium text-[#181818] hover:bg-white"
          >
            Ir para Novo chat
          </button>
        </div>
      ) : (
        <Tabs.Root
          value={section}
          onValueChange={(val) => setSection(val as WorkbenchSection)}
          className="flex min-h-0 flex-1 flex-col gap-3"
        >
          <Tabs.List
            aria-label="Seções de revisão do workspace"
            className="flex flex-wrap items-center gap-1.5 rounded-xl border border-[#303030] bg-[#1C1C1C] p-1.5"
          >
            <Tabs.Trigger
              value="conflicts"
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-[#969696] transition-colors data-[state=active]:bg-[#202020] data-[state=active]:text-[#E8E8E8]"
            >
              <GitMerge aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Revisão e conflitos 3-way</span>
            </Tabs.Trigger>
            <Tabs.Trigger
              value="artifacts"
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-[#969696] transition-colors data-[state=active]:bg-[#202020] data-[state=active]:text-[#E8E8E8]"
            >
              <FileCode2 aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Artefatos e diffs seguros</span>
            </Tabs.Trigger>
            <Tabs.Trigger
              value="pr"
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-[#969696] transition-colors data-[state=active]:bg-[#202020] data-[state=active]:text-[#E8E8E8]"
            >
              <Package aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Pacote de PR</span>
            </Tabs.Trigger>
          </Tabs.List>

          <Tabs.Content value="conflicts" className="min-h-0 flex-1">
            <ConflictWorkbench
              runId={resolvedRunId}
              onIntegrated={() => {
                void runsQuery.refetch();
              }}
            />
          </Tabs.Content>

          <Tabs.Content value="artifacts" className="min-h-0 flex-1">
            <ArtifactViewer runId={resolvedRunId} />
          </Tabs.Content>

          <Tabs.Content value="pr" className="min-h-0 flex-1">
            <PrPackagePanel runId={resolvedRunId} />
          </Tabs.Content>
        </Tabs.Root>
      )}
    </div>
  );
}
