# Persistência de execução — S03 / T03

**Identificador Formal:** `persistencia_execucao.md`
**Caminho Canônico:** `doc/b_spc/persistencia_execucao.md`
**Versão:** `v01_00_0000`
**Status:** `APROVADO / IMPLEMENTADO`
**Autoridade:** Derivado normativo de [`doc/b_spc/prd_tecnico.md`](prd_tecnico.md) (§3.6.6 e §8.1), [`doc/b_spc/prd_funcional.md`](prd_funcional.md) (RF03, RF05), [`doc/d_mer/mer.md`](../d_mer/mer.md) e [`contrato_execucao.md`](contrato_execucao.md) (S02/T02).
**Escopo:** Especificação canônica da camada de persistência transacional em SQLite WAL, motor de migrações versionadas em `migration/`, idempotência de comandos, reconciliação pós-crash e store de execução do núcleo em `src/hydra_orch/core/checkpointer.py`.

---

## 1. Propósito

Formalizar a camada de persistência de dados do **hydra-orch** em SQLite WAL, estabelecendo o esquema relacional canônico do núcleo, o controle de migrações versionadas, a garantia de transação atômica entre mudança de estado e registro de evento, a reconciliação segura após crash/restart e a proteção contra duplicação de execuções via idempotência de comandos.

---

## 2. Justificativa

Os contratos e máquinas de estado estabelecidos em S02/T02 operam puramente em memória. Em um sistema de engenharia de software agêntica, a perda de estado por crash ou reinicialização do processo acarreta efeitos colaterais desastrosos (como commits órfãos, worktrees abandonadas ou execuções duplicadas). A persistência transacional com SQLite WAL garante:
1. **Durabilidade imediata:** Nenhuma confirmação de execução ocorre antes da gravação no log WAL.
2. **Atomicidade estado + evento (RT03):** O estado da entidade (ex.: tarefa `ready_for_review`, run `running`) e o evento correspondente (`RunEvent`) são gravados na mesmíssima transação física (`BEGIN IMMEDIATE`).
3. **Idempotência (RF03 / RT03):** Submissões com a mesma `Idempotency-Key` e payload idêntico retornam o registro existente sem reexecutar; submissões com mesma chave e payload diferente são rejeitadas com `IdempotencyConflictError` (mapeado para HTTP 409).
4. **Isolamento e integridade referencial (RT11):** Foreign Keys ativas (`PRAGMA foreign_keys = ON`) e índice parcial único de tentativa ativa por tarefa impedem corrupção de grafos de tarefas, artefatos desconexos, tentativas órfãs ou concorrência ilegal na mesma tarefa.

---

## 3. Contrato

### 3.1. Pragmas Obrigatórios de Conexão
Toda conexão com o banco SQLite aberta pelo store executa imediatamente:
```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
```

### 3.2. Infraestrutura de Migrações em `migration/`
- As alterações de DDL são armazenadas como scripts SQL ordenados e versionados em `migration/` na raiz do repositório (`0001_initial_core.sql`).
- O controle de migrações aplicadas é mantido na tabela `schema_migrations`:
  ```sql
  CREATE TABLE IF NOT EXISTS schema_migrations (
      version TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      checksum TEXT NOT NULL,
      applied_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```
- O runner de migração descobre arquivos `.sql` em `migration/`, ordena alfanumericamente, calcula o hash SHA-256 (`checksum`, com finais de linha normalizados para LF) do script e aplica em transação exclusiva (`BEGIN IMMEDIATE`) aqueles cuja versão ainda não consta em `schema_migrations`. Caso uma versão já aplicada apresente `checksum` divergente do arquivo em disco, lança `MigrationError`.
- **Preservação de banco legado:** Tabelas legadas de streaming (`checkpoints`, `provider_limits`, `active_generations`, `quota_status`) são preservadas intactas. Caso um banco legado pré-existente contenha a tabela antiga `handoff_checkpoints` (sem coluna `attempt_id`), o migrador a preserva renomeando-a para `legacy_handoff_checkpoints` antes de criar a tabela canônica `handoff_checkpoints`.

### 3.3. Esquema Relacional do Núcleo (V0 / M1)
Conforme definido em `prd_tecnico.md §3.6.6` e `mer.md §3`, as seguintes tabelas compõem o esquema canônico da T03:

