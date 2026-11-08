# visao_produto — Visão Geral do Produto e Modos de Execução

**Identificador Formal:** `visao_produto.md`
**Caminho Canônico:** `doc/a_context/visao_produto.md`
**Versão:** `v05_01_0000`
**Status:** `DOCUMENTO DE VISÃO / ALINHADO À ARQUITETURA V0–V4`
**Autoridade:** Visão de produto do hydra-orch consolidando modos Swarm (em Duas Ondas), Relay e Persistente (com Handoff por Estado Git/Worktree), formalmente especificada em [`../b_spc/prd_funcional.md`](../b_spc/prd_funcional.md) e [`../b_spc/prd_tecnico.md`](../b_spc/prd_tecnico.md).
**Escopo:** Visão de produto, proposta de valor, ecossistema e arquitetura estratégica focada em Engenharia de Software Autônoma.

---

Para requisitos normativos detalhados e desenvolvimento por tasks, consultar o [PRD funcional](../b_spc/prd_funcional.md) e o [PRD técnico](../b_spc/prd_tecnico.md), acompanhados do [diagrama de classes](../e_class/diagrama_classe.md) e do [MER](../d_mer/mer.md). Ideias exploratórias de longo prazo fora do domínio estrito de engenharia de software (como geração multimodal de vídeo/áudio, voz duplex e quantização GGUF) estão preservadas em [`ideia_futura.md`](ideia_futura.md).

> **Status de leitura:** este documento registra a visão de produto do `hydra-orch` reconciliada com a arquitetura de execução verificável. O gateway OmniRoute opera como camada opcional (o Hydra funciona nativamente em modo direto) e o PRD técnico exige evidência real de ferramentas, diffs Git e checks executados. Todos os caminhos de runtime seguem a taxonomia vigente em `.orchestrator/`.

**Projeto / Repositório:** `hydra-orch` (Binário CLI: `hydra`)
**Foco Principal:** Desenvolvimento e Engenharia de Software Automatizados e Verificáveis
**Motor de Conexão Base:** Modo Direto (CLIs e APIs locais/remotas) + OmniRoute Gateway Opcional + Túnel SSH Automático
**Ecossistema Alvo:** Claude (Code CLI / API), OpenAI Codex CLI, Gemini CLI, OpenCode, Aider, DeepSeek, OpenRouter, LLMs Locais (Ollama/LM Studio/vLLM) e GPU Remota em outro PC em casa via SSH.

---

## 1. Visão Geral e o Diferencial Único do `hydra-orch`

O ecossistema open-source atual possui ferramentas separadas para problemas distintos:
1. **Gateways de Inferência e Assinatura (ex: LiteLLM, OpenRouter, OmniRoute):** Roteiam chamadas de API ou OAuth de CLIs e fazem fallback entre modelos. Porém, são apenas roteadores de mensagens: **não sabem decompor projetos de software**, não criam fundações compiláveis antes de paralelizar agentes e não gerenciam worktrees ou suítes de testes.
2. **Gerenciadores de Git Worktrees (ex: Claude Squad, Parallel Code, Nimbalyst):** Criam pastas isoladas para agentes de código, mas carecem de uma **Onda de Fundação Compilável (Wave 0)** que trave schemas, tipos e dependências antes de disparar os agentes paralelos (Wave 1), além de não possuírem **Handoff Estruturado por Estado Git/Worktree** quando uma cota expira no meio de uma tarefa.

### A Proposta de Valor do `hydra-orch`
O **`hydra-orch`** concentra 100% da sua arquitetura nos **4 motores de inteligência de Engenharia de Software**:

