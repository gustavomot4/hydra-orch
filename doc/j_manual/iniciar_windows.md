# Usar o Hydra no Windows

## Abrir e parar

O executável local fica na raiz do projeto: `Hydra.exe`, ao lado do `README.md`. Ele usa este checkout e as instalações locais de Python e Node; mantenha o arquivo na raiz ou use um atalho para ele. O build gera esse arquivo localmente; o binário não é versionado no Git.

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
| **Organização avançada** | Hosts, workspaces, agentes e execuções antigas. Não é necessário abrir essa estrutura para conversar. |

Escolha uma pasta, escreva uma mensagem e clique em **Enviar**. Para adicionar outra pelo executável, abra **Adicionar pasta → Selecionar pasta** e escolha no diálogo do Windows. Também é possível informar o caminho e clicar em **Usar esta pasta**. Clicar em uma pasta da barra lateral abre Novo chat com ela selecionada. A busca encontra pastas e pesquisa os títulos das conversas em todo o histórico, inclusive fora da página atual. A área **Alterações** reúne os resultados para revisão.

O acesso começa em leitura. As opções permitem editar uma cópia isolada. Para reabrir um trabalho, clique no título em **Conversas**. A conversa mantém contexto; não é preciso criar outra sessão ou abrir um terminal a cada mensagem. O terminal restaura o processo já aberto quando você sai e volta à tela.

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
