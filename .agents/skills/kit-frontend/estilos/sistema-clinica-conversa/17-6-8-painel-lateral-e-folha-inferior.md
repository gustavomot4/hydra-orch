### 6.8 Painel lateral e folha inferior

O mesmo componente em três formas: **coluna**, ao lado da página, só para o detalhe da consulta na Agenda a partir de 1280 px (7.2); **painel**, à direita e por cima da página, de 900 a 1279 px e, a partir de 1280 px, nas demais ações rápidas; **folha**, que sobe de baixo, abaixo de 900 px. Abre o detalhe da consulta, o menu Mais e outras ações rápidas. A coluna não cobre nada e é um diálogo não modal: a agenda continua inteira e clicável. O painel e a folha escurecem a página com o véu; o aviso com "Desfazer" fica acima do véu e continua clicável sem fechar o painel.

| | Coluna (Agenda, 1280 px ou mais) | Painel (900 px ou mais) | Folha (abaixo de 900 px) |
| --- | --- | --- | --- |
| Posição | segunda coluna de `.agenda-main`, largura `var(--overlay-width)`, da altura da coluna (7.2) | `position: fixed; top: 0; right: 0; bottom: 0`, largura `min(var(--overlay-width), 100vw)` | `position: fixed; left: 0; right: 0; bottom: 0`, altura máxima `88dvh` |
| Fundo e borda | `--card`, borda `--line` `--border`, raio `--radius-xl` | `--card`, borda esquerda `--line` `--border`, `--shadow-lg` | `--card`, raio `--radius-sheet` nos cantos de cima, `--shadow-lg` |
| Véu | nenhum | `--overlay` atrás; tocar no véu fecha | `--overlay` atrás; tocar no véu fecha |
| Alça | nenhuma | nenhuma | 44 × 5 px, raio `--radius-full`, `--border-strong`, `margin: var(--space-10) auto 0` |
| Cabeçalho | `padding: var(--space-18) var(--space-24) var(--space-4)` | `padding: var(--space-18) var(--space-24) var(--space-4)` | `padding: var(--space-6) var(--space-16) 0 var(--space-20)` |
| Corpo | `padding: var(--space-10) var(--space-24) var(--space-24)`, espaço `--space-20`, rolagem própria com `overscroll-behavior: contain` | o mesmo da coluna | `padding: var(--space-8) var(--space-20) var(--space-20)`, espaço `--space-16` |
| Rodapé opcional | `padding: var(--space-14) var(--space-24) var(--space-20)`, borda superior `--line` `--border` | o mesmo da coluna | `padding: var(--space-12) var(--space-20) calc(var(--space-16) + env(safe-area-inset-bottom))` |
| Entrada | nenhuma: a grade muda de largura de uma vez (seção 8) | desliza 24 px da direita, opacidade de 0,4 a 1, `--duration-slow` `ease-out` | sobe 40 px, opacidade de 0,4 a 1, `--duration-slow` `ease-out` |

- **Título:** curto, em maiúsculas (`--text-small` `--weight-bold` `--muted-foreground` `--tracking-caps`), por exemplo "CONSULTA". O nome da pessoa vem no corpo, grande.
- **Fechar:** botão de ícone `x` `--icon-lg` `ghost` com `aria-label="Fechar"`, no canto do cabeçalho. Esc também fecha.
- **Foco:** vai para o painel, a folha ou a coluna ao abrir e volta ao elemento que o abriu ao fechar.
- `z-index: var(--z-panel)` no painel e na folha; o véu usa `--z-overlay`. A coluna não tem `z-index`: é parte da página.

**Detalhe da consulta** (conteúdo do painel e da coluna lateral da tela Hoje), de cima para baixo. Os itens 1 a 5 rolam dentro do corpo; o item 6, a ação principal, é o rodapé e fica sempre visível, sem rolar:

1. Iniciais `xl` e, ao lado, o nome em `--text-title` e "34 anos · (11) 98765-4321" em `--text-ui` `--muted-foreground` (sem telefone: "Sem telefone cadastrado").
2. Três atalhos numa grade `1.2fr 1fr 1fr`, espaço `--space-8`, todos `sm`: "WhatsApp" (`whatsapp`, `message-circle`), "Ligar" (`secondary`, `phone`, link `tel:`) e "Ficha" (`secondary`, `user-round`). Sem telefone, WhatsApp e Ligar ficam desabilitados. O WhatsApp abre `https://wa.me/55<DDD><número>?text=<lembrete>` com o texto "Olá, Helena! Lembrando da sua consulta de limpeza no dia 28/10/2026 às 10:00. Podemos confirmar?". Nada é enviado sozinho: a conversa abre e a pessoa decide.
3. Caixa de dados: `<dl>` com fundo `--card-soft`, raio `--radius-box`, `padding: var(--space-18)`, espaço `--space-14`. Cada linha é uma grade `24px 1fr` com espaço `--space-12`: ícone `--icon` `--muted-foreground`; rótulo em `--text-caption` `--weight-semibold` `--muted-foreground`; valor em `--text-body` `--weight-medium`. Linhas: Horário ("Hoje, 10:00 às 10:30 · 30 min", ícone `clock`), Procedimento ("Limpeza · R$ 180,00", `clipboard-list`, o ícone da ficha do procedimento, nunca `sparkles`), Profissional (`stethoscope`), Observação (`sticky-note`). Valor vazio: "Não informado" em `--muted-foreground` `--weight-regular`.
4. Etapas (6.15). Em Cancelado e Faltou, no lugar delas, um alerta (`danger` para Cancelado, `warning` para Faltou) "Consulta cancelada" ou "Paciente faltou", com "Para atender de novo, agende uma nova consulta.". Em Concluído, alerta `success` "Atendimento concluído" abaixo das etapas.
5. Ações secundárias, só em situação aberta: grade de 3 colunas, espaço `--space-8`, todas `sm`: "Remarcar" (`secondary`, `calendar-sync`), "Faltou" (`danger`, `user-x`) e "Cancelar" (`danger`, `x`).
6. **Rodapé, ação principal:** botão `lg` `block` `primary` com a ação seguinte do 4.3 (`clock` para Confirmar, `stethoscope` para Iniciar e Concluir). Em situação final, "Agendar de novo" (`soft`, `rotate-ccw`) abre o agendamento com paciente e profissional já escolhidos. O rodapé nunca sai da tela: a rolagem é só do corpo.

Receita da coluna de detalhe, usada na tela Hoje (7.1) e na Agenda a partir de 1280 px (7.2). No painel e na folha, corpo e rodapé seguem a tabela acima.

```css
.detail-column { display: flex; flex-direction: column; overflow: hidden; background: var(--card); border: var(--line) solid var(--border); border-radius: var(--radius-xl); }
.detail-column .detail-body { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: var(--space-20); padding: var(--space-24); overflow-y: auto; overscroll-behavior: contain; }
.detail-column .detail-foot { flex: none; padding: var(--space-14) var(--space-24) var(--space-20); border-top: var(--line) solid var(--border); }
```
