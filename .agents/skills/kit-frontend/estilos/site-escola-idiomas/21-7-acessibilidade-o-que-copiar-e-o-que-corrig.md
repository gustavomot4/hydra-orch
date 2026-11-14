## 7. Acessibilidade — o que copiar e o que corrigir

Piso: WCAG 2.2 AA.

**Copie:**
- `aria-label` descritivo em todo link cujo único texto visível é genérico (`aria-label="{título do post}. Continuar lendo"`, `aria-label="Saiba mais: {assunto}"`) e em todo botão só de ícone (`aria-label="Próximo campo"`, "Abrir menu", "Abrir chat"). Quando o link já contém o nome do destino, como o tile de curso, não precisa.
- `<nav aria-label="Cursos">`, `<nav aria-label="Sobre nós">` — nomeie cada bloco de navegação.
- **Widget de Libras** (VLibras) na posição padrão do plugin, no meio da borda direita. Recomendado em site educacional brasileiro; não substitui a conformidade com a WCAG. Aparece ao chegar, sem depender de clique.
- Alvos de 44px nos botões e campos; nenhum alvo com menos de 24px.

**Semântica:**
- `<html lang="pt-BR">`. Palavra ou trecho em outro idioma leva `lang`: `<span lang="en">Kids</span>`.
- Landmarks `<header>`, `<main id="conteudo">` e `<footer>`. O primeiro elemento focável da página é o skip link "Pular para o conteúdo".
- Um `<h1>` por página. Seções em `<section aria-labelledby>` com `<h2>`; títulos de card e de bloco em `<h3>`; itens em `<h4>`.
- Ação na página é `<button>` (Acesso, acordeão, bullets, seta do formulário, hambúrguer); navegação é `<a>`.
- Datas em `<time datetime>`. `<title>` único por página.

**Foco:**
- Uma regra só, a do §1: anel branco de 2px colado ao elemento e anel `--heading` de 2px por fora. Nunca `outline: none`, nunca anel só na cor da marca (sobre a própria marca ele dá 1,00:1).
- Um dos dois anéis sempre contrasta: o branco passa de 3:1 em todo fundo de luminância até 0,30 e o escuro em todo fundo acima de 0,10; as duas faixas se sobrepõem. Os fundos do guia estão na tabela abaixo.
- Onde o contêiner recorta (tile de curso, acordeão), o anel é desenhado por dentro (§3.2, §3.9).
- Foco não encoberto: o header fixo, a barra das conversões e a cookie bar entram no `scroll-padding` do §1.

**Cor nunca é o único sinal:** erro = borda + ícone + texto; passo do stepper = check ou número + peso do rótulo; item atual da navegação = peso 700 + `aria-current`; link em texto corrido = cor + sublinhado; bullet atual = preenchido contra anel.

**Contraste** dos pares que este guia prescreve, com a marca padrão (`--brand: #d71920`). Calculado pela fórmula de luminância relativa da WCAG; cores com alfa foram compostas sobre o fundo antes do cálculo. Ao trocar a marca, refaça as linhas que têm token `--brand*` (§1.1).

