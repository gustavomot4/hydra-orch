import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  LayoutList,
  MessageSquarePlus,
  Network,
  RefreshCw,
  Search,
} from 'lucide-react';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useLayoutStore } from '@/store/layoutStore';
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
  const project = useLayoutStore((s) => s.selectedProjectId);
  const [params, setParams] = useSearchParams();
  const kind = params.has('execucao') ? 'runs' : 'chats';
  const [page, setPage] = useState(0);
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
    setPage(0);
  }, [project, kind]);
  useEffect(() => {
    if (previousProject.current && previousProject.current !== project) setParams({});
    previousProject.current = project;
  }, [project, setParams]);
  const workList = useQuery({
    queryKey: ['canvas-work', project, kind, page, search],
    queryFn: async ({ signal }) => {
      const base = project ? `&project_id=${encodeURIComponent(project)}` : '';
      if (kind === 'chats')
        return client.request<{ items: Work[]; total: number }>(
          `/v1/control-plane/conversations?limit=10&offset=${page * 10}&q=${encodeURIComponent(search)}${base}`,
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
  const filtered =
    workList.data?.items.filter(
      (item) =>
        kind !== 'runs' || item.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
    ) ?? [];
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
        <span className="canvas-live" role="status">
          {live || runLive ? 'Ao vivo' : 'Atualização automática'}
        </span>
        <details ref={picker} className="canvas-work-picker">
          <summary>{title || 'Escolher pedido'}</summary>
          <div className="canvas-work-options">
            <div className="canvas-switch" aria-label="Origem do trabalho">
              <button
                aria-pressed={kind === 'chats'}
                onClick={() => {
                  setSearch('');
                  setPage(0);
                  setParams({});
                }}
              >
                Conversas
              </button>
              <button
                aria-pressed={kind === 'runs'}
                onClick={() => {
                  setSearch('');
                  setPage(0);
                  setParams({ execucao: '' });
                }}
              >
                Execuções
              </button>
            </div>
            <label className="canvas-search">
              <Search size={16} aria-hidden="true" />
              <input
                type="search"
                aria-label={kind === 'chats' ? 'Buscar pedido' : 'Buscar nesta página'}
                placeholder={kind === 'chats' ? 'Buscar pedido…' : 'Buscar nesta página…'}
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  if (kind === 'chats') setPage(0);
                }}
              />
            </label>
            {filtered.map((work) => (
              <button
                className="canvas-work-option"
                key={work.id}
                aria-pressed={work.id === id}
                onClick={() => choose(work.id)}
              >
                {work.title}
              </button>
            ))}
            {!filtered.length && !workList.isLoading && <p>Nenhum pedido encontrado.</p>}
            {!!workList.data?.total && (
              <div className="canvas-pagination">
                <button
                  aria-label="Página anterior de pedidos"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ArrowLeft size={16} />
                </button>
                <span>
                  {page * 10 + 1}–{Math.min((page + 1) * 10, workList.data.total)} de{' '}
                  {workList.data.total}
                </span>
                <button
                  aria-label="Próxima página de pedidos"
                  disabled={(page + 1) * 10 >= workList.data.total}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ArrowRight size={16} />
                </button>
              </div>
            )}
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
          <div className={`canvas-workbench ${selectedNode ? 'with-inspector' : ''}`}>
            {view === 'canvas' ? (
              <AgentCanvas
                key={workKey}
                graph={graph}
                workId={workKey}
                selected={selected}
                onSelect={setSelected}
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
                      onClick={() => setSelected(node.id)}
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
            {selectedNode && (
              <AgentInspector
                node={selectedNode}
                chat={kind === 'chats' ? conversation.data : undefined}
                onClose={() => {
                  setSelected(null);
                  heading.current?.focus();
                }}
              />
            )}
          </div>
          <p className="canvas-provenance">
            Linhas mostram tarefas, dependências e resultados registrados. Selecione um card para
            inspecionar.
          </p>
        </>
      )}
    </div>
  );
}
