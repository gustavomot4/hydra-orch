# S10 / M1 — Entrada Unificada M1: CLI e API Control Plane sobre RunService

**Identificador Formal:** `api_control_plane.md`  
**Caminho Canônico:** `doc/b_spc/api_control_plane.md`  
**Versão:** `v01_00_0000`  
**Status:** `IMPLEMENTADO (T07)`  
**Autoridade:** Derivado normativo de [`prd_funcional.md`](prd_funcional.md) (RF01–RF08, RF13, RF15), [`prd_tecnico.md`](prd_tecnico.md) (RT01–RT06, RT10, RT11, §3.7.4, §3.9.1, §3.10, §8.1), [`../f_api/openapi.yaml`](../f_api/openapi.yaml) e [`../g_code/architecture.md`](../g_code/architecture.md).  
**Escopo:** Entrega da Task **T07** (`src/hydra_orch/server.py`, `src/hydra_orch/cli.py`, `src/hydra_orch/core/run_service.py`, `tests/test_server.py`, `tests/test_cli.py`), expondo submissão, consulta, eventos SSE com cursor, revisão otimista, integração serializada, retry, cancelamento e descarte controlado sobre a mesma camada de serviço (`RunService`), com proteção loopback e autenticação local.

---

## 1. Purpose (Propósito)

Estabelecer a superfície unificada de entrada do **Marco M1 (Núcleo Verificável Local)** tanto via API HTTP REST/SSE (`/v1/control-plane/*`) quanto via CLI (`hydra`), garantindo que todas as operações de projeto, execução (`run`), consulta de tarefas/artefatos, replay de eventos (`SSE`), revisão humana (`review`), integração (`integrate`), nova tentativa (`retry`), cancelamento (`cancel`) e descarte (`discard`) consumam exatamente a mesma instância/camada de domínio (`RunService` + `ExecutionStore`), sem caminhos paralelos ou bypass de gates.

---

## 2. Why (Justificativa e Valor Arquitetural)

1. **Unidade de Comando e Estado (Eliminação de Divergência CLI vs. API):** Tanto o operador no terminal quanto clientes HTTP/visuais interagem com o mesmo serviço transacional (`RunService`), impedindo que a CLI ou a API fabriquem estados fora do SQLite WAL ou ignorem validações de `base_sha`, escopo e checks.
2. **Isolamento Loopback e Autenticação Local (R09 / RT10):** O servidor vincula-se por padrão a `127.0.0.1`, aplica allowlist estrita de origens CORS (sem wildcard `*` com credenciais) e exige token Bearer local quando configurado (ou rejeita origens/clientes externos não autorizados), protegendo o control plane local.
3. **Observabilidade Reconciliável via SSE (`Last-Event-ID`):** Clientes que desconectam durante uma execução recuperam a trilha monotônica de eventos a partir do último `seq` recebido, recebendo `410 Gone` caso o cursor solicitado tenha expirado.
4. **Semântica Determinística de Erros e Códigos de Saída:** Erros HTTP retornam envelope padronizado (`code`, `message`, `run_id`, `retryable`) sem tracebacks ou segredos expostos; comandos CLI retornam códigos de saída determinísticos (`0` = sucesso, `1` = erro de validação/domínio, `2` = erro de sistema, `3` = conflito de idempotência/revisão/estado).

---

## 3. Contract (Contrato Formal)

### 3.1. Rotas HTTP do Control Plane M1 (`/v1/control-plane`)

