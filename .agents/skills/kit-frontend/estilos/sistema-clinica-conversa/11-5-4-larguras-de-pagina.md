### 5.4 Larguras de página

| Página | Largura máxima | Uso |
| --- | --- | --- |
| Inteira | `--page-max` | Hoje, Agenda, listas, Painel |
| Formulário | `--page-form` | Cadastro e edição |
| Larga | `--page-wide` | Agendar consulta (formulário com resumo ao lado) |

Formulário e página larga ficam centralizados, com o cabeçalho na mesma coluna do conteúdo. Grade de campos: 2 colunas, espaço `--space-16` entre linhas e `--space-18` entre colunas; campo que ocupa a linha inteira usa `grid-column: 1 / -1`.

Cabeçalho de tela: título à esquerda e ações à direita, alinhados pela base, `flex-wrap: wrap`, espaço `--space-16` entre linhas e `--space-24` entre colunas, margem inferior `--space-20` (`--space-16` abaixo de 768 px). Subtítulo, quando houver, em `--text-body` `--muted-foreground`, `margin-top: var(--space-4)`. Link de volta acima do título: seta `arrow-left` `--icon-md`, texto `--text-ui` `--weight-semibold`, altura mínima `--target`.
