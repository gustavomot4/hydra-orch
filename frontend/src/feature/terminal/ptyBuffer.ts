export const MAX_HEADLESS_CHARS = 250_000;
const PTY_CURSOR_STORAGE_PREFIX = 'hydra:pty-cursor:';

export interface PersistedPtyBufferEntry {
  lastSeq: number;
  buffer: string;
}

const ptyBufferCache = new Map<string, PersistedPtyBufferEntry>();

export function getPersistedPtyBuffer(sessionId: string): PersistedPtyBufferEntry | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(`${PTY_CURSOR_STORAGE_PREFIX}${sessionId}`);
    if (!raw) {
      ptyBufferCache.delete(sessionId);
      return null;
    }
    const parsed = JSON.parse(raw) as { lastSeq?: number };
    const seq = typeof parsed.lastSeq === 'number' && parsed.lastSeq >= 0 ? parsed.lastSeq : 0;
    const mem = ptyBufferCache.get(sessionId);
    if (mem && mem.lastSeq === seq) {
      return mem;
    }
    return null;
  } catch {
    return ptyBufferCache.get(sessionId) ?? null;
  }
}

export function setPersistedPtyBuffer(sessionId: string, lastSeq: number, buffer: string): void {
  const trimmed =
    buffer.length > MAX_HEADLESS_CHARS
      ? buffer.slice(buffer.length - MAX_HEADLESS_CHARS)
      : buffer;
  ptyBufferCache.set(sessionId, { lastSeq, buffer: trimmed });
  if (typeof window !== 'undefined') {
    try {
      window.sessionStorage.setItem(
        `${PTY_CURSOR_STORAGE_PREFIX}${sessionId}`,
        JSON.stringify({ lastSeq }),
      );
    } catch {
      // Ignora indisponibilidade de sessionStorage
    }
  }
}

export function clearPersistedPtyBuffer(sessionId?: string): void {
  if (sessionId) {
    ptyBufferCache.delete(sessionId);
    if (typeof window !== 'undefined') {
      try {
        window.sessionStorage.removeItem(`${PTY_CURSOR_STORAGE_PREFIX}${sessionId}`);
      } catch {
        // Ignora indisponibilidade de sessionStorage
      }
    }
    return;
  }
  ptyBufferCache.clear();
}
