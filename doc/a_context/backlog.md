# backlog — Backlog Operacional das Tasks do hydra-orch

**Identificador Formal:** `backlog.md`
**Caminho Canônico:** `doc/a_context/backlog.md`
**Versão:** `v03_00_0000`
**Status:** `CONCLUÍDO — M1 A M4 (28/28 TASKS · 204/204 SP · GATE G-M4 FECHADO)`
**Autoridade:** Espelho operacional de [`prd_tecnico.md (§8)`](../b_spc/prd_tecnico.md) e [`prd_funcional.md`](../b_spc/prd_funcional.md), subordinado a [`AGENTS.md`](../../AGENTS.md) e [`taxonomia_file_system.md`](taxonomia_file_system.md). Ideias pós-M4 permanecem em [`ideia_futura.md`](ideia_futura.md).

---

## 1. Resumo Executivo e Épicos (EP01–EP08)

- **Escopo concluído:** **28 tasks (`T01`–`T28`)**, **204 Story Points** (Fibonacci: `P0` = núcleo M1; `P1` = Control Plane/Swarm/Handoff M2–M3; `P2` = Governança/Entrega M4), em **11 ondas**.
- **Regra de fonte da verdade:** Detalhes algorítmicos, DDL e contratos DBC-9 vivem em [`doc/b_spc/`](../b_spc/); este arquivo mantém a rastreabilidade enxuta de status, dependências, cobertura de gaps e evidência final.

| Épico | Título | Marco | Tasks | SP | Status |
|---|---|---|---|---|---|
| **EP01** | Núcleo Verificável Local | V0 / M1 | T01–T08 | 58 | concluido |
| **EP02** | Control Plane Seguro e HITL | V1 / M2 | T09, T26 | 13 | concluido |
| **EP03** | Workspaces e Catálogo de Perfis | V2 / M3 | T10–T13 | 23 | concluido |
| **EP04** | Sessões, Observabilidade, Rotas e Swarm (Wave 0+1) | V3 / M3 | T14–T16, T25 | 34 | concluido |
| **EP05** | Memória, Discovery e Extensões | V4 / M4 | T17–T20 | 34 | concluido |
| **EP06** | Acessibilidade e Transportes Certificados | V4 / M4 | T21, T22 | 13 | concluido |
| **EP07** | Entrega Governada (Conflitos, Budget, PR) | V4 / M4 | T27, T28 | 16 | concluido |
| **EP08** | Superfícies CLI, CI e Manuais Estendidos | V4 / M4 | T23, T24 | 13 | concluido |

---

## 2. Matriz Consolidada de Tasks (`T01` a `T28`)

