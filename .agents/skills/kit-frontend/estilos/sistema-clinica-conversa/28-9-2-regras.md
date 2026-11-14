### 9.2 Regras

- **Foco:** contorno de 3 px em `--ring` com 2 px de afastamento em tudo que recebe foco pelo teclado; dentro de `[data-surface="dark"]`, em `--ring-on-dark`. Campo usa borda `--primary` e halo (6.2). Cartão da grade usa 1 px de afastamento. O `h1` recebe foco programático a cada navegação (`tabindex="-1"`, `data-autofocus`), sem contorno.
- **Foco à vista:** nada que recebe foco fica escondido atrás da barra superior, da barra de abas, do rodapé fixo ou do botão flutuante: `html { scroll-padding-top: calc(var(--topbar) + var(--space-16)); }` e, abaixo de 1100 px, `scroll-padding-top: calc(var(--topbar-mobile) + var(--space-16)); scroll-padding-bottom: calc(var(--tabbar) + var(--fab) + var(--space-32));`.
- **Alvos:** a regra do início da seção 6.
- **Teclado na casca:** o primeiro Tab mostra "Ir para o conteúdo", que leva o foco para a área principal (`<main id="conteudo" tabindex="-1">`). Depois vêm marca, abas e conta; no celular, o conteúdo vem antes da barra de abas. A área de avisos é alcançada pela tecla F8 e o aviso não some enquanto tem foco.
- **Teclado na lista e na agenda:** cada consulta da lista é um botão; Enter ou Espaço abre o detalhe. Na grade (`role="region"` com `aria-label="Agenda: 26 de outubro a 1 de novembro"`), os cartões são botões na ordem das colunas e, dentro de cada coluna, por horário; Enter abre o detalhe (coluna ou painel) e Esc fecha e devolve o foco ao cartão. Agendar num horário livre, pelo teclado, é pelo botão "Agendar consulta", e um texto oculto antes da grade diz isso. Chips, segmentado e dias do mês são botões com `aria-pressed` ou nome acessível.
- **Teclado no combobox:** seta para baixo abre a lista e desce; seta para cima sobe; Enter escolhe a opção ativa; Esc fecha e mantém a escolha anterior; Tab sai sem escolher. O campo tem `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"` e `aria-activedescendant`; a lista, `role="listbox"` com `aria-label="Sugestões"`; cada opção, `role="option"` com `aria-selected="true"` na ativa. "Nenhum resultado" tem `role="status"`.
- **Diálogos:** o diálogo de confirmação prende o foco, abre em "Voltar" e fecha com Esc. Painel, folha e a coluna de detalhe da Agenda recebem o foco ao abrir, fecham com Esc e devolvem o foco a quem os abriu.
- **Leitura assistiva:** as iniciais são `aria-hidden="true"` porque o nome está escrito ao lado; a pílula compacta tem o rótulo em texto oculto; o cartão da grade tem o nome acessível completo (7.2); o cabeçalho de colunas das listas é visual e cada célula leva o rótulo oculto; contagens que mudam com a busca usam `role="status"`; alerta de perigo usa `role="alert"`; a etapa atual tem `aria-current="step"` e a próxima, o texto oculto "(próximo passo)"; o gráfico tem uma tabela oculta com os mesmos números.
- **Cor nunca é o único sinal:**

| O que | Além da cor |
| --- | --- |
| Situação da consulta | Ícone, rótulo escrito (ou oculto, na pílula compacta) e forma: tracejado, cheio, hachurado, nome riscado |
| Agora | A palavra "Agora" na lista; a hora escrita na grade |
| Erro de campo | Borda de 2 px, ícone e mensagem escrita |
| Linha selecionada | Barra interna de 3 px à esquerda e `aria-pressed` |
| Aba ativa e dia de hoje | Fundo preenchido, `aria-current` e, na grade, "Hoje ·" escrito |
| Chip escolhido | Fundo escuro inteiro e `aria-pressed` |
| Entrada e saída no gráfico | Posição fixa (entrada à esquerda), legenda escrita e valores no balão |

- **Reflow e zoom:** em 320 px de largura e em zoom de 200%, nenhuma tela rola na horizontal. A exceção é o gráfico do Painel, que rola dentro do próprio cartão.
- **Dados pessoais:** formulário que coleta dado pessoal diz para que serve e onde está a política (7.4). Busca, CPF e telefone nunca vão para o endereço da página; o endereço guarda só identificadores, data, visão e página. Exemplos e capturas usam dados fictícios.
- **Movimento:** seção 8.
