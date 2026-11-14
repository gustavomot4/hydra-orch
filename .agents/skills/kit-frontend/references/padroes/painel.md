# Painel

**Quando:** a tela que abre o dia ou resume uma operação. É onde mais aparecem reclamações de poluição e de cara de IA. (G02, G03)

## Regra

- **Responda a uma pergunta.** Antes de desenhar, escreva qual decisão a pessoa toma ao abrir. "Quem vem agora?" muda o layout inteiro em relação a "Quanto faturei?".
- **Herói é o que muda os próximos minutos**, não o número mais impressionante. Ele fica no topo, sem precisar de cartão.
- **Só o que vira ação.** Para cada indicador, escreva a ação que ele dispara. Sem ação, sai. Até 4 indicadores por visão.
- **Indicador:** rótulo, número e uma comparação quando houver, com o período explícito. A definição fica a um toque de distância; não vira parágrafo no cartão. Conflito conhecido: o `sistema-gestao` manda escrever a definição no cartão, o que já gerou reclamação de excesso de texto. Prevalece esta regra.
- **Pendências com atalho:** "23 sem confirmação" abre a lista já filtrada.
- **Sem repetir** o mesmo dado em cartão, gráfico e tabela.
- **Desconhecido não é zero.** Valor ausente aparece como ausente e fica fora da soma.

## Gráfico (G14)

- Título é a resposta: "Entradas superaram as saídas em 4 de 6 meses", não "Fluxo de caixa".
- Rótulo direto na série em vez de legenda. No máximo 2 séries sem pedido explícito.
- Eixo começando em zero em barras. Sem 3D, sem sombra, sem linha suavizada escondendo dado.
- Duas cores que se distinguem em tons de cinza, com posição ou padrão como segundo sinal.
- Alternativa em tabela, pois nem todo mundo lê gráfico. Sem altura artificial para o zero.

## Fugindo do painel genérico

Evite a fórmula de barra escura, quatro cartões e gráfico de área. Alternativas reais, que saem do trabalho:

- Painel que é uma lista: "o dia de hoje" no lugar de resumo.
- Painel que é uma frase: "Faltam 3 confirmações para fechar a manhã", seguida da lista delas.
- Faixa densa de números em linha, sem cartões, separados por espaço.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| Linear | Densidade sem sobrecarga: hierarquia por peso e contraste, menos separadores e ícones |
| Stripe | Número com comparação e período claros (observação) |
| Apple | Subtração: elementos que não servem à tarefa saem |

**Verifique:** `g-muito-texto`, `g-acoes-demais`, `ia-cards-iguais`. Faça o teste dos 5 segundos.
