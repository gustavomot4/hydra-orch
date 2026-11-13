import { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Clock } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ProviderQuotaEntry, QuotaMetricStatus, QuotaStatusPayload } from '@/type/controlPlane';

interface ProviderSlot {
  key: 'claude_pro' | 'chatgpt_plus' | 'gemini_pro';
  label: string;
  renderIcon: () => ReactNode;
}

function ClaudeGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5 text-[#D97757]" fill="currentColor">
      <path d="M8 1.2l1.1 3.7 3.2-2.2-1.9 3.4 3.8.5-3.4 1.9 2.5 2.9-3.7-.7-.4 3.8L8 11.4l-1.2 3.1-.4-3.8-3.7.7 2.5-2.9-3.4-1.9 3.8-.5-1.9-3.4 3.2 2.2z" />
    </svg>
  );
}

function CodexGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5 text-[#E8E8E8]" fill="none" stroke="currentColor" strokeWidth="1.4">
      <polygon points="8,1.5 13.8,4.8 13.8,11.2 8,14.5 2.2,11.2 2.2,4.8" />
      <circle cx="8" cy="8" r="2.1" />
    </svg>
  );
}

function AgyGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5 text-[#60A5FA]" fill="currentColor">
      <path d="M8 1.5C8.5 5.1 10.9 7.5 14.5 8c-3.6.5-6 2.9-6.5 6.5C7.5 10.9 5.1 8.5 1.5 8c3.6-.5 6-2.9 6.5-6.5z" />
    </svg>
  );
}

const PROVIDER_SLOTS: ProviderSlot[] = [
  { key: 'claude_pro', label: 'Claude', renderIcon: () => <ClaudeGlyph /> },
  { key: 'chatgpt_plus', label: 'Codex', renderIcon: () => <CodexGlyph /> },
  { key: 'gemini_pro', label: 'Agy', renderIcon: () => <AgyGlyph /> },
];

export interface UsageBarProps {
  quota?: QuotaStatusPayload | null;
  onOpenUsageDetails?: () => void;
}

function resolveSlotEntry(
  quota: QuotaStatusPayload | null | undefined,
  key: ProviderSlot['key'],
): ProviderQuotaEntry {
  const candidate = quota?.[key];
  if (candidate && typeof candidate === 'object') {
    return candidate;
  }
  return {
    status: 'unknown',
    remaining_percent: null,
    resets_in_seconds: null,
  };
}

function normalizeDisplayPercent(entry: ProviderQuotaEntry): {
  status: QuotaMetricStatus;
  numericPercent: number | null;
  displayText: string;
} {
  if (
    entry.status === 'unknown' ||
    entry.remaining_percent === null ||
    !Number.isFinite(entry.remaining_percent)
  ) {
    return {
      status: entry.status === 'stale' ? 'stale' : 'unknown',
      numericPercent: null,
      displayText: '—',
    };
  }
  const clamped = Math.max(0, Math.min(100, Math.round(entry.remaining_percent)));
  return {
    status: entry.status,
    numericPercent: clamped,
    displayText: `${clamped}%`,
  };
}

export function UsageBar({ quota: quotaOverride, onOpenUsageDetails }: UsageBarProps) {
  const token = useAuthStore((s) => s.token);
  const client = useControlPlaneClient();

  const quotaQuery = useQuery<QuotaStatusPayload>({
    queryKey: ['control-plane', 'quota'],
    queryFn: () => client.getQuota(),
    enabled: Boolean(token) && quotaOverride === undefined,
    refetchInterval: 60_000,
    retry: false,
  });

  const quota = quotaOverride !== undefined ? quotaOverride : quotaQuery.data;

  return (
    <div
      data-testid="usage-bar-footer"
      className="border-t border-[#303030] bg-[#1C1C1C] px-3 py-2.5"
    >
      <button
        type="button"
        onClick={onOpenUsageDetails}
        aria-label="Abrir detalhes de contas e consumo"
        title="Ver detalhes de contas e consumo"
        className="w-full space-y-1.5 rounded-lg p-1 text-left transition-colors hover:bg-[#282828]"
      >
        {PROVIDER_SLOTS.map((slot) => {
          const entry = resolveSlotEntry(quota, slot.key);
          const { status, numericPercent, displayText } = normalizeDisplayPercent(entry);
          const isUnknown = numericPercent === null;
          const isStale = status === 'stale';

          return (
            <div
              key={slot.key}
              data-testid={`usage-row-${slot.key}`}
              data-quota-status={status}
              className="grid grid-cols-[16px_1fr_auto] items-center gap-2"
            >
              <span className="flex h-4 w-4 items-center justify-center" title={slot.label}>
                {slot.renderIcon()}
              </span>

              <div
                role="progressbar"
                aria-label={`Cota ${slot.label}`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={numericPercent ?? undefined}
                aria-valuetext={
                  isUnknown
                    ? 'Desconhecido'
                    : isStale
                      ? `${displayText} (desatualizado)`
                      : displayText
                }
                className="h-1.5 w-full overflow-hidden rounded-full bg-[#303030]"
              >
                {!isUnknown ? (
                  <div
                    className={`h-full rounded-full transition-all ${
                      isStale ? 'bg-[#F59E0B]/80' : 'bg-[#E8E8E8]'
                    }`}
                    style={{ width: `${numericPercent}%` }}
                  />
                ) : null}
              </div>

              <span className="inline-flex min-w-[34px] items-center justify-end gap-1 font-mono text-[11px] tabular-nums text-[#969696]">
                {isStale ? (
                  <Clock
                    aria-label="Desatualizado"
                    data-testid={`usage-stale-${slot.key}`}
                    className="h-2.5 w-2.5 text-[#F59E0B]"
                  />
                ) : null}
                <span className={isUnknown ? 'text-[#969696]' : 'text-[#E8E8E8]'}>
                  {displayText}
                </span>
              </span>
            </div>
          );
        })}
      </button>
    </div>
  );
}
