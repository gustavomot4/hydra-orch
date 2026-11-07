# g_code — Arquitetura de Módulos e Código-Fonte

**Identificador Formal:** `g_code`
**Caminho Canônico:** `doc/g_code/`
**Versão:** `v01_01_0000`
**Status:** `APROVADO / NORMATIVO`
**Autoridade:** Arquitetura do hydra-orch, complementando `prd_tecnico.md`, `stack.md`.
**Escopo:** Stack tecnológica, decomposição de pacotes, responsabilidades por camada, convenções de código.

---

Este diretório concentra a documentação de arquitetura de código do **hydra-orch**.

## Artefatos Canônicos

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| [`stack.md`](stack.md) | Especificação Normativa | Stack tecnológica completa (backend Python, frontend React/TS, infra, tooling, CI/CD, estrutura de diretórios, convenções) |
| [`architecture.md`](architecture.md) | Arquitetura Normativa | Mapeamento de responsabilidades entre camadas (`core`, `engine`, `bridge`, `adapter`), fronteiras Hydra vs OmniRoute vs UI |
| `patterns.md` | Padrões (planejado) | Design patterns, error handling, testing patterns, async patterns |

## Stack Tecnológica

A stack completa está definida em [`stack.md`](stack.md). Resumo:

### Backend (Control Plane)
- **Python 3.12+** com **FastAPI**, **Typer**, **SQLAlchemy 2.0** (async), **SQLite** (WAL)
- **Pydantic v2** para todos contratos (RunSpec, TaskSpec, eventos, API)
- **Structlog** + **Prometheus** para observabilidade
- **GitPython** + **psutil** para workspace e processos
- **Tree-sitter** para code stitching (handoff/Relay)

### Frontend (Interface Visual)
- **React 18** + **TypeScript 5.5** + **Vite 5**
- **TanStack Query** (server state), **Zustand** (UI state)
- **Radix UI** + **Tailwind CSS** (acessibilidade WCAG AA)
- **Monaco Editor** + **diff2html** (diff viewer)
- **OpenAPI → TypeScript** automático via `@hey-api/openapi-ts`

### Infraestrutura
- **Docker** multi-stage (non-root, healthcheck)
- **Docker Compose** para dev stack
- **GitHub Actions** CI/CD (matrix Win/Linux/macOS)
- **Hatch** para build/publish Python

## Estrutura de Pacotes (src/hydra_orch/)

```
src/hydra_orch/
├── __init__.py         # __version__
├── cli.py              # Typer entrypoint
├── server.py           # FastAPI app + lifespan
├── config.py           # Pydantic Settings (config.yaml)
├── model.py            # Schemas Pydantic (contratos centrais)
│
├── core/               # Serviços de aplicação (control plane)
│   ├── checkpointer.py     # SQLAlchemy + Alembic + WAL
│   ├── git_workspace.py    # Git worktree wrapper
│   ├── run_service.py      # Orquestração central
│   ├── session_service.py  # Comandos /compact, /plan, /build
│   ├── scheduler.py        # DAG (Kahn) + semaphore
│   ├── auth.py             # JWT + RBAC
│   ├── redaction.py        # Redactor centralizado
│   ├── budget.py           # BudgetGovernor
│   ├── conflict_resolver.py
│   ├── packaging.py        # PRPackager
│   ├── hitl.py             # Human-in-the-Loop manager
│   ├── mcp_service.py      # Gestão de servidores MCP e live tools
│   ├── computer_use_governor.py # Safety Governor para desktop/browser
│   ├── voice_session.py    # Gerenciador de voz duplex WebSocket
│   └── knowledge/          # Módulo RAG isolado (store, ingest, retriever)
│
├── engine/             # Estratégias de execução
│   ├── swarm.py            # SwarmEngine (paralelo + DAG)
│   ├── relay.py            # RelayEngine + HandoffCheckpoint
│   ├── persist.py          # PersistEngine + timer
│   ├── healer.py           # HealerEngine + tree-sitter
│   └── multimodal.py       # Orquestrador de jobs multimídia (imagem/áudio/vídeo)
│
├── bridge/             # Transporte, subprocess, SSH
│   ├── worker_runner.py    # AgentExecutor interface + drivers
│   ├── process.py          # ProcessManager (tree kill, sandbox)
│   ├── ssh_tunnel.py       # SSH tunnel manager
│   ├── mcp_client.py       # Cliente MCP stdio/SSE/HTTP
│   ├── connector/          # Conectores de tarefas (Jira, Kanbanize, GitHub)
│   ├── voice/              # Drivers STT Whisper e TTS Kokoro
│   ├── computer_use/       # Drivers de desktop OS e browser Playwright
│   ├── local_llm/          # Catálogo Ollama/LM Studio e quantização GGUF
│   ├── omniroute_client.py
│   └── transport_registry.py
│
└── adapter/            # Provedores de inferência
    ├── base.py             # InferenceProvider interface
    ├── remote_local.py     # Provedores locais (Ollama, vLLM)
    └── multimodal.py       # Adaptadores de geração multimídia
```

