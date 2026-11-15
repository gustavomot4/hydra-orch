import { RunDetailSnapshot, BackendTask } from '@/feature/chat/chatTypes';
import { ConversationSnapshot, ConversationTurn } from '@/feature/chat/conversationTypes';

export interface CanvasMessage {
  author: string;
  text: string;
}
export interface CanvasNode {
  id: string;
  title: string;
  role: 'coordinator' | 'worker' | 'review';
  executor: string;
  model: string;
  state: string;
  action: string;
  messages: CanvasMessage[];
  paths: string[];
  checks: { name: string; state: string }[];
  task?: BackendTask;
  runId?: string;
  conversationId?: string;
}
export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}
export interface CanvasGraph {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}
export interface Point {
  x: number;
  y: number;
}
export const NODE_WIDTH = 292;
export const NODE_HEIGHT = 202;

export function agentLabel(value: string) {
  return value === 'codex'
    ? 'Codex'
    : ['claude', 'claude-code'].includes(value)
      ? 'Claude Code'
      : value || 'Não informado';
}
export function statusMeta(value: string) {
  if (value === 'planned') return { label: 'Planejado', tone: 'muted', symbol: '◇' };
  if (['completed', 'succeeded', 'accepted', 'passed'].includes(value))
    return { label: 'Concluído', tone: 'success', symbol: '✓' };
  if (['failed', 'rejected', 'timed_out', 'crashed'].includes(value))
    return { label: 'Falhou', tone: 'error', symbol: '!' };
  if (['running', 'starting'].includes(value))
    return { label: 'Trabalhando', tone: 'info', symbol: '▶' };
  if (['cancelled', 'stopped', 'stopping'].includes(value))
    return { label: 'Interrompido', tone: 'muted', symbol: '■' };
  if (['ready_for_review', 'reviewing'].includes(value))
    return { label: 'Em revisão', tone: 'warning', symbol: '◷' };
  if (['unknown', 'unavailable'].includes(value))
    return { label: 'Sem estado informado', tone: 'muted', symbol: '?' };
  return { label: value === 'blocked' ? 'Bloqueado' : 'Aguardando', tone: 'warning', symbol: '◷' };
}

export function layoutNodes(nodes: CanvasNode[]): Record<string, Point> {
  const result: Record<string, Point> = {};
  const workers = nodes.filter((n) => n.role === 'worker');
  const center = 32 + ((Math.min(workers.length || 1, 3) - 1) * 420) / 2;
  nodes
    .filter((n) => n.role === 'coordinator')
    .forEach((n, i) => {
      result[n.id] = { x: center + i * 420, y: 32 };
    });
  workers.forEach((n, i) => {
    result[n.id] = { x: 32 + (i % 3) * 420, y: 310 + Math.floor(i / 3) * 280 };
  });
  nodes
    .filter((n) => n.role === 'review')
    .forEach((n, i) => {
      result[n.id] = { x: center + i * 420, y: 310 + Math.ceil(workers.length / 3) * 280 };
    });
  return result;
}

export function graphFromConversation(
  chat: ConversationSnapshot,
  run?: RunDetailSnapshot,
): CanvasGraph {
  const turn =
    chat.turns.findLast((t) => ['running', 'stopping'].includes(t.state)) ?? chat.turns.at(-1);
  if (!turn) return { nodes: [], edges: [] };
  const route = turn.route ?? chat.route;
  const graph: CanvasGraph = {
    nodes: [
      {
        id: 'coordinator',
        title: turn.execution_mode === 'swarm' ? 'Coordenador' : 'Agente da conversa',
        role: 'coordinator',
        executor: agentLabel(route?.executor ?? chat.executor),
        model: route?.target_ref || 'Padrão do agente',
        state: turn.state,
        action:
          turn.error ||
          (turn.response
            ? lastLine(turn.response)
            : turn.coordination?.phase === 'running'
              ? 'Acompanhando as tarefas'
              : 'Preparando resposta'),
        messages: chat.turns.flatMap((t) => [
          { author: 'Você', text: t.content },
          ...(t.response
            ? [{ author: agentLabel(t.route?.executor ?? chat.executor), text: t.response }]
            : []),
        ]),
        paths: [],
        checks: [],
        conversationId: chat.id,
        runId: turn.coordination?.run_id,
      },
    ],
    edges: [],
  };
  if (run) appendRun(graph, run, chat.id, turn);
  else
    (turn.coordination?.plan?.tasks ?? []).forEach((t) => {
      const progress = turn.coordination?.tasks?.[t.id];
      graph.nodes.push({
        id: t.id,
        title: t.title,
        role: 'worker',
        executor: agentLabel(progress?.route?.executor ?? route?.executor ?? ''),
        model: progress?.route?.target_ref || route?.target_ref || 'Padrão do agente',
        state: progress?.state || 'planned',
        action:
          progress?.review ||
          progress?.reason ||
          (chat.access_mode === 'read-only'
            ? 'Plano em leitura; execução não iniciada'
            : 'Tarefa registrada no plano'),
        messages: [],
        paths: t.paths,
        checks: [],
        conversationId: chat.id,
      });
      graph.edges.push({ id: 'plan-' + t.id, source: 'coordinator', target: t.id, label: 'Plano' });
    });
  const observed = (chat.agents ?? []).filter((a) => a.turn_id === turn.id);
  for (const agent of observed) {
    graph.nodes.push({
      id: 'cli:' + agent.id,
      title: agent.title,
      role: 'worker',
      executor: agentLabel(agent.executor),
      model: agent.model,
      state: agent.state,
      action: agent.summary,
      messages: [{ author: 'Subagente da CLI', text: agent.summary }],
      paths: [],
      checks: [],
      conversationId: chat.id,
    });
    graph.edges.push({
      id: 'cli-edge:' + agent.id,
      source: observed.some((a) => a.id === agent.parent_id)
        ? 'cli:' + agent.parent_id
        : 'coordinator',
      target: 'cli:' + agent.id,
      label: 'Subagente CLI',
    });
  }
  return graph;
}

