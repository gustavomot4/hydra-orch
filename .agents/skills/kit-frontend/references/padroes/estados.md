# Carregando, vazio e erro

Toda tela com dados tem os três, mais o sucesso. São a parte que mais falta em entrega de agente, e por isso entram no aceite da tela-modelo.

## Carregando

- Esqueleto com o formato do conteúdo real, parado com movimento reduzido.
- Reserve o espaço para a tela não pular.
- Passou de 1 segundo, diga em texto com `role="status"`.
- Em botão: mantém o texto e a largura, com `aria-busy`.

## Vazio

Identifique qual dos três é, porque pedem texto diferente:

| Tipo | Quando | O que dizer |
| --- | --- | --- |
| Sem dados | Primeiro uso | O que vai aparecer aqui e como começar. Uma ação principal |
| Resultado da pessoa | Busca ou filtro sem resultado | Por que está vazio e como ajustar. Mantenha busca e filtros |
| Erro de acesso | Sem permissão, configuração faltando | Por que não há dados e o que fazer, sem código |
| Tudo feito | Lista zerada | Uma frase positiva. Sem próxima ação, sem texto extra |

Regras: substitua a tabela inteira, sem cabeçalho vazio. Título curto, uma frase. Nunca deixe sem saída quando existe próximo passo. Nada de ilustração genérica de pasta vazia, que é outro clichê: sem imagem é melhor do que imagem de banco.

## Erro de leitura

Mantenha a casca e o menu. No lugar do conteúdo: o que aconteceu, "Tentar de novo" e os dados já carregados, quando existirem. `role="alert"`.

## Erro de gravação

Fica junto da ação. Nada do que foi digitado se perde. Foco no aviso. Repetir não duplica.

## Sem acesso e endereço inexistente

Mesma casca, título que explica e "Voltar para o início". Sem código 403 nem 404 na tela.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| Carbon | Tipos de estado vazio, uma só ação principal por estado, substituir o elemento, imagem opcional, esqueleto em vez de spinner |
| Atlassian | Causa, o que fazer e o que acontece se não fizer; se não sabe a causa, não invente |

**Como provar:** deixe na tela de desenvolvimento um jeito de forçar cada estado. Capture cada um na tela-modelo.
