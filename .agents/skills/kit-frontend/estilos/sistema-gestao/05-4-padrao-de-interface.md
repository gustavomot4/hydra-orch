### 4. Padrão de interface

**Tamanhos de referência.** São medidas da área útil do navegador, e o resto do prompt as cita pelo nome. Um notebook de 1366 × 768 não entrega 768 px à página: descontadas a barra do sistema e as do navegador, sobram cerca de 640 px de altura (estimativa; confirme no aparelho de quem vai usar). Por isso o tamanho principal é 1366 × 640.

| Nome | Área útil | Para quê |
| --- | --- | --- |
| `desktop` | 1366 × 640 | Principal: é nele que se mede “sem rolar a página”. Projeto `desktop` do Playwright. |
| `desktop-largo` | 1440 × 900 | Conferir que nada estica nem sobra. |
| `tablet` | 768 × 1024 | Menu recolhido, tabela com as colunas principais. |
| `celular` | 375 × 812 | Projeto `celular` do Playwright. |
| `reflow` | 320 × 568 | Reflow da WCAG 1.4.10, equivalente ao zoom de 400%. Nada rola na horizontal. |
| `zoom-200` | 683 × 320 | O `desktop` com zoom de 200%. |

Pontos de quebra: a partir de 1024 px, barra lateral fixa e tabela; abaixo de 1024 px, a barra lateral vira o topo da página, com o logotipo e um botão “Menu” que abre a navegação, e rola junto com ela; de 600 a 1023 px, a tabela mostra só as colunas principais; abaixo de 600 px, cartões no lugar da tabela, seletor de seção nos formulários e alternância entre lista e calendário na agenda. Neste prompt, “celular” quer dizer abaixo de 600 px; em código, `celular` é o tamanho 375 × 812 da tabela.

**Altura baixa.** Com a janela de até 480 px de altura (o zoom de 400% num monitor de 1280 × 1024 dá 320 × 256), tudo o que é fixo rola junto com a página: barra lateral, barra de ações e cabeçalho. Camada fixa que cobre mais da metade de uma janela dessas deixa a pessoa sem conteúdo. A grade da agenda também perde a rolagem própria e a página rola inteira.

**Estrutura.** Barra lateral escura com logotipo e navegação, área de trabalho clara, cabeçalho de página com título, uma frase de contexto e a ação principal à direita. Usuário e unidade ficam no rodapé da barra lateral; não há barra superior.

**Identidade visual.** Se eu não der identidade visual, use os tokens abaixo sem alterar e pergunte a cor de marca na tabela de decisões. Cor de marca são dois tokens, `--primaria` e `--destaque`; os outros não mudam com ela. Se eu pedir “três direções”, entregue três versões do painel no tamanho `desktop` que mudam só esses dois tokens, cada uma com a tabela de contraste recalculada.

