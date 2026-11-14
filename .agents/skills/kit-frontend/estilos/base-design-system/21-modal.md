### Modal

Largura 560px (em ≤734px, a largura da tela menos 22px de cada lado) · padding
24px · fundo `--surface` · raio 12px · `--shadow-modal` · véu `rgba(0,0,0,.28)`
com `backdrop-filter: blur(4px)`. Título no tamanho de título de seção da tela
(3.2). Botões no rodapé, à direita, com 8px entre eles: o neutro ("Voltar")
antes, a ação depois.

**Numa confirmação destrutiva, a ação destrutiva É a ação primária daquele
diálogo** — e é o único preenchimento dele, em `--danger`. A proteção é o
**texto explícito com o número real** ("Apagar 143 registros") e o "Voltar"
neutro ao lado, que recebe o foco inicial.

**Semântica e teclado:** `<dialog>` aberto com `showModal()` e nomeado por
`aria-labelledby`. Foco inicial no botão neutro; Tab fica preso no diálogo; Esc
fecha; ao fechar, o foco volta ao controle que abriu.

### Estados de tela: vazio, carregando, erro, tudo feito

Toda tela ou bloco com dados tem os quatro.

**Vazio — uma frase.** Sem ícone, sem título grande, sem segunda linha
pedagógica. Quem olha uma tabela vazia já sabe que ela está vazia — o que falta
é **o que fazer a respeito**. Se houver uma ação, ela vem junto; se não, só a
frase.

**Carregando — o layout já montado.** No lugar de cada texto ou número, um
bloco estático em `--fill`, raio 6px, com a altura da linha que ele substitui.
Sem spinner e sem shimmer: os dois são loop (seção 8). Passou de 400ms, aparece
a frase "Carregando…" em `--ink-2`, numa região com `role="status"`.

**Erro — uma frase com a causa e a ação "Tentar de novo"** (botão secundário),
no lugar do conteúdo que falhou, em `--ink`, numa região com `role="alert"`.
Sem ícone, sem ilustração.

**Tudo feito — uma frase**, em `--ink-2`, sem ilustração ("Nenhuma ordem
pendente hoje.").

### Toast

Fundo tinta a 92% (`color-mix(in srgb, var(--ink) 92%, transparent)`) com
`backdrop-filter: blur(20px)` · texto `--surface`, 14px · raio 8px · padding
12px 16px · uma frase · embaixo, centralizado, a 24px da borda (acima da barra
fixa, se houver) · fica 5 s e não some enquanto tiver foco ou hover.
**Sem ícone e sem cor por tipo:** a frase já diz o que aconteceu. No máximo uma
ação ("Desfazer"), em texto `--surface` sublinhado.

**Semântica e teclado:** a região `role="status"` já existe na página antes de o
texto entrar. Erro que pede ação não é toast: é a frase de erro no lugar onde o
problema está.

### O que não está nesta lista

Select, checkbox e radio estão em Campo; abas, em Segmented control. Para o
resto — tooltip, paginação, breadcrumb, seletor de data — use o controle nativo
do navegador com a fonte herdada e `accent-color: var(--ink)`. Onde não houver
nativo, componha com o que já existe aqui (botão terciário, texto `--ink-2`,
lista agrupada). Não crie componente nem estilo novo. Gráfico não tem
especificação além dos anti-padrões da seção 11: antes de desenhar um, pergunte.

---
