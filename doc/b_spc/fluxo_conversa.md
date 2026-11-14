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

Uma worktree Git por conversa é mantida entre turnos e parte do HEAD do projeto ao iniciar a conversa. Alterações locais não commitadas no checkout original não são copiadas. O caminho e a base ficam persistidos. A conversa em leitura continua isolada do checkout original.

O primeiro turno utiliza o histórico persistido. `thread.started` do Codex e `system/init` do Claude confirmam a identidade nativa, usada por `exec resume` / `--resume` nos próximos turnos. Histórico reconstruído tem limite explícito de 120 mil caracteres, sem truncamento silencioso. Mensagens pendentes canceladas não entram nesse histórico.

Anexos são validados pelo serviço existente e copiados para o escopo durável da conversa na confirmação. O executor recebe os caminhos das cópias verificadas, dentro da worktree. Falha mantém o rascunho. Diffs de arquivos rastreados e arquivos novos de até 100 KB são persistidos, com limite total de 200 mil caracteres, para consulta em Revisar alterações. As cópias operacionais dos anexos ficam fora do diff apresentado. Arquivos binários e conteúdo acima desses limites exigem inspeção na worktree preservada.

Uma resposta textual pode concluir sem patch. Exibir um diff significa alterações para revisão; não representa testes aprovados, integração, commit ou push do projeto atendido pelo agente. O serviço de conversa não integra automaticamente essas alterações.

## Protocolos e limites desta entrega

- Codex: JSONL, texto por item de mensagem concluído, atividade de ferramentas e retomada nativa. Isso permite resposta progressiva por mensagem do agente; o protocolo usado não entrega cada token do modelo. O executável desktop recebe `--no-daemon` quando declara suporte. CWD e sandbox são explícitos.
- Claude Code: stream-json, deltas de texto, inicialização e resultado. Permissões são restritas aos recursos expostos; MCP externo fica desabilitado neste adaptador. Operações negadas aparecem na atividade, sem aprovação automática.
- Confirmado nesta máquina: Codex `0.169.0-alpha.11.1`, autenticado via ChatGPT, leu um README e respondeu a dois pedidos encadeados pelo serviço. Claude Code `2.1.222` instalado, sem login; o parser foi validado com subprocesso controlado. A validação real de Claude permanece pendente de login.
- Navegador: jornada com FastAPI e subprocesso controlado, duas mensagens, recarga durante execução, retorno pelo histórico, cancelamento e verificações de layout/axe. A prova autenticada do Codex foi feita pelo serviço, separada da prova de navegador.
- Verificador completo do kit sobre bundle de produção: Novo chat com zero falhas e três avisos; conversa com zero falhas e dois avisos. Os avisos registram áreas de toque da navegação entre 24 e 44 px, a fonte existente e a posição inicial de Tab após foco programático. Leitor de tela real e testes com pessoas não foram executados.
- Aprovações interativas de ferramentas, integração/revisão decisória de patches e distribuição pelo coordenador com políticas de rota/orçamento continuam como expansão do fluxo. Os motores de orquestração existentes permanecem com seus contratos próprios; escolher um agente no chat não anuncia execução de swarm.

Implementação: [ConversationService](../../src/hydra_orch/core/conversation_service.py), [ConversationRunner](../../src/hydra_orch/bridge/conversation_runner.py), [ConversationPage](../../frontend/src/feature/chat/ConversationPage.tsx). Testes: [contratos e recuperação](../../tests/test_conversation.py), [jornada no navegador](../../frontend/tests/e2e/m5_acceptance.spec.ts).
