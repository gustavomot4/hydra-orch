# plano_desenvolvimento — Plano Mestre de Especificação e Desenvolvimento do Hydra

**Identificador Formal:** `plano_desenvolvimento.md`
**Caminho Canônico:** `doc/a_context/plano_desenvolvimento.md`
**Versão:** `v01_00_0000`
**Status:** `PROPOSTO / ATIVO`
**Autoridade:** Diagnóstico arquitetural do checkout do hydra-orch e planejamento de entregas por marcos.
**Escopo:** Revisão do código, lacunas A01 a A18, gates operacionais, inventário de arquivos e sequência de tarefas.

---

**Estado:** proposta de sequência técnica; não comprova implementação das capacidades planejadas.

**Base revisada:** `9a8a7ab8a7a4055b00a28853e00e45428f50e961`, em 2026-11-05.

**Escopo da revisão:** os 58 arquivos versionados, incluindo código, testes, configuração, documentação, encaminhamentos de agentes e marcadores vazios. Metadados internos do Git não integram o produto.

## 1. Purpose — propósito

Detalhamento disponível: [PRD funcional](../b_spc/prd_funcional.md), [PRD técnico com tasks T01–T08](../b_spc/prd_tecnico.md), [diagrama de classes](../e_class/diagrama_classe.md) e [MER](../d_mer/mer.md). A criação documental não conclui as etapas de implementação abaixo.

Transformar o scaffold em um Hydra que combine interface visual, control plane adaptativo e execução verificável de engenharia. O produto deve organizar áreas de trabalho, projetos e repositórios; conectar agentes, modelos, executores, skills e MCPs; apresentar filas, eventos, duração, tokens e custos com origem; e permitir que o usuário escolha ou revise perfis de execução. O primeiro incremento continua recebendo uma tarefa delimitada, executando um worker em worktree real, preservando o resultado, executando checks e preparando integração revisável.

A interface é primeira classe como produto, mas não substitui o núcleo verificável nem decide aceite por conta própria: consome estado persistido e envia comandos explícitos. O OmniRouter permanece uma integração opcional de inferência, quota e fallback; o Hydra continua funcionando no modo direto. Memória adaptativa, discovery local, sessões multiagente, extensões e transportes remotos dependem de gates posteriores de segurança, proveniência, autorização e certificação.

Este documento é o plano mestre de elaboração de specs e entregas. O [PRD técnico (§3.4)](../b_spc/prd_tecnico.md) governa as entidades e contratos de execução; a [arquitetura](../g_code/architecture.md) governa as fronteiras; a [taxonomia](taxonomia_file_system.md) governa os caminhos e organização. As decisões abaixo são propostas para concretizar essas fontes. O [contexto de investigação](CONTEXTO-ORQUESTRACAO.md) permanece como registro histórico, com sua própria base examinada.

## 2. Why — avaliação de coerência

A proposta faz sentido: separar coordenação de engenharia, inferência, execução de ferramentas, persistência e apresentação evita concentrar responsabilidades no gateway. SQLite, subprocessos, Git worktrees e FastAPI oferecem uma base adequada ao primeiro produto local. A UI é uma superfície prioritária do produto, mas só deve operar sobre contratos, read models e eventos persistidos; não deve antecipar ou simular o fluxo verificável.

O repositório ainda não sustenta as promessas de execução autônoma completa, retomada exata ou integração segura. Há duas implementações de swarm, dois checkpoints e dois gerenciadores SSH, com configurações e responsabilidades diferentes. CLI e API usam `core/router.py`; a existência de `engine/` não significa que seus motores participem desses caminhos.

### 2.1. Achado, evidência e consequência

As constatações abaixo são de leitura estática, salvo validação explicitamente indicada. Nenhum agente real ou fluxo de swarm foi disparado nesta revisão.

