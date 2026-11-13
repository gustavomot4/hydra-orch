export type AttachmentTransferStatus =
  | 'local_ready'
  | 'pending_remote_confirm'
  | 'transferred'
  | 'failed';

export type AttachmentUploadPhase =
  | 'preparando'
  | 'enviando'
  | 'local_ready'
  | 'pending_remote_confirm'
  | 'transferred'
  | 'erro';

export interface AttachmentRef {
  attachment_id: string;
  workspace_id: string;
  session_id: string;
  host_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  storage_rel_path: string;
  transfer_status: AttachmentTransferStatus;
  remote_confirmed: boolean;
  created_at: string;
}

export interface AttachmentItemView {
  id: string;
  attachment_id: string | null;
  workspace_id: string;
  session_id: string;
  host_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string | null;
  storage_rel_path: string | null;
  status: AttachmentUploadPhase;
  remote_confirmed: boolean;
  created_at: string | null;
  error_message: string | null;
  error_code: string | null;
  confirming?: boolean;
  file?: File;
}

export interface AttachmentCreateRequest {
  workspace_id: string;
  filename: string;
  content_base64: string;
  mime_type?: string | null;
  host_id?: string;
  attachment_id?: string;
}

export interface AttachmentErrorNotice {
  id: string;
  itemId?: string;
  filename: string;
  code: string;
  message: string;
  retryable: boolean;
  file?: File;
}

export type AttachmentValidationResult =
  | {
      ok: true;
      filename: string;
      mimeType: string;
    }
  | {
      ok: false;
      code: string;
      message: string;
    };

export const DEFAULT_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;

export const FORBIDDEN_ATTACHMENT_EXTENSIONS: ReadonlySet<string> = new Set([
  '.html',
  '.htm',
  '.xhtml',
  '.svg',
  '.svgz',
  '.js',
  '.mjs',
  '.cjs',
  '.exe',
  '.dll',
  '.so',
  '.dylib',
  '.bat',
  '.cmd',
  '.sh',
  '.bash',
  '.zsh',
  '.ps1',
  '.psm1',
  '.psd1',
  '.vbs',
  '.vbe',
  '.wsf',
  '.wsh',
  '.msi',
  '.scr',
  '.com',
  '.pif',
  '.hta',
  '.jar',
  '.app',
  '.dmg',
  '.pkg',
  '.deb',
  '.rpm',
  '.php',
  '.asp',
  '.aspx',
  '.jsp',
  '.wasm',
]);

export const FORBIDDEN_ATTACHMENT_MIME_TYPES: ReadonlySet<string> = new Set([
  'text/html',
  'application/xhtml+xml',
  'image/svg+xml',
  'application/javascript',
  'text/javascript',
  'application/ecmascript',
  'application/x-javascript',
  'application/x-executable',
  'application/x-msdownload',
  'application/x-msdos-program',
  'application/x-dosexec',
  'application/x-sh',
  'application/x-shellscript',
  'text/x-shellscript',
  'application/x-powershell',
  'application/x-bat',
  'application/x-csh',
  'application/wasm',
  'application/x-httpd-php',
  'text/xml',
  'application/xml',
]);

export const SAFE_ATTACHMENT_EXT_TO_MIME: Readonly<Record<string, string>> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.pdf': 'application/pdf',
  '.txt': 'text/plain',
  '.log': 'text/plain',
  '.rst': 'text/plain',
  '.ini': 'text/plain',
  '.cfg': 'text/plain',
  '.sql': 'text/plain',
  '.md': 'text/markdown',
  '.markdown': 'text/markdown',
  '.csv': 'text/csv',
  '.tsv': 'text/tab-separated-values',
  '.diff': 'text/x-diff',
  '.patch': 'text/x-patch',
  '.json': 'application/json',
  '.py': 'text/x-python',
  '.ts': 'application/typescript',
  '.tsx': 'application/typescript',
  '.yaml': 'application/yaml',
  '.yml': 'application/yaml',
  '.toml': 'application/toml',
  '.rs': 'text/x-rust',
  '.go': 'text/x-go',
  '.java': 'text/x-java-source',
  '.c': 'text/x-c',
  '.h': 'text/x-c',
  '.cpp': 'text/x-c++',
  '.hpp': 'text/x-c++',
};

export const SAFE_ATTACHMENT_MIME_TYPES: ReadonlySet<string> = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'application/pdf',
  'text/plain',
  'text/markdown',
  'text/x-markdown',
  'text/csv',
  'text/tab-separated-values',
  'text/x-diff',
  'text/x-patch',
  'application/json',
  'text/x-python',
  'application/x-python-code',
  'application/typescript',
  'text/typescript',
  'text/x-typescript',
  'text/yaml',
  'application/yaml',
  'application/x-yaml',
  'application/toml',
  'text/toml',
  'text/x-rust',
  'text/x-go',
  'text/x-java-source',
  'text/x-c',
  'text/x-c++',
]);

export const SAFE_ATTACHMENT_ACCEPT = Object.keys(SAFE_ATTACHMENT_EXT_TO_MIME).join(',');

