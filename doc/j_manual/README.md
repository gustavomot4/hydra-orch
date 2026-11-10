# j_manual — Manuais Operacionais e Guias de Usuário

**Identificador Formal:** `j_manual`
**Caminho Canônico:** `doc/j_manual/`
**Versão:** `v01_02_0000`
**Status:** `OPERACIONAL M1 + T09/T10 / SERVIÇOS T11–T28 PROPOSTOS`
**Autoridade:** Arquitetura do hydra-orch, complementando [`../b_spc/prd_funcional.md`](../b_spc/prd_funcional.md), [`../b_spc/prd_tecnico.md`](../b_spc/prd_tecnico.md), [`../b_spc/api_control_plane.md`](../b_spc/api_control_plane.md), [`../b_spc/entrega_operacao.md`](../b_spc/entrega_operacao.md) e [`../i_infra/README.md`](../i_infra/README.md).
**Escopo:** Manual operacional verificado do Marco M1 (V0) e referência para os horizontes de expansão (M2–M4 / V1–V4).

---

## 0. Manual Operacional M1 (Núcleo Verificável Local — Validado em T01–T08)

Esta seção documenta a superfície **100% implementada e validada** no Marco **M1 (Gate G-M1)**. As seções 1 a 11 mais abaixo preservam a visão completa do produto incluindo comandos propostos para as ondas de expansão (`T11–T28`); a segurança HTTP T09 está documentada na seção 0.4 e a migração T10 na seção 0.5.

### 0.1. Escopo Operacional M1 vs. Expansão (M2–M4)

| Superfície / Capacidade | Status no Marco M1 (`T01–T08`) | Horizonte de Expansão |
|---|---|---|
| Configuração canônica (`config.yaml`), aliases e runtime `.orchestrator/` | **Operacional** (`T01`) | Catálogo estendido em `T12` |
| Contratos tipados (`RunSpec`, `TaskSpec`, `TaskAttempt`, `TaskResult`, `ReviewDecision`, `Artifact`) | **Operacional** (`T02`) | Snapshots de perfil em `T13` |
| Persistência SQLite WAL (`ExecutionStore`), migração `0001_initial_core.sql`, idempotência e replay | **Operacional** (`T03`) | Migrações V2–V4 em `T10` |
| Runner de subprocessos (`WorkerRunner`), `cwd` real, env filtrado, tree kill e `dry_run` isolado | **Operacional** (`T04`) | Sandboxing de extensões em `T20` |
| Isolamento em Git worktree real (`GitWorkspaceService`), SHA base fixo, auditoria de escopo | **Operacional** (`T05`) | Reparo 3-way de conflito em `T27` |
| Checks determinísticos (`CheckRunner`) e serviço de aplicação/integração (`RunService`) | **Operacional** (`T06`) | Pausas HITL em `T26` |
| CLI M1 (`hydra submit`, `inspect`, `review`, `integrate`, `cancel`, `retry`, `serve`, `status`, `quota`) | **Operacional** (`T07`) | Subcomandos estendidos em `T23` |
| API Control Plane M1 (`/v1/control-plane/projects`, `/runs`, `/events`, `/review`, `/integrate`, `/discard`) | **Operacional** (`T07`) | Bearer/PBKDF2, CORS e redaction entregues em `T09` |
| Pipeline CI offline hermético multiplataforma (`.github/workflows/ci.yml`) | **Operacional** (`T08`) | CI estendido V4 em `T24` |

### 0.2. Instalação e Execução da Suíte Hermética M1

```bash
# 1. Instalar o pacote e dependências de desenvolvimento
python -m pip install -e ".[dev]"

# 2. Verificar superfície da CLI M1
hydra --help

# 3. Executar a suíte de testes offline hermética (zero rede / zero contas externas)
python -m pytest tests -q
```

### 0.3. Fluxo Operacional Completo na CLI M1 (`RunService`)

Todos os comandos da CLI M1 operam sobre a mesma camada transacional (`RunService` + `ExecutionStore` + `GitWorkspaceService`) que a API HTTP, suportando `--json` e `--output <arquivo>`:

```bash
# 1. Submeter (e opcionalmente executar tentativa em worktree real)
hydra submit \
  --repo-root /caminho/para/repositorio \
  --objective "Implementar validação X" \
  --task-id "run-01-t1" \
  --executor "codex" \
  --allowed-paths "src/**,tests/**" \
  --acceptance-cmd "python -m pytest tests/test_x.py -q" \
  --idempotency-key "idem-m1-operacao-0001" \
  --json

# Para validar o pipeline localmente sem invocar CLI externa paga (modo dry-run explícito):
hydra submit \
  --repo-root /caminho/para/repositorio \
  --objective "Validar pipeline M1 offline" \
  --allowed-paths "src/**" \
  --acceptance-cmd "python -c \"import pathlib, sys; sys.exit(0 if pathlib.Path('src/mod.py').exists() else 1)\"" \
  --execute --dry-run --fake-touch "src/mod.py=VALUE = 1\n" \
  --json

# 2. Inspecionar estado do run, tarefas, tentativas, artefatos e eventos
hydra inspect <run_id> --repo-root /caminho/para/repositorio --events --artifacts --json

# 3. Revisar resultado em ready_for_review (controle de concorrência otimista via --expected-revision)
hydra review <run_id> <task_id> \
  --repo-root /caminho/para/repositorio \
  --accept \
  --reason "Diff limpo e checks obrigatórios aprovados" \
  --expected-revision 1 \
  --json

# 4. Integrar resultados aceitos na branch dedicada integrate/<run_id>
#    (Resultados simulados de dry-run são bloqueados aqui por invariante de segurança)
hydra integrate <run_id> --repo-root /caminho/para/repositorio --json

# 5. Reexecutar tarefa rejeitada/falha ou cancelar run/tarefa
hydra retry <run_id> <task_id> --repo-root /caminho/para/repositorio --json
hydra cancel <run_id> --scope task --task-id <task_id> --reason "Cancelado pelo operador" --json
hydra cancel <run_id> --scope run --reason "Run abortado" --json
```

