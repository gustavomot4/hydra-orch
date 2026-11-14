## 9. Acessibilidade

Não é uma seção separada do design — é parte do contrato. Piso: **WCAG 2.2 AA**.

### 9.1 Contraste dos pares prescritos

Razão calculada pela fórmula de luminância relativa da WCAG,
`(L1 + 0,05) / (L2 + 0,05)`. `--fill` e `--fill-2` são translúcidos: o hex da
coluna "Fundo" já é o composto sobre a superfície indicada. Trocou um token,
refaça a tabela.

**Texto — exige 4,5:1**

| Par | Texto | Fundo | Razão | Passa 4,5 | Passa 3,0 |
| --- | --- | --- | --- | --- | --- |
| `--ink` sobre `--surface` | `#1C1B19` | `#FFFFFF` | 17,21:1 | sim | sim |
| `--ink` sobre `--paper` | `#1C1B19` | `#FAF9F7` | 16,36:1 | sim | sim |
| `--ink` sobre `--sunken` | `#1C1B19` | `#F4F2EC` | 15,37:1 | sim | sim |
| `--ink` sobre `--fill` em `--surface` | `#1C1B19` | `#EFEEED` | 14,85:1 | sim | sim |
| `--ink` sobre `--fill` em `--paper` | `#1C1B19` | `#EAE9E6` | 14,16:1 | sim | sim |
| `--ink` sobre `--fill` em `--sunken` | `#1C1B19` | `#E5E3DC` | 13,37:1 | sim | sim |
| `--ink` sobre `--fill-2` em `--surface` | `#1C1B19` | `#E6E6E4` | 13,75:1 | sim | sim |
| `--ink` sobre `--fill-2` em `--paper` | `#1C1B19` | `#E2E1DE` | 13,14:1 | sim | sim |
| `--ink` sobre `--fill-2` em `--sunken` | `#1C1B19` | `#DDDBD5` | 12,43:1 | sim | sim |
| `--ink` sobre `--fill` duas vezes em `--sunken` (hover no segmented, pior caso) | `#1C1B19` | `#D8D5CF` | 11,75:1 | sim | sim |
| `--ink-2` sobre `--surface` | `#6B6862` | `#FFFFFF` | 5,55:1 | sim | sim |
| `--ink-2` sobre `--paper` | `#6B6862` | `#FAF9F7` | 5,28:1 | sim | sim |
| `--ink-2` sobre `--sunken` | `#6B6862` | `#F4F2EC` | 4,96:1 | sim | sim |
| `--ink-2` sobre `--fill` em `--surface` (desabilitado) | `#6B6862` | `#EFEEED` | 4,79:1 | sim | sim |
| `--ink-2` sobre `--fill` em `--paper` (desabilitado) | `#6B6862` | `#EAE9E6` | 4,57:1 | sim | sim |
| `--accent` sobre `--surface` | `#1F4E8C` | `#FFFFFF` | 8,31:1 | sim | sim |
| `--accent` sobre `--paper` | `#1F4E8C` | `#FAF9F7` | 7,90:1 | sim | sim |
| `--accent` sobre `--sunken` | `#1F4E8C` | `#F4F2EC` | 7,42:1 | sim | sim |
| `--accent` sobre `--fill` em `--sunken` (pior fundo) | `#1F4E8C` | `#E5E3DC` | 6,46:1 | sim | sim |
| `--accent-hover` sobre `--surface` | `#2A5B9C` | `#FFFFFF` | 6,83:1 | sim | sim |
| `--accent-hover` sobre `--paper` | `#2A5B9C` | `#FAF9F7` | 6,49:1 | sim | sim |
| `--accent-hover` sobre `--sunken` | `#2A5B9C` | `#F4F2EC` | 6,10:1 | sim | sim |
| `--accent-hover` sobre `--fill` em `--sunken` (pior fundo) | `#2A5B9C` | `#E5E3DC` | 5,31:1 | sim | sim |
| `--accent-active` sobre `--fill` em `--sunken` (pior fundo) | `#183F73` | `#E5E3DC` | 8,17:1 | sim | sim |
| `--danger` sobre `--surface` | `#8E2C26` | `#FFFFFF` | 8,27:1 | sim | sim |
| `--danger` sobre `--paper` | `#8E2C26` | `#FAF9F7` | 7,86:1 | sim | sim |
| `--danger` sobre `--sunken` | `#8E2C26` | `#F4F2EC` | 7,39:1 | sim | sim |
| `--danger` sobre `--fill` em `--sunken` (pior fundo) | `#8E2C26` | `#E5E3DC` | 6,43:1 | sim | sim |
| `--on-accent` sobre `--accent` | `#FFFFFF` | `#1F4E8C` | 8,31:1 | sim | sim |
| `--on-accent` sobre `--accent-hover` | `#FFFFFF` | `#2A5B9C` | 6,83:1 | sim | sim |
| `--on-accent` sobre `--accent-active` | `#FFFFFF` | `#183F73` | 10,51:1 | sim | sim |
| `--on-accent` sobre `--danger` | `#FFFFFF` | `#8E2C26` | 8,27:1 | sim | sim |
| `--on-accent` sobre `--danger-hover` | `#FFFFFF` | `#9C332C` | 7,18:1 | sim | sim |
| `--on-accent` sobre `--danger-active` | `#FFFFFF` | `#7A2520` | 9,94:1 | sim | sim |
| `--surface` sobre `--ink` (secundário em tinta) | `#FFFFFF` | `#1C1B19` | 17,21:1 | sim | sim |
| `--surface` sobre `--ink-2` (secundário em tinta, hover) | `#FFFFFF` | `#6B6862` | 5,55:1 | sim | sim |
| Toast: `--surface` sobre tinta a 92%, com `--surface` por baixo (pior caso) | `#FFFFFF` | `#2E2D2B` | 13,71:1 | sim | sim |
| Barra: `--ink` sobre `--paper` a 80%, com `--ink` por baixo (pior caso, sem contar o desfoque) | `#1C1B19` | `#CECDCB` | 10,79:1 | sim | sim |