export const ATTACHMENT_STATUS_LABELS: Record<AttachmentUploadPhase, string> = {
  preparando: 'Preparando',
  enviando: 'Enviando',
  local_ready: 'Pronto local',
  pending_remote_confirm: 'Confirmar envio remoto',
  transferred: 'Transferido',
  erro: 'Erro',
};

const WINDOWS_RESERVED_NAMES = new Set([
  'CON',
  'PRN',
  'AUX',
  'NUL',
  'COM1',
  'COM2',
  'COM3',
  'COM4',
  'COM5',
  'COM6',
  'COM7',
  'COM8',
  'COM9',
  'LPT1',
  'LPT2',
  'LPT3',
  'LPT4',
  'LPT5',
  'LPT6',
  'LPT7',
  'LPT8',
  'LPT9',
]);

export function getFileExtension(filename: string): string {
  const dotIdx = filename.lastIndexOf('.');
  if (dotIdx <= 0 || dotIdx === filename.length - 1) {
    return '';
  }
  return filename.slice(dotIdx).toLowerCase();
}

export function normalizeMimeType(mimeType?: string | null): string {
  if (!mimeType) {
    return '';
  }
  return mimeType.split(';', 1)[0].trim().toLowerCase();
}

export function formatAttachmentSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return '0 B';
  }
  if (bytes < 1024) {
    return `${Math.round(bytes)} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatSha256Prefix(sha256: string | null | undefined, length = 12): string {
  if (!sha256) {
    return '—';
  }
  return sha256.slice(0, length);
}

export function validateAttachmentFile(
  file: { name: string; size: number; type?: string },
  maxBytes: number = DEFAULT_ATTACHMENT_MAX_BYTES,
): AttachmentValidationResult {
  const rawName = file.name ?? '';
  const cleaned = rawName.trim();
  const hasControlChar = Array.from(cleaned).some((ch) => ch.charCodeAt(0) < 32);

  if (
    !cleaned ||
    cleaned !== rawName ||
    cleaned === '.' ||
    cleaned === '..' ||
    cleaned.includes('..') ||
    cleaned.includes('/') ||
    cleaned.includes('\\') ||
    cleaned.includes(':') ||
    cleaned.includes('\0') ||
    hasControlChar
  ) {
    return {
      ok: false,
      code: 'path_traversal_blocked',
      message: `Nome de arquivo inválido ou inseguro: "${rawName || '(vazio)'}".`,
    };
  }

  const ext = getFileExtension(cleaned);
  const stem = ext ? cleaned.slice(0, -ext.length) : cleaned;
  if (WINDOWS_RESERVED_NAMES.has(stem.toUpperCase())) {
    return {
      ok: false,
      code: 'path_traversal_blocked',
      message: `Nome de arquivo reservado bloqueado: "${cleaned}".`,
    };
  }

  if (file.size > maxBytes) {
    return {
      ok: false,
      code: 'attachment_too_large',
      message: `O arquivo "${cleaned}" (${formatAttachmentSize(file.size)}) excede o limite de ${formatAttachmentSize(maxBytes)}.`,
    };
  }

  const normalizedMime = normalizeMimeType(file.type);
  if (FORBIDDEN_ATTACHMENT_EXTENSIONS.has(ext) || FORBIDDEN_ATTACHMENT_MIME_TYPES.has(normalizedMime)) {
    return {
      ok: false,
      code: 'unsupported_attachment_type',
      message: `Tipo de arquivo bloqueado por segurança (${ext || normalizedMime}): "${cleaned}". HTML, SVG, scripts e executáveis não são permitidos.`,
    };
  }

  if (ext && !(ext in SAFE_ATTACHMENT_EXT_TO_MIME)) {
    return {
      ok: false,
      code: 'unsupported_attachment_type',
      message: `Extensão "${ext}" em "${cleaned}" não está na lista segura de anexos permitidos.`,
    };
  }

  const inferredMime = SAFE_ATTACHMENT_EXT_TO_MIME[ext];
  const resolvedMime =
    normalizedMime && normalizedMime !== 'application/octet-stream'
      ? normalizedMime
      : inferredMime ?? 'text/plain';

  if (!SAFE_ATTACHMENT_MIME_TYPES.has(resolvedMime)) {
    return {
      ok: false,
      code: 'unsupported_attachment_type',
      message: `Tipo MIME "${resolvedMime}" em "${cleaned}" não é permitido para anexos.`,
    };
  }

  return {
    ok: true,
    filename: cleaned,
    mimeType: resolvedMime,
  };
}

export function attachmentRefToView(ref: AttachmentRef): AttachmentItemView {
  const status: AttachmentUploadPhase =
    ref.transfer_status === 'failed' ? 'erro' : ref.transfer_status;
  return {
    id: ref.attachment_id,
    attachment_id: ref.attachment_id,
    workspace_id: ref.workspace_id,
    session_id: ref.session_id,
    host_id: ref.host_id,
    filename: ref.filename,
    mime_type: ref.mime_type,
    size_bytes: ref.size_bytes,
    sha256: ref.sha256,
    storage_rel_path: ref.storage_rel_path,
    status,
    remote_confirmed: ref.remote_confirmed,
    created_at: ref.created_at,
    error_message: status === 'erro' ? 'Falha na transferência do anexo.' : null,
    error_code: status === 'erro' ? 'transfer_failed' : null,
  };
}
