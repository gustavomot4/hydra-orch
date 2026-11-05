# PRD: Hydra-Orch — Orquestrador Universal Autônomo de LLMs para Engenharia de Software

**Caminho Canônico:** `doc/a_spc/prd_hydra_orch.md`  
**Status:** `APROVADO / NORMATIVO`  
**Foco Principal:** Engenharia de Software 100% Automatizada com Conexão Plug-and-Play de LLMs (Zero Trabalho Manual)  
**Ecossistema Suportado:** Claude (Pro/Free), ChatGPT (Plus/Free), Gemini (Pro/Free/CLI), Google Antigravity, Cursor, Windsurf, DeepSeek (Web/API), OpenRouter, LLMs Locais (Ollama/LM Studio/vLLM) e GPU Remota via SSH.

---

## 1. Visão Geral e Propósito do Produto

O **`hydra-orch`** é um middleware local e orquestrador universal projetado especificamente para automação de **Engenharia de Software**. Ele unifica assinaturas mensais de interface gráfica, IDEs agênticas, modelos de nuvem via API, planos gratuitos e máquinas remotas com GPU em um **único cérebro central compatível com a API da OpenAI (`http://localhost:8000/v1`)**.

O sistema elimina a necessidade de copiar e colar prompts entre janelas e resolve quatro gargalos fundamentais do desenvolvimento assistido por IA:

1. **Unificação Total de Assinaturas e Ferramentas:** Integração de interfaces gráficas desktop (Claude Pro, ChatGPT Plus, Gemini Pro), IDEs agênticas (Google Antigravity, Cursor, Windsurf), gateways de API (OpenRouter, DeepSeek API), contas gratuitas e servidores locais/remotos (Ollama/vLLM via túnel SSH).
2. **Paralelismo Real via Multi-Sessões Simultâneas (Swarm):** Diante de demandas complexas (ex.: *"Construa uma aplicação completa de barbearia com agendamento, painel e pagamento"*), o orquestrador decompõe o projeto em frentes independentes baseadas em complexidade e volume, disparando sessões paralelas isoladas por **Git Worktrees**.
3. **Continuidade entre Modelos (Hot-Handoff Instantâneo):** Permite encadear etapas de pipeline (`Planejamento ➡️ Codificação ➡️ Testes ➡️ Documentação`) ou transferir a geração em tempo real para outra IA quando uma cota é atingida.
4. **Resiliência e Auto-Resume de Cotas:** Se a cota de 5 horas do Claude Pro acabar no meio de um arquivo, o orquestrador armazena o stream em buffer SQLite local e pode **hibernar e retomar sozinho no ponto exato assim que a cota voltar** (Modo Persistente) ou **realizar hot-swap imediato** para outro modelo finalizar a tarefa (Modo Relay).

---

## 2. Arquitetura Geral do Sistema

O `hydra-orch` atua como um middleware local que expõe uma API compatível com o padrão OpenAI (`http://localhost:8000/v1/chat/completions`) para ferramentas SWE na ponta frontal, enquanto orquestra as interfaces, IDEs e túneis de rede nos bastidores:

```
+-----------------------------------------------------------------------------+
| CAMADA 1: ENTRADA & AGENTES DE ENGENHARIA DE SOFTWARE                       |
| - CLI Direta: `hydra run "Construa um app de barbearia" --mode swarm`       |
| - Agentes SWE Conectados: Cline (VS Code) | Aider | OpenCode | OpenHands    |
+-----------------------------------------------------------------------------+
                                       │
                                       ▼ (HTTP POST /v1/chat/completions)
+-----------------------------------------------------------------------------+
| CAMADA 2: NÚCLEO DO ORQUESTRADOR (Hydra Core Engine - Python/FastAPI)       |
| - Router & Decomposer: Avaliação de complexidade (1 a 10) e roteamento      |
| - Execution Modes: Modo 1 (Swarm) | Modo 2 (Relay) | Modo 3 (Persistente)   |
| - Stream Checkpointer & Code Stitcher (Buffer SQLite + Auto-Resume Timer)   |
| - Swarm Worktree Manager: Isolamento de branches Git + Auto-Merge + Testes  |
+-----------------------------------------------------------------------------+
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
+-----------------+     +-----------------------------+     +-----------------+
| CONECTOR UI/CDP |     | CONECTOR IDE & API GATEWAY  |     | CONECTOR LOCAL  |
| (Apps Desktop)  |     | (Ferramentas Dev & Nuvem)   |     | & REMOTO (SSH)  |
+-----------------+     +-----------------------------+     +-----------------+
| - Claude Pro    |     | - Google Antigravity        |     | - Ollama Local  |
| - ChatGPT Plus  |     | - Cursor / Windsurf         |     | - LM Studio     |
| - Gemini Pro    |     | - Gemini CLI                |     | - GPU Remota    |
| - DeepSeek Web  |     | - OpenRouter / DeepSeek API |     |   via SSH       |
| - Contas Free   |     | - Modelos Free API          |     |   (Porta 11435) |
+-----------------+     +-----------------------------+     +-----------------+
```

---

## 3. Conectores Universais (Plug-and-Play)

Cada provedor implementa o contrato padrão `BaseAdapter`, expondo métodos assíncronos de streaming, health check e detecção de limites (`LimitHitException`):

| Classe de Conector | Ferramentas e Planos Suportados | Mecanismo de Controle |
| :--- | :--- | :--- |
| **1. Interface Gráfica (UI / CDP)** | Claude (Pro/Free), ChatGPT (Plus/Free), Gemini (Pro/Free), DeepSeek Web | Conecta via Chrome DevTools Protocol (`localhost:9222-9229`) via WebSocket. Injeta prompts e lê o DOM em streaming sem roubar o foco do sistema operacional. |
| **2. IDEs Agênticas e CLIs** | Google Antigravity, Cursor, Windsurf, Gemini CLI | Dispara tarefas via CLI interna (`antigravity`, `cursor`, `gemini`), pontes locais HTTP/IPC ou workspaces isolados com monitoramento via git status. |
| **3. APIs e Gateways** | OpenRouter, DeepSeek API, Groq, Anthropic/OpenAI API | Requisições HTTP REST assíncronas com Server-Sent Events (SSE). Suporta chaves pagas e rotação automática de modelos gratuitos do OpenRouter (`:free`). |
| **4. Local & Remoto via SSH** | Ollama, LM Studio, vLLM (local ou em GPU de outro computador na rede) | Conecta em `localhost:11434` ou abre túnel SSH automático em background (`ssh -N -L 11435:127.0.0.1:11434`) para usar GPU remota com healthcheck de latência. |

### 3.1. Operação do Gemini Pro como Interface Local
Para operar o Gemini Pro com paridade total aos clientes desktop do Claude e ChatGPT, o orquestrador suporta três modalidades:
1. **App Desktop via PWA/Chromium (`--app`):** Inicialização isolada (`--app=https://gemini.google.com --remote-debugging-port=9224 --user-data-dir=~/.hydra/gemini-profile`), expondo o DOM completo para sessões paralelas sem interferir no navegador diário.
2. **Google Antigravity & Gemini CLI:** Acionamento nativo via IDE agêntica Antigravity ou via terminal com sessão autenticada do Gemini CLI.
3. **Google AI Studio (Janela Dedicada):** Conexão via CDP para janelas de contexto estendidas (até 2M tokens) e controle estrito de temperatura e system prompts.

