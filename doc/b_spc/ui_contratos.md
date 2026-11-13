# ui_contratos — Reconciliação DBC-9 e Contratos Backend da Interface Visual (M5 / T31)

**Identificador Formal:** `ui_contratos.md`  
**Caminho Canônico:** `doc/b_spc/ui_contratos.md`  
**Etapa / Task:** `M5 / Onda 12 / T31`  
**Versão:** `v01_00_0000`  
**Status:** `IMPLEMENTADO / VERIFICADO OFFLINE (T31 — módulos Python prontos; fiação server.py/openapi.yaml pelo líder)`  
**Autoridade:** Derivado normativo de [`a_ui/README.md`](a_ui/README.md), [`a_ui/b_interface.md`](a_ui/b_interface.md), [`a_ui/c_process.md`](a_ui/c_process.md), [`a_ui/d_figma.md`](a_ui/d_figma.md), [`prd_funcional.md`](prd_funcional.md), [`prd_tecnico.md`](prd_tecnico.md), [`../a_context/backlog.md`](../a_context/backlog.md), [`../a_context/ideia_futura.md`](../a_context/ideia_futura.md), [`../a_context/taxonomia_file_system.md`](../a_context/taxonomia_file_system.md) e [`../g_code/stack.md`](../g_code/stack.md).  
**Escopo:** Reconciliação normativa entre `UI01`–`UI11`, as 18 telas do protótipo Figma (`d_figma.md`), os requisitos `RF01`–`RF30` / `RT01`–`RT30` e as tasks M5 (`T29`–`T38`), além dos contratos formais de PTY interativo (`src/hydra_orch/bridge/pty_runner.py`), anexos (`AttachmentRef` e `AttachmentService` em `src/hydra_orch/core/attachments.py`), preview seguro de artefatos (`read_safe_preview`), busca global (`QuickOpen` via `SearchService`) e `HostCapabilities` (`build_host_capabilities` em `src/hydra_orch/core/search_index.py`).

---

## 1. Purpose (Propósito)

Formalizar, segundo o padrão **DBC-9**, os contratos backend e a matriz de rastreabilidade necessários para que a CLI interativa (`T30`) e a GUI Control Plane (`T32`–`T36`, `T38`) operem estritamente sobre read models persistidos e serviços autenticados do **hydra-orch**, eliminando inferência de sucesso a partir de texto, prevenindo vazamento de segredos/traversal/XSS e bloqueando qualquer simulação enganosa das capacidades de *Parking Lot* (`F06` voz full-duplex e `F07` *Computer Use* / emulação não certificada).

---

## 2. Why (Justificativa)

1. **Separação Estrita entre Protótipo Visual e Execução Verificável:** O protótipo Figma (`d_figma.md`, 18 telas) e os requisitos `UI01`–`UI11` (`b_interface.md`) descrevem fluxos de terminal interativo, anexos, preview, busca global, agendamentos, ditado e painéis de dispositivos/computador que **não** possuíam contratos backend tipados na base M1–M4 (`T01`–`T28`).
2. **Prevenção de Regressões de Segurança na Camada Visual:** Anexos enviados ao chat e artefatos abertos lado a lado (`ArtifactViewer`) são vetores clássicos de *path traversal*, escape por *symlink* e XSS armazenado via HTML, SVG ou `<script>` embutido em Markdown.
3. **Honestidade Multiplataforma de PTY e Bridges:** Ambientes Windows *headless* (sem ConPTY certificado) não podem anunciar certificação PTY equivalente ao PTY POSIX; bridges de emulador móvel e controle de computador permanecem em [`ideia_futura.md`](../a_context/ideia_futura.md) (`F06`/`F07`) e precisam reportar `unavailable` / `uncertified` por padrão.
4. **Alinhamento à Taxonomia e Stack:** Reconciliar as pastas de `frontend/src/` para o singular (`component/`, `feature/`, `hook/`, `page/`, `store/`, `type/`) e registrar `@xterm/xterm`, `Inter`, `JetBrains Mono` e `Lucide` antes das ondas paralelas `O13`–`O15`.

---

## 3. Contract (Contrato Formal)

