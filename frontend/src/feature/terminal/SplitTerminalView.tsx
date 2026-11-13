import { useState } from 'react';
import { Columns2, Play, Square, Terminal } from 'lucide-react';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import { openPtySession } from './ptyApi';
import { TerminalPane } from './TerminalPane';
import {
  PtySessionInfo,
  PtyWebSocketLike,
  TerminalAdapterFactory,
} from './terminalTypes';

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

  const [mode, setMode] = useState<TerminalLayoutMode>(defaultMode);
  const [primarySession, setPrimarySession] = useState<PtySessionInfo | null>(primaryProp);
  const [secondarySession, setSecondarySession] = useState<PtySessionInfo | null>(secondaryProp);
  const [launchingSlot, setLaunchingSlot] = useState<'primary' | 'secondary' | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);

  const activePrimary = primaryProp !== undefined && primaryProp !== null ? primaryProp : primarySession;
  const activeSecondary =
    secondaryProp !== undefined && secondaryProp !== null ? secondaryProp : secondarySession;

  const handleLaunchSlot = async (slot: 'primary' | 'secondary') => {
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
      if (slot === 'primary') {
        setPrimarySession(created);
      } else {
        setSecondarySession(created);
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

  const showPrimary = mode === 'split' || mode === 'single-primary';
  const showSecondary = mode === 'split' || mode === 'single-secondary';

  return (
    <div
      data-testid="split-terminal-view"
      data-layout-mode={mode}
      className="flex h-full min-h-0 flex-col gap-3 bg-[#141414] p-3 text-[#E8E8E8]"
    >
      {/* Mode toolbar (Figma 7:69, 22:8, 22:239) */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#303030] bg-[#1C1C1C] px-3 py-2">
        <div className="flex items-center gap-2">
          <Terminal aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h1 className="text-xs font-semibold text-[#E8E8E8]">Terminais interativos PTY</h1>
        </div>

        <div role="group" aria-label="Modo de visualização do terminal" className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            aria-pressed={mode === 'split'}
            onClick={() => setMode('split')}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
              mode === 'split'
                ? 'border-[#3B82F6]/60 bg-[#202020] text-[#E8E8E8]'
                : 'border-[#303030] bg-[#181818] text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
            }`}
          >
            <Columns2 aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Lado a lado</span>
          </button>

          <button
            type="button"
            aria-pressed={mode === 'single-primary'}
            onClick={() => setMode('single-primary')}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
              mode === 'single-primary'
                ? 'border-[#3B82F6]/60 bg-[#202020] text-[#E8E8E8]'
                : 'border-[#303030] bg-[#181818] text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
            }`}
          >
            <Square aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{primaryTitle}</span>
          </button>

          <button
            type="button"
            aria-pressed={mode === 'single-secondary'}
            onClick={() => setMode('single-secondary')}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
              mode === 'single-secondary'
                ? 'border-[#3B82F6]/60 bg-[#202020] text-[#E8E8E8]'
                : 'border-[#303030] bg-[#181818] text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
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
          className="rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
        >
          {launchError}
        </div>
      ) : null}

      {/* Keep mounted panes alive across split/single switches so streams & scrollback persist */}
      <div
        className={`grid min-h-0 flex-1 gap-3 ${
          mode === 'split' ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'
        }`}
      >
        <div
          data-testid="terminal-slot-primary"
          className={showPrimary ? 'flex min-h-0 flex-col' : 'hidden'}
        >
          {activePrimary ? (
            <TerminalPane
              session={activePrimary}
              title={primaryTitle}
              client={client}
              token={token}
              transportPreference={transportPreference}
              webSocketFactory={webSocketFactory}
              terminalAdapterFactory={terminalAdapterFactory}
              compact={mode === 'split'}
              onSessionChange={(updated) => {
                setPrimarySession(updated);
                onSessionChange?.('primary', updated);
              }}
              onClosed={(closedSession, keepRunning) => {
                if (!keepRunning) {
                  setPrimarySession(closedSession);
                }
                onSessionClosed?.('primary', closedSession, keepRunning);
              }}
            />
          ) : (
            <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[#303030] bg-[#202020] p-6 text-center">
              <Terminal aria-hidden="true" className="h-7 w-7 text-[#969696]" />
              <div>
                <p className="text-sm font-medium text-[#E8E8E8]">{primaryTitle}</p>
                <p className="mt-1 text-xs text-[#969696]">
                  Nenhuma sessão PTY ativa para este painel.
                </p>
              </div>
              <button
                type="button"
                disabled={launchingSlot === 'primary'}
                onClick={() => void handleLaunchSlot('primary')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-60"
              >
                <Play aria-hidden="true" className="h-3.5 w-3.5" />
                <span>
                  {launchingSlot === 'primary' ? 'Abrindo sessão...' : `Iniciar ${primaryTitle}`}
                </span>
              </button>
            </div>
          )}
        </div>

        <div
          data-testid="terminal-slot-secondary"
          className={showSecondary ? 'flex min-h-0 flex-col' : 'hidden'}
        >
          {activeSecondary ? (
            <TerminalPane
              session={activeSecondary}
              title={secondaryTitle}
              client={client}
              token={token}
              transportPreference={transportPreference}
              webSocketFactory={webSocketFactory}
              terminalAdapterFactory={terminalAdapterFactory}
              compact={mode === 'split'}
              onSessionChange={(updated) => {
                setSecondarySession(updated);
                onSessionChange?.('secondary', updated);
              }}
              onClosed={(closedSession, keepRunning) => {
                if (!keepRunning) {
                  setSecondarySession(closedSession);
                }
                onSessionClosed?.('secondary', closedSession, keepRunning);
              }}
            />
          ) : (
            <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[#303030] bg-[#202020] p-6 text-center">
              <Terminal aria-hidden="true" className="h-7 w-7 text-[#969696]" />
              <div>
                <p className="text-sm font-medium text-[#E8E8E8]">{secondaryTitle}</p>
                <p className="mt-1 text-xs text-[#969696]">
                  Nenhuma sessão PTY ativa para este painel.
                </p>
              </div>
              <button
                type="button"
                disabled={launchingSlot === 'secondary'}
                onClick={() => void handleLaunchSlot('secondary')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-60"
              >
                <Play aria-hidden="true" className="h-3.5 w-3.5" />
                <span>
                  {launchingSlot === 'secondary'
                    ? 'Abrindo sessão...'
                    : `Iniciar ${secondaryTitle}`}
                </span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
