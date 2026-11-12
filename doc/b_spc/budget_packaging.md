# S19 — Governança de Orçamento e Empacotamento de Pull Request (`budget_packaging.md`)

**Identificador Formal:** `budget_packaging.md`  
**Caminho Canônico:** `doc/b_spc/budget_packaging.md`  
**Etapa / Task:** `S19 / T28`  
**Versão:** `v01_00_0000`  
**Status:** `IMPLEMENTADO (T28)`  
**Autoridade:** Derivado normativo de [`prd_funcional.md`](prd_funcional.md) (RF29, RF30), [`prd_tecnico.md`](prd_tecnico.md) (RT29, RT30, §3.6, §7.A, §8.1 T28) e [`../../migration/0001_initial_core.sql`](../../migration/0001_initial_core.sql).

---

## 1. Purpose (Propósito)

Estabelecer o contrato formal de execução para:
1. **Governança de Orçamento (`BudgetGovernor` em `src/hydra_orch/core/budget.py`):** monitoramento e imposição determinística de tetos de consumo por run (`max_usd`, `max_tokens_in`, `max_tokens_out`, `max_wall_seconds`), com limiar configurável de alerta (`alert_threshold_pct` entre `50.0` e `99.0`, padrão `80.0%`), congelamento preventivo em `100%` e fluxo explícito de aprovação ou recusa de extensão pelo operador.
2. **Empacotamento e Publicação de PR (`PRPackager` em `src/hydra_orch/core/packaging.py`):** compilação de dossiê estruturado de Pull Request (`PRPackage`) com branch dedicada (`pr/<run_id>`), descrição Markdown completa e redigida, persistência em `pr_packages` + artefato atômico `Artifact(kind="pr_package")` verificado por SHA-256, exportação auditável e publicação remota estritamente condicionada a autorização explícita.

---

## 2. Why (Justificativa)

Execuções autônomas multi-tentativa podem consumir custo financeiro, tokens ou tempo de parede além do previsto, ou produzir alterações prontas que precisam de entrega auditável sem vazar credenciais nem publicar automaticamente em repositório remoto sem consentimento. O `BudgetGovernor` impede gastos descontrolados sem fabricar zeros quando a telemetria está ausente (`unknown`), enquanto o `PRPackager` separa fisicamente a geração local do pacote de PR (com redaction e integridade por hash) da autorização explícita de push para o remote.

---

## 3. Contract (Contrato Formal)

### 3.1 `BudgetGovernor(store, metrics=None)`

- **Política (`budget_policies`):**
  - Campos: `max_usd` (`REAL`), `max_tokens_in` (`INTEGER`), `max_tokens_out` (`INTEGER`), `max_wall_seconds` (`INTEGER`), `alert_threshold_pct` (`50.0..99.0`, padrão `80.0`), `status` (`active | alerted | frozen | exhausted`).
  - `configure(run_id, ...)` atualiza os limites enquanto a política não estiver `exhausted`.
- **`check(run_id, *, now=None, max_age_seconds=300.0) -> BudgetStatus`:**
  - Consulta métricas com proveniência via `MetricsService` (`observed`, `stale`, `unknown`).
  - Preserva `unknown` como `None` (`current_* = None`): **`unknown` nunca vira `0` e nunca dispara alerta ou congelamento**.
  - Quando todas as parcelas são conhecidas (`observed`/`stale`) ou o subtotal conhecido comprovado (`known_subtotal`) atinge `>= alert_threshold_pct` e `< 100%` de qualquer teto configurado: transita `active -> alerted` e emite evento `budget.alerted`.
  - Quando qualquer teto configurado atinge `>= 100%`: transita `active|alerted -> frozen`, emite evento `budget.frozen`, pausa o run (`runs.status = waiting` com evento `run.waiting`, `reason="budget_frozen"`, quando em `queued`/`running`) e bloqueia novos despachos com `ContractViolation("budget_frozen", ...)`.
- **`assert_dispatchable(run_id) -> BudgetStatus`:**
  - Executado no despacho de `RunService.execute_task_attempt` e `RunService.retry_task` antes de criar worktree ou iniciar subprocesso.
  - Rejeita `frozen` com `ContractViolation("budget_frozen", ...)` e `exhausted` com `ContractViolation("budget_exhausted", ...)`.
- **`extend(run_id, additional_usd=None, *, additional_tokens_in=None, additional_tokens_out=None, additional_wall_seconds=None, approved: bool, actor: str, reason: str) -> ExtensionResult`:**
  - Se `approved=True`: valida incremento positivo em ao menos um teto, amplia os limites em `budget_policies`, retorna `frozen|alerted|active -> active`, emite evento `budget.extended` e retoma `runs.status` de `waiting -> running` (`run.resumed`).
  - Se `approved=False`: transita para `exhausted`, emite evento `budget.exhausted`, marca o run não-terminal como `failed` (`run.finished` com `reason="budget_exhausted"`), preserva todas as evidências existentes (tasks, attempts, results, checks, artifacts, worktrees) e bloqueia novas execuções com `ContractViolation("budget_exhausted", ...)`.