**Códigos de saída determinísticos da CLI M1:**
- `0`: Operação concluída com sucesso.
- `1`: Violação de contrato ou validação de domínio (ex.: escopo inválido, revisão proibida, tentativa de integrar resultado `simulated=True`).
- `2`: Erro de sistema/infraestrutura (ex.: falha de lock SQLite, corrupção de artefato, diretório Git inválido).
- `3`: Conflito de concorrência ou idempotência (`IdempotencyConflictError`, `OptimisticLockError`, `InvalidTransitionError`).

### 0.4. Operação via API REST e SSE (`/v1/control-plane/*`)

Iniciar o servidor local (bind padrão `127.0.0.1:8000`):
```bash
# T09: configure o hash antes de iniciar. A credencial é lida sem eco no terminal.
# Gere previamente um token aleatório (ex.: secrets.token_urlsafe(32)) e guarde-o
# no gerenciador de segredos usado pelos clientes.
export HYDRA_API_TOKEN_HASH="$(python -c 'from getpass import getpass; from hydra_orch.core.auth import TokenVerifier; print(TokenVerifier.from_token(getpass("Token: ")).encode())')"
hydra serve --host 127.0.0.1 --port 8000
```

Todas as requisições HTTP exigem `Authorization: Bearer <token>`, inclusive health,
inferência e SSE. A CLI local de execução continua chamando o serviço diretamente.
Também é possível fornecer `HYDRA_API_TOKEN` por ambiente externo; não configure
as duas variáveis simultaneamente. O servidor mantém apenas o hash derivado.
Para rotacionar o token, substitua o hash e reinicie. Nunca versione a credencial.

Para personalizar as origens do cliente web, configure antes de iniciar:
`HYDRA_CORS_ALLOW_ORIGINS='["http://localhost:3000"]'`. Apenas origens HTTP(S)
loopback explícitas são aceitas. Clientes sem Origin exigem Bearer normalmente;
preflight CORS válido não entrega dados e dispensa token. Veja o contrato
[S16](../b_spc/seguranca_proveniencia.md) para regras de redaction e limites.

Principais endpoints ativos no Marco M1:
- `GET /v1/control-plane/bootstrap` — Estado de configuração, banco SQLite, diretórios `.orchestrator/` e gateway.
- `POST /v1/control-plane/projects` e `GET /v1/control-plane/projects` — Registro e listagem de raízes Git válidas.
- `POST /v1/control-plane/runs` — Submissão idempotente de run (suporta cabeçalho `Idempotency-Key`).
- `GET /v1/control-plane/runs`, `GET /v1/control-plane/runs/{run_id}`, `GET /v1/control-plane/runs/{run_id}/tasks`, `GET /v1/control-plane/runs/{run_id}/artifacts` — Consultas de estado e evidências.
- `GET /v1/control-plane/runs/{run_id}/events` — Stream SSE ordenado por `seq` monotônico com suporte a `Last-Event-ID` (`410 Gone` quando o cursor expirou) e `event: heartbeat`.
- `POST /v1/control-plane/runs/{run_id}/tasks/{task_id}/review` — Decisão de revisão (`accepted` | `rejected`) com `expected_revision`.
- `POST /v1/control-plane/runs/{run_id}/integrate` — Merge serializado na branch dedicada `integrate/<run_id>` com reexecução dos checks combinados.
- `POST /v1/control-plane/runs/{run_id}/cancel` e `POST /v1/control-plane/runs/{run_id}/tasks/{task_id}/retry` — Cancelamento (`scope="run"` ou `scope="task"`) e nova tentativa.
- `POST /v1/control-plane/runs/{run_id}/discard` — Limpeza de worktrees efêmeras após término do run, preservando e verificando o hash `SHA-256` de todos os artefatos retidos no SQLite.


### 0.5. Migrações do control plane (T10)

A inicialização aplica `0002_control_plane.sql`, preservando o núcleo 0001 e o
streaming. O schema cria a base das próximas entregas, sem ativar os serviços.
Antes dos scripts de domínio, o migrador grava backup SQLite com WAL em
`.orchestrator/migration_backup/` e registra checksums e resultados em
`migration_history`. Backups contêm dados locais: proteja-os e não os versione.

Downgrade para 0001 é uma operação explícita com o serviço parado:
`await store.rollback_migrations("0001")`. Ela exige que a expansão esteja vazia
e recusa tentativas ativas ou perda de dados novos. Não há descarte forçado.
Um novo store inicializado pelo checkout atual reaplica 0002; use código
compatível para operar na versão antiga. Contrato e limites em
[S14](../b_spc/workspaces_perfis.md).


### Sessões e acompanhamento de eventos (T14)

A API autenticada expõe sessões e threads sob `/v1/control-plane/runs/{run_id}/sessions`.
Transições exigem expected_state; mensagens exigem expected_last_seq e
Idempotency-Key. IDs de outra run/sessão são recusados. Esses estados representam
conversas; cancelamento de processos continua pelos comandos de RunService.

`GET /v1/control-plane/runs/{run_id}/events` aceita session_id/thread_id, limite de
até 1000 eventos e Last-Event-ID. O padrão é replay finito; `follow=true` acompanha
novos eventos com heartbeat de 15 s e encerra na desconexão. O consumidor deve
salvar o cursor e deduplicar; existe o helper Python EventCursor. Contrato em
[S15](../b_spc/sessoes_observabilidade.md).

---

