# Hydra — plano proposto para espaço, navegação e composição

Data: 2026-11-15. Status: proposta, aguardando escolha visual; não autoriza ou comprova implementação. O pedido foi mostrar imagens primeiro e planejar em seguida. Foram apresentadas três cenas da mesma direção: área de trabalho, conversa/preferências e cotas. São mockups com dados fictícios, sem juízo externo e sem validação funcional. Preto predominante e laranja pontual seguem a preferência vigente; a marca atual será preservada.

Bases: [primeira ideia](compactacao-primeira-ideia.md), [diagnóstico com medição](compactacao-diagnostico.md), [correções do dono](../correcoes.md), [sistema visual](../../DESIGN.md). Após a escolha, registrar a composição aprovada em `DESIGN.md` e ajustar este plano. Não há mudança de backend, frontend ou launcher nesta entrega.

## 1. Densidade e painéis ajustáveis

Objetivo: recuperar área útil sem obrigar a diminuir todo o sistema pelo zoom do navegador.

- Criar densidades compacta, confortável e ampla, regulando altura de linhas, cabeçalhos, campos, botões e espaçamentos. Proposta inicial no desktop: texto de interface de 13–14px e linhas de navegação de 28–32px no compacto. Valores finais passam pela verificação de leitura e teclado; controles para toque mantêm área de 44px.
- Oferecer escala da interface e fontes separadas para conversa e terminal; preservar o zoom independente do canvas. Evitar transformações CSS que desfocam texto ou alteram indevidamente coordenadas de ponteiro.
- Reaproveitar o redimensionamento existente da sidebar. Adicionar divisores ajustáveis ao detalhe de agentes e ao modo dividido, com limites mínimos, dupla ação para restaurar, suporte ao teclado e indicação visual discreta.
- Permitir mostrar/ocultar sidebar, detalhe e barra de status. Preservar a seleção ao ocultar. Manter um botão sempre acessível para reabrir painéis e um comando para restaurar o layout inteiro.
- Persistir preferências e migrar as salvas hoje com valores seguros; adaptar o layout a janelas menores sem deixar conteúdo principal inacessível.

Áreas previstas: `frontend/src/store/layoutStore.ts`, `frontend/src/index.css`, casca da aplicação, componentes de painel e preferências. Preservar o comportamento existente de arrastar cards, navegação do canvas e terminais.

Aceite: reduzir a ocupação de cabeçalhos em relação às capturas do pedido; redimensionar/ocultar/reabrir sem perder conversa, sessão ou posição dos cards; restaurar os valores padrão; recarregar e recuperar preferências. Verificar zoom a 200%, foco visível, teclado e viewport pequena.

## 2. Projetos como pais da navegação

Objetivo: fazer a mesma organização funcionar na sidebar e no seletor da área de trabalho.

- Mostrar o projeto/pasta raiz cadastrado como primeiro nível. Dentro dele, conversas, execuções e subpastas vinculadas. Recolher cada seção ou projeto independentemente e permitir ocultar grupos inteiros nas preferências de navegação.
- Usar vínculos reais dos registros. Raízes independentes continuam independentes; caminhos apenas visualmente parecidos não bastam para deduzir parentesco. Normalizar caminhos Windows e conferir a relação por segmentos; não varrer todo o disco nem assumir a unidade como projeto pai.
- Títulos em uma linha com reticências e nome completo acessível. Mostrar contagens e estado ativo sem repetir blocos grandes de texto.
- Carregar filhos sob demanda e limitar o volume inicial. Reutilizar a paginação existente das execuções onde possível; oferecer mostrar mais/busca para grupos extensos. A busca pode revelar o projeto pai do resultado e expandi-lo sem perder contexto.
- Persistir expansão/recolhimento; ao abrir um item de outro projeto, revelar seu caminho na árvore. Distinguir recolher, ocultar e excluir, sem esconder remoção em um ícone ambíguo.

Áreas previstas: `frontend/src/component/Sidebar.tsx`, `frontend/src/feature/canvas/AgentWorkspacePage.tsx` e consultas de projetos/conversas. Antes de alterar contratos, conferir se os dados atuais já informam todos os vínculos necessários.

Aceite: os mesmos pais aparecem nos dois lugares; escolher uma conversa leva ao canvas correspondente; uma árvore com centenas de itens não expande tudo por padrão; seleção e estado de execução não se perdem ao recolher.

## 3. Cotas e inventários limitados

Objetivo: manter cards comparáveis mesmo com milhares de modelos.

- Card do provedor mostra estado, disponibilidade observada da janela, redefinição e conta; limitar a prévia a três modelos e abrir a lista completa em “Ver modelos (N)”. Não inventar orçamento de tokens quando a fonte só fornece porcentagem.
- Lista completa em painel lateral ou diálogo amplo com busca, filtro de provedor e paginação de 10/25/50 itens. Mostrar contagem total e página atual; a tela de contas não deve renderizar o inventário inteiro novamente abaixo dos cards.
- Primeiro limitar a renderização. Se a API continuar transferindo um inventário excessivo, acrescentar paginação/filtros no servidor com contrato explícito. Não chamar de carregamento por página um recorte apenas visual de todos os dados recebidos.
- Favoritos/recentes aparecem nos mockups como possibilidade, mas não são requisito desta entrega; só incluí-los com persistência e comportamento definidos, sem botões decorativos.

Áreas previstas: `frontend/src/feature/quota/ProviderQuotaCard.tsx`, `frontend/src/feature/quota/QuotaAccountsPage.tsx` e endpoint de inventário se necessário.

Aceite: altura dos cards não cresce com 2.000 modelos; busca/paginação encontram os últimos itens; estados sem dados/erro/atualizando permanecem distintos; números continuam refletindo a fonte real.

