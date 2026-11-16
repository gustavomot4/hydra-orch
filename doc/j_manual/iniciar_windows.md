# Usar o Hydra no Windows

## Abrir e parar

O executável fica na raiz do projeto: [`Hydra.exe`](../../Hydra.exe), ao lado do `README.md`, e é versionado no Git. Ele usa este checkout e as instalações locais de Python e Node; mantenha o arquivo na raiz ou use um atalho para ele. Para recompilá-lo a partir das fontes, use `src/launcher/build.ps1`. O binário é um iniciador do sistema, não um instalador portátil com Python e Node embutidos.

Os arquivos finais da demonstração (vídeo, site gerado, bundle de frontend, capturas e relatórios) estão em [entrega-demo](../../ws/b_output/entrega-demo/README.md). Bancos, credenciais, logs e ambientes de execução continuam fora do Git.

Nesta máquina, o atalho **Hydra** na Área de Trabalho aponta para esse executável com a opção `--start`: abrir o atalho já inicia o sistema e o navegador. A janela de controle permanece disponível para **Parar** e **Abrir Hydra**.

1. Abra **Hydra.exe** e clique em **Iniciar**. O programa prepara a interface quando necessário, inicia ou reutiliza o OmniRoute local, inicia o backend e abre o navegador já conectado.
2. Use **Abrir Hydra** para voltar à interface.
3. Use **Parar** para encerrar a instância iniciada por essa janela. Fechar a janela também encerra seus agentes e terminais; os históricos persistidos permanecem.

O programa começa pela porta 8000 e escolhe uma porta livre se ela estiver ocupada. O endereço correto é aberto automaticamente. Processos anteriores ou pertencentes a outros programas são preservados. A janela controla apenas o backend que ela própria iniciou, inclusive ao parar.

Não é preciso abrir Vite, copiar um token ou lembrar duas portas para o uso pelo executável. Servidores iniciados manualmente continuam disponíveis como configuração avançada.

## OmniRoute junto com o Hydra

Desde 15/11/2026, o início pelo executável habilita a partida automática do gateway. O Hydra consulta a saúde do endereço configurado antes de iniciar qualquer processo. Se o OmniRoute já estiver pronto, reutiliza essa instância. Se a porta local estiver livre, executa a instalação existente com `serve --daemon --no-open --no-tray --port <porta>` e aguarda a saúde por até aproximadamente 35 segundos, sem abrir outro navegador ou console.

O endereço salvo em **Configurações e perfil → Conexão OmniRoute** é lido antes da partida. Uma conexão explicitamente desabilitada permanece desabilitada. A partida local só é permitida para HTTP em loopback; um gateway remoto continua sendo consultado no endereço escolhido, sem criar um substituto local. Um processo que ocupe a porta é preservado. Falta da CLI ou falha de saúde não impede abrir o Hydra em modo opcional; a conexão informa sua indisponibilidade e nenhuma instalação ou atualização é feita automaticamente.

**Parar o Hydra deixa o OmniRoute ligado.** Ele funciona como serviço compartilhado e pode ser reutilizado por outros programas ou na próxima abertura. O Hydra não altera combos, contas ou credenciais do OmniRoute e não envia prompts para validar a partida. O daemon iniciado por ele usa apenas loopback; a credencial local do Hydra não é herdada por esse processo. A credencial da API OmniRoute permanece separada.

No modo avançado, `HYDRA_OMNIROUTE_AUTOSTART=0` desativa essa partida pelo executável. O servidor manual mantém o padrão sem gateway; para optar por partida automática na configuração, use `omniroute.enabled: true`, `connection_mode: optional` (ou `required`) e `auto_start_daemon: true`. O modo `required` continua recusando uma inicialização sem gateway disponível.

Validação: testes com serviço de fixture real em porta livre, segunda partida sem duplicação, porta ocupada, CLI ausente, timeout, separação da credencial, configuração persistida e opção de desativação. A jornada pelo executável usa um runtime de teste isolado e verifica também a preservação do OmniRoute instalado depois de parar o Hydra.

## Pastas e conversas

| Na interface | O que significa |
| --- | --- |
| **Pasta** | Onde estão os arquivos do projeto. Pode ter Git ou ser uma pasta comum. |
| **Conversa** | Seu pedido, as respostas e a continuidade daquele trabalho. Uma pasta pode ter várias conversas. |
| **Área de trabalho** | Canvas ou lista para acompanhar os agentes de uma conversa ou execução. |
| **Estrutura técnica** | Hosts, workspaces, agentes e execuções antigas. Não é necessário abrir essa estrutura para conversar. |

