### 6.11 Mídia e conteúdo expansível

Vídeo usa caixa na proporção da receita, título acessível, controles pertinentes e uma alternativa quando o player não abrir. Aulas ou partes aparecem como linhas com título e estado atual. Um serviço externo disponível para incorporar vídeo precisa ser confirmado no destino.

Imagem de catálogo é opcional, com largura do conteúdo, altura limitada e recorte conforme a receita. Texto alternativo depende do significado da imagem. Conteúdo expansível usa `details` e `summary`, com texto de abertura compreensível.

### 6.12 Estados dos componentes

As regras abaixo completam a especificação de estados. A origem mantém o hover discreto; reproduza a geometria e os pares de cor da variante.

| Família | Padrão e hover | Foco | Pressionado ou escolhido | Desabilitado | Erro ou falha |
| --- | --- | --- | --- | --- | --- |
| Botão e link de ação | Mantém a variante; cursor indica ação; texto continua legível | Anel global; no cartão, envolve a área clicável | Botão desloca conforme a receita; seleção usa o par de ação | Par desabilitado; bloqueio real no controlador | Aviso próximo; rótulo e dados conservados |
| Cartão clicável | Superfície e indicação de avanço; sem mudança de tamanho no hover | Contorno do cartão inteiro | Destino abre pela mesma área; não cria seleção sem necessidade | Somente quando houver causa funcional e explicação | Aviso de leitura ou indisponibilidade |
| Campo e busca | Superfície e borda de campo; hover conserva a moldura | Borda de foco e anel externo da receita | Digitação conserva valor; busca anuncia resultado | Controle nativo desabilitado com motivo pertinente | Borda, mensagem associada e símbolo |
| Chip e opção | Texto e borda visíveis | Anel no alvo inteiro | Marca, estado acessível, fundo e contorno de seleção | Interação bloqueada; texto ainda identificável | Erro do grupo associado à legenda ou ao campo |
| Interruptor | Trilho, título e apoio | Anel no controle | `aria-checked` e posição da pega | Estado e motivo legíveis | Reverte ou informa falha conforme o contrato |
| Etapas e timeline | Informação de progresso, sem hover de controle | Só recebe foco se for controle real | Etapa atual e feita com texto correspondente | Não aplicável a indicador puramente informativo | Processo interrompido vira estado textual real |
| Selo, aviso e vazio | Informação; sem cursor de ação quando não houver ação | Apenas links e botões internos | Sem seleção artificial | Não aplicável à mensagem | A própria mensagem apresenta a falha |
| Painel | Véu e superfície; conteúdo com rolagem própria | Contido no diálogo e devolvido ao fechar | Controle mantém seu estado usual | Botão de envio bloqueado durante a operação | Mensagem no painel; conserva respostas |
