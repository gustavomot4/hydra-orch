# prd_tecnico — Especificação Técnica e Decomposição de Tarefas

**Identificador Formal:** `prd_tecnico.md`
**Caminho Canônico:** `doc/b_spc/prd_tecnico.md`
**Versão:** `v02_00_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch, complementando [`prd_funcional.md`](prd_funcional.md), [`../a_context/plano_desenvolvimento.md`](../a_context/plano_desenvolvimento.md) e [`../g_code/architecture.md`](../g_code/architecture.md).
**Escopo:** Requisitos técnicos (RT01 a RT30), requisitos não-funcionais (RNF01 a RNF10), contratos formais de execução, fronteiras arquiteturais, máquinas de estado, esquemas DDL, API REST, algoritmos centrais (Swarm Wave 0+1 e Handoff por Estado Git/Worktree), critérios negativos e tasks T01 a T28. Ideias pós-M4 residem em [`../a_context/ideia_futura.md`](../a_context/ideia_futura.md).

---

Status: arquitetura técnica normativa proposta, sem alegação de implementação prévia. RT01–RT12 e T01–T08 cobrem o núcleo inicial verificável (M1); RT13–RT30 e T09–T28 cobrem a expansão de control plane (áreas, perfis, sessões, observabilidade, memória, discovery, extensões, acessibilidade, transportes, modos de orquestração Wave 0+1 e Handoff Git, HITL, resolução de conflitos + *Contract Amendment*, budgeting, empacotamento PR). Ideias periféricas (antigos V5/V6) estão isoladas em [`../a_context/ideia_futura.md`](../a_context/ideia_futura.md). Complementa o [PRD funcional](prd_funcional.md) e o [plano](../a_context/plano_desenvolvimento.md). Modelagem relacional em [MER](../d_mer/mer.md) e classes em [diagrama de classes](../e_class/diagrama_classe.md).

## 1. Propósito

Implementar execução verificável local com contratos tipados, estado durável, drivers explícitos, isolamento Git e integração validada, preservando o proxy de inferência. Suportar três modos de orquestração — **Swarm** (paralelo com worktrees), **Relay** (handoff estruturado entre provedores) e **Persistente** (auto-resume por janela de cota) — com seleção explícita e transições governadas por políticas.

A expansão técnica detalha a infraestrutura necessária para suportar interface visual de primeira classe, gestão de áreas de trabalho e repositórios múltiplos, catálogo e perfis de agentes (incluindo Claude Code, OpenCode e Codex como integrações propostas não certificadas), sessões e threads multiagente com SSE replay, métricas com unknown/stale explícitos, seleção adaptativa com OmniRouter opcional, memória consentida separada de checkpoints, discovery local controlado, plugins isolados, acessibilidade verificável, transportes certificados, interação humano-no-loop, resolução assistida de conflitos, governança de orçamento e empacotamento de entrega — sempre mantendo o núcleo de execução verificável isolado de saídas textuais não comprovadas.

## 2. Justificativa

Consolidar os caminhos duplicados de core/engine e remover sucesso fabricado. FastAPI/CLI são entradas do mesmo serviço de aplicação; engines definem estratégia; bridges executam transporte; adapters fornecem inferência. SQLite atende o primeiro operador local; não há necessidade atual de banco distribuído.

A arquitetura proposta separa claramente os serviços de control plane (áreas, repositórios, catálogo, perfis, sessões, métricas, memória, discovery, extensões, orçamento, conflitos, empacotamento) da execução em workspace e da inferência de modelo. O OmniRouter continua sendo camada opcional de roteamento; o banco relacional SQLite local permanece a base transacional, sem introdução de brokers distribuídos desnecessários.

## 3. Contrato técnico

### 3.1 Requisitos Técnicos — Núcleo (RT01 a RT12)

| ID | Obrigação | Verificação |
|----|-----------|-------------|
| **RT01** | Config tipada resolve alias → executor/provedor/modelo; rejeita desconhecidos; referências de segredo externas | Config inválida não inicia subprocesso; modo direto sem gateway; aliases mapeados em `config.yaml` |
| **RT02** | RunSpec/TaskSpec versionados e imutáveis por tentativa; estados separados de processo, tarefa e integração | Validação Pydantic (`model.py`) e tabela de transições; `schema_version` em todo spec |
| **RT03** | Estado e evento na mesma transação; sequência única por run; idempotência de comandos | Concorrência/restart não duplicam run nem evento lógico; chave `Idempotency-Key` + hash do payload |
| **RT04** | Executor usa argv específico, cwd resolvido, env filtrado, timeout e cancelamento de árvore | Fake subprocess só em dry-run; CLI ausente → erro `executor_unavailable`; tree kill verificado no SO |
| **RT05** | Git opera em SHA fixo e worktrees reais; integração serializada por projeto | Falha de Git não cria diretório substituto; conflito preserva worktree; `git worktree add` real |
| **RT06** | Check registra comando, cwd, SHA, tempo, exit code e saída como artefato | Check ausente/falho bloqueia aceite; combinação é testada novamente; artefato com hash SHA-256 |
| **RT07** | Scheduler valida DAG em Duas Ondas (Wave 0 Fundação Compilável -> Wave 1 Swarm Paralelo), ownership, trava de dependências (`pyproject.toml`/`package.json`) na Wave 1 e limite de concorrência (`max_parallel_worktrees`) | Ciclo recusado (Kahn/DFS); Wave 1 aguarda Wave 0 `accepted`; mutação de manifesto de pacotes na Wave 1 recusada; semáforo controla paralelismo |
| **RT08** | Handoff por Estado Git/Worktree (`git status`, `git diff`, checks) para agentes CLI e Retry de Turno Atômico para chamadas de API com `tool_calls` | Crash depois de efeito exige reconciliação; `HandoffCheckpoint` estruturado no workspace; proibida costura cega de strings em `tool_calls` truncados |
| **RT09** | Gateway distingue disabled/optional/required; quota `observed`/`stale`/`unknown` | HTTP simulado cobre offline, 429, erro auth; circuit breaker; fallback de rotas |
| **RT10** | API autoriza comandos locais, restringe origens e caminhos; UI usa contrato comum | Token local obrigatório; CORS allowlist estrita; path traversal recusado; redaction em eventos |
| **RT11** | Artefatos com hash, tamanho e caminho relativo; retenção explícita | Artefato ausente ou adulterado bloqueia integração; gravação atômica (temp → final → ref) |
| **RT12** | CI offline e certificação real por driver/SO separadas | Suíte não exige conta, GPU ou localhost externo; driver real certificado em etapa separada |

### 3.2 Requisitos Técnicos — Expansão (RT13 a RT30)

| ID | Obrigação | Verificação |
|----|-----------|-------------|
| **RT13** | Hierarquia Area → Workspace → Project → Repository com raiz canônica, branch, SHA base, escopo de arquivos e autorização explícita | Recusa repositório fora da allowlist, symlink externo à raiz, repo sem concessão válida; FKs e constraints |
| **RT14** | Catálogo de agentes, executores e capabilities com proveniência e certificação por driver/SO; Claude Code, OpenCode, Codex propostos como não certificados | Capability ausente falha antes do spawn; driver não certificado bloqueado em modo produto; ausência de CLI é erro |
| **RT15** | Perfis de execução e combos combináveis com validação pré-execução e snapshot imutável com hash por run | Combinação incompatível falha antes de processo (422); alteração posterior não afeta runs em andamento; `ProfileSnapshot` com hash |
| **RT16** | Sessões, threads e eventos duráveis com sequência monotônica, relação pai/filho e SSE com cursor Last-Event-ID, replay e deduplicação | Queda de conexão não perde nem duplica eventos; cursor expirado → 410; visibilidade de thread não implica swarm |
| **RT17** | Métricas operacionais vinculadas a run/attempt/session com valor, unidade, fonte, timestamp e status observed/stale/unknown | Ausência de dado → `unknown` (nunca zero); agregações com parcelas desconhecidas → sinalizadas como parciais |
| **RT18** | Roteamento adaptativo com registro auditável de candidatos, critérios, capabilities, fallback e origem da decisão; OmniRouter opcional | Modo direto opera sem gateway; decisão reproduzível e auditável (`RouteDecision`); candidato inelegível nunca selecionado |
| **RT19** | Memória adaptativa consentida com escopo, autor, versão, retenção e revogação, estritamente separada de checkpoints de execução | Gravação sem ConsentRecord → 409; revogação bloqueia novos runs; checkpoints nunca alimentam memória automaticamente |
| **RT20** | Discovery local opt-in restrito a raízes autorizadas, com proveniência, hash e aprovação explícita antes de ativação | Recurso fora da raiz, hash modificado ou capability desconhecida → `untrusted`; ativação automática proibida |
| **RT21** | Skills, MCPs e segredos gerenciados por referências externas; permissões declaradas e env filtrado no spawn | Valor bruto de segredo ausente de perfis, eventos, prompts, memória, artefatos; MCP sem permissão não inicia |
| **RT22** | Extensões e plugins com manifesto versionado, processo isolado, consentimento, revogação e rollback | Manifesto incompatível não inicia; revogação bloqueia novos efeitos; sem acesso a DB core ou segredos não autorizados |
| **RT23** | Acessibilidade verificável e preferências reversíveis com snapshot por run | UI: teclado, foco visível, roles semânticos, estados textuais, contraste WCAG AA, redução de movimento; reversão restaura prévio |
| **RT24** | Transportes locais/remotos certificados com alvo, identidade, healthcheck e falhas tipadas | Alvo incorreto ou host key SSH divergente falha observavelmente; sessões concorrentes isoladas; mock não substitui certificação |
| **RT25** | Segurança transversal: autenticação local obrigatória, CORS allowlist estrita, central de redaction | Origem não autorizada, CORS wildcard com credenciais, token inválido, path traversal → recusados; PBKDF2/Argon2 para tokens |
| **RT26** | Orquestração por modo: Swarm em 2 Ondas (Wave 0 Fundação + Wave 1 Worktrees Paralelas + merge serializado), Relay (handoff por estado Git/Worktree entre provedores), Persistente (pausa/retomada automática por janela de cota) | Modo imutável por run (ProfileSnapshot); Swarm valida Wave 0 -> Wave 1 + semáforo; Relay carrega HandoffCheckpoint; Persistente monitora `window_reset_at` |
| **RT27** | HITL (Humano-no-Loop): pausa intermediária `needs_context` / `needs_approval` com timeout configurável, notificação SSE/UI, retomada com resposta do operador | Evento emitido; operador responde via API; timeout → `failed` + `hitl_timeout`; evidência preservada; resposta injetada no contexto |
| **RT28** | Resolução assistida de conflitos de merge e *Contract Amendment*: relatório 3-way, protocolo de emenda de contrato da Wave 0 e opções (reparo automático por agente, descarte, resolução manual) | Conflito → `conflicted` + relatório; emenda atualiza base e revalida dependentes; `merge_repair` com orçamento próprio; merge só após checks |
| **RT29** | Governança de orçamento: teto USD/tokens/tempo por run; alerta 80%, congelamento 100% com solicitação de extensão ao operador | `unknown` não vira zero nem bloqueia; aprovação estende orçamento; recusa → `budget_exhausted`; métricas com proveniência |
| **RT30** | Empacotamento de entrega: criação automática de branch PR no remote (quando autorizado) com descrição estruturada (objetivo, commits, checks, diff, métricas, decisões) | Descrição padrão gerada; exportação redigida; autorização de publicação separada da execução; dossier auditável |

---

### 3.3 Fronteiras Arquiteturais e Modos de Instalação

O Hydra opera como o **control plane de engenharia de software**, o **OmniRoute** como um gateway opcional de inferência e a futura interface visual como uma consumidora estrita da API do Hydra.

#### Fronteiras de Responsabilidade

```text
Interface visual (web, desktop ou mobile)
  -> consulta projetos, execuções, worktrees, diffs, quotas e decisões (somente read models)
  -> emite comandos explícitos autenticados; nunca decide resultados nem infere sucesso
