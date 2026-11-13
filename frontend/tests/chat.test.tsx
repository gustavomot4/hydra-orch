import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import {
  ChatTimelinePage,
  ChatTimelineState,
  connectRunEventStream,
  deriveTimelineState,
  EventDeduplicator,
} from '@/feature/chat';
import { createHydraQueryClient } from '@/hook/queryClient';
import { useAuthStore } from '@/store/authStore';

function buildRunSnapshot(overrides?: Record<string, unknown>) {
  return {
    id: 'run-1',
    run_id: 'run-1',
    project_id: 'proj-1',
    objective: 'Implementar pipeline de chat e checks',
    mode: 'swarm',
    status: 'running',
    revision: 2,
    base_sha: 'a'.repeat(40),
    created_at: '2026-11-13T01:00:00Z',
    updated_at: '2026-11-13T01:05:00Z',
    tasks: [
      {
        id: 'task-wave0',
        task_id: 'task-wave0',
        run_id: 'run-1',
        status: 'failed',
        revision: 1,
        dependencies: [],
        created_at: '2026-11-13T01:00:00Z',
        updated_at: '2026-11-13T01:02:00Z',
        spec: {
          task_id: 'task-wave0',
          objective: 'Executar suíte backend',
          assigned_executor: 'codex',
          dependencies: [],
          acceptance_criteria: [
            {
              check_id: 'chk-pytest',
              command: ['pytest', 'tests/test_api.py'],
              description: 'Suíte API backend',
            },
            {
              check_id: 'chk-lint',
              command: ['ruff', 'check', '.'],
              description: 'Lint backend',
            },
          ],
        },
        current_attempt: {
          attempt_id: 'att-1',
          task_id: 'task-wave0',
          ordinal: 1,
          executor_id: 'codex',
          provider: 'openai',
          model: 'gpt-5-codex',
          process_status: 'exited',
          exit_code: 1,
          started_at: '2026-11-13T01:01:00Z',
          finished_at: '2026-11-13T01:01:14Z',
          workspace_path: '/repo/.hydra/worktrees/task-wave0',
          result: {
            result_id: 'res-1',
            attempt_id: 'att-1',
            exit_code: 1,
            task_status: 'failed',
            revision: 1,
            summary: 'All tests passed! Concluído com sucesso.',
            checks: [
              {
                check_id: 'chk-pytest',
                command: ['pytest', 'tests/test_api.py'],
                exit_code: 1,
                duration_seconds: 14,
              },
            ],
            failures: [
              {
                code: 'check_failed',
                message: 'pytest retornou código 1',
                retryable: true,
              },
            ],
          },
        },
        attempts: [],
      },
      {
        id: 'task-wave1',
        task_id: 'task-wave1',
        run_id: 'run-1',
        status: 'running',
        revision: 1,
        dependencies: ['task-wave0'],
        created_at: '2026-11-13T01:02:00Z',
        updated_at: '2026-11-13T01:03:00Z',
        spec: {
          task_id: 'task-wave1',
          objective: 'Integrar painel de revisão',
          assigned_executor: 'claude',
          dependencies: ['task-wave0'],
          acceptance_criteria: [],
        },
        current_attempt: {
          attempt_id: 'att-2',
          task_id: 'task-wave1',
          ordinal: 1,
          executor_id: 'claude',
          provider: 'anthropic',
          model: 'claude-sonnet-4',
          process_status: 'running',
          exit_code: null,
          started_at: '2026-11-13T01:02:05Z',
          finished_at: null,
          workspace_path: '/repo/.hydra/worktrees/task-wave1',
          result: null,
        },
        attempts: [],
      },
    ],
    ...(overrides ?? {}),
  };
}

