#!/usr/bin/env node
// Junta as direções num só arquivo, para o dono decidir e repassar: um HTML com as imagens dentro e um PDF.
// Rode depois de scripts/verificar.mjs em cada direção. Lê o conceito de ideias.md, na ordem dos arquivos.
// notas.json, na pasta das direções, é opcional: { "a-conversa": { "nome": "A. Conversa", "assinatura": "…", "cega": "…" } }.
// Uso: node prancha.mjs [pasta] [--verificacao design/verificacao] [--saida <pasta>/comparar-direcoes] [--titulo "Nome"]
// Saída: 0 gerou; 2 faltou captura, navegador ou direção. Sem dependências: Node 22+.
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, readdirSync, mkdtempSync, rmSync } from 'node:fs';
import { join, resolve, extname, basename } from 'node:path';
import { tmpdir, homedir } from 'node:os';
import { pathToFileURL } from 'node:url';

const USO = 'Uso: prancha.mjs [pasta] [--verificacao design/verificacao] [--saida <pasta>/comparar-direcoes] [--titulo "Nome"]';
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) { console.log(USO); process.exit(0); }
const valor = nome => { const i = args.indexOf(nome); if (i < 0) return null; const v = args[i + 1]; args.splice(i, 2); return v; };
const verificacao = resolve(valor('--verificacao') || 'design/verificacao');
const saidaPedida = valor('--saida');
const titulo = valor('--titulo') || 'Três propostas';
const estranha = args.find(a => a.startsWith('-'));
if (estranha) { console.error(`Opção desconhecida: ${estranha}\n${USO}`); process.exit(2); }
const pasta = resolve(args[0] || 'design/direcoes');
if (!existsSync(pasta)) { console.error(`Não achei ${pasta}.`); process.exit(2); }
const saida = resolve(saidaPedida || join(pasta, 'comparar-direcoes'));

const direcoes = readdirSync(pasta).filter(a => a.endsWith('.html') && !['index.html', `${basename(saida)}.html`].includes(a)).sort().map(a => basename(a, '.html'));
if (direcoes.length < 2) { console.error(`Achei ${direcoes.length} direção em ${pasta}: a prancha compara pelo menos duas.`); process.exit(2); }

const CAPTURAS = ['desktop.png', 'celular.png', 'desktop-inteira.jpg', 'celular-inteira.jpg'];
const faltam = direcoes.flatMap(d => CAPTURAS.filter(c => !existsSync(join(verificacao, d, c))).map(c => `${d}/${c}`));
if (faltam.length) { console.error(`Faltam capturas em ${verificacao}: ${faltam.slice(0, 4).join(', ')}. Rode scripts/verificar.mjs em cada direção.`); process.exit(2); }

const esc = t => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const img = (d, c) => `data:${extname(c) === '.png' ? 'image/png' : 'image/jpeg'};base64,${readFileSync(join(verificacao, d, c)).toString('base64')}`;

