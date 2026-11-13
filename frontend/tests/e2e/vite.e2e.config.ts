import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backendPort = process.env.HYDRA_E2E_BACKEND_PORT || '18421';
const uiPort = Number(process.env.HYDRA_E2E_UI_PORT || '15173');
const projectRoot = path.resolve(__dirname, '../..');

export default defineConfig({
  root: projectRoot,
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(projectRoot, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: uiPort,
    strictPort: true,
    proxy: {
      '/v1': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
