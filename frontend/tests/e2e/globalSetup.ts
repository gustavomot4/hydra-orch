import { ChildProcess, spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, '../../..');

export const E2E_TOKEN =
  process.env.HYDRA_API_TOKEN || 'hydra-e2e-hermetic-local-token-0123456789';
export const E2E_BACKEND_PORT = process.env.HYDRA_E2E_BACKEND_PORT || '18421';
export const E2E_UI_PORT = process.env.HYDRA_E2E_UI_PORT || '15173';

function resolvePythonExecutable(): string {
  if (process.env.HYDRA_PYTHON && process.env.HYDRA_PYTHON.trim().length > 0) {
    return process.env.HYDRA_PYTHON.trim();
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

async function waitForBackendHealth(url: string, token: string, proc: ChildProcess, logs: string[]): Promise<void> {
  const deadline = Date.now() + 25_000;
  let lastError = 'not started';

  while (Date.now() < deadline) {
    if (proc.exitCode !== null) {
      throw new Error(
        `E2E backend exited early with code ${String(proc.exitCode)}. Logs:\n${logs.join('')}`,
      );
    }
    try {
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        return;
      }
      lastError = `HTTP ${response.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }

  throw new Error(
    `Timed out waiting for E2E backend at ${url} (${lastError}). Logs:\n${logs.join('')}`,
  );
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  const pythonExe = resolvePythonExecutable();
  const backendScript = path.join(currentDir, 'e2e_backend.py');
  const logs: string[] = [];

  const existingPyPath = process.env.PYTHONPATH || '';
  const srcPath = path.join(repoRoot, 'src');
  const pythonPath = existingPyPath ? `${srcPath}${path.delimiter}${existingPyPath}` : srcPath;

  const backendProc = spawn(pythonExe, [backendScript], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: pythonPath,
      HYDRA_API_TOKEN: E2E_TOKEN,
      HYDRA_E2E_BACKEND_PORT: E2E_BACKEND_PORT,
      HYDRA_E2E_UI_PORT: E2E_UI_PORT,
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  backendProc.stdout?.on('data', (chunk: Buffer) => {
    logs.push(chunk.toString('utf8'));
  });
  backendProc.stderr?.on('data', (chunk: Buffer) => {
    logs.push(chunk.toString('utf8'));
  });

  await waitForBackendHealth(
    `http://127.0.0.1:${E2E_BACKEND_PORT}/health`,
    E2E_TOKEN,
    backendProc,
    logs,
  );

  return async () => {
    if (backendProc.exitCode !== null) {
      return;
    }
    try {
      backendProc.stdin?.end();
    } catch {
      // Ignore already-closed stdin pipe
    }
    const exited = await new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => resolve(false), 5000);
      backendProc.once('exit', () => {
        clearTimeout(timer);
        resolve(true);
      });
    });
    if (!exited && backendProc.exitCode === null) {
      backendProc.kill('SIGTERM');
    }
  };
}
