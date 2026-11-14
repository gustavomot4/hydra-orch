## 9. Acessibilidade

Piso: WCAG 2.2 AA.

### 9.1 Contraste

Calculado pela fórmula de luminância relativa da WCAG a partir dos tokens da seção 2. Onde há transparência, a cor foi composta sobre o fundo indicado. Na hachura, a listra clara (`rgba(255, 255, 255, .55)`) foi composta sobre o fundo da situação, e o fundo sem listra também está na tabela. Texto de controle desabilitado não entra, como a WCAG permite.

| Par | Texto | Fundo | Razão | Texto normal (4,5) | Texto grande e UI (3,0) |
| --- | --- | --- | --- | --- | --- |
| Texto sobre página | `--foreground` #1B2529 | `--background` #F6F2EC | 14,01:1 | passa | passa |
| Texto sobre superfície | `--foreground` #1B2529 | `--card` #FFFFFF | 15,63:1 | passa | passa |
| Texto sobre superfície recuada | `--foreground` #1B2529 | `--card-soft` #FBF8F4 | 14,76:1 | passa | passa |
| Texto sobre hover neutro | `--foreground` #1B2529 | `--muted` #EEE8DF | 12,83:1 | passa | passa |
| Texto sobre seleção suave (linha selecionada, ilustração da entrada) | `--foreground` #1B2529 | `--primary-soft` #E1F0EC | 13,30:1 | passa | passa |
| Secundário sobre página (subtítulo, ajuda da entrada) | `--muted-foreground` #5B676C | `--background` #F6F2EC | 5,22:1 | passa | passa |
| Secundário sobre superfície (segunda linha, eixo, dica) | `--muted-foreground` #5B676C | `--card` #FFFFFF | 5,83:1 | passa | passa |
| Secundário sobre superfície recuada (rótulo de dado, "Sem consultas", dia de outro mês) | `--muted-foreground` #5B676C | `--card-soft` #FBF8F4 | 5,50:1 | passa | passa |
| Secundário sobre neutro (segmentado, campo desabilitado, selo neutro) | `--muted-foreground` #5B676C | `--muted` #EEE8DF | 4,78:1 | passa | passa |
| Secundário sobre seleção suave | `--muted-foreground` #5B676C | `--primary-soft` #E1F0EC | 4,96:1 | passa | passa |
| Texto de exemplo no campo | `--placeholder` #6B7579 | `--card` #FFFFFF | 4,72:1 | passa | passa |
| Primária sobre superfície (link, letra da lista, próxima etapa) | `--primary` #0D6E66 | `--card` #FFFFFF | 6,10:1 | passa | passa |
| Primária sobre página (link de volta) | `--primary` #0D6E66 | `--background` #F6F2EC | 5,47:1 | passa | passa |
| Primária sobre seleção suave (aba ativa, botão suave, selo, coluna de hoje) | `--primary` #0D6E66 | `--primary-soft` #E1F0EC | 5,19:1 | passa | passa |
| Primária no cartão fantasma (coluna de hoje) | `--primary` #0D6E66 | `--primary-soft` 85% sobre `--today-column` #E4F2EE | 5,28:1 | passa | passa |
| Botão primário, página atual, horário escolhido, dia de hoje | `--primary-foreground` #FFFFFF | `--primary` #0D6E66 | 6,10:1 | passa | passa |
| Botão primário em hover | `--primary-foreground` #FFFFFF | `--primary-hover` #0A5C55 | 7,85:1 | passa | passa |
| Secundário sobre primária (dia da semana de hoje, indicador em destaque) | `--on-primary-muted` #CDEBE6 | `--primary` #0D6E66 | 4,83:1 | passa | passa |
| Botão de conversa | `--on-dark` #FFFFFF | `--whatsapp` #187A43 | 5,37:1 | passa | passa |
| Botão de conversa em hover | `--on-dark` #FFFFFF | `--whatsapp-hover` #136437 | 7,22:1 | passa | passa |
| Perigo sobre superfície (botão de perigo, erro de campo, Sair) | `--destructive` #B23B3B | `--card` #FFFFFF | 5,86:1 | passa | passa |
| Perigo sobre perigo suave (hover, alerta, selo) | `--destructive` #B23B3B | `--destructive-soft` #FBE7E7 | 4,93:1 | passa | passa |
| "Agora" na lista | `--accent-text` #B9472A | `--card` #FFFFFF | 5,25:1 | passa | passa |
| Etiqueta da hora atual na grade | `--on-dark` #FFFFFF | `--accent-text` #B9472A | 5,25:1 | passa | passa |
| Claro sobre escuro (chip escolhido, aviso, cartão Próximo, balão) | `--on-dark` #FFFFFF | `--foreground` #1B2529 | 15,63:1 | passa | passa |
| Botão escuro em hover | `--on-dark` #FFFFFF | `--foreground-hover` #0F171A | 18,13:1 | passa | passa |
| Rótulo PRÓXIMO | `--on-dark-accent` #8EE3D6 | `--foreground` #1B2529 | 10,50:1 | passa | passa |
| Secundário sobre escuro (contagem do chip escolhido, aviso, balão) | `--on-dark-muted` #C9D2D5 | `--foreground` #1B2529 | 10,17:1 | passa | passa |
| Desfazer | `--on-dark-accent` #8EE3D6 | `--on-dark-fill` sobre `--foreground` #363F43 | 7,22:1 | passa | passa |
| WhatsApp no cartão Próximo | `--on-dark` #FFFFFF | `--on-dark-fill` sobre `--foreground` #363F43 | 10,74:1 | passa | passa |
| Iniciar atendimento no cartão Próximo | `--foreground` #1B2529 | `--on-dark-accent` #8EE3D6 | 10,50:1 | passa | passa |
| Selo e alerta de sucesso | `--success` #1D7A45 | `--success-soft` #E2F3E8 | 4,64:1 | passa | passa |
| Selo e alerta de aviso | `--warning` #7A5000 | `--warning-soft` #FFF1D2 | 6,30:1 | passa | passa |
| Selo e alerta de informação | `--info` #2F5E9E | `--info-soft` #E5EDF8 | 5,53:1 | passa | passa |
| Pílula Agendado, lembrete de confirmação, hora no cartão Agendado | `--status-agendado-fg` #7A5000 | `--status-agendado-bg` #FFFFFF | 7,05:1 | passa | passa |
| Pílula Confirmado, hora no cartão | `--status-confirmado-fg` #17663B | `--status-confirmado-bg` #DCF3E5 | 5,99:1 | passa | passa |
| Pílula e cartão Em atendimento | `--status-atendimento-fg` #FFFFFF | `--status-atendimento-bg` #5B45C2 | 6,82:1 | passa | passa |
| Pílula Concluído, hora e nome no cartão | `--status-concluido-fg` #4A5559 | `--status-concluido-bg` #ECEEEF | 6,59:1 | passa | passa |
| Pílula Cancelado, hora no cartão | `--status-cancelado-fg` #A12F2F | `--status-cancelado-bg` #FBE7E7 | 5,96:1 | passa | passa |
| Pílula Cancelado, hora no cartão (listra) | `--status-cancelado-fg` #A12F2F | `--status-cancelado-bg` + listra da `--hatch` #FDF4F4 | 6,56:1 | passa | passa |
| Pílula Faltou, hora no cartão | `--status-faltou-fg` #934010 | `--status-faltou-bg` #FCEBDD | 6,05:1 | passa | passa |
| Pílula Faltou, hora no cartão (listra) | `--status-faltou-fg` #934010 | `--status-faltou-bg` + listra da `--hatch` #FEF6F0 | 6,58:1 | passa | passa |
| Nome no cartão Agendado | `--foreground` #1B2529 | `--status-agendado-bg` #FFFFFF | 15,63:1 | passa | passa |
| Detalhe no cartão Agendado | `--muted-foreground` #5B676C | `--status-agendado-bg` #FFFFFF | 5,83:1 | passa | passa |
| Nome no cartão Confirmado | `--foreground` #1B2529 | `--status-confirmado-bg` #DCF3E5 | 13,39:1 | passa | passa |
| Detalhe no cartão Confirmado | `--muted-foreground` #5B676C | `--status-confirmado-bg` #DCF3E5 | 4,99:1 | passa | passa |
| Detalhe no cartão Em atendimento | `--status-atendimento-muted` #E4DEFB | `--status-atendimento-bg` #5B45C2 | 5,24:1 | passa | passa |
| Detalhe no cartão Concluído | `--muted-foreground` #5B676C | `--status-concluido-bg` #ECEEEF | 5,00:1 | passa | passa |
| Nome e detalhe no cartão Cancelado | `--muted-foreground` #5B676C | `--status-cancelado-bg` #FBE7E7 | 4,91:1 | passa | passa |
| Nome e detalhe no cartão Cancelado (listra) | `--muted-foreground` #5B676C | `--status-cancelado-bg` + listra da `--hatch` #FDF4F4 | 5,40:1 | passa | passa |
| Nome no cartão Faltou | `--foreground` #1B2529 | `--status-faltou-bg` #FCEBDD | 13,44:1 | passa | passa |
| Nome no cartão Faltou (listra) | `--foreground` #1B2529 | `--status-faltou-bg` + listra da `--hatch` #FEF6F0 | 14,61:1 | passa | passa |
| Detalhe no cartão Faltou | `--muted-foreground` #5B676C | `--status-faltou-bg` #FCEBDD | 5,01:1 | passa | passa |
| Detalhe no cartão Faltou (listra) | `--muted-foreground` #5B676C | `--status-faltou-bg` + listra da `--hatch` #FEF6F0 | 5,45:1 | passa | passa |
| Iniciais, tom 0 | `--avatar-1-fg` #8E3A19 | `--avatar-1-bg` #FCE3D6 | 6,17:1 | passa | passa |
| Iniciais, tom 1 | `--avatar-2-fg` #1D6B45 | `--avatar-2-bg` #DDF0E6 | 5,45:1 | passa | passa |
| Iniciais, tom 2 | `--avatar-3-fg` #3446A3 | `--avatar-3-bg` #E3E8FB | 6,74:1 | passa | passa |
| Iniciais, tom 3 | `--avatar-4-fg` #8E2F6B | `--avatar-4-bg` #F7E3EF | 6,20:1 | passa | passa |
| Iniciais, tom 4 | `--avatar-5-fg` #6E4B00 | `--avatar-5-bg` #FFEFC4 | 6,89:1 | passa | passa |
| Iniciais, tom 5 | `--avatar-6-fg` #245D7E | `--avatar-6-bg` #DDEDF6 | 5,95:1 | passa | passa |