### 3.1. Matriz Reconciliada: `UI01`–`UI11` + 18 Telas Figma ↔ `RF`/`RT` ↔ Módulos & Tasks M5 (`T29`–`T38`)

> **Regra de Reconciliação (`a_ui/README.md`):** `UI01`–`UI11` são identificadores locais da especificação de interface e **não** renumeram `RF01`–`RF30` nem `RT01`–`RT30`. Capacidades `F06` (antigo RF36) e `F07` (antigo RF37) permanecem isoladas no *Parking Lot* até certificação explícita.

| UI ID | Telas Figma (`d_figma.md`, 18 nós) | RF / RT Normativos Vinculados | Endpoints / Serviços Base (M1–M4) | Novos Módulos / Contratos (M5) | Task M5 | Status após T31 |
|---|---|---|---|---|---|---|
| **UI01** | Novo chat centralizado (`18:8`); Configurações e perfil (`18:454`) | RF01, RF13, RF16, RF17, RF23 / RT10, RT13, RT15, RT23, RT25 | `/v1/control-plane/bootstrap`, `/areas`, `/workspaces`, `/projects`, `/profiles`, `/preferences` | `HostCapabilities` (`search_index.py`), shell + `WorkspaceTree` + `PaneLayout` + `TabBar` | T31, T32 | Contrato backend pronto; GUI em T32 |
| **UI02** | Conversa com coordenador e workers (`7:6`); Coordenação / agentes agrupados (`7:134`) | RF03, RF05, RF07, RF09, RF10, RF13, RF18, RF26, RF27 / RT02, RT03, RT07, RT08, RT16, RT26, RT27 | `/runs`, `/runs/{id}/events` (SSE `Last-Event-ID`), `/sessions`, `/threads`, `/interventions` | `ChatTimeline` SSE dedup + snapshot em `410`, cards de workers, HITL inline | T30, T33 | Base M1–M4 pronta; TUI/GUI em T30/T33 |
| **UI03** | Terminais Codex e Claude Code lado a lado (`7:69`); Codex CLI em painel completo (`22:8`); Claude Code CLI em painel completo (`22:239`) | RF04, RF05, RF06, RF14, RF25 / RT04, RT10, RT14, RT24 | `filter_worker_env`, `cancel_process_tree`, `is_process_alive` (`worker_runner.py`) | `PtyRunner`, `PtySessionInfo`, `PtyChunk` (`bridge/pty_runner.py`) + rotas `/pty/sessions*` | T31, T34, T36 | Módulo PTY pronto (T31); GUI `@xterm/xterm` em T34; certificação SO em T36 |
| **UI04** | Ditado e anexos / inativo (`7:679`) e ativo (`7:1039`) *(fluxo anexos)* | RF03, RF04, RF13, RF16, RF25 / RT10, RT11, RT13, RT25 | `ExecutionStore`, `redact_text` | `AttachmentRef`, `AttachmentService` (`core/attachments.py`) + rotas `/sessions/{id}/attachments*` | T31, T38 | Serviço e contratos prontos (T31); UI drag/drop em T38 |
| **UI05** | Busca global (`7:359`) | RF05, RF13, RF16, RF18 / RT10, RT13, RT16, RT25 | `ExecutionStore` (`areas`, `area_workspaces`, `projects`, `runs`, `sessions`, `artifacts`) | `SearchService.search` (`core/search_index.py`) + `GET /v1/control-plane/search` | T31, T38 | Serviço indexado SQLite pronto (T31); `QuickOpen` `Ctrl+K` em T38 |
| **UI06** | *(Painel adjacente em `7:6`, `7:69` — `ArtifactViewer` & conflitos)* | RF05, RF07, RF08, RF15, RF28, RF30 / RT05, RT06, RT11, RT28, RT30 | `/runs/{id}/artifacts`, `/runs/{id}/conflicts*`, `/runs/{id}/pr-package` | `read_safe_preview`, `ArtifactPreviewResult` (`core/attachments.py`) + `GET /artifacts/{id}/content` | T31, T34 | Preview seguro pronto (T31); viewer lado a lado em T34 |
| **UI07** | Emulador móvel / inativo (`7:519`) e ativo (`7:901`) | RF14, RF25, RB09 / RT14, RT24 *(sem promover escopo futuro)* | `TransportRegistry` (`transport_definitions`, `transport_health`) | `build_host_capabilities` (`mobile_emulator` `unavailable`/`uncertified_parking_lot_bridge`) | T31, T35 | `HostCapabilities` pronto (T31); painel capability-gated em T35 |
| **UI08** | Ditado e anexos / inativo (`7:679`) e ativo (`7:1039`) *(fluxo ditado)* | RF13, RF23 / RT10, RT23 *(distinto de `F06` / antigo RF36 voz duplex)* | `redact_text` | `dictation_stt` em `HostCapabilities` (`available_modes: ["browser_optional_text_draft"]`, `duplex_voice_enabled: false`) | T31, T38 | Capability explícita pronta (T31); rascunho STT revisável sem auto-envio em T38 |
| **UI09** | Contas e consumo (`7:279`); Recursos (`7:205`) *(governança)* | RF11, RF19, RF20, RF21, RF22, RF24, RF29 / RT17, RT18, RT19, RT20, RT21, RT22, RT29 | `/metrics`, `/route-decisions`, `/consents`, `/memory`, `/discovery`, `/skills`, `/mcps`, `/secrets`, `/extensions`, `/budget` | `omniroute_client.py`, `route_selector.py` (`T29`), painéis em `T33`/`T35` | T29, T30, T33, T35 | `T29` paralelo em Onda 12; GUI em T33/T35 |
| **UI10** | Automações / inativo (`7:439`) e ativo (`7:832`) | RF03, RF05, RF13, RF29 / RT03, RT10, RT29 | `ExecutionStore`, `RunService` | `migration/0003_automation.sql`, `core/scheduler.py` (`T37`), `scheduler` capability (`T31`) | T31, T37, T35 | `T37` paralelo em Onda 12; GUI em T35 |
| **UI11** | Controle do computador / inativo (`7:599`) e ativo (`7:970`) | RF14, RF25, RF27 / RT14, RT24, RT27 *(sem promover `F07` / antigo RF37)* | `TransportRegistry`, `HITLService` | `build_host_capabilities` (`computer_use` `unavailable`/`uncertified_parking_lot_bridge`) | T31, T35 | `HostCapabilities` pronto (T31); painel capability-gated em T35 |