Este diretório concentra os manuais operacionais do **hydra-orch** para usuários, operadores e administradores.

## Índice de Manuais

| Manual | Arquivo | Público | Descrição |
|--------|---------|---------|-----------|
| **Instalação e Início Rápido** | `installation.md` | Todos | Instalação, dependências, primeiro run |
| **Configuração** | `configuration.md` | Operadores | `config.yaml`, variáveis de ambiente, perfis |
| **Autenticação e Provedores** | `authentication.md` | Operadores | CLI auth, OmniRoute, OAuth, tokens locais |
| **SSH e Nós Remotos** | `ssh_remote.md` | Operadores | Túneis reversos, GPU remota, certificação |
| **Operação CLI** | `cli_operations.md` | Desenvolvedores | Comandos `hydra` para runs, reviews, cancelamento |
| **Operação UI** | `ui_operations.md` | Desenvolvedores | Interface visual: dashboard, diffs, aprovações |
| **Modos de Orquestração** | `orchestration_modes.md` | Arquitetos | Swarm, Relay, Persistente — quando usar cada um |
| **Runbooks de Manutenção** | `maintenance_runbooks.md` | Admins | Backup, migração, limpeza, healthchecks |
| **Recuperação de Desastres** | `disaster_recovery.md` | Admins | Crash, órfãos, disco cheio, banco corrompido |
| **Auditoria e Conformidade** | `audit_compliance.md` | Segurança | Logs, redactor, exportação, retenção |
| **Acessibilidade** | `accessibility.md` | Todos | Teclado, leitores de tela, contraste, redução movimento |

---

## 1. Instalação e Início Rápido (`installation.md`)

### 1.1 Pré-requisitos
- **Python ≥ 3.10** (recomendado 3.12)
- **Git ≥ 2.30** (worktrees)
- **SQLite 3.35+** (WAL mode)
- **tree-sitter CLI** (code stitching): `cargo install tree-sitter-cli` ou binário
- **Opcional:** `autossh` (túneis SSH robustos), `docker` (contêineres)

### 1.2 Instalação via Pip (Recomendado)
```bash
# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Instalar hydra-orch em modo desenvolvimento
pip install -e .

# Ou instalar de PyPI (quando publicado)
pip install hydra-orch
```

### 1.3 Verificação da Instalação
```bash
# Verificar versão e comandos
hydra --version
hydra --help

# Verificar dependências críticas
hydra doctor
# Saída esperada:
# ✓ Python 3.12.0
# ✓ Git 2.43.0 (worktrees supported)
# ✓ SQLite 3.45.0 (WAL mode)
# ✓ tree-sitter 0.22.0
# ✓ Configuração válida: config.yaml
# ✓ Banco acessível: .orchestrator/checkpoints.sqlite
```

### 1.4 Primeiro Run (Hello World)
```bash
# 1. Inicializar projeto em repo existente
cd /caminho/para/meu/projeto
hydra project init --name "meu-projeto"

# 2. Configurar executor (ex.: Claude Code)
hydra config set executor claude_code
hydra config set model claude-3-5-sonnet

# 3. Submeter tarefa simples
hydra run submit \
  --objective "Corrigir teste falhando em tests/test_math.py" \
  --acceptance "pytest tests/test_math.py -xvs" \
  --allowed-paths "tests/test_math.py" \
  --mode swarm

# 4. Acompanhar progresso
hydra run watch <run_id>

# 5. Revisar e integrar
hydra run review <run_id> --accept
hydra run integrate <run_id>
```

---

## 2. Configuração (`configuration.md`)

### 2.1 Arquivo `config.yaml` (Localização)
| Ambiente | Caminho |
|----------|---------|
| Desenvolvimento | `./config.yaml` (raiz do projeto) |
| Produção | `/etc/hydra-orch/config.yaml` ou `$HYDRA_CONFIG_PATH` |
| Usuário | `~/.config/hydra-orch/config.yaml` |

**Precedência:** CLI args > Variáveis de ambiente > `config.yaml` projeto > `config.yaml` usuário > Defaults.

### 2.2 Estrutura Principal
```yaml
# config.yaml - Exemplo completo
server:
  bind_host: "127.0.0.1"
  bind_port: 8000
  cors_allow_origins:
    - "http://localhost:3000"
    - "tauri://localhost"
  auth:
    enabled: true
    token_expiry_hours: 24
    algorithm: "HS256"
    secret_ref: "env:HYDRA_JWT_SECRET"

omniroute:
  enabled: true
  connection_mode: "optional"  # disabled | optional | required
  base_url: "http://127.0.0.1:20128"
  timeout_sec: 10
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout_sec: 60
  fallback_chain:
    - provider: "claude_pro"
      model: "claude-3-5-sonnet"
    - provider: "chatgpt_plus"
      model: "gpt-4o"
    - provider: "local_ollama"
      model: "llama3.1"

execution:
  default_executor: "claude_code"
  default_model: "claude-3-5-sonnet"
  default_mode: "swarm"  # swarm | relay | persist
  max_parallel_worktrees: 3
  sandbox:
    enabled: false
    memory_max_mb: 2048
    cpu_quota_pct: 100
    pids_max: 256
    network_allowlist: []
  require_certified: false  # true = bloqueia drivers não certificados em produção

ssh_tunnel:
  enabled: false
  remote_host: ""
  remote_user: ""
  remote_port: 22
  local_port: 11435
  target_port: 11434
  identity_file: "~/.ssh/hydra_gpu_ed25519"
  known_hosts_file: "~/.ssh/known_hosts"
  healthcheck_interval_sec: 30
  reconnect_backoff_max_sec: 60

database:
  path: ".orchestrator/checkpoints.sqlite"
  wal_mode: true
  busy_timeout_ms: 5000
  foreign_keys: true

retention:
  artifacts_days: 30
  events_days: 90
  worktrees_days: 7
  orphans_days: 14

redaction:
  patterns:
    - "sk-[a-zA-Z0-9]{32,}"
    - "ghp_[a-zA-Z0-9]{36}"
    - "glpat-[a-zA-Z0-9]{20}"
    - "xoxb-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}"
    - "Bearer\\s+[a-zA-Z0-9._-]{20,}"
    - "-----BEGIN\\s+.*\\s+PRIVATE\\s+KEY-----"
    - "password\\s*=\\s*[^\\s]{8,}"
    - "secret\\s*=\\s*[^\\s]{8,}"
    - "api_key\\s*=\\s*[^\\s]{8,}"
  entropy_threshold: 4.5  # bits/char para detectar segredos genéricos

logging:
  level: "INFO"
  format: "json"
  output: "stdout"
  redact: true
```