```css
:root {
  /* cor de marca */
  --primaria: #145453;       /* botão primário, link, aba e item escolhidos, foco em área clara */
  --destaque: #1ed8cf;       /* só sobre --tinta ou --primaria; nunca em fundo claro */
  /* base */
  --tinta: #01101f;          /* texto principal; fundo da barra lateral */
  --fundo: #f5f8f7;          /* área de trabalho */
  --superficie: #ffffff;     /* cartão, tabela, campo, diálogo; é também o "branco" do texto sobre --primaria e sobre a barra lateral */
  --secundario: #35484e;     /* texto secundário, só em área clara */
  --linhas: #d8e2df;         /* divisória e contorno de cartão; texto da barra lateral */
  --borda: #6b7c80;          /* borda de campo, de botão secundário e de bloco da agenda */
  --neutro-fundo: #e9eeed;   /* hover, escolhido, desabilitado, etiqueta neutra */
  --desabilitado: #5a6b6f;   /* texto de controle desabilitado */
  --lateral-ativo: #10293a;  /* fundo do item ativo da barra lateral */
  --lateral-apoio: #a9bcb8;  /* texto de apoio e ícone inativo da barra lateral */
  /* situações: -texto sobre -fundo na etiqueta; -marca em barra, ponto e ícone */
  --positivo-texto: #0f4544; --positivo-fundo: #dff1ef; --positivo-marca: #145453;
  --aviso-texto: #6a4300;    --aviso-fundo: #fbefd9;    --aviso-marca: #a87400;
  --erro-texto: #8a1c13;     --erro-fundo: #fbe5e2;     --erro-marca: #c0362c;
  --info-texto: #1d3d70;     --info-fundo: #e3ebf8;     --info-marca: #3565b0;
  --neutro-texto: var(--secundario);                    --neutro-marca: var(--borda);
  /* séries de gráfico, nesta ordem */
  --serie-1: #008f88;
  --serie-2: #c2620f;
  /* forma */
  --raio-p: 10px;            /* campo, botão, bloco, item de menu */
  --raio-m: 14px;            /* cartão */
  --raio-g: 18px;            /* diálogo */
  --largura-lateral: 232px;
  --alvo: 44px;              /* menor largura e menor altura de um controle */
  --altura-linha: 48px;      /* linha de lista */
  /* tipografia */
  --fonte: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
}
```

- **Barra lateral.** Fundo `--tinta`, texto `--linhas`, nome do produto e do usuário em branco, texto de apoio e ícone inativo em `--lateral-apoio`. Item ativo: fundo `--lateral-ativo`, texto branco em peso 600, faixa de 3 px em `--destaque` à esquerda e `aria-current="page"`. `--secundario` e botão primário não entram nela.
- **Superfícies.** Cartão em `--superficie` com contorno de 1 px em `--linhas`, sem sombra. Diálogo sobre véu de `--tinta` a 60% de opacidade. `--linhas` nunca é borda de campo nem de controle: para isso existe `--borda`.
- **Controles.** Botão primário: `--primaria` com texto branco; hover e pressionado em `--tinta`. Botão secundário e campo: `--superficie`, borda de 1 px em `--borda`, texto em `--tinta`; hover em `--neutro-fundo`. Escolhido (linha, bloco, opção): contorno de 2 px em `--primaria` sobre `--neutro-fundo`. Aba escolhida: texto em `--tinta` e traço inferior de 3 px em `--primaria`. Desabilitado: texto em `--desabilitado` sobre `--neutro-fundo`, sem borda. Erro de campo: borda de 2 px e mensagem em `--erro-texto`, com ícone. Foco: ver “Acessibilidade”.
- **Situações.** Etiqueta com o nome escrito, em `-texto` sobre `-fundo`. `-marca` serve a segmento de barra, ponto e ícone, nunca a texto. Os nomes das situações vêm da seção 1: associe cada um a um dos cinco papéis e mostre a associação na tabela de decisões.
- **Gráficos.** Séries na ordem dos tokens, sobre `--superficie`, cada uma com nome na legenda ou rótulo direto. Eixo em `--borda`, linhas de grade em `--linhas`. A partir da terceira série, a cor é decisão a confirmar.
- **Tipografia.** IBM Plex Sans nos pesos 400, 500 e 600, com tamanhos em `rem` (1rem = 16 px). Tamanho e altura de linha: título de página 26/32; título de seção 18/24; rótulo de campo, botão, aba, item de menu e dado principal da linha 16/22; cabeçalho de coluna, dado secundário, etiqueta de situação, legenda, definição de indicador e texto de bloco da agenda 14/20; número de indicador 30/36. Peso 600 em títulos, números de indicador, botões e no item de menu ou aba escolhidos; 500 em rótulos, abas, itens de menu e cabeçalhos de coluna; 400 no resto. No protótipo descartável a fonte pode vir de uma CDN.
- **Espaço e ícones.** Espaçamentos de 4, 8, 12, 16 ou 24 px; margem da área de trabalho de 24 px, 16 px abaixo de 600 px. Ícones em SVG, traço de 1,8 px, 20 px, sempre com texto ao lado ou nome acessível.

