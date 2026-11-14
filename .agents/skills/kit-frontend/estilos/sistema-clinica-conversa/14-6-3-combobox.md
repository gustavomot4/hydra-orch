### 6.3 Combobox

Campo de busca com lista de sugestões, no lugar da lista de seleção quando as opções vêm de um cadastro que cresce (procedimentos; profissionais acima de 6).

- **Campo:** o mesmo do 6.2, com `search` à esquerda e, quando há escolha, botão `x` à direita com `aria-label="Limpar <nome>"`. Ao receber foco, seleciona o texto e abre a lista.
- **Lista:** `position: absolute; top: calc(100% + 6px)`, largura do campo, `padding: var(--space-4)`, fundo `--card`, borda `--line` `--border`, raio `--radius-box`, `--shadow`, `z-index: var(--z-popup)`; altura máxima 312 px com rolagem.
- **Opção:** altura mínima `--target`, `padding: var(--space-8) var(--space-10)`, raio `--radius-md`, espaço `--space-10`. Iniciais `xs` opcionais; nome em `--text-ui` `--weight-semibold` com reticências; detalhe à direita em `--text-small` `--muted-foreground` com números tabulares; a opção já escolhida leva `check` `--icon-md` em `--primary`. Abaixo de 600 px, o detalhe desce para a linha de baixo.
- **Opção ativa** (teclado ou mouse): fundo `--primary-soft`.
- **Limite:** 8 opções. Havendo mais, a última linha diz "Mostrando 8 de 23. Continue digitando para achar os outros." em `--text-caption` `--muted-foreground`, com borda superior `--line` `--border`.
- **Vazio:** "Nenhum resultado", `--text-small` `--muted-foreground`, `role="status"`.
- **Busca:** ignora maiúsculas e acentos; procura no nome e no detalhe.
- **Teclado e ARIA:** seção 9.2.

### 6.4 Chips e segmentado

**Chips de filtro** (`role="group"` com `aria-label`, cada chip um `<button aria-pressed>`):

- Altura `--chip`, `padding: 0 var(--space-14)`, raio `--radius-full`, fundo `--card`, borda `--line` `--border`, espaço `--space-8`, `--text-ui` `--weight-semibold` `--foreground`.
- Conteúdo: iniciais `xs` (com `margin-left: -6px`) quando o chip é uma pessoa; rótulo; contagem em `--muted-foreground`.
- Hover: borda `--border-strong`. Ativo (no clique): fundo `--muted`. Escolhido (`aria-pressed="true"`): fundo e borda `--foreground`, texto `--on-dark`, contagem `--on-dark-muted`.
- O primeiro chip é "Todos" com o total. Escolher um chip mostra só aquele grupo; escolher "Todos" limpa o filtro.
- A fileira rola na horizontal sem barra visível (`overflow-x: auto; scrollbar-width: none`) e tem `padding: var(--space-6); margin: calc(-1 * var(--space-6))`, para o contorno de foco não ser cortado. Em formulário, a fileira quebra linha em vez de rolar.
- Profissionais aparecem em chips até 6; acima disso, o filtro e a escolha viram combobox.

**Segmentado** (troca de visão, `role="group"`, botões com `aria-pressed`):

- Caixa `inline-flex`, fundo `--muted`, raio `--radius-md`, `padding: var(--space-4)`, espaço `--space-2`.
- Botão: altura `--control-sm`, `padding: 0 var(--space-16)`, raio `--radius-sm`, sem borda, `--text-ui` `--weight-bold` `--muted-foreground`. Hover: texto `--foreground`. Ativo (no clique): fundo `--card-soft`. Escolhido (`aria-pressed="true"`): fundo `--card`, texto `--foreground`, `--shadow-sm`.
