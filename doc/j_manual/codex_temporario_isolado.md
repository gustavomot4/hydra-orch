# Temporários dos agentes Codex via OmniRoute

Em 15/11/2026, a gravação de uma geração institucional revelou que os workers
Codex no Windows podiam passar o limite de 300 segundos antes de criar arquivos.
O problema também apareceu em um teste local com protocolo Responses controlado,
sem inferência externa: uma chamada de shell recebida pelo CLI não avançava em
`workspace-write`, enquanto a mesma chamada terminava em `read-only`.

## Causa e correção

O adaptador cria um `CODEX_HOME` para cada agente. Esses ambientes herdavam
`TEMP` e `TMP` da máquina. O sandbox Windows cria identificadores de acesso novos
para cada ambiente e prepara as permissões das raízes temporárias graváveis.
O arquivo `cap_sid` do teste confirmou que a raiz preparada era o diretório
temporário geral do usuário. Essa árvore compartilhada pode ser grande; o custo
era repetido por worker e não tinha relação com a complexidade do comando.

`ConversationRunner.invocation` passa agora `TEMP`, `TMP` e `TMPDIR` apontando
para `<estado do agente>/tmp`, criado antes de iniciar o CLI. O caminho é absoluto,
distinto entre agentes e mantido na continuação da mesma sessão. Links simbólicos
ou arquivos no lugar desse diretório são recusados. O sandbox e a política de
aprovação escolhidos continuam sendo passados ao CLI.

Nesse perfil restrito de ferramentas do OmniRoute, `features.plugins=false`
também evita o download automático de marketplaces em cada `CODEX_HOME` novo.
Esses downloads produziram erros `Filename too long` nos diretórios profundos dos
workers. A configuração do Codex pessoal e os combos do OmniRoute não são alterados.

## Evidência e limites

Após a correção, o teste controlado com o CLI instalado, shell nativo e modo
`workspace-write` concluiu em 9,672 segundos; antes, atingia o corte de 45 segundos
sem concluir a primeira ferramenta. Essa reprodução isola a inicialização e a
execução local. Ela não é uma certificação de modelo externo, uma medição de
qualidade do modelo nem prova de geração de site por swarm.

Os testes em `tests/test_conversation_agent_temp.py` verificam isolamento entre
workers, continuidade, preservação das variáveis após o segundo filtro do
coordenador e recusa de redirecionamentos do diretório temporário. Execute:

```powershell
python -m pytest tests/test_conversation_agent_temp.py tests/test_conversation_route.py tests/test_conversation_coordinator.py tests/test_worker_runner.py -q
```

Uma chamada ao provedor ainda pode variar por latência, cota, fallback ou conteúdo.
O isolamento temporário não transforma uma tarefa expirada em resultado aceito.
Novos processos do backend carregam o adaptador atualizado;
um backend que já estava rodando precisa ser reiniciado.

## Orçamento e diagnóstico dos workers

A geração real posterior criou HTML, JS e CSS e passou nos testes de HTML/JS,
mas o worker HTML atingiu o corte fixo de 300 segundos durante suas verificações
adicionais, antes de encerrar a resposta. O coordenador ignorava
`execution.timeout_seconds` do `config.yaml`. Agora o servidor passa essa
configuração até o `TaskSpec` de cada worker. O arquivo de configuração deste
projeto usa 600 segundos por worker; permanecem os limites de 900 segundos da
fase de execução e 1200 segundos da coordenação completa. Verificações e revisão
continuam obrigatórias antes da consolidação.

Em caso de timeout, a mensagem identifica a etapa do worker e seu limite real.
O `WorkerRunner` mantém a leitura de stdout/stderr durante o encerramento da árvore
de processos e salva a saída já produzida nos artefatos, em vez de descartá-la
quando o temporizador cancela a espera. Um timeout continua sendo uma falha,
com os resultados preservados e sem integração automática.
