#!/usr/bin/env node
// Gera uma paleta completa a partir de uma cor, com todos os pares calculados pela fórmula da WCAG.
// Uso: node paleta.mjs "#0e5f4b" [--tema claro|escuro] [--evitar "#d71920,#8d0de3"] [--css]
// Saída: 0 todos os pares passam; 1 algum par reprova; 2 entrada inválida.
import { lerCor, razao } from './contraste.mjs';

const args = process.argv.slice(2);
const opcao = n => { const i = args.indexOf(n); if (i < 0) return null; const v = args[i + 1]; args.splice(i, 2); return v; };
const tema = opcao('--tema') || 'claro';
const evitar = (opcao('--evitar') || '').split(',').map(s => s.trim()).filter(Boolean);
const comoCss = args.includes('--css'); if (comoCss) args.splice(args.indexOf('--css'), 1);
const estranha = args.find(a => a.startsWith('-'));
if (estranha) { console.error(`Opção desconhecida: ${estranha}\nUso: paleta.mjs "#0e5f4b" [--tema claro|escuro] [--evitar "#d71920,#8d0de3"] [--css]`); process.exit(2); }
const semente = args[0];
if (!semente || !lerCor(semente) || !['claro', 'escuro'].includes(tema)) { console.error('Uso: paleta.mjs "#0e5f4b" [--tema claro|escuro] [--evitar "#d71920,#8d0de3"] [--css]'); process.exit(2); }

const paraLinear = v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
function paraOklch(rgb) {
  const [r, g, b] = rgb.map(paraLinear);
  const [l, m, s] = [.4122214708 * r + .5363325363 * g + .0514459929 * b, .2119034982 * r + .6806995451 * g + .1073969566 * b, .0883024619 * r + .2817188376 * g + .6299787005 * b].map(Math.cbrt);
  const A = 1.9779984951 * l - 2.428592205 * m + .4505937099 * s, B = .0259040371 * l + .7827717662 * m - .808675766 * s;
  return { L: .2104542553 * l + .793617785 * m - .0040720468 * s, C: Math.hypot(A, B), h: (Math.atan2(B, A) * 180 / Math.PI + 360) % 360 };
}
function linear(L, C, h) {
  const a = C * Math.cos(h * Math.PI / 180), b = C * Math.sin(h * Math.PI / 180);
  const l = (L + .3963377774 * a + .2158037573 * b) ** 3, m = (L - .1055613458 * a - .0638541728 * b) ** 3, s = (L - .0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s, -.0041960863 * l - .7034186147 * m + 1.707614701 * s];
}
// Fora do que a tela mostra, reduz o croma até caber, sem mudar claridade nem matiz
function hex(L, C, h) {
  L = Math.min(1, Math.max(0, L));
  let v = linear(L, C, h);
  while (C > 0 && v.some(x => x < -.0005 || x > 1.0005)) { C = Math.max(0, C - .002); v = linear(L, C, h); }
  const g = x => { x = Math.min(1, Math.max(0, x)); return Math.round(255 * (x <= .0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - .055)); };
  return '#' + v.map(x => g(x).toString(16).padStart(2, '0')).join('');
}
const contra = (a, b) => razao(lerCor(a), lerCor(b));
// Move a claridade até o par chegar ao mínimo
function ajustar(L, C, h, fundo, minimo, sentido) {
  let l = L;
  while (l >= 0 && l <= 1 && contra(hex(l, C, h), fundo) < minimo) l += sentido * .005;
  return hex(Math.min(1, Math.max(0, l)), C, h);
}

const s = paraOklch(lerCor(semente));
const c = {}; const notas = []; const claro = tema === 'claro';
const h = s.h, tinta = Math.min(s.C, .02);
const BRANCO = '#ffffff';
const RETORNO = { danger: 27, success: 150, warning: 70, info: 250 };

