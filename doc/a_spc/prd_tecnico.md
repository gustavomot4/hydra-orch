# PRD técnico

Status: arquitetura alvo proposta, sem alegação de implementação. Complementa o [PRD funcional](prd_funcional.md), o [contrato](contrato_execucao.md) e o [plano](plano_desenvolvimento.md). Modelagem: [classes](diagrama_classe.md) e [MER](mer.md).

## 1. Propósito

Implementar execução verificável local com contratos tipados, estado durável, drivers explícitos, isolamento Git e integração validada, preservando o proxy de inferência.

## 2. Justificativa

Consolidar os caminhos duplicados de core/engine e remover sucesso fabricado. FastAPI/CLI são entradas do mesmo serviço de aplicação; engines definem estratégia; bridges executam transporte; adapters fornecem inferência. SQLite atende o primeiro operador local; não há necessidade atual de banco distribuído.

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

### Serviços e módulos

`core/run_service.py` (proposto) coordena run/revisão/cancelamento; `core/checkpointer.py` torna-se persistência canônica; `core/git_workspace.py` concentra Git. `engine/swarm.py` e `engine/relay.py` recebem serviços injetados; `engine/healer.py` cria tentativa de reparo real. `bridge/worker_runner.py` implementa a interface AgentExecutor por drivers. `bridge/ssh_tunnel.py` é o único gestor SSH. `core/router.py` permanece fachada de inferência.

Migrar os consumidores antes de remover `core/swarm.py`, `core/ssh_tunnel.py` e duplicação de `engine/checkpointer.py`; preservar imports temporariamente com wrappers e teste de compatibilidade. Não ligar a engine atual diretamente à API sem corrigir gates.

### Dados e estados

SQLite com foreign keys habilitadas em cada conexão, migração versionada, transações curtas e espera por lock limitada. Usar revisão inteira para concorrência otimista. Artefatos ficam no filesystem; gravar arquivo temporário, finalizar atomicamente e só então registrar referência. Após crash, reconciliar órfãos sem apagá-los automaticamente.

Run: `queued -> running -> waiting/reviewing -> running/succeeded/failed/cancelled`; cancelamento também pode partir de queued/running. `waiting` exige causa e limite. Task usa estados do contrato, acrescidos de `cancelled` para cancelamento explícito. Nova tentativa pode devolver failed/blocked/rejected a running por comando registrado; resultado anterior permanece imutável. Acceptance e integração são decisões distintas. Run só sucede com todas as tarefas obrigatórias aceitas e, quando solicitada, integração aprovada.

Persistência em `.orchestrator/checkpoints.sqlite`; artefatos em `.orchestrator/run/<run_id>/task/<task_id>/attempt/<attempt_id>/`; worktrees sob `.orchestrator/worktree/`. IDs são gerados pelo serviço, nunca caminhos fornecidos pelo cliente. Migração de `.hydra/` é explícita, com backup e preservação dos schemas legados.

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

### Segurança e limites

Bind local padrão; token local para comandos e leitura de evidência, CORS com allowlist. Não registrar tokens. Autorizar raiz do projeto e normalizar caminhos/symlinks. Worktree não constitui sandbox: capacidade de contenção depende do executor. Testes e comandos são entradas autorizadas do projeto, executados com limites; logs são redigidos antes de exposição. Cancelamento só é anunciado concluído após verificar árvore encerrada no SO certificado.

## 4. Pré-condições

Configuração validada, schema compatível, repo acessível, executor elegível e orçamento suficiente. Uma tarefa em execução possui no máximo uma tentativa ativa; recuperação deve reconciliar processo antigo antes de novo spawn.

## 5. Pós-condições

Resultado persistido com checks e referências de artefato; evento correlacionado; integração e limpeza têm resultado próprio. Falha de persistência impede anúncio de sucesso. Não há alterações silenciosas da branch ativa do operador.

## 6. Invariantes

Transação para estado/evento, exclusão mútua da integração, resultados imutáveis, tarefas dependentes no mesmo run, contrato fixado por hash e limites de tempo/tentativas. Métricas registram duração, filas e falhas sem inventar custo/token não informado.

## 7. Falhas e recuperação

Cobrir disco cheio, lock do banco, subprocesso órfão, arquivo fora do escopo, conflito, quota desconhecida e conexão perdida. Em efeito externo ambíguo, marcar blocked e exigir reconciliação. Não aplicar retry cego nem deduplicação textual como garantia de integridade de código.

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
| T08 CI e manual M1 | T07 | RF15 / RT12 | .github/workflows/ci.yml, doc/b_manual/README.md, pyproject.toml | Testes offline e instalação reproduzível; driver real com certificação separada |

Paths Python da tabela são relativos a `src/hydra_orch/`, exceto `tests/`, configuração e documentação. Arquivos ainda inexistentes são destinos propostos. T01–T07 concretizam S01–S05/M1; T08 inicia S13. Swarm, retomada e expansão seguem S06–S12 do plano e só recebem status concluído com seus gates. Validar no mínimo Python 3.10 e versão corrente escolhida no CI; SO anunciado precisa validar gestão de processos.

## 9. Exemplo técnico

POST de RunSpec com projeto, objetivo, base SHA e tarefa delimitada cria run queued e evento numa transação. Worker fake altera arquivo numa fixture; check registra SHA/exit code. Resultado vira ready_for_review. Review com revisão correta aceita; integração aplica em worktree própria e repete check. Mesma submissão não gera outro processo; review com revisão antiga retorna 409.
