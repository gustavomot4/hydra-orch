## 7. Telas

Toda tela começa pelo cabeçalho do 5.4, com o `h1` que recebe o foco na navegação, e atualiza o título da aba para `<Tela> — <Nome do produto>`. Filtros, visão e página escolhidos ficam no endereço, para voltar ao mesmo lugar e para compartilhar o link.

### 7.1 Hoje

A tela inicial. Responde em segundos: quem vem hoje, quem é o próximo, quem ainda não confirmou.

**Layout.** A partir de 1100 px a tela é uma grade de duas colunas, `grid-template-columns: minmax(0, 1fr) var(--side)` (`--side-narrow` abaixo de 1280 px), espaço `--space-24`, `align-items: start`. A da esquerda (`.today-main`) leva os itens 1 a 5 e a lista; a da direita é o detalhe (item 6), que começa no alto do conteúdo, ao lado do cabeçalho: assim a ação seguinte cabe na primeira dobra de 1440 × 900. Abaixo de 1100 px é uma coluna só e o detalhe some.

1. **Cabeçalho:** "Bom dia, Carla" e o subtítulo "Quarta, 28 de outubro · 14 consultas". Ação: "Agendar consulta" (`primary`, `plus`), que vira o botão flutuante "Agendar" abaixo de 1100 px.
2. **Faixa de dias** (6.15), margem inferior `--space-14`.
3. **Chips por profissional** (6.4): "Todos 14", "Dra. Lia 6", "Dr. Caio 5", "Dra. Bianca 3" (a contagem de "Todos" é a soma das outras). O filtro fica em `?profissional=`.
4. **Cartão "Próximo"** (6.6), só abaixo de 1100 px; acima disso, o detalhe ao lado já abre com o próximo paciente.
5. **Lembrete de confirmação**, só se houver consultas Agendadas: `clock` `--icon` e "4 pacientes ainda não confirmaram" (singular: "1 paciente ainda não confirmou"), `padding: var(--space-12) var(--space-16)`, raio `--radius-box`, fundo `--status-agendado-bg`, texto `--status-agendado-fg` `--text-ui` `--weight-semibold`, margem inferior `--space-14`.
6. **Lista e detalhe:**
   - Lista: 6.5, com a linha "agora" do 6.7, no fim da coluna `.today-main`.
   - Detalhe: `<aside class="detail-column today-detail" aria-label="Consulta selecionada">` com o corpo e o rodapé da receita do 6.8 (as ações secundárias rolam com o corpo; a ação seguinte fica no rodapé, sempre à vista). Abre com o próximo paciente; sem próximo, com a primeira consulta a partir de agora; sem ela, com a primeira do dia. Sem nenhuma, "Escolha uma consulta para ver os detalhes." centralizado em `--muted-foreground`, sem rodapé.
   - Receita da grade e da coluna fixa:

```css
.today { display: grid; grid-template-columns: minmax(0, 1fr) var(--side); gap: var(--space-24); align-items: start; }
.today-main { min-width: 0; }
.today-detail { position: sticky; top: calc(var(--topbar) + var(--space-20)); max-height: calc(100dvh - var(--topbar) - var(--space-40)); }
@media (max-width: 1279px) { .today { grid-template-columns: minmax(0, 1fr) var(--side-narrow); } }
@media (max-width: 1099px) { .today { display: block; } .today-detail { display: none; } }
```

   - Abaixo de 1100 px a coluna lateral some; tocar na consulta abre o detalhe no painel ou na folha (6.8).

| Estado | O que aparece no lugar da lista |
| --- | --- |
| Carregando | Esqueleto de 6 blocos de 64 px |
| Vazio | `calendar-check`, "Nenhuma consulta hoje", "Quando houver consultas para hoje, elas aparecem aqui em ordem de horário." e "Agendar consulta" |
| Filtro sem resultado | A lista vazia do profissional, com o mesmo estado vazio |
| Erro | Erro ao carregar (6.12) |
