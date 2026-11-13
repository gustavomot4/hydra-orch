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

### 3.2 Frontend (Interface Visual) — React 18 + TypeScript 5.5

> Reconciliado com [`../b_spc/ui_contratos.md`](../b_spc/ui_contratos.md) (DBC-9), [`../b_spc/a_ui/README.md`](../b_spc/a_ui/README.md), [`../b_spc/a_ui/d_figma.md`](../b_spc/a_ui/d_figma.md) e [`../a_context/taxonomia_file_system.md`](../a_context/taxonomia_file_system.md).

| Camada | Tecnologia | Versão (`package.json` / lock) | Finalidade |
|--------|------------|----------------------------------|------------|
| **Runtime** | Node.js | 20 LTS / 24.x (`v24.19.0`) | ES2023, fetch, WebSocket |
| **Build** | Vite | `^5.4.21` (`5.4.21`) | HMR, ESM, proxy `/v1` |
| **Framework** | React / React DOM | `^18.3.1` (`18.3.1`) | Concurrent, Suspense |
| **Language** | TypeScript | `~5.5.0` (`5.5.4`) | Strict mode (`noImplicitAny`, `strictNullChecks`) |
| **Routing** | React Router | `^6.26.0` (`6.30.6`) | Rotas Control Plane, deep links |
| **State/Server** | TanStack Query | `^5.51.0` (`5.107.1`) | Cache, dedup, `retry: false` em mutações e `401/403/404` |
| **Client State** | Zustand | `^4.5.0` (`4.5.7`) | Auth (`sessionStorage`), layout/tabs/split panes, sidebar (`localStorage`) |
| **SSE** | `eventsource-parser` | `^1.1.0` (`1.1.2`) | Parser streaming SSE, reconexão por `seq` |
| **UI Primitives** | Radix UI (`dialog`, `dropdown-menu`, `tabs`, `tooltip`) | `^1.1.x` / `^2.1.x` (`1.2.1`–`2.2.1`) | Acessível, unstyled, WCAG AA |
| **Styling** | Tailwind CSS | `^3.4.0` (`3.4.19`) | Utility-first, tokens Figma dark (`#141414`..`#303030`) |
| **Typography** | `@fontsource/inter` + `@fontsource/jetbrains-mono` | `^5.0.16` / `^5.0.18` (`5.3.0`) | `Inter` (UI) e `JetBrains Mono` (código/paths/terminais), empacotamento hermético offline |
| **Icons** | `lucide-react` | `^0.436.0` (`0.436.0`) | Ícones SVG tree-shakable, sem chrome macOS falso |
| **Terminal PTY** | `@xterm/xterm` + `@xterm/addon-fit` | `^5.5.0` / `^0.10.0` (`5.5.0` / `0.10.0`) | Terminal interativo PTY conectado na Onda 14 |
| **Schema Validation** | Zod | `^3.23.8` (`3.25.76`) | Validação runtime schema-first dos DTOs Control Plane |
| **Unit/Integration** | Vitest + Testing Library + `jsdom` | `^2.0.5` (`2.1.9`) / `^16.0.0` (`16.3.3`) | Unit, integração de shell, AuthGate e contratos |
| **E2E & A11y** | Playwright (`@playwright/test`) + `axe-core` | `^1.47.0` (`1.65.0`) / `^4.10.0` (`4.14.0`) | Testes E2E e auditoria WCAG 2.1 AA |
| **Lint/Format** | ESLint + Prettier | `^8.57.0` (`8.57.1`) / `^3.3.3` (`3.10.1`) | TypeScript-aware, React Hooks/Refresh, `--max-warnings 0` |
| **Diff/Patch (Onda 14)** | `diff2html` / Monaco (lazy) | Planejado M5 | Carregamento sob demanda em `src/feature/artifact/` e `conflict/` |

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
├── frontend/                   # React 18 + TS 5.5 + Vite 5.4 (regra estrita do singular)
│   ├── src/
│   │   ├── component/          # AppRail, AuthGate, CapabilityGate, PaneLayout, Sidebar, StatusBadge, TabBar, UsageBar, WorkspaceTree
│   │   ├── feature/            # Módulos Onda 14/15: artifact/, attachment/, auth/, chat/, composer/, conflict/, dictation/, quickopen/, quota/, shell/, terminal/
│   │   ├── hook/               # queryClient, useBootstrap, useCapabilities, useControlPlaneClient, useKeyboardShortcuts, useWorkspaceHierarchy
│   │   ├── page/               # NovoChatPage (18:8), ConfigPerfilPage (18:454), PlaceholderFeaturePage
│   │   ├── store/              # authStore (sessionStorage), layoutStore (tabs/split/sidebar)
│   │   ├── style/              # tokens.css (paleta Figma #141414..#303030, Inter, JetBrains Mono)
│   │   ├── type/               # DTOs Control Plane e schemas Zod
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── tests/                  # Vitest + Testing Library (+ Playwright E2E/axe-core)
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── .eslintrc.cjs
│   └── .prettierrc
├── src/
│   └── hydra_orch/             # Pacote Python (PEP 621)
│       ├── __init__.py         # __version__ = "0.1.0"
│       ├── cli.py              # Typer app
│       ├── server.py           # FastAPI app + lifespan
│       ├── config.py           # Pydantic Settings
│       ├── model.py            # Schemas Pydantic (contratos)
│       ├── core/               # Serviços de aplicação
│       │   ├── run_service.py
│       │   ├── session_service.py      # Sessões, threads e SSE replay
│       │   └── skill_registry.py       # Catálogo de skills e SecretRef
│       │
│       ├── engine/                     # Camada 2: Estratégias de Execução
│       │   ├── __init__.py
│       │   ├── decomposer.py           # Decompositor DAG (Wave 0 + Wave 1)
│       │   ├── contract.py             # Gerador de Fundação Compilável (Wave 0)
│       │   ├── swarm.py                # Execução paralela em worktrees (Wave 1)
│       │   ├── relay.py                # Handoff por Estado Git/Worktree
│       │   └── healer.py               # Auto-reparo limitado por orçamento
│       │
│       ├── bridge/                     # Camada 3: Transporte e Subprocessos
│       │   ├── __init__.py
│       │   ├── worker_runner.py        # Subprocessos de agentes CLI
│       │   ├── omniroute_client.py     # Cliente gateway opcional
│       │   ├── ssh_tunnel.py           # Gerenciador único de túnel SSH
│       │   ├── mcp_client.py           # Cliente protocolo MCP
│       │   └── cdp_fallback.py         # Fallback experimental via CDP
│       │
│       └── adapter/                    # Camada 4: Adaptadores de Inferência
│           ├── __init__.py
│           ├── base.py                 # Interface BaseAdapter
│           ├── api_gateway.py          # OpenRouter / DeepSeek REST SSE
│           ├── remote_local.py         # Ollama / vLLM local ou SSH
│           ├── ide_bridge.py           # Ponte experimental com IDEs
│           └── ui_cdp.py               # Automação experimental via CDP
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
├── migration/                  # Scripts de migração versionados (singular)
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
omit = ["*/tests/*", "*/migration/*"]

