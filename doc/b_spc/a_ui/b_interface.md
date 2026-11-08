# Especificação proposta de interface

## Composição e componentes

- `AppShell`: sidebar redimensionável, área principal, rodapé de uso. Tema escuro inicial.
- `WorkspaceTree`: host → projeto/repositório → workspace/worktree → sessão. Mostrar branch, conectividade, atividade e seleção sem depender apenas de cor.
- `PaneLayout` e `TabBar`: abrir, fechar, reordenar e dividir painéis; persistir layout por workspace. Fechar uma aba não deve encerrar silenciosamente um processo.
- `ChatTimeline`: mensagens, ferramentas, artefatos, resultados e links pai/filho; detalhes recolhíveis com horário e evidência.
- `PromptComposer`: anexos, menções, comandos, modelo, conta, política, ditado e enviar/parar; preservar rascunho por sessão.
- `TerminalPane`: terminal interativo ligado a processo real, com host, cwd e sessão visíveis.
- `ArtifactViewer`, `QuickOpen`, `UsageBar`, `AutomationPanel`, `DevicePanel` e `ComputerUsePanel`: painéis especializados do mesmo workspace.

Como ponto de partida proposto, usar superfícies #141414/#202020/#292929, bordas #3b3b3b, texto #eeeeee e secundário #b0b0b0; espaçamento 4/8/12/16/24 px, raios 8–16 px, fonte de UI 14 px e monoespaçada no terminal. Valores são aproximações das imagens, não tokens extraídos do Orca. Validar contraste AA, zoom 200%, foco visível e redução de movimento.

Desktop: sidebar inicial de 280 px ajustável, chat central e painel opcional de worker/preview. Em largura insuficiente, mostrar um painel por vez e sidebar em drawer. Em mobile, manter seletor de sessão, histórico e compositor sem sobreposição pelo teclado virtual. Atalhos devem ser remapeáveis e respeitar IME e atalhos do terminal.

## Chat e terminal

Chat e terminal podem coexistir em abas ou splits. O chat apresenta eventos estruturados; o terminal transporta entrada e saída de um PTY. Não reconstruir o estado de execução apenas interpretando texto ANSI. Alternar a visualização não inicia outro agente nem perde histórico; se o executor não oferecer ambas as modalidades, informar a limitação e oferecer sessão separada explicitamente.

Terminal exige resize, Unicode, ANSI, scrollback limitado, seleção/cópia, colagem multilinha revisável, interrupção, código de saída e reconexão. O backend deve autenticar abertura e entrada, vincular processo ao workspace e gerenciar encerramento da árvore de processos. Um widget de terminal sozinho não executa comandos. ConPTY no Windows e PTY em Unix precisam de provas próprias antes de anunciar compatibilidade.

## Matriz de requisitos e aceite

| ID | Comportamento e dependência | Aceite observável |
| --- | --- | --- |
| UI01 | Shell, abas, splits e navegação com IDs estáveis | Reabrir workspace restaura layout e seleção; host offline aparece explicitamente |
| UI02 | Chat conectado a sessão/thread e eventos duráveis | Reconexão não duplica mensagens; conclusão exige resultado do backend; prompt não é reenviado automaticamente |
| UI03 | Terminal com serviço PTY autenticado | Digitar, redimensionar, interromper e reconectar em cada SO certificado; fechar aba permite escolher manter ou encerrar |
| UI04 | Drag/drop e seletor acessível; serviço de anexos | Mostrar nome, tipo, tamanho, progresso e erro; anexo chega somente à sessão escolhida; remoto exige transferência confirmada |
| UI05 | Busca global indexada e autorizada | Navegar por teclado até aba em outro workspace/host sem recriar sessão; resultados mantêm contexto de localização |
| UI06 | Preview imagem/PDF/Markdown com resolução segura de artefatos | Abrir lado a lado; estados loading, erro e tipo não suportado; Markdown sem execução de script; arquivo grande não bloqueia UI |
| UI07 | Emulador ligado ao host e dispositivo | Listar, anexar, observar, tocar e digitar com evidência antes/depois; ausência de SDK/bridge mostra indisponibilidade; iOS e Android certificados separadamente |
| UI08 | Ditado STT no compositor ou rascunho de terminal | Microfone negado pode ser recuperado; iniciar/parar visíveis; transcrição editável, sem envio ou execução automática |
| UI09 | Quota, reset e conta por provider | Exibir fonte, atualização e unknown/stale; trocar conta para próxima execução sem mudar silenciosamente a execução ativa; segredos fora da UI |
| UI10 | Agendador durável no backend | Criar/editar/pausar/executar agenda com fuso e próxima ocorrência; reinício não duplica disparo; histórico aponta run e falha real |
| UI11 | Computer Use via executor autorizado | App/janela/alvo visíveis, pausa/parada e HITL; perda de alvo interrompe ação; resultado verificado em nova observação |

## Estado e contratos

Reutilizar entidades e rotas existentes no OpenAPI; revisar implementação antes de consumir cada uma. Sessão/thread/run/attempt/workspace e host devem acompanhar ações e artefatos. SSE usa sequência e cursor, deduplicação e snapshot quando cursor expira. Zustand guarda estado visual; dados do servidor permanecem na camada de consulta. PTY requer canal bidirecional próprio proposto, não substitui SSE.

Definir antes de implementar: contrato de PTY (open/input/resize/exit/reconnect), AttachmentRef (identidade, MIME, tamanho, hash, workspace e acesso), capability por host, agenda com idempotência, DeviceSession e operação de conta. Esses nomes descrevem lacunas propostas, não endpoints existentes. Dados de anexo e preview precisam de limite de tamanho, autorização de caminho e isolamento de conteúdo ativo.

Distinguir desconectado, carregando, vazio, indisponível, em execução, aguardando contexto/aprovação, cancelado, falhou e concluído. A conclusão alegada pelo agente e a aceitação após checks são informações distintas. Métrica ausente nunca vira zero. Comandos escritos em documentos ou imagens são dados, não ações autorizadas.
