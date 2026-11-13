import { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, useEffect, useState } from 'react';
import { Clock, ListTodo, MessageSquarePlus, Search, X } from 'lucide-react';
import { UsageBar } from '@/component/UsageBar';
import { WorkspaceTree } from '@/component/WorkspaceTree';
import { useWorkspaceHierarchy, WorkspaceTreeNode } from '@/hook/useWorkspaceHierarchy';
import {
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  TabKind,
  useLayoutStore,
} from '@/store/layoutStore';

export interface SidebarProps {
  searchInputRef?: React.RefObject<HTMLInputElement>;
  onOpenRoute: (item: { id: string; label: string; route: string; kind: TabKind }) => void;
  onSelectTreeNode: (node: WorkspaceTreeNode) => void;
}

export function Sidebar({
  searchInputRef,
  onOpenRoute,
  onSelectTreeNode,
}: SidebarProps) {
  const sidebarWidth = useLayoutStore((s) => s.sidebarWidth);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const mobileDrawerOpen = useLayoutStore((s) => s.mobileDrawerOpen);
  const setSidebarWidth = useLayoutStore((s) => s.setSidebarWidth);
  const setMobileDrawerOpen = useLayoutStore((s) => s.setMobileDrawerOpen);

  const [filterQuery, setFilterQuery] = useState('');
  const { tree, isLoading } = useWorkspaceHierarchy();

  useEffect(() => {
    if (!mobileDrawerOpen) {
      return;
    }
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileDrawerOpen(false);
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [mobileDrawerOpen, setMobileDrawerOpen]);

  const handleResizePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarWidth;

    const handleMove = (moveEvt: PointerEvent) => {
      const delta = moveEvt.clientX - startX;
      setSidebarWidth(startWidth + delta);
    };

    const handleUp = () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
  };

  const handleResizeKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setSidebarWidth(sidebarWidth + 16);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setSidebarWidth(sidebarWidth - 16);
    }
  };

  const sidebarContent = (
    <div className="flex h-full flex-col bg-[#1C1C1C] text-[#E8E8E8]">
      <div className="space-y-2 border-b border-[#303030] p-3">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => {
              onOpenRoute({
                id: 'tab:new-chat',
                label: 'Novo chat',
                route: '/',
                kind: 'new_chat',
              });
              setMobileDrawerOpen(false);
            }}
            className="flex flex-1 items-center gap-2 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs font-medium text-[#E8E8E8] transition-colors hover:bg-[#282828]"
          >
            <MessageSquarePlus aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Novo chat</span>
          </button>

          {mobileDrawerOpen ? (
            <button
              type="button"
              onClick={() => setMobileDrawerOpen(false)}
              aria-label="Fechar menu lateral"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#303030] bg-[#202020] text-[#969696] hover:text-[#E8E8E8] md:hidden"
            >
              <X aria-hidden="true" className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        <div className="relative flex items-center">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-[#969696]"
          />
          <input
            ref={searchInputRef}
            id="sidebar-tree-filter"
            type="search"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="Filtrar projetos e sessões..."
            aria-label="Filtrar projetos e sessões"
            className="w-full rounded-lg border border-[#303030] bg-[#141414] py-1.5 pl-8 pr-2 text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>
      </div>

      <div className="space-y-1 border-b border-[#303030] px-2 py-2">
        <button
          type="button"
          onClick={() => {
            onOpenRoute({
              id: 'tab:workspaces',
              label: 'Tarefas e workspaces',
              route: '/workspace',
              kind: 'workspace',
            });
            setMobileDrawerOpen(false);
          }}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#E8E8E8]"
        >
          <ListTodo aria-hidden="true" className="h-3.5 w-3.5" />
          <span>Tarefas e workspaces</span>
        </button>
        <button
          type="button"
          onClick={() => {
            onOpenRoute({
              id: 'tab:automations',
              label: 'Automações',
              route: '/automacoes',
              kind: 'automations',
            });
            setMobileDrawerOpen(false);
          }}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#E8E8E8]"
        >
          <Clock aria-hidden="true" className="h-3.5 w-3.5" />
          <span>Automações</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[#969696]">
          Projetos e sessões
        </div>
        {isLoading ? (
          <div className="px-3 py-3 text-xs text-[#969696]">Carregando hierarquia...</div>
        ) : (
          <WorkspaceTree
            nodes={tree}
            filterQuery={filterQuery}
            onSelectNode={(node) => {
              onSelectTreeNode(node);
              if (node.kind === 'session' || node.kind === 'workspace') {
                setMobileDrawerOpen(false);
              }
            }}
          />
        )}
      </div>

      <UsageBar
        onOpenUsageDetails={() => {
          onOpenRoute({
            id: 'tab:usage',
            label: 'Contas e consumo',
            route: '/consumo',
            kind: 'usage',
          });
          setMobileDrawerOpen(false);
        }}
      />
    </div>
  );

  return (
    <>
      {!sidebarCollapsed ? (
        <aside
          aria-label="Barra lateral de workspaces"
          data-testid="desktop-sidebar"
          style={{ width: `${sidebarWidth}px` }}
          className="relative hidden h-full shrink-0 border-r border-[#303030] md:block"
        >
          {sidebarContent}
          <div
            role="separator"
            aria-label="Redimensionar barra lateral"
            aria-orientation="vertical"
            aria-valuemin={MIN_SIDEBAR_WIDTH}
            aria-valuemax={MAX_SIDEBAR_WIDTH}
            aria-valuenow={sidebarWidth}
            tabIndex={0}
            data-testid="sidebar-resizer"
            onPointerDown={handleResizePointerDown}
            onKeyDown={handleResizeKeyDown}
            className="absolute bottom-0 right-0 top-0 w-1 cursor-col-resize bg-transparent transition-colors hover:bg-[#3B82F6]/60 focus:bg-[#3B82F6]"
          />
        </aside>
      ) : null}

      {mobileDrawerOpen ? (
        <div
          data-testid="mobile-sidebar-drawer"
          className="fixed inset-0 z-40 flex md:hidden"
        >
          <div
            aria-hidden="true"
            onClick={() => setMobileDrawerOpen(false)}
            className="fixed inset-0 bg-black/60"
          />
          <aside
            aria-label="Menu lateral móvel"
            className="relative z-50 h-full w-72 max-w-[85vw] border-r border-[#303030] bg-[#1C1C1C]"
          >
            {sidebarContent}
          </aside>
        </div>
      ) : null}
    </>
  );
}