### 3.2. Detecção de Término de Geração e Proteção de Clipboard (`ui_cdp.py`)
- **End-of-Stream:** Detecção do encerramento da resposta quando o botão `Stop Generating` é removido e os botões de ação (`Copy`, `Regenerate`) permanecem estáveis por $1.5\text{ s}$.
- **Extração Fiel de Markdown:** Acionamento programático do botão nativo "Copy" da interface para extrair blocos de código com indentação e sintaxe perfeitas.
- **Clipboard Guard:** Caso utilize a área de transferência do sistema operacional, o orquestrador armazena o clipboard original do usuário em RAM, extrai o Markdown em menos de $50\text{ ms}$ e restaura o conteúdo original imediatamente.

---

## 4. Os 3 Modos de Operação

O comportamento do orquestrador é configurável via `config.yaml`, linha de comando (`hydra run --mode <modo>`) ou cabeçalho HTTP:

### Modo 1: Enxame Paralelo Multi-Sessão (Swarm Mode)
- **Funcionamento:** Decompõe prompts macros em sub-tarefas especializadas com base em **complexidade ($1\text{ a }10$)** e volume de tokens, executando sessões paralelas simultâneas isoladas por **Git Worktrees**.
- **Distribuição Típica por Especialidade:**
  - *Arquitetura, Planejamento e Regras Críticas (Dificuldade 8-10):* Claude Pro ou Google Antigravity.
  - *Frontend, UI e Componentes (Dificuldade 6-7):* ChatGPT Plus ou Cursor.
  - *Banco de Dados, Migrations e Testes (Dificuldade 4-5):* DeepSeek, OpenRouter ou GPU Remota via SSH.
  - *Documentação, Revisão e Contratos (Contexto Amplo):* Gemini Pro.

### Modo 2: Esteira Sequencial com Failover Instantâneo (Relay Mode)
- **Funcionamento:** Pipeline encadeado por etapas (`Planejamento ➡️ Implementação ➡️ Testes ➡️ Documentação`) com tolerância a falhas.
- **Hot-Handoff em Tempo Real:** Se a IA ativa atingir o limite de tokens da assinatura (ex.: aos 60% de um arquivo complexo), o orquestrador intercepta o evento, preserva o trecho já gerado e transfere o restante da geração instantaneamente para o próximo modelo da esteira continuar sem interrupção.

### Modo 3: Foco Persistente com Auto-Resume (Estilo Nativo Claude)
- **Funcionamento:** Fixa o modelo preferido do usuário (ex.: Claude Pro) como executor mandatário.
- **Espera Ativa e Retomada:**
  1. Salva o código parcial gerado até o momento do corte no SQLite.
  2. Identifica na interface o horário exato de renovação da cota (ex.: *"Limite atingido. Reseta às 19:00"*).
  3. Hiberna a sessão com cronômetro regressivo.
  4. No segundo exato da liberação, dispara a continuação do prompt, concatenando as partes com **Code Stitching** sem duplicar linhas.

### Suporte a Contas Gratuitas (Free Tiers + Local/SSH)
Para ambientes baseados exclusivamente em planos gratuitos e modelos locais:
- Rotação dinâmica de contas free para tarefas de raciocínio crítico.
- Desvio automático de tarefas repetitivas (boilerplate, formatação, testes auxiliares) para o Ollama local ou nó SSH, preservando 100% da cota gratuita de nuvem para decisões arquiteturais.

---

## 5. Exemplo Prático: Execução de Aplicação em Múltiplas Sessões

Fluxo operacional acionado por um único comando macro:

```bash
hydra run "Construa uma aplicação completa de barbearia com agendamento, painel administrativo e pagamentos" --mode swarm
```

### Fase A: Decomposição e Contrato Base (~30 segundos)
1. O `router.py` aciona o modelo arquiteto principal (ex.: Claude Pro) para produzir o **Contrato Base Imutável** (`.orchestrator/CONTRACT.md` / `contract.json`).
2. O contrato formaliza rotas de API, schemas de banco, interfaces TypeScript e fronteiras de arquivos.
3. O orquestrador particiona a demanda em sub-tarefas com complexidade e arquivos-alvo delimitados.

