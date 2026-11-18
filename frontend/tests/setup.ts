import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// jsdom has no pointer capture; the real browser exercises capture in e2e.
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};

if (
  typeof window !== 'undefined' &&
  (typeof window.matchMedia !== 'function' ||
    typeof window.matchMedia('(min-width: 0px)')?.addEventListener !== 'function')
) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

if (
  typeof HTMLCanvasElement !== 'undefined' &&
  typeof navigator !== 'undefined' &&
  /jsdom/i.test(navigator.userAgent)
) {
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    writable: true,
    configurable: true,
    value: () => null,
  });
}

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.restoreAllMocks();
});
