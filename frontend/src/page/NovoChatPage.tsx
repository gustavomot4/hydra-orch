import { ReactNode, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Bot,
  FolderGit2,
  Mic,
  Paperclip,
  Send,
  Sparkles,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import {
  clearComposerDraft,
  OrchestrationMode,
  ORCHESTRATION_MODE_LABELS,
} from '@/feature/composer/composerTypes';
import { useCapabilities } from '@/hook/useCapabilities';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useWorkspaceHierarchy } from '@/hook/useWorkspaceHierarchy';
import { useLayoutStore } from '@/store/layoutStore';
import { ControlPlaneApiError, QuotaInventory } from '@/type/controlPlane';

export interface ComposerSlotProps {
  draft: string;
  onDraftChange: (value: string) => void;
  mode: OrchestrationMode;
  onModeChange: (mode: OrchestrationMode) => void;
  selectedProjectId: string;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export interface NovoChatPageProps {
  renderComposer?: (props: ComposerSlotProps) => ReactNode;
}

interface QuickChip {
  id: string;
  label: string;
  prompt: string;
  icon: typeof Sparkles;
}

const QUICK_CHIPS: QuickChip[] = [
  {
    id: 'chip-review',
    label: 'Revisar alterações e gerar PR',
    prompt: 'Analise o diff atual do workspace, execute os checks e prepare o pacote de PR.',
    icon: Sparkles,
  },
  {
    id: 'chip-tests',
    label: 'Executar testes',
    prompt: 'Execute a suíte de testes do projeto selecionado e reporte eventuais falhas.',
    icon: Bot,
  },
  {
    id: 'chip-swarm',
    label: 'Planejar tarefas em paralelo',
    prompt: 'Decomponha esta entrega em subtarefas paralelas isoladas por worktree.',
    icon: FolderGit2,
  },
];

export function NovoChatPage({ renderComposer }: NovoChatPageProps) {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { projects, executors, isLoading } = useWorkspaceHierarchy();
  const { getHostCapability } = useCapabilities();

  const selectedHostId = useLayoutStore((s) => s.selectedHostId);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);
  const openTab = useLayoutStore((s) => s.openTab);

  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState<OrchestrationMode>('relay');
  const [selectedExecutor, setSelectedExecutor] = useState<string>('codex');
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const composerRef = useRef<HTMLDivElement>(null);

  const effectiveProjectId = selectedProjectId ?? projects[0]?.id ?? '';
  const effectiveExecutorId = executors.some((executor) => executor.id === selectedExecutor)
    ? selectedExecutor
    : executors[0]?.id ?? selectedExecutor;
  const activeProject = useMemo(
    () => projects.find((p) => p.id === effectiveProjectId) ?? null,
    [projects, effectiveProjectId],
  );

  const inventoryQuery = useQuery<QuotaInventory>({
    queryKey: ['control-plane', 'omniroute-inventory'],
    queryFn: () => client.getOmniRouteInventory('default'),
    retry: false,
    staleTime: 30_000,
  });

