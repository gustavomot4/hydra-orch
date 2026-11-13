import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Coins,
  KeyRound,
  Lock,
  Plus,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Terminal,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient, type ControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  SSH_REQUIRED_CHECKS,
  certifyTransport,
  createSecretRef,
  detectRawSecretInInput,
  evaluateBudgetSummary,
  extractGovernanceErrorMessage,
  formatTransportCapabilities,
  getRunBudget,
  getTransportHealth,
  listGovernanceRuns,
  listSecrets,
  listTransports,
  redactTextForUi,
  revokeSecretRef,
  extendRunBudget,
  validateSecretRefInput,
} from './governanceApi';
import type {
  BudgetDimensionReport,
  BudgetStatus,
  GovernanceRunSummary,
  SecretProviderType,
  SecretRefItem,
  SupportedPlatform,
  TransportHealthResult,
  TransportItem,
} from './governanceTypes';

export interface SecretsTransportsBudgetPanelProps {
  initialRunId?: string | null;
  client?: ControlPlaneClient;
  className?: string;
}

const DIMENSION_LABELS: Record<string, string> = {
  usd: 'Custo (USD)',
  tokens_in: 'Tokens de entrada',
  tokens_out: 'Tokens de saída',
  wall_seconds: 'Tempo de parede (s)',
};

function formatDimensionValue(dimension: string, value: number): string {
  if (dimension === 'usd') {
    return `$${value.toFixed(2)}`;
  }
  if (dimension === 'wall_seconds') {
    return `${Math.round(value)}s`;
  }
  return String(Math.round(value));
}

function mapBudgetBadge(status: string): { status: string; labelOverride?: string } {
  switch (status.trim().toLowerCase()) {
    case 'active':
      return { status: 'active', labelOverride: 'Ativo' };
    case 'alerted':
      return { status: 'degraded', labelOverride: 'Alerta 80%' };
    case 'frozen':
      return { status: 'failed', labelOverride: 'Bloqueio 100%' };
    case 'exhausted':
      return { status: 'failed', labelOverride: 'Esgotado' };
    default:
      return { status: status || 'unknown' };
  }
}

function mapTransportHealthBadge(status: string): { status: string; labelOverride?: string } {
  switch (status.trim().toLowerCase()) {
    case 'healthy':
      return { status: 'connected', labelOverride: 'Saudável' };
    case 'degraded':
      return { status: 'degraded', labelOverride: 'Degradado' };
    case 'unreachable':
      return { status: 'failed', labelOverride: 'Inacessível' };
    default:
      return { status: 'unknown' };
  }
}

function resolveRunOptionId(run: GovernanceRunSummary): string {
  return run.id || run.run_id || '';
}

