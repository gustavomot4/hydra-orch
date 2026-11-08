# S13 — Entrega Reproduzível, CI Hermético e Manual Operacional M1 (`entrega_operacao.md`)

**Identificador Formal:** `entrega_operacao.md`  
**Caminho Canônico:** `doc/b_spc/entrega_operacao.md`  
**Etapa / Task:** `S13 / M1 / T08`  
**Versão:** `v01_00_0000`  
**Status:** `IMPLEMENTADO (NÚCLEO M1)`  
**Autoridade:** Derivado normativo de [`prd_funcional.md`](prd_funcional.md) (RF15), [`prd_tecnico.md`](prd_tecnico.md) (RT11, RT12, RNF03, RNF09, §8.1 T08), [`../h_test/README.md`](../h_test/README.md) e [`../j_manual/README.md`](../j_manual/README.md).

---

## 1. Purpose (Propósito)

Estabelecer o contrato de entrega reproduzível do **Marco M1 (V0 — Núcleo Verificável Local)**, compreendendo:
1. Pipeline de Integração Contínua (`.github/workflows/ci.yml`) 100% offline e hermético em matriz multiplataforma (`ubuntu-latest`, `windows-latest`, `macos-latest`), separado da certificação opcional de drivers externos.
2. Configuração empacotada e marcadores de teste em `pyproject.toml` (Python $\ge 3.10$, `pytest`, markers e empacotamento).
3. Manual operacional do Marco M1 em `doc/j_manual/README.md`, distinguindo explicitamente os comandos e rotas verificados em M1 (`T01–T08`) das capacidades planejadas para `M2–M4` (`T09–T28`).
4. Verificação criptográfica de integridade (`SHA-256`) dos artefatos retidos e comprovação automatizada de execução offline sem acesso externo (`test_offline_ci_no_external` e `test_artifact_hash_verification`).

---

## 2. Why (Justificativa)

Antes da T08, o repositório carecia de um workflow `.github/workflows/ci.yml` que executasse a suíte hermética nos três sistemas operacionais alvo (Linux, Windows e macOS) e garantisse que nenhuma regressão dependesse de localhost externo, GPU ou chaves de provedores pagos (GAP A18). Além disso, o manual operacional precisava refletir fielmente os comandos reais da CLI M1 (`hydra submit`, `hydra inspect`, `hydra review`, `hydra integrate`, `hydra cancel`, `hydra retry`) e as rotas `/v1/control-plane/*` entregues na T07, evitando confundir o operador entre o que já está certificado no Gate G-M1 e o que pertence aos horizontes futuros (V1–V4).

---

## 3. Contract (Contrato Técnico)

### 3.1. Workflow de CI Hermético (`.github/workflows/ci.yml`)
- **Job padrão (`hermetic-ci`):**
  - Disparo automático em `push` (`main`, `task/**`) e `pull_request`.
  - Matriz de sistemas operacionais: `ubuntu-latest`, `windows-latest`, `macos-latest`.
  - Matriz de versões Python: `3.10` e `3.12`.
  - Variáveis de ambiente estritas: `HYDRA_OFFLINE_CI=1`, `PYTHONDONTWRITEBYTECODE=1`, `GIT_TERMINAL_PROMPT=0`, `PYTHONUTF8=1`.
  - Zero segredos ou chaves de provedores pagos injetados no job padrão.
  - Verificação de formatação (`git diff --check`), instalação editável (`pip install -e ".[dev]"`), smoke test da CLI (`hydra --help`) e execução integral da suíte (`python -m pytest tests -q`).
- **Job isolado de certificação de driver (`driver-certification`):**
  - Executado exclusivamente sob demanda via `workflow_dispatch` quando `inputs.run_driver_certification == true`.
  - Separado física e logicamente do gate offline (RT12).

### 3.2. Configuração de Pacote e Testes (`pyproject.toml`)
- `requires-python = ">=3.10"`.
- Script CLI instalado: `hydra = "hydra_orch.cli:app"`.
- Configuração `[tool.pytest.ini_options]` com `testpaths = ["tests"]` e registro formal dos markers `unit`, `integration`, `e2e`, `negative`, `security`, `a11y`.

