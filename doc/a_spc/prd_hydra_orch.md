# PRD: Hydra-Orch — Orquestrador Autônomo Multi-Sessão de Engenharia de Software

**Projeto / Repositório:** `hydra-orch` (Binário CLI: `hydra`)
**Versão:** 5.0 (Arquitetura sobre OmniRoute + Inteligência de Engenharia de Software)
**Foco Principal:** Desenvolvimento e Engenharia de Software $100\%$ Automatizados (Zero Trabalho Manual)
**Motor de Conexão Base:** OmniRoute Gateway (OAuth oficial de CLIs, APIs, Free Tiers) + Túnel SSH Automático
**Ecossistema Suportado:** Claude (Pro/Free), ChatGPT/Codex (Plus/Free), Gemini (Pro/Free/CLI), Google Antigravity, Cursor, DeepSeek, OpenRouter, LLMs Locais (Ollama/LM Studio/vLLM) e GPU Remota em outro PC em casa via SSH.

---

## 1. Visão Geral e o Diferencial Único do `hydra-orch`

A pesquisa de mercado revelou que o ecossistema open-source atual possui ferramentas separadas para dois problemas distintos:
1. **Gateways de Assinatura (ex: OmniRoute):** Unificam assinaturas de $\text{US\$ } 20$ (Claude Pro, ChatGPT Plus, Gemini Pro), planos gratuitos e modelos locais via autenticação OAuth de CLI (sem depender de automação frágil de mouse/tela), rastreando a janela de $5\text{ h}$ de cota e fazendo fallback em $< 1\text{ s}$. Porém, o OmniRoute é apenas um roteador de rede: ele **não sabe decompor projetos de software**, não cria contratos de arquitetura nem gerencia múltiplas branches trabalhando juntas.
2. **Gerenciadores de Git Worktrees (ex: Parallel Code, Claude Squad, Crewly):** Criam pastas isoladas para agentes de código, mas carecem de um motor que gere um **Contrato Técnico Imutável** antes de disparar os agentes (para que o Frontend e o Backend não entrem em conflito) e não possuem **costura de código no meio do stream (Auto-Resume & Code Stitching)** quando os tokens acabam na metade de um arquivo.

### A Proposta de Valor do `hydra-orch`
Em vez de reinventar conectores frágeis de scraping em Playwright, o **`hydra-orch`** utiliza o **OmniRoute** por baixo dos panos como sua camada de conectividade e concentra $100\%$ do seu código nos **4 motores de inteligência de Engenharia de Software que não existem integrados no mercado**:

1. **Decompositor de Tarefas por Tamanho e Dificuldade (`Task Decomposer`):** Recebe um prompt macro (ex: *"Construa uma aplicação completa de uma barbearia"*), pontua cada módulo de $1\text{ a }10$ em dificuldade e aloca o melhor modelo combinando especialidade técnica com a cota restante informada pelo OmniRoute.
2. **Gerador de Contrato Base Imutável (`Contract-First Engine`):** Antes de abrir sessões paralelas, gera um contrato unificado (`openapi.yaml`, `schema.prisma`, `interfaces.ts`) que trava rotas, tabelas e variáveis compartilhadas entre todas as IAs.
3. **Orquestrador de Enxame em Git Worktrees (`Multi-Session Swarm`):** Abre múltiplas sessões simultâneas (Claude no Backend, GPT no Frontend, PC Forte via SSH no Banco/Testes, Gemini na Documentação), faz o merge automático e roda testes de integração sozinho.
4. **Motor de Auto-Resume e Costura de Código (`Stream Checkpointer & Stitcher`):** Intercepta a geração em tempo real; se os tokens do Claude Pro acabarem aos $60\%$ de um arquivo, salva o código parcial em SQLite e permite **esperar a cota de $5\text{ h}$ voltar para retomar sozinho da mesma linha (Modo 3)** ou **costurar os $40\%$ restantes instantaneamente em outra IA (Modo 2)**.

