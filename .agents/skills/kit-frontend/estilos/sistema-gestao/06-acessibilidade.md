#### Acessibilidade

Alvo: WCAG 2.2 AA. Este trecho faz parte do piso da ordem de precedência.

- **Contraste.** Texto com 4,5:1 ou mais; texto secundário com 7:1 ou mais; borda de campo, estado de controle, foco e elemento de gráfico com 3:1 ou mais. Use só os pares da tabela abaixo. Par novo, inclusive o de uma cor que eu informar na seção 1, entra na tabela com a razão calculada antes de ir para a tela; se reprovar, pare e pergunte.
- **Tamanhos.** Nenhum texto abaixo de 14 px e rótulo de campo em 16 px (regra deste padrão; a WCAG não fixa tamanho de fonte). Controles com pelo menos 44 × 44 px.
- **Foco.** Sempre visível: contorno de 3 px com 2 px de afastamento, em `--primaria` nas áreas claras e em `--destaque` na barra lateral. Nunca encoberto: a página usa `scroll-padding-bottom` igual à altura da barra de ações fixa.
- **Teclado.** Navegação completa por teclado. Diálogos prendem o foco e o devolvem ao fechar. O primeiro elemento da página é o botão “Pular para o conteúdo”, que move o foco por script para o `<main>` (âncora não serve em rota em hash). A cada rota, `document.title` vira “Tela · Produto” e o foco vai para o `h1`. `<nav>` e `<main>` têm nome.
- **Estrutura.** Hierarquia de títulos sem saltos. Rótulo visível é obrigatório em campo de formulário; só pode ser ocultado na busca (com botão rotulado) e em ações de linha, e nesses casos o nome acessível continua.
- **Avisos.** Sucesso, faixa e total depois de filtrar, quantidade de resultados da busca e aviso de registros fora da área visível usam `role="status"`. Erro de leitura e de gravação usam `role="alert"`. Região em carregamento recebe `aria-busy="true"`.
- **Cor.** Nenhuma informação só por cor: situação tem o nome escrito, série de gráfico tem legenda, item escolhido tem contorno, erro tem ícone e mensagem.
- **Movimento.** Transições desligadas com `prefers-reduced-motion`.
- **Como provar.** Zero violação no axe por grupo de telas, mais um roteiro manual por tela: só teclado; zoom de 200% e de 400%; foco sempre visível e nunca encoberto; ordem de leitura; nenhuma informação só por cor. O relatório diz “WCAG 2.2 AA: verificado por axe e roteiro manual; leitor de tela não verificado”.

Contraste dos tokens, pela fórmula de luminância relativa da WCAG. Par que só passa em 3,0 não pode ser texto.

