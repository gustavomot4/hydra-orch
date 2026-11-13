import { ReactNode, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Bot,
  FolderGit2,
  Mic,
  Paperclip,
  Send,
  Sparkles,
  Terminal,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useCapabilities } from '@/hook/useCapabilities';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useWorkspaceHierarchy } from '@/hook/useWorkspaceHierarchy';
import { useLayoutStore } from '@/store/layoutStore';
import { ControlPlaneApiError, QuotaInventory } from '@/type/controlPlane';

export interface ComposerSlotProps {
  draft: string;
  onDraftChange: (value: string) => void;
  mode: 'relay' | 'swarm' | 'persistent';
  onModeChange: (mode: 'relay' | 'swarm' | 'persistent') => void;
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
    label: 'Executar suíte de testes e diagnosticar falhas',
    prompt: 'Execute a suíte de testes do projeto selecionado e reporte eventuais falhas.',
    icon: Bot,
  },
  {
    id: 'chip-swarm',
    label: 'Planejar decomposição em swarm',
    prompt: 'Decomponha esta entrega em subtarefas paralelas isoladas por worktree.',
    icon: FolderGit2,
  },
  {
    id: 'chip-terminal',
    label: 'Abrir terminal interativo no workspace',
    prompt: 'Preparar sessão PTY interativa no diretório raiz do projeto.',
    icon: Terminal,
  },
];

