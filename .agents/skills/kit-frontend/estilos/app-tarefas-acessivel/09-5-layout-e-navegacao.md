## 5. Layout e navegação

### 5.1 Moldura

Toda tela segue a mesma sequência:

1. Barra superior com marca, retorno quando pertinente, controle de escuta e ações globais.
2. Conteúdo amplo com título, frase de apoio opcional e blocos da tarefa.
3. Rodapé com ação principal, quando a tarefa exigir.
4. Menu principal móvel, quando não houver rodapé de ação.

No desktop, o menu principal aparece na barra superior mesmo em telas com rodapé. No celular, a ação do formulário ou do detalhe ocupa a faixa inferior do menu. Não empilhe duas barras inferiores concorrentes.

Em tela interna móvel, o retorno ocupa o lugar da marca. No desktop, a marca pode permanecer ao lado do retorno, como na origem.

Use altura mínima de viewport dinâmico. O conteúdo pode rolar verticalmente. Topo e rodapé são aderentes ao viewport com `position: sticky`; a área segura inferior do aparelho entra no padding. O conteúdo deve permanecer alcançável por teclado e rolagem.

### 5.2 Regras de adaptação

| Condição da receita | Comportamento |
| --- | --- |
| Janela abaixo do breakpoint de desktop | Marca compacta; navegação inferior em quatro itens; filtros acima da lista |
| Janela a partir de 1100 px | Mesmos destinos no topo, com texto e ícone lado a lado |
| Contêiner estreito | Grades e controles refluem segundo as consultas em `rem` do CSS |
| Grade de categorias com espaço suficiente | Quatro atalhos na mesma linha; antes disso, duas colunas; no limite estreito, uma |
| Catálogo no contêiner amplo | Filtros em coluna lateral e lista contínua à direita |
| Catálogo com espaço adicional | Título e identificação à esquerda; fatos à direita, separados por divisória |
| Conta no contêiner amplo | Opções em duas colunas; cada opção continua sendo uma linha clicável |
| Notificações no contêiner amplo | Texto à esquerda e ações à direita |

As consultas de contêiner respondem à largura útil e ao tamanho da letra. A navegação usa um breakpoint da janela. Preserve essa distinção; não substitua todas as consultas por uma única largura de celular.

**Altura até 480px:** com zoom de 400%, a janela fica em 320 × 256. Barra superior, abas e rodapé de ação deixam de ser fixos e rolam junto (receita em 5.4).

**Link de pular:** toda tela começa por `<a class="ui-skip" href="#conteudo">Pular para o conteúdo</a>`, e o `<main>` tem `id="conteudo"`.

### 5.3 Dois conjuntos de quatro itens

O **menu principal** tem destinos estáveis, como Início, Explorar, Acompanhar e Conta. A **grade do início** reúne categorias de tarefas, como conteúdos, atividades, recursos e pessoas. São estruturas independentes. Rotas secundárias abrem pelos atalhos e mantêm o contexto do destino principal correspondente.

Mantenha o mesmo menu entre perfis de usuário, quando as tarefas permitirem. Adapte o conteúdo do início por perfil. O item atual combina texto, ícone e fundo de seleção; declare `aria-current` de acordo com a rota ou área ativa.