**Cobertura das 18 telas Figma:** `18:8`, `7:6`, `7:134`, `7:69`, `22:8`, `22:239`, `7:205`, `7:279`, `7:359`, `7:439`, `7:832`, `7:519`, `7:901`, `7:599`, `7:970`, `7:679`, `7:1039`, `18:454` (18/18 mapeadas).

**Reconciliação de Stack e Taxonomia (`stack.md` ↔ `taxonomia_file_system.md`):**
- Pastas internas de `frontend/src/` adotam rigorosamente o singular: `component/`, `feature/`, `hook/`, `page/`, `store/`, `type/`.
- Dependências visuais consolidadas em `T32`: `@xterm/xterm` + `@xterm/addon-fit`, `Inter`, `JetBrains Mono`, SVGs `lucide-react` (sem bolinhas macOS), tokens `#141414` / `#181818` / `#1C1C1C` / `#202020` / `#303030` / `#E8E8E8` / `#969696`.

---

### 3.2. Contrato de Sessões PTY Interativas (`src/hydra_orch/bridge/pty_runner.py`)

#### Entidades Tipadas
- **`PtySessionInfo` (`ExecutionModel`):**
  - `session_id: Identifier`, `workspace_id: Optional[str]`, `host_id: NonEmpty = "local"`, `cwd: NonEmpty`, `command: Tuple[str, ...]`, `pid: Optional[int]`, `cols: int (1..1000)`, `rows: int (1..1000)`, `status: Literal["running", "exited", "cancelled", "crashed"]`, `detached: bool`, `exit_code: Optional[int]`, `backend_kind: NonEmpty`, `pty_certified: bool`, `last_seq: int >= 0`, `oldest_seq: int >= 0`, `created_at: UtcTimestamp`, `finished_at: Optional[UtcTimestamp]`.
