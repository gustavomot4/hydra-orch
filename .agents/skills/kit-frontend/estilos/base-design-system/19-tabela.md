### Tabela

Cabeçalho 28px, fundo `--sunken` com raio 6px nas pontas, texto no tamanho de
legenda da tela (12px na ferramenta), peso 400, `--ink-2`, caixa **normal**,
tracking do tamanho (3.4).
Linha `--h-linha`: 36px com ponteiro fino / 44px em `pointer: coarse`. Padding
lateral 12px. Separador `--line` entre linhas.
Valores comparáveis (moeda, contagem, percentual, horário) à direita;
identificador à esquerda; todos com `tabular-nums`.
Hover de linha: `--sunken`. Selecionada: `--sunken` + primeira célula em peso
600 + `aria-selected="true"`.
Dentro de cartão: `margin-inline: -12px`, para o texto da primeira coluna
alinhar com o título do cartão.

**Texto que não cabe na célula:**
`white-space: nowrap; overflow: hidden; text-overflow: ellipsis`, com o valor
inteiro em `title`. Antes de cortar célula, corte coluna: a que não muda decisão
sai.

⚠️ **Zebra só com 5 colunas ou mais**, em `--sunken` nas linhas pares — e então
sem hover de fundo. Em 2–3 colunas ela não ajuda a acompanhar nada e cai direto
na regra de subtração.

**Em ≤734px a tabela vira cartões empilhados** — um por linha, cada valor com o
nome da coluna em `--ink-2` — nunca rolagem horizontal em tabela de dados.

Em 735–1068px, com a lateral de 264px ao lado, sobram cerca de 440px para a
tabela: o cartão ocupa a linha inteira, a coluna de 288px passa para baixo e
saem as colunas que não mudam decisão (no exemplo, Bicicleta e Serviço).

**Semântica e teclado:** `<table>` com `<th scope="col">`. Linha que abre
detalhe tem um link na primeira célula, e é ele que recebe o foco; não ponha
`tabindex` em `<tr>`.

### Segmented control

Altura `--h-controle` (32px) · trilho `--fill` com raio 8px · inset 2px · pílula
selecionada `--surface` com raio 6px e `--shadow-control` · texto 14px `--ink`,
peso 600 no selecionado · hover na opção não selecionada: `--fill` · de 2 a 5
opções.
**Sem cor:** o estado é a posição da pílula **mais o peso 600** — a pílula
sozinha dá de 1,16 a 1,29:1 contra o trilho e não vale como sinal.

**Semântica e teclado:** `role="radiogroup"` com nome; cada opção é
`role="radio"` com `aria-checked`. Uma parada de Tab só (`tabindex="0"` na
selecionada, `-1` nas outras); ← e → movem e selecionam. Abas de conteúdo usam o
mesmo desenho com `role="tablist"`, `tab` e `tabpanel`.

### Interruptor

38×22 · botão de 18px · curso de 16px · trilho em pílula, botão em 50%.
Desligado = trilho `--ink-3` (4,04:1 sobre `--surface`). Ligado = trilho
`--ink`, **sempre** — nunca no acento. Desabilitado = trilho `--fill`.
Botão `--surface` com `--shadow-control`. Rótulo à esquerda, interruptor à
direita, 8px entre os dois.
A caixa tem 22px de altura; o alvo vem do `::after` de 6.3 — 38×28 com mouse,
44×44 no toque.

**Semântica e teclado:** `<button role="switch">` com `aria-checked`, nomeado
pelo rótulo ao lado (`aria-labelledby`). Espaço e Enter alternam. O efeito é
imediato, sem botão de salvar.
