import { create } from 'zustand';

const LAYOUT_STORAGE_KEY = 'hydra_layout_state_v1';
export const DEFAULT_SIDEBAR_WIDTH = 280;
export const MIN_SIDEBAR_WIDTH = 200;
export const MAX_SIDEBAR_WIDTH = 420;

export type TabKind =
  | 'new_chat'
  | 'chat'
  | 'terminal'
  | 'workspace'
  | 'resources'
  | 'automations'
  | 'device'
  | 'computer_use'
  | 'usage'
  | 'search'
  | 'settings';

export interface WorkspaceTab {
  id: string;
  kind: TabKind;
  title: string;
  route: string;
  hostId?: string;
  workspaceId?: string;
  projectId?: string;
  runId?: string;
  sessionId?: string;
  closable?: boolean;
}

export type PaneId = 'primary' | 'secondary';
export type SplitMode = 'single' | 'split';
export type DensityMode = 'comfortable' | 'compact';

export interface PaneState {
  id: PaneId;
  tabIds: string[];
  activeTabId: string | null;
}

interface PersistedLayout {
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  splitMode: SplitMode;
  focusedPaneId: PaneId;
  panes: Record<PaneId, PaneState>;
  tabs: Record<string, WorkspaceTab>;
  selectedHostId: string;
  selectedAreaId: string | null;
  selectedWorkspaceId: string | null;
  selectedProjectId: string | null;
  selectedRunId: string | null;
  selectedSessionId: string | null;
  expandedNodeIds: Record<string, boolean>;
  density: DensityMode;
  reducedMotion: boolean;
  keyboardHintsVisible: boolean;
}

const DEFAULT_HOME_TAB: WorkspaceTab = {
  id: 'tab:new-chat',
  kind: 'new_chat',
  title: 'Novo chat',
  route: '/',
  closable: false,
};

function clampSidebarWidth(width: number): number {
  if (!Number.isFinite(width)) {
    return DEFAULT_SIDEBAR_WIDTH;
  }
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, Math.round(width)));
}

function createDefaultPersistedLayout(): PersistedLayout {
  return {
    sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    sidebarCollapsed: false,
    splitMode: 'single',
    focusedPaneId: 'primary',
    panes: {
      primary: {
        id: 'primary',
        tabIds: [DEFAULT_HOME_TAB.id],
        activeTabId: DEFAULT_HOME_TAB.id,
      },
      secondary: {
        id: 'secondary',
        tabIds: [],
        activeTabId: null,
      },
    },
    tabs: {
      [DEFAULT_HOME_TAB.id]: DEFAULT_HOME_TAB,
    },
    selectedHostId: 'local',
    selectedAreaId: null,
    selectedWorkspaceId: null,
    selectedProjectId: null,
    selectedRunId: null,
    selectedSessionId: null,
    expandedNodeIds: { 'host:local': true },
    density: 'comfortable',
    reducedMotion: false,
    keyboardHintsVisible: true,
  };
}

function loadPersistedLayout(): PersistedLayout {
  const fallback = createDefaultPersistedLayout();
  if (typeof window === 'undefined') {
    return fallback;
  }
  try {
    const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw) as Partial<PersistedLayout>;
    const tabs =
      parsed.tabs && typeof parsed.tabs === 'object'
        ? { [DEFAULT_HOME_TAB.id]: DEFAULT_HOME_TAB, ...parsed.tabs }
        : fallback.tabs;
    const primaryTabs = Array.isArray(parsed.panes?.primary?.tabIds)
      ? parsed.panes.primary.tabIds.filter((id) => Boolean(tabs[id]))
      : fallback.panes.primary.tabIds;
    if (primaryTabs.length === 0) {
      primaryTabs.push(DEFAULT_HOME_TAB.id);
    }
    const secondaryTabs = Array.isArray(parsed.panes?.secondary?.tabIds)
      ? parsed.panes.secondary.tabIds.filter((id) => Boolean(tabs[id]))
      : [];

    return {
      sidebarWidth: clampSidebarWidth(parsed.sidebarWidth ?? DEFAULT_SIDEBAR_WIDTH),
      sidebarCollapsed: Boolean(parsed.sidebarCollapsed),
      splitMode: parsed.splitMode === 'split' ? 'split' : 'single',
      focusedPaneId: parsed.focusedPaneId === 'secondary' ? 'secondary' : 'primary',
      panes: {
        primary: {
          id: 'primary',
          tabIds: primaryTabs,
          activeTabId:
            parsed.panes?.primary?.activeTabId && tabs[parsed.panes.primary.activeTabId]
              ? parsed.panes.primary.activeTabId
              : primaryTabs[0],
        },
        secondary: {
          id: 'secondary',
          tabIds: secondaryTabs,
          activeTabId:
            parsed.panes?.secondary?.activeTabId && tabs[parsed.panes.secondary.activeTabId]
              ? parsed.panes.secondary.activeTabId
              : secondaryTabs[0] ?? null,
        },
      },
      tabs,
      selectedHostId:
        typeof parsed.selectedHostId === 'string' && parsed.selectedHostId
          ? parsed.selectedHostId
          : 'local',
      selectedAreaId: parsed.selectedAreaId ?? null,
      selectedWorkspaceId: parsed.selectedWorkspaceId ?? null,
      selectedProjectId: parsed.selectedProjectId ?? null,
      selectedRunId: parsed.selectedRunId ?? null,
      selectedSessionId: parsed.selectedSessionId ?? null,
      expandedNodeIds:
        parsed.expandedNodeIds && typeof parsed.expandedNodeIds === 'object'
          ? parsed.expandedNodeIds
          : { 'host:local': true },
      density: parsed.density === 'compact' ? 'compact' : 'comfortable',
      reducedMotion: Boolean(parsed.reducedMotion),
      keyboardHintsVisible: parsed.keyboardHintsVisible ?? true,
    };
  } catch {
    return fallback;
  }
}

