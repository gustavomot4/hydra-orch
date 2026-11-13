export type PtySessionStatus = 'running' | 'exited' | 'cancelled' | 'crashed';
export type PtyStreamName = 'pty' | 'stdout' | 'stderr' | 'system';

export interface PtySessionInfo {
  session_id: string;
  workspace_id: string | null;
  host_id: string;
  cwd: string;
  command: string[];
  pid: number | null;
  cols: number;
  rows: number;
  status: PtySessionStatus;
  detached: boolean;
  exit_code: number | null;
  backend_kind: string;
  pty_certified: boolean;
  last_seq: number;
  oldest_seq: number;
  created_at: string;
  finished_at: string | null;
}

export interface PtyChunk {
  seq: number;
  session_id: string;
  stream: PtyStreamName;
  text: string;
  raw_bytes_len: number;
  timestamp: string;
}

export interface PtySessionCreatePayload {
  command: string[];
  cwd: string;
  session_id?: string;
  workspace_id?: string;
  host_id?: string;
  cols?: number;
  rows?: number;
  allowed_env?: Record<string, string>;
}

export interface PtyOutputResponse {
  session: PtySessionInfo;
  chunks: PtyChunk[];
}

export interface PtyInputResponse {
  session_id: string;
  bytes_written: number;
}

export type PtyWsServerMessage =
  | { type: 'chunk'; chunk: PtyChunk }
  | { type: 'state'; session: PtySessionInfo };

export type PtyWsClientMessage =
  | { type: 'input'; data: string }
  | { type: 'resize'; cols: number; rows: number }
  | { type: 'interrupt' }
  | { type: 'close'; keep_running: boolean };

export interface PtyWebSocketLike {
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  send: (data: string) => void;
  close: (code?: number, reason?: string) => void;
}

export type PtyTransportMode = 'ws' | 'sse' | 'poll' | 'connecting' | 'disconnected' | 'closed';

export interface TerminalDimensions {
  cols: number;
  rows: number;
}

export interface TerminalViewportAdapter {
  readonly kind: 'xterm' | 'headless-dom';
  write: (text: string) => void;
  clear: () => void;
  resize: (cols: number, rows: number) => void;
  fit: () => TerminalDimensions | null;
  focus: () => void;
  getSelection: () => string;
  onData: (listener: (data: string) => void) => () => void;
  onResize: (listener: (dims: TerminalDimensions) => void) => () => void;
  dispose: () => void;
}

export interface TerminalAdapterOptions {
  cols: number;
  rows: number;
  onMultilinePaste?: (pastedText: string) => void;
  onInterruptShortcut?: () => void;
}

export type TerminalAdapterFactory = (
  container: HTMLElement,
  options: TerminalAdapterOptions,
) => TerminalViewportAdapter;

export interface AnsiStyleState {
  color?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

export interface AnsiSegment {
  text: string;
  style?: AnsiStyleState;
}

const ANSI_FOREGROUND_COLORS: Record<number, string> = {
  30: '#525252',
  31: '#F87171',
  32: '#4ADE80',
  33: '#FBBF24',
  34: '#60A5FA',
  35: '#C084FC',
  36: '#22D3EE',
  37: '#E8E8E8',
  90: '#737373',
  91: '#FCA5A5',
  92: '#86EFAC',
  93: '#FDE68A',
  94: '#93C5FD',
  95: '#D8B4FE',
  96: '#67E8F9',
  97: '#FFFFFF',
};

const CSI_OR_OSC_RE = new RegExp(
  // eslint-disable-next-line no-control-regex
  '\\x1B\\[[0-9;?]*[A-Za-z]|\\x1B\\][^\\x07\\x1B]*(?:\\x07|\\x1B\\\\)',
  'g',
);

function applySgrCodes(current: AnsiStyleState, paramsText: string): AnsiStyleState {
  const rawParts = paramsText === '' ? ['0'] : paramsText.split(';');
  let next: AnsiStyleState = { ...current };
  for (const part of rawParts) {
    const code = Number.parseInt(part, 10);
    if (!Number.isFinite(code)) {
      continue;
    }
    if (code === 0) {
      next = {};
    } else if (code === 1) {
      next.bold = true;
    } else if (code === 2) {
      next.dim = true;
    } else if (code === 3) {
      next.italic = true;
    } else if (code === 4) {
      next.underline = true;
    } else if (code === 22) {
      next.bold = false;
      next.dim = false;
    } else if (code === 23) {
      next.italic = false;
    } else if (code === 24) {
      next.underline = false;
    } else if (code === 39) {
      next.color = undefined;
    } else if (ANSI_FOREGROUND_COLORS[code]) {
      next.color = ANSI_FOREGROUND_COLORS[code];
    }
  }
  return next;
}

function hasStyle(style: AnsiStyleState): boolean {
  return Boolean(style.color || style.bold || style.dim || style.italic || style.underline);
}

/**
 * Normalize carriage returns and parse ANSI SGR sequences into safe renderable segments.
 * Preserves Unicode text and strips non-SGR control escapes without HTML injection.
 */
export function parseAnsiText(input: string): AnsiSegment[] {
  const normalizedNewlines = input.replace(/\r\n/g, '\n');
  const segments: AnsiSegment[] = [];
  let style: AnsiStyleState = {};
  let lastIndex = 0;

  CSI_OR_OSC_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CSI_OR_OSC_RE.exec(normalizedNewlines)) !== null) {
    if (match.index > lastIndex) {
      const chunk = normalizedNewlines.slice(lastIndex, match.index).replace(/\r/g, '');
      if (chunk.length > 0) {
        segments.push({
          text: chunk,
          style: hasStyle(style) ? { ...style } : undefined,
        });
      }
    }
    const seq = match[0];
    if (seq.startsWith('\x1B[') && seq.endsWith('m')) {
      const params = seq.slice(2, -1);
      style = applySgrCodes(style, params);
    }
    lastIndex = match.index + seq.length;
  }

  if (lastIndex < normalizedNewlines.length) {
    const tail = normalizedNewlines.slice(lastIndex).replace(/\r/g, '');
    if (tail.length > 0) {
      segments.push({
        text: tail,
        style: hasStyle(style) ? { ...style } : undefined,
      });
    }
  }

  return segments;
}

export function countPasteLines(text: string): number {
  if (text.length === 0) {
    return 0;
  }
  return text.split(/\r\n|\r|\n/).length;
}

export function isMultilinePaste(text: string): boolean {
  return countPasteLines(text) > 1;
}

export const PTY_STATUS_LABELS: Record<PtySessionStatus, string> = {
  running: 'Em execução',
  exited: 'Encerrado',
  cancelled: 'Cancelado',
  crashed: 'Falha crítica',
};
