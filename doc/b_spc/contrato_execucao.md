# Contrato de execução — S02 / T02

## 1. Propósito

Formalizar os modelos de execução e suas transições em `hydra_orch.model`, preservando os modelos de chat. Base: [PRD técnico §3.4](prd_tecnico.md#34-contrato-canônico-de-execução-verificável), [plano](../a_context/plano_desenvolvimento.md) e [modelagem de classes](../e_class/diagrama_classe.md).

## 2. Justificativa

Sucesso de processo, resultado de engenharia e integração são decisões distintas. Os contratos permitem testar essas regras sem iniciar modelos, processos, Git ou SQLite.

## 3. Contrato

- `RunSpec`: versão `1.0`, IDs, objetivo, raiz absoluta do repositório, branch/SHA base, modo, orçamento, política `explicit_review`, chave de idempotência e tarefas.
- `TaskSpec`: versão, IDs, objetivo, executor atribuído, capabilities requeridas, checks, caminhos permitidos, dependências, hash de contrato opcional, timeout e limite de reparos.
- `CheckSpec`: `check_id`, comando como array de argumentos (`command`), cwd relativo opcional e descrição. Não é uma string de shell; T04/T06 executarão com `shell=False`.
- `TaskAttempt`: identidade e ordinal, executor/provedor/modelo, workspace, base Git, sessão, estado do processo, timestamps e causa de término. Tentativas encerradas não são reabertas; retry exige nova identidade e ordinal, sob controle do serviço futuro.
- `TaskResult`: identidade, tentativa, base Git, estados de processo/tarefa, código de saída, simulação, resumo, arquivos, commit/patch, checks, artefatos, falhas, revisão e revisão numérica.
- `Artifact` e `CheckResult`: referências relativas, hashes SHA-256, tamanho e vínculo ao run/tentativa; checks identificam comando, cwd, SHA testado, código de saída, duração e artefatos stdout/stderr.
- `ReviewDecision`: resultado, ator, decisão, motivo e `expected_revision`. `review_result` devolve novo snapshot; não modifica o original.
- `RunEvent`: sequência positiva, run e correlação, tipo, timestamp UTC e payload já redigido. Sequenciamento, append-only e redaction efetiva pertencem aos serviços de persistência/segurança; o nome do campo não prova sanitização.
- `HandoffCheckpoint`: objetivo, instruções, decisões, estado Git, referências de diff/checks, efeitos de ferramentas, saída parcial e próximo passo. Efeito `unknown` é preservado, não convertido em permissão de repetição.
- `ExecutorCapabilities`: declaração de capacidades; `require` recusa requisitos ausentes. Declaração não certifica driver, SO ou sandbox.
- `RunSpec`/`TaskSpec` e seus critérios são imutáveis (`frozen` e tuplas); campos extras são recusados. JSON usa arrays para as tuplas. Os envelopes são congelados, mas o payload JSON de `RunEvent` é um dicionário: T03 deve serializá-lo ao persistir, sem depender da identidade do objeto em memória. IDs são strings delimitadas; SHAs Git têm 40 ou 64 dígitos hexadecimais; hashes de artefatos têm 64. Timestamps exigem fuso e são normalizados para UTC.
- Caminhos operacionais relativos não aceitam drive, caminho absoluto ou `..`. Essa validação é lexical; autorização, symlinks, existência e contenção real serão verificadas em T05/T06.
- `RunSpec` recusa IDs duplicados, dependências desconhecidas, auto-dependência, ciclos e tarefas de outro run. Ownership concorrente e scheduler ficam para S06.

### Transições

`transition_status` valida apenas a aresta entre estados do mesmo domínio; não autoriza efeitos. Mesma origem/destino é recusada; idempotência de comandos será tratada pelo serviço.

| Domínio / origem | Destinos |
|---|---|
| Run queued | running, failed, cancelled |
| Run running | waiting, reviewing, failed, cancelled |
| Run waiting | running, failed, cancelled |
| Run reviewing | running, succeeded, failed, cancelled |
| Processo queued | running, cancelled, crashed |
| Processo running | exited, timed_out, cancelled, crashed |
| Tarefa pending | running, blocked, failed, cancelled |
| Tarefa running | needs_context, blocked, failed, ready_for_review, cancelled |
| Tarefa needs_context | running, blocked, failed, cancelled |
| Tarefa blocked | running, failed, cancelled |
| Tarefa ready_for_review | accepted, rejected, cancelled |
| Integração not_integrated | integrating, discarded |
| Integração integrating | integrated, conflicted, failed |
| Integração conflicted | integrating, discarded |
| Integração failed | discarded |

Demais estados são terminais dentro do snapshot/tentativa. `failed` na integração representa falha de check ou infraestrutura sem conflito Git; não equivale a `integrated`.

## 4. Pré-condições

Configuração T01 validada. Critérios de aceite e executor precisam estar declarados antes de iniciar a tentativa. Nenhuma alegação do executor promove automaticamente o resultado.

## 5. Pós-condições

`ready_for_review` exige processo encerrado com zero, resultado real, arquivos alterados, commit/artefato de patch e checks aprovados. `validate_result` confere atribuição entre tarefa/tentativa/resultado, cobertura dos checks exigidos e correspondência entre comandos, cwd e SHA. `review_result` exige revisão atual, ator/motivo e decisão explícita. `assert_integrable` só permite resultado aceito por revisão, real e consistente.

O primeiro contrato de aceite cobre tarefas de alteração de código; tarefas somente de análise/relatório terão critérios próprios em incremento posterior. Artefatos de run podem omitir `attempt_id`, mas evidências anexadas a `TaskResult` devem pertencer à tentativa correspondente.

## 6. Invariantes

Zero do processo nunca implica aceite; simulação nunca integra. Alterar IDs, checks, patch ou código de saída de um resultado revisado exige outro resultado/revisão. Os contratos validam metadados declarados; comprovar os bytes de um patch, executar checks e verificar hashes no disco continuam sendo gates de T04–T06. Aprovação/integrabilidade em memória não executa merge nem publicação.

## 7. Falhas

Schemas inválidos geram `ValidationError`; regras entre entidades geram `ContractViolation` com código estável. Transição ilegal gera `InvalidTransitionError`. Revisão antiga, identidade incompatível, check ausente/falho e evidência simulada bloqueiam aceite. Sem migração de banco nesta entrega; DTOs HTTP de submissão serão implementados em T07.

## 8. Procedimento e aceite

Validar specs → registrar tentativa → coletar resultado → conferir metadados contra specs → receber revisão explícita → validar elegibilidade de integração. Testes cobrem round-trip JSON, negativos de schema, imutabilidade, todas as combinações de estados, revisão e simulação. Gate: suíte offline e 100% de cobertura de linhas de `model.py`.

## 9. Exemplo

```json
{"schema_version":"1.0","task_id":"task-1","run_id":"run-1","objective":"Corrigir a função de soma","assigned_executor":"codex","acceptance_criteria":[{"check_id":"unit","command":["python","-m","pytest","tests/test_sum.py"]}],"allowed_paths":["src/sum.py","tests/test_sum.py"]}
```

O exemplo é validável com `TaskSpec.model_validate_json`. A tentativa encerrada com `exit_code=0` ainda precisa produzir evidência e passar pela revisão.

## Gaps e glossário

- **T03:** persistência/idempotência; **T04–T06:** processos, workspace e evidência real; **T07:** comandos autenticados e API.
- **Snapshot:** representação validada de um estado; specs não mudam durante uma tentativa.
- **Capability:** capacidade declarada do executor, distinta de certificação.
- **Revisão numérica:** controle otimista contra decisões sobre resultados desatualizados.