// A tabela de conceitos do ideias.md, uma linha por direção, na ordem
const ideias = join(pasta, 'ideias.md');
const conceitos = existsSync(ideias) ? (/^## Conceitos[^\n]*\n([\s\S]*?)(?=^## |(?![\s\S]))/m.exec(readFileSync(ideias, 'utf8').replace(/\r\n/g, '\n'))?.[1] || '').split('\n').filter(l => l.startsWith('|')).slice(2).map(l => l.split('|').map(c => c.trim())) : [];
const arquivoNotas = join(pasta, 'notas.json');
let notas = {};
if (existsSync(arquivoNotas)) { try { notas = JSON.parse(readFileSync(arquivoNotas, 'utf8')); } catch (e) { console.error(`notas.json não é JSON válido: ${e.message}`); process.exit(2); } }

const secoes = direcoes.map((d, i) => {
  const n = notas[d] || {}, linha = conceitos[i] || [];
  const nome = n.nome || linha[1] || d, conceito = n.conceito || linha[2] || '';
  const itens = [['Ideia', conceito], ['O que só ela tem', n.assinatura], ['Avaliação às cegas', n.cega]].filter(([, v]) => v);
  return `<section class="folha">
  <h2>${esc(nome)}</h2>
  ${itens.length ? `<dl>${itens.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
  <div class="telas">
    <figure class="pc"><img src="${img(d, 'desktop.png')}" alt="${esc(nome)}, primeira tela no computador"><figcaption>Computador, 1440 × 900</figcaption></figure>
    <figure class="cel"><img src="${img(d, 'celular.png')}" alt="${esc(nome)}, primeira tela no celular"><figcaption>Celular, 375 × 812</figcaption></figure>
  </div>
</section>
<section class="folha inteira">
  <h2>${esc(nome)}: a página inteira</h2>
  <div class="telas">
    <figure><img src="${img(d, 'desktop-inteira.jpg')}" alt="${esc(nome)}, página inteira no computador"><figcaption>Computador</figcaption></figure>
    <figure><img src="${img(d, 'celular-inteira.jpg')}" alt="${esc(nome)}, página inteira no celular"><figcaption>Celular. Barras fixas aparecem só na primeira tela.</figcaption></figure>
  </div>
</section>`;
}).join('\n');

// Sem media query de largura no print: o Chrome mede a página pelo papel padrão e aplicaria a regra de celular
const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(titulo)}</title>
<style>
@page { size: 1400px 1040px; margin: 0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; background: #fff; color: #1a1a1a; font: 400 18px/1.45 system-ui, sans-serif; }
.capa, .folha { padding: 32px 40px; }
.capa h1 { font-size: 44px; line-height: 1.1; margin: 0; }
h2 { font-size: 34px; line-height: 1.1; margin: 0 0 12px; }
dl { display: grid; grid-template-columns: 190px 1fr; gap: 2px 16px; margin: 0 0 20px; }
dt { font-weight: 700; } dd { margin: 0; }
.telas { display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }
figure { margin: 0; }
img { display: block; max-width: 100%; height: auto; border: 1px solid #767676; }
figcaption { margin-top: 6px; font-size: 16px; max-width: 330px; }
.pc img { width: 1000px; } .cel img { width: 300px; }
.inteira img { width: auto; height: 860px; max-width: none; }
@media print {
  .folha { break-before: page; height: 1040px; overflow: hidden; }
  .telas { flex-wrap: nowrap; } figure { flex: none; }
}
@media screen and (max-width: 900px) {
  .capa, .folha { padding: 20px 16px; }
  dl { grid-template-columns: 1fr; } dd { margin-bottom: 8px; }
  .pc img, .inteira img { width: 100%; height: auto; max-width: 100%; }
}
</style></head>
<body><header class="capa"><h1>${esc(titulo)}</h1></header><main>
${secoes}
</main></body></html>`;
writeFileSync(`${saida}.html`, html);

const exe = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`, 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/usr/bin/google-chrome', '/usr/bin/chromium', `${homedir()}/.cache/ms-playwright/chromium/chrome-linux/chrome`].find(c => c && existsSync(c));
if (!exe) { console.error(`${saida}.html gerado, mas sem Chrome ou Edge para o PDF. Defina CHROME_PATH.`); process.exit(2); }
const perfil = mkdtempSync(join(tmpdir(), 'kit-frontend-'));
spawnSync(exe, ['--headless=new', '--disable-gpu', `--user-data-dir=${perfil}`, '--no-pdf-header-footer', '--virtual-time-budget=4000', `--print-to-pdf=${saida}.pdf`, pathToFileURL(`${saida}.html`).href], { stdio: 'ignore', timeout: 120000 });
try { rmSync(perfil, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* o sistema limpa depois */ }
if (!existsSync(`${saida}.pdf`)) { console.error(`${saida}.html gerado, mas o PDF falhou.`); process.exit(2); }
console.log(`${direcoes.length} direções em ${saida}.html e ${saida}.pdf.`);
if (!Object.keys(notas).length) console.log('Sem notas.json: acrescente nome, elemento-assinatura e o que a escolha cega apontou, e rode de novo.');