### 3.3. Retenção e Verificação de Artefatos (RF15 / RT11)
- Todo artefato persistido em `.orchestrator/run/<run_id>/artifacts/` possui hash `SHA-256` e tamanho em bytes gravados na tabela `artifacts`.
- O descarte de runtime (`RunService.discard_run_runtime`) remove worktrees efêmeras após encerramento, mas preserva e valida o `SHA-256` de cada artefato retido em disco, lançando `StorageIntegrityError` se houver truncamento, remoção indevida ou adulteração de bytes.

---

## 4. Preconditions (Pré-condições)

1. Tasks **T01 a T07** implementadas e aprovadas.
2. Git $\ge 2.30$ e Python $\ge 3.10$ disponíveis no runner de CI ou estação do operador.

---

## 5. Postconditions (Pós-condições)

1. `.github/workflows/ci.yml` executa a suíte hermética sem rede externa nos 3 SOs alvo.
2. `doc/j_manual/README.md` documenta o fluxo operacional completo de M1 com comandos exatos e tabela de distinção M1 vs. M2–M4.
3. O Gate **G-M1 (Marco M1 — Núcleo Verificável Local)** encontra-se 100% cumprido.

---

## 6. Invariants (Invariantes)

1. **Invariante de Hermeticidade (RT12 / RNF03):** Nenhum teste executado no job padrão de CI abre conexões para provedores externos pagos, túneis SSH reais ou daemon OmniRoute externo.
2. **Invariante de Integridade de Evidência (RT11):** Nenhum artefato de execução (`patch`, `check_output`, `log`, `handoff`) é considerado válido se o seu `SHA-256` em disco divergir do registro transacional no SQLite.
3. **Invariante de Transparência Documental:** O manual operacional nunca descreve comandos de horizontes futuros como já ativos no binário M1 sem identificá-los explicitamente.

---

## 7. Failure Modes (Modos de Falha)

| Falha | Comportamento Obrigatório | Código / Sinal |
|-------|---------------------------|----------------|
| Artefato adulterado ou ausente no disco durante verificação/descarte | Levanta `StorageIntegrityError` (`HTTP 500`) e aborta o descarte | `storage_integrity_error` |
| Tentativa de descartar run ainda ativo sem `force=True` | Recusa a operação com `ContractViolation` (`HTTP 409`) | `run_still_active` |
| Teste tenta depender de serviço externo não mockado | Falha determinística no ambiente `HYDRA_OFFLINE_CI=1` | Exit code $\neq 0$ no CI |

---

## 8. How (Implementação)

1. **`.github/workflows/ci.yml`**: Define os jobs `hermetic-ci` (matriz OS $\times$ Python) e `driver-certification` (`workflow_dispatch`).
2. **`pyproject.toml`**: Declara dependências, scripts, `[tool.pytest.ini_options]` e markers.
3. **`doc/j_manual/README.md`**: Inclui o Guia Operacional Verificado do Marco M1 (seção M1 dedicada + notas de escopo por seção).
4. **`tests/test_checkpointer.py`**: Implementa `test_restart_preserves_state`, `test_events_monotonic`, `test_offline_ci_no_external` e `test_artifact_hash_verification`.

---

## 9. Examples (Exemplo de Execução Operacional M1)

```bash
# 1. Executar suíte hermética offline
python -m pytest tests -q

# 2. Submeter, executar e inspecionar run em modo dry-run verificável via CLI
hydra submit \
  --repo-root /caminho/do/repo \
  --objective "Implementar feature M1" \
  --allowed-paths "src/**" \
  --acceptance-cmd "python -c \"print('ok')\"" \
  --execute --dry-run --fake-Touch "src/feature.py=ok\n" \
  --json

# 3. Revisar e integrar na branch dedicada integrate/<run_id>
hydra review <run_id> <task_id> --accept --reason "Checks aprovados" --expected-revision 1 --json
hydra integrate <run_id> --json
```

---

## 10. GAPs Resolvidos

- **GAP A18:** Suíte de testes superficial dependente de localhost substituída por 239+ testes herméticos offline e pipeline CI multiplataforma.

---

## 11. Glossary e Acrônimos

| Termo | Definição |
|-------|-----------|
| **CI Hermético** | Pipeline de integração contínua que roda isolado de contas externas, GPUs ou serviços de rede fora do processo de teste. |
| **Driver Certification** | Processo separado de validação de um executor CLI real em um sistema operacional específico. |
| **G-M1** | Gate de saída do Marco M1 (Núcleo Verificável Local — Tasks T01 a T08). |
