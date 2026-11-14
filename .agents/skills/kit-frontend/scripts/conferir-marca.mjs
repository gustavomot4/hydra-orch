#!/usr/bin/env node
// Confere se MARCA.md e design/marca/ estão completos. Não julga se a marca é boa: isso é do dono.
// Uso: node conferir-marca.mjs [pasta do projeto]
// Saída: 0 sem falha; 1 com falha; 2 sem MARCA.md.
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

const raiz = resolve(process.argv[2] || '.');
const arquivo = join(raiz, 'MARCA.md');
if (!existsSync(arquivo)) { console.error(`Não achei ${arquivo}. Crie a partir de assets/modelos/marca.md.`); process.exit(2); }

const texto = readFileSync(arquivo, 'utf8').replace(/\r\n/g, '\n').replace(/<!--[\s\S]*?-->/g, '');
const achados = [];
const falha = m => achados.push(['FALHA', m]);
const aviso = m => achados.push(['aviso', m]);
const secao = nome => new RegExp(`^## ${nome}\\s*\\n([\\s\\S]*?)(?=^## |$(?![\\s\\S]))`, 'm').exec(texto)?.[1] ?? null;
const linhasDeTabela = t => (t || '').split('\n').filter(l => l.startsWith('|')).slice(2).filter(l => l.replace(/[|\s-]/g, ''));

const tamanho = /\*\*Brief:\*\*\s*(curto|completo)/i.exec(texto)?.[1]?.toLowerCase();
if (!tamanho) falha('Falta "**Brief:** curto" ou "**Brief:** completo".');
const completo = tamanho !== 'curto';

const restantes = [...new Set(texto.match(/<[^>\n]{2,}>/g) || [])];
if (restantes.length) falha(`Campos do modelo sem preencher: ${restantes.slice(0, 4).join(', ')}.`);

for (const s of ['Essência', 'Público e personas', 'Personalidade', 'Mensagem e voz', 'O que isso muda na tela', ...(completo ? ['Concorrentes'] : [])]) {
  if (secao(s) === null) falha(`Falta a seção "${s}".`);
}

