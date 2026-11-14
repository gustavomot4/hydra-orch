### 4.5 Estado: peso e texto antes de cor

Status, categoria e seleção **não** usam cor. O único estado com cor é o
crítico, e nele a cor nunca vai sozinha. Use:

| Estado | Como |
| --- | --- |
| Resolvido / concluído | `--ink-2`, peso 400 + rótulo por extenso ("Entregue") |
| Neutro / pendente | `--ink`, peso 400 |
| Exige ação | `--ink`, peso **600** + rótulo por extenso |
| Crítico | `--danger`, peso **600** + rótulo por extenso ("Atrasada 2 dias") |

⚠️ **`opacity` não apaga texto que alguém precisa ler.** `--ink-2` a 50% sobre
branco dá 2,08:1. "Resolvido" continua sendo conteúdo: nome, serviço, horário.
O tom mais claro permitido para texto é `--ink-2`, em opacidade cheia.

Cor por categoria (4 pessoas, 6 projetos, 8 etiquetas) é a maneira mais rápida
de destruir o acento. Se precisar distinguir N itens, use **inicial ou nome**,
não matiz.

---
