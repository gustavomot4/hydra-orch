### 6.5 Item de lista no estilo conversa

A consulta do dia como uma conversa: horário à esquerda, iniciais, nome em destaque e situação à direita. A linha inteira é um `<button>` que abre o detalhe.

```css
.agenda-list { background: var(--card); border: var(--line) solid var(--border); border-radius: var(--radius-lg); padding: var(--space-6); }
.agenda-group { padding: var(--space-12) var(--space-14) var(--space-6); font-size: var(--text-caption); font-weight: var(--weight-extrabold);
  letter-spacing: var(--tracking-caps); text-transform: uppercase; color: var(--muted-foreground); }
.agenda-row { width: 100%; display: grid; grid-template-columns: 58px 44px minmax(0, 1fr) auto; gap: var(--space-12); align-items: center;
  padding: var(--space-10) var(--space-12); border: 0; border-radius: var(--radius); background: transparent; text-align: left; color: var(--foreground); }
.agenda-row:hover { background: var(--card-soft); }
.agenda-row:active { background: var(--muted); }
.agenda-row[aria-pressed="true"] { background: var(--primary-soft); box-shadow: inset 3px 0 0 var(--primary); }
.agenda-row .time { font-size: var(--text-lead); font-weight: var(--weight-bold); font-variant-numeric: tabular-nums; }
.agenda-row .duration { display: block; font-size: var(--text-caption); color: var(--muted-foreground); }
.agenda-row .name { display: block; font-weight: var(--weight-bold); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.agenda-row .meta { display: block; font-size: var(--text-small); color: var(--muted-foreground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.agenda-row[data-status="concluido"] .time, .agenda-row[data-status="concluido"] .name { color: var(--muted-foreground); }
.agenda-row[data-status="cancelado"] .name { text-decoration: line-through; text-decoration-color: var(--border-strong); }
@media (max-width: 599px) { .agenda-row { grid-template-columns: 50px 44px minmax(0, 1fr) auto; gap: var(--space-10); padding: var(--space-10) var(--space-8); } }
```

- **Colunas:** horário (`.time`) com a duração embaixo ("30 min"); iniciais `md`; nome do paciente e, embaixo, "Procedimento · Profissional"; situação. A situação é a pílula do 4.3 a partir de 1100 px e a versão compacta abaixo disso.
- **Grupos:** "MANHÃ · 8", "TARDE · 5", "NOITE · 1" (manhã antes de 12 h, tarde antes de 18 h), em ordem de horário.
- **Selecionado** (`aria-pressed="true"`): só a partir de 1100 px, quando o detalhe fica ao lado. Abaixo disso a linha abre a folha e não fica marcada.