1. **`projects`**: Registro do repositório por caminho canônico (`canonical_root` UNIQUE).
2. **`runs`**: Identidade do run, referência ao projeto (`project_id` `ON DELETE RESTRICT`), snapshot de `RunSpec` (`spec_json`), `base_sha`, status (`RunStatus`) e revisão otimista (`revision`).
3. **`tasks`**: Identidade da tarefa vinculada ao run (`run_id` `ON DELETE CASCADE`), snapshot de `TaskSpec` (`spec_json`), status (`TaskStatus`) e revisão otimista (`revision`).
4. **`task_dependencies`**: Arestas do DAG entre tarefas (`task_id`, `prerequisite_id`), com restrição `CHECK (task_id != prerequisite_id)`.
5. **`attempts`**: Tentativas de execução por tarefa, ordinal sequencial (`task_id`, `ordinal` UNIQUE), executor, status do processo (`ProcessStatus`) e índice parcial único `idx_attempts_active_task` para estados `queued`/`running`.
6. **`workspaces`**: Worktrees isoladas vinculadas a cada tentativa (`attempt_id` UNIQUE, `canonical_path` UNIQUE).
7. **`artifacts`**: Artefatos gerados pelo run ou tentativa com hash SHA-256 e tamanho em bytes (`UNIQUE (run_id, relative_path)`).
8. **`results`**: Resultados de tentativas (`TaskResult`) com código de saída, flag `simulated`, `outcome`, `task_status`, `process_status`, sumário, referência de patch e revisão otimista.
9. **`integrations`** e **`integration_items`**: Ordens de integração serializada em branches dedicadas.
10. **`check_results`**: Resultados de comandos de verificação/teste vinculados exclusivamente a um `result_id` ou `integration_id`.
11. **`reviews`**: Decisões explícitas de aceitação/rejeição (`ReviewDecision`) com ator, motivo e `expected_revision`.
12. **`events`**: Eventos append-only com sequência estritamente monotônica por run (`UNIQUE (run_id, seq)`), tipo (`RunEvent.event_type`), correlação e payload JSON redigido.
13. **`handoff_checkpoints`**: Preservação estruturada de estado Git, diffs, ferramentas executadas e próximo passo por tentativa (`attempt_id` UNIQUE).
14. **`commands`**: Registro de comandos para idempotência (`scope`, `idempotency_key`, `request_hash`, `run_id`, `status`).
15. **`budget_policies`**: Tetos de orçamento por run (USD, tokens, tempo) com status operacional.
16. **`metric_samples`**: Amostras de telemetria com status `observed`/`stale`/`unknown` (nunca inventando zero para `unknown`).
17. **`route_decisions`**: Decisões de roteamento e cadeia de fallback auditáveis.
18. **`pr_packages`**: Pacotes de Pull Request vinculados ao run (`run_id` UNIQUE).