### 2.3 Variáveis de Ambiente
| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `HYDRA_CONFIG_PATH` | Caminho customizado para `config.yaml` | `/etc/hydra/config.yaml` |
| `HYDRA_JWT_SECRET` | Segredo para tokens JWT (obrigatório em prod) | `base64:...` |
| `LLM_PROVIDER` | Provedor padrão para inferência | `omniroute` |
| `LLM_MODEL` | Modelo padrão | `claude-3-5-sonnet` |
| `LLM_API_KEY` | Chave API (se provedor direto) | `sk-...` |
| `HYDRA_LOG_LEVEL` | Nível de log | `DEBUG` |

---

## 3. Autenticação e Provedores (`authentication.md`)

### 3.1 Tokens Locais (Control Plane)
```bash
# Gerar token para usuário/serviço
hydra token create \
  --principal "dev-user" \
  --scopes "run:read,run:write,project:admin" \
  --expires-in 24h

# Saída: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
# Usar em requisições:
curl -H "Authorization: Bearer <token>" http://localhost:8000/v1/control-plane/runs
```

### 3.2 Autenticação CLI (Claude Code, Codex, etc.)
```bash
# Claude Code (assinatura Pro/Free)
claude auth login
# Verificar:
claude auth status

# Codex (ChatGPT Plus/Free)
codex auth login

# Gemini CLI
gemini auth login

# Verificar disponibilidade no Hydra
hydra doctor --check-executors
```

### 3.3 OmniRoute Gateway (Opcional)
```bash
# Instalar OmniRoute (Docker)
docker run -d \
  -p 20128:20128 \
  -v ~/.omniroute:/root/.omniroute \
  ghcr.io/omniroute/omniroute:latest

# Configurar contas no OmniRoute UI (http://localhost:20128)
# Ou via CLI:
omniroute account add claude_pro
omniroute account add chatgpt_plus

# Testar quota
curl http://localhost:20128/v1/quota
```

### 3.4 Escopos de Permissão (RBAC)
| Escopo | Descrição | Rotas |
|--------|-----------|-------|
| `run:read` | Consultar runs, tasks, artifacts | GET /runs, GET /runs/{id}/events |
| `run:write` | Submeter, cancelar, retry runs | POST /runs, POST /runs/{id}/cancel |
| `run:review` | Aceitar/rejeitar resultados | POST /runs/{id}/tasks/{task_id}/review |
| `run:integrate` | Integrar resultados aceitos | POST /runs/{id}/integrate |
| `project:admin` | Gerenciar projetos, repositórios | POST/GET /projects, /repositories |
| `memory:write` | Gravar memória adaptativa | POST /memory |
| `extension:install` | Instalar extensões | POST /extensions/install |
| `admin:all` | Todos os escopos acima | * |

---

## 4. SSH e Nós Remotos (`ssh_remote.md`)

### 4.1 Configuração de Chave SSH
```bash
# Gerar chave Ed25519 dedicada para Hydra
ssh-keygen -t ed25519 -f ~/.ssh/hydra_gpu_ed25519 -C "hydra-gpu-tunnel"

# Copiar para servidor remoto
ssh-copy-id -i ~/.ssh/hydra_gpu_ed25519.pub user@gpu.casa.example

# Testar conexão
ssh -i ~/.ssh/hydra_gpu_ed25519 user@gpu.casa.example "ollama list"
```

### 4.2 Configuração do Túnel Reverso
```yaml
# config.yaml
ssh_tunnel:
  enabled: true
  remote_host: "gpu.casa.example"
  remote_user: "hydra"
  remote_port: 22
  local_port: 11435
  target_port: 11434
  identity_file: "~/.ssh/hydra_gpu_ed25519"
  known_hosts_file: "~/.ssh/known_hosts"
```

### 4.3 Inicialização Manual (para debug)
```bash
# Túnel reverso: expõe Ollama remoto (11434) no local (11435)
ssh -R 11435:localhost:11434 \
  -i ~/.ssh/hydra_gpu_ed25519 \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=~/.ssh/known_hosts \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N user@gpu.casa.example

# Com autossh (reconexão automática)
autossh -M 0 \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -R 11435:localhost:11434 \
  -i ~/.ssh/hydra_gpu_ed25519 \
  user@gpu.casa.example
```

### 4.4 Healthcheck e Certificação
```bash
# Verificar saúde do túnel
hydra transport health ssh-gpu

# Saída esperada:
# Transport: ssh-gpu (ssh)
# Target: gpu.casa.example:22
# Status: healthy
# Last check: 2026-11-06T10:30:00Z
# Host key: SHA256:abc123... (match)
# Latency: 12ms

# Se host key mudou → ERRO:
# Status: unreachable
# Error: Host key verification failed (expected SHA256:abc123, got SHA256:xyz789)
# Ação: Atualizar known_hosts ou investigar MITM
```

