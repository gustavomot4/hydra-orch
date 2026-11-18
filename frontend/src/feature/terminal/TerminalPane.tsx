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
import { useLayoutStore } from '@/store/layoutStore';
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

import { clearPersistedPtyBuffer, getPersistedPtyBuffer, MAX_HEADLESS_CHARS, setPersistedPtyBuffer } from './ptyBuffer';

const RESIZE_DELAY_MS = 90;
function readCssToken(name: string): string | undefined {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return undefined;
  }
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || undefined;
}

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
  labelTitle: string,
): TerminalViewportAdapter {
  const bgMain = readCssToken('--bg-main');
  const bgRail = readCssToken('--bg-rail');
  const textPrimary = readCssToken('--text-primary');
  const accent = readCssToken('--accent');
  const accentSoft = readCssToken('--accent-soft');
  const statusError = readCssToken('--status-error');
  const statusSuccess = readCssToken('--status-success');
  const statusWarning = readCssToken('--status-warning');
  const statusInfo = readCssToken('--status-info');

  const term = new Terminal({
    cols: options.cols,
    rows: options.rows,
    windowsPty: options.backendKind === 'windows_conpty' ? { backend: 'conpty' } : undefined,
    cursorBlink: true,
    fontFamily:
      readCssToken('--font-mono') ??
      'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: useLayoutStore.getState().terminalFontSize,
    lineHeight: 1.4,
    scrollback: 2000,
    theme: {
      background: bgMain,
      foreground: textPrimary,
      cursor: accent ?? textPrimary,
      cursorAccent: bgMain,
      selectionBackground: accentSoft,
      black: bgRail,
      red: statusError,
      green: statusSuccess,
      yellow: statusWarning,
      blue: statusInfo,
      magenta: accent,
      cyan: statusInfo,
      white: textPrimary,
    },
  });
  const fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(container);

  term.attachCustomKeyEventHandler((ev) => {
    if (ev.type === 'keydown' && (ev.key === 'F6' || ev.key === 'Escape')) {
      if (ev.key === 'F6' || ev.ctrlKey || options.shouldEscapeOnBareEsc?.()) {
        ev.preventDefault();
        options.onEscapeFocus?.();
        return false;
      }
    }
    return true;
  });

  const fit = () => {
    if (!container.clientWidth || !container.clientHeight) return null;
    const dimensions = fitAddon.proposeDimensions();
    if (!dimensions) return null;
    if (dimensions.cols !== term.cols || dimensions.rows !== term.rows) {
      fitAddon.fit();
    }
    return { cols: term.cols, rows: term.rows };
  };

  const pasteCaptureHandler = (event: globalThis.ClipboardEvent) => {
    const pasted =
      event.clipboardData?.getData('text/plain') ?? event.clipboardData?.getData('text') ?? '';
    if (pasted && isMultilinePaste(pasted) && options.onMultilinePaste) {
      event.preventDefault();
      event.stopPropagation();
      options.onMultilinePaste(pasted);
    }
  };

  const textarea = term.textarea;
  if (textarea) {
    textarea.setAttribute('aria-label', `Entrada do terminal ${labelTitle}`);
    if (options.escapeHintId) {
      textarea.setAttribute('aria-describedby', options.escapeHintId);
    }
    textarea.addEventListener('paste', pasteCaptureHandler, true);
  }

  const unsubscribeFont = useLayoutStore.subscribe((next, prev) => {
    if (next.terminalFontSize !== prev.terminalFontSize) {
      term.options.fontSize = next.terminalFontSize;
      fit();
    }
  });

  let resizeObserver: ResizeObserver | null = null;
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(fit);
    resizeObserver.observe(container);
  }

  return {
    kind: 'xterm',
    write: (text) => term.write(text),
    restore: (text) => {
      // Escape sequences in the recorded output can request terminal reports.
      // Replaying them must not inject input into the running process.
      term.options.disableStdin = true;
      term.write(text, () => {
        term.options.disableStdin = false;
      });
    },
    clear: () => term.clear(),
    resize: (cols, rows) => term.resize(cols, rows),
    fit,
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
      unsubscribeFont();
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
  autoFocus?: boolean;
  persistCursor?: boolean;
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
  autoFocus = false,
  persistCursor = false,
  onSessionChange,
  onClosed,
  className = '',
  compact = false,
}: TerminalPaneProps) {
  const defaultClient = useControlPlaneClient();
  const storeToken = useAuthStore((s) => s.token);
  const client = clientOverride ?? defaultClient;
  const token = tokenOverride !== undefined ? tokenOverride : storeToken;

  const initialCached = persistCursor ? getPersistedPtyBuffer(initialSession.session_id) : null;

  const [session, setSession] = useState<PtySessionInfo>(initialSession);
  const [transportMode, setTransportMode] = useState<PtyTransportMode>('connecting');
  const [headlessBuffer, setHeadlessBuffer] = useState<string>(initialCached?.buffer ?? '');
  const [rendererKind, setRendererKind] = useState<'xterm' | 'headless-dom' | 'loading'>('loading');
  const [lastSeqDisplay, setLastSeqDisplay] = useState<number>(initialCached?.lastSeq ?? 0);
  const [cursorExpiredNotice, setCursorExpiredNotice] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [terminalFocused, setTerminalFocused] = useState<boolean>(false);

  const [pendingPasteText, setPendingPasteText] = useState<string | null>(null);
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [isClosingSession, setIsClosingSession] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [reconnectNonce, setReconnectNonce] = useState(0);

  const viewportRef = useRef<HTMLDivElement | null>(null);
  const toolbarGroupRef = useRef<HTMLDivElement | null>(null);
  const headlessInputRef = useRef<HTMLTextAreaElement | null>(null);
  const adapterRef = useRef<TerminalViewportAdapter | null>(null);
  const wsRef = useRef<PtyWebSocketLike | null>(null);
  const lastSeqRef = useRef<number>(initialCached?.lastSeq ?? 0);
  const rawTranscriptRef = useRef<string>(initialCached?.buffer ?? '');
  const displaySeqFrame = useRef<number | null>(null);
  const resizeTimer = useRef<number | null>(null);
  const requestedSize = useRef<TerminalDimensions | null>(null);
  const httpInputQueue = useRef(Promise.resolve());
  const sessionRef = useRef<PtySessionInfo>(initialSession);
  const isComposingRef = useRef<boolean>(false);
  const terminalFocusedRef = useRef<boolean>(false);
  const persistCursorRef = useRef<boolean>(persistCursor);
  const onSessionChangeRef = useRef(onSessionChange);
  const autoFocusRef = useRef(autoFocus);

  const resolvedTitle =
    title ?? (session.command.length > 0 ? session.command.join(' ') : 'Terminal PTY');
  const escapeHintId = `terminal-escape-hint-${session.session_id}`;

  useEffect(() => {
    persistCursorRef.current = persistCursor;
  }, [persistCursor]);
  useEffect(() => {
    onSessionChangeRef.current = onSessionChange;
  }, [onSessionChange]);
  useEffect(() => {
    autoFocusRef.current = autoFocus;
  }, [autoFocus]);

  useEffect(
    () => () => {
      if (displaySeqFrame.current !== null) window.cancelAnimationFrame(displaySeqFrame.current);
      if (resizeTimer.current !== null) window.clearTimeout(resizeTimer.current);
      displaySeqFrame.current = null;
      resizeTimer.current = null;
    },
    [],
  );

  const escapeTerminalFocus = useCallback(() => {
    terminalFocusedRef.current = false;
    setTerminalFocused(false);
    const target = toolbarGroupRef.current?.querySelector<HTMLButtonElement>(
      'button:not(:disabled)',
    );
    target?.focus();
  }, []);

  const updateSession = useCallback((next: PtySessionInfo) => {
    if (next.session_id !== sessionRef.current.session_id) return;
    sessionRef.current = next;
    setSession(next);
    onSessionChangeRef.current?.(next);
  }, []);

  // Sync if caller switches to a different session_id (e.g. secondary promoted to primary)
  useEffect(() => {
    if (initialSession.session_id !== sessionRef.current.session_id) {
      const nextCached = persistCursorRef.current
        ? getPersistedPtyBuffer(initialSession.session_id)
        : null;
      const nextSeq = nextCached?.lastSeq ?? 0;
      const nextBuf = nextCached?.buffer ?? '';

      lastSeqRef.current = nextSeq;
      rawTranscriptRef.current = nextBuf;
      requestedSize.current = null;
      if (resizeTimer.current !== null) window.clearTimeout(resizeTimer.current);
      resizeTimer.current = null;
      setLastSeqDisplay(nextSeq);
      setHeadlessBuffer(nextBuf);
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
    const combinedTranscript = rawTranscriptRef.current + chunk.text;
    rawTranscriptRef.current =
      combinedTranscript.length > MAX_HEADLESS_CHARS
        ? combinedTranscript.slice(combinedTranscript.length - MAX_HEADLESS_CHARS)
        : combinedTranscript;

    if (persistCursorRef.current) {
      setPersistedPtyBuffer(sessionRef.current.session_id, chunk.seq, rawTranscriptRef.current);
    }

    if (adapterRef.current) {
      adapterRef.current.write(chunk.text);
      if (displaySeqFrame.current === null) {
        displaySeqFrame.current = window.requestAnimationFrame(() => {
          displaySeqFrame.current = null;
          setLastSeqDisplay(lastSeqRef.current);
        });
      }
    } else {
      setLastSeqDisplay(chunk.seq);
      setHeadlessBuffer(rawTranscriptRef.current);
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
      const { session_id: sessionId } = sessionRef.current;
      httpInputQueue.current = httpInputQueue.current.then(async () => {
        if (sessionRef.current.session_id !== sessionId || sessionRef.current.status !== 'running')
          return;
        try {
          await writePtyInput(client, sessionId, data);
        } catch (err) {
          const msg =
            err instanceof ControlPlaneApiError
              ? err.payload.message
              : 'Falha ao enviar entrada para o terminal.';
          setErrorBanner(msg);
        }
      });
    },
    [client],
  );

  const handleResizeDimensions = useCallback(
    (dims: TerminalDimensions) => {
      if (sessionRef.current.status !== 'running') {
        return;
      }
      const cols = Math.max(1, Math.min(1000, Math.round(dims.cols)));
      const rows = Math.max(1, Math.min(1000, Math.round(dims.rows)));
      const { session_id: sessionId } = sessionRef.current;
      if (resizeTimer.current !== null) window.clearTimeout(resizeTimer.current);
      resizeTimer.current = window.setTimeout(async () => {
        resizeTimer.current = null;
        if (sessionRef.current.session_id !== sessionId || sessionRef.current.status !== 'running')
          return;
        const previous = requestedSize.current ?? sessionRef.current;
        if (previous.cols === cols && previous.rows === rows) return;
        const requested = { cols, rows };
        requestedSize.current = requested;
        try {
          const ws = wsRef.current;
          if (ws?.readyState === 1) {
            ws.send(JSON.stringify({ type: 'resize', cols, rows }));
            return;
          }
          const updated = await resizePtySession(client, sessionId, cols, rows);
          updateSession(updated);
        } catch (err) {
          if (requestedSize.current === requested) requestedSize.current = null;
          if (err instanceof ControlPlaneApiError && err.status !== 409)
            setErrorBanner(err.payload.message);
        }
      }, RESIZE_DELAY_MS);
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

    const adapterOpts: TerminalAdapterOptions = {
      cols: sessionRef.current.cols,
      rows: sessionRef.current.rows,
      backendKind: sessionRef.current.backend_kind,
      escapeHintId,
      onMultilinePaste: (text) => setPendingPasteText(text),
      onInterruptShortcut: () => void handleInterrupt(),
      onEscapeFocus: escapeTerminalFocus,
      shouldEscapeOnBareEsc: () => terminalFocusedRef.current,
    };

    let created: TerminalViewportAdapter | null = null;
    if (terminalAdapterFactory) {
      created = terminalAdapterFactory(container, adapterOpts);
    } else if (canUseCanvasRenderer()) {
      try {
        created = createXtermAdapter(container, adapterOpts, resolvedTitle);
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
    if (rawTranscriptRef.current.length > 0) {
      (created.restore ?? created.write)(rawTranscriptRef.current);
    }
    if (autoFocusRef.current && container.clientWidth > 0) {
      created.focus();
    }
    const unsubData = created.onData((data) => {
      void sendInputData(data);
    });
    const unsubResize = created.onResize((dims) => {
      void handleResizeDimensions(dims);
    });
    const fitToViewport = () => {
      if (adapterRef.current !== created) return;
      const dimensions = created.fit();
      if (dimensions) handleResizeDimensions(dimensions);
    };
    if (created.kind === 'xterm') {
      if (document.fonts) void document.fonts.ready.then(fitToViewport);
      else fitToViewport();
    }

    return () => {
      unsubData();
      unsubResize();
      created?.dispose();
      adapterRef.current = null;
    };
  }, [
    session.session_id,
    escapeHintId,
    resolvedTitle,
    terminalAdapterFactory,
    handleInterrupt,
    escapeTerminalFocus,
    sendInputData,
    handleResizeDimensions,
  ]);

  // Bidirectional WS stream with automatic HTTP SSE & /output fallback + after_seq replay
  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();
    let activeWs: PtyWebSocketLike | null = null;
    let pollTimer: number | null = null;
    let wsAuthTimer: number | null = null;

    const cleanupWs = () => {
      if (wsAuthTimer !== null) {
        window.clearTimeout(wsAuthTimer);
        wsAuthTimer = null;
      }
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
      requestedSize.current = null;
    };

    const resetExpiredCursor = (expiredSeq: number) => {
      setCursorExpiredNotice(
        `Cursor after_seq=${expiredSeq} expirado (HTTP 410); recarregando backlog retido.`,
      );
      lastSeqRef.current = 0;
      rawTranscriptRef.current = '';
      setLastSeqDisplay(0);
      setHeadlessBuffer('');
      adapterRef.current?.clear();
      if (persistCursorRef.current) {
        setPersistedPtyBuffer(session.session_id, 0, '');
      }
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
          resetExpiredCursor(lastSeqRef.current);
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
          resetExpiredCursor(lastSeqRef.current);
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
        (Boolean(token) && typeof window !== 'undefined' && typeof window.WebSocket === 'function');

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
        wsAuthTimer = window.setTimeout(triggerFallback, 2500);
      } catch {
        await runSseFallback();
        return;
      }

      activeWs.onopen = () => {
        if (cancelled) {
          return;
        }
        if (webSocketFactory) {
          markReady();
        } else {
          try {
            activeWs?.send(JSON.stringify({ type: 'authenticate', token }));
          } catch {
            triggerFallback();
          }
        }
      };

      function markReady() {
        if (opened) return;
        if (wsAuthTimer !== null) {
          window.clearTimeout(wsAuthTimer);
          wsAuthTimer = null;
        }
        wsRef.current = activeWs;
        opened = true;
        setTransportMode('ws');
      }

      activeWs.onmessage = (event) => {
        if (cancelled) {
          return;
        }
        try {
          const msg = JSON.parse(event.data) as PtyWsServerMessage;
          if (msg.type === 'ready') {
            markReady();
          } else if (msg.type === 'chunk') {
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

  const handleViewportKeyDownCapture = (event: KeyboardEvent<HTMLDivElement>) => {
    if (isComposingRef.current || pendingPasteText !== null || closeDialogOpen) {
      return;
    }
    if (event.key === 'F6' || (event.key === 'Escape' && (event.ctrlKey || terminalFocused))) {
      event.preventDefault();
      event.stopPropagation();
      escapeTerminalFocus();
    }
  };

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
        typeof window !== 'undefined' ? (window.getSelection()?.toString() ?? '') : '';
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
      typeof window !== 'undefined' ? (window.getSelection()?.toString() ?? '') : '';
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
    clearPersistedPtyBuffer(session.session_id);
    onClosed?.(session, false);
  };

  const handleConfirmClose = async (keepRunning: boolean) => {
    setIsClosingSession(true);
    setCloseError(null);
    try {
      const updated = await closePtySession(client, session.session_id, keepRunning);
      if (!keepRunning) {
        clearPersistedPtyBuffer(session.session_id);
      }
      updateSession(updated);
      setCloseDialogOpen(false);
      onClosed?.(updated, keepRunning);
    } catch (err) {
      const msg =
        err instanceof ControlPlaneApiError ? err.payload.message : 'Erro ao fechar sessão PTY.';
      setCloseError(msg);
    } finally {
      setIsClosingSession(false);
    }
  };

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
      data-transport={transportMode}
      className={`flex h-full min-h-[340px] flex-col overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-main)] text-[var(--text-primary)] ${className}`}
    >
      <header className="border-b border-[var(--border)] bg-[var(--bg-sidebar)] px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[var(--border)] bg-[var(--bg-surface)]">
              <TerminalIcon aria-hidden="true" className="h-3.5 w-3.5 text-[var(--text-primary)]" />
            </span>
            <h2 className="truncate text-xs font-semibold text-[var(--text-primary)]">
              {resolvedTitle}
            </h2>

            <StatusBadge status={session.status} labelOverride={statusLabel} compact />

            {session.exit_code !== null ? (
              <span
                data-testid="pty-exit-code"
                className="inline-flex items-center rounded-md border border-[var(--border)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-xs text-[var(--text-primary)]"
              >
                Código de saída: <code className="ml-1">{session.exit_code}</code>
              </span>
            ) : null}

            <span
              data-testid="pty-capability-badge"
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${
                session.pty_certified
                  ? 'border-[var(--status-success)] bg-[var(--bg-surface)] text-[var(--status-success)]'
                  : 'border-[var(--status-warning)] bg-[var(--bg-surface)] text-[var(--status-warning)]'
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

          <div ref={toolbarGroupRef} className="flex flex-wrap items-center gap-1.5">
            <code className="rounded border border-[var(--border)] bg-[var(--bg-main)] px-1.5 py-0.5 text-xs text-[var(--text-muted)]">
              {transportLabel} {session.cols}×{session.rows} seq {lastSeqDisplay}
            </code>

            <button
              type="button"
              onClick={handleTriggerFitResize}
              disabled={session.status !== 'running'}
              title="Ajustar dimensões do terminal"
              aria-label="Ajustar dimensões do terminal"
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-primary)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] disabled:cursor-not-allowed disabled:opacity-50 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <Maximize2 aria-hidden="true" className="h-3.5 w-3.5" />
              {!compact ? <span>Ajustar</span> : null}
            </button>

            <button
              type="button"
              onClick={() => void handleCopySelection()}
              title="Copiar saída selecionada"
              aria-label={copyFeedback ? `${copyFeedback} saída selecionada` : 'Copiar saída selecionada'}
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-primary)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <Copy aria-hidden="true" className="h-3.5 w-3.5" />
              {!compact ? <span>{copyFeedback ?? 'Copiar'}</span> : null}
            </button>

            <button
              type="button"
              onClick={() => setReconnectNonce((n) => n + 1)}
              title="Reconectar stream a partir do cursor atual"
              aria-label="Reconectar stream PTY"
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-primary)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
              {!compact ? <span>Reconectar</span> : null}
            </button>

            <button
              type="button"
              onClick={() => void handleInterrupt()}
              disabled={session.status !== 'running'}
              title="Enviar interrupção (Ctrl+C / SIGINT)"
              aria-label="Interromper processo"
              className="inline-flex min-h-[32px] items-center justify-center gap-1 rounded-md border border-[var(--status-warning)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs font-medium text-[var(--status-warning)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] disabled:cursor-not-allowed disabled:opacity-40 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
            >
              <OctagonX aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Interromper</span>
            </button>

            <button
              type="button"
              onClick={handleRequestClose}
              title="Fechar terminal"
              aria-label="Fechar terminal"
              className="inline-flex min-h-[32px] items-center justify-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-primary)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:border-[var(--status-error)] [@media(hover:hover)_and_(pointer:fine)]:hover:text-[var(--status-error)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
            >
              <X aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Fechar</span>
            </button>
          </div>
        </div>

        {/* Always-visible identity metadata row */}
        <dl
          data-testid="pty-header-metadata"
          className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--text-muted)]"
        >
          <div className="inline-flex items-center gap-1">
            <Server aria-hidden="true" className="h-3 w-3 text-[var(--text-muted)]" />
            <dt className="sr-only">Host</dt>
            <dd data-testid="pty-meta-host" className="text-[var(--text-primary)]">
              <code>{session.host_id}</code>
            </dd>
          </div>
          <div className="inline-flex min-w-0 items-center gap-1">
            <dt>cwd:</dt>
            <dd
              data-testid="pty-meta-cwd"
              title={session.cwd}
              className="max-w-[320px] truncate text-[var(--text-primary)]"
            >
              <code>{session.cwd}</code>
            </dd>
          </div>
          <div className="inline-flex items-center gap-1">
            <dt>sessão:</dt>
            <dd data-testid="pty-meta-session" className="text-[var(--text-primary)]">
              <code>{session.session_id}</code>
            </dd>
          </div>
          {session.detached ? (
            <span className="rounded bg-[var(--bg-surface)] px-1.5 py-0.5 text-xs text-[var(--text-muted)]">
              Segundo plano
            </span>
          ) : null}
        </dl>
      </header>

      {cursorExpiredNotice ? (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--status-warning)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs text-[var(--status-warning)]"
        >
          <span>{cursorExpiredNotice}</span>
          <button
            type="button"
            onClick={() => setCursorExpiredNotice(null)}
            className="min-h-[28px] px-2 text-xs underline max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
          >
            Dispensar
          </button>
        </div>
      ) : null}

      {errorBanner ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--status-error)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs text-[var(--status-error)]"
        >
          <span>{errorBanner}</span>
          <button
            type="button"
            onClick={() => setErrorBanner(null)}
            className="min-h-[28px] px-2 text-xs underline max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
          >
            Fechar aviso
          </button>
        </div>
      ) : null}

      {/* Viewport */}
      <div
        ref={viewportRef}
        onKeyDownCapture={handleViewportKeyDownCapture}
        onFocusCapture={() => {
          terminalFocusedRef.current = true;
          setTerminalFocused(true);
        }}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            terminalFocusedRef.current = false;
            setTerminalFocused(false);
          }
        }}
        onClick={() => {
          if (adapterRef.current) {
            adapterRef.current.focus();
          } else {
            headlessInputRef.current?.focus();
          }
        }}
        className="relative flex min-h-[240px] min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-main)] focus-within:ring-2 focus-within:ring-inset focus-within:ring-[var(--accent)] [&>.xterm]:h-full [&>.xterm]:w-full"
      >
        {rendererKind === 'headless-dom' ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <pre
              role="log"
              aria-live="polite"
              aria-label={`Saída do terminal ${resolvedTitle}`}
              data-testid="terminal-output"
              className="m-0 min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap break-words p-3 text-xs leading-relaxed text-[var(--text-primary)]"
            >
              {renderedSegments.length === 0 ? (
                <span className="text-[var(--text-muted)]">Aguardando saída do processo PTY...</span>
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
            </pre>

            <div className="border-t border-[var(--border)] bg-[var(--bg-rail)] px-3 py-2">
              <textarea
                ref={headlessInputRef}
                data-testid="terminal-input"
                aria-label={`Entrada do terminal ${resolvedTitle}`}
                aria-describedby={escapeHintId}
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
                className="w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-2.5 py-1.5 font-mono text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>
          </div>
        ) : null}
      </div>

      {/* Subtle accessible keyboard escape hint (WCAG 2.1.2) */}
      <div
        id={escapeHintId}
        data-testid="terminal-escape-hint"
        data-active={terminalFocused ? 'true' : 'false'}
        className={`flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border)] px-3 py-1.5 text-xs ${
          terminalFocused
            ? 'bg-[var(--accent-soft)] text-[var(--text-primary)]'
            : 'bg-[var(--bg-rail)] text-[var(--text-muted)]'
        }`}
      >
        <span>
          Teclado: pressione{' '}
          <kbd className="rounded border border-[var(--border)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-xs text-[var(--text-primary)]">
            F6
          </kbd>
          ,{' '}
          <kbd className="rounded border border-[var(--border)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-xs text-[var(--text-primary)]">
            Ctrl+Esc
          </kbd>{' '}
          ou{' '}
          <kbd className="rounded border border-[var(--border)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-xs text-[var(--text-primary)]">
            Esc
          </kbd>{' '}
          para sair do terminal e focar os controles.
        </span>
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
          <Dialog.Overlay className="fixed inset-0 z-50 bg-[var(--bg-main)]/80" />
          <Dialog.Content
            data-testid="multiline-paste-dialog"
            className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 text-[var(--text-primary)] shadow-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ClipboardPaste
                  aria-hidden="true"
                  className="h-4 w-4 text-[var(--status-warning)]"
                />
                <Dialog.Title className="text-sm font-semibold text-[var(--text-primary)]">
                  Revisar colagem multilinha
                </Dialog.Title>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  aria-label="Fechar revisão de colagem"
                  className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-lg p-1.5 text-[var(--text-muted)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] [@media(hover:hover)_and_(pointer:fine)]:hover:text-[var(--text-primary)] max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
                >
                  <X aria-hidden="true" className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>

            <Dialog.Description className="mt-2 flex items-start gap-2 rounded-lg border border-[var(--status-warning)] bg-[var(--bg-main)] p-2.5 text-xs text-[var(--status-warning)]">
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
              className="mt-3 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-main)] p-3 font-mono text-xs text-[var(--text-primary)] focus:border-[var(--accent)]"
            />

            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--bg-rail)] px-3 py-2 text-xs font-medium text-[var(--text-primary)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
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
                className="min-h-[36px] rounded-lg bg-[var(--btn-primary-bg)] px-3 py-2 text-xs font-medium text-[var(--btn-primary-text)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--accent-hover)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
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
