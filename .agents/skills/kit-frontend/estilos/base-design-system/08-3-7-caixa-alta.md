### 3.7 Caixa alta

**Não use. Sem exceção.** Na leitura do autor, nenhum token de tipografia do
apple.com aplica `text-transform`: o "eyebrow" deles é um título de 21–24px em
caixa normal, e o rótulo de grupo da barra lateral é 13px peso 600 em caixa
normal.

Aqui, o rótulo de grupo (navegação lateral, seção de formulário) é o tamanho de
legenda da tela em peso 600, `--ink-2`, caixa normal. Se ele pede mais destaque
que isso, transforme-o em **título de verdade**.

Cabeçalho de coluna em caixa alta com tracking é a assinatura visual de
dashboard genérico. Use caixa normal, `--ink-2`, peso 400 e o tracking do
tamanho (3.4).

### 3.8 Números

`font-variant-numeric: tabular-nums` em **toda** célula de moeda, contagem,
horário, percentual e ID — qualquer número comparável verticalmente.

⚠️ Tabular alarga a sequência, e o quanto depende dos dígitos: quase nada em
"380,00", muito em "1.111,11", porque o 1 proporcional é estreito. Ligue
**antes** de fechar as larguras de coluna, e dimensione a coluna pela pior
sequência (só algarismos 1).

Texto corrido fica com números proporcionais.

---