## 4. Escolha de pasta e catálogo de modelos

Objetivo: reduzir cliques e espera na preparação de um chat.

- No desktop local, “Adicionar pasta” chama diretamente a seleção nativa do Windows. Reaproveitar o endpoint existente e avaliar diálogo moderno do Explorer com proprietário e primeiro plano corretos; manter cancelamento normal sem erro. Não bloquear a interface enquanto o operador escolhe.
- No navegador sem integração nativa, oferecer entrada de caminho claramente identificada. Selecionar um projeto já cadastrado continua sendo busca/árvore própria, sem abrir Explorer desnecessariamente.
- Ao abrir modelos/combos, apresentar combos disponíveis e itens recentes sem digitar, com busca opcional. Mostrar carregamento verdadeiro, erro acionável e vazio verdadeiro como estados diferentes.
- Medir gateway, versão da CLI, descrição de compatibilidade, SQLite, serialização e renderização. A medição atual confirma 3,606s e 0,828s para duas consultas da API; não identifica sozinha a contribuição de cada etapa.
- Remover do caminho de abertura o trabalho repetido: cache/reuso de descrições coerente com a definição do combo, consulta agrupada de certificados e leitura da versão da CLI reaproveitada. Avaliar retorno separado de combos e inventário de modelos, com carregamento progressivo ou paginação. Não remover controles de compatibilidade para ganhar velocidade.
- Exibir opções do cache enquanto atualiza, identificar falhas e disponibilizar atualização manual. Uma alteração no combo invalida a informação apropriada; a verificação final do backend continua antes de executar. Carregar o catálogo nunca dispara inferência ou certificação paga.

Áreas previstas: `frontend/src/page/NovoChatPage.tsx`, `frontend/src/feature/chat/ConversationRoutePicker.tsx`, `src/launcher/HydraLauncher.cs`, endpoint do launcher, `src/hydra_orch/core/conversation_route.py` e `src/hydra_orch/bridge/omniroute_client.py`.

Aceite: um clique abre o seletor nativo; cancelar preserva o rascunho; combos aparecem sem busca; catálogo em cache pode ser visto imediatamente enquanto atualiza; medir novamente API e tempo até primeiro resultado visível no desktop. Definir meta de latência a partir do perfil das etapas, sem prometer um número ainda não validado.

## 5. Compositor, histórico e conclusão inteligente

Objetivo: escrever e repetir pedidos com menos trabalho, mantendo controle sobre o envio.

- Remover os três atalhos de prompts predefinidos do início. Conservar o campo principal, contexto do projeto e controles do agente/conexão/modelo junto do compositor fixo.
- Histórico de prompts enviados por contexto de projeto/conversa, com limite de retenção e opção de limpar/desativar. Cima/baixo percorrem o histórico apenas nos limites de navegação do campo, sem seleção e sem menu aberto. Guardar o texto não enviado e restaurá-lo ao sair do histórico.
- Mostrar no máximo uma continuação em cinza após o texto digitado. Tab aceita somente se a sugestão estiver visível e aplicável; Esc dispensa. Sem sugestão, Tab continua a navegação de foco. Menus de menção/comando têm precedência; respeitar seleção, IME e texto multilinha.
- Para o próximo passo contextual, usar o estado real da conversa, plano e última resposta. Uma previsão por LLM exige caminho explícito de sugestão somente textual: nenhum comando, ferramenta ou envio automático. Gerar após eventos relevantes/pausa com cache, cancelamento de resposta obsoleta e limite de frequência, sem requisição por tecla. Usar conexão/modelo configurados, sinalizar indisponibilidade e oferecer desativação; definir orçamento antes de habilitar inferência recorrente. Aproveitar histórico local quando útil, sem apresentar simples repetição como previsão semântica comprovada.
- A sugestão não entra no histórico como pedido do usuário até ser aceita e enviada. Nunca sobrescrever o que o operador já digitou com uma resposta que chegou atrasada.

Áreas previstas: `frontend/src/feature/composer/PromptComposer.tsx`, página inicial, estado do compositor e serviço de sugestões a definir após o contrato de custo/contexto. A conclusão semântica é uma entrega própria, depois de estabilizar histórico e teclado.

Aceite: retirar atalhos; recuperar/restaurar rascunho no histórico; aceitar/dispensar sugestão sem enviar; navegar com Tab normalmente quando não há sugestão; menus e composição de caracteres continuam funcionando; respostas atrasadas não alteram o texto; nenhuma inferência é disparada apenas por abrir a tela.

## Ordem e verificação

1. Validar a composição das três imagens e registrar os ajustes do dono.
2. Entregar densidade/painéis nas telas de conversa e área de trabalho, com persistência e restauração.
3. Entregar hierarquia na sidebar e no seletor de trabalho.
4. Entregar cotas limitadas e catálogo de modelos, instrumentando e comparando a latência.
5. Entregar seleção nativa direta e remover atalhos de chat.
6. Entregar histórico/teclado; em seguida, conclusão contextual com comportamento e custo definidos.

Cada entrega deve permanecer pequena e verificável, com no máximo três telas ajustadas por rodada. Testes automatizados devem cobrir transições relevantes de layout, parentesco/paginação, invalidação de catálogo, cancelamento do seletor e precedência de teclas; evitar testes que apenas reproduzem CSS. Executar build e checks exigidos pelo frontend, testes Python pertinentes quando houver alteração de backend, revisão manual de teclado/zoom e fluxo real no desktop. Fotografias ou mockups não substituem esses checks. Confirmar que arrastar cards, atualizações de agentes, terminal e troca de modelo preservam o funcionamento existente. Publicar apenas mudanças verificadas, preservando trabalho concorrente e seguindo `AGENTS.md`.
