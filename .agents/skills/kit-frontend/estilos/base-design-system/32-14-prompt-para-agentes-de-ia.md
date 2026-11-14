## 14. Prompt para agentes de IA

Cole junto com a tarefa quando pedir UI a um assistente de código. O arquivo
`PRD-FRONTEND.md` tem de estar na raiz do projeto (ver "Como usar").

> Siga `PRD-FRONTEND.md`, na raiz deste projeto. Em resumo:
>
> **Subtração antes de decoração** — todo elemento tem que mudar uma decisão do
> usuário; se não muda, não desenhe. Espaço vazio é resultado aceito, desde que a coluna de largura limitada fique centralizada.
>
> **Por tela** (viewports 1440×900 e 390×844): **1 informação herói**, **1 ação
> primária** (ou nenhuma, declarada, em tela de leitura), no máximo 5 blocos de
> informação sem rolar, texto auxiliar de no máximo 1 linha e 60 caracteres.
>
> **Tipografia:** Inter com `opsz`, uma família (no máximo duas, a segunda só
> nos títulos da vitrine); tamanhos só da rampa
> `12·14·17·21·28·40·48·56`, no máximo 4 por tela (o display é 56 em ≥1069px, 48
> em 735–1068px e 40 em ≤734px, e conta como um); line-height por fórmula,
> declarado em cada classe, nunca só no `body`: `calc(1em + 4px)` em título,
> `calc(1em + 8px)` em parágrafo, `calc(1em + 6px)` em tabela, lista, rótulo e
> legenda de 14 e 12, `calc(1em + 3px)` em botão; tracking por tamanho (12
> `-0.005em` · 14 `-0.008em` · 17 `-0.011em` · 21, 28 e 40 `0` · 48 `-0.003em` · 56
> `-0.005em`); **só pesos 400 e 600**; sem caixa alta; `tabular-nums` em toda
> coluna numérica.
>
> **Cor:** neutros + **um** acento, que marca só a ação: no máximo 1
> preenchimento e 3 textos (link, terciário) em `--accent` por viewport. Erro de
> campo, estado crítico e ação destrutiva usam `--danger`, sempre com texto por
> extenso. Status, seleção e categoria se resolvem em peso, posição e
> preenchimento neutro, nunca em matiz nem em `opacity` (a única cor de estado é
> o crítico). `--ink-3` não escreve texto abaixo de 28px. Link dentro de frase
> leva sublinhado permanente. Anel de foco em opacidade cheia.
>
> **Geometria:** escada de raios `6·8·12·18·28·50%·980`, aplicada em *todos* os
> componentes; três sombras, `--shadow-card`, `--shadow-control` e
> `--shadow-modal`, cada uma no seu papel; espaçamento só de
> `4·8·12·16·20·24·32·40`; alvo de 44px em `pointer: coarse` e de 28px com
> ponteiro fino; estilos de hover só dentro de `@media (hover: hover) and
> (pointer: fine)`, e nenhuma ação depende de `hover`.
>
> **Layout:** com `box-sizing: border-box`, conteúdo da vitrine em 980px
> (contêiner 1024 + 22 de padding), parágrafo de até 692px, formulário de fluxo
> em 560px, ferramenta fluida; breakpoints 734 e 1068; texto alinhado à
> esquerda, exceto abertura de capítulo, e coluna de largura limitada centralizada
> na área útil.
>
> **Referência certa:** vitrine ≠ fluxo ≠ ferramenta (seção 10). Não use corpo
> de 17px e botão de 44px numa tabela densa; não use cartão em página de
> marketing.
>
> **Estados e acessibilidade:** vazio, carregando, erro e tudo feito em toda
> tela com dados; botão desabilitado com `aria-disabled` e dizendo o que falta;
> foco visível; semântica e teclado de cada componente (seção 7); WCAG 2.2 AA.
>
> Use os tokens da seção 12 como estão e não invente valor fora deles. Antes de
> entregar, rode o checklist da seção 13 e o script de auditoria, e me diga o
> resultado de cada item e o do teste dos 5 segundos para cada tela.

---
