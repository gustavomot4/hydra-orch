# CONTEXTO-ORQUESTRACAO — Contexto de Desenvolvimento e Investigação

**Identificador Formal:** `CONTEXTO-ORQUESTRACAO.md`
**Caminho Canônico:** `doc/a_context/CONTEXTO-ORQUESTRACAO.md`
**Versão:** `v01_00_0000`
**Status:** `REGISTRO HISTÓRICO / NORMATIVO DE ORIGEM`
**Autoridade:** Investigação de referência do Alethe, arquitetura de comunicação entre agentes e achados comparativos do scaffold do hydra-orch.
**Escopo:** Protocolos de orquestração de workers, gap analysis do scaffold inicial e diretrizes de evolução técnica.

---

Atualizado em 2026-11-05. Repositório principal: https://github.com/gustavomot4/hydra-orch.
Base examinada do Hydra: commit `1ee4073` (scaffold inicial).

## Objetivo e escopo

O Hydra pretende unificar provedores CLI, API, UI/CDP e modelos locais/remotos para engenharia de software nos modos swarm, relay e persistente. O PRD descreve o objetivo do produto; a presença de uma capacidade no README ou PRD não comprova sua implementação ou validação ponta a ponta.

O Alethe é uma referência de arquitetura e protocolo de workers. Esta investigação não copiou seu código nem implementou novos comportamentos no Hydra. As propostas abaixo permanecem pendentes de implementação e testes.

## Referência investigada

- Projeto: https://github.com/Kc1t/alethe-orchestrate-skill.
- Cópia local examinada: versão 24.0.0, declarada em `.codex-plugin/plugin.json`; não foi feita comparação com a versão remota atual.
- Código principal: `skills/alethe/scripts/orchestrate.py`.
- Contrato: `skills/alethe/schemas/plan.schema.json`.
- Orientações: `skills/alethe/SKILL.md`, `references/providers.md` e `references/briefs.md`.

### Como o Alethe coordena workers

1. O agente líder decompõe o trabalho, escolhe o playbook e prepara um plano JSON versionado.
2. O plano define tarefa, provedor, modelo/esforço, diretório, modo de acesso, timeout, isolamento e concorrência.
3. `build_invocation` converte o plano nos argumentos da CLI de cada provedor. Codex e Claude recebem o prompt por stdin; Agy e Kimi o recebem em argumento próprio.
4. `run_batch` usa `ThreadPoolExecutor` com `maxConcurrent`; `run_worker` inicia processos e acompanha seus resultados. Os processos dos agentes realizam o trabalho externo.
5. Cada worker registra `prompt.txt`, `stdout.log`, `stderr.log`, `result.md`, `outcome.json` e, quando aplicável, `diff.patch`.
6. O líder lê resultados compactos, verifica alterações, resolve bloqueios e prepara a próxima rodada. O fluxo estudado não fornece um barramento de mensagens direto entre workers.

O handoff tem linhas `STATUS:` e `SUMMARY:`; revisões também podem ter `VERDICT:`. Os estados de tarefa incluem `DONE`, `DONE_WITH_CONCERNS`, `BLOCKED` e `NEEDS_CONTEXT`. É necessário distinguir sucesso do processo, declaração do worker e aceitação após validação.

As decisões compartilhadas podem ficar em `STATE.md` ou arquivo de especificação, referenciado nos briefs seguintes. Não há compartilhamento automático de toda a memória das sessões.

Workers isolados recebem worktrees em HEAD destacado. A integração é responsabilidade do líder, após revisão. O runner procura desabilitar subagentes nativos de Codex/Claude quando as flags estão disponíveis e adiciona um contrato que proíbe delegação recursiva.

A retomada usa o identificador de sessão do próprio provedor. Esse identificador não transfere memória para outro provedor. Logs preservados também não equivalem a recuperação automática após queda.

### Evidência e limites da verificação

Seis testes existentes do Alethe passaram localmente, com agentes simulados:

- `RunnerTest.test_report_explains_what_each_wave_did_and_spent`;
- `GuardTest.test_handoff_status_and_denied_tools_reach_the_report`;
- `GuardTest.test_failures_are_classified_with_a_hint`;
- `InvocationTest.test_codex_resume_keeps_the_sandbox_and_effort`;
- `InvocationTest.test_claude_streams_and_cannot_start_agents`;
- `InvocationTest.test_handoff_lines_are_read_from_markdown`.

Esses testes validam comportamento local do runner e montagem de comandos, não integrações reais com contas, modelos ou serviços externos.

O MCP REA foi acionado em `capture_process_scenario`, mas retornou `capability_unavailable` / `unsupported_provider`: a captura PTY não suporta Windows nativo porque o adaptador ainda não verifica a limpeza dos processos descendentes. Não houve captura de execução nem Evidence REA de sucesso. Os achados vêm da leitura do código e dos testes executados pelo terminal comum.

