## 3. Componentes — receitas prontas

### 3.1 Botões (três formas, só isso: primário, outline e pílula)

As receitas valem igual em `<a>` e em `<button>`. O foco vem da regra global do §1.

```css
/* comum às três formas */
.btn-primary, .btn-outline, .btn-pill {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
  min-height: 44px;                       /* alvo de toque */
  font: inherit; font-size: var(--fs-caption); font-weight: 700; line-height: var(--lh-heading);
  text-align: center; text-decoration: none; cursor: pointer;
  transition: background-color var(--t-fast), color var(--t-fast), border-color var(--t-fast);
}

/* PRIMARIO — a acao da pagina */
.btn-primary, .btn-outline { padding: 10px 20px; border: 1px solid; border-radius: var(--r-sm); }
.btn-primary       { background: var(--brand); color: var(--on-brand); border-color: var(--brand); }
.btn-primary:hover { background: var(--brand-dark); color: var(--on-brand-dark); border-color: var(--brand-dark); }

/* SECUNDARIO / OUTLINE — acao alternativa, mesmo peso visual, menos urgencia */
.btn-outline       { background: var(--white); color: var(--brand-text-dark); border-color: var(--brand-text-dark); }
.btn-outline:hover { background: var(--brand-dark); color: var(--on-brand-dark); border-color: var(--brand-dark); }

/* PILULA — CTA de hero e de faixa colorida. Sempre em caixa alta. */
.btn-pill {
  width: 100%; padding: 15px var(--space-4);          /* celular: largura total, o rotulo pode quebrar */
  border: 2px solid; border-radius: var(--r-full);
  text-transform: uppercase;
}
@media (min-width: 576px) {
  .btn-pill { width: auto; padding-inline: var(--space-5); white-space: nowrap; }
}
/* solida da marca: a conversao, sobre foto */
.btn-pill--brand            { background: var(--brand); color: var(--on-brand); border-color: var(--brand); }
.btn-pill--brand:hover      { background: var(--brand-dark); color: var(--on-brand-dark); border-color: var(--brand-dark); }
/* branca solida: a conversao, sobre fundo da marca -> vaza para transparente no hover */
.btn-pill--on-brand         { background: var(--white); color: var(--brand-text); border-color: var(--white); }
.btn-pill--on-brand:hover   { background: transparent; color: inherit; border-color: currentColor; }
/* fantasma: a acao de baixo compromisso. Herda a cor do texto do bloco (hero ou faixa) */
.btn-pill--ghost            { background: transparent; color: inherit; border-color: currentColor; }
.btn-pill--ghost:hover      { background: var(--white); color: var(--heading); border-color: var(--white); }

/* pressionado e desabilitado, nas tres formas (por ultimo, para valer sobre o hover) */
.btn-primary:active, .btn-outline:active, .btn-pill:active {
  background: var(--brand-deep); color: var(--white); border-color: var(--brand-deep);
}
.btn-primary:disabled, .btn-outline:disabled, .btn-pill:disabled,
.btn-primary[aria-disabled="true"], .btn-outline[aria-disabled="true"], .btn-pill[aria-disabled="true"] {
  background: var(--bg-gray); color: var(--paragraph); border-color: var(--border); cursor: not-allowed;
}
```

**Padrão de par de CTA:** a ação de baixo compromisso à esquerda ("Fazer teste de nível", com ícone de seta) e a de conversão à direita ("Fazer pré-matrícula"), em todo par do site: no hero, nos depoimentos, na barra das conversões, no wizard ("Voltar" + "Continuar") e no resultado do teste. Sobre foto ou fundo da marca, a da esquerda é *fantasma* e a da direita é *sólida*.

| Fundo do bloco | Cor do texto do bloco | Par |
|---|---|---|
| foto com scrim (hero da home) | `color: var(--white)` | `.btn-pill--ghost` + `.btn-pill--brand` |
| ilustração em tons da marca com scrim (hero de curso) | `color: var(--white)` | `.btn-pill--ghost` + `.btn-pill--on-brand` |
| `--brand` liso (hero de unidades, faixa de CTA) | `color: var(--on-brand)` | `.btn-pill--ghost` + `.btn-pill--on-brand` |

A pílula fantasma e o hover da pílula branca herdam a cor do texto do bloco; por isso o bloco precisa declará-la. Fora de hero e faixa, use `.btn-primary` e `.btn-outline`; nunca misture pílula e botão de raio 6px no mesmo par.
