# Conversa executável

## Contrato implementado

Novo chat envia uma mensagem para uma conversa durável, independente do ciclo de vida dos runs antigos. O backend confirma a persistência com HTTP 202 e executa o turno em segundo plano. Codex e Claude Code usam suas CLIs locais, com a autenticação existente. O frontend mantém a identidade do envio, inclusive após perda da confirmação HTTP.

| Operação | Rota | Resultado |
| --- | --- | --- |
| Descobrir agentes | `GET /v1/control-plane/conversation-agents` | Instalação e estado de login, sem credenciais. |
| Criar e enviar | `POST /v1/control-plane/conversations` | `conversation_id`, `created`. |
| Listar histórico | `GET /v1/control-plane/conversations?limit=10&offset=0` | `items`, `total`. Filtro opcional `project_id`. |
| Recuperar estado | `GET /v1/control-plane/conversations/{id}` | Mensagens, respostas parciais, estados, ferramentas e diffs. |
| Continuar | `POST /v1/control-plane/conversations/{id}/messages` | `turn_id`, `seq`. |
| Interromper | `POST /v1/control-plane/conversations/{id}/turns/{turn_id}/cancel` | Estado confirmado ou `stopping`, observado pelo consumidor que possui o processo. |
| Acompanhar | `GET /v1/control-plane/conversations/{id}/events` | SSE autenticado, replay por `Last-Event-ID` ou `after`. |

O envio inicial exige `project_id`, `executor` (`codex` ou `claude`), `content` e `idempotency_key`. `access_mode` começa em `read-only`; `workspace-write` é opt-in. A continuação exige `content`, `idempotency_key` e `expected_last_seq`. Anexos usam `draft_session_id` e `attachment_ids`, com até dez referências prontas do projeto/conversa correspondente. A autenticação HTTP e a política CORS existentes se aplicam a todas as rotas.

## Consistência e recuperação

`0004_conversation.sql` acrescenta conversas, turnos, eventos e comandos. Preserva as tabelas antigas e vincula cada sessão anterior a uma conversa, importando mensagens como histórico concluído; a migração não dispara agentes. O backup consistente e o controle de checksum existentes continuam obrigatórios. O rollback recusa remover qualquer conversa, inclusive histórico importado.

A mensagem, o turno enfileirado e o evento são gravados na mesma transação SQLite. Dois consumidores concorrentes não conseguem reservar o mesmo turno; apenas um turno fica ativo por conversa. A fila mantém a ordem e permite até dez mensagens pendentes. Saída do agente não invalida um envio em preparação; uma mensagem nova de outra janela causa conflito de sequência, preservando o rascunho.

A posse dura 60 segundos e é renovada durante a execução. Turnos com posse expirada não são reenviados automaticamente. Um PID ainda vivo mantém a conversa em interrupção até confirmar seu encerramento; o reconciliador não mata um PID potencialmente reutilizado. O processo só recebe o prompt depois de persistir seu PID. Encerramento normal do servidor e Parar usam o cancelamento de árvore compartilhado com WorkerRunner. Um limite de 30 minutos encerra a invocação da CLI.

## Contexto e arquivos

Uma worktree Git por conversa é mantida entre turnos e parte do HEAD do projeto ao iniciar a conversa. Alterações locais não commitadas no checkout original não são copiadas. Pastas sem Git usam cópias de base/trabalho, sem inicializar repositório, com exclusão de caches, links e `.env*`, até 10 mil arquivos ou 256 MB. O caminho e a base ficam persistidos. A conversa em leitura continua isolada do checkout original.

O primeiro turno utiliza o histórico persistido. `thread.started` do Codex e `system/init` do Claude confirmam a identidade nativa, usada por `exec resume` / `--resume` somente em turnos consecutivos com configuração compatível. A mudança A→B→A abre um segmento novo em A para incorporar B. O pacote inicial tem orçamento de 56 mil caracteres; o histórico completo permanece em arquivos por turno e índice com hashes em `.orchestrator/chat_context/`, consultáveis por leitura. Mensagens pendentes canceladas não entram nesse histórico.

Anexos são validados pelo serviço existente e copiados para o escopo durável da conversa na confirmação. O executor recebe os caminhos das cópias verificadas, dentro da worktree. Falha mantém o rascunho. Diffs de arquivos rastreados e arquivos novos de até 100 KB são persistidos, com limite total de 200 mil caracteres, para consulta em Revisar alterações. As cópias operacionais dos anexos ficam fora do diff apresentado. Arquivos binários e conteúdo acima desses limites exigem inspeção na worktree preservada.

