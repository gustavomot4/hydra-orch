import { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  AccountOverride,
  OmniRouteAccountItem,
  OmniRouteModelItem,
  ProviderQuotaEntry,
  QuotaInventory,
  QuotaMetricStatus,
  QuotaStatusPayload,
} from '@/type/controlPlane';

export interface QuotaEntryExtended extends ProviderQuotaEntry {
  reset_at?: string | null;
  window_hours?: number | null;
}

export interface OmniRouteAccountExtended extends OmniRouteAccountItem {
  reset_at?: string | null;
}

export type QuotaStatusExtended = QuotaStatusPayload & {
  claude_pro?: QuotaEntryExtended;
  chatgpt_plus?: QuotaEntryExtended;
  gemini_pro?: QuotaEntryExtended;
  [key: string]: QuotaMetricStatus | QuotaEntryExtended | undefined;
};

export interface QuotaInventoryExtended
  extends Omit<QuotaInventory, 'accounts' | 'quota'> {
  accounts: OmniRouteAccountExtended[];
  quota: QuotaStatusExtended;
}

export interface SelectOmniRouteAccountPayload {
  scope_id: string;
  provider: string;
  account_id: string;
  validate_against_gateway?: boolean;
}

export interface ProviderQuotaCardModel {
  providerKey: string;
  overrideProvider: string;
  displayName: string;
  windowLabel: string;
  status: QuotaMetricStatus;
  remainingPercent: number | null;
  displayPercent: string;
  resetsInSeconds: number | null;
  resetAt: string | null;
  observedAt: string | null;
  source: string;
  models: OmniRouteModelItem[];
  accounts: OmniRouteAccountExtended[];
  activeOverride: AccountOverride | null;
}

export interface AccountValidationResult {
  valid: boolean;
  reason: string | null;
}

const SECRET_PATTERNS: Array<{ regex: RegExp; reason: string }> = [
  {
    regex: /(?:^|[\s:=])sk-[A-Za-z0-9_-]*/i,
    reason: 'Segredo detectado (prefixo sk-). Informe apenas o ID da conta, nunca uma chave de API.',
  },
  {
    regex: /(?:^|[\s:=])sk_[A-Za-z0-9_-]{4,}/i,
    reason: 'Segredo detectado (prefixo sk_). Informe apenas o ID da conta, nunca uma chave de API.',
  },
  {
    regex: /\b(?:ghp_|github_pat_|glpat-|xox[baprs]-)[A-Za-z0-9_-]*/i,
    reason: 'Token de provedor detectado. Segredos nunca devem ser inseridos no seletor de contas.',
  },
  {
    regex: /\bBearer\s+\S+/i,
    reason: 'Credencial Bearer detectada. Informe apenas o identificador público da conta.',
  },
  {
    regex: /-----BEGIN\s+(?:[A-Z0-9]+\s+)*PRIVATE KEY-----/i,
    reason: 'Chave privada detectada. Segredos são bloqueados na interface.',
  },
  {
    regex: /\b(?:api[_-]?key|secret|password|passwd|access[_-]?token)\s*[:=]/i,
    reason: 'Atribuição de credencial detectada. Informe apenas o account_id.',
  },
];

export function validateAccountIdentifier(rawInput: string): AccountValidationResult {
  const trimmed = rawInput.trim();
  if (trimmed.length === 0) {
    return { valid: false, reason: 'Informe um identificador de conta válido.' };
  }
  for (const rule of SECRET_PATTERNS) {
    if (rule.regex.test(trimmed)) {
      return { valid: false, reason: rule.reason };
    }
  }
  if (trimmed.length > 128) {
    return {
      valid: false,
      reason: 'O identificador da conta deve ter no máximo 128 caracteres.',
    };
  }
  return { valid: true, reason: null };
}

interface ProviderDefinition {
  key: string;
  overrideProvider: string;
  displayName: string;
  aliases: string[];
}

