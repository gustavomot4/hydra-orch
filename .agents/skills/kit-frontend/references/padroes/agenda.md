# Agenda

**Quando:** produto com hora marcada. Vem de dois projetos reais; a grade foi exigência de quem usa.

## Regra

- **Duas visões, sem trocar uma pela outra.** "Hoje" é uma lista de pessoas (familiar, para atender). "Agenda" é uma grade com horas no eixo vertical e dias no horizontal, com o bloco do tamanho da duração (para planejar).
- **Escala fixa:** 80px por hora a partir de 900px de largura. A grade tem rolagem própria, a página não rola, e ela abre no horário atual.
- **Linha "agora"** atravessa toda a grade e é mais forte na coluna de hoje. A hora aparece escrita. Atualiza a cada 30 segundos.
- **Clicar num horário livre** abre o agendamento já com dia, hora e profissional. Pelo teclado, há um botão "Agendar" equivalente. (G15)
- **Situações que não se confundem:** cor, forma, ícone e texto. Exemplo testado: vazado tracejado para agendado, cheio para confirmado, hachurado para cancelado e falta. (G13)
- **Nome acessível completo** no bloco: "sexta 9, 11:00, Helena Prado, limpeza, confirmado".
- **Sobreposição:** blocos lado a lado, até 3. Acima disso, um botão "+N" que lista no painel.
- **Bloco menor que o texto:** mostre menos dias antes de reduzir a fonte. Alvo de pelo menos 24 × 24px; 44 no toque.
- **Abaixo de 900px:** visões Dia, 3 dias e Mês. Padrão: Dia.
- **Detalhe ao lado a partir de 1280px:** a grade encolhe e nada fica coberto. Abaixo disso, painel ou folha inferior.
- **Filtro por profissional** em chips com contagem, até 6; acima disso, busca. Visão, data e filtro ficam na URL.
- **WhatsApp:** abre a conversa com o lembrete pronto e não envia sozinho.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| Google Calendar | Grade de horas e dias, linha do agora, clicar para criar (observação) |
| WhatsApp | Lista de conversas: iniciais, nome em destaque, hora; é o modelo da tela "Hoje" (observação) |
| Uber | Detalhe sobe em folha inferior, com ação clara na parte de baixo (observação) |

Receitas completas em `estilos/sistema-clinica-conversa/` e `estilos/sistema-gestao/`.

**Verifique:** `g-rolagem-presa` (marque a grade com `data-rolagem-propria` quando a página não rola), `a11y-alvo`. Testar com 3 consultas no mesmo horário e com o nome mais longo do cadastro.
