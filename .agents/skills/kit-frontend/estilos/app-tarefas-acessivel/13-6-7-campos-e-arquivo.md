### 6.7 Campos e arquivo

Cada campo reúne label, dica opcional, controle e erro associado. Use `aria-describedby` para dica e erro e `aria-invalid` quando houver falha. O erro traz texto, símbolo e cor.

- Texto curto e textarea seguem a mesma moldura. O textarea permite crescimento vertical.
- Telefone, moeda e identificadores usam teclado e formatação compatíveis com o destino. Máscara não equivale a validação de negócio.
- O atalho “Falar” pode ficar ao lado do campo; na textarea, abaixo. Digitação continua disponível.
- Arquivo usa botão rotulado, instrução de tipo e limite real, nome do arquivo escolhido e retorno de validação.
- O seletor nativo de arquivo continua sendo usado pelo controlador. A composição não envia o arquivo automaticamente.
- Falha de envio conserva o conteúdo e permite nova tentativa. O tratamento de dados e a política correspondente pertencem ao produto.

### 6.8 Opções e interruptor

**Opção:** radio ou checkbox nativo dentro de um cartão de escolha. O cartão inteiro é o rótulo. O estado escolhido combina contorno, fundo e marca; o grupo usa `fieldset` e `legend`. Se a pergunta já for o título, a legenda pode ficar visualmente oculta.

**Interruptor:** linha com título, explicação opcional e trilho. Use papel `switch` e `aria-checked`, ou um controle nativo equivalente. O trilho se desloca e muda de cor. Não use interruptor para executar uma operação que precise de confirmação antes de ocorrer.

### 6.9 Progresso, linha do tempo e conclusão

**Barra de etapas:** segmentos preenchidos e texto “Passo n de total”. Os segmentos são decorativos; o texto informa o progresso. No limite estreito, o texto quebra para outra linha.

**Linha do tempo:** marcadores conectados e três papéis visuais: feito, atual e futuro. Cada etapa tem título e apoio. Use nomes reais do processo e não acrescente uma transição que o backend não informou.

**Conclusão:** desenho central, título de resultado, uma frase dizendo o que ocorreu, explicação breve do próximo passo e ação para continuar. O resultado só aparece depois da confirmação correspondente.

### 6.10 Painel sobreposto

O `ui-sheet` sobe da borda inferior, com fundo de véu, cantos superiores arredondados, indicador de pega, título, conteúdo e até duas ações. Continua limitado à largura própria do painel no desktop.

O controlador deve fornecer nome de diálogo, `aria-modal`, foco inicial no título, contenção do Tab, fechamento com Escape e retorno ao controle que abriu. Enquanto aberto, o conteúdo de fundo fica indisponível à interação e à navegação assistiva. Não dependa somente do véu visual. Clique fora só fecha quando a tarefa permitir descartar a abertura sem perder dados.
