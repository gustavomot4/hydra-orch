## 5. Layout

### 5.1 Pontos de quebra

Media queries não leem variáveis; use estes valores exatos em `max-width`.

| Abaixo de | O que muda |
| --- | --- |
| 1280 px | Abas da barra superior com `padding: 0 11px` e espaço `--space-18` entre blocos; menu da conta só com as iniciais. Detalhe da tela Hoje com `--side-narrow`. Legenda da grade some. O detalhe da consulta na Agenda deixa de ser coluna e abre como painel por cima, com véu (6.8). Indicadores do Painel em 2 colunas; blocos do Painel em 1 coluna. |
| 1100 px | Casca do celular (5.3): barra compacta em cima e barra de abas embaixo. A ação principal vira botão flutuante. O detalhe da tela Hoje deixa de ficar ao lado e abre ao tocar na consulta. O resumo do agendamento vira barra fixa acima das abas. O aviso e o rodapé de formulário sobem acima das abas. A situação na lista do dia vira a pílula compacta (4.3, 6.5). |
| 900 px | O painel lateral vira folha inferior. A agenda troca Semana por 3 dias e passa a abrir em Dia. A grade usa eixo de 46 px e hora de 68 px. A tela Entrar esconde a ilustração. |
| 768 px | `--page-x` passa a 16 px (já no bloco de tokens). Título da tela em `--text-display-sm`. Formulários em 1 coluna. Cabeçalho de colunas das listas some. Cartão com `padding: var(--space-16)`. Linha de paciente só com iniciais, nome e WhatsApp. Botões do rodapé de formulário dividem a largura. |
| 600 px | Linha da lista do dia com colunas de 50 e 44 px e espaço `--space-10` (6.5); paginação compacta; ações do cartão "Próximo" em largura total, com os botões de `padding` `--space-12` (6.6); aviso em duas linhas (6.10); alerta com a ação embaixo; células do mês com 64 px. |
| 480 px | Botões do diálogo de confirmação dividem a largura. |
| Altura até 480 px | Tudo o que é fixo rola junto com a página: barra superior, barra de abas, botão flutuante, aviso, rodapé de formulário, barra de resumo e coluna de detalhe da Hoje passam a `position: static`. Diálogo, painel e folha, que a pessoa abre e fecha, continuam fixos. A Agenda perde a altura fixa e a rolagem própria da grade. Em 320 × 256, só a barra superior e a de abas fixas já cobririam 53% da janela. |

Tamanhos de conferência: 1440 × 900, 1366 × 768, 1024 × 768, 768 × 1024, 375 × 812, 320 × 568 e 320 × 256 (zoom de 400% em 1280 × 1024), mais zoom de 200% em 1280 × 720. Nenhum deles tem rolagem horizontal na página, e o `body` não tem `min-width`: abaixo de 320 px o conteúdo quebra, não rola.
