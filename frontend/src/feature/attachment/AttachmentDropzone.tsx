import {
  ChangeEvent,
  ClipboardEvent,
  DragEvent,
  ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import { AlertTriangle, Paperclip, RefreshCw, Upload, X } from 'lucide-react';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  bytesToBase64,
  computeSha256Hex,
  confirmAttachmentTransfer,
  readFileBytes,
  uploadSessionAttachment,
} from './attachmentApi';
import { AttachmentList } from './AttachmentList';
import {
  AttachmentErrorNotice,
  AttachmentItemView,
  AttachmentRef,
  DEFAULT_ATTACHMENT_MAX_BYTES,
  SAFE_ATTACHMENT_ACCEPT,
  attachmentRefToView,
  formatAttachmentSize,
  validateAttachmentFile,
} from './attachmentTypes';

export interface AttachmentDropzoneProps {
  sessionId: string | null;
  workspaceId: string;
  hostId?: string;
  maxBytes?: number;
  disabled?: boolean;
  multiple?: boolean;
  showList?: boolean;
  client?: ControlPlaneClient;
  attachments?: AttachmentItemView[];
  onAttachmentsChange?: (items: AttachmentItemView[]) => void;
  onUploaded?: (attachment: AttachmentRef) => void;
  onConfirmed?: (attachment: AttachmentRef) => void;
  onError?: (error: { filename: string; code: string; message: string }) => void;
  className?: string;
  children?: ReactNode;
}

function formatUploadError(err: unknown): { code: string; message: string } {
  if (err instanceof ControlPlaneApiError) {
    return {
      code: err.payload.code,
      message: err.payload.message,
    };
  }
  if (err instanceof Error && err.message.trim().length > 0) {
    return {
      code: 'upload_failed',
      message: err.message,
    };
  }
  return {
    code: 'upload_failed',
    message: 'Falha ao enviar anexo para o Control Plane.',
  };
}

function extractPasteFiles(clipboardData: DataTransfer | null): File[] {
  if (!clipboardData) {
    return [];
  }
  const directFiles = Array.from(clipboardData.files ?? []);
  if (directFiles.length > 0) {
    return directFiles;
  }
  const itemFiles: File[] = [];
  const items = Array.from(clipboardData.items ?? []);
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile();
      if (file) {
        itemFiles.push(file);
      }
    }
  }
  return itemFiles;
}