const STANDARD_PROVIDERS: ProviderDefinition[] = [
  {
    key: 'claude_pro',
    overrideProvider: 'claude_pro',
    displayName: 'Claude (Anthropic)',
    aliases: ['claude_pro', 'claude', 'anthropic'],
  },
  {
    key: 'chatgpt_plus',
    overrideProvider: 'chatgpt_plus',
    displayName: 'Codex / ChatGPT',
    aliases: ['chatgpt_plus', 'codex', 'openai', 'chatgpt'],
  },
  {
    key: 'gemini_pro',
    overrideProvider: 'gemini_pro',
    displayName: 'Agy / Gemini',
    aliases: ['gemini_pro', 'gemini', 'agy', 'antigravity', 'google'],
  },
];

const STATUS_PRIORITY: Record<QuotaMetricStatus, number> = {
  observed: 3,
  stale: 2,
  unknown: 1,
};

function isQuotaEntryObject(val: unknown): val is QuotaEntryExtended {
  return Boolean(val && typeof val === 'object' && !Array.isArray(val) && 'status' in val);
}

function pickBetterQuotaEntry(
  primary?: QuotaEntryExtended | null,
  secondary?: QuotaEntryExtended | null,
): QuotaEntryExtended {
  if (!primary && !secondary) {
    return {
      status: 'unknown',
      remaining_percent: null,
      resets_in_seconds: null,
      reset_at: null,
      source: 'não reportado',
    };
  }
  if (!primary) {
    return secondary!;
  }
  if (!secondary) {
    return primary;
  }
  const pScore = STATUS_PRIORITY[primary.status] ?? 0;
  const sScore = STATUS_PRIORITY[secondary.status] ?? 0;
  const winner = pScore >= sScore ? primary : secondary;
  const fallback = winner === primary ? secondary : primary;
  return {
    ...fallback,
    ...winner,
    reset_at: winner.reset_at ?? fallback.reset_at ?? null,
    observed_at: winner.observed_at ?? fallback.observed_at,
    source: winner.source ?? fallback.source,
  };
}

function normalizePercent(entry: QuotaEntryExtended): {
  status: QuotaMetricStatus;
  remainingPercent: number | null;
  displayPercent: string;
} {
  if (
    entry.status === 'unknown' ||
    entry.remaining_percent === null ||
    typeof entry.remaining_percent !== 'number' ||
    !Number.isFinite(entry.remaining_percent)
  ) {
    return {
      status: entry.status === 'stale' ? 'stale' : 'unknown',
      remainingPercent: null,
      displayPercent: '—',
    };
  }
  const clamped = Math.max(0, Math.min(100, Math.round(entry.remaining_percent)));
  return {
    status: entry.status,
    remainingPercent: clamped,
    displayPercent: `${clamped}%`,
  };
}

