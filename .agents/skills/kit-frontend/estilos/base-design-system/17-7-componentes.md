## 7. Componentes

Especificações concretas. Adapte as unidades ao stack (px na web, pt no iOS,
dp no Android) mas mantenha as **proporções**.

Três regras valem para todos:

- **Toda altura é `min-height`.** Com zoom de texto o componente cresce; não
  corta.
- **Texto que não cabe:** título quebra em até 2 linhas; rótulo de botão nunca
  quebra (`white-space: nowrap`); célula de tabela corta com reticências (ver
  Tabela).
- **Hover** só dentro de `@media (hover: hover) and (pointer: fine)` (6.3).

### Botão — a escada de três degraus, sem segunda cor

É assim que a regra de um acento sobrevive:

| Degrau | Aparência |
| --- | --- |
| 1º — primário | preenchimento `--accent`, texto `--on-accent`, peso 600 |
| 2º — secundário | preenchimento `--fill`, texto `--ink`, peso 400. Quando o bloco não tem primário e ele é a ação mais forte dali: preenchimento `--ink`, texto `--surface` |
| 3º — terciário | texto `--accent`, peso 400, sem caixa, sem raio; sublinhado no hover e no foco |

⚠️ Se o segundo degrau virar um tom claro do acento, ele vira um **segundo
acento** e a regra cai.

| Variante | Altura | Padding lateral | Tipo | Raio |
| --- | --- | --- | --- | --- |
| Primário (vitrine e fluxo) | 44px | 22px | 17px | pílula |
| Secundário (vitrine e fluxo) | 36px | 16px | 14px | pílula |
| Primário e secundário (ferramenta) | 32px | 12px | 14px | 8px |
| Terciário | a do texto + `padding-block: 6px` | 0 | o do texto vizinho | — |

A altura vem de `min-height`, com `line-height: var(--lh-botao)` e sem padding
vertical: somar `14 + 3` de linha com `6 + 6` de padding dá 29px, não 32.
Controles de alturas diferentes na mesma linha alinham pelo centro.

| Estado | Primário | Secundário em `--fill` | Secundário em `--ink` | Terciário |
| --- | --- | --- | --- | --- |
| Hover | `--accent-hover` | `--fill-2` | `--ink-2` | `--accent-hover`, sublinhado |
| Pressionado | `--accent-active` | `--fill-2` | `--ink` | `--accent-active` |
| Foco | anel (6.4) | anel | anel | anel + sublinhado |
| Desabilitado | `--fill` + texto `--ink-2` | idem | idem | texto `--ink-2`, sem sublinhado |

Ação destrutiva (só em confirmação — ver Modal): preenchimento `--danger`,
hover `--danger-hover`, pressionado `--danger-active`, texto `--on-accent`.

⚠️ **Desabilitado não pode ser `opacity`.** Um primário com `opacity: .42`
(texto branco sobre `--accent`, composto sobre `--paper`) cai para **2,12:1** —
ilegível. Troque a **superfície**: fundo `--fill`, texto `--ink-2`, que dá
4,79:1 sobre `--surface` e 4,57:1 sobre `--paper`. Sobre `--sunken` o par cai a
4,31:1: formulário com botão que pode desabilitar não vai em faixa `--sunken`.

✅ **Botão desabilitado deve DIZER o que falta.** Troque o rótulo ("Escolha um
horário", "Preencha seus dados") em vez de deixar uma placa colorida apagada.
Para a instrução chegar a quem usa teclado e leitor de tela, use
`aria-disabled="true"` e mantenha o botão focável: o atributo `disabled` tira o
botão da ordem de Tab e esconde justamente o rótulo que explica.

**Semântica e teclado:** `<button>` para ação, `<a>` para navegação. Enter e
Espaço acionam. Com `aria-disabled="true"` o clique não faz nada.
