# h_test — Especificações de Testes e Matriz de Rastreabilidade

**Identificador Formal:** `h_test`
**Caminho Canônico:** `doc/h_test/`
**Versão:** `v01_01_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch, complementando `prd_funcional.md`, `prd_tecnico.md` e `model.py`.
**Escopo:** Matriz de rastreabilidade RF/RT → testes, estratégia de testes herméticos, critérios de cobertura, testes de segurança e acessibilidade.

---

Este diretório concentra as especificações formais de testes do **hydra-orch**, garantindo que cada requisito funcional e técnico tenha evidência de validação automatizada.

## 1. Matriz de Rastreabilidade (RF/RT → Testes)

### 1.1 Núcleo (V0 - RF01–RF15, RT01–RT12)

| Requisito | Testes Unitários | Testes de Integração | Testes de Sistema/E2E | Critério de Cobertura |
|-----------|------------------|----------------------|------------------------|----------------------|
| **RF01 / RT01** | `tests/test_config.py::test_resolve_aliases`<br>`tests/test_config.py::test_reject_unknown` | `tests/test_server.py::test_create_project_valid_root`<br>`tests/test_server.py::test_create_project_invalid_root` | - | 100% branches config.py |
| **RF02 / RT01** | `tests/test_config.py::test_executor_config_validation`<br>`tests/test_config.py::test_direct_mode_no_gateway` | `tests/test_server.py::test_run_with_executor_config` | - | 100% validações |
| **RF03 / RT02** | `tests/test_model.py::test_run_spec_schema`<br>`tests/test_model.py::test_idempotency_key_validation` | `tests/test_server.py::test_create_run_idempotent`<br>`tests/test_server.py::test_create_run_idempotent_conflict` | `tests/test_e2e.py::test_submit_and_review_flow` | 100% schemas Pydantic |
| **RF04 / RT04** | `tests/test_worker_runner.py::test_cwd_resolved`<br>`tests/test_worker_runner.py::test_env_filtered`<br>`tests/test_worker_runner.py::test_timeout_tree_kill`<br>`tests/test_worker_runner.py::test_fake_only_dry_run` | `tests/test_integration.py::test_executor_real_subprocess` | `tests/test_e2e.py::test_task_execution_worktree` | Tree kill verificado no SO |
| **RF05 / RT03** | `tests/test_checkpointer.py::test_restart_preserves_state`<br>`tests/test_checkpointer.py::test_events_monotonic` | `tests/test_server.py::test_sse_replay_cursor` | `tests/test_e2e.py::test_sse_reconnection` | WAL + busy_timeout |
| **RF06 / RT04** | `tests/test_worker_runner.py::test_cancel_idempotent`<br>`tests/test_worker_runner.py::test_verify_tree_kill` | `tests/test_server.py::test_cancel_run`<br>`tests/test_server.py::test_cancel_task_in_swarm` | `tests/test_e2e.py::test_cancel_preserves_worktree` | Verificação SO certificada |
| **RF07 / RT06** | `tests/test_model.py::test_review_decision_schema`<br>`tests/test_model.py::test_expected_revision_concurrency` | `tests/test_server.py::test_review_accepted`<br>`tests/test_server.py::test_review_rejected` | `tests/test_e2e.py::test_review_requires_checks` | Controle otimista |
| **RF08 / RT05** | `tests/test_git_workspace.py::test_merge_serialized`<br>`tests/test_git_workspace.py::test_conflict_preserves_worktree` | `tests/test_integration.py::test_integrate_accepted_results`<br>`tests/test_integration.py::test_integrate_conflict` | `tests/test_e2e.py::test_integration_branch_dedicated` | Checks combinados |
| **RF09 / RT07** | `tests/test_scheduler.py::test_validate_dag_kahn`<br>`tests/test_scheduler.py::test_semaphore_concurrency`<br>`tests/test_scheduler.py::test_ready_tasks_dispatch` | `tests/test_engine.py::test_swarm_dag_execution` | `tests/test_e2e.py::test_swarm_parallel_tasks` | Aciclicidade + semáforo |
| **RF10 / RT08** | `tests/test_healer.py::test_extract_failure`<br>`tests/test_healer.py::test_build_repair_prompt`<br>`tests/test_healer.py::test_repair_budget_ceiling`<br>`tests/test_handoff.py::test_handoff_checkpoint_structure`<br>`tests/test_handoff.py::test_code_stitching_anchor` | `tests/test_engine.py::test_relay_handoff`<br>`tests/test_engine.py::test_persist_pause_resume` | `tests/test_e2e.py::test_relay_fallback` | Âncora sintática validada |
| **RF11 / RT09** | `tests/test_omniroute.py::test_quota_unknown_stale`<br>`tests/test_omniroute.py::test_circuit_breaker`<br>`tests/test_omniroute.py::test_fallback_chain` | `tests/test_server.py::test_route_decision_audit` | - | Never 100% invented |
| **RF12 / RT12** | `tests/test_healer.py::test_max_repair_attempts`<br>`tests/test_checkpointer.py::test_offline_ci_no_external` | - | - | CI 100% offline |
| **RF13 / RT10** | `tests/test_server.py::test_auth_required`<br>`tests/test_server.py::test_cors_strict_allowlist`<br>`tests/test_redaction.py::test_redact_tokens`<br>`tests/test_redaction.py::test_redact_ssh_keys` | `tests/test_server.py::test_ui_commands_same_service` | `tests/test_e2e.py::test_ui_sse_reconnect` | Redaction 100% segredos |
| **RF14 / RT14** | `tests/test_transport.py::test_ssh_host_key_verification`<br>`tests/test_transport.py::test_cdp_target_validation` | `tests/test_integration.py::test_remote_execution_isolated` | - | Certificação driver/SO |
| **RF15 / RT11** | `tests/test_checkpointer.py::test_artifact_hash_verification`<br>`tests/test_redaction.py::test_export_redacted` | `tests/test_server.py::test_discard_preserves_retention` | `tests/test_e2e.py::test_export_audit_dossier` | Hash SHA-256 verificado |

### 1.2 Expansão (V1–V4 - RF16–RF30, RT13–RT30)

| Requisito | Testes Unitários | Testes de Integração | Critério de Cobertura |
|-----------|------------------|----------------------|----------------------|
| **RF16 / RT13** | `tests/test_workspace_registry.py::test_hierarchy_persistence`<br>`tests/test_workspace_registry.py::test_traversal_blocked`<br>`tests/test_workspace_registry.py::test_auth_not_inherited` | `tests/test_server.py::test_multi_repo_project` | Traversal + allowlist |
| **RF17 / RT14** | `tests/test_agent_registry.py::test_capability_declaration`<br>`tests/test_agent_registry.py::test_uncertified_blocked_production`<br>`tests/test_agent_registry.py::test_cli_absent_is_error` | `tests/test_profile.py::test_profile_validation_incompatible` | Certificação driver/SO |
| **RF17 / RT15** | `tests/test_profile.py::test_snapshot_immutable_hash`<br>`tests/test_profile.py::test_profile_change_not_affect_running` | `tests/test_server.py::test_profile_resolve_pre_exec` | Hash imutável por run |
| **RF18 / RT16** | `tests/test_session.py::test_sse_replay_last_event_id`<br>`tests/test_session.py::test_dedup_monotonic_seq`<br>`tests/test_session.py::test_cursor_expired_410` | `tests/test_server.py::test_session_threads_tree` | Replay + dedup |
| **RF19 / RT17** | `tests/test_metrics.py::test_unknown_never_zero`<br>`tests/test_metrics.py::test_partial_aggregation_flagged`<br>`tests/test_metrics.py::test_provenance_tracking` | `tests/test_server.py::test_metrics_endpoint_status` | unknown/stale/observed |
| **RF20 / RT18** | `tests/test_route_selector.py::test_direct_selector_no_gateway`<br>`tests/test_route_selector.py::test_omniroute_candidates_audit`<br>`tests/test_route_selector.py::test_ineligible_never_selected` | `tests/test_server.py::test_route_decision_endpoint` | Auditável |
| **RF21 / RT19** | `tests/test_memory.py::test_consent_required_write`<br>`tests/test_memory.py::test_revocation_blocks_new_runs`<br>`tests/test_memory.py::test_checkpoint_isolation` | `tests/test_server.py::test_memory_consent_flow` | Tabelas separadas |
| **RF22 / RT20** | `tests/test_discovery.py::test_scan_allowlist_only`<br>`tests/test_discovery.py::test_hash_untrusted_initial`<br>`tests/test_discovery.py::test_auto_untrusted_on_hash_change` | `tests/test_server.py::test_discovery_approve_reject` | Opt-in + untrusted |
| **RF17, RF22 / RT21** | `tests/test_secrets.py::test_secret_ref_rejects_raw_value_and_unavailable_providers`<br>`tests/test_secrets.py::test_missing_secret_and_reserved_env_block_spawn`<br>`tests/test_secrets.py::test_mcp_remote_transports_refused_and_timeout_tree_kill` | `tests/test_secrets.py::test_resolve_at_spawn_filtered_env_and_worker_echo_scrubbed`<br>`tests/test_secrets.py::test_secret_in_patch_rejected`<br>`tests/test_secrets.py::test_mcp_stdio_handshake_tools_permissions_and_redaction` | SecretRef + env filtrado + MCP stdio |
| **RF23 / RT23** | `tests/test_preferences.py::test_scoped_reversible`<br>`tests/test_preferences.py::test_snapshot_immutable`<br>`tests/test_a11y.py::test_keyboard_navigation`<br>`tests/test_a11y.py::test_focus_visible`<br>`tests/test_a11y.py::test_semantic_roles`<br>`tests/test_a11y.py::test_contrast_wcag_aa`<br>`tests/test_a11y.py::test_reduce_motion` | `tests/test_server.py::test_preference_snapshot_run` | Checklist automatizado |
| **RF24 / RT22** | `tests/test_extension.py::test_manifest_validation`<br>`tests/test_extension.py::test_install_requires_active_extension_consent`<br>`tests/test_extension.py::test_process_isolation_no_db`<br>`tests/test_extension.py::test_revocation_immediate_block`<br>`tests/test_extension.py::test_checksum_tampering_on_disk_quarantines`<br>`tests/test_extension.py::test_rollback_restores_previous_approved_version` | `tests/test_server.py::test_extension_lifecycle` (T23) | Isolamento processo |
| **RF25 / RT24** | `tests/test_transport.py::test_ssh_host_key_changed_aborts`<br>`tests/test_transport.py::test_healthcheck_typed`<br>`tests/test_transport.py::test_concurrent_sessions_isolated` | `tests/test_integration.py::test_transport_certification` | Certificação real |
| **RF26 / RT26** | `tests/test_orchestration.py::test_swarm_dag_semaphore`<br>`tests/test_orchestration.py::test_relay_handoff_checkpoint`<br>`tests/test_orchestration.py::test_persist_window_pause_resume` | `tests/test_engine.py::test_three_modes_functional` | 3 modos distintos |
| **RF27 / RT27** | `tests/test_hitl.py::test_needs_context_pause`<br>`tests/test_hitl.py::test_needs_approval_high_risk`<br>`tests/test_hitl.py::test_timeout_failed_hitl_timeout` | `tests/test_server.py::test_hitl_sse_notification` | Timeout configurável |
| **RF28 / RT28** | `tests/test_conflict.py::test_3way_report`<br>`tests/test_conflict.py::test_auto_repair_merge_repair`<br>`tests/test_conflict.py::test_manual_discard_options` | `tests/test_conflict.py::test_conflict_resolution_flow` | Worktree preservada |
| **RF29 / RT29** | `tests/test_budget_packaging.py::test_budget_alert_80_freeze_100_and_restart`<br>`tests/test_budget_packaging.py::test_budget_extend_approve_resumes_and_deny_exhausts`<br>`tests/test_budget_packaging.py::test_unknown_metrics_never_become_zero_and_never_false_freeze` | `tests/test_budget_packaging.py::test_run_service_budget_gate_blocks_dispatch_and_allows_retry_after_extension` (HTTP em T23) | Alertas auditáveis |
| **RF30 / RT30** | `tests/test_budget_packaging.py::test_pr_packager_full_description_redaction_and_gated_publish`<br>`tests/test_budget_packaging.py::test_wall_seconds_stale_alerted_extend_and_pr_unknown_metrics` | `tests/test_server.py::test_pr_package_endpoint` (T23) | Descrição completa |

---

## 2. Estratégia de Testes Herméticos

### 2.1 Princípios
- **Zero dependências externas:** Nenhum teste requer contas reais, APIs pagas, GPU, localhost externo ou rede.
- **Fixtures temporárias:** Repositórios Git criados em `tempfile.TemporaryDirectory()` com `.git` inicializado.
- **Fake executors:** `bridge/worker_runner.py` suporta modo `dry_run` com executor fake que altera arquivo controlado.
- **Mock de OmniRoute:** `bridge/omniroute_client.py` tem implementação `MockOmniRouteClient` para testes.
- **SQLite em memória:** Para testes unitários puros, usa `:memory:`; para integração, arquivo temporário.

### 2.2 Categorias de Teste (conforme padrão da equipe)

| Categoria | Diretório | Descrição |
|-----------|-----------|-----------|
| **TST_UNIT** | `tests/` (unit) | Testes unitários puros: schemas, validações, algoritmos (Kahn, stitching, redactor) |
| **TST_INT** | `tests/` (integration) | Testes entre componentes: RunService + WorkerRunner + GitWorkspace + Checkpointer |
| **TST_E2E** | `tests/` (e2e) | Fluxos completos: submit → execute → review → integrate |
| **TST_NEG** | `tests/` (negative) | Critérios negativos objetivos (§7.A do PRD técnico) |
| **TST_SEC** | `tests/` (security) | Auth, CORS, redaction, path traversal, token derivation |
| **TST_A11Y** | `tests/` (a11y) | Checklist automatizado: teclado, foco, roles, contraste, redução movimento |

### 2.3 Fixtures Compartilhadas (`conftest.py`)

```python
# Fixtures essenciais
@pytest.fixture
def temp_git_repo():
    """Repositório Git temporário com commit inicial."""
    with TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
        yield repo

