import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Gauge, RefreshCw, Server } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError, QuotaStatusPayload } from '@/type/controlPlane';
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
  const [feedback, setFeedback] = useState<{ kind: 'ok' | 'error'; text: string } | null>(
    null,
  );

  const inventoryQuery = useQuery<QuotaInventoryExtended>({
    queryKey: ['control-plane', 'omniroute-inventory', scopeId],
    queryFn: () =>
      client.getOmniRouteInventory(scopeId) as Promise<QuotaInventoryExtended>,
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
      : inventory?.quota?.status ?? 'unknown';

  const isLoading = inventoryQuery.isLoading && quotaQuery.isLoading;
  const loadError = inventoryQuery.error ?? quotaQuery.error;

  const refreshAll = () => {
    void inventoryQuery.refetch();
    void quotaQuery.refetch();
  };

  return (
    <div
      data-testid="quota-accounts-page"
      className="mx-auto flex min-h-full w-full max-w-6xl flex-col gap-6 bg-[#141414] px-4 py-6 text-[#E8E8E8] md:px-8"
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[#303030] pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Gauge aria-hidden="true" className="h-5 w-5 text-[#969696]" />
            <h1 className="text-xl font-semibold tracking-tight text-[#E8E8E8]">
              Contas e consumo
            </h1>
            <StatusBadge status={overallStatus} />
          </div>
          <p className="text-xs text-[#969696]">
            Monitoramento das janelas de 5h por provedor, origem observada/desatualizada/desconhecida e seleção de conta OmniRoute.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg border border-[#3B82F6]/40 bg-[#3B82F6]/10 px-2.5 py-1 text-xs font-medium text-[#93C5FD]">
            Aplica apenas às próximas execuções
          </span>

          <div className="flex items-center gap-1.5">
            <label htmlFor="quota-scope-input" className="text-xs text-[#969696]">
              Escopo:
            </label>
            <input
              id="quota-scope-input"
              type="text"
              value={scopeId}
              onChange={(e) => setScopeId(e.target.value)}
              className="w-28 rounded-lg border border-[#303030] bg-[#202020] px-2 py-1 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <button
            type="button"
            onClick={refreshAll}
            disabled={inventoryQuery.isFetching || quotaQuery.isFetching}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:opacity-50"
          >
            <RefreshCw
              aria-hidden="true"
              className={`h-3.5 w-3.5 text-[#969696] ${
                inventoryQuery.isFetching || quotaQuery.isFetching
                  ? 'motion-safe:animate-spin'
                  : ''
              }`}
            />
            <span>Atualizar</span>
          </button>
        </div>
      </header>

      <section
        aria-label="Estado do gateway OmniRoute"
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#303030] bg-[#1C1C1C] px-4 py-3 text-xs"
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 font-medium text-[#E8E8E8]">
            <Server aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <span>Gateway OmniRoute:</span>
          </span>
          <span className="rounded border border-[#303030] bg-[#141414] px-2 py-0.5 font-mono text-[#E8E8E8]">
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

        <span className="font-mono text-[11px] text-[#969696]">
          {inventory?.models?.length ?? 0} modelo(s) · {inventory?.accounts?.length ?? 0} conta(s)
        </span>
      </section>

      {feedback ? (
        <div
          role={feedback.kind === 'error' ? 'alert' : 'status'}
          className={`rounded-xl border px-4 py-2.5 text-xs ${
            feedback.kind === 'error'
              ? 'border-[#EF4444]/40 bg-[#EF4444]/10 text-[#FCA5A5]'
              : 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]'
          }`}
        >
          {feedback.text}
        </div>
      ) : null}

      {loadError instanceof Error ? (
        <div
          role="alert"
          className="rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-4 py-3 text-xs text-[#FCA5A5]"
        >
          Não foi possível consultar o inventário completo: {loadError.message}
        </div>
      ) : null}

      {isLoading ? (
        <div className="rounded-xl border border-[#303030] bg-[#202020] p-6 text-sm text-[#969696]">
          Consultando janelas de cota e inventário OmniRoute...
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
              isUpdating={updatingProvider === card.overrideProvider && selectAccountMutation.isPending}
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
        className="rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
          Modelos descobertos via OmniRoute
        </h2>

        {!inventory?.models?.length ? (
          <p className="mt-2 text-xs text-[#969696]">
            Nenhum modelo ativo retornado pelo gateway (ou operando em modo direto sem fabricação de entradas).
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-[#303030] text-[11px] text-[#969696]">
                  <th className="py-1.5 pr-4 font-medium">Modelo</th>
                  <th className="py-1.5 pr-4 font-medium">Provedor</th>
                  <th className="py-1.5 font-medium">Proprietário</th>
                </tr>
              </thead>
              <tbody>
                {inventory.models.map((m) => (
                  <tr key={m.id} className="border-b border-[#303030]/60 last:border-b-0">
                    <td className="py-2 pr-4 font-mono text-[#E8E8E8]">{m.id}</td>
                    <td className="py-2 pr-4 font-mono text-[#969696]">{m.provider}</td>
                    <td className="py-2 font-mono text-[#969696]">{m.owned_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
