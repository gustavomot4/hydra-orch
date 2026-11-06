# prd_tecnico — Especificação Técnica e Decomposição de Tarefas

**Identificador Formal:** `prd_tecnico.md`
**Caminho Canônico:** `doc/b_spc/prd_tecnico.md`
**Versão:** `v01_01_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch, complementando `prd_funcional.md`, `contrato_execucao.md` e [`plano_desenvolvimento.md`](../a_context/plano_desenvolvimento.md).
**Escopo:** Requisitos técnicos (RT01 a RT25), contratos de serviço, máquinas de estado, API REST, critérios negativos e tasks T01 a T24.

---

Status: arquitetura alvo proposta, sem alegação de implementação. RT01–RT12 e T01–T08 cobrem o núcleo inicial; RT13–RT25 e T09–T24 cobrem a expansão proposta (áreas, perfis, sessões, observabilidade, memória, discovery, extensões e acessibilidade) e permanecem não implementados. Complementa o [PRD funcional](prd_funcional.md), o [contrato](contrato_execucao.md) e o [plano](../a_context/plano_desenvolvimento.md). Modelagem: [classes](../e_class/diagrama_classe.md) e [MER](../d_mer/mer.md), a serem atualizados em etapa documental própria.

## 1. Propósito

Implementar execução verificável local com contratos tipados, estado durável, drivers explícitos, isolamento Git e integração validada, preservando o proxy de inferência.

A expansão técnica detalha a infraestrutura necessária para suportar interface visual de primeira classe, gestão de áreas de trabalho e repositórios múltiplos, catálogo e perfis de agentes (incluindo Claude Code, OpenCode e Codex como integrações propostas não certificadas), sessões e threads multiagente com SSE replay, métricas com unknown/stale explícitos, seleção adaptativa com OmniRouter opcional, memória consentida separada de checkpoints, discovery local controlado, plugins isolados e acessibilidade verificável, sempre mantendo o núcleo de execução verificável isolado de saídas textuais não comprovadas.

## 2. Justificativa

Consolidar os caminhos duplicados de core/engine e remover sucesso fabricado. FastAPI/CLI são entradas do mesmo serviço de aplicação; engines definem estratégia; bridges executam transporte; adapters fornecem inferência. SQLite atende o primeiro operador local; não há necessidade atual de banco distribuído.

A arquitetura proposta separa claramente os serviços de control plane (áreas, repositórios, catálogo, perfis, sessões, métricas, memória, discovery e extensões) da execução em workspace e da inferência de modelo. O OmniRouter continua sendo camada opcional de roteamento; o banco relacional SQLite local permanece a base transacional, sem introdução de brokers distribuídos desnecessários.

## 3. Contrato técnico

| ID | Obrigação | Verificação |
| --- | --- | --- |
| RT01 | Config tipada resolve alias → executor/provedor/modelo; rejeita desconhecidos; referências de segredo externas | Config inválida não inicia subprocesso; modo direto sem gateway |
| RT02 | RunSpec/TaskSpec versionados e imutáveis por tentativa; estados separados de processo, tarefa e integração | Validação Pydantic e tabela de transições |
| RT03 | Estado e evento na mesma transação; sequência única por run; idempotência de comandos | Concorrência/restart não duplicam run nem evento lógico |
| RT04 | Executor usa argv específico, cwd resolvido, env filtrado, timeout e cancelamento de árvore | Fake subprocesso e descendente terminam; CLI ausente falha |
| RT05 | Git opera em SHA fixo e worktrees reais; integração serializada por projeto | Falha de Git não cria diretório substituto; conflito preserva worktree |
| RT06 | Check registra comando, cwd, SHA, tempo, exit code e saída como artefato | Check ausente/falho bloqueia aceite; combinação é testada novamente |
| RT07 | Scheduler valida DAG, ownership e limite de concorrência | Ciclo recusado; dependente não executa cedo |
| RT08 | Handoff carrega instruções, SHA/diff e efeitos; repetição cria tentativa | Crash depois de efeito exige reconciliação, sem promessa de exactly-once externo |
| RT09 | Gateway distingue disabled/optional/required, quota observed/stale/unknown | HTTP simulado cobre offline, 429 e erro de autenticação |
| RT10 | API autoriza comandos locais, restringe origens e caminhos; UI usa contrato comum | Origem/token inválidos e traversal recusados |
| RT11 | Artefatos com hash, tamanho e caminho relativo; retenção explícita | Artefato ausente ou adulterado bloqueia integração |
| RT12 | CI offline e certificação real por driver/SO separadas | Suíte não exige conta, GPU ou localhost externo |
| RT13 | Hierarquia Area → Workspace → Project → Repository com raiz canônica, branch, SHA base, escopo de arquivos e autorização explícita | Recusa de repositório fora da allowlist, de symlink externo à raiz e de repositório sem concessão válida de autorização; proposto/não implementado |
| RT14 | Catálogo de agentes, executores e capabilities com proveniência e certificação por driver/SO; Claude Code, OpenCode e Codex propostos como não certificados | Capability ausente falha antes do spawn; driver não certificado bloqueado em modo produto; ausência de CLI é erro; proposto/não implementado |
| RT15 | Perfis de execução e combos combináveis com validação pré-execução e snapshot imutável com hash por run | Combinação incompatível falha antes de processo; alteração posterior de perfil não afeta runs já iniciados; proposto/não implementado |
| RT16 | Sessões, threads e eventos duráveis com sequência monotônica, relação pai/filho e SSE com cursor Last-Event-ID, replay e deduplicação | Queda de conexão não perde nem duplica eventos; cursor expirado retorna erro explícito; visibilidade de thread não implica swarm; proposto/não implementado |
| RT17 | Métricas operacionais vinculadas a run/attempt/session com valor, unidade, fonte, timestamp e status observed/stale/unknown | Ausência de dado vira unknown (nunca zero nem 100%); agregações com parcelas desconhecidas são sinalizadas como parciais; proposto/não implementado |
| RT18 | Roteamento adaptativo com registro auditável de candidatos, critérios, capabilities, fallback e origem da decisão; OmniRouter opcional | Modo direto opera sem gateway; decisão é reproduzível e auditável; candidato inelegível nunca é selecionado; proposto/não implementado |
| RT19 | Memória adaptativa consentida com escopo, autor, versão, retenção e revogação, estritamente separada de checkpoints de execução | Gravação sem ConsentRecord recusada; revogação bloqueia novos runs; checkpoints técnicos nunca alimentam memória automaticamente; proposto/não implementado |
| RT20 | Discovery local opt-in restrito a raízes autorizadas, com proveniência, hash e aprovação explícita antes de ativação | Recurso fora da raiz, com hash modificado ou capability desconhecida permanece untrusted; ativação automática proibida; proposto/não implementado |
| RT21 | Skills, MCPs e segredos gerenciados por referências externas; permissões declaradas e env filtrado no spawn | Valor bruto de segredo ausente de perfis, eventos, prompts, memória e artefatos; MCP sem permissão não inicia; proposto/não implementado |
| RT22 | Extensões e plugins com manifesto versionado, processo isolado, consentimento, revogação e rollback | Manifesto incompatível não inicia; revogação bloqueia novos efeitos; sem acesso ao banco core ou segredos não autorizados; proposto/não implementado |
| RT23 | Acessibilidade verificável e preferências reversíveis com snapshot por run | UI operável por teclado, com foco visível, roles semânticos, estados textuais e contraste; reversão restaura estado prévio; proposto/não implementado |
| RT24 | Transportes locais/remotos certificados com alvo, identidade, healthcheck e falhas tipadas | Alvo incorreto ou chave de host alterada falham de forma observável; sessões concorrentes isoladas; mock não substitui certificação; proposto/não implementado |
| RT25 | Segurança transversal com autenticação local obrigatória, CORS com allowlist estrita e central de redaction | Origem não autorizada, CORS wildcard com credenciais, token inválido e path traversal em artefatos são recusados; proposto/não implementado |

### Serviços e módulos

`core/run_service.py` (proposto) coordena run/revisão/cancelamento; `core/checkpointer.py` torna-se persistência canônica; `core/git_workspace.py` concentra Git. `engine/swarm.py` e `engine/relay.py` recebem serviços injetados; `engine/healer.py` cria tentativa de reparo real. `bridge/worker_runner.py` implementa a interface AgentExecutor por drivers. `bridge/ssh_tunnel.py` é o único gestor SSH. `core/router.py` permanece fachada de inferência.

Módulos propostos da expansão (em `src/hydra_orch/`): `core/workspace_registry.py` (áreas, projetos e repositórios), `core/agent_registry.py` (catálogo e capabilities), `core/profile_service.py` (combos e snapshots), `core/session_service.py` (sessões e threads), `core/metrics.py` (observabilidade e métricas operacionais), `core/route_selector.py` (seleção adaptativa), `core/memory_store.py` e `core/consent.py` (memória e consentimento, sem importar checkpointer), `core/discovery.py` (varredura local controlada), `core/extension_host.py` (ciclo de vida de plugins), `core/auth.py` e `core/redaction.py` (segurança e sanitização) e `bridge/transport_registry.py` (gestão de transportes certificados).

Migrar os consumidores antes de remover `core/swarm.py`, `core/ssh_tunnel.py` e duplicação de `engine/checkpointer.py`; preservar imports temporariamente com wrappers e teste de compatibilidade. Não ligar a engine atual diretamente à API sem corrigir gates.

### 3.A. Entidades, estados e interfaces da expansão (proposto)

Todas as entidades e interfaces abaixo são especificações conceituais para realização futura dos requisitos `RF16` a `RF25`. Elas não afirmam implementação prévia.

#### Entidades de domínio da expansão

| Entidade | Campos e garantias mínimos |
| --- | --- |
| `Area` | `area_id`, `name`, `description`, `owner_principal_id`, `created_at`; isolamento de contexto |
| `Workspace` | `workspace_id`, `area_id`, `name`, `status ∈ {active, archived}`; contexto operacional |
| `Project` | `project_id`, `workspace_id`, `name`, `metadata`; agrega múltiplos repositórios |
| `Repository` | `repository_id`, `project_id`, `root_canonical`, `base_branch`, `base_sha`, `allowed_paths`, `authorization_id`; validação contra traversal |
| `Authorization` | `authorization_id`, `resource_ref`, `principal_id`, `scopes`, `granted_at`, `revoked_at`; revogação imediata |
| `AgentDefinition` | `agent_id`, `name`, `version`, `driver_type`, `declared_capabilities`, `limitations`, `is_certified`; Claude Code, OpenCode e Codex são propostos com `is_certified=false` |
| `CapabilityDeclaration` | `name`, `version`, `supports_tools`, `supports_workspace`, `supports_cancellation`, `supports_streaming`, `certified_on` (driver+SO+data) |
| `Profile` | `profile_id`, `name`, `agent_ref`, `model_ref`, `executor_ref`, `skills_refs`, `mcp_refs`, `memory_policy`, `resource_limits` |
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
| `SecretRef` | `secret_name`, `provider_type ∈ {env, vault, keyring}`, `source_key`; valor bruto nunca é armazenado |
| `ExtensionManifest` | `extension_id`, `name`, `version`, `entrypoint`, `permissions_required`, `compatible_api_version`, `checksum` |
| `ExtensionInstall` | `install_id`, `extension_id`, `status ∈ {proposed, consented, installed, active, disabled, quarantined, revoked}`, `installed_at` |
| `Preference` | `preference_id`, `scope_type`, `scope_id`, `key`, `value_json`, `source ∈ {explicit, inferred_opt_in}`, `version` |
| `PreferenceSnapshot` | `run_id`, `preferences_hash`, `resolved_preferences_json`; imutável por run |
| `TransportDefinition` | `transport_id`, `type ∈ {local, ssh, ide, cdp, remote}`, `target_identity`, `capabilities`, `is_certified` |
| `TransportHealth` | `transport_id`, `status ∈ {unknown, healthy, degraded, unreachable}`, `last_check_at`, `error_detail` |
| `AccessToken` | `token_hash`, `principal_id`, `scopes`, `expires_at`, `revoked_at`; valor plano nunca é persistido |

#### Máquinas de estado da expansão

```text
DiscoveredResource:
  untrusted -> approved -> active
  untrusted -> rejected
  active    -> revoked
  active    -> untrusted (quando o hash do arquivo no disco for alterado)

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
```

#### Interfaces de serviço centrais da expansão

- `AgentRegistry`: `resolve(profile) -> EffectiveCapabilities | Error`
- `ProfileResolver`: `validate(components) -> ValidationResult`, `snapshot(profile, run_id) -> ProfileSnapshot`
- `RouteSelector`: `select(request, candidates, policy) -> RouteDecision` (implementações: `DirectSelector` e `OmniRouteSelector`)
- `ConsentService`: `request(purpose, scope) -> ConsentRequest`, `grant(id) -> ConsentRecord`, `revoke(id) -> RevocationResult`
- `MemoryStore`: `store(entry, consent_id) -> MemoryEntry`, `query(scope, query) -> List[MemoryEntry]`, `revoke(id) -> Result`
- `DiscoveryService`: `scan(authorized_root) -> List[DiscoveredResource]`, `approve(id, actor) -> DiscoveredResource`
- `ExtensionHost`: `install(manifest, consent) -> ExtensionInstall`, `execute(call, permissions) -> CallResult`, `revoke(id) -> Result`
- `TransportRegistry`: `check_health(transport_id) -> TransportHealth`, `assert_target(target_identity) -> TargetValidation`
- `Redactor`: `redact_payload(data) -> SanitizedData`, `redact_log(line) -> SanitizedLine`
- `AuthPolicy`: `authorize(token_hash, scope, resource_ref) -> AuthorizationDecision`

### Dados e estados

SQLite com foreign keys habilitadas em cada conexão, migração versionada, transações curtas e espera por lock limitada. Usar revisão inteira para concorrência otimista. Artefatos ficam no filesystem; gravar arquivo temporário, finalizar atomicamente e só então registrar referência. Após crash, reconciliar órfãos sem apagá-los automaticamente.

Novas tabelas da expansão (gerenciadas por migrações versionadas independentes): `areas`, `workspaces`, `projects`, `repositories`, `authorizations`, `agent_definitions`, `profiles`, `profile_snapshots`, `sessions`, `threads`, `metric_samples`, `route_decisions`, `memory_entries`, `consent_records`, `discovered_resources`, `extension_installs`, `preferences`. A tabela de `checkpoints` permanece restrita à recuperação técnica de execuções; `memory_entries` tem ciclo de vida, expiração e auditoria próprios.

Run: `queued -> running -> waiting/reviewing -> running/succeeded/failed/cancelled`; cancelamento também pode partir de queued/running. `waiting` exige causa e limite. Task usa estados do contrato, acrescidos de `cancelled` para cancelamento explícito. Nova tentativa pode devolver failed/blocked/rejected a running por comando registrado; resultado anterior permanece imutável. Acceptance e integração são decisões distintas. Run só sucede com todas as tarefas obrigatórias aceitas e, quando solicitada, integração aprovada.

Persistência em `.orchestrator/checkpoints.sqlite`; artefatos em `.orchestrator/run/<run_id>/task/<task_id>/attempt/<attempt_id>/`; worktrees sob `.orchestrator/worktree/`. Diretórios de expansão: `.orchestrator/memory/` (memórias locais autorizadas), `.orchestrator/discovery/` (índice de varredura), `.orchestrator/extensions/` (plugins instalados). IDs são gerados pelo serviço, nunca caminhos fornecidos pelo cliente. Migração de `.hydra/` é explícita, com backup e preservação dos schemas legados.

### API proposta

Prefixo `/v1/control-plane`. Rotas novas são propostas, exceto bootstrap já existente.

| Método e rota | Semântica |
| --- | --- |
| POST /projects | Valida raiz permitida e cadastra projeto |
| POST /runs | RunSpec, Idempotency-Key; retorna 202 e run ID |
| GET /runs e /runs/{id} | Lista paginada e snapshot versionado |
| GET /runs/{id}/tasks e /runs/{id}/artifacts | Evidência vinculada à execução |
| GET /runs/{id}/events | SSE, Last-Event-ID como sequência; replay seguido de eventos ao vivo |
| POST /runs/{id}/cancel | Solicita cancelamento idempotente; conclusão confirmada por estado |
| POST /runs/{id}/tasks/{task_id}/retry | Nova tentativa após reconciliação |
| POST /runs/{id}/tasks/{task_id}/review | accepted/rejected, motivo e expected_revision |
| POST /runs/{id}/integrate | Integra somente resultados aceitos, reais e íntegros |

Mesma chave e mesmo payload devolvem mesmo resultado; chave reutilizada com payload diferente retorna 409. Revisão vencida/transição inválida: 409; schema inválido: 422; recurso ausente: 404; credencial inválida: 401/403; dependência obrigatória indisponível: 503. Envelope de erro: `code`, `message`, `run_id` opcional, `retryable`; sem traceback/segredo. Falha assíncrona de executor aparece no estado/evento, não modifica retroativamente o HTTP 202.

SSE entrega pelo menos uma vez; cliente deduplica por run/seq. Retenção que invalida cursor retorna erro explícito e solicita novo snapshot. Inferência em `/v1/chat/completions` não inicia mutações Git; manter ID estável por resposta e rejeitar parâmetros/ferramentas não suportados em vez de ignorá-los.

### 3.B. Rotas propostas da expansão (/v1/control-plane)

Todas as rotas abaixo são propostas para realização futura de `RF16` a `RF25`. Todas exigem token de autenticação local com escopo apropriado.

| Método e rota | Semântica da expansão |
| --- | --- |
| GET /areas, POST /areas | Lista e cria áreas lógicas de trabalho |
| GET /workspaces, POST /workspaces | Lista e cadastra workspaces vinculados a áreas |
| GET /projects/{id}/repositories, POST /projects/{id}/repositories | Associa repositório com validação de raiz e caminho canônico |
| GET /agents, GET /executors, GET /capabilities | Consulta catálogo de agentes, executores e status de certificação |
| GET /profiles, POST /profiles | Cadastra e lista perfis combináveis de execução |
| POST /profiles/{id}/resolve | Valida combinação e devolve snapshot efetivo imutável pré-execução |
| GET /sessions, GET /sessions/{id}/threads | Lista sessões ativas e suas árvores de threads |
| GET /sessions/{id}/events | SSE com cursor `Last-Event-ID` para eventos da sessão e de suas threads |
| GET /runs/{id}/metrics | Retorna amostras de métricas com valores `observed`, `stale` ou `unknown` |
| GET /runs/{id}/route-decisions | Retorna trilha auditável de seleção de rota e candidatos avaliados |
| GET /memory, POST /memory | Consulta e grava memórias sob consentimento explícito prévio |
| POST /memory/{id}/revoke | Revoga memória e impede seu uso em novas execuções |
| POST /consents, POST /consents/{id}/revoke | Registra e revoga consentimentos para memória ou extensões |
| POST /discovery/scan | Inicia varredura opt-in restrita a raízes locais allowlisted |
| GET /discovery/resources | Lista recursos descobertos e seus estados de confiança |
| POST /discovery/resources/{id}/approve, POST /discovery/resources/{id}/reject | Aprova ou rejeita recurso descoberto; registra principal |
| GET /skills, POST /skills, GET /mcps, POST /mcps | Gerencia skills e servidores MCP; segredos são apenas referências |
| GET /extensions, POST /extensions/install | Instala extensão com manifesto verificado e consentimento |
| POST /extensions/{id}/revoke, POST /extensions/{id}/rollback | Revoga extensão imediatamente ou restaura versão anterior |
| GET /preferences, PUT /preferences | Consulta e atualiza preferências escopadas por usuário/área/projeto |
| GET /transports, GET /transports/{id}/health | Consulta transportes registrados e seus healthchecks observados |
| POST /tokens, POST /tokens/{id}/revoke | Emite e revoga tokens locais com escopos granulares |

#### Regras de erro adicionais da expansão
- `401 Unauthorized`: token ausente, formato inválido ou assinatura local não reconhecida.
- `403 Forbidden`: token válido, mas sem escopo para o recurso (ex.: token de leitura tentando aprovar recurso descoberto ou disparar integração).
- `409 Conflict`: consentimento ausente para gravação de memória; tentativa de ativação de recurso em estado `untrusted`; conflito de hash de recurso descoberto.
- `410 Gone`: cursor de SSE expirado na retenção; cliente deve solicitar novo snapshot completo.
- `422 Unprocessable Entity`: perfil com combinação incompatível de capacidades (ex.: executor sem suporte a worktree pareado com tarefa que exige isolamento).

#### Equivalência em linha de comando (CLI)
A CLI `hydra` implementará comandos idênticos consumindo a mesma camada de serviço de aplicação: `hydra area`, `hydra project`, `hydra repo`, `hydra agent`, `hydra profile`, `hydra session`, `hydra metrics`, `hydra memory`, `hydra discovery`, `hydra extension`, `hydra preference`, `hydra transport`, `hydra token`. Toda operação CLI suportará flags `--json` para integração scriptável e códigos de saída refletindo sucesso ou falha da operação.

### Segurança e limites

Bind local padrão; token local para comandos e leitura de evidência, CORS com allowlist. Não registrar tokens. Autorizar raiz do projeto e normalizar caminhos/symlinks. Worktree não constitui sandbox: capacidade de contenção depende do executor. Testes e comandos são entradas autorizadas do projeto, executados com limites; logs são redigidos antes de exposição. Cancelamento só é anunciado concluído após verificar árvore encerrada no SO certificado.

Segurança ampliada (RT25): o servidor rejeitará qualquer configuração com `allow_origins=["*"]` associada a credenciais ativas. Tokens de acesso utilizam derivação segura (PBKDF2/Argon2) e nunca são logados ou persistidos em texto plano. O módulo `core/redaction.py` interceptará todos os eventos antes da escrita no banco e antes da transmissão via SSE, expurgando padrões de tokens, chaves SSH, senhas e credenciais OAuth. Nenhum comando de execução ou script de extensão terá acesso a variáveis de ambiente não filtradas ou a soquetes de comunicação fora das allowlists de rede do projeto.

## 4. Pré-condições

Configuração validada, schema compatível, repo acessível, executor elegível e orçamento suficiente. Uma tarefa em execução possui no máximo uma tentativa ativa; recuperação deve reconciliar processo antigo antes de novo spawn. Para a expansão (RT13–RT25), áreas, repositórios, perfis, recursos locais descobertos e extensões exigem concessão prévia de autorização e verificação de integridade antes do uso operacional; nenhum recurso é ativado implicitamente por mera existência no sistema de arquivos.

## 5. Pós-condições

Resultado persistido com checks e referências de artefato; evento correlacionado; integração e limpeza têm resultado próprio. Falha de persistência impede anúncio de sucesso. Não há alterações silenciosas da branch ativa do operador. Operações de consentimento de memória ou aprovação de extensão geram registros auditáveis imutáveis; revogações impedem que novas execuções acessem o recurso revogado.

## 6. Invariantes

Transação para estado/evento, exclusão mútua da integração, resultados imutáveis, tarefas dependentes no mesmo run, contrato fixado por hash e limites de tempo/tentativas. Métricas registram duração, filas e falhas sem inventar custo/token não informado (`unknown` permanece `unknown`).

Invariantes da expansão: (1) checkpoints de execução são separados de memória adaptativa persistente; (2) texto produzido por agente ou declaração textual de sucesso nunca constituem prova de execução ou validação de check; (3) recursos descobertos iniciam no estado `untrusted` e só transitam com aprovação de principal autenticado; (4) extensões operam em processo isolado e não têm acesso direto ao banco de dados do control plane; (5) a interface visual consome apenas read models persistidos e não pode alterar estado sem comando autenticado correspondente; (6) a UI é operável por teclado, com foco visível, rótulos semânticos e estados comunicados sem dependência exclusiva de cor.

## 7. Falhas e recuperação

Cobrir disco cheio, lock do banco, subprocesso órfão, arquivo fora do escopo, conflito, quota desconhecida e conexão perdida. Em efeito externo ambíguo, marcar blocked e exigir reconciliação. Não aplicar retry cego nem deduplicação textual como garantia de integridade de código.

Falhas da expansão: (1) descoberta de recurso adulterado (divergência de hash) força transição para `untrusted` e bloqueia execução; (2) tentativa de escrita de memória sem consentimento ativo gera erro `409` e não persiste dados; (3) perda de conexão SSE é reconciliada por cursor `Last-Event-ID` com deduplicação sem conclusão prematura; (4) extensão incompatível ou revogada é terminada de forma síncrona sem afetar a integridade do processo principal.

### 7.A. Critérios negativos objetivos

| Caso de teste negativo | Comportamento obrigatório do sistema | Requisito |
| --- | --- | --- |
| Repositório fora da allowlist de projetos | Rejeição imediata com código 403 e registro em log de auditoria; nenhum processo Git é iniciado | RT13 |
| Caminho com symlink ou tentativa de traversal fora da raiz autorizada | Bloqueio imediato da operação e registro da violação; rejeição com código 400 | RT13 |
| Repositório secundário sem concessão explícita de autorização | Tentativa de acesso bloqueada; permissão do repositório primário não é herdada | RT13 |
| Driver CLI não certificado selecionado em modo de produção | Execução bloqueada antes do spawn com erro tipado informando ausência de certificação | RT14 |
| Perfil combinando capacidades incompatíveis (ex.: tarefa exige isolamento, executor não suporta) | Rejeição na validação pré-execução com código 422 e indicação da incompatibilidade | RT15 |
| Alteração de definição de perfil enquanto um run correspondente está em andamento | Snapshot do run em execução permanece imutável e inalterado; novo perfil afeta apenas novos runs | RT15 |
| Cliente SSE reconecta com `Last-Event-ID` expirado pela política de retenção | Servidor retorna código 410 (Gone) ou erro tipado orientando solicitação de novo snapshot completo | RT16 |
| Evento retransmitido durante reconciliação de conexão SSE | Cliente deduplica pelo par (escopo, sequência monotônica) sem processar efeito duplicado | RT16 |
| Provedor de inferência não retorna métricas de tokens ou custo | Valor registrado como `unknown`; nunca preenchido com zero ou estimativa inventada | RT17 |
| Quota de modelo indisponível por queda de gateway | Status exibido como `unknown` ou `stale`; proibido reportar 100% disponível | RT17/RT18 |
| Gravação de memória solicitada sem consentimento ativo registrado | Recusa imediata com código 409 e nenhuma persistência de dados em disco | RT19 |
| Checkpoint técnico de tentativa tenta ser importado automaticamente como memória de longo prazo | Bloqueio por validação de esquema; checkpoint e memória possuem tabelas e lifecycles separados | RT19 |
| Recurso descoberto localmente tem seu hash alterado no disco | Recurso transita automaticamente para `untrusted` e tem execução bloqueada até nova aprovação | RT20 |
| Segredo configurado como referência tem seu valor exposto em prompt, evento ou log | Falha de validação no módulo de redaction e sanitização antes de qualquer emissão | RT21 |
| Extensão ou plugin tenta acessar banco de dados do core diretamente | Acesso negado pelo isolamento de processo e falta de permissão de soquete/arquivo | RT22 |
| Extensão revogada tenta emitir novas chamadas de ferramenta | Interceptação pelo `ExtensionHost` e bloqueio imediato com evento de auditoria | RT22 |
| Preferência inferida tenta sobrescrever instrução explícita de projeto sem opt-in | Ação bloqueada; instrução explícita tem precedência estrita no snapshot | RT23 |
| Interface visual tenta marcar tarefa como aceita sem comando versionado correspondente | Bloqueio de ação; a UI é consumidora de API e não autoridade de decisão | RT23 |
| Transporte SSH com chave de host divergente da esperada | Conexão abortada imediatamente sem bypass silencioso de verificação | RT24 |
| Requisição HTTP recebida com cabeçalho de origem não allowlisted ou CORS wildcard com credenciais | Rejeição com código 403 Forbidden; credenciais não processadas | RT25 |

## 8. Tasks iniciais rastreáveis

Todas pendentes. Cada linha é uma unidade de implementação com testes no mesmo commit; não autoriza execução de provedores pagos. Specs S01–S13 detalham posteriormente cada módulo.

| Task | Depende | RF / RT | Arquivos de propriedade | Definição de concluído |
| --- | --- | --- | --- | --- |
| T01 Config canônica | — | RF02 / RT01 | config.py, config.yaml, .gitignore, tests/test_config.py | Aliases resolvidos; inválidos recusados; runtime ignorado |
| T02 Contratos e estados | T01 | RF03/RF07 / RT02 | model.py, contrato_execucao.md, tests/test_model.py | Schemas e transições válidos/inválidos cobertos |
| T03 Store e migração | T02 | RF03/RF05 / RT03/RT11 | core/checkpointer.py, engine/checkpointer.py, tests/test_checkpointer.py | Restart, chave idempotente e transação testados |
| T04 Runner e fake | T03 | RF04/RF06 / RT04 | bridge/worker_runner.py, tests/test_worker_runner.py | Cwd real, erro, timeout e árvore cancelada comprovados |
| T05 Workspace Git | T04 | RF01/RF04 / RT05 | core/git_workspace.py, tests/test_git_workspace.py | SHA fixo e worktree real; estado do usuário preservado |
| T06 Checks e integração | T05 | RF07/RF08 / RT06 | core/git_workspace.py, core/run_service.py, tests/test_integration.py | Patch real, escopo, conflito e checks combinados governam aceite |
| T07 Entrada M1 | T06 | RF03–RF08 / RT10 | cli.py, server.py, tests/test_server.py, tests/test_cli.py | Submeter/consultar/cancelar/revisar usam mesmo serviço com autorização |
| T08 CI e manual M1 | T07 | RF15 / RT12 | .github/workflows/ci.yml, doc/j_manual/README.md, pyproject.toml | Testes offline e instalação reproduzível; driver real com certificação separada |

Paths Python da tabela são relativos a `src/hydra_orch/`, exceto `tests/`, configuração e documentação. Arquivos ainda inexistentes são destinos propostos. T01–T07 concretizam S01–S05/M1; T08 inicia S13. Swarm, retomada e expansão seguem S06–S12 do plano e só recebem status concluído com seus gates. Validar no mínimo Python 3.10 e versão corrente escolhida no CI; SO anunciado precisa validar gestão de processos.

### 8.2. Tasks da expansão (T09 a T24 — propostas)

Todas as tarefas abaixo são propostas para realização dos requisitos `RF16` a `RF25` e `RT13` a `RT25`. Nenhuma capacidade é considerada entregue antes da aprovação dos testes unitários, de processo e de segurança especificados.

| Task | Depende | RF / RT | Arquivos de propriedade propostos | Definição de concluído (DoD) |
| --- | --- | --- | --- | --- |
| T09 Auth e CORS estrito | T07 | RF15/RF24 / RT25 | server.py, core/auth.py, core/redaction.py, tests/test_auth.py | Token local obrigatório; allowlist de CORS estrita sem wildcard credenciado; redaction de segredos validada em testes |
| T10 Migrações do banco de control plane | T03, T09 | RF16–RF25 / RT03/RT25 | core/checkpointer.py, migrations/, tests/test_migrations.py | Tabelas de expansão versionadas; rollback testado; FKs ativas; banco legado preservado sem exclusão |
| T11 Registry de áreas e repositórios | T10 | RF16 / RT13 | core/workspace_registry.py, tests/test_workspace_registry.py | Hierarquia Area/Workspace/Project/Repo persistida; acesso a repositório não autorizado ou traversal bloqueado |
| T12 Catálogo de agentes e capabilities | T02, T04, T10 | RF17, RF14 / RT14 | core/agent_registry.py, config.yaml, tests/test_agent_registry.py | Catálogo com capabilities declaradas; driver não certificado bloqueado em modo produto; ausência de CLI é erro |
| T13 Perfis e snapshots imutáveis | T11, T12 | RF17, RF23 / RT15 | core/profile_service.py, tests/test_profile.py | Resolução de perfis/combos com validação pré-execução; snapshot imutável com hash gerado para cada run |
| T14 Sessões, threads e SSE replay | T03, T07, T10 | RF18, RF05 / RT16 | core/session_service.py, server.py, tests/test_sse_replay.py | Árvore de sessões e threads; stream SSE com Last-Event-ID, replay e deduplicação lógica comprovados |
| T15 Métricas de observabilidade | T03, T10, T14 | RF19 / RT17 | core/metrics.py, tests/test_metrics.py | Fila, duração, tokens e custo vinculados a runs com estados observed, stale ou unknown; zero não é inventado |
| T16 Seleção adaptativa de rotas | T12, T15 | RF20, RF11 / RT18 | core/route_selector.py, bridge/omniroute_client.py, tests/test_route_selector.py | Decisão de rota registrada com candidatos e motivo; modo direto sem OmniRoute comprovado em teste |
| T17 Consentimento e memória adaptativa | T09, T10 | RF21 / RT19 | core/consent.py, core/memory_store.py, tests/test_memory.py | Escrita de memória exige ConsentRecord ativo; revogação funcional; isolamento total contra checkpoints técnicos |
| T18 Discovery local controlado | T09, T11 | RF22 / RT20 | core/discovery.py, tests/test_discovery.py | Varredura opt-in restrita a raízes permitidas; cálculo de hash e estado untrusted; sem ativação automática |
| T19 Skills, MCPs e secret references | T12, T17, T18 | RF17, RF22 / RT21 | core/skill_registry.py, bridge/mcp_client.py, tests/test_secrets.py | Segredos gerenciados como referências externas; resolução no spawn com env filtrado; valores brutos nunca persistidos |
| T20 Isolamento de extensões e plugins | T18, T19 | RF24 / RT22 | core/extension_host.py, tests/test_extension.py | Manifesto validado; processo isolado sem acesso a DB core; revogação de plugin interrompe efeitos imediatamente |
| T21 Preferências e acessibilidade | T13, S11 | RF23 / RT23 | core/preferences.py, tests/test_preferences.py, doc/h_test/README.md | Preferências escopadas e reversíveis; checklist de acessibilidade (teclado, foco, roles e contraste) validado |
| T22 Transportes certificados | T04, T09 | RF25, RF14 / RT24 | bridge/transport_registry.py, bridge/ssh_tunnel.py, tests/test_transport.py | Alvo, identidade e healthcheck verificados; host SSH alterado falha conexão; isolamento de saídas concorrentes |
| T23 CLI de control plane estendida | T11–T22 | RF16–RF25 / RT13–RT25 | cli.py, tests/test_cli.py | Comandos CLI para áreas, projetos, perfis, memória, discovery e extensões consumindo a mesma camada de serviço |
| T24 CI estendido e runbooks operacionais | T08, T23 | RF15, RF23, RF25 / RT12 | .github/workflows/ci.yml, doc/j_manual/README.md | Suíte de testes offline cobrindo regras negativas da expansão; documentação de auditoria e runbooks atualizada |

### 8.3. Faseamento e etapas propostas (S00 a S18)

As etapas S00 a S13 mantêm-se como definidas no [plano de desenvolvimento](../a_context/plano_desenvolvimento.md). As etapas S14 a S18 são propostas para formalizar as especificações técnicas da expansão após o marco M1:

```text
V0 (Núcleo verificável):   S00 -> S01 -> S02 -> S03 -> S04 -> S05 -> M1 (T01-T08)
V1 (Control plane visual): M1  -> S10 (API) -> S11 (UI fina) -> T09
V2 (Workspaces e perfis):  S14 (workspaces_perfis.md: T10, T11, T12, T13)
V3 (Coordenação e rotas):  S06 (swarm) -> S07 (handoff) -> S08 (quota) -> S15 (sessoes_observabilidade.md: T14, T15, T16)
Gate de segurança V4:      S16 (seguranca_proveniencia.md: validação de auth, secrets, consentimento e allowlists)
V4 (Memória e extensões):  S16 -> S17 (memoria_discovery_extensoes.md: T17, T18, T19, T20) -> S18 (acessibilidade_transportes.md: T21, T22, T23, T24)
```

Nenhuma etapa da expansão pode anteceder a conclusão do marco M1 de execução verificável local.

### 8.4. Matriz de rastreabilidade (RF → RT → Task → Evidência → Caso Negativo)

| RF | RT | Task | Etapa | Evidência de conclusão | Caso negativo correspondente (§7.A) |
| --- | --- | --- | --- | --- | --- |
| RF01–RF08 (RF01, RF02, RF03, RF04, RF05, RF06, RF07, RF08) | RT01–RT10 | T01–T07 | S01–S05 / M1 | Execução de subprocesso real em fixture temporária com diff e check registrados | CLI ausente falha; simulação rejeitada |
| RF09, RF10, RF11, RF12 | RT07–RT09 | T02, T06 | S06–S09 | Swarm coordenado por DAG, retomada/handoff sob gate e quota unknown | Ciclo em DAG rejeitado; quota offline unknown |
| RF13–RF15 | RT10–RT12 | T07, T08 | S10–S13 | Bootstrap funcional, exportação sanitizada e suíte offline sem dependência de contas | CORS irrestrito rejeitado; artefato alterado falha |
| RF16 | RT13, RT25 | T10, T11 | S14 | Testes unitários de cadastro e resolução canônica de múltiplos repositórios e áreas | Repositório fora de allowlist ou traversal recusado |
| RF17 | RT14, RT15, RT21 | T12, T13, T19 | S14 | Validador de perfis rejeita incompatibilidades; snapshot imutável gravado no run | Driver não certificado em produção falha antes do spawn |
| RF18 | RT16 | T14 | S15 | Replay de eventos SSE com cursor `Last-Event-ID` e ordenação monotônica | Conexão perdida reconciliada sem duplicação lógica |
| RF19 | RT17 | T15 | S15 | Endpoint de métricas exibe tokens e custos com proveniência e status explícito | Provedor sem tokens gera status unknown (nunca zero) |
| RF20 | RT18 | T16 | S15 | Trilha auditável de `RouteDecision` gravada com candidatos, motivo e fallback | Rota inelegível nunca é selecionada; modo direto OK |
| RF21 | RT19 | T10, T17 | S17 (pós-S16) | Persistência de memória vinculada a `ConsentRecord`; tabela isolada de checkpoints | Tentativa de escrita sem consentimento retorna 409 |
| RF22 | RT20, RT21 | T18, T19 | S17 (pós-S16) | Varredura em raiz allowlisted registra recursos com hash e status untrusted | Recurso com hash alterado bloqueado e desativado |
| RF23 | RT23, RT15 | T13, T21 | S18 / S11 | Checklist automatizado e manual de acessibilidade (teclado, foco e contraste) | Preferência inferida não sobrepõe instrução de projeto |
| RF24 | RT22 | T20 | S17 (pós-S16) | Extensão executada em processo isolado; revogação bloqueia novas chamadas | Tentativa de acesso a DB core por plugin é bloqueada |
| RF25 | RT24, RT14 | T22 | S18 / S12 | Verificação de chave de host SSH e healthcheck tipado de transportes | Host SSH com chave modificada aborta conexão |
| Transversal | RT25 | T09 | S16 | Middleware de autenticação local rejeita tokens inválidos e sanitiza logs/eventos | CORS wildcard com credenciais retorna erro 403 |

### 8.5. Documentos de coerência pendentes (não editados nesta etapa)

A formalização completa da arquitetura da expansão exigirá o alinhamento dos seguintes documentos em etapas documentais dedicadas, antes da codificação das tarefas correspondentes:

- `doc/b_spc/contrato_execucao.md`: formalização dos schemas JSON de `ProfileSnapshot`, `Session`, `Thread`, `ConsentRecord`, `MemoryEntry` e eventos de control plane.
- `doc/b_spc/arquitetura_hydra_omniroute_ui.md`: atualização dos diagramas de blocos para incluir o `AgentRegistry`, `DiscoveryService` e `ExtensionHost`.
- `doc/d_mer/mer.md` e `mer.mmd`: modelagem relacional formal das tabelas de expansão (`areas`, `workspaces`, `repositories`, `profiles`, `sessions`, `memories`, etc.).
- `doc/e_class/diagrama_classe.md` e `diagrama_classe.mmd`: diagramas de classe para as interfaces e serviços de control plane.
- `doc/b_spc/README.md`: sincronização dos contadores normativos para `RF01–RF25`, `RT01–RT25` e `T01–T24`.
- `doc/f_api/README.md`, `doc/h_test/README.md`, `doc/i_infra/README.md`, `doc/j_manual/README.md`: detalhamento de endpoints, matriz de testes de segurança/a11y, infraestrutura de sandboxing e runbooks.

## 9. Exemplos técnicos

### 9.1. Núcleo verificável

POST de RunSpec com projeto, objetivo, base SHA e tarefa delimitada cria run queued e evento numa transação. Worker fake altera arquivo numa fixture; check registra SHA/exit code. Resultado vira ready_for_review. Review com revisão correta aceita; integração aplica em worktree própria e repete check. Mesma submissão não gera outro processo; review com revisão antiga retorna 409.

### 9.2. Exemplos técnicos da expansão (proposto)

**Resolução de perfil e snapshot:** operador solicita execução associando um perfil configurado com Claude Code (driver CLI proposto) e modelo via OmniRouter. O `ProfileResolver` valida se as capabilities exigidas pela tarefa (ex.: isolamento em worktree) são suportadas pelo driver. Se compatível, gera `ProfileSnapshot` com hash imutável e grava na transação do run. Se o driver não for certificado ou faltar a CLI, a chamada falha no HTTP 422 antes de qualquer processo ser iniciado.

**Reconexão SSE com cursor:** cliente visual conecta-se a `/v1/control-plane/sessions/{id}/events` enviando cabeçalho `Last-Event-ID: 42`. O servidor recupera do banco eventos persistidos a partir da sequência 43, emite-os em ordem monotônica e prossegue transmitindo eventos ao vivo. Se a conexão cair na sequência 45, o cliente reconecta com `Last-Event-ID: 45` e deduplica pelo identificador de evento, sem perder estado nem duplicar ações.

**Consentimento e gravação de memória:** ao identificar uma preferência durável, o sistema emite solicitação de consentimento (`ConsentRecord` no estado `requested`). Somente após comando autenticado do usuário em `POST /consents/{id}` o status transita para `granted`. A gravação em `POST /memory` valida a existência do consentimento ativo antes de persistir a `MemoryEntry`. Se o consentimento for revogado via `POST /consents/{id}/revoke`, execuções futuras deixam de receber o fragmento de memória na injeção de contexto.

**Discovery local rejeitando adulteração:** o serviço `DiscoveryService` executa varredura opt-in em raiz autorizada, encontrando um manifesto de skill em disco. O sistema calcula o SHA-256 do arquivo e registra `DiscoveredResource` como `untrusted`. O operador aprova a skill via API/CLI e o status vira `approved`. Se em momento posterior o arquivo da skill for alterado em disco, o próximo hash check detecta a divergência, transita o recurso imediatamente para `untrusted` e impede sua execução em qualquer sessão até nova aprovação explícita.