### 4.5 Uso em Runs
```bash
# Perfil com executor remoto via SSH
hydra profile create \
  --name "remote-gpu" \
  --agent claude_code \
  --model claude-3-5-sonnet \
  --executor ssh_cli \
  --orchestration-mode swarm

# Submeter run usando perfil remoto
hydra run submit \
  --profile remote-gpu \
  --objective "Treinar modelo no GPU remoto" \
  --acceptance "python train.py --eval"
```

---

## 5. Operação CLI (`cli_operations.md`)

### 5.1 Comandos Principais

#### Projetos
```bash
# Cadastrar projeto
hydra project create --name "meu-projeto" --root /caminho/repo --base-branch main

# Listar projetos
hydra project list --json

# Mostrar detalhes
hydra project show <project_id>
```

#### Runs
```bash
# Submeter run (modo swarm padrão)
hydra run submit \
  --project <project_id> \
  --objective "Implementar feature X" \
  --acceptance "pytest tests/ -xvs" \
  --allowed-paths "src/feature_x/**" \
  --mode swarm \
  --budget-max-usd 5.00 \
  --idempotency-key $(uuidgen)

# Listar runs
hydra run list --project <project_id> --status running

# Ver detalhes
hydra run show <run_id> --json

# Acompanhar tempo real (SSE)
hydra run watch <run_id>

# Cancelar
hydra run cancel <run_id> --scope run
hydra run cancel <run_id> --scope task --task-id <task_id>
```

#### Revisão e Integração
```bash
# Ver resultado de task
hydra task result <run_id> <task_id> --attempt 1

# Revisar (aceitar)
hydra run review <run_id> <task_id> \
  --accept \
  --reason "Todos checks passaram, implementação correta" \
  --expected-revision 1

# Revisar (rejeitar)
hydra run review <run_id> <task_id> \
  --reject \
  --reason "Check de integração falhou" \
  --expected-revision 1

# Nova tentativa (reparo)
hydra run retry <run_id> <task_id>

# Integrar
hydra run integrate <run_id> --force false
```

#### Perfis e Agentes
```bash
# Listar agentes disponíveis
hydra agent list

# Criar perfil
hydra profile create \
  --name "backend-claude" \
  --agent claude_code \
  --model claude-3-5-sonnet \
  --executor cli \
  --mode swarm \
  --skills "skill_lint_python,skill_test_pytest"

# Validar perfil (pré-execução)
hydra profile resolve <profile_id>

# Listar perfis
hydra profile list
```

#### Métricas e Observabilidade
```bash
# Métricas de uma run
hydra run metrics <run_id>

# Decisões de rota
hydra run route-decisions <run_id>

# Exportar evidência completa
hydra run export <run_id> --output ./run_evidence.zip --redact
```

### 5.2 Flags Globais
| Flag | Descrição |
|------|-----------|
| `--json` | Saída JSON estruturada (para scripts) |
| `--output <file>` | Salvar saída em arquivo |
| `--config <path>` | Configuração customizada |
| `--verbose` / `-v` | Log nível DEBUG |
| `--no-color` | Desabilitar cores (CI/redirecionamento) |

### 5.3 Códigos de Saída
| Código | Significado |
|--------|-------------|
| 0 | Sucesso |
| 1 | Erro de validação/negócio (ex.: revisão vencida) |
| 2 | Erro de sistema (ex.: banco indisponível, CLI ausente) |
| 3 | Conflito de idempotência (chave reutilizada com payload diferente) |

---

## 6. Operação UI (`ui_operations.md`)

### 6.1 Acesso à Interface
```bash
# Iniciar servidor com UI
hydra serve --with-ui

# Acessar: http://localhost:8000/ui
# Autenticação: token local (Bearer) ou login via página
```

### 6.2 Telas Principais

#### Dashboard de Projetos
- Lista de projetos com status do último run
- Ações rápidas: nova run, ver histórico, configurar

#### Detalhes da Run
- **Visão Geral:** Objetivo, modo, status, orçamento, duração
- **Tarefas:** DAG visual com status por task (pendente, rodando, revisão, aceito, falhou)
- **Worktrees:** Links para diffs, arquivos modificados, checks
- **Eventos:** Timeline SSE com replay (filtro por tipo)
- **Métricas:** Fila, duração, tokens, custo com proveniência (observed/stale/unknown)

#### Revisão de Diff
- Visualizador side-by-side (base ↔ trabalho)
- Navegação por arquivo
- Checks inline (passou/falhou com output)
- Botões: **Aceitar** (requer expected_revision), **Rejeitar**, **Solicitar Reparo**

#### Integração
- Branch de integração (`integrate/<run_id>`)
- Status de merge (sucesso/conflito)
- Checks combinados
- Conflito: visualizador 3-way + opções (auto-repair, manual, descartar)

#### Configurações
- Projetos, repositórios, áreas
- Perfis de execução
- Agentes/executores certificados
- Tokens, consentimentos, descobertas

### 6.3 Acessibilidade (WCAG AA)
- **Teclado:** Tab order lógico, Enter/Space ativam, Escape fecha modais
- **Foco:** Outline visível (3px, cor contrastante)
- **Roles:** `button`, `dialog`, `tablist`, `tree`, `alert` semânticos
- **Estados textuais:** `aria-live="polite"` para notificações; loading, erro, sucesso em texto
- **Contraste:** Mínimo 4.5:1 (texto), 3:1 (UI components)
- **Redução de movimento:** Respeita `prefers-reduced-motion`; animações desabilitadas
- **Leitores de tela:** Labels em todos inputs; descrições em diffs complexos

---

## 7. Modos de Orquestração (`orchestration_modes.md`)

### 7.1 Comparação Rápida

