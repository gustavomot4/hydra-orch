## 4. Cor e situações

Tema claro somente. Fundo de papel quente, superfícies brancas, verde-petróleo para ação e coral só para marcar o momento atual.

### 4.1 Papel de cada cor

| Token | Papel | Pode aparecer | Não pode |
| --- | --- | --- | --- |
| `--background` | Página | Fundo da página; barra superior do celular; caixa de ajuda da tela Entrar; degradê do rodapé fixo de formulário | — |
| `--card` | Superfície | Barra superior, barra de abas, cartão, lista, campo, painel, folha, diálogo, chip inativo | — |
| `--card-soft` | Superfície recuada | Hover de linha; caixa de dados do detalhe; coluna sem consulta e coluna de dia passado na grade; dia de outro mês | Fundo de campo |
| `--muted` | Neutro de apoio | Hover de botão fantasma, aba e item de menu; fundo do segmentado; campo desabilitado; trilho de barra de progresso; esqueleto | Texto |
| `--foreground` | Texto principal e superfície escura | Todo texto principal; fundo do chip escolhido, do cartão "Próximo", do aviso, do balão do gráfico e do botão de confirmação destrutiva | — |
| `--muted-foreground` | Texto secundário | Segunda linha, dica, duração, rótulo opcional, contagem, eixo de gráfico, texto de estado vazio | Ação, link |
| `--placeholder` | Texto de exemplo | Só dentro de campo vazio | Rótulo, dica |
| `--border` | Divisória | Contorno de cartão, lista, chip inativo, botão secundário, linha de hora da grade | Borda única de campo |
| `--border-strong` | Divisória reforçada | Hover de botão secundário, alça da folha inferior, linha de base do gráfico, risco do nome cancelado | Borda de campo |
| `--input` | Borda de controle | Campo, combobox, lista de seleção | Cartão |
| `--primary` | Ação e seleção | Botão primário, link, aba ativa, linha selecionada, dia de hoje, página atual, etapa concluída, horário escolhido | Texto decorativo |
| `--primary-soft` | Seleção suave | Fundo da aba ativa, da linha selecionada, do cabeçalho da coluna de hoje e do botão suave; halo de foco do campo; círculo do ícone de estado vazio | — |
| `--on-primary-muted` | Texto secundário sobre `--primary` | Dia da semana no dia de hoje da faixa; rótulo e dica do indicador em destaque | Sobre fundo claro |
| `--on-dark-accent`, `--on-dark-muted`, `--on-dark-danger`, `--on-dark-fill` | Sobre `--foreground` | Rótulo "PRÓXIMO", botão do cartão "Próximo", ação do aviso, ícone do aviso; texto secundário; ícone de aviso de erro; fundo de botão secundário | Sobre fundo claro |
| `--accent` | Agora | Linha e ponto "agora" | Texto (3,38:1) |
| `--accent-text` | Texto do agora | Palavra "Agora" na lista; fundo da etiqueta da hora atual na grade | — |
| `--accent-soft` | Halo do agora | Halo do ponto "agora"; círculo decorativo da tela Entrar | Texto |
| `--destructive`, `--destructive-soft` | Erro e perigo | Erro de campo, borda de campo inválido, texto do botão de perigo, alerta e selo de erro | Ação comum |
| `--warning`, `--success`, `--info` e os `-soft` | Retorno | Alertas e selos do tom | Situação da consulta |
| `--whatsapp`, `--whatsapp-hover`, `--whatsapp-soft` | Canal de contato | Só o botão que abre a conversa com o paciente | Qualquer outra ação |
| `--chart-in`, `--chart-out`, `--chart-grid` | Gráfico de dinheiro | Barra de entrada (verde), barra de saída (coral), linha de grade | Texto |
| `--today-column`, `--grid-half`, `--slot-edge` | Agenda em grade | Fundo da coluna de hoje; linha da meia hora; borda clara de 1 px do cartão da consulta | — |
| `--avatar-1-bg` a `--avatar-6-bg` e `--avatar-1-fg` a `--avatar-6-fg` | Iniciais das pessoas | Fundo e texto do círculo de iniciais (4.2) | Situação da consulta; texto fora das iniciais |
| `--overlay` | Véu | Atrás do diálogo, do painel lateral e da folha inferior | Atrás da coluna de detalhe da Agenda (ela não cobre a página) |