1. **Decompositor de Tarefas em DAG (`Task Decomposer`):** Recebe um objetivo de engenharia, valida um Grafo Acíclico Dirigido (DAG) de tarefas pontuadas de $1\text{ a }10$ em complexidade e aloca o executor/modelo adequado combinando capacidades certificadas com a cota disponível.
2. **Motor Contract-First em Duas Ondas (`Wave 0 Foundation + Wave 1 Swarm`):** Em vez de jogar agentes paralelos no escuro ou travar contratos estáticos que não compilam, executa a **Wave 0 (Fundação Compilável)** para consolidar schemas, interfaces, stubs e dependências (`pyproject.toml`/`package.json`) validados por linter/typecheck na branch `integrate/<run_id>`, e só então abre as worktrees paralelas da **Wave 1** com protocolo formal de *Contract Amendment* se ajustes de interface forem necessários.
3. **Orquestrador de Enxame em Git Worktrees (`Multi-Session Swarm`):** Abre sessões concorrentes em worktrees reais (`.orchestrator/worktree/`), bloqueia mutações acidentais de pacotes compartilhados durante a Wave 1, executa o merge serializado e roda os checks de integração com loop limitado de auto-reparo (*Self-Healing*).
4. **Motor de Handoff por Estado Git/Worktree e Retry de Turno Atômico (`Checkpointer & Handoff Engine`):** Persiste o estado da execução em SQLite WAL (`.orchestrator/checkpoints.sqlite`). Quando um agente CLI atinge rate-limit (ex.: janela de 5h), preserva o estado exato da worktree (`git status`, `git diff`, histórico de ferramentas e relatório de testes passando/falhando) para retomar após o reset da cota (**Modo 3: Persistente**) ou transferir a worktree imediatamente para outro executor/modelo compatível (**Modo 2: Relay**). Para chamadas no proxy `/v1/chat/completions` interrompidas durante `tool_calls`, descarta o turno incompleto e realiza **Retry de Turno Atômico** sem corromper payloads JSON.

---

## 2. Arquitetura do Sistema em 4 Camadas

O `hydra-orch` expõe a porta `8000` (`http://127.0.0.1:8000/v1`) tanto para o Control Plane (`/v1/control-plane/*`) quanto para inferência compatível com OpenAI (`/v1/chat/completions`):

```text
+--------------------------------------------------------------------------------+
| CAMADA 1: ENTRADA DO OPERADOR, CLI & INTERFACE VISUAL                          |
| - CLI Nativa: `hydra run`, `hydra review`, `hydra integrate`, `hydra status`   |
| - Control Plane UI / Agentes: Aider | OpenCode | Claude Code | Codex CLI       |
+--------------------------------------------------------------------------------+
                                        │
                                        ▼ (HTTP REST / SSE 127.0.0.1:8000/v1)
+--------------------------------------------------------------------------------+
| CAMADA 2: HYDRA-ORCH CORE & ENGINE (Control Plane de Engenharia)               |
| 1. Decompositor DAG + Validador de Capabilities e Orçamento (BudgetGovernor)   |
| 2. Motor Contract-First em 2 Ondas (Wave 0 Fundação -> Wave 1 Swarm Paralelo)  |
| 3. Gerenciador dos 3 Modos (Modo 1: Swarm | Modo 2: Relay | Modo 3: Persist)   |
| 4. Checkpointer SQLite WAL + Handoff por Estado Git/Worktree & Turn Retry      |
| 5. Gate de Integração Serializada (`integrate/<run_id>`) + Self-Healer         |
+--------------------------------------------------------------------------------+
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
[Worktree 1: Backend]         [Worktree 2: Frontend]        [Worktree 3: DB & Tests]
 Isolada a partir da Wave 0    Isolada a partir da Wave 0    Isolada a partir da Wave 0
          │                             │                             │
          └─────────────────────────────┼─────────────────────────────┘
                                        ▼
+--------------------------------------------------------------------------------+
| CAMADA 3: PONTES DE EXECUÇÃO E GATEWAY OPCIONAL (`bridge/` & `adapter/`)       |
| - Worker Runner: Subprocessos reais com `cwd` na worktree e tree-kill por SO   |
| - Modo Direto: Execução nativa via CLIs autenticadas e APIs (OpenRouter/Local) |
| - OmniRoute Gateway (Opcional :20128): Rotação de cotas 5h e planos gratuitos  |
| - SSH Tunnel Manager (:11435): Port-forwarding com verificação de host key     |
+--------------------------------------------------------------------------------+
```

---

## 3. Os 3 Modos de Operação Configuráveis pelo Operador

