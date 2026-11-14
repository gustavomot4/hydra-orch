## 6. Componentes

### 6.1 Barra superior e menu

**Barra superior:** nome ou logotipo nas telas de entrada; retorno textual nas telas internas, acompanhado da marca no desktop quando houver espaço. À direita ficam “Ouvir” e avisos pertinentes. Em tela interna móvel, o aviso pode sair do topo para preservar o espaço de “Voltar” e “Ouvir”.

**Menu móvel:** quatro links com desenho acima do rótulo. O escolhido recebe pílula atrás do desenho e cor de texto de seleção. **Menu desktop:** os mesmos quatro links, horizontais, dentro do topo. O escolhido recebe fundo no item inteiro.

**Contador:** pequeno, circular e com nome acessível completo. O valor visual pode ser limitado, mas o nome deve informar a quantidade real quando conhecida. Não transforme uma contagem em promessa de evento que ainda não foi recebido.

### 6.2 Botão

| Variante | Uso | Aparência |
| --- | --- | --- |
| `primary` | Próxima ação da tarefa | Fundo de ação, texto do par correspondente |
| `secondary` | Alternativa ou revisão | Superfície, borda de ação, texto de ação |
| `quiet` | Ação discreta | Texto sublinhado, sem preenchimento |
| `danger` | Ação destrutiva definida pelo produto | Superfície, borda e texto de erro |
| `contact` | Canal externo opcional | Par verde de contato da paleta padrão |
| `inline` | Modificador de largura | Largura do conteúdo, conservando o alvo de toque |

Use um botão primário por etapa ou tarefa. A navegação usa links; executar uma ação local usa botão. Enquanto uma ação estiver em andamento, bloqueie o envio e mostre uma palavra como “Salvando…”. O resultado da operação fica em aviso ou tela de conclusão.

O estado desabilitado é distinto do estado em andamento: os dois bloqueiam a ação, e o segundo também informa atividade. Um link desabilitado exige bloquear a navegação no controlador; o atributo visual sozinho não faz isso.

### 6.3 Cartões de intenção, categoria e linha

**Cartão de intenção (`ui-bigcard`):** desenho à esquerda, título e uma frase no centro, seta de avanço à direita. Toda a área é um único link ou botão. Use a versão `tile` na grade de categorias, com o desenho acima do texto.

**Cartão de atenção (`highlight`):** preenchido com o par de destaque e texto curto sobre uma pendência. **Cartão de ênfase (`emphasis`):** fundo suave de ação, mantendo título e apoio legíveis. A escolha entre ambos depende do papel da informação, não de alternância decorativa.

**Linha clicável (`ui-rowcard`):** avatar ou ícone, título, apoio, selo ou contador opcional e indicação de avanço. Serve a conta, histórico, conteúdo e lista de pessoas.

**Cartão de conteúdo (`ui-card`):** título, identificação, fatos e ações secundárias. Quando o título abre o detalhe, estenda a área do link ao cartão e mantenha os demais controles acima dessa área. Não aninhe um botão dentro de outro botão ou link.
