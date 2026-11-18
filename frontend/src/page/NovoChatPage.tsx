import { ReactNode, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Send, FolderOpen, ChevronDown } from 'lucide-react';
import { ChatChoice, ChatDialog } from '@/feature/chat/ChatDialog';
import '@/feature/chat/conversation.css';
import { clearComposerDraft, OrchestrationMode } from '@/feature/composer/composerTypes';
import { rememberPrompt } from '@/feature/composer/promptHistory';
import {
  ConversationAgent,
  clearPendingSend,
  pendingSendKey,
  defaultRoute,
  conversationSendError,
  routeSelection,
} from '@/feature/chat/conversationTypes';
import { ConversationRoutePicker } from '@/feature/chat/ConversationRoutePicker';
import { useRouteCatalogWarmup } from '@/feature/chat/useRouteCatalogWarmup';
import { ConversationWorkflow, ExecutionMode } from '@/feature/chat/ConversationWorkflow';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useWorkspaceHierarchy } from '@/hook/useWorkspaceHierarchy';
import { useLayoutStore } from '@/store/layoutStore';

export interface ComposerSlotProps {
  draft: string;
  onDraftChange: (value: string) => void;
  mode: OrchestrationMode;
  onModeChange: (mode: OrchestrationMode) => void;
  selectedProjectId: string;
  onSubmit: () => void;
  isSubmitting: boolean;
  toolbar: ReactNode;
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
  const [route, setRoute] = useState(defaultRoute());
  useRouteCatalogWarmup(route);
  const [routeReady, setRouteReady] = useState(true);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('single');
  const [autoRoute, setAutoRoute] = useState(false);
  const [accessMode, setAccessMode] = useState('read-only');
  const [error, setError] = useState<string | null>(null);
  const [folder, setFolder] = useState('');
  const [folderError, setFolderError] = useState<string | null>(null);
  const [folderOpen, setFolderOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
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
  }, []);
  useEffect(() => {
    if (error) errorRef.current?.focus({ preventScroll: true });
  }, [error]);
  const create = useMutation({
    mutationFn: async () => {
      if (!activeProject) throw new Error('Selecione ou cadastre a pasta do projeto.');
      if (!draft.trim()) throw new Error('Escreva sua mensagem antes de enviar.');
      if (!routeReady)
        throw new Error('Escolha um destino disponível e use Testar combinação antes de enviar.');
      if (!attachmentsReady)
        throw new Error('Aguarde o envio dos anexos ou remova os que falharam.');
      const payload = {
        project_id: activeProject.id,
        executor: effectiveExecutor,
        content: draft.trim(),
        access_mode: accessMode,
        draft_session_id: `draft-${activeProject.id}`,
        attachment_ids: attachmentIds,
        ...(executionMode !== 'single'
          ? { execution_mode: executionMode, auto_route: autoRoute }
          : {}),
        ...(route.connection_mode !== 'direct' || route.target_ref
          ? {
              route: routeSelection({
                ...route,
                executor: effectiveExecutor as 'codex' | 'claude',
              }),
            }
          : {}),
      };
      return client.request<{ conversation_id: string }>('/v1/control-plane/conversations', {
        method: 'POST',
        body: { ...payload, idempotency_key: pendingSendKey(`new:${activeProject.id}`, payload) },
      });
    },
    retry: false,
    onSuccess: ({ conversation_id }) => {
      if (useLayoutStore.getState().promptHistoryEnabled) {
        rememberPrompt(`draft-${activeProject?.id}`, draft.trim());
        rememberPrompt(conversation_id, draft.trim());
      }
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
    onError: (err) => setError(conversationSendError(err, attachmentIds.length > 0)),
    onSettled: () => {
      inFlight.current = false;
    },
  });
  const register = useMutation({
    onMutate: () => setFolderError(null),
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
      setFolderOpen(false);
      setError(null);
    },
    onError: (err) => {
      setFolderError(err instanceof Error ? err.message : 'Não foi possível cadastrar a pasta.');
      setFolderOpen(true);
    },
  });
  const chooseFolder = async () => {
    setPickingFolder(true);
    setFolderError(null);
    try {
      const selected = await client.request<{ path: string | null }>('/v1/launcher/pick-folder', {
        method: 'POST',
      });
      if (selected.path) {
        setFolder(selected.path);
        register.mutate(selected.path);
      }
    } catch (err) {
      setFolderError(
        err instanceof Error
          ? err.message
          : 'Não foi possível abrir o seletor. Informe o caminho da pasta.',
      );
      setFolderOpen(true);
    } finally {
      setPickingFolder(false);
    }
  };
  const addFolder = () => {
    if (desktop) void chooseFolder();
    else setFolderOpen(true);
  };
  const submit = () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setError(null);
    create.mutate();
  };
  const toolbar = (
    <div className="chat-footer-controls">
      <button
        type="button"
        className="chat-choice"
        aria-label={`${effectiveExecutor === 'codex' ? 'Codex' : 'Claude Code'} · ${route.target_ref || 'Padrão do agente'}. Configurar agente, conexão e modelo`}
        aria-haspopup="dialog"
        onClick={() => setConfigOpen(true)}
      >
        <span>
          {effectiveExecutor === 'codex' ? 'Codex' : 'Claude Code'} ·{' '}
          {route.target_ref || 'Padrão do agente'}
        </span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
    </div>
  );
  return (
    <div className="chat-new" data-testid="novo-chat-page">
      <h1 ref={headingRef} tabIndex={-1}>
        O que vamos fazer?
      </h1>
      <div className="chat-context">
        <FolderOpen size={16} aria-hidden="true" />
        <ChatChoice
          label="Pasta"
          value={activeProject?.id ?? ''}
          options={projects.map((p) => ({ id: p.id, name: p.name, detail: p.canonical_root }))}
          onChange={(id) => selectHierarchy({ projectId: id, runId: null, sessionId: null })}
          onAdd={addFolder}
        />
        <button
          type="button"
          className="chat-text-button"
          onClick={addFolder}
          disabled={pickingFolder || register.isPending}
        >
          {pickingFolder
            ? 'Escolha a pasta na janela do Windows…'
            : register.isPending
              ? 'Adicionando pasta…'
              : 'Adicionar pasta'}
        </button>
      </div>
      {isLoading && !projects.length && (
        <p role="status" className="chat-activity">
          Carregando pastas…
        </p>
      )}
      {agents.isError && (
        <p role="alert" className="chat-activity">
          Não foi possível consultar os agentes.{' '}
          <button className="chat-text-button" onClick={() => void agents.refetch()}>
            Tentar novamente
          </button>
        </p>
      )}
      {agents.data && !available.length && (
        <p role="alert" className="chat-activity">
          Nenhum agente instalado disponível.{' '}
          <Link className="underline" to="/terminal">
            Abrir terminal
          </Link>{' '}
          para configurar Codex ou Claude Code.
        </p>
      )}
      {route.connection_mode === 'direct' &&
        agents.data?.find((a) => a.id === effectiveExecutor)?.authenticated === false && (
          <p role="status" className="chat-activity">
            Conecte a conta do agente antes de enviar.{' '}
            <Link className="underline" to="/terminal">
              Abrir terminal
            </Link>{' '}
            para executar{' '}
            <code>{effectiveExecutor === 'codex' ? 'codex login' : 'claude auth login'}</code>.
          </p>
        )}
      <ChatDialog
        title="Adicionar pasta"
        open={folderOpen}
        onOpenChange={(open) => {
          setFolderOpen(open);
          if (!open) setFolderError(null);
        }}
        description="Escolha a pasta do projeto ou informe o caminho neste computador."
      >
        {folderError && <p role="alert" className="chat-error">{folderError}</p>}
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
      </ChatDialog>
      <ChatDialog title="Configuração do pedido" open={configOpen} onOpenChange={setConfigOpen}>
        <fieldset className="chat-agent-options">
          <legend>Agente</legend>
          {(
            agents.data ?? [
              { id: 'codex', name: 'Codex', available: true },
              { id: 'claude', name: 'Claude Code', available: true },
            ]
          ).map((agent) => (
            <label key={agent.id}>
              <input
                type="radio"
                name="new-chat-agent"
                checked={effectiveExecutor === agent.id}
                disabled={!agent.available}
                onChange={() => {
                  setExecutor(agent.id);
                  setRoute(defaultRoute(agent.id as 'codex' | 'claude'));
                }}
              />
              {agent.name}
              {!agent.available && ' · Não instalado'}
            </label>
          ))}
        </fieldset>
        <ConversationRoutePicker
          value={{ ...route, executor: effectiveExecutor as 'codex' | 'claude' }}
          onChange={setRoute}
          onReadyChange={setRouteReady}
          disabled={create.isPending}
        />
        <ConversationWorkflow
          mode={executionMode}
          automatic={autoRoute}
          onChange={(value, automatic) => {
            setExecutionMode(value);
            setMode(value === 'swarm' ? 'swarm' : 'persistent');
            setAutoRoute(automatic);
          }}
          disabled={create.isPending}
        />
        <label className="flex min-h-11 items-center gap-3 text-sm">
          <input
            type="checkbox"
            className="h-6 w-6"
            checked={accessMode === 'workspace-write'}
            onChange={(e) => setAccessMode(e.target.checked ? 'workspace-write' : 'read-only')}
          />
          Permitir edições em uma cópia isolada do projeto
        </label>
        <button type="button" className="chat-save mt-4" onClick={() => setConfigOpen(false)}>
          Concluir configuração
        </button>
      </ChatDialog>
      <div ref={composerRef} className="chat-composer" data-testid="novo-chat-composer-slot">
        {renderComposer ? (
          renderComposer({
            draft,
            onDraftChange: setDraft,
            mode,
            onModeChange: (value) => {
              setMode(value);
              setExecutionMode(value === 'swarm' ? 'swarm' : 'single');
            },
            selectedProjectId: activeProject?.id ?? '',
            onSubmit: submit,
            isSubmitting: create.isPending,
            toolbar,
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
            <div className="mt-3 flex justify-between">
              {toolbar}
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
      <div className="chat-footer-controls">
        <button type="button" className="chat-text-button" onClick={() => setConfigOpen(true)}>
          Opções da conversa
        </button>
        <span className="text-xs text-[var(--text-muted)]">
          {accessMode === 'read-only' ? 'Somente leitura' : 'Edições em cópia isolada'} ·{' '}
          {route.connection_mode === 'omniroute' ? 'OmniRoute' : 'Conta do agente'}
          {executionMode === 'swarm' ? ' · Coordenação de agentes' : ''}
        </span>
      </div>
    </div>
  );
}
