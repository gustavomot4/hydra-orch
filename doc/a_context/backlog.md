# backlog — Backlog Operacional das Tasks do hydra-orch

**Identificador Formal:** `backlog.md`
**Caminho Canônico:** `doc/a_context/backlog.md`
**Versão:** `v04_01_0000`
**Status:** `M1–M4 CONCLUÍDOS (28/28 TASKS · 204 SP) · M5 EM EXECUÇÃO (Onda 12 CONCLUÍDA · T29, T31, T37)`
**Autoridade:** Espelho operacional de [`prd_tecnico.md (§8)`](../b_spc/prd_tecnico.md), [`a_ui/README.md`](../b_spc/a_ui/README.md), [`b_interface.md`](../b_spc/a_ui/b_interface.md), [`c_process.md`](../b_spc/a_ui/c_process.md), [`d_figma.md`](../b_spc/a_ui/d_figma.md) e [`architecture.md`](../g_code/architecture.md), subordinado a [`AGENTS.md`](../../AGENTS.md) e [`taxonomia_file_system.md`](taxonomia_file_system.md). Ideias multimodais/voz/GGUF permanecem em [`ideia_futura.md`](ideia_futura.md).

---

## 1. Resumo Executivo e Épicos (`EP01`–`EP10`)

- **Base concluída (`M1`–`M4`):** `28/28` tasks (`T01`–`T28`, `204 SP`), validada offline em `pytest` (**568 passed**), OpenAPI `3.0.3` (`77` paths) e CLI (`hydra` + `21` subgrupos).
- **Próximo foco (`M5 / V5`):** **OmniRoute** como roteador de IA/quotas + **CLI Interativa (TUI)** + **GUI Control Plane (`frontend/`)** fiel às **18 telas Figma** e requisitos **`UI01`–`UI11`** em [`doc/b_spc/a_ui/`](../b_spc/a_ui/README.md) (`T29`–`T38`, `74 SP`, Ondas `12`–`15`).

| Épico | Título | Marco | Tasks | SP | Status |
|---|---|---|---|---|---|
| **EP01–EP08** | Núcleo Local, Control Plane, Swarm/Relay, Governança e CI (`M1–M4`) | V0–V4 / M1–M4 | T01–T28 | 204 | **28/28 concluido** |
| **EP09** | OmniRoute Operacional, Contratos PTY/Anexos/Busca/Agenda & TUI | V5 / M5 | T29–T31, T37 | 29 | **em execução** (`T29`, `T31`, `T37` concluido; `T30` pendente) |
| **EP10** | GUI Control Plane (`frontend/`, 18 Telas Figma, `UI01`–`UI11` & CI) | V5 / M5 | T32–T36, T38 | 45 | **pendente** (Onda 12 concluída) |

---

## 2. Base Concluída (`M1`–`M4` / Gates `G-M1` a `G-M4` Fechados)

| Marco | Tasks | Specs | Entregáveis Principais (todos `concluido`) |
|---|---|---|---|
| **M1 (`G-M1`)** | `T01`–`T08` (`58 SP`) | [`entrega_operacao.md`](../b_spc/entrega_operacao.md) | `config.py`/`config.yaml` (`.orchestrator/`), `model.py`, `ExecutionStore` WAL (`0001`), `WorkerRunner` (`cwd` + tree kill), `GitWorkspaceService`, `RunService`, CLI/API M1 e CI hermético |
| **M2–M3 (`G-SEG`, `G-M2`, `G-M3`)** | `T09`–`T16`, `T25`, `T26` (`70 SP`) | [`seguranca_proveniencia.md`](../b_spc/seguranca_proveniencia.md), [`workspaces_perfis.md`](../b_spc/workspaces_perfis.md), [`sessoes_observabilidade.md`](../b_spc/sessoes_observabilidade.md), [`intervencao_humana.md`](../b_spc/intervencao_humana.md) | Auth PBKDF2 + CORS + `Redactor`, migração `0002` + rollback, hierarquia Area/Workspace/Project/Repo, agentes/capabilities, perfis SHA-256, sessões/SSE `Last-Event-ID`, métricas, `RouteSelector`, HITL e Swarm Wave 0+1 / Relay / Persist |
| **M4 (`G-M4`)** | `T17`–`T24`, `T27`, `T28` (`76 SP`) | `S16`–`S20` ([`cli_ci_manual.md`](../b_spc/cli_ci_manual.md)), [`openapi.yaml`](../f_api/openapi.yaml) | `ConsentRecord` + memória, discovery opt-in + `untrusted`, `SecretRef`/MCP `stdio`, `ExtensionRunner` isolado, preferências/WCAG AA, SSH estrito, conflitos 3-way + *Contract Amendment*, budget 80%/100%, `PRPackager`, 77 paths REST/SSE, 21 subgrupos CLI, CI negativo/a11y e runbooks `RB-01`–`RB-07` |