**Listagens.** O defeito mais comum é a lista alta, com a paginação fora da tela.

- A partir de 600 px, a lista é uma `<table>` com legenda oculta e `<th scope="col">`: uma linha de 48 px por registro, cabeçalho de colunas e as ações na própria linha. Abaixo de 600 px, vira uma `<ul>` de cartões de até 96 px, em que cada dado mantém o rótulo em texto.
- Ação de linha: até 2 botões de texto curto (“Abrir”, “Editar”) com nome acessível completo (“Editar Marina Teles”); as demais ficam em “Mais ações”. Em lista de painel lateral, a ação é um botão de ícone com o mesmo nome acessível.
- Cada lista declara a ordem padrão (por exemplo: nome, de A a Z). Coluna ordenável tem botão no cabeçalho e `aria-sort`, e a ordem vai para a URL.
- Paginação sempre. Escolha o tamanho da página para que busca, lista e paginação caibam no tamanho `desktop` sem rolar a página: 7 em listas simples, 5 em listas com filtros ou totais e em listas secundárias (históricos, relações), 4 em listas dentro de painéis laterais, 6 em diálogos de busca. Se a medida mostrar que não cabe, diminua o tamanho da página, nunca a fonte nem a altura da linha.
- Mostre a faixa e o total (“1–7 de 124”). Totais e somas consideram todos os registros filtrados, não só a página.
- Densidade vem de espaçamento e de uma linha por registro, não de letra pequena.

**Estado na URL.** Busca, filtros, aba, data, página, ordem e o ID interno do registro selecionado ficam na URL e sobrevivem a abrir um detalhe, voltar e recarregar. Exceção: texto de busca com dígito (CPF, telefone, número de cadastro) não vai para a URL, que fica no histórico e em link copiado; guarde em `sessionStorage`. Mudar um filtro volta à primeira página. Parâmetro inválido é limitado ao intervalo válido.

**Formulários.**

- Obrigatório é só o que a regra exige. Exemplo do Dental Flow: o cadastro de paciente exige apenas o nome.
- Formulário com mais de 8 campos vira seções navegáveis com contagem de preenchimento e barra de ações fixa; abaixo de 600 px, um seletor de seção. Com a janela de até 480 px de altura, a barra rola junto (ver “Altura baixa”).
- Um erro abre a seção do campo, leva o foco a ele e fica associado ao campo. Falha de gravação conserva tudo o que foi digitado e leva o foco ao aviso.
- Bloqueie o envio duplicado, inclusive dois envios antes da próxima renderização, e peça confirmação ao sair com alterações.
- Escolha única entre até 5 opções usa botões de opção com “limpar” quando for opcional, não um campo de texto livre.
- Ação que movimenta dinheiro ou encerra um registro (lançamento de caixa, conclusão de atendimento, inativação) passa por tela de conferência antes de gravar. Não há exclusão definitiva: registro é inativado com motivo; lançamento errado é estornado, não editado. É regra de negócio: confirme na tabela de decisões.

**Seleção em cadastros grandes.** Com mais de 50 itens, use um diálogo de busca em vez de um `select`. Digitar não muda a seleção, só escolher um resultado muda. Busca sem diferenciar acentos nem pontuação, por nome e por identificadores. Em cadastro de pessoas, para distinguir homônimos mostre o que existir, nesta ordem: data de nascimento, 4 últimos dígitos do telefone, código do cadastro; se nada existir, o código e a data do cadastro. Nunca o CPF completo (mostre `***.***.789-10`). Escape fecha e mantém a escolha anterior, com o foco de volta ao campo.

**Agenda ou calendário, se houver.** Com mais de 3 registros no mesmo horário, cartões lado a lado ficam ilegíveis.

