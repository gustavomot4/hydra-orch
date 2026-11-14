## 3. Tipografia e iconografia

### 3.1 Tipografia

A família é a pilha nativa declarada em `--ui-font`. O aspecto pode variar entre Windows, Android e outros sistemas, preservando a hierarquia. Não é necessário baixar uma fonte para recriar o padrão.

| Papel | Token | Aplicação |
| --- | --- | --- |
| Apoio, legenda, selo | `--ui-fs-small` | Descrição curta, data, categoria e instrução auxiliar |
| Corpo | `--ui-fs-body` | Parágrafos, avisos e fatos |
| Corpo de destaque | `--ui-fs-body-lg` | Título de linha, texto de confirmação e navegação no desktop |
| Seção e rótulo de campo | `--ui-fs-heading` | Pergunta secundária, grupo de opções e label |
| Título de cartão | `--ui-fs-card` | Categoria ou item principal |
| Título de tela | `--ui-fs-title` | Um `h1` por página ou etapa |
| Resultado de sucesso | `--ui-fs-display` | “Pronto!” e equivalente do produto |
| Botão | `--ui-fs-button` | Verbo e objeto legíveis |
| Valor do campo | `--ui-fs-input` | Texto digitado, sem reduzir o tamanho no celular |
| Menu móvel | `--ui-fs-tab` | Exceção responsiva para os quatro rótulos caberem |

Use peso 700 em títulos, ações e escolhas; 400 no corpo; 500 no apoio de opções; 600 no texto digitado. Use `--ui-lh-tight` nos títulos e ações e `--ui-lh-body` nos parágrafos. As receitas mantêm os ajustes locais de linha dos componentes.

Os tamanhos são em `rem`. A preferência “Normal”, “Grande” e “Maior” altera a raiz para 100%, 115% e 130%, respectivamente. Guarde a escolha com uma chave própria do produto e aplique-a antes da primeira pintura. Em armazenamento indisponível, a escolha pode valer durante a sessão.

Não use altura fixa para truncar títulos ou rótulos. Deixe o texto quebrar, inclusive em botões. O conteúdo extenso deve continuar disponível.

### 3.2 Iconografia

**Família de reprodução: Phosphor Duotone.** A origem utiliza SVGs dessa família, com a cor herdada do contexto e o desenho decorativo oculto dos leitores de tela. A aplicação de destino pode consumir os SVGs diretamente ou usar a integração apropriada ao seu framework.

- Use uma única família no aplicativo. Preserve a camada secundária Duotone.
- O bloco de ícone reserva espaço de alinhamento; nas categorias comuns ele é transparente.
- Os modificadores `sm`, padrão, `lg` e `xl` estão definidos no CSS. A receita controla também o tamanho do SVG dentro do bloco.
- Ícones de fatos, botões e navegação são menores que os desenhos das categorias; use as medidas declaradas nas receitas e no exemplo.
- Ícone decorativo: `aria-hidden="true"` e `focusable="false"`. O texto ao lado fornece o nome.
- Foto e avatar de iniciais são opcionais. Não obrigue envio de foto para a composição funcionar.
- Escolha desenhos ligados à tarefa do destino. Maleta, livro ou ferramenta são exemplos da origem, sem significado obrigatório em outro produto.