Uma resposta textual pode concluir sem patch. Exibir um diff significa alterações para revisão; não representa testes aprovados, integração, commit ou push do projeto atendido pelo agente. O serviço de conversa não aplica automaticamente essas alterações ao checkout original.

## Protocolos e limites desta entrega

- Codex: JSONL, texto por item de mensagem concluído, atividade de ferramentas e retomada nativa. Isso permite resposta progressiva por mensagem do agente; o protocolo usado não entrega cada token do modelo. O executável desktop recebe `--no-daemon` quando declara suporte. CWD e sandbox são explícitos.
- Claude Code: stream-json, deltas de texto, inicialização e resultado. Permissões são restritas aos recursos expostos; MCP externo fica desabilitado neste adaptador. Operações negadas aparecem na atividade, sem aprovação automática.
- Confirmado nesta máquina: Codex `0.169.0-alpha.11.1`, autenticado via ChatGPT, leu um README e respondeu a dois pedidos encadeados pelo serviço. Claude Code `2.1.222` instalado, sem login; o parser foi validado com subprocesso controlado. A validação real de Claude permanece pendente de login.
- Navegador: jornada com FastAPI e subprocesso controlado, duas mensagens, recarga durante execução, retorno pelo histórico, cancelamento e verificações de layout/axe. A prova autenticada do Codex foi feita pelo serviço, separada da prova de navegador.
- Verificador completo do kit sobre bundle de produção: Novo chat com zero falhas e três avisos; conversa com zero falhas e dois avisos. Os avisos registram áreas de toque da navegação entre 24 e 44 px, a fonte existente e a posição inicial de Tab após foco programático. Leitor de tela real e testes com pessoas não foram executados.
- Aprovações interativas de ferramentas e aplicação automática ao projeto original continuam fora do fluxo. A distribuição pelo coordenador é opt-in e tem o contrato abaixo; escolher um agente por si só mantém a execução individual.
- O [executável Windows](../j_manual/iniciar_windows.md) serve a interface e a API na mesma origem e gerencia a credencial local. O modo manual continua protegido por Bearer; o bootstrap automático é restrito ao modo desktop e à origem local correspondente.

Implementação: [ConversationService](../../src/hydra_orch/core/conversation_service.py), [ConversationRunner](../../src/hydra_orch/bridge/conversation_runner.py), [ConversationPage](../../frontend/src/feature/chat/ConversationPage.tsx). Testes: [contratos e recuperação](../../tests/test_conversation.py), [jornada no navegador](../../frontend/tests/e2e/m5_acceptance.spec.ts).

## Seleção por envio e conexão OmniRoute

As migrações aditivas `0005` e `0006` preservam o histórico, iniciam conversas antigas como diretas/individuais e recusam rollback destrutivo com dados dependentes. A conversa mantém a seleção atual; cada turno guarda rota, revisão, modo de trabalho e opção de roteamento automático. Um envio na fila nunca assume uma escolha posterior.

`PATCH /conversations/{id}/route` exige `route`, `expected_revision` e `idempotency_key`. Aceita também `execution_mode` (`single`/`swarm`) e `auto_route`. Não dispara agentes. A continuação envia `expected_route_revision`; revisão ausente só é aceita no modo direto legado sem alvo explícito. Conflitos preservam o rascunho. Mudanças de agente, conexão ou alvo conservam a mesma conversa e diretório.

`route` contém `executor` (`codex`/`claude`), `connection_mode` (`direct`/`omniroute`), `target_kind` (`model`/`combo`) e `target_ref`. A validação acrescenta fingerprint da definição relevante e versão da CLI. O Hydra revalida esse fingerprint antes da execução; o OmniRoute não oferece aqui uma revisão congelada durante uma chamada. Modelo efetivo e uso só aparecem quando reportados pelo protocolo.

O catálogo `GET /omniroute/combos` devolve nomes/identidades sanitizados e compatibilidade por agente. Não altera combos nem envia inferência. Combos aninhados são resolvidos; ciclos, destinos auxiliares ou desconhecidos e estratégias não suportadas ficam bloqueados. Claude permite testar também combos mistos pela tradução do gateway, com indicação de ausência de suporte oficial da Anthropic para destinos não-Claude. `POST /conversation-routes/verify` é um teste explícito que pode consumir provedor: leitura de fato desconhecido, edição e continuidade nativa. A certificação vale para definição/CLI/perfil testados e não prova todos os fallbacks possíveis. Falha mantém o alvo bloqueado, sem conexão direta substituta.