| ID / prioridade | Evidência no checkout | Consequência e tratamento |
| --- | --- | --- |
| A01 / P0 | `config.py:HydraConfig.providers` constrói provedores fixos; `orchestrator.resilience` usa aliases como `architect_heavy`, ausentes de `HydraRouter.adapters` | O relay pode produzir “No active adapters” com adaptadores registrados. Resolver alias, executor e modelo explicitamente em S01; cobrir o caminho de entrada |
| A02 / P0 | `bridge/worker_runner.py` escreve `CONTRACT_APPLIED.md` e retorna `success=True` quando a CLI falta | Simulação aceita como execução; falhar com `executor_unavailable`, reservando fake para testes/dry-run explícito |
| A03 / P0 | `bridge/omniroute_client.py` fabrica texto de sucesso quando offline e quota de 100% com `offline_or_mock` | Consumidores podem interpretar ausência de evidência como capacidade disponível; devolver erro tipado e quota desconhecida |
| A04 / P0 | `core/router.py:_execute_swarm_mode` chama `adapter.generate`; worktree só consta no prompt; `results` não condiciona merge | Texto não altera arquivos. Conectar executor com `cwd`, capturar diff e validar resultado |
| A05 / P0 | Ambos os swarms integram e limpam sem gate completo; `core/swarm.py` faz checkout de `main`; ambos usam remoção forçada | Pode afetar checkout do usuário e apagar alterações não integradas. Criar integração isolada e preservar worktree em falha |
| A06 / P0 | `engine/swarm.py:create_worktree` cria diretório comum se Git falhar | Isolamento alegado sem worktree; criação deve falhar de forma observável |
| A07 / P1 | `engine/swarm.py` não converte necessariamente alterações do worker em commit/patch integrável; ignora `worker_results` e retorno de merge | Merge pode não conter trabalho produzido; atribuir artefatos e registrar decisão por tarefa |
| A08 / P1 | `core/router.py` grava checkpoint ao terminar/atingir limite; relay troca mensagens por um prompt; persistente reutiliza mensagens originais | Queda perde buffer e retomada pode repetir efeitos; persistir progresso e handoff estruturado |
| A09 / P1 | `engine/relay.py` limita contexto a 1.500 caracteres/15 linhas; checkpoint instanciado não é gravado nesse fluxo | Não existe recuperação durável por etapa; distinguir pipeline de tarefas de failover de inferência |
| A10 / P1 | `engine/healer.py:heal_build_failure` retorna `True` sem aplicar patch/testar; swarm apenas anuncia healing | Reparação não comprovada; transformar em tentativa real limitada pelo orçamento e pelos mesmos gates |
| A11 / P1 | `engine/swarm.py` usa `gather` sem aplicar `max_parallel_worktrees`; runner não encerra explicitamente processo/descendentes em timeout | Concorrência e cancelamento sem garantia; scheduler limitado e ciclo de vida de processo testado por SO |
| A12 / P1 | `config.yaml` usa `.hydra/`; taxonomia determina `.orchestrator/`; `.gitignore` não ignora toda `.hydra/` | Contratos e artefatos textuais podem aparecer como untracked. Normalizar runtime e definir migração sem apagar legado |
| A13 / P1 | `server.py` consulta `providers.remote_local['ssh_remote']`, ausente da compatibilidade fixa, em vez de `remote_ssh_gpu` | Configurar SSH como habilitado não comprova inicialização; unificar configuração e ciclo de vida |
| A14 / P1 | `server.py` permite CORS amplo, não autentica; CDP seleciona primeira página se alvo falha; SSH desativa checagem de host | Antes de comandos de execução na API, especificar autorização local, origem, alvo e identidade do host |
| A15 / P1 | `server.py` gera ID novo por chunk; schemas/adaptadores concentram saída em texto; erros viram texto e resposta não-stream termina com `stop` | Compatibilidade com agentes que usam ferramentas não está comprovada; especificar subconjunto suportado e rejeições explícitas |
| A16 / P2 | Decompositores retornam quatro tarefas fixas; contrato gera OpenAPI/Prisma estáticos; stitcher compara linhas com `strip()` | Sem DAG adaptativo e sem garantia de correção do código costurado; adotar plano estruturado validado e preservar indentação |
| A17 / P2 | PRD exige OmniRoute e promete tempos/reset exatos; arquitetura mais recente o torna opcional; README mostra YAML antigo e link `LICENSE` inexistente | Reconciliar fontes em S00; números e provedores externos permanecem hipóteses até verificação |
| A18 / P1 | 18 funções de teste, majoritariamente schemas/smoke; quota consulta localhost sem mock; teste de runner só verifica ausência da CLI | Suíte não demonstra execução, timeout, merge, recuperação ou segurança; criar fixtures herméticas e gates por entrega |

P0 bloqueia uso do swarm como execução confiável. P1 bloqueia a primeira versão operacional. P2 orienta expansão e fidelidade de produto. Prioridade não significa que algum item foi corrigido nesta tarefa.

A02, A03, A04, A05, A06, A07, A08, A11, A12, A14 e A18 também são dependências explícitas da nova visão: não há interface confiável sem estado persistido; não há seleção de agentes sem capabilities certificadas; não há discovery, memória ou extensões seguras sem proveniência, autorização, consentimento e revogação.

### 2.2. Inventário e destino dos arquivos existentes