Escolha uma pasta, escreva uma mensagem e clique em **Enviar**. Para adicionar outra pelo executável, abra **Adicionar pasta → Selecionar pasta** e escolha no diálogo do Windows. Também é possível informar o caminho e clicar em **Usar esta pasta**. Clicar em uma pasta da barra lateral abre Novo chat com ela selecionada. A busca encontra pastas e pesquisa os títulos das conversas em todo o histórico, inclusive fora da página atual. A área **Alterações** reúne os resultados para revisão.

O acesso começa em leitura. As opções permitem editar uma cópia isolada. Para reabrir um trabalho, clique no título em **Conversas**. A conversa mantém contexto; não é preciso criar outra sessão ou abrir um terminal a cada mensagem. O terminal restaura o processo já aberto quando você sai e volta à tela.

## Acompanhar agentes na Área de trabalho

1. Envie seu pedido pelo **Novo chat**. Para distribuir tarefas, habilite **Opções da conversa → Coordenar tarefas com agentes** antes de enviar.
2. Abra **Ver agentes** no cabeçalho da conversa, ou **Área de trabalho** na navegação lateral. O seletor superior permite escolher outra conversa ou uma execução anterior; conversas têm busca em todo o histórico e execuções têm busca na página atual.
3. Arraste o fundo para navegar e use a roda do mouse ou os botões de zoom para aproximar. **Enquadrar** mostra todos os cards; **Organizar** restaura a distribuição inicial. A alça no canto do card permite movê-lo. Posições e enquadramento são guardados neste navegador por trabalho.
4. Clique em um card para abrir **Conversa**, **Atividade** e **Alterações**. No celular, a lista aparece primeiro e os detalhes ficam abaixo. **Lista** também está disponível no desktop para acompanhar sem arrasto.
5. Use **Abrir conversa** para continuar o pedido no chat. Uma execução antiga sem conversa oferece o vínculo para a execução completa.

Com foco no canvas, as setas navegam, `+`/`-` alteram o zoom e `Home` enquadra. Na alça do card, as setas movem o agente. A geometria e os textos do mapa crescem juntos quando a fonte do navegador aumenta; o restante da página se reorganiza.

Cards e linhas usam os registros existentes: plano, dependências, resultados e revisão persistida. Uma conversa individual mostra seu agente, sem inventar um swarm. Estados têm texto e símbolo além da cor. A base visual continua preta; laranja destaca ações e seleção, conforme a correção do dono.

O painel lê mensagens da conversa, resultados e mensagens de agente disponíveis no log de uma tentativa encerrada. Não transmite mensagens diretas a um worker em execução nem representa as linhas como conversas arbitrárias entre agentes. Ausência de verificações, alterações ou mensagens é informada explicitamente. Esta tela acompanha o trabalho; não muda o processo de execução nem certifica a escolha do melhor modelo.

### Arrastar, acompanhar ao vivo e continuar o chat

Arraste pelo **corpo do card** para mudar sua posição. Um clique abre os detalhes; mover o mouse mais de 5px durante o pressionamento inicia o arrasto. A alça do canto continua disponível para mouse e teclado. Atualizações de estado e entrada de novos cards preservam a organização manual.

O mapa recebe eventos da conversa e da execução. **Ao vivo** indica stream conectado; na reconexão, o último mapa permanece e a consulta automática serve de recuperação. Um agente criado pela própria CLI entra quando seu protocolo informa identidade e estado; os detalhes identificam essa origem. Chamadas de shell e texto afirmando que houve delegação não criam agentes. O acompanhamento não habilita novas ferramentas: as restrições da conexão continuam valendo.

Em **Somente leitura**, o coordenador pode produzir um plano sem executar os workers. Esses cards aparecem como **Planejado**, com a indicação de que a execução não começou. Para executar o plano pelo coordenador, inicie um pedido com coordenação e permita edições em uma cópia isolada de um projeto Git.

No chat, o seletor com **agente e modelo atual** fica junto do campo de mensagem. Clique nele para trocar agente, conexão, modelo ou combo dos próximos envios, mantendo o histórico. A parte das mensagens rola enquanto o compositor permanece acessível. Em janelas com até 480px de altura, a tela volta ao fluxo completo para não encobrir conteúdo. Anexos e voz ficam no próprio compositor; no celular, os controles são compactos.

