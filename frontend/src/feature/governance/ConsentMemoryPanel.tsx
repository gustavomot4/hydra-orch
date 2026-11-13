import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Brain,
  Check,
  CheckCircle2,
  Edit3,
  Plus,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  X,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient, type ControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  createConsent,
  createMemory,
  decideConsent,
  detectRawSecretInInput,
  extractGovernanceErrorMessage,
  formatConsentScope,
  isGovernanceConflictError,
  listConsents,
  listMemory,
  redactTextForUi,
  revokeConsent,
  revokeMemory,
  updateMemory,
} from './governanceApi';
import type {
  ConsentDecisionAction,
  ConsentPurpose,
  ConsentRecord,
  GovernanceScopeType,
  MemoryEntry,
  RetentionPolicy,
} from './governanceTypes';

export interface ConsentMemoryPanelProps {
  client?: ControlPlaneClient;
  className?: string;
}

const SCOPE_OPTIONS: ReadonlyArray<{ value: GovernanceScopeType; label: string }> = [
  { value: 'workspace', label: 'Workspace (workspace)' },
  { value: 'project', label: 'Projeto (project)' },
  { value: 'area', label: 'Área (area)' },
  { value: 'principal', label: 'Principal / Usuário (principal)' },
  { value: 'extension', label: 'Extensão (extension)' },
];

function mapConsentBadge(status: string): { status: string; labelOverride?: string } {
  switch (status.trim().toLowerCase()) {
    case 'requested':
      return { status: 'waiting', labelOverride: 'Solicitado' };
    case 'granted':
      return { status: 'active', labelOverride: 'Concedido' };
    case 'denied':
      return { status: 'failed', labelOverride: 'Negado' };
    case 'revoked':
      return { status: 'cancelled', labelOverride: 'Revogado' };
    case 'expired':
      return { status: 'stale', labelOverride: 'Expirado' };
    default:
      return { status: status || 'unknown' };
  }
}

function mapMemoryBadge(status: string): { status: string; labelOverride?: string } {
  switch (status.trim().toLowerCase()) {
    case 'active':
      return { status: 'active', labelOverride: 'Ativa' };
    case 'pending_consent':
      return { status: 'waiting', labelOverride: 'Aguardando consentimento' };
    case 'revoked':
      return { status: 'cancelled', labelOverride: 'Revogada' };
    case 'rejected':
      return { status: 'failed', labelOverride: 'Rejeitada' };
    case 'expired':
      return { status: 'stale', labelOverride: 'Expirada' };
    default:
      return { status: status || 'unknown' };
  }
}

