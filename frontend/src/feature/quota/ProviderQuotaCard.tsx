import { FormEvent, useState } from 'react';
import { ArrowRightLeft, Clock, Cpu, ShieldAlert, UserCheck } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { ModelCatalog } from './ModelCatalog';
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
      className="flex flex-col justify-between rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 text-left"
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              {card.displayName}
            </h2>
            <p className="text-xs text-[var(--text-muted)]" title={`Fonte: ${card.source}`}>
              {card.windowLabel}
            </p>
          </div>
          <StatusBadge status={card.status} />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs text-[var(--text-muted)]">Disponível</span>
            <span
              data-testid={`provider-quota-percent-${card.providerKey}`}
              className={`text-lg font-semibold tabular-nums ${
                isUnknown ? 'text-[var(--text-muted)]' : 'text-[var(--text-primary)]'
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
            className="h-2 w-full overflow-hidden rounded-full bg-[var(--bg-main)]"
          >
            {!isUnknown ? (
              <div
                className={`h-full rounded-full transition-all ${
                  isStale ? 'bg-[var(--status-warning)]' : 'bg-[var(--text-primary)]'
                }`}
                style={{ width: `${card.remainingPercent}%` }}
              />
            ) : null}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-1 tabular-nums">
              <Clock aria-hidden="true" className="h-3 w-3" />
              <span>Reset: </span>
              {resetInfo.isoTimestamp ? (
                <time
                  dateTime={resetInfo.isoTimestamp}
                  data-testid={`provider-reset-at-${card.providerKey}`}
                  className="text-[var(--text-primary)]"
                >
                  {resetInfo.label}
                </time>
              ) : (
                <span className="text-[var(--text-primary)]">{resetInfo.label}</span>
              )}
            </span>

            {card.observedAt ? (
              <span className="tabular-nums text-xs text-[var(--text-muted)]">
                Leitura: {formatResetDisplay(card.observedAt, null).label}
              </span>
            ) : null}
          </div>
        </div>

        <div className="border-t border-[var(--border)] pt-2.5">
          <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
            <Cpu aria-hidden="true" className="h-3 w-3" />
            <span>Modelos ({card.models.length})</span>
          </div>
          {card.models.length === 0 ? (
            <p className="mt-1 text-xs text-[var(--text-muted)]">Sem modelos ativos.</p>
          ) : (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {card.models.slice(0, 3).map((m) => (
                <code
                  key={m.id}
                  title={m.id}
                  className="max-w-full truncate rounded border border-[var(--border)] bg-[var(--bg-main)] px-1.5 py-0.5 font-mono text-xs text-[var(--text-primary)]"
                >
                  {m.id}
                </code>
              ))}
            </div>
          )}
          {card.models.length > 0 && (
            <ModelCatalog models={card.models} title={`Modelos de ${card.displayName}`} />
          )}
        </div>
      </div>

      <details className="quota-account-settings mt-3">
        <summary className="flex min-h-[32px] cursor-pointer items-center rounded-md px-1 text-xs font-medium text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]">
          Conta para próximas execuções
        </summary>
        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="mt-3 space-y-2.5 border-t border-[var(--border)] pt-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-1.5">
            <span className="inline-flex items-center gap-1 text-xs font-medium text-[var(--text-primary)]">
              <ArrowRightLeft aria-hidden="true" className="h-3.5 w-3.5 text-[var(--text-muted)]" />
              <span>Conta OmniRoute</span>
            </span>
          </div>

          {card.activeOverride ? (
            <div
              data-testid={`active-override-${card.providerKey}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-rail)] px-2.5 py-1.5 text-xs"
            >
              <span className="inline-flex items-center gap-1 text-[var(--text-primary)]">
                <UserCheck aria-hidden="true" className="h-3.5 w-3.5 text-[var(--status-success)]" />
                <span>
                  Próxima conta:{' '}
                  <code className="font-mono font-semibold">{card.activeOverride.account_id}</code>
                </span>
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {card.activeOverride.applies_to}
              </span>
            </div>
          ) : null}

          {card.accounts.length > 0 ? (
            <div>
              <label htmlFor={`account-select-${card.providerKey}`} className="sr-only">
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
                className="min-h-[32px] w-full rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
              >
                {card.accounts.map((acc) => (
                  <option key={acc.account_id} value={acc.account_id}>
                    {acc.label} ({acc.account_id}) —{' '}
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
              className="block text-xs text-[var(--text-muted)]"
            >
              {card.accounts.length > 0
                ? 'Ou informe outro identificador de conta (sem segredos)'
                : 'Identificador da conta (sem segredos)'}
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
              className="mt-1 min-h-[32px] w-full rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
            />
          </div>

          {activeSecretWarning || validationError ? (
            <div
              role="alert"
              data-testid={`account-error-${card.providerKey}`}
              className="flex items-start gap-1.5 rounded-lg border border-[var(--status-error)] bg-[var(--bg-main)] px-2.5 py-1.5 text-xs text-[var(--status-error)]"
            >
              <ShieldAlert aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{activeSecretWarning ?? validationError}</span>
            </div>
          ) : null}

          <button
            type="submit"
            disabled={
              isUpdating || effectiveCandidate.length === 0 || Boolean(activeSecretWarning)
            }
            data-testid={`apply-account-${card.providerKey}`}
            className="min-h-[32px] w-full rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
          >
            {isUpdating ? 'Aplicando...' : 'Definir para próximas execuções'}
          </button>
        </form>
      </details>
    </article>
  );
}
