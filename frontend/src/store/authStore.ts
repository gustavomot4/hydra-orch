import { create } from 'zustand';

const TOKEN_STORAGE_KEY = 'hydra_control_plane_token';

function readSessionToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
    return raw && raw.trim().length > 0 ? raw.trim() : null;
  } catch {
    return null;
  }
}

function writeSessionToken(token: string | null): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    if (token && token.trim().length > 0) {
      window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token.trim());
    } else {
      window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // Ignorar falha de armazenamento em ambientes restritos sem expor token
  }
}

export type AuthStatus = 'locked' | 'authenticating' | 'authenticated';

export interface AuthState {
  token: string | null;
  status: AuthStatus;
  principalId: string | null;
  authError: string | null;
  setAuthenticating: () => void;
  authenticate: (token: string, principalId?: string) => void;
  setAuthError: (message: string | null) => void;
  lock: (reason?: string) => void;
  logout: () => void;
}

const initialToken = readSessionToken();

export const useAuthStore = create<AuthState>((set) => ({
  token: initialToken,
  status: initialToken ? 'authenticated' : 'locked',
  principalId: initialToken ? 'operator' : null,
  authError: null,
  setAuthenticating: () => set({ status: 'authenticating', authError: null }),
  authenticate: (token: string, principalId = 'operator') => {
    const cleaned = token.trim();
    writeSessionToken(cleaned);
    set({
      token: cleaned,
      status: 'authenticated',
      principalId,
      authError: null,
    });
  },
  setAuthError: (message: string | null) =>
    set((state) => ({
      status: state.token ? 'authenticated' : 'locked',
      authError: message,
    })),
  lock: (reason?: string) => {
    writeSessionToken(null);
    set({
      token: null,
      status: 'locked',
      principalId: null,
      authError: reason ?? null,
    });
  },
  logout: () => {
    writeSessionToken(null);
    set({
      token: null,
      status: 'locked',
      principalId: null,
      authError: null,
    });
  },
}));
