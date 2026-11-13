import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Boxes,
  Check,
  CheckCircle2,
  FolderSearch,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  X,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient, type ControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  approveDiscoveredResource,
  detectRawSecretInInput,
  extractGovernanceErrorMessage,
  installExtension,
  listDiscoveredResources,
  listExtensions,
  redactTextForUi,
  rejectDiscoveredResource,
  revokeExtension,
  rollbackExtension,
  scanDiscovery,
} from './governanceApi';
import type { ExtensionInstallItem, NormalizedDiscoveredResource } from './governanceTypes';

export interface DiscoveryExtensionsPanelProps {
  client?: ControlPlaneClient;
  className?: string;
}

function mapGovernanceStatusBadge(status: string): { status: string; labelOverride?: string } {
  const key = status.trim().toLowerCase();
  switch (key) {
    case 'untrusted':
      return { status: 'waiting', labelOverride: 'Não confiável' };
    case 'approved':
      return { status: 'accepted', labelOverride: 'Aprovado' };
    case 'active':
      return { status: 'active', labelOverride: 'Ativo' };
    case 'rejected':
      return { status: 'failed', labelOverride: 'Rejeitado' };
    case 'revoked':
      return { status: 'cancelled', labelOverride: 'Revogado' };
    case 'quarantined':
      return { status: 'degraded', labelOverride: 'Em quarentena' };
    case 'rolled_back':
      return { status: 'archived', labelOverride: 'Rollback aplicado' };
    case 'installed':
      return { status: 'ready', labelOverride: 'Instalado' };
    case 'disabled':
      return { status: 'unavailable', labelOverride: 'Desativado' };
    case 'proposed':
      return { status: 'queued', labelOverride: 'Proposto' };
    case 'consented':
      return { status: 'reviewing', labelOverride: 'Consentido' };
    default:
      return { status: key || 'unknown' };
  }
}

