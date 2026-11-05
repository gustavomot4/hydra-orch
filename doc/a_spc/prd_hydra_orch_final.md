# PRD: Hydra-Orch — Orquestrador Universal Autônomo de LLMs para Engenharia de Software

**Projeto / Repositório:** `hydra-orch` (Binário CLI: `hydra`)  
**Versão:** 4.0 (Especificação Completa e Unificada)  
**Foco Principal:** Desenvolvimento de Software e Engenharia de Software 100% Automatizada (Zero Trabalho Manual)  
**Ecossistema Suportado:** Claude (Pro/Free), ChatGPT (Plus/Free), Gemini (Pro/Free/CLI), Google Antigravity, Cursor, Windsurf, DeepSeek (Web/API), OpenRouter, LLMs Locais (Ollama/LM Studio/vLLM) e GPU Remota em outro PC via SSH.

---

## 1. Visão Geral e Propósito do Produto

O **`hydra-orch`** é um orquestrador e roteador universal local projetado especificamente para **Engenharia de Software**. Ele permite que o desenvolvedor conecte todas as suas assinaturas de IA, ferramentas de código, planos gratuitos e computadores locais/remotos em um único cérebro central, operando com **zero intervenção manual** (sem copiar e colar textos entre janelas).

O sistema resolve quatro problemas centrais do fluxo de desenvolvimento moderno:
1. **Unificação Total de Assinaturas e Ferramentas:** Permite usar assinaturas mensais de interface gráfica (como Claude Pro, ChatGPT Plus e Gemini Pro), IDEs agênticas (Antigravity, Cursor), APIs (OpenRouter, DeepSeek), planos 100% gratuitos (Free Tiers) e modelos rodando localmente ou em outro computador mais forte na rede doméstica via SSH.
2. **Divisão em Múltiplas Sessões Simultâneas (Paralelismo Real):** Diante de uma tarefa grande (ex: *"Construa uma aplicação completa de uma barbearia"*), o orquestrador avalia o tamanho e a dificuldade de cada frente e abre várias sessões ao mesmo tempo — onde uma IA faz o planejamento e arquitetura, outra cria o código de interface, outra constrói o banco/testes e outra atualiza a documentação simultaneamente.
3. **Continuidade entre Modelos (Começar em uma IA, Terminar em Outra):** Permite definir sua IA preferida por etapa ou iniciar uma tarefa em um modelo (ex: Claude Pro) e transferir o contexto automaticamente para outro modelo (ex: ChatGPT Plus ou Gemini Pro) finalizar.
4. **Retomada Automática de Geração (Auto-Resume quando os tokens acabam):** Inspirado no comportamento do Claude, se os tokens de uma assinatura acabarem exatamente no meio da geração de um código, o orquestrador guarda o trecho gerado e pode **aguardar os tokens voltarem para retomar sozinho do ponto exato** (Modo Persistente) ou **passar o código cortado instantaneamente para outra IA terminar** (Modo Failover/Relay).

---

## 2. Arquitetura Geral do Sistema

O `hydra-orch` atua como um middleware local que expõe uma API compatível com o padrão OpenAI (`http://localhost:8000/v1/chat/completions`) para agentes de engenharia de software na ponta frontal, enquanto controla todas as interfaces, IDEs e túneis SSH nos bastidores:

```
+-----------------------------------------------------------------------------+
| CAMADA 1: ENTRADA & AGENTES DE ENGENHARIA DE SOFTWARE                       |
| - CLI Direta: `hydra run "Construa um app de barbearia" --mode 1`           |
| - Agentes SWE Conectados: Cline (VS Code) | Aider | OpenCode | OpenHands    |
+-----------------------------------------------------------------------------+
                                       │
                                       ▼ (HTTP POST /v1/chat/completions)
+-----------------------------------------------------------------------------+
| CAMADA 2: NÚCLEO DO ORQUESTRADOR (Hydra Core Engine - Python/FastAPI)       |
| - Analisador de Tamanho e Dificuldade (Task Decomposer & Router)            |
| - Gerenciador dos Modos de Operação (Modo 1 Swarm | Modo 2 Relay | Modo 3)  |
| - Stream Checkpointer & Code Stitcher (SQLite Buffer + Auto-Resume Timer)   |
| - Sincronizador de Isolamento Git (Git Worktrees Manager + Auto-Merge)      |
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
| - Gemini Pro    |     | - Gemini CLI                |     | - PC Forte em   |
| - DeepSeek Web  |     | - OpenRouter / DeepSeek API |     |   Casa via SSH  |
| - Contas Free   |     | - Modelos Free API          |     |   (Porta 11435) |
+-----------------+     +-----------------------------+     +-----------------+
```

---

## 3. Conectores Universais (Plug-and-Play)

O usuário configura livremente o que tem disponível no seu ambiente. O `hydra-orch` não se prende a ferramentas fixas e suporta quatro classes de conectores:

| Classe de Conector | Ferramentas e Planos Suportados | Como o Orquestrador Controla Sem Trabalho Manual |
| :--- | :--- | :--- |
| **1. Conector de Interface Gráfica (UI / CDP + RPA)** | **Claude** (Pro / Free)<br>**ChatGPT** (Plus / Free)<br>**Gemini** (Pro / Free)<br>**DeepSeek Web** | Conecta aos apps desktop instalados (Electron) e janelas dedicadas via *Chrome DevTools Protocol* (`localhost:9222` a `9229`) usando Playwright Async. Injeta prompts, monitora o streaming em background sem roubar o foco do mouse/teclado e possui fallback para automação de acessibilidade do SO (`pywinauto`/AppleScript). |
| **2. Conector de IDEs Agênticas e CLIs** | **Google Antigravity**<br>**Cursor**<br>**Windsurf**<br>**Gemini CLI** | Aciona as ferramentas nativas via linha de comando (`antigravity`, `cursor`, `gemini`), extensões ponte (IPC Bridge) ou workspaces isolados, delegando criação e refatoração direta de módulos. |
| **3. Conector de APIs e Gateways** | **OpenRouter**<br>**DeepSeek API**<br>**Groq**<br>**Anthropic / OpenAI API** | Chamadas HTTP REST / SSE assíncronas diretas. Suporta tanto chaves pagas por uso quanto a rotação de modelos gratuitos do OpenRouter (`:free`). |
| **4. Conector Local e PC Remoto via SSH** | **Ollama**<br>**LM Studio**<br>**vLLM** (na máquina atual ou em outro PC mais forte) | Conecta ao servidor local (`localhost:11434`) ou abre automaticamente um túnel SSH em segundo plano (`ssh -N -L 11435:127.0.0.1:11434 user@ip-pc-forte`) para consumir a placa de vídeo (GPU) de outro computador em casa como se estivesse local. |

### 3.1. Como o Gemini Pro é Utilizado em Interface Local
Para garantir que o **Gemini Pro** opere como um aplicativo local igual ao Claude Desktop e ao ChatGPT Desktop, o orquestrador suporta três métodos configuráveis:
1. **App Desktop via PWA/Chromium (`--app`):** O orquestrador inicializa o binário do navegador em modo aplicativo dedicado (`--app=https://gemini.google.com --remote-debugging-port=9224 --user-data-dir=~/.hydra/gemini-profile`), expondo todo o DOM para abrir múltiplas sessões simultâneas em segundo plano.
2. **Google Antigravity & Gemini CLI:** Execução direta através da IDE agêntica Antigravity ou pelo terminal autenticado do Gemini CLI.
3. **Google AI Studio (Janela Dedicada):** Controlado via CDP para tarefas que exigem janela de contexto de até $2\text{M}$ de tokens e ajuste de temperatura.

---

## 4. Os Modos de Operação Configuráveis pelo Usuário

O usuário pode escolher na configuração (`config.yaml`) ou por linha de comando como o orquestrador deve gerar as respostas e coordenar as IAs:

