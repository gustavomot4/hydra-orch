# integracao_git — Serviço de Workspace Git Isolado, Checks e Integração Serializada (S05 / T05–T06)

**Identificador Formal:** `integracao_git.md`
**Caminho Canônico:** `doc/b_spc/integracao_git.md`
**Versão:** `v01_00_0000`
**Status:** `IMPLEMENTADO (T05 e T06)`
**Autoridade:** Derivado normativo de [`prd_tecnico.md`](prd_tecnico.md) (§3.1 RT05, RT06; §3.4; §8.1 T05, T06), [`contrato_execucao.md`](contrato_execucao.md) (S02), [`persistencia_execucao.md`](persistencia_execucao.md) (S03) e [`executor_cli.md`](executor_cli.md) (S04).
**Escopo:** Isolamento real em Git worktrees ancoradas a SHA base fixo, preservação estrita do checkout do operador, auditoria de escopo de arquivos (`allowed_paths` / symlinks), captura e atribuição de diffs/commits, integração serializada em branch dedicada, retenção em caso de conflito/falha e limpeza segura de worktrees e locks.

---

## 1. Purpose (Propósito)

Especificar o serviço centralizado `GitWorkspaceService` em `src/hydra_orch/core/git_workspace.py`, eliminando os dois modos de falha críticos diagnosticados no scaffold legado:
1. **GAP A05:** Merges e limpezas executados diretamente sobre a branch do operador (`git checkout main`) sem gates de verificação e com remoção destrutiva (`shutil.rmtree` / `git worktree remove --force`) que descartava evidências não preservadas.
2. **GAP A06:** Fallback silencioso de `create_worktree` para `mkdir(parents=True, exist_ok=True)` quando o comando `git worktree add` falhava, permitindo que workers operassem fora de controle de versão real.

Além de especificar e implementar a **T05 (8 SP)**, este documento realiza a decomposição obrigatória em subtarefas da **T06 (13 SP)** conforme a regra de governança do [`backlog.md` (§3.3)](../a_context/backlog.md).

---

## 2. Why (Justificativa)

Para que o `hydra-orch` opere como um control plane confiável de engenharia de software:
- O checkout principal do operador jamais pode trocar de branch nem ter arquivos staged, unstaged ou untracked afetados por execuções em andamento.
- Cada tentativa (`TaskAttempt`) deve atuar sobre uma Git worktree real criada a partir de um `base_sha` imutável de 40 caracteres hexadecimais.
- Nenhuma integração pode ocorrer concorrentemente no mesmo repositório nem descartar diffs não preservados quando ocorre conflito ou falha de check.

---

## 3. Contract (Contrato Técnico)

### 3.1. Estruturas de Domínio do Workspace Git (`src/hydra_orch/core/git_workspace.py`)

- `GitWorkspaceError(RuntimeError)` — Exceção estruturada portando `failure: ExecutionFailure` tipado (`workspace_invalid`, `scope_violation`, `merge_conflict`, `git_operation_failed`, `dirty_worktree_preserved`).
- `OperatorCheckoutSnapshot` — Registro imutável do estado do checkout do operador (`repo_root`, `head_sha`, `branch`, `status_porcelain`, `staged_files`, `unstaged_files`, `untracked_files`), permitindo comprovar antes e depois de qualquer operação que o workspace do usuário permaneceu 100% intacto.
- `WorkspaceRecord` — Representação tipada da worktree de uma tentativa (`workspace_id`, `attempt_id`, `run_id`, `task_id`, `canonical_path`, `base_sha`, `branch`, `status` $\in$ `{'preparing', 'ready', 'integrating', 'conflicted', 'preserved', 'cleaned'}`).
- `ScopeValidationResult` — Resultado da auditoria de fronteira (`valid`, `changed_files`, `violations`, `symlink_escapes`, `forbidden_hits`).
- `WorktreeDiffArtifact` — Resultado da consolidação de alterações da worktree (`base_sha`, `patch_commit_sha`, `changed_files`, `artifact_ref`, `patch_path`, `has_changes`).
- `IntegrationOutcome` — Resultado auditável da integração serializada (`integration_id`, `run_id`, `target_branch`, `integration_worktree_path`, `expected_base_sha`, `result_sha`, `status`: `IntegrationStatus`, `merged_result_ids`, `conflicted_files`, `failure`).

