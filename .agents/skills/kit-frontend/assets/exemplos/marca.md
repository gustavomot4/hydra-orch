# Marca: Marmitaria da Cida

**Brief:** completo

<!-- Exemplo fictício, com o nível de decisão esperado. Não copie o conteúdo. A direção escolhida para este produto no teste do kit foi a de lista e detalhe: docs/testes/2026-10-30-teste-cego/, no repositório do kit. -->

## Essência

- **Promessa, em uma frase:** nenhum pedido se perde entre o WhatsApp e a sacola.
- **Por que existe:** na hora do almoço, a dona copia 60 pedidos para o caderno com pressa, e pedido anotado errado é cliente perdido.
- **O que nunca seria:** um sistema de gestão, com relatório e painel para aprender a usar.

## Público e personas

### Cida, a dona

- **Base:** hipótese, a partir de uma frase de quem pediu o sistema
- **Objetivo:** anotar rápido e saber o que falta sair, e com quem
- **Medo:** esquecer um pedido ou mandar a marmita errada
- **Contexto de uso:** celular numa mão só, às vezes suja, entre as 10h e as 14h; um computador velho no balcão
- **Familiaridade com tecnologia:** WhatsApp e Pix. Nada além disso
- **Como validar:** acompanhar uma hora de almoço e pedir para ela anotar três pedidos na tela

### Cláudio, o entregador

- **Base:** hipótese
- **Objetivo:** saber quais pedidos levar e quanto cobrar de cada um
- **Medo:** cobrar errado ou faltar troco
- **Contexto de uso:** não usa o sistema; recebe a lista pela Cida
- **Familiaridade com tecnologia:** WhatsApp e mapa
- **Como validar:** perguntar a ele o que faltou na última entrega

## Concorrentes

Neste exemplo fictício, são categorias. Num projeto real, abra as telas de cada um.

| Quem | Cor e fonte | Tom | O que faz bem | Situação |
| --- | --- | --- | --- | --- |
| Caderno de pauta | Papel e caneta | O dela | Abre na hora, não trava, não tem o que aprender | Descrito por quem pediu |
| WhatsApp | Verde, lista de conversas | Pessoal | Ela já sabe usar; é onde os pedidos chegam | Observado |
| Sistema de pedidos típico | Barra escura e muitos números | Técnico | Relatórios e cardápio completo | Não verificado |

**Espaço livre:** tão simples quanto o caderno, mas que não perde pedido e separa por entregador sozinho.

## Personalidade

- **Prática**, não apressada: resolve em poucos toques, sem gritar urgência.
- **Caseira**, não improvisada: tem o jeito do balcão, e funciona sem falhar.
- **Direta**, não seca: fala como a Cida fala, sem palavra de sistema.

### Tom

| Formal ou casual | Sério ou engraçado | Respeitoso ou irreverente | Neutro ou entusiasmado |
| --- | --- | --- | --- |
| Casual | Sério, sem ser duro: dinheiro e comida | Respeitoso | Neutro |

## Mensagem e voz

- **Em 5 segundos, a pessoa precisa sentir:** está tudo anotado.
- **E lembrar:** o que falta sair, e com quem.

### Frases

- Botão: "Anotar pedido"
- Vazio: "Nenhum pedido ainda. Quando chegar o primeiro, anote aqui."
- Erro: "Não deu para salvar. O pedido continua aqui: tente de novo."
- Sucesso: "Pedido 38 anotado."

## O que isso muda na tela

| Do brief | Decisão de design |
| --- | --- |
| Uma mão só, às vezes suja | Alvos de 48px, ação principal ao alcance do polegar |
| Só conhece WhatsApp | Lista e detalhe como uma conversa; sem painel de indicadores |
| Separa por entregador no caderno | Filtro por entregador, com contagem, sempre à vista |
| Pedido errado é cliente perdido | "Sem entregador" é o único aviso em destaque |
| Computador velho | CSS sem recurso novo; fonte servida pelo projeto, com poucos pesos |
| Fala como no balcão | "Fazendo, Pronto, Na rua": nunca "status" nem "em processamento" |
