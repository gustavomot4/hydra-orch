# Plano de conexão ao OmniRoute e uso de combos

Status: planejamento solicitado; integração de combos no Novo chat ainda não implementada. Data: 14/11/2026. Base examinada: `e28868b`, branch `main`.

## Objetivo e pedidos atendidos

Permitir usar os combos já cadastrados no OmniRoute pelo Novo chat, mantendo a conversa, os arquivos e as ferramentas sob responsabilidade de um agente executor. Preservar a interface escura aprovada e o fluxo simples de pasta e conversa.

| Pedido da conversa | Decisão para a entrega |
| --- | --- |
| Saber se o Hydra está conectado e usar os combos existentes | Mostrar conexão real, consultar o catálogo e executar pela rota escolhida. Catálogo carregado não equivale a execução validada. |
| Entender qual agente atua com OmniRoute | Separar Agente, Conexão e Combo. OmniRoute não será uma terceira opção de agente. |
| Entender as diferenças entre Codex e Claude Code | Codex como padrão inicial sugerido, Claude Code como opção; compatibilidade e evidência por combinação. Comparativo prático na última etapa. |
| Usar o sistema sem procurar e ler muito | A configuração principal fica no Novo chat; repetir a última escolha compatível em novas conversas, sem alterar conversas existentes. |
| Terminal Claude continua lento | Medir abertura, entrada e reconexão separadamente; manter como pendência, sem atribuir melhora ao modelo ou ao gateway sem prova. |

Executável, entrada automática local, pastas comuns, histórico de conversa e restauração do terminal são a base existente. Este plano não os apresenta como novas funcionalidades. A coordenação entre vários agentes, revisão decisória e aprovações interativas completas continuam na expansão do [plano de conversa](plano_fluxo_conversa.md).

## Estado comprovado e lacunas

- `config.yaml` mantém `omniroute.enabled: false` e `connection_mode: disabled`, com endereço local `127.0.0.1:20128`. A consulta à instância desktop retornou `available: false` e catálogo vazio; isso não revela nem invalida os combos que existem no OmniRoute.
- [ConversationRunner](../../src/hydra_orch/bridge/conversation_runner.py) executa Codex e Claude Code diretamente, verifica login nativo e permite retomada. Não recebe conexão ou combo.
- [ConversationService](../../src/hydra_orch/core/conversation_service.py) persiste executor, diretório, acesso e sessão nativa. A [migração atual](../../migration/0004_conversation.sql) não registra a rota de inferência da conversa.
- [OmniRouteClient](../../src/hydra_orch/bridge/omniroute_client.py), [RouteSelector](../../src/hydra_orch/core/route_selector.py) e [Contas e consumo](../../frontend/src/feature/quota/QuotaAccountsPage.tsx) já possuem inventário de modelos, contas, quotas e seleção de conta para outros fluxos. Isso não conecta automaticamente o Novo chat ao gateway.
- A instalação local OmniRoute `3.8.52` declara `GET /api/combos`. O acesso efetivo, a forma do catálogo e a credencial necessária ainda precisam de verificação somente leitura com o daemon disponível. `GET /v1/models` sozinho não comprova a definição nem a compatibilidade de um combo.
- Dois turnos reais foram validados com Codex direto. Não há comparação equivalente dos dois agentes pelo gateway nem comprovação de edição por combo.

## Experiência definida para implementação

1. Abrir Novo chat com **Pasta** e **Agente** visíveis. Codex começa selecionado se estiver utilizável; indisponibilidade oferece outra escolha, sem trocar automaticamente após Enviar.
2. Em **Conexão**, escolher **Conta do agente** ou **OmniRoute**. A primeira preserva o funcionamento direto atual.
3. Escolher **OmniRoute** revela **Combo**, com os nomes reais cadastrados e busca quando a lista crescer. Não exigir digitar ID, modelo ou caminho de configuração para cada pedido.
4. Mostrar disponibilidade e uma ação junto do campo: **Testar conexão**, **Atualizar combos** ou **Abrir OmniRoute**, conforme o estado. A configuração inicial fica em Configurações, com acesso direto a partir do erro, sem desviar a pessoa por Hosts e Workspaces.
5. Selecionar um combo compatível, escrever e Enviar. A mensagem é persistida antes de iniciar o agente; preparação e resposta aparecem na mesma conversa.
6. No cabeçalho, mostrar um resumo curto: `Codex · OmniRoute · nome do combo`. Na conta direta, não mostrar campo Combo vazio. Modelo efetivamente observado e detalhes técnicos ficam expansíveis.
7. Continuar e reabrir mantém pasta, agente e conexão. Para trocar agente, conexão ou combo, oferecer **Nova conversa com esta configuração**. Não reutilizar uma sessão nativa sob outra rota nem copiar contexto para outro provedor silenciosamente.