Em Novo chat, clique no nome da **Pasta** para buscar por nome ou caminho. **Adicionar pasta** abre a escolha do Windows ou a entrada de caminho. O seletor junto do compositor e **Opções da conversa** abrem a mesma configuração de agente, conexão, destino, coordenação e acesso. Sugestões apenas preenchem o rascunho; não enviam um pedido automaticamente.

### Pedir uma análise do repositório

Pedidos para explicar capacidades e propor melhorias podem terminar com um relatório no próprio chat, inclusive quando a conversa está no modo coordenado. O planejador distingue esse pedido de uma implementação; uma análise estruturada válida não cria workers nem exige edições. Para uma inspeção, mantenha **Somente leitura** como configuração adequada ao pedido.

Exemplo: “Analise o repositório sem alterar arquivos. Explique o que já está implementado, indique as limitações e proponha melhorias por prioridade. Cite os arquivos que sustentam suas conclusões e separe implementação encontrada de comportamento testado.”

Se aparecer limite de tempo, a mensagem agora identifica a etapa: **leitura e planejamento** (180s), **revisão** (180s), **execução de tarefas** (900s) ou **coordenação total** (1200s). Uma falha antes do plano informa que nenhum worker começou; não anuncia resultados de workers inexistentes. Os registros da tentativa permanecem na conversa. É possível enviar outra mensagem na mesma conversa com um escopo mais específico, preservando o histórico.

## Pastas sem Git

O cadastro do Novo chat aceita pastas comuns e repositórios ainda sem commit. O Hydra não executa `git init` para aceitá-las. Mantém uma cópia de trabalho e uma base para comparar alterações, preservando os arquivos originais.

A cópia exclui `.git`, `.orchestrator`, caches e dependências comuns (`node_modules`, `.venv`, `venv`, `dist`, `build`, `.next`, `__pycache__`), links e arquivos `.env*`. O limite inicial é de 10 mil arquivos ou 256 MB. Projetos Git continuam usando worktrees; operações avançadas de branches e integração exigem Git.

## Por que existe autenticação

A API pode executar comandos e acessar arquivos. A proteção por credencial continua ativa. No modo do executável, o programa gera uma credencial aleatória para aquela execução e a interface local a obtém automaticamente. A credencial não é escrita no executável, na URL ou no HTML.

O acesso automático exige modo desktop explícito, conexão e Host de loopback, origem igual à página, método POST e cabeçalhos da requisição local. As demais rotas da API continuam exigindo Bearer. A interface não pode ser embutida em páginas de outros sites. Essa facilidade atende o operador local; não substitui o bloqueio de sessão do Windows nem autenticação de contas Codex/Claude.

## Atualizar e compilar o controle

