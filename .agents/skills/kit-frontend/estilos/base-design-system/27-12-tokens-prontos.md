## 12. Tokens prontos

Os quatro formatos abaixo dizem a mesma coisa. Cole o CSS inteiro no começo do
CSS do projeto: as medidas são declaradas aqui, uma vez, e o resto do projeto só
usa `var()`. Trocou um valor, troque em todos os formatos.

### CSS

```css
/* Base */
*, *::before, *::after { box-sizing: border-box; }
html { scroll-padding-top: 48px; }   /* altura da barra fixa (seção 7); sem barra fixa, remova */
body { margin: 0; background: var(--paper); color: var(--ink);
       font-family: Inter, system-ui, sans-serif; font-size: var(--t-17); font-weight: 400; }
button, input, select, textarea { font: inherit; letter-spacing: inherit; }

:root {
  color-scheme: light;

  /* Superfícies — uma temperatura só, não misture */
  --paper:    #FAF9F7;
  --surface:  #FFFFFF;
  --sunken:   #F4F2EC;
  --fill:     rgba(118, 114, 106, 0.12);
  --fill-2:   rgba(118, 114, 106, 0.18);
  --line:     #E8E4DC;

  /* Texto — razão sobre --surface · --paper */
  --ink:      #1C1B19;   /* 17,21 · 16,36 */
  --ink-2:    #6B6862;   /*  5,55 ·  5,28 */
  --ink-3:    #827E76;   /*  4,04 ·  3,84 — só não-texto e texto de 28px ou mais */

  /* Acento — troque estes quatro e o produto muda de marca */
  --accent:        #1F4E8C;   /* 8,31 com branco: serve de fundo E de texto */
  --accent-hover:  #2A5B9C;   /* mais claro; 6,83 */
  --accent-active: #183F73;   /* mais escuro; 10,51 */
  --on-accent:     #FFFFFF;

  /* Perigo — só erro de campo, estado crítico e ação destrutiva */
  --danger:        #8E2C26;   /* 8,27 com branco */
  --danger-hover:  #9C332C;   /* 7,18 */
  --danger-active: #7A2520;   /* 9,94 */

  /* Tipografia: a rampa 12·14·17·21·28·40·48·56 */
  --t-12: 0.75rem;
  --t-14: 0.875rem;
  --t-17: 1.0625rem;
  --t-21: 1.3125rem;
  --t-28: 1.75rem;
  --t-display: 3.5rem;      /* 56; vira 48 em 735–1068 e 40 em ≤734 */
  --tr-display: -0.005em;   /* acompanha o tamanho: −0,003em em 48, 0 em 40 */
  --tr-17: -0.011em;
  --tr-14: -0.008em;
  --tr-12: -0.005em;        /* 21 e 28 têm tracking 0 */
  --lh-titulo: calc(1em + 4px);
  --lh-corpo:  calc(1em + 8px);
  --lh-denso:  calc(1em + 6px);
  --lh-botao:  calc(1em + 3px);

  /* Geometria: 50% (avatar, botão do interruptor) é escrito direto */
  --r-6:    6px;
  --r-8:    8px;
  --r-12:  12px;
  --r-18:  18px;
  --r-28:  28px;
  --r-pill: 980px;
  --shadow-card:    2px 4px 12px 0 rgba(0, 0, 0, 0.08);
  --shadow-control: 0 1px 2px 0 rgba(0, 0, 0, 0.18);
  --shadow-modal:   0 16px 48px 0 rgba(0, 0, 0, 0.18);

  /* Espaçamento (5.8) */
  --s-4: 4px;  --s-8: 8px;  --s-12: 12px;  --s-16: 16px;
  --s-20: 20px;  --s-24: 24px;  --s-32: 32px;  --s-40: 40px;

  /* Alturas e alvos (6.3 e seção 7) */
  --h-grande:   44px;   /* botão primário e campo de vitrine e de fluxo */
  --h-medio:    36px;   /* botão secundário de vitrine e de fluxo */
  --h-botao:    32px;   /* botão de ferramenta: no toque o alvo cresce pelo ::after, a caixa não */
  --h-controle: 32px;   /* campo, segmented e item de navegação da ferramenta; 44px no toque */
  --h-linha:    36px;   /* linha de tabela; 44px no toque */
  --alvo:       28px;

  /* Layout (seção 5) */
  --shell:   1024px;    /* 1024 − 44 = 980 de conteúdo */
  --prosa:    692px;
  --fluxo:    560px;
  --gutter:    22px;
  --secao-pt:  96px;
  --secao-pb: 104px;
  --bloco:     40px;
  --pad-cartao: 24px;
  --grade-col: 40px;
  --grade-lin: 82px;

  /* Movimento (seção 8) */
  --dur-fast:   150ms;
  --dur-base:   280ms;
  --dur-screen: 320ms;
  --ease: cubic-bezier(0.28, 0.11, 0.32, 1);
}

@media (max-width: 1068px) {
  :root { --t-display: 3rem; --tr-display: -0.003em;
          --secao-pt: 80px; --secao-pb: 88px; --bloco: 32px; --pad-cartao: 20px; --grade-col: 24px; }
}
@media (max-width: 734px) {
  :root { --t-display: 2.5rem; --tr-display: 0em;
          --secao-pt: 72px; --secao-pb: 78px; --pad-cartao: 16px; }
}
@media (pointer: coarse) {
  :root { --alvo: 44px; --h-controle: 44px; --h-linha: 44px; }
}

/* Texto — cada classe declara tamanho, line-height e tracking (3.3); o peso é .w-600 ou 400 */
.t-display { font-size: var(--t-display); line-height: var(--lh-titulo); letter-spacing: var(--tr-display); font-weight: 600; }
.t-28 { font-size: var(--t-28); line-height: var(--lh-titulo); letter-spacing: 0; }
.t-21 { font-size: var(--t-21); line-height: var(--lh-titulo); letter-spacing: 0; }
.t-17 { font-size: var(--t-17); line-height: var(--lh-corpo);  letter-spacing: var(--tr-17); }
.t-14 { font-size: var(--t-14); line-height: var(--lh-denso);  letter-spacing: var(--tr-14); }
.t-12 { font-size: var(--t-12); line-height: var(--lh-denso);  letter-spacing: var(--tr-12); }
.lh-titulo { line-height: var(--lh-titulo); }   /* título em 17, 14 ou 12 */
.lh-corpo  { line-height: var(--lh-corpo); }    /* parágrafo em 14 */
.w-600 { font-weight: 600; }
.num { font-variant-numeric: tabular-nums; }

/* Layout */
.shell { max-width: var(--shell); margin-inline: auto; padding-inline: var(--gutter); }
.shell-fluxo { max-width: calc(var(--fluxo) + 2 * var(--gutter)); }   /* junto de .shell: 560 de conteúdo */
.grid  { display: grid; grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr));
         column-gap: var(--grade-col); row-gap: var(--grade-lin); }
@media (max-width: 734px) {
  .shell { width: 87.5%; max-width: none; padding-inline: 0; }
  .grid  { grid-template-columns: minmax(0, 1fr); }
}

/* Foco e alvo (6.3 e 6.4) */
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card:focus-visible { outline-offset: 3px; }
.toast :focus-visible { outline-color: var(--surface); }
.btn, .chave, .terciario { position: relative; }
.btn::after, .chave::after, .terciario::after {
  content: ''; position: absolute; top: 50%; left: 50%;
  width: max(100%, var(--alvo)); height: max(100%, var(--alvo));
  transform: translate(-50%, -50%);
}
@media (forced-colors: active) { input, select, textarea { outline: 1px solid CanvasText; } }

/* Movimento reduzido (seção 8) */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important;
                           transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
}
```

Fonte: a URL com `opsz` da seção 3.5 entra no `<head>`. O CSS não precisa de
`font-optical-sizing`.