Estados distintos: conexão desligada, gateway indisponível, credencial ausente/recusada, catálogo carregando, sem combos, sem permissão para consultar combos, combo incompatível, configuração alterada e erro durante execução. Não transformar falha de catálogo em lista vazia ou em indicador Conectado. Preservar rascunho e seleção; oferecer uma próxima ação específica.

Aplicar o [kit de frontend](../../.agents/skills/kit-frontend/SKILL.md), os padrões de seleção e estados e as [correções do projeto](../../design/correcoes.md). Trata-se de ajuste do produto aprovado, sem novo redesenho de marca. Usar rótulos visíveis, teclado completo e alvos de toque de 44 px nos controles alterados. O planejamento textual não substitui a verificação das telas implementadas.

## Contratos e decisões técnicas propostas

### Agente, conexão e compatibilidade

- `executor`: continua `codex` ou `claude`; é quem executa ferramentas no diretório isolado.
- `connection_mode`: `direct` ou `omniroute`; é independente do modo global `disabled/optional/required` do gateway. Uma conversa que escolheu OmniRoute não pode cair silenciosamente na conta direta quando o gateway falhar.
- `combo_ref`: identidade externa e nome exato solicitado, sem credencial. Não normalizar nomes para slugs nem aplicar a restrição de ausência de espaços de `ProfileDefinition.model_ref` aos nomes de combos.
- Matriz por versão de CLI, protocolo do gateway, definição do combo e capacidades: `verified`, `unsupported`, `unverified`, com motivo e data. CLI instalada, login nativo, credencial de gateway e execução comprovada são fatos separados.
- Para Claude Code, começar somente com combos cujos destinos sejam Claude e cujo protocolo de ferramentas tenha sido certificado. A documentação da Anthropic não oferece suporte a modelos não Claude por gateway. Não inferir a família pelo nome do combo.
- Para Codex, confirmar o protocolo aceito pela versão instalada e testar ferramentas, respostas incrementais e retomada. Compatibilidade OpenAI genérica não prova compatibilidade com o agente.
- Resolver destinos de combos aninhados, fallbacks e alvos auxiliares, incluindo shadow/eval quando presentes. Tratar ciclos, definições desconhecidas e destinos dinâmicos como não certificados. Não executar inferência apenas para abrir a lista.
- Combos mistos, estratégias com múltiplas gerações e rotas dinâmicas só ficam selecionáveis após prova específica. A estratégia do combo não será descrita como execução de vários agentes.
- Se nenhuma combinação puder ser certificada, registrar o impedimento e a alternativa técnica necessária antes de ampliar o escopo. Não criar um executor próprio de ferramentas nem trocar de CLI silenciosamente.

### Persistência, fila e continuidade

- Acrescentar migração aditiva, prevista como `0005_conversation_route.sql` se a sequência continuar livre. Não alterar checksums de migrações existentes. Reutilizar backup e recusa de rollback destrutivo quando houver dados dependentes.
- Persistir na conversa a escolha e, no turno, um snapshot sem segredos: executor/versão, modo, referência da conexão, combo solicitado, revisão/hash da definição consultada, protocolo, política de acesso e resultado de compatibilidade. Credencial fica fora do snapshot.
- Conversas antigas migram como `direct`, sem execução automática e sem perder sessão, mensagens ou vínculo com runs. Propostas de campos devem entrar no contrato antes da alteração dos clientes.
- Integrar rota ao hash idempotente, à fila e à reserva do turno. Reenvio, reconexão e dois consumidores não podem criar subprocessos duplicados ou trocar a rota.
- Revalidar disponibilidade e definição ao iniciar cada turno. Combo removido ou alterado exige revisão explícita da configuração antes do próximo envio; mensagens já enfileiradas não assumem a definição nova.
- Um hash local documenta o observado, mas não congela a configuração no OmniRoute. Verificar se há suporte a revisão fixada; sem ele, registrar essa limitação e não prometer imutabilidade durante uma chamada. Registrar divergência observada após a execução.
- Retomada nativa permanece por agente e conexão. Reinício reconcilia a posse e o processo; não repete ferramentas ou chamada potencialmente cobrada apenas por perda da confirmação.

