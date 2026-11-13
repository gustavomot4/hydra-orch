# prd_funcional — Especificação Funcional do hydra-orch

**Identificador Formal:** `prd_funcional.md`
**Caminho Canônico:** `doc/b_spc/prd_funcional.md`
**Versão:** `v02_00_0000`
**Status:** `IMPLEMENTADO / VALIDADO OFFLINE (M1–M4 · GATE G-M4)`
**Autoridade:** Arquitetura do hydra-orch alinhada a [`../a_context/taxonomia_file_system.md`](../a_context/taxonomia_file_system.md) e [`plano_desenvolvimento.md`](../a_context/plano_desenvolvimento.md).
**Escopo:** Requisitos funcionais (RF01 a RF30), casos de uso detalhados (UC01 a UC05), regras de negócio (RB01 a RB20), critérios de aceite e rastreabilidade DBC-9. Ideias exploratórias pós-M4 (antigos V5/V6) residem em [`../a_context/ideia_futura.md`](../a_context/ideia_futura.md).

**Estado das capacidades:** **RF01–RF30** (M1 a M4 / V0 a V4) estão implementados no backend/CLI/API e validados na suíte hermética offline (`python -m pytest tests -q` → **568 testes aprovados**; ver [`../a_context/backlog.md`](../a_context/backlog.md)). Propostas fora do núcleo de engenharia de software residem em [`../a_context/ideia_futura.md`](../a_context/ideia_futura.md); frontend Web UI visual e certificação contra CLIs externas pagas permanecem fora do escopo offline.

---

Status: especificação funcional normativa proposta para implementação. Base: revisão registrada no [plano](../a_context/plano_desenvolvimento.md) e síntese da [visão de produto](../a_context/visao_produto.md). Não representa funcionalidades já certificadas. Este documento detalha o comportamento esperado do produto; o [PRD técnico](prd_tecnico.md) define sua realização e contratos executáveis.

**Incremento de configuração:** parte de RF02 possui implementação offline validada em [S01](configuracao_runtime.md). A configuração de um driver não comprova sua execução; a certificação do Codex e os critérios completos de M1 permanecem pendentes. Swarm é recusado no proxy de inferência até que os gates próprios existam.

**Incremento de contratos:** [S02](contrato_execucao.md) implementa a base tipada de RF03/RF07 e os estados separados de processo, tarefa e integração. As regras são verificadas em memória; submissão persistente, execução real, revisão autenticada e merge dependem de T03–T07.

## 1. Propósito

Permitir que um usuário organize áreas de trabalho, projetos e repositórios, escolha ou componha perfis de agentes e acompanhe tarefas de engenharia por uma interface visual e pelas superfícies CLI/API. O Hydra opera como control plane de engenharia de software unificando a inteligência de orquestração sobre quatro motores centrais integrados:
1. **Decompositor de Tarefas por Tamanho e Dificuldade (`Task Decomposer`):** Avalia pedidos de engenharia, decompõe em módulos pontuados por complexidade (1 a 10) e orquestra a alocação de modelos e executores combinando especialidade técnica com disponibilidade e limites de cota.
2. **Motor Contract-First em Duas Ondas (`Wave 0 Foundation + Wave 1 Swarm`):** Executa primeiro a **Wave 0 (Fundação Compilável)** para gerar e validar com linter/typecheck os schemas, tipos, stubs de rota e dependências (`pyproject.toml`/`package.json`) na branch `integrate/<run_id>`, abrindo em seguida as worktrees paralelas da **Wave 1** com protocolo formal de *Contract Amendment*.
3. **Orquestrador de Enxame em Git Worktrees (`Multi-Session Swarm`):** Dispara sessões paralelas em worktrees isoladas nascidas do SHA da Wave 0, bloqueando mutações concorrentes em manifestos de pacotes durante a Wave 1 e serializando o merge validado por suíte de testes (com auto-healing limitado).
4. **Motor de Handoff por Estado Git/Worktree e Retry de Turno Atômico (`Checkpointer & Handoff Engine`):** Persiste o progresso em SQLite WAL (`.orchestrator/checkpoints.sqlite`), permitindo pausar e aguardar reabertura de cota (Modo Persistente) ou transferir a worktree com seu `git diff`, `git status` e relatório de checks para outro executor (Modo Relay), além de realizar retry de turno atômico quando chamadas de API com `tool_calls` são interrompidas.

O sistema suporta três modos de orquestração distintos — **Swarm** (paralelo com worktrees isoladas), **Relay** (handoff estruturado entre provedores) e **Persistente** (auto-resume por janela de cota) — com seleção explícita pelo operador e transições governadas por políticas de orçamento e capacidade.

## 2. Justificativa e usuários

O operador visual ou terminal configura áreas, projeto, repositórios, perfil de execução e limites; o revisor aceita ou rejeita resultados e integração. No MVP, ambos são o mesmo usuário local. O agente cliente consome inferência ou comandos explícitos de execução. O executor é um sistema externo, sem autoridade para aprovar seu próprio resultado. Em fases posteriores, o usuário poderá acompanhar sessões e threads de múltiplos agentes, revisar memória e autorizar recursos descobertos ou extensões.

Valor esperado: reduzir coordenação manual mantendo rastreabilidade de mudanças, decisões e recuperação de falhas. Medir proporção de tarefas aceitas com checks, falhas que preservam trabalho, reconexões sem perda de eventos e retomadas sem efeitos duplicados; metas de latência, custo e produtividade dependem de baseline posterior.

## 3. Contrato funcional

### 3.1 Escopo por Versão

**MVP (V0 — Núcleo Verificável):**
- Um operador, uma área/projeto local, um repositório, tarefa delimitada, um executor CLI selecionado explicitamente
- Resultado revisável com patch/checks e integração em branch dedicada
- Listar, consultar, cancelar e revisar execução pela CLI/API mínima
- Gateway OmniRoute opcional; modo direto funcionando sem gateway
- UI acompanha somente como cliente de read models e comandos persistidos