| Característica | Swarm | Relay | Persistente |
|----------------|-------|-------|-------------|
| **Paralelismo** | ✅ Múltiplas tasks simultâneas | ❌ Sequencial | ❌ Sequencial |
| **Handoff entre provedores** | ❌ | ✅ Checkpoint estruturado | ❌ |
| **Pausa por janela de cota** | ❌ | ❌ | ✅ Auto-resume |
| **Ideal para** | Features independentes, refatoração paralela | Contextos longos, múltiplos modelos | Janelas de cota conhecidas (Claude Pro 5h) |
| **Overhead** | Worktrees múltiplas | Checkpoint + stitching | Timer + monitoramento |

### 7.2 Swarm (Paralelo com Worktrees)
```bash
hydra run submit --mode swarm \
  --task-spec '{
    "tasks": [
      {"id": "t1", "objective": "Backend API", "dependencies": []},
      {"id": "t2", "objective": "Frontend UI", "dependencies": ["t1"]},
      {"id": "t3", "objective": "Testes E2E", "dependencies": ["t1", "t2"]}
    ]
  }'
```
- Scheduler valida DAG (Kahn), despacha tasks `ready` até `max_parallel_worktrees`
- Cada task em worktree isolada
- Integração serializada por ordem topológica
- Auto-healing: check falha → reparo (teto `max_repair_attempts`)

### 7.3 Relay (Handoff entre Provedores)
```bash
hydra run submit --mode relay \
  --profile "relay-claude-to-codex" \
  --fallback-chain "claude_pro,codex,local_ollama"
```
- Executor primário roda até limite (cota, contexto, erro)
- `HandoffCheckpoint`: instruções, SHA/diff, tools executadas, próximo passo
- `tree-sitter` identifica âncora sintática no corte
- Provedor fallback continua do mesmo ponto
- `RouteDecision` auditável: candidatos, motivo, fallback chain

### 7.4 Persistente (Auto-Resume por Janela)
```bash
hydra run submit --mode persist \
  --budget-window-reset "2026-11-06T18:00:00Z" \
  --budget-max-usd 10.00
```
- Monitora quota via OmniRoute ou heurística (janela 5h)
- Ao atingir limite: run → `waiting` (causa `rate_limit_window`, limite `window_reset_at`)
- Timer aguarda reabertura → retoma **mesmo** `TaskAttempt` (não nova tentativa)
- Zero tokens gastos na espera
- Operador notificado: pausa + retomada automática

### 7.5 Seleção do Modo
| Cenário | Modo Recomendado |
|---------|------------------|
| Feature com múltiplos arquivos independentes | Swarm |
| Refatoração grande que excede contexto de 1 modelo | Relay |
| Tarefa longa com Claude Pro (janela 5h) | Persistente |
| Prototipação rápida, 1 arquivo | Swarm (1 task) |
| Debug iterativo com feedback humano | Persistente + HITL |

---

## 8. Runbooks de Manutenção (`maintenance_runbooks.md`)

### 8.1 Backup Diário (Cron)
```bash
#!/bin/bash
# /etc/cron.daily/hydra-backup
set -euo pipefail

BACKUP_DIR="/var/backups/hydra-orch"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="/opt/hydra-orch/.orchestrator/checkpoints.sqlite"

mkdir -p "$BACKUP_DIR"

# Backup do banco (com WAL, usa .backup do sqlite3)
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/checkpoints_$DATE.sqlite'"

# Backup de configs
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" /etc/hydra-orch/config.yaml

# Retenção: 30 dias
find "$BACKUP_DIR" -name "*.sqlite" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

# Verificar integridade
sqlite3 "$BACKUP_DIR/checkpoints_$DATE.sqlite" "PRAGMA integrity_check;" | grep -q "ok" || {
  echo "ERRO: Backup corrompido!" | logger -t hydra-backup
  exit 1
}
```

### 8.2 Migração de Banco
```bash
# Aplicar migrações (versão atual → target)
hydra db migrate --target v01_02_0000

# Verificar status
hydra db status

# Rollback (se necessário)
hydra db rollback --steps 1

# Backup antes de migração (obrigatório em prod)
hydra db backup --output /tmp/pre_migration_$(date +%s).sqlite
```

### 8.3 Limpeza de Worktrees e Artefatos
```bash
# Limpeza automática (retention policy)
hydra cleanup --dry-run  # Ver o que seria removido
hydra cleanup --execute  # Executar limpeza

# Critérios (config.yaml retention):
# - worktrees: > 7 dias sem run ativo
# - artifacts: > 30 dias
# - events: > 90 dias
# - orphans: > 14 dias
```

### 8.4 Healthchecks Operacionais
```bash
# Verificação completa
hydra doctor --full

# Saída:
# ✓ API respondendo (localhost:8000/health)
# ✓ Banco íntegro (PRAGMA integrity_check = ok)
# ✓ Disco: 45GB livre (mín 1GB)
# ✓ SQLite WAL ativo
# ✓ OmniRoute: healthy (quota observed)
# ✓ SSH Tunnel: healthy (host key match)
# ✓ Worktrees: 3 ativas, 0 órfãs
# ✓ Processos: 0 órfãos
# ✓ Redaction: 0 segredos vazados nos últimos 1000 eventos
```

### 8.5 Rotação de Segredos
```bash
# Rotacionar JWT secret (requer restart)
# 1. Gerar novo secret
openssl rand -base64 32

# 2. Atualizar config.yaml / variável de ambiente
# 3. Revogar tokens antigos
hydra token revoke --all --before $(date -d '1 hour ago' -Iseconds)

# 4. Reiniciar servidor
systemctl restart hydra-orch
```

---

## 9. Recuperação de Desastres (`disaster_recovery.md`)

### 9.1 Cenários e Procedimentos

