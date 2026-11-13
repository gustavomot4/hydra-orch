# backlog — Backlog Operacional das Tasks do hydra-orch

**Identificador Formal:** `backlog.md`
**Caminho Canônico:** `doc/a_context/backlog.md`
**Versão:** `v04_00_0000`
**Status:** `M1–M4 CONCLUÍDOS (28/28 TASKS · 204 SP) · M5 PLANEJADO (T29–T36 · 58 SP)`
**Autoridade:** Espelho operacional de [`prd_tecnico.md (§8)`](../b_spc/prd_tecnico.md), [`a_ui/README.md`](../b_spc/a_ui/README.md) e [`architecture.md`](../g_code/architecture.md), subordinado a [`AGENTS.md`](../../AGENTS.md) e [`taxonomia_file_system.md`](taxonomia_file_system.md). Ideias multimodais/voz/GGUF permanecem em [`ideia_futura.md`](ideia_futura.md).

---

## 1. Resumo Executivo e Épicos (`EP01`–`EP10`)

- **Base concluída (`M1`–`M4`):** `28/28` tasks (`T01`–`T28`, `204 SP`), validada offline em `pytest` (**568 passed**), com OpenAPI `3.0.3` (`77` paths) e CLI (`hydra` + `21` subgrupos).
- **Próximo foco (`M5 / V5`):** **OmniRoute como roteador de IA** + **CLI Interativa** + **GUI Control Plane (`frontend/`)** para o operador orquestrar seus agentes (`T29`–`T36`, `58 SP`, Ondas `12`–`15`).

| Épico | Título | Marco | Tasks | SP | Status |
|---|---|---|---|---|---|
| **EP01–EP08** | Núcleo Local, Control Plane, Swarm/Relay, Governança e CI (`M1–M4`) | V0–V4 / M1–M4 | T01–T28 | 204 | **28/28 concluido** |
| **EP09** | Roteamento OmniRoute, CLI Interativa e Contratos PTY/Anexos | V5 / M5 | T29–T31 | 24 | **em_planejamento** (`T29`, `T31` pronto) |
| **EP10** | Interface Gráfica Control Plane (`frontend/`, Ref. Orca/Figma) | V5 / M5 | T32–T36 | 34 | **pendente** (dep. `T29`–`T32`) |

---

## 2. Base Concluída (`M1`–`M4` / Gates `G-M1` a `G-M4` Fechados)

| Marco | Tasks | Specs | Entregáveis Principais (todos `concluido`) |
|---|---|---|---|
| **M1 (`G-M1`)** | `T01`–`T08` (`58 SP`) | [`entrega_operacao.md`](../b_spc/entrega_operacao.md) | `config.py`/`config.yaml` (`.orchestrator/`), `model.py`, `ExecutionStore` WAL (`0001`), `WorkerRunner` (`cwd` + tree kill), `GitWorkspaceService`, `RunService`, CLI/API M1 e CI hermético |
| **M2–M3 (`G-SEG`, `G-M2`, `G-M3`)** | `T09`–`T16`, `T25`, `T26` (`70 SP`) | [`seguranca_proveniencia.md`](../b_spc/seguranca_proveniencia.md), [`workspaces_perfis.md`](../b_spc/workspaces_perfis.md), [`sessoes_observabilidade.md`](../b_spc/sessoes_observabilidade.md), [`intervencao_humana.md`](../b_spc/intervencao_humana.md) | Auth PBKDF2 + CORS + `Redactor`, migração `0002` + rollback, hierarquia Area/Workspace/Project/Repo, agentes/capabilities, perfis SHA-256, sessões/SSE `Last-Event-ID`, métricas, `RouteSelector`, HITL e Swarm Wave 0+1 / Relay / Persist |
| **M4 (`G-M4`)** | `T17`–`T24`, `T27`, `T28` (`76 SP`) | `S16`–`S20` ([`cli_ci_manual.md`](../b_spc/cli_ci_manual.md)), [`openapi.yaml`](../f_api/openapi.yaml) | `ConsentRecord` + memória, discovery opt-in + `untrusted`, `SecretRef`/MCP `stdio`, `ExtensionRunner` isolado, preferências/WCAG AA, SSH estrito, conflitos 3-way + *Contract Amendment*, budget 80%/100%, `PRPackager`, 77 paths REST/SSE, 21 subgrupos CLI, CI negativo/a11y e runbooks `RB-01`–`RB-07` |

- **Gaps arquiteturais A01–A18:** 100% cobertos em `T01`–`T28` (aliases, runner/swarm/merge reais, quota offline, worktrees, checkpoints, CORS/auth/SSH, cursor SSE e CI hermético).
- **Evidência final M1–M4:** `python -m pytest tests -q` → **`568 passed, 1 warning`** (0 falhas/erros), OpenAPI `3.0.3` validada e smoke CLI (`31` entradas) aprovado.

---

## 3. Próximas Tasks Ativas — Marco `M5` (`V5`: OmniRoute, CLI Interativa & GUI)