@pytest.fixture
def temp_db():
    """SQLite temporário com schema migrado."""
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite"
        # Aplicar migrações...
        yield db_path

@pytest.fixture
def mock_omniroute():
    """Cliente OmniRoute mockado."""
    return MockOmniRouteClient()
```

### 2.4 Testes de Processo e Concorrência

| Cenário | Validação |
|---------|-----------|
| **Subprocesso real** | `test_executor_real_subprocess`: spawn CLI fake, verifica diff + check |
| **Timeout tree kill** | `test_timeout_tree_kill`: processo filho não morre → SIGKILL verifica árvore |
| **Lock SQLite** | `test_concurrent_writes`: 2 conexões, `busy_timeout=5000`, retry |
| **Worktree concorrente** | `test_parallel_worktrees`: semáforo limita `max_parallel_worktrees` |
| **Crash reconciliação** | `test_crash_orphan_reconciliation`: kill -9 durante execução → órfãos detectados |
| **SSE reconexão** | `test_sse_replay_cursor`: Last-Event-ID recupera eventos, dedup por seq |

---

## 3. Critérios de Cobertura

| Métrica | Meta | Ferramenta |
|---------|------|------------|
| **Cobertura de linhas (core/bridge/engine)** | ≥ 80% | `pytest --cov=src/hydra_orch --cov-fail-under=80` |
| **Cobertura de branches (model.py)** | 100% | `pytest --cov=src/hydra_orch/model` |
| **Cobertura de schemas Pydantic** | 100% validações | `tests/test_model.py` (válidos + inválidos) |
| **Testes negativos (§7.A)** | 100% casos cobertos | `tests/test_negative.py` |
| **Testes de segurança** | 100% vetores | `tests/test_security.py` |
| **Testes de acessibilidade** | Checklist completo | `tests/test_a11y.py` + manual |

---

## 4. Execução de Testes

```bash
# Todos os testes (offline, herméticos)
pytest tests/ -v