[tool.alembic]
script_location = "migrations"
```

### 5.2 frontend/package.json (Scripts Essenciais)

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "format": "prettier --write "src/**/*.{ts,tsx,css}" "tests/**/*.{ts,tsx}"",
    "typecheck": "tsc --noEmit"
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
      - run: cd frontend && npm run typecheck
      - run: cd frontend && npm run lint
      - run: cd frontend && npm test
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
- **Strict mode** no `tsconfig.json` (`noImplicitAny`, `strictNullChecks`) e alias `@/*` -> `./src/*`
- **Taxonomia estritamente no singular** sob `frontend/src/` (`component/`, `feature/`, `hook/`, `page/`, `store/`, `style/`, `type/`) conforme [`../a_context/taxonomia_file_system.md`](../a_context/taxonomia_file_system.md)
- **Tokens Figma dark & i18n PT-BR**: paleta `#141414` / `#181818` / `#1C1C1C` / `#202020` / `#282828` / `#303030` / `#E8E8E8` / `#969696`, `@fontsource/inter` + `@fontsource/jetbrains-mono` offline, ícones `lucide-react`, zero semáforos falsos de macOS
- **Zod schemas** para validação runtime dos contratos Control Plane; cota `unknown` permanece `—` (nunca `0%`)
- **TanStack Query** para leitura (`retry: false` em mutações e `401/403/404`) + **Zustand** apenas para auth (`sessionStorage`) e layout local (painéis, tabs, sidebar)
- **Radix UI** + Tailwind para componentes acessíveis por padrão; **Terminal PTY** via `@xterm/xterm` + `@xterm/addon-fit` (Onda 14)
- **Testes**: `vitest` + `@testing-library/react` (unit/shell) e `@playwright/test` + `axe-core` (E2E/WCAG 2.1 AA)

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
| Contratos UI (DBC-9) | [`../b_spc/ui_contratos.md`](../b_spc/ui_contratos.md) |
| Interface UI | [`../b_spc/a_ui/README.md`](../b_spc/a_ui/README.md) |
| Telas Figma UI | [`../b_spc/a_ui/d_figma.md`](../b_spc/a_ui/d_figma.md) |
| Taxonomia de Diretórios | [`../a_context/taxonomia_file_system.md`](../a_context/taxonomia_file_system.md) |
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