Sequenciamento em **4 ondas** (`O12`–`O15`) com propriedade de arquivos disjunta e pré-requisito de spec UI em [`doc/b_spc/a_ui/`](../b_spc/a_ui/README.md) + [`doc/g_code/stack.md`](../g_code/stack.md):

| ID | Nome da Task | Épico / Onda | Prio | SP | Dependências | Base / Specs | Arquivos / Entregáveis Principais | Definition of Done (DoD Sintético) | Status |
|---|---|---|---|---|---|---|---|---|---|
| **T29** | Integração Operacional OmniRoute | EP09 / O12 | P1 | 8 | T16, T23 | RF11, RF20 / RT18, UI09 | `bridge/omniroute_client.py`, `core/route_selector.py`, `cli.py`, `server.py`, `tests/test_route_selector.py` | Descoberta de modelos/rotas via OmniRoute, quota 5h (`observed`/`stale`/`unknown`), troca de conta para próximas runs, modo `optional`/`required` sem quebrar modo direto e stub HTTP hermético | **pronto** |
| **T31** | Contratos Backend PTY, Anexos e Agenda | EP09 / O12 | P1 | 8 | T14, T23 | RF05, RF18 / UI03, UI04, UI10 | `bridge/pty_runner.py`, `core/attachments.py`, `core/scheduler.py`, `server.py`, `doc/f_api/openapi.yaml`, `tests/test_pty_attachments.py` | Protocolo PTY autenticado (open/input/resize/exit/reconnect + tree kill Win ConPTY / Unix PTY), `AttachmentRef` (MIME/tamanho/SHA-256/escopo), agenda durável idempotente e contratos OpenAPI | **pronto** |
| **T30** | CLI Interativa de Orquestração (TUI) | EP09 / O13 | P1 | 8 | T23, T25, T26, T29 | RF26–RF30 / RT28 | `src/hydra_orch/tui.py`, `cli.py`, `tests/test_cli_interactive.py` | Modo interativo (`hydra watch` / `hydra ui`) em terminal consumindo `RunService` + SSE: acompanhar Swarm (Wave 0+1)/Relay/Persist ao vivo, escolher rota OmniRoute, revisar diffs, responder HITL, tratar conflitos e integrar | pendente |
| **T32** | Fundação GUI, Auth, Shell & Workspaces | EP10 / O13 | P1 | 8 | T21, T23, T29 | RF16, RF23 / UI01 | `frontend/` (`package.json`, `AppShell`, `WorkspaceTree`, `PaneLayout`, `TabBar`, cliente OpenAPI/Bearer) | App React 18 + TS + Vite + Tailwind + Radix + TanStack Query + Zustand; login Bearer seguro (sem vazar segredo), navegação `host→projeto→worktree→sessão`, abas/splits persistidos e teclado/contraste WCAG AA | pendente |
| **T33** | GUI: Chat Timeline SSE, OmniRoute & HITL | EP10 / O14 | P1 | 8 | T26, T29, T32 | RF18, RF20, RF27 / UI02, UI09 | `frontend/src/features/chat/`, `composer/`, `quota/` | `ChatTimeline` ligado ao SSE com `Last-Event-ID` + deduplicação (sem auto-reenvio), cards de workers Swarm/Relay/Persist, `PromptComposer` (rascunho por sessão), seletor de modelo/conta OmniRoute, `UsageBar` e aprovação HITL | pendente |
| **T34** | GUI: Terminal PTY, Diffs, Conflitos & Preview | EP10 / O14 | P1 | 8 | T27, T31, T32 | RF08, RF28, RF30 / UI03–UI06 | `frontend/src/features/terminal/`, `artifacts/`, `conflicts/` | `TerminalPane` ligado ao PTY autenticado (ANSI/Unicode, resize, escolher manter/encerrar ao fechar aba), `ArtifactViewer` seguro (diff Git, Markdown sem script, imagem/PDF), upload de `AttachmentRef`, `review`, conflitos 3-way e `pr-package` | pendente |
| **T35** | GUI: Painéis de Governança e Segurança | EP10 / O15 | P2 | 5 | T32, T33 | RF21–RF25, RF29 | `frontend/src/features/governance/` | Fluxos visuais para consentimento/memória (`409` → solicitação), discovery (`approve`/`reject`), extensões (quarentena/rollback), secret refs (metadados apenas), transportes SSH/host-key e alertas de Budget 80%/100% + extensão | pendente |
| **T36** | E2E GUI + TUI, WCAG AA Automatizada & CI M5 | EP10 / O15 | P2 | 5 | T30, T34, T35 | RF15, RF23 / UI01–UI11 | `frontend/tests/`, `tests/`, `.github/workflows/ci.yml`, `doc/j_manual/README.md` | Suíte Vitest/Playwright hermética (backend offline + fixtures sanitizadas), `axe-core` WCAG AA, lint/typecheck/build frontend no CI e manual operacional M5 (**fecha Gate `G-M5`**) | pendente |
