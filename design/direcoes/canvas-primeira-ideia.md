# Canvas de agentes — estudo para aprovação

Pedido: área infinita navegável com mouse, agentes em cards, linhas de comunicação e acesso ao chat ao selecionar um card. Preservar a interface escura existente, com menos taxonomia técnica exposta. Esta entrega apresenta imagens conceituais; não implementa o canvas.

Primeira ideia, antes de referências: uma mesa de trabalho espacial ocupa a área principal. O coordenador distribui tarefas para cards com agente, destino, estado e última ação. Ao selecionar um card, abre um painel de conversa sem perder a posição do canvas. Linhas representam envio de tarefa, dependência e resultado observados; não inventam mensagens diretas entre workers.

Variações: A, mesa livre com detalhe lateral; B, fluxo por etapas com detalhe no próprio card; C, ilhas por pedido com conversa em faixa inferior. As três usam dados fictícios. Estados têm ícone e texto; navegação também oferece enquadrar, organizar, busca e lista, sem exigir arrasto ou depender de cor.

O usuário deve escolher a composição antes de código de produção. Nenhuma proposta declara que diálogo arbitrário entre agentes, pausa/retomada de workers ou edição ao vivo já existem no runtime.

## Escolha e implementação posterior — 15/11/2026

O dono escolheu a composição A com as cores de C e depois corrigiu: “exagerou no laranja, o principal é preto ainda”. A implementação posterior usa preto e cinzas neutros nas superfícies, com laranja em ações, seleção e detalhes. O estudo acima permanece como registro da etapa conceitual. A direção vigente está em [DESIGN.md](../../DESIGN.md); a jornada implementada e seus limites estão no [manual Windows](../../doc/j_manual/iniciar_windows.md#acompanhar-agentes-na-área-de-trabalho).