### Processo, credenciais e evidência

- Reutilizar `SecretRef`/resolução em memória e `filter_worker_env(allowed_env=...)` para fornecer apenas as variáveis exigidas pela conexão escolhida. O filtro atual remove segredos herdados; deixar de resolver isso faria a integração parecer configurada sem autenticar a CLI.
- Configurar gateway/modelo por invocação, sem sobrescrever configurações globais do Codex, Claude ou OmniRoute. Não incluir chaves em argumentos, mensagens, snapshots, URLs, SQLite ou logs. Credencial do Hydra desktop e credencial do OmniRoute são distintas.
- Descoberta passa a considerar o modo de conexão: acesso por gateway não exige indevidamente login direto. Credencial disponível também não basta para anunciar um combo certificado.
- Reutilizar eventos duráveis de texto, ferramenta, erro, interrupção e término. Acrescentar eventos de rota solicitada, definição observada e modelo efetivo quando reportado pelo protocolo. Não inventar modelo, uso ou custo; informação não observada permanece desconhecida.
- Preservar permissões de leitura/edição, anexos, worktree ou cópia de pasta e cancelamento da árvore do agente. O cancelamento não encerra o daemon compartilhado do OmniRoute. Eventuais requisições upstream já aceitas podem continuar sendo contabilizadas; verificar o cancelamento real.
- Distinguir fallback configurado dentro do combo de troca de conexão pelo Hydra. Não acrescentar novos destinos pagos, chamadas paralelas ou retries após efeitos de ferramentas sem política explícita e evidência.
- O launcher mantém entrada automática no Hydra. Deve propagar apenas a configuração necessária ao backend e informar se o gateway está disponível. Preservar a regra de parar somente processos que iniciou; não iniciar, atualizar ou parar o OmniRoute existente para habilitar esta tela.

### API proposta, sem implementação nesta tarefa

| Superfície | Alteração prevista |
| --- | --- |
| `GET /v1/control-plane/omniroute/inventory` | Preservar campos atuais; acrescentar estado detalhado e instante da consulta. Falhas de catálogo não apagam a leitura de saúde ou quota. |
| `GET /v1/control-plane/omniroute/combos` | Novo catálogo sanitizado, atualizado sob demanda, com identidade, nome, proveniência e compatibilidade por agente. Nunca retornar o objeto bruto com configuração sensível. |
| `GET /v1/control-plane/conversation-agents` | Preservar consumidores atuais e acrescentar capacidades por conexão, separando login direto e gateway. |
| `POST /v1/control-plane/conversations` | Acrescentar seleção de conexão/combo com validação no servidor. Omitir os novos campos preserva `direct`. Combinação inválida não inicia processo. |
| Snapshot e SSE da conversa | Expor escolha persistida e evidência observada da rota; preservar sequência, replay e campos existentes. |

Não oferecer edição, exclusão ou duplicação dos combos pelo Hydra nesta entrega. O OmniRoute continua sendo a fonte das regras; a interface oferece abrir sua administração. Cache pode mostrar a última leitura com data, mas não autoriza uma execução nova sem validação adequada.

## Entregas pequenas e dependências

Cada entrega tem um responsável integrador, caminhos explícitos e aceite antes da seguinte. Esta lista não autoriza nem exige agentes paralelos. Nenhuma alteração de runtime é necessária para concluir o planejamento.

