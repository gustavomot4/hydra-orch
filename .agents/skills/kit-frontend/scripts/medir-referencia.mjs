#!/usr/bin/env node
// Mede o visual de páginas de que a pessoa gosta: fontes, escala, cores, raios e mídia.
// Só olha: não clica, não preenche e não aceita cookies. Se o site bloquear, diz isso.
// Uso: node medir-referencia.mjs <url ou arquivo.html> [outros] [--saida design/referencias]
// Saída: 0 ao menos uma medida; 2 nada foi medido. As capturas são para estudo: têm marca de terceiros.
import { spawn } from 'node:child_process';
import { writeFileSync, existsSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const i = args.indexOf('--saida'); const saida = resolve(i >= 0 ? args.splice(i, 2)[1] : 'design/referencias');
if (!args.length) { console.error('Uso: medir-referencia.mjs <url ou arquivo.html> [outros] [--saida pasta]'); process.exit(2); }
const estranha = args.find(a => a.startsWith('-'));
if (estranha) { console.error(`Opção desconhecida: ${estranha}\nUso: medir-referencia.mjs <url ou arquivo.html> [outros] [--saida pasta]`); process.exit(2); }
const exe = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`, 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(c => c && existsSync(c));
if (!exe) { console.error('Não achei Chrome, Edge nem Chromium. Defina CHROME_PATH.'); process.exit(2); }

const perfil = mkdtempSync(join(tmpdir(), 'kit-frontend-'));
const porta = 9900 + Math.floor(Math.random() * 90);
const nav = spawn(exe, ['--headless=new', `--remote-debugging-port=${porta}`, `--user-data-dir=${perfil}`, '--no-first-run', '--no-default-browser-check', '--disable-extensions', 'about:blank'], { stdio: 'ignore' });
const dorme = ms => new Promise(r => setTimeout(r, ms));
let alvo; for (let t = 0; t < 60 && !alvo; t++) { await dorme(200); try { alvo = (await (await fetch(`http://127.0.0.1:${porta}/json`)).json()).find(p => p.type === 'page'); } catch { /* subindo */ } }
if (!alvo) { nav.kill(); console.error('O navegador não abriu a porta de depuração.'); process.exit(2); }
const ws = new WebSocket(alvo.webSocketDebuggerUrl); await new Promise(r => ws.addEventListener('open', r));
let id = 0; const esp = new Map();
ws.addEventListener('message', ev => { const m = JSON.parse(ev.data); if (m.id && esp.has(m.id)) { esp.get(m.id)(m); esp.delete(m.id); } });
const cdp = (method, params = {}) => new Promise(res => { const n = ++id; esp.set(n, res); ws.send(JSON.stringify({ id: n, method, params })); setTimeout(() => { if (esp.has(n)) { esp.delete(n); res({}); } }, 30000); });
const ev = async e => (await cdp('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
await cdp('Page.enable'); await cdp('Runtime.enable');
await cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

const MEDIR = `(() => {
  const cs = e => getComputedStyle(e);
  const vis = e => { const r = e.getBoundingClientRect(), s = cs(e); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0; };
  const todos = [...document.querySelectorAll('body *')].filter(e => !e.closest('svg')).filter(vis);
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), txt = new Map();
  for (let n; (n = tw.nextNode());) { const p = n.parentElement, t = n.textContent.trim(); if (t && p && !['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName) && vis(p)) txt.set(p, (txt.get(p) || 0) + t.length); }
  const fam = {}; for (const [e, n] of txt) { const k = cs(e).fontFamily.split(',')[0].replace(/["']/g, '').trim(); fam[k] = (fam[k] || 0) + n; }
  const tam = [...txt.keys()].map(e => parseFloat(cs(e).fontSize)).filter(Boolean);
  const ctx = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const hex = c => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data; return d[3] < 200 ? null : '#' + [d[0], d[1], d[2]].map(v => v.toString(16).padStart(2, '0')).join(''); };
  const area = {}; todos.forEach(e => { const c = hex(cs(e).backgroundColor); if (!c) return; const r = e.getBoundingClientRect(); area[c] = (area[c] || 0) + r.width * r.height; });
  const raios = {}; todos.forEach(e => { const v = cs(e).borderTopLeftRadius; if (v !== '0px') raios[v] = (raios[v] || 0) + 1; });
  const titulos = [...document.querySelectorAll('h1,h2')].filter(vis).sort((a, b) => parseFloat(cs(b).fontSize) - parseFloat(cs(a).fontSize)).slice(0, 3).map(h => { const s = cs(h); return Math.round(parseFloat(s.fontSize)) + 'px peso ' + s.fontWeight + (s.textTransform === 'uppercase' ? ' caixa alta' : ''); });
  const top = o => Object.entries(o).sort((a, b) => b[1] - a[1]).map(x => x[0]);
  const corpo = document.body.innerText || '';
  // o que está à frente da primeira dobra: um aviso de cookies muda a captura e parte das medidas, e título em imagem não aparece nos tamanhos
  const dobra = innerWidth * innerHeight;
  const naDobra = e => { const r = e.getBoundingClientRect(), l = Math.min(r.right, innerWidth) - Math.max(r.left, 0), a = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0); return l > 0 && a > 0 ? l * a : 0; };
  const fixoDe = e => { for (let n = e; n && n !== document.body; n = n.parentElement) if (cs(n).position === 'fixed') return n; return null; };
  const noMeio = fixoDe(document.elementFromPoint(innerWidth / 2, innerHeight / 2));
  const cookies = todos.filter(e => cs(e).position === 'fixed' && /cookie|consent|lgpd/i.test(e.textContent || '') && naDobra(e) > dobra * .1).sort((a, b) => naDobra(b) - naDobra(a))[0];
  const camada = noMeio && (noMeio.textContent || '').trim().length > 20 && naDobra(noMeio) > dobra * .15 ? noMeio : cookies;
  const maiorMidia = Math.max(0, ...[...document.querySelectorAll('img,svg,video,canvas')].filter(e => !e.parentElement.closest('svg') && vis(e)).map(naDobra));
  return { camada: camada ? Math.round(naDobra(camada) / dobra * 100) : 0, maiorMidia: Math.round(maiorMidia / dobra * 100), titulo: document.title.slice(0, 70), fontes: top(fam).slice(0, 4), maiorFonte: tam.length ? Math.round(Math.max(...tam)) : 0, menorFonte: tam.length ? Math.round(Math.min(...tam) * 10) / 10 : 0, titulos, cores: top(area).slice(0, 6), raios: top(raios).slice(0, 4), imagens: document.images.length, videos: document.querySelectorAll('video').length, canvas: document.querySelectorAll('canvas').length, bloqueio: /verifica[cç][aã]o de seguran|um momento|just a moment|access denied|verify you are human/i.test(document.title + ' ' + corpo.slice(0, 300)) };
})()`;

let medidas = 0;
for (const entrada of args) {
  const url = /^(https?|file):/.test(entrada) ? entrada : pathToFileURL(resolve(entrada)).href;
  const nome = (/^https?:/.test(entrada) ? new URL(entrada).hostname.replace(/^www\./, '') : basename(entrada, '.html')).replace(/[^a-z0-9.-]/gi, '-').toLowerCase();
  const abriu = await cdp('Page.navigate', { url });
  console.log(`\n${entrada}`);
  if (abriu.result?.errorText) { console.log(`  Não abriu: ${abriu.result.errorText}`); continue; }
  await dorme(/^https?:/.test(url) ? 6000 : 800);
  const m = await ev(MEDIR);
  if (!m) { console.log('  Não consegui medir esta página.'); continue; }
  if (m.bloqueio) { console.log('  O site parou numa verificação ou negou o acesso. Não tente contornar: peça uma captura à pessoa.'); continue; }
  medidas++;
  mkdirSync(saida, { recursive: true });
  const c = await cdp('Page.captureScreenshot', { format: 'jpeg', quality: 70 });
  if (c.result?.data) writeFileSync(join(saida, `${nome}.jpg`), Buffer.from(c.result.data, 'base64'));
  console.log(`  fontes: ${m.fontes.join(', ')}\n  tamanhos: de ${m.menorFonte} a ${m.maiorFonte}px; títulos: ${m.titulos.join('; ') || 'nenhum'}\n  cores por área: ${m.cores.join(' ')}\n  raios: ${m.raios.join(', ') || 'nenhum'}\n  mídia: ${m.imagens} imagens, ${m.videos} vídeos, ${m.canvas} canvas\n  maior imagem ou desenho: ${m.maiorMidia}% da primeira dobra`);
  if (m.camada) console.log(`  AVISO: uma camada cobre ${m.camada}% da primeira dobra, provavelmente de cookies. A captura e parte das medidas são dela: peça uma captura limpa à pessoa.`);
}
console.log('\nCopie o raciocínio, nunca a marca, a fonte, a imagem ou o texto. Capturas em ' + saida + '.');
ws.close(); nav.kill(); await dorme(400); try { rmSync(perfil, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* o sistema limpa depois */ }
process.exitCode = medidas ? 0 : 2;
