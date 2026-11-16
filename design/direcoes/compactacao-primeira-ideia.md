# Hydra — estudo de espaço e personalização

Status: registro da proposta visual, aprovada integralmente pelo dono em 15/11/2026 e autorizada para construção. As imagens foram apresentadas antes do [plano](compactacao-plano.md). Este documento preserva a ideia e o limite da evidência dos mockups; as provas da implementação ficam no manual Windows.

Primeira ideia: conservar o canvas livre e o preto aprovado, mas usar a composição de uma bancada de desenvolvimento. Navegação curta, barra de atividade estreita, projetos como pais de conversas/execuções, seções recolhíveis e divisores redimensionáveis. O conteúdo ganha área útil pela redução de cabeçalhos e espaçamentos; texto e zoom do canvas não dependem de uma redução global indiscriminada.

Imagens propostas, com dados fictícios: área de trabalho compacta com árvore de projetos e inspector ajustável; chat com navegação recolhida, sugestão inline e histórico de prompts; cotas com prévias limitadas de modelos e catálogo paginado; preferências de densidade e tamanho. Não reproduzir contas, identificadores ou pedidos reais das capturas do operador.

No desktop, propor tipografia de interface entre 13 e 14px e linhas de navegação entre 28 e 32px; textos auxiliares a partir de 12px. No toque, manter alvos de 44px. Fonte da conversa e do terminal é regulada separadamente. Oferecer modos compacto, confortável e amplo, além de restaurar o layout.

Tab aceita somente uma sugestão visível e segue a ordem de foco na ausência dela; menus de menção/comando têm precedência. Setas de histórico entram apenas com cursor no início/fim e sem seleção/menu aberto, preservando rascunho. A sugestão contextual é proposta, não funcionalidade já implementada, e não envia uma mensagem sozinha.

Adicionar pasta deve abrir diretamente o seletor nativo no modo desktop. A busca de projetos já cadastrados e o cadastro de uma pasta nova são ações diferentes. Sem suporte nativo, oferecer entrada de caminho claramente identificada.

O catálogo deve mostrar resultados iniciais sem exigir texto na busca. A causa da demora precisa de diagnóstico de frontend, API e gateway; não atribuir o atraso à pesquisa sem evidência. Catálogo e cotas não podem executar inferência para carregar opções.

As imagens são mockups gerados para validação de composição. Não representam implementação, teste de acessibilidade, desempenho medido ou integração pronta. A ausência de avaliação externa deve ser declarada; a escolha pertence ao dono.