Hydra control plane (FastAPI + SQLite WAL + Git workspace)
  -> planeja, decompõe tarefas, isola worktrees, valida contratos, executa checks, integra e persiste estado
  -> núcleo de verdade do sistema: a prova de engenharia é o artefato (patch, check exit code, evento persistido)
Executores de agentes (workers)
  -> Claude Code, OpenAI Codex CLI, Gemini CLI, OpenCode, Aider, IDE bridge ou agente local
  -> rodam isolados em worktrees dedicadas, sem autoridade para aprovar o próprio trabalho
OmniRoute (gateway opcional de inferência)
  -> roteia requisições de LLM, aplica fallbacks, rastreia cotas de 5h e janelas de rate limit
  -> desacoplado: o Hydra opera nativamente em modo direto (sem OmniRoute) se configurado
Git e ambientes de execução
  -> branches, worktrees reais, semáforo de concorrência, testes herméticos e branches de integração
```

#### Modos de Instalação

| Perfil | Componentes Ativos | Cenário Operacional |
| :--- | :--- | :--- |
| **Direto** | Hydra + CLI autenticada local (ex.: Claude Code / Aider) | Primeiro uso, testes e desenvolvimento offline simplificado sem gateway |
| **Gateway** | Hydra + OmniRoute Gateway + executores múltiplos | Rotação automática de assinaturas ($20), cotas, modelos free e fallbacks |
| **Remoto (SSH)** | Perfil Gateway + Host SSH remoto (GPU local/casa) | Processamento de builds, migrations e testes pesados em PC remoto via túnel |
| **Visual** | Qualquer perfil acima + cliente Web / UI | Operação visual completa, inspeção gráfica de diffs e aprovação humana (HITL) |

O `config.yaml` utiliza as chaves `omniroute.enabled` e `omniroute.connection_mode` (`disabled`, `optional`, `required`) para governar o gateway. O Hydra falha observavelmente antes de qualquer spawn se o modo for `required` e o daemon do gateway estiver inacessível.

---

### 3.4 Contrato Canônico de Execução Verificável

O contrato canônico de execução padroniza toda a comunicação entre o control plane, executores de agentes, gateways de inferência e a interface visual. Este contrato estabelece que texto gerado por LLMs nunca é tratado como trabalho de engenharia comprovado sem evidências tangíveis de execução.

#### Entidades Centrais de Execução

| Entidade | Responsabilidade Arquitetural | Estado Mínimo Obrigatório |
| :--- | :--- | :--- |
| `RunSpec` | Execução completa iniciada pelo operador ou trigger | `run_id`, `project_id`, `objective`, `repo_root`, `base_sha`, `base_branch`, `budget_policy`, `orchestration_mode`, `integration_policy`, `idempotency_key`, `tasks`, `schema_version` |
| `TaskSpec` | Unidade atômica e delimitada entregue a um executor | `task_id`, `run_id`, `objective`, `acceptance_criteria` (comandos de check), `dependencies`, `allowed_paths`, `assigned_executor` |
| `TaskAttempt` | Tentativa concreta de execução de uma tarefa | `attempt_id`, `task_id`, `ordinal` (1, 2, ...), `provider`, `model`, `started_at`, `finished_at`, `exit_reason` |
| `TaskResult` | Resultado técnico verificável da tentativa | `result_id`, `attempt_id`, `process_status`, `task_status`, `patch_commit_sha`, `checks_executed`, `artifacts`, `risk_level`, `simulated` |
| `RunEvent` | Linha do tempo imutável e monotônica de eventos | `seq` (monotônico), `run_id`, `timestamp`, `event_type`, `correlation_id`, `redacted_payload` |
| `HandoffCheckpoint` | Contexto de continuidade independente de provedor | `checkpoint_id`, `attempt_id`, `instructions`, `git_sha`, `affected_files`, `tools_executed`, `partial_output`, `next_step` |

#### Separação Estrita de Estados

O ciclo de vida do processo do SO e o ciclo de vida da tarefa lógica são rigorosamente desacoplados:

```text
Ciclo de Vida do Processo (SO):
  queued -> running -> exited | timed_out | cancelled | crashed

Ciclo de Vida da Tarefa (Engenharia):
  pending -> running -> needs_context | blocked | failed | ready_for_review -> accepted | rejected | cancelled

Ciclo de Vida da Integração:
  not_integrated -> integrating -> integrated | conflicted | failed
  not_integrated | conflicted | failed -> discarded
