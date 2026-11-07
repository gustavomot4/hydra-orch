# stack — Stack Tecnológica e Estrutura do Projeto hydra-orch

**Identificador Formal:** `stack.md`
**Caminho Canônico:** `doc/g_code/stack.md`
**Versão:** `v01_00_0000`
**Status:** `APROVADO / NORMATIVO`
**Autoridade:** Decisão arquitetural baseada em `prd_tecnico.md`, `architecture.md`, `i_infra/README.md`.
**Escopo:** Linguagens, frameworks, dependências, estrutura de pacotes, tooling, CI/CD para backend (Python) e frontend (React/TS).

---

## 1. Propósito

Definir a stack tecnológica padrão, versões fixas, estrutura de diretórios e convenções de desenvolvimento para garantir consistência, reprodutibilidade e manutenibilidade do hydra-orch.

## 2. Justificativa

O projeto exige execução verificável local, orquestração assíncrona, streaming SSE, isolamento de processos Git, e interface visual desacoplada. A stack escolhida prioriza: zero-config local (SQLite), type-safety ponta-a-ponta (Pydantic + TypeScript), economia de tokens (estrutura previsível), e testes herméticos.

## 3. Contrato

### 3.1 Backend (Control Plane) — Python 3.12+

| Camada | Tecnologia | Versão Mínima | Finalidade |
|--------|------------|---------------|------------|
| **Runtime** | CPython | 3.12 | Async nativo, performance, suporte longo |
| **CLI** | Typer | 0.12 | Type hints, comandos aninhados, shell completion |
| **API** | FastAPI | 0.110 | OpenAPI automático, SSE nativo, validação Pydantic |
| **Server** | Uvicorn | 0.29 | ASGI, workers, reload, TLS |
| **Async** | AnyIO | 4.3 | Structured concurrency, task groups, timeouts |
| **Validação** | Pydantic | 2.7 | Schemas centrais, serialização, OpenAPI |
| **Settings** | Pydantic-Settings | 2.3 | Config tipada (YAML + env vars) |
| **Database** | SQLite + aiosqlite | 3.35 / 0.19 | Embedded, WAL, async, ACID |
| **ORM** | SQLAlchemy | 2.0 | Async, type-safe, migrações Alembic |
| **Migrations** | Alembic | 1.13 | Versionadas, rollback, offline-capable |
| **Git** | GitPython | 3.1 | Worktree, diff, merge, status |
| **Processos** | psutil | 5.9 | Tree kill, resource monitoring, cross-platform |
| **Code Stitching** | Tree-sitter | 0.22 | AST incremental multi-linguagem |
| **HTTP Client** | HTTPX | 0.27 | Async, timeout, retry, circuit breaker |
| **Auth** | python-jose + Passlib | 3.3 / 1.7 | JWT HS256, Argon2, scopes RBAC |
| **Observabilidade** | Structlog + Prometheus | 24.1 / 0.19 | JSON logs, métricas `/metrics` |
| **Config** | PyYAML | 6.0 | `config.yaml` tipado |
| **Build** | Hatch | 1.11 | PEP 621, versioning, publishing |
| **Voice / STT / TTS** *(V5)* | faster-whisper + sounddevice | 1.0 / 0.4 | Transcrição local, reprodução áudio, VAD |
| **Computer Use** *(V5)* | Playwright + PyAutoGUI + Pillow | 1.44 / 0.9 / 10.3 | Automação navegador/desktop, screenshots |
| **Knowledge / RAG** *(V6)* | pypdf + sqlite-vss (ou chromadb) | 4.2 / 0.1 | Extração documentos, busca vetorial híbrida |
| **Local LLM Foundry** *(V6)* | huggingface-hub + llama-cpp-python | 0.23 / 0.2 | Download modelos, quantização GGUF local |
| **Trackers** *(V6)* | jira + python-gitlab | 3.8 / 4.4 | Conectores REST Jira e GitLab |

### 3.2 Frontend (Interface Visual) — React 18 + TypeScript 5.5