export function AttachmentDropzone({
  sessionId,
  workspaceId,
  hostId = 'local',
  maxBytes = DEFAULT_ATTACHMENT_MAX_BYTES,
  disabled = false,
  multiple = true,
  showList = true,
  client,
  attachments,
  onAttachmentsChange,
  onUploaded,
  onConfirmed,
  onError,
  className = '',
  children,
}: AttachmentDropzoneProps) {
  const defaultClient = useControlPlaneClient();
  const activeClient = client ?? defaultClient;

  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const seqRef = useRef(0);

  const [internalItems, setInternalItems] = useState<AttachmentItemView[]>([]);
  const [isDragActive, setIsDragActive] = useState(false);
  const [errorBanner, setErrorBanner] = useState<AttachmentErrorNotice | null>(null);

  const resolvedItems = attachments ?? internalItems;
  const itemsRef = useRef<AttachmentItemView[]>(resolvedItems);
  itemsRef.current = resolvedItems;

  useEffect(() => {
    if (attachments !== undefined) {
      itemsRef.current = attachments;
    }
  }, [attachments]);

  const commitItems = useCallback(
    (updater: (prev: AttachmentItemView[]) => AttachmentItemView[]) => {
      const next = updater(itemsRef.current);
      itemsRef.current = next;
      if (attachments === undefined) {
        setInternalItems(next);
      }
      onAttachmentsChange?.(next);
    },
    [attachments, onAttachmentsChange],
  );

  const nextLocalId = (prefix: string) => {
    seqRef.current += 1;
    return `${prefix}-${Date.now()}-${seqRef.current}`;
  };

  const uploadSingleFile = useCallback(
    async (file: File, existingItemId?: string) => {
      const activeSessionId = sessionId?.trim() ?? '';
      if (!activeSessionId) {
        const notice: AttachmentErrorNotice = {
          id: nextLocalId('err'),
          filename: file.name || '(arquivo)',
          code: 'missing_session_id',
          message: 'Selecione ou inicie uma sessão antes de anexar arquivos.',
          retryable: false,
        };
        setErrorBanner(notice);
        onError?.({ filename: notice.filename, code: notice.code, message: notice.message });
        return;
      }

      const validation = validateAttachmentFile(file, maxBytes);
      if (!validation.ok) {
        const notice: AttachmentErrorNotice = {
          id: nextLocalId('err'),
          filename: file.name || '(arquivo)',
          code: validation.code,
          message: validation.message,
          retryable: false,
        };
        setErrorBanner(notice);
        onError?.({
          filename: notice.filename,
          code: validation.code,
          message: validation.message,
        });
        return;
      }

      const itemId = existingItemId ?? nextLocalId('att-pending');
      const preparingItem: AttachmentItemView = {
        id: itemId,
        attachment_id: null,
        workspace_id: workspaceId,
        session_id: activeSessionId,
        host_id: hostId,
        filename: validation.filename,
        mime_type: validation.mimeType,
        size_bytes: file.size,
        sha256: null,
        storage_rel_path: null,
        status: 'preparando',
        remote_confirmed: false,
        created_at: null,
        error_message: null,
        error_code: null,
        file,
      };

      commitItems((prev) => {
        const idx = prev.findIndex((entry) => entry.id === itemId);
        if (idx === -1) {
          return [...prev, preparingItem];
        }
        const copy = [...prev];
        copy[idx] = preparingItem;
        return copy;
      });
      setErrorBanner((prev) => (prev?.itemId === itemId ? null : prev));

      try {
        const rawBytes = await readFileBytes(file);
        const contentBase64 = bytesToBase64(rawBytes);
        const sha256Prefix = await computeSha256Hex(rawBytes);

        commitItems((prev) =>
          prev.map((entry) =>
            entry.id === itemId
              ? {
                  ...entry,
                  status: 'enviando',
                  sha256: sha256Prefix,
                }
              : entry,
          ),
        );

        const created = await uploadSessionAttachment(activeClient, activeSessionId, {
          workspace_id: workspaceId,
          filename: validation.filename,
          content_base64: contentBase64,
          mime_type: validation.mimeType,
          host_id: hostId,
        });

        const view = attachmentRefToView(created);
        commitItems((prev) =>
          prev.map((entry) => (entry.id === itemId ? view : entry)),
        );
        onUploaded?.(created);
      } catch (err) {
        const formatted = formatUploadError(err);
        commitItems((prev) =>
          prev.map((entry) =>
            entry.id === itemId
              ? {
                  ...entry,
                  status: 'erro',
                  error_code: formatted.code,
                  error_message: formatted.message,
                  file,
                }
              : entry,
          ),
        );
        setErrorBanner({
          id: nextLocalId('err'),
          itemId,
          filename: validation.filename,
          code: formatted.code,
          message: formatted.message,
          retryable: true,
          file,
        });
        onError?.({
          filename: validation.filename,
          code: formatted.code,
          message: formatted.message,
        });
      }
    },
    [sessionId, workspaceId, hostId, maxBytes, activeClient, commitItems, onUploaded, onError],
  );

  const processFiles = useCallback(
    async (files: File[]) => {
      if (disabled || files.length === 0) {
        return;
      }
      const selected = multiple ? files : [files[0]];
      for (const file of selected) {
        await uploadSingleFile(file);
      }
    },
    [disabled, multiple, uploadSingleFile],
  );

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (files.length > 0) {
      void processFiles(files);
    }
  };

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current += 1;
    setIsDragActive(true);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDragActive(false);
    const files = Array.from(event.dataTransfer?.files ?? []);
    if (files.length > 0) {
      void processFiles(files);
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    if (disabled) {
      return;
    }
    const files = extractPasteFiles(event.clipboardData);
    if (files.length > 0) {
      event.preventDefault();
      void processFiles(files);
    }
  };

  const handleConfirmTransfer = useCallback(
    async (item: AttachmentItemView) => {
      if (!item.attachment_id) {
        return;
      }
      commitItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id ? { ...entry, confirming: true } : entry,
        ),
      );
      try {
        const confirmed = await confirmAttachmentTransfer(
          activeClient,
          item.session_id,
          item.attachment_id,
        );
        const view = attachmentRefToView(confirmed);
        commitItems((prev) =>
          prev.map((entry) => (entry.id === item.id ? view : entry)),
        );
        onConfirmed?.(confirmed);
      } catch (err) {
        const formatted = formatUploadError(err);
        commitItems((prev) =>
          prev.map((entry) =>
            entry.id === item.id ? { ...entry, confirming: false } : entry,
          ),
        );
        setErrorBanner({
          id: nextLocalId('err'),
          itemId: item.id,
          filename: item.filename,
          code: formatted.code,
          message: `Falha ao confirmar transferência para ${item.host_id}: ${formatted.message}`,
          retryable: false,
        });
        onError?.({
          filename: item.filename,
          code: formatted.code,
          message: formatted.message,
        });
      }
    },
    [activeClient, commitItems, onConfirmed, onError],
  );

  const handleRetryItem = useCallback(
    async (item: AttachmentItemView) => {
      if (!item.file) {
        return;
      }
      await uploadSingleFile(item.file, item.id);
    },
    [uploadSingleFile],
  );

  const handleDismissItem = useCallback(
    (item: AttachmentItemView) => {
      commitItems((prev) => prev.filter((entry) => entry.id !== item.id));
      setErrorBanner((prev) => (prev?.itemId === item.id ? null : prev));
    },
    [commitItems],
  );

  return (
    <div
      data-testid="attachment-dropzone"
      data-drag-active={isDragActive ? 'true' : 'false'}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onPaste={handlePaste}
      className={`relative rounded-2xl border border-[#303030] bg-[#1C1C1C] p-3 text-[#E8E8E8] transition-colors ${
        isDragActive ? 'border-[#3B82F6] bg-[#202020]' : ''
      } ${className}`}
    >
      {isDragActive ? (
        <div
          data-testid="attachment-drop-overlay"
          className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-[#3B82F6] bg-[#141414]/90 p-4 text-center"
        >
          <Upload aria-hidden="true" className="h-6 w-6 text-[#93C5FD]" />
          <p className="text-sm font-medium text-[#E8E8E8]">
            Solte os arquivos para anexar à sessão
          </p>
          <p className="font-mono text-[11px] text-[#969696]">
            Destino: {hostId} · Máx. {formatAttachmentSize(maxBytes)}
          </p>
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        id={inputId}
        type="file"
        multiple={multiple}
        accept={SAFE_ATTACHMENT_ACCEPT}
        disabled={disabled}
        aria-label="Selecionar arquivos para anexar"
        onChange={handleFileInputChange}
        className="sr-only"
      />

      {children ? <div className="mb-3">{children}</div> : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs font-medium text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Paperclip aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
            <span>Anexar arquivo</span>
          </button>

          <span className="text-[11px] text-[#969696]">
            Arraste e solte, cole (Ctrl+V) ou selecione · Máx.{' '}
            {formatAttachmentSize(maxBytes)}
          </span>
        </div>

        <span className="rounded border border-[#303030] bg-[#141414] px-2 py-0.5 font-mono text-[11px] text-[#969696]">
          host: {hostId}
        </span>
      </div>

      {errorBanner ? (
        <div
          role="alert"
          data-testid="attachment-error-banner"
          className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
        >
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="break-words">{errorBanner.message}</span>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            {errorBanner.retryable && errorBanner.file ? (
              <button
                type="button"
                onClick={() => {
                  if (errorBanner.file) {
                    void uploadSingleFile(errorBanner.file, errorBanner.itemId);
                  }
                }}
                className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#202020] px-2 py-1 text-[11px] font-medium text-[#E8E8E8] hover:bg-[#282828]"
              >
                <RefreshCw aria-hidden="true" className="h-3 w-3" />
                <span>Tentar novamente</span>
              </button>
            ) : null}

            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              aria-label="Dispensar aviso de erro"
              className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] hover:bg-[#282828]"
            >
              <X aria-hidden="true" className="h-3 w-3" />
              <span>Dispensar</span>
            </button>
          </div>
        </div>
      ) : null}

      {showList ? (
        <div className="mt-3">
          <AttachmentList
            items={resolvedItems}
            onConfirmTransfer={handleConfirmTransfer}
            onRetry={handleRetryItem}
            onDismiss={handleDismissItem}
            onRemove={handleDismissItem}
          />
        </div>
      ) : null}
    </div>
  );
}