### Modo 1: Enxame Paralelo Multi-Sessão (Swarm Mode)
* **Como funciona:** Quando o usuário envia um comando complexo (ex: *"Construa uma aplicação de uma barbearia"*), o orquestrador não faz uma fila lenta. Ele calcula o **tamanho e a dificuldade** de cada parte do projeto, divide em frentes independentes e abre **várias sessões ao mesmo tempo**.
* **Alocação Inteligente por Especialidade:**
  * *Planejamento, Arquitetura e Regras Críticas de Backend (Dificuldade Alta):* **Claude Pro** ou **Google Antigravity**.
  * *Criação de Código Frontend, UI e Integração Fullstack (Dificuldade Média/Alta):* **ChatGPT Plus** ou **Cursor**.
  * *Banco de Dados, Migrations SQL, Seeds e Testes Automatizados (Volume/Repetição):* **DeepSeek**, **OpenRouter** ou **PC Forte via SSH (Ollama)**.
  * *Documentação Viva, Leitura de Repositório Completo e Revisão de Contratos (Contexto Amplo):* **Gemini Pro**.

### Modo 2: Esteira Sequencial com Troca de IA e Failover Instantâneo (Relay Mode)
* **Como funciona:** Permite começar a tarefa com uma LLM e terminar com outra de forma encadeada (`IA 1 Planeja -> IA 2 Codifica -> IA 3 Testa -> IA 4 Documenta`).
* **Hot-Handoff no Meio da Geração:** Se a IA que está gerando o código atingir o limite de tokens da assinatura aos $60\%$ do arquivo, o orquestrador não perde nada: ele captura os $60\%$ já gerados e transfere no mesmo segundo para a próxima IA configurada terminar os $40\%$ restantes a partir da exata linha onde parou.

### Modo 3: Foco Persistente com Auto-Resume (Estilo Nativo Claude)
* **Como funciona:** O usuário define sua IA favorita como obrigatória para a tarefa (ex: **Claude Pro**).
* **Retomada Automática Pós-Limite:** Quando os tokens do Claude Pro acabam no meio de uma geração, o orquestrador:
  1. Salva imediatamente todo o texto/código parcial gerado até o momento do corte em um banco SQLite local.
  2. Lê na interface gráfica do Claude o horário exato em que os tokens serão liberados (ex: *"Limite atingido. Volta às 19:00"*).
  3. Coloca a tarefa em estado de espera automática com um cronômetro regressivo.
  4. No segundo exato em que os tokens voltam, envia automaticamente o comando de continuação (ou clica no botão nativo de continuar do app), junta as duas metades do código sem duplicar linhas e entrega ao agente de código.

### Perfil Flexível: Suporte Total para Usuários Apenas com Planos Free + Local/SSH
* Se o usuário configurar o `hydra-orch` possuindo **apenas contas gratuitas** (Claude Free, ChatGPT Free, Gemini Free, DeepSeek Free, OpenRouter Free) combinadas ou não com uma **LLM Local / SSH**, o orquestrador ativa o **Pool de Rotação Automática**:
  * Tarefas pesadas de arquitetura usam a cota gratuita do Claude Free até esgotar, rotacionando automaticamente para DeepSeek, ChatGPT Free e Gemini Free.
  * Tarefas auxiliares (testes, formatação, boilerplate, resumos de arquivos) são desviadas para a LLM local ou para o PC forte via SSH, economizando $100\%$ das mensagens gratuitas da nuvem para os momentos críticos.

---

## 5. Exemplo Prático Completo: Projeto "Aplicação de Barbearia" em Múltiplas Sessões

Veja o que acontece nos bastidores quando o usuário digita um único comando:
```bash
hydra run "Construa uma aplicação completa de uma barbearia com agendamento de clientes, painel de barbeiros, cálculo de comissão e pagamento" --mode 1
```

