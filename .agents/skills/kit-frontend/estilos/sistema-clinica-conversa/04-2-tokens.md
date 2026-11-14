## 2. Tokens

Cada medida compartilhada está declarada uma vez neste bloco, e o texto das outras seções cita o token, não o número. Os nomes de cor seguem os nomes semânticos do shadcn/ui (`--background`, `--foreground`, `--primary`, `--muted`, `--border`, `--input`, `--ring`), para a equipe reconhecer o padrão; os valores são próprios deste design. Medida que só um componente ou uma tela usa aparece uma vez, na descrição dele (seções 6 e 7).

```css
:root {
  /* cor: superfícies e texto */
  --background: #F6F2EC;
  --foreground: #1B2529;
  --foreground-hover: #0F171A;
  --card: #FFFFFF;
  --card-soft: #FBF8F4;
  --muted: #EEE8DF;
  --muted-foreground: #5B676C;
  --placeholder: #6B7579;
  --border: #EAE3D9;
  --border-strong: #CFC6B9;
  --input: #8F8577;
  --on-dark: #FFFFFF;

  /* cor: marca e ação */
  --primary: #0D6E66;
  --primary-hover: #0A5C55;
  --primary-foreground: #FFFFFF;
  --primary-soft: #E1F0EC;
  --primary-soft-hover: #D2E9E3;
  --on-primary-muted: #CDEBE6;
  --ring: var(--primary);

  /* cor: sobre superfície escura (--foreground como fundo) */
  --on-dark-accent: #8EE3D6;
  --on-dark-muted: #C9D2D5;
  --on-dark-danger: #FFB4A6;
  --on-dark-fill: rgba(255, 255, 255, .12);
  --ring-on-dark: var(--on-dark-accent);

  /* cor: marcador "agora" */
  --accent: #E8613C;
  --accent-text: #B9472A;
  --accent-soft: #FDE9E2;

  /* cor: retorno */
  --destructive: #B23B3B;
  --destructive-soft: #FBE7E7;
  --warning: #7A5000;
  --warning-soft: #FFF1D2;
  --success: #1D7A45;
  --success-soft: #E2F3E8;
  --info: #2F5E9E;
  --info-soft: #E5EDF8;

  /* cor: canal de contato (botão que abre a conversa) */
  --whatsapp: #187A43;
  --whatsapp-hover: #136437;
  --whatsapp-soft: #E3F4EA;

  /* cor: gráficos e agenda */
  --chart-in: #2E9D67;
  --chart-out: #E0603C;
  --chart-grid: #F0EBE3;
  --grid-half: #F3EEE7;
  --today-column: #F5FAF8;
  --slot-edge: rgba(255, 255, 255, .9);
  --overlay: rgba(20, 28, 31, .42);

  /* cor: iniciais das pessoas, fundo e texto de cada tom (4.2; o tom 0 usa o par 1) */
  --avatar-1-bg: #FCE3D6; --avatar-1-fg: #8E3A19;
  --avatar-2-bg: #DDF0E6; --avatar-2-fg: #1D6B45;
  --avatar-3-bg: #E3E8FB; --avatar-3-fg: #3446A3;
  --avatar-4-bg: #F7E3EF; --avatar-4-fg: #8E2F6B;
  --avatar-5-bg: #FFEFC4; --avatar-5-fg: #6E4B00;
  --avatar-6-bg: #DDEDF6; --avatar-6-fg: #245D7E;

  /* situações da consulta: texto (fg), fundo (bg) e barra ou contorno (bar) */
  --status-agendado-fg: #7A5000;     --status-agendado-bg: #FFFFFF;     --status-agendado-bar: #D9940E;
  --status-confirmado-fg: #17663B;   --status-confirmado-bg: #DCF3E5;   --status-confirmado-bar: #1F8A4C;
  --status-atendimento-fg: #FFFFFF;  --status-atendimento-bg: #5B45C2;  --status-atendimento-bar: #3E2C99;
  --status-atendimento-muted: #E4DEFB;
  --status-concluido-fg: #4A5559;    --status-concluido-bg: #ECEEEF;    --status-concluido-bar: #A3ACB0;
  --status-cancelado-fg: #A12F2F;    --status-cancelado-bg: #FBE7E7;    --status-cancelado-bar: #D16464;
  --status-faltou-fg: #934010;       --status-faltou-bg: #FCEBDD;       --status-faltou-bar: #E07B3F;
  --hatch: repeating-linear-gradient(135deg, rgba(255, 255, 255, .55) 0 6px, transparent 6px 12px);

  /* tipografia */
  --font: 'Figtree', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --text-hero: clamp(2.25rem, 4vw, 3.375rem);
  --text-display: 2.125rem; --text-display-sm: 1.75rem; --text-title: 1.375rem; --text-heading: 1.25rem; --text-section: 1.125rem; --text-lead: 1.0625rem;
  --text-body: 1rem; --text-ui: 0.9375rem; --text-small: 0.875rem; --text-caption: 0.8125rem; --text-micro: 0.75rem;
  --weight-regular: 400; --weight-medium: 500; --weight-semibold: 600; --weight-bold: 700; --weight-extrabold: 800;
  --leading-tight: 1.1; --leading-card: 1.22; --leading-body: 1.5;
  --tracking-hero: -1.6px; --tracking-display: -0.8px; --tracking-title: -0.4px; --tracking-caps: 0.6px;

  /* espaço */
  --space-2: 2px; --space-4: 4px; --space-6: 6px; --space-8: 8px; --space-10: 10px; --space-12: 12px; --space-14: 14px; --space-16: 16px;
  --space-18: 18px; --space-20: 20px; --space-24: 24px; --space-28: 28px; --space-32: 32px; --space-40: 40px; --space-48: 48px; --space-56: 56px;

  /* forma */
  --radius-sm: 10px; --radius-md: 12px; --radius: 14px; --radius-box: 16px;
  --radius-lg: 20px; --radius-xl: 24px; --radius-sheet: 28px; --radius-full: 999px;
  --line: 1px; --line-control: 1.5px; --line-error: 2px;

  /* tamanhos */
  --target: 44px; --control-sm: 38px; --control-md: 46px; --control-lg: 54px; --field: 50px; --chip: 40px; --fab: 56px;
  --icon-xs: 14px; --icon-sm: 16px; --icon-md: 18px; --icon: 20px; --icon-lg: 24px;

  /* sombra */
  --shadow-sm: 0 1px 4px rgba(40, 30, 20, .12);
  --shadow: 0 8px 24px rgba(27, 37, 41, .08);
  --shadow-lg: 0 24px 50px rgba(27, 37, 41, .18);
  --shadow-bar: 0 -8px 24px rgba(27, 37, 41, .08);
  --shadow-fab: 0 10px 24px color-mix(in srgb, var(--primary) 35%, transparent);
  --shadow-selected: 0 0 0 2.5px var(--primary), 0 8px 18px color-mix(in srgb, var(--primary) 25%, transparent);
  --shadow-live: 0 4px 12px color-mix(in srgb, var(--status-atendimento-bg) 30%, transparent);

  /* movimento */
  --duration-fast: 120ms; --duration-base: 160ms; --duration-slow: 200ms; --duration-spin: 800ms; --duration-shimmer: 1300ms;

  /* casca */
  --topbar: 68px; --topbar-mobile: 60px; --tabbar: 76px; --page-x: 32px;
  --page-max: 1480px; --page-form: 820px; --page-wide: 1180px;
  --side: 420px; --side-narrow: 380px; --summary: 360px; --overlay-width: 460px;
  --z-footer: 5; --z-topbar: 20; --z-fab: 25; --z-tabbar: 30; --z-popup: 30;
  --z-overlay: 40; --z-panel: 41; --z-menu: 50; --z-toast: 60; --z-skip: 100;
}
@media (max-width: 767px) { :root { --page-x: 16px; } }
```

Base, aplicada antes de qualquer componente:

```css
*, *::before, *::after { box-sizing: border-box; }
html { font-family: var(--font); color: var(--foreground); background: var(--background); line-height: var(--leading-body); font-synthesis: none; -webkit-text-size-adjust: 100%; }
body { margin: 0; font-size: var(--text-body); background: var(--background); }
button, input, select, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; }
h1, h2, h3, p, dl, dd, figure { margin: 0; }
ul, ol { margin: 0; padding: 0; }
a { color: var(--primary); text-underline-offset: 3px; }
:focus-visible { outline: 3px solid var(--ring); outline-offset: 2px; }
[data-surface="dark"] :focus-visible { outline-color: var(--ring-on-dark); }
[data-autofocus]:focus { outline: none; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; scroll-behavior: auto !important; }
}
```