| ID | Entrega e caminhos principais | Depende de | Critério de saída |
| --- | --- | --- | --- |
| OR01 | Descoberta do protocolo instalado e catálogo. `bridge/omniroute_client.py`, `tests/test_route_selector.py`, `tests/test_omniroute_live.py`, `doc/j_manual/omniroute_validacao_real.md`. | Base atual | Catálogo real somente leitura com origem, erros distintos e zero segredos; versões e autorização de `/api/combos` documentadas. Fixtures de combo comum, aninhado, misto, removido e dinâmico. |
| OR02 | Contrato de rota e matriz de compatibilidade. Novo `core/conversation_route.py`, `doc/b_spc/fluxo_conversa.md`, testes de contrato. | OR01 | Seleções aceitas/recusadas por evidência e capacidades. Contrato cobre nomes com espaço, referência ausente e mudança externa. Nenhuma promessa de execução derivada apenas de catálogo. |
| OR03 | Persistência e APIs. Migração/rollback novos, `core/conversation_service.py`, `server.py`, `doc/f_api/openapi.yaml`, `tests/test_conversation.py`. | OR02 | Histórico anterior preservado, rotas novas autenticadas, snapshot por turno, idempotência incluindo rota e nenhum subprocesso iniciado para seleção inválida. |
| OR04 | Primeiro caminho real: Codex direto/OmniRoute. `bridge/conversation_runner.py`, `core/conversation_route.py`, testes de subprocesso e conversa. | OR03 | Dois prompts por combo certificado; segundo depende do primeiro. Ler, editar fixture, diff correto, teste local, cancelar e retomar. Modo direto continua passando. Login do gateway validado sem depender do login direto. |
| OR05 | Claude Code direto/OmniRoute. Mesmos módulos, fixtures específicas e testes. | OR04 | Jornada equivalente com combo Claude certificado, limites de ferramentas preservados e evidência real separada do teste controlado. Falha não bloqueia Codex validado nem anuncia Claude como pronto. |
| OR06 | Jornada principal na UI: Novo chat e Conversa. `NovoChatPage.tsx`, `feature/chat/ConversationPage.tsx`, `conversationTypes.ts`, cliente/API, testes de conversa e Playwright. | OR03 e primeiro caminho certificado em OR04 | Escolher e enviar pelo chat; busca de combos, estados de erro, continuidade/reload e rascunho preservado. Só exibir como utilizável a combinação que passou no respectivo agente. |
| OR07 | Configuração e diagnóstico: Configurações, Contas e consumo e launcher. `feature/quota/`, página de configurações existente, `src/launcher/`, `desktop_backend.py`, manual Windows. | OR01, OR04 e OR06 | Estado condizente com o Novo chat; teste de conexão somente leitura; atalho abre com configuração válida; parar Hydra preserva daemon externo e instâncias anteriores. Sem exigir terminal para cada conversa. |
| OR08 | Certificação, desempenho e comparativo. Suítes relevantes, fixtures isoladas e registro no manual. | OR04–OR07; OR05 para comparar os dois | Jornada pelo executável, relatórios por combinação, tempos medidos por etapa e limitações explícitas. Nenhum vencedor geral declarado a partir de uma única tarefa. |

Na implementação, OR01 deve confirmar se o Codex pode ser o primeiro caminho pelo gateway. Se houver incompatibilidade impeditiva, registrar a evidência e reordenar OR04/OR05 para a combinação certificável, mantendo o Codex direto como padrão; não gastar as etapas de UI para esconder ausência de execução.

A página concreta de Configurações e o próximo número de migração serão confirmados no checkout da implementação. Não criar uma superfície concorrente para funções existentes.

## Verificação e critérios de conclusão

### Contratos e execução controlada

- Cobrir catálogo ausente, credencial ausente/negada, timeout, erro parcial, destinos incompatíveis, definição alterada, recursão de combos e nomes Unicode/espaços.
- Cobrir ambiente de subprocesso, isolamento entre conexão direta/gateway, ausência de segredos em persistência e SSE, retomada, interrupção, lease expirado e idempotência.
- Simular ferramentas reais na fixture: um arquivo é alterado no diretório isolado; a origem permanece intacta e o diff corresponde ao arquivo. Texto de sucesso sozinho não aprova o agente.
- Rodar pytest proporcionalmente aos módulos alterados, Vitest, TypeScript/build e Playwright; ampliar a suíte se houver regressão ou alteração transversal. Resultados existentes são referência, não prova da entrega futura.