### Fase 1: Análise de Dificuldade e Contrato Base (~30 segundos)
1. O módulo `router.py` avalia o pedido e solicita ao modelo arquiteto principal (ex: **Claude Pro**) a geração de um **Contrato Técnico Compartilhado** (`contract.json`).
2. Esse contrato define os nomes exatos das tabelas do banco, rotas de API REST (`POST /api/appointments`, `GET /api/barbers`), variáveis de ambiente e interfaces TypeScript.
3. O orquestrador divide o projeto em 4 sub-tarefas pontuadas por **tamanho (tokens estimados)** e **dificuldade ($1\text{ a }10$)**.

### Fase 2: Criação de Git Worktrees e Disparo das 4 Sessões Simultâneas
Para que as 4 IAs trabalhem ao mesmo tempo no mesmo projeto sem que uma apague o arquivo da outra, o módulo `swarm.py` cria 4 pastas/branches isoladas via **Git Worktrees** e dispara todas em paralelo:

```
                    [Contrato Base: contract.json]
                                  │
      ┌───────────────────────────┼───────────────────────────┐
      ▼                           ▼                           ▼
[Sessão Paralela 1]        [Sessão Paralela 2]        [Sessão Paralela 3]        [Sessão Paralela 4]
Branch: feat/backend       Branch: feat/frontend      Branch: feat/db-tests      Branch: feat/docs
IA: Claude Pro /           IA: ChatGPT Plus /         IA: PC Forte via SSH       IA: Gemini Pro
    Antigravity                Cursor                     ou DeepSeek            Dificuldade: 5/10
Dificuldade: 9/10          Dificuldade: 7/10          Dificuldade: 5/10          Contexto: Repositório Todo
--------------------       --------------------       --------------------       --------------------
Cria regras complexas      Cria em paralelo as        Gera migrations SQL,       Lê o código das 3 frentes
de conflito de agenda,     telas React/Next.js,       schemas Prisma, seeds      em tempo real, atualiza
bloqueio de horários       calendário visual do       de barbeiros/serviços e    README.md, documentação
e cálculo de comissão.     cliente e dashboard.       testes unitários/E2E.      Swagger e checa tipos.
```

### Fase 3: Sincronização, Auto-Merge e Validação Autônoma
1. Conforme cada sessão paralela finaliza seus arquivos (com detecção automática de fim de geração), o `hydra-orch` faz o commit na respectiva branch.
2. O sincronizador une (`git merge`) todas as branches na branch principal.
3. O orquestrador roda os testes automatizados gerados pela Sessão 3. Se houver qualquer erro de compilação ou incompatibilidade entre o Backend (Claude) e o Frontend (GPT), o orquestrador abre automaticamente uma rodada cirúrgica de correção enviando o log de erro para a IA responsável.

---

## 6. Mecanismos Técnicos de Automação e Resiliência

### 6.1. Stream Checkpointer & Code Stitcher (`checkpointer.py`)
Garante que nenhum código seja perdido se os tokens acabarem no meio de uma resposta:
* **Monitoramento Contínuo:** Lê os blocos de texto gerados na interface gráfica ou stream de API a cada $500\text{ ms}$ e salva na tabela `active_generations` do SQLite (`.hydra/state.db`).
* **Detecção de Limite de Cota:** Identifica banners e elementos DOM específicos de bloqueio (ex: alerta de limite de 5 horas no Claude Pro, aviso de queda de modelo no ChatGPT Plus ou `HTTP 429` em APIs).
* **Costura Perfeita (Code Stitching):** Ao retomar a geração (seja no próprio Claude quando os tokens voltam ou em outra IA via Hot-Swap), o orquestrador pega as últimas 15 linhas do código salvo antes do corte e injeta o prompt de sistema:
  > *"A geração anterior foi interrompida por limite de tokens exatamente na última linha abaixo. Continue escrevendo o código a partir do próximo caractere, mantendo a indentação e sem repetir o trecho já gerado: [ÚLTIMAS 15 LINHAS]"*.
  Em seguida, concatena a Parte 1 com a Parte 2 de forma invisível.