| Camada | Tecnologia | Versão | Finalidade |
|--------|------------|--------|------------|
| **Runtime** | Node.js | 20 LTS | ES2023, fetch, WebSocket |
| **Build** | Vite | 5.4 | HSR, ESM, otimizado |
| **Framework** | React | 18.3 | Concurrent, Suspense, Server Components ready |
| **Language** | TypeScript | 5.5 | Strict mode, type inference |
| **Routing** | React Router | 6.26 | Data loading, nested routes |
| **State/Server** | TanStack Query | 5.51 | Cache, dedup, SSE integration, mutations |
| **Client State** | Zustand | 4.5 | Global UI state (sidebar, theme, modals) |
| **SSE** | eventsource-parser | 1.1 | Parser streaming, reconnection |
| **UI Primitives** | Radix UI | 1.1 | Acessível, unstyled, WCAG AA |
| **Styling** | Tailwind CSS | 3.4 | Utility-first, design tokens, dark mode |
| **Icons** | Lucide React | 0.436 | Consistente, tree-shakable |
| **Diff/Patch** | diff2html + Monaco | 3.4 / 4.6 | Side-by-side, syntax highlight |
| **Forms** | React Hook Form + Zod | 7.52 / 3.23 | Validação schema-first |
| **Dates** | date-fns | 3.6 | Imutável, tree-shakable, i18n |
| **Testing** | Vitest + Testing Library | 2.0 / 16.0 | Unit, integration, a11y |
| **Lint/Format** | ESLint + Prettier | 8.57 / 3.3 | TypeScript-aware, Tailwind plugin |

### 3.3 Infraestrutura & Deploy

| Componente | Tecnologia | Finalidade |
|------------|------------|------------|
| **Container** | Docker multi-stage (python:slim) | Non-root, healthcheck, digest pins |
| **Orchestration** | Docker Compose | Dev stack (API + OmniRoute + UI) |
| **SSH Tunnel** | autossh / Python | Reverse tunnel GPU remoto, healthcheck |
| **CI/CD** | GitHub Actions | Matrix Win/Linux/macOS, cache, artifacts |
| **Package** | Hatch | PyPI publish, versioning via git tags |
| **Quality** | Ruff + MyPy + PyRight | Fast lint, type check, strict mode |

---

## 4. Estrutura de Diretórios (Monorepo)

```
hydra-orch/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # Testes, lint, type-check, build
│   │   ├── release.yml         # Tag → PyPI + Docker Hub
│   │   └── dependabot.yml      # Updates automáticos
│   └── dependabot.yml
├── .vscode/
│   ├── settings.json           # Python/TS paths, format on save
│   └── launch.json             # Debug configs
├── docs/                       # Symlink para doc/ (compatibilidade)
├── doc/                        # Documentação canônica (prefixos a_..j_)
│   ├── a_context/
│   ├── b_spc/
│   ├── c_activity/
│   ├── d_mer/
│   ├── e_class/
│   ├── f_api/
│   ├── g_code/
│   │   ├── stack.md            # ESTE ARQUIVO
│   │   └── README.md
│   ├── h_test/
│   ├── i_infra/
│   └── j_manual/
├── frontend/                   # React + TS + Vite
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── features/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── pages/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── .eslintrc.json
├── src/
│   └── hydra_orch/             # Pacote Python (PEP 621)
│       ├── __init__.py         # __version__ = "0.1.0"
│       ├── cli.py              # Typer app
│       ├── server.py           # FastAPI app + lifespan
│       ├── config.py           # Pydantic Settings
│       ├── model.py            # Schemas Pydantic (contratos)
│       ├── core/               # Serviços de aplicação
│       │   ├── run_service.py
│       │   ├── session_service.py      # [+ V5] Comandos /compact, /plan, /build
│       │   ├── mcp_service.py          # [+ V6] Catálogo e controle de MCPs
│       │   ├── computer_use_governor.py # [+ V5] HITL e segurança de desktop/browser
│       │   ├── voice_session.py        # [+ V5] Sessão de voz duplex WebSocket
│       │   └── knowledge/              # [+ V6] Módulo RAG corporativo/pessoal
│       │       ├── __init__.py
│       │       ├── store.py            # SQLite + Vector / BM25
│       │       ├── ingest.py           # Extratores PDF, MD, Code
│       │       └── retriever.py        # Busca híbrida e injeção de contexto
│       ├── engine/             # Estratégias (Swarm, Relay, Persist)
│       │   ├── swarm.py
│       │   ├── relay.py
│       │   ├── persist.py
│       │   ├── healer.py
│       │   └── multimodal.py           # [+ V5] Orquestrador de jobs multimídia
│       ├── bridge/             # Transporte, subprocess, SSH
│       │   ├── worker_runner.py
│       │   ├── mcp_client.py           # [+ V6] Cliente protocolo MCP
│       │   ├── connector/              # [+ V6] Conectores de tarefas
│       │   │   ├── __init__.py
│       │   │   ├── base.py             # TicketProvider ABC
│       │   │   ├── jira.py             # Conector Jira REST
│       │   │   ├── kanbanize.py        # Conector Kanbanize API
│       │   │   └── github.py           # Conector GitHub Issues/Projects
│       │   ├── voice/                  # [+ V5] Drivers de áudio
│       │   │   ├── __init__.py
│       │   │   ├── stt.py              # Whisper STT
│       │   │   └── tts.py              # Kokoro / ElevenLabs TTS
│       │   ├── computer_use/           # [+ V5] Automação de SO e browser
│       │   │   ├── __init__.py
│       │   │   ├── desktop.py          # Mouse, teclado e screenshots
│       │   │   └── browser.py          # Playwright CDP wrapper
│       │   └── local_llm/              # [+ V6] Gestão de modelos locais
│       │       ├── __init__.py
│       │       ├── catalog.py          # Ollama/LM Studio API
│       │       ├── quantize.py         # llama.cpp GGUF converter
│       │       └── modelfile.py        # Construtor Modelfiles/Prompts
│       └── adapter/            # Provedores de inferência
│           ├── base.py
│           ├── remote_local.py
│           └── multimodal.py           # [+ V5] Adaptadores FLUX, SD, MusicGen, Sora
├── tests/                      # Pytest (hermético, offline)
│   ├── conftest.py             # Fixtures compartilhadas
│   ├── test_config.py
│   ├── test_model.py
│   ├── test_checkpointer.py
│   ├── test_worker_runner.py
│   ├── test_git_workspace.py
│   ├── test_scheduler.py
│   ├── test_healer.py
│   ├── test_handoff.py
│   ├── test_omniroute.py
│   ├── test_session.py
│   ├── test_memory.py
│   ├── test_discovery.py
│   ├── test_extension.py
│   ├── test_budget.py
│   ├── test_conflict.py
│   ├── test_packaging.py
│   ├── test_server.py
│   ├── test_cli.py
│   ├── test_security.py
│   ├── test_a11y.py
│   └── test_e2e.py
├── migrations/                 # Alembic (versionado)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── scripts/                    # Scripts auxiliares (singular!)
│   ├── dev-setup.sh            # Setup completo dev
│   ├── gen-openapi.sh          # Gera openapi.json + TS types
│   ├── db-migrate.sh           # Wrapper alembic
│   └── release.sh              # Version bump + tag
├── config.yaml                 # Configuração canônica (gitignored secrets)
├── config.yaml.example         # Template para novos usuários
├── pyproject.toml              # Hatch + deps + tool config
├── README.md                   # Visão geral + quickstart
├── LICENSE                     # MIT
├── .gitignore
├── .python-version             # 3.12
├── .node-version               # 20
└── .env.example                # Template variáveis de ambiente
```

