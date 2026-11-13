import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { createHydraQueryClient } from '@/hook/queryClient';
import { PaneLayout } from '@/component/PaneLayout';
import { ConfigPerfilPage } from '@/page/ConfigPerfilPage';
import { NovoChatPage } from '@/page/NovoChatPage';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';

function setupFetchStub() {
  const preferences: Array<Record<string, unknown>> = [
    {
      preference_id: 'pref-1',
      scope_type: 'user',
      scope_id: 'operator',
      key: 'ui.density',
      value_json: '"comfortable"',
      source: 'explicit',
      version: 1,
      created_at: '2026-11-13T00:00:00Z',
      updated_at: '2026-11-13T00:00:00Z',
    },
  ];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';

    if (url.endsWith('/v1/control-plane/bootstrap')) {
      return new Response(
        JSON.stringify({
          api_version: 'v1',
          product: 'hydra-orch',
          ui: {
            enabled: true,
            host: '127.0.0.1',
            port: 8000,
            api_base_path: '/v1/control-plane',
            features: { projects: true, runs: true, worktrees: true, diffs: true, quota: true },
          },
          integrations: {
            omniroute: { enabled: false, connection_mode: 'disabled', configured: false },
            ssh_gpu: { enabled: false },
          },
          capabilities: {
            schema_version: '1.0',
            default_host: 'local',
            platform: 'Windows',
            integrations: {
              omniroute_enabled: false,
              omniroute_connection_mode: 'disabled',
              ssh_gpu_enabled: false,
              visual_interface_enabled: true,
            },
            hosts: {
              local: {
                host_id: 'local',
                transport_type: 'local',
                platform: 'Windows',
                certified: true,
                capabilities: {
                  pty: {
                    status: 'degraded',
                    supported: true,
                    certified: false,
                    backend_kind: 'pipe_interactive_bridge',
                    reason: 'windows_conpty_uncertified_using_pipe_bridge',
                  },
                  attachments: { status: 'available', supported: true, certified: true },
                  quickopen: { status: 'available', supported: true, certified: true },
                  preview: { status: 'available', supported: true, certified: true },
                  scheduler: { status: 'available', supported: true, certified: true },
                  dictation_stt: {
                    status: 'available',
                    supported: true,
                    certified: false,
                    available_modes: ['browser_optional_text_draft'],
                    duplex_voice_enabled: false,
                  },
                  mobile_emulator: {
                    status: 'unavailable',
                    supported: false,
                    certified: false,
                    reason: 'uncertified_parking_lot_bridge',
                  },
                  computer_use: {
                    status: 'unavailable',
                    supported: false,
                    certified: false,
                    reason: 'uncertified_parking_lot_bridge',
                  },
                },
              },
            },
          },
          implemented_read_models: {},
        }),
        { status: 200 },
      );
    }

    if (url.endsWith('/v1/control-plane/capabilities')) {
      return new Response(
        JSON.stringify({
          known_capabilities: [],
          executor_capabilities: [],
          certification_checks: [],
          drivers: [],
          agents: [],
          host_capabilities: {
            schema_version: '1.0',
            default_host: 'local',
            platform: 'Windows',
            integrations: {
              omniroute_enabled: false,
              omniroute_connection_mode: 'disabled',
              ssh_gpu_enabled: false,
              visual_interface_enabled: true,
            },
            hosts: {
              local: {
                host_id: 'local',
                transport_type: 'local',
                platform: 'Windows',
                certified: true,
                capabilities: {
                  pty: {
                    status: 'degraded',
                    supported: true,
                    certified: false,
                    backend_kind: 'pipe_interactive_bridge',
                    reason: 'windows_conpty_uncertified_using_pipe_bridge',
                  },
                  attachments: { status: 'available', supported: true, certified: true },
                  quickopen: { status: 'available', supported: true, certified: true },
                  preview: { status: 'available', supported: true, certified: true },
                  scheduler: { status: 'available', supported: true, certified: true },
                  dictation_stt: {
                    status: 'available',
                    supported: true,
                    certified: false,
                    available_modes: ['browser_optional_text_draft'],
                    duplex_voice_enabled: false,
                  },
                  mobile_emulator: {
                    status: 'unavailable',
                    supported: false,
                    certified: false,
                    reason: 'uncertified_parking_lot_bridge',
                  },
                  computer_use: {
                    status: 'unavailable',
                    supported: false,
                    certified: false,
                    reason: 'uncertified_parking_lot_bridge',
                  },
                },
              },
            },
          },
        }),
        { status: 200 },
      );
    }

    if (url.endsWith('/v1/control-plane/projects')) {
      return new Response(
        JSON.stringify([
          {
            id: 'proj-1',
            canonical_root: '/repo/hydra',
            name: 'hydra-orch',
            base_branch: 'main',
            created_at: '2026-11-13T00:00:00Z',
            updated_at: '2026-11-13T00:00:00Z',
          },
        ]),
        { status: 200 },
      );
    }

    if (url.endsWith('/v1/control-plane/executors')) {
      return new Response(
        JSON.stringify([
          {
            id: 'codex',
            name: 'Codex CLI',
            driver: 'codex',
            driver_type: 'codex',
            executable: '/usr/bin/codex',
            executable_found: true,
            is_certified: true,
            status: 'ready',
            capabilities: ['workspace_execution'],
            platform: 'Windows',
          },
        ]),
        { status: 200 },
      );
    }

    if (url.includes('/v1/control-plane/omniroute/inventory')) {
      return new Response(
        JSON.stringify({
          connection_mode: 'disabled',
          direct_mode_supported: true,
          available: false,
          models: [],
          accounts: [],
          quota: { status: 'unknown' },
          next_account_overrides: {},
        }),
        { status: 200 },
      );
    }

    if (url.includes('/v1/control-plane/preferences') && method === 'GET') {
      return new Response(JSON.stringify(preferences), { status: 200 });
    }

    if (url.endsWith('/v1/control-plane/preferences') && method === 'PUT') {
      const body = JSON.parse(String(init?.body ?? '{}')) as { key: string; value: unknown };
      const updated = {
        preference_id: `pref-${body.key}`,
        scope_type: 'user',
        scope_id: 'operator',
        key: body.key,
        value_json: JSON.stringify(body.value),
        source: 'explicit',
        version: 2,
        created_at: '2026-11-13T00:00:00Z',
        updated_at: '2026-11-13T00:00:00Z',
      };
      return new Response(JSON.stringify(updated), { status: 200 });
    }

    if (url.endsWith('/v1/control-plane/tokens') && method === 'GET') {
      return new Response(
        JSON.stringify([
          {
            id: 'tok-abc-123',
            token_hash: 'pbkdf2_sha256$should-never-appear-in-dom',
            token: 'hydra_tok_should_never_render',
            principal_id: 'operator',
            scopes: ['read', 'write'],
            expires_at: '2026-12-01T00:00:00Z',
            revoked_at: null,
          },
        ]),
        { status: 200 },
      );
    }

    if (url.includes('/v1/control-plane/runs') && method === 'GET') {
      return new Response(
        JSON.stringify({ items: [], total: 0, page: 1, size: 50, pages: 1 }),
        { status: 200 },
      );
    }

    return new Response(JSON.stringify([]), { status: 200 });
  });

  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('PaneLayout, NovoChatPage (18:8) and ConfigPerfilPage (18:454)', () => {
  it('toggles split mode and persists layout tabs across store rehydration', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().authenticate('valid-token', 'operator');
    setupFetchStub();

    const qc = createHydraQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <PaneLayout
            renderTabContent={(tab) => (
              <div data-testid={`pane-content-${tab?.id ?? 'empty'}`}>
                {tab?.kind === 'new_chat' ? <NovoChatPage /> : tab?.title}
              </div>
            )}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const layout = screen.getByTestId('pane-layout');
    expect(layout).toHaveAttribute('data-split-mode', 'single');
    expect(screen.queryByTestId('pane-secondary')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Dividir painéis' }));
    expect(layout).toHaveAttribute('data-split-mode', 'split');
    expect(screen.getByTestId('pane-secondary')).toBeInTheDocument();

    const saved = window.localStorage.getItem('hydra_layout_state_v1');
    expect(saved).not.toBeNull();
    expect(JSON.parse(saved!)).toMatchObject({ splitMode: 'split', sidebarWidth: 280 });
  });

  it('populates NovoChatPage (18:8) draft from quick action chips and exposes extensible composer slot', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().authenticate('valid-token', 'operator');
    setupFetchStub();

    const qc = createHydraQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <NovoChatPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('novo-chat-page')).toBeInTheDocument();
    expect(screen.getByTestId('novo-chat-composer-slot')).toBeInTheDocument();

    const chip = screen.getByRole('button', { name: /Revisar alterações e gerar PR/i });
    await user.click(chip);

    const textarea = screen.getByLabelText('Descreva a tarefa para o coordenador');
    expect(textarea).toHaveValue(
      'Analise o diff atual do workspace, execute os checks e prepare o pacote de PR.',
    );
  });

  it('renders ConfigPerfilPage (18:454), updates preferences, displays honest capabilities and never leaks token hashes', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().authenticate('valid-token', 'operator');
    const fetchMock = setupFetchStub();

    const qc = createHydraQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ConfigPerfilPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('token-meta-tok-abc-123')).toBeInTheDocument();
    // Never leak token_hash or raw secret in DOM
    expect(container.textContent).not.toContain('pbkdf2_sha256');
    expect(container.textContent).not.toContain('hydra_tok_should_never_render');

    // Honest HostCapabilities display
    const hostCap = await screen.findByTestId('host-capabilities-local');
    expect(hostCap).toHaveTextContent('pipe_interactive_bridge');
    expect(hostCap).toHaveTextContent('uncertified_parking_lot_bridge');

    // Update density + reduced motion and persist via PUT /v1/control-plane/preferences
    await user.selectOptions(screen.getByLabelText('Densidade da interface'), 'compact');
    await user.click(screen.getByLabelText('Reduzir movimento'));
    await user.click(screen.getByRole('button', { name: 'Salvar preferências' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/v1/control-plane/preferences',
        expect.objectContaining({ method: 'PUT' }),
      );
    });
  });
});