### 6.2. Detecção de Fim de Geração e Proteção do Clipboard (`ui_cdp.py`)
* **End-of-Stream:** O driver sabe que uma IA terminou de responder quando o botão `Stop Generating` desaparece do DOM e os ícones de ação (`Copy`, `Regenerate`) ficam ativos por $1.5\text{ s}$ consecutivos.
* **Extração Limpa de Markdown:** Para evitar erros de formatação HTML ao ler blocos de código da tela, o driver aciona programaticamente o botão nativo **"Copy"** da resposta da IA.
* **Clipboard Guard:** Caso precise usar a área de transferência do sistema operacional, o orquestrador faz backup imediato do `Ctrl+C` atual do usuário na memória RAM, captura o Markdown da IA em menos de $50\text{ ms}$ e restaura o `Ctrl+C` original do usuário para não atrapalhar seu uso do computador.

### 6.3. Gerenciador de Túnel SSH Automático (`ssh_tunnel.py`)
Para usar uma LLM rodando em outro PC mais forte em casa:
* O orquestrador gerencia um processo persistente de redirecionamento de porta:
  ```bash
  ssh -o ServerAliveInterval=15 -o ExitOnForwardFailure=yes -N -L 11435:127.0.0.1:11434 usuario@ip-do-pc-forte
  ```
* Inclui *Healthcheck* a cada 10 segundos: se o PC forte em casa estiver desligado ou se o usuário estiver fora da rede local (sem VPN/Tailscale), o orquestrador desativa temporariamente o nó SSH e redistribui as tarefas para as demais IAs configuradas sem travar a execução.

---

## 7. Agentes de Engenharia de Software Utilizados

Para não reinventar editores de arquivos, executores de terminal ou manipuladores de Git, o `hydra-orch` funciona nativamente integrado aos melhores agentes de Engenharia de Software do mercado através do seu servidor local (`http://localhost:8000/v1`):

| Agente SWE | Onde Roda | Papel no Desenvolvimento | Como Opera com o `hydra-orch` |
| :--- | :--- | :--- | :--- |
| **Cline** | Extensão VS Code / Cursor / Antigravity | Agente autônomo que cria/edita arquivos, roda comandos no terminal, lê erros de build e corrige sozinho (modo `Auto-Approve`). | Configurado como provedor `OpenAI Compatible` apontando para `localhost:8000/v1`. O Plan Mode e o Act Mode do Cline são roteados automaticamente pelo Hydra para as melhores IAs. |
| **Aider** | Terminal CLI | Especialista em edições multi-arquivo complexas, refatoração de repositórios grandes e commits automáticos no Git. | Executado via `aider --openai-api-base http://localhost:8000/v1`. Aproveita o modo Architect/Editor dividindo raciocínio e edição entre duas LLMs diferentes. |
| **OpenCode** | Terminal / Desktop | Agente modular open-source com execução em background (`opencode run`) e suporte a MCP. | Usado pelo próprio motor de enxame (`swarm.py`) como trabalhador ("worker") dentro de cada Git Worktree nas sessões paralelas. |
| **OpenHands** | Docker / Interface Web | Engenheiro de software completo operando em sandbox isolado com navegador, terminal e editor próprios. | Aponta para `host.docker.internal:8000/v1`, ideal para delegar issues inteiras do GitHub para rodarem sozinhas. |

---

## 8. Especificação Completa do Arquivo de Configuração (`config.yaml`)

O arquivo abaixo representa toda a flexibilidade que o usuário tem para cadastrar suas ferramentas, definir sua IA preferida, configurar o PC remoto via SSH e escolher entre os Modos 1, 2 e 3:

```yaml
orchestrator:
  project_name: "hydra-orch"
  server_host: "127.0.0.1"
  server_port: 8000
  default_mode: 1 # 1: Swarm Paralelo | 2: Relay Sequencial | 3: Persistente Auto-Resume
  preferred_primary_llm: "claude_pro"
  enable_free_tier_rotation: true
  git_worktree_dir: ".orchestrator/worktree"
  state_db_path: ".orchestrator/checkpoints.sqlite"

# =====================================================================
# CADASTRO UNIVERSAL DE PROVEDORES (Use apenas os que você tiver)
# =====================================================================
providers:
  claude_pro:
    enabled: true
    connector: "ui_cdp"
    plan_tier: "pro" # 'pro' ou 'free'
    cdp_port: 9222
    app_executable: "claude"
    max_concurrent_tabs: 2
    strengths: ["architecture", "planning", "complex_backend", "refactoring"]
    min_difficulty: 7
    on_token_limit: "wait_and_resume" # Opções: wait_and_resume | instant_hot_swap

  chatgpt_plus:
    enabled: true
    connector: "ui_cdp"
    plan_tier: "plus" # 'plus' ou 'free'
    cdp_port: 9223
    app_executable: "chatgpt"
    max_concurrent_tabs: 3
    strengths: ["frontend", "coding", "fullstack", "debugging"]
    min_difficulty: 5
    on_token_limit: "instant_hot_swap"

  gemini_pro:
    enabled: true
    connector: "ui_cdp"
    plan_tier: "pro" # 'pro' ou 'free'
    cdp_port: 9224
    launch_mode: "pwa_app" # Opções: pwa_app | antigravity | gemini_cli | ai_studio
    app_args: ["--app=https://gemini.google.com", "--remote-debugging-port=9224"]
    max_concurrent_tabs: 3
    strengths: ["documentation", "large_context", "code_review", "research"]
    min_difficulty: 4
    on_token_limit: "instant_hot_swap"

  antigravity:
    enabled: true
    connector: "ide_bridge"
    cli_command: "antigravity"
    strengths: ["autonomous_engineering", "complex_backend", "multi_file_edit"]
    min_difficulty: 8

  cursor_ide:
    enabled: false # O usuário ativa se quiser usar o Cursor no fluxo
    connector: "ide_bridge"
    cli_command: "cursor"
    strengths: ["frontend", "ui_components", "fast_edits"]
    min_difficulty: 6

  deepseek_provider:
    enabled: true
    connector: "ui_cdp_or_api" # Pode usar a interface web gratuita ou API
    cdp_port: 9225
    api_base_url: "https://api.deepseek.com/v1"
    strengths: ["database_sql", "unit_tests", "algorithms", "boilerplate"]
    min_difficulty: 4

  openrouter_gateway:
    enabled: true
    connector: "api_gateway"
    base_url: "https://openrouter.ai/api/v1"
    use_free_models_fallback: true
    preferred_models:
      - "deepseek/deepseek-chat:free"
      - "qwen/qwen-2.5-coder-32b-instruct:free"
    strengths: ["unit_tests", "seeds", "fallback_coding"]
    min_difficulty: 1

  llm_local_maquina_atual:
    enabled: true
    connector: "local_engine"
    engine: "ollama"
    base_url: "http://127.0.0.1:11434/v1"
    model: "qwen2.5-coder:7b"
    strengths: ["task_classification", "quick_fixes", "formatting"]
    min_difficulty: 1

  pc_forte_casa_ssh:
    enabled: true
    connector: "remote_ssh"
    ssh_user_host: "usuario@192.168.1.100"
    ssh_port: 22
    ssh_key_path: "~/.ssh/id_ed25519"
    local_tunnel_port: 11435
    remote_engine_port: 11434
    engine: "ollama" # Suporta ollama, vllm ou lmstudio no PC remoto
    model: "qwen2.5-coder:32b"
    strengths: ["backend_coding", "database_sql", "unit_tests", "offline_heavy_work"]
    min_difficulty: 5

# =====================================================================
# CONFIGURAÇÃO DOS 3 MODOS DE EXECUÇÃO
# =====================================================================
modes:
  modo_1_swarm:
    description: "Abre várias sessões de uma vez dividindo por tamanho e dificuldade"
    contract_architect: "claude_pro"
    max_parallel_sessions: 4
    role_mapping:
      planning_and_core_backend: ["claude_pro", "antigravity"]
      frontend_and_code_creation: ["chatgpt_plus", "cursor_ide"]
      database_migrations_and_tests: ["pc_forte_casa_ssh", "deepseek_provider", "openrouter_gateway"]
      documentation_and_context_sync: ["gemini_pro"]

  modo_2_relay:
    description: "Começa a task em uma LLM e termina em outra (com failover imediato)"
    default_chain:
      - step: "planejamento"
        provider: "claude_pro"
      - step: "implementacao"
        provider: "chatgpt_plus"
      - step: "testes"
        provider: "pc_forte_casa_ssh"
      - step: "documentacao"
        provider: "gemini_pro"
    mid_stream_failover: true

  modo_3_persistent:
    description: "Foco na IA preferida; se os tokens acabarem no meio, espera voltar e retoma sozinho"
    locked_provider: "claude_pro"
    auto_resume_check_interval_seconds: 30
    stitch_anchor_lines: 15
```