function savePersistedLayout(state: PersistedLayout): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    const payload: PersistedLayout = {
      sidebarWidth: state.sidebarWidth,
      sidebarCollapsed: state.sidebarCollapsed,
      splitMode: state.splitMode,
      focusedPaneId: state.focusedPaneId,
      panes: state.panes,
      tabs: state.tabs,
      selectedHostId: state.selectedHostId,
      selectedAreaId: state.selectedAreaId,
      selectedWorkspaceId: state.selectedWorkspaceId,
      selectedProjectId: state.selectedProjectId,
      selectedRunId: state.selectedRunId,
      selectedSessionId: state.selectedSessionId,
      expandedNodeIds: state.expandedNodeIds,
      density: state.density,
      reducedMotion: state.reducedMotion,
      keyboardHintsVisible: state.keyboardHintsVisible,
    };
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Sem falha se storage estiver indisponivel
  }
}

export interface HierarchySelection {
  hostId?: string;
  areaId?: string | null;
  workspaceId?: string | null;
  projectId?: string | null;
  runId?: string | null;
  sessionId?: string | null;
}

export interface LayoutState extends PersistedLayout {
  mobileDrawerOpen: boolean;
  setSidebarWidth: (width: number) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setMobileDrawerOpen: (open: boolean) => void;
  setSplitMode: (mode: SplitMode) => void;
  toggleSplitMode: () => void;
  focusPane: (paneId: PaneId) => void;
  openTab: (tab: WorkspaceTab, targetPane?: PaneId) => void;
  activateTab: (tabId: string, paneId?: PaneId) => void;
  closeTab: (tabId: string, paneId?: PaneId) => void;
  reorderTabs: (paneId: PaneId, fromIndex: number, toIndex: number) => void;
  selectHierarchy: (selection: HierarchySelection) => void;
  toggleTreeNode: (nodeId: string, force?: boolean) => void;
  setDensity: (density: DensityMode) => void;
  setReducedMotion: (reduced: boolean) => void;
  setKeyboardHintsVisible: (visible: boolean) => void;
  resetLayout: () => void;
}

function updateAndPersist(
  set: (fn: (prev: LayoutState) => Partial<LayoutState>) => void,
  updater: (prev: LayoutState) => Partial<LayoutState>,
): void {
  set((prev) => {
    const patch = updater(prev);
    const next = { ...prev, ...patch };
    savePersistedLayout(next);
    return patch;
  });
}

const initialLayout = loadPersistedLayout();

