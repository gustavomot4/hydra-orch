import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Gauge, RefreshCw, Server } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError, QuotaStatusPayload } from '@/type/controlPlane';
import { ModelCatalog } from './ModelCatalog';
import { ProviderQuotaCard } from './ProviderQuotaCard';
import {
  mergeProviderQuotaCards,
  QuotaInventoryExtended,
  QuotaStatusExtended,
  selectNextOmniRouteAccount,
} from './quotaApi';

export interface QuotaAccountsPageProps {
  scopeId?: string;
}

export function QuotaAccountsPage({ scopeId: initialScopeId = 'default' }: QuotaAccountsPageProps) {
  const queryClient = useQueryClient();
  const client = useControlPlaneClient();

  const [scopeId, setScopeId] = useState(initialScopeId);
  const [updatingProvider, setUpdatingProvider] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const inventoryQuery = useQuery<QuotaInventoryExtended>({
    queryKey: ['control-plane', 'omniroute-inventory', scopeId],
    queryFn: () => client.getOmniRouteInventory(scopeId) as Promise<QuotaInventoryExtended>,
    retry: false,
    staleTime: 15_000,
  });

  const quotaQuery = useQuery<QuotaStatusPayload>({
    queryKey: ['control-plane', 'quota'],
    queryFn: () => client.getQuota(),
    retry: false,
    staleTime: 15_000,
  });

  const selectAccountMutation = useMutation({
    mutationFn: async (input: { provider: string; accountId: string }) => {
      setUpdatingProvider(input.provider);
      return selectNextOmniRouteAccount(client, {
        scope_id: scopeId,
        provider: input.provider,
        account_id: input.accountId,
        validate_against_gateway: false,
      });
    },
    retry: false,
    onSuccess: (override) => {
      setFeedback({
        kind: 'ok',
        text: `Conta "${override.account_id}" definida para "${override.provider}" — Aplica apenas às próximas execuções.`,
      });
      void queryClient.invalidateQueries({
        queryKey: ['control-plane', 'omniroute-inventory'],
      });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'quota'] });
    },
    onError: (err) => {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : err instanceof Error
            ? err.message
            : 'Falha ao definir conta para as próximas execuções.';
      setFeedback({ kind: 'error', text: msg });
    },
    onSettled: () => {
      setUpdatingProvider(null);
    },
  });

  const inventory = inventoryQuery.data ?? null;
  const directQuota = (quotaQuery.data as QuotaStatusExtended | undefined) ?? null;

  const providerCards = useMemo(
    () => mergeProviderQuotaCards(inventory, directQuota),
    [inventory, directQuota],
  );

  const overallStatus =
    directQuota?.status && directQuota.status !== 'unknown'
      ? directQuota.status
      : (inventory?.quota?.status ?? 'unknown');

  const isLoading = inventoryQuery.isLoading && quotaQuery.isLoading;
  const loadError = inventoryQuery.error ?? quotaQuery.error;

  const refreshAll = () => {
    void inventoryQuery.refetch();
    void quotaQuery.refetch();
  };

  return (
    <div
      data-testid="quota-accounts-page"
      className="mx-auto flex min-h-full w-full max-w-6xl flex-col gap-5 bg-[var(--bg-main)] px-4 py-6 text-[var(--text-primary)] md:px-8"
    >
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Gauge aria-hidden="true" className="h-5 w-5 text-[var(--text-muted)]" />
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Contas e consumo
          </h1>
          <StatusBadge status={overallStatus} />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg border border-[var(--status-info)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs font-medium text-[var(--status-info)]">
            Aplica apenas às próximas execuções
          </span>

          <div className="flex items-center gap-1.5">
            <label htmlFor="quota-scope-input" className="text-xs text-[var(--text-muted)]">
              Escopo:
            </label>
            <input
              id="quota-scope-input"
              type="text"
              value={scopeId}
              onChange={(e) => setScopeId(e.target.value)}
              className="min-h-[32px] w-28 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
            />
          </div>

          <button
            type="button"
            onClick={refreshAll}
            disabled={inventoryQuery.isFetching || quotaQuery.isFetching}
            className="inline-flex min-h-[32px] min-w-[24px] items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:opacity-50 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
          >
            <RefreshCw
              aria-hidden="true"
              className={`h-3.5 w-3.5 text-[var(--text-muted)] ${
                inventoryQuery.isFetching || quotaQuery.isFetching ? 'motion-safe:animate-spin' : ''
              }`}
            />
            <span>Atualizar</span>
          </button>
        </div>
      </header>

      <section
        aria-label="Estado do gateway OmniRoute"
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-sidebar)] px-4 py-3 text-xs"
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 font-medium text-[var(--text-primary)]">
            <Server aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
            <span>OmniRoute:</span>
          </span>
          <span className="rounded border border-[var(--border)] bg-[var(--bg-main)] px-2 py-0.5 text-[var(--text-primary)]">
            modo {inventory?.connection_mode ?? '—'}
          </span>
          <StatusBadge
            status={
              inventory?.available
                ? 'available'
                : inventory?.connection_mode === 'disabled'
                  ? 'ready'
                  : 'unavailable'
            }
            labelOverride={
              inventory?.available
                ? 'Gateway ativo'
                : inventory?.connection_mode === 'disabled'
                  ? 'Modo direto'
                  : 'Gateway indisponível'
            }
            compact
          />
        </div>

        <span className="tabular-nums text-xs text-[var(--text-muted)]">
          {inventory?.models?.length ?? 0} modelo(s), {inventory?.accounts?.length ?? 0} conta(s)
        </span>
      </section>

      {feedback ? (
        <div
          role={feedback.kind === 'error' ? 'alert' : 'status'}
          className={`rounded-xl border bg-[var(--bg-surface)] px-4 py-2.5 text-xs ${
            feedback.kind === 'error'
              ? 'border-[var(--status-error)] text-[var(--status-error)]'
              : 'border-[var(--status-success)] text-[var(--status-success)]'
          }`}
        >
          {feedback.text}
        </div>
      ) : null}

      {loadError instanceof Error ? (
        <div
          role="alert"
          className="rounded-xl border border-[var(--status-error)] bg-[var(--bg-surface)] px-4 py-3 text-xs text-[var(--status-error)]"
        >
          Não foi possível consultar o inventário completo: {loadError.message}
        </div>
      ) : null}

      {isLoading ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 text-sm text-[var(--text-muted)]">
          Consultando cotas e contas...
        </div>
      ) : (
        <section
          aria-label="Cotas por provedor"
          className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
        >
          {providerCards.map((card) => (
            <ProviderQuotaCard
              key={card.providerKey}
              card={card}
              isUpdating={
                updatingProvider === card.overrideProvider && selectAccountMutation.isPending
              }
              onSelectAccount={async (provider, accountId) => {
                await selectAccountMutation.mutateAsync({ provider, accountId });
              }}
            />
          ))}
        </section>
      )}

      <section
        aria-label="Inventário de modelos descobertos"
        data-testid="discovered-models-section"
        className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-primary)]">
          Modelos OmniRoute
        </h2>

        {!inventory?.models?.length ? (
          <p className="mt-2 text-xs text-[var(--text-muted)]">Nenhum modelo ativo.</p>
        ) : (
          <ModelCatalog
            models={inventory.models}
            title="Todos os modelos"
            label={`Abrir catálogo (${inventory.models.length})`}
          />
        )}
      </section>
    </div>
  );
}
