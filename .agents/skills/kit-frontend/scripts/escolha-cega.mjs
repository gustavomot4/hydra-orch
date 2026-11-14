#!/usr/bin/env node
// Prepara a escolha da direção por quem não fez as telas: confere ideias.md, compara as direções, sorteia rótulos e captura as imagens.
// Só avança se a primeira ideia e as referências de fora do setor estiverem escritas: quem pula esse passo não chega à escolha.
// Uso: node escolha-cega.mjs [pasta das direções] [--marca MARCA.md]
// Saída: 0 pacote pronto; 1 falta algo ou as direções são quase iguais; 2 não conseguiu rodar.
import { spawn, spawnSync } from 'node:child_process';
import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync, mkdtempSync, rmSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { randomInt } from 'node:crypto';
import { pathToFileURL, fileURLToPath } from 'node:url';

const USO = 'Uso: escolha-cega.mjs [pasta das direções] [--marca MARCA.md]';
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) { console.log(USO); process.exit(0); }
const valor = nome => { const i = args.indexOf(nome); if (i < 0) return null; const v = args[i + 1]; args.splice(i, 2); return v; };
const arquivoMarca = resolve(valor('--marca') || 'MARCA.md');
const pasta = resolve(args[0] || 'design/direcoes');
if (!existsSync(pasta)) { console.error(`Não achei ${pasta}. Nada foi preparado.`); process.exit(2); }
const arquivos = readdirSync(pasta).filter(f => f.endsWith('.html') && !/^(index|prancha|comparativo)/i.test(f)).sort();
if (arquivos.length < 2) { console.error(`Achei ${arquivos.length} direção(ões) em ${pasta}: preciso de pelo menos 2 arquivos HTML.`); process.exit(2); }