---

## 2. Arquitetura do Sistema em 4 Camadas

O `hydra-orch` expõe a porta `8000` (`http://localhost:8000/v1`) para o desenvolvedor ou agente principal, orquestra trabalhadores paralelos em Git Worktrees e consome o OmniRoute na porta `20128` combinado com o túnel SSH na porta `11435`:

```
+--------------------------------------------------------------------------------+
| CAMADA 1: ENTRADA DO DESENVOLVEDOR & AGENTES FRONTAIS                          |
| - Comando Direto: `hydra run "Construa uma aplicação de barbearia" --mode 1`   |
| - IDE / Agente Conectado: Google Antigravity | Cursor | Cline | Aider          |
+--------------------------------------------------------------------------------+
                                        │
                                        ▼ (HTTP POST localhost:8000/v1)
+--------------------------------------------------------------------------------+
| CAMADA 2: HYDRA-ORCH CORE ENGINE (A Inteligência de Engenharia de Software)    |
| 1. Analisador de Tamanho e Dificuldade (1 a 10) + Consulta de Cota OmniRoute   |
| 2. Gerador de Contrato Base Imutável (OpenAPI + DB Schema + Types)             |
| 3. Gerenciador dos 3 Modos (Modo 1: Swarm | Modo 2: Relay | Modo 3: Persist)   |
| 4. Stream Checkpointer & Code Stitcher (SQLite Buffer + Auto-Resume Timer)     |
| 5. SSH Tunnel Manager (Auto-Forwarding e Healthcheck para o PC Forte em Casa)  |
+--------------------------------------------------------------------------------+
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
[Worktree 1: Backend]         [Worktree 2: Frontend]        [Worktree 3: DB/QA & Docs]
Worker: Claude Code/OpenCode  Worker: Codex/OpenCode        Worker: Gemini CLI/Aider
          │                             │                             │
          └─────────────────────────────┼─────────────────────────────┘
                                        ▼
+--------------------------------------------------------------------------------+
| CAMADA 3: GATEWAY DE CONEXÃO UNIFICADO (OmniRoute :20128 + Túnel SSH :11435)   |
| - OAuth Oficial Assinaturas ($20): Claude Pro | ChatGPT Plus | Gemini Pro      |
| - Integrações Nativas: Google Antigravity | Cursor | GitHub Copilot            |
| - Rotação de Planos Free & APIs: DeepSeek | OpenRouter (:free) | Groq          |
| - Nó Local & Remoto (SSH): Ollama / vLLM local (:11434) e PC Forte (:11435)    |
| - Fallback UI/CDP (Opcional): Apenas para ferramentas web sem suporte OAuth    |
+--------------------------------------------------------------------------------+
```

---

## 3. Como Todas as Assinaturas, Planos Free e o PC via SSH são Conectados

Ao adotar o **OmniRoute** como sub-camada de transporte e o **SSH Tunnel Manager** nativo do Hydra, o usuário configura qualquer combinação de ferramentas sem precisar de chaves de API caras:

