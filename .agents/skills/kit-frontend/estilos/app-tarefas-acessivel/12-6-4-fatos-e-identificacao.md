### 6.4 Fatos e identificação

Fatos aparecem em lista, cada um com ícone e valor. Dê destaque ao valor necessário à escolha. Local, prazo, quantidade ou preço são exemplos; preserve apenas os dados pertinentes ao produto.

No detalhe, os fatos podem usar caixas individuais. Na lista ampla, distribua-os ao lado da identificação conforme a receita de catálogo. Um fato desconhecido deve permanecer desconhecido; não use zero, “gratuito” ou “disponível” como substituto automático.

Avatar de foto usa recorte circular e `object-fit: cover`. Sem foto, use iniciais calculadas a partir de um nome de exibição. O avatar não substitui o nome escrito.

### 6.5 Selos, avisos e mensagens temporárias

**Selo:** texto curto de situação, com ícone opcional e fundo semântico. **Aviso de página:** ícone, título opcional, mensagem e ação pertinente. **Mensagem temporária:** mesmo aviso em camada acima do conteúdo, próximo ao topo, com controle de fechamento.

Informação necessária à tarefa deve estar disponível na própria tela ou no histórico adequado. Não dependa exclusivamente de uma mensagem que desaparece. Evite acumular mensagens idênticas durante tentativas repetidas.

Erro precisa dizer o que aconteceu e a próxima ação: “Não deu para abrir. Confira a conexão e tente de novo.” O texto final deve refletir a causa conhecida, sem inventá-la.

### 6.6 Busca e filtros

Busca é uma superfície com lupa, campo e atalho de voz opcional. O campo pode ter rótulo visualmente oculto, desde que mantenha nome acessível. Os demais campos têm label visível.

Filtros rápidos usam `ui-chip`, com texto, estado pressionado e marca de seleção. Eles quebram linha; não introduza rolagem horizontal obrigatória. No catálogo amplo, os mesmos filtros ficam na lateral. Mudar busca ou filtro reinicia a paginação.

**Paginação:** controles Anterior e Próxima, identificação da página e faixa dos itens exibidos. O catálogo da origem utiliza páginas de seis itens; esse tamanho pode ser adotado como configuração inicial, sem transformá-lo em regra funcional universal. Se o contrato fornecer total e última página, mostre-os. Sem total, não invente “de N”; use a página e a faixa conhecidas.

Ao trocar de página, preserve busca e filtros, indique carregamento e leve a leitura ao resumo dos resultados. A escolha de persistir filtros na URL ou na sessão depende dos dados do destino; não coloque informação sensível em um endereço compartilhável.
