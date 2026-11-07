# architecture — Arquitetura de Módulos e Fronteiras do hydra-orch

**Identificador Formal:** `architecture.md`
**Caminho Canônico:** `doc/g_code/architecture.md`
**Versão:** `v01_01_0000`
**Status:** `APROVADO / NORMATIVO`
**Autoridade:** Arquitetura do hydra-orch, delimitando responsabilidades entre control plane, gateway de inferência OmniRoute opcional, executores de agentes, ambientes Git e interface visual.
**Escopo:** Interfaces de control plane, desacoplamento em camadas (`core`, `engine`, `bridge`, `adapter`), ciclo de vida de tarefas e fronteiras de execução.

---

## 1. Propósito

Definir uma arquitetura em que o **Hydra** seja o control plane central de engenharia de software, o **OmniRoute** seja um gateway opcional de inferência desacoplado e a futura **interface visual** seja uma consumidora estrita de read models e comandos autenticados da API do Hydra. Esta especificação formaliza as fronteiras de responsabilidade, modos de instalação, responsabilidades por camada e a sequência de entrega do produto.

---

## 2. Fronteiras de Responsabilidade do Sistema

```text
+-----------------------------------------------------------------------------------+
| INTERFACE VISUAL (Web React/TS, Desktop ou Mobile)                                |
| - Consome read models persistidos via REST e stream de eventos SSE com cursor     |
| - Emite comandos autenticados (run, retry, review, hitl_response, cancel)         |
| - NUNCA decide resultados de tarefas nem infere sucesso a partir de saída de LLM  |
+-----------------------------------------------------------------------------------+
                                         │  (HTTP REST / SSE :8000/v1/control-plane)
                                         ▼
+-----------------------------------------------------------------------------------+
| HYDRA CONTROL PLANE (FastAPI + Typer + SQLite WAL + Git Workspace)                |
| - Serviços de Domínio: áreas, workspaces, projetos, repositórios, perfis, auth    |
| - Orquestração: Decompositor de tarefas, Contract-First Engine, DAG Scheduler     |
| - Governança: BudgetGovernor, ConflictResolver, PRPackager, Redactor de segredos  |
| - Persistência canônica transacional (SQLite WAL) e gravação atômica de artefatos |
+-----------------------------------------------------------------------------------+
                                         │
             ┌───────────────────────────┴───────────────────────────┐
             ▼                                                       ▼
+------------------------------------------+ +--------------------------------------+
| EXECUTORES DE AGENTES (Workers Isolados) | | OMNIROUTE GATEWAY (Opcional)         |
| - Claude Code CLI, OpenAI Codex CLI      | | - Rotação OAuth de assinaturas ($20) |
| - Gemini CLI, OpenCode, Aider            | | - Pool de modelos free (DeepSeek/Qwen|
| - IDE Bridge, Subprocessos e Playwright  | | - Monitor de janela de cota de 5h    |
| - Confinados em worktrees dedicadas      | | - Modo Direto funciona sem gateway   |
+------------------------------------------+ +--------------------------------------+
                     │                                           │
                     └─────────────────────┬─────────────────────┘
                                           ▼
+-----------------------------------------------------------------------------------+
| GIT E AMBIENTES DE EXECUÇÃO (Filesystem Local & Remoto SSH)                       |
| - Worktrees reais em `.orchestrator/worktree/` (isolamento de filesystem)         |
| - Branches dedicadas por tarefa e branch de integração serializada por projeto    |
| - Execução de suítes de testes herméticos e gravação de evidências tangíveis      |
+-----------------------------------------------------------------------------------+
```

### Invariantes de Fronteira
1. **O OmniRoute não substitui o executor de engenharia:** Uma resposta de modelo não comprova edição de arquivos, compilação de código, testes passando ou merge concluído.
2. **A interface visual não decide resultados:** Ela exibe o estado estritamente persistido no SQLite e envia comandos explícitos ao Hydra. Ações de aprovação, integração ou cancelamento dependem do estado gravado em `TaskResult` e nos eventos.
3. **A unidade de verdade do Hydra é o artefato verificável:** Patches Git, hashes de commit, comandos de check executados com exit codes e logs, eventos persistidos e decisões explícitas de integração.

---

## 3. Modos de Instalação e Topologias

| Perfil | Componentes Ativos | Cenário de Uso |
| :--- | :--- | :--- |
| **Direto** | Hydra Control Plane + CLI autenticada local (ex.: Claude Code / Aider) | Primeiro uso, testes automatizados e desenvolvimento local simples sem gateways |
| **Gateway** | Hydra + OmniRoute Gateway + executores locais | Fallback automático entre assinaturas pagas, quotas horárias e modelos gratuitos |
| **Remoto (SSH)** | Perfil Gateway + Host SSH remoto (PC forte com GPU) | Execução de builds, migrations, seeds e testes massivos em máquina dedicada |
| **Visual** | Qualquer perfil acima + cliente Web / UI | Operação visual completa, inspeção interativa de diffs e aprovação humana (HITL) |

O arquivo `config.yaml` utiliza as chaves `omniroute.enabled` (booleano) e `omniroute.connection_mode` (`disabled`, `optional`, `required`) para governar o gateway. O Hydra falha imediatamente antes de iniciar qualquer subprocesso quando o modo for `required` e o gateway não responder ao healthcheck.

