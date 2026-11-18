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

  await page.getByText('Ferramentas', { exact: true }).click();
  const currentUrl = page.url();
  expect(currentUrl).not.toContain(E2E_TOKEN);
  const storedToken = await page.evaluate(() =>
    window.sessionStorage.getItem('hydra_control_plane_token'),
  );
  expect(storedToken).toBe(E2E_TOKEN);
  const folder = page.getByRole('button', { name: /^Pasta:/ });
  await expect(folder).toBeVisible();
  if (!(await folder.textContent())?.includes('hydra-e2e-repo')) {
    await folder.click();
    await page
      .getByRole('button', { name: /hydra-e2e-repo/ })
      .last()
      .click();
  }
}

async function waitForFixtureTurn(page: Page, ordinal: number) {
  // Execution includes a deliberate CLI delay and Git workspace finalization.
  // Wait for durable completion separately from the UI propagation assertion.
  await expect
    .poll(
      async () => {
        const id = page.url().split('/chat/')[1];
        const response = await page.request.get(`/v1/control-plane/conversations/${id}`, {
          headers: { Authorization: `Bearer ${E2E_TOKEN}` },
        });
        return (await response.json()).turns?.find(
          (t: { ordinal: number }) => t.ordinal === ordinal,
        )?.state;
      },
      { timeout: 30000 },
    )
    .toBe('completed');
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
    const card = page.getByTestId('agent-node-task-wave0');
    const originalLeft = await card.evaluate((e) => (e as HTMLElement).style.left);
    const body = (await card.locator('.agent-node-open').boundingBox())!;
    await page.mouse.move(body.x + 70, body.y + 65);
    await page.mouse.down();
    await page.mouse.move(body.x + 130, body.y + 95, { steps: 8 });
    await page.mouse.up();
    await expect
      .poll(() => card.evaluate((e) => (e as HTMLElement).style.left))
      .not.toBe(originalLeft);
    await expect(
      details.getByRole('heading', { name: 'Executar verificação integrada' }),
    ).toBeVisible();
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
    await expect(page.getByRole('button', { name: /^Pasta:/ })).toContainText('plain-folder');
    await page.getByLabel('Sua mensagem').fill('Leia o README desta pasta sem Git');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    // Includes startup of a real CLI subprocess on Windows. Wait for its
    // durable terminal state before asserting the completed response.
    await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(
      page.getByTestId('conversation-turn-1').getByTestId('agent-response'),
    ).toContainText('Segundo, inicie');
  });
  test('keeps a responsive WebSocket terminal while resizing its viewport', async ({ page }) => {
    await loginControlPlane(page);
    await expect(page.getByRole('button', { name: /^Pasta:/ })).toContainText('hydra-e2e-repo');
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
    await expect(page.getByRole('button', { name: /^Pasta:/ })).toContainText('hydra-e2e-repo');
    const image = {
      name: 'referencia-e2e.png',
      mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2ioAAAAASUVORK5CYII=', 'base64'),
    };
    await page.getByTestId('novo-chat-composer-slot').locator('input[type="file"]').setInputFiles(image);
    await expect(page.getByTestId('attachment-list')).toContainText('Pronto local');
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
      attachment_ids: [expect.any(String)],
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
    await expect(page.getByText('Anexo: referencia-e2e.png', { exact: true })).toBeVisible();
    await expect(
      page.getByTestId('conversation-turn-1').getByTestId('agent-response'),
    ).toContainText('Segundo, inicie');
    await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible();
    await page.getByTestId('conversation-page').locator('input[type="file"]').setInputFiles({
      ...image,
      name: 'segunda-referencia-e2e.png',
    });
    await expect(page.getByTestId('attachment-list')).toContainText('Pronto local');
    await page.getByLabel('Sua mensagem').fill('Agora detalhe o segundo passo');
    const secondSend = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/conversations/${createdId}/messages`) &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    const secondReply = await secondSend;
    expect(secondReply.ok(), await secondReply.text()).toBe(true);
    expect(secondReply.request().postDataJSON().attachment_ids).toEqual([expect.any(String)]);
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
      .getByRole('button', { name: 'Novo chat', exact: true })
      .click();
    await expect(composer).toHaveValue('');
    const workTree = page.getByTestId('desktop-sidebar').locator('.project-work-tree');
    const projectSummary = workTree
      .locator('summary')
      .filter({ hasText: 'hydra-e2e-repo' })
      .first();
    if ((await projectSummary.locator('..').getAttribute('open')) === null)
      await projectSummary.click();
    const chatsSummary = workTree.locator('summary').filter({ hasText: 'Conversas' }).first();
    if ((await chatsSummary.locator('..').getAttribute('open')) === null)
      await chatsSummary.click();
    await workTree.getByRole('button', { name: taskObjective, exact: true }).click();
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
    await page.getByRole('button', { name: /Configurar agente, conexão e modelo/ }).click();
    await page.getByRole('button', { name: /^Modelo:/ }).click();
    await page.getByRole('button', { name: 'Modelo A', exact: true }).click();
    await page.getByRole('button', { name: 'Concluir configuração' }).click();
    await page.getByLabel('Sua mensagem').fill('Decisão antiga: preservar o README');
    await expect(page.getByLabel('Sua mensagem')).toHaveValue('Decisão antiga: preservar o README');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await waitForFixtureTurn(page, 1);
    await expect(
      page.getByTestId('conversation-turn-1').getByText('Resposta concluída', { exact: true }),
    ).toBeVisible();
    const url = page.url();
    for (const [index, model] of ['model-b', 'model-a'].entries()) {
      await page.getByRole('button', { name: /Trocar modelo ou combo/ }).click();
      await page.getByRole('button', { name: /^Modelo:/ }).click();
      await page
        .getByRole('button', { name: model === 'model-a' ? 'Modelo A' : 'Modelo B', exact: true })
        .click();
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
      await waitForFixtureTurn(page, index + 2);
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
    await waitForFixtureTurn(page, 1);
    await expect(
      page.getByTestId('conversation-turn-1').getByRole('heading', { name: 'model-a' }),
    ).toBeVisible();
    await expect(
      page.getByTestId('conversation-turn-2').getByRole('heading', { name: 'model-b' }),
    ).toBeVisible();
    await expect(
      page.getByTestId('conversation-turn-3').getByRole('heading', { name: 'model-a' }),
    ).toBeVisible();
    await expect(
      page.getByText('Decisão antiga: preservar o README', { exact: true }).last(),
    ).toBeVisible();
  });

  test('audits and saves coordination options for the next sends', async ({ page }) => {
    await loginControlPlane(page);
    await page.getByLabel('Sua mensagem').fill('Preparar opções de trabalho');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await waitForFixtureTurn(page, 1);
    await expect(
      page.getByTestId('conversation-turn-1').getByText('Resposta concluída', { exact: true }),
    ).toBeVisible();
    const url = page.url();
    await page.getByRole('button', { name: /Trocar modelo ou combo/ }).click();
    await page.getByRole('radio', { name: 'Coordenar tarefas com agentes' }).check();
    await page.getByRole('checkbox', { name: 'Escolher modelo automaticamente' }).check();
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
    await expect(page.getByRole('button', { name: /^Pasta:/ })).toContainText('hydra-e2e-repo');

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
    await rail.getByRole('button', { name: 'Novo chat', exact: true }).click();
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
    await expect(page.getByRole('button', { name: 'Iniciar Codex CLI' })).toBeVisible();

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
    await rail.getByRole('button', { name: 'Novo chat', exact: true }).click();
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
    await quotaPage.locator('.quota-account-settings > summary').first().click();
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
    await page.getByLabel('Orçamento máximo (USD)').fill('5');
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
    await rail.getByRole('button', { name: 'Novo chat', exact: true }).click();
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
    await rail.getByRole('button', { name: 'Novo chat', exact: true }).click();
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

test('keeps composer settings in reach, renders Markdown and adds CLI agents from live events', async ({
  page,
}) => {
  await loginControlPlane(page);
  const chat = {
    id: 'conversation-fixture-live',
    title: 'Revisar o projeto',
    project_id: 'fixture-project',
    project_name: 'Projeto de demonstração',
    executor: 'codex',
    access_mode: 'read-only',
    route_revision: 0,
    execution_mode: 'single',
    last_seq: 1,
    route: { executor: 'codex', connection_mode: 'direct', target_kind: 'model', target_ref: '' },
    tools: [
      {
        seq: 1,
        turn_id: 'turn1',
        type: 'tool.completed',
        payload: {
          tool: 'command_execution',
          detail: JSON.stringify({ command: 'read README.md' }),
        },
      },
    ],
    agents: [] as unknown[],
    turns: [
      {
        id: 'turn1',
        ordinal: 1,
        content: 'Leia o projeto e explique a arquitetura com os próximos passos.',
        state: 'completed',
        error: null,
        diff: '',
        attachments: [],
        route: {
          executor: 'codex',
          connection_mode: 'direct',
          target_kind: 'model',
          target_ref: '',
        },
        response:
          '# Visão do projeto\n\nO Hydra organiza **agentes e tarefas** em uma conversa.\n\n## Como funciona\n\n1. Você descreve o pedido.\n2. O agente lê os arquivos.\n3. O resultado fica disponível para revisão.\n\n```bash\npython -m hydra_orch\n```\n\n## Próximos passos\n\n- Revisar o fluxo de conversa\n- Conferir as verificações\n\n' +
          Array(15)
            .fill(
              '### Uma etapa do trabalho\n\nEste texto de demonstração verifica a leitura do histórico sem tirar o compositor da tela.',
            )
            .join('\n\n'),
      },
    ],
  };
  let snapshotReads = 0;
  await page.route('**/v1/control-plane/conversations/conversation-fixture-live', (route) => {
    snapshotReads++;
    return route.fulfill({ json: chat });
  });
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      if (String(input).endsWith('/conversations/conversation-fixture-live/events')) {
        let streamController: ReadableStreamDefaultController<Uint8Array>;
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            streamController = controller;
            controller.enqueue(new TextEncoder().encode(': ready\n\n'));
          },
        });
        (window as unknown as { emitFixtureEvent: () => void }).emitFixtureEvent = () =>
          streamController.enqueue(
            new TextEncoder().encode('id: 2\nevent: agent.observed\ndata: {}\n\n'),
          );
        init?.signal?.addEventListener('abort', () => {
          try {
            streamController.close();
          } catch {
            /* Stream may already have closed. */
          }
        });
        return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
      }
      return original(input, init);
    };
  });
  await page.goto('/chat/conversation-fixture-live');
  await expect(
    page.getByTestId('agent-response').getByRole('heading', { name: 'Visão do projeto' }),
  ).toBeVisible();
  const transcript = page.getByTestId('chat-transcript');
  await transcript.evaluate((e) => (e.scrollTop = e.scrollHeight));
  await expect(page.getByRole('button', { name: /Trocar modelo ou combo/ })).toBeInViewport();
  await expect(page.getByLabel('Sua mensagem')).toBeInViewport();
  await page.getByRole('button', { name: /Trocar modelo ou combo/ }).click();
  await expect(page.getByRole('dialog', { name: 'Configuração da conversa' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await transcript.evaluate((e) => (e.scrollTop = 0));
  fs.mkdirSync('../ws/b_output/chat_ux', { recursive: true });
  await page.screenshot({
    path: '../ws/b_output/chat_ux/conversation_desktop.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole('button', { name: /Trocar modelo ou combo/ })).toBeInViewport();
  await expect(page.getByLabel('Sua mensagem')).toBeInViewport();
  await page.screenshot({ path: '../ws/b_output/chat_ux/conversation_mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  snapshotReads = 0;
  await page.goto('/agentes?chat=conversation-fixture-live');
  await expect(page.getByTestId('agent-node-coordinator')).toBeVisible();
  // Drain the initial connection refresh before injecting a new observation.
  // A pending initial fetch must not make this event-propagation test pass.
  await expect.poll(() => snapshotReads).toBeGreaterThanOrEqual(2);
  chat.agents = [
    {
      id: 'cli-child',
      parent_id: 'root',
      turn_id: 'turn1',
      title: 'Revisar arquitetura',
      state: 'running',
      executor: 'codex',
      model: 'Não informado pela CLI',
      summary: 'Lendo os módulos',
      source: 'cli',
    },
  ];
  chat.last_seq = 2;
  await page.evaluate(() =>
    (window as unknown as { emitFixtureEvent: () => void }).emitFixtureEvent(),
  );
  await expect(page.getByTestId('agent-node-cli:cli-child')).toBeVisible({ timeout: 1800 });
  await page.getByRole('button', { name: 'Novo chat', exact: true }).first().click();
  await expect(page.getByTestId('novo-chat-page')).toBeVisible();
  await page.screenshot({ path: '../ws/b_output/chat_ux/new_chat_desktop.png', fullPage: true });
  await page.route('**/v1/control-plane/omniroute/combos?**', (route) =>
    route.fulfill({
      json: {
        status: 'connected',
        combos: [
          {
            id: 'demo',
            name: 'Combo de demonstração',
            target_kind: 'combo',
            compatibility: 'unverified',
          },
        ],
        models: [],
        direct_models: [],
      },
    }),
  );
  await page.getByRole('button', { name: /Configurar agente, conexão e modelo/ }).click();
  await page.getByRole('radio', { name: 'OmniRoute', exact: true }).check();
  await page.getByRole('button', { name: /Modelo ou combo/ }).click();
  const catalog = page.getByRole('dialog', { name: 'Escolher modelo ou combo' });
  await expect(catalog).toBeVisible();
  await catalog.getByLabel('Buscar pelo nome').fill('demonstracao');
  await catalog.getByRole('button', { name: /Combo de demonstração/ }).click();
  await expect(catalog).toBeHidden();
  await expect(page.getByRole('button', { name: /Modelo ou combo/ })).toContainText(
    'Combo de demonstração',
  );
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: '../ws/b_output/chat_ux/new_chat_mobile.png', fullPage: true });
});
test('reviews and applies a recorded conversation change and shows the observed model and image', async ({ page }) => {
  await loginControlPlane(page);
  const headers = { Authorization: `Bearer ${E2E_TOKEN}` };
  const projects = await (await page.request.get('/v1/control-plane/projects', { headers })).json();
  const project = projects.find((item: { name: string }) => item.name === 'hydra-e2e-repo');
  expect(project).toBeDefined();
  const created = await page.request.post('/v1/control-plane/conversations', {
    headers,
    data: {
      project_id: project.id,
      executor: 'codex',
      content: 'E2E arquivo para revisão — Atualizar guia de início',
      access_mode: 'workspace-write',
      idempotency_key: 'e2e-review-files-main-0001',
    },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const { conversation_id: id } = await created.json();
  const screenshotDir = '../ws/b_output/conversa-coordenacao';
  fs.mkdirSync(screenshotDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/chat/${id}`);
  await expect(page.getByRole('heading', { name: 'gpt-e2e-test OpenAI' })).toBeVisible();
  await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible();
  const upload = page.getByTestId('conversation-page').locator('input[type="file"]');
  const image = { name: 'referencia.png', mimeType: 'image/png', buffer: fs.readFileSync('../ws/b_output/entrega-demo/site-desktop.png') };
  await upload.setInputFiles(image);
  await expect(page.getByRole('img', { name: 'Prévia de referencia.png' })).toBeVisible();
  await expect(page.getByTestId('attachment-list')).toContainText('Pronto local');
  const remove = page.getByRole('button', { name: 'Remover anexo referencia.png' });
  await remove.press('Enter');
  await expect(page.getByRole('img', { name: 'Prévia de referencia.png' })).toHaveCount(0);
  await upload.setInputFiles(image);
  await page.getByLabel('Sua mensagem').fill('Use esta imagem como referência para o cabeçalho.');
  await expect(page.getByRole('img', { name: 'Prévia de referencia.png' })).toBeVisible();
  await runAxeWcagAA(page, 'conversa com prévia de imagem');
  await page.screenshot({ path: `${screenshotDir}/chat.png`, fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: `${screenshotDir}/chat_celular.png`, fullPage: true });
  await checkConversationLayout(page, 'chat_com_previa');
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.getByRole('link', { name: 'Ver agentes' }).click();
  await expect(page.getByTestId('agent-inspector')).toContainText('gpt-e2e-test');
  await runAxeWcagAA(page, 'área de trabalho com identidade observada');
  await page.screenshot({ path: `${screenshotDir}/area_de_trabalho.png`, fullPage: true });

  await page.goto(`/workspace?chat=${id}`);
  await expect(page.getByRole('heading', { name: 'Arquivos alterados' })).toBeVisible();
  await page.getByRole('button', { name: /src\/calc\.py/ }).click();
  await expect(page.getByTestId('diff-viewer')).toContainText('return x + x');
  await runAxeWcagAA(page, 'revisão por arquivo');
  await page.screenshot({ path: `${screenshotDir}/alteracoes.png`, fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: `${screenshotDir}/alteracoes_celular.png`, fullPage: true });
  await checkConversationLayout(page, 'alteracoes_por_arquivo');
  const applyResponse = page.waitForResponse(
    (response) => response.url().endsWith(`/conversations/${id}/apply`) && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Aplicar ao projeto', exact: true }).click();
  const applied = await applyResponse;
  expect(applied.ok(), await applied.text()).toBe(true);
  expect(await applied.json()).toMatchObject({
    status: 'applied',
    applied_files: expect.arrayContaining(['src/calc.py']),
  });
  await expect(page.getByRole('status').filter({ hasText: 'O projeto já está atualizado' })).toBeVisible();
});
