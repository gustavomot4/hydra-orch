import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowUpRight, MessageSquare, X } from 'lucide-react';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ConversationSnapshot } from '@/feature/chat/conversationTypes';
import { CanvasNode, parseAgentLog, statusMeta } from './canvasModel';
import { CheckEvidence } from '@/feature/chat/CoordinationPanel';

export function AgentInspector({
  node,
  chat,
  onClose,
}: {
  node: CanvasNode;
  chat?: ConversationSnapshot;
  onClose: () => void;
}) {
  const client = useControlPlaneClient();
  const [tab, setTab] = useState('Conversa');
  const title = useRef<HTMLHeadingElement>(null);
  const previousNode = useRef<string | null>(null);
  useEffect(() => {
    // Initial coordination details must not scroll past the work list on mobile.
    // Selecting another card still brings its details into view.
    title.current?.focus({
      preventScroll:
        previousNode.current === node.id ||
        (previousNode.current === null && node.id === 'coordinator'),
    });
    previousNode.current = node.id;
    setTab(node.role === 'validation' ? 'Verificações' : 'Conversa');
  }, [node.id, node.role]);
  const artifactQuery = useQuery({
    queryKey: ['canvas-artifacts', node.runId],
    queryFn: ({ signal }) =>
      client.request<{ artifact_id: string; attempt_id: string | null; relative_path: string }[]>(
        `/v1/control-plane/runs/${encodeURIComponent(node.runId!)}/artifacts`,
        { signal },
      ),
    enabled: Boolean(node.task?.current_attempt?.result && node.runId),
    staleTime: 10000,
    retry: false,
  });
  const stdout = artifactQuery.data?.find(
    (a) =>
      a.attempt_id === node.task?.current_attempt?.attempt_id &&
      a.relative_path.endsWith('/stdout.log'),
  );
  const log = useQuery({
    queryKey: ['canvas-log', node.runId, stdout?.artifact_id],
    queryFn: ({ signal }) =>
      client.request<{ content: string | null; status: string; reason?: string }>(
        `/v1/control-plane/runs/${encodeURIComponent(node.runId!)}/artifacts/${encodeURIComponent(stdout!.artifact_id)}/content?max_bytes=262144`,
        { signal },
      ),
    enabled: Boolean(stdout),
    staleTime: 30000,
    retry: false,
  });
  const agentMessages = log.data?.content ? parseAgentLog(log.data.content) : [];
  const messages = [...node.messages, ...agentMessages];
  const state = statusMeta(node.state);
  const tools = node.role === 'coordinator' ? (chat?.tools ?? []) : [];
  const diff = node.role === 'coordinator' ? chat?.turns.at(-1)?.diff : undefined;
  return (
    <aside
      className="agent-inspector"
      aria-label={node.role === 'validation' ? 'Detalhes da verificação' : 'Detalhes do agente'}
      data-testid="agent-inspector"
    >
      <header>
        <div>
          <span className="canvas-eyebrow">
            {node.role === 'validation'
              ? 'Verificação local'
              : node.role === 'worker'
                ? 'Agente selecionado'
                : node.role === 'review'
                  ? 'Decisões registradas'
                  : 'Conversa e coordenação'}
          </span>
          <h2 ref={title} tabIndex={-1}>
            {node.title}
          </h2>
          <p>
            {node.executor} · {node.model}
          </p>
        </div>
        <button className="canvas-icon-button" onClick={onClose} aria-label="Fechar detalhes">
          <X size={20} />
        </button>
      </header>
      <div className={`canvas-status tone-${state.tone}`}>
        <span aria-hidden="true">{state.symbol}</span>
        {state.label}
      </div>
      <div className="inspector-tabs" aria-label="Conteúdo dos detalhes">
        {(node.role === 'validation'
          ? ['Verificações', 'Atividade']
          : ['Conversa', 'Atividade', 'Alterações']
        ).map((label) => (
          <button key={label} aria-pressed={tab === label} onClick={() => setTab(label)}>
            {label}
          </button>
        ))}
      </div>
      <div className="inspector-body">
        {tab === 'Verificações' && (
          <>
            <p className="canvas-note">Resultados executados pelo Hydra na cópia isolada.</p>
            <CheckEvidence checks={node.checkEvidence ?? []} />
          </>
        )}
        {tab === 'Conversa' && (
          <>
            {messages.map((message, index) => (
              <section
                key={index}
                className={`canvas-message ${message.author === 'Você' ? 'from-user' : ''}`}
              >
                <h3>{message.author}</h3>
                <p>{message.text}</p>
              </section>
            ))}
            {node.role === 'worker' && !agentMessages.length && (
              <p className="canvas-note">
                {log.isError
                  ? 'Não foi possível carregar a saída do agente.'
                  : node.task?.current_attempt?.result
                    ? 'A saída deste agente não está disponível como conversa.'
                    : 'A saída do agente ficará disponível quando a tentativa terminar.'}
              </p>
            )}
            {(artifactQuery.isLoading || (stdout && log.isLoading)) && (
              <p role="status">Carregando saída registrada…</p>
            )}
            {log.data && !log.data.content && (
              <p className="canvas-note">
                {log.data.reason || 'Consulte o arquivo completo na execução.'}
              </p>
            )}
            {log.isError && (
              <button className="canvas-button" onClick={() => void log.refetch()}>
                Tentar carregar saída
              </button>
            )}
            {artifactQuery.isError && (
              <p role="alert">
                Não foi possível consultar os registros.{' '}
                <button className="canvas-button" onClick={() => void artifactQuery.refetch()}>
                  Tentar novamente
                </button>
              </p>
            )}
          </>
        )}
        {tab === 'Atividade' && (
          <>
            <p className="canvas-note">{node.action}</p>
            {node.task?.current_attempt && (
              <dl className="canvas-facts">
                <dt>Tentativa</dt>
                <dd>{node.task.current_attempt.ordinal}</dd>
                <dt>Início</dt>
                <dd>
                  {node.task.current_attempt.started_at
                    ? new Date(node.task.current_attempt.started_at).toLocaleString('pt-BR')
                    : 'Aguardando'}
                </dd>
                <dt>Estado do processo</dt>
                <dd>{node.task.current_attempt.process_status}</dd>
              </dl>
            )}
            {tools.map((tool) => (
              <details key={tool.seq}>
                <summary>{tool.payload.tool || 'Ferramenta'}</summary>
                <pre>{tool.payload.detail}</pre>
              </details>
            ))}
            <h3>Verificações</h3>
            {node.checkEvidence ? (
              <CheckEvidence checks={node.checkEvidence} />
            ) : !node.checks.length ? (
              <p className="canvas-note">Nenhuma verificação executada registrada.</p>
            ) : (
              <ul>
                {node.checks.map((check) => (
                  <li key={check.name}>
                    <span className={`canvas-status tone-${statusMeta(check.state).tone}`}>
                      {check.state === 'passed' ? '✓ Passou' : '! Falhou'}
                    </span>{' '}
                    {check.name}
                  </li>
                ))}
              </ul>
            )}
            {node.runId && (
              <Link className="canvas-button" to={`/chat/${encodeURIComponent(node.runId)}`}>
                Ver execução completa
                <ArrowUpRight size={16} />
              </Link>
            )}
          </>
        )}
        {tab === 'Alterações' && (
          <>
            {!node.paths.length && Boolean(node.plannedPaths?.length) && (
              <>
                <p className="canvas-note">
                  Arquivos previstos no plano; nenhuma alteração registrada.
                </p>
                <ul className="canvas-paths">
                  {node.plannedPaths!.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
              </>
            )}
            {node.paths.length > 0 ? (
              <ul className="canvas-paths">
                {node.paths.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            ) : !node.plannedPaths?.length ? (
              <p className="canvas-note">Nenhum arquivo alterado registrado para este card.</p>
            ) : null}
            {diff && <pre>{diff}</pre>}
            {node.runId && (
              <Link className="canvas-button" to={`/chat/${encodeURIComponent(node.runId)}`}>
                Inspecionar resultado
                <ArrowUpRight size={16} />
              </Link>
            )}
          </>
        )}
      </div>
      <footer>
        <p>
          {node.role === 'validation'
            ? 'Confira a saída de cada verificação. Continue o pedido pela conversa.'
            : node.conversationId
              ? 'Continue o pedido pela conversa. Mensagens para um worker em execução ainda não estão disponíveis.'
              : 'Consulte os registros desta execução. Ela não está vinculada a uma conversa para continuação.'}
        </p>
        <Link
          className="canvas-button canvas-primary"
          to={`/chat/${encodeURIComponent(node.conversationId || node.runId || '')}`}
        >
          <MessageSquare size={16} />
          {node.conversationId ? 'Abrir conversa' : 'Abrir execução'}
        </Link>
      </footer>
    </aside>
  );
}