| Provedor / Recurso | Plano do Usuário | Como Conecta no `hydra-orch` (Zero Trabalho Manual) | Papel Principal na Engenharia de Software |
| :--- | :--- | :--- | :--- |
| **Claude** | **Pro** ou **Free** | Via OAuth nativo do Claude CLI no OmniRoute (com rastreamento exato da janela de $5\text{ h}$). | Planejamento arquitetural, geração do Contrato Base e código crítico de Backend. |
| **ChatGPT / Codex** | **Plus** ou **Free** | Via OAuth nativo do Codex CLI no OmniRoute (com rastreamento de cota semanal/horária). | Criação de código Frontend (React/Next.js), componentes de UI e lógica Fullstack. |
| **Gemini** | **Pro** ou **Free** | Via OAuth do Gemini CLI / Google AI Studio no OmniRoute ou janela PWA dedicada (`--app`). | Leitura do repositório inteiro (contexto de $1\text{M}\text{–}2\text{M}$ tokens), atualização de documentação e revisão de contratos. |
| **Google Antigravity & Cursor** | **Pro / Free** | Conector de IDE Agêntica e rota integrada no OmniRoute. | Execução autônoma multi-arquivo e edição direta em workspaces isolados. |
| **DeepSeek & OpenRouter** | **Free** ou **Pay-per-use** | Rotas `auto/free` e Smart Combos do OmniRoute (rotacionando modelos `:free` como DeepSeek V3/R1 e Qwen Coder). | Geração de migrations SQL, seeds de banco de dados, boilerplate e suítes de testes. |
| **LLM Local (Mesma Máquina)** | **Gratuito (100% Local)** | Servidor local Ollama / LM Studio (`localhost:11434`) registrado no OmniRoute. | Classificação instantânea de complexidade de prompts e tarefas leves offline. |
| **PC Mais Forte em Casa (SSH)** | **Gratuito (GPU Remota)** | O módulo `ssh_tunnel.py` do Hydra abre túnel SSH automático (`localhost:11435 -> pc-forte:11434`) e o registra como nó de alta performance. | Processamento pesado sem custo de cota (geração massiva de testes unitários/E2E, refatoração e fallback offline). |

---

## 4. Os 3 Modos de Operação Configuráveis pelo Usuário

O desenvolvedor escolhe no `config.yaml` ou via flag (`hydra run --mode X`) como o orquestrador vai operar:

### Modo 1: Enxame Paralelo em Múltiplas Sessões (`Contract-First Swarm Mode`)
* **Ideal para:** Criar aplicações inteiras, módulos completos ou features grandes a partir de um único comando.
* **Comportamento:** O `hydra-orch` analisa o tamanho e a dificuldade do pedido, gera o Contrato Base em $\sim 20\text{ s}$ e abre **várias sessões ao mesmo tempo** em Git Worktrees separadas. Enquanto o **Claude Pro** planeja e codifica as regras críticas de negócio, o **ChatGPT Plus** constrói as telas, o **PC Forte via SSH (ou DeepSeek)** cria o banco e os testes, e o **Gemini Pro** atualiza a documentação viva do projeto.

### Modo 2: Esteira Sequencial com Troca de IA e Failover Instantâneo (`Relay Mode`)
* **Ideal para:** Começar uma task em uma LLM específica e terminar em outra (`Planejamento no Claude -> Código no GPT -> Testes no DeepSeek/SSH -> Docs no Gemini`).
* **Hot-Handoff Instantâneo no Meio do Arquivo:** Se a IA ativa atingir o limite de tokens da assinatura no meio da escrita de um código, o `hydra-orch` aciona o fallback em $< 1\text{ s}$, pega o código parcial salvo no buffer SQLite e injeta na próxima IA configurada para terminar apenas as linhas restantes, entregando o arquivo costurado sem interrupção.

### Modo 3: Foco Persistente com Auto-Resume (`Persistent Claude Mode`)
* **Ideal para:** Quando o usuário exige que uma única IA preferida (ex: **Claude Pro**) execute toda a tarefa mantendo $100\%$ de consistência arquitetural.
* **Retomada Automática quando os Tokens Voltam:**
  1. Se a janela de $5\text{ h}$ do Claude Pro acabar aos $65\%$ da geração, o `Stream Checkpointer` salva exatamente o que foi gerado até o último caractere.
  2. O `hydra-orch` consulta a API de cota do OmniRoute (`/api/usage/quota`) para saber o segundo exato do reset da janela de $5\text{ h}$.
  3. A sessão entra em estado de hibernação automática com um cronômetro no terminal (sem perder o contexto).
  4. Assim que a cota do Claude Pro é liberada, o `hydra-orch` acorda sozinho, envia as últimas 15 linhas como âncora de continuação, costura o restante do código e aplica no projeto sem que o usuário precise tocar no teclado.

