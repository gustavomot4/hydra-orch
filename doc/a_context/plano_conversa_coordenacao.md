# Próxima rodada de conversa e coordenação

## Estado verificado

| Pedido | Comportamento observado | Próximo passo |
| --- | --- | --- |
| Modelo e marca no chat e na Área de trabalho | O histórico da conversa conserva a rota escolhida por turno. No OmniRoute, `target_ref` pode identificar o combo, como `free-agent`. Alguns eventos de subagente nativo já carregam `model`, quando informado pela CLI. | Receber e registrar o modelo e a empresa observados por tentativa. Mostrar a origem dessa informação nos detalhes. |
| Seleção automática | No swarm gerenciado, `auto_route` é opcional. A escolha atual, somente no OmniRoute, cruza nomes de combos verificados com palavras relacionadas à tarefa e ordena por duração do teste. Modo direto usa a rota da conversa. Delegações nativas são observadas por eventos da CLI. | Selecionar pela capacidade exigida e pela cota conhecida, com política explícita para cada forma de execução. |
| Falha da loja | Os dois comandos apontavam para binários em `frontend/node_modules` numa worktree onde os módulos esperados estavam ausentes. O coordenador cria as tarefas de edição com `max_repair_attempts=0` e limita as tentativas do run à quantidade de tarefas. | Preparar dependências no diretório do pacote e habilitar reparo coordenado limitado, com diagnóstico por tipo de falha. |
| Imagem no chat | A Onda 1 passou a compartilhar o serviço de anexos entre upload e conversa. Em `76e736e`, o chat de início ainda traduzia qualquer 404 como ausência da rota. A lista existente indica nome e estado do arquivo. | Verificar criação e continuação com imagem no mesmo servidor, inclusive após reinício. Adicionar miniatura no compositor. |
| Rolagem de conversa longa | Em `76e736e`, seguir a saída chamava `scrollIntoView` no fim do histórico e podia rolar contêineres ancestrais. | Exercitar leitura fora do fim, streaming, retorno ao fim e janela baixa nas jornadas de regressão. |
| Área de trabalho | O cabeçalho mantém uma faixa acima da barra que seleciona o pedido. O canvas usa rótulos em conexões que competem por espaço. | Reunir seletor e Novo pedido na faixa compacta e resolver colisões dos rótulos. |
| Alterações | A tela atual parte de uma execução e oferece revisão de conflitos, artefatos e pacote de PR. A aplicação de mudanças de conversas passou a ter endpoint próprio na Onda 2. | Abrir diretamente a revisão da conversa com lista de arquivos, diff e ação de aplicação. Manter os fluxos de execução no acesso avançado. |

## Ordem de entrega e critérios de aceite

### 1. Preparar e reparar verificações do swarm

- Derivar o diretório de trabalho e as dependências dos arquivos de manifesto presentes na base da tentativa, inclusive quando o `package.json` veio de uma tarefa anterior. Honrar o gerenciador e o lockfile do projeto. Usar instalação reproduzível com lockfile no ambiente isolado e registrar a preparação como evidência. Projetos sem lockfile precisam de um caminho documentado, com efeito sobre resolução de versões explícito.
- Antes de typecheck e build, verificar se os executáveis necessários estão disponíveis. Reconhecer falha de preparação, teste de produto, erro transitório do provedor, esgotamento de orçamento e violação de escopo. A preparação só deve escrever na cópia da tentativa, com comandos e diretórios validados pelas regras do runner.
- Para uma falha corrigível de código, preservar a revisão rejeitada e devolver ao worker o check, o diretório, o exit code e a saída redigida. Uma nova tentativa deve aproveitar o patch anterior e manter os mesmos caminhos autorizados. Autorizar inicialmente até um reparo por tarefa dentro de um orçamento de run que reserve tentativas para as tarefas dependentes. Em repetição da mesma causa ou esgotamento do orçamento, apresentar o bloqueio e a evidência.
- Critério de aceite: reproduzir em fixture o plano de dois estágios da loja, com uma worktree sem `node_modules`. Testar preparação bem-sucedida, erro de instalação e um erro TypeScript real que a tentativa de reparo corrige. Conferir que o projeto original e a primeira tentativa são preservados. O run histórico permanece como evidência da falha observada.

### 2. Exibir a identidade observada e selecionar rotas

- Registrar o executor, rota solicitada, modelo e empresa observados, fonte da informação e motivo da seleção. Registrar por tentativa para representar fallback e troca de modelo no meio de um run. Ler metadados reais do provedor ou evento da CLI. Quando a conexão reportar apenas o alias, mostrar **Modelo não informado** e conservar o combo nos detalhes. Verificação local identifica Hydra.
- Adotar a opção **Automático** para trabalho gerenciado. Classificar planejamento, UI, código, revisão e testes. Filtrar por ferramentas, contexto, multimodalidade quando houver imagem, permissões, cota e custo admitido. Usar resultados observados do projeto e uma política configurável de desempate. O modo manual continua disponível.
- Aplicar a mesma política antes de abrir workers ou sessões gerenciadas pelo Hydra, incluindo modelo em modo direto quando o executor aceita a seleção. Para subagentes nativos, usar parâmetros do executor quando o protocolo oferecer controle. Onde a CLI decide internamente, exibir a rota como escolha do executor e só atribuir o modelo quando houver metadado.
- Critério de aceite: dois perfis com candidatos diferentes, cota esgotada com fallback registrado, imagem que exige modelo multimodal, alias sem modelo informado e histórico com duas tentativas de provedores diferentes. Nenhum nome de combo deve ser apresentado como modelo confirmado.

### 3. Chat, Área de trabalho e revisão visual

- **Chat.** Manter a navegação e o preto predominante do Hydra. Usar leitura em coluna central, mensagens do usuário compactas e uma barra de composição com prévia de imagens, remoção e estados de upload. Mostrar modelo e empresa por resposta. Deixar a atividade técnica recolhível. Seguir a saída só quando o leitor estiver perto do fim e oferecer retorno ao fim quando estiver lendo acima.
- **Área de trabalho.** Colocar Novo pedido ao lado do seletor no cabeçalho compacto. Mostrar modelo confirmado no card e combo e motivo da escolha no inspetor. Ancorar conexões às dimensões reais dos cards e proteger rótulos contra colisão. Manter o modo Lista navegável por teclado.
- **Alterações.** Começar com projeto, conversa, arquivos e diff. A ação **Aplicar ao projeto** deve indicar o destino, o estado e arquivos conflitantes. Expor o fluxo de PR, artefatos e resolução avançada sob demanda. Usar mensagem de conclusão quando o projeto já tiver o mesmo conteúdo.
- Critério de aceite: compor e remover imagem por teclado, enviar e continuar no mesmo chat, diferenciar erro de upload de erro de rota, manter o histórico durante streaming e revisar/aplicar sem perder a seleção. Percorrer telas a 320 e 375 px, desktop, texto ampliado e cores forçadas. Validar as capturas do novo visual com o usuário antes da implementação da proposta.

Os protótipos locais em `ws/b_output/proposta-chat/` usam um projeto fictício e dados de execução ilustrativos. A referência de marca para o símbolo de exemplo é a [página de diretrizes da OpenAI](https://openai.com/brand/).