Os caminhos da tabela são relativos à raiz. Cada arquivo versionado da base está representado por nome ou conjunto explicitamente enumerado.

| Arquivo ou conjunto | Avaliação e destino proposto |
| --- | --- |
| `AGENTS.md`; `CLAUDE.md`; `GEMINI.md`; `.github/copilot-instructions.md`; `.cursor/rules/project.mdc`; `.windsurf/rules/project.md` | Encaminhamentos coerentes com a fonte única. Preservar autorização Git, separação de workers e regras de publicação |
| `README.md`; `pyproject.toml`; `config.yaml`; `.gitignore` | Preservar pacote/entrypoint. Atualizar exemplos, subset de compatibilidade, dependências realmente utilizadas, exclusões e configuração. Resolver ausência de licença com o titular; não inventar texto/licenciante |
| `doc/README.md`; `doc/a_context/README.md`; `doc/b_spc/README.md`; `doc/j_manual/README.md`; `doc/j_manual/.gitkeep` | Manter índices; preencher manual de instalação, execução, recuperação e descarte conforme funcionalidades entregues |
| `doc/a_context/CONTEXTO-ORQUESTRACAO.md`; `taxonomia_file_system.md`; `visao_produto.md`; `doc/g_code/architecture.md`; `prd_funcional.md`; `prd_tecnico.md` (em `doc/b_spc/`) | Preservar investigação; consolidar PRD funcional e técnico em `doc/b_spc/`, alocando taxonomia e visão em `doc/a_context/` e arquitetura em `doc/g_code/` |
| `ws/README.md`; `ws/a_input/README.md`; `ws/a_input/.gitkeep`; `ws/b_output/README.md`; `ws/b_output/.gitkeep` | Estrutura coerente. Manter entrada versionável sem segredo e evidência local ignorada |
| `src/hydra_orch/__init__.py`; `cli.py`; `server.py`; `config.py`; `model.py` (todos no pacote) | Manter fachada pública. Configuração tipada, schemas de domínio e injeção de serviço compartilhado; retirar estado operacional criado no import quando necessário ao isolamento dos testes |
| `adapter/__init__.py`; `base.py`; `api_gateway.py`; `ide_bridge.py`; `remote_local.py`; `ui_cdp.py` (em `src/hydra_orch/`) | Manter provedores de inferência. Capacidades de ferramentas/execução só quando testadas. CDP e IDE bridge permanecem experimentais; não presumir servidor bridge externo existente |
| `core/__init__.py`; `router.py`; `swarm.py`; `checkpointer.py`; `ssh_tunnel.py` (em `src/hydra_orch/`) | `core` coordena aplicação, política e persistência canônica; router separa inferência de runs. Migrar Git para serviço único; SSH para bridge; retirar duplicação por wrappers temporários testados |
| `engine/__init__.py`; `decomposer.py`; `contract.py`; `swarm.py`; `relay.py`; `checkpointer.py`; `healer.py` (em `src/hydra_orch/`) | Engines recebem serviços via injeção. Preservar planejamento/estratégias, consolidar estado em core, retirar templates específicos de Prisma do caminho genérico e healing textual do caminho de sucesso |
| `bridge/__init__.py`; `worker_runner.py`; `omniroute_client.py`; `ssh_tunnel.py`; `cdp_fallback.py` (em `src/hydra_orch/`) | Transporte/subprocesso, sem decisão de aceite. Um SSH, um runner com drivers explícitos, gateway opcional sem sucesso fabricado; fallback CDP não deve alegar execução de ferramentas |
| `tests/test_config.py`; `test_model.py`; `test_router.py`; `test_checkpointer.py`; `test_engine.py`; `test_server.py` (todos em `tests/`) | Manter testes úteis e substituir expectativas de scaffold por contratos verificáveis. Remover dependência de serviços localhost; adicionar testes de falha e integração local sem LLM |

## 3. Contract — decisões e escopo do produto

### 3.1. Primeiro marco operacional (MVP)

Um repositório local, um operador, uma tarefa por vez e um executor CLI selecionado explicitamente continuam sendo o primeiro marco verificável. A mesma aplicação atende CLI e API; modo direto funciona sem OmniRoute. Primeiro validar com subprocesso fake que altera um arquivo numa fixture; depois certificar um driver real, sem torná-lo dependência da suíte offline.

O MVP termina em resultado revisável com patch/checks e integração em branch dedicada. Publicar alterações no repositório alvo depende da política explícita daquele run; as permissões permanentes de desenvolvimento deste checkout não viram autorização global para o produto. A UI pode acompanhar esse núcleo apenas como cliente de read models e comandos persistidos.

