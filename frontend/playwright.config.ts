import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium, defineConfig, devices } from '@playwright/test';

const uiPort = Number(process.env.HYDRA_E2E_UI_PORT || '15173');
const backendPort = process.env.HYDRA_E2E_BACKEND_PORT || '18421';

function resolveChromiumExecutable(): string | undefined {
  const fromEnv = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?.trim();
  if (fromEnv && fs.existsSync(fromEnv)) {
    return fromEnv;
  }
  const defaultExe = chromium.executablePath();
  if (defaultExe && fs.existsSync(defaultExe)) {
    return undefined;
  }

  const cacheRoots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, 'ms-playwright') : undefined,
    path.join(os.homedir(), '.cache', 'ms-playwright'),
  ].filter((v): v is string => Boolean(v && v.trim().length > 0));

  for (const root of cacheRoots) {
    if (!fs.existsSync(root)) {
      continue;
    }
    const dirs = fs.readdirSync(root).sort().reverse();
    for (const dir of dirs) {
      if (dir.startsWith('chromium-')) {
        const winExe = path.join(root, dir, 'chrome-win64', 'chrome.exe');
        if (fs.existsSync(winExe)) {
          return winExe;
        }
        const linuxExe = path.join(root, dir, 'chrome-linux', 'chrome');
        if (fs.existsSync(linuxExe)) {
          return linuxExe;
        }
      }
      if (dir.startsWith('chromium_headless_shell-')) {
        const winHeadless = path.join(
          root,
          dir,
          'chrome-headless-shell-win64',
          'chrome-headless-shell.exe',
        );
        if (fs.existsSync(winHeadless)) {
          return winHeadless;
        }
      }
    }
  }
  return undefined;
}

const resolvedExecutablePath = resolveChromiumExecutable();

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [['list']],
  globalSetup: './tests/e2e/globalSetup.ts',
  use: {
    baseURL: `http://127.0.0.1:${uiPort}`,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    ...devices['Desktop Chrome'],
    viewport: { width: 1920, height: 1100 },
    launchOptions: resolvedExecutablePath ? { executablePath: resolvedExecutablePath } : undefined,
  },
  webServer: {
    command: `npx vite --config tests/e2e/vite.e2e.config.ts --port ${uiPort} --strictPort`,
    url: `http://127.0.0.1:${uiPort}/`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      ...process.env,
      HYDRA_E2E_BACKEND_PORT: backendPort,
      HYDRA_E2E_UI_PORT: String(uiPort),
    },
  },
});