### 3.2 `PRPackager(store, metrics=None)`

- **`build(run_id, *, pr_branch=None, create_git_branch=True, runtime_dir=None) -> PRPackage`:**
  - Coleta objetivo do run, commits (`git log` ou resultados aceitos), resumo de checks (`check_results` de integração e tarefas), diff sumarizado (`git diff --numstat` ou `changed_files`), métricas com proveniência/status (`observed`/`stale`/`unknown`, sem converter `unknown` em zero) e decisões de revisão (`reviews`).
  - Se `create_git_branch=True` em repositório Git válido, cria/atualiza a ref `pr_branch` (padrão `pr/<run_id>`) sem alterar o checkout ou branch atual do operador.
  - Aplica `redact_text` e `redact` em todo texto e estrutura serializada (incluindo `description_markdown`, `commits`, `checks_summary`, `diff_summary`, `metrics`, `review_decisions`) antes de gravar.
  - Grava o arquivo do pacote atomicamente (arquivo temporário + `flush()` + `os.fsync()` + `os.replace()`) e calcula `SHA-256` e `size_bytes`.
  - Na mesma transação SQLite: persiste em `pr_packages`, registra `Artifact(kind="pr_package")` em `artifacts` e emite evento `pr_package.created`.
- **`publish(package_id, *, authorized: bool = False, policy_authorized: Optional[bool] = None, remote: str = "origin", push_fn=None, actor: str = "operator") -> PublishResult`:**
  - Recusa explicitamente com `ContractViolation("publish_not_authorized", ...)` se `authorized=False` ou `policy_authorized is False`.
  - Quando autorizado, executa `push_fn` injetado ou `git push` para o remote configurado (em testes herméticos, sempre contra função injetável ou repositório bare local em `tmp_path`, bloqueando URLs externas quando `HYDRA_OFFLINE_CI=1`) e registra auditoria em `commands(scope="pr_publish")`.
- **`export(package_id, *, output_path=None) -> ExportResult`:**
  - Verifica integridade `SHA-256` do artefato retido em disco (se presente), aplica `redact_text` e exporta o dossiê Markdown atomicamente.

---

## 4. Preconditions (Pré-condições)

1. Banco SQLite inicializado com as migrações `0001_initial_core.sql` e `0002_control_plane.sql` (`budget_policies`, `pr_packages`, `artifacts`, `metric_samples`, `events`, `reviews`, `check_results`).
2. `run_id` previamente persistido em `runs` (e política inicial criada em `budget_policies`).
3. Para criação de branch Git em `PRPackager.build`: `repo_root` deve ser um repositório Git válido com commits acessíveis (ou `create_git_branch=False` para cenários sem checkout Git).

---

## 5. Postconditions (Pós-condições)

1. Transições de orçamento (`budget.alerted`, `budget.frozen`, `budget.extended`, `budget.exhausted`) são persistidas atomicamente junto com seus respectivos `RunEvent` em `events`.
2. Após `extend(..., approved=False)`, `budget_policies.status == 'exhausted'` e qualquer tentativa futura de `execute_task_attempt`, `retry_task` ou `extend` falha deterministicamente sem destruir resultados ou artefatos prévios.
3. Após `PRPackager.build(run_id)`, `pr_packages`, `artifacts` (`kind='pr_package'`), o arquivo em disco e o evento `pr_package.created` estão consistentes e livres de segredos detectáveis por `core/redaction.py`.
4. `PRPackager.publish` nunca executa push sem `authorized=True` (e `policy_authorized` não falso).

---

## 6. Invariants (Invariantes)

1. **Invariante de Telemetria Ausente (RT15 / RT29):** Ausência de métrica (`unknown` / `NULL`) nunca é convertida para `0` e nunca causa congelamento ou alerta falso.
2. **Invariante de Admissão de Despacho:** Nenhum `TaskAttempt` é criado ou iniciado quando o orçamento da run está `frozen` ou `exhausted`.
3. **Invariante de Separação Execução vs. Publicação (RT30):** Construir ou exportar um `PRPackage` não autoriza nem executa push remoto; publicação exige decisão explícita (`authorized=True`).
4. **Invariante de Redaction e Integridade (RNF05 / RT11):** Segredos são expurgados antes da persistência no SQLite e antes do cálculo de `SHA-256` do artefato gravado atomicamente.
5. **Invariante de Checkout do Operador (RT05):** `PRPackager.build` nunca altera `HEAD`, working tree ou branch ativa do operador.