**Texto de 28px ou mais e elemento de interface — exige 3,0:1**

| Par | Frente | Fundo | Razão | Passa 4,5 | Passa 3,0 |
| --- | --- | --- | --- | --- | --- |
| `--ink-3` sobre `--surface` (borda de campo, trilho desligado, ícone, texto ≥ 28px) | `#827E76` | `#FFFFFF` | 4,04:1 | não | sim |
| `--ink-3` sobre `--paper` | `#827E76` | `#FAF9F7` | 3,84:1 | não | sim |
| `--ink-3` sobre `--sunken` | `#827E76` | `#F4F2EC` | 3,61:1 | não | sim |
| `--ink-3` sobre `--fill` em `--sunken` (pior fundo) | `#827E76` | `#E5E3DC` | 3,14:1 | não | sim |
| Interruptor desligado: botão `--surface` sobre trilho `--ink-3` | `#FFFFFF` | `#827E76` | 4,04:1 | não | sim |
| Interruptor ligado: botão `--surface` sobre trilho `--ink` | `#FFFFFF` | `#1C1B19` | 17,21:1 | sim | sim |
| Anel de foco `--accent` contra `--surface` | `#1F4E8C` | `#FFFFFF` | 8,31:1 | sim | sim |
| Anel de foco `--accent` contra `--paper` | `#1F4E8C` | `#FAF9F7` | 7,90:1 | sim | sim |
| Anel de foco `--accent` contra `--sunken` | `#1F4E8C` | `#F4F2EC` | 7,42:1 | sim | sim |
| Anel de foco `--surface` dentro do toast | `#FFFFFF` | `#2E2D2B` | 13,71:1 | sim | sim |
| Borda de erro `--danger` contra `--surface` | `#8E2C26` | `#FFFFFF` | 8,27:1 | sim | sim |
| Borda de erro `--danger` contra `--paper` | `#8E2C26` | `#FAF9F7` | 7,86:1 | sim | sim |

**Pares que reprovam, e por isso são proibidos**

| Par | Razão | Regra |
| --- | --- | --- |
| `--ink-2` sobre `--fill-2` (em `--surface` / `--paper` / `--sunken`) | 4,44 / 4,24 / 4,01:1 | sobre `--fill-2`, texto `--ink` |
| `--ink-2` sobre `--fill` em `--sunken` | 4,31:1 | texto `--ink`; nada desabilitado sobre `--sunken` |
| `--ink-2` na barra translúcida, com `--ink` por baixo | 3,48:1 | na barra, texto `--ink` |
| `--ink-3` em texto abaixo de 28px | 3,61 a 4,04:1 | legenda e rótulo são `--ink-2` |
| Texto com `opacity` (`--ink-2` a 50% sobre `--surface`) | 2,08:1 | nenhum texto com `opacity` |
| Anel de foco `--accent` dentro do toast | 1,65:1 | anel `--surface` |

**Onde a cor não basta, o segundo sinal é obrigatório**

| Par | Razão entre as duas cores | Segundo sinal |
| --- | --- | --- |
| Link `--accent` no meio de texto `--ink` | 2,07:1 | sublinhado permanente |
| Crítico `--danger` ao lado de texto `--ink` | 2,08:1 | peso 600 + rótulo por extenso |
| Pílula `--surface` do segmented contra o trilho `--fill` | 1,16 a 1,29:1 | peso 600 no selecionado |
| Item selecionado da lateral (`--fill` sobre `--sunken`) | 1,15:1 | peso 600 + `aria-current` |