### Fase B: Isolamento por Git Worktrees e Execução Simultânea
O módulo `swarm.py` provisiona diretórios físicos paralelos em `.orchestrator/worktree/` para impedir conflitos de escrita concorrente:

```
                    [Contrato Base: CONTRACT.md]
                                  │
       ┌──────────────────────────┼──────────────────────────┐
       ▼                          ▼                          ▼
[Sessão Paralela 1]       [Sessão Paralela 2]       [Sessão Paralela 3]       [Sessão Paralela 4]
Branch: swarm/backend     Branch: swarm/frontend    Branch: swarm/db-test     Branch: swarm/docs
IA: Claude Pro /          IA: ChatGPT Plus /        IA: GPU via SSH /         IA: Gemini Pro
    Antigravity               Cursor                    DeepSeek              Dificuldade: 4/10
Dificuldade: 9/10         Dificuldade: 7/10         Dificuldade: 5/10         Contexto: Amplo
-------------------       -------------------       -------------------       -------------------
Agenda, bloqueio de       Telas Next.js/React,      Schemas Prisma/SQL,       Documentação Swagger,
horários, regras de       calendário do cliente     seeds de barbeiros e      README técnico e
comissão e pagamentos.    e dashboard admin.        testes unitários/E2E.     auditoria de tipos.
```

### Fase C: Sincronização, Auto-Merge e Validação com Testes
1. Conforme cada sessão conclui sua implementação, commits estruturados são gerados nas branches de trabalho.
2. O orquestrador executa a suíte de testes (`pytest`, `npm test`) dentro do worktree.
3. Se os testes forem aprovados, o merge automático é realizado na branch principal. Em caso de discrepância entre Frontend e Backend, uma rodada cirúrgica de alinhamento é disparada contra o contrato base.
4. Os worktrees temporários são removidos e limpos automaticamente via `git worktree prune`.

---

## 6. Mecanismos de Resiliência e Checkpointing

### 6.1. Stream Checkpointer (`checkpointer.py`)
- **Persistência Assíncrona:** Registro contínuo de tokens e blocos de código no SQLite local (`.orchestrator/checkpoints.sqlite`).
- **Tabelas do Sistema:**
  - `checkpoints`: Mantém `session_id`, `provider`, `prompt`, `accumulated_content`, status e timestamps.
  - `provider_limits`: Registra provedores sob rate-limit ativo, timestamp de liberação e motivo.
- **Code Stitching:** Ao retomar uma geração interrompida ou transferi-la via Hot-Handoff, o orquestrador extrai as últimas 15 linhas do código salvo como âncora contextual, orientando o modelo seguinte a continuar exatamente a partir do próximo caractere sem duplicações.

### 6.2. Túnel SSH com Healthcheck Ativo (`ssh_tunnel.py`)
- Gerenciamento de processo em segundo plano com `autossh` ou `ssh -N -L`:
  ```bash
  ssh -N -L 11435:127.0.0.1:11434 user@host-gpu -p 22 -o ServerAliveInterval=15
  ```
- **Failover por Latência:** Monitoramento contínuo da porta forwarded. Caso a latência exceda $500\text{ ms}$ ou a máquina remota fique indisponível, o nó SSH é temporariamente colocado em standby e o tráfego é redirecionado para a esteira de fallback local/nuvem.

---

## 7. Integração com Agentes de Engenharia de Software (SWE)

O `hydra-orch` conecta-se diretamente às principais ferramentas de desenvolvimento através do seu endpoint compatível com OpenAI (`http://localhost:8000/v1`):

