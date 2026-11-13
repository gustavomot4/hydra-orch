# S20 — CLI Control Plane, CI Hermética e Manuais Operacionais

| Campo | Valor |
| :--- | :--- |
| **Spec ID** | `S20` |
| **Versão** | `0.1.0` |
| **Status** | `verified` (`T23` e `T24` implementados e validados) |
| **Tarefas do Backlog** | `T23` (CLI Control Plane Estendida), `T24` (CI Estendida e Manuais Operacionais) |
| **Requisitos Técnicos** | `RT28` (Equivalência CLI vs API), `RT29` (CI Offline Hermética), `RT30` (Manuais e Runbooks) |
| **PRD Referência** | `doc/b_spc/prd_tecnico.md` (§3.7.4, §7.A, §8.2, §8.3) |
| **Implementação / Evidência** | `src/hydra_orch/cli.py`, `tests/test_cli.py`, `.github/workflows/ci.yml`, `doc/j_manual/README.md` |

---

## 1. Purpose

Definir o contrato de especificação DBC-9 para a superfície estendida da **CLI** (`hydra`), a **pipeline de CI offline hermética** e os **manuais/runbooks operacionais** do `hydra-orch`:

- Garantir **paridade funcional 1:1** entre a API HTTP/Control Plane (`S17`) e a CLI (`hydra`), consumindo exatamente a mesma camada de serviços em `core/` e `bridge/` acoplada ao `ExecutionStore` (`RT28`).
- Padronizar saída estruturada (`--json`, `--output`), sanitização/redação de segredos e mapeamento determinístico de códigos de saída (`0`, `1`, `2`, `3`).
- Definir o gate de **CI estendida offline e hermética** (`T24` / `RT29`) cobrindo os fluxos M1 e a expansão negativa do PRD (§7.A), além da documentação operacional atualizada (`RT30`).

---

## 2. Why

Sem equivalência real entre CLI e HTTP Control Plane:

1. Operações críticas (aprovação de descoberta, decisão de consentimento, rotação/revogação de tokens, resolução de conflitos, rollback de extensões, governança de budget e empacotamento de PR) ficariam presas à interface HTTP ou dependeriam de scripts ad-hoc fora da camada transacional.
2. Divergências entre validações da CLI e da API violariam garantias de segurança (aceitação de segredos literais, bypass de consentimento, travessia de caminho, publicação não autorizada de PR) e auditabilidade (`command_records` / `audit_logs`).
3. Uma CI que dependesse de provedores pagos externos, rede aberta ou segredos reais seria não determinística e violaria o princípio de verificação offline hermética do `hydra-orch`.

---

## 3. Contract

### 3.1 Equivalência CLI M1 + Control Plane Estendida (`T23` / `RT28`)

A CLI (`hydra`, entrypoint `hydra_orch.cli:app` via Typer) deve:

1. **Preservar 100% dos comandos M1:**
   - Top-level: `serve`, `run`, `submit`, `inspect`, `review`, `integrate`, `cancel`, `retry`, `status`, `quota`, `project-create`, `project-list`, `runs`.
2. **Expor 21 grupos de subcomandos Typer equivalentes ao Control Plane (`S17`):**
   - `hydra area` (`create`, `list`)
   - `hydra workspace` (`create`, `list`, `archive`)
   - `hydra project` (`create`, `list`, `adopt`)
   - `hydra repo` (`register`, `list`, `grant`, `revoke`)
   - `hydra agent` (`register`, `list`, `certify`, `revoke-cert`, `resolve`)
   - `hydra profile` (`create`, `get`, `resolve`, `snapshot`)
   - `hydra session` (`create`, `list`, `threads`, `transition`)
   - `hydra metrics` (`query`, `usage`)
   - `hydra consent` (`request`, `list`, `decide`, `revoke`)
   - `hydra memory` (`write`, `query`, `revoke`)
   - `hydra discovery` (`scan`, `list`, `approve`, `reject`)
   - `hydra skill` (`register`, `get`, `revoke`)
   - `hydra mcp` (`register`, `get`, `revoke`)
   - `hydra secret` (`register`, `get`, `revoke`)
   - `hydra extension` (`register`, `install`, `list`, `activate`, `disable`, `revoke`, `rollback`)
   - `hydra preference` (`set`, `list`, `resolve`, `revert`, `snapshot`)
   - `hydra transport` (`register`, `list`, `certify`, `health`)
   - `hydra token` (`create`, `revoke`)
   - `hydra conflict` (`analyze`, `auto-repair`, `manual`, `discard`)
   - `hydra budget` (`status`, `extend`)
   - `hydra pr-package` (`build`, `publish`)
