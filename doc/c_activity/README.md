# c_activity — Diagramas de Atividades e Fluxos Operacionais

Este diretório concentra especificações de fluxos de processos, diagramas de atividades (BPMN / Activity Diagrams) e sequências de coordenação do **hydra-orch**.

## Conteúdo Planejado

- Diagramas de ciclo de vida de execução de tarefas (`queued` $\rightarrow$ `running` $\rightarrow$ `reviewing` $\rightarrow$ `succeeded`/`failed`).
- Fluxos de handoff estruturado entre provedores e recuperação pós-falha.
- Fluxos de decomposição e integração concorrente de swarm worktrees.
