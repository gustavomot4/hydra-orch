import {
  Check,
  FileCode2,
  FileImage,
  FileText,
  RefreshCw,
  Server,
  Trash2,
  X,
} from 'lucide-react';
import { StatusBadge, StatusKind } from '@/component/StatusBadge';
import {
  ATTACHMENT_STATUS_LABELS,
  AttachmentItemView,
  AttachmentUploadPhase,
  formatAttachmentSize,
  formatSha256Prefix,
} from './attachmentTypes';

export interface AttachmentListProps {
  items: AttachmentItemView[];
  onConfirmTransfer?: (item: AttachmentItemView) => void | Promise<void>;
  onRetry?: (item: AttachmentItemView) => void | Promise<void>;
  onDismiss?: (item: AttachmentItemView) => void;
  onRemove?: (item: AttachmentItemView) => void;
  emptyLabel?: string;
  hideWhenEmpty?: boolean;
  className?: string;
}

function resolveBadgeStatus(phase: AttachmentUploadPhase): StatusKind {
  switch (phase) {
    case 'preparando':
      return 'queued';
    case 'enviando':
      return 'running';
    case 'local_ready':
      return 'ready';
    case 'pending_remote_confirm':
      return 'waiting';
    case 'transferred':
      return 'succeeded';
    case 'erro':
      return 'failed';
  }
}

function AttachmentIcon({ mimeType }: { mimeType: string }) {
  if (mimeType.startsWith('image/')) {
    return <FileImage aria-hidden="true" className="h-4 w-4 shrink-0 text-[#93C5FD]" />;
  }
  if (
    mimeType.includes('python') ||
    mimeType.includes('typescript') ||
    mimeType.includes('json') ||
    mimeType.includes('yaml') ||
    mimeType.includes('toml') ||
    mimeType.includes('diff') ||
    mimeType.includes('patch')
  ) {
    return <FileCode2 aria-hidden="true" className="h-4 w-4 shrink-0 text-[#4ADE80]" />;
  }
  return <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-[#E8E8E8]" />;
}

export function AttachmentList({
  items,
  onConfirmTransfer,
  onRetry,
  onDismiss,
  onRemove,
  emptyLabel = 'Nenhum anexo vinculado a esta sessão.',
  hideWhenEmpty = false,
  className = '',
}: AttachmentListProps) {
  if (items.length === 0) {
    if (hideWhenEmpty) {
      return null;
    }
    return (
      <div
        data-testid="attachment-list-empty"
        className={`rounded-xl border border-dashed border-[#303030] bg-[#141414]/60 px-3 py-3 text-xs text-[#969696] ${className}`}
      >
        {emptyLabel}
      </div>
    );
  }

  return (
    <ul
      aria-label="Anexos da sessão"
      data-testid="attachment-list"
      className={`space-y-2 ${className}`}
    >
      {items.map((item) => {
        const isRemote = item.host_id !== 'local';
        const needsConfirm = item.status === 'pending_remote_confirm';
        const isError = item.status === 'erro';
        const canRemove =
          onRemove && item.status !== 'preparando' && item.status !== 'enviando';

        return (
          <li
            key={item.id}
            data-testid={`attachment-item-${item.id}`}
            data-upload-status={item.status}
            className="rounded-xl border border-[#303030] bg-[#202020] px-3 py-2.5 text-xs text-[#E8E8E8]"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="flex min-w-0 flex-1 items-start gap-2.5">
                <div className="mt-0.5">
                  <AttachmentIcon mimeType={item.mime_type} />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium text-[#E8E8E8]">
                      {item.filename}
                    </span>
                    <StatusBadge
                      status={resolveBadgeStatus(item.status)}
                      labelOverride={ATTACHMENT_STATUS_LABELS[item.status]}
                      compact
                    />
                    {isRemote || needsConfirm ? (
                      <span
                        data-testid={`attachment-host-badge-${item.id}`}
                        className="inline-flex items-center gap-1 rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
                      >
                        <Server aria-hidden="true" className="h-3 w-3 text-[#969696]" />
                        <span>Destino: {item.host_id}</span>
                      </span>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#969696]">
                    <span className="font-mono">{item.mime_type}</span>
                    <span>{formatAttachmentSize(item.size_bytes)}</span>
                    <span className="font-mono" title={item.sha256 ?? undefined}>
                      SHA-256: {formatSha256Prefix(item.sha256, 12)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                {needsConfirm && onConfirmTransfer && item.attachment_id ? (
                  <button
                    type="button"
                    disabled={Boolean(item.confirming)}
                    onClick={() => void onConfirmTransfer(item)}
                    aria-label={`Confirmar transferência de ${item.filename} para ${item.host_id}`}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-2.5 py-1 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Check aria-hidden="true" className="h-3.5 w-3.5" />
                    <span>
                      {item.confirming ? 'Confirmando...' : 'Confirmar transferência'}
                    </span>
                  </button>
                ) : null}

                {isError && item.file && onRetry ? (
                  <button
                    type="button"
                    onClick={() => void onRetry(item)}
                    aria-label={`Tentar novamente upload de ${item.filename}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#141414] px-2 py-1 text-xs text-[#E8E8E8] hover:bg-[#282828]"
                  >
                    <RefreshCw aria-hidden="true" className="h-3 w-3" />
                    <span>Tentar novamente</span>
                  </button>
                ) : null}

                {isError && onDismiss ? (
                  <button
                    type="button"
                    onClick={() => onDismiss(item)}
                    aria-label={`Dispensar erro de ${item.filename}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#141414] px-2 py-1 text-xs text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]"
                  >
                    <X aria-hidden="true" className="h-3 w-3" />
                    <span>Dispensar</span>
                  </button>
                ) : null}

                {!isError && canRemove ? (
                  <button
                    type="button"
                    onClick={() => onRemove(item)}
                    aria-label={`Remover anexo ${item.filename}`}
                    className="inline-flex items-center justify-center rounded-lg border border-transparent p-1 text-[#969696] hover:border-[#303030] hover:bg-[#282828] hover:text-[#FCA5A5]"
                  >
                    <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
            </div>

            {isError && item.error_message ? (
              <p className="mt-2 rounded-lg border border-[#EF4444]/30 bg-[#EF4444]/10 px-2.5 py-1.5 text-[11px] text-[#FCA5A5]">
                {item.error_message}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
