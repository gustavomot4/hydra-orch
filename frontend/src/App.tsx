import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { AppRail } from '@/component/AppRail';
import { AuthGate } from '@/component/AuthGate';
import { PaneLayout } from '@/component/PaneLayout';
import { Sidebar } from '@/component/Sidebar';
import { AttachmentDropzone, AttachmentItemView } from '@/feature/attachment';
import { AutomationsPage } from '@/feature/automation';
import { ChatTimelinePage } from '@/feature/chat';
import { PromptComposer, SlashCommandItem } from '@/feature/composer';
import { ComputerUsePanel } from '@/feature/computer_use';
import { DevicePanel } from '@/feature/device';
import { DictationControl } from '@/feature/dictation';
import { GovernancePage } from '@/feature/governance';
import { QuickOpenDialog, QuickOpenSearchItem } from '@/feature/quickopen';
import { QuotaAccountsPage } from '@/feature/quota';
import { SplitTerminalView } from '@/feature/terminal';
import { createHydraQueryClient } from '@/hook/queryClient';
import { useBootstrap } from '@/hook/useBootstrap';
import { useKeyboardShortcuts } from '@/hook/useKeyboardShortcuts';
import { useWorkspaceHierarchy, WorkspaceTreeNode } from '@/hook/useWorkspaceHierarchy';
import { ConfigPerfilPage } from '@/page/ConfigPerfilPage';
import { NovoChatPage } from '@/page/NovoChatPage';
import { WorkspaceWorkbenchPage } from '@/page/WorkspaceWorkbenchPage';
import { useAuthStore } from '@/store/authStore';
import { PaneId, TabKind, useLayoutStore, WorkspaceTab } from '@/store/layoutStore';

function buildTabFromQuickOpen(item: QuickOpenSearchItem): WorkspaceTab {
  if (item.tab_hint === 'chat' || item.kind === 'run' || item.kind === 'session') {
    const runTarget = item.run_id ?? (item.kind === 'run' ? item.id : null);
    const targetId = runTarget ?? item.session_id ?? item.id;
    return {
      id: `tab:chat:${targetId}`,
      kind: 'chat',
      title: item.title,
      route: `/chat/${encodeURIComponent(targetId)}`,
      hostId: item.host_id,
      workspaceId: item.workspace_id ?? undefined,
      projectId: item.project_id ?? undefined,
      runId: runTarget ?? undefined,
      sessionId: item.session_id ?? undefined,
      closable: true,
    };
  }
  if (item.tab_hint === 'terminal') {
    return {
      id: `tab:terminal:${item.id}`,
      kind: 'terminal',
      title: `Terminal · ${item.title}`,
      route: '/terminal',
      hostId: item.host_id,
      workspaceId: item.workspace_id ?? undefined,
      projectId: item.project_id ?? undefined,
      closable: true,
    };
  }
  return {
    id: `tab:workspace:${item.id}`,
    kind: 'workspace',
    title: item.kind === 'artifact' ? `Artefato · ${item.title}` : item.title,
    route: '/workspace',
    hostId: item.host_id,
    workspaceId: item.workspace_id ?? undefined,
    projectId: item.project_id ?? undefined,
    runId: item.run_id ?? undefined,
    closable: true,
  };
}

