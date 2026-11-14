### JSON (design tokens)

```json
{
  "color": {
    "paper": "#FAF9F7", "surface": "#FFFFFF", "sunken": "#F4F2EC",
    "fill": "rgba(118, 114, 106, 0.12)", "fill2": "rgba(118, 114, 106, 0.18)",
    "line": "#E8E4DC",
    "ink": "#1C1B19", "ink2": "#6B6862", "ink3": "#827E76",
    "accent": "#1F4E8C", "accentHover": "#2A5B9C", "accentActive": "#183F73",
    "danger": "#8E2C26", "dangerHover": "#9C332C", "dangerActive": "#7A2520",
    "onAccent": "#FFFFFF"
  },
  "font": {
    "family": ["Inter", "system-ui", "sans-serif"],
    "size": [12, 14, 17, 21, 28, 40, 48, 56],
    "weight": [400, 600],
    "tracking": { "12": "-0.005em", "14": "-0.008em", "17": "-0.011em", "21": "0",
                  "28": "0", "40": "0", "48": "-0.003em", "56": "-0.005em" },
    "lineHeight": { "titulo": "1em + 4px", "corpo": "1em + 8px", "denso": "1em + 6px", "botao": "1em + 3px" }
  },
  "radius": [6, 8, 12, 18, 28, "50%", 980],
  "shadow": {
    "card": "2px 4px 12px 0 rgba(0, 0, 0, 0.08)",
    "control": "0 1px 2px 0 rgba(0, 0, 0, 0.18)",
    "modal": "0 16px 48px 0 rgba(0, 0, 0, 0.18)"
  },
  "space": [4, 8, 12, 16, 20, 24, 32, 40],
  "height": { "grande": 44, "medio": 36, "botao": 32, "controle": 32, "linha": 36, "toque": 44 },
  "target": { "pointerFine": 28, "pointerCoarse": 44 },
  "layout": { "shell": 1024, "conteudo": 980, "prosa": 692, "fluxo": 560, "gutter": 22,
              "breakpoints": { "smMax": 734, "mdMax": 1068 } },
  "motion": { "fast": 150, "base": 280, "screen": 320, "ease": "cubic-bezier(0.28, 0.11, 0.32, 1)" }
}
```

### Tailwind

Tailwind 3. Tudo em `theme`, **fora de `extend`**: `extend` soma ao padrão e
deixaria `md`, `text-3xl`, `rounded-2xl`, `font-bold` e `shadow-md` disponíveis.
O display responsivo é `text-40 sm:text-48 lg:text-56 font-semibold`; cada
tamanho já traz o seu tracking.

```js
// tailwind.config.js
module.exports = {
  theme: {
    screens: { sm: '735px', lg: '1069px' },
    colors: {
      transparent: 'transparent', current: 'currentColor',
      paper: '#FAF9F7', surface: '#FFFFFF', sunken: '#F4F2EC',
      fill: { DEFAULT: 'rgba(118, 114, 106, 0.12)', 2: 'rgba(118, 114, 106, 0.18)' },
      line: '#E8E4DC',
      ink: { DEFAULT: '#1C1B19', 2: '#6B6862', 3: '#827E76' },
      accent: { DEFAULT: '#1F4E8C', hover: '#2A5B9C', active: '#183F73' },
      danger: { DEFAULT: '#8E2C26', hover: '#9C332C', active: '#7A2520' },
      'on-accent': '#FFFFFF'
    },
    fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
    fontWeight: { normal: '400', semibold: '600' },
    fontSize: {
      12: ['0.75rem',   { lineHeight: 'calc(1em + 6px)', letterSpacing: '-0.005em' }],
      14: ['0.875rem',  { lineHeight: 'calc(1em + 6px)', letterSpacing: '-0.008em' }],
      17: ['1.0625rem', { lineHeight: 'calc(1em + 8px)', letterSpacing: '-0.011em' }],
      21: ['1.3125rem', { lineHeight: 'calc(1em + 4px)', letterSpacing: '0' }],
      28: ['1.75rem',   { lineHeight: 'calc(1em + 4px)', letterSpacing: '0' }],
      40: ['2.5rem',    { lineHeight: 'calc(1em + 4px)', letterSpacing: '0' }],
      48: ['3rem',      { lineHeight: 'calc(1em + 4px)', letterSpacing: '-0.003em' }],
      56: ['3.5rem',    { lineHeight: 'calc(1em + 4px)', letterSpacing: '-0.005em' }]
    },
    lineHeight: { titulo: 'calc(1em + 4px)', corpo: 'calc(1em + 8px)',
                  denso: 'calc(1em + 6px)', botao: 'calc(1em + 3px)' },
    borderRadius: { none: '0', 6: '6px', 8: '8px', 12: '12px', 18: '18px', 28: '28px',
                    pill: '980px', full: '50%' },
    boxShadow: { none: 'none',
                 card: '2px 4px 12px 0 rgba(0, 0, 0, 0.08)',
                 control: '0 1px 2px 0 rgba(0, 0, 0, 0.18)',
                 modal: '0 16px 48px 0 rgba(0, 0, 0, 0.18)' },
    spacing: { 0: '0px', 1: '4px', 2: '8px', 3: '12px', 4: '16px', 5: '20px',
               6: '24px', 8: '32px', 10: '40px', gutter: '22px' },
    maxWidth: { shell: '1024px', prosa: '692px', fluxo: '560px' },
    transitionDuration: { fast: '150ms', base: '280ms', screen: '320ms' },
    transitionTimingFunction: { DEFAULT: 'cubic-bezier(0.28, 0.11, 0.32, 1)' }
  }
}
```

