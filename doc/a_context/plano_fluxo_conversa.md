# Plano do fluxo de conversa do Hydra

Status proposto para implementação. Atualizado em 14/11/2026.

## Resultado esperado

A pessoa abre **Novo chat**, escolhe o projeto quando necessário, escreve o pedido e clica em **Enviar**. O Hydra inicia o agente e apresenta a resposta na mesma conversa. Ela pode escrever outra mensagem, interromper a resposta, sair da tela e voltar ao histórico.

Direção definida pelo usuário nesta conversa. A interface escura aprovada continua sendo a base visual. A prioridade é reduzir o esforço para começar e acompanhar trabalho.

## Estado examinado

Base da análise em `201d88f`. As correções de transporte e renderização do terminal acompanham esta entrega.

| Caminho atual | Comportamento observado no código | Trabalho necessário |
| --- | --- | --- |
| [NovoChatPage](../../frontend/src/page/NovoChatPage.tsx) | Cria um run com `execute: false` e abre sua conversa. | Conectar o envio ao início efetivo do turno. |
| [ChatTimelinePage](../../frontend/src/feature/chat/ChatTimelinePage.tsx) | Exibe snapshot/SSE e envia mensagens para a thread existente. | Exibir e controlar turnos reais, inclusive após a resposta anterior terminar. |
| [SessionService](../../src/hydra_orch/core/session_service.py) | Persiste mensagens e eventos. Sessões pertencem a um run. | Vincular conversa durável a vários turnos e às execuções correspondentes. |
| [WorkerRunner](../../src/hydra_orch/bridge/worker_runner.py) | Recebe prompt por stdin, possui parâmetros de retomada e coleta a saída com `communicate`. | Disponibilizar eventos incrementais e confirmar a captura do identificador de sessão do provedor. |
| [RunService](../../src/hydra_orch/core/run_service.py) | Executa tentativas em worktree, verifica alterações e resultados. | Reutilizar execução, cancelamento e evidências, com sucesso válido também para respostas de leitura e explicação. |
| [API](../../src/hydra_orch/server.py) | A rota de mensagens apenas persiste a mensagem. A criação de run pode aguardar execução quando solicitada. | Aceitar o envio rapidamente e executar em trabalho supervisionado no backend. |

As sessões de terminal são processos interativos separados. O histórico de conversa precisa representar mensagens, ferramentas e resultados estruturados do agente.

## Experiência proposta

1. **Começar.** Abrir Novo chat com o projeto atual visível. Se ainda não houver projeto, oferecer seleção de pasta e cadastro no próprio fluxo. Mostrar o agente disponível já selecionado e deixar conta, modelo e modo em opções avançadas.
2. **Enviar.** O botão Enviar apresenta a mensagem imediatamente, limpa o campo após a confirmação de persistência e mostra “Iniciando agente…”. A operação ganha uma identidade estável para reconexão e repetição.
3. **Acompanhar.** A resposta aparece progressivamente. Uso de ferramentas pode ser expandido. Pedidos de autorização necessários aparecem na conversa, com uma pergunta específica e o efeito da decisão.
4. **Continuar.** O campo permanece disponível após a resposta. A próxima mensagem utiliza a mesma conversa, o projeto e o contexto confirmado do agente. Durante um turno ativo, mostrar como “Aguardando envio” uma mensagem posterior e permitir cancelar esse envio pendente.
5. **Parar e voltar.** Interromper cancela o turno ativo e preserva o que chegou. Reabrir a conversa restaura histórico, estado e projeto. Uma nova mensagem continua a conversa após a interrupção.

Exemplo de aceite para a primeira entrega

> “Leia o README e explique como iniciar este projeto.”
>
> A resposta aparece no chat.
>
> “Agora detalhe o segundo passo.”
>
> A resposta mantém o contexto da primeira pergunta.

Com projeto e agente configurados, a tarefa começa com o campo e um envio. A pessoa acompanha a resposta na mesma tela.

## Decisões de implementação

- **Conversa e turno.** Criar uma conversa com identidade própria. Cada mensagem do usuário inicia um turno, que pode referenciar run, task e attempt existentes. O fim de um run encerra aquele trabalho e permite continuar a conversa.
- **Compatibilidade.** Preservar IDs e rotas de runs existentes. A migração associa as sessões antigas a conversas e mantém seus eventos, artefatos e vínculos. Runs antigos continuam acessíveis em Workspaces.
- **Persistência e execução.** Persistir mensagem, turno e intenção de execução na mesma transação. Um consumidor do backend inicia o trabalho após o commit. Registrar a posse do turno com lease e impedir dois consumidores de executarem o mesmo envio. Após reinício, reconciliar tentativa e processo antes de reexecutar.
- **Repetição de envio.** Usar chave idempotente estável por mensagem. Repetir a requisição retorna o mesmo turno. Um conflito de sequência mantém o rascunho e recupera o estado atual.
- **Agente inicial.** Fechar a primeira jornada com um executor disponível, escolhido no formulário e confirmado pelo backend. A disponibilidade vem da descoberta local. Login ausente ou executável indisponível precisa de orientação no chat antes de anunciar execução.
- **Transporte de conteúdo.** Acrescentar leitura incremental ao runner e normalizar eventos de texto, ferramenta, autorização, erro e término. Reutilizar os eventos duráveis e o SSE existentes para entrega e replay.
- **Protocolos dos provedores.** Antes de implementar cada adaptador, conferir a versão e as opções instaladas de saída estruturada e retomada. Capturar a sessão nativa por evidência do protocolo. A opção de retomada existente, isoladamente, não comprova continuidade de contexto.
- **Contexto de continuidade.** Usar a sessão nativa confirmada quando suportada. Nos demais casos, reconstruir o contexto com mensagens e resultados persistidos, dentro dos limites do modelo, e registrar a estratégia usada.
- **Workspace.** Fixar projeto, diretório e política de acesso por conversa. Preservar a worktree entre turnos relacionados, com referências explícitas às alterações. Trocar o projeto inicia uma conversa com esse contexto.
- **Resultado sem alteração.** Leitura, diagnóstico e explicação podem concluir com uma resposta textual. Aplicar a validação de patch e os checks relevantes quando houver alteração. Distinguir resposta concluída, alterações aguardando revisão e integração concluída.
- **Anexos.** Promover os anexos do rascunho para a conversa e o turno na confirmação de envio. Resolver conteúdo e acesso no backend e testar a chegada ao executor. Exibir progresso e erro de transferência junto da mensagem.
- **Interrupção.** Usar o cancelamento de processos e os estados existentes, incluindo término dos descendentes. Um envio posterior só inicia após a tentativa anterior ter sido encerrada ou reconciliada.
- **Orquestração.** Expor as escolhas avançadas conforme as capacidades do executor. Após a conversa básica funcionar, integrar o coordenador para distribuir trabalho, acompanhar agentes e aplicar as políticas de rota e orçamento existentes.