**V1 (Control Plane Visual):**
- Interface visual de primeira classe consumindo API versionada
- Dashboard de projetos, execuções, worktrees, diffs, quotas e decisões
- Autenticação local obrigatória, CORS com allowlist estrita, redaction de segredos

**V2 (Workspaces e Perfis):**
- Hierarquia Area → Workspace → Project → Repository com autorização explícita
- Catálogo de agentes/executores com capabilities declaradas e certificação por driver/SO
- Perfis combináveis com snapshot imutável por run (ProfileSnapshot com hash)

**V3 (Coordenação, Rotas e Observabilidade):**
- Swarm com DAG de dependências, scheduler com limite de concorrência
- Handoff estruturado entre provedores (Relay) com checkpoint de progresso
- Métricas operacionais com status `observed`/`stale`/`unknown` (nunca zero inventado)
- Roteamento adaptativo com trilha auditável (RouteDecision); OmniRoute opcional

**V4 (Memória, Discovery, Extensões, Acessibilidade, Transportes):**
- Memória adaptativa consentida, separada de checkpoints técnicos
- Discovery local opt-in restrito a raízes autorizadas, estado `untrusted` até aprovação
- Extensões/plugins em processo isolado, manifesto versionado, consentimento e revogação
- Acessibilidade verificável: teclado, foco visível, roles semânticos, contraste, redução de movimento
- Transportes certificados (SSH, IDE, CDP, remoto) com healthcheck e verificação de identidade

Fora do escopo (não endereçado no primeiro marco): multiusuário, publicação automática irrestrita, garantia universal de compatibilidade com provedores, DAG livre por LLM sem validação humana, healing automático sem teto de tentativas.

### 3.2 Requisitos Funcionais (RF01 a RF30)