const pub = secao('Público e personas') || '';
const personas = pub.split(/^### /m).slice(1);
if (!personas.length) falha('Nenhuma persona.');
if (personas.length > 3) aviso(`${personas.length} personas: mais de 3 raramente mudam alguma decisão.`);
for (const p of personas) {
  const nome = p.split('\n')[0].trim();
  const base = /\*\*Base:\*\*\s*(hip[oó]tese|pesquisa|dado)/i.exec(p)?.[1]?.toLowerCase();
  if (!base) falha(`Persona "${nome}" sem base: diga se é hipótese, pesquisa ou dado.`);
  else if (base.startsWith('hip') && !/\*\*Como validar:\*\*/.test(p)) aviso(`Persona "${nome}" é hipótese e não diz como validar.`);
}

const pers = secao('Personalidade') || '';
const palavras = [...pers.matchAll(/^- \*\*([^*]+)\*\*/gm)].map(m => m[1].trim().toLowerCase());
if (palavras.length < 3) falha(`Personalidade com ${palavras.length} palavra(s); o esperado são 3.`);
for (const l of pers.split('\n').filter(x => x.startsWith('- **'))) if (!/\bn[aã]o\b/i.test(l)) aviso(`Palavra sem o que ela recusa: ${l.slice(2, 40)}`);
const genericas = palavras.filter(p => ['moderno', 'moderna', 'inovador', 'inovadora', 'confiável', 'simples', 'premium', 'profissional', 'clean', 'tecnológico', 'tecnológica'].includes(p));
if (genericas.length) aviso(`Palavras que qualquer concorrente diria: ${genericas.join(', ')}.`);
if (!/formal/i.test(pers) || !/engra[cç]ad/i.test(pers) || !/irreverente/i.test(pers) || !/entusiasmad/i.test(pers)) aviso('Tom sem as quatro dimensões.');

const msg = secao('Mensagem e voz') || '';
const frases = (msg.split(/^### Frases/m)[1] || '').split('\n').filter(l => l.startsWith('- '));
if (frases.length < 3) falha(`Voz com ${frases.length} frase(s) real(is); o mínimo são 3.`);

const muda = linhasDeTabela(secao('O que isso muda na tela'));
if (muda.length < 3) falha(`"O que isso muda na tela" tem ${muda.length} linha(s); o mínimo são 3. Sem isso, o brief não muda nada.`);

if (completo) {
  const conc = secao('Concorrentes') || '';
  if (linhasDeTabela(conc).length < 3) falha('Menos de 3 concorrentes, contando o que a pessoa usa hoje.');
  if (!/\*\*Espaço livre:\*\*\s*\S/.test(conc)) falha('Concorrentes sem o "Espaço livre".');
}

// Espaço livre sem nenhum concorrente olhado é palpite, por mais bem escrito que esteja
const situacoes = linhasDeTabela(secao('Concorrentes')).map(l => l.split('|').at(-2) || '');
if (/Espaço livre/.test(texto) && !situacoes.some(s => /observado|verificado/i.test(s) && !/n[aã]o verificado/i.test(s))) aviso('Nenhum concorrente foi olhado de verdade: o espaço livre é hipótese. Tente scripts/medir-referencia.mjs.');

// Marca que já existe: sem o arquivo, a direção desenha um substituto, e o dono não reconhece a própria marca
if (secao('Identidade existente') !== null && !/\*\*Arquivo do logo:\*\*\s*\S/.test(secao('Identidade existente'))) aviso('Marca existente sem dizer se o arquivo do logo foi recebido. Peça antes de mostrar as direções.');

// O kit só existe depois da escolha da direção: sem a pasta, é aviso
const pasta = join(raiz, 'design', 'marca');
if (!existsSync(pasta)) aviso('Ainda não há design/marca/. O kit vem depois da escolha da direção.');
else {
  const exigidos = completo ? ['logo-positivo.svg', 'logo-negativo.svg', 'icone.svg', 'manual.html'] : ['logo-positivo.svg'];
  for (const a of exigidos) if (!existsSync(join(pasta, a))) falha(`Falta design/marca/${a}.`);
  const svgs = readdirSync(pasta).filter(a => a.endsWith('.svg'));
  for (const a of svgs) {
    const s = readFileSync(join(pasta, a), 'utf8');
    if (/<text[\s>]/.test(s)) falha(`${a} usa <text>: em outro aparelho a letra muda. Converta em curvas com scripts/logotipo.py.`);
    if (/<image[\s>]/.test(s)) falha(`${a} embute imagem: o logotipo precisa ser vetorial.`);
    if (!/viewBox/.test(s)) aviso(`${a} sem viewBox: não escala bem.`);
  }
  if (svgs.includes('logo-positivo.svg') && svgs.includes('logo-negativo.svg') && readFileSync(join(pasta, 'logo-positivo.svg'), 'utf8') === readFileSync(join(pasta, 'logo-negativo.svg'), 'utf8')) aviso('logo-positivo.svg e logo-negativo.svg são iguais.');
  const fontes = join(pasta, 'fontes');
  if (existsSync(fontes)) {
    const lista = readdirSync(fontes);
    if (lista.some(a => /\.(woff2?|ttf|otf)$/i.test(a)) && !lista.some(a => /licen|ofl|copying/i.test(a))) aviso('design/marca/fontes/ sem o arquivo de licença ao lado da fonte.');
  }
}

console.log(`Brief ${tamanho || '?'}: ${personas.length} persona(s), ${palavras.length} palavra(s), ${frases.length} frase(s), ${muda.length} decisão(ões) de design.`);
for (const [n, m] of achados) console.log(`  ${n}  ${m}`);
const falhas = achados.filter(a => a[0] === 'FALHA').length;
console.log(`${falhas} falha(s), ${achados.length - falhas} aviso(s). Quem julga a marca é o dono: isto só confere se ela está completa.`);
process.exit(falhas ? 1 : 0);