- **Gaps A01–A18:** 100% cobertos (`T01`–`T28`). **Evidência:** `python -m pytest tests -q` → **568 passed, 1 warning**.

---

## 3. Próximas Tasks Ativas — Marco `M5` (`V5`: OmniRoute, CLI Interativa & GUI `a_ui`)

Plano derivado de [`b_interface.md`](../b_spc/a_ui/b_interface.md) (`UI01`–`UI11`), [`c_process.md`](../b_spc/a_ui/c_process.md) (Etapas 1–11), [`d_figma.md`](../b_spc/a_ui/d_figma.md) (18 telas `Protótipo navegável`) e [`stack.md`](../g_code/stack.md), organizado em **4 ondas (`O12`–`O15`)**:

| ID | Nome da Task | Épico / Onda | Prio | SP | Dependências | Specs / Figma (`a_ui`) | Arquivos / Entregáveis Principais | Definition of Done (DoD Sintético) | Status |
|---|---|---|---|---|---|---|---|---|---|
| **T29** | OmniRoute Operacional: Rotas, Quotas & Contas | EP09 / O12 | P1 | 8 | T16, T23 | RF11, RF20 / UI09 / Figma `7:279` | `bridge/omniroute_client.py`, `core/route_selector.py`, `cli.py`, `server.py`, `tests/test_route_selector.py` | Descoberta de modelos/rotas via OmniRoute, quota 5h (`observed`/`stale`/`unknown` — ausente nunca vira zero), troca de conta para *próxima* execução sem mutar run ativa nem vazar segredo, preservação do modo direto offline e testes HTTP stub | **concluido** |
| **T31** | Contratos Backend: Reconciliação DBC-9, PTY, Anexos, Preview, Search & Host Capabilities | EP09 / O12 | P1 | 8 | T14, T23 | RF05, RF18 / UI03–UI07, UI11 / Etapa 1–2 | `doc/b_spc/ui_contratos.md`, `bridge/pty_runner.py`, `core/attachments.py`, `core/search_index.py`, `server.py`, `doc/f_api/openapi.yaml`, `tests/test_pty_attachments.py` | Spec DBC-9 + matriz UI↔RF reconciliada; PTY bidirecional autenticado (`open`/`input`/`resize`/`exit`/`reconnect` + tree kill ConPTY Win / PTY Unix); `AttachmentRef` (MIME/tamanho/SHA-256/escopo/remoto explícito); preview seguro (`/artifacts/{id}/content`, Markdown sem script, limite de bytes); `GET /search` (`QuickOpen`); capabilities por host (`unavailable` para bridges não certificadas) | **concluido** |
| **T37** | Agendador Durável Backend (`AutomationSchedule`) & Histórico | EP09 / O12 | P1 | 5 | T14, T23 | UI10 / Figma `7:439`, `7:832` / Etapa 8 | `migration/0003_ui_automation.sql`, `core/scheduler.py`, `server.py`, `cli.py`, `doc/f_api/openapi.yaml`, `tests/test_scheduler.py` | CRUD + pause/resume/trigger em `/v1/control-plane/automations`; cron/intervalo + fuso IANA + DST + política de sobreposição/perda; idempotência após reinício sem disparo duplicado; histórico ligado ao `run_id` e erro real | **concluido** |
| **T30** | CLI Interativa de Orquestração (TUI) | EP09 / O13 | P1 | 8 | T23, T25, T26, T29 | RF26–RF30 / RT28 | `src/hydra_orch/tui.py`, `src/hydra_orch/cli.py`, `tests/test_cli_interactive.py` | Cockpit interativo (`hydra watch` / `hydra ui`) sobre `RunService` + SSE cursor replay: acompanhar Swarm (Wave 0+1)/Relay/Persist ao vivo, escolher rota/conta OmniRoute, `review`, responder HITL, tratar conflitos, `integrate` e `pr-package` | pendente |
| **T32** | Fundação Visual GUI, Tokens Figma/shadcn, Auth, Shell & Workspaces | EP10 / O13 | P1 | 8 | T21, T23, T29, T31 | UI01 / Figma `18:8`, `18:454` / Etapa 1, 3 | `doc/g_code/stack.md`, `frontend/` (`package.json`, tema/tokens, `AppRail`, `Sidebar`, `WorkspaceTree`, `PaneLayout`, `TabBar`, `UsageBar`, `NovoChat`, `ConfigPerfil`) | Reconciliar `stack.md` (`@xterm/xterm`, Inter, JetBrains Mono, Lucide, pastas `frontend/src/`); paleta Figma (`#141414`/`#181818`/`#1C1C1C`/`#202020`/`#303030`/`#E8E8E8`/`#969696`, PT-BR, sem bolinhas macOS); auth Bearer segura; `AppRail` + `Sidebar` (`280px` / drawer mobile) + `WorkspaceTree` (`host→projeto→worktree→conversa→agentes agrupados`); abas/splits persistidos; `UsageBar` compacto (ícone+barra+%, sem nome/reset no rodapé); foco/teclado AA | pendente |
| **T33** | GUI: Chat Timeline SSE, Coordenador + Workers, Contas/Consumo & HITL | EP10 / O14 | P1 | 8 | T26, T29, T32 | UI02, UI09 / Figma `7:6`, `7:134`, `7:279` / Etapa 4, 7 | `frontend/src/feature/{chat,composer,quota}/`, `frontend/tests/chat.test.tsx` | `ChatTimeline` SSE (`eventsource-parser` + `Last-Event-ID` + snapshot em `410` + deduplicação, sem auto-reenvio; 9 estados explícitos; resposta de agente nunca sobrescreve check); coordenador ao centro + cards de workers à direita com eventos recolhíveis (`Worked for Xs`); `PromptComposer` com rascunho por sessão, `@` e `/`; tela `Contas e consumo` (`observed`/`stale`/`unknown`, troca de conta para próxima run); HITL inline | pendente |
| **T34** | GUI: Terminal PTY (Single/Split), Previews Seguros, Diffs & Conflitos | EP10 / O14 | P1 | 8 | T27, T31, T32 | UI03, UI06 / Figma `7:69`, `22:8`, `22:239` / Etapa 5, 6 | `frontend/src/feature/{terminal,artifact,conflict}/`, `frontend/tests/terminal_artifact.test.tsx` | `TerminalPane` (`@xterm/xterm` + fit) em painel único ou dividido (Codex/Claude): host/cwd/sessão visíveis, ANSI/Unicode, colagem multilinha revisável, resize, interrupção, código de saída, reconexão e diálogo ao fechar aba (manter ou encerrar processo); `ArtifactViewer` lado a lado (`diff2html`/Monaco, Markdown sem script, imagem/PDF); `review`, conflitos 3-way, `integrate` e `pr-package` | pendente |
| **T38** | GUI: Busca Global (`QuickOpen`), Anexos (`AttachmentRef`) & Ditado Revisável | EP10 / O14 | P1 | 5 | T31, T32, T33 | UI04, UI05, UI08 / Figma `7:359`, `7:679`, `7:1039` / Etapa 6, 9 | `frontend/src/feature/{quickopen,attachment,dictation}/`, `frontend/tests/quickopen_attachments.test.tsx` | `QuickOpen` (`Ctrl+K`) por teclado em hosts/projetos/workspaces/abas sem recriar sessão; drag/drop e seletor acessível de `AttachmentRef` (nome, MIME, tamanho, progresso, erro, destino explícito remoto); controle de ditado STT (`inativo`/`ativo`/permissão negada recuperável/cancelar), transcrição **editável sem auto-envio** (distinto de voz duplex `RF36`) | pendente |
| **T35** | GUI: Recursos/Governança, Automações & Painéis Capability-Gated | EP10 / O15 | P2 | 8 | T32, T33, T37 | RF21–RF25, RF29 / UI07, UI10, UI11 / Figma `7:205`, `7:439`/`832`, `7:519`/`901`, `7:599`/`970` / Etapa 8, 10 | `frontend/src/feature/{governance,automation,device,computer_use}/`, `frontend/tests/governance_automation.test.tsx` | Tela `Recursos` (skills, MCPs, consentimento/memória `409`, discovery `approve`/`reject`, extensões quarentena/rollback, SecretRef só metadados, SSH host-key, budget 80%/100%); tela `Automações` (agenda + TZ + toggle + histórico ligado ao run); painéis `Emulador móvel` (`UI07`) e `Controle do computador` (`UI11`) estritamente **capability-gated** (exibem `Indisponível / não certificado` sem simular execução falsa) | pendente |
| **T36** | Suíte E2E (GUI + TUI), WCAG AA (`axe-core`), Mobile, Certificação OS & CI M5 | EP10 / O15 | P2 | 8 | T30, T34, T35, T38 | RF15, RF23 / UI01–UI11 / Etapa 11 | `frontend/tests/e2e/`, `tests/`, `.github/workflows/ci.yml`, `doc/j_manual/README.md` | Cenário integrado de 10 passos (`c_process.md`) com executor falso/fixtures (GUI + TUI); `axe-core` WCAG AA (desktop `1920×1100`, estreito, zoom 200%, mobile sem sobreposição do teclado); matriz de prova PTY por SO (Windows ConPTY + Unix PTY) sem processos órfãos; CI M5 (`lint`, `typecheck`, `build`, `Vitest`, `Playwright`) e manual operacional (**fecha Gate `G-M5`**) | pendente |

