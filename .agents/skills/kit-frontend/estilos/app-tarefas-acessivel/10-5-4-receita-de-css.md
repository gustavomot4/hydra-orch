### 5.4 Receita de CSS

O bloco seguinte reúne reset, moldura, navegação e componentes. As classes `ui-` são uma API visual de referência: podem ser adotadas como estão ou mapeadas aos componentes do framework escolhido. O código não implementa estado, rotas, validação, foco de diálogo ou integração de voz; esses comportamentos estão descritos nas próximas seções. O fim do bloco explicita a alternância das duas posições do menu para o exemplo HTML e complementa o estado desabilitado e o movimento reduzido do destino.

```css
/* Base do documento: reset, letra, foco e movimento reduzido. */
*,
*::before,
*::after { box-sizing: border-box; }

html {
  /* lib/theme.ts troca este valor para 115% ou 130% */
  font-size: 100%;
  /* O topo e o rodapé são fixos: quem recebe o foco rola para a faixa livre entre eles, sem ficar encoberto. */
  scroll-padding-block: 10rem;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

body {
  margin: 0;
  min-height: 100dvh;
  background: var(--ui-bg);
  color: var(--ui-text);
  font-family: var(--ui-font);
  font-size: var(--ui-fs-body);
  line-height: var(--ui-lh-body);
  -webkit-font-smoothing: antialiased;
  overflow-wrap: break-word;
}

h1,
h2,
h3,
p { margin: 0; }

button,
input,
select,
textarea { font: inherit; }
button { cursor: pointer; }
a { color: var(--ui-action-text); }
img,
svg { max-width: 100%; }
svg { flex: none; }

:focus-visible {
  outline: 3px solid var(--ui-focus);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* Texto só para leitor de tela. */
.ui-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}


/* Receitas compartilhadas: prefixo ui-, fonte nativa e valores dos tokens acima. */

/* ---------- moldura de tela ---------- */
.ui-screen { display: flex; flex-direction: column; min-height: 100dvh; background: var(--ui-bg); color: var(--ui-text); }
.ui-main { flex: 1 0 auto; width: 100%; max-width: var(--ui-col); margin: 0 auto; padding: var(--ui-sp-4) var(--ui-sp-4) var(--ui-sp-6); container-type: inline-size; overflow-wrap: anywhere; }
.ui-main :is(a, button, input, select, textarea, summary, iframe, [tabindex]) { scroll-margin-block: 1rem; }
.ui-main--wide { max-width: var(--ui-col-wide); }
.ui-main--center { display: flex; flex-direction: column; justify-content: center; }
/* O título recebe o foco ao entrar na tela, para o leitor de tela começar por ele. Não é um controle: fica sem contorno. */
.ui-main h1:focus { outline: none; }

.ui-title { margin-bottom: var(--ui-sp-2); font-size: var(--ui-fs-title); font-weight: 700; line-height: var(--ui-lh-tight); letter-spacing: -0.2px; }
.ui-lead { margin-bottom: var(--ui-sp-4); color: var(--ui-text-2); font-size: var(--ui-fs-body); }
.ui-title + .ui-stack,
.ui-title + .ui-section { margin-top: var(--ui-sp-3); }

.ui-footer { position: sticky; bottom: 0; z-index: 15; flex: none; background: var(--ui-bar); border-top: var(--ui-bar-line) solid var(--ui-line); padding: var(--ui-sp-3) var(--ui-sp-4) calc(var(--ui-sp-4) + env(safe-area-inset-bottom, 0px)); }
.ui-footer__inner { display: grid; gap: 10px; width: 100%; max-width: calc(var(--ui-col) - 2 * var(--ui-sp-4)); margin: 0 auto; }
.ui-footer--wide .ui-footer__inner { max-width: calc(var(--ui-col-wide) - 2 * var(--ui-sp-4)); }

/* ---------- topo ---------- */
.ui-topbar { position: sticky; top: 0; z-index: 20; display: flex; flex: none; flex-wrap: wrap; align-items: center; gap: var(--ui-sp-2); min-height: 64px; padding: var(--ui-sp-2) var(--ui-sp-3); background: var(--ui-bar); border-bottom: var(--ui-bar-line) solid var(--ui-line); }
.ui-topbar__start { display: flex; align-items: center; gap: var(--ui-sp-2); min-width: 0; margin-right: auto; }
.ui-topbar__end { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--ui-sp-2); min-width: 0; margin-left: auto; }
.ui-brand { display: flex; align-items: center; gap: 9px; min-height: var(--ui-tap); color: var(--ui-text); font-size: var(--ui-fs-body-lg); font-weight: 700; line-height: var(--ui-lh-tight); }

.ui-topbtn { position: relative; display: inline-flex; align-items: center; gap: 6px; flex: none; min-height: var(--ui-tap); padding: 0 14px; border: 2px solid transparent; border-radius: var(--ui-r-control); background: var(--ui-surface-2); color: var(--ui-text); font-size: var(--ui-fs-small); font-weight: 700; line-height: var(--ui-lh-tight); text-decoration: none; box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-topbtn--listen { border-radius: var(--ui-r-pill); border-color: var(--ui-action-line); background: var(--ui-action-soft); color: var(--ui-action-text); box-shadow: none; }
.ui-topbtn { max-width: 100%; }
.ui-topbtn--on { border-color: var(--ui-action); background: var(--ui-action); color: var(--ui-on-action); }

.ui-count { display: inline-grid; place-items: center; flex: none; min-width: 26px; height: 26px; padding: 0 7px; border-radius: var(--ui-r-pill); background: var(--ui-count); color: var(--ui-on-count); font-size: var(--ui-fs-small); font-weight: 700; line-height: 1; }

.ui-offline { display: flex; align-items: center; justify-content: center; gap: var(--ui-sp-2); padding: var(--ui-sp-2) var(--ui-sp-4); background: var(--ui-warn-soft); color: var(--ui-warn); font-size: var(--ui-fs-small); font-weight: 700; text-align: center; border-bottom: var(--ui-edge) solid var(--ui-line); }

/* ---------- menu de 4 itens ---------- */
.ui-tabbar { position: sticky; bottom: 0; z-index: 15; display: flex; flex: none; justify-content: space-around; gap: 2px; padding: 6px 6px calc(var(--ui-sp-2) + env(safe-area-inset-bottom, 0px)); background: var(--ui-bar); border-top: var(--ui-bar-line) solid var(--ui-line); }
.ui-tab { position: relative; display: flex; flex: 1 1 auto; flex-direction: column; align-items: center; justify-content: center; gap: 2px; min-width: 0; min-height: 60px; padding: 0 2px; border-radius: var(--ui-r-small); color: var(--ui-text-2); font-size: var(--ui-fs-tab); font-weight: 700; line-height: var(--ui-lh-tight); text-decoration: none; }
.ui-tab__pill { display: grid; place-items: center; width: min(60px, 100%); height: 32px; border-radius: var(--ui-r-pill); }
.ui-tab--active { color: var(--ui-action-text); font-weight: 700; }
.ui-tab--active .ui-tab__pill { background: var(--ui-tab-active); color: var(--ui-on-tab-active); }

/* no computador os mesmos 4 itens ficam no topo */
.ui-tabbar--top { position: static; flex: 0 1 auto; justify-content: center; gap: var(--ui-sp-2); margin: 0 auto; padding: 0; border: 0; background: transparent; }
.ui-tabbar--top .ui-tab { flex: none; flex-direction: row; gap: var(--ui-sp-2); min-height: 52px; padding: 0 18px; border-radius: var(--ui-r-control); font-size: var(--ui-fs-body-lg); }
.ui-tabbar--top .ui-tab__pill { width: auto; height: auto; border-radius: 0; background: transparent; }
.ui-tabbar--top .ui-tab--active { background: var(--ui-selected); color: var(--ui-on-selected); }
.ui-tabbar--top .ui-tab--active .ui-tab__pill { background: transparent; color: inherit; }

/* ---------- botões ---------- */
.ui-btn { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; min-height: var(--ui-btn-h); padding: 10px 18px; border: 2px solid transparent; border-radius: var(--ui-r-control); background: transparent; color: var(--ui-text); font-size: var(--ui-fs-button); font-weight: 700; line-height: var(--ui-lh-tight); text-align: center; text-decoration: none; }
.ui-btn--primary { background: var(--ui-action); color: var(--ui-on-action); }
.ui-btn--secondary { border-color: var(--ui-action); background: var(--ui-surface); color: var(--ui-action-text); }
.ui-btn--quiet { min-height: var(--ui-tap); color: var(--ui-text); font-weight: 700; text-decoration: underline; text-underline-offset: 4px; }
.ui-btn--contact { background: var(--ui-contact); color: var(--ui-on-contact); }
.ui-btn--danger { border-color: var(--ui-danger); background: var(--ui-surface); color: var(--ui-danger); }
.ui-btn--inline { display: inline-flex; width: auto; }
.ui-btn:active { transform: translateY(1px); }
.ui-btn[aria-disabled="true"],
.ui-btn:disabled { border-style: dashed; border-color: var(--ui-disabled-line); background: var(--ui-disabled); color: var(--ui-on-disabled); cursor: not-allowed; transform: none; }

/* ---------- cartões ---------- */
.ui-card { border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-card); background: var(--ui-surface); color: var(--ui-text); }
.ui-card--pad { position: relative; display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--ui-sp-3); padding: 14px; }
.ui-card--ok { border-color: var(--ui-ok); background: var(--ui-ok-soft); }
.ui-card--highlight { border-color: var(--ui-action-line); background: var(--ui-action-soft); }
.ui-card--ok .ui-icon,
.ui-card--highlight .ui-icon,
.ui-card--ok .ui-badge,
.ui-card--highlight .ui-badge,
.ui-rowcard--ok .ui-badge,
.ui-rowcard--highlight .ui-badge { background: var(--ui-surface); }
.ui-card__head { display: flex; align-items: center; gap: var(--ui-sp-3); }
.ui-card__headtext { flex: 1; min-width: 0; }
.ui-card__title { font-size: var(--ui-fs-card); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-card__sub { margin-top: 2px; color: var(--ui-text-2); font-size: var(--ui-fs-small); line-height: 1.3; }
.ui-card__badge { margin-top: 6px; }
/* O link do título cobre o cartão inteiro: o toque vale em qualquer ponto dele. */
.ui-card__link { color: inherit; text-decoration: none; }
.ui-card__link::after { content: ""; position: absolute; inset: 0; border-radius: inherit; }
.ui-card__link:focus-visible { outline: none; }
/* Outros botões e links do cartão recebem o toque: ficam acima da área do link do título. */
.ui-card--pad :is(a, button, input, select, textarea, summary):not(.ui-card__link) { position: relative; z-index: 1; }
.ui-card:has(.ui-card__link:focus-visible) { outline: 3px solid var(--ui-focus); outline-offset: 2px; }

.ui-heading { display: flex; align-items: center; gap: var(--ui-sp-3); margin-bottom: var(--ui-sp-4); }
.ui-heading__text { flex: 1; min-width: 0; }
.ui-heading .ui-title { margin-bottom: 0; }
.ui-heading__sub { margin-top: 2px; color: var(--ui-text-2); font-size: var(--ui-fs-body); line-height: 1.3; }
.ui-heading__badge { margin-top: 6px; }

.ui-bigcard { display: flex; align-items: center; gap: var(--ui-sp-3); width: 100%; min-height: 92px; padding: var(--ui-sp-3); border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-card); background: var(--ui-surface); color: var(--ui-text); text-align: left; text-decoration: none; }
.ui-bigcard__text { flex: 1; min-width: 0; }
.ui-bigcard__title { display: block; font-size: var(--ui-fs-card); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-bigcard__sub { display: block; margin-top: 3px; color: var(--ui-text-2); font-size: var(--ui-fs-small); line-height: 1.3; }
.ui-bigcard__go { flex: none; color: var(--ui-text-2); }
.ui-bigcard--tile { flex-direction: column; align-items: flex-start; gap: 10px; min-height: 0; padding: 14px; }
.ui-bigcard--tile .ui-bigcard__go { display: none; }
.ui-bigcard--emphasis { border-color: var(--ui-action-line); background: var(--ui-action-soft); }
.ui-bigcard--emphasis .ui-icon { background: var(--ui-surface); color: var(--ui-action-text); }
.ui-bigcard--highlight { border-color: transparent; background: var(--ui-highlight); color: var(--ui-on-highlight); min-height: 0; padding: 14px; }
.ui-bigcard--highlight .ui-bigcard__title { font-size: var(--ui-fs-heading); }
.ui-bigcard--highlight .ui-bigcard__sub,
.ui-bigcard--highlight .ui-bigcard__go { color: var(--ui-on-highlight); }

/* grade de cards: duas colunas quando cabem, uma quando a letra está grande ou a tela é estreita */
.ui-cardgrid { container-type: inline-size; }
.ui-cardgrid__inner { display: grid; grid-template-columns: 1fr 1fr; gap: var(--ui-sp-3); }
@container (max-width: 17.5rem) {
  .ui-cardgrid__inner { grid-template-columns: 1fr; }
  .ui-cardgrid__inner .ui-bigcard--tile { flex-direction: row; align-items: center; min-height: 80px; }
  .ui-cardgrid__inner .ui-option--tile { flex-direction: row; justify-content: flex-start; min-height: 64px; text-align: left; }
  .ui-cardgrid__inner .ui-option--tile .ui-option__text { flex: 1; min-width: 0; padding-right: 28px; }
}
@container (min-width: 46rem) {
  .ui-cardgrid--auto .ui-cardgrid__inner { grid-template-columns: repeat(4, 1fr); }
}
.ui-cardgrid--three .ui-cardgrid__inner { grid-template-columns: repeat(3, 1fr); gap: var(--ui-sp-2); }
@container (max-width: 17.5rem) {
  .ui-cardgrid--three .ui-cardgrid__inner { grid-template-columns: 1fr; }
}

.ui-icon { display: grid; place-items: center; flex: none; width: 56px; height: 56px; border-radius: var(--ui-r-control); background: transparent; color: var(--ui-icon-neutral); }
.ui-icon > svg { width: 40px; height: 40px; }
.ui-icon--sm { width: 44px; height: 44px; border-radius: var(--ui-r-small); }
.ui-icon--sm > svg { width: 28px; height: 28px; }
.ui-icon--lg { width: 64px; height: 64px; }
.ui-icon--lg > svg { width: 48px; height: 48px; }
.ui-icon--xl { width: 112px; height: 112px; border-radius: var(--ui-r-pill); }
.ui-icon--xl > svg { width: 64px; height: 64px; }
.ui-icon--cat-1 { color: var(--ui-icon-1); }
.ui-icon--cat-2 { color: var(--ui-icon-2); }
.ui-icon--cat-3 { color: var(--ui-icon-3); }
.ui-icon--cat-4 { color: var(--ui-icon-4); }
.ui-icon--ok { background: var(--ui-ok-soft); color: var(--ui-ok); box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-icon--contactrn { background: var(--ui-warn-soft); color: var(--ui-warn); box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-icon--action { background: var(--ui-action-soft); color: var(--ui-action-text); box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-action-line); }
.ui-icon--contact { background: var(--ui-contact); color: var(--ui-on-contact); }
.ui-icon--plain { background: transparent; color: inherit; }

.ui-rowcard { display: flex; align-items: center; gap: var(--ui-sp-3); width: 100%; min-height: 72px; padding: var(--ui-sp-3) 14px; border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-card); background: var(--ui-surface); color: var(--ui-text); font: inherit; text-align: left; text-decoration: none; }
.ui-rowcard__text { flex: 1; min-width: 0; }
.ui-rowcard__title { display: block; font-size: var(--ui-fs-body-lg); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-rowcard__sub { display: block; margin-top: 2px; color: var(--ui-text-2); font-size: var(--ui-fs-small); line-height: 1.3; }
.ui-rowcard__badge { display: block; margin-top: 6px; }
.ui-rowcard__go { flex: none; color: var(--ui-text-2); }
.ui-rowcard--ok { border-color: var(--ui-ok); background: var(--ui-ok-soft); }
.ui-rowcard--highlight { border-color: var(--ui-action-line); background: var(--ui-action-soft); }
.ui-rowcard--highlight .ui-icon,
.ui-rowcard--ok .ui-icon { background: var(--ui-surface); }

.ui-avatar { display: grid; place-items: center; flex: none; width: 56px; height: 56px; overflow: hidden; border-radius: var(--ui-r-pill); background: var(--ui-action-soft); color: var(--ui-action-text); font-size: var(--ui-fs-card); font-weight: 700; line-height: 1; box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-action-line); }
.ui-avatar--lg { width: 84px; height: 84px; font-size: var(--ui-fs-title); }
.ui-avatar img { width: 100%; height: 100%; object-fit: cover; }

.ui-badge { display: inline-flex; align-items: center; gap: 5px; max-width: 100%; padding: 4px 10px; border-radius: var(--ui-r-pill); background: var(--ui-neutral-soft); color: var(--ui-neutral); font-size: var(--ui-fs-small); font-weight: 700; line-height: 1.3; box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-badge--ok { background: var(--ui-ok-soft); color: var(--ui-ok); }
.ui-badge--warn { background: var(--ui-warn-soft); color: var(--ui-warn); }
.ui-badge--info { background: var(--ui-action-soft); color: var(--ui-action-text); }
.ui-badge--danger { background: var(--ui-danger-soft); color: var(--ui-danger); }

/* ---------- avisos na tela ---------- */
.ui-notice { display: flex; align-items: flex-start; gap: 10px; padding: var(--ui-sp-3) 14px; border-radius: var(--ui-r-small); background: var(--ui-action-soft); color: var(--ui-action-text); font-size: var(--ui-fs-body); line-height: 1.35; box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-notice__body { flex: 1; min-width: 0; }
.ui-notice__title { display: block; font-weight: 700; }
.ui-notice__action { margin-top: var(--ui-sp-2); }
.ui-notice--ok { background: var(--ui-ok-soft); color: var(--ui-ok); }
.ui-notice--warn { background: var(--ui-warn-soft); color: var(--ui-warn); }
.ui-notice--error { background: var(--ui-danger-soft); color: var(--ui-danger); }
.ui-linkbtn { display: inline-flex; align-items: center; gap: 6px; min-height: var(--ui-tap); padding: 0; border: 0; background: transparent; color: inherit; font-size: inherit; font-weight: 700; text-decoration: underline; text-underline-offset: 4px; }

/* avisos que aparecem por alguns segundos, no alto, para não cobrir o botão principal */
.ui-toasts { position: fixed; top: 72px; right: 0; left: 0; z-index: 70; display: grid; justify-items: center; gap: var(--ui-sp-2); padding: 0 var(--ui-sp-3); pointer-events: none; }
.ui-toasts > .ui-notice { width: 100%; max-width: calc(var(--ui-col) - 2 * var(--ui-sp-3)); pointer-events: auto; box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line), 0 8px 24px var(--ui-overlay); }

/* ---------- blocos de conteúdo ---------- */
/* Itens de grade podem ficar mais estreitos que a maior palavra: ela quebra, a tela não rola para o lado. */
.ui-stack > *,
.ui-section > *,
.ui-options > *,
.ui-cardgrid__inner > *,
.ui-footer__inner > *,
.ui-sheet__actions > * { min-width: 0; }
.ui-stack { display: grid; gap: var(--ui-sp-3); }
.ui-stack--tight { gap: var(--ui-sp-2); }
.ui-stack--loose { gap: var(--ui-sp-5); }
.ui-list { display: grid; gap: var(--ui-sp-3); margin: 0; padding: 0; list-style: none; }
.ui-list > * { min-width: 0; }
.ui-section { display: grid; gap: var(--ui-sp-3); }
.ui-section + .ui-section,
.ui-stack > .ui-section + * { margin-top: var(--ui-sp-2); }
.ui-section__title { font-size: var(--ui-fs-heading); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-text { color: var(--ui-text-2); font-size: var(--ui-fs-body); }
.ui-text--strong { color: var(--ui-text); font-weight: 700; }
.ui-loading { padding: var(--ui-sp-6) 0; color: var(--ui-text-2); font-size: var(--ui-fs-body); text-align: center; }

.ui-facts { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.ui-fact { display: flex; align-items: center; gap: 9px; font-size: var(--ui-fs-body); line-height: 1.25; }
.ui-fact > svg { color: var(--ui-action-text); }
.ui-fact__text { min-width: 0; }
.ui-fact__sub { display: block; color: var(--ui-text-2); font-size: var(--ui-fs-small); }
.ui-fact b { font-weight: 700; }
.ui-facts--boxed { gap: 10px; }
.ui-facts--boxed .ui-fact { padding: var(--ui-sp-3) 14px; border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-small); background: var(--ui-surface); font-size: var(--ui-fs-body-lg); }

.ui-empty { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: var(--ui-sp-2); padding: var(--ui-sp-8) 0; text-align: center; }
.ui-empty__title { font-size: var(--ui-fs-title); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-empty__title--sm { font-size: var(--ui-fs-card); }
.ui-empty__text { max-width: 30ch; color: var(--ui-text-2); font-size: var(--ui-fs-body); }
.ui-empty__action { width: 100%; margin-top: var(--ui-sp-3); }
.ui-empty .ui-icon { margin-bottom: var(--ui-sp-3); }

.ui-success { display: flex; flex-direction: column; align-items: center; padding-top: var(--ui-sp-5); text-align: center; }
.ui-success .ui-icon { margin-bottom: 18px; }
.ui-success__title { font-size: var(--ui-fs-display); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-success__text { margin-top: 6px; color: var(--ui-text-2); font-size: var(--ui-fs-body-lg); }
.ui-success__next { margin-top: var(--ui-sp-6); }

/* ---------- linha do tempo ---------- */
.ui-timeline { display: grid; margin: 0; padding: 0; list-style: none; }
.ui-timeline__step { position: relative; display: grid; grid-template-columns: 40px 1fr; gap: var(--ui-sp-3); min-height: 66px; padding-bottom: var(--ui-sp-3); }
.ui-timeline__step::before { content: ""; position: absolute; top: 40px; bottom: 0; left: 18px; width: 4px; background: var(--ui-line); }
.ui-timeline__step:last-child { min-height: 40px; padding-bottom: 0; }
.ui-timeline__step:last-child::before { display: none; }
.ui-timeline__dot { z-index: 1; display: grid; place-items: center; width: 40px; height: 40px; border-radius: var(--ui-r-pill); background: var(--ui-neutral-soft); color: var(--ui-neutral); box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-timeline__title { display: block; padding-top: 2px; font-size: var(--ui-fs-body-lg); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-timeline__text { display: block; color: var(--ui-text-2); font-size: var(--ui-fs-small); line-height: 1.3; }
.ui-timeline__step--done .ui-timeline__dot { background: var(--ui-ok); color: var(--ui-ok-soft); }
.ui-timeline__step--done::before { background: var(--ui-ok); }
.ui-timeline__step--now .ui-timeline__dot { background: var(--ui-action); color: var(--ui-on-action); box-shadow: 0 0 0 5px var(--ui-action-line); }
.ui-timeline__step--todo .ui-timeline__title { color: var(--ui-text-2); font-weight: 700; }

/* ---------- passos ---------- */
.ui-steps { display: flex; align-items: center; gap: 6px; margin-bottom: var(--ui-sp-4); }
.ui-steps__bar { flex: 1; height: 8px; border-radius: var(--ui-r-pill); background: var(--ui-line); box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-steps__bar--on { background: var(--ui-action); box-shadow: none; }
.ui-steps__label { margin-left: var(--ui-sp-2); color: var(--ui-text-2); font-size: var(--ui-fs-small); font-weight: 700; white-space: nowrap; }

/* ---------- escolhas ---------- */
.ui-fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
.ui-fieldset__legend { margin-bottom: var(--ui-sp-2); padding: 0; font-size: var(--ui-fs-heading); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-options { display: grid; gap: 10px; }
.ui-option { position: relative; display: flex; align-items: center; gap: var(--ui-sp-3); min-height: 64px; padding: 10px 14px; border: 2px solid var(--ui-field-border); border-radius: var(--ui-r-control); background: var(--ui-surface); color: var(--ui-text); font-size: var(--ui-fs-body-lg); font-weight: 700; line-height: var(--ui-lh-tight); cursor: pointer; }
.ui-option__input { position: absolute; width: 1px; height: 1px; margin: 0; opacity: 0; }
.ui-option__text { flex: 1; min-width: 0; }
.ui-option__sub { display: block; margin-top: 2px; color: var(--ui-text-2); font-size: var(--ui-fs-small); font-weight: 500; }
.ui-option__check { display: grid; place-items: center; flex: none; width: 30px; height: 30px; border: 2px solid var(--ui-field-border); border-radius: var(--ui-r-pill); color: transparent; }
.ui-option:has(.ui-option__input:checked) { border-color: var(--ui-action); background: var(--ui-selected); color: var(--ui-on-selected); box-shadow: inset 0 0 0 1px var(--ui-action); }
.ui-option:has(.ui-option__input:checked) .ui-option__sub { color: inherit; }
.ui-option:has(.ui-option__input:checked) .ui-option__check { border-color: var(--ui-action); background: var(--ui-action); color: var(--ui-on-action); }
.ui-option:has(.ui-option__input:focus-visible) { outline: 3px solid var(--ui-focus); outline-offset: 2px; }
.ui-option:has(.ui-option__input:disabled) { background: var(--ui-disabled); color: var(--ui-on-disabled); cursor: not-allowed; }
.ui-option--tile { flex-direction: column; justify-content: center; gap: var(--ui-sp-2); min-height: 96px; padding: 10px 8px; font-size: var(--ui-fs-body); text-align: center; }
.ui-option--tile .ui-option__check { position: absolute; top: 6px; right: 6px; width: 24px; height: 24px; }
.ui-option--tile .ui-option__text { flex: none; }

.ui-chips { display: flex; flex-wrap: wrap; gap: 9px; margin: 0; padding: 0; border: 0; }
.ui-chip { display: inline-flex; align-items: center; gap: 7px; min-width: 0; max-width: 100%; min-height: var(--ui-tap); padding: 6px 16px; text-align: left; border: 2px solid var(--ui-field-border); border-radius: var(--ui-r-pill); background: var(--ui-surface); color: var(--ui-text); font-size: var(--ui-fs-body); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-chip[aria-pressed="true"] { border-color: var(--ui-action); background: var(--ui-action); color: var(--ui-on-action); }

.ui-toggle { display: flex; align-items: center; gap: var(--ui-sp-3); width: 100%; min-height: 72px; padding: var(--ui-sp-3) 14px; border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-card); background: var(--ui-surface); color: var(--ui-text); text-align: left; }
.ui-toggle__text { flex: 1; min-width: 0; }
.ui-toggle__label { display: block; font-size: var(--ui-fs-body-lg); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-toggle__sub { display: block; margin-top: 2px; color: var(--ui-text-2); font-size: var(--ui-fs-small); line-height: 1.3; }
.ui-toggle__track { position: relative; flex: none; width: 56px; height: 32px; border-radius: var(--ui-r-pill); background: var(--ui-toggle-off); box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); transition: background-color 150ms ease; }
.ui-toggle__track::after { content: ""; position: absolute; top: 3px; left: 3px; width: 26px; height: 26px; border-radius: var(--ui-r-pill); background: var(--ui-toggle-knob); transition: transform 150ms ease; }
.ui-toggle[aria-checked="true"] .ui-toggle__track { background: var(--ui-toggle-on); box-shadow: none; }
.ui-toggle[aria-checked="true"] .ui-toggle__track::after { background: var(--ui-toggle-knob-on); transform: translateX(24px); }

/* ---------- campos ---------- */
.ui-field { display: grid; gap: 7px; }
.ui-field__label { font-size: var(--ui-fs-heading); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-field__hint { color: var(--ui-text-2); font-size: var(--ui-fs-small); }
.ui-field__row { display: flex; align-items: stretch; gap: var(--ui-sp-2); }
.ui-field__row > .ui-input { flex: 1; min-width: 0; }
.ui-field__error { display: flex; align-items: flex-start; gap: var(--ui-sp-2); padding: 10px var(--ui-sp-3); border-radius: var(--ui-r-small); background: var(--ui-danger-soft); color: var(--ui-danger); font-size: var(--ui-fs-body); font-weight: 700; line-height: 1.35; box-shadow: inset 0 0 0 var(--ui-edge) var(--ui-line); }
.ui-input { width: 100%; min-height: 60px; padding: 10px var(--ui-sp-4); border: 2px solid var(--ui-field-border); border-radius: var(--ui-r-control); background: var(--ui-surface); color: var(--ui-text); font-size: var(--ui-fs-input); font-weight: 600; line-height: 1.3; }
.ui-input::placeholder { color: var(--ui-text-2); font-weight: 500; opacity: 1; }
.ui-input:focus { border-color: var(--ui-focus); outline: none; box-shadow: 0 0 0 4px var(--ui-action-line); }
.ui-input[aria-invalid="true"] { border-color: var(--ui-danger); box-shadow: 0 0 0 4px var(--ui-danger-soft); }
textarea.ui-input { min-height: 132px; resize: vertical; }

.ui-search { display: flex; align-items: center; gap: 10px; min-height: 60px; padding: 4px 6px 4px 14px; border: 2px solid var(--ui-field-border); border-radius: var(--ui-r-control); background: var(--ui-surface); color: var(--ui-text-2); }
.ui-search:focus-within { border-color: var(--ui-focus); box-shadow: 0 0 0 4px var(--ui-action-line); }
.ui-search__input { flex: 1; min-width: 0; min-height: var(--ui-tap); padding: 0; border: 0; background: transparent; color: var(--ui-text); font-size: var(--ui-fs-body-lg); }
.ui-search__input::placeholder { color: var(--ui-text-2); opacity: 1; }
.ui-search__input:focus { outline: none; }

.ui-voice { display: inline-flex; align-items: center; gap: 6px; flex: none; min-height: var(--ui-tap); padding: 0 var(--ui-sp-3); border: 2px solid var(--ui-action-line); border-radius: var(--ui-r-pill); background: var(--ui-action-soft); color: var(--ui-action-text); font-size: var(--ui-fs-small); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-voice[aria-pressed="true"] { border-color: var(--ui-action); background: var(--ui-action); color: var(--ui-on-action); }
.ui-voice--block { min-height: 56px; padding: 0 var(--ui-sp-4); border-style: dashed; border-radius: var(--ui-r-control); }

.ui-qr { display: block; width: min(220px, 100%); height: auto; padding: var(--ui-sp-2); border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-small); background: var(--ui-paper); }

/* ---------- painel que sobe de baixo ---------- */
.ui-sheet-layer { position: fixed; inset: 0; z-index: 60; display: flex; align-items: flex-end; justify-content: center; background: var(--ui-overlay); }
.ui-sheet { width: 100%; max-width: var(--ui-col); max-height: 92dvh; overflow-y: auto; padding: 10px var(--ui-sp-4) calc(18px + env(safe-area-inset-bottom, 0px)); border: 2px solid var(--ui-card-border); border-bottom: 0; border-radius: var(--ui-r-sheet) var(--ui-r-sheet) 0 0; background: var(--ui-surface); color: var(--ui-text); animation: cr-sheet-in 200ms ease-out both; }
.ui-sheet::before { content: ""; display: block; width: 46px; height: 5px; margin: 0 auto 14px; border-radius: var(--ui-r-pill); background: var(--ui-field-border); }
.ui-sheet__title { margin-bottom: 6px; font-size: var(--ui-fs-title); font-weight: 700; line-height: var(--ui-lh-tight); }
.ui-sheet__title:focus { outline: none; }
.ui-sheet__text { margin-bottom: var(--ui-sp-4); color: var(--ui-text-2); font-size: var(--ui-fs-body); }
.ui-sheet__actions { display: grid; gap: 10px; margin-top: var(--ui-sp-5); }
@keyframes cr-sheet-in { from { transform: translateY(24px); opacity: 0; } }

/* ---------- telas muito estreitas ---------- */
/*
 * 320 px com zoom de 200% deixa o conteúdo com cerca de 130 px. As peças se ajustam pela
 * largura do conteúdo (.ui-main é o contêiner), em rem, para valer também com a letra maior.
 */
@container (max-width: 15rem) {
  .ui-steps { flex-wrap: wrap; }
  .ui-steps__label { flex-basis: 100%; margin-left: 0; white-space: normal; }
  .ui-card__head,
  .ui-heading { flex-direction: column; align-items: flex-start; }
  .ui-field__row { flex-direction: column; }
  .ui-voice { align-self: flex-start; }
  .ui-search { flex-wrap: wrap; }
  .ui-search .ui-voice { flex-basis: 100%; justify-content: center; }
}
@container (max-width: 11rem) {
  .ui-bigcard,
  .ui-rowcard,
  .ui-toggle { flex-direction: column; align-items: flex-start; }
  .ui-bigcard__go,
  .ui-rowcard__go { display: none; }
  .ui-icon--lg { width: 56px; height: 56px; }
  .ui-timeline__step { grid-template-columns: 32px 1fr; gap: var(--ui-sp-2); }
  .ui-timeline__dot { width: 32px; height: 32px; }
  .ui-timeline__step::before { top: 32px; left: 14px; }
  .ui-notice { flex-direction: column; }
  .ui-option { flex-direction: column; align-items: flex-start; }
  .ui-option .ui-option__text { flex: none; max-width: 100%; padding-right: 0; }
  .ui-option__check { position: absolute; top: 6px; right: 6px; width: 24px; height: 24px; }
  .ui-input { padding-inline: var(--ui-sp-2); }
}
/* O topo e o rodapé não estão dentro do contêiner: seguem a largura da janela. */
@media (max-width: 15rem) {
  .ui-topbar { padding-inline: var(--ui-sp-2); }
  .ui-topbtn { padding: 0 var(--ui-sp-2); }
  .ui-topbtn > svg { display: none; }
  .ui-footer { padding-inline: var(--ui-sp-2); }
  .ui-btn { padding-inline: var(--ui-sp-2); }
  .ui-main { padding-inline: var(--ui-sp-2); }
  .ui-sheet { padding-inline: var(--ui-sp-2); }
}


/* Lista ampla: o mesmo conteúdo e os mesmos três filtros em qualquer tela. */
.ui-catalog { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--ui-sp-5); }
.ui-catalog > * { min-width: 0; }
.ui-catalog__body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--ui-sp-5); }
.ui-catalog__filters { display: grid; align-content: start; gap: var(--ui-sp-3); min-width: 0; }
.ui-catalog__results { min-width: 0; }
.ui-catalog__summary { color: var(--ui-text-2); font-size: var(--ui-fs-small); scroll-margin-top: 7rem; }
.ui-catalog__summary:focus { outline: none; }
.ui-catalog__pagination { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-sp-3); padding-top: var(--ui-sp-3); border-top: 1px solid var(--ui-line); }
.ui-catalog__pagination > span { color: var(--ui-text-2); font-weight: 700; }
.ui-catalog__pagination .ui-btn { flex: 0 1 auto; }
.ui-catalog-item > .ui-card { height: 100%; }

@container (max-width: 26rem) {
  .ui-catalog__pagination > span { flex-basis: 100%; order: -1; text-align: center; }
  .ui-catalog__pagination .ui-btn { flex: 1 1 7rem; }
}

/* Em rem, o layout volta a empilhar quando a pessoa aumenta a letra. */
@container (min-width: 56rem) {
  .ui-catalog__body { grid-template-columns: 14rem minmax(0, 1fr); gap: var(--ui-sp-8); align-items: start; }
  .ui-catalog__filters { padding: var(--ui-sp-5); border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-card); background: var(--ui-surface); }
  .ui-catalog__filters .ui-chips { display: grid; }
  .ui-catalog__filters .ui-chip { justify-content: flex-start; width: 100%; }
  .ui-catalog-item > .ui-card { padding: var(--ui-sp-5); }
  .ui-catalog-item .ui-card__title { font-size: 1.375rem; }
}

@container (min-width: 68rem) {
  .ui-catalog-item > .ui-card { grid-template-columns: minmax(0, 1fr) minmax(16rem, 0.75fr); align-items: center; gap: var(--ui-sp-6); }
  .ui-catalog-item .ui-facts { padding-left: var(--ui-sp-5); border-left: 1px solid var(--ui-line); }
}


.ui-profile,
.ui-profile__menu { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--ui-sp-3); min-width: 0; }
.ui-profile { margin-top: var(--ui-sp-3); }
.ui-profile > *,
.ui-profile__menu > * { min-width: 0; }

@container (min-width: 56rem) {
  .ui-profile__menu { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--ui-sp-5); }
  .ui-profile .ui-rowcard { min-height: 96px; padding: var(--ui-sp-5); }
  .ui-profile .ui-rowcard__title { font-size: 1.375rem; }
  .ui-profile .ui-icon--sm { width: 56px; height: 56px; }
  .ui-profile .ui-icon--sm > svg { width: 40px; height: 40px; }
}


@container (min-width: 56rem) {
  .ui-notification-item > .ui-card { grid-template-columns: minmax(0, 1fr) minmax(15rem, 20rem); align-items: center; gap: var(--ui-sp-3) var(--ui-sp-6); padding: var(--ui-sp-5); }
  .ui-notification-item .ui-card__head { grid-row: span 2; }
  .ui-notification-item .ui-card__title { font-size: 1.375rem; }
}


.ui-video { display: block; width: 100%; aspect-ratio: 16 / 9; height: auto; border: 2px solid var(--ui-line); border-radius: var(--ui-r-card); background: var(--ui-surface-2); }
.ui-content-list { padding-left: var(--ui-sp-6); color: var(--ui-text); overflow-wrap: anywhere; }
.ui-content-list li + li { margin-top: var(--ui-sp-3); }


.ui-cover { display: block; width: 100%; max-height: 18rem; object-fit: cover; border-radius: var(--ui-r-card); border: 2px solid var(--ui-card-border); }


.ui-details { border: 2px solid var(--ui-card-border); border-radius: var(--ui-r-control); background: var(--ui-surface); padding: var(--ui-sp-3); }
.ui-details summary { min-height: var(--ui-tap); display: flex; align-items: center; color: var(--ui-action-text); font-weight: 700; cursor: pointer; }
.ui-details[open] summary { margin-bottom: var(--ui-sp-3); }
.ui-photo { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: var(--ui-sp-4); color: var(--ui-action-text); }
.ui-file-name { overflow-wrap: anywhere; }


/* Amostras de "A" para os três tamanhos de letra. Seguem as variáveis de tokens.css. */
.ui-font-sample { font-weight: 700; line-height: 1; }
.ui-font-sample--1 { font-size: var(--ui-fs-body); }
.ui-font-sample--2 { font-size: var(--ui-fs-card); }
.ui-font-sample--3 { font-size: var(--ui-fs-title); }


/* O exemplo HTML contém as duas posições do menu; o controlador pode renderizar só uma. */
.ui-tabbar--top { display: none; }
.ui-brand--desktop { display: none; }
@media (min-width: 1100px) {
  .ui-tabbar--top { display: flex; }
  .ui-tabbar--bottom { display: none; }
  .ui-brand--desktop { display: flex; }
}
/* Estados explicitados para a implementação de destino. */
.ui-input:disabled,
.ui-search:has(.ui-search__input:disabled) {
  background: var(--ui-disabled); color: var(--ui-on-disabled);
}
.ui-toggle[aria-disabled="true"] {
  background: var(--ui-disabled); color: var(--ui-on-disabled); cursor: not-allowed;
}
@media (prefers-reduced-motion: reduce) {
  .ui-btn:active { transform: none; }
}
/* Pular para o conteúdo: aparece ao receber foco */
.ui-skip { position: absolute; left: -999px; top: 8px; z-index: 80; display: inline-flex; align-items: center; min-height: var(--ui-tap); padding: 0 var(--ui-sp-4); background: var(--ui-surface); color: var(--ui-action-text); font-weight: 700; }
.ui-skip:focus { left: 8px; }
/* Ícones Phosphor Duotone dentro de texto e de abas */
.ui-tab__pill svg { width: 24px; height: 24px; }
.ui-chip svg, .ui-topbtn svg, .ui-option__check svg { width: 1.125em; height: 1.125em; vertical-align: -.15em; }
/* Altura até 480px (zoom de 400%): tudo o que é fixo rola junto */
@media (max-height: 480px) {
  .ui-topbar, .ui-footer, .ui-tabbar { position: static; }
}
```
