import { CSSProperties, Fragment, ReactNode } from 'react';
import { Columns2 } from 'lucide-react';
import { TabBar } from '@/component/TabBar';
import { PanelResizer } from '@/component/PanelResizer';
import { PaneId, useLayoutStore, WorkspaceTab } from '@/store/layoutStore';

export interface PaneLayoutProps {
  renderTabContent: (tab: WorkspaceTab | null, paneId: PaneId) => ReactNode;
  onSyncRoute?: (route: string) => void;
}

export function PaneLayout({ renderTabContent, onSyncRoute }: PaneLayoutProps) {
  const splitMode = useLayoutStore((s) => s.splitMode);
  const focusedPaneId = useLayoutStore((s) => s.focusedPaneId);
  const panes = useLayoutStore((s) => s.panes);
  const tabs = useLayoutStore((s) => s.tabs);
  const focusPane = useLayoutStore((s) => s.focusPane);
  const openTab = useLayoutStore((s) => s.openTab);
  const splitRatio = useLayoutStore((s) => s.splitRatio);
  const setAppearance = useLayoutStore((s) => s.setAppearance);

  const visiblePaneIds: PaneId[] = splitMode === 'split' ? ['primary', 'secondary'] : ['primary'];

  return (
    <div
      data-testid="pane-layout"
      data-split-mode={splitMode}
      style={
        {
          '--pane-columns': `${splitRatio}fr var(--divider-size) ${100 - splitRatio}fr`,
        } as CSSProperties
      }
      className="workbench-panes grid h-full min-h-0 flex-1 bg-[#141414]"
    >
      {visiblePaneIds.map((paneId) => {
        const pane = panes[paneId];
        const activeTab = pane.activeTabId ? (tabs[pane.activeTabId] ?? null) : null;
        const isFocused = focusedPaneId === paneId;

        return (
          <Fragment key={paneId}>
            <section
              key={paneId}
              aria-label={`Painel ${paneId === 'primary' ? 'principal' : 'secundário'}`}
              data-testid={`pane-${paneId}`}
              data-focused={isFocused ? 'true' : 'false'}
              onClick={() => focusPane(paneId)}
              className={`flex min-h-0 min-w-0 flex-col bg-[#141414] ${
                paneId === 'secondary' ? 'hidden border-l border-[#303030] md:flex' : 'flex'
              }`}
            >
              <TabBar paneId={paneId} onSyncRoute={onSyncRoute} />
              <div className="min-h-0 flex-1 overflow-y-auto">
                {activeTab ? (
                  renderTabContent(activeTab, paneId)
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
                    <Columns2 aria-hidden="true" className="h-8 w-8 text-[#969696]" />
                    <p className="text-sm font-medium text-[#E8E8E8]">Painel secundário vazio</p>
                    <p className="max-w-sm text-xs text-[#969696]">
                      Selecione uma sessão ou terminal na barra lateral para abrir lado a lado.
                    </p>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        openTab(
                          {
                            id: `tab:terminal:split-${Date.now()}`,
                            kind: 'terminal',
                            title: 'Terminal PTY',
                            route: '/terminal',
                            closable: true,
                          },
                          'secondary',
                        );
                      }}
                      className="rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs font-medium text-[#E8E8E8] hover:bg-[#282828]"
                    >
                      Abrir painel de terminal
                    </button>
                  </div>
                )}
              </div>
            </section>
            {paneId === 'primary' && splitMode === 'split' && (
              <PanelResizer
                label="Redimensionar painéis divididos"
                value={splitRatio}
                min={25}
                max={75}
                percent
                onChange={(splitRatio) => setAppearance({ splitRatio })}
                onReset={() => setAppearance({ splitRatio: 50 })}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
