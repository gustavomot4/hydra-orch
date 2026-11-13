import { FormEvent, useState } from 'react';
import { ArrowRightLeft, Clock, Cpu, ShieldAlert, UserCheck } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import {
  formatResetDisplay,
  ProviderQuotaCardModel,
  validateAccountIdentifier,
} from './quotaApi';

export interface ProviderQuotaCardProps {
  card: ProviderQuotaCardModel;
  onSelectAccount: (provider: string, accountId: string) => Promise<void> | void;
  isUpdating?: boolean;
}

export function ProviderQuotaCard({
  card,
  onSelectAccount,
  isUpdating = false,
}: ProviderQuotaCardProps) {
  const [selectedAccountId, setSelectedAccountId] = useState<string>(
    card.activeOverride?.account_id ?? card.accounts[0]?.account_id ?? '',
  );
  const [manualAccountId, setManualAccountId] = useState<string>('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const isUnknown = card.remainingPercent === null;
  const isStale = card.status === 'stale';
  const resetInfo = formatResetDisplay(card.resetAt, card.resetsInSeconds);

  const defaultAccountId = card.activeOverride?.account_id ?? card.accounts[0]?.account_id ?? '';
  const resolvedSelectedAccount = selectedAccountId || defaultAccountId;

  const effectiveCandidate =
    manualAccountId.trim().length > 0 ? manualAccountId.trim() : resolvedSelectedAccount.trim();

  const liveValidation =
    manualAccountId.trim().length > 0
      ? validateAccountIdentifier(manualAccountId)
      : resolvedSelectedAccount.trim().length > 0
        ? validateAccountIdentifier(resolvedSelectedAccount)
        : null;

  const activeSecretWarning =
    liveValidation && !liveValidation.valid ? liveValidation.reason : null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const check = validateAccountIdentifier(effectiveCandidate);
    if (!check.valid) {
      setValidationError(check.reason ?? 'Identificador de conta inválido.');
      return;
    }
    setValidationError(null);
    await onSelectAccount(card.overrideProvider, effectiveCandidate);
    setManualAccountId('');
  };

  return (
    <article
      data-testid={`provider-quota-card-${card.providerKey}`}
      data-quota-status={card.status}
      className="flex flex-col justify-between rounded-xl border border-[#303030] bg-[#202020] p-4 text-left"
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-[#E8E8E8]">{card.displayName}</h2>
            <p className="font-mono text-[11px] text-[#969696]">
              {card.windowLabel} · fonte: {card.source}
            </p>
          </div>
          <StatusBadge status={card.status} />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs text-[#969696]">Disponibilidade da janela</span>
            <span
              data-testid={`provider-quota-percent-${card.providerKey}`}
              className={`font-mono text-lg font-semibold tabular-nums ${
                isUnknown ? 'text-[#969696]' : 'text-[#E8E8E8]'
              }`}
            >
              {card.displayPercent}
            </span>
          </div>

          <div
            role="progressbar"
            aria-label={`Cota ${card.displayName}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={card.remainingPercent ?? undefined}
            aria-valuetext={isUnknown ? 'Desconhecido' : card.displayPercent}
            className="h-2 w-full overflow-hidden rounded-full bg-[#141414]"
          >
            {!isUnknown ? (
              <div
                className={`h-full rounded-full transition-all ${
                  isStale ? 'bg-[#F59E0B]/80' : 'bg-[#E8E8E8]'
                }`}
                style={{ width: `${card.remainingPercent}%` }}
              />
            ) : null}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#969696]">
            <span className="inline-flex items-center gap-1">
              <Clock aria-hidden="true" className="h-3 w-3" />
              <span>Reset: </span>
              {resetInfo.isoTimestamp ? (
                <time
                  dateTime={resetInfo.isoTimestamp}
                  data-testid={`provider-reset-at-${card.providerKey}`}
                  className="font-mono text-[#E8E8E8]"
                >
                  {resetInfo.label} ({resetInfo.isoTimestamp})
                </time>
              ) : (
                <span className="font-mono text-[#E8E8E8]">{resetInfo.label}</span>
              )}
            </span>

            {card.observedAt ? (
              <span className="font-mono text-[10px] text-[#969696]">
                Obs: {formatResetDisplay(card.observedAt, null).label}
              </span>
            ) : null}
          </div>
        </div>

        <div className="border-t border-[#303030] pt-2.5">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-[#969696]">
            <Cpu aria-hidden="true" className="h-3 w-3" />
            <span>Modelos descobertos ({card.models.length})</span>
          </div>
          {card.models.length === 0 ? (
            <p className="mt-1 text-[11px] text-[#969696]">
              Nenhum modelo descoberto para este provedor.
            </p>
          ) : (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {card.models.map((m) => (
                <span
                  key={m.id}
                  className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
                >
                  {m.id}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="mt-4 space-y-2.5 border-t border-[#303030] pt-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          <span className="inline-flex items-center gap-1 text-xs font-medium text-[#E8E8E8]">
            <ArrowRightLeft aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
            <span>Conta OmniRoute</span>
          </span>
          <span className="rounded-md border border-[#3B82F6]/40 bg-[#3B82F6]/10 px-2 py-0.5 text-[10px] font-medium text-[#93C5FD]">
            Aplica apenas às próximas execuções
          </span>
        </div>

        {card.activeOverride ? (
          <div
            data-testid={`active-override-${card.providerKey}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1.5 text-[11px]"
          >
            <span className="inline-flex items-center gap-1 text-[#E8E8E8]">
              <UserCheck aria-hidden="true" className="h-3.5 w-3.5 text-[#22C55E]" />
              <span>
                Próxima conta: <strong className="font-mono">{card.activeOverride.account_id}</strong>
              </span>
            </span>
            <span className="font-mono text-[10px] text-[#969696]">
              {card.activeOverride.applies_to}
            </span>
          </div>
        ) : null}

        {card.accounts.length > 0 ? (
          <div>
            <label
              htmlFor={`account-select-${card.providerKey}`}
              className="sr-only"
            >
              Selecionar conta {card.displayName}
            </label>
            <select
              id={`account-select-${card.providerKey}`}
              value={resolvedSelectedAccount}
              disabled={isUpdating}
              onChange={(e) => {
                setSelectedAccountId(e.target.value);
                setValidationError(null);
              }}
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
            >
              {card.accounts.map((acc) => (
                <option key={acc.account_id} value={acc.account_id}>
                  {acc.label} ({acc.account_id}) ·{' '}
                  {acc.remaining_percent !== null && acc.status !== 'unknown'
                    ? `${Math.round(acc.remaining_percent)}%`
                    : '—'}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div>
          <label
            htmlFor={`account-input-${card.providerKey}`}
            className="block text-[11px] text-[#969696]"
          >
            {card.accounts.length > 0
              ? 'Ou informe outro account_id (sem segredos)'
              : 'Identificador da conta (account_id, sem segredos)'}
          </label>
          <input
            id={`account-input-${card.providerKey}`}
            type="text"
            disabled={isUpdating}
            value={manualAccountId}
            onChange={(e) => {
              setManualAccountId(e.target.value);
              setValidationError(null);
            }}
            placeholder="ex.: conta-trabalho-1"
            className="mt-1 w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>

        {activeSecretWarning || validationError ? (
          <div
            role="alert"
            data-testid={`account-error-${card.providerKey}`}
            className="flex items-start gap-1.5 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1.5 text-xs text-[#FCA5A5]"
          >
            <ShieldAlert aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{activeSecretWarning ?? validationError}</span>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={
            isUpdating ||
            effectiveCandidate.length === 0 ||
            Boolean(activeSecretWarning)
          }
          data-testid={`apply-account-${card.providerKey}`}
          className="w-full rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isUpdating ? 'Aplicando...' : 'Definir para próximas execuções'}
        </button>
      </form>
    </article>
  );
}