Na raiz do projeto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File src/launcher/build.ps1
```

O script usa o compilador .NET Framework disponível no Windows e grava somente o executável de saída local. A interface é compilada a partir do frontend existente quando suas fontes estiverem mais novas. A preparação inicial exige as dependências Python do projeto e `npm ci` em `frontend`.

Após atualizar as fontes, use **Parar** e **Iniciar** para carregar a nova versão do backend e da interface. Feche a janela do controle antes de recompilar o próprio `.exe`.

Fontes do controle: [C#](../../src/launcher/HydraLauncher.cs), [build](../../src/launcher/build.ps1), [backend gerenciado](../../src/hydra_orch/desktop_backend.py). Contrato do chat: [fluxo de conversa](../b_spc/fluxo_conversa.md).

## Verificação desta entrega

O executável compilado foi iniciado com runtime e banco de teste isolados. O navegador conectou sem digitar token, cadastrou uma pasta sem Git e carregou a interface. A parada encerrou o backend e liberou a porta. Há também testes do bootstrap local contra origem externa, cliente remoto, Host indevido, ausência dos cabeçalhos e acesso à API sem Bearer.

A pasta comum foi exercitada com dois pedidos reais ao Codex autenticado, mantendo contexto e sem criar `.git` na origem. Os testes de navegador cobrem retorno ao mesmo terminal após trocar de tela. Medições de abertura da CLI Claude variaram sob carga; reconectar a uma sessão não representa uma promessa sobre o tempo de inicialização da CLI ou de resposta do modelo.

Na rodada final de 14/11/2026, passaram 49 testes de frontend, a checagem TypeScript, 22 testes de conversa/pasta/desktop e 4 testes selecionados do servidor. As 5 jornadas Playwright passaram, incluindo cadastro de pasta comum, dois turnos de conversa, recarga durante execução, histórico, cancelamento e reconexão do terminal por WebSocket. O executável foi recompilado e repetiu o teste de iniciar/parar preservando uma porta ocupada. A instância de uso também abriu com acesso automático e a rota de conversas presente, preservando o servidor anterior.

O verificador do kit, em bundle de produção com dados fictícios, registrou zero falhas em Novo chat e Conversa. Restam 3 avisos em cada tela: controles móveis entre 24 e 44 px, fonte Inter mantida para preservar a interface aprovada e a primeira parada de Tab após o foco programático da navegação. O verificador foi repetido com um adaptador local que aguarda o formulário pronto antes de medir cada tamanho; as capturas da rodada anterior incluíam um estado de carregamento no celular. As capturas e relatórios ficam apenas na saída local de verificação. Leitor de tela real e teste com pessoas não foram executados. O seletor de pastas tem testes de API e de cancelamento; a escolha manual no diálogo nativo ainda precisa ser exercitada pelo operador.

### Rodada do canvas e da paleta — 15/11/2026

A composição A foi implementada com preto predominante e detalhes laranja, incorporando a calibração posterior do dono. Passaram 59 testes de frontend e 8 jornadas Playwright no backend isolado, incluindo canvas, conversa, troca de modelos, coordenação, pasta comum e terminal. Também passaram TypeScript, lint do módulo novo, build de produção e 18 testes Python de coordenação/desktop. A recarga de `/agentes` no servidor desktop foi conferida novamente por um teste específico.

No canvas, a jornada cobre seleção de agente, detalhes, zoom, pan, movimento por teclado, persistência local e recarga; inclui fonte em 200%, lista móvel e axe sem violações sérias/críticas WCAG A/AA. Os processos de teste são controlados: isso comprova a integração local da tela, sem medir velocidade ou qualidade de provedores reais e sem iniciar inferência paga.

O verificador completo do kit sobre bundle de produção registrou **zero falhas** nas três superfícies: Novo chat (2 avisos), Conversa (2) e Área de trabalho (3). Os avisos comuns são áreas móveis herdadas entre 24 e 44px e primeira parada de Tab depois do foco programático. No canvas, o aviso adicional agrupa indicadores preenchidos de seleção (destino, origem e modo de visualização) como se fossem ações concorrentes; eles conservam preenchimento discreto, enquanto a ação principal usa laranja sólido. A checagem de texto sobre imagem é inconclusiva para o fundo pontilhado; textos ficam sobre cards opacos, inspecionados nas capturas. Bordas de controles têm contraste de 3,25:1 contra o hover mais claro; texto principal e botão laranja passam os pares do documento visual.

As páginas inteiras de desktop/celular e a prancha de simulações foram inspecionadas. Leitor de tela real e testes com pessoas continuam pendentes; a árvore semântica automatizada não substitui esses testes. Relatórios e imagens ficam em `ws/b_output/conversation/kit_ready/` e `ws/b_output/canvas/`, ignorados pelo Git. A interface compilada localmente está pronta; use **Parar → Iniciar** no controle quando puder interromper o trabalho atual para carregar também o backend atualizado.

### Rodada de conversa e atualização por eventos — 15/11/2026

Passaram **60 testes de frontend**, **9 jornadas Playwright**, **25 testes Python** de conversa, coordenação e observação, TypeScript, lint dos módulos alterados e build de produção. O subconjunto de cinco testes do protocolo/subagentes foi repetido após os ajustes. O navegador verificou arrasto pelo corpo do card, preservação da seleção, troca A→B→A na mesma conversa, Markdown e compositor acessível após rolar um histórico longo, no desktop e no celular. Um evento controlado acrescentou um subagente ao mapa com a consulta periódica ainda pendente (limite de asserção: 1,8s). Os testes do subprocesso confirmam que frames reais do parser viram observações, persistem e entram no replay. Isso não mede delegação ou qualidade de provedores reais.

O seletor de combos dentro da configuração foi exercitado em uma repetição da jornada: abertura sobre o diálogo pai, busca sem acentos, escolha e fechamento sem disparar inferência. A jornada essencial com pasta e agente já selecionados exige escrever e **Enviar** (ou Enter); para outra pasta, são duas ações, abrir a busca e escolher. A troca de modelo exige abrir a configuração, abrir a busca de modelo, escolher e confirmar para os próximos envios. Nenhuma mensagem precisa ser recriada para a troca.

Verificador do kit no bundle de produção: **Novo chat: 0 falhas/2 avisos; Conversa: 0/3; Área de trabalho: 0/3**. Permanecem os avisos de primeira parada de Tab depois do foco programático e alvos herdados da navegação menores que 44px. Na conversa, a linha compacta de acesso/conexão/modo gera o aviso de metadados separados por pontos; foi mantida porque permite conferir a configuração efetiva junto do envio. No canvas, o aviso de ações concorrentes refere-se a seleções de navegação, origem e modo. As ações novas do compositor têm alvos de 44px no celular. A leitura de contraste sobre o fundo pontilhado permanece inconclusiva para o motor; cards têm fundo opaco.

Foram inspecionados desktop/celular, árvore semântica e prancha de alto contraste/simulações; teclado, Esc e retorno do foco foram exercitados no diálogo da conversa. Leitor de tela real e teste com pessoas continuam não verificados. O build mantém o aviso de chunk acima de 500KB; esta rodada não redesenhou o carregamento de módulos. A instância pessoal em uso foi preservada. Para carregar o novo adaptador de eventos, use **Parar → Iniciar** pelo controle e recarregue a página.

### Correção do limite no planejamento — 15/11/2026

A investigação do registro local confirmou uma tentativa interrompida no planejador, depois de leitura, execução de pytest e tentativa de reparo de diretório temporário. Não havia plano ou execução de workers vinculada. O limite interno de 180s estava sendo apresentado como limite geral da coordenação e com uma mensagem indevida de resultados para revisão.

A correção mantém os limites, distingue a etapa do timeout e acrescenta a saída estruturada de análise. A leitura inicial é fornecida em um pacote limitado, e a orientação do planejador exclui testes, escrita e reparo de ambiente dessa etapa. Passaram **32 testes Python** de conversa e coordenação, incluindo relatório sem workers com acesso de leitura/escrita, validação de plano, limites de planejamento/revisão/execução, cancelamento e preservação do histórico. A validação usou processos controlados, sem chamada nova ao combo real ou consumo de provedor. Para carregar a correção do backend, use **Parar → Iniciar**; a tentativa antiga mantém seu erro original no histórico.

### Compactação, painéis e catálogo — direção aprovada em 15/11/2026

Construção autorizada pelo dono após as três imagens do [plano de compactação](../../design/direcoes/compactacao-plano.md). A marca e o preto predominante foram preservados.

- O botão **Aparência e painéis**, na barra de abas, abre densidade compacta/confortável/ampla, escala de 80–120%, fontes independentes de conversa e terminal, largura de leitura focada/expandida e controles de visibilidade. As mesmas opções estão nas configurações. Alterações são imediatas e locais ao navegador. Preferências locais novas têm precedência sobre uma densidade antiga recebida do servidor; tamanhos inválidos são limitados na leitura do storage.
- Sidebar, divisão entre painéis e detalhe de agentes aceitam redimensionamento. Nos novos divisores, setas ajustam e Home ou duplo clique restauram. A seleção é preservada ao ocultar o detalhe; escolher um card pode revelá-lo novamente. Restaurar tamanhos não apaga conversas nem fecha abas.
- Sidebar e seletor da área de trabalho usam a mesma árvore: projeto/pasta cadastrada → conversas, execuções e subpastas cadastradas. Somente caminhos ancestrais reais no mesmo host são agrupados, respeitando segmentos e regras de maiúsculas do Windows. Não há varredura do disco. Pais e grupos podem ser recolhidos, e os estados ficam salvos; filhos e páginas são consultados ao expandir. Grupos de trabalho têm páginas de dez itens. A busca inicial de conversas considera até cem resultados e pede refinar quando necessário; a busca de execuções informa que vale para a página atual.
- Os cards de cotas mostram no máximo três modelos. **Ver modelos (N)** abre catálogo com busca e páginas de 10/25/50 itens. Esta paginação limita a renderização no cliente; o inventário recebido continua completo. As contas para próximas execuções ficam recolhidas em cada card. Não foram inventados limites de tokens.
- **Adicionar pasta** chama diretamente o Explorer no desktop. Cancelar mantém o rascunho e não cadastra nada. Em navegador sem integração desktop, a entrada de caminho continua disponível. O seletor moderno usa um dono no próprio processo auxiliar: encerrar o auxiliar não deve desabilitar o controle principal. Abertura e cancelamento por Esc foram exercitados no Windows com o helper compilado; não foi selecionada uma pasta pessoal nesse teste. O build do launcher preserva a imagem antiga em `.orchestrator/launcher-build/` ao substituir `Hydra.exe`, permitindo atualizar o arquivo sem encerrar o backend ativo.
- Saíram os atalhos predefinidos de prompts. O histórico com setas guarda apenas envios aceitos, separados por projeto/conversa, preserva o rascunho e tem limpeza/desativação nas preferências. Menus, seleção, IME e navegação multilinha têm precedência. O histórico local tem limites por contexto, quantidade de contextos e volume total.
- Tab aceita uma continuação visível, sem enviar; Esc dispensa. A implementação usa histórico local e sugestões derivadas de tarefa pendente, resultado com diff, falha/cancelamento ou próximos passos explícitos da resposta. Não é previsão semântica livre por LLM. Essa ampliação continua dependendo do contrato de custo/contexto previsto no plano; nenhuma inferência paga por digitação ou carregamento foi habilitada.

**Catálogo OmniRoute:** a primeira lista consulta somente combos (`include_models=false`); modelos são carregados à parte quando solicitados ou pesquisados. A configuração de uma conversa existente pode aquecer o mesmo cache antes de abrir o diálogo. Espera, erro e vazio têm mensagens distintas, e a lista de destinos tem paginação. O backend consulta certificados em lote e reutiliza a versão da CLI; a validação de compatibilidade antes de executar continua obrigatória.

Medição contra o gateway local, usando o serviço novo com um banco de fixture separado e vazio, sem inferência: dez combos em **1,127s** na primeira leitura e **0,013s** na seguinte; lista completa de 2.295 modelos em **3,464s** e **0,083s** com cache. São medidas da camada de serviço, não do HTTP nem do clique até renderização. A medição anterior de 3,606s/0,828s era da API agregada em outro estado de cache; não deve ser usada para afirmar um percentual rigoroso de melhoria. A resposta inicial nova com os combos ficou em aproximadamente 2,5KB no formato serializado do probe. Nenhuma configuração persistida do gateway foi alterada para essa medição.

**Verificação da rodada:** 70 testes de frontend, 51 testes Python de conversa/coordenação/rotas/desktop, lint, TypeScript/build de produção e compilação Windows aprovados. Treze jornadas Playwright passaram no ambiente isolado, incluindo terminal, histórico, anexos, troca A→B→A, agentes ao vivo, redimensionamento e persistência. O comando normal ignora a auditoria pesada opcional; ela foi executada separadamente no bundle de produção de fixture e passou, junto das quatro jornadas novas.

Verificador completo do kit + axe no bundle de produção: **Novo chat: 0 falhas/2 avisos; Área de trabalho: 0/1; Contas e consumo: 0/0**. Um aviso de entrelinha envolve um elemento auxiliar do compositor; os dois avisos de primeira parada de Tab decorrem do foco programático de entrada na tela, preservado para orientar a navegação SPA. Texto, alvos, zoom de 200%, alto contraste, páginas inteiras e lista móvel foram inspecionados com dados fictícios. Leitor de tela real e testes com pessoas não foram realizados. O build mantém o aviso de chunk acima de 500KB.

No teste Python de timeout, a janela artificial de 30ms foi ajustada para um segundo para permitir persistir o evento real no SQLite antes do cancelamento; isso elimina uma corrida de disco no Windows e não altera limites de produção. Os primeiros erros das jornadas por seletores antigos foram corrigidos para refletir a nova hierarquia e seções recolhíveis; as jornadas completas foram repetidas.

Relatórios, capturas e medições locais ficam em `ws/b_output/compact-workbench/`, `compact-*-final.log`, `compact-python.log` e `catalog_latency_after.json`, ignorados pelo Git. O bundle com autenticação fictícia usado na auditoria está em `ws/b_output/compact-production/` e não deve ser usado como interface pessoal. O build normal em `frontend/dist/` não recebe esse token de fixture. `Hydra.exe` permanece na raiz.

Para testar tudo na instância pessoal, conclua os trabalhos ativos, use **Parar**, feche o controle antigo, abra o `Hydra.exe` da raiz e use **Iniciar**. Recarregue a interface. A instância em execução foi preservada durante a construção; o backend precisa dessa reinicialização para usar o catálogo atualizado.