### Modo 1: Enxame Paralelo em Duas Ondas (`Two-Wave Contract-First Swarm`)
* **Ideal para:** Criar módulos completos, features multi-camada ou refatorações estruturadas.
* **Comportamento:**
  * **Wave 0 (Fundação Compilável):** Um único worker arquiteto gera os contratos executáveis (schemas de banco, tipos compartilhados, OpenAPI, stubs de interface e eventuais adições em `pyproject.toml`/`package.json`), valida com linter/typecheck e integra na branch base `integrate/<run_id>`.
  * **Wave 1 (Swarm Paralelo):** O Hydra cria as Git Worktrees isoladas a partir do commit da Wave 0 (com dependências de pacotes travadas contra mutação concorrente) e despacha os workers em paralelo respeitando o semáforo `max_parallel_worktrees`.
  * **Contract Amendment (Emenda de Contrato):** Se um worker da Wave 1 identificar necessidade de alterar um tipo ou rota compartilhada, ele sinaliza `needs_context` / emenda; a alteração é validada na base antes de revalidar as demais worktrees.

### Modo 2: Esteira Sequencial e Handoff Estruturado (`Relay Mode`)
* **Ideal para:** Pipeline sequencial (`Fundação/Arquitetura -> Implementação -> Testes -> Revisão`) ou failover imediato quando a cota de um provedor acaba.
* **Handoff por Estado Git/Worktree:** Se o executor ativo atingir limite de cota (429), o Hydra registra um `HandoffCheckpoint` contendo o `git diff` atual da worktree, os arquivos já modificados, os comandos/testes executados e os critérios pendentes, transferindo a worktree para o próximo executor elegível sem perder o trabalho já salvo em disco.

### Modo 3: Foco Persistente com Auto-Resume (`Persistent Mode`)
* **Ideal para:** Tarefas críticas onde o operador exige que um único modelo/executor (ex.: Claude Pro) conclua todo o trabalho sem troca de família de modelo.
* **Pausa e Retomada Limpa:** Ao detectar esgotamento da janela de cota, o run entra no estado `waiting` (`rate_limit_window`), preserva a worktree e o `HandoffCheckpoint` no SQLite WAL e aguarda a reabertura da janela para retomar a execução no mesmo workspace a partir do estado Git verificado.

---

## 4. Configuração Canônica (`config.yaml`)

```yaml
version: "5.0"

hydra:
  proxy_host: "127.0.0.1"
  proxy_port: 8000
  default_mode: 1 # 1: Swarm (Wave 0+1) | 2: Relay | 3: Persistente
  preferred_primary_model: "claude-pro"
  worktree_base_dir: ".orchestrator/worktree"
  state_db: ".orchestrator/checkpoints.sqlite"
  auto_heal_build_errors: true
  max_heal_attempts: 2

omniroute:
  enabled: false
  auto_start_daemon: false
  connection_mode: "disabled" # disabled | optional | required
  base_url: "http://127.0.0.1:20128/v1"
  quota_api_url: "http://127.0.0.1:20128/api/usage/quota"
  default_routing_strategy: "auto/thrifty"

remote_ssh_gpu:
  enabled: false
  ssh_target: "usuario@192.168.1.100"
  ssh_port: 22
  ssh_key: "~/.ssh/id_ed25519"
  local_port: 11435
  remote_port: 11434
  healthcheck_interval_sec: 10
  auto_register_in_omniroute: true

modes:
  mode_1_swarm:
    max_parallel_worktrees: 4
    worker_cli: "opencode"
    wave_0_foundation_enabled: true
    lock_dependency_manifests_in_wave_1: true
    symlink_dirs: ["node_modules", ".venv", "vendor"]
    roles:
      backend_core: "architect_heavy"
      frontend_ui: "fullstack_coder"
      db_and_tests: "database_and_tests"
      docs_and_review: "context_and_docs"

  mode_2_relay:
    sequence:
      - stage: "contract_and_plan"
        model: "architect_heavy"
      - stage: "implementation"
        model: "fullstack_coder"
      - stage: "unit_and_integration_tests"
        model: "database_and_tests"
      - stage: "documentation"
        model: "context_and_docs"
    handoff_strategy: "worktree_state" # worktree_state | atomic_turn_retry

  mode_3_persistent:
    locked_model: "architect_heavy"
    wait_for_5h_quota_reset: true
    poll_quota_interval_sec: 30
    resume_strategy: "worktree_state"
```
