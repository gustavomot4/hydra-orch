import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  Copy,
  Download,
  FileCode2,
  FileImage,
  FileText,
  RefreshCw,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  ArtifactPreviewResult,
  formatByteSize,
  getArtifactPreview,
  listRunArtifacts,
  RunArtifactItem,
  SAFE_IMAGE_MIME_TYPES,
} from './artifactApi';
import { DiffViewer } from './DiffViewer';
import { MarkdownSafeView } from './MarkdownSafeView';

export interface ArtifactViewerProps {
  runId?: string | null;
  artifacts?: RunArtifactItem[];
  initialSelectedArtifactId?: string;
  initialPreview?: ArtifactPreviewResult | null;
  client?: ControlPlaneClient;
  onSelectArtifact?: (artifact: RunArtifactItem) => void;
  className?: string;
}

const ARTIFACT_KIND_LABELS: Record<string, string> = {
  all: 'Todos',
  patch: 'Patch / Diff',
  report: 'Relatório',
  log: 'Log',
  check_output: 'Check',
  pr_package: 'Pacote PR',
  handoff: 'Handoff',
  export: 'Export',
};

export function ArtifactViewer({
  runId,
  artifacts: artifactsProp,
  initialSelectedArtifactId,
  initialPreview = null,
  client: clientOverride,
  onSelectArtifact,
  className = '',
}: ArtifactViewerProps) {
  const defaultClient = useControlPlaneClient();
  const client = clientOverride ?? defaultClient;

  const [artifacts, setArtifacts] = useState<RunArtifactItem[]>(artifactsProp ?? []);
  const [listLoading, setListLoading] = useState<boolean>(false);
  const [listError, setListError] = useState<string | null>(null);

  const [kindFilter, setKindFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedId, setSelectedId] = useState<string | null>(
    initialSelectedArtifactId ?? artifactsProp?.[0]?.artifact_id ?? null,
  );

  const [preview, setPreview] = useState<ArtifactPreviewResult | null>(initialPreview);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [previewError, setPreviewError] = useState<{
    status: number;
    code: string;
    message: string;
  } | null>(null);
  const [copiedNotice, setCopiedNotice] = useState<boolean>(false);

  const loadArtifacts = useCallback(async () => {
    if (artifactsProp) {
      setArtifacts(artifactsProp);
      return;
    }
    if (!runId) {
      setArtifacts([]);
      return;
    }
    setListLoading(true);
    setListError(null);
    try {
      const items = await listRunArtifacts(client, runId);
      setArtifacts(items);
      setSelectedId((prev) => {
        if (prev && items.some((a) => a.artifact_id === prev)) {
          return prev;
        }
        return items[0]?.artifact_id ?? null;
      });
    } catch (err) {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : 'Não foi possível listar os artefatos da run.';
      setListError(msg);
    } finally {
      setListLoading(false);
    }
  }, [artifactsProp, client, runId]);

  useEffect(() => {
    void loadArtifacts();
  }, [loadArtifacts]);

  const filteredArtifacts = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return artifacts.filter((item) => {
      if (kindFilter !== 'all' && item.kind !== kindFilter) {
        return false;
      }
      if (!q) {
        return true;
      }
      return (
        item.relative_path.toLowerCase().includes(q) ||
        item.kind.toLowerCase().includes(q) ||
        item.artifact_id.toLowerCase().includes(q)
      );
    });
  }, [artifacts, kindFilter, searchQuery]);

  const selectedArtifact = useMemo(
    () => artifacts.find((a) => a.artifact_id === selectedId) ?? null,
    [artifacts, selectedId],
  );

  const loadPreview = useCallback(
    async (artifact: RunArtifactItem) => {
      const targetRunId = runId || artifact.run_id;
      if (!targetRunId) {
        return;
      }
      setPreviewLoading(true);
      setPreviewError(null);
      try {
        const result = await getArtifactPreview(client, targetRunId, artifact.artifact_id);
        setPreview(result);
      } catch (err) {
        setPreview(null);
        if (err instanceof ControlPlaneApiError) {
          setPreviewError({
            status: err.status,
            code: err.payload.code,
            message: err.payload.message,
          });
        } else {
          setPreviewError({
            status: 500,
            code: 'preview_fetch_failed',
            message: 'Falha ao carregar preview do artefato.',
          });
        }
      } finally {
        setPreviewLoading(false);
      }
    },
    [client, runId],
  );

  useEffect(() => {
    if (initialPreview && selectedArtifact && initialPreview.artifact_id === selectedArtifact.artifact_id) {
      return;
    }
    if (selectedArtifact) {
      void loadPreview(selectedArtifact);
    } else if (!initialPreview) {
      setPreview(null);
      setPreviewError(null);
    }
  }, [selectedArtifact, loadPreview, initialPreview]);

  const handleCopyContent = async () => {
    const text = preview?.sanitized_markdown ?? preview?.content ?? '';
    if (!text || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopiedNotice(true);
      window.setTimeout(() => setCopiedNotice(false), 1500);
    } catch {
      setCopiedNotice(false);
    }
  };

  const renderPreviewBody = () => {
    if (previewLoading) {
      return (
        <div
          data-testid="artifact-preview-loading"
          className="flex min-h-[220px] items-center justify-center rounded-xl border border-[#303030] bg-[#141414] p-6 text-xs text-[#969696]"
        >
          Carregando preview seguro do artefato...
        </div>
      );
    }

    if (previewError) {
      const isTooLarge =
        previewError.status === 413 || previewError.code === 'preview_too_large';
      return (
        <div
          role="alert"
          data-testid={isTooLarge ? 'artifact-too-large-banner' : 'artifact-error-banner'}
          className="rounded-xl border border-[#F59E0B]/40 bg-[#F59E0B]/10 p-5 text-xs text-[#FCD34D]"
        >
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0" />
            <span>
              {isTooLarge
                ? 'Artefato excede o limite de preview seguro (HTTP 413)'
                : `Não foi possível exibir o artefato (${previewError.code})`}
            </span>
          </div>
          <p className="mt-2 text-[#E8E8E8]">{previewError.message}</p>
          {selectedArtifact ? (
            <button
              type="button"
              onClick={() => void loadPreview(selectedArtifact)}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs font-medium text-[#E8E8E8] hover:bg-[#282828]"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Tentar novamente</span>
            </button>
          ) : null}
        </div>
      );
    }

    if (!preview) {
      return (
        <div className="flex min-h-[220px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[#303030] bg-[#141414] p-6 text-center text-xs text-[#969696]">
          <FileText aria-hidden="true" className="h-6 w-6" />
          <span>Selecione um artefato para visualizar seu preview seguro.</span>
        </div>
      );
    }

    if (
      !preview.supported ||
      preview.status === 'unsupported_media_type' ||
      preview.render_mode === 'unsupported'
    ) {
      return (
        <div
          role="status"
          data-testid="artifact-unsupported-banner"
          className="rounded-xl border border-[#303030] bg-[#202020] p-5 text-xs"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-semibold text-[#E8E8E8]">
              <Ban aria-hidden="true" className="h-4 w-4 text-[#FCD34D]" />
              <span>Tipo de mídia não suportado para preview seguro</span>
            </div>
            <StatusBadge status="unavailable" labelOverride="Bloqueado / Não suportado" compact />
          </div>
          <p className="mt-2 text-[#969696]">
            Conteúdo ativo ou binário (HTML, SVG, scripts ou executáveis) nunca é renderizado no
            navegador para prevenir XSS e execução arbitrária.
          </p>
          <dl className="mt-3 grid gap-2 rounded-lg border border-[#303030] bg-[#141414] p-3 sm:grid-cols-3">
            <div>
              <dt className="text-[#969696]">Arquivo</dt>
              <dd className="truncate font-mono text-[#E8E8E8]">{preview.rel_path}</dd>
            </div>
            <div>
              <dt className="text-[#969696]">MIME</dt>
              <dd className="font-mono text-[#E8E8E8]">{preview.mime_type}</dd>
            </div>
            <div>
              <dt className="text-[#969696]">Motivo</dt>
              <dd className="font-mono text-[#E8E8E8]">{preview.reason ?? preview.status}</dd>
            </div>
          </dl>
        </div>
      );
    }

    if (preview.render_mode === 'diff' || preview.kind === 'diff') {
      return <DiffViewer diffText={preview.content ?? ''} filePath={preview.rel_path} />;
    }

    if (preview.render_mode === 'markdown' || preview.kind === 'markdown') {
      return (
        <MarkdownSafeView
          markdown={preview.sanitized_markdown ?? preview.content ?? ''}
          scriptStripped={preview.script_stripped}
          redacted={preview.redacted}
        />
      );
    }

    if (preview.render_mode === 'image' || preview.kind === 'image') {
      if (!SAFE_IMAGE_MIME_TYPES.has(preview.mime_type) || !preview.content_base64) {
        return (
          <div
            data-testid="artifact-unsupported-banner"
            className="rounded-xl border border-[#303030] bg-[#202020] p-4 text-xs text-[#FCD34D]"
          >
            Imagem bloqueada: MIME não permitido para renderização segura ({preview.mime_type}).
          </div>
        );
      }
      const dataUri = `data:${preview.mime_type};base64,${preview.content_base64}`;
      return (
        <div
          data-testid="artifact-image-preview"
          className="space-y-3 rounded-xl border border-[#303030] bg-[#141414] p-4"
        >
          <div className="flex items-center justify-between text-xs text-[#969696]">
            <span className="inline-flex items-center gap-1.5 font-mono text-[#E8E8E8]">
              <FileImage aria-hidden="true" className="h-4 w-4 text-[#969696]" />
              {preview.rel_path}
            </span>
            <span>
              {preview.mime_type} · {formatByteSize(preview.size_bytes)}
            </span>
          </div>
          <div className="flex justify-center overflow-auto rounded-lg border border-[#303030] bg-[#181818] p-3">
            <img
              src={dataUri}
              alt={preview.rel_path}
              className="max-h-[480px] max-w-full rounded object-contain"
            />
          </div>
        </div>
      );
    }

    if (preview.render_mode === 'pdf' || preview.kind === 'pdf') {
      const pdfUri = preview.content_base64
        ? `data:application/pdf;base64,${preview.content_base64}`
        : null;
      return (
        <div
          data-testid="artifact-pdf-preview"
          className="space-y-3 rounded-xl border border-[#303030] bg-[#202020] p-4 text-xs"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText aria-hidden="true" className="h-4 w-4 text-[#E8E8E8]" />
              <span className="font-mono font-medium text-[#E8E8E8]">{preview.rel_path}</span>
              <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]">
                {preview.mime_type} · {formatByteSize(preview.size_bytes)}
              </span>
            </div>
            {pdfUri ? (
              <a
                href={pdfUri}
                download={preview.rel_path.split('/').pop() ?? 'documento.pdf'}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 font-medium text-[#181818] hover:bg-white"
              >
                <Download aria-hidden="true" className="h-3.5 w-3.5" />
                <span>Baixar PDF</span>
              </a>
            ) : null}
          </div>
          {pdfUri ? (
            <iframe
              title={`Preview PDF ${preview.rel_path}`}
              src={pdfUri}
              className="h-[420px] w-full rounded-lg border border-[#303030] bg-[#141414]"
            />
          ) : (
            <p className="text-[#969696]">Conteúdo base64 do PDF indisponível.</p>
          )}
        </div>
      );
    }

    // Default safe monospace text/code preview
    const textLines = (preview.content ?? '').replace(/\r\n/g, '\n').split('\n');
    return (
      <div
        data-testid="artifact-text-preview"
        className="overflow-hidden rounded-xl border border-[#303030] bg-[#141414]"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#303030] bg-[#1C1C1C] px-3 py-2 text-xs">
          <div className="flex items-center gap-2">
            <FileCode2 aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <span className="font-mono font-medium text-[#E8E8E8]">{preview.rel_path}</span>
            {preview.redacted ? (
              <span className="inline-flex items-center gap-1 rounded border border-[#22C55E]/40 bg-[#22C55E]/10 px-1.5 py-0.5 text-[11px] text-[#4ADE80]">
                <ShieldCheck aria-hidden="true" className="h-3 w-3" />
                <span>Segredos redigidos</span>
              </span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => void handleCopyContent()}
            className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] hover:bg-[#282828]"
          >
            <Copy aria-hidden="true" className="h-3 w-3" />
            <span>{copiedNotice ? 'Copiado' : 'Copiar'}</span>
          </button>
        </div>

        <div className="max-h-[480px] overflow-auto font-mono text-xs">
          <table className="w-full border-collapse">
            <tbody>
              {textLines.map((line, idx) => (
                <tr key={idx} className="hover:bg-[#181818]">
                  <td className="w-12 select-none border-r border-[#303030]/60 px-2 py-0.5 text-right tabular-nums text-[#969696]">
                    {idx + 1}
                  </td>
                  <td className="whitespace-pre-wrap break-words px-3 py-0.5 text-[#E8E8E8]">
                    {line}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <section
      aria-label="Visualizador seguro de artefatos e diffs"
      data-testid="artifact-viewer"
      className={`grid gap-3 rounded-xl border border-[#303030] bg-[#181818] p-3 text-[#E8E8E8] lg:grid-cols-[280px_1fr] ${className}`}
    >
      {/* Left list */}
      <aside className="flex flex-col gap-2.5 rounded-xl border border-[#303030] bg-[#1C1C1C] p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-xs font-semibold text-[#E8E8E8]">
            Artefatos ({filteredArtifacts.length})
          </h2>
          {runId && !artifactsProp ? (
            <button
              type="button"
              onClick={() => void loadArtifacts()}
              aria-label="Atualizar lista de artefatos"
              className="rounded-md p-1 text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>

        <div className="relative flex items-center">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-[#969696]"
          />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filtrar artefatos..."
            aria-label="Filtrar artefatos"
            className="w-full rounded-lg border border-[#303030] bg-[#141414] py-1.5 pl-8 pr-2.5 text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>

        <select
          aria-label="Filtrar por tipo de artefato"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          className="rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8] focus:border-[#3B82F6] focus:outline-none"
        >
          {Object.entries(ARTIFACT_KIND_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        {listError ? (
          <div
            role="alert"
            className="rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 p-2 text-xs text-[#FCA5A5]"
          >
            {listError}
          </div>
        ) : null}

        {listLoading ? (
          <p className="py-4 text-center text-xs text-[#969696]">Carregando artefatos...</p>
        ) : filteredArtifacts.length === 0 ? (
          <p className="py-4 text-center text-xs text-[#969696]">
            {runId || artifactsProp
              ? 'Nenhum artefato encontrado para este filtro.'
              : 'Selecione um run para inspecionar artefatos.'}
          </p>
        ) : (
          <ul className="max-h-[460px] space-y-1 overflow-y-auto">
            {filteredArtifacts.map((artifact) => {
              const isSelected = artifact.artifact_id === selectedId;
              return (
                <li key={artifact.artifact_id}>
                  <button
                    type="button"
                    aria-current={isSelected ? 'true' : undefined}
                    onClick={() => {
                      setSelectedId(artifact.artifact_id);
                      onSelectArtifact?.(artifact);
                    }}
                    className={`w-full rounded-lg border p-2 text-left transition-colors ${
                      isSelected
                        ? 'border-[#3B82F6]/60 bg-[#202020] text-[#E8E8E8]'
                        : 'border-transparent bg-[#141414]/60 text-[#969696] hover:bg-[#202020] hover:text-[#E8E8E8]'
                    }`}
                  >
                    <p className="truncate font-mono text-xs font-medium text-[#E8E8E8]">
                      {artifact.relative_path}
                    </p>
                    <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-[#969696]">
                      <span className="rounded bg-[#181818] px-1.5 py-0.5 font-mono">
                        {artifact.kind}
                      </span>
                      <span>{formatByteSize(artifact.size_bytes)}</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </aside>

      {/* Right preview pane */}
      <div className="flex min-w-0 flex-col gap-2.5">
        {preview ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#303030] bg-[#1C1C1C] px-3 py-2 text-xs">
            <span className="truncate font-mono text-[#E8E8E8]">{preview.rel_path}</span>
            <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-[#969696]">
              <span>{preview.mime_type}</span>
              <span>·</span>
              <span>{formatByteSize(preview.size_bytes)}</span>
              <span>·</span>
              <span title={preview.sha256}>sha256:{preview.sha256.slice(0, 10)}</span>
            </div>
          </div>
        ) : null}

        {renderPreviewBody()}
      </div>
    </section>
  );
}