| ID | Requisito | Descrição Detalhada | Critérios de Aceite Observáveis | Etapa |
|----|-----------|---------------------|----------------------------------|-------|
| **RF01** | Cadastrar projeto por raiz Git e selecionar base | Permitir registrar um projeto informando caminho absoluto do repositório Git. Validação de existência do `.git`, acessibilidade, e seleção de branch/SHA base. O sistema deve exibir o SHA base selecionado e preservá-lo imutável para o ciclo de vida do run. | Raiz inválida ou sem `.git` é recusada com erro claro; SHA base exibido e travado; tentativa de alterar base após criação do run falha. | S01/S05 |
| **RF02** | Configurar executor, modelo, modo e limites | Permitir definir qual executor CLI (Claude Code, Codex, Gemini CLI, OpenCode, Aider), modelo alvo, modo de orquestração (swarm/relay/persist) e limites de orçamento (tokens, custo USD, tempo parede, concorrência). Configuração inválida deve falhar antes de iniciar qualquer subprocesso. Modo direto (sem gateway) deve ser suportado nativamente. | Config inválida (executor desconhecido, modelo não suportado, limites negativos) falha com erro tipado antes do spawn; gateway desligado permite execução direta; validação de capabilities do executor contra requisitos da tarefa. | S01 |
| **RF03** | Submeter objetivo com escopo e critérios de aceite | Receber objetivo em linguagem natural, arquivos permitidos (glob patterns), critérios de aceite executáveis (comandos de teste/check), dependências entre tarefas, e chave de idempotência. Retornar run ID. Repetição com mesma chave e payload idêntico deve retornar o mesmo run (idempotência). | Retorna run ID único; mesma chave/payload → mesmo run; chave reutilizada com payload diferente → erro 409; validação de schema do RunSpec antes de persistir. | S02/S03/M1 |
| **RF04** | Executar tarefa em workspace isolado | Criar worktree Git real (não diretório comum) para cada tentativa. Executor roda com `cwd` resolvido, `argv` específico, env filtrado (sem segredos), timeout e cancelamento de árvore de processos. Ausência da CLI do executor configurado é erro, nunca sucesso simulado. | Worktree criada em `.orchestrator/worktree/<run_id>_<task_id>/`; diff atribuído à tentativa; CLI ausente → erro `executor_unavailable`; fake subprocess só em dry-run explícito. | S04/S05 |
| **RF05** | Acompanhar progresso e consultar evidências | Exibir estado da run, tarefa, tentativa, checks executados, diff gerado, motivo de falha. Estado deve ser consultável inclusive após reinício do servidor (persistência em SQLite). Eventos disponíveis via SSE com replay por cursor. | Estado, tentativa, checks, diff e falha visíveis via CLI/API/UI; reinício do servidor não perde estado; SSE replay com `Last-Event-ID` funciona. | S03/M1/S10 |
| **RF06** | Cancelar execução | Solicitar cancelamento idempotente de run/tarefa/tentativa. Confirmar término do processo e descendentes (tree kill) ou informar falha de cancelamento. Preservar arquivos, worktree e evidências para inspeção posterior. | Processo e filhos terminados; worktree preservada; artefatos retidos; evento `task.cancelled` ou `run.cancelled` emitido; tentativa de cancelar run já finalizado retorna estado atual sem erro. | S04/M1 |
| **RF07** | Aceitar ou rejeitar resultado | Revisor decide sobre resultado de uma tentativa. Exige versão atual do resultado (controle de concorrência otimista) e checks obrigatórios definidos no TaskSpec. Rejeição mantém evidência completa e permite nova tentativa. | Aceite só com `expected_revision` correspondente e checks obrigatórios passando; rejeição registra motivo e preserva `TaskResult`; nova tentativa cria `TaskAttempt` ordinal incrementado. | S05/M1 |
| **RF08** | Integrar resultados aceitos | Aplicar patches/commits aceitos em branch de integração dedicada (não na branch do operador). Validar combinação rodando checks novamente no contexto integrado. Conflito de merge não altera branch do operador; preserva worktree de integração para resolução. | Merge em branch `integrate/<run_id>`; checks reexecutados; conflito → status `conflicted`, worktree preservada, não toca branch do usuário; integração só de resultados `accepted`. | S05 |
| **RF09** | Planejar tarefas em Duas Ondas (Wave 0 + Wave 1) e executar swarm | Permitir definir DAG de tarefas com Wave 0 (Fundação Compilável: schemas, tipos, stubs e dependências validados na branch de integração) seguida da Wave 1 (Swarm Paralelo em worktrees com manifestos de pacotes bloqueados contra edição concorrente). Scheduler valida aciclicidade (Kahn/DFS), ownership e limite de concorrência (`max_parallel_worktrees`). | Ciclo no DAG → erro na submissão; Wave 1 só inicia após Wave 0 `accepted`; mutação de `pyproject.toml`/`package.json` na Wave 1 bloqueada; concorrência respeita semáforo. | S06 |
| **RF10** | Retomar ou trocar executor por Estado Git/Worktree e Retry de Turno | Suportar handoff estruturado baseado no estado real do workspace (`git status`, `git diff`, histórico de ferramentas e checks executados) para agentes CLI, e retry de turno atômico (descartando `tool_calls` truncados na queda) para chamadas no proxy HTTP. Efeito ambíguo bloqueia repetição automática e exige reconciliação. | Handoff carrega `HandoffCheckpoint` com `git diff` e checks da worktree; queda em `tool_calls` reenvia o turno inteiro sem corromper JSON; crash pós-ferramenta → `blocked`. | S07 |
| **RF11** | Consultar quota e escolher rota elegível | Exibir cota disponível por modelo/provedor com origem (OmniRoute, cache local, direto) e frescor (timestamp). Valor desconhecido aparece como `unknown`/`stale`, nunca como 100% disponível. Rota selecionada registra candidatos avaliados, critério, fallback e origem da decisão. | Quota `unknown`/`stale` exibida corretamente; rota inelegível nunca selecionada; decisão de rota auditável em `RouteDecision`; modo direto opera sem gateway. | S08 |
| **RF12** | Solicitar reparação limitada (Auto-Healing) | Quando check falha, permitir nova tentativa de reparo aplicando mudança e repetindo checks. Orçamento de reparo (máx. tentativas, tokens, custo) configurável; esgotamento termina com falha. Reparo não é loop infinito: teto rígido (ex.: máx. 2 tentativas por tarefa). | Nova tentativa aplica patch e roda checks; `max_repair_attempts` respeitado; esgotamento → falha final com evidência; reparo não modifica tentativas anteriores (imutabilidade). | S09 |
| **RF13** | Operar interface visual | UI consome read models persistidos e envia comandos autorizados (mesma camada de serviço da CLI). Reconexão por cursor SSE (`Last-Event-ID`) com deduplicação. Estado exibido é snapshot do banco, não inferido de texto de agente. | UI mostra estado persistido; reconexão recupera eventos perdidos; comandos UI → mesma validação da CLI; nenhuma ação de aprovação/integração sem comando autenticado correspondente. | S10/S11 |
| **RF14** | Usar SSH/IDE/CDP conforme capacidade certificada | Suportar execução remota via SSH (túnel automático, healthcheck de host key), IDE Bridge e CDP fallback. Alvo incorreto ou host key divergente recusa conexão. Inferência (chat) não é anunciada como execução de ferramentas. | SSH com host key alterada → aborta conexão; CDP falha alvo → erro, não seleciona página aleatória; execução remota isolada por worktree; capabilities declaradas e certificadas por driver/SO. | S12 |
| **RF15** | Exportar evidência e descartar runtime | Exportar dossier completo da execução (objetivo, tasks, attempts, patches, checks, métricas, decisões) com redaction de segredos. Descarte explícito de runtime (worktrees, checkpoints, artefatos temporários) só remove o que tem retenção comprovada; evidência necessária a execução ativa não expira. | Exportação redigida (sem tokens, chaves, senhas); descarte não remove trabalho sem retenção; órfãos de crash reconciliados antes de limpeza. | S13 |
| **RF16** | Gerenciar áreas de trabalho, projetos e múltiplos repositórios | Hierarquia: Area → Workspace → Project → Repository. Cada repositório tem raiz canônica, branch base, SHA base, caminhos permitidos (`allowed_paths`) e autorização explícita (`Authorization`). Acesso implícito recusado; symlink/traversal fora da raiz bloqueado. | Repositório fora de allowlist → 403; traversal/symlink → 400; repo secundário sem autorização própria → bloqueado; hierarquia persistida e consultável. | V2 / S10+ |
| **RF17** | Criar perfil combinando agente, modelo, executor, skills, MCP e memória | Perfil agrupa `AgentDefinition` (driver, capabilities, limitações, certificação), modelo, executor, skills, MCPs, política de memória e limites de recursos. Validação pré-execução rejeita combinações incompatíveis (ex.: tarefa exige worktree, executor não suporta). Snapshot imutável (`ProfileSnapshot` com hash) gravado no run. | Perfil mostra capabilities, origem, versão, permissões, limitações; combinação inválida → 422 antes do spawn; snapshot imutável por run; alteração posterior de perfil não afeta runs em andamento. | V2 / S01–S03 |
| **RF18** | Exibir sessões e threads multiagente | Cada sessão/thread possui identidade, agente, estado, eventos monotônicos e relação pai/filho. SSE com cursor `Last-Event-ID` para replay e deduplicação. Visibilidade de thread não implica swarm implementado. | Árvore de sessões/threads consultável; replay SSE ordenado monotônico; queda de conexão reconciliada sem duplicação lógica; cursor expirado → erro 410 orientando novo snapshot. | V3 / S06–S07 |
| **RF19** | Exibir observabilidade operacional | Fila, estado, duração, tokens (in/out), custo vinculados a run/attempt/session. Cada amostra (`MetricSample`) tem valor, unidade, fonte, timestamp e status `observed`/`stale`/`unknown`. Ausência de dado → `unknown` (nunca zero); agregações com parcelas desconhecidas → sinalizadas como parciais. | Métricas com proveniência e status explícito; provedor sem tokens → `unknown`; quota offline → `unknown`/`stale`; dashboard UI mostra `unknown` visualmente distinto. | V1/V3 / S03/S08/S10 |
| **RF20** | Selecionar rota adaptativamente | Hydra registra candidatos, critério de seleção, capabilities, cadeia de fallback e origem da decisão (`hydra`, `omnirouter`, `operator`). OmniRouter é opcional; modo direto opera sem gateway. Decisão reproduzível e auditável. | `RouteDecision` gravada com candidatos, motivo, fallback; rota inelegível nunca selecionada; modo direto comprovado em teste; decisão não muta estado de execução anterior. | V3 / S08 |
| **RF21** | Persistir memória adaptativa com consentimento e escopo | Memória (`MemoryEntry`) só gravada após `ConsentRecord` ativo (`granted`). Escopo, autor, versão, retenção e revogação consultáveis. Estritamente separada de checkpoints técnicos (tabelas e lifecycles distintos). Revogação impede uso em novos runs. | Gravação sem consentimento → 409; revogação funcional; checkpoint nunca alimenta memória automaticamente; tabela isolada com expiração e auditoria próprias. | V4 / gate segurança |
| **RF22** | Descobrir skills, MCPs, memórias e sessões locais de forma controlada | Discovery (`DiscoveryService`) opt-in, restrito a raízes autorizadas (`allowlist`). Calcula hash do recurso, registra `DiscoveredResource` como `untrusted`. Sem ativação automática; aprovação explícita de principal autenticado necessária. Hash alterado em disco → transição automática para `untrusted` e bloqueio. | Varredura só em raízes allowlisted; recurso → `untrusted`; aprovação → `approved`; hash alterado → `untrusted` + bloqueio; recurso fora da raiz ignorado. | V4 / gate proveniência |
| **RF23** | Personalizar interface, comportamento e acessibilidade | Preferências (`Preference`) escopadas (user/area/project), reversíveis, com snapshot por run (`PreferenceSnapshot`). UI operável por teclado, foco visível, roles semânticos, estados textuais além de cor, contraste WCAG AA, redução de movimento. Preferência inferida não sobrepõe instrução explícita de projeto. | Checklist automatizado/manual de a11y validado; snapshot imutável por run; reversão restaura estado prévio; inferida não sobrepõe explícita. | V1/V4 / S11 |
| **RF24** | Instalar e operar extensões/plugins | Plugin declara manifesto versionado (`ExtensionManifest`): entrypoint, permissões, capabilities, versão API compatível, checksum. Instalação requer consentimento; revogação bloqueia novos efeitos imediatamente. Processo isolado sem acesso a DB core ou segredos não autorizados. Rollback para versão anterior aprovada suportado. | Manifesto incompatível → não inicia; revogação → bloqueio imediato + evento auditoria; plugin não acessa DB core; rollback funcional. | V4 / gate extensão |
| **RF25** | Usar transportes locais/remotos certificados | Cada transporte (`TransportDefinition`) expõe tipo (local, ssh, ide, cdp, remote), target_identity, capabilities declaradas, certificação. Healthcheck tipado (`TransportHealth`). Alvo incorreto ou host key SSH divergente falha observavelmente. Sessões concorrentes isoladas. | SSH host key modificada → aborta; healthcheck tipado; mock não substitui certificação; saídas concorrentes isoladas. | V4 / S12–S13 |
| **RF26** | Selecionar modo de orquestração (Swarm / Relay / Persistente) | Operador escolhe explicitamente o modo na submissão do run ou via perfil: **Swarm** (decomposição em DAG, execução paralela em worktrees, merge serializado); **Relay** (handoff sequencial entre provedores/modelos quando cota/contexto esgota); **Persistente** (pausa automática ao atingir rate limit de janela — ex.: 5h Claude Pro — e retomada automática quando janela reabre). Modo é imutável por run (snapshot no ProfileSnapshot). | Modo válido selecionado; Swarm → DAG validado + worktrees paralelas; Relay → handoff checkpoint estruturado entre tentativas; Persistente → pausa/retomada automática por janela de cota; mudança de modo em run ativo → erro. | V0 / S02–S06 |
| **RF27** | Interação Humano-no-Loop (HITL) durante execução | Suporte a pausas intermediárias solicitadas pelo executor: `needs_context` (esclarecimento de escopo/ambiguidade), `needs_approval` (comando de alto risco: rede, migração destrutiva, fora do workspace). Operador notificado via evento SSE/UI; resposta (aprovação/rejeição/esclarecimento) retoma a tentativa. Timeout de HITL configurável; expiração → falha da tentativa com evidência. | Evento `task.needs_context` ou `task.needs_approval` emitido; operador responde via CLI/API/UI; retomada carrega resposta no contexto; timeout → `failed` com motivo `hitl_timeout`; evidência preservada. | V1 / S03–S04 |
| **RF28** | Resolução de conflitos de merge assistida | Quando integração detecta conflito, sistema apresenta relatório visual 3-way (base, branch tarefa, branch integração) e oferece: (a) solicitar ao agente que rebaseie e resolva na worktree; (b) descartar a tarefa; (c) abrir para resolução manual pelo desenvolvedor. Opção (a) cria nova tentativa de reparo de merge com orçamento próprio. | Conflito → status `conflicted` + relatório 3-way; opção (a) dispara `TaskAttempt` de `merge_repair`; opção (b) → `rejected`; opção (c) → worktree preservada para edição manual; merge só prossegue após resolução e checks. | V0 / S05 |
| **RF29** | Governança de orçamento e tetos de consumo (Budgeting / Hard Caps) | Permitir configurar teto de custo USD por run, teto de tokens (input/output), teto de tempo parede. Gatilhos: alerta em 80%, congelamento preventivo em 100% com solicitação de extensão ao operador (aprovação estende orçamento; recusa finaliza run com `budget_exhausted`). Custo desconhecido permanece `unknown`; não bloqueia por estimativa. | Teto configurável; alerta 80% emitido; 100% → pausa + solicitação extensão; aprovação estende; recusa → `budget_exhausted`; `unknown` não vira zero nem bloqueia. | V1 / S08 |
| **RF30** | Empacotamento de entrega e auditoria de Pull Request | Criação automática de branch de Pull Request no remote (quando autorizado via configuração/política do run) com descrição estruturada: objetivo, lista de commits, saída dos checks, diff sumarizado, métricas de execução, decisões de revisão. Dossiê exportável para auditoria offline. | PR criado com descrição padrão; diff, checks, métricas incluídos; exportação redigida; autorização de publicação separada da execução. | V1 / S05/S13 |