---

## 4. Decomposição de Camadas do Código (`src/hydra_orch/`)

O código-fonte do Hydra é estruturado em quatro camadas estritas de separação de responsabilidades:

```
src/hydra_orch/
├── core/               # Camada 1: Serviços de Aplicação e Control Plane
├── engine/             # Camada 2: Estratégias de Execução de Tarefas
├── bridge/             # Camada 3: Transporte, Subprocessos, Conectores e Drivers
└── adapter/            # Camada 4: Adaptadores de Inferência e Multimodal
```

### 4.1 Mapeamento de Responsabilidades

| Camada | Responsabilidade Primária | O Que NÃO Faz |
| :--- | :--- | :--- |
| **`core/`** | Orquestração central, ciclo de vida de runs/tasks, persistência no banco relacional (SQLite WAL), segurança (auth, redaction), governança (orçamento, conflitos, empacotamento, HITL) e gestão de áreas/projetos/repositórios. | NUNCA executa subprocessos diretamente, não roda inferência de LLM nem manipula transporte de rede de baixo nível. |
| **`engine/`** | Estratégias de resolução de tarefas: Swarm (DAG paralelo + semáforo), Relay (handoff estruturado entre modelos), Persistente (auto-resume pós-cota), Healer (auto-healing limitado) e Multimodal (jobs de mídia). | NUNCA toca no banco SQLite diretamente (usa serviços de `core/`), não toma decisões de auth nem altera branches Git fora do contrato. |
| **`bridge/`** | Transporte de baixo nível, execução de subprocessos (`ProcessManager`), túneis SSH, drivers de desktop/browser (Playwright/CDP), drivers de áudio (STT/TTS), clientes MCP e conectores externos (Jira, GitHub). | NUNCA implementa lógica de negócio ou regras de aprovação de tarefas. |
| **`adapter/`** | Protocolos de inferência de linguagem e adaptadores de geração multimodal (imagem, áudio, vídeo). Fornece interfaces assíncronas uniformes. | NUNCA realiza mutações no repositório Git nem executa ferramentas do sistema. |

---

## 5. Interface Visual Planejada

A interface visual opera estritamente contra endpoints REST e SSE versionados do control plane. O contrato de inicialização `GET /v1/control-plane/bootstrap` informa as capacidades ativas do servidor e lista explicitamente os read models disponíveis.

### Telas Canônicas da Aplicação Visual

1. **Dashboard de Projetos e Execuções:** Visão macro de objetivos, SHA base, estado do run e consumo de orçamento em tempo real.
2. **Fila e Grafo de Tarefas (DAG View):** Visualização de dependências, responsáveis, executores alocados, progresso das tentativas e gates pendentes.
3. **Inspetor de Worktrees e Diffs:** Visualização interativa de arquivos modificados (Monaco Editor / diff2html), relatórios de checks executados, botões de aceite/rejeição e gatilhos de integração.
4. **Painel de Provedores e Quotas:** Status de gateways, contas elegíveis, frescor de cotas (`observed`, `stale`, `unknown`), histórico de decisões de roteamento e fallbacks.
5. **Timeline de Eventos e Checkpoints:** Linha do tempo monotônica de eventos do run, alertas de orçamento, pausas de HITL com solicitação de contexto e checkpoints salvos.
6. **Hub de Modelos e MCPs:** Inspetor dinâmico de ferramentas MCP, ativação seletiva, catálogo de modelos locais e status de downloads/quantizações.

---

## 6. Sequência de Entrega por Marcos

1. **Marco M1 (Núcleo Verificável — S00 a S05):** Contratos de execução tipados (`RunSpec`, `TaskSpec`), persistência transacional local (SQLite WAL) e execução verificável em worktree com checks reais (Tasks T01 a T08).
2. **Marco M2 (Control Plane e API REST — S10 e S11):** Camada de API `/v1/control-plane/*`, autenticação local, CORS restrito, redaction central e read models expostos para UI (Tasks T09 e T26).
3. **Marco M3 (Workspaces, Perfis e Orquestração Swarm/Relay/Persist — S06 a S09, S14 e S15):** Hierarquia de áreas/repositórios, perfis imutáveis com snapshot por run, escalonador DAG de Swarm, handoff estruturado com code stitching e auto-healing limitado (Tasks T10 a T16, T25).
4. **Marco M4 (Governança, Extensões e Capacidades Avançadas — S16 a S28):** Memória consentida, discovery local seguro, extensões isoladas, acessibilidade WCAG AA, budgeting com alerta/congelamento, empacotamento de PR e expansão multimodal/RAG/voz/computer use (Tasks T17 a T24, T27 a T44).

---

## 7. Decisões de Produto e Referências de Arquitetura

- **OmniRoute:** Integração opcional e desacoplada, preservando a capacidade do Hydra operar isoladamente.
- **Alethe:** Referência conceitual para briefs de engenharia, ondas de execução (waves), evidências verificáveis e gates formais de integração.
- **Orca / Claude Squad:** Referências de experiência de usuário e interface; o Hydra foca primeiro na integridade do estado e execução verificável antes de interfaces elaboradas.
- **Unidade de Verdade:** A verdade do sistema nunca reside em logs ou respostas textuais de LLMs, mas em artefatos verificáveis gravados com integridade SHA-256 no filesystem e indexados no banco transacional.
