import { useEffect, useMemo, useRef } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppRail } from '@/component/AppRail';
import { AuthGate } from '@/component/AuthGate';
import { PaneLayout } from '@/component/PaneLayout';
import { Sidebar } from '@/component/Sidebar';
import { createHydraQueryClient } from '@/hook/queryClient';
import { useBootstrap } from '@/hook/useBootstrap';
import { useKeyboardShortcuts } from '@/hook/useKeyboardShortcuts';
import { WorkspaceTreeNode } from '@/hook/useWorkspaceHierarchy';
import { ConfigPerfilPage } from '@/page/ConfigPerfilPage';
import { NovoChatPage } from '@/page/NovoChatPage';
import { PlaceholderFeaturePage } from '@/page/PlaceholderFeaturePage';
import { useAuthStore } from '@/store/authStore';
import { PaneId, TabKind, useLayoutStore, WorkspaceTab } from '@/store/layoutStore';

function renderTabPage(tab: WorkspaceTab | null, _paneId: PaneId) {
  if (!tab) {
    return null;
  }
  switch (tab.kind) {
    case 'new_chat':
      return <NovoChatPage />;
    case 'settings':
      return <ConfigPerfilPage />;
    case 'chat':
      return (
        <PlaceholderFeaturePage
          kind="chat"
          title={`Conversa · ${tab.title}`}
          targetWave="Onda 14 (T33)"
          targetModule="src/feature/chat/"
          description="Timeline SSE durável, deduplicação por seq, cards de workers e aprovação HITL inline serão conectados na Onda 14."
        />
      );
    case 'terminal':
      return (
        <PlaceholderFeaturePage
          kind="terminal"
          title={`Terminal PTY · ${tab.title}`}
          targetWave="Onda 14 (T34)"
          targetModule="src/feature/terminal/"
          description="Emulador @xterm/xterm conectado ao bridge PTY autenticado (/v1/control-plane/pty/sessions) com resize, interrupção e reconexão."
          capability="pty"
        />
      );
    case 'workspace':
      return (
        <PlaceholderFeaturePage
          kind="workspace"
          title="Workspaces e tarefas"
          targetWave="Onda 14 (T33 / T34)"
          targetModule="src/feature/conflict/"
          description="Gestão de áreas, worktrees Git, diffs lado a lado, resolução de conflitos e pacote de PR."
        />
      );
    case 'resources':
      return (
        <PlaceholderFeaturePage
          kind="resources"
          title="Recursos, skills e MCPs"
          targetWave="Onda 14 (T35)"
          targetModule="src/feature/shell/"
          description="Inventário de skills, servidores MCP, descoberta opt-in, extensões e políticas de consentimento."
        />
      );
    case 'automations':
      return (
        <PlaceholderFeaturePage
          kind="automations"
          title="Automações agendadas"
          targetWave="Onda 14 (T35)"
          targetModule="src/feature/shell/"
          description="Agendador durável com fuso horário, política de sobreposição e histórico vinculado a runs."
          capability="scheduler"
        />
      );
    case 'usage':
      return (
        <PlaceholderFeaturePage
          kind="usage"
          title="Contas e consumo"
          targetWave="Onda 14 (T33)"
          targetModule="src/feature/quota/"
          description="Janelas de cota de 5h por provedor, origem observada/desatualizada/desconhecida, horário de reset e troca explícita de conta para o próximo run."
        />
      );
    case 'search':
      return (
        <PlaceholderFeaturePage
          kind="search"
          title="Busca global (QuickOpen)"
          targetWave="Onda 15 (T38)"
          targetModule="src/feature/quickopen/"
          description="Paleta indexada (/v1/control-plane/search) com navegação por teclado entre hosts, projetos, runs, sessões e artefatos."
          capability="quickopen"
        />
      );
  }
}

