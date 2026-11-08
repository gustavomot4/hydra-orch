# Executor CLI e Subprocessos — S04 / T04

**Identificador Formal:** `executor_cli.md`
**Caminho Canônico:** `doc/b_spc/executor_cli.md`
**Versão:** `v01_00_0000`
**Status:** `APROVADO / IMPLEMENTADO`
**Autoridade:** Derivado normativo de [`doc/b_spc/prd_tecnico.md`](prd_tecnico.md) (§3.4, §3.6.4, §3.10, §8.1 e RNF01/RNF03), [`doc/b_spc/prd_funcional.md`](prd_funcional.md) (RF04, RF06), [`doc/g_code/architecture.md`](../g_code/architecture.md), [`doc/i_infra/README.md`](../i_infra/README.md) e [`contrato_execucao.md`](contrato_execucao.md) (S02/T02).
**Escopo:** Especificação canônica do executor de subprocessos de agentes CLI (`WorkerRunner`), montagem determinística de `argv`/`stdin` por driver, validação de diretório operacional (`cwd`), filtragem de ambiente (`env`), captura de artefatos com SHA-256, timeout e cancelamento idempotente com encerramento verificado da árvore de processos (`tree kill`) e isolamento estrito do modo `dry_run` em `src/hydra_orch/bridge/worker_runner.py`.

---

## 1. Propósito

Formalizar o transporte de execução de subprocessos locais do **hydra-orch** em `src/hydra_orch/bridge/worker_runner.py`, garantindo que cada tentativa de tarefa (`TaskAttempt`) seja executada em um diretório de trabalho (`cwd`) real e validado, com ambiente (`env`) expurgado de segredos não autorizados, argumentos construídos sem invocação de shell (`shell=False`), captura de logs (`stdout`/`stderr`) como artefatos verificáveis, encerramento garantido de processos descendentes (`tree kill`) em caso de timeout ou cancelamento, e proibição absoluta de sucesso fabricado quando uma CLI não estiver instalada.

---

## 2. Justificativa

Na revisão arquitetural inicial (`plano_desenvolvimento.md §2.1`), duas falhas bloqueadoras foram identificadas no scaffold:
1. **GAP A02 (P0):** `worker_runner.py` criava `CONTRACT_APPLIED.md` e retornava `success=True` quando a CLI estava ausente, mascarando ausência de ferramenta como sucesso de engenharia.
2. **GAP A11 (P1):** O encerramento por timeout ou cancelamento não garantia o extermínio verificável da árvore de processos filhos nem rastreava tentativas ativas para cancelamento idempotente.
3. **Vazamento de Ambiente:** O método `_Filtered_env()` retornava `dict(os.environ)` integralmente, expondo chaves privadas, tokens e credenciais do processo pai ao worker.

A especificação S04 / T04 resolve integralmente essas lacunas.

---

## 3. Contrato

### 3.1. Drivers CLI e Montagem de Invocação (`build_invocation`)
- Nenhum comando é executado via `shell=True`. Todo disparo utiliza `asyncio.create_subprocess_exec` com tupla imutável de argumentos (`argv: Tuple[str, ...]`).
- `build_invocation(driver: str, prompt: str, *, extra_args: Sequence[str] = (), resume_session: Optional[str] = None, custom_command: Optional[Sequence[str]] = None) -> InvocationPlan`:
  - **`codex`**: `("codex", "exec", "--sandbox", "workspace-write", ...)` (ou `"resume", <session>` quando `resume_session` informado), recebendo o prompt via `stdin`.
  - **`claude` / `claude_code`**: `("claude", "--print", "--output-format", "text", ...)` recebendo o prompt via `stdin`.
  - **`opencode`**: `("opencode", "run", prompt, ...)`.
  - **`agy`**: `("agy", "chat", "--prompt", prompt, ...)`.
  - **`gemini` / `gemini_cli`**: `("gemini", "--prompt", prompt, ...)`.
  - **`aider`**: `("aider", "--yes-always", "--no-auto-commits", "--message", prompt, ...)`.
  - **`custom` / `python_fake`**: Executa o `custom_command` explícito (ex.: `(sys.executable, "-c", ...)` em fixtures herméticas de teste) com `cwd` real e `stdin` opcional.

