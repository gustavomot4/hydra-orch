# Workspace do hydra-orch

O espaço de trabalho operacional do checkout é dividido em dois diretórios estritamente ordenados pelo ciclo de vida:

1. **`a_input/`**: Entradas, briefs de tarefas, especificações recebidas e esquemas contratuais versionados.
2. **`b_output/`**: Saídas locais, evidências de testes, logs de orquestração e artefatos de execução.

As entradas em `a_input/` são versionáveis. As saídas em `b_output/` são locais e ignoradas pelo Git (exceto `.gitkeep` e `README.md`).
