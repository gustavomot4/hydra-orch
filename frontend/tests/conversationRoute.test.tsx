import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { PromptComposer } from '@/feature/composer';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConversationRoutePicker } from '@/feature/chat/ConversationRoutePicker';
import { ConversationPage } from '@/feature/chat/ConversationPage';
import { defaultRoute } from '@/feature/chat/conversationTypes';

const client = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('@/hook/useControlPlaneClient', () => ({ useControlPlaneClient: () => client }));

function mount(element: React.ReactNode) {
  const query = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={query}>{element}</QueryClientProvider>
    </MemoryRouter>,
  );
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  client.request.mockReset();
});

describe('conversation route choices', () => {
  it('shows combos before fetching models and distinguishes loading from an empty search', async () => {
    const user = userEvent.setup();
    const selection = { ...defaultRoute(), connection_mode: 'omniroute' as const };
    let releaseCatalog!: (value: unknown) => void;
    client.request.mockImplementation((url: string) => {
      if (url.includes('include_models=false'))
        return new Promise((resolve) => {
          releaseCatalog = resolve;
        });
      return Promise.resolve({
        status: 'connected',
        combos: [],
        models: [{ id: 'last-model', name: 'last-model', target_kind: 'model' }],
        direct_models: [],
      });
    });
    mount(<ConversationRoutePicker value={selection} onChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /Modelo ou combo/ }));
    expect(screen.getByText('Carregando opções…')).toBeInTheDocument();
    expect(screen.queryByText(/Nenhum resultado/)).not.toBeInTheDocument();
    releaseCatalog({
      status: 'connected',
      combos: [{ id: 'a', name: 'Meu combo', target_kind: 'combo' }],
      models: [],
      direct_models: [],
    });
    expect(await screen.findByRole('button', { name: /Meu combo/ })).toBeVisible();
    expect(client.request.mock.calls.some(([url]) => url.includes('include_models=true'))).toBe(
      false,
    );
    await user.click(screen.getByRole('button', { name: 'Modelos' }));
    expect(await screen.findByRole('button', { name: /last-model/ })).toBeVisible();
    expect(client.request.mock.calls.some(([url]) => url.includes('include_models=true'))).toBe(
      true,
    );
    expect(client.request.mock.calls.some(([url]) => url.endsWith('/verify'))).toBe(false);
  });
  it('keeps a prompt typed before the initial project arrives and separates later project drafts', async () => {
    const user = userEvent.setup();
    function InitialProject() {
      const [project, setProject] = useState('');
      const [draft, setDraft] = useState('');
      return (
        <>
          <button onClick={() => setProject('initial')}>Projeto carregou</button>
          <button onClick={() => setProject('other')}>Outra pasta</button>
          <PromptComposer
            sessionKey={`first-project-${project || 'default'}`}
            selectedProjectId={project}
            draft={draft}
            onDraftChange={setDraft}
            textareaAriaLabel="Pedido antes da pasta"
          />
        </>
      );
    }
    render(<InitialProject />);
    await user.type(screen.getByLabelText('Pedido antes da pasta'), 'Preserve meu pedido');
    await user.click(screen.getByRole('button', { name: 'Projeto carregou' }));
    expect(screen.getByLabelText('Pedido antes da pasta')).toHaveValue('Preserve meu pedido');
    await user.click(screen.getByRole('button', { name: 'Outra pasta' }));
    expect(screen.getByLabelText('Pedido antes da pasta')).toHaveValue('');
  });
  it('releases the composer after durable acceptance even if the background snapshot is delayed', async () => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('stream offline')));
    let accepted = false;
    client.request.mockImplementation(async (_path: string, options?: { method?: string }) => {
      if (options?.method === 'POST') {
        accepted = true;
        return { turn_id: 'accepted-turn', seq: 2 };
      }
      if (accepted) return new Promise(() => {});
      return {
        id: 'conversation-ack',
        title: 'Envio durável',
        project_id: 'p',
        executor: 'codex',
        access_mode: 'read-only',
        last_seq: 0,
        tools: [],
        turns: [],
      };
    });
    mount(<ConversationPage conversationId="conversation-ack" />);
    await user.type(await screen.findByLabelText('Sua mensagem'), 'Pedido aceito');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    await screen.findByText('Pedido aceito', { exact: true });
    expect(screen.getByLabelText('Sua mensagem')).toBeEnabled();
    expect(screen.getByLabelText('Sua mensagem')).toHaveValue('');
    expect(screen.getByText('Aguardando envio')).toBeInTheDocument();
  });
  it('searches a large catalog and requires actual certification before marking the selected combo ready', async () => {
    const user = userEvent.setup();
    let certified = false;
    const onReady = vi.fn();
    const selection = { ...defaultRoute(), connection_mode: 'omniroute' as const };
    client.request.mockImplementation(async (path: string) => {
      if (path.endsWith('/verify')) {
        certified = true;
        return { compatibility: 'verified' };
      }
      if (path.endsWith('/describe'))
        return { compatibility: certified ? 'verified' : 'unverified' };
      return {
        status: 'connected',
        combos: [
          {
            id: 'combo-a',
            name: 'Programação grande',
            target_kind: 'combo',
            compatibility: certified ? 'verified' : 'unverified',
          },
        ],
        models: Array.from({ length: 80 }, (_, i) => ({
          id: `model-${i}`,
          name: `model-${i}`,
          target_kind: 'model',
        })),
        direct_models: [],
      };
    });
    const { rerender } = mount(
      <ConversationRoutePicker value={selection} onChange={vi.fn()} onReadyChange={onReady} />,
    );
    await screen.findByText('Conectado ao OmniRoute');
    await user.click(screen.getByRole('button', { name: /Modelo ou combo/ }));
    expect(await screen.findByText('Mostrando 1–1 de 1')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Buscar pelo nome'), 'programacao');
    const choose = screen.getByRole('button', { name: /Programação grande/ });
    expect(choose).toBeEnabled();
    cleanup();
    mount(
      <ConversationRoutePicker
        value={{ ...selection, target_kind: 'combo', target_ref: 'Programação grande' }}
        onChange={vi.fn()}
        onReadyChange={onReady}
      />,
    );
    const test = await screen.findByRole('button', { name: 'Testar combinação' });
    await user.click(test);
    await screen.findByText(/Combinação verificada/);
    await waitFor(() => expect(onReady).toHaveBeenLastCalledWith(true));
    expect(client.request.mock.calls.filter(([p]) => p.endsWith('/verify'))).toHaveLength(1);
    void rerender;
  });

  it('preserves the same chat and old turn attribution when changing its next model', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('test stream offline')));
    const first = { ...defaultRoute(), target_ref: 'model-a' };
    const state = {
      id: 'conversation-route-test',
      title: 'Mesmo trabalho',
      project_id: 'p1',
      executor: 'codex',
      access_mode: 'read-only',
      route: first,
      route_revision: 0,
      last_seq: 3,
      tools: [],
      execution_mode: 'single',
      auto_route: false,
      turns: [
        {
          id: 't1',
          ordinal: 1,
          content: 'Decisão: usar verde',
          response: 'Decisão registrada.',
          state: 'completed',
          error: null,
          diff: '',
          attachments: [],
          route: first,
          identity: { model: 'model-a', company: null, source: 'cli' },
        },
      ],
    };
    const changes: unknown[] = [];
    client.request.mockImplementation(
      async (path: string, options?: { method?: string; body?: { route: typeof first } }) => {
        if (options?.method === 'PATCH') {
          changes.push(options.body);
          state.route = options.body!.route;
          state.route_revision = 1;
          return { route_revision: 1 };
        }
        if (path.includes('/combos'))
          return {
            status: 'not_requested',
            combos: [],
            models: [],
            direct_models: [
              { id: 'model-a', name: 'Modelo A' },
              { id: 'model-b', name: 'Modelo B' },
            ],
          };
        return structuredClone(state);
      },
    );
    mount(<ConversationPage conversationId={state.id} />);
    await screen.findByText('Decisão registrada.');
    await user.click(screen.getByRole('button', { name: /Trocar modelo ou combo/ }));
    await user.click(await screen.findByRole('button', { name: /^Modelo:/ }));
    await user.click(screen.getByRole('button', { name: 'Modelo B' }));
    await user.click(screen.getByRole('radio', { name: 'Coordenar tarefas com agentes' }));
    expect(screen.getByRole('checkbox', { name: 'Escolher modelo automaticamente' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Usar nos próximos envios' }));
    await waitFor(() => expect(changes).toHaveLength(1));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Cancelar troca' })).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Decisão: usar verde')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'model-a' })).toBeInTheDocument();
    expect(changes[0]).toMatchObject({
      expected_revision: 0,
      route: { target_ref: 'model-b' },
      execution_mode: 'swarm',
      auto_route: true,
    });
    expect(client.request.mock.calls.some(([p]) => p.endsWith('/conversations'))).toBe(false);
  });
});
