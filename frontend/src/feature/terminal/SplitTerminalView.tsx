import { useEffect, useState } from 'react';
import { Columns2, Play, Square, Terminal } from 'lucide-react';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import { openPtySession } from './ptyApi';
import { TerminalPane } from './TerminalPane';
import { clearPersistedPtyBuffer } from './ptyBuffer';
import { PtySessionInfo, PtyWebSocketLike, TerminalAdapterFactory } from './terminalTypes';

export type TerminalLayoutMode = 'split' | 'single-primary' | 'single-secondary';

export interface SplitTerminalViewProps {
  primarySession?: PtySessionInfo | null;
  secondarySession?: PtySessionInfo | null;
  primaryTitle?: string;
  secondaryTitle?: string;
  defaultMode?: TerminalLayoutMode;
  defaultCwd?: string;
  hostId?: string;
  workspaceId?: string;
  client?: ControlPlaneClient;
  token?: string | null;
  transportPreference?: 'auto' | 'ws' | 'sse' | 'poll';
  webSocketFactory?: (url: string, options: { token: string | null }) => PtyWebSocketLike;
  terminalAdapterFactory?: TerminalAdapterFactory;
  onSessionChange?: (slot: 'primary' | 'secondary', session: PtySessionInfo) => void;
  onSessionClosed?: (
    slot: 'primary' | 'secondary',
    session: PtySessionInfo,
    keepRunning: boolean,
  ) => void;
}

interface PersistedSplitViewState {
  mode?: TerminalLayoutMode;
  primary?: string | null;
  secondary?: string | null;
  primarySnapshot?: PtySessionInfo | null;
  secondarySnapshot?: PtySessionInfo | null;
  dismissed?: string[];
}

const splitStateMemory = new Map<string, PersistedSplitViewState>();

function readPersistedSplitState(sessionKey: string): PersistedSplitViewState {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.sessionStorage.getItem(sessionKey);
    if (!raw) {
      splitStateMemory.delete(sessionKey);
      return {};
    }
    const parsed = JSON.parse(raw) as PersistedSplitViewState;
    const mem = splitStateMemory.get(sessionKey);
    return {
      ...mem,
      ...parsed,
      primarySnapshot: parsed.primarySnapshot ?? mem?.primarySnapshot ?? null,
      secondarySnapshot: parsed.secondarySnapshot ?? mem?.secondarySnapshot ?? null,
    };
  } catch {
    return splitStateMemory.get(sessionKey) ?? {};
  }
}

function writePersistedSplitState(sessionKey: string, next: PersistedSplitViewState): void {
  splitStateMemory.set(sessionKey, next);
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage.setItem(sessionKey, JSON.stringify({
      mode: next.mode, primary: next.primary, secondary: next.secondary, dismissed: next.dismissed,
    }));
  } catch {
    // Ignora falha opcional de persistência local
  }
}

function getSessionDriver(session: PtySessionInfo): string | undefined {
  return session.command[0]
    ?.replace(/\\/g, '/')
    .split('/')
    .pop()
    ?.replace(/\.(exe|cmd|bat)$/i, '')
    .toLowerCase();
}