export const useLayoutStore = create<LayoutState>((set) => ({
  ...initialLayout,
  mobileDrawerOpen: false,
  setSidebarWidth: (width) =>
    updateAndPersist(set, () => ({ sidebarWidth: clampSidebarWidth(width) })),
  setSidebarCollapsed: (collapsed) =>
    updateAndPersist(set, () => ({ sidebarCollapsed: collapsed })),
  toggleSidebar: () =>
    updateAndPersist(set, (prev) => ({ sidebarCollapsed: !prev.sidebarCollapsed })),
  setMobileDrawerOpen: (open) => set({ mobileDrawerOpen: open }),
  setSplitMode: (mode) =>
    updateAndPersist(set, (prev) => ({
      splitMode: mode,
      focusedPaneId: mode === 'single' ? 'primary' : prev.focusedPaneId,
    })),
  toggleSplitMode: () =>
    updateAndPersist(set, (prev) => {
      const nextMode: SplitMode = prev.splitMode === 'single' ? 'split' : 'single';
      return {
        splitMode: nextMode,
        focusedPaneId: nextMode === 'single' ? 'primary' : prev.focusedPaneId,
      };
    }),
  focusPane: (paneId) =>
    updateAndPersist(set, (prev) => ({
      focusedPaneId: prev.splitMode === 'single' ? 'primary' : paneId,
    })),
  openTab: (tab, targetPane) =>
    updateAndPersist(set, (prev) => {
      const existingPaneId: PaneId | null = prev.panes.primary.tabIds.includes(tab.id)
        ? 'primary'
        : prev.panes.secondary.tabIds.includes(tab.id)
          ? 'secondary'
          : null;

      const paneId: PaneId =
        existingPaneId ??
        (targetPane && prev.splitMode === 'split'
          ? targetPane
          : prev.splitMode === 'split'
            ? prev.focusedPaneId
            : 'primary');

      const pane = prev.panes[paneId];
      const nextTabIds = pane.tabIds.includes(tab.id) ? pane.tabIds : [...pane.tabIds, tab.id];

      return {
        tabs: {
          ...prev.tabs,
          [tab.id]: { ...prev.tabs[tab.id], ...tab },
        },
        panes: {
          ...prev.panes,
          [paneId]: {
            ...pane,
            tabIds: nextTabIds,
            activeTabId: tab.id,
          },
        },
        focusedPaneId: paneId,
      };
    }),
  activateTab: (tabId, paneId) =>
    updateAndPersist(set, (prev) => {
      const resolvedPane: PaneId =
        paneId ??
        (prev.panes.secondary.tabIds.includes(tabId) ? 'secondary' : 'primary');
      const pane = prev.panes[resolvedPane];
      if (!pane.tabIds.includes(tabId)) {
        return {};
      }
      return {
        panes: {
          ...prev.panes,
          [resolvedPane]: {
            ...pane,
            activeTabId: tabId,
          },
        },
        focusedPaneId: resolvedPane,
      };
    }),
  closeTab: (tabId, paneId) =>
    updateAndPersist(set, (prev) => {
      const targetPaneId: PaneId =
        paneId ??
        (prev.panes.secondary.tabIds.includes(tabId) ? 'secondary' : 'primary');
      const tab = prev.tabs[tabId];
      if (!tab || tab.closable === false) {
        return {};
      }
      const pane = prev.panes[targetPaneId];
      const idx = pane.tabIds.indexOf(tabId);
      if (idx === -1) {
        return {};
      }
      const nextTabIds = pane.tabIds.filter((id) => id !== tabId);
      let nextActive = pane.activeTabId;
      if (pane.activeTabId === tabId) {
        nextActive = nextTabIds[idx] ?? nextTabIds[idx - 1] ?? null;
      }
      if (targetPaneId === 'primary' && nextTabIds.length === 0) {
        nextTabIds.push(DEFAULT_HOME_TAB.id);
        nextActive = DEFAULT_HOME_TAB.id;
      }

      const otherPaneId: PaneId = targetPaneId === 'primary' ? 'secondary' : 'primary';
      const usedElsewhere = prev.panes[otherPaneId].tabIds.includes(tabId);
      const nextTabs = { ...prev.tabs };
      if (!usedElsewhere && tabId !== DEFAULT_HOME_TAB.id) {
        delete nextTabs[tabId];
      }

      return {
        tabs: nextTabs,
        panes: {
          ...prev.panes,
          [targetPaneId]: {
            ...pane,
            tabIds: nextTabIds,
            activeTabId: nextActive,
          },
        },
      };
    }),
  reorderTabs: (paneId, fromIndex, toIndex) =>
    updateAndPersist(set, (prev) => {
      const pane = prev.panes[paneId];
      if (
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= pane.tabIds.length ||
        toIndex >= pane.tabIds.length ||
        fromIndex === toIndex
      ) {
        return {};
      }
      const next = [...pane.tabIds];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return {
        panes: {
          ...prev.panes,
          [paneId]: {
            ...pane,
            tabIds: next,
          },
        },
      };
    }),
  selectHierarchy: (selection) =>
    updateAndPersist(set, (prev) => ({
      selectedHostId: selection.hostId ?? prev.selectedHostId,
      selectedAreaId:
        selection.areaId !== undefined ? selection.areaId : prev.selectedAreaId,
      selectedWorkspaceId:
        selection.workspaceId !== undefined ? selection.workspaceId : prev.selectedWorkspaceId,
      selectedProjectId:
        selection.projectId !== undefined ? selection.projectId : prev.selectedProjectId,
      selectedRunId: selection.runId !== undefined ? selection.runId : prev.selectedRunId,
      selectedSessionId:
        selection.sessionId !== undefined ? selection.sessionId : prev.selectedSessionId,
    })),
  toggleTreeNode: (nodeId, force) =>
    updateAndPersist(set, (prev) => {
      const current = Boolean(prev.expandedNodeIds[nodeId]);
      const nextValue = force !== undefined ? force : !current;
      return {
        expandedNodeIds: {
          ...prev.expandedNodeIds,
          [nodeId]: nextValue,
        },
      };
    }),
  setDensity: (density) => updateAndPersist(set, () => ({ density })),
  setReducedMotion: (reducedMotion) => updateAndPersist(set, () => ({ reducedMotion })),
  setKeyboardHintsVisible: (keyboardHintsVisible) =>
    updateAndPersist(set, () => ({ keyboardHintsVisible })),
  resetLayout: () => {
    const fresh = createDefaultPersistedLayout();
    savePersistedLayout(fresh);
    set({ ...fresh, mobileDrawerOpen: false });
  },
}));
