import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { expect, Page, test } from '@playwright/test';

const output = '../ws/b_output/coordination-ui';
const token = process.env.HYDRA_API_TOKEN || 'hydra-e2e-hermetic-local-token-0123456789';
const axe = fs.readFileSync('node_modules/axe-core/axe.min.js', 'utf8');

async function fixture(page: Page) {
  const response = await page.request.get('/v1/control-plane/conversations?limit=100', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const { items } = await response.json();
  return items.find((item: { title: string }) =>
    item.title.includes('Conferir preparação do projeto'),
  ).id as string;
}

async function login(page: Page) {
  await page.goto('/');
  if (process.env.HYDRA_E2E_KIT_AUTH !== '1') {
    await page.getByLabel('Token Bearer', { exact: true }).fill(token);
    await page.getByRole('button', { name: 'Conectar ao Control Plane' }).click();
  }
  await expect(page.getByTestId('hydra-app-shell')).toBeVisible();
}

async function audit(page: Page) {
  await page.evaluate(axe);
  const violations = await page.evaluate(async () => {
    const engine = (
      window as unknown as {
        axe: { run: (context: Document, options: unknown) => Promise<{ violations: unknown[] }> };
      }
    ).axe;
    return (
      await engine.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
      })
    ).violations;
  });
  expect(violations).toEqual([]);
}

test('shows local check evidence consistently in chat and canvas, including keyboard and narrow layouts', async ({
  page,
}) => {
  test.setTimeout(120_000);
  fs.mkdirSync(output, { recursive: true });
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  await login(page);
  const id = await fixture(page);
  await page.goto(`/chat/${id}`);
  const panel = page.getByRole('region', { name: 'Trabalho coordenado' });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('status')).toHaveText('1 de 3 concluídas · 1 com falha');
  await expect(panel.getByText('Validada', { exact: true })).toBeVisible();
  await expect(panel.getByText('Não iniciada', { exact: true })).toBeVisible();
  const disclosure = panel.locator('summary').filter({ hasText: 'tipos-frontend' });
  await disclosure.focus();
  await page.keyboard.press('Enter');
  await expect(panel.getByLabel('Saída de tipos-frontend')).toContainText('limite de tempo');
  await expect(disclosure).toBeFocused();
  await audit(page);
  fs.writeFileSync(
    `${output}/entrelinha.json`,
    JSON.stringify(
      await page.evaluate(() =>
        [...document.querySelectorAll('p,li,blockquote,dd,div,td,figcaption')]
          .filter((element) => {
            const style = getComputedStyle(element);
            return (
              element.getClientRects().length > 0 &&
              Number.parseFloat(style.lineHeight) / Number.parseFloat(style.fontSize) < 1.3
            );
          })
          .map((element) => ({
            tag: element.tagName,
            classes: element.className,
            text: (element as HTMLElement).innerText.slice(0, 120),
            lineHeight: getComputedStyle(element).lineHeight,
            fontSize: getComputedStyle(element).fontSize,
          })),
      ),
      null,
      2,
    ),
  );
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
    [320, 256],
  ]) {
    await page.setViewportSize({ width, height });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByLabel('Sua mensagem')).toBeVisible();
    if (width !== 320)
      await page.screenshot({ path: `${output}/conversa-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '200%';
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '';
  });
  await page.getByRole('link', { name: 'Ver agentes', exact: true }).click();
  await page.getByRole('button', { name: 'Lista', exact: true }).click();
  await page.locator('.agent-list-item').filter({ hasText: 'Verificar tipos do frontend' }).click();
  const inspector = page.getByRole('complementary', { name: 'Detalhes da verificação' });
  await expect(inspector.getByText('Verificações', { exact: true })).toBeVisible();
  const check = inspector.locator('summary').filter({ hasText: 'tipos-frontend' });
  await check.focus();
  await page.keyboard.press('Enter');
  await expect(inspector.getByLabel('Saída de tipos-frontend')).toBeVisible();
  await expect(inspector.getByText('Hydra · Verificação local', { exact: true })).toBeVisible();
  await expect(inspector.getByText('Alterações', { exact: true })).toHaveCount(0);
  await audit(page);
  await page.screenshot({ path: `${output}/area-de-trabalho-1280.png`, fullPage: true });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.screenshot({ path: `${output}/area-de-trabalho-contraste.png`, fullPage: true });
  expect(requests.some((url) => /\/runs\/(?:null|undefined)(?:[/?]|$)/.test(url))).toBe(false);
});

test('runs the frontend kit on the two updated views', async ({ page, baseURL }) => {
  test.skip(process.env.HYDRA_RUN_KIT !== '1', 'Requires isolated fixture authentication.');
  test.setTimeout(300_000);
  fs.mkdirSync(output, { recursive: true });
  const id = await fixture(page);
  const result = await promisify(execFile)(
    process.execPath,
    [
      path.resolve('../.agents/skills/kit-frontend/scripts/verificar.mjs'),
      `${baseURL}/chat/${id}`,
      `${baseURL}/agentes?chat=${id}`,
      '--saida',
      path.resolve(`${output}/kit`),
      '--design',
      path.resolve('../DESIGN.md'),
      '--axe',
      path.resolve('node_modules/axe-core/axe.min.js'),
      '--esperar',
      '.coordination-panel, .agent-node, .agent-list-item',
    ],
    { cwd: path.resolve('..'), timeout: 280_000 },
  );
  fs.writeFileSync(`${output}/kit-run.txt`, result.stdout + result.stderr);
});