| ID | Nome da Task | Épico / Versão | Prio | SP | Dependências | RF / RT | Arquivos / Entregáveis Principais | DoD Sintético | Status |
|---|---|---|---|---|---|---|---|---|---|
| **T01** | Config canônica | EP01 / V0 | P0 | 3 | — | RF02 / RT01 | `config.py`, `config.yaml`, `.gitignore` | Aliases/provedores explícitos; inválidos recusados; runtime `.orchestrator/`; gateway desligado sem rede | concluido |
| **T02** | Contratos e estados | EP01 / V0 | P0 | 5 | T01 | RF03, RF07 / RT02 | `model.py`, `tests/test_model.py` | Schemas Pydantic + máquinas de transição válidas/inválidas 100% cobertas | concluido |
| **T03** | Store e migração | EP01 / V0 | P0 | 8 | T02 | RF03, RF05 / RT03, RT11 | `core/checkpointer.py`, `migration/0001_initial_core.sql`, `tests/test_checkpointer.py` | SQLite WAL, restart seguro, idempotência, transação atômica e FKs ativas | concluido |
| **T04** | Runner e fake | EP01 / V0 | P0 | 8 | T03 | RF04, RF06 / RT04 | `bridge/worker_runner.py`, `tests/test_worker_runner.py` | Cwd real, erro `executor_unavailable`, timeout com tree kill, fake restrito a dry-run | concluido |
| **T05** | Workspace Git | EP01 / V0 | P0 | 8 | T04 | RF01, RF04 / RT05 | `core/git_workspace.py`, `tests/test_git_workspace.py` | SHA base fixo, worktree real isolada, checkout do usuário intacto, lock cleanup | concluido |
| **T06** | Checks e integração | EP01 / V0 | P0 | 13 | T05 | RF07, RF08 / RT06 | `core/git_workspace.py`, `core/run_service.py`, `tests/test_integration.py` | Patch real atribuível, escopo validado, conflito bloqueante, checks determinam aceite | concluido |
| **T07** | Entrada M1 (CLI/API) | EP01 / V0 | P0 | 8 | T06 | RF03–RF08 / RT10 | `cli.py`, `server.py`, `tests/test_server.py`, `tests/test_cli.py` | Submeter/consultar/cancelar/revisar usam `RunService`; auth local Bearer/loopback | concluido |
| **T08** | CI e manual M1 | EP01 / V0 | P0 | 5 | T07 | RF15 / RT12 | `.github/workflows/ci.yml`, `doc/j_manual/README.md`, `pyproject.toml` | Suíte offline hermética no CI (Linux/Windows/macOS); manual operacional M1 | concluido |
| **T09** | Auth e CORS estrito | EP02 / V1 | P1 | 5 | T07 | RF15, RF24 / RT25 | `server.py`, `core/auth.py`, `core/redaction.py`, `tests/test_auth.py` | Token local PBKDF2 obrigatório; CORS allowlist estrita; redaction de segredos | concluido |
| **T10** | Migrações control plane | EP03 / V2 | P1 | 8 | T03, T09 | RF16–RF30 / RT03, RT25 | `core/checkpointer.py`, `migration/0002_control_plane.sql`, `tests/test_migration.py` | Tabelas de expansão versionadas em `migration/`; rollback auditável; FKs ativas | concluido |
| **T11** | Registry áreas/repos | EP03 / V2 | P1 | 5 | T10 | RF16 / RT13 | `core/workspace_registry.py`, `tests/test_workspace_registry.py` | Hierarquia Area/Workspace/Project/Repo persistida; path traversal bloqueado | concluido |
| **T12** | Catálogo agentes/capabilities | EP03 / V2 | P1 | 5 | T02, T04, T10 | RF17, RF14 / RT14 | `core/agent_registry.py`, `config.yaml`, `tests/test_agent_registry.py` | Capabilities declaradas; driver não certificado bloqueado; CLI ausente gera erro claro | concluido |
| **T13** | Perfis e snapshots | EP03 / V2 | P1 | 5 | T11, T12 | RF17, RF23 / RT15 | `core/profile_service.py`, `tests/test_profile.py` | Validação pré-execução; ProfileSnapshot imutável com hash SHA-256 por run | concluido |
| **T14** | Sessões, threads, SSE replay | EP04 / V3 | P1 | 8 | T03, T07, T10 | RF18, RF05 / RT16 | `core/session_service.py`, `server.py`, `tests/test_sse_replay.py` | Árvore hierárquica sessões/threads; SSE com `Last-Event-ID`, replay e dedup | concluido |
| **T15** | Métricas observabilidade | EP04 / V3 | P1 | 5 | T03, T10, T14 | RF19 / RT17 | `core/metrics.py`, `tests/test_metrics.py` | Fila, duração, tokens, custo com status `observed`/`stale`/`unknown`; zero não inventado | concluido |
| **T16** | Seleção adaptativa rotas | EP04 / V3 | P1 | 8 | T12, T15 | RF20, RF11 / RT18 | `core/route_selector.py`, `bridge/omniroute_client.py`, `tests/test_route_selector.py` | RouteDecision auditável; modo direto sem gateway testado; quota `unknown` | concluido |
| **T17** | Consentimento e memória | EP05 / V4 | P2 | 8 | T09, T10 | RF21 / RT19 | `core/consent.py`, `core/memory_store.py`, `tests/test_memory.py` | Escrita exige `ConsentRecord`; revogação funcional; isolamento de checkpoints | concluido |
| **T18** | Discovery local controlado | EP05 / V4 | P2 | 5 | T09, T11 | RF22 / RT20 | `core/discovery.py`, `tests/test_discovery.py` | Varredura opt-in restrita a allowlist; SHA-256 + `untrusted`; sem auto-ativação | concluido |
| **T19** | Skills, MCPs, secret refs | EP05 / V4 | P2 | 8 | T12, T17, T18 | RF17, RF22 / RT21 | `core/skill_registry.py`, `bridge/mcp_client.py`, `tests/test_secrets.py` | Segredos como referências externas; resolução no spawn com env filtrado | concluido |
| **T20** | Isolamento extensões/plugins | EP05 / V4 | P2 | 13 | T18, T19 | RF24 / RT22 | `core/extension_host.py`, `bridge/extension_runner.py`, `tests/test_extension.py` | Manifesto versionado; subprocesso sem acesso ao DB core; quarentena e rollback | concluido |
| **T21** | Preferências e acessibilidade | EP06 / V4 | P2 | 5 | T13 | RF23 / RT23 | `core/preferences.py`, `tests/test_preferences.py`, `tests/test_a11y.py` | Preferências escopadas reversíveis (`explicit > inferred_opt_in`); checklist WCAG AA | concluido |
| **T22** | Transportes certificados | EP06 / V4 | P2 | 8 | T04, T09 | RF25, RF14 / RT24 | `bridge/transport_registry.py`, `bridge/ssh_tunnel.py`, `tests/test_transport.py` | Alvo/identidade/healthcheck; host key SSH alterada aborta; isolamento de saídas | concluido |
| **T23** | CLI/API control plane estendida | EP08 / V4 | P2 | 8 | T11, T12, T13, T17, T18, T20 | RF16–RF30 / RT13–RT25 | `cli.py`, `server.py`, `doc/f_api/openapi.yaml`, `tests/test_cli.py`, `tests/test_server.py` | 77 paths OpenAPI `3.0.3` + 21 grupos CLI com paridade de serviço e `--json`/`--output` | concluido |
| **T24** | CI estendido e runbooks | EP08 / V4 | P2 | 5 | T08, T23 | RF15, RF23, RF25 / RT12 | `.github/workflows/ci.yml`, `tests/test_ci_negative_gate.py`, `doc/j_manual/README.md` | CI offline estendido + gates negativos/security/a11y + runbooks M2–M4 | concluido |
| **T25** | Orquestração Swarm/Relay/Persist | EP04 / V3 | P1 | 13 | T06, T13 | RF26 / RT26 | `engine/swarm.py`, `engine/relay.py`, `engine/persist.py`, `tests/test_orchestration.py` | Swarm 2 Ondas (Wave 0 + Wave 1 paralela), Handoff por Estado Git e Retry atômico | concluido |
| **T26** | HITL (Humano-no-Loop) | EP02 / V1 | P1 | 8 | T07, T14 | RF27 / RT27 | `core/hitl.py`, `core/run_service.py`, `tests/test_hitl.py` | Pausa `needs_context`/`needs_approval`; expiração por timeout; retomada auditada | concluido |
| **T27** | Resolução conflitos merge | EP07 / V4 | P2 | 8 | T06, T08 | RF28 / RT28 | `core/conflict_resolver.py`, `core/git_workspace.py`, `tests/test_conflict.py` | Relatório 3-way; `merge_repair` + *Contract Amendment*; opções `manual`/`discard` | concluido |
| **T28** | Budgeting e PR Packaging | EP07 / V4 | P2 | 8 | T07, T15 | RF29, RF30 / RT29, RT30 | `core/budget.py`, `core/packaging.py`, `tests/test_budget_packaging.py` | Tetos USD/tokens/tempo (80% alerta / 100% congela); PR package redigido com publish gated | concluido |

