### 4.4 Neutros: escolha uma temperatura e não misture

Cinzas de sistema costumam ser **azulados** (B > R). Se a marca é quente (couro,
madeira, âmbar, terra), misturar as duas famílias faz o off-white parecer
encardido e o cinza parecer sujo.

Monte a rampa inteira na mesma temperatura, casada por luminância:

```
--paper      fundo da página
--surface    cartão, lista, tabela, campo, modal       (normalmente #FFFFFF)
--sunken     área recuada: faixa de capítulo, navegação lateral,
             cabeçalho de tabela, hover de linha
--fill       preenchimento translúcido (12%): trilho, chip, botão
             secundário, bloco de carregamento
--fill-2     hover de tudo que está em --fill; fundo de avatar (18%)
--line       separador de 1px, por border — nunca por box-shadow
--ink        texto principal                            ≥ 12:1
--ink-2      texto secundário, legenda, placeholder     ≥ 4,5:1
--ink-3      NÃO escreve texto corrido: borda de campo, trilho de
             interruptor desligado, ícone, texto de 28px ou mais   ≥ 3:1
```

Onde este documento diz "branco" e "cinza", leia assim:

| Tipo de tela | Página | Área recuada ("cinza") | Cartão ("branco") |
| --- | --- | --- | --- |
| Vitrine | `--paper` | faixa de capítulo em `--sunken`, full-bleed (5.7) | não existe |
| Fluxo | `--paper` | — | `--surface`, raio 12px, `--shadow-card` |
| Ferramenta | `--paper` | navegação lateral e cabeçalho de tabela em `--sunken` | `--surface`, raio 18px, `--shadow-card` |

⚠️ **`--ink-3` não escreve letra miúda.** 3:1 só vale para elemento de interface
e para texto grande — que nesta rampa quer dizer **28px ou mais** (a WCAG põe o
corte em 24px, ou 18,66px em negrito). Legenda, rótulo e rodapé são `--ink-2`.

⚠️ **`--ink-2` tem fundos proibidos:** `--fill-2` em qualquer superfície (4,01 a
4,44:1) e `--fill` aplicado em `--sunken` (4,31:1). Em cima de preenchimento, o
texto é `--ink`. A única exceção prescrita é o controle desabilitado (botão e
campo), `--ink-2` sobre `--fill`, que por isso só existe sobre `--surface` e
`--paper` (ver Botão).

⚠️ **Os label colors do iOS reprovam AA na web.** Achatados sobre branco:
`secondaryLabel` (`rgba(60, 60, 67, .6)`) = 3,44:1 · `tertiaryLabel` (`.3`) =
1,73:1 · `quaternaryLabel` (`.18`) = 1,37:1. Funcionam num iPhone a 30cm com
texto de 17px; num monitor a 60cm com texto de 13px, não. Use os números da web,
não os do sistema.

⚠️ **O par página/superfície precisa ser um degrau real.** A Apple vive sem
borda de 1px porque `#FFFFFF` sobre `#F5F5F7` é um degrau visível: 1,09:1. Os
neutros padrão daqui ficam mais próximos — `--surface` sobre `--paper` dá
1,05:1 — então vale a regra: **abaixo de 1,08:1 entre cartão e página, a sombra
do cartão (`--shadow-card`) é obrigatória.** Com os tokens padrão, sempre. A
faixa de capítulo (`--sunken` sobre `--paper`, 1,06:1) se sustenta por ser
full-bleed: a aresta atravessa a tela inteira.

**Só existe tema claro** (`color-scheme: light`). Tema escuro está fora de
escopo: não gere bloco `prefers-color-scheme: dark`.
