#!/usr/bin/env node
// Compara as direções visuais em 1440 × 900: tipografia, composição, cor e código comum. Três direções quase iguais não são três escolhas.
// Uso: node comparar-direcoes.mjs <pasta ou arquivos.html> [--json]
// Saída: 0 direções diferentes; 1 há par quase igual; 2 não conseguiu rodar. Mede a diferença, não a qualidade: quem julga é o dono.
import { spawn } from 'node:child_process';
import { readdirSync, existsSync, statSync, mkdtempSync, rmSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL, fileURLToPath } from 'node:url';

const USO = 'Uso: comparar-direcoes.mjs <pasta ou arquivos.html> [--json]';
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) { console.log(USO); process.exit(0); }
const comoJson = args.includes('--json'); if (comoJson) args.splice(args.indexOf('--json'), 1);
if (!args.length) { console.error(USO); process.exit(2); }
const faltando = args.filter(a => !existsSync(resolve(a)));
if (faltando.length) { console.error(`Não achei: ${faltando.join(', ')}. Nada foi comparado.`); process.exit(2); }
// numa pasta, só a cópia de cada direção: comparativo e índice não contam
const arquivos = args.flatMap(a => statSync(resolve(a)).isDirectory() ? readdirSync(resolve(a)).filter(f => f.endsWith('.html') && !/^(index|prancha|comparativo)/i.test(f)).sort().map(f => join(resolve(a), f)) : [resolve(a)]);
if (arquivos.length < 2) { console.error(`Achei ${arquivos.length} direção(ões): preciso de pelo menos 2 arquivos HTML.`); process.exit(2); }