## Estado observado no Hydra

| Área | Implementação examinada | Lacuna para o objetivo |
| --- | --- | --- |
| Provedores | `adapter/base.py` define disponibilidade e geração de texto em stream | Uma resposta textual não comprova execução de arquivos ou comandos no workspace |
| Bridge de IDE | `adapter/ide_bridge.py` chama `/health` e `/v1/chat/agent` | Depende de um servidor bridge externo; os arquivos examinados não demonstram sua implementação |
| Decomposição | `core/swarm.py` retorna quatro tarefas fixas, com descrições baseadas nos primeiros 120 caracteres do prompt | Planejamento adaptativo e dependências ainda precisam ser implementados |
| Worktrees | Há criação de branches/worktrees, merge e limpeza | O diretório é colocado no prompt; não é passado como contexto operacional de execução para `adapter.generate` |
| Execução swarm | `core/router.py` chama `adapter.generate` em paralelo e mede o tamanho da resposta | Não há aplicação explícita do texto gerado aos arquivos, captura de patch ou comprovação de commits das tarefas nesse fluxo |
| Resultados e falhas | `asyncio.gather(..., return_exceptions=True)` coleta saídas/exceções | A lista `results` não é usada para impedir merge/limpeza de tarefas que falharam |
| Integração | O router tenta merge e chama limpeza para cada tarefa | `run_tests` existe no gerenciador, mas não é chamado nesse caminho; faltam gates de validação e preservação de resultados rejeitados |
| Checkpoints | SQLite armazena conteúdo e limites por provedor | No router examinado, gravações ocorrem ao concluir ou capturar limite, não a cada chunk; queda abrupta ainda pode perder o buffer em memória |
| Relay | Troca de provedor após limite constrói prompt com saída parcial | A troca substitui o histórico por uma mensagem de usuário; faltam preservação de instruções, reconciliação de sobreposição e checkpoint de ferramentas/arquivos |
| Persistente | Aguarda o reset e tenta gerar novamente | `current_messages` não é atualizado com a saída parcial nesse caminho; retomar o mesmo texto não é garantido |

Essas observações são de análise estática dos caminhos mencionados. Não foi executado swarm contra este repositório nem testada uma integração real do Hydra nesta investigação.

## Direção proposta para adaptação

Separar duas capacidades, preservando o proxy de inferência já existente:

- **Provedor de inferência:** recebe mensagens e produz conteúdo/eventos de geração.
- **Executor de agente:** recebe tarefa e workspace, executa ferramentas, devolve artefatos e evidência de validação.

Um adaptador só pode anunciar execução de agente se realmente fornecer essas operações. Enviar um caminho no prompt não cria isolamento de escrita nem concede ao modelo acesso ao filesystem.

Fluxo proposto: `tarefa -> coordenador -> executor/adaptador -> artefatos -> validação -> próxima etapa`.

### Contratos mínimos propostos

- `TaskSpec`: versão, run/task/attempt IDs, objetivo, critérios de aceite, dependências, arquivos permitidos, contrato compartilhado, provedor, workspace e orçamento.
- `TaskResult`: estado do processo e estado da tarefa separados, resumo, sessão do provedor, arquivos alterados, patch/commit, checks com resultado, falhas e referências a artefatos.
- `RunEvent`: sequência persistente, correlação com tarefa/tentativa, tipo e payload; exemplos: started, progress, needs_context, artifact_created, rate_limited, completed e failed.
- `HandoffCheckpoint`: objetivo, instruções relevantes, decisões, tarefas concluídas/pendentes, base Git, alterações, ferramentas já executadas, saída parcial e âncora de continuação.

Esses nomes são propostas de desenho; não são modelos implementados atualmente.

### Próximos incrementos recomendados

1. Definir contratos tipados e um executor CLI com agente falso para validar o ciclo sem consumir modelos pagos.
2. Persistir estado, eventos e artefatos por execução/tarefa/tentativa, com recuperação e repetição idempotente.
3. Conectar o workspace real ao executor, limitar concorrência e atribuir propriedade de arquivos.
4. Implementar handoff estruturado e testes de interrupção/retomada sem duplicação de alterações.
5. Validar resultados e integração em branch/worktree dedicada antes de alterar a branch principal; preservar trabalho em falhas.
6. Expandir os transportes API, SSH e CDP conforme as capacidades efetivamente verificadas de cada adaptador.

Não tratar as últimas 15 linhas, um session ID ou um stream salvo como garantia de continuidade completa entre modelos. A validação precisa incluir decisões, efeitos de ferramentas e estado do repositório.