| Agente SWE | Ambiente | Papel Operacional | Forma de Conexão com o Hydra |
| :--- | :--- | :--- | :--- |
| **Cline** | VS Code / Cursor / Forks | Agente de código autônomo com leitura de terminal, edição de arquivos e auto-correção de testes. | Configurado como provedor `OpenAI Compatible` apontando para `http://localhost:8000/v1`. Plan Mode e Act Mode são roteados dinamicamente pelo Hydra. |
| **Aider** | Terminal CLI | Edição multi-arquivo cirúrgica, commits atômicos no Git e modo Architect/Editor. | Executado via `aider --openai-api-base http://localhost:8000/v1 --openai-api-key hydra --model openai/hydra-default`. |
| **OpenCode** | CLI / Background Worker | Execução em lote e automações headless com suporte a MCP. | Empregado como worker interno do motor de enxame (`swarm.py`) dentro dos Git Worktrees. |
| **OpenHands** | Docker / Web | Engenheiro autônomo operando em sandbox com navegador, terminal e editor integrados. | Aponta para `http://host.docker.internal:8000/v1` para resolução autônoma de issues e PRs. |

---

## 8. Especificação do Arquivo de Configuração (`config.yaml`)

Modelo normativo com todas as opções de conectores, thresholds e parâmetros operacionais:

```yaml
version: "1.0"

server:
  host: "127.0.0.1"
  port: 8000
  title: "Hydra Orchestrator API"
  description: "Universal Autonomous LLM Orchestrator"

orchestrator:
  default_mode: "relay" # swarm | relay | persistent
  preferred_primary_llm: "claude_pro"
  resilience:
    database_path: ".orchestrator/checkpoints.sqlite"
    on_limit_action: "hot_handoff" # hot_handoff | auto_resume
    handoff_fallback_chain:
      - "claude_pro"
      - "chatgpt_plus"
      - "deepseek"
      - "openrouter"
      - "ssh_remote"
      - "ollama_local"
    auto_resume_check_interval_seconds: 30

swarm:
  worktrees_dir: ".orchestrator/worktree"
  base_contract_file: ".orchestrator/CONTRACT.md"
  auto_merge: true
  run_tests_before_merge: true
  test_command: "pytest"
  difficulty_thresholds:
    simple:
      max_complexity: 3
      preferred_provider: "ollama_local"
    moderate:
      max_complexity: 7
      preferred_provider: "deepseek"
    complex:
      max_complexity: 10
      preferred_provider: "claude_pro"

providers:
  ui_cdp:
    claude_pro:
      enabled: true
      cdp_port: 9222
      target_url: "https://claude.ai"
      session_timeout_seconds: 300
      rate_limit_reset_hours: 5.0
    chatgpt_plus:
      enabled: true
      cdp_port: 9223
      target_url: "https://chatgpt.com"
      session_timeout_seconds: 300
    gemini_pro:
      enabled: true
      cdp_port: 9224
      target_url: "https://gemini.google.com"
      launch_mode: "pwa_app"
      session_timeout_seconds: 300

  ide_bridge:
    antigravity:
      enabled: true
      bridge_url: "http://127.0.0.1:9330"
    cursor:
      enabled: true
      bridge_url: "http://127.0.0.1:9331"

  api_gateway:
    openrouter:
      enabled: true
      base_url: "https://openrouter.ai/api/v1"
      api_key_env: "OPENROUTER_API_KEY"
      default_model: "anthropic/claude-3.5-sonnet"
    deepseek:
      enabled: true
      base_url: "https://api.deepseek.com/v1"
      api_key_env: "DEEPSEEK_API_KEY"
      default_model: "deepseek-coder"

  remote_local:
    ollama_local:
      enabled: true
      base_url: "http://127.0.0.1:11434"
      default_model: "qwen2.5-coder:32b"
    ssh_remote:
      enabled: false
      host: "gpu-node.local"
      port: 22
      user: "hydra"
      key_file: "~/.ssh/id_ed25519"
      remote_port: 11434
      local_bind_port: 11435
      use_autossh: true
      default_model: "qwen2.5-coder:32b"
```

---

## 9. Estrutura do Repositório (Conforme Taxonomia Oficial)

