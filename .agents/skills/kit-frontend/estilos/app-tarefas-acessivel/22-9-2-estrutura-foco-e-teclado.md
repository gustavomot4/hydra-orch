### 9.2 Estrutura, foco e teclado

- Um título principal por tela. Título da aba no formato “Tela · Produto”. Ao navegar, o foco vai ao título, preservando um controle já em uso durante uma atualização do conteúdo.
- Navegação e conteúdo principal têm nome acessível. Disponibilize um atalho para pular ao conteúdo; em SPA, mova também o foco por script quando necessário.
- Botões e campos conservam o alvo mínimo definido por `--ui-tap`. Os rótulos podem crescer; a altura declarada é mínima.
- O foco permanece visível e livre de topo, menu, rodapé e mensagens temporárias. A compensação de rolagem precisa considerar a altura efetiva das barras, inclusive com letra ampliada e quebra de linha.
- Radio, checkbox, botão, link e campo usam semântica nativa. Não transforme uma `div` clicável em substituto sem teclado e nome acessível.
- Erros de campo são associados ao controle. Falha importante usa anúncio apropriado; atualização não urgente usa região de status. Carregamento indica `aria-busy` na região pertinente.
- Cor tem reforço em texto, símbolo, marca ou posição. Contagem, seleção, etapa e erro são compreensíveis sem distinguir a matiz.
- O diálogo prende o foco, torna o fundo inativo à interação assistiva, fecha com Escape quando permitido e devolve o foco ao acionador.
- Refluxo, zoom e letra ampliada conservam texto, ação e leitura. Não use `overflow-x: hidden` para esconder um defeito de largura.
- Vídeo, imagem, arquivo, áudio e recursos assistivos têm alternativas e nomes coerentes com sua função.

### 9.3 Regras que completam a reprodução

Atalho de pular conteúdo, inatividade assistiva do fundo de diálogo, tratamento robusto de mensagens e compensação dinâmica de barras são critérios para a aplicação de destino. A inspeção visual e a leitura das fontes não verificaram integralmente esses comportamentos na origem. Preserve a aparência e valide essas condições durante a implementação.