---

## 7. Failure Modes (Modos de Falha)

| Falha | Comportamento Obrigatório | Código `ContractViolation` |
|-------|---------------------------|----------------------------|
| Despacho com orçamento `frozen` | Bloqueia antes de criar worktree/tentativa | `budget_frozen` |
| Despacho ou extensão com orçamento `exhausted` | Bloqueia permanentemente preservando evidências | `budget_exhausted` |
| Parâmetros inválidos em extensão/configuração | Rejeita delta $\le 0$, booleano, NaN/Inf ou ator/motivo vazio | `budget_invalid` |
| `PRPackager.publish` sem autorização (`authorized=False` ou política negada) | Recusa publicação sem executar push | `publish_not_authorized` |
| Tentativa de construir segundo `PRPackage` para o mesmo `run_id` | Rejeita duplicata preservando pacote original | `pr_package_exists` |
| Artefato `pr_package` adulterado em disco durante `export` | Aborta exportação por divergência de SHA-256 | `artifact_tampered` |
| `run_id` ou `package_id` inexistente | Falha antes de qualquer mutação | `resource_not_found` |

---

## 8. How (Arquitetura e Implementação)

1. **[`../../src/hydra_orch/core/budget.py`](../../src/hydra_orch/core/budget.py):** Implementa `BudgetGovernor`, `BudgetStatus`, `BudgetDimensionReport` e `ExtensionResult` sobre `ExecutionStore` e `MetricsService`, usando aritmética decimal exata na avaliação de `alert_threshold_pct`.
2. **[`../../src/hydra_orch/core/packaging.py`](../../src/hydra_orch/core/packaging.py):** Implementa `PRPackager`, `PRPackage`, `PublishResult` e `ExportResult`, coletando commits, checks, diff, métricas e reviews, aplicando `redact_text`/`redact` e persistindo artefato atômico (`temp + fsync + os.replace`) + `pr_packages` + evento `pr_package.created`.
3. **[`../../src/hydra_orch/core/run_service.py`](../../src/hydra_orch/core/run_service.py):** Integra `BudgetGovernor.assert_dispatchable` no início de `_execute_task_attempt_inner` (cobrindo `execute_task_attempt` e `retry_task`), atualiza `check(run_id)` após coleta de métricas da tentativa e expõe métricas/status reais em `get_run_detail`.
4. **[`../../src/hydra_orch/model.py`](../../src/hydra_orch/model.py):** Inclui `budget.extended`, `budget.exhausted` e `pr_package.created` em `RunEvent.event_type`.

---

## 9. Examples (Exemplos de Uso)

```python
# 1. Governança de orçamento
governor = BudgetGovernor(store)
status = await governor.check(run_id)           # active -> alerted (80%) -> frozen (100%)
ext = await governor.extend(
    run_id, additional_usd=1.0, approved=True, actor="operator", reason="approved scope"
)                                                # frozen -> active + budget.extended

# 2. Empacotamento e publicação condicionada
packager = PRPackager(store)
pkg = await packager.build(run_id)               # pr_packages + Artifact(kind="pr_package") + pr_package.created
# packager.publish(pkg.package_id, authorized=False) -> ContractViolation("publish_not_authorized")
res = await packager.publish(pkg.package_id, authorized=True, remote=str(bare_remote))
```

---

## 10. GAPs

- **GAP-T28-01:** Rotas HTTP dedicadas `/v1/control-plane/runs/{id}/budget/extend` e `/v1/control-plane/runs/{id}/pr-package` permanecem fora do escopo desta task (camada `server.py` / `cli.py` reservada ao líder).
- **GAP-T28-02:** Provedores CLI sem telemetria estruturada continuam reportando `unknown`; o `BudgetGovernor` aguarda observações reais (`observed`/`stale`) sem estimativas artificiais.

---

## 11. Glossary e Acrônimos

| Termo | Definição |
|-------|-----------|
| **BudgetGovernor** | Componente de núcleo responsável por monitorar tetos de orçamento e bloquear despachos ao atingir `100%`. |
| **DBC-9** | Padrão normativo de especificação em 9 seções usado em `doc/b_spc/`. |
| **PRPackage** | Dossiê estruturado e redigido contendo branch de PR, commits, checks, diff sumarizado, métricas com proveniência e decisões de revisão. |
| **PRPackager** | Serviço que compila, redige, persiste atomicamente, exporta e publica sob autorização o `PRPackage`. |
| **Redaction** | Expurgo determinístico de tokens, senhas, chaves privadas e credenciais antes de persistência ou exportação. |
| **SHA-256** | Resumo criptográfico usado para verificar a integridade de artefatos retidos em disco. |