### 3.2. Operações de `GitWorkspaceService`

1. `resolve_repo_root(repo_root)` $\rightarrow$ `Path`:
   - Resolve `os.path.realpath` e confirma via `git rev-parse --show-toplevel` que o caminho é a raiz canônica de um repositório Git real; recusa diretórios comuns, caminhos inexistentes ou symlinks fora da raiz com `workspace_invalid`.
2. `resolve_commit_sha(ref="HEAD", cwd=None)` $\rightarrow$ `str`:
   - Resolve qualquer referência Git (`HEAD`, branch ou SHA) para um `CommitSha` completo de 40 caracteres hexadecimais via `git rev-parse --verify <ref>^{commit}`.
3. `snapshot_operator_checkout()` e `assert_operator_checkout_intact(before, after=None)`:
   - Captura e valida que `head_sha`, `branch` e `status_porcelain` (incluindo arquivos untracked fora de `.orchestrator/`) não sofreram qualquer mutação.
4. `create_worktree(run_id, task_id, attempt_id, base_sha, branch_name=None)` $\rightarrow$ `WorkspaceRecord`:
   - Valida `base_sha` (40 hex existentes no repo), limpa locks órfãos se aplicável e executa `git worktree add -b <branch> <worktree_path> <base_sha>`.
   - **Proibição de pasta substituta (GAP A06):** Se `git worktree add` falhar por qualquer motivo, remove eventual diretório vazio residual e lança `GitWorkspaceError` com `ExecutionFailure(code="workspace_invalid")`. Jamais cria pasta comum sem `.git`.
   - Confirma que `<worktree_path>/.git` existe e que `HEAD` na worktree corresponde exatamente a `base_sha`.
5. `validate_worktree_scope(worktree_path, base_sha, allowed_paths, forbidden_paths=())` $\rightarrow$ `ScopeValidationResult`:
   - Inspeciona todos os arquivos modificados, adicionados, removidos, renomeados e untracked na worktree em relação a `base_sha`.
   - Detecta qualquer symlink que aponte para fora de `worktree_path` (`symlink_escapes`) e qualquer caminho fora de `allowed_paths` ou dentro de `forbidden_paths` (como `pyproject.toml` / `package.json` bloqueados na Wave 1).
6. `capture_and_commit_patch(record, commit_message, allowed_paths=("**/*",), forbidden_paths=())` $\rightarrow$ `WorktreeDiffArtifact`:
   - Valida o escopo antes de commitar; se houver violação, preserva a worktree e lança `GitWorkspaceError(code="scope_violation")`.
   - Se houver alterações válidas, cria commit real atribuído na branch da worktree (`patch_commit_sha` $\neq$ `base_sha`), exporta o diff binário (`git diff --binary <base_sha>..<patch_commit_sha>`) para `.orchestrator/run/<run_id>/patches/<attempt_id>.patch`, calcula SHA-256 e registra `ArtifactRef(kind=ArtifactKind.PATCH)`.
7. `integrate_results(run_id, expected_base_sha, results, target_branch=None, check_runner=None)` $\rightarrow$ `IntegrationOutcome`:
   - Adquire lock assíncrono por repositório (`asyncio.Lock`) + lock de arquivo em `.orchestrator/lock/` para garantir **exclusão mútua estrita** (`test_merge_serialized`).
   - Valida cada `TaskResult` com `assert_integrable(result, base_sha=expected_base_sha)`.
   - Cria ou reutiliza uma worktree dedicada de integração (`.orchestrator/worktree/integrate_<run_id>`) na branch `integrate/<run_id>` ancorada em `expected_base_sha` — **nunca faz checkout na raiz do operador**.
   - Realiza merge `--no-ff` de cada `patch_commit_sha` na ordem recebida:
     - Se ocorrer conflito (`returncode != 0`), coleta `conflicted_files`, aborta apenas o índice incompleto na worktree de integração se configurado ou preserva o estado para inspeção, marca os workspaces envolvidos como `conflicted` / `preserved`, **não remove** as worktrees e retorna `IntegrationOutcome(status=IntegrationStatus.CONFLICTED)` (`test_conflict_preserves_worktree`).