```

**Invariante de Aceite:** Um processo que termina em `exited` com código de retorno zero (`exit_code = 0`) **NÃO** implica que a tarefa foi aceita. Respostas simuladas, saídas sem patch ou tarefas com ausência de execução de checks obrigatórios são categorizadas como falhas de execução e têm o avanço para merge bloqueado.

#### Implementação tipada S02 / T02

O contrato implementado está em `hydra_orch.model` e na [spec S02](contrato_execucao.md). Os exemplos de classes e DTOs abaixo são propostas complementares; em divergência de nomes ou tipos com o núcleo implementado, prevalecem S02 e os schemas Pydantic gerados por `model_json_schema()`.

- Versão inicial `schema_version: "1.0"`; campos extras recusados; specs congeladas com coleções em tuplas, serializadas como arrays JSON.
- `CheckSpec.command` é um array de argumentos com `check_id`, preservando espaços e argumentos vazios após o executável. Não há interpretação de shell. IDs, referências de checks, limites e DAG são validados antes da execução.
- O modo canônico é `persistent`, alinhado à CLI existente; o primeiro run usa `relay`. A política inicial de integração é exclusivamente `explicit_review`.
- Estados de run, processo, tarefa e integração são enums separados. `transition_status` valida adjacência, sem autorizar efeitos. Resultados encerrados/rejeitados permanecem auditáveis; nova tentativa tem nova identidade.
- `review_result` compara revisão atual, atribuição e todos os checks obrigatórios antes do aceite; rejeição pode registrar checks ainda incompletos. `assert_integrable` exige aceite explícito e resultado real. O commit de patch deve ser diferente da base.
- Validação de metadados não substitui leitura/hash de artefatos, checks realmente executados, persistência ou autenticação. Esses gates pertencem a T03–T07. Simulação nunca autoriza integração.

#### Requisitos Normativos para Integrar uma Tarefa

Para que o resultado de uma tarefa seja aceito e elegível para merge na branch de integração:
1. **Estado Observável:** A tentativa deve terminar em estado observável e persistido no SQLite (`checkpoints.sqlite`).
2. **Execução Real Comprovada:** O campo `simulated` deve ser obrigatoriamente `false` (exceto em modo dry-run explícito).
3. **Atribuição Git Exclusiva:** As alterações de código devem estar confinadas e comprovadamente atribuídas à worktree e branch da respectiva tarefa (`.orchestrator/worktree/<run_id>_<task_id>`).
4. **Evidência de Checks:** Todos os comandos de verificação definidos em `TaskSpec.acceptance_criteria` devem ter sido executados, com exit code `0`, duração e saídas stdout/stderr gravadas como artefatos indexados por SHA-256.
5. **Merge Serializado e Auditado:** A integração deve ocorrer na branch dedicada `integrate/<run_id>`, registrando hash de sucesso ou relatório de conflito 3-way (`ConflictReport`) antes da remoção da worktree.
6. **Preservação de Falhas:** Em caso de falha de teste ou conflito, os artefatos, worktrees e evidências permanecem preservados para inspeção pelo operador ou ação de auto-healing.

#### Handoff Estruturado entre Provedores

A transferência de contexto entre modelos (modos Relay e Persistente) não se apoia em histórico de chat nem em concatenação de strings parciais no meio de um stream SSE. O `HandoffCheckpoint` opera em dois níveis estritos:
1. **Nível de Workspace / Agente CLI (`worktree_state`):** Agrega o objetivo original, critérios de aceite, estado físico da worktree (`git_sha`, `git status --porcelain`, `git diff`), resumo das ferramentas invocadas e relatório de checks já aprovados/pendentes, permitindo que o próximo executor assuma a própria worktree exatamente de onde parou.
2. **Nível de Proxy HTTP (`/v1/chat/completions` — `atomic_turn_retry`):** Se uma requisição de inferência ou `tool_calls` cair por erro `429` ou corte de stream antes do fechamento do JSON (`finish_reason != 'stop'` e `!= 'tool_calls'`), o proxy descarta os chunks truncados daquele turno e reenvia a requisição completa do turno para o provedor de fallback.

#### Catálogo Mínimo de Eventos para UI e Observabilidade

Os eventos emitidos via SSE possuem sequência monotônica (`id: <seq>`) e redaction compulsória de credenciais:
- **Ciclo de Run:** `run.created`, `run.started`, `run.waiting`, `run.resumed`, `run.finished`, `run.cancelled`.
- **Ciclo de Tarefa:** `task.queued`, `task.started`, `task.needs_context`, `task.needs_approval`, `task.ready_for_review`, `task.accepted`, `task.rejected`, `task.completed`, `task.failed`, `task.cancelled`.
- **Tentativas e Handoff:** `attempt.started`, `attempt.provider_selected`, `attempt.rate_limited`, `attempt.handoff_created`, `attempt.finished`.
- **Artefatos e Integração:** `artifact.created`, `check.started`, `check.finished`, `merge.started`, `merge.completed`, `merge.conflicted`.
- **Infraestrutura e Sessão:** `heartbeat`, `budget.alerted`, `budget.frozen`.

---

### 3.5 Serviços e módulos

**Núcleo (existentes/propostos):**
- `core/run_service.py` — coordena run/revisão/cancelamento
- `core/checkpointer.py` — persistência canônica (SQLite WAL)
- `core/git_workspace.py` — operações Git centralizadas (worktree, diff, merge, checkout)
- `engine/swarm.py` — estratégia Swarm (DAG, scheduler, despacho paralelo)
- `engine/relay.py` — estratégia Relay (handoff, checkpoint, seleção fallback)
- `engine/healer.py` — auto-healing real (extração de falha, prompt de reparo, teto de tentativas)
- `bridge/worker_runner.py` — interface AgentExecutor por drivers (CLI, SSH, CDP)
- `bridge/ssh_tunnel.py` — único gestor SSH (túnel, healthcheck, host key)
- `core/router.py` — fachada de inferência (chat/completions), não inicia mutações Git

**Expansão (propostos em `src/hydra_orch/`):**
- `core/workspace_registry.py` — hierarquia Area/Workspace/Project/Repository + Authorization
- `core/agent_registry.py` — catálogo AgentDefinition, CapabilityDeclaration, certificação driver/SO
- `core/profile_service.py` — Profile, ProfileResolver (validação pré-exec), ProfileSnapshot (hash imutável)
- `core/session_service.py` — Session, Thread, eventos monotônicos, SSE replay/dedup
- `core/metrics.py` — MetricSample (observed/stale/unknown), agregações parciais
- `core/route_selector.py` — RouteSelector (DirectSelector, OmniRouteSelector), RouteDecision auditável
- `core/memory_store.py` — MemoryEntry (consentido, escopado, versionado, revogável)
- `core/consent.py` — ConsentRecord (requested/granted/revoked/expired)
- `core/discovery.py` — DiscoveryService (opt-in, allowlist, hash, untrusted→approved)
- `core/extension_host.py` — ExtensionHost (processo isolado, manifesto, consentimento, revogação, rollback)
- `core/auth.py` — AuthPolicy (token local, escopos, PBKDF2/Argon2)
- `core/redaction.py` — Redactor (regex + entropia, intercepta eventos/logs/artefatos)
- `core/budget.py` — BudgetGovernor (tetos, alertas, congelamento, extensão)
- `core/conflict_resolver.py` — ConflictResolver (relatório 3-way, merge_repair, opções)
- `core/packaging.py` — PRPackager (branch PR, descrição estruturada, exportação)
- `core/skill_registry.py` — Registro e validação de skills e referências de segredos (`SecretRef`)
- `bridge/mcp_client.py` — Cliente de integração com servidores MCP autorizados

**Migração:** Migrar consumidores antes de remover `core/swarm.py` (legado), `core/ssh_tunnel.py` (duplicado), `engine/checkpointer.py` (duplicado). Preservar imports temporariamente com wrappers e teste de compatibilidade. Não ligar engine atual diretamente à API sem corrigir gates.

---

### 3.6 Entidades, estados e interfaces da expansão (proposto)

Todas as entidades e interfaces abaixo são especificações conceituais para realização futura dos requisitos `RF16` a `RF30`. Elas não afirmam implementação prévia.

#### Entidades de domínio da expansão

| Entidade | Campos e garantias mínimos |
|----------|----------------------------|
| `Area` | `area_id`, `name`, `description`, `owner_principal_id`, `created_at`; isolamento de contexto |
| `Workspace` | `workspace_id`, `area_id`, `name`, `status ∈ {active, archived}`; contexto operacional |
| `Project` | `project_id`, `workspace_id`, `name`, `metadata`; agrega múltiplos repositórios |
| `Repository` | `repository_id`, `project_id`, `root_canonical`, `base_branch`, `base_sha`, `allowed_paths`, `authorization_id`; validação contra traversal |
| `Authorization` | `authorization_id`, `resource_ref`, `principal_id`, `scopes`, `granted_at`, `revoked_at`; revogação imediata |
| `AgentDefinition` | `agent_id`, `name`, `version`, `driver_type`, `declared_capabilities`, `limitations`, `is_certified`; Claude Code, OpenCode, Codex propostos com `is_certified=false` |
| `CapabilityDeclaration` | `name`, `version`, `supports_tools`, `supports_workspace`, `supports_cancellation`, `supports_streaming`, `certified_on` (driver+SO+data) |
| `Profile` | `profile_id`, `name`, `agent_ref`, `model_ref`, `executor_ref`, `skills_refs`, `mcp_refs`, `memory_policy`, `resource_limits`, `orchestration_mode ∈ {swarm, relay, persist}` |
| `ProfileSnapshot` | `snapshot_hash`, `profile_id`, `effective_config_json`, `created_at`; imutável por run |
| `Session` | `session_id`, `run_id` opcional, `origin_ref`, `agent_ref`, `state`, `created_at`, `closed_at` |
| `Thread` | `thread_id`, `session_id`, `parent_thread_id` opcional, `agent_ref`, `state`, `last_seq` |
| `MetricSample` | `sample_id`, `run_id`, `scope`, `kind ∈ {queue, duration, tokens_in, tokens_out, cost}`, `value` (nullable), `unit`, `source`, `observed_at`, `status ∈ {observed, stale, unknown}` |
| `RouteDecision` | `decision_id`, `run_id`, `candidates_json`, `selected_route`, `reason`, `fallback_chain`, `decision_source ∈ {hydra, omnirouter, operator}`, `timestamp` |
| `MemoryEntry` | `memory_id`, `scope_type`, `scope_id`, `content_redacted`, `author_ref`, `consent_id`, `version`, `retention_policy_id`, `status ∈ {pending_consent, active, revoked, expired}` |
| `ConsentRecord` | `consent_id`, `principal_id`, `purpose`, `scope`, `granted_at`, `revoked_at` |
| `DiscoveredResource` | `discovery_id`, `resource_type ∈ {skill, mcp, memory, session}`, `source_canonical_path`, `content_hash`, `capabilities_json`, `trust_status ∈ {untrusted, approved, rejected, revoked}` |
| `SkillDefinition` | `skill_id`, `name`, `version`, `manifest_ref`, `permissions_declared`, `checksum` |
| `McpDefinition` | `mcp_id`, `server_name`, `transport_type`, `endpoint`, `secret_ref`, `declared_tools`, `permissions` |
| `SecretRef` | `secret_name`, `provider_type ∈ {env, vault, keyring}`, `source_key`; valor bruto nunca armazenado |
| `ExtensionManifest` | `extension_id`, `name`, `version`, `entrypoint`, `permissions_required`, `compatible_api_version`, `checksum` |
| `ExtensionInstall` | `install_id`, `extension_id`, `status ∈ {proposed, consented, installed, active, disabled, quarantined, revoked}`, `installed_at` |
| `Preference` | `preference_id`, `scope_type`, `scope_id`, `key`, `value_json`, `source ∈ {explicit, inferred_opt_in}`, `version` |
| `PreferenceSnapshot` | `run_id`, `preferences_hash`, `resolved_preferences_json`; imutável por run |
| `TransportDefinition` | `transport_id`, `type ∈ {local, ssh, ide, cdp, remote}`, `target_identity`, `capabilities`, `is_certified` |
| `TransportHealth` | `transport_id`, `status ∈ {unknown, healthy, degraded, unreachable}`, `last_check_at`, `error_detail` |
| `AccessToken` | `token_hash`, `principal_id`, `scopes`, `expires_at`, `revoked_at`; valor plano nunca persistido |
| `HandoffCheckpoint` | `checkpoint_id`, `attempt_id`, `instructions_json`, `git_sha`, `diff_artifact_ids`, `tools_executed_json`, `partial_output_json`, `next_step`, `created_at` |
| `BudgetPolicy` | `budget_id`, `run_id`, `max_usd`, `max_tokens_in`, `max_tokens_out`, `max_wall_seconds`, `alert_threshold_pct`, `status ∈ {active, alerted, frozen, exhausted}` |
| `ConflictReport` | `conflict_id`, `integration_id`, `base_sha`, `ours_sha`, `theirs_sha`, `conflicted_files_json`, `resolution_options`, `status ∈ {open, auto_repair, manual, discarded}` |
| `PRPackage` | `package_id`, `run_id`, `pr_branch`, `description_markdown`, `commits_json`, `checks_summary_json`, `diff_summary_json`, `metrics_json`, `created_at` |

#### Máquinas de estado da expansão

```text
DiscoveredResource:
  untrusted -> approved -> active
  untrusted -> rejected
  active    -> revoked
  active    -> untrusted (quando hash do arquivo no disco for alterado)

ConsentRecord:
  requested -> granted -> revoked
  requested -> denied
  granted   -> expired (por tempo ou política de retenção)

MemoryEntry:
  pending_consent -> active -> revoked
  pending_consent -> rejected
  active          -> expired

ExtensionInstall:
  proposed -> consented -> installed -> active -> disabled -> active
  active   -> quarantined (após detecção de anomalia)
  active   -> revoked (bloqueia imediatamente novos efeitos)
  active   -> rolled_back (restaura versão anterior aprovada)

Session / Thread:
  created -> running -> waiting -> completed
  running -> failed
  running -> cancelled
  running -> lost (desconexão transitória; reconciliável por cursor, sem concluir o run)

MetricSample.status:
  unknown   (estado padrão se não houver fonte confirmada; nunca transita para zero artificial)
  observed -> stale (após expiração do TTL de frescor)

BudgetPolicy:
  active -> alerted (>= 80%) -> frozen (>= 100%) -> exhausted (recusa extensão)
  frozen -> active (aprovação de extensão)

ConflictReport:
  open -> auto_repair (tentativa merge_repair) -> open (se falha) / closed (se sucesso)
  open -> manual (resolução humana) -> closed
  open -> discarded -> closed
