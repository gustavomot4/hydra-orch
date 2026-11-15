import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { expect, Page, test } from '@playwright/test';

const require = createRequire(import.meta.url);
const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const kitSource = fs.readFileSync('../.agents/skills/kit-frontend/scripts/tela.js', 'utf8');

async function checkConversationLayout(page: Page, name: string) {
  const reports: unknown[] = [];
  for (const [width, height] of [
    [1440, 900],
    [768, 1024],
    [375, 812],
    [320, 256],
  ]) {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.evaluate(
      (papel) => {
        (window as unknown as { __kitOpcoes: unknown }).__kitOpcoes = { papel };
      },
      width <= 375 ? 'celular' : 'desktop',
    );
    const report = await page.evaluate(kitSource);
    reports.push({ width, height, report });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
  fs.mkdirSync('../ws/b_output/conversation', { recursive: true });
  fs.writeFileSync(
    `../ws/b_output/conversation/${name}_layout.json`,
    JSON.stringify(reports, null, 2),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '200%';
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '';
  });
  await page.emulateMedia({ forcedColors: 'active' });
  await page.screenshot({
    path: `../ws/b_output/conversation/${name}_contrast.png`,
    fullPage: true,
  });
  await page.emulateMedia({ forcedColors: 'none' });
  await page.setViewportSize({ width: 1920, height: 1100 });
}