  const createRunMutation = useMutation({
    mutationFn: async () => {
      if (!activeProject) {
        throw new Error('Selecione um projeto para criar a tarefa.');
      }
      const cleanObjective = draft.trim();
      if (!cleanObjective) {
        throw new Error('Descreva o objetivo da tarefa antes de enviar.');
      }
      const idempotencyKey = `ui-run-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
      const resolvedExecutor =
        executors.find((ex) => ex.id === effectiveExecutorId)?.driver ?? effectiveExecutorId;
      return client.request<{ run_id: string }>('/v1/control-plane/runs', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: {
          project_id: activeProject.id,
          repo_root: activeProject.canonical_root,
          base_branch: activeProject.base_branch ?? 'main',
          objective: cleanObjective,
          mode,
          task_spec: {
            task_id: `task-${idempotencyKey}`,
            objective: cleanObjective,
            acceptance_criteria: [
              {
                check_id: 'chk-status',
                command: ['git', 'status', '--short'],
                description: 'Verificação base do workspace',
              },
            ],
            allowed_paths: ['*'],
            assigned_executor: resolvedExecutor,
          },
          idempotency_key: idempotencyKey,
          execute: false,
        },
      });
    },
    retry: false,
    onSuccess: (created) => {
      const route = `/chat/${encodeURIComponent(created.run_id)}`;
      if (activeProject) clearComposerDraft(`draft-${activeProject.id}`);
      setDraft('');
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'runs'] });
      openTab({
        id: `tab:run:${created.run_id}`,
        kind: 'chat',
        title: draft.trim(),
        route,
        runId: created.run_id,
        projectId: activeProject?.id,
        hostId: selectedHostId,
        closable: true,
      });
      navigate(route);
    },
    onError: (err) => {
      if (err instanceof ControlPlaneApiError) {
        setSubmissionError(err.payload.message);
      } else if (err instanceof Error) {
        setSubmissionError(err.message);
      } else {
        setSubmissionError('Não foi possível criar a tarefa. Tente novamente.');
      }
    },
  });
  const submitTask = () => {
    setSubmissionError(null);
    createRunMutation.mutate();
  };

  const attachmentsCap = getHostCapability(selectedHostId, 'attachments');
  const dictationCap = getHostCapability(selectedHostId, 'dictation_stt');
  const inventory = inventoryQuery.data;
  const routeModeLabel =
    !inventory
      ? (inventoryQuery.isLoading ? 'Consultando rota…' : 'Rota indisponível')
      : inventory.connection_mode === 'disabled'
        ? 'Rota direta'
        : inventory.available
          ? `Gateway (${inventory.connection_mode})`
          : 'Gateway indisponível';

  const accountOverrideKeys = inventory
    ? Object.keys(inventory.next_account_overrides ?? {})
    : [];

  return (
    <div
      data-testid="novo-chat-page"
      className="mx-auto w-full max-w-4xl px-4 py-6 md:px-8 md:py-12"
    >
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight text-[#E8E8E8] md:text-3xl">
          Novo chat
        </h1>
        <div className="flex flex-wrap gap-3">
          <div className="flex min-w-0 flex-[2_1_10rem] flex-col gap-1">
            <label htmlFor="novo-chat-project-select" className="text-sm font-medium text-[#D1D1D1]">
              Projeto
            </label>
            <select
              id="novo-chat-project-select"
              value={effectiveProjectId}
              onChange={(e) => {
                const project = projects.find((entry) => entry.id === e.target.value);
                selectHierarchy({
                  projectId: project?.id ?? null,
                  workspaceId: project?.workspace_id ?? null,
                  runId: null,
                  sessionId: null,
                });
              }}
              className="min-h-9 w-full rounded-lg border border-[#666] bg-[#1C1C1C] px-2.5 py-1.5 text-sm text-[#E8E8E8] [@media(pointer:coarse)]:min-h-[44px]"
            >
              {projects.length === 0 ? (
                <option value="">{isLoading ? 'Carregando projetos…' : 'Selecione um projeto'}</option>
              ) : (
                <>
                  {!activeProject ? <option value={effectiveProjectId}>Selecione um projeto</option> : null}
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name} ({project.base_branch ?? 'main'})
                    </option>
                  ))}
                </>
              )}
            </select>
          </div>

          <div className="flex min-w-0 flex-[1_1_8rem] flex-col gap-1">
            <label htmlFor="novo-chat-agent-select" className="text-sm font-medium text-[#D1D1D1]">
              Agente
            </label>
            <select
              id="novo-chat-agent-select"
              value={effectiveExecutorId}
              onChange={(e) => setSelectedExecutor(e.target.value)}
              className="min-h-9 w-full rounded-lg border border-[#666] bg-[#1C1C1C] px-2.5 py-1.5 text-sm text-[#E8E8E8] [@media(pointer:coarse)]:min-h-[44px]"
            >
              {executors.length === 0 ? (
                <>
                  <option value="codex">Codex</option>
                  <option value="claude">Claude</option>
                </>
              ) : (
                executors.map((ex) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name}
                  </option>
                ))
              )}
            </select>
          </div>
        </div>
        {!activeProject && !isLoading ? (
          <p role="status" className="text-sm text-[#D1D1D1]">
            {projects.length ? 'Selecione um projeto para criar a tarefa.' : 'Cadastre um projeto para criar sua primeira tarefa.'}
          </p>
        ) : null}
      </div>

      <div
        data-testid="novo-chat-composer-slot"
        ref={composerRef}
        className="mt-4"
      >
        {renderComposer ? (
          renderComposer({
            draft,
            onDraftChange: setDraft,
            mode,
            onModeChange: setMode,
            selectedProjectId: activeProject?.id ?? '',
            onSubmit: submitTask,
            isSubmitting: createRunMutation.isPending,
          })
        ) : (
          <div className="rounded-2xl border border-[#303030] bg-[#202020] p-3 shadow-lg">
            <label htmlFor="novo-chat-prompt-input" className="mb-1 block text-sm font-semibold">
              Descreva a tarefa para o coordenador
            </label>
            <textarea
              id="novo-chat-prompt-input"
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Descreva a tarefa ou comando para o coordenador..."
              className="w-full resize-y rounded-lg border border-[#666] bg-[#181818] px-2 py-2 text-sm text-[#E8E8E8] placeholder:text-[#969696]"
            />

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[#303030] pt-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="novo-chat-mode-select" className="sr-only">
                  Modo de orquestração
                </label>
                <select
                  id="novo-chat-mode-select"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as OrchestrationMode)}
                  className="rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1 text-xs text-[#E8E8E8]"
                >
                  {Object.entries(ORCHESTRATION_MODE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>

                <span
                  title={
                    attachmentsCap.supported
                      ? 'Anexos habilitados na Onda 14'
                      : 'Anexos indisponíveis neste host'
                  }
                  className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#141414] px-2 py-1 text-[11px] text-[#969696]"
                >
                  <Paperclip aria-hidden="true" className="h-3 w-3" />
                  <span>Anexos</span>
                </span>

                <span
                  title={
                    dictationCap.detail?.duplex_voice_enabled
                      ? 'Voz ativa'
                      : 'Ditado opcional apenas como rascunho de texto (Onda 14)'
                  }
                  className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#141414] px-2 py-1 text-[11px] text-[#969696]"
                >
                  <Mic aria-hidden="true" className="h-3 w-3" />
                  <span>Ditado</span>
                </span>
              </div>

              <button
                type="button"
                disabled={createRunMutation.isPending || !activeProject || !draft.trim()}
                onClick={submitTask}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3.5 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Send aria-hidden="true" className="h-3.5 w-3.5" />
                <span>{createRunMutation.isPending ? 'Enviando...' : 'Criar tarefa'}</span>
              </button>
            </div>
          </div>
        )}

        {submissionError ? (
          <div
            role="alert"
            className="mt-2 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-sm text-[#FCA5A5]"
          >
            {submissionError}
          </div>
        ) : null}
      </div>
      <div className="mt-5 space-y-3 border-t border-[#303030] pt-3">
        {!draft.trim() ? (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Sugestões de tarefa">
            {QUICK_CHIPS.map((chip) => {
              const Icon = chip.icon;
              return (
                <button
                  key={chip.id}
                  type="button"
                  onClick={() => {
                    setDraft(chip.prompt);
                    setSubmissionError(null);
                    composerRef.current?.querySelector('textarea')?.focus();
                  }}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-left text-sm text-[#E8E8E8] hover:bg-[#282828]"
                >
                  <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />
                  <span>{chip.label}</span>
                </button>
              );
            })}
          </div>
        ) : null}
        <details className="text-sm text-[#D1D1D1]">
          <summary className="w-fit cursor-pointer rounded-md py-1">Roteamento e conta</summary>
          <div className="flex flex-wrap items-center gap-2 px-4 py-2">
            <span>{routeModeLabel}</span>
            {accountOverrideKeys.length ? <span>{accountOverrideKeys.join(', ')}</span> : null}
            <StatusBadge status={inventory?.quota?.status ?? 'unknown'} compact />
          </div>
        </details>
      </div>
    </div>
  );
}