#### Crash do Servidor Durante Execução
```bash
# 1. Reiniciar servidor
systemctl restart hydra-orch

# 2. Verificar runs ativas
hydra run list --status running

# 3. Reconciliação automática ocorre no startup:
#    - Eventos órfãos detectados
#    - Worktrees órfãs → .orchestrator/orphans/
#    - Tentativas sem fim → status 'crashed' + evento

# 4. Para cada run 'crashed':
hydra run show <run_id> --json
# Verificar última tentativa, trabalho parcial preservado
# Decidir: retry, cancel, ou nova run reaproveitando diffs
```

#### Banco de Dados Corrompido
```bash
# 1. Parar servidor
systemctl stop hydra-orch

# 2. Restaurar backup mais recente
cp /var/backups/hydra-orch/checkpoints_20261105_030000.sqlite \
   /opt/hydra-orch/.orchestrator/checkpoints.sqlite

# 3. Verificar integridade
sqlite3 /opt/hydra-orch/.orchestrator/checkpoints.sqlite "PRAGMA integrity_check;"

# 4. Iniciar servidor
systemctl start hydra-orch

# 5. Validar runs recentes
hydra run list --since 2026-11-05
```

#### Disco Cheio (`.orchestrator/`)
```bash
# 1. Identificar ocupação
du -sh /opt/hydra-orch/.orchestrator/*

# 2. Limpeza de emergência (preserva runs ativas)
hydra cleanup --execute --preserve-active

# 3. Se ainda cheio: mover artifacts antigos para storage frio
mkdir -mnt /mnt/cold_storage/hydra_artifacts
mv /opt/hydra-orch/.orchestrator/run/2026-10/* /mnt/cold_storage/hydra_artifacts/

# 4. Atualizar config.yaml se path mudou
# database.path permanece; artifacts são por run_id
```

#### Worktree Corrompida / Git Lock
```bash
# 1. Detectar worktrees problemáticas
git -C /opt/hydra-orch/.orchestrator/worktree/worktree_abc123 status

# 2. Limpar locks órfãos
git -C /opt/hydra-orch/.orchestrator/worktree/worktree_abc123 worktree prune --expire=0

# 3. Se worktree irrecuperável:
#    - Mover para orphans
#    - Marcar tentativa como 'crashed' no banco
#    - Nova run com retry
```

#### Perda de Conectividade OmniRoute
```bash
# Modo direto automático se connection_mode=optional
# Verificar:
hydra doctor --check-omniroute

# Se required e OmniRoute down:
# - Runs em espera (waiting) até recovery
# - Circuit breaker abre após 5 falhas
# - Recovery timeout: 60s (configurável)
```

### 9.2 Checklist de Recuperação Pós-Incidente
- [ ] Servidor reiniciado e saudável (`hydra doctor --full`)
- [ ] Runs ativas reconciliadas (nenhuma 'running' órfã)
- [ ] Banco íntegro (`PRAGMA integrity_check = ok`)
- [ ] Worktrees limpas (0 órfãs)
- [ ] Backups validados (restore testado)
- [ ] Logs de auditoria completos (sem gaps)
- [ ] Stakeholders notificados (se run de produção afetada)

---

## 10. Auditoria e Conformidade (`audit_compliance.md`)

### 10.1 Logs de Auditoria
| Evento | Local | Retenção |
|--------|-------|----------|
| Comandos CLI/API | `events` table + `COMMAND` table | 90 dias |
| Decisões de review | `REVIEW` table | Permanente |
| Integrações | `INTEGRATION` + `INTEGRATION_ITEM` | Permanente |
| Consentimentos | `CONSENT_RECORD` | Permanente |
| Aprovações discovery | `DISCOVERED_RESOURCE` | Permanente |
| Instalações extensão | `EXTENSION_INSTALL` | Permanente |
| Rotas (RouteDecision) | `ROUTE_DECISION` | 90 dias |
| Orçamento (alertas/congelamento) | `BUDGET_POLICY` + events | 90 dias |

### 10.2 Exportação para Auditoria
```bash
# Dossiê completo de uma run (redigido)
hydra run export <run_id> \
  --output ./audit_run_<run_id>.zip \
  --format json \
  --include-events \
  --include-artifacts \
  --redact

# Conteúdo do ZIP:
# - run_spec.json (RunSpec completo)
# - tasks.json (todas tasks + specs)
# - attempts.json (todas tentativas + resultados)
# - events.jsonl (eventos monotônicos redigidos)
# - artifacts/ (patches, check outputs, handoff checkpoints)
# - reviews.json (decisões com expected_revision)
# - integration.json (merge + checks combinados)
# - metrics.json (amostras com proveniência)
# - route_decisions.json (trilha auditável)
# - budget_events.json (alertas, congelamento, extensões)
# - manifest.json (hashes SHA-256 de todos arquivos)
```

### 10.3 Redaction (Sanitização)
- Aplicado **antes** de: escrita no banco, SSE, logs, exportação
- Padrões: `config.yaml → redaction.patterns` + entropia (>4.5 bits/char)
- Teste: `hydra test redactor --corpus ./test_secrets_corpus.txt`
- **Nunca** logar/exportar: tokens, chaves SSH, senhas, OAuth secrets, PII

### 10.4 Retenção e Exclusão
| Dado | Retenção | Exclusão |
|------|----------|----------|
| Runs concluídas (succeeded/failed/cancelled) | 90 dias | `hydra cleanup` |
| Runs com integração aprovada | 1 ano | Manual |
| Artefatos (patches, logs) | 30 dias | `hydra cleanup` |
| Eventos SSE | 90 dias | `hydra cleanup` |
| Worktrees | 7 dias pós-run | `hydra cleanup` |
| Órfãos (reconciliação) | 14 dias | `hydra cleanup` |
| Consentimentos, aprovações, extensões | Permanente | Revogação explícita |
| Exportações de auditoria | Conforme política da org | Manual |