Ficam fora do MVP: planejamento livre por LLM, múltiplos workers, recuperação entre provedores, healing automático, memória adaptativa, discovery local, extensões, SSH/CDP operacional e coordenação multiagente ampla. A inferência existente pode continuar disponível como capacidade separada, com suas limitações declaradas.

### 3.2. Fronteiras e consolidação

```text
CLI / API / futura UI
         |
serviço de aplicação em core
   | política, estado, Git, eventos
   +---- engine: estratégias de tarefa, relay e swarm
   +---- bridge: executor CLI, gateway opcional, SSH
   +---- adapter: inferência e capacidades de cada provedor
```

Proposta: manter `core/router.py` como fachada de inferência e criar um serviço de run em `core/`. Não manter swarms independentes nem checkpoints concorrentes como fontes de verdade. Migrar consumidores e testes antes de retirar imports públicos legados. O compartilhamento de ambientes por symlink não integra o padrão inicial: worktree isola arquivos Git, mas não restringe ferramentas nem diretórios externos acessíveis ao processo.

As superfícies futuras devem separar catálogo de agentes/executores, resolução de perfis, discovery, memória, sessões/threads, extensões e preferências visuais. Esses serviços não podem ativar recursos encontrados localmente por mera existência: origem, versão, capabilities, escopo, consentimento e autorização precisam ser persistidos antes do uso.

Runtime canônico segue `.orchestrator/`, com subpastas singulares por run/tarefa/tentativa, worktrees em `.orchestrator/worktree/` e SQLite em `.orchestrator/checkpoints.sqlite`. Artefatos de saída ficam sob a execução ou `ws/b_output/`, sempre ignorados. Instalação fora do checkout precisa de diretório de estado explícito e raiz do projeto resolvida; não depender do `cwd` acidental do servidor. Migração de `.hydra/` deve ser explícita, preservar os dois schemas legados e jamais apagá-los automaticamente.

### 3.3. Entidades a formalizar em S02

A base tipada foi implementada na [spec S02](../b_spc/contrato_execucao.md), com versão de schema e exemplos válidos/inválidos. A tabela abaixo mantém a direção de evolução; campos e tipos efetivos do incremento inicial estão em `hydra_orch.model`.

| Entidade | Campos/garantias mínimos |
| --- | --- |
| `RunSpec` | `schema_version`, `run_id`, objetivo, repo absoluto, SHA base, modo, orçamento, política de integração, chave de idempotência |
| `TaskSpec` | `task_id`, objetivo e aceite, dependências, caminhos permitidos, hash do contrato, executor/capacidades, timeout, checks e autorização operacional |
| `TaskAttempt` | ID único, tarefa, provedor/modelo, sessão, workspace, início/fim, processo e causa de término; repetir cria outra tentativa |
| `TaskResult` | execução real/simulada, código do processo, estado da tarefa, resumo, diff/commit vinculado ao SHA base, arquivos, checks, artefatos e falhas |
| `RunEvent` | sequência monotônica por run, ID estável, timestamp UTC, correlação, tipo e payload redigido; replay por cursor |
| `HandoffCheckpoint` | instruções relevantes, objetivo, decisões, dependências, SHA/diff, ferramentas e seus efeitos, progresso persistido, pendências e âncora auxiliar |
| Capacidade de executor/provedor | inferência, execução em workspace, ferramentas, retomada nativa, cancelamento, isolamento efetivo e quota observada com origem/data/frescor |

Processo zero, declaração `DONE` e aceite são coisas diferentes. Tarefa de código exige diff atribuível ou justificativa verificável de ausência de mudança; tarefa de revisão pode entregar relatório/check sem patch. `simulated=true` nunca autoriza integração de produto. Quota desconhecida não recebe percentual inventado nem equivale a custo zero. Checkpoint descreve o estado de uma execução; memória adaptativa é persistência consentida entre sessões e possui escopo, retenção, revisão e revogação próprios.

Definir estados terminais do run (sucesso, falha, cancelamento) e estados de espera/revisão, além das transições já propostas para processo/tarefa. Cancelamento e crash não devem deixar tarefa eternamente `running`. Uma tentativa rejeitada permanece auditável.

### 3.4. Superfícies públicas propostas

Preservar `/v1/chat/completions` para inferência: uma chamada de chat não deve iniciar alteração de repositório por default. A migração dos modelos `hydra-swarm`/flags existentes precisa de erro ou aviso explícito, sem trocar silenciosamente sua semântica.

