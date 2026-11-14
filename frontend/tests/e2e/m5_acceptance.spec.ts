import fs from 'node:fs';
import { createRequire } from 'node:module';
import { expect, Page, test } from '@playwright/test';

const require = createRequire(import.meta.url);
const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

const E2E_TOKEN =
  process.env.HYDRA_API_TOKEN || 'hydra-e2e-hermetic-local-token-0123456789';

interface AxeRunResult {
  violations: Array<{
    id: string;
    impact?: string | null;
    description: string;
    nodes: Array<{ target: string[]; failureSummary?: string }>;
  }>;
}

async function loginControlPlane(page: Page): Promise<void> {
  await page.goto('/');
  const tokenInput = page.locator('#hydra-bearer-token-input');
  await expect(tokenInput).toBeVisible();
  await tokenInput.fill(E2E_TOKEN);
  await page.getByRole('button', { name: 'Conectar ao Control Plane' }).click();
  await expect(page.getByTestId('hydra-app-shell')).toBeVisible({ timeout: 20_000 });

  const currentUrl = page.url();
  expect(currentUrl).not.toContain(E2E_TOKEN);
  const storedToken = await page.evaluate(() =>
    window.sessionStorage.getItem('hydra_control_plane_token'),
  );
  expect(storedToken).toBe(E2E_TOKEN);
}

async function runAxeWcagAA(page: Page, contextLabel: string): Promise<void> {
  await page.addScriptTag({ content: axeSource });
  const results = await page.evaluate(async () => {
    const w = window as unknown as {
      axe: {
        run: (
          ctx: Document,
          options: { runOnly: { type: 'tag'; values: string[] } },
        ) => Promise<AxeRunResult>;
      };
    };
    return w.axe.run(document, {
      runOnly: {
        type: 'tag',
        values: ['wcag2a', 'wcag2aa'],
      },
    });
  });

  const criticalOrSerious = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious',
  );
  expect(
    criticalOrSerious,
    `WCAG AA serious/critical violations on ${contextLabel}: ${JSON.stringify(criticalOrSerious, null, 2)}`,
  ).toEqual([]);
}