- Escala de 48 px a cada 30 min. A grade tem rolagem própria e abre no horário atual; no tamanho `desktop` a página não rola.
- Sem filtro de responsável: um bloco por horário de início, com a quantidade e, em texto, quantos pedem ação (exemplo: “6 consultas” e, abaixo, “2 a confirmar”). A barra de situações é reforço, nunca o único sinal: 6 px, na borda esquerda do bloco, com legenda visível, ordem fixa dos segmentos e 2 px entre eles. O nome acessível do bloco diz tudo (exemplo: “sexta 9, 11:00, 6 consultas: 4 confirmadas, 2 a confirmar”).
- Com um responsável filtrado: cartões proporcionais à duração. Os que se sobrepõem ficam lado a lado, até 3 e só enquanto cada um mantiver 44 px de largura; o excedente vira um botão “+N”, que lista o horário no painel.
- Nenhum bloco ou cartão tem menos de 44 × 44 px: duração menor que 30 min ocupa 44 px e mostra a duração em texto. Se o texto do bloco não couber em 14 px, mostre menos dias; não reduza a fonte nem corte o texto.
- Blocos e cartões são botões, na ordem dia e depois horário; cada cabeçalho de dia é um botão que lista o dia. Escolher bloco ou dia move o foco para o título do painel, em qualquer largura. O dia de hoje traz a palavra “hoje”.
- Ao lado, um painel lista o dia ou o horário escolhido, 4 por página.
- Atalhos de período: Hoje, Esta semana, Próxima semana. Quando houver registros fora da área visível da grade, avise com a contagem e um botão que leva até eles.
- Abaixo de 768 px, o calendário mostra um dia por vez: seis colunas não dão 112 px ao bloco, e o texto de 14 px não cabe em menos. Os seis dias viram um seletor de botões de 44 px, e o dia escolhido aparece por extenso acima da grade.
- Abaixo de 600 px, alterne entre lista do dia e calendário, com a lista como padrão.

**Painel.** Abas por assunto, com filtro de período no topo e, havendo mais de uma unidade, filtro de unidade. Abas que mudam a URL são links com `aria-current="page"`. Indicador mostra só o rótulo e o número. A definição (o que conta e o que não conta) fica a um toque: um botão de informação de 44 × 44 px ao lado do rótulo, com nome acessível “Como é contado: <rótulo>” e `aria-expanded`, que abre o texto sob o número. Pendências com atalho que abre o módulo já filtrado. Não repita listas dos módulos no painel. Todo gráfico tem alternativa em tabela, com o alternador “Gráfico | Tabela” no próprio cartão, usa a mesma escala nas séries e não dá altura artificial ao zero. Abaixo de 600 px, as colunas lado a lado viram barras horizontais, uma linha por dia, com o valor no fim de cada barra e as mesmas cores e escala. O painel pode rolar a página.

**Estados.** Toda tela trata carregamento, vazio com a próxima ação, erro de leitura com “tentar novamente”, erro de gravação e sucesso. Inclua um painel de revisão para simular carregamento lento, falha de leitura e falha de gravação: é o que permite testar esses estados. Ele fica em `#/revisao`, fora da navegação principal, existe só no servidor de desenvolvimento e na origem isolada e não entra no build publicado.

**Linguagem.** Português direto, ações com verbo e objeto (exemplo: “Cadastrar paciente”), sem jargão técnico. Palavras financeiras exatas, por exemplo: valor apresentado não é valor recebido, orçamento não é receita, quantidade de registros não é ocupação. Tema escuro e outros idiomas ficam fora do padrão, salvo pedido na seção 1.

**Impressão e exportação.** Relatório tem versão de impressão sem navegação e exportação CSV: UTF-8 com BOM, separador `;`, fim de linha CRLF, número com vírgula decimal e sem símbolo de moeda, data `AAAA-MM-DD`. Valor desconhecido sai vazio. Célula de texto iniciada por `=`, `+`, `-` ou `@` recebe um apóstrofo na frente. Exportar gera evento de auditoria. Coluna com dado pessoal sensível (de saúde, por exemplo) só entra se eu pedir.
