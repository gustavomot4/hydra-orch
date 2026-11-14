# Lista e tabela

**Quando:** qualquer conjunto de registros que a pessoa percorre, compara ou opera.

## Regra

- **Sempre diga o que é cada dado:** `<table>` com `<th scope="col">`, cabeçalho visível e legenda oculta. Abaixo de 600px vira lista de cartões, com cada valor acompanhado do nome. (G12)
- **Densidade por tipo de uso.** Linha de 40px para uso diário denso, 48px como padrão de sistema, 56 a 64px quando a linha tem duas linhas de texto. O cabeçalho tem a mesma altura das linhas. No toque, nunca abaixo de 44px.
- **Alinhamento.** Número e moeda à direita, com `tabular-nums`. Texto à esquerda. Data no formato de sempre.
- **Busca e filtros acima, paginação abaixo, sempre à vista.** A paginação fica no rodapé da tabela. Mostre a faixa e o total: "21–40 de 134". (G10)
- **Filtro e busca mudam a URL** (exceto dado pessoal) e voltam à página 1. Voltar do detalhe devolve à mesma página.
- **Ordem padrão declarada.** Coluna ordenável usa botão no cabeçalho com `aria-sort`. O ícone aparece na coluna ativa.
- **Ações na linha:** até 2 visíveis, com nome completo para leitor de tela ("Editar Marina Teles"). O resto em "Mais ações". Nada aparece só no hover: no toque, hover não existe.
- **Ação em lote:** barra no topo da tabela só com itens selecionados, com contagem e cancelar. Nesse modo, as ações de linha ficam desativadas.
- **Colunas demais:** corte a que não muda decisão. Só depois considere truncar, e o texto completo precisa estar no detalhe.
- **Sem cabeçalho quando vazia:** o estado vazio substitui a tabela inteira (`references/padroes/estados.md`).
- **Carregando:** esqueleto nas linhas, nunca spinner no lugar da tabela.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| Carbon (IBM) | Cinco alturas de linha (24, 32, 40, 48, 64px), cabeçalho igual à linha, paginação no rodapé, barra de lote no topo |
| Polaris (Shopify) | Filtros e abas de visão acima da lista, busca junto, ação em massa contextual (conhecimento geral) |
| Linear | Densidade alta sem ruído: hierarquia por peso e contraste, poucos separadores |
| Stripe | Número alinhado, filtro por chips, linha inteira abre o detalhe (observação) |

## Erros comuns

Tabela alta com a paginação fora da tela; ação revelada só no hover; rolagem horizontal em tabela de dados no celular; linha clicável sem link de verdade; texto pequeno para caber mais (compacte com espaçamento, não com fonte).

**Verifique:** `g-tabela-sem-cabecalho`, `g-lista-sem-paginacao`, `a11y-rolagem-horizontal`.