Os nomes de entidades e operações acima descrevem a proposta. Os contratos de API, migração e eventos serão definidos na primeira etapa antes de alterar os clientes.

## Ordem de entrega

| Etapa | Entrega concreta | Evidência de aceite |
| --- | --- | --- |
| 1. Contrato e continuidade | Modelo de conversa/turno, vínculos com runs, migração, fila durável, idempotência e estratégia de contexto. | Banco com dados antigos migra e preserva histórico. Envio repetido e consumo concorrente produzem um turno e uma execução. |
| 2. Primeiro executor | Prompt inicia um agente real pelo backend. Texto e ferramentas geram eventos. Leitura e resposta sem patch concluem. | Dois prompts encadeados pelo serviço, com contexto, erro de login e cancelamento exercitados. Registrar provedor e versão usados. |
| 3. Jornada no frontend | Novo chat com Enviar, conversa com resposta incremental e Parar, nome automático pelo primeiro pedido e reabertura pela sidebar. | Executar o exemplo de README inteiramente pela interface, incluindo recarregar durante a resposta, sem duplicação. |
| 4. Anexos e edição | Transferência do rascunho, leitura de arquivo, edição em workspace, diff e revisão na conversa. | Agente usa o arquivo enviado, altera um arquivo de teste e o diff corresponde ao artefato persistido. Falha de envio preserva rascunho. |
| 5. Outros agentes e coordenação | Adaptador adicional, continuidade por capacidade, políticas de roteamento, trabalho paralelo e estados de espera. | A mesma jornada passa por executor suportado e pela recuperação de falha sem prometer capacidades ausentes. |

A primeira entrega utilizável reúne as etapas 1, 2 e 3. O cadastro isolado de uma mensagem é uma base técnica do fluxo.

## Estados que a tela precisa resolver

| Situação | Resposta da interface |
| --- | --- |
| Projeto ausente | Selecionar ou cadastrar pasta a partir do Novo chat. |
| Agente sem login ou instalação | Informar o problema e mostrar a ação para recuperar a conexão. |
| Início demorado | Manter a mensagem visível e indicar que o agente está iniciando, com opção de interromper. |
| Agente trabalhando | Resposta incremental, atividade atual e Parar. |
| Pedido de decisão | Mostrar a pergunta e a consequência das opções no chat. |
| Conexão perdida | Preservar mensagem e resposta parcial, reconectar com cursor e recuperar o turno. |
| Falha do processo | Mostrar o motivo disponível, preservar evidências e permitir tentar de novo com identidade de tentativa própria. |
| Resposta concluída | Manter o campo pronto para a mensagem seguinte. |
| Alterações produzidas | Mostrar arquivos/diff e oferecer a revisão correspondente. |
| Cancelamento solicitado | Mostrar “Interrompendo…” até o backend confirmar o encerramento. |

## Verificação e conclusão

- Testes de serviço devem cobrir reenvio, concorrência, lease expirado, reconexão, interrupção, continuidade e migração de sessões existentes.
- O teste de navegador deve começar no Novo chat e terminar na segunda resposta, incluindo um recarregamento durante o primeiro turno.
- Testes com executores controlados verificam contratos e falhas. Registrar separadamente a execução real com a CLI autenticada, incluindo versão, primeiro evento, resposta e preservação de contexto.
- Conferir teclado, foco, leitor de tela, 320/375 px, fonte ampliada e redução de movimento nas telas alteradas.
- Apresentar a jornada real ao usuário para validar facilidade de uso. O aceite exige conseguir enviar e continuar prompts pelo chat.

## Relação com o encerramento do terminal

A tarefa do terminal corrige autenticação WebSocket no navegador, estabilidade da instância xterm, sincronização de dimensões e abertura do primeiro painel em largura total. Corrige também a herança de `TERM=dumb` e usa a opção `--no-daemon` quando suportada pelo Codex distribuído no aplicativo desktop.

Na verificação local, um processo de eco controlado confirmou digitação por WebSocket e preservação da tela ao redimensionar. O Codex instalado abriu até o campo de prompt em aproximadamente 2,3 segundos numa medição, sem enviar pedido ao modelo. Essa evidência cobre a abertura e a renderização. A resposta do provedor e o uso diário exigem validação própria.

O plano acima conecta a conversa ao executor em uma próxima implementação.
