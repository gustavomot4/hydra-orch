### 3.8 Badge de idade

```css
.badge {
  display: inline-block; padding: var(--space-1) var(--space-3);
  background: var(--brand-dark); color: var(--on-brand-dark);   /* 7,44:1 com a marca padrao */
  border-radius: var(--r-md);
  font-size: var(--fs-caption); font-weight: 700; line-height: var(--lh-caption);
}
```
As faixas não se sobrepõem: `4 a 10 anos`, `11 a 14 anos`, `15 anos ou mais`. `--brand-light` não serve de fundo de badge nem de cor de texto.

### 3.9 Acordeão (séries e níveis)

```html
<details class="accordion">
  <summary><span lang="en">Kids</span></summary>
  <div class="accordion__panel">…</div>
</details>
```
```css
.accordion { background: var(--white); border: 1px solid var(--border); border-radius: var(--r-lg); }
.accordion + .accordion { margin-top: var(--space-3); }
.accordion summary {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  min-height: 64px; padding: var(--space-3) var(--space-4);
  border-radius: var(--r-lg); cursor: pointer; list-style: none;
  font-size: var(--fs-item); font-weight: 600; line-height: var(--lh-heading); color: var(--heading); text-transform: uppercase;
}
.accordion summary::-webkit-details-marker { display: none; }
.accordion summary::after {              /* chevron */
  content: ""; flex: none; width: 10px; height: 10px; margin-right: var(--space-1);
  border-right: 2px solid currentColor; border-bottom: 2px solid currentColor;
  transform: translateY(-3px) rotate(45deg); transition: transform var(--t-fast);
}
.accordion[open] summary::after { transform: translateY(2px) rotate(-135deg); }
.accordion summary:focus-visible { outline-offset: -2px; box-shadow: inset 0 0 0 4px var(--heading); }   /* foco por dentro */
.accordion__panel { padding: 0 var(--space-4) var(--space-4); }
```
`<details>` nativo: abre com clique, Enter e Espaço sem JS, e o conteúdo fechado continua no HTML. Vários podem ficar abertos ao mesmo tempo.

### 3.10 Carrossel (hero, cursos, depoimentos)

Todo carrossel do site segue as mesmas regras:

- Setas "Anterior" e "Próximo": `<button>` circular de 44px com `aria-label`, fundo `--white`, ícone `--heading`, sombra `--shadow-card`.
- Bullets: ponto visível de 10px dentro de um `<button>` de 24px; o atual é preenchido e leva `aria-current="true"`, os demais são um anel de 2px. Cor: `--brand-text` sobre fundo claro; `--white` no hero, onde bullets e botão de pausa ficam no canto inferior esquerdo do slide, dentro da área do scrim e 56px (`--space-6`) acima da base, para não ficarem sob a faixa de CTA.
- Autoplay só no hero: 6s por slide, pausa com o ponteiro em cima e com foco dentro, e um botão "Pausar"/"Retomar" de 44px sempre visível, com a receita das setas. Cursos e depoimentos não andam sozinhos.
- Slides fora da vista levam `inert`. O contêiner tem `aria-roledescription="carousel"` e um rótulo; cada slide tem `role="group"`, `aria-roledescription="slide"` e `aria-label="2 de 4"`.
- Com `prefers-reduced-motion: reduce` o autoplay nasce desligado (§6).
