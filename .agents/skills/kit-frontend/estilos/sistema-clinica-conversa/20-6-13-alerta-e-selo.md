### 6.13 Alerta e selo

- **Alerta:** `display: flex; align-items: center`, espaço `--space-14`, `padding: var(--space-14) var(--space-18)`, raio `--radius-box`, `--text-ui`. Fundo `--<tom>-soft`, texto `--<tom>` (`--destructive` no tom de perigo), borda `--line` `color-mix(in srgb, currentColor 25%, transparent)`. Ícone `--icon` num círculo de 38 px com fundo `color-mix(in srgb, currentColor 12%, transparent)`: `info`, `check-check`, `triangle-alert` ou `octagon-alert`. Título opcional em `--weight-bold`; ação opcional à direita. Perigo usa `role="alert"`; os outros, `role="status"`. Abaixo de 600 px, a ação desce e ocupa a largura.
- **Selo:** altura 28 px, `padding: 0 var(--space-10)`, raio `--radius-full`, `--text-caption` `--weight-semibold`, ícone `--icon-sm` opcional. Tons: neutro (`--muted` com `--muted-foreground`), `primary`, `success`, `warning`, `info` e perigo, cada um com o `-soft` de fundo.

### 6.14 Diálogo de confirmação

Só para ação que não se desfaz (cancelar consulta, marcar falta, descartar alterações). Modal.

- Véu `--overlay`, aparece em `--duration-base`. Caixa centralizada, largura `min(var(--overlay-width), calc(100vw - 32px))`, fundo `--card`, raio `--radius-xl`, `padding: var(--space-24)`, `--shadow-lg`, espaço `--space-12`; entra subindo 4% da própria altura com opacidade de 0 a 1 em `--duration-base`.
- Título em `--text-title` `--weight-extrabold`, como pergunta: "Cancelar esta consulta?". Texto em `--text-body` `--muted-foreground` com a consequência: "A consulta cancelada não pode ser reaberta. Para atender o paciente, será preciso agendar de novo."
- Botões à direita, espaço `--space-10`: "Voltar" (`secondary`) e a ação com verbo e objeto, "Cancelar consulta" ou "Marcar falta" (`dark`; `primary` quando a ação não é destrutiva). Abaixo de 480 px, os dois dividem a largura.
- O foco abre em "Voltar". Esc e "Voltar" fecham sem fazer nada. Enquanto salva, o botão da ação fica em carregando.

### 6.15 Faixa de dias, etapas, cartão e indicador

**Faixa de dias** (`<nav aria-label="Dias da semana">`): os 7 dias da semana atual, de segunda a domingo, cada um um link com `flex: 1 0 58px`, largura máxima 72 px, altura 66 px, raio `--radius-box`, fundo `--card`, borda `--line` `--border`; dia da semana abreviado em `--text-caption` `--weight-semibold` `--muted-foreground` e número em `--text-heading` `--weight-bold`. Hover: borda `--border-strong`. Hoje: fundo e borda `--primary`, número `--primary-foreground`, dia da semana `--on-primary-muted`, `aria-current="date"`. Os outros dias abrem a agenda na visão Dia daquela data. Sem espaço, a faixa rola na horizontal.

**Etapas da consulta** (`<ol aria-label="Etapas da consulta">`): as quatro etapas do 4.3 lado a lado, com a legenda "Situação: **Confirmado** · Próximo: **iniciar atendimento**" acima, em `--text-small` `--muted-foreground`.

- Cada etapa: círculo de 26 px e o rótulo embaixo em `--text-caption` `--weight-semibold`, ligados por uma linha de 2 px na altura do centro do círculo.
- Pendente: círculo com fundo `--background` e borda 2 px `--border`, rótulo `--muted-foreground`, linha `--border`.
- Feita (a atual e as anteriores): círculo `--primary` com `check` `--icon-xs` em `--primary-foreground`, rótulo `--foreground`, linha `--primary`. A atual leva `aria-current="step"`.
- Próxima: círculo com fundo `--card`, borda 2 px tracejada `--primary` e halo `0 0 0 4px var(--primary-soft)`, rótulo `--primary` `--weight-extrabold`, e o texto oculto " (próximo passo)".

**Cartão:** fundo `--card`, borda `--line` `--border`, raio `--radius-lg`, `padding: var(--space-20) var(--space-24)` (`--space-16` abaixo de 768 px). Cabeçalho opcional com `h2` em `--text-section` `--weight-extrabold` e uma ação à direita, margem inferior `--space-14`.

**Indicador:** cartão com `padding: var(--space-18) var(--space-20)` e espaço `--space-4`. Ícone `--icon` num quadrado de 40 px, raio `--radius-md`, com as cores do selo do tom; rótulo em `--text-ui` `--weight-semibold` `--muted-foreground`; valor em `--text-display-sm` `--weight-extrabold` `--tracking-display`, números tabulares; dica em `--text-small` `--muted-foreground`. Em destaque (um por tela, o saldo): fundo e borda `--primary`, valor `--primary-foreground`, rótulo e dica `--on-primary-muted`, quadrado do ícone `--on-dark-fill` com ícone `--on-dark`. Abaixo de 600 px: `padding: var(--space-14)`, quadrado de 34 px, valor em `--text-heading` sem quebra de linha.