### Operação Universal para Quem Só Tem Planos Free ou Local/SSH
* Se o usuário configurar o `hydra-orch` apenas com contas gratuitas (Claude Free, ChatGPT Free, Gemini Free, OpenRouter Free) e/ou uma LLM local/SSH, o orquestrador vincula a rota `auto/free` do OmniRoute ao seu Decompositor de Tarefas:
  * Preserva os tokens escassos do Claude Free e GPT Free exclusivamente para decisões de arquitetura de dificuldade $\ge 8$.
  * Descarrega toda a escrita bruta de código, testes e documentação para o **Gemini Free**, **OpenRouter Free (`qwen-2.5-coder:free`, `deepseek:free`)** e **PC Forte via SSH**.

---

## 5. Detalhamento dos 3 Motores Exclusivos do `hydra-orch`

### 5.1. Motor 1: Decompositor e Enxame Multi-Sessão (Exemplo: "Aplicação de Barbearia")

Quando o usuário executa:
```bash
hydra run "Construa uma aplicação completa de uma barbearia com agendamento, painel de barbeiros e pagamento" --mode 1
```
O `hydra-orch` executa **4 fases automatizadas**:

#### Fase A: Avaliação de Tamanho/Dificuldade e Geração do Contrato Base (`contract.py`)
Para que 4 IAs trabalhando ao mesmo tempo não criem nomes de rotas ou colunas de banco diferentes, o orquestrador chama o modelo arquiteto (`claude_pro`) para gerar um pacote de contrato imutável na pasta `.hydra/contracts/`:
* `schema.prisma` (ou SQL DDL): Define as tabelas `User`, `Barber`, `Service`, `Appointment` e `Payment`.
* `openapi.json`: Define todos os endpoints (`GET /api/barbers`, `POST /api/appointments`) e seus payloads JSON.
* `task_graph.json`: Lista as sub-tarefas pontuadas por **dificuldade ($1\text{ a }10$)** e **estimativa de tokens**:
  * *Sub-tarefa 1 (Core Backend & Regras de Horário):* Dificuldade $9/10$ $\rightarrow$ Alocada para **Claude Pro / Antigravity**.
  * *Sub-tarefa 2 (Frontend Next.js, Calendário e Painel):* Dificuldade $7/10$ $\rightarrow$ Alocada para **ChatGPT Plus / Cursor**.
  * *Sub-tarefa 3 (Migrations, Seeds e Testes E2E):* Dificuldade $5/10$ $\rightarrow$ Alocada para **PC Forte via SSH (`qwen2.5-coder:32b`) ou DeepSeek**.
  * *Sub-tarefa 4 (Documentação Técnica e Auditoria de Contrato):* Dificuldade $4/10$ (Contexto Amplo) $\rightarrow$ Alocada para **Gemini Pro**.

#### Fase B: Isolamento Automático em Git Worktrees (`swarm.py`)
O `hydra-orch` cria instantaneamente 4 branches e 4 diretórios de trabalho independentes usando `git worktree add`, criando links simbólicos (`symlinks`) para `node_modules` e `.venv` para não duplicar gigabytes em disco:
* `.hydra/worktree/wt-backend` (Branch: `hydra/backend`)
* `.hydra/worktree/wt-frontend` (Branch: `hydra/frontend`)
* `.hydra/worktree/wt-db-tests` (Branch: `hydra/db-tests`)
* `.hydra/worktree/wt-docs` (Branch: `hydra/docs`)

#### Fase C: Execução Simultânea de Workers
Em cada Worktree, o `hydra-orch` dispara um trabalhador autônomo em background (usando **OpenCode CLI**, **Aider** ou os agentes nativos **Claude Code / Codex CLI / Gemini CLI**) apontando para a rota correspondente no OmniRoute e injetando o Contrato Base como regra estrita de leitura. Todas as 4 frentes codificam seus arquivos ao mesmo tempo.