# Apenas unitários
pytest tests/ -m "unit" -v

# Apenas integração
pytest tests/ -m "integration" -v

# E2E (pode ser mais lento)
pytest tests/ -m "e2e" -v

# Negativos (critérios §7.A)
pytest tests/ -m "negative" -v

# Segurança
pytest tests/ -m "security" -v

# Acessibilidade
pytest tests/ -m "a11y" -v

# Com cobertura
pytest tests/ --cov=src/hydra_orch --cov-report=term-missing --cov-fail-under=80

# Gate G-M4 / Expansão negativa, segurança e acessibilidade (T24)
pytest tests/ -m "negative or security or a11y" -v
pytest tests/test_ci_negative_gate.py -v

# CI (GitHub Actions — M1-M4 / V4)
# Ver .github/workflows/ci.yml
```

---

## 5. Relatórios de Teste

Cada categoria de teste gera `report.md` em `doc/h_test/reports/`:

| Relatório | Conteúdo |
|-----------|----------|
| `unit_report.md` | Status, escopo, comando, resultado, limite por módulo |
| `integration_report.md` | Cenários multi-componente, fixtures, evidências |
| `e2e_report.md` | Fluxos completos UC01–UC05, tempo, recursos |
| `negative_report.md` | Cada caso §7.A: PASS/FAIL + evidência |
| `security_report.md` | Auth, CORS, redaction, traversal, tokens |
| `a11y_report.md` | Checklist WCAG AA automatizado + manual |

Formato operacional configurável:
```
Status: PASS | PARTIAL | FAIL | BLOCKED | SKIPPED | NOT_RUN
Escopo: <módulo/funcionalidade>
Comando: pytest tests/...::test_xxx -v
Resultado: <resumo>
Limite: <critério de aceitação>
```

---

## 6. GAPs de Teste

- GAP-TEST-01: Validar `tree-sitter` code stitching para todas linguagens alvo (Python, TS, Rust, Go).
- GAP-TEST-02: Testar `taskkill /F /T` em Windows CI (GitHub Actions Windows runner).
- GAP-TEST-03: Simular `omniroute` offline/429/503 com `MockOmniRouteClient` comportamental.
- GAP-TEST-04: Testar `max_parallel_worktrees` com > 10 worktrees simultâneas (recursos SO).
- GAP-TEST-05: Validar redactor com corpus de segredos reais (GitHub, AWS, Slack, OAuth, SSH).
- GAP-TEST-06: Testar migração up/down de todas as tabelas de expansão (T10).
- GAP-TEST-07: Load test local opcional (locust/k6) para RNF07 (10 runs, 20 worktrees).

---

## 7. Glossary e Acrônimos

| Termo | Significado |
|-------|-------------|
| CI | Continuous Integration |
| E2E | End-to-End |
| Hermetic | Teste isolado, sem dependências externas, determinístico |
| Mock | Implementação simulada para testes |
| Fixture | Estado de teste preparado e limpo automaticamente |
| TST_UNIT | Teste unitário |
| TST_INT | Teste de integração |
| TST_E2E | Teste end-to-end |
| TST_NEG | Teste negativo (critérios objetivos) |
| TST_SEC | Teste de segurança |
| TST_A11Y | Teste de acessibilidade |
| WCAG AA | Web Content Accessibility Guidelines nível AA |
| Tree Kill | Término de processo e todos descendentes |
| WAL | Write-Ahead Logging |
| SSE | Server-Sent Events |