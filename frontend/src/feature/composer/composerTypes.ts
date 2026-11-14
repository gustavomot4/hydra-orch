import { ReactNode } from 'react';

export type OrchestrationMode = 'relay' | 'swarm' | 'persistent';

export const ORCHESTRATION_MODE_LABELS: Record<OrchestrationMode, string> = {
  relay: 'Em sequência (Relay)',
  swarm: 'Em paralelo (Swarm)',
  persistent: 'Persistente',
};

export type MentionKind = 'file' | 'workspace' | 'agent';

export interface MentionItem {
  id: string;
  label: string;
  kind: MentionKind;
  insertText?: string;
  description?: string;
}

export type SlashCommandName = '/review' | '/terminal' | '/swarm' | '/status' | '/limpar';

export interface SlashCommandItem {
  command: SlashCommandName;
  label: string;
  description: string;
}

export const SLASH_COMMANDS: SlashCommandItem[] = [
  {
    command: '/review',
    label: 'Revisão e checks',
    description: 'Solicitar análise de diff, checks canônicos e revisão da tarefa.',
  },
  {
    command: '/terminal',
    label: 'Terminal PTY',
    description: 'Abrir ou vincular sessão interativa de terminal no workspace.',
  },
  {
    command: '/swarm',
    label: 'Modo Swarm',
    description: 'Alternar orquestração para execução paralela por worktree.',
  },
  {
    command: '/status',
    label: 'Status do run',
    description: 'Consultar estado atual dos workers, orçamento e verificações.',
  },
  {
    command: '/limpar',
    label: 'Limpar rascunho',
    description: 'Limpar o texto não enviado desta sessão.',
  },
];

export const DEFAULT_MENTION_ITEMS: MentionItem[] = [
  {
    id: 'agent:coordenador',
    label: 'coordenador',
    kind: 'agent',
    insertText: 'coordenador',
    description: 'Agente coordenador principal',
  },
  {
    id: 'agent:codex',
    label: 'codex',
    kind: 'agent',
    insertText: 'codex',
    description: 'Executor Codex CLI',
  },
  {
    id: 'agent:claude',
    label: 'claude',
    kind: 'agent',
    insertText: 'claude',
    description: 'Executor Claude Code CLI',
  },
  {
    id: 'workspace:principal',
    label: 'workspace-principal',
    kind: 'workspace',
    insertText: 'workspace-principal',
    description: 'Worktree ativo do projeto selecionado',
  },
  {
    id: 'file:src/hydra_orch/server.py',
    label: 'src/hydra_orch/server.py',
    kind: 'file',
    insertText: 'src/hydra_orch/server.py',
    description: 'Servidor FastAPI Control Plane',
  },
  {
    id: 'file:frontend/src/App.tsx',
    label: 'frontend/src/App.tsx',
    kind: 'file',
    insertText: 'frontend/src/App.tsx',
    description: 'Shell principal da interface web',
  },
];

const COMPOSER_DRAFTS_STORAGE_KEY = 'hydra_composer_drafts_v1';
const memoryDraftFallback = new Map<string, string>();

export function loadAllComposerDrafts(): Record<string, string> {
  if (typeof window === 'undefined') {
    return Object.fromEntries(memoryDraftFallback.entries());
  }
  try {
    const raw = window.sessionStorage.getItem(COMPOSER_DRAFTS_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    const clean: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === 'string') {
        clean[k] = v;
      }
    }
    return clean;
  } catch {
    return Object.fromEntries(memoryDraftFallback.entries());
  }
}

export function loadComposerDraft(sessionKey: string): string {
  const key = sessionKey.trim() || 'default';
  if (typeof window === 'undefined') {
    return memoryDraftFallback.get(key) ?? '';
  }
  const all = loadAllComposerDrafts();
  return all[key] ?? '';
}

export function saveComposerDraft(sessionKey: string, value: string): void {
  const key = sessionKey.trim() || 'default';
  memoryDraftFallback.set(key, value);
  if (typeof window === 'undefined') {
    return;
  }
  try {
    const all = loadAllComposerDrafts();
    if (value.length === 0) {
      delete all[key];
    } else {
      all[key] = value;
    }
    window.sessionStorage.setItem(COMPOSER_DRAFTS_STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Fallback em memória já atualizado
  }
}

export function clearComposerDraft(sessionKey: string): void {
  saveComposerDraft(sessionKey, '');
}

export interface ComposerTriggerMatch {
  kind: 'mention' | 'slash';
  query: string;
  startIndex: number;
  endIndex: number;
}

export function detectComposerTrigger(
  text: string,
  cursorPos: number,
): ComposerTriggerMatch | null {
  const safeCursor = Math.max(0, Math.min(cursorPos, text.length));
  const before = text.slice(0, safeCursor);

  const slashMatch = before.match(/(?:^|\s)(\/[^\s]*)$/);
  if (slashMatch) {
    const token = slashMatch[1];
    return {
      kind: 'slash',
      query: token.slice(1),
      startIndex: safeCursor - token.length,
      endIndex: safeCursor,
    };
  }

  const mentionMatch = before.match(/(?:^|\s)(@[^\s]*)$/);
  if (mentionMatch) {
    const token = mentionMatch[1];
    return {
      kind: 'mention',
      query: token.slice(1),
      startIndex: safeCursor - token.length,
      endIndex: safeCursor,
    };
  }

  return null;
}

export function replaceTriggerToken(
  text: string,
  startIndex: number,
  endIndex: number,
  replacement: string,
): { nextText: string; nextCursor: number } {
  const prefix = text.slice(0, startIndex);
  const suffix = text.slice(endIndex);
  const needsTrailingSpace = suffix.length === 0 || !suffix.startsWith(' ');
  const inserted = needsTrailingSpace ? `${replacement} ` : replacement;
  const nextText = `${prefix}${inserted}${suffix}`;
  return {
    nextText,
    nextCursor: prefix.length + inserted.length,
  };
}

export interface PromptComposerProps {
  draft?: string;
  onDraftChange?: (value: string) => void;
  mode?: OrchestrationMode;
  onModeChange?: (mode: OrchestrationMode) => void;
  selectedProjectId?: string;
  onSubmit?: (submittedText?: string) => void;
  isSubmitting?: boolean;
  sessionKey?: string;
  placeholder?: string;
  submitLabel?: string;
  submitDisabled?: boolean;
  disabled?: boolean;
  hideModeSelector?: boolean;
  mentionItems?: MentionItem[];
  slashCommands?: SlashCommandItem[];
  onSlashCommand?: (command: SlashCommandItem) => boolean | void;
  renderAttachControl?: ReactNode;
  renderDictationControl?: ReactNode;
  attachmentChips?: ReactNode;
  textareaAriaLabel?: string;
  visibleTextareaLabel?: boolean;
  className?: string;
}
