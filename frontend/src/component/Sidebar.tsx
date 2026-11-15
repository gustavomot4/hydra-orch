import {
  ComponentProps,
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  useState,
} from 'react';
import { Search, FolderGit2 } from 'lucide-react';
import { AppRail } from '@/component/AppRail';
import { WorkspaceTree } from '@/component/WorkspaceTree';
import { ConversationHistory } from '@/feature/chat/ConversationHistory';
import { useWorkspaceHierarchy, WorkspaceTreeNode } from '@/hook/useWorkspaceHierarchy';
import { MAX_SIDEBAR_WIDTH, MIN_SIDEBAR_WIDTH, useLayoutStore } from '@/store/layoutStore';

export interface SidebarProps extends Omit<ComponentProps<typeof AppRail>, 'children'> {
  onSelectTreeNode: (node: WorkspaceTreeNode) => void;
}

export function Sidebar({ onSelectTreeNode, ...navigation }: SidebarProps) {
  const sidebarWidth = useLayoutStore((s) => s.sidebarWidth);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const mobileDrawerOpen = useLayoutStore((s) => s.mobileDrawerOpen);
  const setSidebarWidth = useLayoutStore((s) => s.setSidebarWidth);
  const setMobileDrawerOpen = useLayoutStore((s) => s.setMobileDrawerOpen);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);

  const [filterQuery, setFilterQuery] = useState('');
  const { tree, projects, isLoading } = useWorkspaceHierarchy();

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
      window.removeEventListener('pointercancel', handleUp);
    };

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp, { once: true });
    window.addEventListener('pointercancel', handleUp, { once: true });
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

  return (
    <aside
      aria-label="Barra lateral"
      data-testid="desktop-sidebar"
      style={{ '--sidebar-width': `min(${sidebarWidth}px, 40vw)` } as CSSProperties}
      className={`relative h-full shrink-0 border-r border-[#303030] ${
        sidebarCollapsed ? 'w-14' : 'w-14 md:w-[var(--sidebar-width)]'
      }`}
    >
      {mobileDrawerOpen ? (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setMobileDrawerOpen(false)}
        />
      ) : null}
      <AppRail {...navigation}>
        <section
          className="border-t border-[#303030] pb-2 pt-3"
          aria-labelledby="sidebar-projects-title"
        >
          <h2 id="sidebar-projects-title" className="px-2 text-sm font-semibold text-[#E8E8E8]">
            Seu trabalho
          </h2>
          <div className="relative mx-2 my-2 flex items-center">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-[#969696]"
            />
            <input
              id="sidebar-tree-filter"
              type="search"
              maxLength={100}
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              placeholder="Buscar pastas ou conversas"
              aria-label="Buscar pastas ou conversas"
              className="min-h-9 w-full rounded-lg border border-[#666] bg-[#141414] py-1.5 pl-8 pr-2 text-sm text-[#E8E8E8] placeholder:text-[#969696]"
            />
          </div>
          <ConversationHistory
            filter={filterQuery}
            onSelect={(node) => {
              onSelectTreeNode(node);
              setMobileDrawerOpen(false);
            }}
          />
          <h3 className="mt-3 px-2 text-sm font-semibold text-[#E8E8E8]">Pastas</h3>
          {isLoading ? (
            <div role="status" className="px-3 py-3 text-sm text-[#D1D1D1]">
              Carregando pastas…
            </div>
          ) : (
            <div className="mt-2 space-y-1">
              {projects
                .filter((p) => p.name.toLocaleLowerCase().includes(filterQuery.toLocaleLowerCase()))
                .map((project) => (
                  <button
                    key={project.id}
                    className={`flex min-h-11 w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-[#D1D1D1] ${selectedProjectId === project.id ? 'bg-[#282828] ring-1 ring-inset ring-[#666]' : ''}`}
                    onClick={() => {
                      onSelectTreeNode({
                        id: `project:${project.id}`,
                        kind: 'project',
                        label: project.name,
                        status: 'active',
                        hostId: 'local',
                        projectId: project.id,
                        workspaceId: project.workspace_id,
                        children: [],
                      });
                      setMobileDrawerOpen(false);
                    }}
                  >
                    <FolderGit2 size={16} aria-hidden="true" />
                    <span className="break-words">{project.name}</span>
                  </button>
                ))}
              {!projects.length && (
                <p className="px-2 py-2 text-sm text-[#D1D1D1]">Adicione uma pasta no Novo chat.</p>
              )}
            </div>
          )}
          <details className="mt-3 border-t border-[#303030] pt-2 text-sm text-[#D1D1D1]">
            <summary className="flex min-h-11 cursor-pointer items-center px-2">
              Estrutura técnica
            </summary>
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
          </details>
        </section>
      </AppRail>
      {!sidebarCollapsed ? (
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
          className="absolute bottom-0 -right-4 top-0 z-10 hidden w-8 cursor-col-resize bg-transparent focus:outline focus:outline-2 focus:outline-[#3B82F6] md:block"
        />
      ) : null}
    </aside>
  );
}