8. `cleanup_worktree(record, force_discard=False)` e `cleanup_stale_locks()`:
   - Antes de remover uma worktree, verifica se há modificações não commitadas (`git status --porcelain`) ou commits não preservados. Se houver diff não preservado e `force_discard=False`, recusa a remoção e marca o workspace como `preserved` (eliminando **GAP A05**).
   - `cleanup_stale_locks()` remove arquivos `.lock` órfãos em `.orchestrator/lock/` cujo PID criador não está mais vivo (`is_process_alive(pid) == False`) e executa `git worktree prune` para limpar registros administrativos órfãos.

---

## 4. Preconditions (Pré-condições)

1. `repo_root` deve ser a raiz de um repositório Git inicializado contendo pelo menos um commit válido (`base_sha`).
2. O binário `git` deve estar disponível no `PATH` do sistema operacional.
3. Para integração, todos os `TaskResult` devem estar em estado `TaskStatus.ACCEPTED`, `simulated=False`, com `patch_commit_sha != base_sha` e checks obrigatórios aprovados.

---

## 5. Postconditions (Pós-condições)

1. Toda worktree ativa criada por `create_worktree` possui arquivo/link `.git` válido e `HEAD == base_sha` no momento da criação.
2. O checkout principal do operador permanece na mesma branch, mesmo `HEAD` e com os mesmos arquivos staged/unstaged/untracked antes, durante e após qualquer operação de `GitWorkspaceService`.
3. Em caso de conflito de merge, violação de escopo ou falha de check, a worktree e seus artefatos permanecem fisicamente preservados em disco.
4. O estado do workspace e da integração é refletido no `ExecutionStore` quando acoplado.

---

## 6. Invariants (Invariantes)

- **Invariante de Worktree Real (Anti-GAP A06):** Nenhuma falha de `git worktree add` é mascarada com `mkdir`.
- **Invariante de Imutabilidade do Operador (Anti-GAP A05):** `GitWorkspaceService` nunca executa `git checkout`, `git reset`, `git merge` ou `git clean` no diretório raiz do operador (`repo_root`).
- **Invariante de Retenção de Evidência:** `cleanup_worktree` nunca apaga uma worktree suja sem ordem explícita de descarte (`force_discard=True`).
- **Invariante de Integração Serializada:** Apenas uma operação `integrate_results` pode executar por vez em um mesmo repositório.

---

## 7. Failure Modes (Modos de Falha e Recuperação)

| Cenário de Falha | Código de Erro (`ExecutionFailure.code`) | Comportamento Obrigatório |
|---|---|---|
| `repo_root` não é repositório Git ou `base_sha` inexiste | `workspace_invalid` | Recusa imediata sem criar diretórios em `.orchestrator/worktree/` |
| Falha no comando `git worktree add` | `workspace_invalid` | Remove diretório vazio residual se criado e lança erro; proibido fallback para pasta comum |
| Worker modifica arquivo fora de `allowed_paths` ou cria symlink externo | `scope_violation` | Bloqueia commit/aceite, preserva worktree para auditoria e retorna lista de violações |
| Conflito de merge durante `integrate_results` | `merge_conflict` | Marca integração como `conflicted`, preserva worktrees das tarefas e da integração, checkout do operador intacto |
| Tentativa de limpar worktree com diff não commitado (`force_discard=False`) | `dirty_worktree_preserved` | Mantém diretório em disco, atualiza status para `preserved` e levanta erro/aviso estruturado |
| Lock de integração órfão deixado por processo morto | — (Recuperação automática) | `cleanup_stale_locks()` verifica `is_process_alive(pid)` e remove o lock órfão antes de prosseguir |

---

## 8. How (Implementação T05 e Decomposição Obrigatória da T06 — 13 SP)

### 8.1. Escopo Implementado na T05 (8 SP)
- Módulo `src/hydra_orch/core/git_workspace.py` contendo `GitWorkspaceService`, `WorkspaceRecord`, `OperatorCheckoutSnapshot`, `ScopeValidationResult`, `WorktreeDiffArtifact` e `IntegrationOutcome`.
- Suíte hermética `tests/test_git_workspace.py` operando 100% sobre repositórios Git temporários (`tmp_path`).

