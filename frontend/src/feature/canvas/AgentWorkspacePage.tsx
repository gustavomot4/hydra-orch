import { CSSProperties, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import {
  LayoutList,
  MessageSquarePlus,
  Network,
  RefreshCw,
  Search,
  PanelRight,
} from 'lucide-react';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useLayoutStore } from '@/store/layoutStore';
import { PanelResizer } from '@/component/PanelResizer';
import { ProjectWorkTree } from '@/feature/chat/ProjectWorkTree';
import { useWorkspaceHierarchy } from '@/hook/useWorkspaceHierarchy';
import { useLiveInvalidation } from '@/hook/useLiveInvalidation';
import { ConversationSnapshot } from '@/feature/chat/conversationTypes';
import { RunDetailSnapshot } from '@/feature/chat/chatTypes';
import { AgentCanvas } from './AgentCanvas';
import { AgentInspector } from './AgentInspector';
import { graphFromConversation, graphFromRun, statusMeta } from './canvasModel';
import './canvas.css';

type Work = { id: string; title: string };
export function AgentWorkspacePage() {
  const client = useControlPlaneClient();
  const { projects } = useWorkspaceHierarchy();
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);
  const project = useLayoutStore((s) => s.selectedProjectId);
  const inspectorWidth = useLayoutStore((s) => s.inspectorWidth);
  const inspectorVisible = useLayoutStore((s) => s.inspectorVisible);
  const statusBarVisible = useLayoutStore((s) => s.statusBarVisible);
  const setAppearance = useLayoutStore((s) => s.setAppearance);
  const [params, setParams] = useSearchParams();
  const kind = params.has('execucao') ? 'runs' : 'chats';
  const page = 0;
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<string | null>('coordinator');
  const [view, setView] = useState<'canvas' | 'list'>(() =>
    window.innerWidth < 840 ? 'list' : 'canvas',
  );
  const picker = useRef<HTMLDetailsElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const previousProject = useRef(project);
  useEffect(() => {
    document.title = 'Área de trabalho · Hydra';
    heading.current?.focus();
  }, []);
  useEffect(() => {
    if (previousProject.current && previousProject.current !== project) setParams({});
    previousProject.current = project;
  }, [project, setParams]);
  const workList = useQuery({
    queryKey: ['canvas-work', project, kind, page],
    queryFn: async ({ signal }) => {
      const base = project ? `&project_id=${encodeURIComponent(project)}` : '';
      if (kind === 'chats')
        return client.request<{ items: Work[]; total: number }>(
          `/v1/control-plane/conversations?limit=10&offset=${page * 10}${base}`,
          { signal },
        );
      const result = await client.request<{
        items: { id: string; objective: string }[];
        total: number;
      }>(`/v1/control-plane/runs?page=${page + 1}&size=10${base}`, { signal });
      return {
        items: result.items.map((r) => ({ id: r.id, title: r.objective })),
        total: result.total,
      };
    },
    refetchInterval: 5000,
    retry: false,
  });
  const id =
    params.get(kind === 'chats' ? 'chat' : 'execucao') || workList.data?.items[0]?.id || '';
  const workKey = kind + ':' + id;
  useEffect(() => {
    if (id && !params.get(kind === 'chats' ? 'chat' : 'execucao'))
      setParams({ [kind === 'chats' ? 'chat' : 'execucao']: id }, { replace: true });
  }, [id, kind, params, setParams]);
  useEffect(() => {
    setSelected('coordinator');
  }, [workKey]);
  const conversation = useQuery({
    queryKey: ['canvas-conversation', id],
    queryFn: ({ signal }) =>
      client.request<ConversationSnapshot>(
        `/v1/control-plane/conversations/${encodeURIComponent(id)}`,
        { signal },
      ),
    enabled: Boolean(id) && kind === 'chats',
    refetchInterval: 2500,
    retry: false,
  });
  const turn =
    conversation.data?.turns.findLast((t) => t.state === 'running' || t.state === 'stopping') ??
    conversation.data?.turns.at(-1);
  const runId = kind === 'runs' ? id : turn?.coordination?.run_id;
  // Read-only planning has a plan but no RunService execution to fetch.
  const hasRun = Boolean(runId && (kind === 'runs' || turn?.coordination?.phase));
  const live = useLiveInvalidation(
    id && kind === 'chats'
      ? `/v1/control-plane/conversations/${encodeURIComponent(id)}/events`
      : null,
    [
      ['canvas-conversation', id],
      ['canvas-run', runId],
    ],
  );
  const runLive = useLiveInvalidation(
    hasRun ? `/v1/control-plane/runs/${encodeURIComponent(runId!)}/events` : null,
    [['canvas-run', runId]],
  );
  const run = useQuery({
    queryKey: ['canvas-run', runId],
    queryFn: ({ signal }) =>
      client.request<RunDetailSnapshot>(`/v1/control-plane/runs/${encodeURIComponent(runId!)}`, {
        signal,
      }),
    enabled: hasRun,
    refetchInterval: 2500,
    retry: false,
  });
  const graph = useMemo(
    () =>
      kind === 'chats' && conversation.data
        ? graphFromConversation(conversation.data, hasRun ? run.data : undefined)
        : kind === 'runs' && run.data
          ? graphFromRun(run.data)
          : { nodes: [], edges: [] },
    [kind, conversation.data, run.data, hasRun],
  );
  const selectedNode = graph.nodes.find((n) => n.id === selected);
  const title = kind === 'chats' ? conversation.data?.title : run.data?.objective;
  const busy =
    workList.isLoading ||
    Boolean(id && (kind === 'chats' ? conversation.isLoading : run.isLoading));
  const error =
    (workList.isError && !workList.data) ||
    Boolean(
      id &&
      (kind === 'chats' ? conversation.isError && !conversation.data : run.isError && !run.data),
    );
  function choose(id: string, mode = kind) {
    setParams({ [mode === 'chats' ? 'chat' : 'execucao']: id });
    if (picker.current) picker.current.open = false;
  }
  return (
    <div className="canvas-page" data-testid="agent-workspace-page">
      <header className="canvas-page-header">
        <div>
          <span className="canvas-eyebrow">Hydra · Seu trabalho</span>
          <h1 ref={heading} tabIndex={-1}>
            Área de trabalho
          </h1>
        </div>
        <Link to="/" className="canvas-button canvas-primary">
          <MessageSquarePlus size={18} aria-hidden="true" />
          Novo pedido
        </Link>
      </header>
      <div className="canvas-toolbar">
        <button
          className="canvas-icon-button"
          aria-label={
            inspectorVisible ? 'Ocultar detalhes dos agentes' : 'Mostrar detalhes dos agentes'
          }
          aria-pressed={inspectorVisible}
          onClick={() => setAppearance({ inspectorVisible: !inspectorVisible })}
        >
          <PanelRight size={16} aria-hidden="true" />
        </button>
        <span className="canvas-live" role="status">
          {live || runLive ? 'Ao vivo' : 'Atualização automática'}
        </span>
        <details ref={picker} className="canvas-work-picker">
          <summary>{title || 'Escolher pedido'}</summary>
          <div className="canvas-work-options">
            <label className="canvas-search">
              <Search size={16} aria-hidden="true" />
              <input
                type="search"
                aria-label="Buscar projeto ou conversa"
                placeholder="Buscar projeto ou conversa…"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                }}
              />
            </label>
            <ProjectWorkTree
              projects={projects}
              search={search}
              selectedId={id}
              onChoose={(work) => {
                previousProject.current = work.projectId;
                selectHierarchy({ projectId: work.projectId, runId: work.id });
                choose(work.id, work.kind);
              }}
            />
          </div>
        </details>
        <div className="canvas-switch" aria-label="Visualização do trabalho">
          <button aria-pressed={view === 'canvas'} onClick={() => setView('canvas')}>
            <Network size={16} />
            Canvas
          </button>
          <button aria-pressed={view === 'list'} onClick={() => setView('list')}>
            <LayoutList size={16} />
            Lista
          </button>
        </div>
        <button
          className="canvas-icon-button"
          aria-label="Atualizar área de trabalho"
          onClick={() => {
            void workList.refetch();
            if (kind === 'chats') void conversation.refetch();
            if (hasRun) void run.refetch();
          }}
        >
          <RefreshCw size={17} />
        </button>
      </div>
      {busy ? (
        <div className="canvas-empty" role="status">
          <Network size={36} aria-hidden="true" />
          <p>Carregando os agentes deste trabalho…</p>
        </div>
      ) : error ? (
        <div className="canvas-empty" role="alert">
          <h2>Não foi possível abrir o trabalho</h2>
          <p>Seus registros continuam preservados.</p>
          <button
            className="canvas-button"
            onClick={() => {
              void workList.refetch();
              if (kind === 'chats') void conversation.refetch();
              else void run.refetch();
            }}
          >
            Tentar novamente
          </button>
        </div>
      ) : !graph.nodes.length ? (
        <div className="canvas-empty">
          <Network size={44} aria-hidden="true" />
          <h2>Uma mesa para seus agentes</h2>
          <p>Envie um pedido para acompanhar os agentes e abrir os detalhes de cada tarefa.</p>
          <Link to="/" className="canvas-button canvas-primary">
            Iniciar uma conversa
          </Link>
          <button className="canvas-button" onClick={() => setParams({ execucao: '' })}>
            Ver execuções existentes
          </button>
        </div>
      ) : (
        <>
          {kind === 'chats' && hasRun && run.isError && (
            <p role="alert" className="canvas-data-warning">
              O plano está visível, mas os detalhes da execução não carregaram.{' '}
              <button onClick={() => void run.refetch()}>Tentar novamente</button>
            </p>
          )}
          <div
            className={`canvas-workbench ${selectedNode && inspectorVisible ? 'with-inspector' : ''}`}
            style={{ '--inspector-width': `${inspectorWidth}px` } as CSSProperties}
          >
            {view === 'canvas' ? (
              <AgentCanvas
                key={workKey}
                graph={graph}
                workId={workKey}
                selected={selected}
                onSelect={(id) => {
                  setSelected(id);
                  if (id) setAppearance({ inspectorVisible: true });
                }}
              />
            ) : (
              <div className="agent-list" aria-label="Agentes deste trabalho">
                {graph.nodes.map((node) => {
                  const meta = statusMeta(node.state);
                  return (
                    <button
                      key={node.id}
                      className={`agent-list-item ${node.id === selected ? 'is-selected' : ''}`}
                      aria-pressed={node.id === selected}
                      onClick={() => {
                        setSelected(node.id);
                        setAppearance({ inspectorVisible: true });
                      }}
                    >
                      <span className={`canvas-status tone-${meta.tone}`}>
                        {meta.symbol} {meta.label}
                      </span>
                      <strong>{node.title}</strong>
                      <span>
                        {node.executor} · {node.model}
                      </span>
                      <p>{node.action}</p>
                    </button>
                  );
                })}
              </div>
            )}
            {selectedNode && inspectorVisible && (
              <PanelResizer
                label="Redimensionar detalhes dos agentes"
                value={inspectorWidth}
                min={260}
                max={640}
                reversed
                onChange={(inspectorWidth) => setAppearance({ inspectorWidth })}
                onReset={() => setAppearance({ inspectorWidth: 320 })}
              />
            )}
            {selectedNode && inspectorVisible && (
              <AgentInspector
                node={selectedNode}
                chat={kind === 'chats' ? conversation.data : undefined}
                onClose={() => {
                  setAppearance({ inspectorVisible: false });
                  heading.current?.focus();
                }}
              />
            )}
          </div>
          {statusBarVisible && (
            <p className="canvas-provenance">
              Linhas mostram tarefas, dependências e resultados registrados. Selecione um card para
              inspecionar.
            </p>
          )}
        </>
      )}
    </div>
  );
}