### 10.5 Conformidade LGPD/GDPR
- **Direito ao esquecimento:** `hydra memory revoke <memory_id>` + `hydra consent revoke <consent_id>`
- **Portabilidade:** `hydra run export` + `hydra memory query --scope user --scope-id <user_id>`
- **Minimização:** Só coleta dados necessários para execução; `unknown` nunca virado em zero
- **Segurança:** Tokens hasheados (PBKDF2/Argon2), CORS estrito, redaction obrigatória

---

## 11. Acessibilidade (`accessibility.md`)

### 11.1 Compromisso WCAG 2.1 AA
O hydra-orch UI é projetado para ser acessível por padrão.

### 11.2 Checklist Implementado

#### Navegação por Teclado
- [x] Tab order lógico em todas as telas
- [x] Enter/Space ativam botões/links
- [x] Escape fecha modais/dropdowns
- [x] Setas navegam árvores (DAG, threads, arquivos)
- [x] Skip links para conteúdo principal

#### Foco Visível
- [x] Outline 3px sólido, cor `#0066CC` (contraste 4.5:1 sobre branco)
- [x] Focus ring em inputs, botões, cards clicáveis
- [x] Não removido por `outline: none` sem substituição

#### Roles Semânticos (ARIA)
- [x] `role="button"` em elementos clicáveis não `<button>`
- [x] `role="dialog"` + `aria-modal="true"` em modais
- [x] `role="tablist"` / `role="tabpanel"` em abas
- [x] `role="tree"` / `role="treeitem"` em DAG de tasks
- [x] `role="alert"` / `aria-live="polite"` em toasts/notificações
- [x] `aria-label` em ícones sem texto

#### Estados Textuais (Além de Cor)
- [x] Loading: "Carregando..." + spinner
- [x] Sucesso: "Salvo com sucesso" + ícone ✓
- [x] Erro: "Falha: detalhe" + ícone ✗
- [x] Aviso: "Atenção: detalhe" + ícone ⚠
- [x] Status de task: badge com texto (Rodando, Revisão, Aceito, Falhou)

#### Contraste (WCAG AA)
- [x] Texto normal: 4.5:1 mínimo
- [x] Texto grande (18px+): 3:1 mínimo
- [x] Componentes UI (bordas, foco): 3:1 mínimo
- [x] Modo escuro/claro: ambos testados

#### Redução de Movimento
- [x] Respeita `@media (prefers-reduced-motion: reduce)`
- [x] Animações CSS desabilitadas (`transition: none`, `animation: none`)
- [x] Auto-scroll desabilitado
- [x] Carrosséis/pausa automática desabilitados

#### Leitores de Tela
- [x] `lang="pt-BR"` no HTML
- [x] Headings hierárquicos (h1→h2→h3)
- [x] Labels em todos inputs (`<label for>` ou `aria-label`)
- [x] Descrições em diffs complexos (`aria-describedby`)
- [x] Tabelas com `<th scope="col">` e `<caption>`
- [x] Imagens decorativas com `alt=""` ou `role="presentation"`

### 11.3 Testes de Acessibilidade
```bash
# Automatizado (axe-core)
npm test -- --grep "a11y"

# Manual (checklist)
# 1. Navegar só com teclado (Tab, Enter, Escape, Setas)
# 2. Zoom 200% (Ctrl++) - layout não quebra
# 3. Contraste: DevTools → Rendering → Emulate CSS media prefers-contrast: more
# 4. Redução movimento: DevTools → Rendering → Emulate prefers-reduced-motion
# 5. Leitor de tela: NVDA (Windows) / VoiceOver (macOS) / Orca (Linux)
```

### 11.4 Preferências de Acessibilidade (Persistidas)
```bash
# Via UI: Configurações → Acessibilidade
# Via CLI:
hydra preference set --scope user --key reduce_motion --value true
hydra preference set --scope user --key high_contrast --value true
hydra preference set --scope user --key screen_reader_optimized --value true

# Snapshot por run (imutável)
# Preferências aplicadas no início da run não mudam durante execução
```

---

## 12. Glossary e Acrônimos (Consolidado)

| Termo | Significado |
|-------|-------------|
| API | Application Programming Interface |
| AST | Abstract Syntax Tree |
| CDP | Chrome DevTools Protocol |
| CI | Continuous Integration |
| CLI | Command Line Interface |
| DAG | Directed Acyclic Graph |
| DBC-9 | Design by Contract — 9 partes |
| diff | Diferença entre versões (patch) |
| Git | Controle de versão distribuído |
| HITL | Human-in-the-Loop |
| HTTP | Hypertext Transfer Protocol |
| IDE | Integrated Development Environment |
| JSON | JavaScript Object Notation |
| MCP | Model Context Protocol |
| MER | Modelo Entidade-Relacionamento |
| MVP | Minimum Viable Product |
| OmniRoute | Gateway opcional de inferência/quota/fallback |
| OpenAPI | Especificação REST |
| PR | Pull Request |
| PRD | Product Requirements Document |
| RF | Requisito Funcional |
| RNF | Requisito Não-Funcional |
| RT | Requisito Técnico |
| SSE | Server-Sent Events |
| SSH | Secure Shell |
| Swarm | Orquestração paralela com worktrees |
| Relay | Orquestração com handoff entre provedores |
| Persistente | Orquestração com auto-resume por janela |
| SQLite | Banco relacional embarcado |
| UI | User Interface |
| UUID | Universally Unique Identifier |
| WAL | Write-Ahead Logging |
| WCAG AA | Web Content Accessibility Guidelines nível AA |
| tree-sitter | Parser incremental multi-linguagem |
| YAML | YAML Ain't Markup Language |
