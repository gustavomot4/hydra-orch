import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
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

function buildWave15FetchStub() {
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
      });
    }

    if (
      path === '/v1/control-plane/projects' ||
      path === '/v1/control-plane/areas' ||
      path === '/v1/control-plane/workspaces' ||
      path === '/v1/control-plane/executors' ||
      path === '/v1/control-plane/runs' ||
      path === '/v1/control-plane/sessions' ||
      path === '/v1/control-plane/session-threads' ||
      path === '/v1/control-plane/skills' ||
      path === '/v1/control-plane/mcps' ||
      path === '/v1/control-plane/automations'
    ) {
      return jsonResponse([]);
    }

    if (path === '/v1/quota' || path === '/v1/control-plane/quota') {
      return jsonResponse({ status: 'unknown', providers: {} });
    }

    return jsonResponse([]);
  });
}

describe('Onda 15 Part A (T35) App shell wiring', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/');
    useAuthStore.getState().authenticate('tok-w15', 'op');
    useLayoutStore.getState().resetLayout();
    vi.stubGlobal('fetch', buildWave15FetchStub());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('navigates across Recursos (GovernancePage), Automações (AutomationsPage), Emulador móvel and Controle do computador', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByLabelText('Descreva a tarefa para o coordenador');
    const rail = within(screen.getByRole('navigation', { name: 'Navegação principal' }));

    await user.click(rail.getByRole('button', { name: 'Recursos' }));
    expect(await screen.findByTestId('governance-page')).toBeInTheDocument();

    await user.click(rail.getByRole('button', { name: 'Automações' }));
    expect(await screen.findByTestId('automations-page')).toBeInTheDocument();

    await user.click(rail.getByRole('button', { name: 'Emulador móvel' }));
    const devicePanel = await screen.findByTestId('device-panel');
    expect(devicePanel).toBeInTheDocument();
    expect(within(devicePanel).getByText(/não possui certificação ativa/i)).toBeInTheDocument();
    expect(within(devicePanel).getByRole('status')).toHaveTextContent(/Indisponível/i);

    await user.click(rail.getByRole('button', { name: 'Controle do computador' }));
    const cuPanel = await screen.findByTestId('computer-use-panel');
    expect(cuPanel).toBeInTheDocument();
    expect(within(cuPanel).getByText(/não possui certificação ativa/i)).toBeInTheDocument();
    expect(within(cuPanel).getByRole('status')).toHaveTextContent(/Indisponível/i);
  });
});
