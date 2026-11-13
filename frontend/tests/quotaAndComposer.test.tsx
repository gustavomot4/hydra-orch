import { useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PromptComposer } from '@/feature/composer';
import { QuotaAccountsPage } from '@/feature/quota';
import { createHydraQueryClient } from '@/hook/queryClient';
import { NovoChatPage } from '@/page/NovoChatPage';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';

function ControlledDraftHarness({ initialSession }: { initialSession: string }) {
  const [sessionKey, setSessionKey] = useState(initialSession);
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState<'relay' | 'swarm' | 'persistent'>('relay');

  return (
    <div>
      <button type="button" onClick={() => setSessionKey('sess-a')}>
        Ir para Sessão A
      </button>
      <button type="button" onClick={() => setSessionKey('sess-b')}>
        Ir para Sessão B
      </button>
      <span data-testid="current-mode">{mode}</span>
      <PromptComposer
        sessionKey={sessionKey}
        draft={draft}
        onDraftChange={setDraft}
        mode={mode}
        onModeChange={setMode}
        renderAttachControl={<button type="button">Slot Anexos T38</button>}
        renderDictationControl={<button type="button">Slot Ditado T38</button>}
        attachmentChips={<span>arquivo-anexo.md</span>}
      />
    </div>
  );
}

describe('PromptComposer (T33) and QuotaAccountsPage (7:279)', () => {
  it('persists drafts per sessionKey across tab switches and supports T38 render slots + NovoChatPage ComposerSlotProps', async () => {
    const user = userEvent.setup();
    render(<ControlledDraftHarness initialSession="sess-a" />);

    const textarea = screen.getByLabelText('Descreva a tarefa para o coordenador');
    expect(screen.getByRole('button', { name: 'Slot Anexos T38' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Slot Ditado T38' })).toBeInTheDocument();
    expect(screen.getByTestId('composer-attachment-chips')).toHaveTextContent('arquivo-anexo.md');

    await user.type(textarea, 'Rascunho exclusivo da sessao A');
    expect(textarea).toHaveValue('Rascunho exclusivo da sessao A');

    await user.click(screen.getByRole('button', { name: 'Ir para Sessão B' }));
    expect(textarea).toHaveValue('');
    await user.type(textarea, 'Texto da sessao B');

    await user.click(screen.getByRole('button', { name: 'Ir para Sessão A' }));
    expect(textarea).toHaveValue('Rascunho exclusivo da sessao A');

    await user.click(screen.getByRole('button', { name: 'Ir para Sessão B' }));
    expect(textarea).toHaveValue('Texto da sessao B');
  });

  it('supports @ mention popover and / command menu via ArrowUp/ArrowDown/Enter/Escape and integrates with NovoChatPage', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();
    useAuthStore.getState().authenticate('valid-token', 'operator');

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
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
      if (url.includes('/v1/control-plane/runs')) {
        return new Response(
          JSON.stringify({ items: [], total: 0, page: 1, size: 50, pages: 1 }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const qc = createHydraQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <NovoChatPage
            renderComposer={(slotProps) => (
              <PromptComposer {...slotProps} sessionKey="novo-chat-test" />
            )}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const textarea = screen.getByLabelText('Descreva a tarefa para o coordenador');

    // Trigger '/' slash command menu and verify all 5 commands exist
    await user.type(textarea, '/');
    const slashMenu = screen.getByTestId('slash-command-menu');
    expect(within(slashMenu).getByText('/review')).toBeInTheDocument();
    expect(within(slashMenu).getByText('/terminal')).toBeInTheDocument();
    expect(within(slashMenu).getByText('/swarm')).toBeInTheDocument();
    expect(within(slashMenu).getByText('/status')).toBeInTheDocument();
    expect(within(slashMenu).getByText('/limpar')).toBeInTheDocument();

    // Navigate with ArrowDown to /swarm (index 2: /review -> /terminal -> /swarm) and press Enter
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');
    expect(screen.getByLabelText('Modo de orquestração')).toHaveValue('swarm');

    // Trigger '@' mention popover, navigate with keyboard, Escape closes, reopen and Enter selects
    await user.type(textarea, '@');
    expect(screen.getByTestId('mention-popover')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('mention-popover')).toBeNull();

    await user.type(textarea, 'cod');
    expect(screen.getByTestId('mention-popover')).toBeInTheDocument();
    await user.keyboard('{Enter}');
    expect(textarea).toHaveValue('@codex ');

    // Slash command /limpar resets draft
    await user.type(textarea, '/limpar');
    await user.keyboard('{Enter}');
    expect(textarea).toHaveValue('');
  });

  it('reads inventory + /v1/quota, shows — for unknown (never 0%), renders reset_at, rejects sk-... secrets, and applies next-run account override', async () => {
    const user = userEvent.setup();
    useAuthStore.getState().authenticate('valid-token', 'operator');

    const postAccountCalls: Array<Record<string, unknown>> = [];
    let currentOverrides: Record<string, unknown> = {};

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.includes('/v1/control-plane/omniroute/inventory') && method === 'GET') {
        return new Response(
          JSON.stringify({
            connection_mode: 'optional',
            direct_mode_supported: true,
            available: true,
            models: [
              { id: 'claude-sonnet-4', provider: 'claude', owned_by: 'anthropic' },
              { id: 'gpt-5-codex', provider: 'codex', owned_by: 'openai' },
            ],
            accounts: [
              {
                account_id: 'acct-claude-work',
                provider: 'claude_pro',
                label: 'Claude Trabalho',
                quota_key: 'claude_pro',
                status: 'observed',
                remaining_percent: 72,
                resets_in_seconds: 5400,
                reset_at: '2026-11-13T18:00:00Z',
                observed_at: '2026-11-13T12:00:00Z',
                source: 'omniroute:accounts_api',
              },
              {
                account_id: 'acct-claude-backup',
                provider: 'claude_pro',
                label: 'Claude Backup',
                quota_key: 'claude_pro',
                status: 'observed',
                remaining_percent: 91,
                resets_in_seconds: 7200,
                observed_at: '2026-11-13T12:00:00Z',
                source: 'omniroute:accounts_api',
              },
            ],
            quota: {
              status: 'observed',
              claude_pro: {
                status: 'observed',
                remaining_percent: 72,
                resets_in_seconds: 5400,
                reset_at: '2026-11-13T18:00:00Z',
                source: 'omniroute:quota_api',
              },
              chatgpt_plus: {
                status: 'stale',
                remaining_percent: 38,
                resets_in_seconds: 1800,
                source: 'omniroute:cache',
              },
              gemini_pro: {
                status: 'unknown',
                remaining_percent: null,
                resets_in_seconds: null,
              },
            },
            next_account_overrides: currentOverrides,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/v1/quota') && method === 'GET') {
        return new Response(
          JSON.stringify({
            status: 'observed',
            claude_pro: {
              status: 'observed',
              remaining_percent: 72,
              resets_in_seconds: 5400,
              reset_at: '2026-11-13T18:00:00Z',
              source: 'omniroute:quota_api',
            },
            chatgpt_plus: {
              status: 'stale',
              remaining_percent: 38,
              resets_in_seconds: 1800,
              source: 'omniroute:cache',
            },
            gemini_pro: {
              status: 'unknown',
              remaining_percent: null,
              resets_in_seconds: null,
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/v1/control-plane/omniroute/account') && method === 'POST') {
        const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
        postAccountCalls.push(body);
        const override = {
          scope_id: String(body.scope_id ?? 'default'),
          provider: String(body.provider),
          account_id: String(body.account_id),
          selected_by: 'operator',
          selected_at: '2026-11-13T12:15:00Z',
          applies_to: 'next_run',
        };
        currentOverrides = { ...currentOverrides, [String(body.provider)]: override };
        return new Response(JSON.stringify(override), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return new Response(JSON.stringify({}), { status: 404 });
    });

    vi.stubGlobal('fetch', fetchMock);
    const qc = createHydraQueryClient();

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <QuotaAccountsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const claudeCard = await screen.findByTestId('provider-quota-card-claude_pro');
    expect(claudeCard).toHaveAttribute('data-quota-status', 'observed');
    expect(screen.getByTestId('provider-quota-percent-claude_pro')).toHaveTextContent('72%');
    expect(screen.getByTestId('provider-reset-at-claude_pro')).toHaveAttribute(
      'datetime',
      '2026-11-13T18:00:00Z',
    );
    expect(within(claudeCard).getByText('claude-sonnet-4')).toBeInTheDocument();

    const codexCard = screen.getByTestId('provider-quota-card-chatgpt_plus');
    expect(codexCard).toHaveAttribute('data-quota-status', 'stale');
    expect(screen.getByTestId('provider-quota-percent-chatgpt_plus')).toHaveTextContent('38%');

    // Unknown metric MUST render "—", NEVER "0%"
    const geminiCard = screen.getByTestId('provider-quota-card-gemini_pro');
    expect(geminiCard).toHaveAttribute('data-quota-status', 'unknown');
    expect(screen.getByTestId('provider-quota-percent-gemini_pro')).toHaveTextContent('—');
    expect(within(geminiCard).queryByText('0%')).toBeNull();

    // Explicit badge "Aplica apenas às próximas execuções"
    expect(screen.getAllByText('Aplica apenas às próximas execuções').length).toBeGreaterThanOrEqual(
      1,
    );

    // Both endpoints GET /v1/control-plane/omniroute/inventory and GET /v1/quota were fetched
    const requestedUrls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(requestedUrls.some((u) => u.includes('/v1/control-plane/omniroute/inventory'))).toBe(true);
    expect(requestedUrls.some((u) => u.endsWith('/v1/quota'))).toBe(true);

    // Client-side rejection of secret sk-... prefix without sending POST
    const claudeInput = within(claudeCard).getByPlaceholderText('ex.: conta-trabalho-1');
    await user.type(claudeInput, 'sk-ant-secret-999999');
    expect(screen.getByTestId('account-error-claude_pro')).toHaveTextContent(/sk-/i);
    expect(screen.getByTestId('apply-account-claude_pro')).toBeDisabled();
    expect(postAccountCalls).toHaveLength(0);

    // Valid account selection calls POST /v1/control-plane/omniroute/account
    await user.clear(claudeInput);
    await user.selectOptions(
      within(claudeCard).getByLabelText('Selecionar conta Claude (Anthropic)'),
      'acct-claude-backup',
    );
    await user.click(screen.getByTestId('apply-account-claude_pro'));

    await waitFor(() => {
      expect(postAccountCalls).toHaveLength(1);
    });
    expect(postAccountCalls[0]).toMatchObject({
      scope_id: 'default',
      provider: 'claude_pro',
      account_id: 'acct-claude-backup',
    });
  });
});