---

### 3.3 Casos de Uso Detalhados (UC01 a UC05)

#### UC01 — Submissão e Revisão de Tarefa Simples (Caminho Feliz)

| Elemento | Descrição |
|----------|-----------|
| **Ator Primário** | Operador (desenvolvedor) |
| **Pré-condições** | Projeto cadastrado (RF01), executor configurado e disponível (RF02), base Git válida |
| **Fluxo Principal** | 1. Operador submete objetivo, arquivos permitidos, critérios de aceite (comando de teste), chave de idempotência (RF03)<br>2. Hydra valida RunSpec, cria run `queued`, persiste evento `run.created`<br>3. Scheduler despacha tarefa: cria worktree, spawn executor com argv/cwd/env filtrado (RF04)<br>4. Executor trabalha; operador acompanha via eventos SSE/CLI (RF05)<br>5. Executor finaliza; Hydra coleta diff, roda checks definidos (RF04/RF12)<br>6. Resultado `ready_for_review` disponibilizado com patch, checks, resumo (RF07)<br>7. Operador revisa diff e checks; aceita com `expected_revision` correto (RF07)<br>8. Hydra integra em branch `integrate/<run_id>`, roda checks de combinação (RF08)<br>9. Merge bem-sucedido → run `succeeded`; evento `run.finished` |
| **Fluxos Alternativos** | **A1:** Check falha → resultado `failed`; operador pode solicitar reparo (RF12) → nova tentativa ordinal+1<br>**A2:** Operador rejeita → resultado `rejected`; evidência preservada; nova tentativa permitida<br>**A3:** Conflito no merge → status `conflicted`; operador escolhe reparo automático, descarte ou resolução manual (RF28) |
| **Fluxos de Exceção** | **E1:** CLI ausente → erro `executor_unavailable` antes do spawn; run `failed`<br>**E2:** Timeout de execução → cancelamento de árvore; run `timed_out`; evidência preservada<br>**E3:** Perda de conexão SSE → reconexão por `Last-Event-ID` recupera eventos; sem perda lógica |
| **Pós-condições** | Run concluído com estado final persistido; evidência completa (diff, checks, decisões) consultável; branch de integração pronta ou worktree preservada para resolução |

