# Checkup e diagnóstico da coordenação

O coordenador distingue `operation="validate"` de `operation="edit"` no plano estruturado. Validações executam checks pelo `CheckRunner`, sem iniciar um worker de código e sem produzir commits vazios. Edições continuam passando pelo contrato de patch atribuível do `RunService`, seguido de checks e revisão. A seleção do modo coordenado não autoriza publicação no repositório original.

Validações são independentes, executadas antes das edições. Uma falha bloqueia o início das edições e preserva os resultados das outras validações. Elas não podem ser fundação nem depender de uma tarefa de edição. Uma execução composta apenas de validações não anuncia um ID de execução de patches inexistente.

## Checks suportados

| Tipo | Execução e uso |
| --- | --- |
| `pytest` | `python -m pytest -q`; diretórios em validações são divididos em checks por arquivo. Cada arquivo tem seu timeout e sua evidência. |
| `python_compile` | Sintaxe de arquivos Python explícitos; não comprova comportamento. |
| `node_test` | Runner nativo `node --test`, para testes desse runner. |
| `typescript` | TypeScript local com `--noEmit -p <tsconfig>`; exige um projeto explícito. |
| `vitest` | Vitest local com `run`; para os testes React/Vite. |
| `eslint` | ESLint local, arquivos TS/TSX, sem avisos permitidos. |
| `frontend_build` | Checks separados de `tsc -b` e `vite build`. |
| `docs` | Links Markdown locais e whitespace do diff/commit; dispensa testes Python sem relação com a edição. |

Os caminhos de check são relativos a `check_cwd`. Para o frontend deste projeto, use `check_cwd="frontend"` e `check_paths=["tsconfig.json"]` no TypeScript. As dependências precisam estar disponíveis no diretório validado; o runner não instala pacotes automaticamente. Uma falha de dependências deve ser relatada como tal, sem ser promovida a validação aprovada.

## Evidência e falhas

Os eventos `coordinator.task` persistem comando, SHA testado, código de saída, duração, referências aos logs e trechos limitados/redigidos de stdout/stderr. O progresso é persistido após cada arquivo concluído, sem esperar o fim da suíte. Os arquivos completos ficam no runtime, sob `run/<id>/checks/<escopo>/`. Em timeout de check, a saída já emitida é preservada após encerrar a árvore do processo. O limite total padrão é de uma hora para acomodar checkups; leitura/planejamento e execução de workers mantêm seus limites próprios de 180 e 900 segundos. Cada worker/check mantém o timeout configurado. O limite total continua valendo: dividir arquivos não concede tempo ilimitado.

Uma validação pura guarda as referências nos eventos da conversa; não cria um resultado integrável de código nem um link para uma execução de patches inexistente. Em tarefas de edição, os checks e seus artefatos continuam acessíveis pela execução do `RunService`. A mensagem de erro inclui o check, código de saída e trecho da falha, em vez de só informar seu identificador.

Se o executável do agente não for localizado, a mensagem distingue esse fato de autenticação. Confira a instalação e o PATH herdado pelo backend; reinicie o Hydra se o PATH mudou. Esse diagnóstico não afirma que a conta está desconectada.

## Checkup local sem inferência

Execute `python -m pytest tests -q` fora de workers para conferir toda a suíte. Em máquinas com pouco recurso, divida pelos arquivos; mantenha `test_server.py`, `test_integration.py`, `test_m5_pty_matrix.py` e `test_omniroute_daemon.py` em blocos próprios. `test_omniroute_live.py` é opt-in e permanece ignorado sem configuração explícita.

Em `frontend/`, execute `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build` e `npm run test:e2e`. O Vitest limita jsdom a dois workers e permite até 15 segundos por teste dos fluxos com múltiplos passos, para acomodar disputa com o backend e o navegador no desktop. As asserções dos fluxos continuam obrigatórias, sem retries automáticos. O Playwright usa backend, contas e executores de teste isolados. Sucesso dessas suítes não certifica um provedor real.