- **`PtyChunk` (`ExecutionModel`):**
  - `seq: int >= 1` (monotônico por sessão), `session_id: Identifier`, `stream: Literal["pty", "stdout", "stderr", "system"]`, `text: str` (UTF-8 com substituição de bytes inválidos e redigido via `redact_text`), `raw_bytes_len: int >= 0`, `timestamp: UtcTimestamp`.

#### Operações do Serviço `PtyRunner`
| Operação Lógica | Assinatura Python (`PtyRunner`) | Rota HTTP/Stream Proposta (fiação pelo líder) | Comportamento Normativo |
|---|---|---|---|
| `open` | `await open_session(command, *, cwd, session_id=None, workspace_id=None, host_id="local", cols=80, rows=24, allowed_env=None, env=None) -> PtySessionInfo` | `POST /v1/control-plane/pty/sessions` | Valida `cwd` existente (sem NUL), valida `command` e `cols`/`rows`, filtra ambiente com `filter_worker_env` e inicia PTY POSIX (`posix_pty`, `pty_certified=True`) ou `pipe_interactive_bridge` (`pty_certified=False`) em Windows *headless*. |
| `input` | `await write_input(session_id, data) -> int` | `POST /v1/control-plane/pty/sessions/{session_id}/input` | Envia bytes/UTF-8 para stdin/PTY master apenas se `status == "running"`. |
| `resize` | `await resize(session_id, *, cols, rows) -> PtySessionInfo` | `POST /v1/control-plane/pty/sessions/{session_id}/resize` | Atualiza `cols`/`rows` e aplica `fcntl.ioctl(..., TIOCSWINSZ, ...)` em `posix_pty`. |
| `interrupt` | `await interrupt(session_id) -> PtySessionInfo` | `POST /v1/control-plane/pty/sessions/{session_id}/interrupt` | Envia `\x03` + `SIGINT` no grupo de processo POSIX ou `\x03` + `CTRL_BREAK_EVENT` no grupo Windows (idempotente se já encerrado). |
| `reconnect/backlog` | `read_output(session_id, *, after_seq=0) -> List[PtyChunk]` / `async for c in stream(session_id, *, after_seq=0)` | `GET /v1/control-plane/pty/sessions/{session_id}/output?after_seq=` / `GET .../stream` | Entrega apenas chunks com `seq > after_seq` do ring buffer limitado; se `after_seq > 0` foi evictado, levanta `ContractViolation("cursor_expired")` (`410`). |
| `exit` | `await wait(session_id, *, timeout=None) -> PtySessionInfo` / `get_session(session_id)` | `GET /v1/control-plane/pty/sessions/{session_id}` | Drena leitores antes de publicar EOF e persiste `status="exited"` + `exit_code`. |
| `close(keep_running)` | `await close_session(session_id, *, keep_running=False) -> PtySessionInfo` | `POST /v1/control-plane/pty/sessions/{session_id}/close` | `keep_running=True`: desconecta assinantes ativos (`stream`) mantendo `status="running"` e `detached=True`. `keep_running=False`: encerra toda a árvore de processos com `cancel_process_tree` e fecha leitores sem órfãos. |
| Shutdown | `await close_all() -> None` | *Lifespan shutdown* | Encerra todas as sessões com `keep_running=False`. |

---

### 3.3. Contrato de Anexos (`AttachmentRef` & `AttachmentService`)

- **`AttachmentRef` (`ExecutionModel`):**
  - `attachment_id: Identifier`, `workspace_id: NonEmpty`, `session_id: NonEmpty`, `host_id: NonEmpty = "local"`, `filename: NonEmpty`, `mime_type: NonEmpty`, `size_bytes: int >= 0`, `sha256: Sha256`, `storage_rel_path: RelativePath`, `transfer_status: Literal["local_ready", "pending_remote_confirm", "transferred", "failed"]`, `remote_confirmed: bool`, `created_at: UtcTimestamp`.
