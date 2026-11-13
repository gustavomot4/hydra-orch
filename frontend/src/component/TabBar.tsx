import { KeyboardEvent } from 'react';
import { Columns2, Plus, Square, X } from 'lucide-react';
import { PaneId, useLayoutStore } from '@/store/layoutStore';

export interface TabBarProps {
  paneId: PaneId;
  onSyncRoute?: (route: string) => void;
}

export function TabBar({ paneId, onSyncRoute }: TabBarProps) {
  const pane = useLayoutStore((s) => s.panes[paneId]);
  const tabs = useLayoutStore((s) => s.tabs);
  const splitMode = useLayoutStore((s) => s.splitMode);
  const focusedPaneId = useLayoutStore((s) => s.focusedPaneId);
  const activateTab = useLayoutStore((s) => s.activateTab);
  const closeTab = useLayoutStore((s) => s.closeTab);
  const openTab = useLayoutStore((s) => s.openTab);
  const toggleSplitMode = useLayoutStore((s) => s.toggleSplitMode);

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      const nextId = pane.tabIds[(index + 1) % pane.tabIds.length];
      if (nextId) {
        activateTab(nextId, paneId);
        onSyncRoute?.(tabs[nextId]?.route ?? '/');
      }
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      const prevId = pane.tabIds[(index - 1 + pane.tabIds.length) % pane.tabIds.length];
      if (prevId) {
        activateTab(prevId, paneId);
        onSyncRoute?.(tabs[prevId]?.route ?? '/');
      }
    }
  };

  return (
    <div
      data-testid={`tab-bar-${paneId}`}
      className={`flex h-10 items-center justify-between gap-2 border-b border-[#303030] bg-[#181818] px-2 ${
        splitMode === 'split' && focusedPaneId === paneId ? 'border-b-[#3B82F6]/60' : ''
      }`}
    >
      <div
        role="tablist"
        aria-label={`Abas do painel ${paneId === 'primary' ? 'principal' : 'secundário'}`}
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
      >
        {pane.tabIds.map((tabId, idx) => {
          const tab = tabs[tabId];
          if (!tab) {
            return null;
          }
          const isActive = pane.activeTabId === tabId;
          return (
            <div
              key={tabId}
              className={`group flex max-w-[200px] items-center rounded-md border text-xs transition-colors ${
                isActive
                  ? 'border-[#303030] bg-[#202020] text-[#E8E8E8]'
                  : 'border-transparent text-[#969696] hover:bg-[#282828]/70 hover:text-[#E8E8E8]'
              }`}
            >
              <button
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => {
                  activateTab(tabId, paneId);
                  onSyncRoute?.(tab.route);
                }}
                onKeyDown={(e) => handleTabKeyDown(e, idx)}
                className="truncate px-2.5 py-1 text-left"
              >
                {tab.title}
              </button>
              {tab.closable !== false ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tabId, paneId);
                  }}
                  aria-label={`Fechar aba ${tab.title}`}
                  title="Fechar aba (não encerra processos em execução)"
                  className="mr-1 rounded p-0.5 text-[#969696] hover:bg-[#303030] hover:text-[#E8E8E8]"
                >
                  <X aria-hidden="true" className="h-3 w-3" />
                </button>
              ) : null}
            </div>
          );
        })}

        <button
          type="button"
          onClick={() => {
            openTab(
              {
                id: 'tab:new-chat',
                kind: 'new_chat',
                title: 'Novo chat',
                route: '/',
                closable: false,
              },
              paneId,
            );
            onSyncRoute?.('/');
          }}
          aria-label="Abrir novo chat neste painel"
          title="Novo chat"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]"
        >
          <Plus aria-hidden="true" className="h-3.5 w-3.5" />
        </button>
      </div>

      {paneId === 'primary' ? (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={toggleSplitMode}
            aria-label={splitMode === 'split' ? 'Voltar para painel único' : 'Dividir painéis'}
            aria-pressed={splitMode === 'split'}
            title="Alternar divisão de painéis (Alt+S)"
            className="flex h-7 items-center gap-1.5 rounded-md border border-[#303030] bg-[#202020] px-2 text-xs text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#E8E8E8]"
          >
            {splitMode === 'split' ? (
              <Square aria-hidden="true" className="h-3.5 w-3.5" />
            ) : (
              <Columns2 aria-hidden="true" className="h-3.5 w-3.5" />
            )}
            <span className="hidden sm:inline">
              {splitMode === 'split' ? 'Painel único' : 'Dividir'}
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
