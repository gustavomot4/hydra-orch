## 11. Anti-padrões

Os detalhes que mais denunciam interface genérica:

| ❌ Não | ✅ Em vez disso |
| --- | --- |
| Cabeçalho de coluna em CAIXA ALTA com tracking | caixa normal, cinza secundário |
| Cor por categoria (N matizes) | inicial, nome ou posição |
| Badge colorido para status | peso, tom de tinta e texto por extenso |
| Texto apagado com `opacity` | `--ink-2` em opacidade cheia |
| Ícone decorativo ao lado de cada KPI | nada — o rótulo já nomeia o número |
| Cartão em página de marketing | espaço |
| Centralizar o texto do formulário e o título de painel | texto à esquerda; a coluna do formulário centralizada na área útil |
| Borda de 1px contornando tudo | degrau de tom + espaço |
| Sombra inventada para dar profundidade | as três dos tokens, cada uma no seu papel |
| `backdrop-filter` sobre fundo chapado | fundo sólido |
| "Simulado", "Beta", "Novo" repetido 3× na tela | uma vez, se muda a leitura |
| Gráfico que só pode subir | nenhum gráfico |
| Sparkline + gráfico grande da mesma série | um dos dois |
| Total de uma coluna de 4 números | nada |
| Percentual sem ponto de comparação | valor absoluto, ou nada |
| Contador de vaidade ("11k clientes") | nada |
| Zebra em tabela de 2 colunas | separador simples |
| Ação escondida em `hover` | alvo persistente |
| Alvo e hover decididos pela largura da tela | `pointer` e `hover` |
| Mesma cor para a ação primária e para erro ou atraso | `--accent` na ação, `--danger` no perigo |
| Botão desabilitado sem dizer o porquê | rótulo que diz o que falta |
| Gradiente, sombra colorida, brilho, textura | superfície plana e um tom de fundo |
| Animação de entrada em tela de uso diário | nada |
| Confirmação sem o número real do impacto | "Apagar 143 registros" |
| Três famílias tipográficas | uma |
| Peso 500 e 700 misturados a 400/600 | só 400 e 600 |
| Anel de foco com alfa | acento em opacidade cheia |

---