- **Política de Segurança e Persistência (`AttachmentService(root_dir, *, max_bytes=10 MiB)`):**
  - **Allowlist MIME/Extensão:** `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `application/pdf`, `text/plain`, `text/markdown`, `application/json`, `text/x-python`, `application/typescript`, `text/csv`, `text/x-diff`, `text/x-patch`, `text/yaml`, `application/toml`.
  - **Rejeição Explícita (`ContractViolation("unsupported_attachment_type")`):** `text/html`, `image/svg+xml`, `application/javascript`, `.html`, `.htm`, `.svg`, `.js`, `.exe`, `.bat`, `.cmd`, `.sh`, `.ps1`, assinaturas executáveis (`MZ`, `\x7fELF`) ou HTML/SVG disfarçado.
  - **Limite de Tamanho (`ContractViolation("attachment_too_large")`):** `size_bytes <= max_bytes`.
  - **Anti-Traversal & Symlink (`ContractViolation("path_traversal_blocked")`):** Rejeita `..`, `/`, `\`, `:`, `\x00` no nome do arquivo e qualquer *symlink* escapando de `root_dir`.
  - **Persistência Durável:** Escrita atômica (`tmp` → `fsync` → `os.replace`) do payload e do índice `root_dir / "_index.json"` sobrevivendo a reinícios do serviço.
  - **Escopo por Sessão (`ContractViolation("forbidden_scope")`):** `list_attachments(session_id)` e `get_attachment(attachment_id, *, session_id)` restringem acesso exclusivamente à sessão proprietária.
  - **Transferência Remota Explícita:** Para `host_id != "local"`, grava inicialmente `transfer_status="pending_remote_confirm"` e `remote_confirmed=False`; somente `confirm_remote_transfer(attachment_id, *, session_id)` transiciona para `transfer_status="transferred"`, `remote_confirmed=True`.
- **Rotas Propostas (fiação pelo líder):**
  - `POST /v1/control-plane/sessions/{session_id}/attachments` (`201 Created`)
  - `GET /v1/control-plane/sessions/{session_id}/attachments` (`200 OK`)
  - `POST /v1/control-plane/sessions/{session_id}/attachments/{attachment_id}/confirm-transfer` (`200 OK`)

---

### 3.4. Contrato de Preview Seguro de Artefatos (`read_safe_preview` & `ArtifactPreviewResult`)

- **Função:** `read_safe_preview(base_dir: Path | str, rel_path: str, *, max_bytes: int = 512 * 1024) -> Dict[str, Any]` (e `build_safe_preview(...) -> ArtifactPreviewResult`).
- **Rota Proposta (fiação pelo líder):** `GET /v1/control-plane/artifacts/{id}/content` (e preview relativo ao workspace autorizado).
- **Modos de Renderização:**
  - `markdown`: aplica `redact_text`, remove `<script>...</script>`, blocos/tags `<iframe|object|embed|svg|math>`, atributos `on\w+=` e URIs `javascript:` / `vbscript:` / `data:text/html`; retorna `sanitized_markdown`, `content`, `render_mode="markdown"`, `script_stripped: bool`, `supported=True`, `status="ok"`.
  - `text` / `diff`: aplica `redact_text`, `supported=True`, `status="ok"`.
  - `image` (`png`, `jpeg`, `webp`, `gif`) e `pdf`: valida assinatura (bloqueia HTML/SVG disfarçado), calcula `sha256` e retorna `content_base64`, `render_mode="image"|"pdf"`, `supported=True`, `status="ok"`.
  - `unsupported` (`text/html`, `image/svg+xml`, `.js`, `.exe`, binários desconhecidos): **jamais** retorna HTML/SVG executável; retorna `supported=False`, `status="unsupported_media_type"`, `content=None`, `content_base64=None`.

---

### 3.5. Contrato de Busca Global (`QuickOpen` — `SearchService`)

- **Rota:** `GET /v1/control-plane/search?q=<query>&scope=<opt>&host_id=<opt>&limit=<opt>`
- **Assinatura:** `await SearchService(store).search(query, *, scope=None, host_id="local", limit=25) -> List[Dict[str, Any]]`
- **Tabelas Consultadas (SQLite WAL parametrizado com `LIKE ? ESCAPE '\'`):** `areas`, `area_workspaces`, `projects`, `runs`, `sessions`, `artifacts`.
- **Estrutura de Cada Item:**
  ```json
  {
    "kind": "area | workspace | project | run | session | artifact",
    "id": "string",
    "title": "string (redigido)",
    "subtitle": "string (redigido)",
    "host_id": "local",
    "workspace_id": "string | null",
    "project_id": "string | null",
    "run_id": "string | null",
    "session_id": "string | null",
    "tab_hint": "workspace | chat | terminal | artifact"
  }
  ```
