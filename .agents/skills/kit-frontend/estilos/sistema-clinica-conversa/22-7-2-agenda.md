### 7.2 Agenda

Grade de tempo: horas no eixo vertical, dias no horizontal, cada consulta um cartão com a altura da duração do procedimento.

**Cabeçalho:** título "Agenda" e subtítulo com o período e o total ("26 de outubro a 1 de novembro · 65 consultas"; na visão Dia, "Hoje, 28 de outubro"). Ações, nesta ordem: "Período anterior" (botão de ícone `secondary`, `chevron-left`), "Hoje" (`secondary`), "Próximo período" (`chevron-right`), o segmentado de visão e "Agendar consulta" (`primary`, `plus`; botão flutuante abaixo de 1100 px).

**Visões:**

| Visão | Colunas | Quando |
| --- | --- | --- |
| Semana (padrão a partir de 900 px) | 7 dias, de segunda a domingo | Só a partir de 900 px |
| 3 dias | O dia escolhido e os 2 seguintes | Só abaixo de 900 px; substitui Semana |
| Dia (padrão abaixo de 900 px) | A partir de 900 px, uma coluna por profissional; abaixo, uma coluna só | Sempre |
| Mês | Calendário de 7 colunas com a contagem por dia | Sempre |

Visão, data, profissional e consulta aberta ficam no endereço: `?ver=semana&data=2026-10-28&profissional=3&consulta=812`.

**Abaixo do cabeçalho:** chips por profissional com contagem e, à direita, a legenda das situações (4.3), que some abaixo de 1280 px e desce para a linha de baixo quando não couber (com a coluna de detalhe aberta, por exemplo). Depois, o cartão "Próximo" (6.6) quando o período mostrado inclui hoje e há próximo paciente; compacto abaixo de 900 px.

**Grade:**

```css
.grid { --axis: 58px; --hour: 80px; display: flex; flex-direction: column; min-width: 0; overflow: hidden;
  background: var(--card); border: var(--line) solid var(--border); border-radius: var(--radius-lg); }
.grid-head, .grid-canvas { display: grid; grid-template-columns: var(--axis) repeat(var(--columns), minmax(0, 1fr)); }
.grid-head { border-bottom: var(--line) solid var(--border); }
.grid-col-head { display: flex; align-items: center; gap: var(--space-10); min-width: 0; padding: var(--space-10) var(--space-12); border-left: var(--line) solid var(--border); }
.grid-col-head b { display: block; font-size: var(--text-body); font-weight: var(--weight-extrabold); }
.grid-col-head small { display: block; font-size: var(--text-caption); font-weight: var(--weight-semibold); color: var(--muted-foreground); }
.grid-col-head[data-today] { background: var(--primary-soft); }
.grid-col-head[data-today] b, .grid-col-head[data-today] small { color: var(--primary); }
.grid-col-head[data-past] b { color: var(--muted-foreground); }
.grid-body { flex: 1 1 auto; min-height: calc(var(--hour) * 3); overflow-y: auto; overscroll-behavior: contain; }
.grid-canvas { position: relative; }
.grid-hours { position: relative; }
.grid-hours span { position: absolute; right: var(--space-10); transform: translateY(-50%); font-size: var(--text-micro);
  font-weight: var(--weight-bold); color: var(--muted-foreground); font-variant-numeric: tabular-nums; }
.grid-hours span:first-child { transform: none; top: var(--space-4) !important; }
.grid-column { position: relative; border-left: var(--line) solid var(--border);
  background-image: repeating-linear-gradient(to bottom,
    var(--border) 0, var(--border) 1px, transparent 1px, transparent calc(var(--hour) / 2),
    var(--grid-half) calc(var(--hour) / 2), var(--grid-half) calc(var(--hour) / 2 + 1px), transparent calc(var(--hour) / 2 + 1px), transparent var(--hour)); }
.grid-column[data-today] { background-color: var(--today-column); }
.grid-column[data-past], .grid-column[data-empty] { background-color: var(--card-soft); }
.grid-empty { position: absolute; top: var(--space-16); left: 0; right: 0; text-align: center;
  font-size: var(--text-caption); font-weight: var(--weight-semibold); color: var(--muted-foreground); }
@media (max-width: 899px) {
  .grid { --axis: 46px; --hour: 68px; }
  .grid-col-head { justify-content: center; text-align: center; padding: var(--space-8) var(--space-4); }
  .grid-hours span { right: var(--space-6); }
}
```