`GET/PUT /conversation-routes/connection` persiste somente endereço e habilitação, com versão esperada/idempotência. Credencial vem do ambiente do backend, nunca do snapshot, argumento ou SQLite. No Codex por gateway, um transporte local autenticado adapta exclusivamente ferramentas de função; texto com aparência de ferramenta não é executado. A configuração da CLI é privada por execução e não sobrescreve configurações globais.

## Coordenação opt-in dentro da conversa

Em **Opções da conversa → Coordenar tarefas com agentes**, a leitura inicial distingue análise de implementação. Para explicar o sistema, avaliar o repositório ou propor melhorias sem implementar, o modelo pode retornar `intent: analysis`, um relatório em Markdown e nenhuma tarefa. A resposta é devolvida à conversa sem criar execução, worktrees de workers, checks ou commits, mesmo quando a conversa permite escrita. A escolha vem da resposta estruturada do modelo, não de uma regra por palavras-chave. O contrato rejeita relatório misturado com tarefas executáveis.

Quando o pedido autoriza implementação, o planejador usa leitura dos arquivos para propor de uma a quatro tarefas específicas, com propriedade exclusiva de arquivos e verificações de uma lista conhecida. O plano JSON passa por validação antes de qualquer worker. Não há quatro frentes fixas, comandos livres de verificação ou DAG arbitrário. São aceitas tarefas independentes ou uma fundação verificada seguida de tarefas independentes, até dois workers simultâneos.

Quando há plano de implementação, o modo de leitura devolve esse plano e não executa edições. Em escrita, o coordenador prepara automaticamente o isolamento necessário, inclusive em pastas comuns e em planos de uma única tarefa. Quando falta Git, o Hydra inicializa um repositório privado na cópia da conversa, registra uma base local (mesmo vazia) e usa worktrees para os workers. Os metadados ficam fora de `work`, em um caminho compacto de `folder_git/` dentro do runtime. A pasta original e o repositório que contém o próprio Hydra não são inicializados, sincronizados nem publicados por essa preparação. Não há remoto configurado no repositório interno. Alterações anteriores da cópia são preservadas e registradas como base antes da distribuição.

Conversas antigas que falharam por falta de Git podem continuar na mesma cópia: o próximo pedido coordenado com escrita prepara o Git interno automaticamente, sem recriar a conversa ou reescrever as falhas históricas. Uma cópia já preparada reutiliza seu repositório sem reset. Marcadores ou diretórios redirecionados por links são recusados; `.env*`, caches, dependências e `.orchestrator/` não entram na base.

O planejador recebe até 16 mil caracteres de trechos iniciais de README, manifestos e pontos de entrada presentes, além do inventário. O pacote é parcial, não inclui credenciais nem links para fora da pasta, e documentos devem ser confrontados com código. O prompt restringe a etapa à leitura: não rodar testes, builds, instalação, escrita, Git de sincronização/publicação ou reparo de ambiente. Essa orientação não é um novo filtro de comandos; o sandbox e as permissões da CLI continuam sendo as barreiras de execução.

Os limites padrão permanecem: 180s por planejamento ou revisão estruturada, 900s na execução/consolidação e 1200s no total. Timeout interno não é apresentado como timeout total. Planejamento informa que nenhum worker foi iniciado; revisão e execução indicam quais registros e resultados podem existir. O evento `coordinator.diagnostic` registra etapa, job e orçamento em timeout estruturado. Históricos antigos não são reescritos para trocar mensagens já persistidas.

Workers usam `RunService`, subprocessos, worktrees próprias, fronteiras de arquivos, orçamento, verificações e artefatos canônicos. Um revisor de agente em leitura precisa aceitar o resultado estruturado. A política `agent_review_in_isolation` só permite essa revisão em cópia de conversa registrada; não representa aprovação humana. Fundação e consolidação final repetem as verificações. A consolidação só avança a cópia da conversa após conferir que ela não mudou durante o trabalho. Falhas preservam resultados e bloqueiam aplicação.