| Par | Texto | Fundo | Razão | Passa 4,5 | Passa 3,0 |
|---|---|---|---|---|---|
| Corpo e placeholder (`--paragraph`) sobre `--white` | `#666666` | `#ffffff` | 5,74:1 | sim | sim |
| Corpo sobre `--bg-gray` (também campo e botão desabilitados) | `#666666` | `#f2f3ef` | 5,15:1 | sim | sim |
| Corpo e placeholder sobre `--brand-tint` | `#666666` | `#fdf1f2` | 5,21:1 | sim | sim |
| Títulos (`--heading`) sobre `--white` (também botões da cookie bar e hover da pílula fantasma) | `#04000b` | `#ffffff` | 20,79:1 | sim | sim |
| Títulos sobre `--bg-gray` | `#04000b` | `#f2f3ef` | 18,66:1 | sim | sim |
| Títulos sobre `--brand-tint` | `#04000b` | `#fdf1f2` | 18,85:1 | sim | sim |
| H2 (`--brand-deep`) sobre `--white` | `#5a0b0d` | `#ffffff` | 14,11:1 | sim | sim |
| H2 sobre `--bg-gray` | `#5a0b0d` | `#f2f3ef` | 12,66:1 | sim | sim |
| H2 sobre `--brand-tint` | `#5a0b0d` | `#fdf1f2` | 12,79:1 | sim | sim |
| `--brand-text` sobre `--white` (tag, rótulo ativo, asterisco, contador, pílula branca) | `#d71920` | `#ffffff` | 5,19:1 | sim | sim |
| `--brand-text` sobre `--bg-gray` | `#d71920` | `#f2f3ef` | 4,65:1 | sim | sim |
| `--brand-text` sobre `--brand-tint` | `#d71920` | `#fdf1f2` | 4,70:1 | sim | sim |
| `--brand-text-dark` sobre `--white` (links, botão outline) | `#aa1419` | `#ffffff` | 7,44:1 | sim | sim |
| `--brand-text-dark` sobre `--bg-gray` | `#aa1419` | `#f2f3ef` | 6,67:1 | sim | sim |
| `--brand-text-dark` sobre `--brand-tint` (também o ícone no círculo) | `#aa1419` | `#fdf1f2` | 6,74:1 | sim | sim |
| `--on-brand` sobre `--brand` (botão primário, faixa de CTA e seu asterisco, hero de unidades) | `#ffffff` | `#d71920` | 5,19:1 | sim | sim |
| `--on-brand-dark` sobre `--brand-dark` (footer, hover de botão, badge) | `#ffffff` | `#aa1419` | 7,44:1 | sim | sim |
| `--white` sobre `--brand-deep` (botão pressionado) | `#ffffff` | `#5a0b0d` | 14,11:1 | sim | sim |
| Texto de campo (`--input-text`) sobre `--white` | `#212529` | `#ffffff` | 15,43:1 | sim | sim |
| Texto de campo sobre `--brand-tint` (busca do header) | `#212529` | `#fdf1f2` | 13,99:1 | sim | sim |
| Erro (`--danger`) sobre `--white` | `#b3261e` | `#ffffff` | 6,54:1 | sim | sim |
| Erro sobre `--bg-gray` | `#b3261e` | `#f2f3ef` | 5,86:1 | sim | sim |
| Erro sobre `--brand-tint` | `#b3261e` | `#fdf1f2` | 5,93:1 | sim | sim |
| Sucesso (`--success`) sobre `--white` | `#1b6e3a` | `#ffffff` | 6,29:1 | sim | sim |
| Sucesso sobre `--bg-gray` | `#1b6e3a` | `#f2f3ef` | 5,64:1 | sim | sim |
| Sucesso sobre `--brand-tint` | `#1b6e3a` | `#fdf1f2` | 5,70:1 | sim | sim |
| Cookie bar: `--white` sobre `--dark` | `#ffffff` | `#0e0f11` | 19,18:1 | sim | sim |
| Hero abaixo de 768px: `--white` sobre foto branca com scrim de 0,6 (pior caso) | `#ffffff` | `#666666` | 5,74:1 | sim | sim |
| Hero a partir de 768px: `--white` sobre foto branca com scrim de 0,55 (pior caso, na borda da área de texto) | `#ffffff` | `#737373` | 4,74:1 | sim | sim |
| Tile: `--white` sobre foto branca com overlay de 0,55 (pior caso, a meia altura) | `#ffffff` | `#737373` | 4,74:1 | sim | sim |
| Borda de campo (`--border-input`) sobre `--white` | `#6c757d` | `#ffffff` | 4,69:1 | sim | sim |
| Borda de campo sobre `--bg-gray` | `#6c757d` | `#f2f3ef` | 4,21:1 | não (é borda: vale 3,0) | sim |
| Borda de campo sobre `--brand-tint` (busca do header) | `#6c757d` | `#fdf1f2` | 4,25:1 | não (é borda: vale 3,0) | sim |
| Foco: anel `--heading` sobre `--white` | `#04000b` | `#ffffff` | 20,79:1 | sim | sim |
| Foco: anel `--heading` sobre `--bg-gray` | `#04000b` | `#f2f3ef` | 18,66:1 | sim | sim |
| Foco: anel `--heading` sobre `--brand-tint` | `#04000b` | `#fdf1f2` | 18,85:1 | sim | sim |
| Foco: anel `--white` sobre `--brand` | `#ffffff` | `#d71920` | 5,19:1 | sim | sim |
| Foco: anel `--white` sobre `--brand-dark` | `#ffffff` | `#aa1419` | 7,44:1 | sim | sim |
| Foco: anel `--white` sobre `--dark` | `#ffffff` | `#0e0f11` | 19,18:1 | sim | sim |
| Foco: anel `--white` sobre foto com scrim de 0,55 (pior caso) | `#ffffff` | `#737373` | 4,74:1 | sim | sim |

Não recebem texto: `--brand-light` (branco sobre ela dá 4,55:1 com a marca padrão, sem folga, e cai abaixo de 4,5 com outras marcas) e `--border` (1,30:1 sobre branco; é só divisória).

**Corrija no seu projeto (falhas que o autor viu no site analisado, por inspeção de fora; não foram verificadas por terceiros):**
- Imagens sem `loading="lazy"` e com `alt="Slide 3"` (sem valor semântico). Use `alt` descritivo ou `alt=""` se decorativo; `lazy` em tudo abaixo da dobra, menos na imagem do hero; `width` e `height` em todas.
- Logo com largura nativa de 797px renderizado a 102px — sirva imagens no tamanho certo (`srcset` + WebP/AVIF).
- `!important` espalhado no CSS de botões. Com tokens você não precisa disso.
- Garanta foco visível de teclado em todos os interativos: o anel duplo do §1, não um anel na cor da marca.

---