- **Regras:** Consultas de segredos ou resultados vazios após `redact()` são descartados; navegação usa `session_id` / `run_id` / `tab_hint` para focar a aba existente sem recriar sessão.

---

### 3.6. Contrato de `HostCapabilities` (`build_host_capabilities`)

- **Assinatura:** `build_host_capabilities(config=None, transports=()) -> Dict[str, Any]`
- **Rota Proposta:** Incorporado em `/v1/control-plane/bootstrap` e `/v1/control-plane/capabilities`.
- **Valores Padrão Obrigatórios por Host (`local` + cada transporte em `transports`):**
  - `pty`: `{status: "available" | "degraded" | "unavailable", supported, certified, backend_kind, platform, reason}`
  - `attachments`: `{status, supported, certified, max_bytes, remote_confirm_required}`
  - `quickopen`: `{status, supported, certified}`
  - `preview`: `{status, supported, certified, max_bytes, supported_kinds}`
  - `scheduler`: `{status, supported, certified}`
  - `dictation_stt`: `{status: "available"|"unavailable", available_modes: ["browser_optional_text_draft"], duplex_voice_enabled: false, requires_review_before_send: true}`
  - `mobile_emulator`: `{status: "unavailable", supported: false, certified: false, reason: "uncertified_parking_lot_bridge"}` *(só muda para `available`/`certified=True` se um transporte em `transports` com `is_certified=True` declarar explicitamente `mobile_emulator`)*
  - `computer_use`: `{status: "unavailable", supported: false, certified: false, reason: "uncertified_parking_lot_bridge"}` *(só muda para `available`/`certified=True` se um transporte em `transports` com `is_certified=True` declarar explicitamente `computer_use`)*

---

## 4. Preconditions (Pré-condições)

1. `ExecutionStore` inicializado com migrações `0001_initial_core.sql` e `0002_control_plane.sql` para consultas de `SearchService`.
2. Diretório `cwd` do PTY e `base_dir` do preview existem e são diretórios reais no host local.
3. Requisições HTTP futuras ao control plane possuem token Bearer local válido e origem CORS allowlisted (RT10/RT25).

---

## 5. Postconditions (Pós-condições)

1. Todo chunk emitido por `PtyRunner` possui `seq` monotônico único na sessão, conteúdo UTF-8 válido e redigido via `redact_text`.
2. Fechar sessão PTY com `keep_running=False` ou encerrar via `close_all()` mata toda a árvore de processos (`is_process_alive(pid) == False` inclusive descendentes) e finaliza tarefas leitoras.
3. Todo anexo aceito em `AttachmentService` possui `sha256` verificável, persistência no arquivo e em `_index.json`, sobrevivendo a reinício.
4. `build_host_capabilities` reporta explicitamente `unavailable` / `certified=False` para `mobile_emulator` e `computer_use` não certificados e `duplex_voice_enabled=False` para ditado.

---

## 6. Invariants (Invariantes)

- **Invariante de Não-Fabricação:** Nenhum transporte não certificado (`is_certified=False`) ou bridge Windows sem ConPTY pode anunciar `certified=True`.
- **Invariante Zero Segredos:** Variáveis sensíveis são filtradas antes do spawn (`filter_worker_env`), saídas PTY/preview/search passam por `redact_text`/`redact`.
- **Invariante de Confinamento de Caminho:** Nenhum anexo ou preview resolve fora de seu diretório raiz autorizado, nem via `..` nem via *symlink*.
- **Invariante de Isolamento de Sessão:** Um `session_id` não lê nem confirma anexos pertencentes a outra sessão (`forbidden_scope`).
- **Invariante de Conteúdo Inerte:** Markdown sanitizado nunca preserva `<script>`, `on*=` ou `javascript:`; HTML e SVG retornam `unsupported_media_type` sem corpo executável.