| Método | Rota | Status Sucesso | Semântica e Regras de Contrato |
|---|---|---|---|
| `GET` | `/v1/control-plane/bootstrap` | `200 OK` | Metadados de capacidades e read models ativos (`projects`, `runs`, `worktrees`, `diffs`, `health`, `models`, `quota`). |
| `POST` | `/v1/control-plane/projects` | `201 Created` | Valida raiz Git real (`resolve_repo_root`), bloqueia diretórios sem `.git` ou path traversal (`400`), persiste projeto e resolve `base_sha`. |
| `GET` | `/v1/control-plane/projects` | `200 OK` | Lista projetos cadastrados. |
| `GET` | `/v1/control-plane/projects/{id}` | `200 OK` | Retorna detalhes do projeto ou `404`. |
| `POST` | `/v1/control-plane/runs` | `202 Accepted` | Cria ou retorna run idempotente (`Idempotency-Key` + SHA-256 do payload). Mesmo payload $\rightarrow$ `202` com mesmo `run_id`; payload divergente $\rightarrow$ `409 Conflict`. |
| `GET` | `/v1/control-plane/runs` | `200 OK` | Lista paginada (`project_id`, `status`, `page`, `size`). |
| `GET` | `/v1/control-plane/runs/{id}` | `200 OK` | Snapshot completo da run (`RunDetailResponse` com `revision`, `tasks`, `budget`). |
| `GET` | `/v1/control-plane/runs/{id}/tasks` | `200 OK` | Lista tarefas da run com tentativas (`attempts`), tentativa atual e resultado/checks. |
| `GET` | `/v1/control-plane/runs/{id}/artifacts` | `200 OK` | Lista artefatos vinculados à run (filtro opcional `kind`). |
| `GET` | `/v1/control-plane/runs/{id}/events` | `200 OK` (`text/event-stream`) | Replay monotônico a partir de `Last-Event-ID` + `event: heartbeat`. Cursor expirado $\rightarrow$ `410 Gone`. |
| `POST` | `/v1/control-plane/runs/{id}/cancel` | `200 OK` | Cancela a run inteira (`scope="run"`) ou tarefa específica (`scope="task"`, `task_id`). Run já terminal $\rightarrow$ `409 Conflict`. |
| `POST` | `/v1/control-plane/runs/{id}/tasks/{task_id}/retry` | `200 OK` | Reconcilia tentativa interrompida (se solicitado) e executa/agenda nova tentativa (`ordinal + 1`). |
| `POST` | `/v1/control-plane/runs/{id}/tasks/{task_id}/review` | `200 OK` | Registra decisão (`accepted`/`rejected`) com `expected_revision`. Revisão divergente ou check falho $\rightarrow$ `409 Conflict`. |
| `POST` | `/v1/control-plane/runs/{id}/integrate` | `200 OK` / `422` | Integra resultados `accepted` em `integrate/<run_id>` e roda checks combinados. Não aceito $\rightarrow$ `409`; conflito de merge $\rightarrow$ `422`. |
| `POST` | `/v1/control-plane/runs/{id}/discard` | `200 OK` | Remove worktrees temporárias apenas se a run for terminal e evidências estiverem retidas (`409` se run ativa ou worktree suja sem `force`). |

### 3.2. Equivalência CLI (`src/hydra_orch/cli.py`)

Comandos CLI operando sobre `RunService`, com suporte a `--json` e `--output <path>`:
- `hydra project-create`, `hydra project-list`
- `hydra submit`: submete uma run a partir de arquivo JSON ou opções de linha de comando (com `--idempotency-key` e opção `--execute` para despachar a tentativa).
- `hydra runs`, `hydra inspect <run_id>`: consulta estado, revisão, tarefas, artefatos e eventos da run.
- `hydra review <run_id> <task_id> --decision accepted|rejected --reason "..." --expected-revision <rev>`
- `hydra integrate <run_id>`
- `hydra cancel <run_id> [--task-id <tid>] [--reason "..."]`
- `hydra retry <run_id> <task_id>`
- Comandos existentes preservados: `hydra serve`, `hydra run`, `hydra status`, `hydra quota`.

---

## 4. Preconditions (Pré-condições)

1. `ExecutionStore` inicializado com migração `0001_initial_core.sql` em modo SQLite WAL.
2. Para operações de repositório/execução, `canonical_root` deve apontar para um checkout Git válido com commit `base_sha` verificável.
3. Quando `HYDRA_API_TOKEN` (ou `app.state.api_token`) estiver configurado, requisições HTTP devem apresentar `Authorization: Bearer <token>`.

---

## 5. Postconditions (Pós-condições)

1. Toda mutação disparada via HTTP ou CLI persiste transacionalmente no SQLite WAL e emite o `RunEvent` correspondente antes de retornar ao chamador.
2. Submissões repetidas com mesma `Idempotency-Key` e mesmo payload retornam o `run_id` original sem duplicar registros ou subprocessos.
3. Cancelamento de tarefa individual (`scope="task"`) em uma run multi-tarefa encerra apenas a tarefa alvo e preserva as demais tarefas independentes.

---

## 6. Invariants (Invariantes)

- **Invariante de Serviço Único:** `server.py` e `cli.py` delegam 100% das mutações de estado de run/tarefa para `RunService`.
- **Invariante de Envelope de Erro:** Nenhum erro HTTP de validação, domínio ou infraestrutura expõe stack trace Python ou variáveis de ambiente no corpo JSON.
- **Invariante de Inferência Pura:** `POST /v1/chat/completions` jamais cria worktrees ou altera estado Git (`unsupported_mode` para `hydra-swarm`).

---

## 7. Failure Modes (Modos de Falha)