export function ConsentMemoryPanel({
  client: clientOverride,
  className = '',
}: ConsentMemoryPanelProps) {
  const hookClient = useControlPlaneClient();
  const client = clientOverride ?? hookClient;

  // Scope filter state
  const [scopeType, setScopeType] = useState<GovernanceScopeType>('workspace');
  const [scopeId, setScopeId] = useState('default');
  const [searchQuery, setSearchQuery] = useState('');

  // Server data
  const [consents, setConsents] = useState<ConsentRecord[]>([]);
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conflictBanner, setConflictBanner] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Consent creation state
  const [consentPurpose, setConsentPurpose] = useState<ConsentPurpose>('memory');
  const [creatingConsent, setCreatingConsent] = useState(false);
  const [actingConsentId, setActingConsentId] = useState<string | null>(null);

  // Memory creation state (preserved across 409 conflicts)
  const [newMemoryContent, setNewMemoryContent] = useState('');
  const [newMemoryConsentId, setNewMemoryConsentId] = useState('');
  const [newRetentionPolicy, setNewRetentionPolicy] = useState<RetentionPolicy>('month');
  const [creatingMemory, setCreatingMemory] = useState(false);

  // Memory inline edit state (preserved across 409 conflicts)
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [editingRetentionPolicy, setEditingRetentionPolicy] = useState<RetentionPolicy>('month');
  const [editingExpectedVersion, setEditingExpectedVersion] = useState<number>(1);
  const [serverSnapshotHint, setServerSnapshotHint] = useState<string | null>(null);
  const [actingMemoryId, setActingMemoryId] = useState<string | null>(null);

  const loadAll = useCallback(
    async (signal?: AbortSignal): Promise<{ consents: ConsentRecord[]; memories: MemoryEntry[] } | null> => {
      const cleanScopeId = scopeId.trim() || 'default';
      setLoading(true);
      setError(null);
      try {
        const [consentItems, memoryItems] = await Promise.all([
          listConsents(client, { scope_type: scopeType, scope_id: cleanScopeId }, signal),
          listMemory(
            client,
            { scope_type: scopeType, scope_id: cleanScopeId, query: searchQuery.trim() },
            signal,
          ),
        ]);
        if (signal?.aborted) {
          return null;
        }
        setConsents(consentItems);
        setMemories(memoryItems);
        return { consents: consentItems, memories: memoryItems };
      } catch (err) {
        if (signal?.aborted) {
          return null;
        }
        setError(
          extractGovernanceErrorMessage(
            err,
            'Não foi possível carregar consentimentos e memórias do escopo.',
          ),
        );
        return null;
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [client, scopeId, scopeType, searchQuery],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadAll(controller.signal);
    return () => controller.abort();
  }, [loadAll]);

  const handleScopeChange = (nextScope: GovernanceScopeType) => {
    setScopeType(nextScope);
    setConsentPurpose(nextScope === 'extension' ? 'extension' : 'memory');
  };

  const handleMutationError = (err: unknown, fallback: string) => {
    if (isGovernanceConflictError(err)) {
      setConflictBanner(extractGovernanceErrorMessage(err, fallback));
      return;
    }
    setError(extractGovernanceErrorMessage(err, fallback));
  };

  const handleReloadCurrentState = async () => {
    setFeedback(null);
    const reloaded = await loadAll();
    if (!reloaded) {
      return;
    }
    setConflictBanner(null);
    if (editingMemoryId) {
      const latest = reloaded.memories.find((m) => m.memory_id === editingMemoryId);
      if (latest) {
        setEditingExpectedVersion(latest.version);
        setServerSnapshotHint(
          `Estado atualizado para v${latest.version} (${latest.content_redacted}). Seu rascunho foi preservado.`,
        );
      } else {
        setServerSnapshotHint(
          'Esta memória não está mais ativa no servidor após o recarregamento.',
        );
      }
    }
    setFeedback('Estado atual recarregado do servidor.');
  };

  const handleCreateConsent = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setConflictBanner(null);
    setFeedback(null);

    const cleanScopeId = scopeId.trim() || 'default';
    setCreatingConsent(true);
    try {
      const created = await createConsent(client, {
        scope_type: scopeType,
        scope_id: cleanScopeId,
        purpose: consentPurpose,
      });
      setConsents((prev) => [...prev, created]);
      setFeedback(`Consentimento "${created.consent_id}" solicitado (${created.purpose}).`);
    } catch (err) {
      handleMutationError(err, 'Falha ao solicitar consentimento.');
    } finally {
      setCreatingConsent(false);
    }
  };

  const handleDecideConsent = async (consentId: string, action: ConsentDecisionAction) => {
    setError(null);
    setConflictBanner(null);
    setFeedback(null);
    setActingConsentId(consentId);
    try {
      const updated = await decideConsent(client, consentId, action);
      setConsents((prev) => prev.map((c) => (c.consent_id === consentId ? updated : c)));
      if (action === 'granted' && updated.purpose === 'memory' && !newMemoryConsentId) {
        setNewMemoryConsentId(updated.consent_id);
      }
      setFeedback(
        `Consentimento "${consentId}" atualizado para "${action === 'granted' ? 'Concedido' : 'Negado'}".`,
      );
    } catch (err) {
      handleMutationError(err, 'Falha ao atualizar decisão de consentimento.');
    } finally {
      setActingConsentId(null);
    }
  };

  const handleRevokeConsent = async (consentId: string) => {
    setError(null);
    setConflictBanner(null);
    setFeedback(null);
    setActingConsentId(consentId);
    try {
      const updated = await revokeConsent(client, consentId);
      setConsents((prev) => prev.map((c) => (c.consent_id === consentId ? updated : c)));
      setFeedback(`Consentimento "${consentId}" revogado.`);
    } catch (err) {
      handleMutationError(err, 'Falha ao revogar consentimento.');
    } finally {
      setActingConsentId(null);
    }
  };

  const handleCreateMemory = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setConflictBanner(null);
    setFeedback(null);

    const cleanContent = newMemoryContent.trim();
    if (!cleanContent) {
      setError('Informe o conteúdo da memória antes de gravar.');
      return;
    }
    const secretMsg = detectRawSecretInInput(cleanContent);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }

    const cleanScopeId = scopeId.trim() || 'default';
    const cleanConsentId = newMemoryConsentId.trim();

    setCreatingMemory(true);
    try {
      const created = await createMemory(client, {
        scope_type: scopeType,
        scope_id: cleanScopeId,
        content: cleanContent,
        ...(cleanConsentId ? { consent_id: cleanConsentId } : {}),
        retention_policy: newRetentionPolicy,
      });
      setMemories((prev) => [...prev, created]);
      setNewMemoryContent('');
      setFeedback(`Memória "${created.memory_id}" registrada (v${created.version}).`);
    } catch (err) {
      handleMutationError(err, 'Falha ao registrar entrada de memória.');
    } finally {
      setCreatingMemory(false);
    }
  };

  const startEditingMemory = (entry: MemoryEntry) => {
    setEditingMemoryId(entry.memory_id);
    setEditingContent(entry.content_redacted);
    setEditingRetentionPolicy(entry.retention_policy_id);
    setEditingExpectedVersion(entry.version);
    setServerSnapshotHint(null);
    setConflictBanner(null);
    setError(null);
  };

  const cancelEditingMemory = () => {
    setEditingMemoryId(null);
    setEditingContent('');
    setServerSnapshotHint(null);
    setConflictBanner(null);
  };

  const handleSaveMemoryEdit = async (entry: MemoryEntry) => {
    setError(null);
    setConflictBanner(null);
    setFeedback(null);

    const cleanContent = editingContent.trim();
    if (!cleanContent) {
      setError('O conteúdo editado da memória não pode ficar vazio.');
      return;
    }
    const secretMsg = detectRawSecretInInput(cleanContent);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }

    setActingMemoryId(entry.memory_id);
    try {
      const updated = await updateMemory(client, entry.memory_id, editingExpectedVersion, {
        scope_type: entry.scope_type,
        scope_id: entry.scope_id,
        content: cleanContent,
        consent_id: entry.consent_id,
        retention_policy: editingRetentionPolicy,
      });
      setMemories((prev) =>
        prev.map((m) => (m.memory_id === entry.memory_id ? updated : m)),
      );
      setEditingMemoryId(null);
      setEditingContent('');
      setServerSnapshotHint(null);
      setFeedback(`Memória "${updated.memory_id}" atualizada para v${updated.version}.`);
    } catch (err) {
      handleMutationError(err, 'Falha ao atualizar memória.');
    } finally {
      setActingMemoryId(null);
    }
  };

  const handleRevokeMemory = async (memoryId: string) => {
    setError(null);
    setConflictBanner(null);
    setFeedback(null);
    setActingMemoryId(memoryId);
    try {
      const updated = await revokeMemory(client, memoryId);
      setMemories((prev) =>
        prev.map((m) => (m.memory_id === memoryId ? updated : m)),
      );
      setFeedback(`Memória "${memoryId}" revogada.`);
    } catch (err) {
      handleMutationError(err, 'Falha ao revogar memória.');
    } finally {
      setActingMemoryId(null);
    }
  };

  const grantedMemoryConsents = consents.filter(
    (c) => c.status === 'granted' && c.purpose === 'memory',
  );

  return (
    <div data-testid="consent-memory-panel" className={`flex flex-col gap-5 ${className}`}>
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border border-[#303030] bg-[#1C1C1C] p-4">
        <div className="grid flex-1 gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <label htmlFor="consent-memory-scope-type" className="block text-xs text-[#969696]">
              Tipo de escopo (scope_type)
            </label>
            <select
              id="consent-memory-scope-type"
              value={scopeType}
              onChange={(e) => handleScopeChange(e.target.value as GovernanceScopeType)}
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
            >
              {SCOPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label htmlFor="consent-memory-scope-id" className="block text-xs text-[#969696]">
              ID do escopo (scope_id)
            </label>
            <input
              id="consent-memory-scope-id"
              type="text"
              value={scopeId}
              onChange={(e) => setScopeId(e.target.value)}
              placeholder="default"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="memory-search-query" className="block text-xs text-[#969696]">
              Filtrar memória (query)
            </label>
            <input
              id="memory-search-query"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar conteúdo..."
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={() => void loadAll()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
        >
          <RefreshCw
            aria-hidden="true"
            className={`h-3.5 w-3.5 text-[#969696] ${loading ? 'motion-safe:animate-spin' : ''}`}
          />
          <span>Atualizar escopo</span>
        </button>
      </div>

      {conflictBanner ? (
        <div
          role="alert"
          data-testid="consent-memory-conflict-banner"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#F59E0B]/50 bg-[#F59E0B]/10 px-4 py-3 text-xs text-[#FCD34D]"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span>
              <strong>Conflito de versão/consentimento (HTTP 409)</strong> — {conflictBanner}
            </span>
          </div>
          <button
            type="button"
            onClick={() => void handleReloadCurrentState()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#F59E0B]/50 bg-[#141414] px-3 py-1.5 text-xs font-medium text-[#FCD34D] hover:bg-[#202020]"
          >
            <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Recarregar estado atual</span>
          </button>
        </div>
      ) : null}

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

      <div className="grid gap-5 lg:grid-cols-2">
        <section
          aria-label="Consentimentos explícitos"
          className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
        >
          <div className="flex items-center gap-2">
            <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
              Consentimentos ({consents.length})
            </h3>
          </div>

          <form
            onSubmit={handleCreateConsent}
            className="flex flex-wrap items-end gap-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3"
          >
            <div className="min-w-[160px] flex-1 space-y-1">
              <label htmlFor="consent-purpose-select" className="block text-xs text-[#969696]">
                Finalidade
              </label>
              <select
                id="consent-purpose-select"
                value={consentPurpose}
                onChange={(e) => setConsentPurpose(e.target.value as ConsentPurpose)}
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
              >
                <option value="memory">Memória (memory)</option>
                <option value="extension">Extensão (extension)</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={creatingConsent}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
            >
              <Plus aria-hidden="true" className="h-3.5 w-3.5" />
              <span>{creatingConsent ? 'Solicitando...' : 'Solicitar consentimento'}</span>
            </button>
          </form>

          {consents.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-5 text-center text-xs text-[#969696]">
              {loading ? 'Carregando consentimentos...' : 'Nenhum consentimento neste escopo.'}
            </p>
          ) : (
            <ul className="space-y-2.5">
              {consents.map((consent) => {
                const badge = mapConsentBadge(consent.status);
                const busy = actingConsentId === consent.consent_id;
                const isRequested = consent.status === 'requested';
                const canRevoke = consent.status === 'granted';
                return (
                  <li
                    key={consent.consent_id}
                    data-testid={`consent-card-${consent.consent_id}`}
                    className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="font-mono font-semibold text-[#E8E8E8]">
                          {consent.consent_id}
                        </p>
                        <p className="font-mono text-[11px] text-[#969696]">
                          escopo: {formatConsentScope(consent)} · finalidade: {consent.purpose}
                        </p>
                      </div>
                      <StatusBadge {...badge} compact />
                    </div>

                    <div className="flex flex-wrap justify-end gap-2">
                      {isRequested ? (
                        <>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void handleDecideConsent(consent.consent_id, 'granted')}
                            className="inline-flex items-center gap-1 rounded-md border border-[#22C55E]/40 bg-[#22C55E]/10 px-2.5 py-1 text-[11px] font-medium text-[#4ADE80] hover:bg-[#22C55E]/20 disabled:opacity-40"
                          >
                            <Check aria-hidden="true" className="h-3 w-3" />
                            <span>Conceder</span>
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void handleDecideConsent(consent.consent_id, 'denied')}
                            className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                          >
                            <X aria-hidden="true" className="h-3 w-3" />
                            <span>Negar</span>
                          </button>
                        </>
                      ) : null}

                      {canRevoke ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleRevokeConsent(consent.consent_id)}
                          className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                        >
                          <ShieldOff aria-hidden="true" className="h-3 w-3" />
                          <span>Revogar consentimento</span>
                        </button>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section
          aria-label="Memória controlada e retenção"
          className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
        >
          <div className="flex items-center gap-2">
            <Brain aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
              Memória ({memories.length})
            </h3>
          </div>

          <form
            onSubmit={handleCreateMemory}
            className="space-y-3 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3"
          >
            <div className="space-y-1">
              <label htmlFor="memory-new-content" className="block text-xs text-[#969696]">
                Conteúdo da memória (sem segredos)
              </label>
              <textarea
                id="memory-new-content"
                rows={2}
                value={newMemoryContent}
                onChange={(e) => setNewMemoryContent(e.target.value)}
                placeholder="ex.: Preferência de revisão estrita antes de merge"
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
              />
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <label htmlFor="memory-consent-id" className="block text-xs text-[#969696]">
                  ID do consentimento (opcional se concedido)
                </label>
                <input
                  id="memory-consent-id"
                  type="text"
                  list="granted-memory-consents-list"
                  value={newMemoryConsentId}
                  onChange={(e) => setNewMemoryConsentId(e.target.value)}
                  placeholder={grantedMemoryConsents[0]?.consent_id ?? 'consent-id'}
                  className="w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8]"
                />
                <datalist id="granted-memory-consents-list">
                  {grantedMemoryConsents.map((c) => (
                    <option key={c.consent_id} value={c.consent_id} />
                  ))}
                </datalist>
              </div>

              <div className="space-y-1">
                <label htmlFor="memory-retention-select" className="block text-xs text-[#969696]">
                  Política de retenção
                </label>
                <select
                  id="memory-retention-select"
                  value={newRetentionPolicy}
                  onChange={(e) => setNewRetentionPolicy(e.target.value as RetentionPolicy)}
                  className="w-full rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
                >
                  <option value="day">1 dia (day)</option>
                  <option value="month">30 dias (month)</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={creatingMemory}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
            >
              <Plus aria-hidden="true" className="h-3.5 w-3.5" />
              <span>{creatingMemory ? 'Salvando...' : 'Registrar memória'}</span>
            </button>
          </form>

          {memories.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-5 text-center text-xs text-[#969696]">
              {loading ? 'Carregando memórias...' : 'Nenhuma entrada de memória ativa.'}
            </p>
          ) : (
            <ul className="space-y-2.5">
              {memories.map((entry) => {
                const badge = mapMemoryBadge(entry.status);
                const isEditing = editingMemoryId === entry.memory_id;
                const busy = actingMemoryId === entry.memory_id;
                const isRevoked = entry.status === 'revoked';

                return (
                  <li
                    key={entry.memory_id}
                    data-testid={`memory-card-${entry.memory_id}`}
                    className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-[#E8E8E8]">
                            {entry.memory_id}
                          </span>
                          <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] text-[#E8E8E8]">
                            v{entry.version}
                          </span>
                          <span className="font-mono text-[11px] text-[#969696]">
                            retenção: {entry.retention_policy_id}
                          </span>
                        </div>
                        <p className="font-mono text-[11px] text-[#969696]">
                          consent: {entry.consent_id} · autor: {entry.author_ref}
                        </p>
                      </div>
                      <StatusBadge {...badge} compact />
                    </div>

                    <p className="rounded border border-[#303030] bg-[#141414] px-2.5 py-2 text-xs text-[#E8E8E8]">
                      {redactTextForUi(entry.content_redacted)}
                    </p>

                    {isEditing ? (
                      <div className="space-y-2 rounded-lg border border-[#3B82F6]/40 bg-[#141414] p-2.5">
                        <label
                          htmlFor={`edit-memory-content-${entry.memory_id}`}
                          className="block text-[11px] text-[#969696]"
                        >
                          Editar conteúdo (versão esperada: v{editingExpectedVersion})
                        </label>
                        <textarea
                          id={`edit-memory-content-${entry.memory_id}`}
                          rows={2}
                          value={editingContent}
                          onChange={(e) => setEditingContent(e.target.value)}
                          className="w-full rounded border border-[#303030] bg-[#1C1C1C] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
                        />

                        {serverSnapshotHint ? (
                          <p className="text-[11px] text-[#FCD34D]">{serverSnapshotHint}</p>
                        ) : null}

                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <select
                            aria-label="Retenção na edição"
                            value={editingRetentionPolicy}
                            onChange={(e) =>
                              setEditingRetentionPolicy(e.target.value as RetentionPolicy)
                            }
                            className="rounded border border-[#303030] bg-[#1C1C1C] px-2 py-1 text-[11px] text-[#E8E8E8]"
                          >
                            <option value="day">1 dia (day)</option>
                            <option value="month">30 dias (month)</option>
                          </select>

                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={cancelEditingMemory}
                              className="rounded border border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] text-[#969696] hover:text-[#E8E8E8]"
                            >
                              Cancelar
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void handleSaveMemoryEdit(entry)}
                              className="rounded bg-[#E8E8E8] px-2.5 py-1 text-[11px] font-medium text-[#181818] hover:bg-white disabled:opacity-50"
                            >
                              {busy ? 'Salvando...' : 'Salvar edição'}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          disabled={busy || isRevoked}
                          onClick={() => startEditingMemory(entry)}
                          className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-40"
                        >
                          <Edit3 aria-hidden="true" className="h-3 w-3" />
                          <span>Editar</span>
                        </button>
                        <button
                          type="button"
                          disabled={busy || isRevoked}
                          onClick={() => void handleRevokeMemory(entry.memory_id)}
                          className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                        >
                          <ShieldOff aria-hidden="true" className="h-3 w-3" />
                          <span>Revogar memória</span>
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
