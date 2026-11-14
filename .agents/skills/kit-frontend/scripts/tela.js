// Audita a tela renderizada. Roda dentro da página, pelo verificar.mjs ou colado no console do navegador.
// Devolve { achados: [{ id, nivel, msg, exemplos }], medidas }. nivel: falha | aviso.
// a11y-* vem da WCAG 2.2 e da ABNT NBR 17225; g-* vem do perfil de gosto; ia-* vem de references/marca/anti-generico.md; q-* vem de falhas vistas em teste real (docs/testes/2026-10-31-outro-agente).
((opcoes = window.__kitOpcoes || {}) => {
  const papel = opcoes.papel || 'desktop';
  // linhas de "Do's and Don'ts" que explicam uma escolha; "inter" não pode casar com "interface"
  const motivos = (opcoes.fontesComMotivo || []).map(l => l.toLowerCase());
  const temMotivo = f => { const r = new RegExp('(^|[^\\p{L}\\p{N}])' + f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '($|[^\\p{L}\\p{N}])', 'u'); return motivos.some(l => r.test(l)); };
  const publicos = opcoes.publicos || [];   // do PRODUTO.md; ver references/qualidade/publicos.md
  const achados = [];
  const achar = (id, nivel, msg, exemplos = []) => achados.push({ id, nivel, msg, exemplos: [...new Set(exemplos)].slice(0, 5) });
  const cs = (e, p) => getComputedStyle(e, p);
  const num = v => parseFloat(v) || 0;
  const curto = (t, n = 34) => (t || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const vis = e => {
    const r = e.getBoundingClientRect(), s = cs(e);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0 && !e.closest('[inert],[hidden]');
  };
  const todos = [...document.querySelectorAll('body *')].filter(e => !e.closest('svg') || e.tagName === 'svg').filter(vis);

  // cor: o canvas converte qualquer formato do navegador para sRGB
  const tela2d = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const cor = c => { tela2d.clearRect(0, 0, 1, 1); tela2d.fillStyle = '#000'; tela2d.fillStyle = c; tela2d.fillRect(0, 0, 1, 1); const d = tela2d.getImageData(0, 0, 1, 1).data; return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 }; };
  const sobre = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lin = v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
  const lum = c => .2126 * lin(c.r) + .7152 * lin(c.g) + .0722 * lin(c.b);
  const razao = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const satura = c => { const m = Math.max(c.r, c.g, c.b), n = Math.min(c.r, c.g, c.b); return m ? (m - n) / m : 0; };
  const matiz = c => { const m = Math.max(c.r, c.g, c.b), n = Math.min(c.r, c.g, c.b), d = m - n; if (!d) return 0; const h = m === c.r ? (c.g - c.b) / d % 6 : m === c.g ? (c.b - c.r) / d + 2 : (c.r - c.g) / d + 4; return (h * 60 + 360) % 360; };

  const sobrepoe = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  const midia = 'img,svg,video,picture,canvas';
  // fundo efetivo; null quando há imagem ou gradiente atrás do texto (não dá para medir assim)
  const fundo = e => {
    const r = e.getBoundingClientRect(), pilha = [];
    for (let n = e, nivel = 0; n; n = n.parentElement, nivel++) {
      const s = cs(n);
      if (s.backgroundImage !== 'none') return null;
      if (nivel < 7 && [...n.querySelectorAll(midia)].some(m => !m.closest('button,a') && !m.contains(e) && m.getBoundingClientRect().width > 80 && sobrepoe(m.getBoundingClientRect(), r))) return null;
      const c = cor(s.backgroundColor);
      if (c.a > 0) { pilha.push(c); if (c.a === 1) break; }
    }
    let b = { r: 255, g: 255, b: 255, a: 1 };
    for (const c of pilha.reverse()) b = sobre(c, b);
    return b;
  };

  // textos visíveis
  const comTexto = new Map();
  const andador = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = andador.nextNode());) {
    const p = n.parentElement, t = n.textContent.trim();
    if (!t || !p || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TITLE'].includes(p.tagName) || p.closest('svg') || !vis(p)) continue;
    comTexto.set(p, (comTexto.get(p) || '') + ' ' + t);
  }
  const textos = [...comTexto.keys()];
  const oculto = e => { const r = e.getBoundingClientRect(); return r.right <= 0 || r.bottom <= -2000 || r.left >= innerWidth + 2000 || e.closest('[aria-hidden="true"]'); };

  // medidas gerais
  const contagem = (lista, f) => { const m = {}; lista.forEach(i => { const k = f(i); m[k] = (m[k] || 0) + (comTexto.get(i) || '').length; }); return Object.entries(m).sort((a, b) => b[1] - a[1]); };
  const familias = contagem(textos, e => cs(e).fontFamily.split(',')[0].replace(/["']/g, '').trim());
  const tamanhos = [...new Set(textos.map(e => num(cs(e).fontSize)))].sort((a, b) => a - b);
  const primeiraDobra = e => { const r = e.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0 && r.left < innerWidth && r.right > 0; };
  // header com o h1 é herói, não cabeçalho: o texto dele conta
  const foraDaConta = e => e.closest('nav,footer,[aria-hidden="true"]') || (e.closest('header') && !e.closest('header').querySelector('h1'));
  const palavrasDobra = textos.filter(e => primeiraDobra(e) && !foraDaConta(e)).reduce((n, e) => n + (comTexto.get(e) || '').trim().split(/\s+/).length, 0);

  // --- acessibilidade -------------------------------------------------------------------------------
  const interativos = todos.filter(e => e.matches('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=radio],[role=checkbox],[role=switch],[role=menuitem],[tabindex]:not([tabindex="-1"])'));
  const nomeDe = e => {
    if (e.getAttribute('aria-label')) return e.getAttribute('aria-label');
    const ref = e.getAttribute('aria-labelledby');
    if (ref) return ref.split(/\s+/).map(i => document.getElementById(i)?.textContent || '').join(' ').trim();
    if (e.labels && e.labels.length) return [...e.labels].map(l => l.textContent).join(' ').trim();
    if (e.matches('input[type=submit],input[type=button]')) return e.value;
    if (e.matches('input,select,textarea')) return e.title || '';
    return (e.textContent || '').trim() || e.querySelector('img[alt]')?.alt || e.querySelector('svg[aria-label]')?.getAttribute('aria-label') || e.querySelector('svg title')?.textContent || e.title || '';
  };

  const documento = new URL(location.href);
  documento.hash = '';
  const ancorasAusentes = [], links = [];
  for (const a of interativos.filter(e => e.matches('a[href]'))) {
    let destino;
    try { destino = new URL(a.href); } catch { continue; }
    const local = documento.protocol === 'file:' && destino.protocol === 'file:' && !destino.hostname;
    const mesmaOrigem = ['http:', 'https:'].includes(destino.protocol) && destino.origin === documento.origin;
    if (!local && !mesmaOrigem) continue;
    const fragmento = destino.hash.slice(1).split(':~:')[0];
    destino.hash = '';
    const rotulo = curto(nomeDe(a), 64);
    if (destino.href !== documento.href) {
      links.push({ destino: destino.href, rotulo });
      continue;
    }
    if (!fragmento || /^!?\//.test(fragmento)) continue; // topo, fragmento de texto ou rota por hash
    let alvo = fragmento;
    try { alvo = decodeURIComponent(fragmento); } catch { /* o navegador ainda aceita o ID literal */ }
    if ([fragmento, alvo].some(id => /^top$/i.test(id) || document.getElementById(id) ||
      [...document.getElementsByName(id)].some(e => e.localName === 'a'))) continue;
    ancorasAusentes.push(rotulo ? `${rotulo} → #${fragmento}` : `#${fragmento}`);
  }
  if (ancorasAusentes.length) achar('q-ancora-sem-destino', 'falha', 'Link para uma âncora sem destino nesta tela.', ancorasAusentes);

  const rastros = [];
  for (const e of textos) {
    if (e.closest('code,pre,kbd,samp,var,[data-conferido~="q-texto-de-implementacao"]')) continue;
    if (e.checkVisibility && !e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
    const trecho = comTexto.get(e).trim();
    const encontrado = /\[object Object\]|\{\{\s*[\w$][\w$.[\]'"]*\s*\}\}|\$\{\s*[\w$][\w$.[\]'"]*\s*\}|(?:R\$|US\$|€|\$|:)\s*NaN\b|\bNaN(?=\s*(?:%|\/))|^NaN$/.exec(trecho);
    if (encontrado) rastros.push(curto(trecho.slice(Math.max(0, encontrado.index - 24)), 96));
  }
  if (rastros.length) achar('q-texto-de-implementacao', 'falha', 'Valor de código ou expressão de template foi exibido na tela.', rastros);

  if (papel === 'desktop') {
    if (!document.documentElement.lang) achar('a11y-idioma', 'falha', '<html> sem lang.');
    if (!document.title.trim()) achar('a11y-titulo-aba', 'falha', 'Página sem <title>.');
    const mains = document.querySelectorAll('main,[role=main]').length;
    if (mains !== 1) achar('a11y-main', 'falha', `Esperado 1 <main>; há ${mains}.`);
    const h1s = [...document.querySelectorAll('h1')].filter(vis).length;
    if (h1s !== 1) achar('a11y-h1', 'falha', `Esperado 1 <h1>; há ${h1s}.`);
    const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => ({ n: +h.tagName[1], t: curto(h.textContent, 24) }));
    const saltos = hs.filter((h, i) => i && h.n - hs[i - 1].n > 1).map(h => `h${h.n}: ${h.t}`);
    if (saltos.length) achar('a11y-titulos', 'aviso', 'Hierarquia de títulos pula nível.', saltos);
    const semNomeNav = [...document.querySelectorAll('nav')].filter(n => !n.getAttribute('aria-label') && !n.getAttribute('aria-labelledby')).length;
    if (document.querySelectorAll('nav').length > 1 && semNomeNav) achar('a11y-nav', 'aviso', `${semNomeNav} <nav> sem nome, com mais de uma na página.`);
    const semNome = interativos.filter(e => !nomeDe(e).trim() && !(e.matches('input,select,textarea') && e.closest('label')));
    if (semNome.length) achar('a11y-nome', 'falha', `${semNome.length} controle(s) sem nome acessível.`, semNome.map(e => e.outerHTML.slice(0, 60)));
    const semAlt = [...document.images].filter(i => !i.hasAttribute('alt'));
    if (semAlt.length) achar('a11y-alt', 'falha', `${semAlt.length} imagem(ns) sem alt.`, semAlt.map(i => i.src.slice(-40)));
    const vp = document.querySelector('meta[name=viewport]')?.content || '';
    if (/user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?(\s|,|$)/i.test(vp)) achar('a11y-zoom', 'falha', 'A meta viewport bloqueia o zoom.', [vp]);

    // contraste de texto
    let medidos = 0, semMedida = 0; const reprova = [];
    for (const e of textos) {
      if (oculto(e) && e.closest('[aria-hidden="true"]')) continue;
      const b = fundo(e); if (!b) { if (!e.closest('[data-conferido~="a11y-contraste-imagem"]')) semMedida++; continue; }
      const c = cor(cs(e).color); if (c.a === 0) continue;
      const rz = razao(sobre(c, b), b), s = num(cs(e).fontSize), g = s >= 24 || (s >= 18.66 && +cs(e).fontWeight >= 700);
      if (rz < 1.05) continue;   // invisível de propósito
      medidos++;
      if (rz < (g ? 3 : 4.5) && !e.closest('button:disabled,[aria-disabled="true"]')) reprova.push(`${rz.toFixed(2)}:1 ${hex(c)} sobre ${hex(b)} "${curto(e.textContent, 22)}"`);
    }
    if (reprova.length) achar('a11y-contraste', 'falha', `${reprova.length} texto(s) abaixo do contraste mínimo.`, reprova);
    if (semMedida) achar('a11y-contraste-imagem', 'aviso', `${semMedida} texto(s) sobre imagem ou gradiente não medidos: confira à mão.`);

    // fonte fixa em px ignora o tamanho de letra escolhido no navegador
    let px = 0, rem = 0;
    for (const f of document.styleSheets) { try { for (const r of f.cssRules) { const t = r.cssText || ''; px += (t.match(/(font-size|--(text|fs|t)-[a-z0-9-]*):\s*[\d.]+px/g) || []).length; rem += (t.match(/(font-size|--(text|fs|t)-[a-z0-9-]*):\s*(clamp\()?[\d.]+(rem|em)/g) || []).length; } } catch { /* outra origem */ } }
    if (px > 3 && px > rem) achar('a11y-fonte-px', 'aviso', `Fontes em px (${px}) mais que em rem (${rem}): o tamanho de letra do navegador é ignorado.`);
    const miudos = textos.filter(e => num(cs(e).fontSize) < 12 && !oculto(e) && !e.closest('header a,a[aria-label]'));
    if (miudos.length) achar('a11y-fonte-pequena', 'aviso', `${miudos.length} texto(s) abaixo de 12px.`, miudos.map(e => `${cs(e).fontSize} "${curto(e.textContent, 18)}"`));

    // controles e nomes que o teclado e o controle por voz não alcançam
    const simples = t => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    const controle = 'a[href],button,input,select,textarea,summary,label,[role=button],[role=link],[role=tab],[role=radio],[role=checkbox],[role=switch],[role=menuitem],[tabindex]';
    const clicaveis = todos.filter(e => !e.closest(controle) && !e.closest('[aria-hidden="true"]') && !e.querySelector(controle) && (e.hasAttribute('onclick') || (cs(e).cursor === 'pointer' && (!e.parentElement || cs(e.parentElement).cursor !== 'pointer'))));
    if (clicaveis.length) achar('a11y-clique-sem-semantica', clicaveis.some(e => e.hasAttribute('onclick')) ? 'falha' : 'aviso', `${clicaveis.length} elemento(s) que parecem clicáveis e não são botão nem link: o teclado não chega neles (WCAG 2.1.1).`, clicaveis.map(e => `${e.tagName.toLowerCase()}: ${curto(e.textContent, 24)}`));
    // em cartão com muito texto, basta o nome trazer a maior parte das palavras visíveis
    const palavrasDe = t => simples(t).split(' ').filter(Boolean);
    const divergentes = interativos.filter(e => { if (!e.hasAttribute('aria-label') || simples(e.innerText).length < 2) return false; const vistas = palavrasDe(e.innerText), nome = palavrasDe(e.getAttribute('aria-label')); return vistas.filter(p => nome.includes(p)).length / vistas.length < .6; });
    if (divergentes.length) achar('a11y-nome-visivel', 'falha', `${divergentes.length} controle(s) com aria-label sem o texto visível: quem usa controle por voz fala o que vê (WCAG 2.5.3).`, divergentes.map(e => `"${curto(e.innerText, 20)}" x "${curto(e.getAttribute('aria-label'), 24)}"`));
    const tabPositivo = [...document.querySelectorAll('[tabindex]')].filter(e => +e.getAttribute('tabindex') > 0);
    if (tabPositivo.length) achar('a11y-tabindex-positivo', 'aviso', `${tabPositivo.length} elemento(s) com tabindex positivo: a ordem do Tab deixa de seguir a tela (WCAG 2.4.3).`, tabPositivo.map(e => curto(nomeDe(e), 24)));
    const pontos = todos.filter(e => { const r = e.getBoundingClientRect(), c = cor(cs(e).backgroundColor); return !e.children.length && !(e.textContent || '').trim() && !e.matches('input,img,svg,video,canvas') && !e.getAttribute('aria-label') && !e.title && r.width >= 6 && r.width <= 24 && Math.abs(r.width - r.height) < 2 && c.a > .5 && satura(c) > .25; });
    const coresDePonto = new Set(pontos.map(e => hex(cor(cs(e).backgroundColor))));
    // cada cor com forma própria não depende só da cor: quadrado e losango se distinguem em cinza
    const formasPorCor = new Map();
    pontos.forEach(e => { const c = hex(cor(cs(e).backgroundColor)), f = [cs(e).borderTopLeftRadius, cs(e).transform, cs(e).clipPath].join('|'); if (!formasPorCor.has(c)) formasPorCor.set(c, new Set()); formasPorCor.get(c).add(f); });
    const formasSeparam = [...formasPorCor.values()].every((a, i, l) => l.every((b, j) => i === j || ![...a].some(f => b.has(f))));
    if (coresDePonto.size >= 2 && !formasSeparam) achar('a11y-so-cor', 'aviso', `${pontos.length} marcador(es) de ${coresDePonto.size} cores, sem texto nem forma: confira se a situação não depende só da cor (WCAG 1.4.1).`, [...coresDePonto]);
    if (['pouca-leitura', 'idosos', 'cognitivo'].some(p => publicos.includes(p))) {
      // logo com o nome desenhado em curvas é texto para quem olha: passa se for largo e tiver nome para o leitor de tela
      const logoComNome = e => { const m = e.querySelector('svg,img'), r = m.getBoundingClientRect(); return r.width / Math.max(r.height, 1) >= 2.5 && (m.getAttribute('alt') || m.getAttribute('aria-label') || e.getAttribute('aria-label') || '').trim(); };
      const soIcone = interativos.filter(e => !simples(e.innerText) && e.querySelector('svg,img') && !logoComNome(e));
      if (soIcone.length) achar('a11y-icone-sem-texto', 'falha', `${soIcone.length} controle(s) só com ícone: para este público, ícone anda com texto.`, soIcone.map(e => curto(nomeDe(e), 24)));
    }

    // imagem, link e erro que não dizem nada fora de contexto
    const altRuim = [...document.images].filter(vis).filter(i => /\.(jpe?g|png|gif|webp|avif|svg)$/i.test(i.alt.trim()) || /^(img|imagem|image|foto|figura|picture|dsc|captura|screenshot)[\s_-]*\d*$/i.test(i.alt.trim()));
    if (altRuim.length) achar('a11y-alt-ruim', 'falha', `${altRuim.length} imagem(ns) com alt que não descreve nada (WCAG 1.1.1).`, altRuim.map(i => i.alt));
    const vagos = [...document.querySelectorAll('a[href]')].filter(vis).filter(a => !a.getAttribute('aria-label') && !a.getAttribute('aria-labelledby') && /^(clique aqui|clique|aqui|saiba mais|leia mais|ver mais|veja mais|mais|acesse|acesse aqui|link|click here|here|read more|learn more)$/.test(simples(a.innerText)));
    if (vagos.length) achar('a11y-link-vago', 'aviso', `${vagos.length} link(s) que não dizem para onde vão: quem navega por lista de links não entende (WCAG 2.4.4).`, vagos.map(a => a.innerText.trim()));
    const ligado = (c, m) => `${c.getAttribute('aria-describedby') || ''} ${c.getAttribute('aria-errormessage') || ''}`.split(/\s+/).some(i => i && document.getElementById(i)?.contains(m));
    const campoPerto = m => { for (const n of [m.previousElementSibling, m.parentElement, m.nextElementSibling]) { if (!n) continue; const c = n.matches('input,select,textarea') ? n : n.querySelector('input,select,textarea'); if (c) return c; } return null; };
    const errosSoltos = textos.filter(e => !e.matches('label,legend,button,a,h1,h2,h3,h4,h5,h6,option,th') && !e.closest('label') && (comTexto.get(e) || '').trim().length <= 90 && /(inv[aá]lid|obrigat[oó]ri|incorret|n[aã]o pode ficar|preencha)/i.test(comTexto.get(e))).filter(m => { const c = campoPerto(m); return c && !ligado(c, m); });
    if (errosSoltos.length) achar('a11y-erro-sem-ligacao', 'aviso', `${errosSoltos.length} mensagem(ns) de campo sem aria-describedby: o leitor de tela não anuncia junto do campo (WCAG 1.3.1, 3.3.1).`, errosSoltos.map(e => curto(e.textContent, 28)));

    // mídia
    const videos = [...document.querySelectorAll('video')].filter(vis);
    const semLegenda = videos.filter(v => !v.querySelector('track[kind=captions],track[kind=subtitles]') && !(v.hasAttribute('muted') && !v.hasAttribute('controls')));
    if (semLegenda.length) achar('a11y-video-legenda', 'falha', `${semLegenda.length} vídeo(s) sem <track> de legenda (WCAG 1.2.2). Veja references/padroes/midia-e-libras.md.`);
    const semPausa = videos.filter(v => v.hasAttribute('autoplay') && !v.hasAttribute('controls') && ![...(v.parentElement?.querySelectorAll('button') || [])].some(b => /paus|parar|stop/i.test(nomeDe(b))));
    if (semPausa.length) achar('a11y-video-sem-controle', 'falha', `${semPausa.length} vídeo(s) que tocam sozinhos sem como pausar (WCAG 2.2.2).`);
    if ([...document.querySelectorAll('audio')].filter(vis).length && !/transcri/i.test(document.body.innerText)) achar('a11y-audio-transcricao', 'aviso', 'Áudio sem transcrição à vista (WCAG 1.2.1).');
    if (publicos.includes('surdos-libras') || opcoes.superficie === 'publica') {
      if (!document.querySelector('[vw],script[src*="vlibras" i],script[src*="handtalk" i]')) achar('a11y-libras', publicos.includes('surdos-libras') && opcoes.superficie === 'publica' ? 'falha' : 'aviso', 'Superfície pública sem recurso de Libras ao chegar. Veja references/padroes/midia-e-libras.md.');
    }

    // blocos de texto: dislexia, baixa visão, cognição (WCAG 1.4.8)
    const blocos = textos.filter(e => e.matches('p,li,blockquote,dd,div,td,figcaption')).map(e => { const s = cs(e), fonte = num(s.fontSize), lh = num(s.lineHeight) || fonte * 1.2, t = (e.innerText || '').trim(), linhas = Math.max(1, Math.round(e.getBoundingClientRect().height / lh)); return { e, s, t, fonte, lh, linhas, por: t.length / linhas }; });
    const lista = b => curto(b.t, 28);
    const justificados = blocos.filter(b => b.t.length >= 120 && b.s.textAlign === 'justify');
    if (justificados.length) achar('a11y-justificado', 'aviso', `${justificados.length} bloco(s) justificados: os espaços irregulares atrapalham a leitura.`, justificados.map(lista));
    const emCaixaAlta = blocos.filter(b => b.t.length >= 60 && (b.s.textTransform === 'uppercase' || b.t === b.t.toUpperCase() && /\p{L}/u.test(b.t)));
    if (emCaixaAlta.length) achar('a11y-caixa-alta', 'aviso', `${emCaixaAlta.length} bloco(s) longos em caixa alta: tiram a forma das palavras.`, emCaixaAlta.map(lista));
    const italicos = blocos.filter(b => b.t.length >= 120 && b.s.fontStyle === 'italic');
    if (italicos.length) achar('a11y-italico-longo', 'aviso', `${italicos.length} bloco(s) longos em itálico.`, italicos.map(lista));
    const largas = blocos.filter(b => b.linhas >= 2 && b.por > 88);
    if (largas.length) achar('a11y-linha-longa', 'aviso', `${largas.length} bloco(s) com mais de 80 caracteres por linha: quem lê perde a linha seguinte.`, largas.map(b => `${Math.round(b.por)} por linha: ${lista(b)}`));
    const apertadas = blocos.filter(b => b.linhas >= 2 && b.fonte < 24 && b.lh / b.fonte < 1.3);
    if (apertadas.length) achar('a11y-entrelinha', 'aviso', `${apertadas.length} bloco(s) com entrelinha abaixo de 1,3.`, apertadas.map(b => `${(b.lh / b.fonte).toFixed(2)}: ${lista(b)}`));

    // legibilidade em português: índice de Flesch adaptado (Martins et al., 1996). É alerta, não aprovação.
    // Limites calibrados em docs/testes/2026-10-31-fase-1: textos fáceis deram de 66 a 89; jurídicos, de -86 a -4.
    if ((document.documentElement.lang || '').toLowerCase().startsWith('pt')) {
      const silabas = p => { const w = p.toLowerCase().replace(/qu(?=[aeioáéíóâêô])/g, 'q').replace(/g[uü](?=[eiéí])/g, 'g'); return Math.max(1, (w.match(/[aeiouáéíóúâêôãõàü]+/g) || []).reduce((n, g) => n + (g.length === 1 || /^(ai|au|ei|eu|oi|ou|iu|ui|ãe|ão|õe|ãi|éi|éu|ói|ái|áu)$/.test(g) ? 1 : Math.ceil(g.length / 2) + (g.length === 2 ? 1 : 0)), 0)); };
      const baixa = publicos.includes('pouca-leitura') || publicos.includes('cognitivo');
      const dificeis = blocos.filter(b => b.t.split(/\s+/).length >= 20 && b.t !== b.t.toUpperCase()).map(b => { const pal = b.t.split(/\s+/), frases = Math.max(1, (b.t.match(/[.!?]+(\s|$)/g) || []).length), sil = pal.reduce((n, w) => n + silabas(w), 0); return { t: b.t, porFrase: pal.length / frases, indice: 248.835 - 1.015 * (pal.length / frases) - 84.6 * (sil / pal.length) }; }).filter(b => b.indice < (baixa ? 50 : 10) || (baixa && b.porFrase > 25));
      if (dificeis.length) achar('a11y-leitura-dificil', 'aviso', `${dificeis.length} parágrafo(s) difíceis de ler: frases longas e palavras compridas. Leia em voz alta e reescreva.`, dificeis.map(b => `índice ${Math.round(b.indice)}: ${curto(b.t, 28)}`));
    }
  }

  // alvos
  if (papel === 'desktop' || papel === 'celular' || papel === 'tablet') {
    const medir = e => { const r = e.getBoundingClientRect(), a = cs(e, '::after'), aw = a.position === 'absolute' ? num(a.width) : 0, ah = a.position === 'absolute' ? num(a.height) : 0; return { w: Math.max(r.width, aw), h: Math.max(r.height, ah), t: curto(nomeDe(e), 22) || e.tagName }; };
    // só link no meio da frase é exceção (WCAG 2.5.8); botão e campo dentro de parágrafo são medidos
    const alvos = interativos.filter(e => !(e.tagName === 'A' && (cs(e).display === 'inline' || e.closest('p,li p'))) && !oculto(e) && e.getBoundingClientRect().width > 2).map(medir);
    const menores = alvos.filter(a => a.w < 24 || a.h < 24);
    if (menores.length) achar('a11y-alvo', 'falha', `${menores.length} alvo(s) abaixo de 24×24px (WCAG 2.5.8).`, menores.map(a => `${a.t} ${Math.round(a.w)}×${Math.round(a.h)}`));
    if (papel === 'celular') {
      const toque = alvos.filter(a => (a.w < 44 || a.h < 44) && a.w >= 24 && a.h >= 24);
      if (toque.length) achar('a11y-toque', 'aviso', `${toque.length} de ${alvos.length} alvo(s) abaixo de 44×44px no toque.`, toque.map(a => `${a.t} ${Math.round(a.w)}×${Math.round(a.h)}`));
    }
  }

  // rolagem horizontal: vale em todo tamanho
  const raiz = document.documentElement;
  if (raiz.scrollWidth > raiz.clientWidth + 1) {
    const larg = raiz.clientWidth;
    const culpados = todos.filter(e => e.getBoundingClientRect().right > larg + 1 && !e.closest('[style*="overflow"]')).map(e => `${e.tagName.toLowerCase()}.${String(e.className).split(' ')[0]}`);
    achar('a11y-rolagem-horizontal', 'falha', `A página rola na horizontal: ${raiz.scrollWidth}px em ${larg}px.`, culpados);
  }

  // camadas fixas em janela baixa
  const faixas = new Array(innerHeight).fill(0);
  todos.filter(e => ['fixed', 'sticky'].includes(cs(e).position) && !e.closest('dialog[open]')).forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width < innerWidth * .6 || r.left >= innerWidth || r.right <= 0 || r.bottom <= 0 || r.top >= innerHeight || r.height >= innerHeight) return;
    for (let y = Math.max(0, Math.floor(r.top)); y < Math.min(innerHeight, Math.ceil(r.bottom)); y++) faixas[y] = 1;
  });
  const coberto = faixas.reduce((a, b) => a + b, 0), parte = coberto / innerHeight;
  if (innerHeight <= 480 && parte > .5) achar('a11y-camadas-fixas', 'falha', `Em ${innerWidth}×${innerHeight}, camadas fixas cobrem ${Math.round(parte * 100)}% da altura: quem usa zoom alto quase não vê conteúdo.`);
  else if (innerHeight <= 480 && parte > .35) achar('a11y-camadas-fixas', 'aviso', `Em ${innerWidth}×${innerHeight}, camadas fixas cobrem ${Math.round(parte * 100)}% da altura.`);

  // --- fotos e letras: o que passou num teste real com 0 falhas ---------------------------------------
  if (papel !== 'zoom') {
    // height no HTML sem height:auto no CSS ignora o aspect-ratio e deixa a foto na altura original
    const fotos = [...document.images].filter(vis).map(i => { const r = i.getBoundingClientRect(), naTela = r.width / r.height, natural = i.naturalWidth / i.naturalHeight; return { w: r.width, h: r.height, ajuste: cs(i).objectFit, resta: Math.min(naTela / natural, natural / naTela), nome: curto(i.alt, 24) || (i.currentSrc || i.src).split('/').pop().slice(0, 24), svg: /\.svg(\?|$)|^data:image\/svg/i.test(i.currentSrc || i.src), grande: i.naturalWidth >= 64 && i.naturalHeight >= 64 }; }).filter(f => !f.svg && f.grande && f.w >= 64 && f.h >= 64);
    const caixa = f => `${f.nome}: ${Math.round(f.w)}×${Math.round(f.h)}`;
    const esticadas = fotos.filter(f => f.ajuste === 'fill' && f.resta < .85);
    if (esticadas.length) achar('q-foto-deformada', 'falha', `${esticadas.length} foto(s) esticadas: a caixa tem outra proporção. Use aspect-ratio com height:auto e object-fit.`, esticadas.map(caixa));
    const cortadas = fotos.filter(f => f.ajuste === 'cover' && f.resta < .45);
    if (cortadas.length) achar('q-foto-cortada', cortadas.some(f => f.resta < .25 || f.h > innerHeight * 1.2) ? 'falha' : 'aviso', `${cortadas.length} foto(s) com a maior parte cortada. Se a imagem tem height no HTML, falta height:auto no CSS.`, cortadas.map(f => `${caixa(f)}, aparece ${Math.round(f.resta * 100)}% da foto`));
    // palavras coladas: limites do kit, a partir do mesmo teste
    const rigor = publicos.includes('dislexia') || publicos.includes('pouca-leitura');
    const espacoDe = e => num(cs(e).letterSpacing) / num(cs(e).fontSize);
    const coladas = textos.filter(e => /\S\s+\S/.test((comTexto.get(e) || '').trim()) && espacoDe(e) <= (rigor ? -.03 : -.05));
    if (coladas.length) achar('a11y-letra-apertada', rigor ? 'falha' : 'aviso', `${coladas.length} texto(s) com letras tão apertadas que as palavras se colam.`, coladas.map(e => `${espacoDe(e).toFixed(3)}em: ${curto(e.textContent, 24)}`));
  }

  // --- gosto -----------------------------------------------------------------------------------------
  if (papel === 'desktop' || papel === 'celular') {
    // a mesma ação duas vezes à vista: menu que sobrou de outra largura, ou botão repetido pela barra fixa
    const repetidos = {};
    interativos.filter(primeiraDobra).filter(e => e.matches('a[href]')).forEach(e => { const nome = curto(nomeDe(e), 40).toLowerCase(); if (nome) (repetidos[`${nome} ${e.href}`] ||= []).push(curto(nomeDe(e), 30)); });
    const acoesIguais = Object.values(repetidos).filter(l => l.length > 1).map(l => l[0]);
    if (acoesIguais.length) achar('g-acao-repetida', 'aviso', `${acoesIguais.length} ação(ões) aparecem duas vezes na primeira dobra: deixe uma (G01).`, acoesIguais);

    const doc = raiz.scrollHeight > innerHeight + 40;
    const presas = todos.filter(e => { const s = cs(e); return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 40 && e.clientHeight > 80 && e !== document.body && e !== raiz && !e.closest('dialog,[role=dialog],[data-rolagem-propria],textarea,pre'); });
    if (doc && presas.length) achar('g-rolagem-presa', 'aviso', 'Área com rolagem própria dentro de página que também rola: a pessoa fica presa e o resto não aparece (G09).', presas.map(e => `${e.tagName.toLowerCase()}.${String(e.className).split(' ')[0]}`));
    const limite = papel === 'desktop' ? 180 : 110;
    if (palavrasDobra > limite) achar('g-muito-texto', 'aviso', `${palavrasDobra} palavras na primeira dobra (limite ${limite}): muito texto para bater o olho (G03).`);

    // camada fixa estreita, como botão de Libras ou de conversa: o texto que passa por baixo perde letras. Faixa larga é com a11y-camadas-fixas.
    const comSombra = (r, l = []) => { for (const e of r.querySelectorAll('*')) { l.push(e); if (e.shadowRoot) comSombra(e.shadowRoot, l); } return l; };
    const camadas = comSombra(document.body).filter(e => { const s = cs(e), r = e.getBoundingClientRect(); return s.position === 'fixed' && s.visibility !== 'hidden' && +s.opacity > 0 && r.width > 2 && r.height > 2 && r.width < innerWidth * .6 && r.height < innerHeight * .6 && r.right > 0 && r.left < innerWidth && r.bottom > 0 && r.top < innerHeight && !e.closest('dialog,[role=dialog],[aria-hidden="true"]'); }).map(e => ({ e, r: e.getBoundingClientRect() }));
    if (camadas.length) {
      const fim = Math.max(0, raiz.scrollHeight - innerHeight), folga = 4, sob = new Map();
      for (const e of textos) for (const n of e.childNodes) {
        if (n.nodeType !== 3 || !n.textContent.trim() || camadas.some(c => c.e.contains(e))) continue;
        const g = document.createRange(); g.selectNodeContents(n);
        for (const t of g.getClientRects()) for (const { r } of camadas) {
          const dx = Math.min(r.right, t.right) - Math.max(r.left, t.left), meio = (r.top + r.bottom) / 2 / innerHeight;
          if (dx <= folga) continue;
          // no meio da tela, conta qualquer ponto da rolagem; nas pontas, só onde rolar não tira o texto de baixo
          const de = meio > 2 / 3 ? fim : 0, ate = meio < 1 / 3 ? 0 : fim;
          if (t.top + scrollY - ate < r.bottom - folga && t.bottom + scrollY - de > r.top + folga) sob.set(curto(n.textContent, 24), Math.max(sob.get(curto(n.textContent, 24)) || 0, Math.round(dx)));
        }
      }
      if (sob.size) achar('q-camada-sobre-texto', 'aviso', `${sob.size} texto(s) ficam sob uma camada fixa: quem lê perde letras. Reserve margem no texto ou mude a camada de lugar.`, [...sob].map(([t, px]) => `${px}px sobre "${t}"`));
    }
  }
  if (papel === 'desktop') {
    const selects = [...document.querySelectorAll('select')].filter(s => s.options.length > 12);
    if (selects.length) achar('g-lista-suspensa-longa', selects.some(s => s.options.length > 30) ? 'falha' : 'aviso', 'Lista suspensa longa: dado que cresce pede busca, não dropdown (G11).', selects.map(s => `${nomeDe(s) || s.name}: ${s.options.length} opções`));
    const tabelas = [...document.querySelectorAll('table')].filter(t => vis(t) && t.getAttribute('role') !== 'presentation' && !t.querySelector('th'));
    if (tabelas.length) achar('g-tabela-sem-cabecalho', 'falha', `${tabelas.length} tabela(s) sem cabeçalho: não dá para saber que dado é cada coluna (G12).`);
    const temPaginacao = /(pr[oó]xim|anterior|p[aá]gina \d|ver mais|carregar mais)/i.test(document.body.innerText);
    const longas = [...document.querySelectorAll('tbody,ul,ol')].filter(l => l.children.length > 30 && vis(l));
    if (longas.length && !temPaginacao) achar('g-lista-sem-paginacao', 'aviso', `Lista com ${longas[0].children.length} itens e sem paginação (G10).`);

    // ocupação do espaço no computador
    const area = (document.querySelector('main,[role=main]') || document.body).getBoundingClientRect();
    const folhas = todos.filter(e => { const r = e.getBoundingClientRect(); return (comTexto.has(e) || e.matches('img,svg,table,canvas,video,input,select,button')) && r.top < innerHeight * 2 && r.left >= area.left - 1 && r.right <= area.right + 1 && (document.querySelector('main,[role=main]') ? e.closest('main,[role=main]') : true) && !cs(e).position.match(/fixed/); });
    if (folhas.length > 3 && innerWidth >= 1200) {
      const esq = Math.min(...folhas.map(e => e.getBoundingClientRect().left)), dir = Math.max(...folhas.map(e => e.getBoundingClientRect().right));
      // a caixa de um título vai até a borda mesmo com texto curto: G08 mede onde o texto termina
      const fimDoTexto = e => { const r = e.getBoundingClientRect(); if (!comTexto.has(e) || e.matches('button,input,select,table')) return r.right; const g = document.createRange(); g.selectNodeContents(e); const q = g.getBoundingClientRect(); return q.width > 0 ? q.right : r.right; };
      // coluna centralizada na tela já está equilibrada, mesmo com o texto mais curto que ela
      const centrada = area.left > 24 && Math.abs(area.left - (document.documentElement.clientWidth - area.right)) < 32;
      const sobraE = esq - area.left, sobraD = area.right - (centrada ? dir : Math.max(...folhas.map(fimDoTexto))), largura = area.width;
      if (sobraD > largura * .25 && sobraD > 2 * sobraE + 48) achar('g-colado-a-esquerda', 'aviso', `Conteúdo termina ${Math.round(sobraD)}px antes da borda direita e começa a ${Math.round(sobraE)}px da esquerda: parece desalinhado (G08).`);
      else if ((dir - esq) / largura < .5) achar('g-pouco-uso-da-tela', 'aviso', `Conteúdo usa ${Math.round((dir - esq) / largura * 100)}% da largura: parece o celular colado no computador (G07).`);
    }

    // mais de uma ação principal na primeira dobra
    const grupos = {};
    interativos.filter(primeiraDobra).filter(e => e.matches('button,a,[role=button]')).forEach(e => { const c = cor(cs(e).backgroundColor); if (c.a > .9 && satura(c) > .25) { (grupos[hex(c)] ||= []).push(curto(e.textContent, 20)); } });
    const maior = Object.values(grupos).sort((a, b) => b.length - a.length)[0];
    if (maior && maior.length >= 3) achar('g-acoes-demais', 'aviso', `${maior.length} botões preenchidos com a mesma cor na primeira dobra: qual é a ação principal? (G01)`, maior);

    // SVG em <img> tem cor fixa: em alto contraste o fundo muda, e o logo pode sumir
    const logosFixos = [...document.images].filter(vis).filter(i => /\.svg(\?|$)/i.test(i.currentSrc || i.src) && (/logo|marca/i.test(i.currentSrc || i.src) || i.closest('header'))).filter(i => !i.closest('picture')?.querySelector('source[media*="forced-colors"]') && !i.closest('[data-conferido~="a11y-logo-alto-contraste"]'));
    if (logosFixos.length) achar('a11y-logo-alto-contraste', 'aviso', 'Logo em SVG com cor fixa pode sumir em alto contraste: dê a versão para fundo escuro com <picture> e media="(forced-colors: active)".', logosFixos.map(i => curto(i.alt || i.src.split('/').pop(), 30)));

    // logo em quadradinho
    const logos = todos.filter(e => { const r = e.getBoundingClientRect(), s = cs(e), t = (e.textContent || '').trim(); const raio = num(s.borderTopLeftRadius); return r.top < 140 && r.left < 320 && r.width >= 24 && r.width <= 72 && Math.abs(r.width / r.height - 1) < .15 && raio > 0 && !s.borderTopLeftRadius.includes('%') && raio < r.width / 2 && cor(s.backgroundColor).a > .9 && satura(cor(s.backgroundColor)) > .2 && /^[A-ZÀ-Ú]{1,3}$/.test(t); });
    if (logos.length) achar('g-logo-em-quadrado', 'aviso', 'Marca como iniciais dentro de um quadrado colorido: você já reprovou isso (G17).', logos.map(e => e.textContent.trim()));

    // --- cara de IA ----------------------------------------------------------------------------------
    const principal = (familias[0]?.[0] || '').toLowerCase();
    const padrao = ['inter', 'roboto', 'arial', 'helvetica', 'helvetica neue', 'system-ui', '-apple-system', 'segoe ui', 'open sans', 'poppins', 'sans-serif', 'montserrat', 'lato'];
    if (padrao.includes(principal) && !temMotivo(principal)) achar('ia-fonte-padrao', 'aviso', `Fonte principal "${familias[0][0]}" é escolha padrão de gerador. Se foi decisão, escreva o motivo em "Do's and Don'ts" no DESIGN.md.`);
    // @font-face só com local() é a fonte do sistema com outro nome; folha de outra origem não dá para ler
    const soLocal = new Set(), comArquivo = new Set();
    for (const f of document.styleSheets) { try { for (const r of f.cssRules) if (r.type === CSSRule.FONT_FACE_RULE) (/url\(/.test(r.style.getPropertyValue('src')) ? comArquivo : soLocal).add(r.style.getPropertyValue('font-family').replace(/["']/g, '').trim().toLowerCase()); } catch { /* outra origem */ } }
    const servidas = new Set([...(document.fonts || [])].map(f => f.family.replace(/["']/g, '').toLowerCase()).filter(n => comArquivo.has(n) || !soLocal.has(n)));
    if (principal && !servidas.has(principal) && !['system-ui', '-apple-system', 'ui-sans-serif', 'ui-serif', 'sans-serif', 'serif', 'monospace'].includes(principal)) achar('g-fonte-nao-servida', 'aviso', `Fonte "${familias[0][0]}" vem do sistema, não do projeto: em outro aparelho, como um Android, a tela muda de letra, com motivo ou sem. Sirva em WOFF2, ou use a pilha genérica (system-ui).`);
    const TW = { indigo: 'eef2ff e0e7ff c7d2fe a5b4fc 818cf8 6366f1 4f46e5 4338ca 3730a3 312e81', violeta: 'f5f3ff ede9fe ddd6fe c4b5fd a78bfa 8b5cf6 7c3aed 6d28d9 5b21b6 4c1d95', roxo: 'faf5ff f3e8ff e9d5ff d8b4fe c084fc a855f7 9333ea 7e22ce 6b21a8 581c87', azul: 'eff6ff dbeafe bfdbfe 93c5fd 60a5fa 3b82f6 2563eb 1d4ed8 1e40af 1e3a8a', cinza: 'f9fafb f3f4f6 e5e7eb d1d5db 9ca3af 6b7280 4b5563 374151 1f2937 111827', ardosia: 'f8fafc f1f5f9 e2e8f0 cbd5e1 94a3b8 64748b 475569 334155 1e293b 0f172a', zinco: 'fafafa f4f4f5 e4e4e7 d4d4d8 a1a1aa 71717a 52525b 3f3f46 27272a 18181b', vermelho: 'fef2f2 fee2e2 fecaca fca5a5 f87171 ef4444 dc2626 b91c1c 991b1b 7f1d1d', verde: 'f0fdf4 dcfce7 bbf7d0 86efac 4ade80 22c55e 16a34a 15803d 166534 14532d', esmeralda: 'ecfdf5 d1fae5 a7f3d0 6ee7b7 34d399 10b981 059669 047857 065f46 064e3b', ambar: 'fffbeb fef3c7 fde68a fcd34d fbbf24 f59e0b d97706 b45309 92400e 78350f' };
    const cores = new Set(); todos.forEach(e => { const s = cs(e); [s.color, s.backgroundColor].forEach(v => { const c = cor(v); if (c.a > .5) cores.add(hex(c)); }); });
    const achadas = {}; for (const [fam, lista] of Object.entries(TW)) { const h = lista.split(' ').filter(x => cores.has('#' + x)); if (h.length) achadas[fam] = h; }
    const totalTW = Object.values(achadas).flat().length;
    if (achadas.indigo || achadas.violeta || achadas.roxo) achar('ia-indigo', 'aviso', 'Índigo ou violeta da paleta padrão do Tailwind: a paleta que você reprovou como "muita cara de IA".', [...(achadas.indigo || []), ...(achadas.violeta || []), ...(achadas.roxo || [])].map(x => '#' + x));
    if (totalTW >= 5) achar('ia-paleta-padrao', 'aviso', `${totalTW} cores idênticas à paleta padrão do Tailwind: paleta sem decisão própria.`, Object.keys(achadas));
    const textoGrad = textos.filter(e => cs(e).webkitBackgroundClip === 'text' || cs(e).backgroundClip === 'text');
    if (textoGrad.length) achar('ia-texto-gradiente', 'aviso', 'Texto com gradiente.', textoGrad.map(e => curto(e.textContent, 24)));
    const gradRoxo = todos.filter(e => /gradient/.test(cs(e).backgroundImage) && (cs(e).backgroundImage.match(/rgba?\([^)]+\)/g) || []).some(v => { const c = cor(v); return c.a > .3 && satura(c) > .3 && matiz(c) >= 230 && matiz(c) <= 300; }));
    if (gradRoxo.length) achar('ia-gradiente-roxo', 'aviso', 'Gradiente em tons de roxo ou azul-violeta.');
    const sobrancelhas = [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis).filter(h => { const a = h.previousElementSibling; if (!a || !vis(a) || (a.textContent || '').length > 40) return false; const s = cs(a); return num(s.fontSize) <= 15 && (s.textTransform === 'uppercase') && num(s.letterSpacing) > .2; });
    if (sobrancelhas.length >= 2) achar('ia-sobrancelha', 'aviso', `${sobrancelhas.length} rótulos em caixa alta com tracking acima de títulos.`, sobrancelhas.map(h => curto(h.previousElementSibling.textContent, 20)));
    const quadradoIcone = c => [...c.querySelectorAll('div,span,i,figure')].some(q => { const r = q.getBoundingClientRect(), s = cs(q); return r.width >= 28 && r.width <= 72 && Math.abs(r.width / r.height - 1) < .15 && num(s.borderTopLeftRadius) > 0 && cor(s.backgroundColor).a > .2 && q.querySelector('svg') && !(q.textContent || '').trim(); });
    const grades = todos.filter(p => p.children.length >= 3 && /grid|flex/.test(cs(p).display)).filter(p => { const f = [...p.children].filter(vis); if (f.length < 3) return false; const w = f[0].getBoundingClientRect().width; return f.every(c => Math.abs(c.getBoundingClientRect().width - w) < w * .06) && f.filter(quadradoIcone).length >= 3; });
    if (grades.length) achar('ia-cards-iguais', 'aviso', 'Grade de cartões iguais com ícone em quadradinho, título e texto: o layout mais repetido por gerador.');
    const cartao = e => { const s = cs(e); return num(s.borderTopLeftRadius) >= 8 && cor(s.backgroundColor).a > .9 && (s.boxShadow !== 'none' || num(s.borderTopWidth) >= 1) && e.getBoundingClientRect().height > 60; };
    const cartoes = todos.filter(cartao);
    const aninhados = cartoes.filter(c => { let p = c.parentElement; while (p) { if (cartoes.includes(p) && c.getBoundingClientRect().width > p.getBoundingClientRect().width * .4) return true; p = p.parentElement; } return false; });
    if (aninhados.length >= 2) achar('ia-cartao-em-cartao', 'aviso', `${aninhados.length} cartões dentro de cartões.`);
    const emoji = textos.filter(e => e.closest('button,a,nav,h1,h2,h3') && /\p{Extended_Pictographic}/u.test(comTexto.get(e)) && !/^[\s✓✔✕×←→↑↓]+$/.test(comTexto.get(e)));
    if (emoji.length) achar('ia-emoji', 'aviso', 'Emoji fazendo papel de ícone em controle ou título.', emoji.map(e => curto(e.textContent, 18)));
    const faiscas = document.querySelectorAll('svg[class*="sparkle" i],[data-lucide*="sparkle" i],[class*="lucide-sparkle" i]').length;
    if (faiscas) achar('ia-faisca', 'aviso', `${faiscas} ícone(s) de faíscas: virou o símbolo de produto feito por IA.`);
    const bordaEsq = cartoes.filter(c => { const s = cs(c); return num(s.borderLeftWidth) >= 3 && num(s.borderRightWidth) <= 1 && satura(cor(s.borderLeftColor)) > .3; });
    if (bordaEsq.length >= 3) achar('ia-borda-esquerda', 'aviso', `${bordaEsq.length} cartões com borda colorida à esquerda.`);
    const cliches = (document.body.innerText || '').match(/\b(transforme (seu|sua|a)|revolucion\w+|potencialize|sem complica[cç][aã]o|bem-vindo de volta|bem-vinda de volta|lorem ipsum|simples\. r[aá]pido|solu[cç][aã]o completa|pr[oó]ximo n[ií]vel|sua jornada|em um s[oó] lugar|seamless|supercharge|unleash|all-in-one|elevate your)\b/gi);
    if (cliches) achar('ia-texto-cliche', 'aviso', 'Frases de gerador no texto da tela.', cliches.map(c => c.toLowerCase()));

    // os looks de quem fugiu do índigo; ver references/marca/anti-generico.md
    const luz = c => { const m = Math.max(c.r, c.g, c.b) / 255, n = Math.min(c.r, c.g, c.b) / 255, l = (m + n) / 2; return { l, s: m === n ? 0 : (m - n) / (1 - Math.abs(2 * l - 1)) }; };
    const serifada = f => /(^|,\s*)"?serif/i.test(f) || /georgia|times|garamond|playfair|fraunces|cormorant|lora|newsreader|crimson|instrument serif|dm serif/i.test(f.split(',')[0]);
    const fundoDaPagina = [document.body, raiz].map(n => cor(cs(n).backgroundColor)).find(c => c.a > .9);
    const creme = fundoDaPagina && matiz(fundoDaPagina) >= 30 && matiz(fundoDaPagina) <= 60 && luz(fundoDaPagina).l >= .88 && luz(fundoDaPagina).l < .985 && luz(fundoDaPagina).s >= .15;
    const terracota = [...cores].some(h => { const c = cor(h), { l, s } = luz(c); return matiz(c) >= 8 && matiz(c) <= 28 && s >= .35 && s <= .85 && l >= .22 && l <= .7; });
    const titulo1 = document.querySelector('h1');
    if (creme && terracota && titulo1 && serifada(cs(titulo1).fontFamily)) achar('ia-creme-terracota', 'aviso', 'Fundo creme, título com serifa e acento terracota: virou o padrão de quem foge do índigo.');
    const destaques = [...document.querySelectorAll('h1,h2')].filter(vis).filter(h => (h.textContent || '').trim().split(/\s+/).length >= 3 && [...h.children].some(f => f.matches('em,i,span,mark,strong,b') && (f.textContent || '').trim().split(/\s+/).length <= 2 && (cs(f).color !== cs(h).color || (cs(f).fontStyle === 'italic' && cs(h).fontStyle !== 'italic'))));
    if (destaques.length) achar('ia-palavra-destaque', 'aviso', 'Uma palavra do título em itálico ou em outra cor.', destaques.map(h => curto(h.textContent, 28)));
    const enfeitesMono = textos.filter(e => /mono|consolas|courier|menlo|monaco|fira code|cascadia/i.test(cs(e).fontFamily.split(',')[0]) && !e.closest('code,pre,kbd,samp,table,time,data') && !/^[\d\s.,:%/-]+$/.test((comTexto.get(e) || '').trim()));
    if (enfeitesMono.length >= 2) achar('ia-mono-enfeite', 'aviso', `${enfeitesMono.length} texto(s) em monoespaçada fora de código ou dado: enfeite de "técnico".`, enfeitesMono.map(e => curto(e.textContent, 24)));
    const numeracao = textos.filter(e => /^0\d[.)]?$/.test((comTexto.get(e) || '').trim()));
    // identificador fora de ordem (guinchos 01, 03, 02) não é numeração: só conta corrida crescente de três
    const valores = numeracao.map(e => parseInt((comTexto.get(e) || '').trim(), 10));
    if (valores.some((v, i) => valores[i + 1] === v + 1 && valores[i + 2] === v + 2)) achar('ia-numeracao', 'aviso',`Numeração ${numeracao.slice(0, 3).map(e => e.textContent.trim()).join(', ')}: só vale quando o conteúdo é mesmo uma sequência.`);
    const durasSombras = todos.filter(e => [...cs(e).boxShadow.matchAll(/\)\s+(-?[\d.]+)px\s+(-?[\d.]+)px\s+0px/g)].some(m => Math.abs(+m[1]) >= 2 && Math.abs(+m[2]) >= 2));
    if (durasSombras.length) achar('ia-sombra-dura', 'aviso', `${durasSombras.length} elemento(s) com sombra dura deslocada, sem desfoque.`, durasSombras.map(e => curto(e.textContent, 20)));
    const vidros = todos.filter(e => /blur/.test(cs(e).backdropFilter || cs(e).webkitBackdropFilter || '') && !/fixed|sticky/.test(cs(e).position) && !e.closest('dialog,[role=dialog]'));
    if (vidros.length) achar('ia-vidro', 'aviso', `${vidros.length} painel(éis) de vidro e desfoque como decoração.`);
    const metricas = todos.filter(p => /grid|flex/.test(cs(p).display)).filter(p => { const f = [...p.children].filter(vis); return f.length >= 3 && f.every(c => { const n = c.firstElementChild; return n && /\d/.test(n.textContent || '') && num(cs(n).fontSize) >= 40 && (c.textContent || '').trim().length <= 40; }); });
    if (metricas.length) achar('ia-metrica-heroi', 'aviso', 'Número enorme com rótulo pequeno, em série: o modelo pronto de "resultados". Número precisa ter fonte real.');
    const jornal = serifada(cs(document.body).fontFamily) && todos.some(p => /grid|flex/.test(cs(p).display) && num(cs(p).borderTopLeftRadius) === 0 && num(cs(p).borderTopWidth) >= 1 && num(cs(p).borderTopWidth) <= 1.5 && num(cs(p).borderBottomWidth) >= 1 && [...p.children].filter(c => num(cs(c).borderLeftWidth) >= 1 && num(cs(c).borderLeftWidth) <= 1.5).length >= 3);
    if (jornal) achar('ia-jornal', 'aviso', 'Serifa, fios finos e colunas de jornal, sem nada do assunto pedindo isso.');
    const pulsos = (document.getAnimations ? document.getAnimations() : []).filter(a => { const t = a.effect?.getTiming?.(), alvo = a.effect?.target; if (!alvo || !t || t.iterations !== Infinity) return false; const r = alvo.getBoundingClientRect(); return r.width > 0 && r.width <= 16 && r.height <= 16 && !(alvo.textContent || '').trim() && !alvo.closest('[role=progressbar],[aria-busy=true]'); });
    if (pulsos.length) achar('ia-pulso', 'aviso', `${pulsos.length} ponto(s) pulsando sem parar: se não indica um estado real, é enfeite.`);
    const pontosMedios = textos.filter(e => ((comTexto.get(e) || '').match(/\s[·•]\s/g) || []).length >= 2);
    if (pontosMedios.length) achar('ia-pontos-medios', 'aviso', 'Linha de metadados separada por pontos médios.', pontosMedios.map(e => curto(e.textContent, 28)));
    const setas = interativos.filter(e => /(\s|^)(→|->|⟶|↗)\s*$/.test(e.innerText || ''));
    if (setas.length) achar('ia-seta', 'aviso', `${setas.length} botão(ões) ou link(s) com seta no fim do texto.`, setas.map(e => curto(e.innerText, 24)));
    const efeito = (document.body.innerText || '').match(/\b(n[aã]o [eé] (s[oó]|apenas) [^.!?\n]{1,60}[,:;—-]\s*[eé]?|mais (do )?que (um|uma) [^.!?\n]{1,40}[:,]|n[aã]o (s[oó]|apenas) [^.!?\n]{1,60}, mas|not just [^.!?\n]{1,60})/gi);
    if (efeito) achar('ia-frase-de-efeito', 'aviso', 'Frase de efeito em negativa: "não é só X, é Y".', efeito.map(c => curto(c, 32)));
  }

  const raios = {}; todos.forEach(e => { const v = cs(e).borderTopLeftRadius; if (v !== '0px') raios[v] = (raios[v] || 0) + 1; });
  return {
    url: location.href, tamanho: `${innerWidth}x${innerHeight}`, papel, achados, links,
    medidas: { fontes: familias.slice(0, 4).map(f => f[0]), tamanhosDeFonte: tamanhos, palavrasNaDobra: palavrasDobra, raios, sombras: new Set(todos.map(e => cs(e).boxShadow).filter(v => v !== 'none')).size, camadasFixasPx: coberto, alvos: interativos.length },
  };
})()