#### Fase D: Auto-Merge e Loop de Validação (Self-Healing)
1. Assim que as sessões paralelas terminam, o `swarm.py` faz o merge sequencial das branches na branch de integração.
2. Executa a suíte de build e testes criada na Worktree 3 (`npm run build && npm test`).
3. Se um teste falhar (ex: o Frontend enviou um campo com formato diferente do esperado pelo Backend), o `hydra-orch` lê o `stderr`, identifica qual arquivo falhou e dispara uma micro-sessão automática apenas para corrigir o erro até o build passar com $100\%$ de sucesso.

---

### 5.2. Motor 2: Stream Checkpointer, Auto-Resume & Code Stitcher (`checkpointer.py`)

O OmniRoute gerencia o failover entre requisições, mas se uma geração de código longa cair aos $70\%$ do stream SSE, o agente de código comum falha ou descarta a resposta parcial. O `checkpointer.py` do `hydra-orch` fica posicionado **entre o Agente SWE e o OmniRoute** para garantir zero perda de tokens:

```
[Agente SWE] <─── (Conexão Mantida Viva pelo Hydra) ─── [Stream Checkpointer SQLite]
                                                                    │
                                    ┌───────────────────────────────┴───────────────────────────────┐
                                    ▼ (Stream cai aos 65% por limite de 5h no Claude Pro)           ▼
                         [Modo 3: Auto-Resume]                                           [Modo 2: Hot-Handoff]
                 Aguarda o timer de reset do OmniRoute                           Redireciona imediatamente para a
                 e retoma no Claude Pro do ponto exato                           rota GPT Plus / SSH no OmniRoute
                                    └───────────────────────────────┬───────────────────────────────┘
                                                                    ▼
                                               [Code Stitcher: Costura Parte 1 + Parte 2]
```

* **Algoritmo de Costura Sem Duplicação (`Stitching`):**
  1. O buffer SQLite armazena cada chunk SSE recebido em tempo real.
  2. Ao detectar interrupção prematura (`finish_reason != "stop"` ou erro de cota `429`), o `hydra-orch` **não fecha** a conexão HTTP com o Agente SWE (ou salva o estado da task do worker).
  3. Extrai os últimos $15$ linhas do código gerado até o momento do corte (`ANCHOR_BLOCK`).
  4. Envia uma requisição silenciosa de continuação (para o mesmo modelo após o timer no Modo 3, ou para o modelo de backup no Modo 2) com o prompt:
     > *"O arquivo abaixo foi interrompido durante a geração. Continue escrevendo o código exatamente a partir da última linha do bloco âncora abaixo. NÃO repita o bloco âncora e NÃO adicione explicações antes do código:\n\n[ANCHOR_BLOCK]"*
  5. Remove qualquer sobreposição de linhas usando comparação de sufixo/prefixo (algoritmo KMP de *string overlap*) e transmite o restante dos tokens para o agente como se a geração nunca tivesse parado.

---

### 5.3. Motor 3: Gerenciador de Túnel SSH para PC Forte em Casa (`ssh_tunnel.py`)

Para aproveitar um desktop com GPU potente na rede local (ou via Tailscale/WireGuard) sem trabalho manual:
* Ao iniciar o `hydra serve` ou `hydra run`, o `ssh_tunnel.py` verifica o `config.yaml` e sobe um sub-processo gerenciado:
  ```bash
  ssh -o BatchMode=yes -o ServerAliveInterval=10 -o ExitOnForwardFailure=yes -N -L 11435:127.0.0.1:11434 usuario@ip-pc-forte
  ```