### 8.2. Decomposição Obrigatória da T06 (13 SP) em Subtarefas Atômicas
Conforme regra normativa do [`backlog.md` (§3.3)](../a_context/backlog.md), a **T06 (Checks e integração — 13 SP)** fica decomposta nas 4 subtarefas abaixo para execução sequencial imediata:
- **T06.1 (3 SP) — Executor de Checks Determinísticos (`CheckRunner`):** Execução de `CheckSpec.command` (array `argv` sem shell) dentro da worktree da tentativa ou da integração, medindo duração, capturando `stdout`/`stderr` como `ArtifactRef(kind=ArtifactKind.CHECK_OUTPUT)` com SHA-256 e gerando `CheckResult` vinculado ao `tested_sha`.
- **T06.2 (3 SP) — Validação de Escopo, Diff e Promoção para `ready_for_review`:** Integração entre saída do `WorkerRunner`, validação `validate_worktree_scope`, geração de `patch_commit_sha` atribuível, execução de `TaskSpec.acceptance_criteria` e transição para `TaskStatus.READY_FOR_REVIEW` (ou `FAILED` se não houver diff em tarefa de código ou se algum check falhar).
- **T06.3 (4 SP) — Serviço de Aplicação `RunService` (`src/hydra_orch/core/run_service.py`):** Coordenação transacional completa do ciclo `submit` $\rightarrow$ `execute` $\rightarrow$ `review` (`review_result` com `expected_revision`) $\rightarrow$ `integrate` (`integrate_results` + reexecução dos checks combinados na worktree de integração) $\rightarrow$ `cancel`.
- **T06.4 (3 SP) — Suíte de Integração Ponta a Ponta (`tests/test_integration.py`):** Testes herméticos validando subprocesso real em worktree, bloqueio de arquivo fora de escopo, bloqueio de check falho, revisão otimista e integração serializada com checks combinados.

---

## 9. Examples (Exemplos de Aceite)

### Exemplo 1: Isolamento da Worktree e Preservação do Operador
```python
svc = GitWorkspaceService(repo_root=temp_repo)
snap_before = svc.snapshot_operator_checkout()
record = svc.create_worktree(
    run_id="run_01",
    task_id="task_a",
    attempt_id="att_01",
    base_sha=snap_before.head_sha,
)
# O worker edita arquivos em record.canonical_path
(record.canonical_path / "feature.py").write_text("x = 1\n", encoding="utf-8")
diff_art = svc.capture_and_commit_patch(
    record,
    commit_message="feat: add feature",
    allowed_paths=("feature.py",),
)
svc.assert_operator_checkout_intact(snap_before)
assert diff_art.patch_commit_sha != snap_before.head_sha
```

### Exemplo 2: Conflito de Merge Preservando Worktrees
Quando duas tentativas aceitas modificam a mesma linha de `shared.py` a partir do mesmo `base_sha`, `await svc.integrate_results(...)` executa o primeiro merge com sucesso na worktree `integrate/run_01`, detecta o conflito no segundo merge, registra `conflicted_files=("shared.py",)`, preserva ambas as worktrees em `.orchestrator/worktree/` com status `conflicted` e mantém a branch `main` do operador intocada.

---

## 10. GAPs Resolvidos

- **GAP-GIT-01 (A05):** Eliminado checkout/merge na raiz do operador e bloqueada remoção de worktree com diff não preservado.
- **GAP-GIT-02 (A06):** Eliminado fallback de `create_worktree` para diretório comum quando o Git falha.

---

## 11. Glossary e Acrônimos

| Termo | Significado |
|---|---|
| `base_sha` | Hash SHA-1 completo (40 hex) do commit base imutável de um run/tentativa |
| `integrate/<run_id>` | Branch dedicada criada em worktree própria para validação de merges serializados |
| `patch_commit_sha` | Hash SHA-1 completo (40 hex) do commit gerado na worktree da tentativa |
| Worktree | Árvore de trabalho adicional do Git vinculada ao repositório principal via `git worktree add` |

---

## 12. T27 — Resolução Assistida de Conflitos de Merge e Contract Amendment

### 12.1 Escopo e Contrato do Módulo

A Task **T27** estende a camada de integração Git ([`GitWorkspaceService`](../../src/hydra_orch/core/git_workspace.py)) com o serviço [`ConflictResolver`](../../src/hydra_orch/core/conflict_resolver.py) para inspecionar conflitos 3-way sem tocar o checkout ativo do operador, conduzir reparo isolado (`merge_repair`), suportar entrega manual ou descarte auditado e executar o protocolo de **Contract Amendment** (RT28 / PRD §3.6.3) quando um contrato da Wave 0 precisa evoluir durante a Wave 1.