Planejar `/v1/control-plane/projects`, `/runs`, `/runs/{id}`, `/runs/{id}/events`, `/runs/{id}/tasks` e `/runs/{id}/artifacts`; comandos de cancelamento, repetição, revisão e integração devem validar estado e idempotência. São rotas propostas, não presentes no checkout. A CLI terá operações equivalentes, com IDs, saída JSON opcional e código de saída que reflita o resultado.

Eventos próprios do control plane usam SSE com cursor/reconexão. O stream de chat preserva ID/created/model por resposta, `finish_reason` e erros estruturados. `tool_calls`, mensagens de ferramenta e parâmetros não suportados exigem suporte comprovado ou rejeição clara; aceitar um campo e ignorá-lo não basta para anunciar compatibilidade com agentes SWE.

## 4. Preconditions — condições para cada implementação

1. Ler governança, contexto e spec do incremento; conferir/sincronizar Git conforme `AGENTS.md`.
2. Ter contrato com exemplos, dono de arquivos, dependências e critério de aceite antes de codificar o incremento.
3. Obter baseline dos testes em ambiente preparado, sem instalar dependências como efeito colateral de revisão documental.
4. Usar repositórios temporários nos testes Git; nunca usar este checkout como fixture de swarm/merge/limpeza.
5. Nenhuma execução externa é necessária para aceitar testes offline. Certificação real de provedor tem configuração e evidência separadas.

## 5. Postconditions — sequência de specs e entregas

Cada linha exige spec revisável e uma entrega pequena, testada, antes da etapa dependente. Arquivos abaixo são destinos planejados em `doc/b_spc/`; não estão sendo criados como specs vazias nesta tarefa. Toda spec seguirá DBC-9: propósito, justificativa, contrato, pré/pós-condições, invariantes, falhas, procedimento e exemplos.

| Etapa / spec planejada | Depende | Entrega e módulos principais | Gate objetivo de aceite |
| --- | --- | --- | --- |
| S00 — alinhamento no PRD e neste plano | — | Reconciliar visão, subset de compatibilidade, caminhos, licença pendente e matriz de capacidades. Separar metas de comportamento atual | Documentos não afirmam execução, recuperação ou suporte externo sem evidência; todos os exemplos locais têm destino coerente |
| S01 — `configuracao_runtime.md` | S00 | Schema único, validação de modos/URLs/limites, resolução alias → modelo/provedor/executor; política de gateway disabled/optional/required; migrador explícito. `config.py`, YAML, `.gitignore` | Config inválida falha antes de qualquer processo; modo direto funciona com gateway desligado; required indisponível falha; segredo ausente é erro claro; relay escolhe provedor elegível em teste |
| S02 — [contrato_execucao.md](../b_spc/contrato_execucao.md) | S01 | Models tipados em `prd_tecnico.md` (§3.4), estados, erros, capabilities, orçamento e exemplos JSON; `model.py` ou módulo singular dedicado | IDs/dependências/limites inválidos rejeitados; transições ilegais impedidas; zero do processo não promove aceite; fake não integra |
| S03 — [persistencia_execucao.md](../b_spc/persistencia_execucao.md) | S02 | Um armazenamento SQLite, migração versionada, eventos, referências/hash de artefato, idempotência e reconciliação pós-crash; core/checkpointer e engine/checkpointer | Estado+evento gravados em transação; replay ordenado; duas submissões idênticas não duplicam run; tentativa interrompida é reconciliada; banco legado preservado |
| S04 — [executor_cli.md](../b_spc/executor_cli.md) | S02, S03 | Runner com `argv` por driver, stdin quando suportado, cwd real, env filtrado, timeout/cancelamento e artefatos; sem fallback de sucesso | Fake subprocesso altera arquivo na fixture e produz diff/check; CLI ausente, erro, saída vazia, timeout e cancelamento têm estados corretos; nenhum descendente continua após término confirmado |
| S05 — `integracao_git.md` | S04 | Serviço Git único, SHA base fixo, worktree real, ownership, checks antes e depois da combinação, integração serializada e retenção em falha | Conflito/check falho/arquivo fora do escopo bloqueiam integração; caller não troca de branch; mudanças do usuário ficam intactas; remoção nunca perde diff não preservado |
| M1 — execução verificável local | S01–S05 | CLI/API chamam o mesmo serviço para uma tarefa e devolvem resultado revisável. Drivers reais são certificados individualmente | Executar cenário offline completo e um cenário real do driver escolhido antes de anunciá-lo operacional; falha não é resposta de sucesso; gateway não é requisito |
| S06 — `planejamento_swarm.md` | M1 | Plano explícito primeiro, DAG validado, contrato com hash e scheduler limitado; consolidar core/swarm e engine/swarm | Ciclo/ID inexistente/ownership incompatível rejeitados antes de spawn; dependente aguarda requisito aceito; concorrência respeita limite; falha parcial preserva trabalho e bloqueia só dependentes |
| S07 — `retomada_handoff.md` | M1; S06 para múltiplas tarefas | Separar failover de inferência de relay de tarefas. Checkpoint de efeitos, retomada persistente cancelável, orçamento e bloqueio de duplicação | Interromper/reiniciar fixture com efeito de ferramenta não o repete; manter instruções e estado Git; orçamento encerra espera/retries; troca de provedor não presume memória compartilhada |
| S08 — `gateway_quota.md` | S01, S02, S03 | OmniRoute opcional, clientes HTTP simuláveis, quota unknown/stale/observed, resolução de modelos e limites reais do protocolo | Offline nunca fabrica tokens/cota; 429/Retry-After/autenticação/conexão têm tratamentos distintos; rota escolhida e origem/frescor da quota são auditáveis |
| S09 — `validacao_reparo.md` | S05, S07 | Healing como nova tentativa delimitada, patch real, validação e budget; `engine/healer.py` | Falha induzida só vira reparada após diff aplicado e checks aprovados; esgotamento termina com falha e conserva artefatos |
| S10 — `api_control_plane.md` | M1, S03; leituras avançadas dependem de S06–S08 | Runs, tarefas, diffs, eventos e comandos; autorização local, CORS por origem, paginação, idempotência e códigos de erro | Contratos HTTP contra serviço fake; replay com cursor sem perda/duplicação lógica; comandos em estado inválido recusados; acesso a artefato fora do run bloqueado |
| S11 — `interface_visual.md` | S10 | Cliente web fino para fila, execução, diff/check, revisão, cancelamento e recuperação de conexão | Mostra estado persistido, inclusive unknown/simulated; reconecta pelo cursor; revisão envia comando versionado e não infere aceite pelo texto |
| S12 — `transporte_remoto.md` | M1, S08, S10 | Consolidar SSH; certificar alvo/host/health real; IDE/CDP opcionais e capabilities limitadas | SSH não altera confiança do host silenciosamente; alvo CDP incorreto falha; sessão concorrente não mistura saídas; testes reais separados dos mocks |
| S13 — `entrega_operacao.md` | M1; requisitos das capacidades publicadas | CI offline, compatibilidade Python/SO declarada, instalação, runbook, retenção/exportação e recuperação | Instalação limpa e CLI/API documentadas; CI não exige contas/localhost; matriz de drivers certificados acompanha versão; política de descarte verificável |

