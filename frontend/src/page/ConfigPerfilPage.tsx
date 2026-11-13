import { FormEvent, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  KeyRound,
  Keyboard,
  LogOut,
  RotateCcw,
  Shield,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useCapabilities } from '@/hook/useCapabilities';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { DensityMode, useLayoutStore } from '@/store/layoutStore';
import {
  ControlPlaneApiError,
  Preference,
  TokenMetadata,
} from '@/type/controlPlane';

const KEYBOARD_SHORTCUTS = [
  { keys: 'Ctrl + B', description: 'Recolher ou expandir barra lateral' },
  { keys: 'Ctrl + K', description: 'Focar busca de projetos e sessões' },
  { keys: 'Alt + S', description: 'Alternar painel único / dividido' },
  { keys: 'Alt + W', description: 'Fechar aba ativa no painel em foco' },
  { keys: 'Alt + 1 / Alt + 2', description: 'Alternar foco entre painel principal e secundário' },
];

export function ConfigPerfilPage() {
  const queryClient = useQueryClient();
  const client = useControlPlaneClient();
  const principalId = useAuthStore((s) => s.principalId) ?? 'operator';
  const logout = useAuthStore((s) => s.logout);

  const density = useLayoutStore((s) => s.density);
  const reducedMotion = useLayoutStore((s) => s.reducedMotion);
  const keyboardHintsVisible = useLayoutStore((s) => s.keyboardHintsVisible);
  const setDensity = useLayoutStore((s) => s.setDensity);
  const setReducedMotion = useLayoutStore((s) => s.setReducedMotion);
  const setKeyboardHintsVisible = useLayoutStore((s) => s.setKeyboardHintsVisible);

  const { hosts } = useCapabilities();

  const [prefFeedback, setPrefFeedback] = useState<{ kind: 'ok' | 'error'; text: string } | null>(
    null,
  );
  const [tokenFeedback, setTokenFeedback] = useState<{ kind: 'ok' | 'error'; text: string } | null>(
    null,
  );
  const [issuedSessionTokens, setIssuedSessionTokens] = useState<TokenMetadata[]>([]);
  const [newTokenScopes, setNewTokenScopes] = useState('read,write');

  const preferencesQuery = useQuery<Preference[]>({
    queryKey: ['control-plane', 'preferences', principalId],
    queryFn: () => client.listPreferences('user', principalId),
    retry: false,
  });

  const tokensQuery = useQuery({
    queryKey: ['control-plane', 'tokens'],
    queryFn: () => client.listTokens(),
    retry: false,
  });

  useEffect(() => {
    const items = preferencesQuery.data;
    if (!items) {
      return;
    }
    for (const pref of items) {
      try {
        const val = JSON.parse(pref.value_json);
        if (pref.key === 'ui.density' && (val === 'compact' || val === 'comfortable')) {
          setDensity(val);
        } else if (pref.key === 'ui.reduced_motion' && typeof val === 'boolean') {
          setReducedMotion(val);
        } else if (pref.key === 'ui.keyboard_hints' && typeof val === 'boolean') {
          setKeyboardHintsVisible(val);
        }
      } catch {
        // Ignora preferência com JSON não esperado
      }
    }
  }, [preferencesQuery.data, setDensity, setReducedMotion, setKeyboardHintsVisible]);

  const savePreferenceMutation = useMutation({
    mutationFn: async (input: { key: string; value: unknown }) => {
      const existing = preferencesQuery.data?.find((p) => p.key === input.key);
      const idempotencyKey = `pref-${input.key}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
      return client.setPreference({
        scope_type: 'user',
        scope_id: principalId,
        key: input.key,
        value: input.value,
        source: 'explicit',
        expected_version: existing?.version,
        idempotency_key: idempotencyKey,
      });
    },
    retry: false,
    onSuccess: (saved) => {
      setPrefFeedback({
        kind: 'ok',
        text: `Preferência ${saved.key} salva (versão ${saved.version}).`,
      });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'preferences'] });
    },
    onError: (err) => {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : 'Não foi possível salvar a preferência.';
      setPrefFeedback({ kind: 'error', text: msg });
    },
  });

  const revertPreferenceMutation = useMutation({
    mutationFn: async (key: string) => {
      const existing = preferencesQuery.data?.find((p) => p.key === key);
      const idempotencyKey = `rev-${key}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
      return client.revertPreference({
        scope_type: 'user',
        scope_id: principalId,
        key,
        expected_version: existing?.version,
        idempotency_key: idempotencyKey,
      });
    },
    retry: false,
    onSuccess: () => {
      setPrefFeedback({ kind: 'ok', text: 'Preferência revertida com sucesso.' });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'preferences'] });
    },
    onError: (err) => {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : 'Não foi possível reverter a preferência.';
      setPrefFeedback({ kind: 'error', text: msg });
    },
  });

  const createTokenMutation = useMutation({
    mutationFn: async () => {
      const scopes = newTokenScopes
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
      return client.createToken({
        principal_id: principalId,
        scopes: scopes.length > 0 ? scopes : ['read'],
        expires_at: expiresAt,
        redact_token: true,
      });
    },
    retry: false,
    onSuccess: (created) => {
      setIssuedSessionTokens((prev) => [created, ...prev]);
      setTokenFeedback({
        kind: 'ok',
        text: `Token ${created.id} emitido sem exposição de hash/segredo na interface.`,
      });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'tokens'] });
    },
    onError: (err) => {
      const msg =
        err instanceof ControlPlaneApiError ? err.payload.message : 'Erro ao emitir token.';
      setTokenFeedback({ kind: 'error', text: msg });
    },
  });

  const revokeTokenMutation = useMutation({
    mutationFn: (tokenId: string) => client.revokeToken(tokenId),
    retry: false,
    onSuccess: (revoked) => {
      setIssuedSessionTokens((prev) =>
        prev.map((item) => (item.id === revoked.id ? revoked : item)),
      );
      setTokenFeedback({ kind: 'ok', text: `Token ${revoked.id} revogado.` });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'tokens'] });
    },
    onError: (err) => {
      const msg =
        err instanceof ControlPlaneApiError ? err.payload.message : 'Erro ao revogar token.';
      setTokenFeedback({ kind: 'error', text: msg });
    },
  });

  const combinedTokens: TokenMetadata[] = [
    ...(tokensQuery.data?.items ?? []),
    ...issuedSessionTokens.filter(
      (st) => !(tokensQuery.data?.items ?? []).some((remote) => remote.id === st.id),
    ),
  ];

  const handleSaveAll = async (event: FormEvent) => {
    event.preventDefault();
    setPrefFeedback(null);
    try {
      await savePreferenceMutation.mutateAsync({ key: 'ui.density', value: density });
      await savePreferenceMutation.mutateAsync({
        key: 'ui.reduced_motion',
        value: reducedMotion,
      });
      await savePreferenceMutation.mutateAsync({
        key: 'ui.keyboard_hints',
        value: keyboardHintsVisible,
      });
    } catch {
      // Erro tratado em onError da mutation
    }
  };

  return (
    <div
      data-testid="config-perfil-page"
      className="mx-auto w-full max-w-4xl space-y-6 px-4 py-8 md:px-8"
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#303030] pb-4">
        <div>
          <h1 className="text-xl font-semibold text-[#E8E8E8]">Configurações e perfil</h1>
          <p className="text-xs text-[#969696]">
            Preferências versionadas, acessibilidade WCAG AA, metadados de acesso e capacidades do host.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status="connected" labelOverride={`Principal: ${principalId}`} />
          <button
            type="button"
            onClick={logout}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] hover:bg-[#282828]"
          >
            <LogOut aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Encerrar sessão</span>
          </button>
        </div>
      </header>

      <section
        aria-labelledby="pref-section-title"
        className="rounded-2xl border border-[#303030] bg-[#202020] p-5"
      >
        <div className="flex items-center gap-2">
          <SlidersHorizontal aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h2 id="pref-section-title" className="text-sm font-semibold text-[#E8E8E8]">
            Tema, densidade e acessibilidade
          </h2>
        </div>

        <form onSubmit={handleSaveAll} className="mt-4 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-[#303030] bg-[#141414] p-3">
              <div className="text-xs font-medium text-[#E8E8E8]">Tema visual</div>
              <p className="mt-0.5 text-[11px] text-[#969696]">
                Paleta escura neutra Figma (#141414 / #1C1C1C / #202020) com contraste WCAG AA.
              </p>
              <div className="mt-2 inline-flex rounded-md border border-[#303030] bg-[#202020] px-2.5 py-1 text-xs text-[#E8E8E8]">
                Escuro canônico ativo
              </div>
            </div>

            <div className="rounded-xl border border-[#303030] bg-[#141414] p-3">
              <label
                htmlFor="config-density-select"
                className="block text-xs font-medium text-[#E8E8E8]"
              >
                Densidade da interface
              </label>
              <select
                id="config-density-select"
                value={density}
                onChange={(e) => setDensity(e.target.value as DensityMode)}
                className="mt-2 w-full rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
              >
                <option value="comfortable">Confortável (14px padrão)</option>
                <option value="compact">Compacta (13px denso)</option>
              </select>
            </div>
          </div>

          <div className="space-y-2 rounded-xl border border-[#303030] bg-[#141414] p-3">
            <label className="flex cursor-pointer items-center justify-between gap-3 py-1">
              <div>
                <div className="text-xs font-medium text-[#E8E8E8]">Reduzir movimento</div>
                <div className="text-[11px] text-[#969696]">
                  Desativa transições e animações de carregamento (respeita prefers-reduced-motion).
                </div>
              </div>
              <input
                type="checkbox"
                checked={reducedMotion}
                onChange={(e) => setReducedMotion(e.target.checked)}
                aria-label="Reduzir movimento"
                className="h-4 w-4 accent-[#3B82F6]"
              />
            </label>

            <label className="flex cursor-pointer items-center justify-between gap-3 border-t border-[#303030] pt-2">
              <div>
                <div className="text-xs font-medium text-[#E8E8E8]">
                  Exibir dicas de atalhos de teclado
                </div>
                <div className="text-[11px] text-[#969696]">
                  Mantém anéis de foco visíveis (2px) e legendas de atalhos na barra e painéis.
                </div>
              </div>
              <input
                type="checkbox"
                checked={keyboardHintsVisible}
                onChange={(e) => setKeyboardHintsVisible(e.target.checked)}
                aria-label="Exibir dicas de atalhos de teclado"
                className="h-4 w-4 accent-[#3B82F6]"
              />
            </label>
          </div>

          {prefFeedback ? (
            <div
              role={prefFeedback.kind === 'error' ? 'alert' : 'status'}
              className={`rounded-lg border px-3 py-2 text-xs ${
                prefFeedback.kind === 'error'
                  ? 'border-[#EF4444]/40 bg-[#EF4444]/10 text-[#FCA5A5]'
                  : 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]'
              }`}
            >
              {prefFeedback.text}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={savePreferenceMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3.5 py-2 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-60"
            >
              <Check aria-hidden="true" className="h-3.5 w-3.5" />
              <span>
                {savePreferenceMutation.isPending ? 'Salvando...' : 'Salvar preferências'}
              </span>
            </button>

            <button
              type="button"
              disabled={revertPreferenceMutation.isPending}
              onClick={() => revertPreferenceMutation.mutate('ui.density')}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#141414] px-3 py-2 text-xs text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-60"
            >
              <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Reverter densidade</span>
            </button>
          </div>
        </form>
      </section>

      <section
        aria-labelledby="tokens-section-title"
        className="rounded-2xl border border-[#303030] bg-[#202020] p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <KeyRound aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h2 id="tokens-section-title" className="text-sm font-semibold text-[#E8E8E8]">
              Metadados de tokens (/v1/control-plane/tokens)
            </h2>
          </div>
          <span className="font-mono text-[11px] text-[#969696]">
            hashes e segredos ocultos por contrato
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[200px]">
            <label htmlFor="new-token-scopes" className="mb-1 block text-xs text-[#969696]">
              Escopos para emissão
            </label>
            <input
              id="new-token-scopes"
              type="text"
              value={newTokenScopes}
              onChange={(e) => setNewTokenScopes(e.target.value)}
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>
          <button
            type="button"
            disabled={createTokenMutation.isPending}
            onClick={() => createTokenMutation.mutate()}
            className="rounded-lg bg-[#E8E8E8] px-3.5 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-60"
          >
            {createTokenMutation.isPending ? 'Emitindo...' : 'Emitir metadado de token'}
          </button>
        </div>

        {tokenFeedback ? (
          <div
            role={tokenFeedback.kind === 'error' ? 'alert' : 'status'}
            className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
              tokenFeedback.kind === 'error'
                ? 'border-[#EF4444]/40 bg-[#EF4444]/10 text-[#FCA5A5]'
                : 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]'
            }`}
          >
            {tokenFeedback.text}
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {tokensQuery.data && !tokensQuery.data.supported && combinedTokens.length === 0 ? (
            <p className="text-xs text-[#969696]">
              Listagem remota de tokens não exposta nesta instância; tokens emitidos nesta sessão aparecerão aqui apenas por metadados não secretos.
            </p>
          ) : combinedTokens.length === 0 ? (
            <p className="text-xs text-[#969696]">Nenhum metadado de token registrado.</p>
          ) : (
            combinedTokens.map((tok) => (
              <div
                key={tok.id}
                data-testid={`token-meta-${tok.id}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#303030] bg-[#141414] px-3 py-2 text-xs"
              >
                <div className="space-y-0.5">
                  <div className="font-mono text-[#E8E8E8]">
                    {tok.id} · {tok.principal_id}
                  </div>
                  <div className="text-[11px] text-[#969696]">
                    Escopos: {tok.scopes.join(', ')}
                    {tok.expires_at ? ` · Expira: ${tok.expires_at}` : ''}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={tok.revoked_at ? 'cancelled' : 'active'} compact />
                  {!tok.revoked_at ? (
                    <button
                      type="button"
                      onClick={() => revokeTokenMutation.mutate(tok.id)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] hover:bg-[#282828]"
                    >
                      <Trash2 aria-hidden="true" className="h-3 w-3" />
                      <span>Revogar</span>
                    </button>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section
        aria-labelledby="shortcuts-section-title"
        className="rounded-2xl border border-[#303030] bg-[#202020] p-5"
      >
        <div className="flex items-center gap-2">
          <Keyboard aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h2 id="shortcuts-section-title" className="text-sm font-semibold text-[#E8E8E8]">
            Atalhos de teclado
          </h2>
        </div>

        <ul className="mt-3 divide-y divide-[#303030] rounded-xl border border-[#303030] bg-[#141414]">
          {KEYBOARD_SHORTCUTS.map((sc) => (
            <li key={sc.keys} className="flex items-center justify-between gap-4 px-3 py-2 text-xs">
              <span className="text-[#969696]">{sc.description}</span>
              <kbd className="rounded border border-[#303030] bg-[#202020] px-2 py-0.5 font-mono text-[11px] text-[#E8E8E8]">
                {sc.keys}
              </kbd>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="capabilities-section-title"
        className="rounded-2xl border border-[#303030] bg-[#202020] p-5"
      >
        <div className="flex items-center gap-2">
          <Shield aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h2 id="capabilities-section-title" className="text-sm font-semibold text-[#E8E8E8]">
            Capacidades declaradas por host (HostCapabilities)
          </h2>
        </div>

        <div className="mt-4 space-y-4">
          {hosts.length === 0 ? (
            <p className="text-xs text-[#969696]">Aguardando capacidades de bootstrap...</p>
          ) : (
            hosts.map((host) => (
              <div
                key={host.host_id}
                data-testid={`host-capabilities-${host.host_id}`}
                className="rounded-xl border border-[#303030] bg-[#141414] p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="font-mono text-xs font-semibold text-[#E8E8E8]">
                      {host.host_id} ({host.transport_type})
                    </h3>
                    {host.platform ? (
                      <p className="text-[11px] text-[#969696]">Plataforma: {host.platform}</p>
                    ) : null}
                  </div>
                  <StatusBadge status={host.certified ? 'available' : 'degraded'} compact />
                </div>

                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {(
                    [
                      [
                        'pty',
                        'Terminal PTY',
                        host.capabilities.pty.status,
                        [host.capabilities.pty.backend_kind, host.capabilities.pty.reason]
                          .filter(Boolean)
                          .join(' · ') || null,
                      ],
                      ['attachments', 'Anexos', host.capabilities.attachments.status, host.capabilities.attachments.reason],
                      ['quickopen', 'Busca global', host.capabilities.quickopen.status, host.capabilities.quickopen.reason],
                      ['preview', 'Preview seguro', host.capabilities.preview.status, host.capabilities.preview.reason],
                      ['scheduler', 'Automações', host.capabilities.scheduler.status, host.capabilities.scheduler.reason],
                      [
                        'dictation_stt',
                        'Ditado STT',
                        host.capabilities.dictation_stt.status,
                        host.capabilities.dictation_stt.duplex_voice_enabled
                          ? 'voz_duplex_ativa'
                          : 'apenas_rascunho_revisavel',
                      ],
                      [
                        'mobile_emulator',
                        'Emulador móvel (F07)',
                        host.capabilities.mobile_emulator.status,
                        host.capabilities.mobile_emulator.reason,
                      ],
                      [
                        'computer_use',
                        'Computer Use (F07)',
                        host.capabilities.computer_use.status,
                        host.capabilities.computer_use.reason,
                      ],
                    ] as const
                  ).map(([capKey, label, status, reason]) => (
                    <div
                      key={capKey}
                      className="flex items-center justify-between gap-2 rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-2 text-xs"
                    >
                      <div className="min-w-0">
                        <div className="font-medium text-[#E8E8E8]">{label}</div>
                        {reason ? (
                          <div className="truncate font-mono text-[10px] text-[#969696]">
                            {reason}
                          </div>
                        ) : null}
                      </div>
                      <StatusBadge status={status} compact />
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