### 3.2. Resolução de `cwd` e Filtragem de Variáveis de Ambiente (`filter_worker_env`)
- **Diretório Operacional (`cwd`):** O caminho `worktree_path` é resolvido canonicamente via `os.path.realpath` / `Path.resolve()`. Se o diretório não existir ou não for um diretório válido, a execução falha antes do spawn com `error="invalid_workspace_cwd"` e `process_status="crashed"`.
- **Filtragem de Ambiente (`filter_worker_env`):**
  - Preserva apenas variáveis operacionais essenciais do sistema (`PATH`, `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, `TEMP`, `TMP`, `TMPDIR`, `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `HOMEDRIVE`, `HOMEPATH`, `LANG`, `LC_ALL`, `TERM`, `PYTHONPATH`, `VIRTUAL_ENV`, `SYSTEMDRIVE`).
  - Expurga qualquer variável cujo nome contenha sufixos/padrões sensíveis (`TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `PRIVATE_KEY`, `API_KEY`, `ACCESS_KEY`, `CREDENTIAL`, `AUTH`, `COOKIE`, `SESSION_KEY`, `DATABASE_URL`), a menos que seja explicitamente autorizada em `allowed_env`.
  - Injeta `HYDRA_WORKER_ISOLATED="1"` e `GIT_TERMINAL_PROMPT="0"` para impedir travamentos interativos de credenciais Git.

### 3.3. Proibição de Sucesso Fabricado e Isolamento do Modo `dry_run` (GAP A02)
- Em execução normal (`dry_run=False`), se o executável não for encontrado por `shutil.which`, o runner **nunca** escreve arquivos no workspace e retorna imediatamente:
  - `success = False`
  - `simulated = False`
  - `process_status = "crashed"`
  - `error = "executor_unavailable"`
  - `failure = FailureDetail(code="executor_unavailable", message=..., retryable=False)`
- O modo simulado (`dry_run=True`) só é ativado mediante solicitação explícita do chamador, grava `CONTRACT_APPLIED.md` para inspeção de dry-run e retorna obrigatoriamente `simulated = True` (impedido pelos contratos S02/T02 de ser aceito como resultado real ou integrado).

### 3.4. Timeout, Cancelamento Idempotente e Tree Kill Verificado (RF04, RF06, RT04, RNF03)
- **Registro de processos ativos:** `WorkerRunner` mantém o mapa de processos em execução por `attempt_id` (e por `pid`).
- **`cancel_process_tree(pid: int)`:**
  - **Windows (`sys.platform == "win32"`):** Executa `taskkill /PID <pid> /T /F` via subprocesso assíncrono para encerrar o processo pai e toda a árvore de filhos/netos, com fallback para `os.kill` / `TerminateProcess`.
  - **POSIX (`Linux` / `macOS`):** Inicia o worker com `start_new_session=True` (grupo de processos próprio) e envia `os.killpg(pgid, signal.SIGTERM)` seguido de `signal.SIGKILL`.
  - **Verificação pós-kill (`verify_tree_killed`):** Confirma que o PID principal e eventuais PIDs descendentes monitorados não estão mais ativos (`is_process_alive(pid) == False`).
- **`cancel(attempt_id: str) -> Dict[str, Any]`:**
  - Cancela uma tentativa ativa em andamento, acionando `cancel_process_tree` e marcando a tentativa como `process_status="cancelled"`, `exit_reason="cancelled_by_operator"`.
  - **Idempotência:** Chamar `cancel(attempt_id)` repetidas vezes ou para uma tentativa já finalizada/inexistente retorna `{"cancelled": True, "already_terminated": True}` sem erro.

### 3.5. Captura de Artefatos (`stdout.log`, `stderr.log`)
- Quando `artifacts_dir` e `run_id`/`attempt_id` são fornecidos, o runner persiste `stdout.log` e `stderr.log` de forma atômica (arquivo temporário + `os.replace`), calcula o hash SHA-256 e `size_bytes` de cada saída e retorna objetos `Artifact` (`kind="check_output"` ou `kind="log"`) prontos para registro no `ExecutionStore`.

---

## 4. Pré-condições

1. Contratos `model.py` (T02) e `ExecutionStore` (T03) implementados.
2. Diretório de trabalho (`worktree_path`) existente no sistema de arquivos para execuções reais.

---

## 5. Pós-condições

1. O subprocesso executa comprovadamente com `cwd` igual ao caminho canônico resolvido de `worktree_path`.
2. Nenhum segredo do ambiente pai vaza para o subprocesso sem autorização explícita.
3. Em caso de timeout ou cancelamento, nenhum processo filho ou neto da árvore permanece em execução após o retorno de `execute_task_in_worktree` / `cancel`.
4. A latência de despacho do subprocesso local (tempo entre o agendamento em `WorkerRunner` e o spawn do processo) é $\le 300\text{ ms}$ em fixture local (RNF01).

---

## 6. Invariantes

1. **Invariante `shell=False`:** Nenhum comando de worker ou kill utiliza interpretação de shell.
2. **Invariante Anti-Fabricação (GAP A02):** `simulated=False` exige execução real de processo do sistema operacional; ausência de binário implica `success=False` e `error="executor_unavailable"`.
3. **Invariante de Separação Processo vs. Tarefa:** `exit_code == 0` indica apenas `process_status = ProcessStatus.EXITED`; a validação de diff e checks pertence às etapas de validação (T06).

---

## 7. Falhas e Tratamento de Exceções

| Situação | `process_status` | `error` / `FailureDetail.code` | Comportamento |
|---|---|---|---|
| CLI ausente (`dry_run=False`) | `crashed` | `executor_unavailable` | Não cria arquivos; falha imediata antes de spawn |
| `worktree_path` inexistente/inválido | `crashed` | `invalid_workspace_cwd` | Falha imediata antes de spawn |
| Argumentos/driver inválidos | `crashed` | `invalid_driver_invocation` | Levanta `ContractViolation` ou retorna erro estruturado |
| Subprocesso retorna `exit_code != 0` | `exited` | `worker_nonzero_exit` | Preserva `stdout`, `stderr` e `exit_code` |
| Timeout estourado | `timed_out` | `execution_timed_out` | Mata árvore (`tree kill`), confirma fim dos filhos e preserva saída parcial |
| Cancelamento explícito (`cancel()`) | `cancelled` | `execution_cancelled` | Mata árvore (`tree kill`), confirma fim e retorna estado `cancelled` |

---

## 8. Procedimento e Aceite

1. **Testes Obrigatórios em `tests/test_worker_runner.py`:**
   - `test_cwd_resolved`: Subprocesso real verifica e grava `os.getcwd()` e altera arquivo dentro da worktree temporária.
   - `test_env_filtered`: Segredos no `os.environ` (`OPENAI_API_KEY`, `GITHUB_TOKEN`, `MY_SECRET_KEY`, `DATABASE_URL`) são removidos do ambiente do subprocesso, enquanto variáveis explícitas em `allowed_env` e `PATH` permanecem.
   - `test_fake_only_dry_run`: CLI ausente com `dry_run=False` falha com `executor_unavailable` sem tocar no disco; `dry_run=True` marca `simulated=True`.
   - `test_timeout_tree_kill` e `test_verify_tree_kill`: Processo pai que cria processo filho dormindo em loop tem tanto o pai quanto o filho exterminados no timeout, comprovando que o PID do filho não sobrevive.
   - `test_cancel_idempotent`: Cancelamento concorrente durante execução mata a árvore de processos e chamadas subsequentes a `cancel()` são idempotentes.
   - `test_dispatch_latency`: Despacho de subprocesso local ocorre em $< 300\text{ ms}$ (RNF01).
2. **Gate de Cobertura:** $\ge 80\%$ em `src/hydra_orch/bridge/worker_runner.py` e 100% da suíte `pytest tests` aprovada offline.

---

## 9. Exemplos

### 9.1. Execução Real em Fixture com Subprocesso e Verificação de `cwd`
```python
runner = WorkerRunner(default_cli="codex")
result = await runner.execute_task_in_worktree(
    worktree_path=tmp_worktree,
    prompt="Update module",
    custom_command=(sys.executable, "-c", "import pathlib; pathlib.Path('out.txt').write_text('ok')"),
)
assert result["success"] is True
assert result["simulated"] is False
assert result["process_status"] == "exited"
assert (tmp_worktree / "out.txt").read_text() == "ok"
```

### 9.2. Cancelamento Idempotente com Tree Kill Verificado
```python
cancel_res = await runner.cancel(attempt_id="att-001")
assert cancel_res["cancelled"] is True
# Segunda chamada é idempotente
cancel_again = await runner.cancel(attempt_id="att-001")
assert cancel_again["already_terminated"] is True
```
