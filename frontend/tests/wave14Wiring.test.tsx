import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '@/App';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function buildFetchStub() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const rawUrl = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(rawUrl, 'http://localhost');
    const path = url.pathname;

    if (path === '/v1/control-plane/bootstrap') {
      return jsonResponse({
        schema_version: '1.0',
        auth_required: true,
        principal_id: 'op',
        host_capabilities: {
          schema_version: '1.0',
          default_host: 'local',
          platform: 'Windows',
          integrations: {
            omniroute_enabled: true,
            omniroute_connection_mode: 'gateway',
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
                mobile_emulator: { status: 'unavailable', supported: false, certified: false },
                computer_use: { status: 'unavailable', supported: false, certified: false },
              },
            },
          },
        },
        implemented_read_models: {},
      });
    }

    if (path === '/v1/control-plane/capabilities') {
      return jsonResponse({
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
            omniroute_enabled: true,
            omniroute_connection_mode: 'gateway',
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
                },
                mobile_emulator: { status: 'unavailable', supported: false, certified: false },
                computer_use: { status: 'unavailable', supported: false, certified: false },
              },
            },
          },
        },
      });
    }

    if (path === '/v1/control-plane/projects') {
      return jsonResponse([
        {
          id: 'proj-1',
          canonical_root: '/repo/hydra',
          name: 'hydra-orch',
          base_branch: 'main',
          created_at: '2026-11-13T00:00:00Z',
          updated_at: '2026-11-13T00:00:00Z',
        },
      ]);
    }

    if (path === '/v1/control-plane/areas') {
      return jsonResponse([]);
    }

    if (path === '/v1/control-plane/workspaces') {
      return jsonResponse([
        {
          id: 'ws-1',
          project_id: 'proj-1',
          name: 'workspace-principal',
          worktree_path: '/repo/hydra',
          branch: 'main',
          status: 'active',
        },
      ]);
    }

    if (path === '/v1/control-plane/executors') {
      return jsonResponse([
        {
          id: 'codex',
          name: 'Codex CLI',
          driver: 'codex',
          driver_type: 'codex',
          executable: '/usr/bin/codex',
          executable_found: true,
        },
      ]);
    }

    if (path === '/v1/control-plane/runs') {
      return jsonResponse([
        {
          id: 'run-1',
          run_id: 'run-1',
          project_id: 'proj-1',
          workspace_id: 'ws-1',
          objective: 'Validar integração Onda 14',
          prompt: 'Validar integração Onda 14',
          mode: 'relay',
          status: 'review',
          created_at: '2026-11-13T00:00:00Z',
          updated_at: '2026-11-13T00:05:00Z',
        },
      ]);
    }

    if (path === '/v1/control-plane/runs/run-1') {
      return jsonResponse({
        id: 'run-1',
        run_id: 'run-1',
        project_id: 'proj-1',
        workspace_id: 'ws-1',
        objective: 'Validar integração Onda 14',
        prompt: 'Validar integração Onda 14',
        mode: 'relay',
        status: 'review',
        checks: [],
        tasks: [],
        events: [],
        created_at: '2026-11-13T00:00:00Z',
        updated_at: '2026-11-13T00:05:00Z',
      });
    }

    if (path === '/v1/control-plane/runs/run-1/interventions') {
      return jsonResponse([]);
    }

    if (path === '/v1/control-plane/runs/run-1/sessions') {
      return jsonResponse([]);
    }

    if (path === '/v1/control-plane/runs/run-1/events') {
      return jsonResponse({
        events: [],
        last_event_id: '0',
      });
    }

    if (path === '/v1/control-plane/runs/run-1/artifacts') {
      return jsonResponse([]);
    }

    if (path === '/v1/control-plane/runs/run-1/conflicts') {
      return jsonResponse({
        run_id: 'run-1',
        conflicts: [],
      });
    }

    if (path === '/v1/control-plane/runs/run-1/tasks') {
      return jsonResponse([]);
    }

    if (path === '/v1/control-plane/runs/run-1/pr-package') {
      return jsonResponse({
        run_id: 'run-1',
        title: 'chore: onda 14 validation',
        summary: 'Pacote pronto para revisão.',
        files_changed: [],
        checks_passed: true,
      });
    }

    if (path === '/v1/control-plane/sessions' || path === '/v1/control-plane/session-threads') {
      return jsonResponse([]);
    }

    if (path === '/v1/control-plane/omniroute/inventory') {
      return jsonResponse({
        scope_id: 'default',
        available: true,
        connection_mode: 'gateway',
        models: [],
        accounts: [],
        next_account_overrides: {},
        quota: {
          status: 'unknown',
          providers: {},
        },
      });
    }

    if (path === '/v1/control-plane/quota' || path === '/v1/quota') {
      return jsonResponse({
        status: 'unknown',
        providers: {},
        updated_at: '2026-11-13T00:05:00Z',
      });
    }

    if (path === '/v1/control-plane/search') {
      return jsonResponse({
        query: url.searchParams.get('q') ?? '',
        scope: 'all',
        total: 1,
        items: [
          {
            id: 'run-1',
            kind: 'run',
            title: 'Run Hydra Integrado',
            subtitle: 'relay · review',
            host_id: 'local',
            project_id: 'proj-1',
            workspace_id: 'ws-1',
            run_id: 'run-1',
            tab_hint: 'chat',
          },
        ],
      });
    }

    if (path === '/v1/control-plane/pty/sessions') {
      return jsonResponse([]);
    }

    return jsonResponse({ detail: `unhandled mock route: ${path}` }, 404);
  });
}