---

## 3. Cobertura dos Gaps Arquiteturais (`A01`–`A18`)

| Gaps | Tema / Lacuna Original | Tasks de Resolução | Cobertura |
|---|---|---|---|
| **A01, A12, A17** | Aliases no relay, conflito `.hydra/` vs `.orchestrator/`, `LICENSE` / política OmniRoute | `T01`, `G0` | Total |
| **A02, A04, A05, A06** | Simulação forjada em `worker_runner`, texto no swarm, merge inseguro, fallback sem Git | `T04`, `T05`, `T06`, `T07` | Total |
| **A03, A13, A14** | Quota fictícia offline, SSH com config/host key ausente, CORS aberto e ausência de auth | `T01`, `T09`, `T16`, `T22` | Total |
| **A07, A08, A09, A10, A11, A16** | Merge ignorando resultados, relay destrutivo, healer fake, sem tree kill, 4 tasks fixas | `T02`, `T03`, `T04`, `T06`, `T25` | Total |
| **A15, A18** | Streaming SSE sem cursor/dedup e suíte superficial dependente de `localhost` | `T07`, `T08`, `T14`, `T24` | Total |

---

## 4. Evidências Consolidadas por Marco (`G-M1` a `G-M4`)

Detalhes contratuais DBC-9 e limites específicos estão registrados nas respectivas specs em [`doc/b_spc/`](../b_spc/README.md) e na matriz [`doc/h_test/README.md`](../h_test/README.md).