3. **Compartilhar a mesma camada de serviços e storage:**
   - Todos os comandos obtêm o `RunService` via `get_run_service()` (mesmo singleton configurável via `set_run_service()` para testes herméticos) e instanciam os serviços de domínio (`WorkspaceRegistry`, `AgentRegistry`, `ProfileService`, `SessionService`, `MetricsService`, `ConsentService`, `MemoryStore`, `DiscoveryService`, `SkillRegistry`, `ExtensionHost`, `PreferenceService`, `TransportRegistry`, `ConflictResolver`, `BudgetGovernor`, `PRPackager`, `TokenVerifier`) sobre `svc.store` e `svc.repo_root` / `svc.runtime_dir`.
4. **Suportar `--json` e `--output <path>`:**
   - Todo comando operacional e de leitura suporta `--json` (saída JSON determinística via stdout ou arquivo) e `--output <path>` (escrita atômica/direta no arquivo especificado).
5. **Códigos de saída determinísticos:**
   - `0`: Sucesso (`ok`).
   - `1`: Erro de validação de entrada, JSON inválido, regra de negócio/escopo/autorização, `ConfigError`, recurso não encontrado ou violação de path traversal/segredo literal.
   - `2`: Erro de sistema, storage (`StorageError`), I/O ou exceção inesperada.
   - `3`: Conflito de estado/concorrência/revisão/idempotência/consentimento/certificação/revisão (`IdempotencyConflictError`, `OptimisticLockError`, `ConflictError`, violações de transição de sessão/thread/conflito, `consent_required`, `budget_frozen`, `budget_exhausted`, `extension_revoked`, `component_untrusted`, `transport_uncertified`, `publish_not_authorized`, etc.).

### 3.2 CI Hermética Estendida e Manuais Operacionais (`T24` / `RT29` / `RT30`)

1. **CI offline hermética (`.github/workflows/ci.yml`):**
   - Executa `python -m pytest` sem chamadas a APIs externas pagas, usando `ExecutionStore` em `tmp_path`, repositórios Git locais temporários e transportes/adaptadores simulados herméticos.
   - Deve validar tanto os testes M1 quanto a matriz completa do Control Plane, CLI (`tests/test_cli.py`), segurança/proveniência, budget/packaging e testes negativos do PRD §7.A.
   - Executa validação de schema OpenAPI (`doc/f_api/openapi.yaml`) e `git diff --check` / lint sem dependência de rede em tempo de teste.
2. **Manuais e runbooks (`doc/j_manual/README.md` e runbooks específicos):**
   - Documentar todos os grupos de comandos da CLI, exemplos com `--json` e `--output`, tabela de exit codes (`0/1/2/3`), troubleshooting de falhas comuns (consentimento, aprovação de discovery, certificação de transporte, orçamento congelado, publicação de PR bloqueada, resolução manual de conflitos).

---

## 4. Preconditions

- `ExecutionStore` inicializado com migrations `0001` e `0002` (e eventuais migrations posteriores carregadas pelo store).
- `get_run_service()` retorna um `RunService` válido vinculado a `repo_root`, `runtime_dir` e `store` consistentes (em produção via `config.yaml` / env; em testes via `set_run_service(...)`).
- Operações que envolvem diretórios locais (`project create`, `repo register`, `discovery scan`, `extension register/install`, `conflict`, `pr-package`) devem operar sobre caminhos canônicos dentro de `allowed_roots`.
- Comandos destrutivos ou de governança sensível (`consent`, `memory`, `discovery approve/reject`, `secret`, `extension`, `token`, `pr-package publish`) exigem `principal_id` e metadados obrigatórios explícitos.

---

## 5. Postconditions

- Toda mutação bem-sucedida pela CLI persiste exatamente nos mesmos registros SQLite (`areas`, `workspaces`, `projects`, `repositories`, `agents`, `profiles`, `sessions`, `threads`, `consents`, `memory_entries`, `discovered_resources`, `skills`, `mcps`, `secret_refs`, `extension_installs`, `preferences`, `transports`, `access_tokens`, `conflict_resolutions`, `budget_decisions`, `pr_packages`, `command_records`, `audit_logs`) que os endpoints equivalentes de `server.py`.
- Quando `--output <path>` é fornecido, o artefato serializado (JSON quando `--json`, ou resumo estruturado em texto/JSON) é gravado em `<path>` e pode ser consumido por pipelines/CI.
- Quando um erro ocorre com `--json`, o payload JSON `{"error": {"code": ..., "message": ...}}` é emitido no stdout/stderr padronizado conforme `_handle_cli_exception` com o exit code determinístico (`1`, `2` ou `3`).

---

## 6. Invariants

