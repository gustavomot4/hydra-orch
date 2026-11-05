# Contrato de execução verificável

## Objetivo

Padronizar a comunicação entre o control plane do Hydra, executores de agentes, OmniRoute opcional e a futura interface visual. Este contrato evita tratar texto produzido por um modelo como trabalho de engenharia comprovado.

## Entidades propostas

| Entidade | Responsabilidade | Estado mínimo |
| --- | --- | --- |
| `RunSpec` | Execução completa iniciada pelo usuário | objetivo, repositório, branch base, orçamento, modo |
| `TaskSpec` | Unidade delimitada entregue a um executor | objetivo, critérios de aceite, dependências, arquivos permitidos, worktree e executor |
| `TaskAttempt` | Uma tentativa concreta de uma tarefa | provedor, modelo, sessão, início, fim e motivo de término |
| `TaskResult` | Resultado verificável da tentativa | status do processo, status da tarefa, patch/commit, checks, artefatos e risco |
| `RunEvent` | Linha do tempo persistida | sequência, timestamp, tipo, correlação e payload sem segredo |
| `HandoffCheckpoint` | Contexto independente de provedor | decisões, estado Git, arquivos afetados, ferramentas, saída parcial e pendências |

## Estados

O processo e a tarefa têm estados separados:

```text
processo: queued -> running -> exited | timed_out | cancelled | crashed
tarefa:   pending -> running -> needs_context | blocked | failed | ready_for_review -> accepted | rejected
```

`exited` com código zero não implica `accepted`. Um resultado simulado, uma resposta vazia ou a ausência de patch/checks deve ser identificado como tal e não pode avançar para merge automático.

## Requisitos para integrar uma tarefa

1. A tentativa deve terminar em estado observável e persistido.
2. O resultado deve indicar se a execução foi real ou simulada.
3. Alterações precisam ser atribuíveis à worktree/branch da tarefa.
4. Checks definidos em `TaskSpec` precisam ter saída e código de término registrados.
5. O merge precisa registrar sucesso ou conflito antes de limpeza da worktree.
6. Em falha, os artefatos ficam preservados até uma decisão explícita de descarte.

## Handoff entre provedores

O handoff não pode depender apenas das últimas linhas de texto. Deve carregar o objetivo original, critérios de aceite, decisões tomadas, estado Git, arquivos modificados, comandos/checks executados, saída parcial, limite detectado e o próximo passo. A âncora textual serve apenas para continuidade de geração, não como fonte completa de verdade.

## Eventos mínimos para a interface visual

- `run.created`, `run.started`, `run.finished`
- `task.queued`, `task.started`, `task.needs_context`, `task.completed`, `task.failed`
- `attempt.provider_selected`, `attempt.rate_limited`, `attempt.handoff_created`
- `artifact.created`, `check.finished`, `merge.completed`, `merge.conflicted`

Os eventos devem ser sequenciais por execução e seguros para expor à UI: credenciais, prompts com segredos e logs brutos devem permanecer protegidos ou redigidos.