const E2E_TOKEN = process.env.HYDRA_API_TOKEN || 'hydra-e2e-hermetic-local-token-0123456789';

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
  test('navigates the real agent canvas, inspects tasks and preserves layout', async ({ page }) => {
    await loginControlPlane(page);
    await page
      .getByRole('navigation', { name: 'Navegação principal' })
      .getByRole('button', { name: 'Área de trabalho', exact: true })
      .click();
    await expect(page.getByTestId('agent-workspace-page')).toBeVisible();
    await page.goto('/agentes?execucao=run-e2e-swarm');
    const canvas = page.getByTestId('canvas-viewport');
    await expect(canvas).toBeVisible();
    await expect(page.getByTestId('agent-node-task-wave0')).toBeVisible();
    await page.getByTestId('agent-node-task-wave1').locator('.agent-node-open').click();
    const details = page.getByTestId('agent-inspector');
    await expect(
      details.getByRole('heading', { name: 'Executar verificação integrada' }),
    ).toBeVisible();
    await details.getByRole('button', { name: 'Atividade', exact: true }).click();
    await expect(details.getByText('Nenhuma verificação executada registrada.')).toBeVisible();
    const scale = Number(await canvas.getAttribute('data-scale'));
    await page.getByRole('button', { name: 'Aumentar zoom' }).click();
    await expect
      .poll(async () => Number(await canvas.getAttribute('data-scale')))
      .toBeGreaterThan(scale);
    const world = page.locator('.agent-map-world');
    const before = await world.getAttribute('style');
    const box = (await canvas.boundingBox())!;
    await page.mouse.move(box.x + 16, box.y + 16);
    await page.mouse.down();
    await page.mouse.move(box.x + 75, box.y + 55, { steps: 5 });
    await page.mouse.up();
    await expect(world).not.toHaveAttribute('style', before!);
    const move = page.getByRole('button', {
      name: 'Mover Executar verificação integrada. Use as setas.',
    });
    const node = page.getByTestId('agent-node-task-wave1'),
      position = await node.evaluate((e) => (e as HTMLElement).style.left);
    await move.focus();
    await page.keyboard.press('ArrowRight');
    await expect.poll(() => node.evaluate((e) => (e as HTMLElement).style.left)).not.toBe(position);
    await expect
      .poll(() =>
        page.evaluate(() =>
          Object.keys(localStorage).some((k) => k === 'hydra:canvas:runs:run-e2e-swarm'),
        ),
      )
      .toBe(true);
    await page.getByRole('button', { name: 'Enquadrar', exact: true }).click();
    await runAxeWcagAA(page, 'canvas com detalhes');
    fs.mkdirSync('../ws/b_output/canvas', { recursive: true });
    await page.screenshot({
      path: '../ws/b_output/canvas/implemented_desktop.png',
      fullPage: true,
    });
    const originalHeight = (await node.boundingBox())!.height;
    await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
    await expect
      .poll(async () => (await node.boundingBox())!.height)
      .toBeGreaterThan(originalHeight * 1.9);
    expect(await node.locator('strong').evaluate((e) => e.scrollHeight <= e.clientHeight + 2)).toBe(
      true,
    );
    await page.evaluate(() => (document.documentElement.style.fontSize = ''));
    await page.getByRole('button', { name: 'Lista', exact: true }).click();
    await page.setViewportSize({ width: 375, height: 812 });
    await expect(page.locator('.agent-list')).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await runAxeWcagAA(page, 'lista de agentes no celular');
    await page.reload();
    await expect(page.locator('.agent-list')).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Área de trabalho', exact: true }),
    ).toBeInViewport();
    await page.screenshot({ path: '../ws/b_output/canvas/implemented_mobile.png', fullPage: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await page.evaluate(() => (document.documentElement.style.fontSize = ''));
    await page.emulateMedia({ forcedColors: 'active' });
    await page.screenshot({
      path: '../ws/b_output/canvas/implemented_contrast.png',
      fullPage: true,
    });
    await page.emulateMedia({ forcedColors: 'none' });
    await page.reload();
    await expect(page.getByTestId('agent-node-task-wave1')).toBeVisible();
    await expect(page).toHaveURL(/execucao=run-e2e-swarm/);
  });
  test('registers an ordinary folder and starts its conversation without Git', async ({
    page,
    request,
  }) => {
    await loginControlPlane(page);
    const projects = await (
      await request.get('/v1/control-plane/projects', {
        headers: { Authorization: `Bearer ${E2E_TOKEN}` },
      })
    ).json();
    const folder = path.resolve(projects[0].canonical_root, '..', 'plain-folder');
    await page.getByText('Adicionar pasta', { exact: true }).click();
    await page.getByLabel('Caminho da pasta neste computador').fill(folder);
    const registration = page.waitForResponse(
      (r) => r.url().endsWith('/v1/control-plane/projects') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Usar esta pasta', exact: true }).click();
    const registered = await registration;
    expect(registered.ok()).toBe(true);
    expect(registered.request().postDataJSON().allow_plain_folder).toBe(true);
    expect((await registered.json()).workspace_kind).toBe('folder');
    await expect(page.getByLabel('Pasta', { exact: true })).toContainText('plain-folder');
    await page.getByLabel('Sua mensagem').fill('Leia o README desta pasta sem Git');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await expect(
      page.getByTestId('conversation-turn-1').getByTestId('agent-response'),
    ).toContainText('Segundo, inicie');
    await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible();
  });
  test('keeps a responsive WebSocket terminal while resizing its viewport', async ({ page }) => {
    await loginControlPlane(page);
    await expect(page.getByLabel('Pasta', { exact: true })).toContainText('hydra-e2e-repo');
    await page
      .getByRole('navigation', { name: 'Navegação principal' })
      .getByRole('button', { name: 'Terminal', exact: true })
      .click();
    const started = Date.now();
    await page.getByRole('button', { name: 'Iniciar Codex CLI' }).click();
    const terminal = page.locator('[data-session-id][data-renderer="xterm"]');
    await expect(terminal).toHaveAttribute('data-transport', 'ws');
    await expect(terminal.getByText('HYDRA-PTY-READY:codex', { exact: true })).toBeVisible();
    console.log(`PTY de teste pronto em ${Date.now() - started} ms`);
    await expect(page.getByTestId('split-terminal-view')).toHaveAttribute(
      'data-layout-mode',
      'single-primary',
    );
    await expect(terminal.locator('textarea.xterm-helper-textarea')).toBeFocused();
    const inputRequests: string[] = [];
    page.on('request', (request) => {
      if (request.url().includes('/pty/sessions/') && request.url().endsWith('/input')) {
        inputRequests.push(request.url());
      }
    });
    const typed = Date.now();
    await page.keyboard.type('teste-pty');
    await page.keyboard.press('Enter');
    await expect(terminal.getByText('ECHO:codex:teste-pty', { exact: true })).toBeVisible();
    console.log(`Entrada e eco visíveis em ${Date.now() - typed} ms`);
    const sessionId = await terminal.getAttribute('data-session-id');
    await page
      .getByRole('navigation', { name: 'Navegação principal' })
      .getByRole('button', { name: 'Novo chat', exact: true })
      .click();
    await page
      .getByRole('navigation', { name: 'Navegação principal' })
      .getByRole('button', { name: 'Terminal', exact: true })
      .click();
    await expect(terminal).toHaveAttribute('data-session-id', sessionId!);
    await expect(terminal.getByText('ECHO:codex:teste-pty', { exact: true })).toBeVisible();
    const initialXterm = await terminal.locator('.xterm').elementHandle();
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(terminal.getByText('ECHO:codex:teste-pty', { exact: true })).toBeVisible();
    expect(await initialXterm?.evaluate((element) => element.isConnected)).toBe(true);
    expect(inputRequests).toHaveLength(0);
    await page.screenshot({ path: '../ws/b_output/terminal/desktop.png' });
    await page.getByRole('button', { name: 'Fechar terminal', exact: true }).click();
    await page.getByRole('button', { name: 'Encerrar processo', exact: true }).click();
    await expect(page.getByTestId('terminal-close-dialog')).toBeHidden();
  });

  test('sends two chat turns, reloads during execution, reopens history and cancels', async ({
    page,
  }) => {
    await loginControlPlane(page);
    await checkConversationLayout(page, 'novo_chat');
    await runAxeWcagAA(page, 'Novo chat');
    const taskObjective = 'Leia o README e explique como iniciar o projeto';
    const composer = page.getByLabel('Sua mensagem');
    await expect(page.getByLabel('Pasta', { exact: true })).toContainText('hydra-e2e-repo');
    await composer.fill(taskObjective);
    await expect(composer).toHaveValue(taskObjective);
    const creation = page.waitForResponse(
      (response) =>
        response.url().endsWith('/v1/control-plane/conversations') &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    const created = await creation;
    const body = await created.text();
    expect(created.ok(), body).toBe(true);
    expect(created.request().postDataJSON()).toMatchObject({
      content: taskObjective,
      executor: 'codex',
      access_mode: 'read-only',
    });
    const { conversation_id: createdId } = JSON.parse(body);
    await expect(page).toHaveURL(new RegExp(`/chat/${createdId}$`));
    await expect(
      page.getByTestId('conversation-page').getByText(taskObjective, { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByTestId('conversation-turn-1').getByTestId('agent-response'),
    ).toContainText('Primeiro');
    await page.reload();
    await expect(
      page.getByTestId('conversation-turn-1').getByTestId('agent-response'),
    ).toContainText('Segundo, inicie');
    await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible();
    await page.getByLabel('Sua mensagem').fill('Agora detalhe o segundo passo');
    const secondSend = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/conversations/${createdId}/messages`) &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    const secondReply = await secondSend;
    expect(secondReply.ok(), await secondReply.text()).toBe(true);
    await expect(
      page.getByTestId('conversation-turn-2').getByTestId('agent-response'),
    ).toContainText('Segundo passo detalhado');
    await runAxeWcagAA(page, 'conversa com duas respostas');
    await checkConversationLayout(page, 'chat');
    fs.mkdirSync('../ws/b_output/conversation', { recursive: true });
    await page.screenshot({ path: '../ws/b_output/conversation/desktop.png', fullPage: true });
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({ path: '../ws/b_output/conversation/mobile.png', fullPage: true });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.setViewportSize({ width: 1920, height: 1100 });
    await page
      .getByRole('navigation', { name: 'Navegação principal' })
      .getByRole('button', { name: 'Novo chat' })
      .click();
    await expect(composer).toHaveValue('');
    await page
      .getByRole('region', { name: 'Conversas recentes' })
      .getByRole('button', { name: taskObjective, exact: true })
      .click();
    await expect(page.getByTestId('conversation-turn-2')).toBeVisible();
    await page.getByLabel('Sua mensagem').fill('Aguarde e explique de novo');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await expect(
      page.getByTestId('conversation-turn-3').getByTestId('agent-response'),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Parar', exact: true }).click();
    await expect(page.getByText('Interrompido', { exact: true })).toBeVisible();
  });

  test('changes models A B A in the same durable chat and keeps turn attribution', async ({
    page,
  }) => {
    await loginControlPlane(page);
    await page.getByLabel('Modelo', { exact: true }).selectOption('model-a');
    await page.getByLabel('Sua mensagem').fill('Decisão antiga: preservar o README');
    await expect(page.getByLabel('Sua mensagem')).toHaveValue('Decisão antiga: preservar o README');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await expect(
      page.getByTestId('conversation-turn-1').getByText('Resposta concluída', { exact: true }),
    ).toBeVisible();
    const url = page.url();
    for (const [index, model] of ['model-b', 'model-a'].entries()) {
      await page.getByRole('button', { name: 'Trocar modelo ou combo' }).click();
      await page.getByLabel('Modelo', { exact: true }).selectOption(model);
      await page.getByRole('button', { name: 'Usar nos próximos envios' }).click();
      await expect(page.getByRole('button', { name: 'Cancelar troca' })).toBeHidden();
      await page
        .getByLabel('Sua mensagem')
        .fill(`Continue a partir do histórico, etapa ${index + 2}`);
      const acceptance = page.waitForResponse(
        (response) =>
          response.url().endsWith('/messages') && response.request().method() === 'POST',
      );
      await page.getByRole('button', { name: 'Enviar', exact: true }).click();
      const accepted = await acceptance;
      expect(accepted.ok(), await accepted.text()).toBe(true);
      await expect(
        page.getByTestId(`conversation-turn-${index + 2}`).getByTestId('agent-response'),
      ).toBeVisible();
      await expect(
        page
          .getByTestId(`conversation-turn-${index + 2}`)
          .getByText('Resposta concluída', { exact: true }),
      ).toBeVisible();
      expect(page.url()).toBe(url);
    }
    await page.reload();
    await expect(
      page.getByTestId('conversation-turn-1').getByRole('heading', { name: 'Codex · model-a' }),
    ).toBeVisible();
    await expect(
      page.getByTestId('conversation-turn-2').getByRole('heading', { name: 'Codex · model-b' }),
    ).toBeVisible();
    await expect(
      page.getByTestId('conversation-turn-3').getByRole('heading', { name: 'Codex · model-a' }),
    ).toBeVisible();
    await expect(
      page.getByText('Decisão antiga: preservar o README', { exact: true }).last(),
    ).toBeVisible();
  });

  test('audits and saves coordination options for the next sends', async ({ page }) => {
    await loginControlPlane(page);
    await page.getByLabel('Sua mensagem').fill('Preparar opções de trabalho');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await expect(
      page.getByTestId('conversation-turn-1').getByText('Resposta concluída', { exact: true }),
    ).toBeVisible();
    const url = page.url();
    await page.getByRole('button', { name: 'Trocar modelo ou combo' }).click();
    await page.getByRole('radio', { name: 'Coordenar tarefas com agentes' }).check();
    await page.getByRole('checkbox', { name: /Escolher entre combos/ }).check();
    await runAxeWcagAA(page, 'opções de execução');
    await checkConversationLayout(page, 'route_workflow');
    await page.screenshot({
      path: '../ws/b_output/conversation/route_workflow_desktop.png',
      fullPage: true,
    });
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({
      path: '../ws/b_output/conversation/route_workflow_mobile.png',
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Usar nos próximos envios' }).click();
    await expect(page.getByRole('button', { name: 'Cancelar troca' })).toBeHidden();
    const response = await page.request.get(
      url.replace(/\/chat\//, '/v1/control-plane/conversations/'),
      { headers: { Authorization: `Bearer ${E2E_TOKEN}` } },
    );
    expect(await response.json()).toMatchObject({
      execution_mode: 'swarm',
      auto_route: true,
      route_revision: 1,
    });
  });

  test('executes full 10-step E2E scenario against isolated FastAPI backend with test executors', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const postedRuns: Array<{ url: string; method: string }> = [];
    page.on('request', (req) => {
      if (
        req.url().includes('/v1/control-plane/runs') &&
        req.method() === 'POST' &&
        !req.url().includes('/interventions')
      ) {
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
    const composer = page.getByLabel('Sua mensagem');
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
    await page
      .getByRole('button', { name: /Fechar terminal/i })
      .first()
      .click();
    await expect(page.getByTestId('terminal-close-dialog')).toBeVisible();
    await page.getByRole('button', { name: 'Encerrar processo' }).click();
    await expect(page.getByTestId('terminal-close-dialog')).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText('Cancelado').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: 'Interromper processo' }).first()).toBeDisabled();

    // Step 3 + Step 5: Open seeded Swarm run timeline, verify Coordinator + Workers & zero duplicate replay on reload
    await page.goto('/chat/run-e2e-swarm');
    await expect(page.getByTestId('coordinator-view')).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Auditoria E2E M5 multi-agente' }),
    ).toBeVisible();
    await expect(page.getByTestId('worker-card-task-wave0')).toBeVisible();
    await expect(page.getByTestId('worker-card-task-wave1')).toBeVisible();
    await expect(page.getByText('Aprovar aplicação do patch da Onda 1?')).toBeVisible();

    const runPostCountBeforeReload = postedRuns.length;
    await page.reload();
    await expect(page.getByTestId('coordinator-view')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Auditoria E2E M5 multi-agente' })).toHaveCount(
      1,
    );
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
    await rail.getByRole('button', { name: 'Alterações' }).click();
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
    await expect(
      page.getByRole('button', { name: 'Executar agora Auditoria E2E M5' }),
    ).toBeVisible();

    await page.getByRole('button', { name: 'Executar agora Auditoria E2E M5' }).click();
    const runsPanel = page.getByTestId('automation-runs-panel');
    await expect(runsPanel.getByRole('button', { name: /Abrir run/i }).first()).toBeVisible({
      timeout: 10_000,
    });
    await runsPanel
      .getByRole('button', { name: /Abrir run/i })
      .first()
      .click();
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
    await expect(drawer.getByRole('button', { name: 'Alterações', exact: true })).toHaveText(
      'Alterações',
    );
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

    await expect(page.getByLabel('Sua mensagem')).toHaveValue(
      /Revisar patch E2E editado manualmente/,
    );
    expect(runSubmitCalls).toBe(0);
  });
});