1. **Proibição absoluta de persistência/impressão de segredos e tokens em plaintext:**
   - `hydra secret register` rejeita literais de segredo / valores de alta entropia (delegando a `SecretRef` / `SkillRegistry`) e aceita apenas referências (`provider_type` + `source_key`).
   - `hydra secret get` retorna apenas metadados da referência (`secret_id`, `secret_name`, `provider_type`, `source_key`, `status`), nunca resolvendo ou imprimindo valores de ambiente/vault.
   - `hydra token create` calcula exclusivamente o hash PBKDF2-SHA256 via `TokenVerifier.from_token(...).encode()` antes de persistir em `access_tokens.token_hash`; nunca grava o token em texto claro no banco ou em `command_records`/`audit_logs`, e aplica `redact` / `redact_text` em qualquer saída/erro.
2. **Sem duplicação de regras de negócio na CLI:**
   - A CLI faz parsing de argumentos/JSON, construção de DTOs e apresentação; toda regra de autorização, consentimento, estado, orçamento, travessia e versionamento otimista reside em `core/` e `bridge/`.
3. **Sem bypass de gates de segurança ou estado:**
   - `memory write` sem consentimento válido falha com exit code `3`.
   - `pr-package publish` sem autorização explícita de política falha com exit code `3`.
   - `repo register` / `discovery scan` / `extension` com path traversal fora de `allowed_roots` falha com exit code `1`.
4. **Rápida introspecção de `--help`:**
   - `hydra --help` e `hydra <grupo> --help` devem responder localmente sem inicializar loops assíncronos de rede, servidores ou banco de dados.

---

## 7. Failure Modes

| Código de Saída | Categoria | Exceções / Códigos Típicos | Comportamento Esperado |
| :--- | :--- | :--- | :--- |
| `0` | Sucesso | — | Payload emitido em formato humano/tabela ou `--json`, gravado em `--output` se informado. |
| `1` | Validação / Negócio / Escopo / Auth | `ValidationError`, `ValueError`, `json.JSONDecodeError`, `ConfigError`, `GitWorkspaceError` (não dirty), `ContractViolation` de validação/escopo (`secret_value_rejected`, `path_traversal`, `unauthorized_principal`, `resource_not_found`, `invalid_scope`, `agent_not_found`, etc.) | Mensagem redigida; em `--json`, JSON estruturado `{"error": {"code": ..., "message": ...}}`. |
| `2` | Sistema / Storage | `StorageError`, erros inesperados de I/O / OS / exceções não tratadas | Falha operacional; nenhuma corrupção parcial transacional nos repositórios gerenciados pelo `ExecutionStore`. |
| `3` | Conflito / Estado / Idempotência / Consentimento / Gate | `IdempotencyConflictError`, `OptimisticLockError`, `StorageIntegrityError` (exceto not found), `dirty_worktree_preserved`, `consent_required`, `consent_conflict`, `memory_conflict`, `session_state_conflict`, `thread_state_conflict`, `workspace_archived`, `profile_snapshot_conflict`, `extension_revoked`, `extension_quarantined`, `rollback_unavailable`, `preference_revert_unavailable`, `explicit_preference_precedence`, `conflict_already_resolved`, `invalid_conflict_transition`, `budget_frozen`, `budget_exhausted`, `pr_package_exists`, `packaging_branch_conflict`, `publish_not_authorized`, `discovery_untrusted`, `component_untrusted`, `component_revoked`, `transport_uncertified` | Preserva estado/worktree atual; orienta correção ou resolução explícita. |

---

## 8. How

### 8.1 Arquitetura da CLI (`src/hydra_orch/cli.py`)

```text
hydra <grupo> <subcomando> [opções] [--json] [--output PATH]
  │
  ├─► Parse & validação sintática (Typer + JSON payloads)
  │
  ├─► _run_cli_action(coro_fn, as_json=..., output_file=...)
  │      ├─ Obtém RunService via get_run_service()
  │      ├─ Executa serviço de domínio (core/* ou bridge/*) sobre svc.store
  │      ├─ Sucesso ─► _emit_output(payload, as_json=..., output_file=...) ─► exit 0
  │      └─ Erro    ─► _handle_cli_exception(exc, as_json=...) ─► redact ─► exit 1 | 2 | 3
```

### 8.2 Regras Específicas de Tokens e Segredos