export function formatResetDisplay(
  resetAt: string | null | undefined,
  resetsInSeconds: number | null | undefined,
): { label: string; isoTimestamp: string | null } {
  if (typeof resetAt === 'string' && resetAt.trim().length > 0) {
    const cleanIso = resetAt.trim();
    const parsed = new Date(cleanIso);
    if (!Number.isNaN(parsed.getTime())) {
      const formatted = new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(parsed);
      return { label: formatted, isoTimestamp: cleanIso };
    }
    return { label: cleanIso, isoTimestamp: cleanIso };
  }

  if (
    typeof resetsInSeconds === 'number' &&
    Number.isFinite(resetsInSeconds) &&
    resetsInSeconds >= 0
  ) {
    const totalMinutes = Math.round(resetsInSeconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    const text =
      hours > 0
        ? `em ${hours}h ${minutes}min`
        : minutes > 0
          ? `em ${minutes}min`
          : `em ${Math.round(resetsInSeconds)}s`;
    return { label: text, isoTimestamp: null };
  }

  return { label: '—', isoTimestamp: null };
}

export function mergeProviderQuotaCards(
  inventory?: QuotaInventoryExtended | null,
  directQuota?: QuotaStatusExtended | null,
): ProviderQuotaCardModel[] {
  const models = inventory?.models ?? [];
  const accounts = inventory?.accounts ?? [];
  const overrides = inventory?.next_account_overrides ?? {};

  const cards: ProviderQuotaCardModel[] = [];
  const consumedKeys = new Set<string>(['status']);

  for (const def of STANDARD_PROVIDERS) {
    const invRaw = inventory?.quota?.[def.key];
    const dirRaw = directQuota?.[def.key];
    const invEntry = isQuotaEntryObject(invRaw) ? invRaw : null;
    const dirEntry = isQuotaEntryObject(dirRaw) ? dirRaw : null;
    const merged = pickBetterQuotaEntry(dirEntry, invEntry);
    consumedKeys.add(def.key);

    const aliasSet = new Set(def.aliases.map((a) => a.toLowerCase()));
    const matchedModels = models.filter(
      (m) =>
        aliasSet.has(m.provider.toLowerCase()) ||
        aliasSet.has(m.owned_by.toLowerCase()),
    );
    const matchedAccounts = accounts.filter(
      (acc) =>
        aliasSet.has(acc.provider.toLowerCase()) ||
        (acc.quota_key ? aliasSet.has(acc.quota_key.toLowerCase()) : false),
    );

    let activeOverride: AccountOverride | null = null;
    for (const candidateKey of [def.key, ...def.aliases]) {
      if (overrides[candidateKey]) {
        activeOverride = overrides[candidateKey];
        break;
      }
    }

    const overrideProvider = matchedAccounts[0]?.provider ?? def.overrideProvider;
    const { status, remainingPercent, displayPercent } = normalizePercent(merged);

    cards.push({
      providerKey: def.key,
      overrideProvider,
      displayName: def.displayName,
      windowLabel:
        typeof merged.window_hours === 'number' && merged.window_hours > 0
          ? `Janela de ${merged.window_hours}h`
          : 'Janela de 5h',
      status,
      remainingPercent,
      displayPercent,
      resetsInSeconds: merged.resets_in_seconds ?? null,
      resetAt: merged.reset_at ?? null,
      observedAt: merged.observed_at ?? null,
      source: merged.source ?? 'não reportado',
      models: matchedModels,
      accounts: matchedAccounts,
      activeOverride,
    });
  }

  const extraKeys = new Set<string>();
  for (const sourceObj of [directQuota, inventory?.quota]) {
    if (!sourceObj) {
      continue;
    }
    for (const [key, val] of Object.entries(sourceObj)) {
      if (!consumedKeys.has(key) && isQuotaEntryObject(val)) {
        extraKeys.add(key);
      }
    }
  }

  for (const key of extraKeys) {
    const invRaw = inventory?.quota?.[key];
    const dirRaw = directQuota?.[key];
    const merged = pickBetterQuotaEntry(
      isQuotaEntryObject(dirRaw) ? dirRaw : null,
      isQuotaEntryObject(invRaw) ? invRaw : null,
    );
    const { status, remainingPercent, displayPercent } = normalizePercent(merged);
    const lowerKey = key.toLowerCase();

    cards.push({
      providerKey: key,
      overrideProvider: key,
      displayName: key,
      windowLabel: 'Janela de 5h',
      status,
      remainingPercent,
      displayPercent,
      resetsInSeconds: merged.resets_in_seconds ?? null,
      resetAt: merged.reset_at ?? null,
      observedAt: merged.observed_at ?? null,
      source: merged.source ?? 'não reportado',
      models: models.filter(
        (m) =>
          m.provider.toLowerCase() === lowerKey ||
          m.owned_by.toLowerCase() === lowerKey,
      ),
      accounts: accounts.filter(
        (a) =>
          a.provider.toLowerCase() === lowerKey ||
          (a.quota_key?.toLowerCase() === lowerKey),
      ),
      activeOverride: overrides[key] ?? null,
    });
  }

  return cards;
}

export async function selectNextOmniRouteAccount(
  client: ControlPlaneClient,
  payload: SelectOmniRouteAccountPayload,
): Promise<AccountOverride> {
  const check = validateAccountIdentifier(payload.account_id);
  if (!check.valid) {
    throw new Error(check.reason ?? 'Identificador de conta inválido.');
  }
  return client.request<AccountOverride>('/v1/control-plane/omniroute/account', {
    method: 'POST',
    body: {
      scope_id: payload.scope_id.trim() || 'default',
      provider: payload.provider.trim(),
      account_id: payload.account_id.trim(),
      validate_against_gateway: payload.validate_against_gateway ?? false,
    },
  });
}