---

#### UC02 — Execução em Swarm com Reparação Automática (Auto-Healing)

| Elemento | Descrição |
|----------|-----------|
| **Ator Primário** | Operador |
| **Pré-condições** | Projeto cadastrado; perfil com modo `swarm`; DAG de tarefas válido (RF09); concorrência configurada |
| **Fluxo Principal** | 1. Operador submete run com múltiplas tarefas e dependências (DAG) (RF03/RF09)<br>2. Scheduler valida DAG (aciclicidade, ownership, concorrência) (RF09)<br>3. Tarefas sem dependências (`ready`) despachadas em paralelo até `max_parallel_worktrees` (RF09)<br>4. Cada tarefa executa em worktree isolada (RF04)<br>5. Tarefa T1 falha em check; operador solicita reparo (RF12)<br>6. Nova tentativa de T1 aplica patch corretivo e reexecuta checks (RF12)<br>7. T1 aceita → tarefas dependentes (T2, T3) tornam-se `ready` e são despachadas<br>8. Todas tarefas obrigatórias `accepted` → integração serializada (RF08)<br>9. Checks de integração passam → run `succeeded` |
| **Fluxos Alternativos** | **A1:** Tarefa dependente falha → bloqueia suas dependentes; independentes continuam<br>**A2:** Reparo esgota `max_repair_attempts` → tarefa `failed` final; dependentes bloqueadas<br>**A3:** Operador cancela run → todas tentativas ativas canceladas; worktrees preservadas (RF06) |
| **Fluxos de Exceção** | **E1:** Ciclo no DAG detectado na submissão → erro 422, run não criado<br>**E2:** Concorrência excedida → tarefas `queued` aguardam semáforo<br>**E3:** Crash de executor → tarefa `crashed`; reconciliação necessária antes de retry (RF10) |
| **Pós-condições** | DAG executado respeitando dependências; evidência por tarefa; integração validada ou worktrees preservadas para resolução manual |

---

#### UC03 — Interrupção por Rate Limit e Continuidade por Relay / Persistência