export function DiscoveryExtensionsPanel({
  client: clientOverride,
  className = '',
}: DiscoveryExtensionsPanelProps) {
  const hookClient = useControlPlaneClient();
  const client = clientOverride ?? hookClient;

  const [resources, setResources] = useState<NormalizedDiscoveredResource[]>([]);
  const [extensions, setExtensions] = useState<ExtensionInstallItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Discovery opt-in scan form
  const [authorizedRoot, setAuthorizedRoot] = useState('');
  const [optIn, setOptIn] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [actingResourceId, setActingResourceId] = useState<string | null>(null);

  // Extension install & quarantine/rollback form
  const [manifestId, setManifestId] = useState('');
  const [consentId, setConsentId] = useState('');
  const [installing, setInstalling] = useState(false);
  const [quarantineReason, setQuarantineReason] = useState('operator_quarantine');
  const [actingInstallId, setActingInstallId] = useState<string | null>(null);
  const loadGenRef = useRef(0);

  const loadAll = useCallback(
    async (signal?: AbortSignal) => {
      const seq = ++loadGenRef.current;
      setLoading(true);
      setError(null);
      try {
        const [resItems, extItems] = await Promise.all([
          listDiscoveredResources(client, signal),
          listExtensions(client, signal),
        ]);
        if (signal?.aborted || seq !== loadGenRef.current) {
          return;
        }
        setResources(resItems);
        setExtensions(extItems);
      } catch (err) {
        if (signal?.aborted || seq !== loadGenRef.current) {
          return;
        }
        setError(
          extractGovernanceErrorMessage(
            err,
            'Não foi possível carregar discovery e extensões.',
          ),
        );
      } finally {
        if (!signal?.aborted && seq === loadGenRef.current) {
          setLoading(false);
        }
      }
    },
    [client],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadAll(controller.signal);
    return () => controller.abort();
  }, [loadAll]);

  const handleScan = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);

    if (!optIn) {
      setError('É obrigatório marcar o consentimento opt-in antes de iniciar a varredura.');
      return;
    }
    const cleanRoot = authorizedRoot.trim();
    if (!cleanRoot) {
      setError('Informe o diretório raiz autorizado para varredura.');
      return;
    }
    const secretMsg = detectRawSecretInInput(cleanRoot);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }

    loadGenRef.current += 1;
    setScanning(true);
    try {
      const scanned = await scanDiscovery(client, {
        authorized_root: cleanRoot,
        opt_in: true,
      });
      setResources((prev) => {
        const byId = new Map(prev.map((item) => [item.resourceId, item]));
        for (const item of scanned) {
          byId.set(item.resourceId, item);
        }
        return Array.from(byId.values());
      });
      setFeedback(
        `Varredura opt-in concluída em "${cleanRoot}": ${scanned.length} recurso(s) encontrado(s).`,
      );
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao executar varredura opt-in.'));
    } finally {
      setScanning(false);
    }
  };

  const handleApproveResource = async (res: NormalizedDiscoveredResource) => {
    setError(null);
    setFeedback(null);
    if (!res.hash) {
      setError(`Recurso "${res.resourceId}" não possui hash SHA-256 para aprovação.`);
      return;
    }
    loadGenRef.current += 1;
    setActingResourceId(res.resourceId);
    try {
      const updated = await approveDiscoveredResource(client, res.resourceId, res.hash);
      setResources((prev) =>
        prev.map((item) => (item.resourceId === res.resourceId ? updated : item)),
      );
      setFeedback(`Recurso "${res.resourceId}" aprovado por hash.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao aprovar recurso descoberto.'));
    } finally {
      setActingResourceId(null);
    }
  };

  const handleRejectResource = async (res: NormalizedDiscoveredResource) => {
    setError(null);
    setFeedback(null);
    loadGenRef.current += 1;
    setActingResourceId(res.resourceId);
    try {
      const updated = await rejectDiscoveredResource(client, res.resourceId);
      setResources((prev) =>
        prev.map((item) => (item.resourceId === res.resourceId ? updated : item)),
      );
      setFeedback(`Recurso "${res.resourceId}" rejeitado.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao rejeitar recurso descoberto.'));
    } finally {
      setActingResourceId(null);
    }
  };

  const handleInstallExtension = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);

    const cleanManifest = manifestId.trim();
    const cleanConsent = consentId.trim();
    if (!cleanManifest || !cleanConsent) {
      setError('Informe manifest_id e consent_id para instalar a extensão.');
      return;
    }

    loadGenRef.current += 1;
    setInstalling(true);
    try {
      const created = await installExtension(client, {
        manifest_id: cleanManifest,
        consent_id: cleanConsent,
        activate: true,
      });
      setExtensions((prev) => [...prev, created]);
      setManifestId('');
      setConsentId('');
      setFeedback(`Extensão "${created.install_id}" instalada e ativada.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao instalar extensão.'));
    } finally {
      setInstalling(false);
    }
  };

  const handleRevokeExtension = async (installId: string) => {
    setError(null);
    setFeedback(null);
    const reason = quarantineReason.trim() || 'operator_quarantine';
    const secretMsg = detectRawSecretInInput(reason);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }
    loadGenRef.current += 1;
    setActingInstallId(installId);
    try {
      const updated = await revokeExtension(client, installId, reason);
      setExtensions((prev) =>
        prev.map((item) => (item.install_id === installId ? updated : item)),
      );
      setFeedback(`Extensão "${installId}" colocada em quarentena / revogada.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao revogar extensão.'));
    } finally {
      setActingInstallId(null);
    }
  };

  const handleRollbackExtension = async (installId: string) => {
    setError(null);
    setFeedback(null);
    loadGenRef.current += 1;
    setActingInstallId(installId);
    try {
      const updated = await rollbackExtension(client, installId);
      setExtensions((prev) =>
        prev.map((item) => (item.install_id === installId ? updated : item)),
      );
      setFeedback(`Rollback da extensão "${installId}" concluído.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao executar rollback da extensão.'));
    } finally {
      setActingInstallId(null);
    }
  };

  return (
    <div data-testid="discovery-extensions-panel" className={`flex flex-col gap-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#303030] bg-[#1C1C1C] px-4 py-3">
        <div className="space-y-0.5">
          <h2 className="text-sm font-semibold text-[#E8E8E8]">
            Discovery Opt-in e Ciclo de Vida de Extensões
          </h2>
          <p className="text-xs text-[#969696]">
            Arquivos descobertos são dados não confiáveis até aprovação por hash; extensões suportam quarentena imediata e rollback.
          </p>
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

      <section
        aria-label="Varredura opt-in e aprovação por hash"
        className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <div className="flex items-center gap-2">
          <FolderSearch aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
            Discovery Opt-in ({resources.length})
          </h3>
        </div>

        <form
          onSubmit={handleScan}
          className="space-y-3 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3"
        >
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1 space-y-1">
              <label htmlFor="discovery-root-input" className="block text-xs text-[#969696]">
                Raiz autorizada para varredura
              </label>
              <input
                id="discovery-root-input"
                type="text"
                value={authorizedRoot}
                onChange={(e) => setAuthorizedRoot(e.target.value)}
                placeholder="/workspace/projeto"
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
              />
            </div>

            <button
              type="submit"
              disabled={!optIn || authorizedRoot.trim().length === 0 || scanning}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-4 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FolderSearch aria-hidden="true" className="h-3.5 w-3.5" />
              <span>{scanning ? 'Varrendo...' : 'Executar varredura opt-in'}</span>
            </button>
          </div>

          <label className="flex items-start gap-2 text-xs text-[#E8E8E8]">
            <input
              id="discovery-opt-in-checkbox"
              type="checkbox"
              checked={optIn}
              onChange={(e) => setOptIn(e.target.checked)}
              className="mt-0.5 accent-[#3B82F6]"
            />
            <span>
              Confirmo opt-in explícito para varredura apenas na raiz autorizada. Manifestos permanecem não confiáveis até aprovação explícita do hash.
            </span>
          </label>
        </form>

        {resources.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-5 text-center text-xs text-[#969696]">
            {loading ? 'Carregando recursos descobertos...' : 'Nenhum recurso descoberto.'}
          </p>
        ) : (
          <ul className="space-y-2.5">
            {resources.map((res) => {
              const badge = mapGovernanceStatusBadge(res.status);
              const busy = actingResourceId === res.resourceId;
              const isFinalRejected =
                res.status === 'rejected' || res.status === 'revoked';
              return (
                <li
                  key={res.resourceId}
                  data-testid={`discovery-resource-${res.resourceId}`}
                  className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[#969696]">
                          {res.kind}
                        </span>
                        <span className="font-mono font-semibold text-[#E8E8E8]">
                          {res.resourceId}
                        </span>
                      </div>
                      <p className="truncate font-mono text-[11px] text-[#969696]">
                        {redactTextForUi(res.path)}
                      </p>
                    </div>
                    <StatusBadge {...badge} compact />
                  </div>

                  <p className="truncate font-mono text-[11px] text-[#969696]">
                    Hash: {res.hash || '—'}
                  </p>

                  {res.capabilities.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {res.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className="flex flex-wrap justify-end gap-2 pt-1">
                    <button
                      type="button"
                      disabled={busy || !res.hash || res.status === 'approved' || res.status === 'active'}
                      onClick={() => void handleApproveResource(res)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#22C55E]/40 bg-[#22C55E]/10 px-2.5 py-1 text-[11px] font-medium text-[#4ADE80] hover:bg-[#22C55E]/20 disabled:opacity-40"
                    >
                      <Check aria-hidden="true" className="h-3 w-3" />
                      <span>Aprovar hash</span>
                    </button>
                    <button
                      type="button"
                      disabled={busy || isFinalRejected}
                      onClick={() => void handleRejectResource(res)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                    >
                      <X aria-hidden="true" className="h-3 w-3" />
                      <span>Rejeitar</span>
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section
        aria-label="Extensões instaladas"
        className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Boxes aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
              Extensões ({extensions.length})
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="extension-quarantine-reason" className="text-xs text-[#969696]">
              Motivo quarentena:
            </label>
            <input
              id="extension-quarantine-reason"
              type="text"
              value={quarantineReason}
              onChange={(e) => setQuarantineReason(e.target.value)}
              className="w-44 rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1 text-xs text-[#E8E8E8]"
            />
          </div>
        </div>

        <form
          onSubmit={handleInstallExtension}
          className="grid gap-3 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 md:grid-cols-3"
        >
          <div className="space-y-1">
            <label htmlFor="extension-manifest-id" className="block text-xs text-[#969696]">
              ID do manifesto (manifest_id)
            </label>
            <input
              id="extension-manifest-id"
              type="text"
              value={manifestId}
              onChange={(e) => setManifestId(e.target.value)}
              placeholder="ext-manifest-01"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="extension-consent-id" className="block text-xs text-[#969696]">
              ID do consentimento (consent_id)
            </label>
            <input
              id="extension-consent-id"
              type="text"
              value={consentId}
              onChange={(e) => setConsentId(e.target.value)}
              placeholder="consent-ext-01"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={installing}
              className="w-full rounded-lg bg-[#E8E8E8] px-4 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
            >
              {installing ? 'Instalando...' : 'Instalar e ativar extensão'}
            </button>
          </div>
        </form>

        {extensions.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-5 text-center text-xs text-[#969696]">
            {loading ? 'Carregando extensões...' : 'Nenhuma extensão instalada.'}
          </p>
        ) : (
          <ul className="space-y-2.5">
            {extensions.map((ext) => {
              const badge = mapGovernanceStatusBadge(ext.status);
              const busy = actingInstallId === ext.install_id;
              const isTerminal = ext.status === 'revoked' || ext.status === 'rolled_back';
              return (
                <li
                  key={ext.install_id}
                  data-testid={`extension-card-${ext.install_id}`}
                  className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[#E8E8E8]">
                          {ext.name ? `${ext.name}${ext.version ? ` v${ext.version}` : ''}` : ext.extension_manifest_id}
                        </span>
                        <span className="font-mono text-[11px] text-[#969696]">
                          install: {ext.install_id}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-[#969696]">
                        manifest: {ext.extension_manifest_id} · consent: {ext.consent_record_id}
                      </p>
                    </div>
                    <StatusBadge {...badge} compact />
                  </div>

                  <div className="flex flex-wrap justify-end gap-2 pt-1">
                    <button
                      type="button"
                      disabled={busy || isTerminal}
                      onClick={() => void handleRevokeExtension(ext.install_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#F59E0B]/40 bg-[#F59E0B]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCD34D] hover:bg-[#F59E0B]/20 disabled:opacity-40"
                    >
                      <ShieldAlert aria-hidden="true" className="h-3 w-3" />
                      <span>Quarentena / Revogar</span>
                    </button>
                    <button
                      type="button"
                      disabled={busy || isTerminal}
                      onClick={() => void handleRollbackExtension(ext.install_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] font-medium text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-40"
                    >
                      <RotateCcw aria-hidden="true" className="h-3 w-3" />
                      <span>Rollback</span>
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