const exe = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`, 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(c => c && existsSync(c));
if (!exe) { console.error('Não achei Chrome, Edge nem Chromium. Defina CHROME_PATH.'); process.exit(2); }
const perfil = mkdtempSync(join(tmpdir(), 'kit-frontend-'));
const porta = 9800 + Math.floor(Math.random() * 90);
const nav = spawn(exe, ['--headless=new', `--remote-debugging-port=${porta}`, `--user-data-dir=${perfil}`, '--no-first-run', '--no-default-browser-check', '--disable-extensions', 'about:blank'], { stdio: 'ignore' });
const dorme = ms => new Promise(r => setTimeout(r, ms));
const fechar = async c => { try { nav.kill(); } catch { /* já saiu */ } await dorme(400); try { rmSync(perfil, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* o sistema limpa depois */ } process.exit(c); };
let alvo; for (let t = 0; t < 60 && !alvo; t++) { await dorme(200); try { alvo = (await (await fetch(`http://127.0.0.1:${porta}/json`)).json()).find(p => p.type === 'page'); } catch { /* subindo */ } }
if (!alvo) { console.error('O navegador não abriu a porta de depuração.'); await fechar(2); }
const ws = new WebSocket(alvo.webSocketDebuggerUrl); await new Promise(r => ws.addEventListener('open', r));
let id = 0; const esp = new Map();
ws.addEventListener('message', ev => { const m = JSON.parse(ev.data); if (m.id && esp.has(m.id)) { esp.get(m.id)(m); esp.delete(m.id); } });
const cdp = (method, params = {}) => new Promise(res => { const n = ++id; esp.set(n, res); ws.send(JSON.stringify({ id: n, method, params })); });
const ev = async e => (await cdp('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
await cdp('Page.enable'); await cdp('Runtime.enable');
await cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

const MEDIR = `(async () => {
  await Promise.race([Promise.all([...document.images].map(i => { i.loading = 'eager'; return i.complete ? 0 : new Promise(r => { i.addEventListener('load', r, { once: true }); i.addEventListener('error', r, { once: true }); }); })), new Promise(r => setTimeout(r, 4000))]);
  await document.fonts.ready;
  const cs = e => getComputedStyle(e);
  const vis = e => { const r = e.getBoundingClientRect(), s = cs(e); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0; };
  const todos = [...document.querySelectorAll('body *')].filter(e => !e.closest('svg') || e.tagName === 'svg').filter(vis);
  const familia = e => cs(e).fontFamily.split(',')[0].replace(/["']/g, '').trim().toLowerCase();
  // tipografia: a família do título e a família com mais texto
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), pesos = {};
  for (let n; (n = tw.nextNode());) { const p = n.parentElement, t = n.textContent.trim(); if (t && p && !['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName) && vis(p)) { const f = familia(p); pesos[f] = (pesos[f] || 0) + t.length; } }
  const h1 = document.querySelector('h1') || document.querySelector('h2');
  const tipografia = { titulo: h1 ? familia(h1) : '', peso: h1 ? +cs(h1).fontWeight : 0, tamanho: h1 ? parseFloat(cs(h1).fontSize) : 0, corpo: Object.entries(pesos).sort((a, b) => b[1] - a[1])[0]?.[0] || '' };
  // ideia: outra pele na mesma página mantém o título e as seções, na mesma ordem
  const limpo = t => (t || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/\\s+/g, ' ').trim();
  const ideia = { titulo: limpo(document.querySelector('h1')?.textContent), secoes: [...document.querySelectorAll('h2')].filter(vis).map(h => limpo(h.textContent)) };
  // composição: o que ocupa cada célula de uma grade de 120 x 60 px, nos primeiros 3 mil px
  const tipoDe = e => e.matches('img,svg,video,canvas,picture') ? 'm' : e.matches('button,input,select,textarea,a[href]') ? 'c' : [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) ? 't' : '';
  const celulas = {};
  const ordem = { t: 1, c: 2, m: 3 };
  for (const e of todos) {
    const tipo = tipoDe(e); if (!tipo || cs(e).position === 'fixed') continue;
    let r = e.getBoundingClientRect();
    if (tipo === 't') { const g = document.createRange(); g.selectNodeContents(e); r = g.getBoundingClientRect(); }
    const topo = r.top + scrollY, base = r.bottom + scrollY;
    for (let y = Math.floor(topo / 60); y <= Math.floor((base - 1) / 60) && y < 50; y++) for (let x = Math.floor(r.left / 120); x <= Math.floor((r.right - 1) / 120) && x < 12; x++) { const k = x + ':' + y, a = celulas[k]; if (!a || ordem[tipo] > ordem[a]) celulas[k] = tipo; }
  }
  // cor: fundo pintado em cada célula de 24 px da primeira dobra, sem contar foto
  const ctx = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const rgb = c => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data; return d[3] < 200 ? null : [d[0], d[1], d[2]]; };
  const faixa = v => Math.round(v / 24) * 24;
  const base = rgb(cs(document.body).backgroundColor) || rgb(cs(document.documentElement).backgroundColor) || [255, 255, 255];
  const pintura = {};
  for (let y = 0; y < innerHeight; y += 24) for (let x = 0; x < innerWidth; x += 24) pintura[x + ':' + y] = base;
  for (const e of todos) {
    const r = e.getBoundingClientRect(); if (r.top >= innerHeight || r.bottom <= 0) continue;
    const c = e.matches('img,svg,video,canvas,picture') ? 'foto' : rgb(cs(e).backgroundColor); if (!c) continue;
    for (let y = Math.max(0, Math.ceil(r.top / 24) * 24); y < Math.min(innerHeight, r.bottom); y += 24) for (let x = Math.max(0, Math.ceil(r.left / 24) * 24); x < Math.min(innerWidth, r.right); x += 24) pintura[x + ':' + y] = c;
  }
  const cores = {}; let pintadas = 0;
  for (const c of Object.values(pintura)) { if (c === 'foto') continue; const k = c.map(faixa).join(','); cores[k] = (cores[k] || 0) + 1; pintadas++; }
  for (const k in cores) cores[k] /= pintadas || 1;
  // estrutura: pares de pai e filho, com as classes. Gerador comum repete quase todos.
  const estrutura = {};
  for (const e of document.querySelectorAll('body *')) { if (e.closest('svg') && e.tagName !== 'svg') continue; const nome = n => n.tagName.toLowerCase() + '.' + [...n.classList].sort().join('.'); const k = nome(e.parentElement) + '>' + nome(e); estrutura[k] = (estrutura[k] || 0) + 1; }
  // código comum: as folhas externas de cada direção; o tamanho vem do disco
  const folhas = [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.href), dentro = [...document.querySelectorAll('style')].reduce((n, s) => n + s.textContent.length, 0);
  return { tipografia, ideia, celulas, cores, estrutura, folhas, dentro };
})()`;

const direcoes = [];
for (const a of arquivos) {
  const abriu = await cdp('Page.navigate', { url: pathToFileURL(a).href });
  if (abriu.result?.errorText) { console.error(`Não abriu ${a}: ${abriu.result.errorText}`); await fechar(2); }
  for (let i = 0; i < 50; i++) { await dorme(100); if (await ev('document.readyState') === 'complete') break; }
  await dorme(250);
  const m = await ev(MEDIR);
  if (!m) { console.error(`Não consegui medir ${a}.`); await fechar(2); }
  direcoes.push({ nome: basename(a, '.html'), ...m });
}
ws.close();

// parte em comum entre dois mapas: 1 é igual, 0 não tem nada em comum
const emComum = (a, b) => { let dentro = 0, tudo = 0; for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) { dentro += Math.min(a[k] || 0, b[k] || 0); tudo += Math.max(a[k] || 0, b[k] || 0); } return tudo ? dentro / tudo : 0; };
const celulasEmComum = (a, b) => { let dentro = 0; const juntas = new Set([...Object.keys(a), ...Object.keys(b)]); for (const k of juntas) if (a[k] && a[k] === b[k]) dentro++; return juntas.size ? dentro / juntas.size : 0; };
const coresEmComum = (a, b) => { let s = 0; for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) s += Math.min(a[k] || 0, b[k] || 0); return s; };
const tipografiaIgual = (a, b) => a.titulo === b.titulo && a.corpo === b.corpo && Math.abs(a.peso - b.peso) < 200 && Math.min(a.tamanho, b.tamanho) / Math.max(a.tamanho, b.tamanho) > .75;
const tamanho = h => { try { return statSync(fileURLToPath(h)).size; } catch { return 0; } };
const folhaComum = (a, b) => { const total = a.folhas.reduce((t, h) => t + tamanho(h), a.dentro), comum = a.folhas.filter(h => b.folhas.includes(h)).reduce((t, h) => t + tamanho(h), 0); return total ? comum / total : 0; };
// quantas seções vêm na mesma ordem, a partir do começo do que as duas têm em comum
const secoesEmOrdem = (a, b) => { const x = a.filter(s => b.includes(s)), y = b.filter(s => a.includes(s)), maior = Math.max(a.length, b.length); let i = 0; while (i < x.length && x[i] === y[i]) i++; return maior ? i / maior : 0; };

