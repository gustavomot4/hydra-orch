import { useEffect } from 'react';
import { useLayoutStore } from '@/store/layoutStore';

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) {
    return true;
  }
  return Boolean(target.closest('.xterm'));
}

export interface KeyboardShortcutOptions {
  onFocusSearch?: () => void;
  enabled?: boolean;
}

export function useKeyboardShortcuts(options: KeyboardShortcutOptions = {}) {
  const enabled = options.enabled ?? true;
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const toggleSplitMode = useLayoutStore((s) => s.toggleSplitMode);
  const focusPane = useLayoutStore((s) => s.focusPane);
  const closeTab = useLayoutStore((s) => s.closeTab);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.isComposing) {
        return;
      }
      const mod = event.ctrlKey || event.metaKey;
      const inEditor = isEditableElement(event.target);

      if (mod && event.key.toLowerCase() === 'b' && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        toggleSidebar();
        return;
      }

      if (mod && event.key.toLowerCase() === 'k' && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        options.onFocusSearch?.();
        return;
      }

      if (inEditor) {
        return;
      }

      if (event.altKey && event.key.toLowerCase() === 's') {
        event.preventDefault();
        toggleSplitMode();
        return;
      }

      if (event.altKey && event.key === '1') {
        event.preventDefault();
        focusPane('primary');
        return;
      }

      if (event.altKey && event.key === '2') {
        event.preventDefault();
        focusPane('secondary');
        return;
      }

      if (event.altKey && event.key.toLowerCase() === 'w') {
        event.preventDefault();
        const state = useLayoutStore.getState();
        const pane = state.panes[state.focusedPaneId];
        if (pane?.activeTabId) {
          closeTab(pane.activeTabId, state.focusedPaneId);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [enabled, toggleSidebar, toggleSplitMode, focusPane, closeTab, options]);
}