```

#### Interfaces de serviço centrais da expansão

- `AgentRegistry`: `resolve(profile) -> EffectiveCapabilities | Error`
- `ProfileResolver`: `validate(components) -> ValidationResult`, `snapshot(profile, run_id) -> ProfileSnapshot`
- `RouteSelector`: `select(request, candidates, policy) -> RouteDecision` (impl: `DirectSelector`, `OmniRouteSelector`)
- `ConsentService`: `request(purpose, scope) -> ConsentRequest`, `grant(id) -> ConsentRecord`, `revoke(id) -> RevocationResult`
- `MemoryStore`: `store(entry, consent_id) -> MemoryEntry`, `query(scope, query) -> List[MemoryEntry]`, `revoke(id) -> Result`
- `DiscoveryService`: `scan(authorized_root) -> List[DiscoveredResource]`, `approve(id, actor) -> DiscoveredResource`
- `ExtensionHost`: `install(manifest, consent) -> ExtensionInstall`, `execute(call, permissions) -> CallResult`, `revoke(id) -> Result`
- `TransportRegistry`: `check_health(transport_id) -> TransportHealth`, `assert_target(target_identity) -> TargetValidation`
- `Redactor`: `redact_payload(data) -> SanitizedData`, `redact_log(line) -> SanitizedLine`
- `AuthPolicy`: `authorize(token_hash, scope, resource_ref) -> AuthorizationDecision`
- `BudgetGovernor`: `check(run_id) -> BudgetStatus`, `alert(run_id) -> AlertResult`, `extend(run_id, additional_usd) -> ExtensionResult`
- `ConflictResolver`: `analyze(integration_id) -> ConflictReport`, `auto_repair(conflict_id) -> RepairResult`
- `PRPackager`: `build(run_id) -> PRPackage`, `publish(package_id) -> PublishResult`

---

### 3.7 Dados e estados

**SQLite:** Foreign keys habilitadas (`PRAGMA foreign_keys=ON`); modo WAL obrigatório (`PRAGMA journal_mode=WAL`); `PRAGMA busy_timeout = 5000` para concorrência control plane + webhooks; migração versionada; transações curtas; concorrência otimista via coluna `revision` (inteiro). Artefatos no filesystem: gravar arquivo temporário, `fsync`, rename atômico, só então registrar referência. Após crash, reconciliar órfãos (arquivos sem ref / refs sem arquivo) sem apagar automaticamente.

**Novas tabelas da expansão** (migrações versionadas independentes):
`areas`, `area_workspaces`, `projects`, `repositories`, `authorizations`, `agent_definitions`, `capability_declarations`, `profiles`, `profile_snapshots`, `sessions`, `threads`, `metric_samples`, `route_decisions`, `memory_entries`, `consent_records`, `discovered_resources`, `skill_definitions`, `mcp_definitions`, `secret_refs`, `extension_manifests`, `extension_installs`, `preferences`, `preference_snapshots`, `transport_definitions`, `transport_health`, `access_tokens`, `handoff_checkpoints`, `budget_policies`, `conflict_reports`, `pr_packages`.

Mapeamento físico T10: o workspace organizacional é `area_workspaces`; `workspaces` continua sendo a tabela de worktrees por tentativa da 0001. A expansão é aditiva e a T10 também materializa associações `profile_skills` e `profile_mcps`. Contrato de migração/rollback e limites dos serviços em [S14](workspaces_perfis.md).

Tabela `checkpoints` restrita à recuperação técnica de execuções; `memory_entries` tem ciclo de vida, expiração e auditoria próprias.

**Estados de Run:** `queued -> running -> waiting/reviewing -> running/succeeded/failed/cancelled`; cancelamento também parte de `queued/running`. `waiting` exige causa (`rate_limit_window`, `hitl`, `budget_frozen`) e limite (`window_reset_at`, `hitl_deadline`). Task usa estados do contrato + `cancelled`. Nova tentativa pode devolver `failed/blocked/rejected` a `running` por comando registrado; resultado anterior imutável. Acceptance e integração são decisões distintas. Run só sucede com todas as tarefas obrigatórias `accepted` e, quando solicitada, integração aprovada.

**Persistência:** `.orchestrator/checkpoints.sqlite`; artefatos em `.orchestrator/run/<run_id>/task/<task_id>/attempt/<attempt_id>/`; worktrees em `.orchestrator/worktree/`; expansão: `.orchestrator/memory/`, `.orchestrator/discovery/`, `.orchestrator/extension/`. IDs gerados pelo serviço (UUIDv7), nunca caminhos do cliente. Migração `.hydra/` → `.orchestrator/` explícita, com backup e preservação dos schemas legados.

---

### 3.8 Algoritmos Centrais (Detalhamento Técnico)

#### 3.6.1 Protocolo SSE com Heartbeat, Replay e Resiliência (RT16)

**Formato de frame estrito:**
```
event: <tipo>          # ex: run.started, task.completed, attempt.rate_limited
id: <seq>              # sequência monotônica por run (inteiro)
retry: <ms>            # sugerido 15000 (15s) para reconexão do cliente
data: <JSON payload>   # payload redigido (sem segredos)
```

**Heartbeat / Ping:** A cada 15 segundos, servidor emite frame `event: heartbeat` com `data: {}` e `retry: 15000`. Impede encerramento por timeout em proxies reversos, load balancers e firewalls corporativos.

**Buffer de replay:** Ring buffer em memória (ex.: últimos 500 eventos por run) para replay imediato de reconexões rápidas (< 30s). Fallback: busca indexada no SQLite (`WHERE run_id=? AND seq > ? ORDER BY seq`) para reconexões tardias.

**Deduplicação cliente:** Cliente mantém `last_seq` processado. No replay, ignora eventos com `seq <= last_seq`. Sequência monotônica garante ordenação.

**Cursor expirado:** Se `Last-Event-ID` refere-se a sequência já purgada pela retenção (padrão: 7 dias ou 10k eventos/run), servidor retorna HTTP 410 Gone com payload `{ "code": "CURSOR_EXPIRED", "message": "Cursor expirado, solicite snapshot completo via GET /runs/{id}/events?from=0" }`.

#### 3.6.2 Handoff por Estado Git/Worktree e Retry de Turno Atômico (RT08, RT26-Relay/Persist)

**Separação entre Execução em Workspace e Proxy de Inferência:**
Agentes de engenharia modernos (Claude Code, OpenCode, Aider, Codex CLI) operam em loops de *tool-calling* e edições incrementais no disco. Cortar um stream de texto na linha 15 e tentar costurar strings brutas em outro modelo corrompe chamadas JSON de ferramentas. O Hydra adota portanto duas estratégias determinísticas:

1. **Handoff de Agente em Worktree (`worktree_state`):**
   - `bridge/worker_runner.py` monitora o processo do agente na worktree. Quando ocorre interrupção por rate-limit (`429` / fim da janela de 5h) ou timeout:
   - O Hydra inspeciona o estado físico da worktree (`git status --porcelain`, `git diff HEAD`) e executa os checks rápidos de verificação.
   - Grava um `HandoffCheckpoint` contendo:
     - `instructions_json`: objetivo original + critérios de aceite + decisões da Wave 0
     - `git_sha`: SHA base da worktree
     - `diff_artifact_ids`: IDs dos artefatos contendo o `git diff` acumulado em disco até o corte
     - `tools_executed_json`: histórico auditado de comandos/ferramentas concluídos
     - `partial_output_json`: resumo dos checks que já passam e dos checks ainda pendentes
     - `next_step`: instrução estruturada para o próximo agente assumir a mesma worktree e concluir apenas os critérios faltantes
   - Antes de despachar o agente substituto (Modo Relay) ou retomar após o reset da cota (Modo Persistente), o Hydra valida a integridade sintática dos arquivos modificados na worktree (`ast.parse` em Python ou linter do projeto); se um arquivo ficou truncado no disco pelo kill do processo, faz `git checkout -- <arquivo_corrompido>` apenas daquele arquivo incompleto, preservando todos os demais arquivos salvos.

2. **Retry de Turno Atômico no Proxy (`/v1/chat/completions` — `atomic_turn_retry`):**
   - Quando o Hydra atua como proxy HTTP OpenAI-compatível e o provedor upstream interrompe o stream no meio de uma geração ou `tool_calls` (erro 429 ou desconexão abrupta), o roteador **não concatena fragmentos parciais de tool_calls**; descarta o buffer incompleto daquele turno e reenvia a requisição integral do turno para o próximo modelo da cadeia de fallback.

#### 3.6.3 Execução Swarm em Duas Ondas (Wave 0 + Wave 1), Protocolo de Emenda e Scheduler DAG (RT07, RT26-Swarm)

**Arquitetura em Duas Ondas (Prevenção de Conflitos de Contrato):**
Em vez de gerar um contrato puramente textual/estático e disparar todas as frentes no escuro, todo run em modo Swarm é estruturado em duas ondas no DAG:
- **Wave 0 (Fundação Compilável):** Tarefa raiz única (`wave=0`) executada na branch de integração `integrate/<run_id>`. Cria os schemas reais do banco, modelos tipados (ex.: Pydantic/Prisma/TypeScript), interfaces/stubs de rotas e declara todas as dependências novas em `pyproject.toml` / `package.json`. O aceite da Wave 0 exige que o linter/typecheck passe com exit code `0`.
- **Wave 1 (Swarm Paralelo):** Tarefas paralelas (`wave=1`, ex.: `wt-backend`, `wt-frontend`, `wt-db-tests`, `wt-docs`) que dependem formalmente da conclusão e aceite da Wave 0. Cada worktree nasce a partir do SHA consolidado da Wave 0.
- **Protocolo de *Contract Amendment* (Emenda de Contrato):** Se um worker da Wave 1 detectar que o contrato da Wave 0 precisa de um novo campo ou ajuste de assinatura, ele não edita arquivos fora de seu `allowed_paths`; emite o estado `needs_context` com um payload `ContractAmendmentRequest`. O coordenador aplica a emenda na branch de integração, roda o typecheck e atualiza (rebase) as worktrees ativas.

**Validação topológica (Kahn):**
```python
def validate_dag(tasks: List[TaskSpec]) -> ValidationResult:
    adj = {t.id: [] for t in tasks}
    in_degree = {t.id: 0 for t in tasks}
    for t in tasks:
        for dep in t.dependencies:
            if dep not in adj: return Error("dependency_not_in_dag")
            adj[dep].append(t.id)
            in_degree[t.id] += 1
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    topo = []
    while queue:
        u = queue.pop(0)
        topo.append(u)
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
    if len(topo) != len(tasks):
        return Error("cycle_detected", cycle_nodes=find_cycle(adj))
    return Ok(topo)
```

**Gerenciador de concorrência:** `asyncio.Semaphore(max_parallel_worktrees)`. Tarefas `ready` (dependências satisfeitas) adquirem semáforo antes de spawn e liberam ao terminar.

#### 3.6.4 Gerenciamento Físico de Worktrees e Proteção de Dependências (RT05, RT26-Swarm)

**Nomenclatura e isolamento:** `.orchestrator/worktree/<run_id>_<task_id>_<attempt_ordinal>/`. Cada tentativa tem worktree própria. Worktree de integração separada: `.orchestrator/worktree/integrate_<run_id>/`.

**Proteção de Ambientes Compartilhados (`.venv` / `node_modules`):**
- O compartilhamento de `.venv` ou `node_modules` por symlink entre worktrees da Wave 1 só é seguro se nenhum worker mutar o ambiente compartilhado concorrentemente.
- Durante a **Wave 1**, os arquivos de manifesto de dependências (`pyproject.toml`, `poetry.lock`, `requirements.txt`, `package.json`, `pnpm-lock.yaml`, `Cargo.toml`) são **excluídos de `allowed_paths`** (read-only para os workers paralelos). Qualquer tentativa de modificar esses manifestos ou rodar `pip install`/`npm install` fora da Wave 0 reprova o gate de escopo da tentativa.

**Prevenção/limpeza de locks abandonados e Multiplataforma:**
- Antes de `git worktree add`, verifica e remove `.git/worktrees/<name>/lock` órfãos (processo não existe) e executa `git worktree prune --expire=0` em startup.
- Windows: `taskkill /PID <pid> /T /F` para árvore; Linux/macOS: `os.killpg(os.getpgid(pid), SIGKILL)`.
- Normalização: `os.path.realpath()` para resolver symlinks antes de validar `allowed_paths`.

#### 3.6.5 Auto-Healing (Reparação Cirúrgica) (RT12, RF12)

**Extração determinística de falha:**
1. Captura `exit_code`, `stdout`, `stderr` do check falho
2. Parsing por linguagem/tool: regex para stack trace + arquivo:linha (ex.: `File "foo.py", line 42`)
3. Isola trecho de código relevante (±20 linhas ao redor do erro)
4. Constrói prompt de reparo contendo **apenas**: patch aplicado, erro isolado, código atual do arquivo

**Política de teto:**
- `max_repair_attempts` por tarefa (padrão: 2, configurável no `BudgetPolicy`)
- Cada reparo consome orçamento (tokens, custo, tempo)
- Esgotamento → tarefa `failed` final; dependentes bloqueadas
- Tentativas de reparo são `TaskAttempt` com `ordinal` incrementado e `parent_attempt_id` para rastreabilidade

**Validação de reparo:** Mesmos checks da tarefa original + check de regressão (rodar testes não modificados).

#### 3.6.6 Modelo Relacional SQLite — DDL e Índices (RT03, RT11, RT16, RT17)

```sql
-- Modo WAL e performance
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

