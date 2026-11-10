# S15 — Sessões, observabilidade e modos de orquestração

## T14 — Sessões, threads e replay

`SessionService` persiste sessões por run e árvores de threads por sessão.
Os IDs são UUIDv7; pais devem pertencer à mesma sessão. Não há operação para
reatribuir um pai, de modo que a criação não introduz ciclos. As mutações de
estado e seus eventos são atômicos no ExecutionStore canônico.

Estados: created → running/cancelled; running e waiting podem alternar entre si
e terminar em completed/failed/cancelled. Estados terminais não reabrem. O comando
de transição exige expected_state, e mensagens exigem expected_last_seq. Concluir
uma sessão/thread com descendentes ativos é recusado; cancelamento/falha fecha
descendentes ativos atomicamente. Filhos criados que nunca iniciaram passam a
cancelled na falha do pai. Esses estados descrevem a conversa; encerramento
de processos de worker continua sendo responsabilidade de RunService.

`append_message` exige chave de idempotência de 16–64 caracteres e conteúdo
limitado a 100.000 caracteres. Mensagem, evento, cursor da thread e resposta do
comando são uma transação. Repetição com o mesmo payload retorna o mesmo seq;
payload diferente com a mesma chave retorna conflito. O conteúdo é sanitizado
antes do evento entrar no banco; isso não inicia inferência nem ferramentas.

Eventos incluem session_id/thread_id opcionais, validados contra a run e sessão.
M1 e fixtures com somente migração 0001 continuam compatíveis. IDs de outra
run/sessão são recusados; a superfície HTTP permanece no modo local de um
operador autenticado por Bearer, sem alegação de multi-tenancy por usuário.

### Superfície HTTP implementada

Prefixo: `/v1/control-plane/runs/{run_id}`.

| Método | Caminho | Operação |
|---|---|---|
| POST/GET | `/sessions` | Criar/listar sessões |
| GET | `/sessions/{session_id}` | Inspecionar sessão |
| POST | `/sessions/{session_id}/state` | Transição com state/expected_state |
| POST/GET | `/sessions/{session_id}/threads` | Criar/listar árvore de threads |
| POST | `/sessions/{session_id}/threads/{thread_id}/state` | Transição de thread |
| POST | `/sessions/{session_id}/threads/{thread_id}/messages` | Mensagem com Idempotency-Key e expected_last_seq |
| GET | `/events` | Replay por Last-Event-ID ou after_seq, filtros session_id/thread_id |

Falta de token retorna 401; escopo cruzado 403; ID inexistente 404; conflito de
estado/idempotência 409; prefixo de cursor não mais retido 410; validação 422.

### SSE e consumidor de referência

O seq é global por run; filtros de sessão/thread podem apresentar saltos legítimos.
Replay tem páginas de até 1.000 eventos e lê estado persistido, sem depender de
fila em memória. O modo padrão mantém o replay finito do M1, encerrando com
heartbeat. `follow=true` acompanha novas linhas do SQLite a cada 250 ms,
com heartbeat a cada 15 s e encerramento na desconexão do cliente.

Não há purga automática nesta entrega. Quando o prefixo confirmado do run tiver
sido removido por retenção externa, after_seq anterior ao prefixo é recusado.
O mapa de expiração M1 permanece compatível, mas a checagem de prefixo mínimo
também funciona após restart. Não remova o último evento/cursor de um run ativo.

`EventCursor` é um consumidor Python de referência para eventos entregues em
ordem: accept(event) serializa a atualização do cursor e recusa seq repetido ou
regressivo. O cliente deve persistir last_seq entre processos e reenviá-lo em
Last-Event-ID. Isso não implementa a futura UI nem promete exactly-once de efeitos
externos. Testes cobrem dedup concorrente, restart, mensagens idempotentes, escopo,
rollback, replay filtrado, SSE contínuo e desconexão sem serviço de rede externo.

## T15 — Métricas com proveniência

`MetricsService` grava MetricSample e evento metric.sampled atomicamente, validando
run e escopo (run/attempt/session/thread). Valores ausentes são NULL/unknown;
zero só é observed quando fornecido explicitamente ou medido. Unidades canônicas:
queue/duration em seconds, tokens_in/out em tokens, cost em USD. Valores negativos,
NaN, tokens fracionários, unidade incorreta, origem com credenciais ou timestamp
futuro são recusados. Não há estimativa de preço nem extração de uso por texto.

query retorna a última amostra por tipo; sem evidência, retorna unknown com origem
not_reported. TTL padrão de 300 s muda a apresentação observed para stale,
retendo valor/proveniência sem reescrever histórico. Empates de observed_at usam
ordem de inserção. aggregate_usage soma tentativas, inclusive retries; se faltar
uma parcela, o total é unknown e known_subtotal/contadores expõem a cobertura.
Sem amostras, subtotal também é NULL.

RunService registra duração a partir dos timestamps reais da tentativa e tokens/
custo como unknown enquanto a CLI não fornecer telemetria estruturada certificada.
created_at legado com precisão de segundos não comprova atraso de despacho:
queue permanece unknown nesse caso. O serviço também aceita medições explícitas
via record_batch/record_usage; não muda o resultado de execução com texto inferido.

GET /v1/control-plane/runs/{run_id}/metrics aceita scope/scope_id/max_age_seconds;
GET no sufixo /metrics/usage fornece agregações com cobertura. HTTP exige Bearer e
recusa escopo de outra run. Os testes cobrem zero explícito, ausência, staleness,
reinicialização, rollback do lote, fontes, limites e captura após subprocesso real.

## T16 — Seleção adaptativa auditável

`RouteSelector` valida candidatos explícitos contra certificado/capabilities/CLI,
modo de conexão e quota. disabled não chama gateway; optional aceita fallback
direto se o gateway falhar; required não permite bypass por rota direta. Quota
observed=0 recusa a rota. Quota unknown/stale segue a política explícita allow/reject,
sem converter ausência em disponibilidade observada.

Elegíveis são ordenados por prioridade declarada, custo e duração observados e
ID estável. Métricas só entram no ranking se a tentativa pertencer à mesma run,
modelo e executor. Unknown/stale não vira custo zero nem latência estimada. O
registro persiste candidatos, razões, fontes, timestamps, valores usados,
certificado, escolha e fallback; falha sem elegíveis emite route.rejected sem
inventar um selected_route. O read model autenticado está em
GET /v1/control-plane/runs/{run_id}/route-decisions.

OmniRouteClient normaliza o subset de quota (percentual numérico 0–100 e reset
não negativo), retorna unknown para respostas inválidas e stale para último valor
conhecido quando a conexão cai. Disabled não faz requests, inclusive geração.
O timestamp indica coleta do gateway; isso não certifica um protocolo externo
ou disponibilidade real da conta. Relatórios/HTTP de testes são simulados.

Selecionar uma rota não inicia execução. O coordenador T25 deve revalidar as
permissões e o certificado no despacho, usar a decisão/modelo na invocação e
registrar mudanças de rota; a auditoria não substitui prova de execução do worker.
