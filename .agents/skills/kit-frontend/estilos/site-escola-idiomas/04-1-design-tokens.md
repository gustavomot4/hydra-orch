## 1. Design Tokens

Copie este bloco como base do seu CSS. Os valores partem dos que o autor observou no site analisado; os que reprovavam em contraste ou não funcionavam como escritos foram corrigidos na versão 2.0.0 (ver `CHANGELOG.md`). Para usar outra marca, defina só `--brand` e siga o §1.1.

```css
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: light;   /* sem tema escuro */

  /* ---------- MARCA (defina só --brand; o resto é derivado) ---------- */
  --brand:            #d71920;                                      /* botões, faixa de CTA, destaques */
  --brand-dark:       color-mix(in srgb, var(--brand) 79%, black);  /* #aa1419: footer, hover de botão, badge */
  --brand-deep:       color-mix(in srgb, var(--brand) 42%, black);  /* #5a0b0d: "vinho", títulos de seção, botão pressionado */
  --brand-light:      color-mix(in srgb, var(--brand) 88%, white);  /* #dc353b: só decorativa (gradientes, ilustrações) */
  --brand-tint:       color-mix(in srgb, var(--brand) 6%, white);   /* #fdf1f2: fundo de seção suave */

  /* texto ligado à marca: confira pelo §1.1 ao trocar --brand */
  --on-brand:         #ffffff;            /* texto e ícone sobre --brand */
  --on-brand-dark:    #ffffff;            /* texto e ícone sobre --brand-dark */
  --brand-text:       var(--brand);       /* a marca como texto sobre fundo claro: tag, rótulo ativo, asterisco, números */
  --brand-text-dark:  var(--brand-dark);  /* links, botão outline, ícones */

  /* ---------- NEUTROS ---------- */
  --heading:          #04000b;  /* títulos: quase-preto, NÃO #000 */
  --paragraph:        #666666;  /* corpo de texto e placeholder */
  --input-text:       #212529;  /* texto digitado em campo */
  --dark:             #0e0f11;  /* cookie bar */
  --white:            #ffffff;
  --bg-gray:          #f2f3ef;  /* fundo de seção alternado (quente, não frio) */
  --border:           #dee2e6;  /* divisórias e bordas decorativas; NÃO serve de limite de campo */
  --border-input:     #6c757d;  /* limite de input e select; passos futuros do stepper */

  /* ---------- ESTADO (sempre com ícone e texto, nunca só a cor) ---------- */
  --danger:           #b3261e;
  --success:          #1b6e3a;

  /* ---------- TIPOGRAFIA ---------- */
  --font: "Montserrat", system-ui, -apple-system, sans-serif;

  --fs-hero:      clamp(2.25rem, 1.4rem + 3.2vw, 3.75rem);     /* h1 do hero: 36 a 60px */
  --fs-section:   clamp(1.75rem, 1.2rem + 2.3vw, 3.125rem);    /* título de seção: 28 a 50px */
  --fs-cta:       clamp(1.5rem, 1rem + 2vw, 2.5rem);           /* título da faixa de CTA: 24 a 40px */
  --fs-hero-sub:  clamp(1.125rem, 1rem + .6vw, 1.5625rem);     /* subtítulo do hero: 18 a 25px */
  --fs-card:      clamp(1.375rem, 1.2rem + .6vw, 1.6875rem);   /* h3 de tile e de bloco: 22 a 27px */
  --fs-body-lg:   clamp(1.0625rem, .98rem + .35vw, 1.25rem);   /* corpo do hero: 17 a 20px */
  --fs-item:      1.25rem;         /* 20px: h4 de item, título de card */
  --fs-body:      1.0625rem;       /* 17px: corpo padrão (NÃO 16px) */
  --fs-ui:        max(1rem, 16px); /* 16px: campos, labels, links de navegação */
  --fs-caption:   .875rem;         /* 14px: eyebrow, badge, botão, data */

  --lh-tight:     1.15;  /* h1 */
  --lh-heading:   1.2;   /* h2..h6 e botões */
  --lh-snug:      1.3;   /* subtítulo do hero, título de card */
  --lh-caption:   1.4;   /* textos de 14px */
  --lh-lead:      1.6;   /* corpo do hero */
  --lh-body:      1.7;   /* parágrafos e leitura longa */

  /* ---------- ESPAÇAMENTO (escala de 6 passos) ---------- */
  --space-1: .25rem;  --space-2: .5rem;   --space-3: 1rem;
  --space-4: 1.5rem;  --space-5: 2.5rem;  --space-6: 3.5rem;
  --grid-gap:        2rem;    /* 32px: gap das grades de cards */

  --section-pt:      60px;    /* padding de seção, em cima */
  --section-pb:      60px;    /* padding de seção, embaixo */
  --section-tight:   48px;    /* .section--tight, em cima e embaixo */
  --heading-mb:      40px;    /* espaço entre título de seção e conteúdo */

  /* ---------- LAYOUT ---------- */
  --container:       1320px;  /* largura máxima do .container (1250px úteis com o respiro de 35px) */
  --container-pad:   20px;    /* respiro lateral */
  --header-h:        64px;    /* header de uma faixa */
  --cta-bar-h:       56px;    /* barra fixa das duas conversões, abaixo de 1200px */
  --cookie-h:        0px;     /* altura da cookie bar: o JS grava ao exibir e zera ao fechar */

  /* ---------- FORMA ---------- */
  --r-sm:   6px;    /* inputs e botões */
  --r-md:   8px;    /* badges */
  --r-lg:   20px;   /* cards, imagens, acordeão */
  --r-xl:   32px;   /* faixa de CTA */
  --r-full: 999px;  /* pílulas, eyebrow, campo da faixa de CTA */

  /* ---------- ELEVAÇÃO ---------- */
  --shadow-card:  0 2px 12px 0 rgb(0 0 0 / .09);
  --shadow-hover: 0 20px 40px -12px rgb(0 0 0 / .12), 0 8px 20px -8px color-mix(in srgb, var(--brand) 14%, transparent);
  --shadow-brand: 0 10px 30px 0 color-mix(in srgb, var(--brand) 40%, transparent); /* glow da bolha de chat */

  /* ---------- MOVIMENTO ---------- */
  --t-fast: .2s ease;          /* troca de cor em hover, dropdowns */
  --t-base: .25s ease;         /* cards */
  --t-slow: .35s ease-in-out;  /* imagem e overlay do tile */
}

@media (min-width: 768px) {
  :root { --section-pt: 100px; --section-pb: 120px; --heading-mb: 60px; --container-pad: 35px; }
}
@media (min-width: 1200px) {
  :root { --header-h: 143px; --cta-bar-h: 0px; }   /* header de duas faixas: 64 + 79 */
}

/* ---------- BASE ---------- */
html { scroll-padding-top: var(--header-h); scroll-padding-bottom: calc(var(--cta-bar-h) + var(--cookie-h) + var(--space-4)); }
body {
  margin: 0; padding-bottom: calc(var(--cta-bar-h) + var(--cookie-h));
  font-family: var(--font); font-size: var(--fs-body); line-height: var(--lh-body);
  color: var(--paragraph); background: var(--white);
}
h1, h2, h3, h4 { margin: 0; color: var(--heading); line-height: var(--lh-heading); letter-spacing: 0; }
h1 { line-height: var(--lh-tight); }
a { color: var(--brand-text-dark); }               /* link em texto corrido: cor + sublinhado do navegador */
button, input, select, textarea { font: inherit; } /* sem isso os controles saem em Arial */
::placeholder { color: var(--paragraph); opacity: 1; }

/* Foco: anel duplo, branco por dentro e escuro por fora. Um dos dois contrasta com qualquer fundo (§7). */
:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--white); outline-offset: 0;
  box-shadow: 0 0 0 4px var(--heading);
}
```
