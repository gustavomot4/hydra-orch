### Auditoria automática (web)

Cole no console da página, com a janela em 1440×900 e de novo em 390×844. Ele lê
o DOM **renderizado** e só o que está no primeiro viewport. O acento, as sombras
e o `.shell` vêm dos tokens da seção 12, então trocar de marca não muda o script.

```js
(() => {
  const sonda = document.body.appendChild(document.createElement('i'));
  const token = (prop, nome) => { sonda.style[prop] = `var(${nome})`; return getComputedStyle(sonda)[prop]; };
  const ACENTO = token('backgroundColor', '--accent');
  const SOMBRAS = ['--shadow-card', '--shadow-control', '--shadow-modal'].map(n => token('boxShadow', n));
  sonda.remove();
  const RAIOS = ['0px', '6px', '8px', '12px', '18px', '28px', '980px', '50%'];
  const cs = e => getComputedStyle(e), unicos = a => [...new Set(a)];
  const vis = e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0 && r.left < innerWidth
        && cs(e).visibility !== 'hidden' && cs(e).display !== 'none'; };
  const els = [...document.querySelectorAll('body *')].filter(vis);
  const textos = [], tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = tw.nextNode());) if (n.textContent.trim() && vis(n.parentElement)) textos.push(n.parentElement);
  const txt = e => e.textContent.trim().slice(0, 30);
  const shell = document.querySelector('.shell');
  return {
    viewport:  `${innerWidth}x${innerHeight}`,
    familias:  unicos(textos.map(e => cs(e).fontFamily.split(',')[0].replace(/["']/g, '').trim())),
    tamanhos:  unicos(textos.map(e => cs(e).fontSize)).sort((a, b) => parseFloat(a) - parseFloat(b)),
    pesos:     unicos(textos.map(e => cs(e).fontWeight)).sort(),
    caixaAlta: unicos(textos.filter(e => cs(e).textTransform === 'uppercase').map(txt)),
    textoComOpacity: unicos(textos.filter(e => +cs(e).opacity < 1).map(txt)),
    acentoFundo: unicos(els.filter(e => cs(e).backgroundColor === ACENTO).map(txt)),
    acentoTexto: unicos(textos.filter(e => cs(e).color === ACENTO).map(txt)),
    sombrasFora: unicos(els.map(e => cs(e).boxShadow).filter(v => v !== 'none' && !v.includes('inset') && !SOMBRAS.includes(v))),
    raiosFora: unicos(els.flatMap(e => ['TopLeft', 'TopRight', 'BottomLeft', 'BottomRight'].map(c => cs(e)[`border${c}Radius`])).filter(v => !RAIOS.includes(v))),
    conteudo:  shell ? Math.round(shell.clientWidth - parseFloat(cs(shell).paddingLeft) - parseFloat(cs(shell).paddingRight)) : null,
    estrutura: { lang: document.documentElement.lang, main: document.querySelectorAll('main').length,
                 h1: document.querySelectorAll('h1').length,
                 navSemNome: document.querySelectorAll('nav:not([aria-label]):not([aria-labelledby])').length }
  };
})()
```

**Esperado:** `familias` com 1 ou 2 itens · `tamanhos` com no máximo 4 (40, 48 e
56 contam como um) · `pesos` `["400","600"]` · `caixaAlta`, `textoComOpacity`,
`sombrasFora` e `raiosFora` vazios · `acentoFundo` com 0 ou 1 item (o nome da
ação primária) · `acentoTexto` com no máximo 3 · `conteudo` 980 numa vitrine a
partir de 1069px, 560 num fluxo, `null` numa ferramenta (sem `.shell`) ·
`estrutura` com `lang` preenchido, `main` 1, `h1` 1 e `navSemNome` 0.

**O que o script não vê:** pseudo-elementos (o alvo ampliado pelo `::after`),
`opacity` herdada de um ancestral e os estados que não estão na tela (hover,
foco, erro, modal, toast). Esses ficam no checklist e na passada de `Tab`.

---
