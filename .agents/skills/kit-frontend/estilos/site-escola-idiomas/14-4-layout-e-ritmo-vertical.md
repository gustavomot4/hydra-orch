## 4. Layout e ritmo vertical

```css
.container { max-width: var(--container); margin-inline: auto; padding-inline: var(--container-pad); }
.section   { padding-block: var(--section-pt) var(--section-pb); }   /* 60/60; 100/120 a partir de 768px, pelos tokens */
.section--tint  { background: var(--brand-tint); }   /* secao destacada */
.section--gray  { background: var(--bg-gray); }      /* alternancia */
.section--tight { padding-block: var(--section-tight); }
.section__title { margin: 0 0 var(--heading-mb); font-size: var(--fs-section); font-weight: 700; color: var(--brand-deep); text-align: left; }

.grid-cards { display: grid; grid-template-columns: 1fr; gap: var(--grid-gap); }
.split      { display: grid; grid-template-columns: 1fr; gap: var(--grid-gap); align-items: center; }   /* imagem | texto */
@media (min-width: 768px) {
  .grid-cards { grid-template-columns: repeat(2, 1fr); }
  .split      { grid-template-columns: 1fr 1fr; gap: var(--space-6); }
}
@media (min-width: 1200px) {
  .grid-cards    { grid-template-columns: repeat(3, 1fr); }
  .grid-cards--4 { grid-template-columns: repeat(4, 1fr); }   /* modalidades */
}
```

O `.container` não tem media query: o respiro lateral muda pelo token `--container-pad`. Quando o H2 está dentro de uma coluna de texto (`.split`), a margem abaixo dele é `var(--space-4)`, não `--heading-mb`: os 40/60px valem para o título que ocupa a largura da seção.

**Ritmo de alternância de fundo** (evita a monotonia do branco infinito): cada seção tem o fundo indicado na coluna "Fundo" das tabelas do §5.2 e do §5.3. São três fundos, `--white`, `--brand-tint` e `--bg-gray`, e nunca dois coloridos iguais em sequência. Se, ao cortar seções, sobrarem dois fundos iguais vizinhos, o segundo vira `--white` (ou `--bg-gray`, se os dois forem brancos).

**Grades:**
- Cursos: faixa de tiles encostados, sem gap e sem raio (§3.2).
- Cards de blog / recursos / depoimentos / unidades: `.grid-cards`, 1 coluna → 2 a partir de 768px → 3 a partir de 1200px, com `gap: var(--grid-gap)` (32px).
- Modalidades: `.grid-cards.grid-cards--4`, 1 → 2 → 4 colunas.
- Diferenciais/prêmios, sobre e viagens: `.split`, 2 colunas a partir de 768px (imagem | texto ou lista de itens com ícone).

**Breakpoints:** três, sempre `min-width`: `576`, `768` e `1200`. O site analisado usa também `992` e `1400`; este guia não precisa deles.

**Altura até 480px: tudo o que é fixo rola junto.** É a única regra que não é de largura. O zoom de 400% num monitor de 1280 × 1024 dá uma janela de 320 × 256; ali o header (64px), a barra das conversões (56px) e a cookie bar (76 a 148px) juntos cobrem a janela inteira e a pessoa não vê conteúdo. Com a janela de até 480px de altura, header, barra das conversões, cookie bar, bolha de chat e botão de Libras deixam de ser fixos e viram itens do fluxo da página (a barra, a cookie bar e os dois botões ficam no fim dela), e o espaço reservado para eles some.

```css
@media (max-height: 480px) {
  html { scroll-padding-top: 0; scroll-padding-bottom: 0; }
  body { padding-bottom: 0; }
  .site-header, .cta-bar, .cookie-bar, .chat-bubble, .libras { position: static; }
  .cookie-bar, .cookie-bar__inner { height: auto; }
  .chat-bubble { margin: var(--space-3) 24px 24px auto; }
  .libras { margin-left: auto; transform: none; }
}
```

| A partir de | O que muda |
|---|---|
| base | 1 coluna em tudo; pílulas com largura total; tiles de curso 1,2 por tela; faixa de CTA empilhada; hero com scrim uniforme; stepper vertical; header de 64px e barra fixa das conversões |
| 576px | pílulas com a largura do rótulo, lado a lado |
| 768px | seções com 100/120px e `--container-pad` de 35px; `.grid-cards` em 2 colunas; `.split` em 2 colunas; tiles 2 por tela; faixa de CTA na horizontal; hero com o texto nos 55% da esquerda; stepper horizontal; footer em colunas |
| 1200px | header de duas faixas (143px), sem barra fixa; `.grid-cards` em 3 colunas (modalidades em 4); tiles 4 por tela; hero em coverflow |

---
