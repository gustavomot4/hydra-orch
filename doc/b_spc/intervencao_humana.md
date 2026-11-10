# T26 — Intervenção humana durável (RT27)

`HITLService` pausa o coordenador entre tentativas com solicitações needs_context
ou needs_approval. A solicitação fica em `commands(scope=hitl)` e seus eventos
hitl.requested/resolved no mesmo SQLite canônico. Uma run tem uma solicitação
pendente por vez; criação/resposta usam Idempotency-Key e revision.

Solicitar durante tentativa/processo ou despacho em andamento é recusado. A CLI
precisa encerrar preservando a worktree antes de pedir intervenção. O serviço não
finge suspender um processo ativo. Para tarefas ainda pendentes, o estado passa
a blocked; needs_context já existente é preservado. O motivo específico e deadline
ficam na solicitação; o run entra em waiting com reason=hitl.

Barreiras transacionais no store impedem run/task/attempt de entrar em running
enquanto há solicitação pendente, incluindo retry. A criação do pedido disputa
o mesmo writer lock com a admissão do despacho; se o despacho já iniciou, o
pedido é recusado. Resultados concluídos continuam no fluxo de revisão explícita.

Resposta aprovada move a solicitação para answered e retoma o coordenador;
responder não inicia outro worker. A próxima tentativa recebe respostas aplicáveis
em JSON no prompt. Repetição da mesma resposta não duplica eventos, transições ou
execuções. Worktrees, resultados e checks anteriores são preservados. Snapshots de
perfil podem ser fixados após aprovação de preparação, desde que nenhuma tentativa
ou despacho tenha começado. Mudança de perfil após iniciar continua bloqueada.

Negação ou expiração falha a run e a tarefa pendente/bloqueada associada, com
reason=hitl_denied/hitl_timeout. Cancelamento externo fecha a solicitação sem
ressuscitar o run. Deadlines são reconciliados em leitura/despacho e a cada segundo
durante o lifespan HTTP; o job é encerrado no shutdown. Após restart, a primeira
reconciliação expira pedidos vencidos. Pergunta, resposta e ator são sanitizados
antes de persistir. Não há execução automática de scripts vindos da resposta.

## API

Prefixo autenticado: `/v1/control-plane/runs/{run_id}/interventions`.

- POST: kind, question, task_id opcional, timeout_seconds (1–86400); Idempotency-Key.
- GET: listar; GET `/{request_id}`: inspecionar estado, revision e deadline.
- POST `/{request_id}/response`: response, actor, approved, expected_revision; Idempotency-Key.

O ator é um rótulo de auditoria do operador autenticado local, sem delegação de
permissões ou alegação de identidade multiusuário. Escopo cruzado retorna 403;
estado/revision/idempotência em conflito retorna 409. Eventos aparecem no stream
global do run para a futura UI; esta entrega não implementa a interface visual.