- **Altura:** sem número fixo. A página da Agenda tem a altura da janela abaixo da barra superior (`<main class="agenda-main">`, com o `padding` da casca dentro da altura) e a coluna da esquerda (`.agenda-col`) é uma coluna `flex`: cabeçalho, chips e cartão "Próximo" têm a altura que têm, a grade ocupa o que sobra (`flex: 1 1 auto; min-height: 0`) e só o corpo da grade rola (`.grid-body`, `flex: 1 1 auto; overflow-y: auto`), com o piso de 3 horas (`calc(var(--hour) * 3)`). Se o que está acima da grade deixar menos que o piso, a página rola.

```css
.agenda-main { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); gap: var(--space-24); height: calc(100dvh - var(--topbar)); }
.agenda-col { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.agenda-col > .grid { flex: 1 1 auto; min-height: 0; }
.agenda-col .page-actions { margin-left: auto; }
.filters-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-12) var(--space-20); margin-bottom: var(--space-14); }
.filters-row .legend { margin-left: auto; }
.agenda-detail { min-height: 0; }
.agenda-detail .detail-head { display: flex; align-items: center; justify-content: space-between; padding: var(--space-18) var(--space-24) var(--space-4); }
.agenda-detail .detail-body { padding-top: var(--space-10); }
@media (min-width: 1280px) { .agenda-main[data-panel] { grid-template-columns: minmax(0, 1fr) var(--overlay-width); } }
@media (max-width: 1099px) { .agenda-main { height: calc(100dvh - var(--topbar-mobile)); } }
```

- **Consulta aberta:** a partir de 1280 px, clicar num cartão abre o detalhe numa coluna própria: o `<main class="agenda-main" data-panel>` ganha a segunda coluna, `<aside class="detail-column agenda-detail">` com cabeçalho "CONSULTA" e fechar, corpo e rodapé do 6.8, e a grade encolhe para caber ao lado. Nada fica coberto: nem as colunas da grade, nem a legenda, nem as ações do cabeçalho, nem o menu da conta. Fechar (botão ou Esc) tira o `data-panel` e a grade volta à largura inteira. Abaixo de 1280 px o detalhe abre como painel (900 a 1279 px) ou folha (abaixo de 900 px), por cima da página e com véu. Com a coluna aberta cada dia fica mais estreito (≈119 px a 1440 px, contra ≈188 px); por isso o conteúdo dos cartões acompanha a largura (ver "Conteúdo pelo espaço"), e o cabeçalho e a linha dos chips quebram em duas linhas quando preciso.

- **Montagem:** o elemento `.grid` recebe o número de colunas em `--columns` (por exemplo, `style="--columns: 7"`); dentro de `.grid-body`, o `.grid-canvas` tem altura `(fim − início da janela) / 60 × --hour`, com `.grid-hours` na primeira coluna e uma `.grid-column` por dia ou profissional.
- **Janela de horas:** de 7 h às 19 h, ampliada até a hora cheia anterior à primeira consulta ou posterior à última. Um rótulo por hora no eixo ("08:00"); linha `--border` na hora cheia e `--grid-half` na meia hora.
- **Cabeçalho da coluna:** "Seg 26" e, embaixo, "Hoje · 14 consultas" ou "12 consultas". Na visão Dia por profissional: iniciais `sm`, nome e "Ortodontia · 6 consultas". Dia passado com o título em `--muted-foreground` e a coluna em `--card-soft`; dia sem consulta com a coluna em `--card-soft` e "Sem consultas" no topo (`.grid-empty`).
- **Rolagem inicial:** 1 hora antes de agora quando hoje está na tela; senão, meia hora antes da primeira consulta. Só rola de novo quando o período muda.

**Cartão da consulta** (um `<button>` posicionado na coluna):