| Par | Texto ou traço | Fundo | Razão | Passa 4,5 | Passa 3,0 |
| --- | --- | --- | --- | --- | --- |
| Texto principal | `--tinta` `#01101f` | `--fundo` `#f5f8f7` | 17,94:1 | sim | sim |
| Texto principal | `--tinta` `#01101f` | `--superficie` `#ffffff` | 19,17:1 | sim | sim |
| Texto em hover ou em item escolhido | `--tinta` `#01101f` | `--neutro-fundo` `#e9eeed` | 16,36:1 | sim | sim |
| Texto secundário | `--secundario` `#35484e` | `--fundo` `#f5f8f7` | 8,98:1 | sim | sim |
| Texto secundário | `--secundario` `#35484e` | `--superficie` `#ffffff` | 9,60:1 | sim | sim |
| Texto secundário; etiqueta neutra | `--secundario` `#35484e` | `--neutro-fundo` `#e9eeed` | 8,19:1 | sim | sim |
| Link, aba escolhida, foco | `--primaria` `#145453` | `--fundo` `#f5f8f7` | 8,11:1 | sim | sim |
| Link, aba escolhida, foco | `--primaria` `#145453` | `--superficie` `#ffffff` | 8,67:1 | sim | sim |
| Contorno de escolhido | `--primaria` `#145453` | `--neutro-fundo` `#e9eeed` | 7,40:1 | sim | sim |
| Rótulo do botão primário | branco `#ffffff` | `--primaria` `#145453` | 8,67:1 | sim | sim |
| Rótulo do botão primário em hover | branco `#ffffff` | `--tinta` `#01101f` | 19,17:1 | sim | sim |
| Borda de controle; marca de neutro | `--borda` `#6b7c80` | `--superficie` `#ffffff` | 4,36:1 | não | sim |
| Borda de controle; marca de neutro | `--borda` `#6b7c80` | `--fundo` `#f5f8f7` | 4,08:1 | não | sim |
| Borda de controle; marca de neutro | `--borda` `#6b7c80` | `--neutro-fundo` `#e9eeed` | 3,72:1 | não | sim |
| Texto desabilitado | `--desabilitado` `#5a6b6f` | `--neutro-fundo` `#e9eeed` | 4,76:1 | sim | sim |
| Mensagem e borda de erro | `--erro-texto` `#8a1c13` | `--superficie` `#ffffff` | 9,31:1 | sim | sim |
| Mensagem e borda de erro | `--erro-texto` `#8a1c13` | `--fundo` `#f5f8f7` | 8,71:1 | sim | sim |
| Barra lateral: texto | `--linhas` `#d8e2df` | `--tinta` `#01101f` | 14,49:1 | sim | sim |
| Barra lateral: nome do produto e do usuário | branco `#ffffff` | `--tinta` `#01101f` | 19,17:1 | sim | sim |
| Barra lateral: texto de apoio, ícone inativo | `--lateral-apoio` `#a9bcb8` | `--tinta` `#01101f` | 9,65:1 | sim | sim |
| Barra lateral: texto do item ativo | branco `#ffffff` | `--lateral-ativo` `#10293a` | 15,00:1 | sim | sim |
| Barra lateral: faixa e ícone do item ativo | `--destaque` `#1ed8cf` | `--lateral-ativo` `#10293a` | 8,41:1 | sim | sim |
| Barra lateral: foco | `--destaque` `#1ed8cf` | `--tinta` `#01101f` | 10,75:1 | sim | sim |
| Destaque sobre ação primária | `--destaque` `#1ed8cf` | `--primaria` `#145453` | 4,86:1 | sim | sim |
| Etiqueta de positivo | `--positivo-texto` `#0f4544` | `--positivo-fundo` `#dff1ef` | 9,19:1 | sim | sim |
| Etiqueta de aviso | `--aviso-texto` `#6a4300` | `--aviso-fundo` `#fbefd9` | 7,64:1 | sim | sim |
| Etiqueta de erro | `--erro-texto` `#8a1c13` | `--erro-fundo` `#fbe5e2` | 7,72:1 | sim | sim |
| Etiqueta de informação | `--info-texto` `#1d3d70` | `--info-fundo` `#e3ebf8` | 8,96:1 | sim | sim |
| Marca de positivo | `--positivo-marca` `#145453` | `--neutro-fundo` `#e9eeed` | 7,40:1 | sim | sim |
| Marca de aviso | `--aviso-marca` `#a87400` | `--neutro-fundo` `#e9eeed` | 3,47:1 | não | sim |
| Marca de erro | `--erro-marca` `#c0362c` | `--neutro-fundo` `#e9eeed` | 4,71:1 | sim | sim |
| Marca de informação | `--info-marca` `#3565b0` | `--neutro-fundo` `#e9eeed` | 4,92:1 | sim | sim |
| Série 1 de gráfico | `--serie-1` `#008f88` | `--superficie` `#ffffff` | 3,97:1 | não | sim |
| Série 2 de gráfico | `--serie-2` `#c2620f` | `--superficie` `#ffffff` | 4,16:1 | não | sim |
| Proibido: destaque em fundo claro | `--destaque` `#1ed8cf` | `--superficie` `#ffffff` | 1,78:1 | não | não |
| Proibido: linhas como borda de campo | `--linhas` `#d8e2df` | `--superficie` `#ffffff` | 1,32:1 | não | não |
| Proibido: texto secundário na barra lateral | `--secundario` `#35484e` | `--tinta` `#01101f` | 2,00:1 | não | não |
| Proibido: botão primário na barra lateral | `--primaria` `#145453` | `--tinta` `#01101f` | 2,21:1 | não | não |

As marcas de situação estão medidas contra `--neutro-fundo`, o fundo do bloco escolhido; sobre `--superficie` e `--fundo` a razão é maior, e sobre o `-fundo` da própria situação a menor é 3,57:1 (aviso). `--linhas` como divisória ou contorno de cartão é decorativa e não entra na conta.