---

## 5. Configurações de Tooling

### 5.1 pyproject.toml (Resumo das Seções Críticas)

```toml
[project]
name = "hydra-orch"
version = "0.1.0"
description = "Orquestrador de engenharia de software com execução verificável"
requires-python = ">=3.12"
dependencies = [
    # Core: typer, fastapi, uvicorn, pydantic, pydantic-settings, anyio
    # Data: sqlalchemy[asyncio], alembic, aiosqlite
    # Git: gitpython
    # System: psutil, tree-sitter, tree-sitter-python, tree-sitter-typescript, tree-sitter-rust, tree-sitter-go
    # HTTP: httpx, python-jose[cryptography], passlib[argon2]
    # Obs: structlog, prometheus-client
    # Config: pyyaml
]
optional-dependencies = {
    dev = ["pytest", "pytest-asyncio", "pytest-cov", "pytest-mock", "respx", "hypothesis", "ruff", "mypy", "pre-commit"],
    backend = ["slowapi", "scalar-fastapi", "arq", "redis", "prometheus-fastapi-instrumentator"],
    ui = ["jinja2", "markdown-it-py"],
    voice = ["faster-whisper", "sounddevice", "scipy", "webrtcvad"],
    computer_use = ["playwright", "pyautogui", "pillow"],
    rag = ["pypdf", "sqlite-vss"],
    local_llm = ["huggingface-hub", "llama-cpp-python"],
    trackers = ["jira", "python-gitlab"],
}

[tool.hatch.build.targets.wheel]
packages = ["src/hydra_orch"]

[tool.hatch.version]
source = "regex"
regex = '^__version__ = "(.+)"$'
path = "src/hydra_orch/__init__.py"

[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "PT", "PTH", "RUF", "SIM", "TID", "PYI"]
ignore = ["S101", "PTH118", "PTH120", "TRY003"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
disallow_untyped_defs = true
no_implicit_optional = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["unit", "integration", "e2e", "negative", "security", "a11y", "slow"]

[tool.coverage.run]
source = ["src/hydra_orch"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.alembic]
script_location = "migrations"
```