```css
.slot { --fg: var(--status-confirmado-fg); --bg: var(--status-confirmado-bg); --bar: var(--status-confirmado-bar);
  position: absolute; z-index: 1; display: flex; flex-direction: column; gap: 1px; overflow: hidden; text-align: left;
  padding: var(--space-4) var(--space-6) var(--space-4) var(--space-10); border: var(--line) solid var(--slot-edge);
  border-radius: var(--radius-sm); background-color: var(--bg); color: var(--foreground);
  font-size: var(--text-micro); line-height: var(--leading-card); }
.slot::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--bar); }
.slot:hover { filter: brightness(.97); z-index: 2; }
.slot:focus-visible { outline-offset: 1px; z-index: 3; }
.slot[aria-current="true"] { box-shadow: var(--shadow-selected); z-index: 3; }
.slot .time { display: flex; align-items: center; gap: var(--space-4); font-weight: var(--weight-bold); color: var(--fg); font-variant-numeric: tabular-nums; white-space: nowrap; }
.slot .time svg { width: var(--icon-xs); height: var(--icon-xs); stroke-width: 2.6; margin-left: auto; flex: none; }
.slot .name { font-size: var(--text-caption); font-weight: var(--weight-bold); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slot .detail, .slot .who { color: var(--muted-foreground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slot .who { display: flex; align-items: center; gap: var(--space-4); margin-top: auto; font-weight: var(--weight-semibold); }
.slot.one-line { flex-direction: row; align-items: center; gap: var(--space-4); }
.slot.one-line .time { flex: none; }
.slot.one-line .name { flex: 1 1 auto; min-width: 0; }
.slot { container-type: inline-size; }
@container (width < 86px) { .slot .to { display: none; } }
@container (width < 50px) { .slot .at { display: none; } }
@container (width < 150px) { .slot.one-line .to { display: none; } }
@container (width < 114px) { .slot.one-line .at { display: none; } }
@container (width < 38px) { .slot.packed .name { display: none; } }
.slot[data-status="agendado"] { --fg: var(--status-agendado-fg); --bg: var(--status-agendado-bg); border: var(--line-control) dashed var(--status-agendado-bar); }
.slot[data-status="agendado"]::before { display: none; }
.slot[data-status="atendimento"] { --fg: var(--status-atendimento-fg); --bg: var(--status-atendimento-bg); --bar: var(--status-atendimento-bar); color: var(--status-atendimento-fg); box-shadow: var(--shadow-live); }
.slot[data-status="atendimento"] .detail, .slot[data-status="atendimento"] .who { color: var(--status-atendimento-muted); }
.slot[data-status="concluido"] { --fg: var(--status-concluido-fg); --bg: var(--status-concluido-bg); --bar: var(--status-concluido-bar); }
.slot[data-status="concluido"] .name { color: var(--status-concluido-fg); }
.slot[data-status="cancelado"] { --fg: var(--status-cancelado-fg); --bg: var(--status-cancelado-bg); --bar: var(--status-cancelado-bar); background-image: var(--hatch); }
.slot[data-status="cancelado"] .name { color: var(--muted-foreground); text-decoration: line-through; }
.slot[data-status="faltou"] { --fg: var(--status-faltou-fg); --bg: var(--status-faltou-bg); --bar: var(--status-faltou-bar); background-image: var(--hatch); }
```

