import { KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  FileText,
  FolderGit2,
  GitBranch,
  Layers,
  Loader2,
  MessageSquare,
  Play,
  Search,
  Server,
  Terminal,
  X,
} from 'lucide-react';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  QUICK_OPEN_KIND_LABELS,
  QUICK_OPEN_SCOPES,
  QUICK_OPEN_TAB_HINT_LABELS,
  QuickOpenItemKind,
  QuickOpenScope,
  QuickOpenSearchItem,
  QuickOpenTabHint,
  searchControlPlane,
} from './quickOpenApi';

export interface QuickOpenDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectItem: (item: QuickOpenSearchItem) => void;
  hostId?: string;
  limit?: number;
  debounceMs?: number;
  initialQuery?: string;
  client?: ControlPlaneClient;
}

function ResultIcon({
  kind,
  tabHint,
}: {
  kind: QuickOpenItemKind;
  tabHint: QuickOpenTabHint;
}) {
  switch (kind) {
    case 'area':
      return <Layers aria-hidden="true" className="h-4 w-4 shrink-0 text-[#969696]" />;
    case 'workspace':
      return <GitBranch aria-hidden="true" className="h-4 w-4 shrink-0 text-[#969696]" />;
    case 'project':
      return <FolderGit2 aria-hidden="true" className="h-4 w-4 shrink-0 text-[#E8E8E8]" />;
    case 'run':
      return <Play aria-hidden="true" className="h-4 w-4 shrink-0 text-[#93C5FD]" />;
    case 'session':
      return tabHint === 'terminal' ? (
        <Terminal aria-hidden="true" className="h-4 w-4 shrink-0 text-[#4ADE80]" />
      ) : (
        <MessageSquare aria-hidden="true" className="h-4 w-4 shrink-0 text-[#E8E8E8]" />
      );
    case 'artifact':
      return <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-[#FCD34D]" />;
  }
}

function formatErrorMessage(err: unknown): string {
  if (err instanceof ControlPlaneApiError) {
    return err.payload.message;
  }
  if (err instanceof Error && err.message.trim().length > 0) {
    return err.message;
  }
  return 'Falha ao consultar o índice de busca global.';
}

export function QuickOpenDialog({
  open,
  onOpenChange,
  onSelectItem,
  hostId = 'local',
  limit = 25,
  debounceMs = 150,
  initialQuery = '',
  client,
}: QuickOpenDialogProps) {
  const defaultClient = useControlPlaneClient();
  const activeClient = client ?? defaultClient;

  const baseId = useId();
  const listboxId = `${baseId}-listbox`;
  const inputRef = useRef<HTMLInputElement>(null);
  const optionRefs = useRef<Array<HTMLDivElement | null>>([]);
  const abortRef = useRef<AbortController | null>(null);

  const [query, setQuery] = useState(initialQuery);
  const [scope, setScope] = useState<QuickOpenScope>('all');
  const [items, setItems] = useState<QuickOpenSearchItem[]>([]);
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [retrySeq, setRetrySeq] = useState(0);

  const getOptionId = useCallback(
    (index: number) => `${baseId}-option-${index}`,
    [baseId],
  );

  // Reset transient state cleanly when dialog opens or closes.
  useEffect(() => {
    if (open) {
      setQuery(initialQuery);
      setErrorMessage(null);
    } else {
      abortRef.current?.abort();
      abortRef.current = null;
      setItems([]);
      setActiveIndex(-1);
      setIsLoading(false);
      setErrorMessage(null);
    }
  }, [open, initialQuery]);

  // Debounced search query execution with request cancellation.
  useEffect(() => {
    if (!open) {
      return;
    }

    const trimmed = query.trim();
    if (trimmed.length === 0) {
      abortRef.current?.abort();
      abortRef.current = null;
      setItems([]);
      setActiveIndex(-1);
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const res = await searchControlPlane(
          activeClient,
          { query: trimmed, scope, hostId, limit },
          { signal: controller.signal },
        );
        if (cancelled || controller.signal.aborted) {
          return;
        }
        setItems(res.items);
        setActiveIndex(res.items.length > 0 ? 0 : -1);
      } catch (err) {
        if (
          cancelled ||
          controller.signal.aborted ||
          (err instanceof Error && err.name === 'AbortError')
        ) {
          return;
        }
        setItems([]);
        setActiveIndex(-1);
        setErrorMessage(formatErrorMessage(err));
      } finally {
        if (!cancelled && !controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }, debounceMs);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query, scope, hostId, limit, debounceMs, activeClient, retrySeq]);

  useEffect(() => {
    if (activeIndex < 0) {
      return;
    }
    const target = optionRefs.current[activeIndex];
    target?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex]);

  const handleSelect = useCallback(
    (item: QuickOpenSearchItem) => {
      onSelectItem(item);
      onOpenChange(false);
    },
    [onSelectItem, onOpenChange],
  );

  const handleComboboxKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onOpenChange(false);
      return;
    }

    if (items.length === 0) {
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((prev) => (prev < 0 ? 0 : (prev + 1) % items.length));
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? items.length - 1 : prev - 1));
      return;
    }

    if (event.key === 'Home') {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }

    if (event.key === 'End') {
      event.preventDefault();
      setActiveIndex(items.length - 1);
      return;
    }

    if (event.key === 'Enter' && activeIndex >= 0 && items[activeIndex]) {
      event.preventDefault();
      handleSelect(items[activeIndex]);
    }
  };

  const handleScopeKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      const next = QUICK_OPEN_SCOPES[(index + 1) % QUICK_OPEN_SCOPES.length];
      if (next) {
        setScope(next.id);
      }
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      const prev =
        QUICK_OPEN_SCOPES[(index - 1 + QUICK_OPEN_SCOPES.length) % QUICK_OPEN_SCOPES.length];
      if (prev) {
        setScope(prev.id);
      }
    }
  };

  const activeDescendantId =
    activeIndex >= 0 && items[activeIndex] ? getOptionId(activeIndex) : undefined;
  const hasQuery = query.trim().length > 0;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/75 backdrop-blur-[1px]" />
        <Dialog.Content
          data-testid="quickopen-dialog"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            inputRef.current?.focus();
          }}
          className="fixed left-1/2 top-[12%] z-50 w-[min(92vw,680px)] -translate-x-1/2 overflow-hidden rounded-2xl border border-[#303030] bg-[#1C1C1C] text-[#E8E8E8] shadow-2xl focus:outline-none"
        >
          <div className="flex items-center justify-between gap-3 border-b border-[#303030] bg-[#181818] px-4 py-2.5">
            <div className="flex items-center gap-2">
              <Dialog.Title className="text-xs font-semibold uppercase tracking-wider text-[#E8E8E8]">
                Busca global (QuickOpen)
              </Dialog.Title>
              <span className="inline-flex items-center gap-1 rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]">
                <Server aria-hidden="true" className="h-3 w-3" />
                <span>{hostId}</span>
              </span>
            </div>

            <Dialog.Description className="sr-only">
              Pesquise áreas, workspaces, projetos, runs, sessões e artefatos sem alterar rascunhos
              ou abas abertas.
            </Dialog.Description>

            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Fechar busca global"
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-transparent text-[#969696] transition-colors hover:border-[#303030] hover:bg-[#282828] hover:text-[#E8E8E8]"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="border-b border-[#303030] bg-[#141414] px-4 py-3">
            <div className="relative flex items-center">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 h-4 w-4 text-[#969696]"
              />
              <input
                ref={inputRef}
                type="text"
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={true}
                aria-controls={listboxId}
                aria-activedescendant={activeDescendantId}
                aria-label="Buscar no Control Plane"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleComboboxKeyDown}
                placeholder="Buscar áreas, workspaces, projetos, runs, sessões ou artefatos..."
                autoComplete="off"
                spellCheck={false}
                className="w-full rounded-xl border border-[#303030] bg-[#202020] py-2.5 pl-10 pr-10 text-sm text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
              />
              {isLoading ? (
                <Loader2
                  aria-label="Buscando..."
                  className="absolute right-3 h-4 w-4 animate-spin text-[#969696]"
                />
              ) : query.length > 0 ? (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    inputRef.current?.focus();
                  }}
                  aria-label="Limpar busca"
                  className="absolute right-2.5 rounded p-1 text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]"
                >
                  <X aria-hidden="true" className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>

            <div
              role="tablist"
              aria-label="Filtrar escopo da busca"
              className="mt-2.5 flex flex-wrap items-center gap-1"
            >
              {QUICK_OPEN_SCOPES.map((tab, idx) => {
                const selected = scope === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    onClick={() => {
                      setScope(tab.id);
                      inputRef.current?.focus();
                    }}
                    onKeyDown={(event) => handleScopeKeyDown(event, idx)}
                    className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
                      selected
                        ? 'border-[#E8E8E8]/50 bg-[#E8E8E8] text-[#181818]'
                        : 'border-[#303030] bg-[#202020] text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
                    }`}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="max-h-[340px] overflow-y-auto bg-[#141414] p-2">
            {errorMessage ? (
              <div
                role="alert"
                className="m-2 flex items-center justify-between gap-3 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2.5 text-xs text-[#FCA5A5]"
              >
                <span>{errorMessage}</span>
                <button
                  type="button"
                  onClick={() => setRetrySeq((prev) => prev + 1)}
                  className="shrink-0 rounded-md border border-[#EF4444]/40 bg-[#202020] px-2.5 py-1 text-xs font-medium text-[#E8E8E8] hover:bg-[#282828]"
                >
                  Tentar novamente
                </button>
              </div>
            ) : null}

            <div
              id={listboxId}
              role="listbox"
              aria-label="Resultados da busca"
              className="space-y-1"
            >
              {items.map((item, index) => {
                const isActive = index === activeIndex;
                return (
                  <div
                    key={`${item.kind}:${item.id}`}
                    id={getOptionId(index)}
                    ref={(el) => {
                      optionRefs.current[index] = el;
                    }}
                    role="option"
                    aria-selected={isActive}
                    data-active={isActive ? 'true' : 'false'}
                    onClick={() => handleSelect(item)}
                    onMouseEnter={() => setActiveIndex(index)}
                    className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                      isActive
                        ? 'border-[#3B82F6]/60 bg-[#282828] text-[#E8E8E8]'
                        : 'border-transparent bg-[#1C1C1C]/60 text-[#E8E8E8] hover:bg-[#202020]'
                    }`}
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <ResultIcon kind={item.kind} tabHint={item.tab_hint} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-[#E8E8E8]">
                          {item.title}
                        </div>
                        {item.subtitle ? (
                          <div className="truncate text-xs text-[#969696]">
                            {item.subtitle}
                          </div>
                        ) : null}
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      <span className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 text-[11px] text-[#E8E8E8]">
                        {QUICK_OPEN_KIND_LABELS[item.kind]}
                      </span>
                      <span className="rounded border border-[#303030] bg-[#181818] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]">
                        {item.host_id}
                      </span>
                      <span className="hidden rounded border border-[#303030] bg-[#181818] px-1.5 py-0.5 text-[11px] text-[#969696] sm:inline">
                        {QUICK_OPEN_TAB_HINT_LABELS[item.tab_hint]}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {!errorMessage && !isLoading && items.length === 0 ? (
              <div
                role="status"
                className="px-4 py-8 text-center text-xs text-[#969696]"
              >
                {hasQuery
                  ? `Nenhum resultado encontrado para "${query.trim()}" neste escopo.`
                  : 'Digite para buscar áreas, workspaces, projetos, runs, sessões ou artefatos.'}
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#303030] bg-[#181818] px-4 py-2 text-[11px] text-[#969696]">
            <div className="flex flex-wrap items-center gap-3">
              <span>
                <kbd className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[#E8E8E8]">
                  ↑↓
                </kbd>{' '}
                navegar
              </span>
              <span>
                <kbd className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[#E8E8E8]">
                  Home/End
                </kbd>{' '}
                início/fim
              </span>
              <span>
                <kbd className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[#E8E8E8]">
                  Enter
                </kbd>{' '}
                abrir
              </span>
              <span>
                <kbd className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[#E8E8E8]">
                  Esc
                </kbd>{' '}
                fechar
              </span>
            </div>
            <span className="font-mono">
              {items.length > 0 ? `${items.length} resultado(s)` : 'Ctrl+K'}
            </span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
