### 5.2 Navegação por perfil

| Área | Ícone (Lucide) | Responsável | Recepção | No celular |
| --- | --- | --- | --- | --- |
| Hoje | `sun` | sim | sim | aba |
| Agenda | `calendar-days` | sim | sim | aba |
| Pacientes | `users` | sim | sim | aba |
| Painel | `chart-column` | sim | não | em Mais |
| Áreas financeiras e de estoque, se houver | um ícone por área | sim | não | em Mais |
| Clínica (dados, profissionais, procedimentos, acessos) | `building-2` | sim; edição só dele | só leitura | em Mais |

O menu mostra só o que o perfil pode abrir. Se alguém chegar a uma área sem acesso pelo endereço, vê o estado "sem acesso" da seção 7.7. A tela inicial depois de entrar é Hoje.

### 5.3 Casca

**No computador (1100 px ou mais):**

- Link "Ir para o conteúdo" como primeiro elemento focável, fora da tela até receber foco; com foco, aparece em `top: 12px; left: 16px`, fundo `--card`, `--shadow`, raio `--radius-md`, `--weight-bold`, `z-index: var(--z-skip)`.
- Barra superior `position: sticky; top: 0`, altura `--topbar`, fundo `--card`, borda inferior `--line` `--border`, `padding: 0 var(--page-x)`, espaço `--space-28` entre marca, navegação e conta, `z-index: var(--z-topbar)`.
- Marca: só o nome, sem símbolo em forma colorida, em `--text-heading`, `--weight-extrabold`, `--tracking-title`, com altura mínima `--target`; a segunda palavra em `--primary`. Esta é a versão positiva, sobre `--card`. Sobre `--foreground` vale a negativa: primeira palavra em `--on-dark` e segunda em `--on-dark-accent`. A marca leva para Hoje.
- Abas: pílulas de 42 px de altura, `padding: 0 14px`, raio `--radius-full`, ícone `--icon` e texto `--text-ui` `--weight-semibold` em `--muted-foreground`, espaço `--space-8`. Hover: fundo `--muted`, texto `--foreground`. Ativa: fundo `--primary-soft`, texto `--primary`, `aria-current="page"`.
- Conta, à direita: iniciais `sm`, nome em `--text-ui` `--weight-bold` (no máximo 160 px, com reticências), perfil em `--text-caption` `--muted-foreground` e seta para baixo `--icon-md`. Abre um menu suspenso com "Nome · Perfil" (`--text-small` `--muted-foreground`), uma divisória e "Sair" (`log-out`) em `--destructive`. Menu suspenso: largura mínima 220 px, fundo `--card`, borda `--line` `--border`, raio `--radius-box`, `padding: var(--space-6)`, `--shadow-lg`, `z-index: var(--z-menu)`, a 8 px do botão; item com altura mínima `--target`, `padding: 0 var(--space-12)`, raio `--radius-sm`, `--text-ui` `--weight-semibold`, ícone `--icon-md` `--muted-foreground`, destacado (teclado ou mouse) com fundo `--muted`.
- Conteúdo: `max-width: var(--page-max)`, centralizado, `padding: var(--space-28) var(--page-x) var(--space-40)`.

**No celular e no tablet (abaixo de 1100 px):**

- Barra superior compacta `position: sticky`, altura `--topbar-mobile`, fundo `color-mix(in srgb, var(--background) 94%, transparent)` com `backdrop-filter: blur(10px)`, borda inferior `--line` `--border`. Marca com o nome em `--text-section`; conta só com as iniciais.
- Barra de abas `position: fixed` embaixo, altura `calc(var(--tabbar) + env(safe-area-inset-bottom))`, fundo `--card`, borda superior `--line` `--border`, `padding: 6px 8px env(safe-area-inset-bottom)`, `z-index: var(--z-tabbar)`. Quatro colunas iguais: as três áreas de aba e Mais (`ellipsis`).
- Item de aba: coluna com ícone `--icon-lg` dentro de uma pílula de 58 × 32 px e rótulo em `--text-micro` `--weight-bold` `--muted-foreground`, altura mínima 56 px. Ativo: rótulo `--primary`, pílula `--primary-soft`.
- Mais: abre a folha inferior "Mais opções" (6.8) com uma linha por área (altura mínima 64 px; ícone `--icon-lg` num quadrado de 44 px, raio `--radius`, fundo `--primary-soft`, cor `--primary`; nome em `--text-body` `--weight-bold`; dica de uma linha em `--text-small` `--muted-foreground`; seta à direita) e o botão "Sair da conta" (altura 52 px, raio `--radius`, borda `--line-control` `--border`, texto `--destructive` `--weight-bold`).
- Conteúdo: `padding: var(--space-18) var(--page-x) calc(var(--tabbar) + var(--space-32) + env(safe-area-inset-bottom))`.