| Marco / Gate | Tasks | Principais Specs | Evidência Consolidada |
|---|---|---|---|
| **M1 (`G-M1`)** | `T01`–`T08` | `S01`–`S13` ([`entrega_operacao.md`](../b_spc/entrega_operacao.md)) | Config estrita `.orchestrator/`, `model.py`, `ExecutionStore` WAL (`0001`), `WorkerRunner` (cwd + tree kill), `GitWorkspaceService`, `RunService`, CLI/API M1 e CI hermético |
| **Segurança & M2–M3 (`G-SEG`, `G-M2`, `G-M3`)** | `T09`–`T16`, `T25`, `T26` | [`seguranca_proveniencia.md`](../b_spc/seguranca_proveniencia.md), [`workspaces_perfis.md`](../b_spc/workspaces_perfis.md), [`sessoes_observabilidade.md`](../b_spc/sessoes_observabilidade.md), [`intervencao_humana.md`](../b_spc/intervencao_humana.md) | Bearer PBKDF2 + CORS + `Redactor`, migração `0002` + rollback, Area/Repo/Agent/Profile/Session, SSE `Last-Event-ID`, `MetricsService`, `RouteSelector`, HITL e Swarm Wave 0+1 / Relay / Persist |
| **V4 Governança (`G-M4` parte 1)** | `T17`–`T22`, `T27`, `T28` | `S16`, [`acessibilidade_preferences.md`](../b_spc/acessibilidade_preferences.md), [`transportes_certificados.md`](../b_spc/transportes_certificados.md), [`integracao_git.md`](../b_spc/integracao_git.md), [`budget_packaging.md`](../b_spc/budget_packaging.md) | `ConsentRecord` obrigatório, Discovery allowlist + `untrusted`, `SecretRef` + MCP `stdio`, `ExtensionRunner` sem acesso ao SQLite core, preferências/WCAG AA, SSH `StrictHostKeyChecking=yes`, conflitos 3-way + *Contract Amendment*, Budget 80%/100% e `PRPackager` |
| **V4 Fechamento (`G-M4` final)** | `T23`, `T24` | [`cli_ci_manual.md`](../b_spc/cli_ci_manual.md) (`S20`), [`openapi.yaml`](../f_api/openapi.yaml) | 77 paths OpenAPI `3.0.3`, 21 grupos CLI + M1, `test_ci_negative_gate.py`, workflow CI M1–M4, correções CRLF/Windows e runbooks `RB-01`–`RB-07` em [`doc/j_manual/README.md`](../j_manual/README.md) |

- **Validação final do backlog após integração completa (Windows / Python 3.12.10):**
  - `python -m pytest tests -q` → **`568 passed, 1 warning in 854.32s`** (0 falhas, 0 erros; warning preexistente `httpx`/`starlette.testclient`).
  - `python -m compileall -q src tests`, validação YAML/rotas `doc/f_api/openapi.yaml` (`77` paths), smoke test CLI (`31` comandos/grupos), verificação de links locais e `git diff --check` aprovados sem erros.
  - **Fora da suíte offline (próximos passos pós-M4):** execução real no GitHub Actions multi-OS, certificação opt-in de CLIs externas (`driver-certification`), construção do frontend Web UI sobre [`doc/b_spc/a_ui/README.md`](../b_spc/a_ui/README.md) e eventuais promoções futuras em [`ideia_futura.md`](ideia_futura.md).
