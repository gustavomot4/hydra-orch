import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { expect, Page, test } from '@playwright/test';

const token = process.env.HYDRA_API_TOKEN || 'hydra-e2e-hermetic-local-token-0123456789';
const output = '../ws/b_output/compact-workbench';
const kit = fs.readFileSync('../.agents/skills/kit-frontend/scripts/tela.js', 'utf8');
type KitReport = { achados: { nivel: string; id: string; exemplos: string[] }[] };
async function login(page: Page) {
  fs.mkdirSync(output, { recursive: true });
  await page.goto('/');
  if (process.env.HYDRA_E2E_KIT_AUTH !== '1') {
    await page.locator('#hydra-bearer-token-input').fill(token);
    await page.getByRole('button', { name: 'Conectar ao Control Plane' }).click();
  }
  await expect(page.getByTestId('hydra-app-shell')).toBeVisible();
}
async function audit(page: Page, name: string, reportPath: string) {
  const reports: { width?: number; height?: number; zoom?: number; result: KitReport }[] = [];
  for (const [width, height] of [
    [1440, 900],
    [768, 1024],
    [375, 812],
    [320, 480],
  ]) {
    await page.setViewportSize({ width, height });
    if (name === 'workspace' && width >= 840)
      await page.getByRole('button', { name: 'Enquadrar', exact: true }).click();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.evaluate(() => {
      (window as unknown as { __kitOpcoes: unknown }).__kitOpcoes = {
        fontesComMotivo: ['Inter é mantida porque preserva a continuidade da interface existente.'],
      };
    });
    reports.push({ width, height, result: await page.evaluate<KitReport>(kit) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `${output}/${name}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '200%';
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  reports.push({ zoom: 200, result: await page.evaluate<KitReport>(kit) });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '';
  });
  await page.emulateMedia({ forcedColors: 'active' });
  await page.screenshot({ path: `${output}/${name}-contrast.png`, fullPage: true });
  await page.emulateMedia({ forcedColors: 'none' });
  await page.setViewportSize({ width: 1440, height: 900 });
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(reports, null, 2));
  const failures = reports.flatMap(({ result, ...viewport }) =>
    result.achados.filter(({ nivel }) => nivel === 'falha').map((finding) => ({ ...viewport, ...finding })),
  );
  expect(failures).toEqual([]);
}

test('compact preferences persist and panel dividers keep tabs intact', async ({ page }) => {
  await login(page);
  await expect(
    page.getByRole('button', { name: 'Revise o código e encontre problemas', exact: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Aparência e painéis' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Densidade da interface').selectOption('compact');
  await dialog.getByLabel('Texto da conversa (px)').fill('18');
  await dialog.getByLabel('Mostrar barra lateral', { exact: true }).uncheck();
  await expect(page.getByTestId('desktop-sidebar')).toHaveCSS('width', '58px');
  await dialog.getByLabel('Mostrar barra lateral', { exact: true }).check();
  await page.screenshot({ path: `${output}/appearance-desktop.png`, fullPage: true });
  await dialog.getByRole('button', { name: 'Fechar', exact: true }).click();
  await page.getByRole('button', { name: 'Dividir painéis', exact: true }).click();
  const divider = page.getByRole('separator', { name: 'Redimensionar painéis divididos' });
  await divider.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(divider).toHaveAttribute('aria-valuenow', '48');
  await page.reload();
  await expect(
    page.getByRole('separator', { name: 'Redimensionar painéis divididos' }),
  ).toHaveAttribute('aria-valuenow', '48');
  await page.getByRole('button', { name: 'Aparência e painéis' }).first().click();
  await page.getByRole('button', { name: 'Restaurar tamanhos e painéis' }).click();
  await expect(page.getByLabel('Texto da conversa (px)')).toHaveValue('14');
  await page.getByRole('dialog').getByRole('button', { name: 'Fechar', exact: true }).click();
});

test('workspace picker reveals project parents and inspector resizing is persistent', async ({
  page,
}, testInfo) => {
  await login(page);
  await page.goto('/agentes?execucao=run-e2e-swarm');
  await expect(page.getByTestId('agent-workspace-page')).toBeVisible();
  await expect(
    page.getByRole('separator', { name: 'Redimensionar detalhes dos agentes' }),
  ).toBeVisible();
  const divider = page.getByRole('separator', { name: 'Redimensionar detalhes dos agentes' });
  await divider.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(divider).toHaveAttribute('aria-valuenow', '336');
  await page.getByRole('button', { name: 'Ocultar detalhes dos agentes' }).click();
  await expect(divider).toHaveCount(0);
  await page.getByRole('button', { name: 'Mostrar detalhes dos agentes' }).click();
  await expect(divider).toHaveAttribute('aria-valuenow', '336');
  const picker = page.locator('.canvas-work-picker');
  await picker.locator(':scope > summary').click();
  await picker.locator('summary').filter({ hasText: 'hydra-e2e-repo' }).click();
  await picker.locator('summary').filter({ hasText: 'Execuções' }).click();
  await expect(picker.getByRole('button', { name: 'Auditoria E2E M5 multi-agente' })).toBeVisible();
  await picker.getByRole('button', { name: 'Auditoria E2E M5 multi-agente' }).click();
  await expect(page.locator('.agent-map-stage')).toBeVisible();
  await audit(page, 'workspace', testInfo.outputPath('workspace-audit.json'));
});

test('quota model dialog bounds long lists and keyboard focus returns to its trigger', async ({
  page,
}, testInfo) => {
  await login(page);
  await page.goto('/consumo');
  await expect(page.getByTestId('quota-accounts-page')).toBeVisible();
  const catalog = page.getByRole('button', { name: /Abrir catálogo/ });
  await expect(catalog).toBeVisible();
  await catalog.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('table')).toBeVisible();
  expect(await dialog.getByRole('row').count()).toBeLessThanOrEqual(11);
  await page.keyboard.press('Escape');
  await expect(catalog).toBeFocused();
  await audit(page, 'quota', testInfo.outputPath('quota-audit.json'));
});

test('new chat keeps folder fallback and keyboard history without predefined chips', async ({
  page,
}, testInfo) => {
  await login(page);
  await page.getByRole('button', { name: 'Adicionar pasta', exact: true }).click();
  await expect(
    page.getByRole('dialog').getByLabel('Caminho da pasta neste computador'),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  const input = page.getByRole('textbox', { name: 'Sua mensagem', exact: true });
  await input.fill('Rascunho preservado');
  await page.getByRole('button', { name: 'Aparência e painéis' }).first().click();
  await page.keyboard.press('Escape');
  await expect(input).toHaveValue('Rascunho preservado');
  await audit(page, 'new-chat', testInfo.outputPath('new-chat-audit.json'));
});

test('runs the frontend kit against the authenticated isolated fixture', async ({ baseURL }) => {
  test.skip(
    process.env.HYDRA_RUN_KIT !== '1',
    'Run explicitly with the fixture-only kit authentication enabled.',
  );
  test.setTimeout(300000);
  const args = [
    path.resolve('../.agents/skills/kit-frontend/scripts/verificar.mjs'),
    `${baseURL}/`,
    `${baseURL}/agentes?execucao=run-e2e-swarm`,
    `${baseURL}/consumo`,
    `${baseURL}/chat/run-e2e-swarm`,
    `${baseURL}/terminal`,
    `${baseURL}/workspace`,
    `${baseURL}/recursos`,
    `${baseURL}/automacoes`,
    `${baseURL}/dispositivos`,
    `${baseURL}/computador`,
    `${baseURL}/busca`,
    `${baseURL}/configuracoes`,
    '--saida',
    path.resolve(`${output}/kit`),
    '--design',
    path.resolve('../DESIGN.md'),
    '--axe',
    path.resolve('node_modules/axe-core/axe.min.js'),
    '--esperar',
    'h1',
  ];
  const result = await promisify(execFile)(process.execPath, args, {
    timeout: 270000,
    maxBuffer: 4 * 1024 * 1024,
  }).catch((error) => ({ stdout: error.stdout, stderr: error.stderr, code: error.code }));
  fs.writeFileSync(`${output}/kit-command.log`, `${result.stdout}\n${result.stderr}`);
  expect('code' in result ? result.code : 0).toBe(0);
});
