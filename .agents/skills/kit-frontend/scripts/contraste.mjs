#!/usr/bin/env node
// Calcula contraste pela fórmula de luminância relativa da WCAG.
// Uso: node contraste.mjs "#ffffff" "#0d6e66"    um par
//      node contraste.mjs DESIGN.md              todo par de componente e todo par nome/on-nome do arquivo
// Saída: 0 tudo passa; 1 algum par reprova; 2 entrada inválida.
import { readFileSync, existsSync } from 'node:fs';

const lin = v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
const lum = c => .2126 * lin(c[0]) + .7152 * lin(c[1]) + .0722 * lin(c[2]);
export const razao = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };

// aceita #rgb, #rrggbb, rgb() e oklch()
export function lerCor(t) {
  t = String(t).trim().replace(/^["']|["']$/g, '');
  let m;
  if ((m = /^#([0-9a-f]{3})$/i.exec(t))) return [...m[1]].map(c => parseInt(c + c, 16));
  if ((m = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(t))) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
  if ((m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(t))) return [+m[1], +m[2], +m[3]];
  if ((m = /^oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)/i.exec(t))) {
    const L = m[2] ? +m[1] / 100 : +m[1], C = +m[3], h = +m[4] * Math.PI / 180;
    const a = C * Math.cos(h), b = C * Math.sin(h);
    const l = (L + .3963377774 * a + .2158037573 * b) ** 3, mm = (L - .1055613458 * a - .0638541728 * b) ** 3, s = (L - .0894841775 * a - 1.291485548 * b) ** 3;
    const g = v => { v = Math.min(1, Math.max(0, v)); return 255 * (v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055); };
    return [g(4.0767416621 * l - 3.3077115913 * mm + .2309699292 * s), g(-1.2684380046 * l + 2.6097574011 * mm - .3413193965 * s), g(-.0041960863 * l - .7034186147 * mm + 1.707614701 * s)];
  }
  return null;
}

// leitor mínimo do bloco YAML do DESIGN.md: só colors e components
export function paresDoDesign(texto) {
  const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(texto);
  if (!fm) return { cores: {}, pares: [] };
  const cores = {}, comps = {}; let secao = null, comp = null;
  for (const linha of fm[1].split(/\r?\n/)) {
    if (/^\S/.test(linha)) { secao = linha.split(':')[0].trim(); comp = null; continue; }
    if (secao === 'colors') { const m = /^\s+([\w-]+):\s*(.+?)\s*$/.exec(linha); if (m) cores[m[1]] = m[2].replace(/^["']|["']$/g, ''); }
    if (secao === 'components') {
      const n = /^ {2}([\w-]+):\s*$/.exec(linha); if (n) { comp = n[1]; comps[comp] = {}; continue; }
      const m = /^\s{4,}([\w-]+):\s*(.+?)\s*$/.exec(linha); if (m && comp) comps[comp][m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  }
  const resolver = v => { const r = /^\{colors\.([\w-]+)\}$/.exec(v || ''); return r ? cores[r[1]] : v; };
  const pares = [];
  for (const [nome, c] of Object.entries(comps)) if (c.backgroundColor && c.textColor) pares.push({ nome: `componente ${nome}`, frente: resolver(c.textColor), fundo: resolver(c.backgroundColor), minimo: 4.5 });
  for (const nome of Object.keys(cores)) { const base = /^on-(.+)$/.exec(nome); if (base && cores[base[1]]) pares.push({ nome: `${nome} sobre ${base[1]}`, frente: cores[nome], fundo: cores[base[1]], minimo: 4.5 }); }
  return { cores, pares };
}

const eu = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/').split('/').pop());
if (eu) {
  const a = process.argv.slice(2);
  const mostrar = (nome, f, b, min) => { const cf = lerCor(f), cb = lerCor(b); if (!cf || !cb) { console.log(`  ?     ${nome}: não li a cor (${f} / ${b})`); return null; } const r = razao(cf, cb); console.log(`  ${r >= min ? 'passa' : 'FALHA'} ${r.toFixed(2).replace('.', ',')}:1  ${nome}  ${f} sobre ${b}`); return r >= min; };
  if (a.length === 2 && lerCor(a[0]) && lerCor(a[1])) {
    const r = razao(lerCor(a[0]), lerCor(a[1]));
    console.log(`${r.toFixed(2).replace('.', ',')}:1  texto normal (4,5): ${r >= 4.5 ? 'passa' : 'reprova'}  texto grande e interface (3,0): ${r >= 3 ? 'passa' : 'reprova'}`);
    process.exit(r >= 3 ? 0 : 1);
  }
  if (a.length === 1 && existsSync(a[0])) {
    const { pares, cores } = paresDoDesign(readFileSync(a[0], 'utf8'));
    if (!Object.keys(cores).length) { console.error('Não achei o bloco colors no início do arquivo.'); process.exit(2); }
    console.log(`${Object.keys(cores).length} cores, ${pares.length} pares:`);
    const res = pares.map(p => mostrar(p.nome, p.frente, p.fundo, p.minimo));
    process.exit(res.includes(false) ? 1 : 0);
  }
  console.error('Uso: contraste.mjs "#fff" "#0d6e66"  ou  contraste.mjs DESIGN.md');
  process.exit(2);
}
