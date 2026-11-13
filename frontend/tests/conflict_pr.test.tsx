import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  ConflictWorkbench,
  PrPackagePanel,
  type ConflictReport,
  type PRPackage,
  type RunTaskItem,
} from '@/feature/conflict';

function makeTask(overrides: Partial<RunTaskItem> = {}): RunTaskItem {
  return {
    id: 't1',
    task_id: 't1',
    run_id: 'run-99',
    spec: { task_id: 't1', title: 'Implementar parser AST' },
    status: 'reviewing',
    revision: 1,
    dependencies: [],
    current_attempt: {
      id: 'att-1',
      attempt_id: 'att-1',
      task_id: 't1',
      ordinal: 1,
      executor_id: 'codex-1',
      provider: 'openai',
      model: 'gpt-5-codex',
      process_status: 'exited',
      exit_code: 0,
      result: {
        id: 'res-1',
        result_id: 'res-1',
        attempt_id: 'att-1',
        exit_code: 0,
        simulated: false,
        outcome: 'success',
        task_status: 'reviewing',
        revision: 2,
        summary: 'Patch aplicado e 4 checks aprovados.',
        patch_commit_sha: 'abc111',
        patch_artifact_id: 'art-patch-1',
        changed_files: ['src/parser.py'],
        checks: [{ check_id: 'pytest', exit_code: 0, duration_seconds: 1.4 }],
        failures: [],
      },
    },
    attempts: [],
    created_at: '2026-11-13T00:00:00Z',
    updated_at: '2026-11-13T00:00:05Z',
    ...overrides,
  };
}

function makeConflict(overrides: Partial<ConflictReport> = {}): ConflictReport {
  return {
    conflict_id: 'cnf-01',
    integration_id: 'int-01',
    run_id: 'run-99',
    base_sha: '0000base',
    ours_sha: '1111ours',
    theirs_sha: '2222theirs',
    conflicted_files: ['src/app.ts', 'src/config.ts'],
    file_details: [
      {
        path: 'src/app.ts',
        base_content: 'const mode = "base";',
        ours_content: 'const mode = "ours";',
        theirs_content: 'const mode = "theirs";',
        merged_preview: '<<<<<<< OURS\nconst mode = "ours";\n=======\nconst mode = "theirs";\n>>>>>>>',
        hunks: ['@@ -1 +1 @@'],
      },
      {
        path: 'src/config.ts',
        base_content: 'export const timeout = 10;',
        ours_content: 'export const timeout = 20;',
        theirs_content: 'export const timeout = 30;',
        merged_preview: '',
        hunks: [],
      },
    ],
    resolution_options: ['auto_repair', 'manual', 'discarded'],
    status: 'open',
    repair_attempts_used: 0,
    max_repair_attempts: 2,
    repair_worktree_path: '/tmp/wt-repair-01',
    repair_branch: 'hydra/repair/cnf-01',
    resolved_sha: null,
    created_at: '2026-11-13T00:01:00Z',
    resolved_at: null,
    ...overrides,
  };
}

