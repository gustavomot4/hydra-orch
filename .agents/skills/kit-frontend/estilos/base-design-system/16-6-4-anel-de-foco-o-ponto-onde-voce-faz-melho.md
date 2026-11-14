### 6.4 Anel de foco — o ponto onde você faz melhor que a Apple

A Apple usa um `outline` de 4px na cor de destaque a 60%. Composto sobre branco
isso dá **2,27:1** com `rgba(0, 125, 250, .6)` e **2,46:1** com o azul de botão,
`rgba(0, 113, 227, .6)`. Nos dois casos **reprova na WCAG 1.4.11**, que exige
3:1 para indicador não-textual.

**Use o acento em opacidade cheia:**

```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card:focus-visible { outline-offset: 3px; }
.toast :focus-visible { outline-color: var(--surface); }   /* sobre tinta o acento dá 1,65:1 */
```

- `outline`, não `box-shadow`: acompanha o raio, não disputa com as sombras do
  componente e continua visível em `forced-colors`. Nenhum dos dois escapa de um
  ancestral com `overflow: hidden` — contêiner que recorta precisa de **4px ou
  mais de folga interna** em volta de qualquer controle.
- Offset de 3px no cartão focável, para o anel não encostar na sombra.
- Linha de tabela não recebe `tabindex`: o foco vai no link da primeira célula
  (ver Tabela).
- Só em `:focus-visible`, nunca em `:focus` — senão o anel aparece no clique de
  mouse.

---