// Calibrado em 31/10/2026: direções de um mesmo gerador deram HTML de 77 a 84% e composição de 52 a 68%; direções feitas à parte, de 2 a 14% e de 21 a 32%.
// A cor mede só o fundo pintado na primeira dobra: duas direções claras podem dar 90% e ser diferentes no acento.
// Com o mesmo título, seções na mesma ordem: 75% em três direções de uma ideia só e até 20% em ideias diferentes, em três conjuntos reais.
const LIMITE = { estrutura: .5, composicao: .45, cor: .95, folha: .5, secoes: .6 };
const pares = [];
for (let i = 0; i < direcoes.length; i++) for (let j = i + 1; j < direcoes.length; j++) {
  const a = direcoes[i], b = direcoes[j];
  const p = { par: `${a.nome} x ${b.nome}`, tipografiaIgual: tipografiaIgual(a.tipografia, b.tipografia), composicao: celulasEmComum(a.celulas, b.celulas), cor: coresEmComum(a.cores, b.cores), estrutura: emComum(a.estrutura, b.estrutura), folha: Math.max(folhaComum(a, b), folhaComum(b, a)), mesmoTitulo: Boolean(a.ideia.titulo) && a.ideia.titulo === b.ideia.titulo, secoes: secoesEmOrdem(a.ideia.secoes, b.ideia.secoes) };
  p.motivos = [];
  if (p.mesmoTitulo && p.secoes >= LIMITE.secoes) p.motivos.push('mesma ideia: o título e a ordem das seções não mudam');
  if (p.estrutura >= LIMITE.estrutura) p.motivos.push('quase todo o HTML é igual');
  if (p.folha >= LIMITE.folha) p.motivos.push('a maior parte do CSS é comum');
  const iguais = [p.tipografiaIgual && 'tipografia', p.composicao >= LIMITE.composicao && 'composição', p.cor >= LIMITE.cor && 'cor'].filter(Boolean);
  if (iguais.length) p.motivos.push(`${iguais.join(', ')} não ${iguais.length > 1 ? 'mudam' : 'muda'}`);
  pares.push(p);
}
const proximos = pares.filter(p => p.motivos.length);
const pct = v => `${Math.round(v * 100)}%`;
if (comoJson) console.log(JSON.stringify({ direcoes: direcoes.map(d => ({ nome: d.nome, tipografia: d.tipografia })), pares }, null, 1));
else {
  for (const d of direcoes) console.log(`${d.nome}: título ${d.tipografia.titulo} ${d.tipografia.peso} em ${Math.round(d.tipografia.tamanho)}px; texto ${d.tipografia.corpo}`);
  console.log('');
  for (const p of pares) console.log(`${p.par}: HTML ${pct(p.estrutura)}, CSS comum ${pct(p.folha)}, composição ${pct(p.composicao)}, cor ${pct(p.cor)}, seções em ordem ${pct(p.secoes)}, título ${p.mesmoTitulo ? 'igual' : 'muda'}, tipografia ${p.tipografiaIgual ? 'igual' : 'muda'}${p.motivos.length ? `\n  QUASE IGUAIS: ${p.motivos.join('; ')}` : ''}`);
  console.log(proximos.length ? `\n${proximos.length} de ${pares.length} par(es) quase iguais. Refaça cada direção num arquivo próprio, sem gerador nem CSS comum: tipografia, composição, cor e ideia precisam mudar. Veja references/marca/identidade.md.` : `\nAs ${direcoes.length} direções diferem. Isto mede a diferença, não a qualidade: quem julga é o dono.`);
}
await fechar(proximos.length ? 1 : 0);