describe('ConflictWorkbench', () => {
  it('validates required reason, submits review decisions (accepted/needs_repair/rejected), handles integrate 422 conflict & success, and executes 3-way conflict actions', async () => {
    const calls: Array<{ path: string; method?: string; body?: Record<string, unknown> }> = [];
    let conflictsState: ConflictReport[] = [];
    let integrateCalls = 0;

    const mockClient = {
      request: vi.fn(
        async (path: string, options?: { method?: string; body?: Record<string, unknown> }) => {
          calls.push({ path, method: options?.method, body: options?.body });

          if (path === '/v1/control-plane/runs/run-99/tasks') {
            return [makeTask()];
          }
          if (path === '/v1/control-plane/runs/run-99/conflicts') {
            return conflictsState;
          }
          if (path === '/v1/control-plane/runs/run-99/tasks/t1/review') {
            return {
              review_id: 'rev-01',
              result_id: 'res-1',
              task_id: 't1',
              run_id: 'run-99',
              decision: options?.body?.decision ?? 'accepted',
              task_status:
                options?.body?.decision === 'accepted'
                  ? 'accepted'
                  : String(options?.body?.decision ?? 'needs_repair'),
              revision: 3,
              created_at: '2026-11-13T00:02:00Z',
            };
          }
          if (path === '/v1/control-plane/runs/run-99/integrate') {
            integrateCalls += 1;
            if (integrateCalls === 1) {
              conflictsState = [makeConflict()];
              throw new ControlPlaneApiError(422, {
                code: 'merge_conflict',
                message: 'Conflito de merge durante integração',
                run_id: 'run-99',
                retryable: true,
                details: { conflicted_files: ['src/app.ts', 'src/config.ts'] },
              });
            }
            return {
              integration_id: 'int-02',
              status: 'succeeded',
              result_sha: '9999merged',
              target_branch: 'main',
              conflict_report_id: null,
            };
          }
          if (path.endsWith('/conflicts/cnf-01/auto-repair')) {
            conflictsState = [makeConflict({ status: 'auto_repair', repair_attempts_used: 1, resolved_sha: 'aaaa1111' })];
            return {
              conflict_id: 'cnf-01',
              integration_id: 'int-01',
              run_id: 'run-99',
              option: 'auto_repair',
              status: 'auto_repair',
              repaired: true,
              attempt_number: 1,
              repair_worktree_path: '/tmp/wt-repair-01',
              repair_branch: 'hydra/repair/cnf-01',
              resolved_sha: 'aaaa1111',
              checks_executed: [],
              failures: [],
              resolved_at: '2026-11-13T00:03:00Z',
            };
          }
          if (path.endsWith('/conflicts/cnf-01/manual')) {
            conflictsState = [makeConflict({ status: 'manual', resolved_sha: 'bbbb2222' })];
            return {
              conflict_id: 'cnf-01',
              integration_id: 'int-01',
              run_id: 'run-99',
              option: 'manual',
              status: 'manual',
              repaired: true,
              attempt_number: 1,
              repair_worktree_path: '/tmp/wt-repair-01',
              repair_branch: 'hydra/repair/cnf-01',
              resolved_sha: 'bbbb2222',
              checks_executed: [],
              failures: [],
              resolved_at: '2026-11-13T00:04:00Z',
            };
          }
          if (path.endsWith('/conflicts/cnf-01/discard')) {
            conflictsState = [makeConflict({ status: 'discarded' })];
            return {
              conflict_id: 'cnf-01',
              integration_id: 'int-01',
              run_id: 'run-99',
              option: 'discarded',
              status: 'discarded',
              repaired: false,
              attempt_number: 0,
              repair_worktree_path: null,
              repair_branch: null,
              resolved_sha: null,
              checks_executed: [],
              failures: [],
              resolved_at: '2026-11-13T00:05:00Z',
            };
          }
          return null;
        },
      ),
    } as unknown as ControlPlaneClient;

    render(<ConflictWorkbench runId="run-99" client={mockClient} />);

    await waitFor(() => {
      expect(screen.getByText('Implementar parser AST')).toBeInTheDocument();
    });

    // Empty reason must block review POST
    fireEvent.click(screen.getByRole('button', { name: 'Enviar revisão' }));
    expect(
      screen.getByText('Justificativa obrigatória para registrar a revisão da tarefa.'),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith('/review'))).toBe(false);

    // Choose needs_repair + enter reason
    fireEvent.click(screen.getByRole('button', { name: /Solicitar reparo/i }));
    fireEvent.change(screen.getByLabelText(/Justificativa da revisão/i), {
      target: { value: 'Faltou cobrir caso de borda.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar revisão' }));

    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.path.endsWith('/tasks/t1/review') &&
            c.body?.decision === 'needs_repair' &&
            c.body?.reason === 'Faltou cobrir caso de borda.' &&
            c.body?.expected_revision === 2,
        ),
      ).toBe(true);
    });

    // Trigger integration -> 422 merge_conflict automatically loads 3-way conflict
    fireEvent.change(screen.getByLabelText(/Branch de destino/i), { target: { value: 'main' } });
    fireEvent.click(screen.getByRole('button', { name: 'Integrar run' }));

    await waitFor(() => {
      expect(screen.getByText(/Conflito de merge durante integração/i)).toBeInTheDocument();
      expect(screen.getByText('0000base')).toBeInTheDocument();
      expect(screen.getByText('1111ours')).toBeInTheDocument();
      expect(screen.getByText('2222theirs')).toBeInTheDocument();
      expect(screen.getByText('const mode = "base";')).toBeInTheDocument();
      expect(screen.getByText('const mode = "ours";')).toBeInTheDocument();
      expect(screen.getByText('const mode = "theirs";')).toBeInTheDocument();
    });

    // Switch conflicted file tab
    fireEvent.click(screen.getByRole('button', { name: 'src/config.ts' }));
    expect(screen.getByText('export const timeout = 30;')).toBeInTheDocument();

    // Auto-repair with valid idempotency key >= 16 chars
    fireEvent.click(screen.getByRole('button', { name: 'Executar auto-reparo' }));
    await waitFor(() => {
      const autoCall = calls.find((c) => c.path.endsWith('/auto-repair'));
      expect(autoCall).toBeDefined();
      expect(String(autoCall?.body?.idempotency_key ?? '').length).toBeGreaterThanOrEqual(16);
      expect(screen.getByText(/aaaa1111/)).toBeInTheDocument();
    });

    // Manual resolve
    fireEvent.change(screen.getByLabelText('Mensagem de commit manual'), {
      target: { value: 'resolve: merge manual' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar resolução manual' }));
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.path.endsWith('/manual') &&
            c.body?.commit_message === 'resolve: merge manual' &&
            c.body?.finalize === true,
        ),
      ).toBe(true);
    });

    // Discard conflict
    fireEvent.change(screen.getByLabelText('Motivo do descarte'), {
      target: { value: 'Substituído por novo run' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Descartar conflito' }));
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.path.endsWith('/discard') && c.body?.reason === 'Substituído por novo run',
        ),
      ).toBe(true);
    });

    // Retry integration -> succeeds
    fireEvent.click(screen.getByRole('button', { name: 'Integrar run' }));
    await waitFor(() => {
      expect(screen.getByText('Integração concluída com sucesso')).toBeInTheDocument();
      expect(screen.getByText(/9999merged/)).toBeInTheDocument();
    });
  });
});