### 3.4. Interfaces do Store em `src/hydra_orch/core/checkpointer.py`
A classe `ExecutionStore` (unificada com `StreamCheckpointer` para manter 100% de compatibilidade com consumidores existentes) provê:
- `initialize(apply_migrations: bool = True) -> None`: Prepara o diretório, aplica pragmas WAL/FK/busy_timeout e executa migrações pendentes de `migration/`.
- `get_applied_migrations() -> List[Dict[str, Any]]`: Lista as migrações aplicadas com versão, nome, checksum e timestamp.
- `record_command(idempotency_key: str, request_hash: str, run_id: Optional[str] = None, scope: str = "run", response_payload: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]`: Registra um comando idempotente ou retorna `(False, existing_run_id)` se a chave já existir com o mesmo `request_hash`. Se o `request_hash` divergir, lança `IdempotencyConflictError`.
- `submit_run_idempotent(run_spec: RunSpec, request_hash: Optional[str] = None, initial_status: RunStatus = RunStatus.QUEUED) -> Tuple[bool, Dict[str, Any]]`: Submete um `RunSpec` garantindo que duas submissões idênticas retornem o mesmo run sem duplicar registros ou eventos, e que payload divergente na mesma `idempotency_key` lance `IdempotencyConflictError`.
- `save_run_atomic(run_spec: RunSpec, initial_status: Union[RunStatus, str] = RunStatus.QUEUED, correlation_id: Optional[str] = None) -> Dict[str, Any]`: Persiste projeto, run, política de orçamento, tarefas (`TaskSpec`), arestas de dependência (`task_dependencies`), comando de idempotência e o evento inicial `run.created` (`seq=1`) na mesma transação atômica.
- `record_event_atomic(run_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None, task_id: Optional[str] = None, attempt_id: Optional[str] = None) -> RunEvent`: Aloca o próximo `seq` monotônico para o `run_id`, valida com `RunEvent` e persiste em transação.
- `update_run_status_atomic(run_id: str, new_status: Union[RunStatus, str], expected_revision: int, event_type: str, event_payload: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None) -> Dict[str, Any]`: Valida transição de `RunStatus` via `transition_status`, aplica controle otimista (`expected_revision`) e grava estado + evento na mesma transação.
- `update_task_status_atomic(task_id: str, new_status: Union[TaskStatus, str], expected_revision: int, event_type: str, event_payload: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None, attempt_id: Optional[str] = None) -> Dict[str, Any]`: Valida transição de `TaskStatus` via `transition_status`, aplica controle otimista (`expected_revision`) e grava estado + evento na mesma transação.
- `save_attempt_atomic(attempt: TaskAttempt, event_type: str = "attempt.started", event_payload: Optional[Dict[str, Any]] = None) -> TaskAttempt`: Registra ou atualiza tentativa validando transições e unicidade de tentativa ativa por tarefa, gravando o evento correlacionado na mesma transação.
- `save_artifact(artifact: Union[Artifact, Dict[str, Any]]) -> Artifact`: Persiste metadados e hash SHA-256 de artefato vinculado ao run/tentativa.
- `save_task_result_atomic(task_spec: TaskSpec, attempt: TaskAttempt, result: TaskResult, expected_task_revision: Optional[int] = None) -> TaskResult`: Valida atribuição via `validate_result`, persiste artefatos, checks, resultado, atualiza o status da tarefa e emite o evento correspondente na mesma transação.
- `record_review_atomic(task_spec: TaskSpec, attempt: TaskAttempt, decision: ReviewDecision, expected_task_revision: Optional[int] = None) -> TaskResult`: Valida revisão via `review_result` (controle otimista de revisão do resultado e da tarefa), grava registro em `reviews`, atualiza `results` e `tasks` e emite `task.accepted` ou `task.rejected` na mesma transação.
- `save_handoff_checkpoint_atomic(checkpoint: HandoffCheckpoint, run_id: str) -> HandoffCheckpoint`: Persiste `HandoffCheckpoint` e emite `attempt.handoff_created` atomicamente.
- `reconcile_interrupted_attempts(run_id: Optional[str] = None, reason: str = "process_interrupted_on_restart") -> List[Dict[str, Any]]`: Reconciliação pós-crash — localiza tentativas que ficaram em `queued` ou `running` após queda do processo, transiciona-as para `crashed` (ou `cancelled` quando `queued`), marca tarefas `running` correspondentes como `blocked` para exigir reconciliação sem repetir efeitos cegamente e emite eventos auditáveis na mesma transação.
- Consultas: `get_pragmas`, `get_run`, `get_task`, `list_tasks`, `get_attempt`, `list_attempts`, `get_result`, `get_result_by_attempt`, `get_artifacts`, `get_handoff_checkpoint`, `get_events`.

---

## 4. Pré-condições

1. Contratos `model.py` implementados e testados (T02 concluído).
2. Caminho do banco de dados (`.orchestrator/checkpoints.sqlite` por padrão) em diretório com permissão de escrita.
3. `aiosqlite` disponível no ambiente Python.

---

## 5. Pós-condições

1. O banco SQLite opera em modo WAL (`journal_mode=wal`) com `foreign_keys=1` e `busy_timeout=5000`.
2. Toda mutação de estado de run, tarefa, tentativa, resultado ou revisão que emite evento persiste ambos em transação única (`BEGIN IMMEDIATE`).
3. Qualquer exceção ou violação de contrato durante uma operação composta executa `ROLLBACK`, não deixando estado atualizado sem evento nem evento órfão sem estado.
4. Após restart do processo (nova instância de `ExecutionStore` sobre o mesmo arquivo SQLite), todos os runs, tarefas, tentativas, artefatos, resultados, revisões e eventos confirmados permanecem íntegros, e tentativas interrompidas são reconciliáveis de forma determinística.
5. Replay de eventos (`get_events(run_id, after_seq)`) retorna sequência estritamente crescente sem lacunas ou duplicatas.