export function NovoChatPage({ renderComposer }: NovoChatPageProps) {
  const client = useControlPlaneClient();
  const { projects, executors } = useWorkspaceHierarchy();
  const { getHostCapability } = useCapabilities();

  const selectedHostId = useLayoutStore((s) => s.selectedHostId);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);
  const openTab = useLayoutStore((s) => s.openTab);

  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState<'relay' | 'swarm' | 'persistent'>('relay');
  const [selectedExecutor, setSelectedExecutor] = useState<string>('codex');
  const [feedback, setFeedback] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const effectiveProjectId = selectedProjectId ?? projects[0]?.id ?? '';
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
        throw new Error('Selecione ou registre um projeto antes de iniciar um run.');
      }
      const cleanObjective = draft.trim();
      if (!cleanObjective) {
        throw new Error('Descreva o objetivo da tarefa antes de enviar.');
      }
      const idempotencyKey = `ui-run-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
      const resolvedExecutor =
        executors.find((ex) => ex.id === selectedExecutor)?.driver ??
        selectedExecutor ??
        'codex';
      return client.request<{ run_id: string; status: string }>('/v1/control-plane/runs', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: {
          project_id: activeProject.id,
          repo_root: activeProject.canonical_root,
          base_branch: activeProject.base_branch ?? 'main',
          objective: cleanObjective,
          mode,
          task_spec: {
            task_id: 'task-1',
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
      setFeedback({
        kind: 'ok',
        text: `Run ${created.run_id} registrado (${created.status}).`,
      });
      setDraft('');
      openTab({
        id: `tab:run:${created.run_id}`,
        kind: 'chat',
        title: created.run_id,
        route: `/chat/${created.run_id}`,
        runId: created.run_id,
        projectId: activeProject?.id,
        hostId: selectedHostId,
        closable: true,
      });
    },
    onError: (err) => {
      if (err instanceof ControlPlaneApiError) {
        setFeedback({ kind: 'error', text: err.payload.message });
      } else if (err instanceof Error) {
        setFeedback({ kind: 'error', text: err.message });
      } else {
        setFeedback({ kind: 'error', text: 'Falha ao registrar run no Control Plane.' });
      }
    },
  });

  const attachmentsCap = getHostCapability(selectedHostId, 'attachments');
  const dictationCap = getHostCapability(selectedHostId, 'dictation_stt');
  const inventory = inventoryQuery.data;
  const routeModeLabel =
    inventory?.connection_mode === 'disabled' || !inventory
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
      className="mx-auto flex min-h-full w-full max-w-4xl flex-col items-center justify-between px-4 py-8 md:px-8"
    >
      <div className="flex w-full flex-1 flex-col items-center justify-center gap-6 py-6 text-center">
        <div className="space-y-2">
          <p className="font-mono text-xs uppercase tracking-widest text-[#969696]">
            {selectedHostId} · {activeProject ? activeProject.name : 'sem workspace ativo'}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-[#E8E8E8] md:text-3xl">
            Novo chat
          </h1>
          <p className="mx-auto max-w-lg text-sm text-[#969696]">
            Inicie uma conversa coordenada com verificação real de workspace, checks e histórico durável.
          </p>
        </div>

        <div className="flex w-full max-w-2xl flex-wrap items-center justify-center gap-2 rounded-xl border border-[#303030] bg-[#202020] p-3 text-left">
          <div className="flex min-w-[180px] flex-1 flex-col gap-1">
            <label htmlFor="novo-chat-project-select" className="text-[11px] text-[#969696]">
              Projeto / Workspace
            </label>
            <select
              id="novo-chat-project-select"
              value={effectiveProjectId}
              onChange={(e) => selectHierarchy({ projectId: e.target.value || null })}
              className="rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
            >
              {projects.length === 0 ? (
                <option value="">Nenhum projeto registrado</option>
              ) : (
                projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name} ({project.base_branch ?? 'main'})
                  </option>
                ))
              )}
            </select>
          </div>

          <div className="flex min-w-[160px] flex-1 flex-col gap-1">
            <label htmlFor="novo-chat-agent-select" className="text-[11px] text-[#969696]">
              Executor / Agente
            </label>
            <select
              id="novo-chat-agent-select"
              value={selectedExecutor}
              onChange={(e) => setSelectedExecutor(e.target.value)}
              className="rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
            >
              {executors.length === 0 ? (
                <>
                  <option value="codex">codex (padrão)</option>
                  <option value="claude">claude (padrão)</option>
                </>
              ) : (
                executors.map((ex) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name} ({ex.status})
                  </option>
                ))
              )}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-[#969696]">Roteamento e conta</span>
            <div className="flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]">
              <span>{routeModeLabel}</span>
              {accountOverrideKeys.length > 0 ? (
                <span className="font-mono text-[11px] text-[#969696]">
                  · {accountOverrideKeys.join(', ')}
                </span>
              ) : null}
              <StatusBadge
                status={inventory?.quota?.status ?? 'unknown'}
                compact
              />
            </div>
          </div>
        </div>

        <div
          aria-label="Ações rápidas"
          className="flex w-full max-w-2xl flex-wrap items-center justify-center gap-2"
        >
          {QUICK_CHIPS.map((chip) => {
            const Icon = chip.icon;
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => {
                  setDraft(chip.prompt);
                  setFeedback(null);
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] transition-colors hover:bg-[#282828]"
              >
                <Icon aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
                <span>{chip.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div
        data-testid="novo-chat-composer-slot"
        className="w-full max-w-3xl"
      >
        {renderComposer ? (
          renderComposer({
            draft,
            onDraftChange: setDraft,
            mode,
            onModeChange: setMode,
            selectedProjectId: effectiveProjectId,
            onSubmit: () => createRunMutation.mutate(),
            isSubmitting: createRunMutation.isPending,
          })
        ) : (
          <div className="rounded-2xl border border-[#303030] bg-[#202020] p-3 shadow-lg">
            <label htmlFor="novo-chat-prompt-input" className="sr-only">
              Descreva a tarefa para o coordenador
            </label>
            <textarea
              id="novo-chat-prompt-input"
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Descreva a tarefa ou comando para o coordenador..."
              className="w-full resize-none bg-transparent px-1 py-1 text-sm text-[#E8E8E8] placeholder:text-[#969696] focus:outline-none"
            />

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[#303030] pt-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="novo-chat-mode-select" className="sr-only">
                  Modo de orquestração
                </label>
                <select
                  id="novo-chat-mode-select"
                  value={mode}
                  onChange={(e) =>
                    setMode(e.target.value as 'relay' | 'swarm' | 'persistent')
                  }
                  className="rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1 text-xs text-[#E8E8E8]"
                >
                  <option value="relay">Modo Relay</option>
                  <option value="swarm">Modo Swarm</option>
                  <option value="persistent">Modo Persistente</option>
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
                disabled={createRunMutation.isPending}
                onClick={() => createRunMutation.mutate()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3.5 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Send aria-hidden="true" className="h-3.5 w-3.5" />
                <span>{createRunMutation.isPending ? 'Enviando...' : 'Iniciar run'}</span>
              </button>
            </div>
          </div>
        )}

        {feedback ? (
          <div
            role={feedback.kind === 'error' ? 'alert' : 'status'}
            className={`mt-2 rounded-lg border px-3 py-2 text-xs ${
              feedback.kind === 'error'
                ? 'border-[#EF4444]/40 bg-[#EF4444]/10 text-[#FCA5A5]'
                : 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]'
            }`}
          >
            {feedback.text}
          </div>
        ) : null}
      </div>
    </div>
  );
}