-- Tabela base: projects
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    canonical_root TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Runs
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    spec_json TEXT NOT NULL,           -- RunSpec completo com schema_version
    base_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','waiting','reviewing','succeeded','failed','cancelled')),
    revision INTEGER NOT NULL DEFAULT 1,  -- concorrência otimista
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_runs_project ON runs(project_id);
CREATE INDEX idx_runs_status ON runs(status);

-- Tasks
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    spec_json TEXT NOT NULL,           -- TaskSpec completo
    status TEXT NOT NULL CHECK (status IN ('pending','running','needs_context','blocked','failed','ready_for_review','accepted','rejected','cancelled')),
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_tasks_run ON tasks(run_id);
CREATE INDEX idx_tasks_status ON tasks(run_id, status);

-- Task Dependencies (DAG edges)
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    prerequisite_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, prerequisite_id)
);
-- Constraint: no self-ref, no cross-run (validado na aplicação)

-- Attempts
CREATE TABLE attempts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,          -- 1, 2, 3...
    executor_id TEXT NOT NULL,
    provider_model_json TEXT NOT NULL,
    provider_session TEXT,
    process_status TEXT CHECK (process_status IN ('queued','running','exited','timed_out','cancelled','crashed')),
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (task_id, ordinal)
);
CREATE INDEX idx_attempts_task ON attempts(task_id);

-- Workspaces (por tentativa)
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
    canonical_path TEXT NOT NULL UNIQUE,
    base_sha TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('preparing','ready','integrating','conflicted','preserved','cleaned'))
);

-- Results
CREATE TABLE results (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
    exit_code INTEGER,
    simulated BOOLEAN NOT NULL DEFAULT 0,
    outcome TEXT CHECK (outcome IN ('success','failure','partial')),
    summary TEXT,
    patch_artifact_id TEXT REFERENCES artifacts(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Artifacts
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    relative_path TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('patch','check_output','log','handoff','export','pr_package')),
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, relative_path)
);
CREATE INDEX idx_artifacts_run ON artifacts(run_id);
CREATE INDEX idx_artifacts_attempt ON artifacts(attempt_id);

-- Check Results
CREATE TABLE check_results (
    id TEXT PRIMARY KEY,
    result_id TEXT REFERENCES results(id) ON DELETE CASCADE,
    integration_id TEXT REFERENCES integrations(id) ON DELETE CASCADE,
    command_json TEXT NOT NULL,
    cwd TEXT NOT NULL,
    tested_sha TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    output_artifact_id TEXT REFERENCES artifacts(id),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    CHECK (result_id IS NOT NULL OR integration_id IS NOT NULL),
    CHECK (result_id IS NULL OR integration_id IS NULL)
);

-- Reviews
CREATE TABLE reviews (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL REFERENCES results(id) ON DELETE CASCADE,
    actor TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted','rejected')),
    reason TEXT,
    expected_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Events (SSE + auditoria)
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,              -- monotônico por run
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,        -- redigido
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, seq)
);
CREATE INDEX idx_events_run_seq ON events(run_id, seq);
CREATE INDEX idx_events_task ON events(task_id);

-- Integrations
CREATE TABLE integrations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    workspace_path TEXT NOT NULL,
    expected_base_sha TEXT NOT NULL,
    result_sha TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','conflicted','failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Integration Items (ordem de merge)
