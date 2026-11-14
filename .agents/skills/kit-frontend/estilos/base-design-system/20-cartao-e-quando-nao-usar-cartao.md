### Cartão — e quando NÃO usar cartão

O modelo **inverte** conforme a superfície:

| Superfície | Cartão |
| --- | --- |
| Vitrine (página de marketing) | **não existe** — raio 0, fundo transparente, sem sombra. O conteúdo se sustenta sozinho no espaço. |
| Fluxo | `--surface`, raio 12px, `--shadow-card`, padding 24px, **sem borda** |
| Ferramenta (painel, listagem, loja) | página `--paper`, cartão `--surface`, raio 18px, `--shadow-card`, **sem borda**. Padding 24 / 20 / 16px (5.4); 16px entre o cabeçalho e o conteúdo |

Enfiar cartão em página de marketing é o erro mais comum de quem "aplica um
design system" numa landing.

### Mídia

Imagem ou captura do produto. Raio 28px · proporção fixa por `aspect-ratio`:
**16:10** quando ocupa a largura do contêiner, **4:3** dentro de célula de
grade · fundo `--sunken` quando é ilustração ou enquanto a imagem carrega · sem
texto sobreposto, sem gradiente. Superfície desenhada dentro dela: `--surface`,
raio 18px.

Mídia não é faixa de capítulo (5.7): é conteúdo, fica dentro do contêiner e por
isso tem raio. `alt` descreve o que a imagem mostra; a puramente decorativa leva
`alt=""`.

### Ícone

Só quando substitui uma palavra dentro de um controle (fechar, buscar, abrir
menu) — nunca ao lado de um rótulo que já nomeia. 16px junto de texto de 14px,
20px junto de texto de 17px · traço de 1,5px em `currentColor`, sem
preenchimento. `aria-hidden="true"` no ícone e o nome no controle
(`aria-label`). Botão só de ícone: caixa de 32px, alvo pelo `::after` de 6.3.

Sem logotipo fornecido, a marca é o nome em texto, 17px peso 600, `--ink`. Não
desenhe um logotipo.

### Navegação lateral

Largura 264px · fundo `--sunken` · padding interno **8px** · item de
`--h-controle` (32px) com raio 6px e padding lateral 10px · gap de 2px · texto
14px `--ink` · hover = `--fill` · selecionado = `--fill` + peso 600 +
`aria-current="page"`. Rótulo de grupo: 12px, peso 600, `--ink-2`, padding
lateral 10px.

Em ≤734px a lateral sai do lado do conteúdo e vira gaveta, aberta por um botão
"Menu" na barra; a gaveta segue a semântica do Modal.

⚠️ **A pílula não existe sem o respiro de 8px.** Com padding lateral cheio sai um
retângulo colado nas duas bordas — pior que não arredondar.

**Semântica e teclado:** `<nav aria-label="…">` com `<ul>`; cada item é um
`<a>`; Tab percorre na ordem visual.

### Barra translúcida

```css
.bar { position: sticky; top: 0; z-index: 10; min-height: 48px; background: var(--paper); }
@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .bar {
    background: color-mix(in srgb, var(--paper) 80%, transparent);
    -webkit-backdrop-filter: saturate(1.8) blur(20px);
    backdrop-filter: saturate(1.8) blur(20px);
  }
}
html { scroll-padding-top: 48px; }   /* o foco não fica escondido atrás da barra */
```

O fundo translúcido só entra onde o navegador desfoca; sem `backdrop-filter` a
barra fica sólida. 48px de altura, `sticky`, sem borda inferior. Marca à
esquerda, links de 14px. Texto na barra é sempre `--ink`: com conteúdo escuro
rolando por baixo, `--ink-2` cai a 3,48:1.

A **saturação** é o que impede o fundo de virar cinza morto atrás do vidro — não
use só `blur`.

⚠️ **Critério mecânico: use `backdrop-filter` só onde há conteúdo rolando por
baixo.** Sobre um fundo chapado ele não produz efeito nenhum e ainda força uma
camada de composição. Sim no topo de uma página com herói; sim numa barra fixa
sobre tabela rolando; **não** numa barra sobre fundo liso.

⚠️ **Duas barras nunca ficam fixas ao mesmo tempo.** Se existe uma barra
secundária (contexto, produto, filtros), a global solta e só a secundária gruda.