export function HydraShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const searchInputRef = useRef<HTMLInputElement>(null);

  const token = useAuthStore((s) => s.token);
  const status = useAuthStore((s) => s.status);
  const density = useLayoutStore((s) => s.density);
  const reducedMotion = useLayoutStore((s) => s.reducedMotion);
  const openTab = useLayoutStore((s) => s.openTab);
  const setMobileDrawerOpen = useLayoutStore((s) => s.setMobileDrawerOpen);

  const bootstrapQuery = useBootstrap();

  useKeyboardShortcuts({
    enabled: Boolean(token) && status === 'authenticated',
    onFocusSearch: () => {
      searchInputRef.current?.focus();
    },
  });

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.density = density;
      document.documentElement.dataset.reducedMotion = reducedMotion ? 'true' : 'false';
    }
  }, [density, reducedMotion]);

  // Sync direct URL navigation into the active pane tab deterministically.
  useEffect(() => {
    const path = location.pathname;
    if (path === '/configuracoes') {
      openTab({
        id: 'tab:settings',
        kind: 'settings',
        title: 'Configurações e perfil',
        route: '/configuracoes',
        closable: true,
      });
    } else if (path === '/workspace') {
      openTab({
        id: 'tab:workspaces',
        kind: 'workspace',
        title: 'Workspaces',
        route: '/workspace',
        closable: true,
      });
    } else if (path === '/recursos') {
      openTab({
        id: 'tab:resources',
        kind: 'resources',
        title: 'Recursos',
        route: '/recursos',
        closable: true,
      });
    } else if (path === '/automacoes') {
      openTab({
        id: 'tab:automations',
        kind: 'automations',
        title: 'Automações',
        route: '/automacoes',
        closable: true,
      });
    } else if (path === '/consumo') {
      openTab({
        id: 'tab:usage',
        kind: 'usage',
        title: 'Contas e consumo',
        route: '/consumo',
        closable: true,
      });
    } else if (path === '/busca') {
      openTab({
        id: 'tab:search',
        kind: 'search',
        title: 'Busca global',
        route: '/busca',
        closable: true,
      });
    } else if (path === '/terminal') {
      openTab({
        id: 'tab:terminal',
        kind: 'terminal',
        title: 'Terminal PTY',
        route: '/terminal',
        closable: true,
      });
    } else if (path === '/') {
      openTab({
        id: 'tab:new-chat',
        kind: 'new_chat',
        title: 'Novo chat',
        route: '/',
        closable: false,
      });
    }
  }, [location.pathname, openTab]);

  if (!token || status !== 'authenticated') {
    return <AuthGate />;
  }

  const handleNavigate = (item: { id: string; label: string; route: string; kind: TabKind }) => {
    openTab({
      id: item.id,
      kind: item.kind,
      title: item.label,
      route: item.route,
      closable: item.kind !== 'new_chat',
    });
    if (location.pathname !== item.route) {
      navigate(item.route);
    }
    setMobileDrawerOpen(false);
  };

  const handleSelectTreeNode = (node: WorkspaceTreeNode) => {
    if (node.kind === 'session') {
      const targetId = node.sessionId ?? node.runId ?? node.id;
      const route = `/chat/${encodeURIComponent(targetId)}`;
      openTab({
        id: `tab:session:${targetId}`,
        kind: 'chat',
        title: node.label,
        route,
        hostId: node.hostId,
        workspaceId: node.workspaceId ?? undefined,
        projectId: node.projectId ?? undefined,
        runId: node.runId ?? undefined,
        sessionId: node.sessionId ?? undefined,
        closable: true,
      });
      navigate(route);
    } else if (node.kind === 'workspace') {
      handleNavigate({
        id: 'tab:workspaces',
        label: 'Workspaces',
        route: '/workspace',
        kind: 'workspace',
      });
    }
  };

  const shellContent = (
    <div
      data-testid="hydra-app-shell"
      className="flex h-screen w-screen overflow-hidden bg-[#141414] text-[#E8E8E8]"
    >
      <AppRail activeRoute={location.pathname} onNavigate={handleNavigate} />

      <Sidebar
        searchInputRef={searchInputRef}
        onOpenRoute={handleNavigate}
        onSelectTreeNode={handleSelectTreeNode}
      />

      <main className="flex min-w-0 flex-1 flex-col bg-[#141414]">
        {bootstrapQuery.isLoading ? (
          <div className="flex flex-1 items-center justify-center text-sm text-[#969696]">
            Carregando Control Plane Hydra...
          </div>
        ) : (
          <PaneLayout
            renderTabContent={renderTabPage}
            onSyncRoute={(route) => {
              if (location.pathname !== route) {
                navigate(route);
              }
            }}
          />
        )}
      </main>
    </div>
  );

  return (
    <Routes>
      <Route path="/" element={shellContent} />
      <Route path="/chat/:id" element={shellContent} />
      <Route path="/terminal" element={shellContent} />
      <Route path="/workspace" element={shellContent} />
      <Route path="/recursos" element={shellContent} />
      <Route path="/automacoes" element={shellContent} />
      <Route path="/consumo" element={shellContent} />
      <Route path="/busca" element={shellContent} />
      <Route path="/configuracoes" element={shellContent} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  const queryClient = useMemo(() => createHydraQueryClient(), []);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <HydraShell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
