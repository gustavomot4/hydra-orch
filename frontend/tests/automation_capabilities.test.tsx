import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AutomationsPage,
  listAutomations,
  type AutomationRunRecord,
  type AutomationSchedule,
} from '@/feature/automation';
import { ComputerUsePanel } from '@/feature/computer_use';
import { DevicePanel } from '@/feature/device';
import { createHydraQueryClient } from '@/hook/queryClient';
import { createControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeSchedule(overrides: Partial<AutomationSchedule> = {}): AutomationSchedule {
  return {
    id: 'sched-1',
    name: 'Auditoria noturna',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    target_host: 'local',
    executor_id: 'codex',
    prompt: 'Executar suíte de regressão completa',
    cron_expr: '0 2 * * *',
    interval_seconds: null,
    timezone: 'America/Sao_Paulo',
    enabled: true,
    overlap_policy: 'skip',
    missed_policy: 'skip',
    max_retries: 1,
    next_run_at: '2026-11-14T05:00:00Z',
    last_run_at: '2026-11-13T05:00:00Z',
    revision: 1,
    created_at: '2026-11-10T00:00:00Z',
    updated_at: '2026-11-13T05:00:00Z',
    ...overrides,
  };
}

function makeRunRecord(overrides: Partial<AutomationRunRecord> = {}): AutomationRunRecord {
  return {
    id: 'arun-1',
    schedule_id: 'sched-1',
    occurrence_key: 'sched-1:2026-11-13T05:00:00+00:00',
    scheduled_for: '2026-11-13T05:00:00Z',
    run_id: 'run-777',
    status: 'succeeded',
    attempt_count: 1,
    error_detail: null,
    dispatched_at: '2026-11-13T05:00:01Z',
    finished_at: '2026-11-13T05:02:10Z',
    ...overrides,
  };
}

function buildDefaultCapabilities(certified = false) {
  const hosts: Record<string, unknown> = {
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
          platforms: { ios: 'unavailable', android: 'unavailable' },
        },
        computer_use: {
          status: 'unavailable',
          supported: false,
          certified: false,
          reason: 'uncertified_parking_lot_bridge',
        },
      },
    },
  };

  if (certified) {
    hosts['mac-lab'] = {
      host_id: 'mac-lab',
      transport_id: 'ssh-mac-01',
      transport_type: 'ssh',
      target_identity: 'iPhone 16 Pro Simulator',
      platform: 'Darwin',
      certified: true,
      capabilities: {
        pty: { status: 'available', supported: true, certified: true, backend_kind: 'posix_pty' },
        attachments: { status: 'available', supported: true, certified: true },
        quickopen: { status: 'available', supported: true, certified: true },
        preview: { status: 'available', supported: true, certified: true },
        scheduler: { status: 'unavailable', supported: false, certified: false },
        dictation_stt: {
          status: 'unavailable',
          supported: false,
          certified: false,
          available_modes: [],
          duplex_voice_enabled: false,
        },
        mobile_emulator: {
          status: 'available',
          supported: true,
          certified: true,
          transport_id: 'ssh-mac-01',
          target_device: 'iPhone 16 Pro (iOS 18.1)',
          platforms: { ios: 'available', android: 'unavailable' },
        },
        computer_use: {
          status: 'available',
          supported: true,
          certified: true,
          transport_id: 'cu-bridge-01',
          target_window: 'VS Code · hydra-orch',
        },
      },
    };
  }

  return {
    schema_version: '1.0',
    default_host: 'local',
    platform: 'Windows',
    integrations: {
      omniroute_enabled: false,
      omniroute_connection_mode: 'disabled',
      ssh_gpu_enabled: false,
      visual_interface_enabled: true,
    },
    hosts,
  };
}