#### Modelos Principais (`conflict_resolver.py` & `git_workspace.py`)

| Símbolo | Responsabilidade |
|---|---|
| `ThreeWayFileConflict` / `ThreeWayInspection` | Snapshot 3-way (`base_sha`, `ours_sha`, `theirs_sha`) com conteúdo `base`/`ours`/`theirs`, preview com marcadores e hunks extraídos via `git merge-tree --write-tree`. |
| `ConflictReport` (`ConflictedFileDetail`) | Relatório persistido em `conflict_reports` contendo `conflict_id`, `integration_id`, SHAs 3-way, `conflicted_files`, `file_details`, `resolution_options = ("auto_repair", "manual", "discarded")`, `status`, `repair_attempts_used`, `max_repair_attempts`, caminho/branch isolados, `resolved_sha` e `resolved_at`. |
| `RepairResult` | Resultado tipado de `auto_repair`, `resolve_manual`, `finalize_manual` e `discard`, com `checks_executed`, `artifacts`, `failures`, `resolved_sha` e `resolved_at`. |
| `ContractAmendmentProposal` | Proposta e estado de aplicação de emenda de contrato da Wave 0 (`status: "proposed" | "applied" | "rejected"`), `base_sha_before/after`, `run_revision_after`, `affected_wave1_task_ids`, `revalidated_worktrees` e `conflicted_worktrees`. |

#### API Pública de `ConflictResolver`

- `analyze(integration_id, *, base_sha=None, ours_sha=None, theirs_sha=None, max_repair_attempts=None, idempotency_key=None, correlation_id=None) -> ConflictReport`
- `get_report(conflict_id, *, include_details=True) -> ConflictReport` / `list_reports(*, integration_id=None, run_id=None) -> tuple[ConflictReport, ...]`
- `build_repair_prompt(report) -> str`
- `auto_repair(conflict_id, *, repairer=None, repair_command=None, checks=None, max_repair_attempts=None, actor="conflict_resolver", allowed_paths=None, forbidden_paths=(), idempotency_key=None, correlation_id=None) -> RepairResult`
- `resolve_manual(conflict_id, *, actor="operator", finalize=False, worktree_path=None, checks=None, commit_message=None, idempotency_key=None, correlation_id=None) -> RepairResult`
- `finalize_manual(...) -> RepairResult`
- `discard(conflict_id, *, actor="operator", reason="operator_discarded", idempotency_key=None, correlation_id=None) -> RepairResult`
- `propose_contract_amendment(run_id, wave0_task_id, *, reason, target_files, summary, actor, expected_run_revision, requested_by_task_id=None, authorized_actors=None, authorization_id=None, transition_requester_needs_context=False, idempotency_key=None, correlation_id=None) -> ContractAmendmentProposal`
- `apply_contract_amendment(amendment_id, *, actor, expected_run_revision, amend_fn=None, patch_files=None, amend_command=None, checks=None, authorized_actors=None, authorization_id=None, active_worktrees=(), idempotency_key=None, correlation_id=None) -> ContractAmendmentProposal`
- `get_pending_revalidations(run_id) -> tuple[str, ...]` / `mark_task_revalidated(run_id, task_id, *, tested_sha, actor="coordinator", idempotency_key=None, correlation_id=None) -> tuple[str, ...]`

#### Helpers 3-way e `merge_repair` em `GitWorkspaceService`

- `inspect_three_way(ours_sha, theirs_sha, *, base_sha=None)`: executa `git merge-tree --write-tree --name-only` (ou `--merge-base=<base>`) sem alterar index nem working tree do repositório raiz, extraindo versões `base`, `ours`, `theirs` e hunks com marcadores.
- `create_merge_repair_worktree(run_id, conflict_id, attempt_ordinal, ours_sha, theirs_sha=None, *, populate_conflict=True, branch_name=None, prefix="repair")`: cria worktree isolado sob `.orchestrator/worktree/` com branch dedicada `merge_repair/...` (ou prefixo `manual`/`amend`) e, quando `populate_conflict=True`, inicializa o estado de conflito 3-way com `git merge --no-commit --no-ff <theirs>`.
- `inspect_worktree_conflicts(worktree_path, candidate_files=(), *, require_staged=False)`: detecta marcadores residuais (`<<<<<<<`, `=======`, `>>>>>>>`) no disco e entradas não resolvidas em `--diff-filter=U` (bloqueando binários/deleções pendentes até resolução explícita).
- `commit_resolved_worktree(worktree_path, commit_message, *, candidate_files=())`: exige ausência de conflitos residuais, executa `git add -A` + `git commit` exclusivamente no worktree isolado e retorna `HEAD` resultante.
- `update_worktree_base(worktree_path, target_sha)`: reaplica alterações pendentes da task da Wave 1 sobre o novo `base_sha` da Wave 0 via `git rebase --onto` (abortando o rebase e reportando conflito sem corromper o worktree em caso de colisão).