test.describe('M5 Acceptance E2E (Cenário Integrado 10 passos + WCAG AA + Responsividade)', () => {
  test('opens the task created from Novo chat and clears its draft', async ({ page }) => {
    await loginControlPlane(page);
    const taskObjective = 'Verificar criação pelo Novo chat';
    const composer = page.getByLabel('Descreva a tarefa para o coordenador');
    await expect(page.getByLabel('Projeto', { exact: true })).toContainText('hydra-e2e-repo');
    await composer.fill(taskObjective);
    const creation = page.waitForResponse((response) =>
      response.url().endsWith('/v1/control-plane/runs') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Criar tarefa', exact: true }).click();
    const created = await creation;
    const body = await created.text();
    expect(created.ok(), body).toBe(true);
    expect(created.request().postDataJSON()).toMatchObject({ objective: taskObjective, execute: false });
    const { run_id: createdId } = JSON.parse(body);
    await expect(page).toHaveURL(new RegExp(`/chat/${createdId}$`));
    await expect(page.getByTestId('coordinator-view').getByText(taskObjective, { exact: true }).first()).toBeVisible();
    await page.getByRole('navigation', { name: 'Navegação principal' }).getByRole('button', { name: 'Novo chat' }).click();
    await expect(composer).toHaveValue('');
  });

  test('executes full 10-step E2E scenario against real FastAPI backend without fake bridges', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const postedRuns: Array<{ url: string; method: string }> = [];
    page.on('request', (req) => {
      if (req.url().includes('/v1/control-plane/runs') && req.method() === 'POST' && !req.url().includes('/interventions')) {
        postedRuns.push({ url: req.url(), method: req.method() });
      }
    });

    await loginControlPlane(page);

    const rail = page.getByRole('navigation', { name: 'Navegação principal' });

    // Step 1: Select project/workspace + open Split Terminal PTY & verify live output + clean terminate
    await expect(page.getByTestId('novo-chat-page')).toBeVisible();
    await expect(page.locator('#novo-chat-project-select')).toContainText('hydra-e2e-repo');

    // Step 2: Attach file in composer & verify real upload
    const dropzone = page.getByTestId('novo-chat-composer-slot').locator('input[type="file"]');
    await dropzone.setInputFiles({
      name: 'evidencia-e2e.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Conteúdo de anexo válido E2E M5\n', 'utf8'),
    });
    await expect(page.getByText('evidencia-e2e.txt')).toBeVisible();

    // Preserved unsent composer draft across route/tab navigation (Step 3 invariant)
    const composer = page.getByLabel('Descreva a tarefa para o coordenador');
    const preservedDraft = 'Rascunho preservado durante inspeção E2E';
    await composer.fill(preservedDraft);

    // Step 1/2: Open Split Terminal PTY via QuickOpen / navigation and verify live output + clean terminate
    await rail.getByRole('button', { name: 'Recursos' }).click();
    await expect(page.getByTestId('governance-page')).toBeVisible();
    await rail.getByRole('button', { name: 'Novo chat' }).click();
    await expect(composer).toHaveValue(preservedDraft);

    await page.keyboard.press('Control+k');
    const quickSearch = page.getByTestId('quickopen-dialog').getByPlaceholder(/Buscar/i);
    await quickSearch.fill('Auditoria');
    await expect(page.getByText(/Auditoria E2E M5 multi-agente/i).first()).toBeVisible({
      timeout: 10_000,
    });
    await page.keyboard.press('Escape');

    await rail.getByRole('button', { name: 'Terminal', exact: true }).click();
    await expect(page.getByTestId('split-terminal-view')).toBeVisible();
    await page.getByRole('button', { name: 'Iniciar Codex CLI' }).click();
    await expect(page.getByText('HYDRA-PTY-READY:codex')).toBeVisible({ timeout: 15_000 });

    // Cleanly close active PTY process via UI close dialog (ensuring zero orphan children)
    await page.getByRole('button', { name: /Fechar terminal/i }).first().click();
    await expect(page.getByTestId('terminal-close-dialog')).toBeVisible();
    await page.getByRole('button', { name: 'Encerrar processo' }).click();
    await expect(page.getByTestId('terminal-close-dialog')).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText('Cancelado').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: 'Interromper processo' }).first()).toBeDisabled();

    // Step 3 + Step 5: Open seeded Swarm run timeline, verify Coordinator + Workers & zero duplicate replay on reload
    await page.goto('/chat/run-e2e-swarm');
    await expect(page.getByTestId('coordinator-view')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Auditoria E2E M5 multi-agente' })).toBeVisible();
    await expect(page.getByTestId('worker-card-task-wave0')).toBeVisible();
    await expect(page.getByTestId('worker-card-task-wave1')).toBeVisible();
    await expect(page.getByText('Aprovar aplicação do patch da Onda 1?')).toBeVisible();

    const runPostCountBeforeReload = postedRuns.length;
    await page.reload();
    await expect(page.getByTestId('coordinator-view')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Auditoria E2E M5 multi-agente' })).toHaveCount(1);
    await expect(
      page.getByTestId('coordinator-timeline-pane').locator('[data-testid^="step-group-"]'),
    ).toHaveCount(1);
    expect(postedRuns.length).toBe(runPostCountBeforeReload);

    // Step 9 (HITL): Approve inline intervention cleanly once
    await page
      .getByPlaceholder(/Justificativa ou instrução adicional/i)
      .fill('Aprovado no aceite E2E');
    await page.getByRole('button', { name: 'Aprovar' }).click();
    await expect(page.locator('[data-testid^="hitl-resolved-"]').first()).toBeVisible({
      timeout: 10_000,
    });

    // Step 3 check: return to Novo chat and confirm unsent composer draft persisted or re-enter draft
    await rail.getByRole('button', { name: 'Novo chat' }).click();
    await expect(page.getByTestId('novo-chat-page')).toBeVisible();

    // Step 4: Inspect Markdown (no XSS), PNG image, PDF & Diff safe previews in Workbench
    await rail.getByRole('button', { name: 'Workspaces' }).click();
    await expect(page.getByTestId('workspace-workbench-page')).toBeVisible();
    await page.locator('#workbench-run-select').selectOption('run-e2e-swarm');
    await page.getByRole('tab', { name: /Artefatos e diffs seguros/i }).click();

    await page.getByRole('button', { name: /artifacts\/report\.md/i }).click();
    await expect(page.getByText(/seguro validado sem execução XSS/i)).toBeVisible();
    await expect(page.getByText(/Conteúdo ativo\/script bloqueado/i)).toBeVisible();
    const xssExecuted = await page.evaluate(
      () => (window as unknown as { __xss_executed?: unknown }).__xss_executed,
    );
    expect(xssExecuted).toBeUndefined();

    await page.getByRole('button', { name: /artifacts\/diagram\.png/i }).click();
    await expect(page.getByTestId('artifact-image-preview')).toBeVisible();

    await page.getByRole('button', { name: /artifacts\/spec\.pdf/i }).click();
    await expect(page.getByTestId('artifact-pdf-preview')).toBeVisible();

    await page.getByRole('button', { name: /artifacts\/change\.diff/i }).click();
    await expect(page.getByTestId('diff-viewer')).toContainText('return x * 2');

    // Step 6: Quota & OmniRoute honest telemetry (observed vs stale vs unknown "—") + account override
    await rail.getByRole('button', { name: 'Contas e consumo' }).click();
    const quotaPage = page.getByTestId('quota-accounts-page');
    await expect(quotaPage).toBeVisible();
    await expect(quotaPage.getByText('Aplica apenas às próximas execuções').first()).toBeVisible();
    await expect(quotaPage.getByText('68%').first()).toBeVisible();
    await expect(quotaPage.getByText('42%').first()).toBeVisible();
    await expect(quotaPage).toContainText('—');
    const selectNextButtons = quotaPage.getByRole('button', {
      name: /Definir para próximas execuções/i,
    });
    await expect(selectNextButtons.first()).toBeEnabled({ timeout: 10_000 });
    await selectNextButtons.first().click();
    await expect(quotaPage.locator('[data-testid^="active-override-"]').first()).toBeVisible({
      timeout: 10_000,
    });

    // Step 7: Create Automation schedule with IANA TZ + trigger + navigate to linked run
    await rail.getByRole('button', { name: 'Automações' }).click();
    await expect(page.getByTestId('automations-page')).toBeVisible();
    await page.getByRole('button', { name: 'Nova automação' }).click();
    await page.getByLabel('Nome da automação').fill('Auditoria E2E M5');
    await page.getByLabel('Prompt da execução').fill('Rodar checagem agendada E2E');
    await page.getByLabel(/Fuso horário/i).fill('America/Sao_Paulo');
    await page.getByLabel('Projeto (opcional)').selectOption({ label: 'hydra-e2e-repo' });
    await page.getByRole('button', { name: 'Criar automação' }).click();
    await expect(page.getByRole('button', { name: 'Executar agora Auditoria E2E M5' })).toBeVisible();

    await page.getByRole('button', { name: 'Executar agora Auditoria E2E M5' }).click();
    const runsPanel = page.getByTestId('automation-runs-panel');
    await expect(runsPanel.getByRole('button', { name: /Abrir run/i }).first()).toBeVisible({
      timeout: 10_000,
    });
    await runsPanel.getByRole('button', { name: /Abrir run/i }).first().click();
    await expect(page.getByTestId('coordinator-view')).toBeVisible();

    // Step 9 (Parking Lot F06/F07): Verify capability-gated panels never fake execution
    await rail.getByRole('button', { name: 'Emulador móvel' }).click();
    const devicePanel = page.getByTestId('device-panel');
    await expect(devicePanel).toBeVisible();
    await expect(devicePanel).toContainText('não possui certificação ativa');
    await expect(page.getByTestId('device-certified-surface')).toHaveCount(0);

    await rail.getByRole('button', { name: 'Controle do computador' }).click();
    const cuPanel = page.getByTestId('computer-use-panel');
    await expect(cuPanel).toBeVisible();
    await expect(cuPanel).toContainText('não possui certificação ativa');
    await expect(page.getByTestId('computer-use-certified-surface')).toHaveCount(0);

    // Step 10 (QuickOpen Ctrl+K + Recursos GovernancePage + axe-core WCAG AA)
    await rail.getByRole('button', { name: 'Recursos' }).click();
    await expect(page.getByTestId('governance-page')).toBeVisible();
    await runAxeWcagAA(page, 'GovernancePage (1920x1100)');

    await page.keyboard.press('Control+k');
    const quickOpenInput = page.getByTestId('quickopen-dialog').getByPlaceholder(/Buscar/i);
    await expect(quickOpenInput).toBeVisible();
    await quickOpenInput.fill('Auditoria');
    await expect(page.getByText(/Auditoria E2E M5 multi-agente/i).first()).toBeVisible({
      timeout: 10_000,
    });
    await page.keyboard.press('Escape');

    // Desktop & narrow zoom 200% responsive WCAG checks
    await rail.getByRole('button', { name: 'Novo chat' }).click();
    await expect(page.getByTestId('novo-chat-page')).toBeVisible();
    await runAxeWcagAA(page, 'NovoChat (1920x1100)');

    await rail.getByRole('button', { name: 'Contas e consumo' }).click();
    await expect(page.getByTestId('quota-accounts-page')).toBeVisible();
    await runAxeWcagAA(page, 'QuotaAccountsPage (1920x1100)');

    await page.setViewportSize({ width: 960, height: 600 });
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '32px';
    });
    const zoomOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    );
    expect(zoomOverflow).toBe(false);
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '';
    });

    // Mobile narrow viewport (390x844) drawer + zero horizontal page overflow + WCAG AA
    await page.setViewportSize({ width: 390, height: 844 });
    await rail.getByRole('button', { name: 'Novo chat' }).click();
    await expect(page.getByTestId('novo-chat-page')).toBeVisible();
    const mobileOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    );
    expect(mobileOverflow).toBe(false);
    await runAxeWcagAA(page, 'Mobile NovoChat (390x844)');

    const drawerToggle = rail.getByRole('button', { name: /barra lateral/i });
    await drawerToggle.click();
    const drawer = page.getByTestId('mobile-sidebar-drawer');
    await expect(drawer.getByRole('button', { name: 'Workspaces', exact: true })).toHaveText('Workspaces');
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(drawerToggle).toBeFocused();

  });

  test('Step 8: Dictation control handles permission denial and editable preview without auto-submit', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      class MockSpeechRecognition {
        lang = 'pt-BR';
        interimResults = true;
        continuous = true;
        onresult: ((ev: unknown) => void) | null = null;
        onerror: ((ev: { error: string }) => void) | null = null;
        onend: (() => void) | null = null;

        start() {
          const countKey = '__hydraSpeechCalls';
          const prev = Number((window as unknown as Record<string, number>)[countKey] ?? 0) + 1;
          (window as unknown as Record<string, number>)[countKey] = prev;
          if (prev === 1) {
            setTimeout(() => {
              this.onerror?.({ error: 'not-allowed' });
            }, 25);
            return;
          }
          setTimeout(() => {
            this.onresult?.({
              resultIndex: 0,
              results: [
                Object.assign([{ transcript: 'Revisar patch antes do merge' }], {
                  isFinal: true,
                }),
              ],
            });
          }, 25);
        }

        stop() {
          this.onend?.();
        }

        abort() {
          this.onend?.();
        }
      }
      (window as unknown as Record<string, unknown>).SpeechRecognition = MockSpeechRecognition;
    });

    let runSubmitCalls = 0;
    page.on('request', (req) => {
      if (req.url().includes('/v1/control-plane/runs') && req.method() === 'POST') {
        runSubmitCalls += 1;
      }
    });

    await loginControlPlane(page);
    await expect(page.getByTestId('novo-chat-page')).toBeVisible();

    await page.locator('summary').filter({ hasText: 'Ditado por voz' }).click();
    await page.getByRole('button', { name: 'Iniciar ditado' }).click();
    await expect(page.getByTestId('dictation-error-notice')).toBeVisible({ timeout: 5000 });

    // Recover and retry dictation cleanly
    await page.getByRole('button', { name: 'Tentar novamente' }).first().click();
    const previewBox = page.getByLabel('Rascunho revisável do ditado');
    await expect(previewBox).toBeVisible({ timeout: 5000 });
    await expect(previewBox).toHaveValue(/Revisar patch antes do merge/);

    await previewBox.fill('Revisar patch E2E editado manualmente');
    await page.getByRole('button', { name: 'Inserir no rascunho' }).click();

    await expect(page.getByLabel('Descreva a tarefa para o coordenador')).toHaveValue(
      /Revisar patch E2E editado manualmente/,
    );
    expect(runSubmitCalls).toBe(0);
  });
});