### 5.2 frontend/package.json (Scripts Essenciais)

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage",
    "lint": "eslint . --ext ts,tsx --max-warnings 0",
    "format": "prettier --write .",
    "typecheck": "tsc --noEmit",
    "gen:api": "hey-api openapi-ts -i http://localhost:8000/openapi.json -o src/types/api --client fetch --hooks react-query --schemas zod"
  }
}
```

### 5.3 GitHub Actions CI (`.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  backend:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: ${{ matrix.python }} }
      - name: Install deps
        run: pip install -e ".[dev,backend]"
      - name: Ruff
        run: ruff check src tests
      - name: MyPy
        run: mypy src/hydra_orch
      - name: Tests
        run: pytest -v --cov=src/hydra_orch --cov-fail-under=80
      - name: Upload coverage
        uses: codecov/codecov-action@v4
  
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm", cache-dependency-path: "frontend/package-lock.json" }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npm run typecheck
      - run: cd frontend && npm run test:coverage
      - run: cd frontend && npm run build
  
  docker:
    needs: [backend, frontend]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/gustavomot4/hydra-orch:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## 6. Convenções de Desenvolvimento

### 6.1 Python
- **Type hints obrigatórios** em toda API pública (`mypy --strict`)
- **Pydantic v2** para todos contratos (RunSpec, TaskSpec, eventos, API)
- **Async/await** em todo I/O (DB, HTTP, subprocess, Git)
- **Structured logging** via `structlog` (JSON, contextvars)
- **Zero `print()`** — usar `logger.info/debug/warning/error`
- **Testes no mesmo commit** da implementação (TDD leve)

### 6.2 TypeScript/React
- **Strict mode** no `tsconfig.json` (`noImplicitAny`, `strictNullChecks`)
- **Zod schemas** derivados do OpenAPI para forms + validação runtime
- **TanStack Query** para todo server state (cache, dedup, retry)
- **Zustand** apenas para UI state global (theme, sidebar, modals)
- **Radix UI** + Tailwind para componentes acessíveis por padrão
- **Monaco Editor** apenas no DiffView (lazy load)
- **Testes**: `vitest` + `testing-library` (unit + a11y)

### 6.3 Git & Commits
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- **Branch naming**: `feat/<id>-<slug>`, `fix/<id>-<slug>`
- **PR template**: Descrição, testes, breaking changes, screenshots (UI)
- **Merge**: Squash + rebase linear history

---

## 7. Versionamento & Release

| Evento | Ação |
|--------|------|
| **Patch** | Bugfix, docs, testes → `hatch version patch` → tag `v0.1.1` |
| **Minor** | Nova feature compatível → `hatch version minor` → tag `v0.2.0` |
| **Major** | Breaking change → `hatch version major` → tag `v1.0.0` |

**Release automation** (`.github/workflows/release.yml`):
1. Push tag `v*` → Build wheel + Docker image
2. Publica no PyPI + GHCR
3. Gera changelog via `git-cliff`
4. Cria GitHub Release com artifacts

---

## 8. GAPs Conhecidos

- GAP-STACK-01: Validar `tree-sitter` grammars para Rust/Go em Windows CI (binários)
- GAP-STACK-02: Confirmar `arq` (Redis queue) só necessário pós-V1 (background jobs)
- GAP-STACK-03: Definir estratégia de `pyi` stubs para `tree-sitter` grammars (typing)
- GAP-STACK-04: Avaliar `pydantic-extra-types` para validadores custom (path, url, secret)
- GAP-STACK-05: Configurar `pre-commit` hooks (ruff, mypy, pytest quick) no template

---

## 9. Referências Cruzadas

| Documento | Link |
|-----------|------|
| PRD Técnico | [`../b_spc/prd_tecnico.md`](../b_spc/prd_tecnico.md) |
| Infraestrutura | [`../i_infra/README.md`](../i_infra/README.md) |
| API OpenAPI | [`../f_api/openapi.yaml`](../f_api/openapi.yaml) |
| Testes | [`../h_test/README.md`](../h_test/README.md) |
| Manuais | [`../j_manual/README.md`](../j_manual/README.md) |

---

## 10. Glossary e Acrônimos

| Termo | Significado |
|-------|-------------|
| ASGI | Asynchronous Server Gateway Interface |
| AST | Abstract Syntax Tree |
| CI | Continuous Integration |
| CLI | Command Line Interface |
| ESM | ECMAScript Modules |
| HSR | Hot Module Replacement |
| LSP | Language Server Protocol |
| ORM | Object-Relational Mapping |
| PEP | Python Enhancement Proposal |
| RBAC | Role-Based Access Control |
| SSE | Server-Sent Events |
| TC | Type Checking |
| TUI | Text User Interface |
| WAL | Write-Ahead Logging |
| WCAG | Web Content Accessibility Guidelines |