Ordem crítica: S00 → S01 → S02 → S03 → S04 → S05 → M1. Depois, S06 e S07 ampliam execução; S08 habilita roteamento informado; S10 precede UI. S09 e S12 só entram com seus gates. S13 começa pelo CI na primeira entrega e amadurece com cada capacidade. Não transformar essas etapas em promessa de quatro sprints: duração depende da certificação do primeiro executor e das falhas encontradas.

### 5.1. Slices de produto e dependências

Os slices abaixo organizam a visão de produto sem converter documentação em prova de implementação:

| Slice | Escopo | Base e limite |
| --- | --- | --- |
| V0 — núcleo verificável | Projeto local, tarefa delimitada, executor CLI, worktree, diff, checks, revisão e integração | S00–S05/M1; RF01–RF08. É o caminho crítico e não depende de UI rica ou OmniRouter |
| V1 — control plane visual | Read models de projetos, runs, tarefas, eventos, artefatos, diffs, revisão, cancelamento e reconexão por cursor | S10–S11; RF05–RF07, RF13, RF15. UI apenas consulta e envia comandos explícitos |
| V2 — workspaces e perfis | Áreas de trabalho, projetos, múltiplos repositórios e perfis agente/modelo/executor/skills/MCP/memória | Depende de autorização e contratos persistentes; RF16–RF17 |
| V3 — coordenação adaptativa | DAG, swarm, threads, retomada, roteamento, quota, custo e seleção adaptativa | S06–S09; RF09–RF12, RF18–RF20. Falhas e efeitos ambíguos continuam bloqueando aceite |
| V4 — memória e extensibilidade controladas | Memória consentida, discovery local, plugins, personalização avançada, acessibilidade e transportes certificados | Só após gate de segurança/proveniência/consentimento; RF21–RF25 |

Antes de V4, o gate deve comprovar autorização por área/projeto/repositório, consentimento para persistência, origem/hash/versão de itens descobertos, permissões mínimas, revogação e ausência de ativação automática de skills, MCPs, memórias ou plugins.