### Prova real e comparação dos agentes

1. Consultar gateway e combos somente leitura, sem chamar modelo durante descoberta, busca ou Testar conexão.
2. Com execução autorizada e conta disponível, usar projeto fictício separado dos arquivos do usuário. Registrar CLI/versão, combo/revisão observada, modo de acesso e origem da resposta.
3. Pelo Novo chat, pedir leitura de README e uma continuação dependente do contexto; em outra jornada com edição permitida, corrigir um defeito pequeno, conferir diff e rodar o teste relevante.
4. Recarregar durante resposta, reabrir histórico, interromper um turno e continuar. Separar prova de API/serviço, navegador com executor controlado e navegador com provedor real.
5. Comparar Codex e Claude Code em cópias independentes da mesma fixture, instruções e limites equivalentes; registrar modelo, tempo, tokens/custo quando observados, resultado dos testes e intervenção necessária. Se modelos diferirem, o resultado compara os conjuntos agente/modelo, não isola a qualidade do agente. Falta de login ou rota impede a comparação real, sem substituir isso por mocks.

### Desempenho e UX

- Medir confirmação do envio, inicialização do processo, primeiro evento, primeiro texto, duração total, reconexão e entrada/eco do terminal. Separar sessão fria e restaurada; registrar carga e repetições, com mediana e p95 quando houver amostras suficientes.
- Meta inicial em ambiente controlado: confirmação de envio em até 1 segundo e entrada/eco do terminal em p95 até 250 ms, sem chamadas HTTP por tecla. São critérios futuros de teste, não resultados já medidos ou garantia de rede/modelo.
- Login e catálogo usam cache com validade e atualização explícita; não bloquear renderização nem refazer preflight de vários segundos em toda troca de tela. Uma falha conserva a escolha e o texto.
- Confirmar o mesmo terminal ao sair/voltar e ausência de processos duplicados. A abertura fria do Claude permanece pendente até medição e correção comprovadas; não mascarar com animação nem iniciar agentes escondidos para parecer instantâneo.
- Verificar Novo chat, Conversa e configuração nas larguras do kit, 320/375 px, teclado, foco, ampliação de fonte, alto contraste e movimento reduzido. Capturar desktop/celular após o carregamento real e registrar falhas, avisos e justificativas.
- Registrar leitor de tela real e teste com pessoas como executados, pendentes ou não executados. Não declarar conformidade a partir do verificador automático.

### Conclusão funcional

A entrega de combos só está concluída quando a pessoa consegue, pelo executável, escolher uma combinação certificada, enviar um pedido, acompanhar ferramentas/resposta, continuar com contexto e reabrir o histórico, sem abrir terminal e sem recriar no Hydra os combos do OmniRoute. Catálogo e monitoramento sozinhos são entrega parcial. Funcionalidades certificadas de um agente não certificam automaticamente o outro.

Encerrar com manual atualizado, versões testadas, limites conhecidos, revisão do diff, validações e commit/push conforme `AGENTS.md`. Não incluir segredos, banco, logs, transcrições, capturas ou bundles no commit.

## Fontes e fronteira deste planejamento

- [Contexto arquitetural](CONTEXTO-ORQUESTRACAO.md): inferência e execução de ferramentas são capacidades distintas.
- [Contrato de conversa atual](../b_spc/fluxo_conversa.md) e [manual do executável](../j_manual/iniciar_windows.md): base a preservar.
- [Validação OmniRoute anterior](../j_manual/omniroute_validacao_real.md): evidencia catálogo/saúde/quotas, não execução de combos pelo chat.
- [Codex: configuração de provedores](https://learn.chatgpt.com/docs/config-file/config-advanced) e [integração como plataforma](https://developers.openai.com/blog/codex-as-a-platform).
- [Claude Code: gateways](https://code.claude.com/docs/en/llm-gateway) e [compatibilidade de protocolo](https://code.claude.com/docs/en/llm-gateway-protocol). Fontes oficiais consultadas na discussão de 14/11/2026; conferir novamente diante de mudança de versão.

Esta tarefa produz apenas o plano e seus vínculos na documentação. Não liga o OmniRoute, altera combos, cria migração, troca a conexão de conversas nem executa provedores para validar a proposta.