O roteamento automático é opt-in, conserva executor/conexão e considera apenas combos com prova vigente. O perfil é inferido do nome do combo e o desempate usa tempo observado no teste. Sem avaliação comparativa por tarefa, o sistema não afirma escolher o melhor LLM. A regra e o destino são mostrados em cada tarefa. Na ausência de candidato, a seleção explícita permanece.

Eventos `coordinator.plan`, `coordinator.task` e `coordinator.run` alimentam o progresso do mesmo chat e o vínculo para execução/verificações. Cancelamento interrompe a coordenação e suas árvores próprias; não encerra o daemon OmniRoute. Reinício não reenvia automaticamente operações incertas. Retomada automática de coordenação interrompida e reparo autônomo continuam fora desta versão; os resultados preservados permitem inspeção e novo pedido explícito.

Evidência: [testes de rota/contexto](../../tests/test_conversation_route.py) e [coordenação com processos reais controlados](../../tests/test_conversation_coordinator.py). Estes últimos comprovam mecanismos locais, sem certificar desempenho ou qualidade de provedores reais.

## Visualização espacial dos agentes

`/agentes?chat=<id>` acompanha o turno ativo ou o último turno de uma conversa; `/agentes?execucao=<id>` permite inspecionar uma execução existente. O botão **Ver agentes** preserva o vínculo com a conversa. O canvas e a lista leem snapshots das APIs atuais, sem disparar agentes, verificações ou provedores. As posições e o enquadramento ficam no navegador por trabalho e não alteram o plano persistido.

O modelo visual só acrescenta workers encontrados no plano ou na execução; linhas mostram plano, dependências, resultados e revisão registrados. `GET /runs/{id}` expõe também `current_attempt.result.review`, opcional e nulo quando ausente, com a decisão persistida. O detalhe consulta artefatos da tentativa encerrada para extrair mensagens de agente; saída de ferramentas não é convertida em resposta do assistente. Não há chat direto com worker, barramento novo entre agentes ou streaming de stdout do worker nesta entrega. A continuação permanece no chat canônico.

Implementação: [Área de trabalho](../../frontend/src/feature/canvas/AgentWorkspacePage.tsx), [adaptação dos registros](../../frontend/src/feature/canvas/canvasModel.ts) e [testes de interação e fidelidade](../../frontend/tests/agentCanvas.test.tsx). Jornada de uso: [manual Windows](../j_manual/iniciar_windows.md#acompanhar-agentes-na-área-de-trabalho).

### Atualização e subagentes observados

O canvas assina os streams autenticados de conversa e execução e invalida seus snapshots ao receber eventos, com agrupamento de 60ms e polling de 2,5s como recuperação. Reconexão preserva o último mapa e reapresenta o cursor; cancelamento da tela encerra suas conexões. A seleção e posições manuais não são descartadas quando novos cards chegam. O corpo do card aceita arrasto com limiar de 5px; um clique continua abrindo o detalhe e a alça conserva o movimento por teclado.

O adaptador de CLI normaliza `collab_tool_call` do Codex e tarefas `local_agent`/`remote_agent` explicitamente informadas pelo Claude em eventos duráveis `agent.observed`. O snapshot acrescenta `agents`, com identidade e turno, parentesco, título, estado, executor, modelo quando informado e último resumo observado. A UI filtra o turno atual e distingue a origem CLI. Texto dizendo que houve delegação, comandos Bash e tarefas ambientais não criam agentes. Encerrar a chamada de criação não equivale a concluir o filho.

Esse acompanhamento não habilita ferramentas novas, delegação nativa ou permissões adicionais. O modo de conexão e as restrições existentes continuam governando o que a CLI pode fazer. Execuções gerenciadas pelo coordenador mantêm seus próprios workers, verificações e revisão. Planos produzidos em leitura mostram **Planejado**, sem indicar execução. Histórico operacional de subagentes é limitado aos mil eventos mais recentes no snapshot; cada processo observa até 128 identidades. A ausência de evento, modelo ou saída é mostrada como ausência, sem inferir execução.

O chat passa a manter o compositor e a seleção de agente/modelo/combo na parte inferior da área útil, com diálogo de configuração para os próximos envios. O transcript tem rolagem própria; em altura até 480px volta ao fluxo completo. O renderizador Markdown existente é reutilizado, sem HTML executável, com hierarquia de títulos abaixo do título da conversa. A entrada de Novo chat usa busca de pastas, ações explícitas para adicionar e controles compactos junto do compositor. Contratos de idempotência, contexto e revisão da rota permanecem os mesmos.