export function SplitTerminalView({
  primarySession: primaryProp = null,
  secondarySession: secondaryProp = null,
  primaryTitle = 'Codex CLI',
  secondaryTitle = 'Claude Code CLI',
  defaultMode = 'split',
  defaultCwd = '.',
  hostId = 'local',
  workspaceId,
  client: clientOverride,
  token,
  transportPreference = 'auto',
  webSocketFactory,
  terminalAdapterFactory,
  onSessionChange,
  onSessionClosed,
}: SplitTerminalViewProps) {
  const defaultClient = useControlPlaneClient();
  const client = clientOverride ?? defaultClient;

  const isControlledByProps = primaryProp !== null || secondaryProp !== null;
  const sessionKey = `hydra:terminals:${JSON.stringify([hostId, workspaceId ?? null, defaultCwd])}`;
  const initialPersisted = !isControlledByProps ? readPersistedSplitState(sessionKey) : {};

  const [mode, setMode] = useState<TerminalLayoutMode>(
    !isControlledByProps && initialPersisted.mode ? initialPersisted.mode : defaultMode,
  );
  const [primarySession, setPrimarySession] = useState<PtySessionInfo | null>(
    primaryProp ?? initialPersisted.primarySnapshot ?? null,
  );
  const [secondarySession, setSecondarySession] = useState<PtySessionInfo | null>(
    secondaryProp ?? initialPersisted.secondarySnapshot ?? null,
  );
  const [dismissedIds, setDismissedIds] = useState<string[]>(
    !isControlledByProps ? (initialPersisted.dismissed ?? []) : [],
  );
  const [launchingSlot, setLaunchingSlot] = useState<'primary' | 'secondary' | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(
    !isControlledByProps &&
      !initialPersisted.primarySnapshot &&
      !initialPersisted.secondarySnapshot,
  );

  // Sync controlled session props when parent passes explicit sessions
  useEffect(() => {
    if (primaryProp !== null) {
      setPrimarySession(primaryProp);
    }
  }, [primaryProp]);

  useEffect(() => {
    if (secondaryProp !== null) {
      setSecondarySession(secondaryProp);
    }
  }, [secondaryProp]);

  // Persist layout mode and active session IDs across tab switches
  useEffect(() => {
    if (isControlledByProps || restoring) {
      return;
    }
    writePersistedSplitState(sessionKey, {
      mode,
      primary: primarySession?.session_id ?? null,
      secondary: secondarySession?.session_id ?? null,
      primarySnapshot: primarySession,
      secondarySnapshot: secondarySession,
      dismissed: dismissedIds,
    });
  }, [isControlledByProps, sessionKey, mode, primarySession, secondarySession, dismissedIds, restoring]);

  useEffect(() => {
    if (isControlledByProps) {
      setRestoring(false);
      return;
    }
    let mounted = true;
    const pinned = readPersistedSplitState(sessionKey);
    if (!pinned.primarySnapshot && !pinned.secondarySnapshot) {
      setRestoring(true);
    }
    const normalize = (value: string) => {
      const normalized = value.replace(/\\/g, '/').replace(/\/$/, '');
      return /^[a-z]:\//i.test(normalized) ? normalized.toLocaleLowerCase() : normalized;
    };
    void client
      .request<PtySessionInfo[]>('/v1/control-plane/pty/sessions')
      .then((rows) => {
        if (!mounted || !Array.isArray(rows)) return;
        const latestPinned = readPersistedSplitState(sessionKey);
        const dismissedSet = new Set(latestPinned.dismissed ?? []);
        const byId = new Map(rows.map((s) => [s.session_id, s]));

        const matching = rows
          .filter(
            (s) =>
              s.status === 'running' &&
              !dismissedSet.has(s.session_id) &&
              s.host_id === hostId &&
              (defaultCwd === '.'
                ? [latestPinned.primary, latestPinned.secondary].includes(s.session_id)
                : normalize(s.cwd) === normalize(defaultCwd)) &&
              (s.workspace_id ?? null) === (workspaceId ?? null),
          )
          .sort((a, b) => a.created_at.localeCompare(b.created_at));

        let nextPrimary: PtySessionInfo | null = null;
        if (latestPinned.primary !== undefined) {
          nextPrimary = latestPinned.primary
            ? (byId.get(latestPinned.primary) ?? latestPinned.primarySnapshot ?? null)
            : null;
        } else {
          nextPrimary = matching.filter((s) => getSessionDriver(s) === 'codex').pop() ?? null;
        }

        let nextSecondary: PtySessionInfo | null = null;
        if (latestPinned.secondary !== undefined) {
          nextSecondary = latestPinned.secondary
            ? (byId.get(latestPinned.secondary) ?? latestPinned.secondarySnapshot ?? null)
            : null;
        } else {
          nextSecondary = matching.filter((s) => getSessionDriver(s) === 'claude').pop() ?? null;
        }

        setPrimarySession(nextPrimary);
        setSecondarySession(nextSecondary);

        if (latestPinned.mode) {
          setMode(latestPinned.mode);
        } else if (nextPrimary && nextSecondary) {
          setMode('split');
        } else if (nextPrimary) {
          setMode('single-primary');
        } else if (nextSecondary) {
          setMode('single-secondary');
        }
      })
      .catch(() => {
        /* An unavailable inventory must not discard an existing session. */
      })
      .finally(() => {
        if (mounted) setRestoring(false);
      });
    return () => {
      mounted = false;
    };
  }, [client, defaultCwd, hostId, workspaceId, isControlledByProps, sessionKey]);

  const handleLaunchSlot = async (slot: 'primary' | 'secondary') => {
    if (launchingSlot || restoring) return;
    setLaunchingSlot(slot);
    setLaunchError(null);
    const command = slot === 'primary' ? ['codex'] : ['claude'];
    try {
      const created = await openPtySession(client, {
        command,
        cwd: defaultCwd,
        host_id: hostId,
        workspace_id: workspaceId,
        cols: 100,
        rows: 28,
      });
      setDismissedIds((prev) => prev.filter((id) => id !== created.session_id));
      const hadAnySession = Boolean(primarySession || secondarySession);
      if (slot === 'primary') {
        setPrimarySession(created);
      } else {
        setSecondarySession(created);
      }
      if (!hadAnySession) {
        setMode(slot === 'primary' ? 'single-primary' : 'single-secondary');
      }
      onSessionChange?.(slot, created);
    } catch (err) {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : 'Não foi possível abrir nova sessão PTY.';
      setLaunchError(msg);
    } finally {
      setLaunchingSlot(null);
    }
  };

  const handleSlotClosed = (
    slot: 'primary' | 'secondary',
    closedSession: PtySessionInfo,
    keepRunning: boolean,
  ) => {
    if (!keepRunning) {
      clearPersistedPtyBuffer(closedSession.session_id);
    }
    setDismissedIds((prev) =>
      prev.includes(closedSession.session_id) ? prev : [...prev, closedSession.session_id],
    );

    if (slot === 'secondary') {
      setSecondarySession(null);
      if (mode === 'split' || mode === 'single-secondary') {
        setMode('single-primary');
      }
    } else {
      if (secondarySession) {
        setPrimarySession(secondarySession);
        setSecondarySession(null);
        setMode('single-primary');
      } else {
        setPrimarySession(null);
        if (mode === 'split') {
          setMode('single-primary');
        }
      }
    }

    onSessionClosed?.(slot, closedSession, keepRunning);
  };

  const resolvePaneTitle = (session: PtySessionInfo, fallbackTitle: string): string => {
    const driver = getSessionDriver(session);
    if (fallbackTitle === 'Codex CLI' && driver === 'claude') {
      return secondaryTitle;
    }
    if (fallbackTitle === 'Claude Code CLI' && driver === 'codex') {
      return primaryTitle;
    }
    return fallbackTitle;
  };

  const showPrimary = mode === 'split' || mode === 'single-primary';
  const showSecondary = mode === 'split' || mode === 'single-secondary';

  return (
    <div
      data-testid="split-terminal-view"
      data-layout-mode={mode}
      className="flex h-full min-h-0 flex-col gap-3 bg-[var(--bg-main)] p-3 text-[var(--text-primary)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-sidebar)] px-3 py-2">
        <div className="flex items-center gap-2">
          <Terminal aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
          <h1 className="text-sm font-semibold text-[var(--text-primary)]">Terminal</h1>
        </div>

        <div
          role="group"
          aria-label="Modo de visualização do terminal"
          className="flex flex-wrap items-center gap-1.5"
        >
          <button
            type="button"
            aria-pressed={mode === 'split'}
            onClick={() => setMode('split')}
            className={`inline-flex min-h-[32px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px] ${
              mode === 'split'
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--text-primary)]'
                : 'border-[var(--border)] bg-[var(--bg-rail)] text-[var(--text-muted)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] [@media(hover:hover)_and_(pointer:fine)]:hover:text-[var(--text-primary)]'
            }`}
          >
            <Columns2 aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Lado a lado</span>
          </button>

          <button
            type="button"
            aria-pressed={mode === 'single-primary'}
            onClick={() => setMode('single-primary')}
            className={`inline-flex min-h-[32px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px] ${
              mode === 'single-primary'
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--text-primary)]'
                : 'border-[var(--border)] bg-[var(--bg-rail)] text-[var(--text-muted)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] [@media(hover:hover)_and_(pointer:fine)]:hover:text-[var(--text-primary)]'
            }`}
          >
            <Square aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{primaryTitle}</span>
          </button>

          <button
            type="button"
            aria-pressed={mode === 'single-secondary'}
            onClick={() => setMode('single-secondary')}
            className={`inline-flex min-h-[32px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px] ${
              mode === 'single-secondary'
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--text-primary)]'
                : 'border-[var(--border)] bg-[var(--bg-rail)] text-[var(--text-muted)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] [@media(hover:hover)_and_(pointer:fine)]:hover:text-[var(--text-primary)]'
            }`}
          >
            <Square aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{secondaryTitle}</span>
          </button>
        </div>
      </div>

      {launchError ? (
        <div
          role="alert"
          className="rounded-lg border border-[var(--status-error)] bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--status-error)]"
        >
          {launchError}
        </div>
      ) : null}
      {restoring && (
        <p role="status" className="text-sm text-[var(--text-muted)]">
          Reconectando aos terminais abertos…
        </p>
      )}

      {/* Keep mounted panes alive across split/single switches so streams & scrollback persist */}
      <div
        className={`grid min-h-0 flex-1 gap-3 ${
          mode === 'split' ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'
        }`}
      >
        <div
          data-testid="terminal-slot-primary"
          className={showPrimary ? 'flex min-h-0 min-w-0 flex-col' : 'hidden'}
        >
          {primarySession ? (
            <TerminalPane
              session={primarySession}
              title={resolvePaneTitle(primarySession, primaryTitle)}
              client={client}
              token={token}
              transportPreference={transportPreference}
              webSocketFactory={webSocketFactory}
              terminalAdapterFactory={terminalAdapterFactory}
              compact={mode === 'split'}
              autoFocus={showPrimary}
              persistCursor={!isControlledByProps}
              onSessionChange={(updated) => {
                setPrimarySession(updated);
                onSessionChange?.('primary', updated);
              }}
              onClosed={(closedSession, keepRunning) => {
                handleSlotClosed('primary', closedSession, keepRunning);
              }}
            />
          ) : (
            <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-center">
              <Terminal aria-hidden="true" className="h-7 w-7 text-[var(--text-muted)]" />
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">{primaryTitle}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Abra o Codex e digite seu prompt no terminal.
                </p>
              </div>
              <button
                type="button"
                disabled={launchingSlot !== null || restoring}
                onClick={() => void handleLaunchSlot('primary')}
                className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg bg-[var(--btn-primary-bg)] px-3.5 py-1.5 text-xs font-medium text-[var(--btn-primary-text)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--accent-hover)] disabled:opacity-60 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
              >
                <Play aria-hidden="true" className="h-3.5 w-3.5" />
                <span>
                  {launchingSlot === 'primary' ? 'Abrindo Codex…' : `Iniciar ${primaryTitle}`}
                </span>
              </button>
            </div>
          )}
        </div>

        <div
          data-testid="terminal-slot-secondary"
          className={showSecondary ? 'flex min-h-0 min-w-0 flex-col' : 'hidden'}
        >
          {secondarySession ? (
            <TerminalPane
              session={secondarySession}
              title={resolvePaneTitle(secondarySession, secondaryTitle)}
              client={client}
              token={token}
              transportPreference={transportPreference}
              webSocketFactory={webSocketFactory}
              terminalAdapterFactory={terminalAdapterFactory}
              compact={mode === 'split'}
              autoFocus={showSecondary && !primarySession}
              persistCursor={!isControlledByProps}
              onSessionChange={(updated) => {
                setSecondarySession(updated);
                onSessionChange?.('secondary', updated);
              }}
              onClosed={(closedSession, keepRunning) => {
                handleSlotClosed('secondary', closedSession, keepRunning);
              }}
            />
          ) : (
            <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-6 text-center">
              <Terminal aria-hidden="true" className="h-7 w-7 text-[var(--text-muted)]" />
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">{secondaryTitle}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Abra o Claude e digite seu prompt no terminal.
                </p>
              </div>
              <button
                type="button"
                disabled={launchingSlot !== null || restoring}
                onClick={() => void handleLaunchSlot('secondary')}
                className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg bg-[var(--btn-primary-bg)] px-3.5 py-1.5 text-xs font-medium text-[var(--btn-primary-text)] [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--accent-hover)] disabled:opacity-60 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
              >
                <Play aria-hidden="true" className="h-3.5 w-3.5" />
                <span>
                  {launchingSlot === 'secondary' ? 'Abrindo Claude…' : `Iniciar ${secondaryTitle}`}
                </span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