---

### 12.2 Máquinas de Estado e Persistência SQLite

#### Estados de `conflict_reports`

A tabela `conflict_reports` (`migration/0002_control_plane.sql`) impõe `CHECK (status IN ('open','auto_repair','manual','discarded'))` e `resolved_at TEXT`. A distinção entre em-curso e concluído é governada pela combinação `(status, resolved_at)`:

```text
  [analyze(integration_id)]
             |
             v
   (status='open', resolved_at=NULL)
      |            |              \
      |            |               \ [discard()]
      v            v                v
auto_repair     manual          discarded
(res_at=NULL)  (res_at=NULL)    (res_at!=NULL)  [TERMINAL]
  |       |      |       |
  |       |      |       +--[discard()]--> discarded (res_at!=NULL)
  |       |      |
  |       |      +--[finalize_manual() + checks OK]--> manual (res_at!=NULL) [TERMINAL]
  |       |
  |       +--[falha / check != 0 / escopo / marcador residual]--> aborta MERGE_HEAD, volta p/ 'open' (res_at=NULL)
  |
  +--[marcadores OK + escopo OK + checks OK]--> auto_repair (res_at!=NULL) [TERMINAL]
```

Regras de consistência:
- **Qualquer transição rejeitada** após `resolved_at IS NOT NULL` dispara `InvalidTransitionError` (ou `ContractViolation` em `invalid_conflict_state`).
- Toda operação registra linha auditável em `commands(scope='conflict_resolver', idempotency_key, request_hash, response_json, status)` e evento tipado em `events` (`merge.conflict_analyzed`, `merge.conflict_repair_started`, `merge.conflict_repair_failed`, `merge.conflict_resolved`, `merge.conflict_discarded`).

#### Estados de `ContractAmendmentProposal`

```text
  [propose_contract_amendment()]
                 |
                 v
            "proposed"
            /        \
           |          \ [falha check Wave 0]
           v           v
       "applied"   (mantém run/base intactos; registra failure e check.finished)
```

---

### 12.3 Pré-condições, Pós-condições e Invariantes

1. **Preservação do Checkout do Operador (Invariante Absoluto):** Toda leitura e escrita ocorre no `Object Database` do Git ou em worktrees isolados sob `.orchestrator/worktree/`. Snapshot antes/depois (`snapshot_operator_checkout()` / `assert_operator_checkout_intact()`) garante que `HEAD`, branch atual, working tree e index do operador nunca são modificados.
2. **Orçamento de Tentativas (`max_repair_attempts`):** `auto_repair` rejeita novas execuções com `ContractViolation("repair_budget_exhausted")` quando `repair_attempts_used >= max_repair_attempts`, mantendo o relatório em `status='open'` sem criar merge sujo.
3. **Portão Obrigatório de Verificação:** Nem `auto_repair` nem `finalize_manual` podem concluir com `resolved_at != NULL` ou atualizar `integrations.status = 'integrated'` enquanto houver marcadores de conflito, violação de `allowed_paths`/`forbidden_paths`, ou qualquer `CheckSpec` com `exit_code != 0`. Em caso de falha no `auto_repair`, `git merge --abort` limpa `MERGE_HEAD`, preserva evidências/artefatos em `commands` e `events`, e retorna o registro para `'open'`.
4. **Protocolo Contract Amendment (Wave 0 -> Wave 1):**
   - **Pré-condições:** `wave0_task_id` deve ser uma task raiz (`dependencies == ()`), `actor` deve estar autorizado (`authorized_actors` e/ou `authorizations` ativa com escopo `'write'` ou `'integrate'`), e `expected_run_revision` deve coincidir com `runs.revision` (`OptimisticLockError` caso contrário).
   - **Pós-condições de `apply_contract_amendment`:** A emenda é aplicada em worktree isolado sobre `base_sha_before`; checks obrigatórios da Wave 0 precisam passar antes de qualquer atualização de banco; a revisão do run avança atomicamente (`revision + 1`), `runs.base_sha` recebe `base_sha_after`, é criada uma integração auditável em `integrations`, worktrees ativos da Wave 1 são re-baseados (classificados em `revalidated_worktrees` ou `conflicted_worktrees`), todas as tasks transitivamente dependentes da Wave 1 têm seu estado invalidado para revalidação (`PENDING/RUNNING/NEEDS_CONTEXT -> BLOCKED`, `READY_FOR_REVIEW -> REJECTED`), e `get_pending_revalidations(run_id)` lista todas as pendentes até confirmação via `mark_task_revalidated(...)`.

