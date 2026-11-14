### 7.3 Agendar consulta

Página larga (`--page-wide`). A partir de 1100 px, formulário à esquerda e resumo fixo à direita numa grade `minmax(0, 1fr) var(--summary)` com espaço `--space-24`.

- **Formulário**, em cartões empilhados com espaço `--space-16`, cada um com título e ícone `--icon` `--primary`: paciente (busca por nome; escolhido, aparece com iniciais `lg`, nome em `--text-lead` e o botão "Trocar"), profissional (chips até 6, combobox acima), procedimento (combobox), dia e horário, observação (até 255 caracteres).
- **Horários livres:** depois de escolher o profissional e o dia, os horários livres aparecem agrupados por período ("MANHÃ", "TARDE"), numa grade `repeat(auto-fill, minmax(78px, 1fr))` com espaço `--space-8`. Cada horário é um botão de 42 px, raio `--radius-md`, borda `--line-control` `--border`, `--text-ui` `--weight-bold`, números tabulares; hover com borda `--primary`; escolhido com fundo `--primary`, texto `--primary-foreground` e `aria-pressed="true"`. Até 8 por período, com "Ver todos (14)" embaixo, que vira "Ver menos". Enquanto confere, "Conferindo a agenda…"; sem horário livre, "Não há horário livre neste dia. Escolha outro dia ou informe o horário manualmente."
- **Resumo:** `position: sticky; top: calc(var(--topbar) + var(--space-20))`, fundo `--card`, borda, raio `--radius-xl`, `padding: var(--space-24)`. Título "Resumo da consulta"; lista em `--card-soft` com Paciente, Profissional, Procedimento e Dia e horário (o que falta aparece em itálico `--muted-foreground`, por exemplo "Escolha o paciente"); alerta `warning` "Este horário já está ocupado" se ele se sobrepõe a outra consulta do mesmo profissional; botão `lg` `block` "Agendar consulta" e, embaixo, "Cancelar" (`ghost`, `block`).
- **Abaixo de 1100 px:** uma coluna; o resumo vira uma barra fixa acima da barra de abas (fundo `--card`, borda superior, `--shadow-bar`, `padding: var(--space-10) var(--page-x)`), com o paciente em `--text-ui` `--weight-bold`, o resto em `--text-caption` e o botão "Agendar" à direita. O aviso de sobreposição desce para dentro do formulário.

### 7.4 Pacientes

**Lista:**

1. Cabeçalho "Pacientes", subtítulo "248 cadastrados", ação "Novo paciente" (`user-plus`; botão flutuante abaixo de 1100 px).
2. Busca grande: campo `type="search"` com `search` à esquerda, altura `--control-lg`, raio `--radius-full`, `padding-left: 50px`, texto `--text-lead`, largura máxima 640 px (inteira abaixo de 768 px), rótulo oculto "Buscar paciente" e o exemplo "Buscar pelo nome, CPF ou telefone". A busca ignora acentos e maiúsculas e filtra enquanto se digita.
3. Lista num cartão (`padding: var(--space-6) var(--space-6) var(--space-10)`), agrupada pela primeira letra do nome (letra em `--text-small` `--weight-extrabold` `--primary`, `padding: var(--space-12) var(--space-14) var(--space-4)`). Durante a busca, "12 pacientes encontrados" em `--text-small` `--weight-semibold` `--muted-foreground`, com `role="status"`.
4. Cabeçalho de colunas (só visual, `aria-hidden="true"`): "PACIENTE", "CELULAR", "CPF" e "WHATSAPP", em `--text-micro` `--weight-extrabold` `--tracking-caps` maiúsculo `--muted-foreground`, borda inferior `--line` `--border`. As células levam o rótulo em texto oculto ("Celular: ").
5. Linha: um link para a ficha numa grade `44px minmax(0, 1.4fr) minmax(0, .8fr) minmax(0, .8fr) 22px` com espaço `--space-14` e `padding: var(--space-10) 66px var(--space-10) var(--space-12)`, raio `--radius`, hover `--card-soft`. Iniciais `md`; nome em `--text-body` `--weight-bold` com reticências e, embaixo, "Centro · 34 anos" em `--text-small` `--muted-foreground`; celular e CPF em `--text-ui` `--muted-foreground` tabulares; `chevron-right` `--icon` `--muted-foreground`. Fora do link, à direita, o botão redondo de conversa: 44 × 44 px, raio `--radius-full`, fundo `--whatsapp-soft`, `message-circle` `--icon` em `--whatsapp`, `aria-label="WhatsApp de Helena Prado"`. Abaixo de 768 px, a grade fica `44px minmax(0, 1fr)` e celular, CPF e seta somem.
6. Paginação (6.11), 20 por página.

