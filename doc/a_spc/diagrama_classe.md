# Diagrama de classes

Status: modelo alvo proposto, não engenharia reversa das classes atuais. Contratos em [PRD técnico](prd_tecnico.md); persistência em [MER](mer.md).

## 1. Propósito

Definir entidades, serviços e interfaces para execução verificável.

## 2. Justificativa

Separar dados, decisões e transporte permite testar sem contas externas e consolidar os motores existentes.

## 3. Contrato estrutural

```mermaid
classDiagram
    class Project {
        +str id
        +str repo_root
    }
    class RunSpec {
        +str schema_version
        +str id
        +str base_sha
        +str objective
        +str mode
    }
    class Budget {
        +int max_attempts
        +int max_wall_seconds
        +int max_concurrency
    }
    class TaskSpec {
        +str id
        +str objective
        +str contract_hash
        +list allowed_paths
        +list acceptance_criteria
    }
    class TaskAttempt {
        +str id
        +str process_state
        +str provider_session
        +str executor_id
        +str model
    }
    class Workspace {
        +str id
        +str path
        +str base_sha
        +str branch
        +str state
    }
    class TaskResult {
        +str id
        +int exit_code
        +bool simulated
        +str summary
        +str outcome
    }
    class CheckResult {
        +str id
        +str scope
        +str tested_sha
        +int exit_code
    }
    class Artifact {
        +str id
        +str relative_path
        +str sha256
        +int size_bytes
    }
    class ReviewDecision {
        +str decision
        +str reason
        +str actor
        +int expected_revision
    }
    class Integration {
        +str id
        +str expected_base_sha
        +str result_sha
        +str state
    }
    class RunEvent {
        +int seq
        +str type
        +dict payload
    }
    class HandoffCheckpoint {
        +str id
        +str git_sha
        +dict context
        +list tool_effects
    }
    class RunService {
        +submit(spec)
        +cancel(run_id)
        +review(result_id, revision)
        +integrate(run_id)
    }
    class Scheduler {
        +validate_dag(tasks)
        +next_ready(run_id)
    }
    class ExecutionStore {
        <<interface>>
        +save_transition(state, event)
        +events_after(run_id, seq)
    }
    class AgentExecutor {
        <<interface>>
        +capabilities()
        +execute(task, workspace)
        +cancel(attempt_id)
    }
    class CliExecutor {
        +execute(task, workspace)
        +cancel(attempt_id)
    }
    class InferenceProvider {
        <<interface>>
        +generate_stream(messages)
    }
    class GitWorkspaceService {
        +create(base_sha)
        +capture_diff(workspace)
        +integrate(results)
        +cleanup(workspace)
    }
    class ValidationService {
        +check_scope(result)
        +run_checks(workspace)
        +evaluate_acceptance(result)
    }
    Project "1" --> "0..*" RunSpec : possui
    RunSpec "1" *-- "1" Budget
    RunSpec "1" *-- "1..*" TaskSpec
    TaskSpec "0..*" --> "0..*" TaskSpec : depende de
    TaskSpec "1" --> "0..*" TaskAttempt
    TaskAttempt "1" --> "0..1" Workspace
    TaskAttempt "1" --> "0..1" TaskResult
    TaskAttempt "1" --> "0..*" HandoffCheckpoint
    TaskResult "1" --> "0..*" CheckResult
    TaskResult "1" --> "0..*" Artifact
    TaskResult "1" --> "0..*" ReviewDecision
    Integration "0..*" --> "1..*" TaskResult : inclui aceitos
    Integration "1" --> "0..*" CheckResult
    RunSpec "1" --> "0..*" Integration
    RunSpec "1" --> "0..*" RunEvent
    AgentExecutor <|.. CliExecutor
    RunService --> ExecutionStore
    RunService --> Scheduler
    RunService --> AgentExecutor
    RunService --> GitWorkspaceService
    RunService --> ValidationService
    Scheduler ..> InferenceProvider : planejamento opcional
```

RunSpec/TaskSpec são snapshots imutáveis. Estado operacional e revisão pertencem aos registros Run/Task no MER; não alterar o snapshot para registrar progresso. TaskResult é evidência imutável, ReviewDecision é decisão posterior. Métodos ilustram responsabilidades; assinaturas Python completas serão fixadas nas specs de módulo.

## 4. Pré-condições

Run possui projeto e pelo menos uma tarefa; dependências pertencem ao mesmo run. Attempt pode existir sem workspace quando preparação falha.

## 5. Pós-condições

Tentativa terminada produz resultado ou falha de persistência explicitamente reconciliável. Checks de integração pertencem à combinação, não substituem checks da tentativa.

## 6. Invariantes

No máximo uma tentativa ativa por tarefa. Integração inclui apenas resultados aceitos e reais. Serviço de aplicação é o único coordenador das transições. Executor não depende da UI nem decide aceite.

## 7. Falhas

Capability ausente impede dispatch; DAG cíclico impede agendamento; revisão vencida impede aceite. Processo zero sem evidência não atravessa ValidationService.

## 8. Aplicação

T02 implementa entidades; T03 store; T04 executor; T05 workspace; T06 validação/integração; T07 serviço público. Scheduler paralelo entra em S06. Não criar todos os serviços como classes vazias antecipadamente.

## 9. Exemplo

RunService recebe RunSpec, persiste início, solicita workspace e executor, coleta TaskResult, valida e espera ReviewDecision. Após aceite, GitWorkspaceService prepara Integration e ValidationService valida a combinação.