| Elemento | Descrição |
|----------|-----------|
| **Ator Primário** | Operador (passivo — sistema age automaticamente) |
| **Pré-condições** | Run em modo `relay` ou `persist` (RF26); executor com cota conhecida (ex.: Claude Pro 5h) |
| **Fluxo Principal (Relay)** | 1. Executor atinge limite de cota/contexto (evento `attempt.rate_limited`)<br>2. Hydra cria `HandoffCheckpoint` com: objetivo, decisões, SHA/diff, ferramentas/executadas, saída parcial, próximo passo (RF10)<br>3. Seleciona próximo provedor/modelo elegível (RF11/RF20) com capabilities compatíveis<br>4. Nova tentativa (`TaskAttempt` ordinal+1) inicia com checkpoint carregado<br>5. Execução continua; operador pode acompanhar transição via eventos |
| **Fluxo Principal (Persistente)** | 1. Executor atinge rate limit de janela (ex.: 5h Claude Pro)<br>2. Hydra pausa run: estado `waiting` com causa `rate_limit_window` e limite `window_reset_at` (RF26)<br>3. Timer monitora reabertura da janela (consulta quota via OmniRoute ou heurística)<br>4. Janela reabre → run retoma automaticamente do mesmo ponto (mesmo `TaskAttempt`)<br>5. Nenhum token gasto na espera; operador notificado de pausa/retomada |
| **Fluxos Alternativos** | **A1:** Nenhum provedor fallback elegível (Relay) → run `blocked` aguardando intervenção<br>**A2:** Operador cancela durante espera (Persistente) → run `cancelled` |
| **Fluxos de Exceção** | **E1:** Quota desconhecida (`unknown`) → não assume disponibilidade; modo Persistente não inicia espera cega<br>**E2:** Crash durante handoff → reconciliação de efeitos ambíguos antes de nova tentativa (RF10) |
| **Pós-condições** | Continuidade da execução preservada; handoff auditável (`RouteDecision`, `HandoffCheckpoint`); nenhum efeito duplicado; custo de espera não contabilizado |

---

#### UC04 — Cancelamento Forçado com Preservação de Trabalho Parcial

| Elemento | Descrição |
|----------|-----------|
| **Ator Primário** | Operador |
| **Pré-condições** | Run em execução (`running`) com uma ou mais tentativas ativas |
| **Fluxo Principal** | 1. Operador emite `cancel` para run/tarefa/tentativa específica (RF06)<br>2. Hydra solicita cancelamento idempotente ao processo executor<br>3. Aguarda término de árvore de processos (tree kill verificado no SO)<br>4. Confirma término → estado `cancelled`; emite evento `task.cancelled`/`run.cancelled`<br>5. Worktree, artefatos, checkpoints, diff parcial preservados para inspeção<br>6. Operador pode consultar evidência, criar nova run reaproveitando trabalho |
| **Fluxos Alternativos** | **A1:** Cancelamento de tarefa específica em swarm → dependentes bloqueadas; independentes continuam<br>**A2:** Processo não termina em timeout → força kill (SIGKILL/taskkill /F); registra `cancel_failed` mas preserva arquivos |
| **Fluxos de Exceção** | **E1:** Processo órfão (parent morreu) → reconciliação detecta e limpa; trabalho preservado<br>**E2:** Disco cheio durante preservação → erro persistível; run fica `cancelled_partial` |
| **Pós-condições** | Nenhum processo remanescente; worktree e evidência íntegros; estado final consultável; nova run pode ser submetida com mesmo objetivo |

---

#### UC05 — Descoberta e Ativação Controlada de Ferramenta Local (MCP / Skill)

| Elemento | Descrição |
|----------|-----------|
| **Ator Primário** | Operador |
| **Pré-condições** | Discovery opt-in habilitado; raízes autorizadas configuradas (RF22) |
| **Fluxo Principal** | 1. Operador dispara `discovery scan` em raiz autorizada (RF22)<br>2. `DiscoveryService` varre filesystem; para cada manifesto (skill, MCP, memory, session) calcula SHA-256<br>3. Registra `DiscoveredResource` com status `untrusted`, hash, capabilities declaradas, proveniência<br>4. Operador consulta recursos descobertos; vê `untrusted` com detalhes<br>5. Operador aprova recurso específico via API/CLI → status `approved` (RF22)<br>6. Recurso aprovado fica disponível para inclusão em perfis (RF17)<br>7. Em uso: se hash no disco divergir do registrado → transição automática `untrusted` + bloqueio (RF22) |
| **Fluxos Alternativos** | **A1:** Operador rejeita → status `rejected`; não aparece em catálogo<br>**A2:** Recurso já aprovado tem hash alterado → `untrusted` + notificação; nova aprovação necessária |
| **Fluxos de Exceção** | **E1:** Arquivo fora de raiz autorizada → ignorado, log de auditoria<br>**E2:** Manifesto inválido ou capability desconhecida → `untrusted` com motivo; não ativável<br>**E3:** Tentativa de usar recurso `untrusted` em perfil → erro 422 na validação pré-execução (RF17) |
| **Pós-condições** | Catálogo só contém recursos `approved`; proveniência e hash rastreáveis; ativação automática impossível; revogação de aprovação bloqueia novos usos |

---

### 3.4 Regras de Negócio (RB01 a RB20)

