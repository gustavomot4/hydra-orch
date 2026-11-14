## 10. Checklist de aceite

**Tokens e base**

- [ ] O CSS do projeto declara todos os tokens da seção 2 com os mesmos nomes e valores, e nenhuma cor, tamanho de fonte ou raio fora deles aparece nas folhas de estilo, salvo as medidas próprias de componente das seções 6 e 7.
- [ ] A Figtree carrega com os pesos 400, 500, 600, 700 e 800; nenhum texto usa outra família.
- [ ] Nenhum texto que a pessoa precisa ler, fora as iniciais, tem menos de 12 px; valor de campo e texto corrido têm 16 px no celular.
- [ ] Todo tamanho de fonte está em `rem`, e o `body` não tem `min-width`.
- [ ] A marca é só o nome, sem iniciais dentro de quadrado ou círculo colorido.
- [ ] Em 320 × 256 nada fixo cobre a janela e nada rola na horizontal (5.1, “Altura até 480 px”).

**Casca**

- [ ] Em 1440 × 900 a barra superior tem 68 px, as abas mostram só as áreas do perfil e a ativa tem fundo `--primary-soft`.
- [ ] Em 375 × 812 há barra de abas embaixo com Hoje, Agenda, Pacientes e Mais, e Mais abre a folha com as demais áreas e "Sair da conta".
- [ ] Entrando como Recepção, Painel e áreas financeiras não aparecem no menu, e abrir o endereço do Painel mostra "Esta área é do responsável pela clínica".
- [ ] O primeiro Tab de qualquer tela mostra "Ir para o conteúdo".

**Hoje e detalhe**

- [ ] A lista mostra horário e duração à esquerda, iniciais coloridas, nome em negrito, "Procedimento · Profissional" e a situação à direita, agrupada em Manhã, Tarde e Noite.
- [ ] O mesmo nome tem a mesma cor de iniciais em todas as telas.
- [ ] A linha "Agora" aparece entre a última consulta já iniciada e a primeira ainda por começar.
- [ ] Em 1440 px o detalhe fica ao lado e abre com o próximo paciente; em 375 px tocar na consulta abre a folha inferior com alça.
- [ ] Em 1440 × 900, sem rolar a página, o detalhe mostra o nome, WhatsApp, Ligar, Ficha, as etapas e a ação seguinte no rodapé; numa janela mais baixa, só o corpo rola e o rodapé continua à vista.
- [ ] O detalhe tem WhatsApp, Ligar e Ficha; o WhatsApp abre `wa.me` com o lembrete pronto e não envia nada sozinho.
- [ ] Confirmar mostra o aviso "Consulta de <nome> confirmada" com "Desfazer", e Desfazer volta a situação para Agendado.
- [ ] Cancelar e Faltou pedem confirmação, abrem o diálogo com o foco em "Voltar" e não oferecem Desfazer.

**Agenda**

- [ ] Em 1440 px a visão padrão é Semana, com horas no eixo vertical, 7 dias no horizontal e 80 px por hora.
- [ ] Um cartão de 30 minutos tem 37 px de altura, com hora e nome na mesma linha (`.one-line`), e um de 1 hora, 77 px, com duas linhas.
- [ ] Três consultas simultâneas no mesmo dia ficam lado a lado, cada uma com um terço da largura menos 6 px, e todas mantêm o ícone da situação; com 3 faixas ou mais o cartão mostra só o ícone e as iniciais do paciente (só o ícone se a largura interna for menor que 38 px).
- [ ] Cada uma das seis situações aparece com a forma do 4.3: Agendado tracejado sem barra, Em atendimento roxo cheio, Cancelado e Faltou hachurados, Cancelado com o nome riscado.
- [ ] Com hoje na tela, a linha "agora" atravessa a grade, é mais forte na coluna de hoje e a hora aparece no eixo.
- [ ] Clicar num horário livre futuro abre o agendamento com dia, hora e profissional preenchidos; num horário passado, nada acontece.
- [ ] Abaixo de 900 px as visões são Dia, 3 dias e Mês, e a padrão é Dia.
- [ ] Escolher um profissional nos chips mostra só as consultas dele e os cartões ocupam a largura do dia.
- [ ] Recarregar a página mantém visão, data, profissional e consulta aberta.
- [ ] A partir de 1280 px, abrir uma consulta põe o detalhe numa coluna ao lado e a grade encolhe: nenhuma coluna da grade, a legenda, as ações do cabeçalho nem o menu da conta ficam cobertos. Abaixo de 1280 px o detalhe abre por cima, com véu e botão fechar.
- [ ] A grade tem a altura que sobra da janela (sem número fixo): em 1440 × 900 a página da Agenda não rola e só o corpo da grade rola.

**Pacientes e formulários**

- [ ] A busca encontra "José" digitando "jose" e mostra "N pacientes encontrados".
- [ ] A lista tem cabeçalho de colunas Paciente, Celular, CPF e WhatsApp a partir de 768 px e mostra 20 por página com "Mostrando 21–40 de N".
- [ ] Voltar da ficha para a lista devolve à mesma página.
- [ ] O cadastro de paciente diz para que servem os dados e tem link para a política.
- [ ] Salvar com CPF repetido mostra o erro no campo CPF, com borda de 2 px, ícone e texto, e mantém o que foi digitado.
- [ ] O rodapé com Cancelar e Salvar fica visível ao rolar e, em 375 px, acima da barra de abas.

**Estados**

- [ ] Hoje, Agenda, Pacientes, ficha e Painel mostram esqueleto ao carregar, estado vazio com uma ação e erro com "Tentar de novo".
- [ ] O botão flutuante não cobre a paginação nem o último item em 375 × 812.

**Acessibilidade**

- [ ] Todos os pares da tabela 9.1 conferem com os valores aplicados no navegador.
- [ ] O axe não aponta violação de nível A ou AA em Hoje, Agenda, Pacientes, cadastro de paciente, Painel e Entrar.
- [ ] Tab percorre todos os controles de cada tela com o contorno visível, inclusive dentro do cartão "Próximo" e do aviso, onde o contorno é `--ring-on-dark`.
- [ ] No combobox de procedimento, setas, Enter e Esc funcionam como na seção 9.2, sem mouse.
- [ ] Em 320 × 568 e em zoom de 200%, nenhuma tela rola na horizontal, exceto o gráfico dentro do cartão.
- [ ] Com movimento reduzido ativado no sistema, painel, folha, diálogo e aviso aparecem sem deslizar e o esqueleto fica parado.
- [ ] Nenhuma situação, erro ou seleção é indicada só por cor (conferir a tabela da seção 9.2 tela a tela).
