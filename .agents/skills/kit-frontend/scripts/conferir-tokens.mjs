#!/usr/bin/env node
// Confere se as cores e as fontes do código estão no DESIGN.md. Regra do kit: valor novo entra lá primeiro.
// Só olha hex, rgb() e o primeiro nome de font-family. Tamanho e espaçamento ainda são com você.
// Uso: node conferir-tokens.mjs <pasta ou arquivos> [--design DESIGN.md]
// Saída: 0 sem desvio; 1 com desvio; 2 entrada inválida. Sem dependências: Node 22+.
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, extname, relative, resolve } from 'node:path';

const USO = 'Uso: conferir-tokens.mjs <pasta ou arquivos> [--design DESIGN.md]';
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) { console.log(USO); process.exit(0); }
const i = args.indexOf('--design'); const arquivoDesign = i >= 0 ? args.splice(i, 2)[1] : 'DESIGN.md';
const estranha = args.find(a => a.startsWith('-'));
if (estranha) { console.error(`Opção desconhecida: ${estranha}\n${USO}`); process.exit(2); }
if (!args.length) { console.error(USO); process.exit(2); }
if (!existsSync(arquivoDesign)) { console.error(`Não achei ${arquivoDesign}.`); process.exit(2); }

const norma = h => { let v = h.toLowerCase().slice(1); if (v.length === 3 || v.length === 4) v = [...v.slice(0, 3)].map(c => c + c).join(''); return '#' + v.slice(0, 6); };
const design = readFileSync(arquivoDesign, 'utf8');
const coresOk = new Set((design.match(/#[0-9a-f]{3,8}\b/gi) || []).map(norma));
const nomeFonte = f => f.trim().replace(/^['"]|['"]$/g, '').toLowerCase();
const fontesOk = new Set([...design.matchAll(/fontFamily:\s*["']?([^"'\n,]+)/g)].map(m => nomeFonte(m[1])));
for (const g of ['serif', 'sans-serif', 'monospace', 'cursive', 'system-ui', 'inherit', 'initial', 'unset', '-apple-system', 'buttontext']) fontesOk.add(g);

const EXT = new Set(['.css', '.scss', '.html', '.htm', '.vue', '.svelte', '.astro', '.jsx', '.tsx']);
const IGNORAR = new Set(['node_modules', 'dist', 'build', '.git', '.next', 'vendor']);
const listar = c => { const s = statSync(c); if (s.isFile()) return EXT.has(extname(c)) ? [c] : []; return readdirSync(c).filter(n => !IGNORAR.has(n)).flatMap(n => listar(join(c, n))); };
const faltando = args.filter(a => !existsSync(a));
if (faltando.length) { console.error(`Não achei: ${faltando.join(', ')}.`); process.exit(2); }
const arquivos = args.flatMap(listar);
if (!arquivos.length) { console.error('Nenhum arquivo de código nessa pasta.'); process.exit(2); }

const desvios = [];
const paraHex = (r, g, b) => '#' + [r, g, b].map(v => Math.round(+v).toString(16).padStart(2, '0')).join('');
function conferirDeclaracoes(texto, base, marca) {
  // só valores de declaração: #fade num seletor é id, não cor
  for (const m of texto.matchAll(/([\w-]+)\s*:\s*([^;{}]+)/g)) {
    const [, prop, val] = m, pos = base + m.index;
    for (const h of val.matchAll(/#[0-9a-f]{3,8}\b/gi)) if (!coresOk.has(norma(h[0]))) marca(pos, norma(h[0]));
    for (const c of val.matchAll(/rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/gi)) { const h = paraHex(c[1], c[2], c[3]); if (!coresOk.has(h)) marca(pos, `${h} (${c[0]})`); }
    if (/^(font-family|--[\w-]*font[\w-]*)$/i.test(prop) && !/^\s*var\(/i.test(val) && /[a-z]/i.test(val) && !/^\s*\d/.test(val)) {
      const primeira = nomeFonte(val.split(',')[0]);
      if (!fontesOk.has(primeira)) marca(pos, `fonte "${primeira}"`);
    }
  }
}
for (const arquivo of arquivos) {
  const texto = readFileSync(arquivo, 'utf8');
  const vistos = new Set();
  const marca = (pos, v) => { if (vistos.has(v)) return; vistos.add(v); desvios.push(`${relative('.', resolve(arquivo)).replace(/\\/g, '/')}:${texto.slice(0, pos).split('\n').length}  ${v}`); };
  if (['.css', '.scss'].includes(extname(arquivo))) { conferirDeclaracoes(texto, 0, marca); continue; }
  for (const m of texto.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)) conferirDeclaracoes(m[1], m.index + m[0].indexOf(m[1]), marca);
  for (const m of texto.matchAll(/\bstyle=(["'])([\s\S]*?)\1/gi)) conferirDeclaracoes(m[2], m.index, marca);
  for (const m of texto.matchAll(/\b(?:fill|stroke|color|stop-color)=["'](#[0-9a-f]{3,8})["']/gi)) if (!coresOk.has(norma(m[1]))) marca(m.index, norma(m[1]));
}

if (desvios.length) {
  console.log(`${desvios.length} valor(es) fora do ${arquivoDesign}. Acrescente lá, com o motivo, ou troque no código:`);
  desvios.forEach(d => console.log(`  ${d}`));
  process.exit(1);
}
console.log(`${arquivos.length} arquivo(s) conferido(s): cores e fontes estão no ${arquivoDesign}. Tamanho e espaçamento não foram conferidos.`);
