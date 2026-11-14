### 1.1 Como trocar a marca

Defina `--brand`. As quatro variantes saem dela por `color-mix()` e não são editadas. Depois calcule quatro contrastes com a fórmula de luminância relativa da WCAG e ajuste os tokens de texto:

| Confira | Se der menos de 4,5:1 |
|---|---|
| `#ffffff` sobre `--brand` | `--on-brand: var(--heading);` |
| `#ffffff` sobre `--brand-dark` | `--on-brand-dark: var(--heading);` |
| `--brand` sobre `--bg-gray` e sobre `--brand-tint` | `--brand-text: var(--brand-dark);` e, se `--brand-dark` também reprovar, `var(--brand-deep)` |
| `--brand-dark` sobre `--bg-gray` e sobre `--brand-tint` | `--brand-text-dark: var(--brand-deep);` |

Com a marca padrão (`#d71920`) nenhum ajuste é necessário: 5,19 · 7,44 · 4,65 e 4,70 · 6,67 e 6,74. A regra foi conferida por cálculo com outras doze cores de marca (amarelo `#ffd400`, ciano `#00bcd4`, laranja `#f57c00`, verde `#2eab5b`, azul `#1565c0`, roxo `#6a1b9a`, entre outras): aplicados os ajustes, todos os pares da tabela do §7 ficam em 4,5:1 ou mais. `--brand-deep` e branco sobre `--brand-deep` passam com qualquer `--brand`.

Nenhuma receita deste documento escreve a cor da marca nem `#fff` sobre ela: tudo passa pelos tokens acima. Não crie um vermelho de erro a partir da marca; erro é `--danger`.

### 1.2 Equivalente Tailwind (`tailwind.config.js`)

O config não repete valores: cada chave aponta para o token do `:root` acima e usa o mesmo nome. O bloco de tokens continua sendo o único lugar onde um valor é escrito.

```js
/** tailwind.config.js (formato do Tailwind v3) */
module.exports = {
  content: ['./src/**/*.{html,js,jsx,ts,tsx,astro}'],
  theme: {
    screens: { sm: '576px', md: '768px', xl: '1200px' },   // os três breakpoints do §4, e só eles
    extend: {
      colors: {
        brand: {
          DEFAULT: 'var(--brand)', dark: 'var(--brand-dark)', deep: 'var(--brand-deep)',
          light: 'var(--brand-light)', tint: 'var(--brand-tint)',
          text: 'var(--brand-text)', 'text-dark': 'var(--brand-text-dark)',
        },
        'on-brand':   { DEFAULT: 'var(--on-brand)', dark: 'var(--on-brand-dark)' },
        heading:      'var(--heading)',
        paragraph:    'var(--paragraph)',
        'input-text': 'var(--input-text)',
        dark:         'var(--dark)',
        white:        'var(--white)',
        'bg-gray':    'var(--bg-gray)',
        border:       { DEFAULT: 'var(--border)', input: 'var(--border-input)' },
        danger:       'var(--danger)',
        success:      'var(--success)',
      },
      fontFamily: { sans: ['Montserrat', 'system-ui', '-apple-system', 'sans-serif'] },
      fontSize: {
        caption:    ['var(--fs-caption)',  'var(--lh-caption)'],
        ui:         ['var(--fs-ui)',       '1.5'],
        body:       ['var(--fs-body)',     'var(--lh-body)'],     // corpo = 17px/1.7, não 16
        'body-lg':  ['var(--fs-body-lg)',  'var(--lh-lead)'],
        item:       ['var(--fs-item)',     'var(--lh-heading)'],
        card:       ['var(--fs-card)',     'var(--lh-heading)'],
        'hero-sub': ['var(--fs-hero-sub)', 'var(--lh-snug)'],
        cta:        ['var(--fs-cta)',      'var(--lh-heading)'],
        section:    ['var(--fs-section)',  'var(--lh-heading)'],
        hero:       ['var(--fs-hero)',     'var(--lh-tight)'],
      },
      spacing: {
        'section-pt': 'var(--section-pt)', 'section-pb': 'var(--section-pb)', 'section-tight': 'var(--section-tight)',
        'heading-mb': 'var(--heading-mb)', 'container-pad': 'var(--container-pad)', 'grid-gap': 'var(--grid-gap)',
        'header-h': 'var(--header-h)', 'cta-bar-h': 'var(--cta-bar-h)',
      },
      borderRadius: { sm: 'var(--r-sm)', md: 'var(--r-md)', lg: 'var(--r-lg)', xl: 'var(--r-xl)', full: 'var(--r-full)' },
      maxWidth:     { container: 'var(--container)' },
      boxShadow:    { card: 'var(--shadow-card)', hover: 'var(--shadow-hover)', brand: 'var(--shadow-brand)' },
    },
  },
};
```

- A escala `--space-1` a `--space-6` coincide com os passos `1`, `2`, `4`, `6`, `10` e `14` da escala padrão do Tailwind; não precisa de chave própria.
- Transições usam o token direto: `[transition:background-color_var(--t-fast)]`.
- No Tailwind v4 a configuração é feita em CSS (`@theme`); o mapa é o mesmo, chave por chave. O bloco acima não foi testado em build nesta revisão.

---