---

## 9. Estrutura do Repositório (`hydra-orch`)

Estrutura modular pronta para implementação em Python 3.11+:

```text
hydra-orch/
├── config.yaml                      # Configuração universal de assinaturas, SSH e modos
├── pyproject.toml                   # Dependências e registro do comando global 'hydra'
├── README.md                        # Documentação do repositório
└── src/
    └── hydra_orch/
        ├── __init__.py
        ├── cli.py                   # Comandos: hydra serve, hydra run, hydra status
        ├── server.py                # Proxy FastAPI compatível com OpenAI (:8000/v1)
        ├── core/
        │   ├── __init__.py
        │   ├── config_loader.py     # Validação Pydantic do config.yaml
        │   ├── router.py            # Avaliador de tamanho/dificuldade e escolha de IA
        │   ├── swarm.py             # Modo 1: Decompositor, Contrato Base e Git Worktrees
        │   ├── relay.py             # Modo 2: Pipeline encadeado (Começa em A, termina em B)
        │   ├── checkpointer.py      # Modo 3: Buffer SQLite, Auto-Resume e Code Stitcher
        │   └── ssh_tunnel.py        # Túnel SSH automático para o PC forte em casa
        └── adapter/
            ├── __init__.py
            ├── base.py              # Interface abstrata UniversalProviderAdapter
            ├── ui_cdp.py            # Playwright CDP + Clipboard Guard (Claude/GPT/Gemini)
            ├── ide_bridge.py        # Conector Antigravity, Cursor e Gemini CLI
            ├── api_gateway.py       # Conector OpenRouter e DeepSeek API
            └── local_remote.py      # Conector Ollama / vLLM local e via túnel SSH
```

---

## 10. Roadmap de Implementação no Antigravity

1. **Etapa 1 — Fundação, Config e Túnel SSH (`core/config_loader.py` + `core/ssh_tunnel.py`):**
   * Leitura do `config.yaml`, criação da CLI (`hydra`) e abertura automática do túnel SSH para o PC remoto com healthcheck.
2. **Etapa 2 — Conector de Interfaces Gráficas e Auto-Resume (`adapter/ui_cdp.py` + `core/checkpointer.py`):**
   * Conexão CDP nas janelas do Claude Pro, ChatGPT Plus e Gemini Pro (`--app`), detecção de fim de streaming, proteção de Clipboard e motor de retomada automática quando os tokens acabam no meio da geração (Modo 3) ou costura em outra IA (Modo 2).
3. **Etapa 3 — Motor Multi-Sessão Paralelo e Git Worktrees (`core/swarm.py` + `core/router.py`):**
   * Decomposição de projetos grandes por tamanho e dificuldade, geração do `contract.json` e abertura de múltiplas sessões simultâneas isoladas por branches Git (Modo 1).
4. **Etapa 4 — Servidor Proxy OpenAI para Agentes SWE (`server.py`):**
   * Exposição do endpoint `http://localhost:8000/v1/chat/completions` para plugar o Cline, Aider, OpenCode ou Antigravity.