Não texto (piso 3:1): contornos de controle, foco, linhas e ícones que carregam informação.

| Elemento | Cor | Fundo | Razão | Passa 3,0 |
| --- | --- | --- | --- | --- |
| Borda de campo sobre superfície | `--input` #8F8577 | `--card` #FFFFFF | 3,62:1 | passa |
| Borda de campo sobre página | `--input` #8F8577 | `--background` #F6F2EC | 3,25:1 | passa |
| Borda de campo sobre superfície recuada | `--input` #8F8577 | `--card-soft` #FBF8F4 | 3,42:1 | passa |
| Foco sobre página | `--ring` #0D6E66 | `--background` #F6F2EC | 5,47:1 | passa |
| Foco sobre superfície | `--ring` #0D6E66 | `--card` #FFFFFF | 6,10:1 | passa |
| Foco sobre superfície recuada | `--ring` #0D6E66 | `--card-soft` #FBF8F4 | 5,76:1 | passa |
| Foco sobre neutro (segmentado) | `--ring` #0D6E66 | `--muted` #EEE8DF | 5,01:1 | passa |
| Foco sobre seleção suave | `--ring` #0D6E66 | `--primary-soft` #E1F0EC | 5,19:1 | passa |
| Foco sobre coluna de hoje | `--ring` #0D6E66 | `--today-column` #F5FAF8 | 5,78:1 | passa |
| Foco em superfície escura | `--ring-on-dark` #8EE3D6 | `--foreground` #1B2529 | 10,50:1 | passa |
| Borda de campo em foco | `--primary` #0D6E66 | `--card` #FFFFFF | 6,10:1 | passa |
| Borda de campo com erro | `--destructive` #B23B3B | `--card` #FFFFFF | 5,86:1 | passa |
| Linha "agora" na coluna de hoje | `--accent` #E8613C | `--today-column` #F5FAF8 | 3,20:1 | passa |
| Ponto "agora" sobre superfície | `--accent` #E8613C | `--card` #FFFFFF | 3,38:1 | passa |
| Barra de entrada no gráfico | `--chart-in` #2E9D67 | `--card` #FFFFFF | 3,42:1 | passa |
| Barra de saída no gráfico | `--chart-out` #E0603C | `--card` #FFFFFF | 3,55:1 | passa |
| Ícone de conversa na lista de pacientes | `--whatsapp` #187A43 | `--whatsapp-soft` #E3F4EA | 4,71:1 | passa |
| Ícone de erro no aviso | `--on-dark-danger` #FFB4A6 | `--foreground` #1B2529 | 9,18:1 | passa |
| Barra Confirmado (apoio) | `--status-confirmado-bar` #1F8A4C | `--status-confirmado-bg` #DCF3E5 | 3,75:1 | passa |
| Contorno Agendado (apoio) | `--status-agendado-bar` #D9940E | `--status-agendado-bg` #FFFFFF | 2,56:1 | reprova |
| Barra Concluído (apoio) | `--status-concluido-bar` #A3ACB0 | `--status-concluido-bg` #ECEEEF | 1,98:1 | reprova |
| Barra Cancelado (apoio) | `--status-cancelado-bar` #D16464 | `--status-cancelado-bg` #FBE7E7 | 3,09:1 | passa |
| Barra Faltou (apoio) | `--status-faltou-bar` #E07B3F | `--status-faltou-bg` #FCEBDD | 2,55:1 | reprova |

As linhas marcadas "apoio" reforçam a situação, que já tem ícone, rótulo escrito e nome acessível; não são o único sinal. As fatias do anel do Painel usam as mesmas cores e têm ao lado a lista com rótulo e número.