| ID | Regra | Descrição |
|----|-------|-----------|
| **RB01** | Código de processo zero e texto `DONE` não bastam para aceite. | Aceite exige checks obrigatórios passando e evidência de alteração (patch/commit). |
| **RB02** | Simulação deve aparecer como simulação e não pode ser integrada como trabalho real. | Campo `simulated: true` no `TaskResult` bloqueia integração automática. |
| **RB03** | Tarefa de implementação exige patch ou justificativa verificável de ausência de mudança; revisão pode entregar relatório. | `TaskResult` sem patch e sem justificativa documentada → `needs_context` ou `failed`. |
| **RB04** | Aceite de tarefa não equivale a integração concluída; integração requer checks da combinação. | `accepted` → `ready_for_integration`; merge só após checks integrados passarem. |
| **RB05** | Permissões deste checkout não autorizam publicação em todos os projetos operados pelo produto. | Publicação em remote exige configuração/política explícita por run; não é padrão. |
| **RB06** | Espera, fallback e reparo obedecem a orçamento; custo desconhecido permanece desconhecido. | `unknown` nunca vira zero; orçamento esgotado → falha controlada, não estimativa. |
| **RB07** | Recursos descobertos localmente são não confiáveis até validação de origem, hash, capabilities, escopo e consentimento; existência no filesystem não autoriza ativação. | Estado inicial `untrusted`; transição só com aprovação de principal autenticado. |
| **RB08** | Memória persistente é opt-in, escopada e revogável; secrets e PII não entram em memória, eventos, prompts ou exportações sem política explícita. | Redaction obrigatório; consentimento pré-requisito; tabelas separadas de checkpoints. |
| **RB09** | Plugin, skill, MCP e transporte precisam declarar permissões e capabilities; incompatibilidade ou revogação bloqueia novos efeitos. | Manifesto validado na instalação; revogação → interrupção síncrona de efeitos. |
| **RB10** | A UI mostra decisões e estado persistido, mas não aprova, integra ou transforma texto em evidência sem comando e gate correspondentes. | UI é consumidora de API; ações de decisão requerem comando autenticado versionado. |
| **RB11** | Modo de orquestração (Swarm/Relay/Persistente) é imutável por run; definido no ProfileSnapshot. | Mudança de modo em run ativo → erro; novo run com modo diferente. |
| **RB12** | HITL (Humano-no-Loop) tem timeout configurável; expiração falha a tentativa com evidência. | Não espera infinita; operador notificado; timeout → `failed` + motivo `hitl_timeout`. |
| **RB13** | Conflito de merge não altera branch do operador; worktree de integração preservada para resolução. | Branch do usuário intocada; opções: reparo automático, descarte, resolução manual. |
| **RB14** | Auto-healing tem teto rígido de tentativas (`max_repair_attempts`, padrão 2); esgotamento = falha final. | Não há loop infinito de reparo; cada tentativa consome orçamento. |
| **RB15** | Quota/custo `unknown` ou `stale` nunca aparece como 100% disponível; exibição visual distinta. | Dashboard mostra `unknown` com ícone/cor específica; não engana operador. |
| **RB16** | Handoff entre provedores opera sobre o estado real do Git/Worktree (`git diff`, `git status` e checks) para workers CLI e retry de turno atômico para `tool_calls`. | `HandoffCheckpoint` estruturado no workspace; proibida costura cega de strings no meio de chamadas de ferramentas. |
| **RB17** | Snapshot de perfil (`ProfileSnapshot`) e preferências (`PreferenceSnapshot`) são imutáveis por run. | Alteração posterior não afeta runs em andamento; hash garante integridade. |
| **RB18** | Eventos SSE são sequenciais por run, com `Last-Event-ID` para replay; heartbeat impede timeout de proxy. | Ping a cada 15s; buffer ring para replay rápido; fallback para busca indexada no SQLite. |
| **RB19** | SQLite em modo WAL com `busy_timeout=5000`; transações curtas; foreign keys habilitadas. | Concorrência control plane + webhooks sem deadlock; integridade referencial. |
| **RB20** | Exportação e logs passam por redactor determinístico (regex + entropia) antes de exposição. | Tokens, chaves SSH, senhas, OAuth expurgados; nenhum segredo em artefatos/exportações. |

---

## 4. Pré-condições

Projeto acessível, base Git existente, configuração válida e executor com capacidade declarada. Credenciais ficam no mecanismo do provedor ou em referência de ambiente, sem entrar na spec. Certificação real é separada dos testes offline. Para RF16–RF30, áreas, repositórios, agentes, perfis, recursos descobertos, memória, extensões, transportes e orçamentos precisam de escopo e autorização explícitos; nenhum recurso é ativado por descoberta implícita. Modo de orquestração selecionado deve ser compatível com capabilities do executor.

## 5. Pós-condições

Toda execução consultável possui estado e evidência, inclusive falha/cancelamento. Sucesso significa tarefas obrigatórias aceitas e integração validada quando solicitada. Uma run apenas de revisão pode concluir sem merge. Critérios não atendidos impedem sucesso. Evidência exportável e auditável. Worktrees e runtime limpos conforme política de retenção; evidência necessária não expira.

## 6. Invariantes

Preservar trabalho do operador, separar inferência de comandos de execução, manter histórico de tentativas e decisões, não ocultar indisponibilidade. A UI deve oferecer navegação por teclado, foco visível, rótulos/roles, estados textuais além de cor, leitura por tecnologia assistiva, contraste WCAG AA e opção de redução de movimento. Checkpoint de execução não é memória adaptativa; memória requer consentimento, escopo, retenção e revogação. Eventos persistem na mesma transação da mudança de estado. Snapshots de perfil e preferências são imutáveis por run. Valores de quota/custo futuros incluem origem, frescor e nulabilidade, sem converter desconhecido em zero.

## 7. Falhas

| Cenário | Comportamento Obrigatório |
|---------|---------------------------|
| CLI ausente | Erro `executor_unavailable` antes do spawn; run `failed`; corrigir config e repetir |
| Quota ausente/desconhecida | Exibir `unknown`/`stale`; nunca inventar 100%; modo Persistente não espera cegamente |
| Conflito de merge | Preservar branch do operador; worktree de integração retida; status `conflicted`; opções de resolução |
| Perda de conexão SSE | Reconexão por `Last-Event-ID` recupera eventos; deduplicação por (run, seq); cursor expirado → 410 |
| Crash após ferramenta | Reconciliação de efeitos ambíguos antes de retry; estado `blocked` se ambíguo |
| Arquivo fora do escopo | Rejeitar resultado; reter diff para inspeção; não integrar |
| Discovery fora da raiz | Ignorar; log de auditoria; não registrar como recurso |
| Recurso com hash alterado | Transição automática `untrusted`; bloqueio execução; notificação operador |
| Memória sem consentimento | Recusa imediata (409); nenhuma persistência |
| Thread perdida / extensão incompatível | Não ativar, não persistir efeitos; registrar causa em auditoria |
| Orçamento esgotado | Run `budget_exhausted`; evidência preservada; extensão só com aprovação |
| Timeout HITL | Tentativa `failed` com motivo `hitl_timeout`; evidência preservada |