## Responsabilidades por Camada

| Camada | Responsabilidade | Não Faz |
|--------|------------------|---------|
| **core/** | Orquestração, estado, persistência, políticas, segurança | Execução direta, inferência, transporte |
| **engine/** | Estratégias de tarefa (Swarm, Relay, Persist, Heal) | Persistência, auth, Git direto |
| **bridge/** | Transporte, subprocess, SSH, gateway OmniRoute | Lógica de negócio, decisões de aceite |
| **adapter/** | Inferência (chat/completions), capabilities | Mutação Git, execução de ferramentas |

## Princípios de Código

1. **Type hints obrigatórios** — `mypy --strict` em toda API pública
2. **Pydantic v2 everywhere** — Schemas = Contratos = OpenAPI = Testes
3. **Async/await** — Todo I/O (DB, HTTP, subprocess, Git, SSE)
4. **Structured logging** — `structlog` JSON, contextvars, redaction hook
5. **Zero `print()`** — Logger em todos módulos
6. **Testes no mesmo commit** — TDD leve, fixtures em `tests/conftest.py`
7. **Imutabilidade** — RunSpec/TaskSpec/ProfileSnapshot congelados por run

## Convenções de Nomenclatura

| Tipo | Padrão | Exemplo |
|------|--------|---------|
| Arquivos/módulos | `snake_case` singular | `run_service.py`, `git_workspace.py` |
| Classes | `PascalCase` | `RunService`, `HandoffCheckpoint` |
| Funções/métodos | `snake_case` | `create_worktree`, `validate_dag` |
| Constantes | `UPPER_SNAKE` | `MAX_PARALLEL_WORKTREES` |
| Variáveis privadas | `_leading_underscore` | `_cache`, `_semaphore` |
| Type aliases | `PascalCase` + `Type` | `RunSpecType`, `TaskStatus` |

## Referências Cruzadas

| Documento | Link |
|-----------|------|
| Stack Completa | [`stack.md`](stack.md) |
| Arquitetura e Fronteiras | [`architecture.md`](architecture.md) |
| PRD Técnico | [`../b_spc/prd_tecnico.md`](../b_spc/prd_tecnico.md) |
| API OpenAPI | [`../f_api/openapi.yaml`](../f_api/openapi.yaml) |
| Testes | [`../h_test/README.md`](../h_test/README.md) |
| Infraestrutura | [`../i_infra/README.md`](../i_infra/README.md) |

---

## GAPs

- GAP-GCODE-01: Documentar `architecture.md` com diagramas de sequência por caso de uso
- GAP-GCODE-02: Definir `patterns.md` com error handling, retry, circuit breaker patterns
- GAP-GCODE-03: Especificar interface `AgentExecutor` completa com todos drivers
- GAP-GCODE-04: Documentar migração de `core/swarm.py` legado → `engine/swarm.py`