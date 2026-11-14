import { ReactNode, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Send } from 'lucide-react';
import { clearComposerDraft, OrchestrationMode } from '@/feature/composer/composerTypes';
import {
  ConversationAgent,
  clearPendingSend,
  pendingSendKey,
} from '@/feature/chat/conversationTypes';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useWorkspaceHierarchy } from '@/hook/useWorkspaceHierarchy';
import { useLayoutStore } from '@/store/layoutStore';
import { ControlPlaneApiError } from '@/type/controlPlane';

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
  attachmentIds?: string[];
  attachmentsReady?: boolean;
  onStarted?: () => void;
}
const fieldClass =
  'min-h-11 w-full rounded-lg border border-[#666] bg-[#1C1C1C] px-3 py-2 text-sm text-[#E8E8E8]';

export function NovoChatPage({
  renderComposer,
  attachmentIds = [],
  attachmentsReady = true,
  onStarted,
}: NovoChatPageProps) {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { projects, isLoading } = useWorkspaceHierarchy();
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectedHostId = useLayoutStore((s) => s.selectedHostId);
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);
  const openTab = useLayoutStore((s) => s.openTab);
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState<OrchestrationMode>('persistent');
  const [executor, setExecutor] = useState('codex');
  const [accessMode, setAccessMode] = useState('read-only');
  const [error, setError] = useState<string | null>(null);
  const [folder, setFolder] = useState('');
  const [pickingFolder, setPickingFolder] = useState(false);
  const desktop = Boolean(document.querySelector('meta[name="hydra-desktop"]'));
  const inFlight = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const activeProject = selectedProjectId
    ? projects.find((p) => p.id === selectedProjectId)
    : projects[0];
  const agents = useQuery({
    queryKey: ['control-plane', 'conversation-agents'],
    queryFn: () => client.request<ConversationAgent[]>('/v1/control-plane/conversation-agents'),
    retry: false,
  });
  const available = agents.data?.filter((agent) => agent.available) ?? [];
  const effectiveExecutor =
    available.find((a) => a.id === executor)?.id ?? available[0]?.id ?? executor;
  useEffect(() => {
    document.title = 'Novo chat · Hydra';
    headingRef.current?.focus();
  }, []);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  const create = useMutation({
    mutationFn: async () => {
      if (!activeProject) throw new Error('Selecione ou cadastre a pasta do projeto.');
      if (!draft.trim()) throw new Error('Escreva sua mensagem antes de enviar.');
      if (!attachmentsReady)
        throw new Error('Aguarde o envio dos anexos ou remova os que falharam.');
      const payload = {
        project_id: activeProject.id,
        executor: effectiveExecutor,
        content: draft.trim(),
        access_mode: accessMode,
        draft_session_id: `draft-${activeProject.id}`,
        attachment_ids: attachmentIds,
      };
      return client.request<{ conversation_id: string }>('/v1/control-plane/conversations', {
        method: 'POST',
        body: { ...payload, idempotency_key: pendingSendKey(`new:${activeProject.id}`, payload) },
      });
    },
    retry: false,
    onSuccess: ({ conversation_id }) => {
      const route = `/chat/${encodeURIComponent(conversation_id)}`;
      clearPendingSend(`new:${activeProject?.id}`);
      clearComposerDraft(`draft-${activeProject?.id}`);
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'conversations'] });
      openTab({
        id: `tab:chat:${conversation_id}`,
        kind: 'chat',
        title: draft.trim().slice(0, 90),
        route,
        runId: conversation_id,
        projectId: activeProject?.id,
        hostId: selectedHostId,
        closable: true,
      });
      setDraft('');
      onStarted?.();
      navigate(route);
    },
    onError: (err) =>
      setError(
        err instanceof ControlPlaneApiError && err.status === 404
          ? 'O backend aberto ainda não tem o fluxo de conversa. Reinicie o backend e tente novamente. Sua mensagem foi preservada.'
          : err instanceof ControlPlaneApiError
            ? err.payload.message
            : err instanceof Error
              ? err.message
              : 'Não foi possível enviar. Tente novamente.',
      ),
    onSettled: () => {
      inFlight.current = false;
    },
  });
  const register = useMutation({
    mutationFn: async (selectedFolder: string | undefined) => {
      const chosen = (selectedFolder ?? folder).trim().replace(/^"(.*)"$/, '$1');
      const normalize = (value: string) =>
        /^[a-z]:[\\/]/i.test(value)
          ? value.replace(/\\/g, '/').replace(/\/$/, '').toLowerCase()
          : value.replace(/\/$/, '');
      const existing = projects.find((p) => normalize(p.canonical_root) === normalize(chosen));
      if (existing) return existing;
      return client.request<{ id: string }>('/v1/control-plane/projects', {
        method: 'POST',
        body: {
          canonical_root: chosen,
          allow_plain_folder: true,
          name: chosen.split(/[\\/]/).filter(Boolean).pop() || 'Meu projeto',
        },
      });
    },
    onSuccess: (project) => {
      selectHierarchy({ projectId: project.id, runId: null, sessionId: null });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'projects'] });
      setFolder('');
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Não foi possível cadastrar a pasta.'),
  });
  const chooseFolder = async () => {
    setPickingFolder(true);
    setError(null);
    try {
      const selected = await client.request<{ path: string | null }>('/v1/launcher/pick-folder', {
        method: 'POST',
      });
      if (selected.path) {
        setFolder(selected.path);
        register.mutate(selected.path);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível abrir o seletor. Informe o caminho da pasta.',
      );
    } finally {
      setPickingFolder(false);
    }
  };
  const submit = () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setError(null);
    create.mutate();
  };
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6" data-testid="novo-chat-page">
      <h1 ref={headingRef} tabIndex={-1} className="mb-6 text-2xl font-semibold text-[#E8E8E8]">
        O que vamos fazer?
      </h1>
      <p className="mb-5 text-sm text-[#D1D1D1]">
        Escolha uma pasta e envie seu pedido. Cada conversa mantém seu próprio histórico.
      </p>
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="min-w-0 flex-[2_1_12rem]">
          <label htmlFor="novo-chat-project-select" className="mb-1 block text-sm text-[#D1D1D1]">
            Pasta
          </label>
          <select
            id="novo-chat-project-select"
            value={activeProject?.id ?? ''}
            className={fieldClass}
            onChange={(e) =>
              selectHierarchy({ projectId: e.target.value, runId: null, sessionId: null })
            }
          >
            {!projects.length && (
              <option value="">
                {isLoading ? 'Carregando pastas…' : 'Adicione uma pasta abaixo'}
              </option>
            )}
            {projects.length > 0 && !activeProject && <option value="">Selecione uma pasta</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 flex-[1_1_9rem]">
          <label htmlFor="novo-chat-agent-select" className="mb-1 block text-sm text-[#D1D1D1]">
            Agente
          </label>
          <select
            id="novo-chat-agent-select"
            className={fieldClass}
            value={effectiveExecutor}
            onChange={(e) => setExecutor(e.target.value)}
          >
            {(
              agents.data ?? [
                { id: 'codex', name: 'Codex', available: true },
                { id: 'claude', name: 'Claude Code', available: true },
              ]
            ).map((agent) => (
              <option key={agent.id} value={agent.id} disabled={!agent.available}>
                {agent.name}
                {!agent.available ? ' · Não instalado' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>
      {agents.data && !available.length && (
        <p role="status" className="mb-3 text-sm text-[#D1D1D1]">
          Instale Codex ou Claude Code e conecte sua conta.{' '}
          <Link to="/recursos" className="underline">
            Abrir recursos
          </Link>
        </p>
      )}
      {agents.data?.find((a) => a.id === effectiveExecutor)?.authenticated === false &&
        available.length > 0 && (
          <p role="status" className="mb-3 text-sm text-[#D1D1D1]">
            Conecte a conta do agente antes de enviar.{' '}
            <Link className="underline" to="/terminal">
              Abrir terminal
            </Link>{' '}
            para executar{' '}
            <code>{effectiveExecutor === 'codex' ? 'codex login' : 'claude auth login'}</code>.
          </p>
        )}
      <details className="mb-4 text-sm text-[#D1D1D1]" open={!projects.length && !isLoading}>
        <summary className="w-fit cursor-pointer py-2">Adicionar pasta</summary>
        <form
          className="mt-2 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            register.mutate(undefined);
          }}
        >
          {desktop && (
            <button
              type="button"
              disabled={pickingFolder || register.isPending}
              className="min-h-11 rounded-lg border border-[#666] px-3"
              onClick={() => void chooseFolder()}
            >
              {pickingFolder ? 'Escolhendo pasta…' : 'Selecionar pasta'}
            </button>
          )}
          <div className="min-w-0 flex-[1_1_15rem]">
            <label htmlFor="chat-folder" className="mb-1 block">
              Caminho da pasta neste computador
            </label>
            <input
              id="chat-folder"
              className={fieldClass}
              autoComplete="off"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder="C:\\projetos\\meu-projeto"
            />
          </div>
          <button
            className="min-h-11 rounded-lg border border-[#666] px-3"
            disabled={!folder.trim() || register.isPending}
          >
            Usar esta pasta
          </button>
        </form>
      </details>
      <div ref={composerRef} data-testid="novo-chat-composer-slot">
        {renderComposer ? (
          renderComposer({
            draft,
            onDraftChange: setDraft,
            mode,
            onModeChange: setMode,
            selectedProjectId: activeProject?.id ?? '',
            onSubmit: submit,
            isSubmitting: create.isPending,
          })
        ) : (
          <form
            className="rounded-2xl border border-[#666] bg-[#202020] p-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <label htmlFor="novo-chat-prompt-input" className="mb-2 block text-sm text-[#D1D1D1]">
              Sua mensagem
            </label>
            <textarea
              id="novo-chat-prompt-input"
              className={`${fieldClass} min-h-28 resize-y`}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ex.: leia o README e explique como iniciar este projeto."
            />
            <div className="mt-3 flex justify-end">
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-[#E8E8E8] px-4 text-[#181818] disabled:opacity-60"
                disabled={create.isPending || !draft.trim() || !activeProject}
                aria-busy={create.isPending}
              >
                <Send aria-hidden="true" size={16} />
                {create.isPending ? 'Enviando…' : 'Enviar'}
              </button>
            </div>
          </form>
        )}
      </div>
      {error && (
        <div
          ref={errorRef}
          tabIndex={-1}
          role="alert"
          className="mt-3 rounded-lg border border-[#FCA5A5] p-3 text-sm text-[#FCA5A5]"
        >
          {error}
        </div>
      )}
      {!attachmentsReady && (
        <p role="status" className="mt-2 text-sm text-[#D1D1D1]">
          Aguarde os anexos ou remova os que falharam antes de enviar.
        </p>
      )}
      {!draft && (
        <div className="mt-4 flex flex-wrap gap-2" aria-label="Sugestões de mensagem">
          {[
            'Explique como iniciar este projeto',
            'Revise o código e encontre problemas',
            'Me ajude a planejar uma mudança',
          ].map((label) => (
            <button
              key={label}
              className="min-h-11 rounded-lg border border-[#666] px-3 py-2 text-left text-sm text-[#D1D1D1]"
              onClick={() => {
                setDraft(label);
                composerRef.current?.querySelector('textarea')?.focus();
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <details className="mt-4 text-sm text-[#D1D1D1]">
        <summary className="w-fit cursor-pointer py-2">Opções da conversa</summary>
        <label className="mt-2 flex min-h-11 items-center gap-3">
          <input
            type="checkbox"
            className="h-8 w-8 shrink-0"
            checked={accessMode === 'workspace-write'}
            onChange={(e) => setAccessMode(e.target.checked ? 'workspace-write' : 'read-only')}
          />
          Permitir edições em uma cópia isolada do projeto
        </label>
        <p className="mt-1">As alterações ficam disponíveis para revisão na conversa.</p>
      </details>
    </div>
  );
}