* **Auto-Discovery e Registro no OmniRoute:** O `hydra-orch` testa `http://localhost:11435/api/tags` a cada $10\text{ s}$. Quando o túnel está ativo, ele registra automaticamente os modelos da sua GPU remota (ex: `qwen2.5-coder:32b`, `deepseek-r1:32b`) no pool de roteamento do OmniRoute com custo zero. Se você desligar o PC forte ou sair de casa, o healthcheck detecta a queda em $2\text{ s}$ e redireciona as tarefas de banco/testes para o DeepSeek/OpenRouter ou Gemini Pro automaticamente.

---

## 6. Arquivo de Configuração Unificado (`config.yaml`)

Toda a configuração do usuário fica centralizada em um único `config.yaml` que controla tanto o cérebro do `hydra-orch` quanto as rotas do **OmniRoute** e do **PC via SSH**:

```yaml
hydra:
  proxy_host: "127.0.0.1"
  proxy_port: 8000
  default_mode: 1 # 1: Swarm Multi-Sessao | 2: Relay Sequencial | 3: Persistente Auto-Resume
  preferred_primary_model: "claude-pro"
  worktree_base_dir: ".hydra/worktree"
  state_db: ".hydra/state.db"
  auto_heal_build_errors: true
  max_heal_attempts: 3

# ============================================================================
# INTEGRAÇÃO COM O OMNIROUTE GATEWAY (Conexão OAuth Assinaturas + Free Tiers)
# ============================================================================
omniroute:
  auto_start_daemon: true
  base_url: "http://127.0.0.1:20128/v1"
  quota_api_url: "http://127.0.0.1:20128/api/usage/quota"
  default_routing_strategy: "auto/thrifty" # Usa assinaturas pagas -> cai pro SSH/Free -> volta quando reseta

  # Mapeamento dos Provedores Configurados pelo Usuário no OmniRoute
  LogicalModels:
    architect_heavy:
      primary: "claude-code/claude-3-7-sonnet"     # Assinatura Claude Pro ($20) via OAuth
      fallbacks: ["antigravity/gemini-2-5-pro", "openrouter/deepseek-r1:free"]
      min_difficulty: 8

    fullstack_coder:
      primary: "codex/gpt-4o-plus"                # Assinatura ChatGPT Plus ($20) via OAuth
      fallbacks: ["cursor/claude-sonnet", "claude-code/claude-3-7-sonnet"]
      min_difficulty: 6

    context_and_docs:
      primary: "gemini-cli/gemini-2-5-pro"        # Assinatura Gemini Pro ($20) via OAuth / PWA
      fallbacks: ["ai-studio/gemini-pro-free"]
      min_difficulty: 4

    database_and_tests:
      primary: "ssh-home-gpu/qwen2.5-coder:32b"   # PC Forte em Casa via Túnel SSH
      fallbacks: ["deepseek/deepseek-chat", "openrouter/qwen-2.5-coder-32b-instruct:free"]
      min_difficulty: 3

    fast_classifier:
      primary: "local-ollama/qwen2.5-coder:7b"    # Máquina atual ou rota gratuita instantânea
      fallbacks: ["openrouter/llama-3.3-70b-instruct:free"]
      min_difficulty: 1

# ============================================================================
# CONEXÃO AUTOMÁTICA COM OUTRO PC MAIS FORTE EM CASA (VIA SSH)
# ============================================================================
remote_ssh_gpu:
  enabled: true
  ssh_target: "usuario@192.168.1.100"
  ssh_port: 22
  ssh_key: "~/.ssh/id_ed25519"
  local_port: 11435
  remote_port: 11434 # Porta do Ollama / vLLM no PC forte
  healthcheck_interval_sec: 10
  auto_register_in_omniroute: true

# ============================================================================
# COMPORTAMENTO DOS 3 MODOS DE EXECUÇÃO
# ============================================================================
modes:
  mode_1_swarm:
    max_parallel_worktrees: 4
    worker_cli: "opencode" # Opções: opencode | aider | claude-code | antigravity
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
    mid_stream_hot_swap: true

  mode_3_persistent:
    locked_model: "architect_heavy"
    wait_for_5h_quota_reset: true
    poll_quota_interval_sec: 30
    stitch_anchor_lines: 15
```