---

## 7. Failure Modes (Modos de Falha)

| Cenário | Código `ContractViolation` | HTTP Mapeado | Comportamento Obrigatório |
|---|---|---|---|
| `cwd` inexistente, arquivo ou com NUL no PTY | `invalid_workspace_cwd` | `400` | Rejeita antes do spawn |
| Cursor `after_seq` evictado do ring buffer PTY | `cursor_expired` | `410` | Informa expiração do cursor ao cliente |
| Cursor `after_seq < 0` | `invalid_cursor` | `400` | Recusa leitura/stream |
| Escrita/resize em sessão PTY encerrada | `pty_session_closed` | `409` | Recusa mutação sem crash |
| Anexo `.html`, `.svg`, `.js`, `.exe`, `.bat`, `.sh`, `.ps1` | `unsupported_attachment_type` | `422` | Rejeita sem gravar em disco |
| Anexo acima de `max_bytes` | `attachment_too_large` | `422` / `413` | Rejeita antes de persistir |
| Traversal (`..`, `/`, `\`, `:`) ou symlink externo | `path_traversal_blocked` | `400` / `403` | Bloqueia acesso imediatamente |
| Acesso a anexo de outra sessão | `forbidden_scope` | `403` | Nega acesso cross-session |
| Preview excede `max_bytes` | `preview_too_large` | `422` / `413` | Nega leitura evitando bloqueio de UI |
| Artefato/anexo/sessão inexistente | `resource_not_found` | `404` | Envelope padronizado sem stack trace |
| Preview de `text/html`, `image/svg+xml` ou binário | *(retorno `supported=False`)* | `200` / `415` | `status="unsupported_media_type"`, sem conteúdo ativo |
| Payload SQL injection em `QuickOpen` | *(consulta parametrizada)* | `200` | Tratado como texto literal sem erro SQL |

---

## 8. How (Arquitetura e Implementação)

1. **`src/hydra_orch/bridge/pty_runner.py`:**
   - Reaproveita `filter_worker_env`, `cancel_process_tree` e `is_process_alive` de `bridge/worker_runner.py` e `redact_text` de `core/redaction.py`.
   - Em POSIX (`Linux`/`Darwin`), abre par `pty.openpty()`, aplica `TIOCSCTTY` e `TIOCSWINSZ`, lê assincronamente via `loop.add_reader` com decodificador UTF-8 incremental. Em Windows *headless*, usa pipes bidirecionais em `CREATE_NEW_PROCESS_GROUP` reportando `backend_kind="pipe_interactive_bridge"` e `pty_certified=False`.
   - Mantém `collections.deque` limitado por chunks e bytes para replay (`read_output`/`stream`) e filas por assinante para detach limpo (`keep_running=True`).
2. **`src/hydra_orch/core/attachments.py`:**
   - `AttachmentService` valida MIME/extensão/assinatura binária, isola arquivos em `files/<session_id>/` sob `root_dir`, grava payloads e `_index.json` atomicamente com `fsync` + `os.replace`.
   - `read_safe_preview` e `build_safe_preview` validam todos os segmentos contra *symlinks* externos, aplicam teto `max_bytes`, sanitizam Markdown e bloqueiam HTML/SVG/executáveis.
3. **`src/hydra_orch/core/search_index.py`:**
   - `SearchService` executa consultas SQLite parametrizadas (`LIKE ? ESCAPE '\'`) nas 6 tabelas do control plane, redige resultados e preserva IDs de navegação para `QuickOpen`.
   - `build_host_capabilities` agrega `detect_pty_backend()`, `HydraConfig` e `TransportDefinition` mantendo `F06`/`F07` bloqueados por padrão.

---

## 9. Examples (Exemplos de Aceite)

### Exemplo 1: Sessão PTY com Detach, Reconexão por Cursor e Tree Kill
1. `info = await runner.open_session([sys.executable, "-u", "echo.py"], cwd=tmp_path)` → `info.status == "running"`, `info.backend_kind` explícito.
2. `await runner.write_input(info.session_id, "olá 🚀\n")` → chunk recebido com Unicode preservado e `seq == 1`.
3. `await runner.close_session(info.session_id, keep_running=True)` → assinante `stream` encerra limpo, `detached == True`, processo continua vivo; nova saída recebe `seq == 2`.
4. `missed = runner.read_output(info.session_id, after_seq=1)` → retorna exatamente `[chunk(seq=2)]` sem lacuna nem duplicação.
5. `await runner.close_session(info.session_id, keep_running=False)` → `cancel_process_tree` encerra pai e filhos (`is_process_alive == False`).

### Exemplo 2: Anexo Remoto, Escopo Cruzado e Preview Seguro
1. `ref = service.save_attachment("ws-1", "sess-a", "spec.md", b"# Hi\n<script>alert(1)</script>", host_id="ssh-1")` → `ref.transfer_status == "pending_remote_confirm"`, `ref.remote_confirmed is False`.
2. `service.get_attachment(ref.attachment_id, session_id="sess-b")` → levanta `ContractViolation("forbidden_scope")`.
3. `confirmed = service.confirm_remote_transfer(ref.attachment_id, session_id="sess-a")` → `confirmed.transfer_status == "transferred"`, `confirmed.remote_confirmed is True`.
4. `preview = read_safe_preview(base_dir, "spec.md")` → `preview["script_stripped"] is True`, `"<script"` ausente de `preview["sanitized_markdown"]`.

---

## 10. GAPs

- **GAP-UI-01 (Integração `server.py` / `openapi.yaml`):** A exposição HTTP das rotas `/v1/control-plane/pty/sessions*`, `/v1/control-plane/sessions/{id}/attachments*`, `/v1/control-plane/artifacts/{id}/content` e `/v1/control-plane/search` e o mapeamento HTTP de `forbidden_scope` (`403`), `path_traversal_blocked` (`400`/`403`) e `attachment_too_large` / `preview_too_large` (`413`/`422`) pertencem à etapa de integração do líder após Onda 12.
- **GAP-UI-02 (Certificação Win32 ConPTY):** Em Windows *headless*, `PtyRunner` opera com `backend_kind="pipe_interactive_bridge"` e `pty_certified=False`; a certificação dedicada de ConPTY Windows ocorrerá na Task `T36`.
- **GAP-UI-03 (Parking Lot `F06` e `F07`):** Voz full-duplex (`F06`), *Computer Use* (`F07`) e emulação móvel permanecem `unavailable` até entrega de bridges certificados com HITL e gate próprio.

---

## 11. Glossary e Acrônimos

| Termo / Acrônimo | Definição |
|---|---|
| **`after_seq`** | Cursor numérico monotônico usado para reconexão e replay sem lacunas em streams PTY e SSE |
| **`ArtifactPreviewResult`** | Schema Pydantic padronizado para retorno seguro de preview de Markdown, texto, diff, imagem e PDF |
| **`AttachmentRef`** | Referência tipada de anexo vinculada a `workspace_id`, `session_id`, `host_id`, SHA-256 e estado de transferência |
| **`ConPTY`** | Pseudoconsole nativo do Windows (ainda não certificado nesta fase; substituído explicitamente por `pipe_interactive_bridge`) |
| **`DBC-9`** | Design by Contract em 9 seções normativas padrão do `hydra-orch` |
| **`HostCapabilities`** | Mapa honesto de capacidades por host computado por `build_host_capabilities` |
| **HITL** | *Human-in-the-Loop* — intervenção humana autenticada antes de ações sensíveis |
| **Parking Lot** | Catálogo de ideias futuras isoladas em [`ideia_futura.md`](../a_context/ideia_futura.md) (`F01`–`F08`) fora do escopo certificado |
| **PTY** | *Pseudo-Terminal* — canal interativo bidirecional de terminal com suporte a ANSI, resize e sinais |
| **`QuickOpen`** | Paleta de busca global por teclado (`Ctrl+K`) indexada por `SearchService` sobre o SQLite WAL |
| **Redaction** | Sanitização determinística de segredos e credenciais via `core/redaction.py` |
| **XSS** | *Cross-Site Scripting* — mitigado no preview pela sanitização de Markdown e bloqueio de HTML/SVG ativos |
