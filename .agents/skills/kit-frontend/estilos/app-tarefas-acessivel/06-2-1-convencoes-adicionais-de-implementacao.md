### 2.1 Convenções adicionais de implementação

O CSS de componentes abaixo mantém algumas medidas locais da interface original, como o padding de cartão e a altura da barra. Elas estão centralizadas na receita do componente correspondente. Não use essas exceções para iniciar uma segunda escala de espaçamentos.

- `--ui-col-wide` define a largura máxima externa, incluindo o padding do conteúdo.
- `--ui-col` serve aos painéis sobrepostos e à opção de tela estreita. O padrão das páginas é amplo.
- `--ui-line` e `--ui-card-border` são divisórias ou contornos decorativos. Campos e escolhas usam `--ui-field-border`.
- `--ui-tone-1` a `--ui-tone-4` e seus pares preservam a paleta de categoria. O ícone de categoria comum usa fundo transparente e `--ui-icon-1` a `--ui-icon-4`.
- `--ui-highlight` é o cartão de atenção preenchido. No escuro ele tem papel magenta próprio, enquanto ações usam azul.
- `--ui-contact` e `--ui-on-contact` são o par verde da ação de contato opcional. Use esse par no canal correspondente ou redefina ambos para outro canal, calculando o contraste.
- `--ui-paper` permanece branco para conteúdo que precisa desse fundo, como um código visual de leitura por câmera.