| Estado | O que aparece |
| --- | --- |
| Carregando | Esqueleto de 8 blocos de 60 px |
| Nenhum cadastro | `users`, "Nenhum paciente cadastrado", "Os pacientes cadastrados aparecem aqui, em ordem alfabética." e "Cadastrar o primeiro paciente" |
| Busca sem resultado | `search`, "Ninguém encontrado", "Confira a grafia ou busque pelo CPF ou telefone." e "Limpar a busca" (`secondary`) |
| Erro | Erro ao carregar (6.12) |

**Ficha:** link de volta "Pacientes", título com o nome, ação "Editar" (`secondary`, `pencil`). Um cartão de perfil (iniciais `xl`, nome em `--text-title`, "34 anos · Centro" em `--muted-foreground`, e à direita "Agendar consulta" `primary`, "WhatsApp" `whatsapp` e "Ligar" `secondary`; abaixo de 768 px os botões descem e dividem a largura). Embaixo, três cartões lado a lado (um por linha abaixo de 1100 px): Contato (celular, e-mail), Documento (CPF, nascimento com a idade), Endereço. Cada um com a lista de dados do 6.8. Carregando: esqueleto de 3 blocos de 140 px.

**Cadastro e edição:** página de formulário (`--page-form`), título "Novo paciente" ou "Editar paciente", link de volta. Cartões com título e ícone: "Quem é o paciente" (`user-round`: Nome completo na linha inteira, CPF, Data de nascimento opcional), "Como falar com ele(a)" (`message-circle`: Celular / WhatsApp opcional, E-mail opcional), "Endereço" (`map-pin`: campos do 6.2). Antes do primeiro cartão, uma linha em `--text-small` `--muted-foreground` diz para que os dados servem e onde está a política: "Usamos estes dados para agendar e lembrar as consultas. Veja a política de privacidade." com o link.

- **Rodapé fixo:** `position: sticky; bottom: 0` (abaixo de 1100 px, `bottom: calc(var(--tabbar) + env(safe-area-inset-bottom))`), `z-index: var(--z-footer)`, `padding: var(--space-14) 0`, fundo `linear-gradient(transparent, var(--background) 30%)`, botões à direita com espaço `--space-10`: "Cancelar" (`secondary`) e "Salvar paciente" (`lg`; "Salvar alterações" na edição). Abaixo de 768 px, os dois dividem a largura.
- **Erros:** ao salvar com campo inválido, alerta `warning` "Confira os campos destacados abaixo." no topo e cada erro no seu campo, com o foco no primeiro. CPF repetido: "Já existe um paciente com este CPF na clínica." no campo CPF. Falha do servidor: alerta `danger` "Não foi possível salvar" com a mensagem, mantendo tudo o que foi digitado.
- **Carregando** (edição): esqueleto de 3 blocos de 160 px. **Salvando:** botão de salvar em carregando.
- Sair com alterações não salvas pede confirmação (6.14): título "Descartar as alterações?", texto "Há alterações não salvas. Se sair agora, elas se perdem.", botões "Voltar" e "Sair sem salvar".