---

## 7. Estrutura Enxuta e Foco do Repositório (`hydra-orch`)

Ao delegar a autenticação OAuth e os provedores para o OmniRoute, o repositório do `hydra-orch` fica extremamente limpo, estável e $100\%$ focado em Engenharia de Software:

```text
hydra-orch/
├── config.yaml                      # Configuração unificada (Hydra + OmniRoute + SSH + Modos)
├── pyproject.toml                   # Empacotamento e registro do binário 'hydra'
├── README.md                        # Documentação oficial da arquitetura
└── src/
    └── hydra_orch/
        ├── __init__.py
        ├── cli.py                   # Comandos: hydra run, hydra serve, hydra quota, hydra status
        ├── server.py                # Proxy FastAPI (:8000/v1) para Cline, Aider e Antigravity
        ├── engine/
        │   ├── __init__.py
        │   ├── decomposer.py        # Analisa tamanho/dificuldade (1-10) do prompt do usuário
        │   ├── contract.py          # Gera o Contrato Base (OpenAPI, Prisma, Types) pré-execução
        │   ├── swarm.py             # Modo 1: Cria Git Worktrees, roda workers paralelos e faz merge
        │   ├── relay.py             # Modo 2: Esteira sequencial (Começa na IA A, termina na IA B)
        │   ├── checkpointer.py      # Modo 3 & 2: SQLite Stream Buffer, Auto-Resume e Code Stitcher
        │   └── healer.py            # Roda build/testes pós-merge e corrige erros de integração
        └── bridge/
            ├── __init__.py
            ├── omniroute_client.py  # Cliente HTTP/SSE para o OmniRoute (:20128) + Leitor de Cota 5h
            ├── ssh_tunnel.py        # Gerenciador automático do túnel SSH para a GPU do PC remoto
            ├── worker_runner.py     # Dispara OpenCode, Aider, Claude Code, Codex ou Antigravity nas Worktrees
            └── cdp_fallback.py      # Fallback opcional via Playwright apenas para web apps sem CLI
```

---

## 8. Roadmap de Implementação Prático (4 Sprints)

1. **Sprint 1 — Ponte OmniRoute + Túnel SSH Automático (`omniroute_client.py` & `ssh_tunnel.py`):**
   * Subir e conectar o `hydra-orch` ao daemon do OmniRoute (`localhost:20128`), ler o status em tempo real das janelas de cota de $5\text{ h}$ do Claude Pro / GPT Plus / Gemini Pro e automatizar a abertura do túnel SSH (`localhost:11435`) com o PC forte em casa.
2. **Sprint 2 — Stream Checkpointer, Auto-Resume & Code Stitcher (`checkpointer.py` & `server.py`):**
   * Construir o proxy FastAPI na porta `8000` com gravação contínua em SQLite, implementando o **Modo 3** (pausar quando os tokens do Claude Pro acabam no meio da resposta, aguardar o timer do OmniRoute e costurar o resto do código sozinho) e o **Modo 2** (costurar o restante imediatamente usando outra IA).
3. **Sprint 3 — Gerador de Contrato Base & Decompositor de Dificuldade (`contract.py` & `decomposer.py`):**
   * Implementar a inteligência que recebe um pedido grande (como a aplicação da barbearia), pontua as tarefas de $1\text{ a }10$ e gera os arquivos de contrato imutáveis (`.hydra/contracts/`) antes da codificação.
4. **Sprint 4 — Motor Swarm em Git Worktrees & Auto-Healing (`swarm.py` & `healer.py`):**
   * Automatizar a criação das Git Worktrees com *symlinks*, disparar as 4 sessões paralelas simultâneas e executar o merge + bateria de testes automatizados ao final.
