# i_infra — Infraestrutura, Contêineres e Conectividade

**Identificador Formal:** `i_infra`
**Caminho Canônico:** `doc/i_infra/`
**Versão:** `v01_01_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch, complementando `prd_tecnico.md`, `../g_code/architecture.md`.
**Escopo:** Topologia de rede, tunelamento SSH, gateway OmniRoute, contêineres, sandboxing, certificação de drivers, gestão de processos multiplataforma.

---

Este diretório concentra as especificações de infraestrutura do **hydra-orch** para operação local, remota e híbrida.

## 1. Topologia de Rede e Portas

| Componente | Porta | Protocolo | Bind | Descrição |
|------------|-------|-----------|------|-----------|
| **Hydra Control Plane (API/CLI)** | 8000 | HTTP/REST + SSE | `127.0.0.1` (configurável) | Entrada principal: `/v1/control-plane/*`, `/v1/chat/completions` |
| **OmniRoute Gateway** | 20128 | HTTP | `127.0.0.1` | Gateway opcional de inferência, quota, fallback (OAuth CLIs) |
| **SSH Tunnel (Reverso)** | 11435 | SSH/TCP | `0.0.0.0` (no host remoto) | Túnel para nó GPU remoto (PC forte em casa) |
| **Ollama / vLLM Local** | 11434 | HTTP | `127.0.0.1` | Modelos locais (acessados via OmniRoute ou direto) |
| **CDP (Chrome DevTools)** | 9222 | WebSocket | `127.0.0.1` | Fallback para ferramentas web sem OAuth |

**Regras de Bind:**
- Padrão: `127.0.0.1` (apenas local). Exposição remota requer configuração explícita + autenticação + TLS.
- `server.bind_host` e `server.bind_port` em `config.yaml`.
- CORS allowlist estrita (`server.cors_allow_origins`), nunca `["*"]` com credenciais.

---

## 2. Tunelamento SSH Reverso (Nó GPU Remoto)

### 2.1 Arquitetura
```
[Hydra Local] ←── SSH Tunnel (port 11435) ──→ [PC Remoto / Servidor GPU]
     │                                              │
     └── OmniRoute (20128) ◄── SSH Tunnel ──── Ollama/vLLM (11434)
```

### 2.2 Especificação do Túnel
- **Tipo:** SSH reverso (`ssh -R 11434:localhost:11434 user@remote`)
- **Autenticação:** Chave SSH (Ed25519), sem senha. `ssh-agent` recomendado.
- **Healthcheck:** Ping a cada 30s (`ssh -O check` + TCP connect na porta tunelada).
- **Host Key Verification:** `StrictHostKeyChecking=yes`, `UserKnownHostsFile` conhecido. Falha se host key divergir (RT24).
- **Auto-reconnect:** `autossh` ou loop com backoff exponencial (1s, 2s, 4s, max 60s).
- **Isolamento:** Cada sessão concorrente usa porta local efêmera distinta no lado remoto.

### 2.3 Configuração (`config.yaml`)
```yaml
ssh_tunnel:
  enabled: true
  remote_host: "gpu.casa.example"
  remote_user: "hydra"
  remote_port: 22
  local_port: 11435           # Porta de entrada do túnel no local
  target_port: 11434          # Ollama/vLLM no remoto
  identity_file: "~/.ssh/hydra_gpu_ed25519"
  known_hosts_file: "~/.ssh/known_hosts"
  healthcheck_interval_sec: 30
  reconnect_backoff_max_sec: 60
```

### 2.4 Certificação de Transporte (RT24)
- `TransportDefinition` com `type: ssh`, `target_identity` (fingerprint SHA-256 da host key).
- `TransportHealth` verificado antes de cada uso: TCP connect + SSH banner + host key match.
- Falha observável: aborta conexão, não faz bypass silencioso.

---

## 3. Gateway OmniRoute (Opcional)

### 3.1 Papel
- Roteamento de inferência entre provedores (Claude Pro, ChatGPT Plus, Gemini Pro, DeepSeek, OpenRouter, Groq, modelos locais).
- Gestão de quota/janela de cota (ex.: 5h Claude Pro) com frescor (`observed`/`stale`/`unknown`).
- Fallback automático por cadeia de provedores priorizada.
- Autenticação OAuth oficial das CLIs (não scraping Playwright).

### 3.2 Modos de Operação (`config.yaml`)
```yaml
omniroute:
  enabled: true                    # false = modo direto obrigatório
  connection_mode: "optional"      # disabled | optional | required
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
```

### 3.3 Contrato HTTP (Hydra ↔ OmniRoute)
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/v1/quota` | GET | Retorna quota por provedor/modelo: `observed`/`stale`/`unknown`, `reset_at`, `remaining` |
| `/v1/chat/completions` | POST | Proxy compatível OpenAI para inferência |
| `/v1/route` | POST | Seleção adaptativa: recebe candidatos, retorna decisão + fallback chain |

### 3.4 Resiliência
- **Circuit Breaker:** Abre após N falhas consecutivas; `half-open` testa recuperação.
- **Timeout:** 10s padrão; configurável por provedor.
- **Modo Direto:** Se `enabled: false` ou `connection_mode: disabled`, Hydra usa drivers CLI diretos (Claude Code, Codex, etc.) sem gateway.
- **Mock para Testes:** `MockOmniRouteClient` simula offline, 429, erro auth, quota unknown.

---

## 4. Contêineres e Empacotamento

### 4.1 Imagem Base (Dockerfile)
```dockerfile
# Multi-stage build
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client tree-sitter-cli && \
    rm -rf /var/lib/apt/lists/*

FROM base AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

FROM base AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ ./src
COPY config.yaml ./
RUN useradd -m -u 1000 hydra && chown -R hydra:hydra /app
USER hydra
EXPOSE 8000
ENV PYTHONUNBUFFERED=1
CMD ["hydra", "serve"]
```

### 4.2 Docker Compose (Desenvolvimento)
```yaml
services:
  hydra:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ~/.ssh:/home/hydra/.ssh:ro
      - hydra_data:/home/hydra/.orchestrator
    environment:
      - LLM_PROVIDER=omniroute
      - LLM_MODEL=auto
    depends_on:
      - omniroute
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  omniroute:
    image: ghcr.io/omniroute/omniroute:latest
    ports:
      - "20128:20128"
    volumes:
      - ~/.omniroute:/root/.omniroute
    environment:
      - OMNIROUTE_CONFIG=/root/.omniroute/config.yaml

volumes:
  hydra_data:
```

### 4.3 Requisitos de Segurança (Dockerfile)
- Imagem base **com tag explícita** (não `latest`; digest aceito).
- Estágio final **sem root** (`USER hydra`).
- `HEALTHCHECK` presente no Dockerfile e no compose.
- Nenhum `ARG` ou `ENV` sensível com valor literal.
- `product_artifact_issues` valida esses pontos no CI.

---

## 5. Sandboxing e Isolamento de Execução

### 5.1 Worktree Git (Isolamento de Arquivos)
- **Não é sandbox de segurança:** Processo executor tem acesso ao SO, rede, filesystem conforme permissões do usuário.
- Isola apenas arquivos versionados pelo Git (branches/worktrees).
- `.orchestrator/worktree/<run_id>_<task_id>_<ordinal>/` — cada tentativa tem worktree própria.
- `allowed_paths` no `TaskSpec` restringe escopo via validação pós-execução (não enforcement de SO).

### 5.2 Contenção de Processo (Best Effort)
| Plataforma | Mecanismo | Limitação |
|------------|-----------|-----------|
| **Linux** | `cgroups v2` (se disponível): `memory.max`, `cpu.max`, `pids.max` | Requer root ou delegate cgroup |
| **Linux** | `systemd-run --scope --user --property=MemoryMax=...` | systemd user session |
| **macOS** | `launchd` + `ulimit` | Limitado |
| **Windows** | `Job Objects` (`CreateJobObject`, `AssignProcessToJobObject`) | API nativa via `pywin32` |

**Configuração (`config.yaml`):**
```yaml
execution:
  sandbox:
    enabled: false           # Opt-in; best effort
    memory_max_mb: 2048
    cpu_quota_pct: 100
    pids_max: 256
    network_allowlist: []    # CIDRs permitidos (vazio = sem rede)
```
- Se sandbox falha ao ativar → log warning + execução sem sandbox (não bloqueia).
- `bridge/worker_runner.py` aplica limites antes do `subprocess.Popen`.

### 5.3 Variáveis de Ambiente Filtradas
- Executor recebe apenas `env` filtrado: remove segredos, tokens, chaves privadas.
- `SecretRef` resolvido no spawn → injetado apenas se `declared_tools`/`permissions` do MCP/Skill autorizam.
- `core/redaction.py` sanitiza logs e eventos **após** execução (defesa em profundidade).

---

## 6. Certificação de Drivers (RT14, RT24)

### 6.1 Matriz de Certificação
| Driver / Executor | CLI | Suporta Tools | Suporta Worktree | Suporta Cancel | Suporta Streaming | Certificado (SO+Data) |
|-------------------|-----|---------------|------------------|----------------|-------------------|----------------------|
| `claude_code` | `claude` | ✅ | ✅ | ✅ | ✅ | ❌ (proposto) |
| `codex` | `codex` | ✅ | ✅ | ✅ | ✅ | ❌ (proposto) |
| `gemini_cli` | `gemini` | ✅ | ✅ | ⚠️ | ✅ | ❌ (proposto) |
| `opencode` | `opencode` | ✅ | ✅ | ✅ | ✅ | ❌ (proposto) |
| `aider` | `aider` | ✅ | ✅ | ✅ | ⚠️ | ❌ (proposto) |
| `ssh_cli` | `ssh` + CLI remoto | ✅ | ✅ | ✅ | ✅ | ✅ (Linux/macOS) |
| `cdp_fallback` | Chrome CDP | ❌ | ❌ | ❌ | ✅ | ❌ (experimental) |

### 6.2 Processo de Certificação
1. **Teste de capabilities:** `AgentExecutor.capabilities()` retorna `CapabilityDeclaration` verificado.
2. **Teste de integração:** Executa tarefa real em fixture, valida diff + check.
3. **Teste de cancelamento:** `SIGTERM`/`taskkill` → árvore terminada verificada.
4. **Teste de SO:** Roda em Windows 11, Ubuntu 22.04+, macOS 13+.
5. **Registro:** `AgentDefinition.is_certified = true` + `CapabilityDeclaration.certified_on = "driver+v1.2.3+linux+2026-11-06"`.
6. **Modo Produção:** `config.execution.require_certified = true` bloqueia drivers não certificados.

---

## 7. Gestão de Processos Multiplataforma

### 7.1 Tree Kill (Cancelamento Verificado)
```python
# Pseudocódigo bridge/worker_runner.py
async def cancel_tree(pid: int) -> bool:
    if sys.platform == "win32":
        # Windows: taskkill /PID <pid> /T /F
        proc = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(pid), "/T", "/F",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    else:
        # POSIX: kill process group
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            await asyncio.sleep(2)  # graceful
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True  # já morto
    # Verificar término
    await asyncio.sleep(0.5)
    return not is_alive(pid)
```

### 7.2 High-level API (`src/hydra_orch/bridge/process.py`)
```python
class ProcessManager:
    @staticmethod
    async def spawn(argv: List[str], cwd: Path, env: Dict[str, str],
                    timeout: float, on_output: Callable[[bytes], None]
                   ) -> ExecutionResult:
        # Cria process group (POSIX) / Job Object (Windows)
        # Aplica sandbox se habilitado
        # Monitora stdout/stderr com callback
        # Enforca timeout com tree kill
        # Retorna exit_code, timed_out, cancelled
```

### 7.3 Reconciliação de Órfãos
- Em startup: `psutil.process_iter()` encontra processos filhos do Hydra (por PPID ou label).
- `git worktree prune --expire=0` limpa worktrees órfãs.
- Arquivos em `.orchestrator/run/` sem registro no banco → movidos para `.orchestrator/orphans/` para inspeção.

---

## 8. Segurança de Infraestrutura

### 8.1 Autenticação Local
- Token JWT assinado (HS256) ou opaco (PBKDF2/Argon2 hash armazenado).
- `Authorization: Bearer <token>` em todas as rotas `/v1/control-plane/*`.
- Escopos granulares: `run:read`, `run:write`, `project:admin`, `memory:write`, `extension:install`, etc.
- Expiração configurável (padrão 24h), renovação via refresh token.

### 8.2 Redaction Centralizada
- `core/redaction.py` intercepta **todos** eventos antes de:
  - Escrita no banco (`ExecutionStore.save_transition`)
  - Transmissão SSE (`RunEvent.payload`)
  - Logs estruturados
  - Exportação de artefatos
- Padrões: `sk-`, `ghp_`, `glpat-`, `xoxb-`, `Bearer `, `-----BEGIN * PRIVATE KEY-----`, `password=`, `secret=`, `api_key=`, URLs `user:pass@`.
- Entropia: strings base64/hex > 32 chars com alta entropia → mascarados.

### 8.3 Allowlists de Rede
- `config.execution.sandbox.network_allowlist`: CIDRs permitidos para processos executores.
- OmniRoute: apenas `127.0.0.1:20128` (local) ou host configurado.
- SSH túnel: apenas host remoto configurado.
- CDP: apenas `127.0.0.1:9222`.
- Qualquer conexão fora da allowlist → bloqueada no nível do processo (se sandbox ativo) ou logado + alerta.

---

## 9. Observabilidade de Infraestrutura

### 9.1 Healthchecks
| Componente | Endpoint | Frequência | Critério de Sucesso |
|------------|----------|------------|---------------------|
| Hydra API | `GET /health` | 30s | 200 OK + `{"status": "healthy"}` |
| OmniRoute | `GET /v1/quota` | 60s | 200 + quota não `unknown` para provedores ativos |
| SSH Tunnel | TCP connect + SSH banner | 30s | Porta aberta + host key match |
| SQLite | `PRAGMA integrity_check` | 5min | `ok` |
| Disk Space | `shutil.disk_usage` | 5min | > 1GB livre em `.orchestrator/` |

### 9.2 Métricas de Infra (Prometheus /stats)
- `hydra_runs_active` (gauge)
- `hydra_worktrees_count` (gauge)
- `hydra_executor_spawn_duration_seconds` (histogram)
- `hydra_tree_kill_duration_seconds` (histogram)
- `hydra_sse_connections_active` (gauge)
- `hydra_omniroute_quota_status` (gauge: 0=unknown, 1=stale, 2=observed)
- `hydra_ssh_tunnel_status` (gauge: 0=down, 1=healthy, 2=degraded)

---

## 10. GAPs de Infraestrutura

- GAP-INFRA-01: Definir suporte a `cgroups v2` rootless no Linux (systemd delegate).
- GAP-INFRA-02: Implementar `Job Objects` Windows com `pywin32` para sandbox.
- GAP-INFRA-03: Certificar `claude_code` driver em Windows/Linux/macOS com testes reais.
- GAP-INFRA-04: Validar `autossh` vs loop Python para reconexão SSH (robustez).
- GAP-INFRA-05: Especificar rotação de tokens de acesso (refresh token flow).
- GAP-INFRA-06: Definir política de backup/restore de `.orchestrator/checkpoints.sqlite`.
- GAP-INFRA-07: Validar `tree-sitter` binário em contêiner (multi-arch: amd64/arm64).

---

## 11. Glossary e Acrônimos

| Termo | Significado |
|-------|-------------|
| autossh | Wrapper SSH que reconecta automaticamente |
| CDP | Chrome DevTools Protocol |
| CIDR | Classless Inter-Domain Routing |
| cgroups | Control Groups (Linux resource isolation) |
| Ed25519 | Algoritmo de assinatura SSH moderno |
| Job Object | Windows API para agrupamento e limitação de processos |
| OmniRoute | Gateway opcional de inferência/quota/fallback |
| PBKDF2/Argon2 | Funções de derivação de chave para hash de tokens |
| Reverse SSH Tunnel | Túnel SSH iniciado do remoto para o local (`-R`) |
| Sandbox | Ambiente isolado (best effort no hydra) |
| tree-sitter | Parser incremental multi-linguagem para AST |
| WAL | Write-Ahead Logging (SQLite) |