---

## 6. Invariantes

1. **Invariante de Sequência Monotônica:** Para qualquer `run_id`, os eventos possuem `seq` iniciando em `1` e incrementando de `1` em `1`, protegidos por `UNIQUE (run_id, seq)`.
2. **Invariante de Atomicidade Estado-Evento:** Nenhuma transição de status em `runs` ou `tasks` é confirmada sem seu `RunEvent` na mesma transação.
3. **Invariante de Idempotência:** Chaves de idempotência reutilizadas no mesmo `scope` com payload idêntico nunca duplicam runs; com payload diferente geram `IdempotencyConflictError` e preservam o registro original.
4. **Invariante de Integridade Referencial:** Inserções com FKs inexistentes ou duas tentativas simultaneamente ativas (`queued`/`running`) para a mesma tarefa falham imediatamente no SQLite.
5. **Invariante de Separação de Domínios:** Checkpoints técnicos (`handoff_checkpoints` / `checkpoints`) permanecem isolados de memória adaptativa (que só entrará em V4 mediante `ConsentRecord`).

---

## 7. Falhas e Tratamento de Exceções

- `StorageError` (`ContractViolation`): Classe base de erros da camada de persistência.
- `IdempotencyConflictError` (`code="idempotency_conflict"`): Mesma `idempotency_key` submetida no mesmo `scope` com `request_hash` diferente.
- `OptimisticLockError` (`code="optimistic_lock_conflict"`): `expected_revision` divergente da revisão atual da entidade (`runs`, `tasks` ou `results`).
- `StorageIntegrityError` (`code="storage_integrity_error"`): Violação de chave estrangeira, unicidade ou `CHECK` constraint do SQLite.
- `StorageLockError` (`code="storage_lock_error"`): Bloqueio persistente do banco SQLite após esgotar `busy_timeout = 5000` ms.
- `MigrationError` (`code="migration_error"`): Script de migração corrompido, SQL inválido ou divergência de checksum de migração já aplicada.

---

## 8. Procedimento e Aceite

1. **Execução de Migrações:** `ExecutionStore.initialize()` cria `schema_migrations`, aplica `migration/0001_initial_core.sql` e preserva tabelas legadas.
2. **Testes Herméticos (`tests/test_checkpointer.py`):**
   - Pragmas WAL, `foreign_keys=ON` e `busy_timeout=5000` verificados.
   - Idempotência: repetição de mesmo payload retorna mesmo run sem duplicar; payload divergente levanta `IdempotencyConflictError`.
   - Atomicidade: falha injetada durante atualização de status + evento reverte ambos via `ROLLBACK`.
   - Concorrência otimista: revisão obsoleta levanta `OptimisticLockError`.
   - Transições inválidas de estado rejeitadas via `InvalidTransitionError`.
   - Foreign keys ativas e índice parcial de tentativa ativa única por tarefa comprovados.
   - Ciclo completo de persistência (`RunSpec` → `TaskAttempt` → `Artifact` → `TaskResult` → `ReviewDecision` → `HandoffCheckpoint`) + restart de store + reconciliação pós-crash + replay SSE por cursor `after_seq`.
   - Compatibilidade retroativa integral com `StreamCheckpointer` e `EngineCheckpointer`.
3. **Gate de Cobertura:** $\ge 80\%$ em `src/hydra_orch/core/checkpointer.py` e 100% da suíte `pytest tests` aprovada offline.

---

## 9. Exemplos

### 9.1. Submissão Idempotente e Transação Atômica Estado + Evento
```python
store = ExecutionStore(db_path=str(tmp_path / "checkpoints.sqlite"))
await store.initialize()

created, run_record = await store.submit_run_idempotent(run_spec)
assert created is True

# Segunda chamada com mesmo RunSpec / idempotency_key não duplica o run nem emite novo evento
created_again, same_record = await store.submit_run_idempotent(run_spec)
assert created_again is False
assert same_record["id"] == run_record["id"]
```

### 9.2. Replay Ordenado por Cursor (`after_seq`)
```python
events = await store.get_events(run_id=run_spec.run_id, after_seq=1)
assert [event.seq for event in events] == list(range(2, len(events) + 2))
```