Tailwind 4 não lê `tailwind.config.js` por padrão: o mesmo conteúdo vai em
`@theme`, e `--namespace-*: initial` apaga o padrão do grupo. Duração e curva
ficam nas variáveis de `:root` do CSS acima.

```css
@import "tailwindcss";
@theme {
  --breakpoint-*: initial;  --breakpoint-sm: 735px;  --breakpoint-lg: 1069px;
  --color-*: initial;
  --color-paper: #FAF9F7;  --color-surface: #FFFFFF;  --color-sunken: #F4F2EC;
  --color-fill: rgba(118, 114, 106, 0.12);  --color-fill-2: rgba(118, 114, 106, 0.18);
  --color-line: #E8E4DC;
  --color-ink: #1C1B19;  --color-ink-2: #6B6862;  --color-ink-3: #827E76;
  --color-accent: #1F4E8C;  --color-accent-hover: #2A5B9C;  --color-accent-active: #183F73;
  --color-danger: #8E2C26;  --color-danger-hover: #9C332C;  --color-danger-active: #7A2520;
  --color-on-accent: #FFFFFF;
  --font-sans: Inter, system-ui, sans-serif;
  --font-weight-*: initial;  --font-weight-normal: 400;  --font-weight-semibold: 600;
  --text-*: initial;
  --text-12: 0.75rem;    --text-12--line-height: calc(1em + 6px);  --text-12--letter-spacing: -0.005em;
  --text-14: 0.875rem;   --text-14--line-height: calc(1em + 6px);  --text-14--letter-spacing: -0.008em;
  --text-17: 1.0625rem;  --text-17--line-height: calc(1em + 8px);  --text-17--letter-spacing: -0.011em;
  --text-21: 1.3125rem;  --text-21--line-height: calc(1em + 4px);  --text-21--letter-spacing: 0;
  --text-28: 1.75rem;    --text-28--line-height: calc(1em + 4px);  --text-28--letter-spacing: 0;
  --text-40: 2.5rem;     --text-40--line-height: calc(1em + 4px);  --text-40--letter-spacing: 0;
  --text-48: 3rem;       --text-48--line-height: calc(1em + 4px);  --text-48--letter-spacing: -0.003em;
  --text-56: 3.5rem;     --text-56--line-height: calc(1em + 4px);  --text-56--letter-spacing: -0.005em;
  --leading-*: initial;  --leading-titulo: calc(1em + 4px);  --leading-corpo: calc(1em + 8px);
  --leading-denso: calc(1em + 6px);  --leading-botao: calc(1em + 3px);
  --radius-*: initial;  --radius-6: 6px;  --radius-8: 8px;  --radius-12: 12px;  --radius-18: 18px;
  --radius-28: 28px;  --radius-pill: 980px;  --radius-full: 50%;
  --shadow-*: initial;
  --shadow-card: 2px 4px 12px 0 rgba(0, 0, 0, 0.08);
  --shadow-control: 0 1px 2px 0 rgba(0, 0, 0, 0.18);
  --shadow-modal: 0 16px 48px 0 rgba(0, 0, 0, 0.18);
}
```

No v4 o espaçamento aceita qualquer inteiro (`p-7`): use só 1, 2, 3, 4, 5, 6, 8
e 10, que dão a escala de 5.8.

Duas proibições valem nos dois: nada de `bg-[#1F4E8C]` no HTML (cor sempre pelo
token) e nada de valor arbitrário de raio, sombra, tamanho de fonte ou
espaçamento fora da escala (`rounded-[10px]`, `shadow-[…]`, `text-[15px]`).
