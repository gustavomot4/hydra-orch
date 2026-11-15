import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AgentCanvas } from '@/feature/canvas/AgentCanvas';
import { AgentWorkspacePage } from '@/feature/canvas/AgentWorkspacePage';
import { graphFromConversation, graphFromRun, parseAgentLog } from '@/feature/canvas/canvasModel';
import { RunDetailSnapshot } from '@/feature/chat/chatTypes';
import { ConversationSnapshot } from '@/feature/chat/conversationTypes';
import { useLayoutStore } from '@/store/layoutStore';

const client = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('@/hook/useControlPlaneClient', () => ({ useControlPlaneClient: () => client }));
const run = {
  id: 'fixture-run',
  run_id: 'fixture-run',
  project_id: 'p1',
  objective: 'Criar cadastro',
  mode: 'swarm',
  status: 'running',
  tasks: [
    {
      id: 'interface',
      task_id: 'interface',
      status: 'accepted',
      dependencies: [],
      spec: { objective: 'Construir interface', assigned_executor: 'claude' },
      current_attempt: {
        attempt_id: 'att-interface',
        ordinal: 1,
        executor_id: 'claude',
        model: 'dev-rapido',
        process_status: 'exited',
        result: {
          summary: 'Interface concluída',
          changed_files: ['src/form.tsx'],
          checks: [{ check_id: 'typecheck', exit_code: 0 }],
          review: {
            actor: 'agent:codex',
            decision: 'accepted',
            reason: 'Verificações e diff revisados.',
          },
        },
      },
    },
    {
      id: 'api',
      task_id: 'api',
      status: 'running',
      dependencies: ['interface'],
      spec: { objective: 'Construir API', assigned_executor: 'codex' },
      current_attempt: {
        attempt_id: 'att-api',
        ordinal: 1,
        executor_id: 'codex',
        model: 'dev-agent',
        process_status: 'running',
      },
    },
  ],
} as unknown as RunDetailSnapshot;

function mount(element: React.ReactNode, entry = '/agentes?execucao=fixture-run') {
  const query = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={query}>{element}</QueryClientProvider>
    </MemoryRouter>,
  );
}
afterEach(() => {
  client.request.mockReset();
  useLayoutStore.getState().resetLayout();
});