export function SecretsTransportsBudgetPanel({
  initialRunId = null,
  client: clientOverride,
  className = '',
}: SecretsTransportsBudgetPanelProps) {
  const hookClient = useControlPlaneClient();
  const client = clientOverride ?? hookClient;

  // Global panel state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Secrets state (metadata-only)
  const [secrets, setSecrets] = useState<SecretRefItem[]>([]);
  const [secretName, setSecretName] = useState('');
  const [providerType, setProviderType] = useState<SecretProviderType>('env');
  const [sourceKey, setSourceKey] = useState('');
  const [secretValidationError, setSecretValidationError] = useState<string | null>(null);
  const [creatingSecret, setCreatingSecret] = useState(false);
  const [revokingSecretId, setRevokingSecretId] = useState<string | null>(null);

  // Transports state
  const [transports, setTransports] = useState<TransportItem[]>([]);
  const [healthById, setHealthById] = useState<Record<string, TransportHealthResult>>({});
  const [checkingHealthId, setCheckingHealthId] = useState<string | null>(null);
  const [certifyingId, setCertifyingId] = useState<string | null>(null);
  const [openCertifyId, setOpenCertifyId] = useState<string | null>(null);
  const [certPlatform, setCertPlatform] = useState<SupportedPlatform>('Linux');
  const [certVersion, setCertVersion] = useState('1.0.0');
  const [certFingerprint, setCertFingerprint] = useState('');
  const [submittingCertify, setSubmittingCertify] = useState(false);

  // Budget state
  const [runs, setRuns] = useState<GovernanceRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId ?? '');
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [loadingBudget, setLoadingBudget] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [additionalUsd, setAdditionalUsd] = useState('5');
  const [extendReason, setExtendReason] = useState('');
  const [extendingBudget, setExtendingBudget] = useState(false);

  const loadBaseData = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const [secretItems, transportItems, runItems] = await Promise.all([
          listSecrets(client, signal),
          listTransports(client, signal),
          listGovernanceRuns(client, signal),
        ]);
        if (signal?.aborted) {
          return;
        }
        setSecrets(secretItems);
        setTransports(transportItems);
        setRuns(runItems);
        setSelectedRunId((prev) => {
          if (prev) {
            return prev;
          }
          const first = runItems[0];
          return first ? resolveRunOptionId(first) : '';
        });
      } catch (err) {
        if (signal?.aborted) {
          return;
        }
        setError(
          extractGovernanceErrorMessage(
            err,
            'Não foi possível carregar segredos, transportes e runs.',
          ),
        );
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [client],
  );

  const loadBudget = useCallback(
    async (runId: string, signal?: AbortSignal) => {
      if (!runId) {
        setBudget(null);
        return;
      }
      setLoadingBudget(true);
      setBudgetError(null);
      try {
        const result = await getRunBudget(client, runId, signal);
        if (signal?.aborted) {
          return;
        }
        setBudget(result);
      } catch (err) {
        if (signal?.aborted) {
          return;
        }
        setBudget(null);
        setBudgetError(
          extractGovernanceErrorMessage(err, 'Falha ao consultar orçamento da run.'),
        );
      } finally {
        if (!signal?.aborted) {
          setLoadingBudget(false);
        }
      }
    },
    [client],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadBaseData(controller.signal);
    return () => controller.abort();
  }, [loadBaseData]);

  useEffect(() => {
    if (initialRunId) {
      setSelectedRunId(initialRunId);
    }
  }, [initialRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      setBudget(null);
      return;
    }
    const controller = new AbortController();
    void loadBudget(selectedRunId, controller.signal);
    return () => controller.abort();
  }, [loadBudget, selectedRunId]);

  const liveSecretDanger = useMemo(() => {
    return detectRawSecretInInput(secretName) ?? detectRawSecretInInput(sourceKey);
  }, [secretName, sourceKey]);

  const handleCreateSecret = async (e: FormEvent) => {
    e.preventDefault();
    setSecretValidationError(null);
    setError(null);
    setFeedback(null);

    const check = validateSecretRefInput({
      secret_name: secretName,
      source_key: sourceKey,
    });
    if (!check.valid) {
      setSecretValidationError(check.reason ?? 'Referência de segredo inválida.');
      return;
    }

    setCreatingSecret(true);
    try {
      const created = await createSecretRef(client, {
        secret_name: secretName.trim(),
        provider_type: providerType,
        source_key: sourceKey.trim(),
      });
      setSecrets((prev) => [...prev, created]);
      setSecretName('');
      setSourceKey('');
      setFeedback(`Referência de segredo "${created.secret_name}" registrada (somente metadados).`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao criar referência de segredo.'));
    } finally {
      setCreatingSecret(false);
    }
  };

  const handleRevokeSecret = async (secretId: string) => {
    setError(null);
    setFeedback(null);
    setRevokingSecretId(secretId);
    try {
      await revokeSecretRef(client, secretId, 'operator_revoked');
      setSecrets((prev) =>
        prev.map((item) => (item.secret_id === secretId ? { ...item, revoked: true } : item)),
      );
      setFeedback(`SecretRef "${secretId}" revogado.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao revogar referência de segredo.'));
    } finally {
      setRevokingSecretId(null);
    }
  };

  const handleRefreshHealth = async (transportId: string) => {
    setError(null);
    setCheckingHealthId(transportId);
    try {
      const health = await getTransportHealth(client, transportId, true);
      setHealthById((prev) => ({ ...prev, [transportId]: health }));
      setFeedback(`Saúde do transporte "${transportId}" atualizada (${health.status}).`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao verificar saúde do transporte.'));
    } finally {
      setCheckingHealthId(null);
    }
  };

  const openCertifyForm = (transport: TransportItem) => {
    setOpenCertifyId(transport.transport_id);
    setCertPlatform('Linux');
    setCertVersion('1.0.0');
    setCertFingerprint(
      transport.target_identity.startsWith('SHA256:') ? transport.target_identity : '',
    );
    setError(null);
  };

  const handleCertifyTransport = async (e: FormEvent, transport: TransportItem) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);

    const cleanVersion = certVersion.trim();
    const cleanFingerprint = certFingerprint.trim();
    if (!cleanVersion) {
      setError('Informe a versão do transporte para certificação.');
      return;
    }
    if (transport.type === 'ssh' && !cleanFingerprint) {
      setError('Transporte SSH exige fingerprint SHA256 de host-key para certificação.');
      return;
    }
    const secretMsg = detectRawSecretInInput(cleanFingerprint) ?? detectRawSecretInInput(cleanVersion);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }

    setCertifyingId(transport.transport_id);
    setSubmittingCertify(true);
    try {
      const passedChecks =
        transport.type === 'ssh'
          ? [...SSH_REQUIRED_CHECKS]
          : ['host_key_verified', 'target_identity', 'healthcheck'];

      await certifyTransport(client, transport.transport_id, {
        transport_id: transport.transport_id,
        transport_type: transport.type,
        platform: certPlatform,
        version: cleanVersion,
        target_identity: transport.target_identity,
        ...(cleanFingerprint ? { fingerprint: cleanFingerprint } : {}),
        passed_checks: passedChecks,
        simulated: false,
      });

      setTransports((prev) =>
        prev.map((item) =>
          item.transport_id === transport.transport_id ? { ...item, is_certified: true } : item,
        ),
      );
      setOpenCertifyId(null);
      setFeedback(`Transporte "${transport.transport_id}" certificado com sucesso.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao certificar transporte.'));
    } finally {
      setCertifyingId(null);
      setSubmittingCertify(false);
    }
  };

  const handleExtendBudget = async (e: FormEvent) => {
    e.preventDefault();
    setBudgetError(null);
    setFeedback(null);

    if (!selectedRunId) {
      setBudgetError('Selecione uma run antes de estender o orçamento.');
      return;
    }

    const parsedUsd = Number(additionalUsd);
    if (!Number.isFinite(parsedUsd) || parsedUsd <= 0) {
      setBudgetError('Informe um valor adicional positivo em USD (> 0).');
      return;
    }

    const cleanReason = extendReason.trim();
    if (!cleanReason) {
      setBudgetError('Informe a justificativa operacional da aprovação de extensão.');
      return;
    }
    const secretMsg = detectRawSecretInInput(cleanReason);
    if (secretMsg) {
      setBudgetError(secretMsg);
      return;
    }

    setExtendingBudget(true);
    try {
      const result = await extendRunBudget(client, selectedRunId, {
        additional_usd: parsedUsd,
        reason: cleanReason,
        approved: true,
      });
      setBudget(result.budget_status);
      setExtendReason('');
      setFeedback(
        `Orçamento da run "${selectedRunId}" estendido em +$${parsedUsd.toFixed(2)} (aprovado).`,
      );
    } catch (err) {
      setBudgetError(extractGovernanceErrorMessage(err, 'Falha ao estender orçamento.'));
    } finally {
      setExtendingBudget(false);
    }
  };

  const budgetSummary = useMemo(
    () => (budget ? evaluateBudgetSummary(budget) : null),
    [budget],
  );

  const runOptions = useMemo(() => {
    const ids = new Set<string>();
    const items: Array<{ id: string; label: string }> = [];
    if (selectedRunId) {
      ids.add(selectedRunId);
      items.push({ id: selectedRunId, label: selectedRunId });
    }
    for (const r of runs) {
      const id = resolveRunOptionId(r);
      if (id && !ids.has(id)) {
        ids.add(id);
        items.push({
          id,
          label: r.status ? `${id} · ${r.status}` : id,
        });
      }
    }
    return items;
  }, [runs, selectedRunId]);

  const displayedSecretAlert = secretValidationError ?? liveSecretDanger;

  return (
    <div
      data-testid="secrets-transports-budget-panel"
      className={`flex flex-col gap-5 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#303030] bg-[#1C1C1C] px-4 py-3">
        <div className="space-y-0.5">
          <h2 className="text-sm font-semibold text-[#E8E8E8]">
            Segredos (Metadados), Transportes SSH e Orçamento
          </h2>
          <p className="text-xs text-[#969696]">
            Gerencie referências externas sem valores brutos, certifique fingerprints SSH e controle limites de orçamento (80% / 100%).
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            void loadBaseData();
            if (selectedRunId) {
              void loadBudget(selectedRunId);
            }
          }}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
        >
          <RefreshCw
            aria-hidden="true"
            className={`h-3.5 w-3.5 text-[#969696] ${loading ? 'motion-safe:animate-spin' : ''}`}
          />
          <span>Atualizar</span>
        </button>
      </div>

      {error ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-4 py-3 text-xs text-[#FCA5A5]"
        >
          <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {feedback ? (
        <div
          role="status"
          className="flex items-center gap-2 rounded-xl border border-[#22C55E]/40 bg-[#22C55E]/10 px-4 py-3 text-xs text-[#4ADE80]"
        >
          <CheckCircle2 aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span>{feedback}</span>
        </div>
      ) : null}

      {/* 1. SecretRef metadata-only */}
      <section
        aria-label="Referências de segredo (somente metadados)"
        className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <KeyRound aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
              SecretRef — Somente Metadados ({secrets.length})
            </h3>
          </div>
          <span className="inline-flex items-center gap-1 rounded border border-[#303030] bg-[#141414] px-2 py-0.5 text-[11px] text-[#969696]">
            <Lock aria-hidden="true" className="h-3 w-3" />
            <span>Valores brutos nunca são armazenados ou exibidos</span>
          </span>
        </div>

        <form
          onSubmit={handleCreateSecret}
          className="space-y-3 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3"
        >
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1">
              <label htmlFor="secret-ref-name" className="block text-xs text-[#969696]">
                Nome simbólico (secret_name)
              </label>
              <input
                id="secret-ref-name"
                type="text"
                value={secretName}
                onChange={(e) => {
                  setSecretName(e.target.value);
                  setSecretValidationError(null);
                }}
                placeholder="OPENAI_API_KEY"
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="secret-ref-provider" className="block text-xs text-[#969696]">
                Provedor (provider_type)
              </label>
              <select
                id="secret-ref-provider"
                value={providerType}
                onChange={(e) => setProviderType(e.target.value as SecretProviderType)}
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
              >
                <option value="env">Variável de ambiente (env)</option>
                <option value="vault">Vault (vault)</option>
                <option value="keyring">Keyring do sistema (keyring)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label htmlFor="secret-ref-source-key" className="block text-xs text-[#969696]">
                Chave de origem (source_key)
              </label>
              <input
                id="secret-ref-source-key"
                type="text"
                value={sourceKey}
                onChange={(e) => {
                  setSourceKey(e.target.value);
                  setSecretValidationError(null);
                }}
                placeholder="OPENAI_API_KEY ou secret/data/openai"
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
              />
            </div>
          </div>

          {displayedSecretAlert ? (
            <div
              role="alert"
              data-testid="secret-ref-validation-alert"
              className="flex items-center gap-2 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
            >
              <AlertCircle aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              <span>{displayedSecretAlert}</span>
            </div>
          ) : null}

          <button
            type="submit"
            disabled={creatingSecret}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
          >
            <Plus aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{creatingSecret ? 'Registrando...' : 'Registrar SecretRef'}</span>
          </button>
        </form>

        {secrets.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-4 text-center text-xs text-[#969696]">
            {loading ? 'Carregando referências...' : 'Nenhuma referência SecretRef cadastrada.'}
          </p>
        ) : (
          <ul className="grid gap-2.5 md:grid-cols-2">
            {secrets.map((sec) => (
              <li
                key={sec.secret_id}
                data-testid={`secret-card-${sec.secret_id}`}
                className="flex items-center justify-between gap-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
              >
                <div className="min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold text-[#E8E8E8]">
                      {redactTextForUi(sec.secret_name)}
                    </span>
                    <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[#969696]">
                      {sec.provider_type}
                    </span>
                  </div>
                  <p className="truncate font-mono text-[11px] text-[#969696]">
                    origem: {redactTextForUi(sec.source_key)} · id: {sec.secret_id}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <StatusBadge
                    status={sec.revoked ? 'cancelled' : 'active'}
                    labelOverride={sec.revoked ? 'Revogado' : 'Ativo'}
                    compact
                  />
                  <button
                    type="button"
                    disabled={sec.revoked || revokingSecretId === sec.secret_id}
                    onClick={() => void handleRevokeSecret(sec.secret_id)}
                    className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2 py-1 text-[11px] text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                  >
                    <ShieldOff aria-hidden="true" className="h-3 w-3" />
                    <span>Revogar</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 2. Transports & SSH Host-Key Certification */}
      <section
        aria-label="Transportes e certificação SSH"
        className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <div className="flex items-center gap-2">
          <Terminal aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
            Transportes e Certificação SSH Host-Key ({transports.length})
          </h3>
        </div>

        {transports.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-4 text-center text-xs text-[#969696]">
            {loading ? 'Carregando transportes...' : 'Nenhum transporte registrado.'}
          </p>
        ) : (
          <ul className="space-y-3">
            {transports.map((transport) => {
              const health = healthById[transport.transport_id];
              const caps = formatTransportCapabilities(transport.capabilities);
              const isCertifyOpen = openCertifyId === transport.transport_id;
              const isBusyCert = certifyingId === transport.transport_id && submittingCertify;

              return (
                <li
                  key={transport.transport_id}
                  data-testid={`transport-card-${transport.transport_id}`}
                  className="space-y-3 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono font-semibold text-[#E8E8E8]">
                          {transport.transport_id}
                        </span>
                        <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[#969696]">
                          {transport.type}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-[#969696]">
                        alvo: {redactTextForUi(transport.target_identity)}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge
                        status={transport.is_certified ? 'accepted' : 'waiting'}
                        labelOverride={transport.is_certified ? 'Certificado' : 'Não certificado'}
                        compact
                      />
                      {health ? (
                        <StatusBadge {...mapTransportHealthBadge(health.status)} compact />
                      ) : null}
                    </div>
                  </div>

                  {caps.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {caps.map((cap) => (
                        <span
                          key={cap}
                          className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]"
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {health ? (
                    <p
                      data-testid={`transport-health-${transport.transport_id}`}
                      className="font-mono text-[11px] text-[#969696]"
                    >
                      Último healthcheck: {health.status}
                      {health.last_check_at ? ` · ${health.last_check_at}` : ''}
                      {health.error_detail ? ` · ${redactTextForUi(health.error_detail)}` : ''}
                    </p>
                  ) : null}

                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      disabled={checkingHealthId === transport.transport_id}
                      onClick={() => void handleRefreshHealth(transport.transport_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
                    >
                      <Activity aria-hidden="true" className="h-3 w-3" />
                      <span>
                        {checkingHealthId === transport.transport_id
                          ? 'Verificando...'
                          : 'Atualizar saúde'}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        isCertifyOpen ? setOpenCertifyId(null) : openCertifyForm(transport)
                      }
                      className="inline-flex items-center gap-1 rounded-md border border-[#3B82F6]/40 bg-[#3B82F6]/10 px-2.5 py-1 text-[11px] font-medium text-[#93C5FD] hover:bg-[#3B82F6]/20"
                    >
                      <ShieldCheck aria-hidden="true" className="h-3 w-3" />
                      <span>{isCertifyOpen ? 'Fechar certificação' : 'Certificar host'}</span>
                    </button>
                  </div>

                  {isCertifyOpen ? (
                    <form
                      onSubmit={(e) => void handleCertifyTransport(e, transport)}
                      className="grid gap-3 rounded-lg border border-[#3B82F6]/30 bg-[#141414] p-3 md:grid-cols-3"
                    >
                      <div className="space-y-1">
                        <label
                          htmlFor={`cert-platform-${transport.transport_id}`}
                          className="block text-[11px] text-[#969696]"
                        >
                          Plataforma
                        </label>
                        <select
                          id={`cert-platform-${transport.transport_id}`}
                          value={certPlatform}
                          onChange={(e) => setCertPlatform(e.target.value as SupportedPlatform)}
                          className="w-full rounded border border-[#303030] bg-[#1C1C1C] px-2 py-1 text-xs text-[#E8E8E8]"
                        >
                          <option value="Linux">Linux</option>
                          <option value="Windows">Windows</option>
                          <option value="Darwin">Darwin</option>
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label
                          htmlFor={`cert-version-${transport.transport_id}`}
                          className="block text-[11px] text-[#969696]"
                        >
                          Versão
                        </label>
                        <input
                          id={`cert-version-${transport.transport_id}`}
                          type="text"
                          value={certVersion}
                          onChange={(e) => setCertVersion(e.target.value)}
                          className="w-full rounded border border-[#303030] bg-[#1C1C1C] px-2.5 py-1 font-mono text-xs text-[#E8E8E8]"
                        />
                      </div>

                      <div className="space-y-1">
                        <label
                          htmlFor={`cert-fingerprint-${transport.transport_id}`}
                          className="block text-[11px] text-[#969696]"
                        >
                          Fingerprint SHA256 (host-key)
                        </label>
                        <input
                          id={`cert-fingerprint-${transport.transport_id}`}
                          type="text"
                          value={certFingerprint}
                          onChange={(e) => setCertFingerprint(e.target.value)}
                          placeholder="SHA256:..."
                          className="w-full rounded border border-[#303030] bg-[#1C1C1C] px-2.5 py-1 font-mono text-xs text-[#E8E8E8]"
                        />
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-2 md:col-span-3">
                        <span className="text-[11px] text-[#969696]">
                          Atestado explícito do operador (simulated: false · check host_key_verified)
                        </span>
                        <button
                          type="submit"
                          disabled={isBusyCert}
                          className="rounded bg-[#E8E8E8] px-3 py-1 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
                        >
                          {isBusyCert ? 'Certificando...' : 'Confirmar certificação'}
                        </button>
                      </div>
                    </form>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* 3. Budget 80% / 100% Governance */}
      <section
        aria-label="Governança de orçamento da run"
        className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Coins aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
              Orçamento por Run (80% Alerta / 100% Bloqueio)
            </h3>
            {budget ? <StatusBadge {...mapBudgetBadge(budget.status)} compact /> : null}
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="budget-run-select" className="text-xs text-[#969696]">
              Run:
            </label>
            <select
              id="budget-run-select"
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="min-w-[200px] rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1 font-mono text-xs text-[#E8E8E8]"
            >
              {runOptions.length === 0 ? (
                <option value="">Nenhuma run disponível</option>
              ) : (
                runOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))
              )}
            </select>
          </div>
        </div>

        {budgetError ? (
          <div
            role="alert"
            className="flex items-center gap-2 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
          >
            <AlertCircle aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
            <span>{budgetError}</span>
          </div>
        ) : null}

        {!selectedRunId ? (
          <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-4 text-center text-xs text-[#969696]">
            Selecione uma run para consultar o orçamento e limites configurados.
          </p>
        ) : loadingBudget && !budget ? (
          <p className="rounded-lg border border-[#303030] bg-[#1C1C1C] px-3 py-4 text-center text-xs text-[#969696]">
            Carregando orçamento da run {selectedRunId}...
          </p>
        ) : budget && budgetSummary ? (
          <div className="space-y-4">
            {budgetSummary.isAlert80 ? (
              <div
                role="alert"
                data-testid="budget-alert-80"
                className="flex items-center gap-2 rounded-lg border border-[#F59E0B]/50 bg-[#F59E0B]/10 px-3 py-2.5 text-xs font-medium text-[#FCD34D]"
              >
                <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0" />
                <span>Alerta 80% de orçamento — revise o consumo antes do bloqueio automático.</span>
              </div>
            ) : null}

            {budgetSummary.isBlocked100 ? (
              <div
                role="alert"
                data-testid="budget-block-100"
                className="flex items-center gap-2 rounded-lg border border-[#EF4444]/50 bg-[#EF4444]/10 px-3 py-2.5 text-xs font-medium text-[#FCA5A5]"
              >
                <ShieldOff aria-hidden="true" className="h-4 w-4 shrink-0" />
                <span>Bloqueio 100% atingido — aprovação necessária para estender</span>
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {budgetSummary.dimensions.map((dim: BudgetDimensionReport) => {
                const isUnknown = dim.status === 'unknown' || dim.current === null;
                const clampedPct =
                  dim.pct_used !== null ? Math.max(0, Math.min(100, dim.pct_used)) : 0;
                return (
                  <div
                    key={dim.dimension}
                    data-testid={`budget-dim-${dim.dimension}`}
                    className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-medium text-[#E8E8E8]">
                        {DIMENSION_LABELS[dim.dimension] ?? dim.dimension}
                      </span>
                      <StatusBadge status={dim.status} compact />
                    </div>

                    <div className="font-mono text-xs text-[#E8E8E8]">
                      {isUnknown ? (
                        <span className="text-[#969696]">Desconhecido</span>
                      ) : (
                        <span>
                          {formatDimensionValue(dim.dimension, dim.current as number)}
                          {dim.limit !== null
                            ? ` / ${formatDimensionValue(dim.dimension, dim.limit)}`
                            : ''}
                        </span>
                      )}
                    </div>

                    <div
                      role="progressbar"
                      aria-label={DIMENSION_LABELS[dim.dimension] ?? dim.dimension}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={dim.pct_used !== null ? Math.round(clampedPct) : undefined}
                      aria-valuetext={
                        dim.pct_used !== null ? `${dim.pct_used.toFixed(1)}%` : 'Desconhecido'
                      }
                      className="h-1.5 w-full overflow-hidden rounded-full bg-[#141414]"
                    >
                      {dim.pct_used !== null ? (
                        <div
                          className={`h-full rounded-full ${
                            dim.triggered_freeze
                              ? 'bg-[#EF4444]'
                              : dim.triggered_alert
                                ? 'bg-[#F59E0B]'
                                : 'bg-[#22C55E]'
                          }`}
                          style={{ width: `${clampedPct}%` }}
                        />
                      ) : null}
                    </div>

                    <p className="font-mono text-[11px] text-[#969696]">
                      {dim.pct_used !== null ? `${dim.pct_used.toFixed(1)}% usado` : 'Desconhecido'}
                    </p>
                  </div>
                );
              })}
            </div>

            <form
              onSubmit={handleExtendBudget}
              className="grid gap-3 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 md:grid-cols-3"
            >
              <div className="space-y-1">
                <label htmlFor="budget-extend-usd" className="block text-xs text-[#969696]">
                  Incremento adicional (USD)
                </label>
                <input
                  id="budget-extend-usd"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={additionalUsd}
                  onChange={(e) => setAdditionalUsd(e.target.value)}
                  className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="budget-extend-reason" className="block text-xs text-[#969696]">
                  Justificativa da aprovação
                </label>
                <input
                  id="budget-extend-reason"
                  type="text"
                  value={extendReason}
                  onChange={(e) => setExtendReason(e.target.value)}
                  placeholder="Aprovação operacional para finalizar run"
                  className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
                />
              </div>

              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={extendingBudget}
                  className="w-full rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
                >
                  {extendingBudget ? 'Aprovando...' : 'Aprovar e estender orçamento'}
                </button>
              </div>
            </form>
          </div>
        ) : null}
      </section>
    </div>
  );
}