describe('ChatTimeline SSE, Coordinator, Workers and HITL Inline (T33)', () => {
  it('models all 9 explicit timeline states deterministically', () => {
    const states: ChatTimelineState[] = [
      deriveTimelineState({ connectionPhase: 'idle' }),
      deriveTimelineState({ connectionPhase: 'connecting', runStatus: 'running' }),
      deriveTimelineState({ connectionPhase: 'streaming', runStatus: 'running' }),
      deriveTimelineState({ connectionPhase: 'streaming', runStatus: 'waiting', hasPendingHitl: true }),
      deriveTimelineState({ connectionPhase: 'streaming', runStatus: 'reviewing' }),
      deriveTimelineState({ connectionPhase: 'closed', runStatus: 'succeeded' }),
      deriveTimelineState({ connectionPhase: 'closed', runStatus: 'failed' }),
      deriveTimelineState({ connectionPhase: 'closed', runStatus: 'cancelled' }),
      deriveTimelineState({ connectionPhase: 'stale_cursor', runStatus: 'running' }),
    ];

    expect(states).toEqual([
      'idle',
      'connecting',
      'streaming',
      'paused_hitl',
      'reviewing',
      'completed',
      'failed',
      'cancelled',
      'stale_cursor',
    ]);
  });

  it('sends Bearer and Last-Event-ID in headers (never URL), deduplicates seq/id, and recovers via snapshot on HTTP 410', async () => {
    const dedup = new EventDeduplicator();
    expect(dedup.accept({ seq: 1, id: '1' })).toBe(true);
    expect(dedup.accept({ seq: 1, id: '1' })).toBe(false);
    expect(dedup.accept({ seq: 2, id: 'evt-2' })).toBe(true);
    expect(dedup.accept({ id: 'evt-2' })).toBe(false);
    expect(dedup.accept({ id: 'evt-custom' })).toBe(true);
    expect(dedup.accept({ id: 'evt-custom' })).toBe(false);

    const observedUrls: string[] = [];
    const observedHeaders: Array<Record<string, string>> = [];
    const stateTransitions: ChatTimelineState[] = [];
    const recoveredEvents: number[] = [];

    const mockFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const headers = (init?.headers ?? {}) as Record<string, string>;
      observedUrls.push(url);
      observedHeaders.push(headers);

      if (url.includes('/events') && url.includes('follow=true')) {
        return new Response(
          JSON.stringify({ code: 'cursor_expired', message: 'Cursor expirado' }),
          { status: 410, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/v1/control-plane/runs/run-410')) {
        return new Response(
          JSON.stringify(buildRunSnapshot({ id: 'run-410', run_id: 'run-410', status: 'reviewing' })),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.includes('/v1/control-plane/runs/run-410/events') && url.includes('follow=false')) {
        const sseBody = [
          'id: 10',
          'event: task.started',
          'data: {"run_id":"run-410","seq":10,"type":"task.started","task_id":"task-wave0","payload":{"message":"Retomado"},"timestamp":"2026-11-13T01:10:00Z"}',
          '',
          'id: 10',
          'event: task.started',
          'data: {"run_id":"run-410","seq":10,"type":"task.started","task_id":"task-wave0","payload":{"message":"Duplicado"},"timestamp":"2026-11-13T01:10:00Z"}',
          '',
          'id: 11',
          'event: assistant.message',
          'data: {"run_id":"run-410","seq":11,"type":"assistant.message","payload":{"content":"Snapshot recuperado"},"timestamp":"2026-11-13T01:10:05Z"}',
          '',
          '',
        ].join('\n');
        return new Response(sseBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }

      if (url.endsWith('/v1/control-plane/runs/run-410/interventions')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return new Response(JSON.stringify({}), { status: 404 });
    });

    const result = await connectRunEventStream({
      runId: 'run-410',
      token: 'secret-bearer-token-xyz',
      lastEventId: '3',
      fetchImpl: mockFetch as unknown as typeof fetch,
      onEvent: () => undefined,
      onStateChange: (s) => stateTransitions.push(s),
      onSnapshotRecovery: (_bundle, accepted) => {
        recoveredEvents.push(...accepted.map((e) => e.seq));
      },
    });

    expect(result.status).toBe('recovered_from_410');
    expect(stateTransitions).toContain('connecting');
    expect(stateTransitions).toContain('stale_cursor');
    expect(stateTransitions[stateTransitions.length - 1]).toBe('reviewing');
    expect(recoveredEvents).toEqual([10, 11]);

    // Token NEVER appears in URL query parameters
    for (const url of observedUrls) {
      expect(url).not.toContain('secret-bearer-token-xyz');
      expect(url).not.toContain('token=');
    }

    // First SSE request carried Authorization + Last-Event-ID
    expect(observedHeaders[0].Authorization).toBe('Bearer secret-bearer-token-xyz');
    expect(observedHeaders[0]['Last-Event-ID']).toBe('3');

    // Snapshot recovery GET /events did NOT send stale Last-Event-ID
    const snapshotEventsCallIdx = observedUrls.findIndex((u) => u.includes('follow=false'));
    expect(snapshotEventsCallIdx).toBeGreaterThan(-1);
    expect(observedHeaders[snapshotEventsCallIdx]['Last-Event-ID']).toBeUndefined();

    // No POST/PUT/PATCH/DELETE mutation calls were triggered during 410 recovery
    expect(mockFetch.mock.calls.every((c) => !c[1]?.method || c[1].method === 'GET')).toBe(true);
  });

  it('renders Coordinator + Swarm Wave 0/1 Workers, Worked for Xs, collapsible traces, check invariant, single-submit HITL and task retry', async () => {
    const user = userEvent.setup();
    useAuthStore.getState().authenticate('hydra-valid-token', 'operator');

    let hitlResolved = false;
    let resolveHitlPost!: (resp: Response) => void;
    const hitlPostCalls: Array<{ url: string; headers: Record<string, string>; body: string }> = [];
    const retryPostCalls: string[] = [];

    const ssePayload = [
      'id: 1',
      'event: task.started',
      'data: {"run_id":"run-1","seq":1,"type":"task.started","task_id":"task-wave0","payload":{"message":"Iniciando worker Wave 0"},"timestamp":"2026-11-13T01:01:00Z"}',
      '',
      'id: 1',
      'event: task.started',
      'data: {"run_id":"run-1","seq":1,"type":"task.started","task_id":"task-wave0","payload":{"message":"Evento duplicado ignorado"},"timestamp":"2026-11-13T01:01:00Z"}',
      '',
      'id: 2',
      'event: worker.message',
      'data: {"run_id":"run-1","seq":2,"type":"worker.message","task_id":"task-wave0","payload":{"content":"All tests passed! Concluído com sucesso."},"timestamp":"2026-11-13T01:01:14Z"}',
      '',
      'event: heartbeat',
      'data: {"run_id":"run-1","timestamp":"2026-11-13T01:01:15Z"}',
      '',
      '',
    ].join('\n');

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/v1/control-plane/runs/run-1') && method === 'GET') {
        return new Response(
          JSON.stringify(
            buildRunSnapshot({
              status: hitlResolved ? 'running' : 'waiting',
            }),
          ),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.includes('/v1/control-plane/runs/run-1/events') && url.includes('follow=false')) {
        return new Response(ssePayload, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }

      if (url.includes('/v1/control-plane/runs/run-1/events') && url.includes('follow=true')) {
        return new Response(
          'id: 2\nevent: worker.message\ndata: {"run_id":"run-1","seq":2,"type":"worker.message","task_id":"task-wave0","payload":{"content":"Duplicado stream"},"timestamp":"2026-11-13T01:01:14Z"}\n\n',
          { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
        );
      }

      if (url.endsWith('/v1/control-plane/runs/run-1/interventions') && method === 'GET') {
        return new Response(
          JSON.stringify([
            {
              request_id: 'hitl-req-1',
              run_id: 'run-1',
              task_id: 'task-wave1',
              kind: 'needs_approval',
              question: 'Autorizar aplicação do patch na branch principal?',
              state: hitlResolved ? 'answered' : 'pending',
              revision: hitlResolved ? 2 : 1,
              created_at: '2026-11-13T01:02:00Z',
              deadline: '2026-11-13T02:00:00Z',
              response: hitlResolved ? 'Pode prosseguir' : null,
              actor: hitlResolved ? 'operator' : null,
              resolved_at: hitlResolved ? '2026-11-13T01:03:00Z' : null,
            },
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/v1/control-plane/runs/run-1/interventions/hitl-req-1/response') && method === 'POST') {
        hitlPostCalls.push({
          url,
          headers: (init?.headers ?? {}) as Record<string, string>,
          body: String(init?.body ?? ''),
        });
        return new Promise<Response>((resolve) => {
          resolveHitlPost = resolve;
        });
      }

      if (url.endsWith('/v1/control-plane/runs/run-1/tasks/task-wave0/retry') && method === 'POST') {
        retryPostCalls.push(url);
        return new Response(
          JSON.stringify({
            attempt_id: 'att-retry-2',
            result_id: 'res-retry-2',
            task_id: 'task-wave0',
            run_id: 'run-1',
            ordinal: 2,
            status: 'running',
            task_status: 'running',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.includes('/v1/control-plane/sessions')) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      return new Response(JSON.stringify([]), { status: 200 });
    });

    vi.stubGlobal('fetch', fetchMock);
    const qc = createHydraQueryClient();

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ChatTimelinePage runId="run-1" fetchImpl={fetchMock as unknown as typeof fetch} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Wait for workers Wave 0 and Wave 1 + duration badge "Worked for 14s"
    expect(await screen.findByTestId('worker-card-task-wave0')).toBeInTheDocument();
    expect(screen.getByTestId('worker-card-task-wave1')).toBeInTheDocument();
    expect(screen.getByTestId('worker-wave-group-0')).toHaveTextContent('Swarm Wave 0');
    expect(screen.getByTestId('worker-wave-group-1')).toHaveTextContent('Swarm Wave 1');
    expect(screen.getByTestId('worker-duration-task-wave0')).toHaveTextContent('Worked for 14s');
    expect(screen.getByTestId('worker-card-task-wave0')).toHaveTextContent(
      '/repo/.hydra/worktrees/task-wave0',
    );

    // Deduplication check: message content appears once in coordinator timeline, duplicated events ignored
    const timelinePane = screen.getByTestId('coordinator-timeline-pane');
    expect(within(timelinePane).getAllByText('All tests passed! Concluído com sucesso.')).toHaveLength(1);

    // UI Invariant: worker claiming "All tests passed!" NEVER marks failed/pending checks as passed
    const failedCheckBadge = screen.getByTestId('check-badge-task-wave0-chk-pytest');
    expect(failedCheckBadge).toHaveAttribute('data-check-status', 'failed');
    expect(failedCheckBadge).toHaveTextContent('Falhou');

    const pendingCheckBadge = screen.getByTestId('check-badge-task-wave0-chk-lint');
    expect(pendingCheckBadge).toHaveAttribute('data-check-status', 'pending');
    expect(pendingCheckBadge).toHaveTextContent('Pendente');

    expect(screen.getByTestId('unverified-claim-warning')).toBeInTheDocument();

    // Collapsible trace rows on WorkerCard
    const wave0Card = screen.getByTestId('worker-card-task-wave0');
    const traceToggle = within(wave0Card).getByRole('button', { name: /Trace \(/i });
    expect(traceToggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(traceToggle);
    expect(traceToggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('worker-trace-rows-task-wave0')).toHaveTextContent('task.started');

    // Collapsible thought/step group in CoordinatorView
    const stepToggle = screen.getByRole('button', { name: /Passos de coordenação/i });
    expect(stepToggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(stepToggle);
    expect(stepToggle).toHaveAttribute('aria-expanded', 'true');

    // HITL inline reply: single non-retried POST + disabled during in-flight
    const hitlCard = screen.getByTestId('hitl-card-hitl-req-1');
    const hitlInput = within(hitlCard).getByLabelText('Resposta da intervenção HITL');
    await user.type(hitlInput, 'Pode prosseguir');

    const approveBtn = within(hitlCard).getByRole('button', { name: 'Aprovar' });
    await user.click(approveBtn);

    expect(approveBtn).toBeDisabled();
    // Second rapid click while in flight must NOT fire a second POST
    await user.click(approveBtn);
    expect(hitlPostCalls).toHaveLength(1);
    expect(hitlPostCalls[0].headers['Idempotency-Key']?.length).toBeGreaterThanOrEqual(16);
    expect(JSON.parse(hitlPostCalls[0].body)).toMatchObject({
      response: 'Pode prosseguir',
      actor: 'operator',
      expected_revision: 1,
      approved: true,
    });

    hitlResolved = true;
    resolveHitlPost(
      new Response(
        JSON.stringify({
          request_id: 'hitl-req-1',
          run_id: 'run-1',
          task_id: 'task-wave1',
          kind: 'needs_approval',
          question: 'Autorizar aplicação do patch na branch principal?',
          state: 'answered',
          revision: 2,
          created_at: '2026-11-13T01:02:00Z',
          deadline: '2026-11-13T02:00:00Z',
          response: 'Pode prosseguir',
          actor: 'operator',
          resolved_at: '2026-11-13T01:03:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await waitFor(() => {
      expect(screen.getByTestId('hitl-resolved-hitl-req-1')).toBeInTheDocument();
    });

    // Retry failed task
    const retryBtn = screen.getByTestId('retry-task-task-wave0');
    await user.click(retryBtn);
    await waitFor(() => {
      expect(retryPostCalls).toEqual(['/v1/control-plane/runs/run-1/tasks/task-wave0/retry']);
    });
  });
});