describe('PrPackagePanel', () => {
  it('builds PR package, preserves null diff metrics instead of 0, renders safe markdown, and gates publish on explicit authorization checkbox', async () => {
    const requests: Array<{ path: string; method?: string; body?: Record<string, unknown> }> = [];

    const pkgFixture: PRPackage = {
      package_id: 'pkg-01',
      run_id: 'run-99',
      pr_branch: 'hydra/run-99-pr',
      base_branch: 'main',
      base_sha: 'base1234',
      head_sha: 'head5678',
      description_markdown:
        '# Resumo do PR\n\nMudanças validadas.\n\n<script>alert("xss")</script>',
      commits: [{ sha: 'head5678', message: 'feat: parser' }],
      checks_summary: { total: 3, passed: 3, failed: 0, checks: [] },
      diff_summary: {
        files_changed: 1,
        insertions: null,
        deletions: null,
        files: [{ path: 'src/parser.py', insertions: null, deletions: 4 }],
      },
      metrics: {},
      review_decisions: [],
      artifact_id: 'art-pr-1',
      artifact_path: 'runs/run-99/pr_package.json',
      artifact_sha256: 'deadbeef',
      created_at: '2026-11-13T00:05:00Z',
    };

    const mockClient = {
      request: vi.fn(
        async (path: string, options?: { method?: string; body?: Record<string, unknown> }) => {
          requests.push({ path, method: options?.method, body: options?.body });

          if (path === '/v1/control-plane/runs/run-99/pr-package' && options?.method === 'GET') {
            throw new ControlPlaneApiError(404, {
              code: 'resource_not_found',
              message: 'PR package ainda não existe',
              run_id: 'run-99',
              retryable: false,
            });
          }
          if (path === '/v1/control-plane/runs/run-99/pr-package' && options?.method === 'POST') {
            return pkgFixture;
          }
          if (path === '/v1/control-plane/runs/run-99/pr-package/publish') {
            return {
              package_id: 'pkg-01',
              run_id: 'run-99',
              pr_branch: 'hydra/run-99-pr',
              remote: String(options?.body?.remote ?? 'origin'),
              pushed_sha: 'head5678',
              published: true,
              published_at: '2026-11-13T00:06:00Z',
            };
          }
          return null;
        },
      ),
    } as unknown as ControlPlaneClient;

    render(<PrPackagePanel runId="run-99" client={mockClient} />);

    // 404 initially renders clean empty state
    await waitFor(() => {
      expect(
        screen.getByText(/Nenhum pacote de PR gerado para este run ainda/i),
      ).toBeInTheDocument();
    });

    // Generate package
    fireEvent.change(screen.getByLabelText(/Nome da branch de PR/i), {
      target: { value: 'hydra/run-99-pr' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Gerar pacote de PR' }));

    await waitFor(() => {
      expect(screen.getByText('pkg-01')).toBeInTheDocument();
    });

    // Null insertions/deletions stay 'Desconhecido' / '—', never converted to '0'
    expect(screen.getAllByText('Desconhecido').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('—')).toBeInTheDocument();

    // MarkdownSafeView removes <script>
    const md = screen.getByTestId('markdown-safe-view');
    expect(md.querySelector('script')).toBeNull();
    expect(md).toHaveTextContent('Resumo do PR');

    // Publish button MUST be disabled until operator explicitly checks authorization box
    const publishButton = screen.getByRole('button', { name: 'Publicar pacote de PR' });
    expect(publishButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Remote Git de destino'), {
      target: { value: 'upstream' },
    });
    const authCheckbox = screen.getByRole('checkbox', {
      name: /Autorizo explicitamente a publicação remota/i,
    });
    expect(authCheckbox).not.toBeChecked();
    fireEvent.click(authCheckbox);

    expect(publishButton).toBeEnabled();
    fireEvent.click(publishButton);

    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/runs/run-99/pr-package/publish' &&
            r.body?.authorized === true &&
            r.body?.remote === 'upstream',
        ),
      ).toBe(true);
    });
    expect(screen.getByText(/Publicado em/i)).toBeInTheDocument();
  });
});
