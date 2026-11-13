import fs from 'node:fs';
import path from 'node:path';
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { HydraShell } from '@/App';
import { createHydraQueryClient } from '@/hook/queryClient';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';

const MOCK_BOOTSTRAP = {
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
  implemented_read_models: { projects: true, runs: true },
};

describe('Figma dark design tokens & PT-BR shell invariants', () => {
  it('defines exact Figma dark palette CSS custom properties', () => {
    const tokensCss = fs.readFileSync(
      path.resolve(__dirname, '../src/style/tokens.css'),
      'utf-8',
    );
    expect(tokensCss).toContain('--bg-main: #141414');
    expect(tokensCss).toContain('--bg-rail: #181818');
    expect(tokensCss).toContain('--bg-sidebar: #1c1c1c');
    expect(tokensCss).toContain('--bg-surface: #202020');
    expect(tokensCss).toContain('--bg-hover: #282828');
    expect(tokensCss).toContain('--border: #303030');
    expect(tokensCss).toContain('--text-primary: #e8e8e8');
    expect(tokensCss).toContain('--text-muted: #969696');
    expect(tokensCss).toContain('Inter');
    expect(tokensCss).toContain('JetBrains Mono');
  });

  it('renders PT-BR navigation and zero macOS traffic lights inside AppShell', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith('/v1/control-plane/bootstrap')) {
          return new Response(JSON.stringify(MOCK_BOOTSTRAP), { status: 200 });
        }
        if (url.endsWith('/v1/control-plane/capabilities')) {
          return new Response(
            JSON.stringify({
              known_capabilities: [],
              executor_capabilities: [],
              certification_checks: [],
              drivers: [],
              agents: [],
              host_capabilities: MOCK_BOOTSTRAP.capabilities,
            }),
            { status: 200 },
          );
        }
        if (url.includes('/v1/control-plane/runs')) {
          return new Response(
            JSON.stringify({ items: [], total: 0, page: 1, size: 50, pages: 1 }),
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
        if (url.endsWith('/v1/quota')) {
          return new Response(JSON.stringify({ status: 'unknown' }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );

    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().authenticate('valid-test-token', 'operator');

    const qc = createHydraQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/']}>
          <HydraShell />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('hydra-app-shell')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Navegação principal' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Configurações e perfil' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Novo chat' })).toBeInTheDocument();

    // Zero fake macOS window dots
    expect(container.querySelector('.bg-red-500')).toBeNull();
    expect(container.querySelector('.bg-yellow-500')).toBeNull();
    expect(container.querySelector('[data-testid="macos-traffic-lights"]')).toBeNull();
  });
});