describe('Onda 15 Part A — AutomationsPage (UI10) and Capability-Gated Panels (UI07 / UI11)', () => {
  beforeEach(() => {
    useAuthStore.getState().authenticate('tok-onda15', 'operator');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defensively accepts both array and { items } payloads from GET /automations', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        items: [makeSchedule({ id: 'sched-wrapped', name: 'Agenda encapsulada' })],
      }),
    );
    const client = createControlPlaneClient('tok-onda15', { fetchImpl: fetchMock });
    const items = await listAutomations(client);
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe('sched-wrapped');
  });

  it('lists and filters schedules, creates cron vs interval schedules with exclusive payload keys, toggles pause/resume, edits, triggers and opens linked run', async () => {
    const user = userEvent.setup();
    const onOpenRun = vi.fn();

    let schedulesState: AutomationSchedule[] = [
      makeSchedule({
        id: 'sched-1',
        name: 'Auditoria noturna',
        enabled: true,
        revision: 1,
        cron_expr: '0 2 * * *',
        interval_seconds: null,
        timezone: 'America/Sao_Paulo',
        overlap_policy: 'skip',
        missed_policy: 'skip',
      }),
      makeSchedule({
        id: 'sched-2',
        name: 'Sync métricas UTC',
        enabled: false,
        revision: 4,
        cron_expr: null,
        interval_seconds: 600,
        timezone: 'UTC',
        overlap_policy: 'queue',
        missed_policy: 'run_once',
        next_run_at: null,
        last_run_at: null,
      }),
    ];

    const runsBySchedule: Record<string, AutomationRunRecord[]> = {
      'sched-1': [
        makeRunRecord({
          id: 'arun-1',
          schedule_id: 'sched-1',
          run_id: 'run-777',
          status: 'succeeded',
          attempt_count: 1,
          error_detail: null,
        }),
        makeRunRecord({
          id: 'arun-2',
          schedule_id: 'sched-1',
          occurrence_key: 'sched-1:2026-11-12T05:00:00+00:00',
          scheduled_for: '2026-11-12T05:00:00Z',
          run_id: null,
          status: 'failed',
          attempt_count: 2,
          error_detail: 'automation_dispatch_unavailable',
        }),
      ],
      'sched-2': [],
    };

    const capturedPosts: Array<{ path: string; body: Record<string, unknown> | null }> = [];
    const capturedPuts: Array<{ path: string; body: Record<string, unknown> | null }> = [];
    const capturedDeletes: string[] = [];

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      const path = url.pathname;
      const method = init?.method ?? 'GET';
      const parsedBody =
        typeof init?.body === 'string' && init.body.length > 0
          ? (JSON.parse(init.body) as Record<string, unknown>)
          : null;

      if (path === '/v1/control-plane/capabilities') {
        return jsonResponse({
          known_capabilities: [],
          executor_capabilities: [],
          certification_checks: [],
          drivers: [],
          agents: [],
          host_capabilities: buildDefaultCapabilities(false),
        });
      }
      if (path === '/v1/control-plane/bootstrap') {
        return jsonResponse({
          api_version: 'v1',
          product: 'hydra-orch',
          capabilities: buildDefaultCapabilities(false),
        });
      }
      if (path === '/v1/control-plane/workspaces') {
        return jsonResponse([{ id: 'ws-1', area_id: 'a-1', name: 'Workspace Principal', status: 'active', revision: 1, created_at: '2026-11-10T00:00:00Z', updated_at: '2026-11-10T00:00:00Z' }]);
      }
      if (path === '/v1/control-plane/projects') {
        return jsonResponse([{ id: 'proj-1', canonical_root: '/repo/hydra', name: 'hydra-orch', created_at: '2026-11-10T00:00:00Z', updated_at: '2026-11-10T00:00:00Z' }]);
      }
      if (path === '/v1/control-plane/executors') {
        return jsonResponse([
          { id: 'codex', name: 'Codex CLI', driver: 'codex', driver_type: 'codex', executable: '/bin/codex', executable_found: true, is_certified: true, status: 'ready', capabilities: [], platform: 'Linux' },
        ]);
      }

      if (path === '/v1/control-plane/automations' && method === 'GET') {
        return jsonResponse(schedulesState);
      }

      if (path === '/v1/control-plane/automations' && method === 'POST') {
        capturedPosts.push({ path, body: parsedBody });
        const created = makeSchedule({
          id: `sched-${schedulesState.length + 1}`,
          name: String(parsedBody?.name ?? 'Nova'),
          prompt: String(parsedBody?.prompt ?? 'Tarefa'),
          cron_expr: typeof parsedBody?.cron_expr === 'string' ? parsedBody.cron_expr : null,
          interval_seconds:
            typeof parsedBody?.interval_seconds === 'number' ? parsedBody.interval_seconds : null,
          timezone: String(parsedBody?.timezone ?? 'UTC'),
          overlap_policy: (parsedBody?.overlap_policy as AutomationSchedule['overlap_policy']) ?? 'skip',
          missed_policy: (parsedBody?.missed_policy as AutomationSchedule['missed_policy']) ?? 'skip',
          revision: 1,
        });
        schedulesState = [...schedulesState, created];
        runsBySchedule[created.id] = [];
        return jsonResponse(created, 201);
      }

      const runsMatch = path.match(/^\/v1\/control-plane\/automations\/([^/]+)\/runs$/);
      if (runsMatch && method === 'GET') {
        return jsonResponse(runsBySchedule[decodeURIComponent(runsMatch[1])] ?? []);
      }

      const pauseMatch = path.match(/^\/v1\/control-plane\/automations\/([^/]+)\/pause$/);
      if (pauseMatch && method === 'POST') {
        const sid = decodeURIComponent(pauseMatch[1]);
        capturedPosts.push({ path, body: parsedBody });
        schedulesState = schedulesState.map((s) =>
          s.id === sid ? { ...s, enabled: false, revision: s.revision + 1, next_run_at: null } : s,
        );
        return jsonResponse(schedulesState.find((s) => s.id === sid));
      }

      const resumeMatch = path.match(/^\/v1\/control-plane\/automations\/([^/]+)\/resume$/);
      if (resumeMatch && method === 'POST') {
        const sid = decodeURIComponent(resumeMatch[1]);
        capturedPosts.push({ path, body: parsedBody });
        schedulesState = schedulesState.map((s) =>
          s.id === sid
            ? { ...s, enabled: true, revision: s.revision + 1, next_run_at: '2026-11-14T06:00:00Z' }
            : s,
        );
        return jsonResponse(schedulesState.find((s) => s.id === sid));
      }

      const triggerMatch = path.match(/^\/v1\/control-plane\/automations\/([^/]+)\/trigger$/);
      if (triggerMatch && method === 'POST') {
        const sid = decodeURIComponent(triggerMatch[1]);
        capturedPosts.push({ path, body: parsedBody });
        const manualRun = makeRunRecord({
          id: 'arun-manual-99',
          schedule_id: sid,
          occurrence_key: 'manual:uuid-99',
          run_id: 'run-manual-99',
          status: 'dispatched',
          attempt_count: 1,
          error_detail: null,
          finished_at: null,
        });
        runsBySchedule[sid] = [manualRun, ...(runsBySchedule[sid] ?? [])];
        return jsonResponse({
          automation_run_id: manualRun.id,
          schedule_id: sid,
          occurrence_key: manualRun.occurrence_key,
          scheduled_for: manualRun.scheduled_for,
          run_id: manualRun.run_id,
          status: manualRun.status,
          attempt_count: manualRun.attempt_count,
          error_detail: null,
          dispatched_at: manualRun.dispatched_at,
          finished_at: null,
        });
      }

      const itemMatch = path.match(/^\/v1\/control-plane\/automations\/([^/]+)$/);
      if (itemMatch && method === 'PUT') {
        const sid = decodeURIComponent(itemMatch[1]);
        capturedPuts.push({ path, body: parsedBody });
        schedulesState = schedulesState.map((s) =>
          s.id === sid
            ? {
                ...s,
                name: String(parsedBody?.name ?? s.name),
                prompt: String(parsedBody?.prompt ?? s.prompt),
                revision: s.revision + 1,
              }
            : s,
        );
        return jsonResponse(schedulesState.find((s) => s.id === sid));
      }
      if (itemMatch && method === 'DELETE') {
        const sid = decodeURIComponent(itemMatch[1]);
        capturedDeletes.push(sid);
        schedulesState = schedulesState.filter((s) => s.id !== sid);
        return jsonResponse({ deleted: true, schedule_id: sid });
      }

      return jsonResponse({ code: 'not_found', message: `Unhandled ${method} ${path}` }, 404);
    });

    vi.stubGlobal('fetch', fetchMock);
    const qc = createHydraQueryClient();

    render(
      <QueryClientProvider client={qc}>
        <AutomationsPage onOpenRun={onOpenRun} />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('automations-page')).toBeInTheDocument();
    const firstCard = await screen.findByTestId('automation-card-sched-1');
    expect(within(firstCard).getByText('Auditoria noturna')).toBeInTheDocument();
    expect(within(firstCard).getByText('Ativa')).toBeInTheDocument();
    expect(within(firstCard).getByText('Cron: 0 2 * * *')).toBeInTheDocument();
    expect(within(firstCard).getByText('America/Sao_Paulo')).toBeInTheDocument();
    expect(within(firstCard).getByText('rev. 1')).toBeInTheDocument();
    expect(within(firstCard).getByText(/skip \/ skip/)).toBeInTheDocument();

    const secondCard = screen.getByTestId('automation-card-sched-2');
    expect(within(secondCard).getByRole('status')).toHaveTextContent('Pausada');
    expect(within(secondCard).getByText(/Intervalo: 600s/)).toBeInTheDocument();
    expect(within(secondCard).getByText('UTC')).toBeInTheDocument();
    expect(within(secondCard).getByText('rev. 4')).toBeInTheDocument();

    // Filter by paused vs search
    await user.selectOptions(screen.getByLabelText('Estado:'), 'paused');
    expect(screen.queryByTestId('automation-card-sched-1')).toBeNull();
    expect(screen.getByTestId('automation-card-sched-2')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Estado:'), 'all');

    const searchInput = screen.getByLabelText('Buscar automações');
    await user.type(searchInput, 'Auditoria');
    expect(screen.getByTestId('automation-card-sched-1')).toBeInTheDocument();
    expect(screen.queryByTestId('automation-card-sched-2')).toBeNull();
    await user.clear(searchInput);

    // Occurrence history displays linked run button + error_detail
    const runsPanel = screen.getByTestId('automation-runs-panel');
    const openRunBtn = await within(runsPanel).findByRole('button', { name: 'Abrir run run-777' });
    await user.click(openRunBtn);
    expect(onOpenRun).toHaveBeenCalledWith('run-777');
    expect(within(runsPanel).getByText('automation_dispatch_unavailable')).toBeInTheDocument();
    expect(within(runsPanel).getByText('Tentativas: 2')).toBeInTheDocument();
    expect(within(runsPanel).getByText('Sem run vinculado')).toBeInTheDocument();

    // Pause and resume send expected_revision
    await user.click(screen.getByRole('button', { name: 'Pausar Auditoria noturna' }));
    await waitFor(() => {
      expect(
        capturedPosts.some(
          (entry) =>
            entry.path === '/v1/control-plane/automations/sched-1/pause' &&
            entry.body?.expected_revision === 1,
        ),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(within(screen.getByTestId('automation-card-sched-1')).getByText('rev. 2')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Retomar Auditoria noturna' }));
    await waitFor(() => {
      expect(
        capturedPosts.some(
          (entry) =>
            entry.path === '/v1/control-plane/automations/sched-1/resume' &&
            entry.body?.expected_revision === 2,
        ),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(within(screen.getByTestId('automation-card-sched-1')).getByText('rev. 3')).toBeInTheDocument();
    });

    // Edit sends expected_revision (3)
    await user.click(screen.getByRole('button', { name: 'Editar Auditoria noturna' }));
    const nameInput = screen.getByLabelText('Nome da automação');
    await user.clear(nameInput);
    await user.type(nameInput, 'Auditoria revisada');
    await user.click(screen.getByRole('button', { name: 'Salvar alterações' }));
    await waitFor(() => {
      expect(capturedPuts).toHaveLength(1);
    });
    expect(capturedPuts[0].body).toMatchObject({
      name: 'Auditoria revisada',
      expected_revision: 3,
      cron_expr: '0 2 * * *',
    });
    expect(Object.keys(capturedPuts[0].body ?? {})).not.toContain('interval_seconds');

    // Manual trigger refreshes runs history
    const triggerBtn = await screen.findByRole('button', { name: 'Executar agora Auditoria revisada' });
    await user.click(triggerBtn);
    expect(await within(runsPanel).findByRole('button', { name: 'Abrir run run-manual-99' })).toBeInTheDocument();

    // Create Cron schedule: must send ONLY cron_expr, never interval_seconds
    await user.click(screen.getByRole('button', { name: 'Nova automação' }));
    await user.type(screen.getByLabelText('Nome da automação'), 'Build diário');
    await user.type(screen.getByLabelText('Prompt da execução'), 'Rodar lint e typecheck');
    const cronInput = screen.getByRole('textbox', { name: /Expressão Cron/ });
    await user.clear(cronInput);
    await user.type(cronInput, '30 8 * * 1-5');
    await user.click(screen.getByRole('button', { name: 'Criar automação' }));

    expect(await screen.findByTestId('automation-card-sched-3')).toBeInTheDocument();
    const cronPost = capturedPosts.find((entry) => entry.path === '/v1/control-plane/automations');
    expect(cronPost?.body?.cron_expr).toBe('30 8 * * 1-5');
    expect(Object.keys(cronPost?.body ?? {})).not.toContain('interval_seconds');

    // Create Interval schedule: rejects < 60s, then accepts >= 60s sending ONLY interval_seconds
    await user.click(screen.getByRole('button', { name: 'Nova automação' }));
    await user.type(screen.getByLabelText('Nome da automação'), 'Healthcheck');
    await user.type(screen.getByLabelText('Prompt da execução'), 'Verificar status dos runners');
    await user.click(screen.getByLabelText('Intervalo (segundos)'));
    const intervalInput = screen.getByLabelText(/Intervalo em segundos/);
    await user.clear(intervalInput);
    await user.type(intervalInput, '30');
    await user.click(screen.getByRole('button', { name: 'Criar automação' }));
    expect(await screen.findByText(/maior ou igual a 60 segundos/i)).toBeInTheDocument();

    await user.clear(intervalInput);
    await user.type(intervalInput, '120');
    await user.click(screen.getByRole('button', { name: 'Criar automação' }));

    expect(await screen.findByTestId('automation-card-sched-4')).toBeInTheDocument();
    const intervalPost = capturedPosts.filter(
      (entry) => entry.path === '/v1/control-plane/automations',
    )[1];
    expect(intervalPost?.body?.interval_seconds).toBe(120);
    expect(Object.keys(intervalPost?.body ?? {})).not.toContain('cron_expr');

    // Delete with confirmation removes schedule
    await user.click(screen.getByRole('button', { name: 'Excluir Sync métricas UTC' }));
    await user.click(screen.getByRole('button', { name: 'Confirmar exclusão' }));
    await waitFor(() => {
      expect(capturedDeletes).toContain('sched-2');
      expect(screen.queryByTestId('automation-card-sched-2')).toBeNull();
    });
  }, 15_000);

  it('handles HTTP 409 optimistic-lock conflict explicitly with role="alert" and preserves form edits across reload', async () => {
    const user = userEvent.setup();
    let serverRevision = 1;
    let returnConflictOnNextPut = true;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      const path = url.pathname;
      const method = init?.method ?? 'GET';
      const parsedBody =
        typeof init?.body === 'string' && init.body.length > 0
          ? (JSON.parse(init.body) as Record<string, unknown>)
          : null;

      if (path === '/v1/control-plane/capabilities') {
        return jsonResponse({
          known_capabilities: [],
          executor_capabilities: [],
          certification_checks: [],
          drivers: [],
          agents: [],
          host_capabilities: buildDefaultCapabilities(false),
        });
      }
      if (path === '/v1/control-plane/bootstrap') {
        return jsonResponse({
          api_version: 'v1',
          product: 'hydra-orch',
          capabilities: buildDefaultCapabilities(false),
        });
      }
      if (path === '/v1/control-plane/workspaces' || path === '/v1/control-plane/projects' || path === '/v1/control-plane/executors') {
        return jsonResponse([]);
      }
      if (path === '/v1/control-plane/automations' && method === 'GET') {
        return jsonResponse([makeSchedule({ id: 'sched-1', revision: serverRevision })]);
      }
      if (path === '/v1/control-plane/automations/sched-1/runs' && method === 'GET') {
        return jsonResponse([]);
      }
      if (path === '/v1/control-plane/automations/sched-1' && method === 'PUT') {
        if (returnConflictOnNextPut) {
          returnConflictOnNextPut = false;
          serverRevision = 5;
          return jsonResponse(
            {
              code: 'optimistic_lock_conflict',
              message: 'AutomationSchedule revision changed',
              run_id: null,
              retryable: true,
            },
            409,
          );
        }
        return jsonResponse(
          makeSchedule({
            id: 'sched-1',
            prompt: String(parsedBody?.prompt ?? ''),
            revision: Number(parsedBody?.expected_revision ?? serverRevision) + 1,
          }),
        );
      }
      return jsonResponse({}, 404);
    });

    vi.stubGlobal('fetch', fetchMock);
    const qc = createHydraQueryClient();

    render(
      <QueryClientProvider client={qc}>
        <AutomationsPage />
      </QueryClientProvider>,
    );

    await screen.findByTestId('automation-card-sched-1');
    await user.click(screen.getByRole('button', { name: 'Editar Auditoria noturna' }));

    const promptInput = screen.getByLabelText('Prompt da execução');
    await user.clear(promptInput);
    await user.type(promptInput, 'Prompt atualizado sem perder contexto');
    await user.click(screen.getByRole('button', { name: 'Salvar alterações' }));

    const conflictAlert = await screen.findByTestId('automation-conflict-alert');
    expect(conflictAlert).toHaveAttribute('role', 'alert');
    expect(conflictAlert).toHaveTextContent(/409/);
    // Form edits remain intact when 409 occurs
    expect(screen.getByLabelText('Prompt da execução')).toHaveValue(
      'Prompt atualizado sem perder contexto',
    );

    // Reload updates revision while preserving edited prompt, enabling clean resubmit
    await user.click(within(conflictAlert).getByRole('button', { name: 'Recarregar automações' }));
    await waitFor(() => {
      expect(within(screen.getByTestId('automation-card-sched-1')).getByText('rev. 5')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Prompt da execução')).toHaveValue(
      'Prompt atualizado sem perder contexto',
    );

    await user.click(screen.getByRole('button', { name: 'Salvar alterações' }));
    await waitFor(() => {
      expect(screen.getByTestId('automation-status-banner')).toHaveTextContent('revisão 6');
    });
  });

  it('DevicePanel (UI07 / F06) gates uncertified local host with Indisponível and renders certified iOS/Android status without fake execution', async () => {
    const user = userEvent.setup();
    const onHostChange = vi.fn();

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost');
      if (url.pathname === '/v1/control-plane/capabilities') {
        return jsonResponse({
          known_capabilities: [],
          executor_capabilities: [],
          certification_checks: [],
          drivers: [],
          agents: [],
          host_capabilities: buildDefaultCapabilities(true),
        });
      }
      if (url.pathname === '/v1/control-plane/bootstrap') {
        return jsonResponse({
          api_version: 'v1',
          product: 'hydra-orch',
          capabilities: buildDefaultCapabilities(true),
        });
      }
      return jsonResponse({}, 404);
    });

    vi.stubGlobal('fetch', fetchMock);
    const qc = createHydraQueryClient();

    const { container } = render(
      <QueryClientProvider client={qc}>
        <DevicePanel onHostChange={onHostChange} />
      </QueryClientProvider>,
    );

    const panel = await screen.findByTestId('device-panel');
    expect(within(panel).getByText('Parking Lot F06 · Capability-gated')).toBeInTheDocument();
    expect(await within(panel).findByText('Indisponível')).toBeInTheDocument();
    expect(within(panel).getByText(/não possui certificação/i)).toBeInTheDocument();
    expect(within(panel).getByText('uncertified_parking_lot_bridge')).toBeInTheDocument();
    expect(screen.queryByTestId('device-certified-surface')).toBeNull();
    expect(container.querySelector('canvas')).toBeNull();

    // Switch to certified remote host mac-lab
    await user.selectOptions(
      screen.getByLabelText('Selecionar host para emulador móvel'),
      'mac-lab',
    );
    expect(onHostChange).toHaveBeenCalledWith('mac-lab');

    const certifiedSurface = await screen.findByTestId('device-certified-surface');
    expect(within(certifiedSurface).getByText('Bridge pronto')).toBeInTheDocument();
    expect(within(screen.getByTestId('device-platform-ios')).getByText('Disponível')).toBeInTheDocument();
    expect(
      within(screen.getByTestId('device-platform-android')).getByText('Indisponível'),
    ).toBeInTheDocument();
    expect(within(certifiedSurface).getByText('iPhone 16 Pro (iOS 18.1)')).toBeInTheDocument();
    expect(container.querySelector('canvas')).toBeNull();
  });

  it('ComputerUsePanel (UI11 / F07) gates uncertified local host with Indisponível and renders visible-target + HITL/emergency-stop invariants for certified host', async () => {
    const user = userEvent.setup();
    const onHostChange = vi.fn();

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost');
      if (url.pathname === '/v1/control-plane/capabilities') {
        return jsonResponse({
          known_capabilities: [],
          executor_capabilities: [],
          certification_checks: [],
          drivers: [],
          agents: [],
          host_capabilities: buildDefaultCapabilities(true),
        });
      }
      if (url.pathname === '/v1/control-plane/bootstrap') {
        return jsonResponse({
          api_version: 'v1',
          product: 'hydra-orch',
          capabilities: buildDefaultCapabilities(true),
        });
      }
      return jsonResponse({}, 404);
    });

    vi.stubGlobal('fetch', fetchMock);
    const qc = createHydraQueryClient();

    const { container } = render(
      <QueryClientProvider client={qc}>
        <ComputerUsePanel onHostChange={onHostChange} />
      </QueryClientProvider>,
    );

    const panel = await screen.findByTestId('computer-use-panel');
    expect(within(panel).getByText('Parking Lot F07 · Capability-gated')).toBeInTheDocument();
    expect(await within(panel).findByText('Indisponível')).toBeInTheDocument();
    expect(within(panel).getByText(/não possui certificação/i)).toBeInTheDocument();
    expect(within(panel).getByText('uncertified_parking_lot_bridge')).toBeInTheDocument();
    expect(screen.queryByTestId('computer-use-certified-surface')).toBeNull();
    expect(container.querySelector('canvas')).toBeNull();

    await user.selectOptions(
      screen.getByLabelText('Selecionar host para controle do computador'),
      'mac-lab',
    );
    expect(onHostChange).toHaveBeenCalledWith('mac-lab');

    const certifiedSurface = await screen.findByTestId('computer-use-certified-surface');
    expect(within(certifiedSurface).getByText('Executor pronto')).toBeInTheDocument();
    expect(screen.getByTestId('computer-use-target-requirement')).toHaveTextContent(
      'VS Code · hydra-orch',
    );
    expect(screen.getByTestId('computer-use-hitl-invariant')).toHaveTextContent(
      /task\.needs_approval/,
    );
    expect(screen.getByTestId('computer-use-hitl-invariant')).toHaveTextContent(
      /Parada de emergência/i,
    );
    expect(container.querySelector('canvas')).toBeNull();
  });
});
