### 4.3 As seis situações da consulta

A consulta avança em quatro etapas (Agendado → Confirmado → Em atendimento → Concluído) e pode terminar antes em Cancelado ou Faltou. Concluído, Cancelado e Faltou são finais: não reabrem.

| Situação | Rótulo | Ícone (Lucide) | Forma | Texto | Fundo | Barra ou contorno | Ação seguinte | Aviso depois da ação |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Agendado | Agendado | `clock` | Vazado, contorno tracejado | `--status-agendado-fg` | `--status-agendado-bg` | Contorno `--line-control` tracejado em `--status-agendado-bar` | Confirmar | "Consulta de Helena confirmada" + Desfazer |
| Confirmado | Confirmado | `check` | Cheio claro, barra à esquerda | `--status-confirmado-fg` | `--status-confirmado-bg` | Barra de 4 px em `--status-confirmado-bar` | Iniciar atendimento | "Atendimento de Helena iniciado" + Desfazer |
| Em atendimento | Em atendimento | `stethoscope` | Cheio escuro, com sombra | `--status-atendimento-fg` | `--status-atendimento-bg` | Barra de 4 px em `--status-atendimento-bar`; `--shadow-live` | Concluir atendimento | "Atendimento de Helena concluído" + Desfazer |
| Concluído | Concluído | `check-check` | Cheio cinza, nome em cinza | `--status-concluido-fg` | `--status-concluido-bg` | Barra de 4 px em `--status-concluido-bar` | Agendar de novo | — |
| Cancelado | Cancelado | `x` | Hachurado, nome riscado | `--status-cancelado-fg` | `--status-cancelado-bg` + `--hatch` | Barra de 4 px em `--status-cancelado-bar` | Agendar de novo | "Consulta de Helena cancelada", sem Desfazer |
| Faltou | Faltou | `user-x` | Hachurado | `--status-faltou-fg` | `--status-faltou-bg` + `--hatch` | Barra de 4 px em `--status-faltou-bar` | Agendar de novo | "Falta de Helena registrada", sem Desfazer |

Cancelar e marcar falta pedem confirmação antes (seção 6.14) e não oferecem "Desfazer", porque não reabrem. O aviso usa só o primeiro nome.

Pílula de situação, usada na lista, no detalhe e onde mais a situação aparecer como texto:

```css
.status { --fg: var(--status-agendado-fg); --bg: var(--status-agendado-bg);
  display: inline-flex; align-items: center; gap: var(--space-6); height: 30px; padding: 0 var(--space-12) 0 var(--space-10);
  border-radius: var(--radius-full); background-color: var(--bg); color: var(--fg);
  font-size: var(--text-small); font-weight: var(--weight-semibold); white-space: nowrap; }
.status svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: 2.4; flex: none; }
.status[data-status="agendado"] { border: var(--line-control) dashed var(--status-agendado-bar); }
.status[data-status="confirmado"] { --fg: var(--status-confirmado-fg); --bg: var(--status-confirmado-bg); }
.status[data-status="atendimento"] { --fg: var(--status-atendimento-fg); --bg: var(--status-atendimento-bg); }
.status[data-status="concluido"] { --fg: var(--status-concluido-fg); --bg: var(--status-concluido-bg); }
.status[data-status="cancelado"] { --fg: var(--status-cancelado-fg); --bg: var(--status-cancelado-bg); }
.status[data-status="faltou"] { --fg: var(--status-faltou-fg); --bg: var(--status-faltou-bg); }
.status[data-status="cancelado"], .status[data-status="faltou"] { background-image: var(--hatch); }
```

```html
<span class="status" data-status="confirmado"><svg aria-hidden="true"><!-- check --></svg>Confirmado</span>
```

Versão compacta, para a lista do dia abaixo de 1100 px (o ponto de quebra da casca do celular, 5.1): círculo de 30 px com o mesmo fundo, contorno e hachura, só o ícone (`stroke-width: 2.5`), o rótulo em `.sr-only` e o mesmo rótulo no atributo `title`.

Legenda da grade: uma lista com as seis situações, cada uma com uma amostra de 20 × 14 px, raio 4 px, mesma forma do cartão (contorno tracejado, barra esquerda de 4 px, hachura) e o rótulo em `--text-caption`, `--weight-semibold`, `--muted-foreground`.
