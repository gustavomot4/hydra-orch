import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: true,
    // Bound jsdom process pressure on desktop machines also running the backend
    // and browser checks. More workers made navigation tests exceed 5 seconds.
    maxWorkers: 2,
    minWorkers: 1,
    // These include multi-step app flows, not only isolated unit functions.
    testTimeout: 15_000,
  },
});