| Cenário | Código HTTP / CLI Exit | Resposta Estruturada |
|---|---|---|
| Raiz de projeto inexistente, fora de `.git` ou com path traversal | HTTP `400` / Exit `1` | `code="workspace_invalid"` |
| `Idempotency-Key` reutilizada com payload distinto | HTTP `409` / Exit `3` | `code="idempotency_conflict"` |
| `expected_revision` divergente em `review` | HTTP `409` / Exit `3` | `code="optimistic_lock_conflict"` |
| Cancelamento de run já em estado terminal (`succeeded`, `failed`, `cancelled`) | HTTP `409` / Exit `3` | `code="invalid_run_state"` |
| Tentativa de integrar resultado não `accepted` ou simulado | HTTP `409` / Exit `3` | `code="result_not_accepted"` / `code="simulated_result_not_integrable"` |
| Conflito de merge durante `integrate` | HTTP `422` / Exit `1` | `code="merge_conflict"`, `conflicted_files`, worktree preservada |
| Cursor SSE `Last-Event-ID` expirado | HTTP `410` | `code="cursor_expired"` |
| Token Bearer ausente/inválido quando autenticação ativa | HTTP `401` | `code="unauthorized"` |
| Origem CORS fora da allowlist estrita | HTTP `403` | `code="cors_origin_forbidden"` |

---

## 8. How (Arquitetura e Implementação)

1. **Extensão do `ExecutionStore` e `RunService`:**
   - Métodos de leitura/cadastro de projetos (`create_project`, `get_project`, `list_projects`), listagem paginada de runs (`list_runs`), cancelamento granular de tarefa (`cancel_task`), busca de detalhe consolidado (`get_run_detail`, `list_run_tasks`) e descarte seguro de runtime (`discard_run_runtime` com verificação de hash SHA-256 de artefatos retidos).
2. **Camada HTTP (`src/hydra_orch/server.py`):**
   - Lifespan assíncrono substituindo `@app.on_event` depreciado (mantendo `startup_event` e `shutdown_event` compatíveis);
   - Middleware de verificação de origem CORS allowlist e dependência de autenticação Bearer/loopback;
   - Rotas em `/v1/control-plane/*` com mapeamento determinístico de exceções (`ContractViolation`, `OptimisticLockError`, `IdempotencyConflictError`, `StorageIntegrityError`, `GitWorkspaceError`) para envelopes JSON padronizados.
3. **Camada CLI (`src/hydra_orch/cli.py`):**
   - Comandos Typer consumindo `RunService` e emitindo saída formatada (Rich ou `--json` / `--output`) com códigos de saída `0`, `1`, `2`, `3`.

---

## 9. Examples (Exemplos de Aceite)

### Exemplo 1: Submissão Idempotente, Execução, Revisão e Integração via API/CLI
1. `POST /v1/control-plane/projects` com `canonical_root` válido $\rightarrow$ `201 Created`.
2. Duas chamadas `POST /v1/control-plane/runs` com mesmo `Idempotency-Key` e mesmo payload $\rightarrow$ ambas retornam `202 Accepted` com o mesmo `run_id`.
3. Terceira chamada com mesmo `Idempotency-Key` e `objective` alterado $\rightarrow$ `409 Conflict` (`idempotency_conflict`).
4. Após execução da tentativa e aprovação dos checks (`ready_for_review`), `POST /v1/control-plane/runs/{id}/tasks/{task_id}/review` com `decision="accepted"` e `expected_revision=1` $\rightarrow$ `200 OK`.
5. `GET /v1/control-plane/runs/{id}/events` com `Last-Event-ID: 2` retorna apenas eventos com `seq > 2` em ordem monotônica.

---

## 10. GAPs Resolvidos

- **GAP A04 (Parcial T07):** A entrada CLI/API passa a acionar o `RunService` real sobre worktrees e checks, sem forjar conclusão textual.
- **GAP A15 (Parcial T07):** Stream SSE de eventos de run possui `id: <seq>` monotônico estável por evento e suporte a `Last-Event-ID`.

---

## 11. Glossary e Acrônimos

| Termo / Acrônimo | Definição |
|---|---|
| **CORS** | Cross-Origin Resource Sharing — política de origens permitidas pelo servidor HTTP |
| **Idempotency-Key** | Chave única enviada pelo cliente para garantir que repetições da mesma requisição não dupliquem efeitos |
| **Last-Event-ID** | Cabeçalho HTTP SSE informando o último número de sequência (`seq`) processado pelo cliente |
| **Loopback** | Interface de rede local (`127.0.0.1` / `::1` / `localhost`) restrita à própria máquina |
| **SSE** | Server-Sent Events (`text/event-stream`) para transmissão unidirecional de eventos numerados |