- **`hydra secret register`**: exige `--name`, `--provider` (`env|vault|keyring`) e `--source-key`. O valor da referência é validado por `SecretRef` / `SkillRegistry.create_secret_ref`, que rejeita literais aparentes (`secret_value_rejected` -> exit `1`).
- **`hydra token create`**: aceita `--principal-id`, opcionalmente `--scopes`, `--expires-at` e `--token` ou `--token-env` (ou gera um token efêmero seguro localmente sem logá-lo se omitido); calcula `token_hash = TokenVerifier.from_token(raw_token).encode()`, insere em `access_tokens` via transação do `ExecutionStore` com auditoria sem o segredo e retorna apenas metadados (`token_id`, `principal_id`, `scopes`, `expires_at`, `created: True`).
- **`hydra token revoke`**: marca `revoked_at = datetime('now')` em `access_tokens` para o `token_id` informado (ou falha com `resource_not_found` -> exit `1` se inexistente).

### 8.3 Pipeline de CI Estendida (`T24`)

1. Job único ou matriz determinística no GitHub Actions executando em ambiente limpo sem segredos de provedores reais.
2. Etapas recomendadas:
   - Verificação de higiene (`git diff --check`, validação de sintaxe Python e schema OpenAPI).
   - Suite M1 + suite completa do Control Plane (`pytest tests/` com `PYTHONPATH=src`).
   - Verificação hermética de smoke da CLI (`hydra --help` e subgrupos críticos).

---

## 9. Examples

```bash
# Fluxo de área -> workspace -> projeto -> repositório (JSON + arquivo)
hydra area create --name platform --principal-id op-1 --json --output area.json
hydra workspace create --area-id <area_id> --name core --principal-id op-1 --json
hydra project create --workspace-id <ws_id> --name demo --root /abs/repo --principal-id op-1 --json
hydra repo register --project-id <proj_id> --root /abs/repo --principal-id op-1 --authorized-principal op-1 --scopes read,write --json

# Fluxo de consentimento e memória
hydra consent request --scope-type workspace --scope-id <ws_id> --principal-id op-1 --json
hydra consent decide <consent_id> --action granted --principal-id op-1 --json
hydra memory write --scope-type workspace --scope-id <ws_id> --consent-id <consent_id> --content "build uses pytest" --principal-id op-1 --json

# Segredos e tokens sem exposição de plaintext
hydra secret register --name openai-key --provider env --source-key HYDRA_TEST_KEY --principal-id op-1 --json
hydra secret get <secret_id> --json
hydra token create --principal-id op-1 --scopes read,write --token-env HYDRA_BOOTSTRAP_TOKEN --json
hydra token revoke <token_id> --json

# Budget, conflito e PR package
hydra budget status <run_id> --json
hydra budget extend <run_id> --additional-usd 5.0 --actor op-1 --reason "extra verification" --json
hydra pr-package build <run_id> --no-create-git-branch --json
hydra pr-package publish <package_id> --authorized --json
```

---

## 10. GAPs

| ID | Descrição | Tarefa Relacionada | Status |
| :--- | :--- | :--- | :--- |
| `GAP-S20-01` | A cobertura completa de `T24` em `.github/workflows/ci.yml` (gates específicos da expansão negativa §7.A e validação automática do OpenAPI `doc/f_api/openapi.yaml`) ainda precisa ser expandida após consolidação do Control Plane. | `T24` | Fechado (`tests/test_ci_negative_gate.py` e `.github/workflows/ci.yml`) |
| `GAP-S20-02` | `doc/j_manual/README.md` atualmente documenta os comandos M1 e protótipos parciais; precisa ser atualizado em `T24` com o catálogo completo dos 21 novos grupos CLI, exit codes e runbooks de falha. | `T24` | Fechado (`doc/j_manual/README.md` §0.6–0.7) |
| `GAP-S20-03` | `hydra token create` grava diretamente em `access_tokens` via `ExecutionStore` + `TokenVerifier` porque ainda não há um `TokenService` dedicado em `core/auth.py`; caso seja extraído posteriormente, a CLI deve delegar ao serviço sem alterar o contrato de hash/não-impressão. | `T23` | Observação arquitetural |

---

## 11. Glossary e Acrônimos

- **DBC-9:** Formato padrão de especificação do repositório (seções 1–9 + `GAPs` + `Glossary e Acrônimos`).
- **M1:** Milestone 1 (execução local de runs, worktrees, review, integração e orçamento base).
- **Control Plane Estendida:** Capacidades M2–M6 adicionadas pelas tasks `T11`–`T23` (áreas, workspaces, agentes, perfis, sessões, métricas, consentimento, memória, descoberta, skills, MCP, segredos, extensões, preferências, transportes, tokens, conflitos, budget governor e PR packaging).
- **Exit Codes (`0/1/2/3`):** Contrato determinístico da CLI para sucesso (`0`), erro de validação/negócio/escopo (`1`), falha de sistema/storage (`2`) e conflito de estado/concorrência/consentimento/gate (`3`).
- **Hermetic CI:** Execução de testes automatizados isolada de rede externa, credenciais reais e estado global da máquina.