### 5.1. Primeira tarefa de desenvolvimento recomendada

Elaborar S01 e corrigir configuração/roteamento antes de conectar qualquer swarm à CLI. Escopo: `config.py`, `config.yaml`, `.gitignore`, testes de config e resolução no router. Aceite: aliases resolvidos, campos desconhecidos diagnosticados, runtime alinhado, gateway disabled/required testados e ausência de provedor devolvendo erro estruturado. Sem worktrees, conexão paga, CDP ou alterações de autenticação nesse incremento.

## 6. Invariants — garantias permanentes

- Uma fonte de verdade para estado de run; estado persistido precede a notificação externa.
- Executor recebe workspace operacional; citar caminho no prompt não equivale a acesso ou isolamento.
- Apenas coordenação integra; worker não publica, não delega recursivamente e não muda política do run.
- Worktree não é sandbox. Restrições efetivas de filesystem/rede dependem do executor e devem ser declaradas e verificadas, sem prometer contenção por texto do brief.
- Resultados rejeitados/falhos preservam evidências; limpeza tem precondições, alvo absoluto validado e política explícita.
- Contrato de tarefa é imutável por tentativa; alteração de fronteira/schema exige revisão e nova versão/hash.
- Orçamento limita tentativas, tempo, concorrência e custo quando mensurável. Valor desconhecido não vira estimativa inventada.
- Segredos não entram em eventos, prompts versionados ou artefatos publicados. API local não implica autorização irrestrita de browser/origem.
- Nenhum modo infere sucesso de quantidade de texto, `exit_code=0`, quota presumida ou nome do modelo.
- Discovery, memória e extensões exigem proveniência, autorização, consentimento quando aplicável e revogação auditável.
- Preferências inferidas não substituem instrução explícita sem opt-in; cada run mantém snapshot reprodutível das preferências efetivas.
- Acessibilidade inclui teclado, foco, labels, estados textuais, independência de cor, leitores de tela e redução de movimento; não é apenas uma opção visual.

## 7. Failure modes — riscos que a spec deve resolver

| Falha | Resposta exigida e teste |
| --- | --- |
| CLI ausente ou comando de driver incompatível | Tentativa não executada com causa explícita; testar driver por `argv` e disponibilidade, sem escolher outra conta silenciosamente |
| Timeout/cancelamento com processo filho vivo | Encerrar árvore com estratégia própria do SO e confirmar fim; capacidade não suportada bloqueia certificação desse SO |
| Processo morre após editar e antes de gravar resultado | Reconciliar SHA/diff e marcar tentativa interrompida; não repetir ferramenta automaticamente |
| Duas execuções tentam integrar no mesmo repo | Serializar integração e conferir SHA esperado; avanço da base exige nova validação |
| Worker altera arquivo proibido ou segue symlink externo | Bloquear aceite e reter evidência; proteção efetiva exige sandbox do executor, além da auditoria de diff |
| Conflito ou teste falha na integração | Parar na worktree de integração, preservar tentativas e não tocar branch do operador |
| Quota/reset indisponível | Estado unknown/stale; espera com limite e cancelamento; não pressupor janela universal de cinco horas |
| Stream cai após parcial ou costura altera indentação | Marcar incompleto, preservar bytes/offset, reconciliar antes de retransmitir; testes com linhas iguais, indentação diferente e corte no meio da linha |
| Cliente desconecta ou repete comando | Run durável independente do HTTP; idempotência e replay por cursor, sem spawn duplicado |
| Disco cheio/banco bloqueado/artefato ausente | Falha observável; não anunciar conclusão sem persistência; reconciliar artefato por hash e registrar recuperação |
| Discovery encontra recurso não confiável, conflitante ou fora da raiz autorizada | Não ativar; exibir origem/hash/capabilities e exigir aprovação explícita; testar traversal, conflito de versão e revogação |
| Memória contém segredo, PII ou preferência conflitante | Bloquear redação automática sem revisão; preservar auditoria, permitir correção/remoção e impedir vazamento entre escopos |
| Sessão/thread perde conexão ou evento | Persistir sequência, reconciliar por cursor e deduplicar; não declarar conclusão por desconexão |
| Extensão incompatível ou revogada | Impedir inicialização e novos efeitos; preservar evidência e permitir rollback para versão anterior |

## 8. How — execução e evidência

Para cada spec: registrar requisitos identificáveis, contrato, exemplos, caminho de migração, cenários negativos, arquivos de implementação e testes que comprovam cada aceite. Entregar diffs pequenos e revisar a integração antes de remover compatibilidade. Atualizar catálogo/manual na mesma entrega. Não criar todas as specs vazias nem reescrever todos os módulos de uma vez.

