import {
  Blocks,
  Clock,
  FolderGit2,
  Gauge,
  LogOut,
  MessageSquarePlus,
  PanelLeft,
  Search,
  Settings,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { TabKind, useLayoutStore } from '@/store/layoutStore';

interface RailNavItem {
  id: string;
  label: string;
  route: string;
  kind: TabKind;
  Icon: typeof MessageSquarePlus;
}

const RAIL_NAV_ITEMS: RailNavItem[] = [
  { id: 'tab:new-chat', label: 'Novo chat', route: '/', kind: 'new_chat', Icon: MessageSquarePlus },
  { id: 'tab:workspaces', label: 'Workspaces', route: '/workspace', kind: 'workspace', Icon: FolderGit2 },
  { id: 'tab:resources', label: 'Recursos', route: '/recursos', kind: 'resources', Icon: Blocks },
  { id: 'tab:automations', label: 'Automações', route: '/automacoes', kind: 'automations', Icon: Clock },
  { id: 'tab:usage', label: 'Contas e consumo', route: '/consumo', kind: 'usage', Icon: Gauge },
  { id: 'tab:search', label: 'Busca global', route: '/busca', kind: 'search', Icon: Search },
];

export interface AppRailProps {
  activeRoute: string;
  onNavigate: (item: { id: string; label: string; route: string; kind: TabKind }) => void;
}

export function AppRail({ activeRoute, onNavigate }: AppRailProps) {
  const logout = useAuthStore((s) => s.logout);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const setMobileDrawerOpen = useLayoutStore((s) => s.setMobileDrawerOpen);
  const mobileDrawerOpen = useLayoutStore((s) => s.mobileDrawerOpen);

  return (
    <nav
      aria-label="Navegação principal"
      data-testid="app-rail"
      className="flex h-full w-14 shrink-0 flex-col items-center justify-between border-r border-[#303030] bg-[#181818] py-3"
    >
      <div className="flex flex-col items-center gap-2">
        <div
          aria-label="Hydra"
          title="Hydra Control Plane"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#303030] bg-[#202020] text-[#E8E8E8]"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <path d="M4 5v10M16 5v10M4 10h12M10 5v10" strokeLinecap="round" />
          </svg>
        </div>

        <button
          type="button"
          onClick={() => {
            if (typeof window !== 'undefined' && window.innerWidth < 768) {
              setMobileDrawerOpen(!mobileDrawerOpen);
            } else {
              toggleSidebar();
            }
          }}
          aria-label={sidebarCollapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'}
          title="Alternar barra lateral (Ctrl+B)"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#E8E8E8]"
        >
          <PanelLeft aria-hidden="true" className="h-4 w-4" />
        </button>

        <div className="my-1 h-px w-6 bg-[#303030]" role="separator" />

        {RAIL_NAV_ITEMS.map((item) => {
          const isActive = activeRoute === item.route;
          const Icon = item.Icon;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item)}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
              title={item.label}
              className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
                isActive
                  ? 'bg-[#282828] text-[#E8E8E8]'
                  : 'text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
              }`}
            >
              <Icon aria-hidden="true" className="h-4 w-4" />
            </button>
          );
        })}
      </div>

      <div className="flex flex-col items-center gap-2">
        <button
          type="button"
          onClick={() =>
            onNavigate({
              id: 'tab:settings',
              label: 'Configurações e perfil',
              route: '/configuracoes',
              kind: 'settings',
            })
          }
          aria-label="Configurações e perfil"
          aria-current={activeRoute === '/configuracoes' ? 'page' : undefined}
          title="Configurações e perfil"
          className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
            activeRoute === '/configuracoes'
              ? 'bg-[#282828] text-[#E8E8E8]'
              : 'text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
          }`}
        >
          <Settings aria-hidden="true" className="h-4 w-4" />
        </button>

        <button
          type="button"
          onClick={logout}
          aria-label="Bloquear sessão e sair"
          title="Sair / Bloquear sessão"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#FCA5A5]"
        >
          <LogOut aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
    </nav>
  );
}