---

## 4. Regras de Execução Swarm e Reconciliação (`a_ui` ↔ Contratos)

1. **Matriz de Propriedade de Arquivos por Onda (Anti-Colisão):**
   - **Onda 12 (`T29`, `T31`, `T37`):** Workers em worktrees isoladas produzem seus módulos exclusivos (`omniroute_client.py`/`route_selector.py` vs `pty_runner.py`/`attachments.py`/`search_index.py`/`ui_contratos.md` vs `migration/0003` + `scheduler.py`); **apenas o líder** integra as rotas compartilhadas em `src/hydra_orch/server.py`, `src/hydra_orch/cli.py` e `doc/f_api/openapi.yaml`.
   - **Onda 13 (`T30` || `T32`):** Disjunta entre Python (`tui.py` + `cli.py`) e Frontend (`frontend/` + `stack.md`). `T32` executa a **Wave 0 do Frontend** (pinagem de dependências em `package.json`, tema e tipos base) antes de abrir a Wave 1 paralela da Onda 14.
   - **Onda 14 (`T33` || `T34` || `T38`):** Cada task atua apenas no próprio slice sob `frontend/src/feature/*` e `frontend/tests/*`; mudanças em tipos/rotas compartilhadas passam pelo líder.
   - **Onda 15 (`T35` → `T36`):** Consolida painéis finais e fecha E2E, `axe-core`, PTY por SO e CI no `Gate G-M5`.
2. **Invariantes Visuais e de Escopo (`d_figma.md` + `ideia_futura.md`):**
   - **Identidade Figma consolidada:** PT-BR, sem bolinhas de janela macOS, barra lateral estreita (`#181818`) + sidebar (`#1C1C1C`) + área principal (`#141414`) + cartões (`#202020`), `Inter` + `JetBrains Mono`, SVGs Lucide + logos dos provedores, rodapé compacto apenas com ícone + barra + `%` (nunca `0%` quando desconhecido).
   - **Taxonomia no Frontend (`taxonomia_file_system.md`):** Usar pastas internas no singular (`frontend/src/component/`, `feature/`, `hook/`, `page/`, `store/`, `type/`) e registrar a reconciliação com `doc/g_code/stack.md` (§4) em `T31`/`T32`.
   - **Parking Lot (`F06`/`F07`):** Telas do Figma de Emulador Móvel e Controle do Computador não promovem execução não certificada; permanecem **capability-gated** (`Indisponível / não certificado` por padrão) e Ditado é apenas captura/revisão de texto em rascunho.
