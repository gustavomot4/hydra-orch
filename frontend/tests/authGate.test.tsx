import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { HydraShell } from '@/App';
import { createHydraQueryClient } from '@/hook/queryClient';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';

const MINIMAL_BOOTSTRAP = {
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
    hosts: {},
  },
  implemented_read_models: {},
};

describe('Bearer AuthGate', () => {
  it('stays locked on 401 and unlocks cleanly on valid Bearer token, clearing on logout without URL leakage', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().logout();

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
      if (url.endsWith('/v1/control-plane/bootstrap')) {
        if (auth === 'Bearer secret-local-token') {
          return new Response(JSON.stringify(MINIMAL_BOOTSTRAP), { status: 200 });
        }
        return new Response(
          JSON.stringify({
            code: 'unauthorized',
            message: 'A valid local Bearer token is required',
            run_id: null,
            retryable: false,
          }),
          { status: 401 },
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
    });
    vi.stubGlobal('fetch', fetchMock);

    const qc = createHydraQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/']}>
          <HydraShell />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const input = screen.getByLabelText('Token Bearer');
    await user.type(input, 'wrong-token');
    await user.click(screen.getByRole('button', { name: 'Conectar ao Control Plane' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 401');
    expect(useAuthStore.getState().token).toBeNull();
    expect(window.sessionStorage.getItem('hydra_control_plane_token')).toBeNull();

    await user.clear(input);
    await user.type(input, 'secret-local-token');
    await user.click(screen.getByRole('button', { name: 'Conectar ao Control Plane' }));

    expect(await screen.findByTestId('hydra-app-shell')).toBeInTheDocument();
    expect(window.sessionStorage.getItem('hydra_control_plane_token')).toBe('secret-local-token');
    expect(window.location.href).not.toContain('secret-local-token');

    await user.click(screen.getByRole('button', { name: 'Bloquear sessão e sair' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Token Bearer')).toBeInTheDocument();
    });
    expect(window.sessionStorage.getItem('hydra_control_plane_token')).toBeNull();
    expect(useAuthStore.getState().token).toBeNull();
  });

  it('re-locks shell automatically when authenticated bootstrap returns 401', async () => {
    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().authenticate('stale-token', 'operator');

    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            code: 'unauthorized',
            message: 'Token expired',
            run_id: null,
            retryable: false,
          }),
          { status: 401 },
        ),
      ),
    );

    const qc = createHydraQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/']}>
          <HydraShell />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByLabelText('Token Bearer')).toBeInTheDocument();
    expect(useAuthStore.getState().token).toBeNull();
  });
});
