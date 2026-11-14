## 2. Tokens

Os nomes foram neutralizados com o prefixo `--ui-`. As quatro categorias são numeradas; associe cada uma a um assunto da aplicação. Os valores de cor, fonte, espaço e geometria preservam a versão observada. O bloco seguinte pode ser copiado para um arquivo CSS sem depender do repositório de origem.

O tema claro é o padrão do CSS. A aplicação pode selecionar o tema inicial pela preferência do sistema, como no produto observado. Para trocar, atribua `data-theme="light"`, `data-theme="dark"` ou `data-theme="contrast"` ao elemento raiz.

```css
:root {
  color-scheme: light;

  /* superfícies */
  --ui-bg: #f3f6f8;
  --ui-bar: #ffffff;
  --ui-surface: #ffffff;
  --ui-surface-2: #edf2f5;
  --ui-line: #dae4eb;
  --ui-card-border: #dae4eb;
  --ui-field-border: #7d8991;
  --ui-overlay: rgba(15, 19, 32, 0.5);

  /* texto */
  --ui-text: #111a20;
  --ui-text-2: #384249;

  /* ação */
  --ui-action: #025e88;
  --ui-on-action: #ffffff;
  --ui-action-text: #014261;
  --ui-action-soft: #e7f3fc;
  --ui-action-line: #b1d7f1;
  --ui-selected: #e7f3fc;
  --ui-on-selected: #014261;
  --ui-tab-active: #e7f3fc;
  --ui-on-tab-active: #025e88;
  --ui-highlight: #025e88;
  --ui-on-highlight: #ffffff;
  --ui-focus: #025e88;
  --ui-disabled: #e4e8ea;
  --ui-on-disabled: #4b565d;
  --ui-disabled-line: transparent;

  /* situação */
  --ui-ok: #0a554f;
  --ui-ok-soft: #d9f5ee;
  --ui-warn: #7c3a03;
  --ui-warn-soft: #f9f5c8;
  --ui-danger: #8f1616;
  --ui-danger-soft: #fee2df;
  --ui-neutral: #384249;
  --ui-neutral-soft: #e4e8ea;
  --ui-count: #b42b01;
  --ui-on-count: #ffffff;

  /* liga e desliga */
  --ui-toggle-off: #7d8991;
  --ui-toggle-on: #077674;
  --ui-toggle-knob: #ffffff;
  --ui-toggle-knob-on: #ffffff;

  /* papel: sempre branco, para o que a câmera precisa ler (código em quadrado) */
  --ui-paper: #ffffff;

  /* WhatsApp: igual nos três temas */
  --ui-contact: #25d366;
  --ui-on-contact: #06281c;

  /* blocos de desenho dos cards */
  --ui-tone-1: #e7f3fc;
  --ui-on-tone-1: #025e88;
  --ui-tone-2: #fff1cf;
  --ui-on-tone-2: #8a4b00;
  --ui-tone-3: #d9f5ee;
  --ui-on-tone-3: #077674;
  --ui-tone-4: #ffe1ea;
  --ui-on-tone-4: #9f1640;
  --ui-tone-neutral: #eaeff2;
  --ui-on-tone-neutral: #384249;

  /* desenhos Duotone sobre a superfície, sem caixa pastel */
  --ui-icon-1: #025e88;
  --ui-icon-2: #8a4b00;
  --ui-icon-3: #077674;
  --ui-icon-4: #9f1640;
  --ui-icon-neutral: #384249;

  /* contorno extra de selos e avisos: só o alto contraste usa */
  --ui-edge: 0px;
  --ui-bar-line: 1px;

  /* letra: tudo em rem, para seguir o tamanho escolhido em "Letra, cor e som" */
  --ui-font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --ui-fs-small: 1rem;
  --ui-fs-body: 1.0625rem;
  --ui-fs-body-lg: 1.1875rem;
  --ui-fs-heading: 1.125rem;
  --ui-fs-card: 1.25rem;
  --ui-fs-title: 1.625rem;
  --ui-fs-display: 2.25rem;
  --ui-fs-button: 1.1875rem;
  --ui-fs-input: 1.25rem;
  /* o nome dos itens do menu encolhe com a largura da tela para os quatro caberem em 320 px */
  --ui-fs-tab: min(1rem, 4.4vw);
  --ui-lh-tight: 1.2;
  --ui-lh-body: 1.45;

  /* espaço */
  --ui-sp-1: 4px;
  --ui-sp-2: 8px;
  --ui-sp-3: 12px;
  --ui-sp-4: 16px;
  --ui-sp-5: 20px;
  --ui-sp-6: 24px;
  --ui-sp-8: 32px;

  /* raio */
  --ui-r-card: 20px;
  --ui-r-control: 16px;
  --ui-r-small: 12px;
  --ui-r-sheet: 26px;
  --ui-r-pill: 999px;

  /* medidas */
  --ui-tap: 48px;
  --ui-btn-h: 58px;
  --ui-col: 600px;
  --ui-col-wide: 1440px;
}

:root[data-theme="dark"] {
  color-scheme: dark;

  --ui-bg: #0e1014;
  --ui-bar: #14171d;
  --ui-surface: #1b2028;
  --ui-surface-2: #232a34;
  --ui-line: #2c333f;
  --ui-card-border: transparent;
  --ui-field-border: #7b8696;
  --ui-overlay: rgba(0, 0, 0, 0.62);

  --ui-text: #eef1f5;
  --ui-text-2: #aeb7c4;

  --ui-action: #2bb5ee;
  --ui-on-action: #03131b;
  --ui-action-text: #7fd4f8;
  --ui-action-soft: #0f3346;
  --ui-action-line: #1d5f80;
  --ui-selected: #0f3346;
  --ui-on-selected: #7fd4f8;
  --ui-tab-active: #2bb5ee;
  --ui-on-tab-active: #03131b;
  --ui-highlight: #9b2f93;
  --ui-on-highlight: #ffffff;
  --ui-focus: #7fd4f8;
  --ui-disabled: #232a34;
  --ui-on-disabled: #aeb7c4;
  --ui-disabled-line: transparent;

  --ui-ok: #74e3a3;
  --ui-ok-soft: #10391f;
  --ui-warn: #f5c451;
  --ui-warn-soft: #3f3011;
  --ui-danger: #ff9b9b;
  --ui-danger-soft: #3a1518;
  --ui-neutral: #aeb7c4;
  --ui-neutral-soft: #232a34;
  --ui-count: #ff9b9b;
  --ui-on-count: #2a0a0c;

  --ui-toggle-off: #7b8696;
  --ui-toggle-on: #2bb5ee;
  --ui-toggle-knob: #ffffff;
  --ui-toggle-knob-on: #03131b;

  --ui-tone-1: #2bb5ee;
  --ui-on-tone-1: #0b0d10;
  --ui-tone-2: #f2b632;
  --ui-on-tone-2: #0b0d10;
  --ui-tone-3: #2bb35a;
  --ui-on-tone-3: #0b0d10;
  --ui-tone-4: #c44fbb;
  --ui-on-tone-4: #0b0d10;
  --ui-tone-neutral: #3a4250;
  --ui-on-tone-neutral: #ffffff;

  --ui-icon-1: #2bb5ee;
  --ui-icon-2: #f2b632;
  --ui-icon-3: #2bb35a;
  --ui-icon-4: #e18ada;
  --ui-icon-neutral: #eef1f5;
}

:root[data-theme="contrast"] {
  color-scheme: dark;

  --ui-icon-1: #ffffff;
  --ui-icon-2: #ffffff;
  --ui-icon-3: #ffffff;
  --ui-icon-4: #ffffff;
  --ui-icon-neutral: #ffffff;

  --ui-bg: #000000;
  --ui-bar: #000000;
  --ui-surface: #000000;
  --ui-surface-2: #000000;
  --ui-line: #ffffff;
  --ui-card-border: #ffffff;
  --ui-field-border: #ffffff;
  --ui-overlay: rgba(0, 0, 0, 0.85);

  --ui-text: #ffffff;
  --ui-text-2: #ffffff;

  --ui-action: #ffd60a;
  --ui-on-action: #000000;
  --ui-action-text: #ffd60a;
  --ui-action-soft: #000000;
  --ui-action-line: #ffd60a;
  --ui-selected: #ffd60a;
  --ui-on-selected: #000000;
  --ui-tab-active: #ffd60a;
  --ui-on-tab-active: #000000;
  --ui-highlight: #ffffff;
  --ui-on-highlight: #000000;
  --ui-focus: #ffd60a;
  --ui-disabled: #000000;
  --ui-on-disabled: #ffffff;
  --ui-disabled-line: #ffffff;

  --ui-ok: #ffffff;
  --ui-ok-soft: #000000;
  --ui-warn: #ffffff;
  --ui-warn-soft: #000000;
  --ui-danger: #ffffff;
  --ui-danger-soft: #000000;
  --ui-neutral: #ffffff;
  --ui-neutral-soft: #000000;
  --ui-count: #ffffff;
  --ui-on-count: #000000;

  --ui-toggle-off: #000000;
  --ui-toggle-on: #ffd60a;
  --ui-toggle-knob: #ffffff;
  --ui-toggle-knob-on: #000000;

  --ui-tone-1: #ffffff;
  --ui-on-tone-1: #000000;
  --ui-tone-2: #ffffff;
  --ui-on-tone-2: #000000;
  --ui-tone-3: #ffffff;
  --ui-on-tone-3: #000000;
  --ui-tone-4: #ffffff;
  --ui-on-tone-4: #000000;
  --ui-tone-neutral: #ffffff;
  --ui-on-tone-neutral: #000000;

  --ui-edge: 2px;
  --ui-bar-line: 2px;
}
```