if (claro) {
  c.background = hex(.975, Math.min(s.C, .006), h); c.surface = BRANCO;
  const escuro = hex(.22, tinta, h);
  c['on-background'] = escuro; c['on-surface'] = escuro;
  c.muted = ajustar(.52, tinta, h, c.background, 4.6, -1);
  c.line = hex(.9, Math.min(s.C, .012), h);
  c['border-control'] = ajustar(.66, tinta, h, c.background, 3.1, -1);
  const seme = semente.toLowerCase(), comBranco = contra(BRANCO, seme), comTinta = contra(escuro, seme);
  if (s.L > .9 && s.C < .03) { c.primary = escuro; c['on-primary'] = BRANCO; notas.push('A cor é quase branca: a ação ficou em tinta, para continuar visível.'); }
  else if (comBranco >= 4.5) { c.primary = hex(s.L, s.C, h); c['on-primary'] = BRANCO; }
  else if (s.L >= .7 && comTinta >= 4.5) { c.primary = hex(s.L, s.C, h); c['on-primary'] = escuro; notas.push('Cor clara: o botão leva texto escuro, e links usam um tom mais escuro da mesma cor.'); }
  else { c.primary = ajustar(s.L, s.C, h, BRANCO, 4.6, -1); c['on-primary'] = BRANCO; notas.push(`${semente} com texto branco não chega a 4,5:1: a ação escureceu para ${c.primary}. A cor original continua livre para áreas sem texto.`); }
  const P = paraOklch(lerCor(c.primary)), sobeHover = P.L < .3;
  c['primary-hover'] = ajustar(P.L + (sobeHover ? .06 : -.06), P.C, h, c['on-primary'], 4.6, c['on-primary'] === BRANCO ? -1 : 1);
  c['primary-text'] = ajustar(P.L, P.C, h, c.background, 4.6, -1);
  c['primary-soft'] = hex(.95, Math.min(P.C, .04), h);
  c['on-primary-soft'] = ajustar(P.L, P.C, h, c['primary-soft'], 4.6, -1);
  c.focus = c['primary-text'];
  for (const [n, m] of Object.entries(RETORNO)) {
    c[`${n}-soft`] = hex(.95, .03, m);
    c[n] = ajustar(.5, .14, m, c[`${n}-soft`], 4.6, -1);
  }
  c['on-danger'] = BRANCO;
} else {
  c.background = hex(.19, Math.min(s.C, .012), h); c.surface = hex(.235, Math.min(s.C, .014), h);
  const clara = hex(.93, Math.min(s.C, .01), h);
  c['on-background'] = clara; c['on-surface'] = clara;
  c.muted = ajustar(.72, tinta, h, c.surface, 4.6, 1);
  c.line = hex(.32, Math.min(s.C, .012), h);
  c['border-control'] = ajustar(.52, tinta, h, c.surface, 3.1, 1);
  const croma = Math.min(s.C, .14);
  c.primary = ajustar(Math.max(s.L, .68), croma, h, c.surface, 4.6, 1);
  c['on-primary'] = hex(.18, tinta, h);
  const P = paraOklch(lerCor(c.primary));
  c['primary-hover'] = hex(Math.min(.95, P.L + .05), croma, h);
  c['primary-text'] = c.primary;
  c['primary-soft'] = hex(.3, Math.min(croma, .05), h);
  c['on-primary-soft'] = ajustar(.85, croma, h, c['primary-soft'], 4.6, 1);
  c.focus = c.primary;
  notas.push('Tema escuro: a cor foi clareada e dessaturada. Mostre em imagem antes de aplicar.');
  for (const [n, m] of Object.entries(RETORNO)) {
    c[`${n}-soft`] = hex(.28, .05, m);
    c[n] = ajustar(.76, .12, m, c[`${n}-soft`], 4.6, 1);
  }
  c['on-danger'] = hex(.18, .02, 27);
}

// Conflitos de significado e de mercado
const distancia = (a, b) => { const d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
if (s.C > .05 && distancia(h, RETORNO.danger) < 20) notas.push('Marca na faixa do vermelho: ação e erro ficam parecidos. Erro sempre com ícone e texto.');
if (s.C > .12 && h >= 262 && h <= 292) notas.push('Faixa do índigo e do violeta, comum em tela de gerador: confira se esta cor é mesmo da marca.');
for (const e of evitar) {
  const rgb = lerCor(e); if (!rgb) continue;
  const o = paraOklch(rgb);
  if (s.C > .04 && o.C > .04 && distancia(h, o.h) < 25) notas.push(`Matiz próximo de ${e}, que você pediu para evitar.`);
}

const PARES = [
  ['on-background', 'background', 4.5], ['on-surface', 'surface', 4.5], ['muted', 'background', 4.5], ['muted', 'surface', 4.5],
  ['on-primary', 'primary', 4.5], ['on-primary', 'primary-hover', 4.5], ['primary-text', 'background', 4.5], ['primary-text', 'surface', 4.5], ['on-primary-soft', 'primary-soft', 4.5],
  ['on-danger', 'danger', 4.5], ...Object.keys(RETORNO).flatMap(n => [[n, `${n}-soft`, 4.5], [n, 'surface', 4.5]]),
  ['border-control', 'background', 3], ['border-control', 'surface', 3], ['focus', 'background', 3], ['focus', 'surface', 3],
];

if (comoCss) console.log(`:root {\n${Object.entries(c).map(([k, v]) => `  --${k}: ${v};`).join('\n')}\n}`);
else console.log(`colors:\n${Object.entries(c).map(([k, v]) => `  ${k}: "${v}"`).join('\n')}`);
console.log(`\nContraste, tema ${tema}, a partir de ${semente}:`);
let reprovados = 0;
for (const [a, b, min] of PARES) {
  const r = contra(c[a], c[b]), ok = r >= min; if (!ok) reprovados++;
  console.log(`  ${ok ? 'passa' : 'FALHA'} ${r.toFixed(2).replace('.', ',')}:1  ${a} sobre ${b}  (mínimo ${String(min).replace('.', ',')})`);
}
for (const n of notas) console.log(`  nota  ${n}`);
console.log('\nA conta garante leitura, não beleza. Olhe a paleta aplicada numa tela real.');
process.exit(reprovados ? 1 : 0);