---

### 12.4 Modos de Falha Tratados

| Código / Exceção | Condição | Efeito Garantido |
|---|---|---|
| `ContractViolation("resource_not_found")` | `integration_id`, `conflict_id` ou `amendment_id` inexistente | Nenhuma mutação de estado ou worktree. |
| `ContractViolation("conflict_not_applicable")` | Integração já está em `'integrated'` ou `'discarded'` | Análise recusada. |
| `ContractViolation("repair_budget_exhausted")` | `repair_attempts_used >= max_repair_attempts` | Evento `merge.conflict_repair_failed` registrado; `conflict_reports` permanece `'open'`. |
| `ContractViolation("unresolved_conflicts_remain")` | `finalize_manual` chamado com marcadores ou entradas não resolvidas | `conflict_reports` permanece `'manual'` com `resolved_at=NULL` e worktree preservado. |
| `RepairResult(repaired=False, status='open')` | `scope_violation`, `unresolved_conflicts_remain`, `post_repair_check_failed` ou erro do reparador em `auto_repair` | `git merge --abort` no worktree isolado, `resolved_at=NULL`, tentativa contabilizada no orçamento. |
| `ContractViolation("authorization_denied")` | Ator não autorizado ou `authorization_id` revogado/sem escopo | Proposta/aplicação de emenda recusada antes de tocar Git. |
| `OptimisticLockError` | `expected_run_revision` divergente de `runs.revision` | Emenda rejeitada sem mutar `base_sha`. |
| `ContractViolation("amendment_check_failed")` | Check da Wave 0 falha ao aplicar emenda | Emenda abortada, `runs.base_sha` e `runs.revision` preservados, tarefas Wave 1 inalteradas. |
| `IdempotencyConflictError` | Mesma `idempotency_key` reutilizada com payload diferente | Rejeição antes de executar efeitos colaterais. |

---

### 12.5 Exemplos de Uso

```python
resolver = ConflictResolver(store, git_workspace, repo_root=repo_root)

# 1. Inspeção 3-way sem tocar o checkout do operador
report = await resolver.analyze(outcome.integration_id, max_repair_attempts=2)

# 2. Tentativa isolada de merge_repair + validação por checks
res = await resolver.auto_repair(
    report.conflict_id,
    repairer=my_merge_repairer,
    checks=mandatory_checks,
    allowed_paths=("src/shared.py",),
)
if not res.repaired:
    # Escalona para resolução manual preservando worktree isolado
    manual = await resolver.resolve_manual(report.conflict_id, actor="dev-alice", finalize=False)
    # ... operador resolve no caminho manual.repair_worktree_path ...
    res = await resolver.finalize_manual(report.conflict_id, actor="dev-alice", checks=mandatory_checks)

# 3. Contract Amendment na Wave 0 com invalidação de dependentes da Wave 1
proposal = await resolver.propose_contract_amendment(
    run_id,
    wave0_task_id,
    reason="Adicionar campo tenant_id ao payload compartilhado",
    target_files=("contracts/api.py",),
    summary="Contrato v2 com tenant_id",
    actor="lead-architect",
    expected_run_revision=1,
    authorization_id=auth_id,
)
applied = await resolver.apply_contract_amendment(
    proposal.amendment_id,
    actor="lead-architect",
    expected_run_revision=1,
    patch_files={"contracts/api.py": new_contract_source},
    checks=wave0_checks,
    authorization_id=auth_id,
    active_worktrees=active_wave1_worktrees,
)
pending_ids = await resolver.get_pending_revalidations(run_id)
```