O layout do repositório segue a norma normativa de taxonomia (`doc/a_spc/taxonomia_file_system.md`), com pastas estritamente no singular, prefixos sequenciais de execução e raiz limpa:

```text
hydra-orch/
├── .github/                         # Workflows e instruções para agentes
├── .gitignore                       # Ignora temporários, checkpoints e saídas locais
├── AGENTS.md                        # Fonte única de governança para agentes
├── CLAUDE.md                        # Redirecionamento canônico para AGENTS.md
├── GEMINI.md                        # Redirecionamento canônico para AGENTS.md
├── config.yaml                      # Configuração declarativa central
├── pyproject.toml                   # Metadados e ponto de entrada da CLI 'hydra'
├── README.md                        # Apresentação do projeto e guia rápido
├── doc/
│   ├── README.md                    # Índice geral da documentação
│   ├── a_spc/                       # Especificações normativas e PRDs
│   │   ├── CONTEXTO-ORQUESTRACAO.md # Investigação e decisões de arquitetura
│   │   ├── prd_hydra_orch.md        # PRD unificado do produto (este documento)
│   │   ├── taxonomia_file_system.md # Norma oficial de taxonomia do repositório
│   │   └── README.md                # Catálogo de especificações
│   └── b_manual/                    # Manuais operacionais e runbooks
│       ├── .gitkeep
│       └── README.md
├── ws/                              # Espaço de trabalho ordenado
│   ├── a_input/                     # Insumos de entrada para tarefas
│   └── b_output/                    # Saídas e relatórios gerados (ignorado no git)
├── src/
│   └── hydra_orch/
│       ├── __init__.py
│       ├── cli.py                   # CLI: hydra serve, hydra run, hydra status
│       ├── config.py                # Parser Pydantic do config.yaml
│       ├── model.py                 # Schemas OpenAI Chat Completions & Streaming
│       ├── server.py                # Servidor FastAPI proxy OpenAI (:8000/v1)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── checkpointer.py      # SQLite checkpoints, Auto-Resume e Code Stitching
│       │   ├── router.py            # Roteador dos modos Swarm, Relay e Persistente
│       │   ├── ssh_tunnel.py        # Gerenciador de túneis SSH / autossh para GPU
│       │   └── swarm.py             # Particionamento, Contratos e Git Worktrees
│       └── adapter/
│           ├── __init__.py
│           ├── base.py              # Classe BaseAdapter e LimitHitException
│           ├── api_gateway.py       # Driver OpenRouter e DeepSeek REST SSE
│           ├── ide_bridge.py        # Driver Antigravity e Cursor
│           ├── remote_local.py      # Driver Ollama / vLLM local e via SSH
│           └── ui_cdp.py            # Driver Chrome DevTools Protocol (9222-9229)
└── tests/                           # Suíte de testes automatizados pytest
    ├── test_checkpointer.py
    ├── test_config.py
    ├── test_model.py
    ├── test_router.py
    └── test_server.py
```

---

## 10. Roadmap de Implementação

1. **Fase 1 — Fundação e Governança:** Formalização da taxonomia oficial, configuração centralizada, suporte à CLI (`hydra`) e gestão de túnel SSH com healthcheck.
2. **Fase 2 — Conectores Universais e Resiliência:** Conexão CDP nas portas `9222-9229`, clipboard guard, stream checkpointer com buffer SQLite, e mecanismos de Hot-Handoff e Auto-Resume de cotas de assinatura.
3. **Fase 3 — Motor de Enxame Paralelo (Swarm):** Decomposição de tarefas por complexidade, geração do contrato base imutável, criação de Git Worktrees e merge automatizado com execução de testes.
4. **Fase 4 — Servidor Proxy OpenAI:** Exposição do endpoint `http://localhost:8000/v1/chat/completions` com suporte a streaming Server-Sent Events (SSE) para conexão direta com Cline, Aider, OpenCode e OpenHands.