CREATE TABLE integration_items (
    integration_id TEXT NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    result_id TEXT NOT NULL REFERENCES results(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (integration_id, position)
);

-- Handoff Checkpoints
CREATE TABLE handoff_checkpoints (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    instructions_json TEXT NOT NULL,
    git_sha TEXT NOT NULL,
    diff_artifact_ids TEXT NOT NULL,   -- JSON array
    tools_executed_json TEXT NOT NULL,
    partial_output_json TEXT,
    next_step TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Metric Samples
CREATE TABLE metric_samples (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('run','attempt','session','thread')),
    scope_id TEXT NOT NULL,            -- attempt_id, session_id, etc.
    kind TEXT NOT NULL CHECK (kind IN ('queue','duration','tokens_in','tokens_out','cost')),
    value REAL,                        -- NULL = unknown
    unit TEXT NOT NULL,
    source TEXT NOT NULL,              -- ex: 'omniroute', 'local_calc', 'provider_api'
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('observed','stale','unknown')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_metrics_run ON metric_samples(run_id);
CREATE INDEX idx_metrics_scope ON metric_samples(scope, scope_id);

-- Route Decisions
CREATE TABLE route_decisions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    candidates_json TEXT NOT NULL,
    selected_route TEXT NOT NULL,
    reason TEXT NOT NULL,
    fallback_chain_json TEXT NOT NULL,
    decision_source TEXT NOT NULL CHECK (decision_source IN ('hydra','omnirouter','operator')),
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Budget Policies
CREATE TABLE budget_policies (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    max_usd REAL,
    max_tokens_in INTEGER,
    max_tokens_out INTEGER,
    max_wall_seconds INTEGER,
    alert_threshold_pct REAL NOT NULL DEFAULT 80.0,
    status TEXT NOT NULL CHECK (status IN ('active','alerted','frozen','exhausted')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

### 3.9 API Proposta — Especificação Completa

**Prefixo:** `/v1/control-plane`. Autenticação: token local (header `Authorization: Bearer <token>`). CORS: allowlist estrita (config `server.cors_allow_origins`), sem wildcard com credenciais.

#### 3.9.1 Núcleo (MVP)

| Método | Rota | Request | Response | Semântica |
|--------|------|---------|----------|-----------|
| POST | `/projects` | `ProjectCreateRequest` | `ProjectResponse` | Valida raiz permitida, cadastra projeto |
| POST | `/runs` | `RunCreateRequest` + `Idempotency-Key` | `202 Accepted` + `RunResponse` | Cria run, retorna run_id |
| GET | `/runs` | query: `project_id`, `status`, `page`, `size` | `PaginatedResponse<RunSummary>` | Lista paginada |
| GET | `/runs/{id}` | — | `RunDetailResponse` | Snapshot versionado (revision) |
| GET | `/runs/{id}/tasks` | — | `List<TaskResponse>` | Tarefas da run |
| GET | `/runs/{id}/artifacts` | query: `kind` | `List<ArtifactResponse>` | Evidência vinculada |
| GET | `/runs/{id}/events` | header: `Last-Event-ID` (opcional) | `text/event-stream` (SSE) | Replay + eventos ao vivo |
| POST | `/runs/{id}/cancel` | `CancelRequest` | `CancelResponse` | Cancelamento idempotente |
| POST | `/runs/{id}/tasks/{task_id}/retry` | `RetryRequest` | `RetryResponse` | Nova tentativa após reconciliação |
| POST | `/runs/{id}/tasks/{task_id}/review` | `ReviewRequest` | `ReviewResponse` | accepted/rejected + motivo + expected_revision |
| POST | `/runs/{id}/integrate` | `IntegrateRequest` | `IntegrateResponse` | Integra só resultados aceitos, reais, íntegros |

**Idempotência:** `Idempotency-Key` + hash do payload (SHA-256). Mesma chave + mesmo payload → mesmo resultado (202 com mesmo run_id). Chave reutilizada com payload diferente → 409 Conflict.

**Erros:** Envelope `{ "code": "...", "message": "...", "run_id": "...", "retryable": bool }`. Códigos: 400 (validação), 401 (auth), 403 (escopo), 404 (recurso), 409 (conflito/idempotência), 410 (cursor expirado), 422 (schema/compatibilidade), 503 (dependência indisponível). Sem traceback/segredo no payload.

**SSE:** Entrega pelo menos uma vez. Cliente deduplica por `(run_id, seq)`. Heartbeat a cada 15s (`event: heartbeat`). Cursor expirado → 410.

**Inferência:** `/v1/chat/completions` (compatível OpenAI) não inicia mutações Git. ID estável por resposta. Rejeita parâmetros/ferramentas não suportados (422).

#### 3.9.2 Expansão (/v1/control-plane)

| Método | Rota | Semântica |
|--------|------|-----------|
| GET/POST | `/areas` | Lista/cria áreas lógicas |
| GET/POST | `/workspaces` | Lista/cadastra workspaces vinculados a áreas |
| GET/POST | `/projects/{id}/repositories` | Associa repositório com validação canônica |
| GET | `/agents`, `/executors`, `/capabilities` | Consulta catálogo com certificação |
| GET/POST | `/profiles` | Cadastra/lista perfis combináveis |
| POST | `/profiles/{id}/resolve` | Valida combinação → `ProfileSnapshot` imutável |
| GET | `/sessions`, `/sessions/{id}/threads` | Lista sessões e árvores de threads |
| GET | `/sessions/{id}/events` | SSE com cursor para sessão + threads |
| GET | `/runs/{id}/metrics` | `MetricSample` com observed/stale/unknown |
| GET | `/runs/{id}/route-decisions` | Trilha auditável de seleção de rota |
| GET/POST | `/memory` | Consulta/grava memórias (exige consentimento) |
| POST | `/memory/{id}/revoke` | Revoga memória |
| POST | `/consents`, `/consents/{id}/revoke` | Registra/revoga consentimentos |
| POST | `/discovery/scan` | Varredura opt-in em raízes allowlisted |
| GET | `/discovery/resources` | Lista recursos com trust_status |
| POST | `/discovery/resources/{id}/approve\|reject` | Aprova/rejeita recurso; registra principal |
| GET/POST | `/skills`, `/mcps` | Gerencia skills/MCPs; segredos = referências |
| GET/POST | `/extensions`, `/extensions/install` | Instala extensão com manifesto + consentimento |
| POST | `/extensions/{id}/revoke\|rollback` | Revoga imediato ou restaura versão anterior |
| GET/PUT | `/preferences` | Preferências escopadas (user/area/project) |
| GET | `/transports`, `/transports/{id}/health` | Transportes registrados + healthchecks |
| POST | `/tokens`, `/tokens/{id}/revoke` | Emite/revoga tokens locais com escopos granulares |

**Regras de erro da expansão:**
- 401: token ausente/inválido/assinatura não reconhecida
- 403: token válido mas sem escopo (ex.: read-only tentando aprovar)
- 409: consentimento ausente para memória; recurso `untrusted` ativado; hash conflitante
- 410: cursor SSE expirado → solicitar snapshot completo
- 422: perfil incompatível (ex.: executor sem worktree + tarefa que exige isolamento)

#### 3.9.3 Schemas Pydantic de Referência (Entrada/Saída)

```python
# model.py — esquemas centrais (excertos)

class ProjectCreateRequest(BaseModel):
    canonical_root: DirectoryPath
    name: str = Field(min_length=1, max_length=100)
    base_branch: str = "main"
    base_sha: Optional[str] = None  # auto-resolve se None

class ProjectResponse(BaseModel):
    id: str
    canonical_root: str
    name: str
    base_branch: str
    base_sha: str
    created_at: datetime

class RunCreateRequest(BaseModel):
    project_id: str
    objective: str = Field(min_length=10, max_length=5000)
    mode: Literal["swarm", "relay", "persistent"] = "relay"
    task_spec: TaskSpecRequest
    budget: Optional[BudgetPolicyRequest] = None
    profile_id: Optional[str] = None
    idempotency_key: str = Field(min_length=16, max_length=64)

class TaskSpecRequest(BaseModel):
    objective: str
    acceptance_criteria: List[CheckSpec] = Field(min_length=1)
    allowed_paths: List[str] = Field(default_factory=lambda: ["**/*"])
    dependencies: List[str] = Field(default_factory=list)  # task_ids
    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    max_repair_attempts: int = Field(default=2, ge=0, le=5)

class CheckSpec(BaseModel):
    check_id: str
    command: List[str] = Field(min_length=1)
    cwd: Optional[str] = None
    description: str = ""

class BudgetPolicyRequest(BaseModel):
    max_usd: Optional[float] = Field(default=None, ge=0)
    max_tokens_in: Optional[int] = Field(default=None, ge=0)
    max_tokens_out: Optional[int] = Field(default=None, ge=0)
    max_wall_seconds: Optional[int] = Field(default=None, ge=60)
    alert_threshold_pct: float = Field(default=80.0, ge=50, le=99)

class RunResponse(BaseModel):
    run_id: str
    status: RunStatus
    created_at: datetime

class RunDetailResponse(BaseModel):
    run_id: str
    project_id: str
    spec: RunSpecFull
    status: RunStatus
    revision: int
    base_sha: str
    tasks: List[TaskResponse]
    budget: Optional[BudgetStatus]
    created_at: datetime
    updated_at: datetime

class ReviewRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=1)

class IntegrateRequest(BaseModel):
    force: bool = False  # se True, tenta resolver conflitos automaticamente (merge_repair)

# SSE Event payloads (redigidos)
class RunEventPayload(BaseModel):
    run_id: str
    seq: int
    type: str
    task_id: Optional[str] = None
    attempt_id: Optional[str] = None
    payload: Dict[str, Any]  # já redigido
    timestamp: datetime
```

#### 3.7.4 Equivalência CLI

`hydra` implementa comandos idênticos consumindo a mesma camada de serviço:
`hydra area`, `hydra project`, `hydra repo`, `hydra agent`, `hydra profile`, `hydra session`, `hydra metrics`, `hydra memory`, `hydra discovery`, `hydra extension`, `hydra preference`, `hydra transport`, `hydra token`, `hydra run`, `hydra review`, `hydra integrate`, `hydra cancel`, `hydra retry`. Flags: `--json` (saída estruturada), `--output` (arquivo), códigos de saída: 0=sucesso, 1=erro válido, 2=erro de sistema, 3=idempotência/conflito.

---

### 3.10 Segurança e limites

Bind local padrão (`127.0.0.1:8000`); token local para comandos e leitura de evidência; CORS com allowlist estrita (config `server.cors_allow_origins`, sem `["*"]` com credenciais). Não registrar tokens. Autorizar raiz do projeto e normalizar caminhos/symlinks (`os.path.realpath`). Worktree não constitui sandbox: contenção depende do executor. Testes e comandos são entradas autorizadas do projeto, executados com limites (timeout, cgroup se disponível); logs redigidos antes de exposição. Cancelamento só anunciado concluído após verificar árvore encerrada no SO certificado (`psutil` + tree kill).

**Segurança ampliada (RT25):**
- Servidor rejeita configuração com `allow_origins=["*"]` + credenciais ativas
- Tokens de acesso: derivação PBKDF2/Argon2; nunca logados ou persistidos em texto plano
- `core/redaction.py` intercepta **todos** eventos antes de escrita no banco e transmissão SSE: expurga padrões de tokens (`sk-`, `ghp_`, `glpat-`, `xoxb-`, `Bearer `), chaves SSH (`-----BEGIN OPENSSH PRIVATE KEY-----`), senhas (`password=`, `secret=`, `api_key=`), credenciais OAuth, URLs com user:pass
- Nenhum comando de execução ou script de extensão acessa variáveis de ambiente não filtradas ou soquetes fora das allowlists de rede do projeto
- `SecretRef` usa provedores externos (`env`, `vault`, `keyring`); valor bruto nunca em perfil, evento, prompt, memória, artefato

---

## 4. Pré-condições

Configuração validada, schema compatível, repo acessível, executor elegível e orçamento suficiente. Uma tarefa em execução possui no máximo uma tentativa ativa; recuperação deve reconciliar processo antigo antes de novo spawn. Para a expansão (RT13–RT30), áreas, repositórios, perfis, recursos locais descobertos, extensões, orçamentos, conflitos e empacotamento exigem concessão prévia de autorização e verificação de integridade antes do uso operacional; nenhum recurso é ativado implicitamente por mera existência no sistema de arquivos. Modo de orquestração selecionado deve ser compatível com capabilities do executor.

## 5. Pós-condições

Resultado persistido com checks e referências de artefato; evento correlacionado; integração e limpeza têm resultado próprio. Falha de persistência impede anúncio de sucesso. Não há alterações silenciosas da branch ativa do operador. Operações de consentimento de memória ou aprovação de extensão geram registros auditáveis imutáveis; revogações impedem que novas execuções acessem o recurso revogado. Orçamento respeitado com alertas e congelamento auditáveis. Conflitos resolvidos com evidência. PR package gerado com descrição completa quando autorizado.

## 6. Invariantes

Transação para estado/evento, exclusão mútua da integração, resultados imutáveis, tarefas dependentes no mesmo run, contrato fixado por hash e limites de tempo/tentativas. Métricas registram duração, filas e falhas sem inventar custo/token não informado (`unknown` permanece `unknown`).

Invariantes da expansão:
1. Checkpoints de execução são separados de memória adaptativa persistente (tabelas e lifecycles distintos)
2. Texto produzido por agente ou declaração textual de sucesso nunca constituem prova de execução ou validação de check
3. Recursos descobertos iniciam no estado `untrusted` e só transitam com aprovação de principal autenticado
4. Extensões operam em processo isolado e não têm acesso direto ao banco de dados do control plane
5. A interface visual consome apenas read models persistidos e não pode alterar estado sem comando autenticado correspondente
6. A UI é operável por teclado, com foco visível, rótulos semânticos e estados comunicados sem dependência exclusiva de cor (WCAG AA)
7. Snapshots de perfil (`ProfileSnapshot`) e preferências (`PreferenceSnapshot`) são imutáveis por run
8. Eventos SSE sequenciais por run, com heartbeat e replay por cursor; deduplicação cliente por `(run_id, seq)`
9. SQLite WAL + `busy_timeout=5000` + FKs + concorrência otimista via `revision`
10. Exportação e logs passam por redactor determinístico (regex + entropia) antes de exposição

---

## 7. Falhas e recuperação

Cobrir: disco cheio, lock do banco, subprocesso órfão, arquivo fora do escopo, conflito, quota desconhecida, conexão perdida. Em efeito externo ambíguo, marcar `blocked` e exigir reconciliação. Não aplicar retry cego nem deduplicação textual como garantia de integridade de código.

**Falhas da expansão:**
1. Descoberta de recurso adulterado (divergência de hash) → transição automática `untrusted` + bloqueio execução
2. Tentativa de escrita de memória sem consentimento ativo → erro 409, nenhuma persistência
3. Perda de conexão SSE → reconciliada por cursor `Last-Event-ID` com deduplicação sem conclusão prematura
4. Extensão incompatível ou revogada → terminada síncrona sem afetar integridade do processo principal
5. Orçamento esgotado + recusa de extensão → run `budget_exhausted`; evidência preservada
6. Conflito de merge não resolvido → worktree preservada; run `conflicted`; opções: auto_repair, manual, discard
7. HITL timeout → tentativa `failed` com motivo `hitl_timeout`; evidência preservada

### 7.A Critérios negativos objetivos (expandido)

| Caso de teste negativo | Comportamento obrigatório | Requisito |
|------------------------|---------------------------|-----------|
| Repositório fora da allowlist | 403 + log auditoria; nenhum Git iniciado | RT13 |
| Symlink/traversal fora da raiz | 400 + bloqueio + log violação | RT13 |
| Repo secundário sem autorização | Bloqueado; permissão primária não herdada | RT13 |
| Driver CLI não certificado em produção | Bloqueado antes do spawn + erro tipado | RT14 |
| Perfil com capabilities incompatíveis | 422 na validação pré-exec + indicação da incompatibilidade | RT15 |
| Alteração de perfil durante run ativo | Snapshot do run imutável; novo perfil afeta só novos runs | RT15 |
| Cliente SSE com `Last-Event-ID` expirado | 410 Gone + orientação snapshot completo | RT16 |
| Evento retransmitido na reconciliação | Cliente deduplica por (run, seq) sem efeito duplicado | RT16 |
| Provedor não retorna tokens/custo | `unknown`; nunca zero ou estimativa | RT17 |
| Quota indisponível por queda gateway | `unknown`/`stale`; proibido 100% | RT17/RT18 |
| Gravação memória sem consentimento | 409 imediato; zero persistência | RT19 |
| Checkpoint técnico → memória auto | Bloqueio por schema; tabelas/lifecycles separados | RT19 |
| Recurso descoberto com hash alterado | Transição `untrusted` automática + bloqueio | RT20 |
| Segredo exposto em prompt/evento/log | Falha validação redaction antes de emissão | RT21 |
| Extensão tenta acessar DB core | Acesso negado por isolamento de processo | RT22 |
| Extensão revogada emite chamada | Interceptação `ExtensionHost` + bloqueio + auditoria | RT22 |
| Preferência inferida sobrepõe explícita | Bloqueio; explícita tem precedência no snapshot | RT23 |
| UI marca aceita sem comando versionado | Bloqueio; UI é consumidora, não autoridade | RT23 |
| SSH host key divergente | Abort imediato; sem bypass silencioso | RT24 |
| Origem não allowlisted / CORS wildcard + creds | 403 Forbidden; credenciais não processadas | RT25 |
| Modo Swarm com DAG cíclico | 422 na submissão; run não criado | RT26 |
| HITL timeout expirado | Tentativa `failed` + `hitl_timeout` + evidência | RT27 |
| Conflito merge sem resolução | Worktree preservada; status `conflicted`; opções ofertadas | RT28 |
| Orçamento 100% + recusa extensão | Run `budget_exhausted`; evidência preservada | RT29 |
| PR package sem autorização | Não criado; exportação local só sob demanda | RT30 |

---

## 8. Tasks iniciais rastreáveis

O estado de implementação é registrado no backlog; a T01 possui uma entrega de configuração e roteamento especificada em [configuracao_runtime.md](configuracao_runtime.md). Cada linha é uma unidade de implementação com testes no mesmo commit; não autoriza execução de provedores pagos. Para o acompanhamento operacional por ondas de execução, estimativas em Story Points e políticas de agentes, consulte [`../a_context/backlog.md`](../a_context/backlog.md) e o planejamento estratégico em [`../a_context/roadmap.md`](../a_context/roadmap.md). Specs S01–S13 detalham posteriormente cada módulo.

### 8.1 Núcleo (T01 a T08)

| Task | Depende | RF / RT | Arquivos de propriedade | Definição de concluído (DoD) |
|------|---------|---------|-------------------------|------------------------------|
| **T01** Config canônica | — | RF02 / RT01 | `config.py`, `config.yaml`, `.gitignore`, consumo em `core/router.py`, `bridge/omniroute_client.py`, `cli.py`, `server.py`; testes correspondentes | Aliases/modelos resolvidos; CLI separada de CDP; inválidos recusados; runtime ignorado; gateway disabled/required comprovado |
| **T02** Contratos e estados | T01 | RF03/RF07 / RT02 | `model.py`, `prd_tecnico.md (§3.4)`, `tests/test_model.py` | Schemas Pydantic + transições válidos/inválidos cobertos |
| **T03** Store e migração | T02 | RF03/RF05 / RT03/RT11 | `core/checkpointer.py`, `migration/`, `tests/test_checkpointer.py` | Restart, chave idempotente, transação, WAL, FKs testados |
| **T04** Runner e fake | T03 | RF04/RF06 / RT04 | `bridge/worker_runner.py`, `tests/test_worker_runner.py` | Cwd real, erro, timeout, árvore cancelada, fake só dry-run |
| **T05** Workspace Git | T04 | RF01/RF04 / RT05 | `core/git_workspace.py`, `tests/test_git_workspace.py` | SHA fixo, worktree real, estado usuário preservado, lock cleanup |
| **T06** Checks e integração | T05 | RF07/RF08 / RT06 | `core/git_workspace.py`, `core/run_service.py`, `tests/test_integration.py` | Patch real, escopo, conflito, checks combinados governam aceite |
| **T07** Entrada M1 (CLI/API) | T06 | RF03–RF08 / RT10 | `cli.py`, `server.py`, `tests/test_server.py`, `tests/test_cli.py` | Submeter/consultar/cancelar/revisar usam mesmo serviço + auth |
| **T08** CI e manual M1 | T07 | RF15 / RT12 | `.github/workflows/ci.yml`, `doc/j_manual/README.md`, `pyproject.toml` | Testes offline reproduzíveis; driver real com certificação separada |

Paths Python relativos a `src/hydra_orch/`, exceto `tests/`, config, docs. T01–T07 concretizam S01–S05/M1; T08 inicia S13. Validar Python ≥ 3.10 e SO anunciado (gestão de processos testada).

### 8.2 Expansão (T09 a T28 — propostas)

| Task | Depende | RF / RT | Arquivos de propriedade propostos | Definição de concluído (DoD) |
|------|---------|---------|-----------------------------------|------------------------------|
| **T09** Auth e CORS estrito | T07 | RF15/RF24 / RT25 | `server.py`, `core/auth.py`, `core/redaction.py`, `tests/test_auth.py` | Token local obrigatório; CORS allowlist estrita; redaction validada |
| **T10** Migrações control plane | T03, T09 | RF16–RF30 / RT03/RT25 | `core/checkpointer.py`, `migration/`, `tests/test_migration.py` | Tabelas expansão versionadas; rollback; FKs ativas; legado preservado |
| **T11** Registry áreas/repos | T10 | RF16 / RT13 | `core/workspace_registry.py`, `tests/test_workspace_registry.py` | Hierarquia Area/WS/Project/Repo persistida; traversal bloqueado |
| **T12** Catálogo agentes/capabilities | T02, T04, T10 | RF17, RF14 / RT14 | `core/agent_registry.py`, `config.yaml`, `tests/test_agent_registry.py` | Capabilities declaradas; driver não certificado bloqueado; CLI ausente = erro |
| **T13** Perfis e snapshots imutáveis | T11, T12 | RF17, RF23 / RT15 | `core/profile_service.py`, `tests/test_profile.py` | Validação pré-exec; snapshot imutável com hash por run |
| **T14** Sessões, threads, SSE replay | T03, T07, T10 | RF18, RF05 / RT16 | `core/session_service.py`, `server.py`, `tests/test_sse_replay.py` | Árvore sessões/threads; SSE Last-Event-ID, replay, dedup comprovados |
| **T15** Métricas observabilidade | T03, T10, T14 | RF19 / RT17 | `core/metrics.py`, `tests/test_metrics.py` | Fila, duração, tokens, custo com observed/stale/unknown; zero não inventado |
| **T16** Seleção adaptativa rotas | T12, T15 | RF20, RF11 / RT18 | `core/route_selector.py`, `bridge/omniroute_client.py`, `tests/test_route_selector.py` | RouteDecision auditável; modo direto sem OmniRoute testado |
| **T17** Consentimento e memória | T09, T10 | RF21 / RT19 | `core/consent.py`, `core/memory_store.py`, `tests/test_memory.py` | Escrita exige ConsentRecord; revogação funcional; isolamento checkpoints |
| **T18** Discovery local controlado | T09, T11 | RF22 / RT20 | `core/discovery.py`, `tests/test_discovery.py` | Varredura opt-in allowlist; hash + untrusted; sem ativação auto |
| **T19** Skills, MCPs, secret refs | T12, T17, T18 | RF17, RF22 / RT21 | `core/skill_registry.py`, `bridge/mcp_client.py`, `tests/test_secrets.py` | Segredos como referências; resolução no spawn com env filtrado |
| **T20** Isolamento extensões/plugins | T18, T19 | RF24 / RT22 | `core/extension_host.py`, `tests/test_extension.py` | Manifesto validado; processo isolado sem DB core; revogação imediata |
| **T21** Preferências e acessibilidade | T13, S11 | RF23 / RT23 | `core/preferences.py`, `tests/test_preferences.py`, `doc/h_test/README.md` | Preferências escopadas/reversíveis; checklist a11y (teclado, foco, roles, contraste) |
| **T22** Transportes certificados | T04, T09 | RF25, RF14 / RT24 | `bridge/transport_registry.py`, `bridge/ssh_tunnel.py`, `tests/test_transport.py` | Alvo, identidade, healthcheck; host key SSH alterada falha; isolamento saídas |
| **T23** CLI control plane estendida | T11–T22 | RF16–RF30 / RT13–RT25 | `cli.py`, `tests/test_cli.py` | Comandos para áreas, projetos, perfis, memória, discovery, extensões |
| **T24** CI estendido e runbooks | T08, T23 | RF15, RF23, RF25 / RT12 | `.github/workflows/ci.yml`, `doc/j_manual/README.md` | Testes offline cobrindo regras negativas expansão; runbooks atualizados |
| **T25** Orquestração Swarm/Relay/Persist | T06, T13 | RF26 / RT26 | `engine/swarm.py`, `engine/relay.py`, `engine/persist.py`, `tests/test_orchestration.py` | 3 modos funcionais: DAG+semáforo, handoff checkpoint, pausa/retomada janela |
| **T26** HITL (Humano-no-Loop) | T07, T14 | RF27 / RT27 | `core/hitl.py`, `core/run_service.py`, `tests/test_hitl.py` | Pausa needs_context/needs_approval; timeout; retomada com resposta; evidência |
| **T27** Resolução conflitos merge | T06, T08 | RF28 / RT28 | `core/conflict_resolver.py`, `core/git_workspace.py`, `tests/test_conflict.py` | Relatório 3-way; merge_repair com orçamento; opções manual/discard |
| **T28** Budgeting e PR Packaging | T07, T15 | RF29, RF30 / RT29, RT30 | `core/budget.py`, `core/packaging.py`, `tests/test_budget_packaging.py` | Tetos USD/tokens/tempo; alerta 80%/congelamento 100%; PR package auto |

### 8.3 Faseamento e etapas propostas (S00 a S20)

```text
V0 (Núcleo verificável):      S00 -> S01 -> S02 -> S03 -> S04 -> S05 -> M1 (T01-T08)
V1 (Control plane + HITL):    M1  -> S10 (API) -> S11 (UI) -> T09, T26
V2 (Workspaces e Perfis):     S14 (workspaces_perfis.md: T10, T11, T12, T13)
V3 (Coordenação, Rotas, Swarm/Relay/Persist):
                              S06 (swarm) -> S07 (handoff) -> S08 (quota)
                              -> S15 (sessoes_observabilidade.md: T14, T15, T16, T25)
Gate de Segurança V4:         S16 (seguranca_proveniencia.md: auth, secrets, consent, allowlists)
V4 (Memória, Discovery, Extensões, Conflitos, Budget, PR):
                              S16 -> S17 (memoria_discovery_extensoes.md: T17, T18, T19, T20, T27)
                              -> S18 (acessibilidade_transportes.md: T21, T22)
                              -> S19 (budget_packaging.md: T28)
                              -> S20 (cli_ci_manual.md: T23, T24)
```

Nenhuma etapa da expansão pode anteceder a conclusão do marco M1 de execução verificável local.

### 8.4 Matriz de rastreabilidade (RF → RT → Task → Evidência → Caso Negativo)

| RF | RT | Task | Etapa | Evidência de conclusão | Caso negativo (§7.A) |
|----|----|------|-------|------------------------|----------------------|
| RF01–RF08 | RT01–RT10 | T01–T07 | S01–S05/M1 | Subprocesso real em fixture com diff/check | CLI ausente falha; simulação rejeitada |
| RF09, RF10, RF11, RF12 | RT07–RT09, RT12 | T02, T06, T25 | S06–S09 | Swarm DAG, handoff, quota unknown | Ciclo DAG rejeitado; quota offline unknown |
| RF13–RF15 | RT10–RT12 | T07, T08, T26 | S10–S13 | Bootstrap, exportação sanitizada, suíte offline | CORS irrestrito rejeitado; artefato alterado falha |
| RF16 | RT13, RT25 | T10, T11 | S14 | Cadastro/resolução canônica multi-repo/área | Repo fora allowlist/traversal recusado |
| RF17 | RT14, RT15, RT21 | T12, T13, T19 | S14 | Perfil validador rejeita incompatibilidades; snapshot imutável | Driver não certificado falha antes spawn |
| RF18 | RT16 | T14 | S15 | Replay SSE Last-Event-ID monotônico | Conexão perdida reconciliada sem dup |
| RF19 | RT17 | T15 | S15 | Métricas com proveniência + status explícito | Provedor sem tokens → unknown |
| RF20 | RT18 | T16 | S15 | RouteDecision com candidatos/motivo/fallback | Rota inelegível nunca selecionada; direto OK |
| RF21 | RT19 | T10, T17 | S17 (pós-S16) | Memória vinculada a ConsentRecord; isolada checkpoints | Escrita sem consentimento → 409 |
| RF22 | RT20, RT21 | T18, T19 | S17 (pós-S16) | Varredura allowlist → hash + untrusted | Hash alterado → blocked |
| RF23 | RT23, RT15 | T13, T21 | S18/S11 | Checklist a11y automatizado/manual | Inferida não sobrepõe explícita |
| RF24 | RT22 | T20 | S17 (pós-S16) | Extensão isolada; revogação bloqueia efeitos | Acesso DB core por plugin bloqueado |
| RF25 | RT24, RT14 | T22 | S18/S12 | Host key SSH verificada; healthcheck tipado | Host key modificada aborta |
| RF26 | RT26 | T25 | S15 | 3 modos: DAG+semáforo, handoff, pausa/retomada | DAG cíclico → 422 |
| RF27 | RT27 | T26 | S11 | HITL needs_context/approval + timeout + retomada | Timeout → failed + evidência |
| RF28 | RT28 | T27 | S05/S17 | Conflito 3-way + merge_repair + opções | Worktree preservada; não toca branch user |
| RF29 | RT29 | T28 | S19 | Budget 80% alert / 100% freeze / extend | Recusa → budget_exhausted |
| RF30 | RT30 | T28 | S19/S13 | PR package auto com descrição completa | Sem autorização → não publica |
| Transversal | RT25 | T09 | S16 | Auth local + CORS estrita + redaction | CORS wildcard + creds → 403 |

---

### 8.5 Documentos de coerência pendentes

A formalização completa da arquitetura da expansão exigirá o alinhamento dos seguintes documentos em etapas documentais dedicadas, antes da codificação das tarefas correspondentes:

- `doc/b_spc/prd_tecnico.md` (§3.4): formalização dos schemas JSON de `ProfileSnapshot`, `Session`, `Thread`, `ConsentRecord`, `MemoryEntry`, `HandoffCheckpoint`, `BudgetPolicy`, `ConflictReport`, `PRPackage` e eventos de control plane.
- `doc/g_code/architecture.md`: atualização dos diagramas de blocos para incluir `AgentRegistry`, `DiscoveryService`, `ExtensionHost`, `BudgetGovernor`, `ConflictResolver`, `PRPackager`.
- `doc/d_mer/mer.md` e `mer.mmd`: modelagem relacional formal das tabelas de expansão (`areas`, `workspaces`, `repositories`, `profiles`, `sessions`, `memories`, `metric_samples`, `route_decisions`, `handoff_checkpoints`, `budget_policies`, `conflict_reports`, `pr_packages`).
- `doc/e_class/diagrama_classe.md` e `diagrama_classe.mmd`: diagramas de classe para interfaces e serviços de control plane (incluindo `BudgetGovernor`, `ConflictResolver`, `PRPackager`, `HitlManager`).
- `doc/b_spc/README.md`: sincronização dos contadores normativos para `RF01–RF30`, `RT01–RT30`, `RNF01–RNF10` e `T01–T28`.
- `doc/f_api/openapi.yaml`: especificação OpenAPI 3.0 completa para `/v1/control-plane/*` e `/v1/chat/completions`.
- `doc/h_test/README.md`: matriz de rastreabilidade RF/RT → testes, estratégia hermética, critérios de cobertura, testes de segurança/a11y.
- `doc/i_infra/README.md`: infraestrutura de sandboxing, gestão de processos multiplataforma, certificação de drivers.
- `doc/j_manual/README.md`: manuais de configuração, autenticação, SSH, operação M1–M4, runbooks de auditoria e recuperação.

---

## 9. Requisitos Não-Funcionais (RNF01 a RNF10)

| ID | Categoria | Requisito | Métrica / Critério de Aceite |
|----|-----------|-----------|------------------------------|
| **RNF01** | Performance | Despacho de subprocesso executor < 300ms após agendamento | P99 ≤ 300ms em fixture local (medido em `tests/test_worker_runner.py::test_dispatch_latency`) |
| **RNF02** | Consumo de Recursos | Processo Hydra Control Plane ≤ 200MB RAM em repouso; ≤ 500MB sob carga (4 worktrees ativas) | Monitoramento contínuo em CI; `memory_profiler` em testes de integração |
| **RNF03** | Compatibilidade SO | Suporte formal testado: Windows 11 (`taskkill /T /F`), Ubuntu 22.04+ / macOS 13+ (`os.killpg` + process groups) | CI matrix: Windows + Linux + macOS; testes de tree kill em cada SO |
| **RNF04** | Integridade de Dados | Zero perda de eventos em encerramento abrupto (persistência antecede ou mesma transação da emissão) | Teste de crash simulado (`kill -9` / `TerminateProcess`) + verificação de eventos no banco |
| **RNF05** | Segurança e Higiene | 100% de segredos expurgados em logs, eventos SSE, artefatos, exportações (regex + entropia) | Teste de redactor com corpus de segredos conhecidos + falsos positivos < 0.1% |
| **RNF06** | Disponibilidade | Reinicialização do servidor em < 5s (incluindo migração DB e reconciliação de órfãos) | Benchmark de startup frio + quente em CI |
| **RNF07** | Escalabilidade Local | Suporta até 10 runs concorrentes, 20 worktrees ativas, 100 tasks em fila sem degradação > 2x latência base | Teste de carga local (locust/k6) em CI opcional |
| **RNF08** | Observabilidade | 100% de operações críticas (run, task, attempt, check, review, integrate, cancel) emitem evento SSE com payload redigido | Cobertura de eventos verificada em `tests/test_events_coverage.py` |
| **RNF09** | Manutenibilidade | Cobertura de testes ≥ 80% em `core/`, `bridge/`, `engine/`; 100% em `model.py` (schemas) | `pytest --cov=src/hydra_orch --cov-fail-under=80` |
| **RNF10** | Portabilidade | Zero dependências de runtime não-vendored; Python stdlib + dependências declaradas em `pyproject.toml` | `pip-audit` + `cyclonedx-bom` em CI; sem `sys.path` hacks |

---

## 10. Exemplos técnicos

### 10.1 Núcleo verificável

POST de `RunSpec` com projeto, objetivo, base SHA e tarefa delimitada cria run `queued` e evento numa transação. Worker fake altera arquivo numa fixture; check registra SHA/exit code. Resultado vira `ready_for_review`. Review com revisão correta aceita; integração aplica em worktree própria e repete check. Mesma submissão não gera outro processo; review com revisão antiga retorna 409.

### 10.2 Exemplos técnicos da expansão (proposto)

**Resolução de perfil e snapshot:** Operador solicita execução associando perfil com Claude Code (driver CLI proposto, `is_certified=false`) e modelo via OmniRouter. `ProfileResolver` valida se capabilities exigidas (ex.: isolamento em worktree) são suportadas pelo driver. Se compatível, gera `ProfileSnapshot` com hash imutável (SHA-256 do JSON efetivo) e grava na transação do run. Se driver não certificado ou CLI ausente, falha HTTP 422 antes de qualquer processo.

**Reconexão SSE com cursor:** Cliente visual conecta a `/v1/control-plane/sessions/{id}/events` com header `Last-Event-ID: 42`. Servidor recupera do banco eventos a partir da sequência 43, emite em ordem monotônica e prossegue com eventos ao vivo. Se conexão cai na sequência 45, cliente reconecta com `Last-Event-ID: 45` e deduplica por `(run_id, seq)` sem perder estado nem duplicar ações.

**Consentimento e gravação de memória:** Ao identificar preferência durável, sistema emite solicitação (`ConsentRecord` estado `requested`). Após comando autenticado `POST /consents/{id}` → `granted`. Gravação `POST /memory` valida consentimento ativo antes de persistir `MemoryEntry`. Revogação via `POST /consents/{id}/revoke` impede uso em novos runs.

**Discovery local rejeitando adulteração:** `DiscoveryService` varre raiz autorizada, encontra manifesto de skill. Calcula SHA-256, registra `DiscoveredResource` como `untrusted`. Operador aprova via API/CLI → `approved`. Se arquivo alterado em disco, próximo hash check detecta divergência, transita para `untrusted` e impede execução até nova aprovação.

**Handoff Relay por Estado Git/Worktree:** Executor atinge rate limit (evento `attempt.rate_limited`). Hydra inspeciona a worktree (`git status`, `git diff`), reverte apenas eventual arquivo truncado por kill com `git checkout -- <file>`, e grava `HandoffCheckpoint` com o diff consolidado, ferramentas executadas e checks pendentes. Seleciona provedor fallback compatível que assume a worktree no estado verificado para concluir as pendências.

**Swarm com DAG e Auto-Healing:** Run modo `swarm` com T1→T2, T1→T3. Scheduler valida DAG (Kahn), despacha T1. T1 falha check. Operador solicita reparo → nova tentativa T1 (ordinal 2) com prompt de reparo contendo só erro + código atual. `max_repair_attempts=2` respeitado. T1 aceita → T2, T3 tornam-se `ready` e despachadas em paralelo (semáforo `max_parallel_worktrees=3`). Todas aceitas → integração serializada com checks combinados.

**Budgeting com alerta e congelamento:** Run com `max_usd=2.00`, `alert_threshold_pct=80`. Em $1.60 → `BudgetPolicy` status `alerted`, evento `budget.alerted` emitido. Em $2.00 → status `frozen`, run pausa com `waiting` causa `budget_frozen`, evento `budget.frozen`. Operador aprova extensão $1.00 via `POST /budget/{run_id}/extend` → status `active`, run retoma. Recusa → `budget_exhausted`, run `failed`.

**PR Package automático:** Run concluído com 3 tasks aceitas. Política de publicação autorizada. `PRPackager.build()` cria branch `pr/<run_id>`, descrição Markdown com: objetivo, 3 commits (SHA + mensagem), 12 checks (comando + exit_code + duração), diff sumarizado (4 arquivos, +120/-45 linhas), métricas (tokens: 45k in / 18k out, custo: $0.87, duração: 14min), decisões de review. `PRPackager.publish()` faz push no remote configurado.

**Resolução de conflito assistida:** Integração detecta conflito em `src/api/routes.py`. `ConflictResolver.analyze()` gera `ConflictReport` com base/ours/theirs SHA, arquivos conflitantes, diff 3-way. Operador escolhe "auto_repair" → `ConflictResolver.auto_repair()` cria `TaskAttempt` tipo `merge_repair` com orçamento próprio, prompt contendo conflito + arquivos base. Se checks passam → integração prossegue. Se falha → operador escolhe "manual" (worktree preservada) ou "discard" (tarefa rejected).

---

## 11. Glossary e Acrônimos

| Termo | Significado |
|-------|-------------|
| API | Application Programming Interface |
| AST | Abstract Syntax Tree |
| CDP | Chrome DevTools Protocol |
| CI | Continuous Integration |
| CLI | Command Line Interface |
| DAG | Directed Acyclic Graph |
| DBC-9 | Design by Contract — 9 partes (Purpose, Why, Contract, Preconditions, Postconditions, Invariants, Failure Modes, How, Examples) |
| DDL | Data Definition Language |
| ER | Entity-Relationship |
| FK | Foreign Key |
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
| PK | Primary Key |
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