export function HydraShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const searchInputRef = useRef<HTMLInputElement>(null);

  const token = useAuthStore((s) => s.token);
  const status = useAuthStore((s) => s.status);
  const density = useLayoutStore((s) => s.density);
  const reducedMotion = useLayoutStore((s) => s.reducedMotion);
  const selectedHostId = useLayoutStore((s) => s.selectedHostId);
  const selectedWorkspaceId = useLayoutStore((s) => s.selectedWorkspaceId);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectedRunId = useLayoutStore((s) => s.selectedRunId);
  const openTab = useLayoutStore((s) => s.openTab);
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);
  const setMobileDrawerOpen = useLayoutStore((s) => s.setMobileDrawerOpen);

  const [quickOpenOpen, setQuickOpenOpen] = useState(false);
  const [draftAttachments, setDraftAttachments] = useState<AttachmentItemView[]>([]);

  const bootstrapQuery = useBootstrap();
  const { projects } = useWorkspaceHierarchy();

  const activeProjectRoot = useMemo(() => {
    const project = projects.find((p) => p.id === selectedProjectId) ?? projects[0];
    return project?.canonical_root ?? '.';
  }, [projects, selectedProjectId]);

  useKeyboardShortcuts({
    enabled: Boolean(token) && status === 'authenticated',
    onFocusSearch: () => {
      setQuickOpenOpen(true);
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
    } else if (path === '/dispositivos') {
      openTab({
        id: 'tab:device',
        kind: 'device',
        title: 'Emulador móvel',
        route: '/dispositivos',
        closable: true,
      });
    } else if (path === '/computador') {
      openTab({
        id: 'tab:computer-use',
        kind: 'computer_use',
        title: 'Controle do computador',
        route: '/computador',
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
    } else if (path.startsWith('/chat/')) {
      const chatId = decodeURIComponent(path.slice('/chat/'.length));
      if (chatId) {
        const tabs = useLayoutStore.getState().tabs;
        const alreadyOpen = Object.values(tabs).some(
          (t) => t.route === path && t.kind === 'chat',
        );
        if (!alreadyOpen) {
          openTab({
            id: `tab:chat:${chatId}`,
            kind: 'chat',
            title: `Run ${chatId.slice(0, 12)}`,
            route: path,
            runId: chatId,
            closable: true,
          });
        }
      }
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

  const handleNavigate = useCallback(
    (item: { id: string; label: string; route: string; kind: TabKind }) => {
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
    },
    [location.pathname, navigate, openTab, setMobileDrawerOpen],
  );

  const handleSelectTreeNode = useCallback(
    (node: WorkspaceTreeNode) => {
      if (node.kind === 'session') {
        const targetId = node.runId ?? node.sessionId ?? node.id;
        const route = `/chat/${encodeURIComponent(targetId)}`;
        selectHierarchy({
          hostId: node.hostId,
          projectId: node.projectId ?? null,
          workspaceId: node.workspaceId ?? null,
          runId: node.runId ?? null,
          sessionId: node.sessionId ?? null,
        });
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
        selectHierarchy({
          hostId: node.hostId,
          projectId: node.projectId ?? null,
          workspaceId: node.workspaceId ?? null,
        });
        handleNavigate({
          id: 'tab:workspaces',
          label: 'Workspaces',
          route: '/workspace',
          kind: 'workspace',
        });
      }
    },
    [handleNavigate, navigate, openTab, selectHierarchy],
  );

  const handleSelectQuickOpenItem = useCallback(
    (item: QuickOpenSearchItem) => {
      selectHierarchy({
        hostId: item.host_id,
        projectId: item.project_id ?? null,
        workspaceId: item.workspace_id ?? null,
        runId: item.run_id ?? (item.kind === 'run' ? item.id : null),
        sessionId: item.session_id ?? (item.kind === 'session' ? item.id : null),
      });
      const nextTab = buildTabFromQuickOpen(item);
      openTab(nextTab);
      if (location.pathname !== nextTab.route) {
        navigate(nextTab.route);
      }
    },
    [location.pathname, navigate, openTab, selectHierarchy],
  );

  const handleOpenTerminalFromRun = useCallback(
    (runId: string) => {
      const tab: WorkspaceTab = {
        id: `tab:terminal:${runId}`,
        kind: 'terminal',
        title: `Terminal · ${runId.slice(0, 12)}`,
        route: '/terminal',
        hostId: selectedHostId,
        workspaceId: selectedWorkspaceId ?? undefined,
        projectId: selectedProjectId ?? undefined,
        runId,
        closable: true,
      };
      openTab(tab);
      if (location.pathname !== '/terminal') {
        navigate('/terminal');
      }
    },
    [location.pathname, navigate, openTab, selectedHostId, selectedProjectId, selectedWorkspaceId],
  );

  const handleOpenRunFromAutomation = useCallback(
    (runId: string) => {
      const route = `/chat/${encodeURIComponent(runId)}`;
      selectHierarchy({
        hostId: selectedHostId,
        workspaceId: selectedWorkspaceId,
        projectId: selectedProjectId,
        runId,
      });
      openTab({
        id: `tab:chat:${runId}`,
        kind: 'chat',
        title: `Run ${runId.slice(0, 12)}`,
        route,
        hostId: selectedHostId,
        workspaceId: selectedWorkspaceId ?? undefined,
        projectId: selectedProjectId ?? undefined,
        runId,
        closable: true,
      });
      if (location.pathname !== route) {
        navigate(route);
      }
    },
    [
      location.pathname,
      navigate,
      openTab,
      selectHierarchy,
      selectedHostId,
      selectedProjectId,
      selectedWorkspaceId,
    ],
  );

  const renderTabPage = useCallback(
    (tab: WorkspaceTab | null, _paneId: PaneId) => {
      if (!tab) {
        return null;
      }
      switch (tab.kind) {
        case 'new_chat':
          return (
            <NovoChatPage
              renderComposer={(slot) => {
                const draftSessionId = `draft-${slot.selectedProjectId || 'default'}`;
                const workspaceScope = selectedWorkspaceId ?? (slot.selectedProjectId || 'default');
                const handleSlash = (item: SlashCommandItem): boolean | void => {
                  if (item.command === '/review') {
                    handleNavigate({
                      id: 'tab:workspaces',
                      label: 'Workspaces',
                      route: '/workspace',
                      kind: 'workspace',
                    });
                    return true;
                  }
                  if (item.command === '/terminal') {
                    handleNavigate({
                      id: 'tab:terminal',
                      label: 'Terminal PTY',
                      route: '/terminal',
                      kind: 'terminal',
                    });
                    return true;
                  }
                  if (item.command === '/status') {
                    handleNavigate({
                      id: 'tab:usage',
                      label: 'Contas e consumo',
                      route: '/consumo',
                      kind: 'usage',
                    });
                    return true;
                  }
                };

                return (
                  <AttachmentDropzone
                    sessionId={draftSessionId}
                    workspaceId={workspaceScope}
                    hostId={selectedHostId}
                    attachments={draftAttachments}
                    onAttachmentsChange={setDraftAttachments}
                  >
                    <PromptComposer
                      draft={slot.draft}
                      onDraftChange={slot.onDraftChange}
                      mode={slot.mode}
                      onModeChange={slot.onModeChange}
                      selectedProjectId={slot.selectedProjectId}
                      sessionKey={draftSessionId}
                      onSubmit={slot.onSubmit}
                      isSubmitting={slot.isSubmitting}
                      submitLabel="Iniciar run"
                      onSlashCommand={handleSlash}
                      renderAttachControl={null}
                      renderDictationControl={
                        <DictationControl
                          onInsertTranscript={(text) => {
                            const cleaned = text.trim();
                            if (!cleaned) {
                              return;
                            }
                            const next = slot.draft.trim()
                              ? `${slot.draft.trimEnd()} ${cleaned}`
                              : cleaned;
                            slot.onDraftChange(next);
                          }}
                        />
                      }
                    />
                  </AttachmentDropzone>
                );
              }}
            />
          );
        case 'settings':
          return <ConfigPerfilPage />;
        case 'chat':
          return (
            <ChatTimelinePage
              runId={tab.runId}
              sessionId={tab.sessionId}
              onOpenTerminal={handleOpenTerminalFromRun}
            />
          );
        case 'terminal':
          return (
            <SplitTerminalView
              hostId={tab.hostId ?? selectedHostId}
              workspaceId={tab.workspaceId ?? selectedWorkspaceId ?? undefined}
              defaultCwd={activeProjectRoot}
            />
          );
        case 'workspace':
          return (
            <WorkspaceWorkbenchPage
              initialRunId={tab.runId ?? null}
              initialSection={tab.title.startsWith('Artefato') ? 'artifacts' : 'conflicts'}
            />
          );
        case 'resources':
          return <GovernancePage initialRunId={selectedRunId} />;
        case 'automations':
          return (
            <AutomationsPage
              onOpenRun={handleOpenRunFromAutomation}
              defaultWorkspaceId={selectedWorkspaceId ?? undefined}
              defaultProjectId={selectedProjectId ?? undefined}
            />
          );
        case 'device':
          return (
            <DevicePanel
              hostId={selectedHostId}
              onHostChange={(nextHostId) => selectHierarchy({ hostId: nextHostId })}
            />
          );
        case 'computer_use':
          return (
            <ComputerUsePanel
              hostId={selectedHostId}
              onHostChange={(nextHostId) => selectHierarchy({ hostId: nextHostId })}
            />
          );
        case 'usage':
          return <QuotaAccountsPage />;
        case 'search':
          return (
            <div
              data-testid="search-tab-launcher"
              className="mx-auto flex max-w-2xl flex-col items-center justify-center gap-3 p-8 text-center"
            >
              <Search aria-hidden="true" className="h-8 w-8 text-[#969696]" />
              <h1 className="text-lg font-semibold text-[#E8E8E8]">Busca global (QuickOpen)</h1>
              <p className="text-xs text-[#969696]">
                Pressione <kbd className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]">Ctrl+K</kbd> em qualquer tela para pesquisar áreas, workspaces, projetos, runs, sessões e artefatos sem perder rascunhos abertos.
              </p>
              <button
                type="button"
                onClick={() => setQuickOpenOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-4 py-1.5 text-xs font-medium text-[#181818] hover:bg-white"
              >
                <Search aria-hidden="true" className="h-3.5 w-3.5" />
                <span>Abrir QuickOpen</span>
              </button>
            </div>
          );
      }
    },
    [
      activeProjectRoot,
      draftAttachments,
      handleNavigate,
      handleOpenRunFromAutomation,
      handleOpenTerminalFromRun,
      selectHierarchy,
      selectedHostId,
      selectedProjectId,
      selectedRunId,
      selectedWorkspaceId,
    ],
  );

  if (!token || status !== 'authenticated') {
    return <AuthGate />;
  }

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

      <QuickOpenDialog
        open={quickOpenOpen}
        onOpenChange={setQuickOpenOpen}
        hostId={selectedHostId}
        onSelectItem={handleSelectQuickOpenItem}
      />
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
      <Route path="/dispositivos" element={shellContent} />
      <Route path="/computador" element={shellContent} />
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
