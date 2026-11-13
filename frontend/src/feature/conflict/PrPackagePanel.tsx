import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2,
  FileCode2,
  GitBranch,
  Package,
  RefreshCw,
  ShieldAlert,
  Upload,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { MarkdownSafeView } from '@/feature/artifact';
import { useControlPlaneClient, type ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  buildPrPackage,
  formatNullableMetric,
  getPrPackage,
  publishPrPackage,
  type PRPackage,
  type PublishResult,
} from './conflictApi';

export interface PrPackagePanelProps {
  runId: string;
  client?: ControlPlaneClient;
  onPublished?: (result: PublishResult) => void;
  className?: string;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ControlPlaneApiError) {
    return `${error.payload.message} (${error.payload.code})`;
  }
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

export function PrPackagePanel({
  runId,
  client: clientOverride,
  onPublished,
  className = '',
}: PrPackagePanelProps) {
  const hookClient = useControlPlaneClient();
  const client = clientOverride ?? hookClient;

  const [prPackage, setPrPackage] = useState<PRPackage | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Build state
  const [prBranchInput, setPrBranchInput] = useState<string>('');
  const [createGitBranch, setCreateGitBranch] = useState<boolean>(false);
  const [building, setBuilding] = useState<boolean>(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  // Publish state — explicit opt-in checkbox ALWAYS starts false
  const [remote, setRemote] = useState<string>('origin');
  const [authorized, setAuthorized] = useState<boolean>(false);
  const [publishing, setPublishing] = useState<boolean>(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);

  const loadPackage = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setLoadError(null);
      try {
        const fetched = await getPrPackage(client, runId, signal);
        if (!signal?.aborted) {
          setPrPackage(fetched);
        }
      } catch (error) {
        if (!signal?.aborted) {
          setLoadError(getErrorMessage(error, 'Erro ao carregar pacote de PR do run.'));
        }
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [client, runId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadPackage(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadPackage]);

  const handleBuildPackage = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBuilding(true);
    setBuildError(null);
    setPublishResult(null);
    try {
      const created = await buildPrPackage(client, runId, {
        pr_branch: prBranchInput.trim().length > 0 ? prBranchInput.trim() : null,
        create_git_branch: createGitBranch,
      });
      setPrPackage(created);
      setAuthorized(false);
    } catch (error) {
      setBuildError(getErrorMessage(error, 'Falha ao gerar pacote de PR.'));
    } finally {
      setBuilding(false);
    }
  };

  const handlePublish = async () => {
    if (!authorized || !prPackage) {
      return;
    }
    setPublishing(true);
    setPublishError(null);
    try {
      const result = await publishPrPackage(client, runId, {
        authorized: true,
        remote: remote.trim().length > 0 ? remote.trim() : 'origin',
      });
      setPublishResult(result);
      onPublished?.(result);
    } catch (error) {
      setPublishError(getErrorMessage(error, 'Falha ao publicar pacote de PR.'));
    } finally {
      setPublishing(false);
    }
  };

  return (
    <section
      aria-label="Pacote de Pull Request e Publicação"
      className={`flex flex-col gap-4 rounded-md border border-[#303030] bg-[#141414] p-4 text-[#E8E8E8] ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#303030] pb-3">
        <div className="flex items-center gap-2.5">
          <Package className="h-4 w-4 text-[#969696]" />
          <div>
            <h2 className="text-sm font-semibold text-[#E8E8E8]">Pacote de Pull Request (PR)</h2>
            <p className="font-mono text-xs text-[#969696]">run: {runId}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {prPackage ? (
            <StatusBadge status="ready" labelOverride="Pacote pronto" compact />
          ) : (
            <StatusBadge status="waiting" labelOverride="Não gerado" compact />
          )}
          <button
            type="button"
            onClick={() => void loadPackage()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs font-medium text-[#E8E8E8] hover:border-[#4A4A4A] disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </button>
        </div>
      </header>

      {loadError ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
        >
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span>{loadError}</span>
        </div>
      ) : null}

      {/* Formulário para gerar / reconstruir o pacote */}
      <form
        onSubmit={handleBuildPackage}
        className="flex flex-wrap items-end gap-3 rounded-md border border-[#303030] bg-[#181818] p-3"
      >
        <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-xs">
          <span className="font-medium text-[#E8E8E8]">Nome da branch de PR (opcional)</span>
          <input
            type="text"
            value={prBranchInput}
            onChange={(e) => setPrBranchInput(e.target.value)}
            placeholder="Ex.: hydra/run-123-pr"
            className="rounded border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8] placeholder:text-[#6B6B6B]"
          />
        </label>

        <label className="inline-flex cursor-pointer items-center gap-2 pb-1.5 text-xs text-[#E8E8E8]">
          <input
            type="checkbox"
            checked={createGitBranch}
            onChange={(e) => setCreateGitBranch(e.target.checked)}
          />
          <span>Criar branch Git local</span>
        </label>

        <button
          type="submit"
          disabled={building}
          className="inline-flex items-center gap-1.5 rounded border border-[#3B82F6]/60 bg-[#2563EB]/20 px-3 py-1.5 text-xs font-medium text-[#93C5FD] hover:bg-[#2563EB]/30 disabled:opacity-50"
        >
          <Package className="h-3.5 w-3.5" />
          {building ? 'Gerando pacote...' : prPackage ? 'Regerar pacote de PR' : 'Gerar pacote de PR'}
        </button>
      </form>

      {buildError ? (
        <div
          role="alert"
          className="rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
        >
          {buildError}
        </div>
      ) : null}

      {!prPackage && !loading ? (
        <div className="rounded-md border border-[#303030] bg-[#181818] px-3 py-5 text-center text-xs text-[#969696]">
          Nenhum pacote de PR gerado para este run ainda. Utilize o formulário acima para montar o
          dossiê determinístico do PR.
        </div>
      ) : null}

      {prPackage ? (
        <div className="flex flex-col gap-4">
          {/* Metadados e Resumo de Diff / Checks */}
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-md border border-[#303030] bg-[#181818] p-3 text-xs">
              <div className="mb-1.5 flex items-center gap-1.5 font-semibold uppercase tracking-wide text-[#969696]">
                <GitBranch className="h-3.5 w-3.5" />
                Branches e SHAs
              </div>
              <dl className="space-y-1 font-mono text-[11px]">
                <div className="flex justify-between gap-2">
                  <dt className="text-[#969696]">package_id:</dt>
                  <dd className="truncate text-[#E8E8E8]">{prPackage.package_id}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-[#969696]">pr_branch:</dt>
                  <dd className="truncate text-[#93C5FD]">{prPackage.pr_branch}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-[#969696]">base_branch:</dt>
                  <dd className="truncate text-[#E8E8E8]">{prPackage.base_branch}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-[#969696]">head_sha:</dt>
                  <dd className="truncate text-[#E8E8E8]">{prPackage.head_sha}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-[#969696]">base_sha:</dt>
                  <dd className="truncate text-[#E8E8E8]">{prPackage.base_sha}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-md border border-[#303030] bg-[#181818] p-3 text-xs">
              <div className="mb-1.5 font-semibold uppercase tracking-wide text-[#969696]">
                Checks do Run
              </div>
              <dl className="space-y-1 font-mono text-[11px]">
                <div className="flex justify-between">
                  <dt className="text-[#969696]">Total:</dt>
                  <dd className="text-[#E8E8E8]">{prPackage.checks_summary.total}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-[#969696]">Aprovados:</dt>
                  <dd className="text-[#4ADE80]">{prPackage.checks_summary.passed}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-[#969696]">Falhos:</dt>
                  <dd className="text-[#FCA5A5]">{prPackage.checks_summary.failed}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-md border border-[#303030] bg-[#181818] p-3 text-xs">
              <div className="mb-1.5 flex items-center gap-1.5 font-semibold uppercase tracking-wide text-[#969696]">
                <FileCode2 className="h-3.5 w-3.5" />
                Resumo do Diff
              </div>
              <dl className="space-y-1 font-mono text-[11px]">
                <div className="flex justify-between">
                  <dt className="text-[#969696]">Arquivos alterados:</dt>
                  <dd className="text-[#E8E8E8]">{prPackage.diff_summary.files_changed}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-[#969696]">Inserções:</dt>
                  <dd className="text-[#4ADE80]">
                    {formatNullableMetric(prPackage.diff_summary.insertions, 'Desconhecido')}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-[#969696]">Remoções:</dt>
                  <dd className="text-[#FCA5A5]">
                    {formatNullableMetric(prPackage.diff_summary.deletions, 'Desconhecido')}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          {/* Tabela de arquivos do diff */}
          {prPackage.diff_summary.files.length > 0 ? (
            <div className="overflow-x-auto rounded-md border border-[#303030] bg-[#181818]">
              <table className="w-full text-left font-mono text-xs">
                <thead className="border-b border-[#303030] bg-[#202020] text-[11px] uppercase text-[#969696]">
                  <tr>
                    <th className="px-3 py-1.5">Arquivo</th>
                    <th className="px-3 py-1.5 text-right">+ Inserções</th>
                    <th className="px-3 py-1.5 text-right">- Remoções</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#262626]">
                  {prPackage.diff_summary.files.map((file) => (
                    <tr key={file.path}>
                      <td className="px-3 py-1.5 text-[#E8E8E8]">{file.path}</td>
                      <td className="px-3 py-1.5 text-right text-[#4ADE80]">
                        {formatNullableMetric(file.insertions, '—')}
                      </td>
                      <td className="px-3 py-1.5 text-right text-[#FCA5A5]">
                        {formatNullableMetric(file.deletions, '—')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {/* Descrição do PR renderizada com segurança */}
          <div className="flex flex-col gap-2 rounded-md border border-[#303030] bg-[#181818] p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#969696]">
              Descrição do PR (Markdown seguro)
            </h3>
            <MarkdownSafeView markdown={prPackage.description_markdown} />
          </div>

          {/* Publicação remota protegida por autorização explícita */}
          <div className="flex flex-col gap-3 rounded-md border border-[#F59E0B]/40 bg-[#1C1C1C] p-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[#FCD34D]">
                Publicação Remota (Exige Autorização Explícita)
              </h3>
              {prPackage.artifact_path ? (
                <span className="truncate font-mono text-[11px] text-[#969696]">
                  artefato: {prPackage.artifact_path}
                </span>
              ) : null}
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <label className="flex min-w-[180px] flex-col gap-1 text-xs">
                <span className="font-medium text-[#E8E8E8]">Remote Git de destino</span>
                <input
                  type="text"
                  value={remote}
                  onChange={(e) => setRemote(e.target.value)}
                  className="rounded border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8]"
                />
              </label>

              <label className="flex flex-1 cursor-pointer items-start gap-2 rounded border border-[#303030] bg-[#141414] px-3 py-2 text-xs text-[#E8E8E8]">
                <input
                  type="checkbox"
                  checked={authorized}
                  onChange={(e) => setAuthorized(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  Autorizo explicitamente a publicação remota (git push) desta branch de PR (
                  <span className="font-mono">{prPackage.pr_branch}</span>) para{' '}
                  <span className="font-mono">{remote.trim() || 'origin'}</span>.
                </span>
              </label>

              <button
                type="button"
                onClick={() => void handlePublish()}
                disabled={!authorized || publishing}
                className="inline-flex items-center gap-1.5 rounded border border-[#22C55E]/50 bg-[#22C55E]/15 px-3 py-2 text-xs font-medium text-[#86EFAC] hover:bg-[#22C55E]/25 disabled:cursor-not-allowed disabled:opacity-45"
              >
                <Upload className="h-3.5 w-3.5" />
                {publishing ? 'Publicando...' : 'Publicar pacote de PR'}
              </button>
            </div>

            {publishError ? (
              <div
                role="alert"
                className="rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
              >
                {publishError}
              </div>
            ) : null}

            {publishResult ? (
              <div
                role="status"
                className="flex items-center gap-2 rounded border border-[#22C55E]/40 bg-[#22C55E]/10 px-3 py-2 text-xs text-[#86EFAC]"
              >
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>
                  Publicado em <span className="font-mono">{publishResult.remote}</span> /{' '}
                  <span className="font-mono">{publishResult.pr_branch}</span> · sha:{' '}
                  <span className="font-mono">{publishResult.pushed_sha}</span>
                </span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