describe('Onda 14 App shell wiring', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/');
    useAuthStore.getState().authenticate('tok-w14', 'op');
    useLayoutStore.getState().resetLayout();
    vi.stubGlobal('fetch', buildFetchStub());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('wires NovoChat composer, attachments, dictation and Ctrl+K QuickOpen without losing draft', async () => {
    const user = userEvent.setup();
    render(<App />);

    const textarea = await screen.findByLabelText('Descreva a tarefa para o coordenador');
    expect(screen.getByRole('button', { name: /Anexar arquivo/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ditado/i })).toBeInTheDocument();

    await user.type(textarea, 'Implementar fluxo integrado');
    expect((textarea as HTMLTextAreaElement).value).toBe('Implementar fluxo integrado');

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    const dialog = await screen.findByTestId('quickopen-dialog');
    expect(dialog).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByTestId('quickopen-dialog')).not.toBeInTheDocument();
    });

    const stillTextarea = screen.getByLabelText('Descreva a tarefa para o coordenador') as HTMLTextAreaElement;
    expect(stillTextarea.value).toBe('Implementar fluxo integrado');
  });

  it('navigates across QuotaAccountsPage, WorkspaceWorkbenchPage and ChatTimelinePage', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByLabelText('Descreva a tarefa para o coordenador');

    await user.click(screen.getByRole('button', { name: 'Contas e consumo' }));
    expect(await screen.findByRole('heading', { name: 'Contas e consumo' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Workspaces' }));
    expect(await screen.findByTestId('workspace-workbench-page')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    const combobox = await screen.findByRole('combobox');
    await user.type(combobox, 'Hydra');
    const match = await screen.findByText('Run Hydra Integrado');
    await user.click(match);

    await waitFor(() => {
      expect(window.location.pathname).toBe('/chat/run-1');
    });
    expect(await screen.findByTestId('coordinator-view')).toBeInTheDocument();
  });

  it('opens SplitTerminalView when routed to /terminal', async () => {
    window.history.pushState({}, '', '/terminal');
    render(<App />);

    expect(await screen.findByTestId('split-terminal-view')).toBeInTheDocument();
  });
});
