### 3.3 Card de conteúdo / blog

```css
.card {
  background: var(--white); border-radius: var(--r-lg); overflow: hidden;
  box-shadow: var(--shadow-card);
  transition: box-shadow var(--t-base), transform var(--t-base);
}
.card:hover { box-shadow: var(--shadow-hover); transform: translateY(-4px); }
.card--static:hover { box-shadow: var(--shadow-card); transform: none; }   /* card que nao e clicavel inteiro */
.card__img   { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; }
.card__body  { display: grid; gap: var(--space-2); padding: var(--space-4); }
.card__meta  { font-size: var(--fs-caption); line-height: var(--lh-caption); color: var(--paragraph); }   /* "28 de agosto de 2026" */
.card__tag   { font-size: var(--fs-caption); line-height: var(--lh-caption); font-weight: 700; color: var(--brand-text); text-transform: uppercase; }   /* "Dicas" */
.card__title { margin: 0; font-size: var(--fs-item); font-weight: 600; line-height: var(--lh-snug); color: var(--heading); }
.card__link  { justify-self: start; padding-block: var(--space-2); font-size: var(--fs-caption); line-height: var(--lh-caption); font-weight: 700; color: var(--brand-text-dark); }   /* "Continuar lendo" */
```
Ordem visual do card de blog: **imagem → data → categoria → título → "Continuar lendo"**. Sem resumo/excerpt — o título carrega tudo.

- A data vai em `<time datetime="2026-08-28">28 de agosto de 2026</time>`. O título é um `<h3>`.
- "Continuar lendo" é o único link do card e leva `aria-label="{título do post}. Continuar lendo"`. Com o padding ele mede 36px de altura (o mínimo da WCAG 2.2 para alvo é 24px).
- Imagem em 16:10, card com padding de 24px (`--space-4`). A sombra fica visível sobre branco e sobre `--bg-gray`.

### 3.4 Faixa de CTA (newsletter/lead)

O autor aponta este componente como o principal ponto de captação do site analisado (observação, sem dados de conversão). É um card largo, na cor da marca, com raio `--r-xl`, da mesma largura do conteúdo do `.container`. Na home ele fica sobreposto entre o hero e a primeira seção.

```css
.cta-band {
  /* mesma largura util do .container: nunca encosta na borda da tela */
  width: min(100% - 2 * var(--container-pad), var(--container) - 2 * var(--container-pad));
  margin-inline: auto;
  display: flex; flex-direction: column; gap: var(--space-4);
  padding: var(--space-4) var(--container-pad);
  background: var(--brand); color: var(--on-brand);
  border-radius: var(--r-xl);
}
.cta-band h2 { margin: 0; font-size: var(--fs-cta); font-weight: 700; line-height: var(--lh-heading); text-transform: uppercase; color: inherit; }
.cta-band p a { color: inherit; }  /* link do consentimento: o link da marca (§1) some sobre a propria marca */
.cta-band--overlap { position: relative; z-index: 2; margin-top: -40px; }   /* so na home: invade o hero */
@media (min-width: 768px) {
  .cta-band { flex-direction: row; align-items: center; justify-content: space-between; }
}
```
Título curto e imperativo, que diz o que a pessoa vai receber: **"Receba dicas e novidades da escola"** (a caixa alta vem do CSS). A mesma faixa, sem `--overlap` e com uma pílula no lugar do formulário, fecha a página de curso (§5.3).