## 8. Desenvolvimento por tasks

Cada RF gera tasks na etapa indicada do [plano](../a_context/plano_desenvolvimento.md). Cada task deve conter ID, RF/RT relacionado, slice V0–V4, dependências, arquivos próprios, exemplo de entrada, saída esperada, evidência, teste negativo e status `proposto/não implementado` quando a capacidade ainda não tiver gate concluído. O [PRD técnico](prd_tecnico.md) fornece a primeira decomposição implementável. RF não pode ser marcado concluído apenas porque sua documentação foi criada.

A rastreabilidade mínima é:

```text
RF -> slice -> etapa S/M -> task técnica -> evidência -> caso negativo
```

Para RF16–RF30, as tasks futuras devem cobrir autorização, proveniência, consentimento, revogação, reconexão, acessibilidade, isolamento, modos de orquestração, HITL, resolução de conflitos, budgeting e empacotamento PR antes de anunciar a capacidade. O contrato técnico, o modelo de dados e a arquitetura precisam ser atualizados em uma etapa documental própria antes da implementação dessas entidades.

## 9. Exemplos de Aceite

**Núcleo verificável (RF01–RF08):** Dada uma função com teste falhando em repo temporário, quando o executor corrige somente o arquivo permitido e o check passa, então a tarefa fica pronta para revisão. Quando aceita e combinada numa branch de integração com checks aprovados, o run conclui. Se o processo apenas imprime uma correção, a tarefa não é aceita.

**Modos de orquestração (RF26):** Dado um run em modo `swarm` com DAG de 3 tarefas (T1→T2, T1→T3), quando T1 é aceita, então T2 e T3 são despachadas em paralelo respeitando `max_parallel_worktrees`. Dado modo `relay`, quando executor atinge rate limit, então handoff carrega checkpoint estruturado e nova tentativa inicia com provedor fallback. Dado modo `persist`, quando janela de 5h fecha, então run pausa e retoma automaticamente na reabertura sem gasto de tokens.

**HITL (RF27):** Dada uma tarefa que executa comando `npm publish` (marcado como alto risco), quando o executor solicita aprovação, então o operador recebe evento `task.needs_approval` com detalhes do comando; ao aprovar, a execução retoma; ao rejeitar, a tentativa falha com evidência.

**Resolução de conflito (RF28):** Dada integração com conflito 3-way, quando o operador escolhe "reparo automático", então o sistema cria tentativa de `merge_repair` com orçamento próprio; se checks passam, integração prossegue; se falha, operador escolhe descarte ou resolução manual.

**Budgeting (RF29):** Dado run com teto $2.00, quando custo acumulado atinge $1.60 (80%), então alerta emitido; quando atinge $2.00, run pausa e solicita extensão; se operador aprova $1.00 adicional, run retoma; se recusa, run finaliza `budget_exhausted`.

**Empacotamento PR (RF30):** Dado run concluído com 3 tarefas aceitas, quando política de publicação autoriza, então branch `pr/<run_id>` é criada no remote com descrição contendo objetivo, 3 commits, saída de 12 checks, diff sumarizado (4 arquivos, +120/-45 linhas), métricas (tokens: 45k in / 18k out, custo: $0.87, duração: 14min).

**Perfil e observabilidade (RF17, RF19):** Dada uma tarefa em área autorizada, quando o usuário seleciona perfil com Claude Code (driver CLI proposto, `is_certified=false`) e modelo via OmniRoute, então o Hydra exibe capabilities, origem, versão, permissões e limites antes da execução. Fila, duração, tokens ou custo sem fonte aparecem como `unknown`/`stale`; nenhum valor é inventado.

**Memória e discovery (RF21, RF22):** Dada uma preferência do usuário, quando o Hydra solicita consentimento explícito e o usuário aprova, então a memória registra escopo, versão, origem, retenção e revogação. Um item descoberto fora da raiz autorizada, com hash conflitante ou sem capability conhecida, não é ativado.

**Sessões e extensões (RF18, RF24):** Dada uma execução com threads, quando a conexão cai, o Hydra reconcilia eventos por cursor e deduplica sem declarar conclusão prematura. Uma extensão sem manifesto compatível, permissão ou confiança não inicia nem produz efeitos.

---

## 10. Glossary e Acrônimos

| Termo | Significado |
|-------|-------------|
| API | Application Programming Interface |
| AST | Abstract Syntax Tree |
| CDP | Chrome DevTools Protocol |
| CLI | Command Line Interface |
| DAG | Directed Acyclic Graph |
| DBC-9 | Design by Contract — 9 partes (Purpose, Why, Contract, Preconditions, Postconditions, Invariants, Failure Modes, How, Examples) |
| ER | Entity-Relationship |
| Git | Sistema de controle de versão distribuído |
| HITL | Human-in-the-Loop |
| HTTP | Hypertext Transfer Protocol |
| IDE | Integrated Development Environment |
| JSON | JavaScript Object Notation |
| MCP | Model Context Protocol |
| MER | Modelo Entidade-Relacionamento |
| MVP | Minimum Viable Product |
| OmniRoute | Gateway opcional de inferência, quota e fallback |
| OpenAPI | Especificação de API REST |
| PR | Pull Request |
| PRD | Product Requirements Document |
| RF | Requisito Funcional |
| RNF | Requisito Não-Funcional |
| RT | Requisito Técnico |
| SSE | Server-Sent Events |
| SSH | Secure Shell |
| Swarm | Modo de orquestração paralela com worktrees isoladas |
| Relay | Modo de orquestração com handoff entre provedores |
| Persistente | Modo de orquestração com auto-resume por janela de cota |
| SQLite | Banco de dados relacional embarcado |
| UI | User Interface |
| UUID | Universally Unique Identifier |
| WAL | Write-Ahead Logging (modo SQLite) |
| WebSocket | Protocolo de comunicação full-duplex |
| YAML | YAML Ain't Markup Language |