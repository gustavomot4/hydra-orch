import {
  ChangeEvent,
  ClipboardEvent,
  CompositionEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import {
  AlertTriangle,
  ClipboardPaste,
  Copy,
  Maximize2,
  OctagonX,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Terminal as TerminalIcon,
  X,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  buildPtyWebSocketUrl,
  closePtySession,
  interruptPtySession,
  readPtyOutput,
  resizePtySession,
  streamPtySse,
  writePtyInput,
} from './ptyApi';
import { TerminalCloseDialog } from './TerminalCloseDialog';
import {
  countPasteLines,
  isMultilinePaste,
  parseAnsiText,
  PTY_STATUS_LABELS,
  PtyChunk,
  PtySessionInfo,
  PtyTransportMode,
  PtyWebSocketLike,
  PtyWsServerMessage,
  TerminalAdapterFactory,
  TerminalAdapterOptions,
  TerminalDimensions,
  TerminalViewportAdapter,
} from './terminalTypes';

const MAX_HEADLESS_CHARS = 250_000;

function canUseCanvasRenderer(): boolean {
  if (typeof document === 'undefined') {
    return false;
  }
  try {
    const canvas = document.createElement('canvas');
    if (typeof canvas.getContext !== 'function') {
      return false;
    }
    return canvas.getContext('2d') !== null;
  } catch {
    return false;
  }
}

function createXtermAdapter(
  container: HTMLElement,
  options: TerminalAdapterOptions,
): TerminalViewportAdapter {
  const term = new Terminal({
    cols: options.cols,
    rows: options.rows,
    cursorBlink: true,
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: 13,
    lineHeight: 1.4,
    scrollback: 2000,
    theme: {
      background: '#141414',
      foreground: '#E8E8E8',
      cursor: '#E8E8E8',
      cursorAccent: '#141414',
      selectionBackground: 'rgba(59, 130, 246, 0.3)',
      black: '#181818',
      red: '#F87171',
      green: '#4ADE80',
      yellow: '#FBBF24',
      blue: '#60A5FA',
      magenta: '#C084FC',
      cyan: '#22D3EE',
      white: '#E8E8E8',
    },
  });
  const fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(container);
  try {
    fitAddon.fit();
  } catch {
    // Container pode ainda não estar dimensionado
  }

  const pasteCaptureHandler = (event: globalThis.ClipboardEvent) => {
    const pasted = event.clipboardData?.getData('text/plain') ?? event.clipboardData?.getData('text') ?? '';
    if (pasted && isMultilinePaste(pasted) && options.onMultilinePaste) {
      event.preventDefault();
      event.stopPropagation();
      options.onMultilinePaste(pasted);
    }
  };

  const textarea = term.textarea;
  textarea?.addEventListener('paste', pasteCaptureHandler, true);

  let resizeObserver: ResizeObserver | null = null;
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      try {
        fitAddon.fit();
      } catch {
        // Ignora resize enquanto painel estiver oculto
      }
    });
    resizeObserver.observe(container);
  }

  return {
    kind: 'xterm',
    write: (text) => term.write(text),
    clear: () => term.clear(),
    resize: (cols, rows) => term.resize(cols, rows),
    fit: () => {
      try {
        fitAddon.fit();
        return { cols: term.cols, rows: term.rows };
      } catch {
        return null;
      }
    },
    focus: () => term.focus(),
    getSelection: () => term.getSelection(),
    onData: (listener) => {
      const disp = term.onData(listener);
      return () => disp.dispose();
    },
    onResize: (listener) => {
      const disp = term.onResize(listener);
      return () => disp.dispose();
    },
    dispose: () => {
      resizeObserver?.disconnect();
      textarea?.removeEventListener('paste', pasteCaptureHandler, true);
      term.dispose();
    },
  };
}