Validação por camada:

1. **Unidade:** validação de config/model, estados, aliases, orçamento e algoritmo de overlap que preserve bytes/indentação.
2. **Processo:** fake executado como subprocesso real, sem LLM, cobrindo escrita, stderr, código não zero, timeout, cancelamento e descendentes.
3. **Git:** repositório temporário com SHA conhecido, mudança staged/unstaged/untracked do operador, branches, conflito e retenção; nunca usar `main` deste checkout como alvo de teste.
4. **Persistência:** restart, sequência concorrente de eventos, transação, idempotência e migração de banco legado.
5. **HTTP:** transportes mockados para gateway/API/SSH health; SSE com ID estável, finalização/erro e replay.
6. **Certificação externa:** por driver/provedor/versão/SO, com artefato e resultado explicitamente real; não faz parte do gate offline e não se deduz de mock aprovado.

### 8.1. Evidência desta revisão

- Checkout inicialmente limpo em `main`, upstream `origin/main`; `git pull --ff-only` confirmou atualização após executar com permissão para escrever metadados Git.
- Leitura dos 58 arquivos versionados e dos dois documentos obrigatórios antes das decisões arquiteturais.
- Encontradas 18 funções de teste nos seis arquivos da suíte. Isso é inventário estático, não contagem de testes aprovados.
- `python -m pytest tests -q` foi tentado e não iniciou a suíte: o Python disponível retornou `No module named pytest`. Não existe `.venv` neste checkout; nenhuma dependência foi instalada.
- Análise sintática com `ast.parse` aprovada nos 34 arquivos Python versionados, sem executar imports. `git diff --check` sem erros. Dos 17 links locais nos documentos alterados/novo, 16 têm destino existente; a única ausência é `README.md → LICENSE`, preexistente e registrada em A17. Nenhum link novo aponta para arquivo ausente.
- Nenhuma CLI de agente, conta, modelo pago, túnel SSH ou automação CDP foi executada. As alegações de suporte externo no PRD não foram verificadas na internet nesta revisão do checkout e precisam de certificação antes de publicação como suporte real.

O registro de conclusão da tarefa deve informar separadamente os checks documentais executados, o commit e o resultado do push. Análise sintática Python, se executada, não substitui pytest nem prova comportamento.

### 8.2. Decisões pendentes e hipótese de trabalho

| Decisão | Hipótese para avançar | Quando resolver |
| --- | --- | --- |
| Primeiro executor real | Um driver CLI selecionado por configuração; fake como fixture da infraestrutura | S04, após inventário de CLI/autenticação sem expor credenciais |
| Sistemas operacionais certificados | Windows é o ambiente observado; não anunciar cancelamento portátil sem teste em cada SO | S04/S13 |
| Política de integração automática | Preparar branch/diff revisável; publicação precisa de política explícita do run | S02/S05 |
| Persistência legada | Um banco novo versionado com importação explícita, backups e ausência de descarte automático | S03 |
| Stack da UI | Cliente web separado; framework ainda aberto | S11, sem bloquear backend |
| Limites de desempenho | Instrumentar tempos e volume antes de assumir metas de latência/concurrency | S06/S08 |
| Licença e suporte externo | README declara MIT, mas não há `LICENSE`; rotas/modelos/assinaturas são exemplos não certificados | S00/S13, com decisão do titular e fontes oficiais na certificação |

## 9. Examples — cenários de aceite do produto

**Execução local:** operador fornece objetivo “alterar função X e validar teste Y”, repo e SHA base. Hydra cria run/tarefa/tentativa, prepara worktree, executa fake/driver certificado com cwd, captura diff, executa Y e devolve `ready_for_review`. Revisão aceita o resultado; integração separada valida combinação. O checkout original permanece na branch de entrada.

**Falha segura:** CLI termina com zero, mas só escreve uma explicação sem alterar a função. O resultado preserva stdout; o critério de aceite falha. Não há merge, limpeza destrutiva nem anúncio de tarefa aceita.

**Retomada:** worker altera um arquivo e atinge limite. A tentativa é encerrada ou reconciliada antes da seguinte; checkpoint referencia diff e ferramentas já executadas. Novo provedor recebe instruções e pendência, sem repetir a alteração concluída. O teste de restart verifica os efeitos no repo, além do texto produzido.

**Gateway desligado:** configuração direta permite executor local sem chamar OmniRoute. Consulta de quota mostra indisponível/desconhecida. Se gateway for obrigatório e cair, a execução termina ou aguarda conforme política limitada, preservando resultado parcial.
