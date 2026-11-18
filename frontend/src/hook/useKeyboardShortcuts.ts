import { useEffect, useRef } from 'react';
import { useLayoutStore } from '@/store/layoutStore';

function isXtermTarget(target: EventTarget | null): boolean {
  if (target instanceof Element) {
    return Boolean(target.closest('.xterm, [data-renderer="xterm"]'));
  }
  return false;
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return isXtermTarget(target);
  }
  const tag = target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) {
    return true;
  }
  return isXtermTarget(target);
}

function isNarrowViewport(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(max-width: 767px)').matches;
  }
  return window.innerWidth <= 767;
}

export interface KeyboardShortcutOptions {
  onFocusSearch?: () => void;
  onSyncRoute?: (route: string) => void;
  enabled?: boolean;
}

export function useKeyboardShortcuts(options: KeyboardShortcutOptions = {}) {
  const enabled = options.enabled ?? true;
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.isComposing) {
        return;
      }
      const mod = event.ctrlKey || event.metaKey;
      const inXterm = isXtermTarget(event.target);

      if (mod && event.key.toLowerCase() === 'b' && !event.shiftKey && !event.altKey) {
        if (inXterm) {
          return;
        }
        event.preventDefault();
        const state = useLayoutStore.getState();
        if (isNarrowViewport()) {
          state.setMobileDrawerOpen(!state.mobileDrawerOpen);
        } else {
          state.toggleSidebar();
        }
        return;
      }

      if (mod && event.key.toLowerCase() === 'k' && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        optionsRef.current.onFocusSearch?.();
        return;
      }

      if (isEditableElement(event.target)) {
        return;
      }

      if (event.altKey && event.key.toLowerCase() === 's') {
        event.preventDefault();
        useLayoutStore.getState().toggleSplitMode();
        return;
      }

      if (event.altKey && event.key === '1') {
        event.preventDefault();
        useLayoutStore.getState().focusPane('primary');
        return;
      }

      if (event.altKey && event.key === '2') {
        event.preventDefault();
        useLayoutStore.getState().focusPane('secondary');
        return;
      }

      if (event.altKey && event.key.toLowerCase() === 'w') {
        event.preventDefault();
        const state = useLayoutStore.getState();
        const targetPaneId = state.focusedPaneId;
        const pane = state.panes[targetPaneId];
        const closingId = pane?.activeTabId;
        if (closingId) {
          state.closeTab(closingId, targetPaneId);
          const nextState = useLayoutStore.getState();
          const nextActiveId = nextState.panes[targetPaneId].activeTabId;
          const nextTab = nextActiveId ? nextState.tabs[nextActiveId] : null;
          if (nextTab && nextActiveId !== closingId) {
            optionsRef.current.onSyncRoute?.(nextTab.route);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [enabled]);
}