- **Posição:** `top = (início − início da janela) / 60 × --hour + 1,5 px`; `height = max(duração / 60 × --hour − 3 px, 26 px)`. A duração é a do procedimento; sem ela, 30 minutos.
- **Simultâneas lado a lado:** consultas que se sobrepõem formam um grupo; cada uma vai para a primeira faixa livre do grupo, e o grupo divide a largura em partes iguais: `left: calc(faixa / faixas × 100% + 3px)`, `width: calc(100% / faixas − 6px)`. Com um profissional escolhido no filtro, o cartão ocupa a largura do dia.
- **Conteúdo pelo espaço:** o ícone da situação nunca sai do cartão, porque Confirmado e Concluído têm a mesma forma e sem ele só a cor os separaria. O resto depende das faixas, da largura e da altura do cartão:
  - **1 ou 2 faixas:** nome completo, cortado com reticências depois do ícone; procedimento (`.detail`) com altura de 64 px ou mais; profissional (`.who`, iniciais `xxs` e primeiro nome) com 84 px ou mais e sem filtro de profissional.
  - **3 faixas ou mais** (classe `.packed`): só o ícone e as iniciais do paciente (duas letras, as mesmas do 4.2, em `--text-caption` `--weight-bold`, sem círculo e com `aria-hidden="true"`), sem hora, nome, procedimento nem profissional. Se a largura interna do cartão for menor que 38 px (14 do ícone + 4 de espaço + 20 das iniciais), só o ícone.
  - **Hora**, pela largura interna do cartão (sem borda nem padding), no `.at` (início) e no `.to` (fim, com o travessão): em duas linhas, início e fim ("09:00–09:30") a partir de 86 px, só o início a partir de 50 px, nenhuma abaixo disso; em linha única, 150 px e 114 px, porque o nome precisa do resto. A 1440 px, sem a coluna de detalhe aberta, isso dá início e fim no cartão sozinho, só o início no de duas faixas com duas linhas e nenhuma hora no de duas faixas em linha única.
  - **Linha única:** abaixo de 43 px de altura, hora e nome ficam na mesma linha (`.one-line`): duas linhas pedem 14,64 px (`--text-micro` × `--leading-card`) + 1 px de espaço + 15,86 px (`--text-caption` × `--leading-card`) + 8 px de padding + 3 px de borda tracejada = 42,5 px. O cartão de 30 minutos, com 37 px, é sempre `.one-line`; o de 45 minutos (57 px), não.
- **Nome acessível:** "09:00 às 09:30, Helena Prado, Limpeza, Dra. Lia Moura, Confirmado". Clicar abre o detalhe na coluna ao lado da grade ou, abaixo de 1280 px, no painel (6.8), sem tirar a grade da tela; o cartão aberto leva `aria-current="true"`.

**Agendar num horário livre:** com o mouse sobre um espaço vazio de hoje (a partir de agora) ou de um dia futuro, aparece um cartão fantasma de 30 minutos no horário arredondado para baixo de 15 em 15 minutos: borda `--line-control` tracejada `--primary`, fundo `color-mix(in srgb, var(--primary-soft) 85%, transparent)`, raio `--radius-sm`, "+ 09:30 · Agendar" em `--text-micro` `--weight-bold` `--primary`. Clicar abre o agendamento com dia, hora e profissional preenchidos. Pelo teclado, o caminho é o botão "Agendar consulta"; um texto oculto antes da grade diz isso.

**Linha "agora"** (só quando hoje está na tela e a hora atual cabe na janela, `aria-hidden="true"`, `z-index: 4`, sem receber clique):

- Linha de 2 px atravessando todas as colunas, de `--axis` até a borda direita, em `color-mix(in srgb, var(--accent) 45%, transparent)`, com um ponto de 10 px `--accent` no começo.
- Na coluna de hoje, por cima, uma linha de 3 px em `--accent`.
- No eixo, a hora atual numa etiqueta: fundo `--accent-text`, texto `--on-dark` `--text-micro` `--weight-extrabold`, números tabulares, raio 6 px, `padding: var(--space-2) var(--space-4)`, a 4 px da esquerda.

**Mês:** cabeçalho com "SEG" a "DOM" no estilo de rótulo em maiúsculas (seção 3), `padding: var(--space-10) var(--space-12)`. Cada dia é um `<button>` com altura mínima 104 px (64 px abaixo de 600 px), `padding: var(--space-10) var(--space-12)` (`var(--space-8) var(--space-6)` abaixo de 600 px), bordas superior e esquerda `--line` `--border`, fundo `--card`, hover `--card-soft`. Número do dia em `--text-body` `--weight-bold`; hoje com o número num círculo de 30 px `--primary` e `--primary-foreground`; dia de outro mês com fundo `--card-soft` e número em `--muted-foreground` `--weight-regular`. Dia com consultas mostra um selo `primary` com `calendar-plus` e "6 consultas" (abaixo de 600 px, só o número). Nome acessível "28: 6 consultas". Clicar abre a visão Dia daquela data.

| Estado | O que aparece |
| --- | --- |
| Carregando | Esqueleto de 1 bloco de 480 px no lugar da grade; ao trocar de período, a grade anterior fica até chegar a nova |
| Vazio | A grade, com todas as colunas em "Sem consultas", e o botão de agendar |
| Erro | Erro ao carregar (6.12) no lugar da grade |
