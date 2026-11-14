## 8. Movimento

| Uso | Duração | Token |
| --- | --- | --- |
| Hover, mudança de cor | 150ms | `--dur-fast` |
| Entrada de painel, gaveta, modal | 280ms | `--dur-base` |
| Transição de tela | 320ms | `--dur-screen` |

Curva: `cubic-bezier(0.28, 0.11, 0.32, 1)` (`--ease`).

- Animação de entrada em tela usada muitas vezes por dia é **custo, não
  encanto**. Corte.
- Nada de animação em loop permanente — spinner e shimmer de carregamento
  inclusive (ver Estados de tela).
- `@media (prefers-reduced-motion: reduce)` zerando tudo é obrigatório. O bloco
  está nos tokens (seção 12).

---