export interface TerminalPaneProps {
  session: PtySessionInfo;
  title?: string;
  client?: ControlPlaneClient;
  token?: string | null;
  transportPreference?: 'auto' | 'ws' | 'sse' | 'poll';
  pollIntervalMs?: number;
  webSocketFactory?: (url: string, options: { token: string | null }) => PtyWebSocketLike;
  terminalAdapterFactory?: TerminalAdapterFactory;
  onSessionChange?: (session: PtySessionInfo) => void;
  onClosed?: (session: PtySessionInfo, keepRunning: boolean) => void;
  className?: string;
  compact?: boolean;
}

export function TerminalPane({
  session: initialSession,
  title,
  client: clientOverride,
  token: tokenOverride,
  transportPreference = 'auto',
  pollIntervalMs = 500,
  webSocketFactory,
  terminalAdapterFactory,
  onSessionChange,
  onClosed,
  className = '',
  compact = false,
}: TerminalPaneProps) {
  const defaultClient = useControlPlaneClient();
  const storeToken = useAuthStore((s) => s.token);
  const client = clientOverride ?? defaultClient;
  const token = tokenOverride !== undefined ? tokenOverride : storeToken;

  const [session, setSession] = useState<PtySessionInfo>(initialSession);
  const [transportMode, setTransportMode] = useState<PtyTransportMode>('connecting');
  const [headlessBuffer, setHeadlessBuffer] = useState<string>('');
  const [rendererKind, setRendererKind] = useState<'xterm' | 'headless-dom'>('headless-dom');
  const [lastSeqDisplay, setLastSeqDisplay] = useState<number>(0);
  const [cursorExpiredNotice, setCursorExpiredNotice] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  const [pendingPasteText, setPendingPasteText] = useState<string | null>(null);
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [isClosingSession, setIsClosingSession] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [reconnectNonce, setReconnectNonce] = useState(0);

  const viewportRef = useRef<HTMLDivElement | null>(null);
  const headlessInputRef = useRef<HTMLTextAreaElement | null>(null);
  const adapterRef = useRef<TerminalViewportAdapter | null>(null);
  const wsRef = useRef<PtyWebSocketLike | null>(null);
  const lastSeqRef = useRef<number>(0);
  const sessionRef = useRef<PtySessionInfo>(initialSession);
  const isComposingRef = useRef<boolean>(false);

  const updateSession = useCallback(
    (next: PtySessionInfo) => {
      sessionRef.current = next;
      setSession(next);
      onSessionChange?.(next);
    },
    [onSessionChange],
  );

  // Sync if caller switches to a different session_id
  useEffect(() => {
    if (initialSession.session_id !== sessionRef.current.session_id) {
      lastSeqRef.current = 0;
      setLastSeqDisplay(0);
      setHeadlessBuffer('');
      setCursorExpiredNotice(null);
      setErrorBanner(null);
      adapterRef.current?.clear();
      sessionRef.current = initialSession;
      setSession(initialSession);
    } else {
      sessionRef.current = initialSession;
      setSession(initialSession);
    }
  }, [initialSession]);

  const appendOutputChunk = useCallback((chunk: PtyChunk) => {
    if (chunk.seq <= lastSeqRef.current) {
      return;
    }
    lastSeqRef.current = chunk.seq;
    setLastSeqDisplay(chunk.seq);

    if (adapterRef.current) {
      adapterRef.current.write(chunk.text);
    } else {
      setHeadlessBuffer((prev) => {
        const combined = prev + chunk.text;
        return combined.length > MAX_HEADLESS_CHARS
          ? combined.slice(combined.length - MAX_HEADLESS_CHARS)
          : combined;
      });
    }
  }, []);

  const sendInputData = useCallback(
    async (data: string) => {
      if (!data || sessionRef.current.status !== 'running') {
        return;
      }
      const ws = wsRef.current;
      if (ws && ws.readyState === 1) {
        try {
          ws.send(JSON.stringify({ type: 'input', data }));
          return;
        } catch {
          // Fallback para HTTP POST /input se o socket falhar ao enviar
        }
      }
      try {
        await writePtyInput(client, sessionRef.current.session_id, data);
      } catch (err) {
        const msg =
          err instanceof ControlPlaneApiError
            ? err.payload.message
            : 'Falha ao enviar entrada para o terminal.';
        setErrorBanner(msg);
      }
    },
    [client],
  );

  const handleResizeDimensions = useCallback(
    async (dims: TerminalDimensions) => {
      if (sessionRef.current.status !== 'running') {
        return;
      }
      const cols = Math.max(1, Math.min(1000, Math.round(dims.cols)));
      const rows = Math.max(1, Math.min(1000, Math.round(dims.rows)));
      try {
        const updated = await resizePtySession(client, sessionRef.current.session_id, cols, rows);
        updateSession(updated);
      } catch (err) {
        if (err instanceof ControlPlaneApiError && err.status !== 409) {
          setErrorBanner(err.payload.message);
        }
      }
    },
    [client, updateSession],
  );

  const handleInterrupt = useCallback(async () => {
    if (sessionRef.current.status !== 'running') {
      return;
    }
    try {
      const updated = await interruptPtySession(client, sessionRef.current.session_id);
      updateSession(updated);
    } catch (err) {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : 'Não foi possível enviar sinal de interrupção.';
      setErrorBanner(msg);
    }
  }, [client, updateSession]);

  // Mount xterm.js + FitAddon when canvas is available or custom factory is injected;
  // gracefully fall back to headless ANSI/Unicode DOM mode in JSDOM.
  useEffect(() => {
    const container = viewportRef.current;
    if (!container) {
      return;
    }

    let created: TerminalViewportAdapter | null = null;
    if (terminalAdapterFactory) {
      created = terminalAdapterFactory(container, {
        cols: sessionRef.current.cols,
        rows: sessionRef.current.rows,
        onMultilinePaste: (text) => setPendingPasteText(text),
        onInterruptShortcut: () => void handleInterrupt(),
      });
    } else if (canUseCanvasRenderer()) {
      try {
        created = createXtermAdapter(container, {
          cols: sessionRef.current.cols,
          rows: sessionRef.current.rows,
          onMultilinePaste: (text) => setPendingPasteText(text),
          onInterruptShortcut: () => void handleInterrupt(),
        });
      } catch {
        created = null;
      }
    }

    if (!created) {
      adapterRef.current = null;
      setRendererKind('headless-dom');
      return;
    }

    adapterRef.current = created;
    setRendererKind(created.kind);
    const unsubData = created.onData((data) => {
      void sendInputData(data);
    });
    const unsubResize = created.onResize((dims) => {
      void handleResizeDimensions(dims);
    });

    return () => {
      unsubData();
      unsubResize();
      created?.dispose();
      adapterRef.current = null;
    };
  }, [
    session.session_id,
    terminalAdapterFactory,
    handleInterrupt,
    sendInputData,
    handleResizeDimensions,
  ]);

  // Bidirectional WS stream with automatic HTTP SSE & /output fallback + after_seq replay
  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();
    let activeWs: PtyWebSocketLike | null = null;
    let pollTimer: number | null = null;

    const cleanupWs = () => {
      if (activeWs) {
        activeWs.onopen = null;
        activeWs.onmessage = null;
        activeWs.onerror = null;
        activeWs.onclose = null;
        try {
          activeWs.close();
        } catch {
          // Ignora falha ao fechar socket
        }
        activeWs = null;
      }
      wsRef.current = null;
    };

    const runHttpBacklogRead = async (resetOnExpired = true): Promise<PtySessionInfo | null> => {
      try {
        const res = await readPtyOutput(client, session.session_id, lastSeqRef.current);
        if (cancelled) {
          return null;
        }
        for (const chunk of res.chunks) {
          appendOutputChunk(chunk);
        }
        updateSession(res.session);
        return res.session;
      } catch (err) {
        if (cancelled) {
          return null;
        }
        if (
          resetOnExpired &&
          err instanceof ControlPlaneApiError &&
          (err.status === 410 || err.payload.code === 'cursor_expired')
        ) {
          setCursorExpiredNotice(
            `Cursor after_seq=${lastSeqRef.current} expirado (HTTP 410); recarregando backlog retido.`,
          );
          lastSeqRef.current = 0;
          setLastSeqDisplay(0);
          return runHttpBacklogRead(false);
        }
        if (err instanceof ControlPlaneApiError) {
          setErrorBanner(err.payload.message);
        } else {
          setErrorBanner('Erro ao consultar saída do terminal PTY.');
        }
        return null;
      }
    };

    const runPollingLoop = async () => {
      if (cancelled) {
        return;
      }
      setTransportMode('poll');
      const latest = await runHttpBacklogRead();
      if (cancelled) {
        return;
      }
      if (!latest || latest.status !== 'running') {
        setTransportMode('closed');
        return;
      }
      pollTimer = window.setTimeout(() => {
        void runPollingLoop();
      }, pollIntervalMs);
    };

    const runSseFallback = async () => {
      if (cancelled) {
        return;
      }
      setTransportMode('sse');
      try {
        await streamPtySse({
          sessionId: session.session_id,
          afterSeq: lastSeqRef.current,
          token,
          signal: abortController.signal,
          onChunk: appendOutputChunk,
          onState: (nextSession) => {
            updateSession(nextSession);
            if (nextSession.status !== 'running') {
              setTransportMode('closed');
            }
          },
        });
        if (!cancelled && sessionRef.current.status === 'running') {
          await runPollingLoop();
        } else if (!cancelled) {
          setTransportMode('closed');
        }
      } catch (err) {
        if (cancelled || abortController.signal.aborted) {
          return;
        }
        if (
          err instanceof ControlPlaneApiError &&
          (err.status === 410 || err.payload.code === 'cursor_expired')
        ) {
          setCursorExpiredNotice(
            `Cursor after_seq=${lastSeqRef.current} expirado (HTTP 410); recarregando backlog retido.`,
          );
          lastSeqRef.current = 0;
          setLastSeqDisplay(0);
          await runSseFallback();
          return;
        }
        await runPollingLoop();
      }
    };

    const start = async () => {
      setErrorBanner(null);
      setTransportMode('connecting');

      if (sessionRef.current.status !== 'running') {
        await runHttpBacklogRead();
        if (!cancelled) {
          setTransportMode('closed');
        }
        return;
      }

      if (transportPreference === 'poll') {
        await runPollingLoop();
        return;
      }

      if (transportPreference === 'sse') {
        await runSseFallback();
        return;
      }

      const canAttemptWs =
        Boolean(webSocketFactory) ||
        (typeof window !== 'undefined' && typeof window.WebSocket === 'function');

      if (!canAttemptWs) {
        await runSseFallback();
        return;
      }

      const wsUrl = buildPtyWebSocketUrl(session.session_id, lastSeqRef.current);
      let opened = false;
      let fellBack = false;

      const triggerFallback = () => {
        if (cancelled || fellBack || sessionRef.current.status !== 'running') {
          return;
        }
        fellBack = true;
        cleanupWs();
        void runSseFallback();
      };

      try {
        activeWs = webSocketFactory
          ? webSocketFactory(wsUrl, { token })
          : (new window.WebSocket(wsUrl) as unknown as PtyWebSocketLike);
        wsRef.current = activeWs;
      } catch {
        await runSseFallback();
        return;
      }

      activeWs.onopen = () => {
        if (cancelled) {
          return;
        }
        opened = true;
        setTransportMode('ws');
      };

      activeWs.onmessage = (event) => {
        if (cancelled) {
          return;
        }
        try {
          const msg = JSON.parse(event.data) as PtyWsServerMessage;
          if (msg.type === 'chunk') {
            appendOutputChunk(msg.chunk);
          } else if (msg.type === 'state') {
            updateSession(msg.session);
            if (msg.session.status !== 'running') {
              setTransportMode('closed');
              cleanupWs();
            }
          }
        } catch {
          // Ignora frame inválido
        }
      };

      activeWs.onerror = () => {
        if (!opened) {
          triggerFallback();
        }
      };

      activeWs.onclose = () => {
        if (cancelled) {
          return;
        }
        if (sessionRef.current.status !== 'running') {
          setTransportMode('closed');
          cleanupWs();
          return;
        }
        triggerFallback();
      };
    };

    void start();

    return () => {
      cancelled = true;
      abortController.abort();
      if (pollTimer !== null) {
        window.clearTimeout(pollTimer);
      }
      cleanupWs();
    };
  }, [
    session.session_id,
    client,
    token,
    transportPreference,
    pollIntervalMs,
    webSocketFactory,
    reconnectNonce,
    appendOutputChunk,
    updateSession,
  ]);

  const renderedSegments = useMemo(() => parseAnsiText(headlessBuffer), [headlessBuffer]);

  const handleHeadlessPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted =
      event.clipboardData?.getData('text/plain') ?? event.clipboardData?.getData('text') ?? '';
    if (!pasted) {
      return;
    }
    event.preventDefault();
    if (isMultilinePaste(pasted)) {
      setPendingPasteText(pasted);
      return;
    }
    void sendInputData(pasted);
  };

  const handleHeadlessKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (session.status !== 'running') {
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {
      const selected =
        typeof window !== 'undefined' ? window.getSelection()?.toString() ?? '' : '';
      if (selected.length === 0) {
        event.preventDefault();
        void handleInterrupt();
      }
      return;
    }
    if (event.key === 'Enter' && !isComposingRef.current) {
      event.preventDefault();
      void sendInputData('\r');
    } else if (event.key === 'Backspace') {
      event.preventDefault();
      void sendInputData('\x7f');
    } else if (event.key === 'Tab') {
      event.preventDefault();
      void sendInputData('\t');
    } else if (event.key === 'Escape') {
      event.preventDefault();
      void sendInputData('\x1b');
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      void sendInputData('\x1b[A');
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      void sendInputData('\x1b[B');
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      void sendInputData('\x1b[C');
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      void sendInputData('\x1b[D');
    }
  };

  const handleHeadlessChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    if (isComposingRef.current) {
      return;
    }
    const value = event.target.value;
    if (value) {
      event.target.value = '';
      void sendInputData(value);
    }
  };

  const handleHeadlessCompositionStart = () => {
    isComposingRef.current = true;
  };

  const handleHeadlessCompositionEnd = (event: CompositionEvent<HTMLTextAreaElement>) => {
    isComposingRef.current = false;
    const text = event.currentTarget.value;
    event.currentTarget.value = '';
    if (text) {
      void sendInputData(text);
    }
  };

  const handleCopySelection = async () => {
    const adapterSelection = adapterRef.current?.getSelection() ?? '';
    const domSelection =
      typeof window !== 'undefined' ? window.getSelection()?.toString() ?? '' : '';
    const text = adapterSelection || domSelection || headlessBuffer;
    if (!text || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopyFeedback('Copiado');
      window.setTimeout(() => setCopyFeedback(null), 1500);
    } catch {
      setCopyFeedback(null);
    }
  };

  const handleTriggerFitResize = () => {
    if (adapterRef.current) {
      const dims = adapterRef.current.fit();
      if (dims) {
        void handleResizeDimensions(dims);
        return;
      }
    }
    const el = viewportRef.current;
    if (el && el.clientWidth > 0 && el.clientHeight > 0) {
      const nextCols = Math.max(20, Math.min(300, Math.floor(el.clientWidth / 8)));
      const nextRows = Math.max(8, Math.min(120, Math.floor(el.clientHeight / 18)));
      void handleResizeDimensions({ cols: nextCols, rows: nextRows });
      return;
    }
    void handleResizeDimensions({ cols: session.cols, rows: session.rows });
  };

  const handleRequestClose = () => {
    setCloseError(null);
    if (session.status === 'running') {
      setCloseDialogOpen(true);
      return;
    }
    onClosed?.(session, false);
  };

  const handleConfirmClose = async (keepRunning: boolean) => {
    setIsClosingSession(true);
    setCloseError(null);
    try {
      const updated = await closePtySession(client, session.session_id, keepRunning);
      updateSession(updated);
      setCloseDialogOpen(false);
      onClosed?.(updated, keepRunning);
    } catch (err) {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : 'Erro ao fechar sessão PTY.';
      setCloseError(msg);
    } finally {
      setIsClosingSession(false);
    }
  };

  const resolvedTitle = title ?? (session.command.length > 0 ? session.command.join(' ') : 'Terminal PTY');
  const statusLabel = PTY_STATUS_LABELS[session.status] ?? session.status;
  const transportLabel =
    transportMode === 'ws'
      ? 'WS'
      : transportMode === 'sse'
        ? 'SSE'
        : transportMode === 'poll'
          ? 'HTTP'
          : transportMode === 'connecting'
            ? 'Conectando...'
            : 'Desconectado';

  return (
    <section
      aria-label={`Terminal PTY ${resolvedTitle}`}
      data-testid={`terminal-pane-${session.session_id}`}
      data-session-id={session.session_id}
      data-pty-certified={String(session.pty_certified)}
      data-renderer={rendererKind}
      className={`flex h-full min-h-[340px] flex-col overflow-hidden rounded-xl border border-[#303030] bg-[#141414] text-[#E8E8E8] ${className}`}
    >
      {/* Header without macOS dots; always shows host_id, cwd, session_id, status, exit_code & certification */}
      <header className="border-b border-[#303030] bg-[#1C1C1C] px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[#303030] bg-[#202020]">
              <TerminalIcon aria-hidden="true" className="h-3.5 w-3.5 text-[#E8E8E8]" />
            </span>
            <h2 className="truncate text-xs font-semibold text-[#E8E8E8]">{resolvedTitle}</h2>

            <StatusBadge status={session.status} labelOverride={statusLabel} compact />

            {session.exit_code !== null ? (
              <span
                data-testid="pty-exit-code"
                className="inline-flex items-center rounded-md border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
              >
                Código de saída: {session.exit_code}
              </span>
            ) : null}

            <span
              data-testid="pty-capability-badge"
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                session.pty_certified
                  ? 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]'
                  : 'border-[#F59E0B]/40 bg-[#F59E0B]/10 text-[#FCD34D]'
              }`}
            >
              {session.pty_certified ? (
                <>
                  <ShieldCheck aria-hidden="true" className="h-3 w-3" />
                  <span>PTY certificado ({session.backend_kind})</span>
                </>
              ) : (
                <>
                  <ShieldAlert aria-hidden="true" className="h-3 w-3" />
                  <span>Pipe bridge (não ConPTY certificado)</span>
                </>
              )}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1">
            <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]">
              {transportLabel} · {session.cols}×{session.rows} · seq {lastSeqDisplay}
            </span>

            <button
              type="button"
              onClick={handleTriggerFitResize}
              disabled={session.status !== 'running'}
              title="Ajustar dimensões do terminal"
              aria-label="Ajustar dimensões do terminal"
              className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Maximize2 aria-hidden="true" className="h-3 w-3" />
              {!compact ? <span>Ajustar</span> : null}
            </button>

            <button
              type="button"
              onClick={() => void handleCopySelection()}
              title="Copiar saída selecionada"
              aria-label="Copiar saída selecionada"
              className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] transition-colors hover:bg-[#282828]"
            >
              <Copy aria-hidden="true" className="h-3 w-3" />
              {!compact ? <span>{copyFeedback ?? 'Copiar'}</span> : null}
            </button>

            <button
              type="button"
              onClick={() => setReconnectNonce((n) => n + 1)}
              title="Reconectar stream a partir do cursor atual"
              aria-label="Reconectar stream PTY"
              className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] transition-colors hover:bg-[#282828]"
            >
              <RefreshCw aria-hidden="true" className="h-3 w-3" />
              {!compact ? <span>Reconectar</span> : null}
            </button>

            <button
              type="button"
              onClick={() => void handleInterrupt()}
              disabled={session.status !== 'running'}
              title="Enviar interrupção (Ctrl+C / SIGINT)"
              aria-label="Interromper processo"
              className="inline-flex items-center gap-1 rounded-md border border-[#F59E0B]/40 bg-[#F59E0B]/10 px-2 py-1 text-[11px] font-medium text-[#FCD34D] transition-colors hover:bg-[#F59E0B]/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <OctagonX aria-hidden="true" className="h-3 w-3" />
              <span>Interromper</span>
            </button>

            <button
              type="button"
              onClick={handleRequestClose}
              title="Fechar terminal"
              aria-label="Fechar terminal"
              className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px] text-[#E8E8E8] transition-colors hover:bg-[#EF4444]/15 hover:text-[#FCA5A5]"
            >
              <X aria-hidden="true" className="h-3 w-3" />
              <span>Fechar</span>
            </button>
          </div>
        </div>

        {/* Always-visible identity metadata row */}
        <dl
          data-testid="pty-header-metadata"
          className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[#969696]"
        >
          <div className="inline-flex items-center gap-1">
            <Server aria-hidden="true" className="h-3 w-3 text-[#969696]" />
            <dt className="sr-only">Host</dt>
            <dd data-testid="pty-meta-host" className="font-mono text-[#E8E8E8]">
              {session.host_id}
            </dd>
          </div>
          <div className="inline-flex min-w-0 items-center gap-1">
            <dt>cwd:</dt>
            <dd
              data-testid="pty-meta-cwd"
              title={session.cwd}
              className="max-w-[320px] truncate font-mono text-[#E8E8E8]"
            >
              {session.cwd}
            </dd>
          </div>
          <div className="inline-flex items-center gap-1">
            <dt>sessão:</dt>
            <dd data-testid="pty-meta-session" className="font-mono text-[#E8E8E8]">
              {session.session_id}
            </dd>
          </div>
          {session.detached ? (
            <span className="rounded bg-[#202020] px-1.5 py-0.5 text-[10px] text-[#969696]">
              Segundo plano
            </span>
          ) : null}
        </dl>
      </header>

      {cursorExpiredNotice ? (
        <div
          role="status"
          className="flex items-center justify-between gap-2 border-b border-[#F59E0B]/30 bg-[#F59E0B]/10 px-3 py-1.5 text-xs text-[#FCD34D]"
        >
          <span>{cursorExpiredNotice}</span>
          <button
            type="button"
            onClick={() => setCursorExpiredNotice(null)}
            className="text-[11px] underline"
          >
            Dispensar
          </button>
        </div>
      ) : null}

      {errorBanner ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-2 border-b border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-1.5 text-xs text-[#FCA5A5]"
        >
          <span>{errorBanner}</span>
          <button
            type="button"
            onClick={() => setErrorBanner(null)}
            className="text-[11px] underline"
          >
            Fechar aviso
          </button>
        </div>
      ) : null}

      {/* Viewport */}
      <div
        ref={viewportRef}
        onClick={() => {
          if (adapterRef.current) {
            adapterRef.current.focus();
          } else {
            headlessInputRef.current?.focus();
          }
        }}
        className="relative flex min-h-[240px] flex-1 flex-col overflow-hidden bg-[#141414]"
      >
        {rendererKind === 'headless-dom' ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div
              role="log"
              aria-live="polite"
              aria-label={`Saída do terminal ${resolvedTitle}`}
              data-testid="terminal-output"
              className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap break-words p-3 font-mono text-xs leading-relaxed text-[#E8E8E8]"
            >
              {renderedSegments.length === 0 ? (
                <span className="text-[#969696]">Aguardando saída do processo PTY...</span>
              ) : (
                renderedSegments.map((seg, index) => (
                  <span
                    key={index}
                    style={
                      seg.style
                        ? {
                            color: seg.style.color,
                            fontWeight: seg.style.bold ? 700 : undefined,
                            opacity: seg.style.dim ? 0.7 : undefined,
                            fontStyle: seg.style.italic ? 'italic' : undefined,
                            textDecoration: seg.style.underline ? 'underline' : undefined,
                          }
                        : undefined
                    }
                  >
                    {seg.text}
                  </span>
                ))
              )}
            </div>

            <div className="border-t border-[#303030] bg-[#181818] px-3 py-2">
              <textarea
                ref={headlessInputRef}
                data-testid="terminal-input"
                aria-label={`Entrada do terminal ${resolvedTitle}`}
                rows={1}
                disabled={session.status !== 'running'}
                placeholder={
                  session.status === 'running'
                    ? 'Digite comandos ou cole aqui (colagem multilinha abre revisão)...'
                    : 'Sessão encerrada — somente leitura'
                }
                onPaste={handleHeadlessPaste}
                onKeyDown={handleHeadlessKeyDown}
                onChange={handleHeadlessChange}
                onCompositionStart={handleHeadlessCompositionStart}
                onCompositionEnd={handleHeadlessCompositionEnd}
                className="w-full resize-none rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>
          </div>
        ) : null}
      </div>

      {/* Multiline paste review dialog */}
      <Dialog.Root
        open={pendingPasteText !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingPasteText(null);
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
          <Dialog.Content
            data-testid="multiline-paste-dialog"
            className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-[#303030] bg-[#202020] p-6 text-[#E8E8E8] shadow-2xl focus:outline-none"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ClipboardPaste aria-hidden="true" className="h-4 w-4 text-[#FCD34D]" />
                <Dialog.Title className="text-sm font-semibold text-[#E8E8E8]">
                  Revisar colagem multilinha
                </Dialog.Title>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  aria-label="Fechar revisão de colagem"
                  className="rounded-lg p-1 text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]"
                >
                  <X aria-hidden="true" className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>

            <Dialog.Description className="mt-2 flex items-start gap-2 rounded-lg border border-[#F59E0B]/40 bg-[#F59E0B]/10 p-2.5 text-xs text-[#FCD34D]">
              <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                {countPasteLines(pendingPasteText ?? '')} linhas detectadas. Colar múltiplas linhas
                pode disparar execução imediata no shell. Revise ou edite antes de enviar.
              </span>
            </Dialog.Description>

            <textarea
              aria-label="Conteúdo revisado para colagem"
              value={pendingPasteText ?? ''}
              onChange={(e) => setPendingPasteText(e.target.value)}
              rows={6}
              className="mt-3 w-full rounded-xl border border-[#303030] bg-[#141414] p-3 font-mono text-xs text-[#E8E8E8] focus:border-[#3B82F6] focus:outline-none"
            />

            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-lg border border-[#303030] bg-[#181818] px-3 py-2 text-xs font-medium text-[#E8E8E8] hover:bg-[#282828]"
                >
                  Cancelar
                </button>
              </Dialog.Close>
              <button
                type="button"
                onClick={() => {
                  const textToSend = pendingPasteText ?? '';
                  setPendingPasteText(null);
                  if (textToSend) {
                    void sendInputData(textToSend);
                  }
                }}
                className="rounded-lg bg-[#E8E8E8] px-3 py-2 text-xs font-medium text-[#181818] hover:bg-white"
              >
                Enviar para o terminal
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <TerminalCloseDialog
        open={closeDialogOpen}
        session={session}
        isSubmitting={isClosingSession}
        errorMessage={closeError}
        onOpenChange={setCloseDialogOpen}
        onKeepRunning={() => void handleConfirmClose(true)}
        onTerminate={() => void handleConfirmClose(false)}
      />
    </section>
  );
}
