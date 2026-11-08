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