// A ordem importa: a primeira ideia e as referências vêm antes das direções. O script só vê se estão escritas, não quando foram.
const problemas = [];
const arquivoPrimeira = join(pasta, 'primeira-ideia.md'), arquivoIdeias = join(pasta, 'ideias.md');
const vazio = t => !t.trim() || /<[^>\n]{2,}>/.test(t);
// num teste real, a "primeira ideia" foi escrita depois de medir referências e baixar fontes: a data do arquivo expõe isso
const primeiraEm = existsSync(arquivoPrimeira) && !vazio(readFileSync(arquivoPrimeira, 'utf8')) ? statSync(arquivoPrimeira).mtimeMs : null;
if (primeiraEm === null) problemas.push(`Escreva em ${arquivoPrimeira} a primeira ideia: a que veio antes de todas, em uma frase, antes de qualquer referência.`);
const antesDaPrimeira = c => primeiraEm !== null && statSync(c).mtimeMs < primeiraEm;
for (const a of arquivos) if (antesDaPrimeira(join(pasta, a))) problemas.push(`${a} é mais antigo que primeira-ideia.md: ela já não é a primeira.`);
if (!existsSync(arquivoIdeias)) problemas.push(`Falta ${arquivoIdeias}, com as referências e os conceitos. Modelo em assets/modelos/ideias.md.`);
else {
  const texto = readFileSync(arquivoIdeias, 'utf8').replace(/\r\n/g, '\n').replace(/<!--[\s\S]*?-->/g, '');
  const secao = nome => new RegExp(`^## ${nome}\\s*\\n([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, 'm').exec(texto)?.[1] ?? '';
  const linhas = t => t.split('\n').filter(l => l.startsWith('|')).slice(2).map(l => l.split('|').slice(1, -1).map(c => c.trim())).filter(c => c.some(Boolean));
  const referencias = linhas(secao('Referências de fora do setor')).filter(c => !vazio(c.join(' ')));
  if (referencias.length < 2) problemas.push(`Faltam referências de fora do setor: ${referencias.length} de 2.`);
  for (const [nome, , medida] of referencias) {
    const captura = /[\w./\\-]+\.(?:jpe?g|png)/i.exec(medida || '')?.[0];
    const achada = captura && [captura, join(pasta, captura), join(pasta, '..', captura), join(pasta, '..', '..', captura)].map(c => resolve(c)).find(c => existsSync(c));
    if (captura ? !achada : !/erro|bloque|n[aã]o abriu|sem rede/i.test(medida || '')) problemas.push(`Referência "${nome}" sem medida: rode scripts/medir-referencia.mjs e cite a captura, ou o erro que deu ao tentar.`);
    if (achada && antesDaPrimeira(achada)) problemas.push(`A captura de "${nome}" é mais antiga que primeira-ideia.md: ela já não é a primeira.`);
    // os sites de references/marca/criatividade.md já estão no kit: repetidos, todo projeto sai do mesmo repertório
    if (/nubank|\bc6\b|ita[uú]|\b99|ifood|valorant|fortnite|epic ?(games|store)|hyper3d|cozygpu|cequence/i.test(nome)) problemas.push(`"${nome}" já está no repertório do kit: procure uma referência que ele não cita.`);
  }
  const conceitos = linhas(secao('Conceitos')).filter(c => !vazio(c.join(' ')));
  if (conceitos.length < arquivos.length) problemas.push(`Conceitos escritos: ${conceitos.length}; direções: ${arquivos.length}.`);
  if (conceitos.filter(c => /^sim/i.test(c.at(-1) || '')).length > 1) problemas.push('Mais de uma direção parte da primeira ideia: no máximo uma.');
  if (/recomend/i.test(texto)) problemas.push('Tire a recomendação de ideias.md: quem escolhe é quem não fez as telas.');
}
if (!existsSync(arquivoMarca)) problemas.push(`Falta ${arquivoMarca}: quem escolhe precisa saber o que a marca quer dizer.`);
if (problemas.length) { console.log(`Ainda não dá para escolher:\n${problemas.map(p => `  - ${p}`).join('\n')}`); process.exit(1); }

// Direções quase iguais não vão à escolha: seria escolher entre três peles da mesma página.
const aqui = dirname(fileURLToPath(import.meta.url));
const comparacao = spawnSync(process.execPath, [join(aqui, 'comparar-direcoes.mjs'), pasta], { encoding: 'utf8' });
if (comparacao.status !== 0) { console.log(comparacao.stdout + comparacao.stderr); process.exit(comparacao.status === 1 ? 1 : 2); }

const exe = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`, 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(c => c && existsSync(c));
if (!exe) { console.error('Não achei Chrome, Edge nem Chromium. Defina CHROME_PATH.'); process.exit(2); }
const perfil = mkdtempSync(join(tmpdir(), 'kit-frontend-'));
const porta = 10000 + randomInt(90);
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

// rótulo sorteado: nada no nome do arquivo diz qual é a A, a B ou a C
const letras = 'kmrtwz'.split('');
for (let i = letras.length - 1; i > 0; i--) { const j = randomInt(i + 1); [letras[i], letras[j]] = [letras[j], letras[i]]; }
const saida = join(pasta, 'cega'); rmSync(saida, { recursive: true, force: true }); mkdirSync(saida, { recursive: true });
const chave = {};
const abrir = async (arquivo, w, h, movel) => {
  await cdp('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: movel });
  await cdp('Page.navigate', { url: pathToFileURL(join(pasta, arquivo)).href });
  for (let i = 0; i < 50; i++) { await dorme(100); if (await ev('document.readyState') === 'complete') break; }
  await ev(`Promise.race([Promise.all([...document.images].map(i => { i.loading = 'eager'; return i.complete ? 0 : new Promise(r => { i.addEventListener('load', r, { once: true }); i.addEventListener('error', r, { once: true }); }); })), new Promise(r => setTimeout(r, 4000))]).then(() => 1)`);
  await ev('document.fonts ? document.fonts.ready.then(() => 1) : 1'); await dorme(300);
};
const imagens = [];
const gravar = (nome, c) => { if (c.result?.data) { writeFileSync(join(saida, nome), Buffer.from(c.result.data, 'base64')); imagens.push(nome); } };
// camada fixa na página inteira cai no meio do conteúdo e cobre texto, sem ser defeito da tela: ela aparece só na primeira dobra
const ESCONDER_FIXAS = `(() => { const visita = r => { for (const e of r.querySelectorAll('*')) { if (getComputedStyle(e).position === 'fixed') e.style.setProperty('display', 'none', 'important'); if (e.shadowRoot) visita(e.shadowRoot); } }; visita(document.body); return 1; })()`;
// página alta vira várias imagens: inteira, ela chega reduzida a quem lê, e o texto fica ilegível
const capturarInteira = async (nome, w) => {
  await ev(ESCONDER_FIXAS);
  const altura =Math.min(await ev('document.documentElement.scrollHeight'), 8000), PEDACO = 1600;
  for (let y = 0, n = 1; y < altura; y += PEDACO, n++) gravar(`${nome}-${n}.jpg`, await cdp('Page.captureScreenshot', { format: 'jpeg', quality: 80, captureBeyondViewport: true, clip: { x: 0, y, width: w, height: Math.min(PEDACO, altura - y), scale: 1 } }));
};
for (const [i, arquivo] of arquivos.entries()) {
  const letra = letras[i]; chave[letra] = arquivo;
  await abrir(arquivo, 1440, 900, false);
  gravar(`tela-${letra}-primeira-dobra.jpg`, await cdp('Page.captureScreenshot', { format: 'jpeg', quality: 80 }));
  await capturarInteira(`tela-${letra}-computador`, 1440);
  await abrir(arquivo, 375, 812, true);
  gravar(`tela-${letra}-celular-primeira-dobra.jpg`, await cdp('Page.captureScreenshot', { format: 'jpeg', quality: 80 }));
  await capturarInteira(`tela-${letra}-celular`, 375);
}
ws.close();

// o que a marca quer dizer fica noutro arquivo: quem julga só abre depois de gravar o que viu
const marca = readFileSync(arquivoMarca, 'utf8').replace(/\r\n/g, '\n').replace(/<!--[\s\S]*?-->/g, '');
const campo = rotulo => new RegExp(`\\*\\*${rotulo}:\\*\\*\\s*(.+)`).exec(marca)?.[1]?.trim() || 'não informado';
const personalidade = (/^## Personalidade\s*\n([\s\S]*?)(?=^##|(?![\s\S]))/m.exec(marca)?.[1] || '').split('\n').filter(l => l.startsWith('- **')).map(l => l.replace(/\*\*/g, ''));
const rotulos = [...new Set(imagens.map(n => n.split('-')[1].toUpperCase()))].sort().join(', ');
const pedido = `# Escolha entre ${arquivos.length} telas

Você vai escolher entre telas de um mesmo produto, sem saber quem as fez nem qual é a preferida de ninguém. Responda só pelo que vê. Crítica e elogio precisam apontar o lugar da tela. "Correta e sem graça" não é escolha: se nenhuma serve, diga "nenhuma".

Abra só estas imagens, nesta pasta, e nada além delas: ${saida}

${imagens.map(n => `- ${n}`).join('\n')}

## Etapa 1

Para cada tela (${rotulos}):

1. O que ela promete e para quem, numa frase?
2. O que você sente em 5 segundos?
3. O que lembraria dela amanhã?
4. Com outro texto, serviria para outro setor? Qual?

Grave as respostas em ${join(pasta, 'escolha-1.md')}. Se esse arquivo já existir, não o abra: use ${join(pasta, 'escolha-2.md')}. Só depois abra ${join(saida, 'etapa-2.md')}, que diz o que a marca quer dizer. Não mude o que gravou.
`;
const etapa2 = `# Etapa 2

A marca quer dizer isto:

- Promessa: ${campo('Promessa, em uma frase')}
- O que nunca seria: ${campo('O que nunca seria')}
- Em 5 segundos, sentir: ${campo('Em 5 segundos, a pessoa precisa sentir')}
- Lembrar: ${campo('E lembrar')}
${personalidade.join('\n')}

Qual tela diz isso melhor? Diga a letra ou "nenhuma", a margem (clara, leve ou empate) e o lugar da tela que prova. Diga o que precisa mudar na escolhida e o que vale pegar das outras.

Acrescente a resposta no mesmo arquivo, depois da etapa 1.
`;
writeFileSync(join(saida, 'pedido.md'), pedido);
writeFileSync(join(saida, 'etapa-2.md'), etapa2);
writeFileSync(join(pasta, 'cega-chave.json'), JSON.stringify(chave, null, 1) + '\n');
console.log(`Pacote pronto em ${saida}: ${arquivos.length} direções, ${imagens.length} imagens.\n\nEntregue ${join(saida, 'pedido.md')} a dois agentes novos, um de cada vez, sem o contexto desta conversa. Num teste, dois agentes escolheram direções diferentes: se discordarem, é empate. A chave está em ${join(pasta, 'cega-chave.json')}: não entregue e não abra antes das respostas.\nSem como chamar um agente novo, escreva "escolha sem juízo externo" no DESIGN.md.`);
await fechar(0);