export function graphFromRun(run: RunDetailSnapshot): CanvasGraph {
  const graph: CanvasGraph = {
    nodes: [
      {
        id: 'coordinator',
        title: 'Coordenação',
        role: 'coordinator',
        executor: 'Hydra',
        model: run.mode,
        state: run.status,
        action: run.objective,
        messages: [{ author: 'Pedido', text: run.objective }],
        paths: [],
        checks: [],
        runId: run.id,
      },
    ],
    edges: [],
  };
  appendRun(graph, run);
  return graph;
}

function appendRun(
  graph: CanvasGraph,
  run: RunDetailSnapshot,
  conversationId?: string,
  turn?: ConversationTurn,
) {
  const ids = new Set(run.tasks.map((t) => t.id));
  const reviews: CanvasMessage[] = [];
  for (const task of run.tasks) {
    const attempt = task.current_attempt;
    const result = attempt?.result;
    const review = (
      result as typeof result & { review?: { actor: string; decision: string; reason: string } }
    )?.review;
    if (review) reviews.push({ author: review.actor, text: review.reason });
    const planTask = turn?.coordination?.plan?.tasks?.find((t) =>
      task.spec.objective.startsWith(t.title),
    );
    const progress = planTask ? turn?.coordination?.tasks?.[planTask.id] : undefined;
    graph.nodes.push({
      id: task.id,
      title: planTask?.title || task.spec.objective.split('\n')[0],
      role: 'worker',
      executor: agentLabel(attempt?.executor_id || task.spec.assigned_executor),
      model: attempt?.model || progress?.route?.target_ref || 'Aguardando destino',
      state: task.status,
      action:
        result?.failures?.[0]?.message ||
        result?.summary ||
        (attempt ? 'Execução registrada' : 'Aguardando início'),
      messages: [
        { author: 'Tarefa', text: task.spec.objective },
        ...(result ? [{ author: 'Resultado', text: result.summary }] : []),
      ],
      paths: result?.changed_files ?? [],
      checks: (result?.checks ?? []).map((c) => ({
        name: c.check_id,
        state: c.exit_code === 0 ? 'passed' : 'failed',
      })),
      task,
      runId: run.id,
      conversationId,
    });
    const dependencies = task.dependencies ?? task.spec.dependencies ?? [];
    if (!dependencies.length)
      graph.edges.push({
        id: 'delegate-' + task.id,
        source: 'coordinator',
        target: task.id,
        label: attempt ? 'Tarefa iniciada' : 'Plano',
      });
    for (const dependency of dependencies)
      if (ids.has(dependency))
        graph.edges.push({
          id: dependency + '-' + task.id,
          source: dependency,
          target: task.id,
          label: 'Depende de',
        });
    if (result)
      graph.edges.push({
        id: 'result-' + task.id,
        source: task.id,
        target: 'coordinator',
        label: 'Resultado',
      });
  }
  // A review card exists only when a review decision is actually persisted.
  if (reviews.length) {
    graph.nodes.push({
      id: 'review',
      title: 'Revisão registrada',
      role: 'review',
      executor: [...new Set(reviews.map((r) => r.author))].join(', '),
      model: 'Decisões registradas',
      state: run.tasks.every((t) => t.status === 'accepted') ? 'accepted' : 'reviewing',
      action: reviews.at(-1)!.text,
      messages: reviews,
      paths: [],
      checks: [],
      runId: run.id,
      conversationId,
    });
    graph.edges.push({
      id: 'review-result',
      source: 'coordinator',
      target: 'review',
      label: 'Revisão',
    });
  }
}

function lastLine(value: string) {
  return value.trim().split('\n').filter(Boolean).at(-1)?.slice(0, 180) || 'Resposta registrada';
}

export function parseAgentLog(text: string): CanvasMessage[] {
  const messages: CanvasMessage[] = [];
  for (const line of text.split('\n')) {
    try {
      const event = JSON.parse(line);
      if (event.type === 'item.completed' && event.item?.type === 'agent_message')
        messages.push({ author: 'Agente', text: String(event.item.text || '') });
      if (event.type === 'assistant')
        for (const block of event.message?.content ?? [])
          if (block.type === 'text') messages.push({ author: 'Agente', text: String(block.text) });
      if (event.type === 'error' || event.type === 'turn.failed')
        messages.push({
          author: 'Erro',
          text: String(event.message || event.error?.message || 'Falha registrada'),
        });
    } catch {
      /* Other CLI output remains available in the original log. */
    }
  }
  return messages;
}