describe('agent workspace uses persisted evidence', () => {
  it('builds only recorded task dependencies, results and review decisions', () => {
    const graph = graphFromRun(run);
    expect(graph.nodes.map((n) => n.id)).toEqual(['coordinator', 'interface', 'api', 'review']);
    expect(graph.edges).toContainEqual({
      id: 'interface-api',
      source: 'interface',
      target: 'api',
      label: 'Depende de',
    });
    expect(graph.edges.some((e) => e.id === 'result-api')).toBe(false);
    expect(graph.nodes.find((n) => n.id === 'review')?.messages[0].author).toBe('agent:codex');
    const withoutReview = structuredClone(run);
    delete withoutReview.tasks[0].current_attempt!.result!.review;
    expect(graphFromRun(withoutReview).nodes.some((n) => n.role === 'review')).toBe(false);
  });

  it('represents a single chat without inventing workers or cross-agent messages', () => {
    const graph = graphFromConversation({
      id: 'c1',
      executor: 'claude',
      turns: [
        {
          id: 't1',
          content: 'Explique o projeto',
          response: 'Resposta real',
          state: 'completed',
          ordinal: 1,
        },
      ],
      tools: [],
    } as unknown as ConversationSnapshot);
    expect(graph.nodes).toHaveLength(1);
    expect(graph.edges).toEqual([]);
    expect(graph.nodes[0].messages).toEqual([
      { author: 'Você', text: 'Explique o projeto' },
      { author: 'Claude Code', text: 'Resposta real' },
    ]);
  });

  it('shows observed CLI children under their parent and excludes agents from older turns', () => {
    const chat = {
      id: 'c1',
      executor: 'codex',
      access_mode: 'read-only',
      tools: [],
      turns: [
        { id: 'old', content: 'Antes', response: 'Feito', state: 'completed', ordinal: 1 },
        { id: 'current', content: 'Agora', response: '', state: 'running', ordinal: 2 },
      ],
      agents: [
        {
          id: 'old-child',
          parent_id: 'root',
          turn_id: 'old',
          title: 'Trabalho antigo',
          state: 'completed',
          executor: 'codex',
          model: 'a',
          summary: 'Feito',
          source: 'cli',
        },
        {
          id: 'child',
          parent_id: 'root',
          turn_id: 'current',
          title: 'Revisar API',
          state: 'running',
          executor: 'codex',
          model: 'a',
          summary: 'Lendo',
          source: 'cli',
        },
        {
          id: 'nested',
          parent_id: 'child',
          turn_id: 'current',
          title: 'Conferir testes',
          state: 'completed',
          executor: 'codex',
          model: 'a',
          summary: 'Pronto',
          source: 'cli',
        },
      ],
    } as unknown as ConversationSnapshot;
    const graph = graphFromConversation(chat);
    expect(graph.nodes.map((n) => n.id)).toEqual(['coordinator', 'cli:child', 'cli:nested']);
    expect(graph.edges).toContainEqual(
      expect.objectContaining({ source: 'cli:child', target: 'cli:nested' }),
    );
    expect(graph.nodes.find((n) => n.id === 'cli:nested')?.state).toBe('completed');
  });

  it('parses actual CLI messages and keeps command output out of the chat', () => {
    const log = [
      { type: 'item.completed', item: { type: 'agent_message', text: 'Mensagem real' } },
      {
        type: 'item.completed',
        item: { type: 'command_execution', aggregated_output: 'not an agent reply' },
      },
      {
        type: 'assistant',
        message: { content: [{ type: 'text', text: '<script>texto</script>' }] },
      },
      { type: 'error', message: 'Falha real' },
    ]
      .map((e) => JSON.stringify(e))
      .join('\n');
    expect(parseAgentLog(log).map((m) => m.text)).toEqual([
      'Mensagem real',
      '<script>texto</script>',
      'Falha real',
    ]);
  });

  it('supports zoom and moving cards by keyboard, preserving position across status updates', async () => {
    const graph = graphFromRun(run),
      onSelect = vi.fn();
    const { rerender } = render(
      <AgentCanvas graph={graph} workId="fixture" selected={null} onSelect={onSelect} />,
    );
    const node = screen.getByTestId('agent-node-api'),
      before = node.style.left;
    fireEvent.keyDown(screen.getByRole('button', { name: 'Mover Construir API. Use as setas.' }), {
      key: 'ArrowRight',
    });
    expect(node.style.left).not.toBe(before);
    await waitFor(() => expect(localStorage.getItem('hydra:canvas:fixture')).not.toBeNull());
    const moved = node.style.left;
    rerender(
      <AgentCanvas
        graph={graphFromRun({ ...run, status: 'succeeded' })}
        workId="fixture"
        selected={null}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByTestId('agent-node-api').style.left).toBe(moved);
    const viewport = screen.getByTestId('canvas-viewport'),
      scale = Number(viewport.getAttribute('data-scale'));
    fireEvent.click(screen.getByRole('button', { name: 'Aumentar zoom' }));
    expect(Number(viewport.getAttribute('data-scale'))).toBeGreaterThan(scale);
    fireEvent.click(within(node).getByRole('button', { pressed: false }));
    expect(onSelect).toHaveBeenCalledWith('api');
  });

  it('opens recorded worker output and checks without creating a directed worker send', async () => {
    const user = userEvent.setup();
    client.request.mockImplementation(async (path: string) => {
      if (path.includes('/artifacts/art-log/content'))
        return {
          content: JSON.stringify({
            type: 'item.completed',
            item: { type: 'agent_message', text: 'Saída real do agente' },
          }),
        };
      if (path.endsWith('/artifacts'))
        return [
          {
            artifact_id: 'art-log',
            attempt_id: 'att-interface',
            relative_path: '.orchestrator/stdout.log',
          },
        ];
      if (path.startsWith('/v1/control-plane/runs?')) return { items: [run], total: 1 };
      if (path.endsWith('/fixture-run')) return run;
      throw Error(path);
    });
    mount(<AgentWorkspacePage />);
    const node = await screen.findByTestId('agent-node-interface');
    await user.click(within(node).getByRole('button', { pressed: false }));
    await screen.findByText('Saída real do agente');
    const inspector = screen.getByTestId('agent-inspector');
    expect(within(inspector).queryByRole('textbox')).not.toBeInTheDocument();
    await user.click(within(inspector).getByRole('button', { name: 'Atividade' }));
    expect(within(inspector).getByText('typecheck')).toBeInTheDocument();
    expect(within(inspector).getByText('✓ Passou')).toBeInTheDocument();
    await user.click(within(inspector).getByRole('button', { name: 'Alterações' }));
    expect(within(inspector).getByText('src/form.tsx')).toBeInTheDocument();
    expect(
      client.request.mock.calls.every(
        ([, options]) => !options?.method || options.method === 'GET',
      ),
    ).toBe(true);
  });

  it('provides an actionable empty state and a recoverable read error', async () => {
    client.request.mockResolvedValue({ items: [], total: 0 });
    const mounted = mount(<AgentWorkspacePage />, '/agentes');
    expect(
      await screen.findByRole('heading', { name: 'Uma mesa para seus agentes' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Iniciar uma conversa' })).toHaveAttribute('href', '/');
    mounted.unmount();
    client.request.mockRejectedValue(new Error('offline'));
    mount(<AgentWorkspacePage />, '/agentes');
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeEnabled();
  });
});
