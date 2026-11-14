import {
  Blocks,
  Clock,
  FolderGit2,
  Gauge,
  Lock,
  MessageSquarePlus,
  Monitor,
  PanelLeft,
  Search,
  Settings,
  Smartphone,
  Terminal,
} from 'lucide-react';
import { ReactNode, useEffect, useRef, useState } from 'react';
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
  { id: 'tab:search', label: 'Busca global', route: '/busca', kind: 'search', Icon: Search },
  {
    id: 'tab:workspaces',
    label: 'Workspaces',
    route: '/workspace',
    kind: 'workspace',
    Icon: FolderGit2,
  },
  { id: 'tab:terminal', label: 'Terminal', route: '/terminal', kind: 'terminal', Icon: Terminal },
  {
    id: 'tab:automations',
    label: 'Automações',
    route: '/automacoes',
    kind: 'automations',
    Icon: Clock,
  },
];

const TOOL_NAV_ITEMS: RailNavItem[] = [
  { id: 'tab:resources', label: 'Recursos', route: '/recursos', kind: 'resources', Icon: Blocks },
  { id: 'tab:usage', label: 'Contas e consumo', route: '/consumo', kind: 'usage', Icon: Gauge },
  {
    id: 'tab:device',
    label: 'Emulador móvel',
    route: '/dispositivos',
    kind: 'device',
    Icon: Smartphone,
  },
  {
    id: 'tab:computer-use',
    label: 'Controle do computador',
    route: '/computador',
    kind: 'computer_use',
    Icon: Monitor,
  },
];

export interface AppRailProps {
  activeRoute: string;
  onNavigate: (item: { id: string; label: string; route: string; kind: TabKind }) => void;
  onSearch: () => void;
  children?: ReactNode;
}

export function AppRail({ activeRoute, onNavigate, onSearch, children }: AppRailProps) {
  const logout = useAuthStore((s) => s.logout);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const setMobileDrawerOpen = useLayoutStore((s) => s.setMobileDrawerOpen);
  const mobileDrawerOpen = useLayoutStore((s) => s.mobileDrawerOpen);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 768,
  );

  useEffect(() => {
    const sync = () => {
      const isNarrow = window.innerWidth < 768;
      setNarrow(isNarrow);
      if (!isNarrow && useLayoutStore.getState().mobileDrawerOpen) setMobileDrawerOpen(false);
    };
    window.addEventListener('resize', sync);
    return () => window.removeEventListener('resize', sync);
  }, [setMobileDrawerOpen]);
  useEffect(() => {
    if (mobileDrawerOpen) toggleRef.current?.focus();
  }, [mobileDrawerOpen]);

  const expanded = narrow ? mobileDrawerOpen : !sidebarCollapsed;
  const closeDrawer = () => {
    setMobileDrawerOpen(false);
    toggleRef.current?.focus();
  };
  const buttonClass = (active: boolean) =>
    `flex min-h-9 w-full items-center gap-3 rounded-lg px-2 py-1 text-left text-sm focus-visible:outline-offset-0 [@media(pointer:coarse)]:min-h-[44px] ${
      expanded ? 'justify-start' : 'justify-center'
    } ${active ? 'bg-[#282828] font-semibold text-[#E8E8E8] ring-1 ring-inset ring-[var(--accent)]' : 'text-[#B4B4B4] hover:bg-[#282828] hover:text-[#E8E8E8]'}`;
  const renderNavItem = ({ id, label, route, kind, Icon }: RailNavItem) => {
    const active = activeRoute === route;
    return (
      <button
        key={id}
        type="button"
        onClick={() => {
          if (mobileDrawerOpen) closeDrawer();
          if (kind === 'search') onSearch();
          else onNavigate({ id, label, route, kind });
        }}
        aria-label={label}
        aria-current={active ? 'page' : undefined}
        title={label}
        className={buttonClass(active)}
      >
        <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
        {expanded ? <span>{label}</span> : null}
        {expanded && kind === 'search' ? (
          <kbd className="ml-auto hidden text-xs md:inline">Ctrl+K</kbd>
        ) : null}
      </button>
    );
  };

  return (
    <nav
      aria-label="Navegação principal"
      data-testid="app-rail"
      onKeyDown={(event) => {
        if (!mobileDrawerOpen || event.defaultPrevented) return;
        if (event.key === 'Escape') {
          event.preventDefault();
          closeDrawer();
        }
        if (event.key !== 'Tab') return;
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'button:not([disabled]):not([tabindex="-1"]), input:not([disabled]), [tabindex="0"]',
          ),
        ).filter((control) => control.getClientRects().length > 0);
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && event.target === first && last) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && event.target === last && first) {
          event.preventDefault();
          first.focus();
        }
      }}
      className={`flex h-full flex-col bg-[#1C1C1C] ${
        mobileDrawerOpen
          ? 'fixed inset-y-0 left-0 z-50 w-80 max-w-[85vw] border-r border-[#303030] md:static md:w-auto md:max-w-none'
          : ''
      }`}
    >
      <div
        id="hydra-sidebar-destinos"
        role={mobileDrawerOpen ? 'dialog' : undefined}
        aria-modal={mobileDrawerOpen ? true : undefined}
        aria-label={mobileDrawerOpen ? 'Menu lateral' : undefined}
        data-testid={mobileDrawerOpen ? 'mobile-sidebar-drawer' : undefined}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div
          className={`flex items-center gap-2 px-2 pt-2 ${expanded ? 'justify-between' : 'flex-col'}`}
        >
          <div
            role="img"
            aria-label="Hydra"
            className="flex min-h-9 items-center gap-2 px-2 text-[#E8E8E8]"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 20 20"
              className="h-4 w-4 shrink-0"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
            >
              <path d="M4 5v10M16 5v10M4 10h12M10 5v10" strokeLinecap="round" />
            </svg>
            {expanded ? <span className="font-semibold">Hydra</span> : null}
          </div>

          <button
            ref={toggleRef}
            type="button"
            onClick={() => {
              if (!narrow) toggleSidebar();
              else if (mobileDrawerOpen) closeDrawer();
              else setMobileDrawerOpen(true);
            }}
            aria-expanded={expanded}
            aria-controls="hydra-sidebar-destinos"
            aria-label={expanded ? 'Recolher barra lateral' : 'Expandir barra lateral'}
            title="Alternar barra lateral (Ctrl+B)"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[#B4B4B4] hover:bg-[#282828] hover:text-[#E8E8E8]"
          >
            <PanelLeft aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
          <div className="pb-2 pt-2">{RAIL_NAV_ITEMS.map(renderNavItem)}</div>

          {expanded ? children : null}

          <div className="mt-auto border-t border-[#303030] pt-2">
            {TOOL_NAV_ITEMS.map(renderNavItem)}
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
              className={buttonClass(activeRoute === '/configuracoes')}
            >
              <Settings aria-hidden="true" className="h-4 w-4 shrink-0" />
              {expanded ? <span>Configurações e perfil</span> : null}
            </button>

            <button
              type="button"
              onClick={logout}
            aria-label="Bloquear sessão e sair"
            title="Bloquear sessão e sair"
              className={buttonClass(false)}
            >
              <Lock aria-hidden="true" className="h-4 w-4 shrink-0" />
            {expanded ? <span>Bloquear sessão</span> : null}
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
