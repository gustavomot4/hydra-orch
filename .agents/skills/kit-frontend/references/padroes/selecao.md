# Escolher entre opções

Escolha o controle pelo tamanho da lista e por quanto ela pode crescer. (G11)

| Situação | Controle |
| --- | --- |
| 2 opções, liga e desliga, efeito imediato | Interruptor |
| 2 a 5 opções, escolha única | Botões de opção ou cartões, todos visíveis |
| 2 a 5 opções, várias escolhas | Caixas de marcar |
| 6 a 12 opções fixas, que não crescem | Lista suspensa nativa |
| Dado de cadastro que cresce (paciente, serviço, cidade) | Busca com sugestões |
| Mais de 50 itens, ou homônimos | Diálogo de busca, com dados que distinguem |
| Filtros de uma lista | Chips, até 6; acima disso, busca |

## Busca com sugestões

- Rótulo visível. Ao focar, abre as sugestões mais usadas.
- Ignora maiúsculas, acentos e pontuação. Procura no nome e nos identificadores.
- Digitar não muda a escolha; só escolher um resultado muda. Esc mantém a anterior.
- Até 8 sugestões, e diga quando há mais: "Mostrando 8 de 23".
- Sem resultado: diga isso e ofereça criar, quando fizer sentido.
- Homônimos: mostre o que distingue (nascimento, 4 últimos dígitos do telefone). Nunca o CPF completo.
- Teclado: setas navegam, Enter escolhe, Esc fecha. `role="combobox"` e `listbox`, conforme o WAI-ARIA Authoring Practices. Use uma base testada em vez de escrever à mão.

## Erros comuns

Dropdown com centenas de itens; lista que corta no celular; ícone sem rótulo como opção; escolha múltipla que perde a seleção ao filtrar.

**Verifique:** `g-lista-suspensa-longa`.
