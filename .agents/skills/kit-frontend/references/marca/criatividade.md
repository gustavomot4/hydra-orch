# Criatividade: o que os sites admirados fazem

Referências do dono de 30/10 e 01/11/2026; interpretações do agente. Evidências em `docs/pesquisa/referencias-sites.md` e `docs/pesquisa/identidade-e-sistemas.md`, no repositório do kit. A síntese abaixo acompanha a instalação. Crie a expressão a partir de `MARCA.md`.

## Primeiro, a superfície

| Superfície | Exemplos | Expressão |
| --- | --- | --- |
| **Marca** | Landing, site, página de produto, abertura de app, jogo | Alta. Aplique tudo abaixo |
| **Trabalho** | Sistema, painel, cadastro, tela usada o dia inteiro | Contida. `references/gosto/perfil.md` manda (G01 a G03). Use uma ou duas ideias daqui, como escala no dado principal e o elemento-assinatura |
| **Tarefa curta** | Cadastro, pagamento, passo a passo | Baixa no meio do fluxo. Marca na abertura e na conclusão |

## O que a primeira rodada ensinou

Observações de 30/10/2026, contextualizadas:

| Decisão | Referência e aplicação |
| --- | --- |
| Escala e peso | Nubank: 156px; C6: 100px, peso 300; Valorant: condensada pesada. Hierarquia com escala responsiva |
| Tipografia | Nubank, C6, Itaú, 99, iFood, Valorant e Fortnite têm fonte própria ou distinta. Epic, Hyper3D e Cequence mostram que fonte comum pode conviver com identidade |
| Cor e forma | 99: amarelo e imagens com cantos amplos; Valorant: cortes retos; Nubank: curvas. Defina papéis e motivos para cor e forma |
| Imagem | Nove dos onze usam foto, arte ou render com peso; CozyGPU repete desenho de linha; Hyper3D mostra resultado; Cequence, diagrama. Use material próprio ou licenciado |
| Mensagem e ritmo | Nubank e iFood Parceiros aproximam promessa e primeiro campo. Alterne composição conforme o conteúdo, com uma ação dominante e prova verificável |
| Tema | Jogos e ferramentas de criação da amostra usam escuro; bancos variam. Tema depende da superfície e do produto; trabalho segue G05 |

## Sete referências acrescentadas em 01/11/2026

Páginas públicas em 1280 × 720; base documental no Canva. Não é manual oficial das marcas.

| Referência | Como a identidade aparece | O que levar para um sistema |
| --- | --- | --- |
| [McDonald’s](https://www.mcdonalds.com.br/) | Speedee, amarelo, alimento e voz cotidiana | A abertura orienta retirada ou entrega; o cardápio muda a composição e preserva os sinais |
| [Burger King](https://www.burgerking.com.br/) | Flame, creme e marrom; letras volumosas e fotos do alimento | A personalidade continua nos nomes e cartões do cardápio, além da campanha |
| [Canva](https://www.canva.com/) | Criações variadas dentro de uma casca estável | Deixar o conteúdo variar e manter controles, hierarquia e espaçamento consistentes |
| [Globoplay](https://globoplay.globo.com/) | Fundo escuro, capas e curadoria por assunto | Fileiras repetem proporções e navegação; categorias mudam a seleção. A arte do destaque não carregou |
| [Netflix](https://www.netflix.com/br/) | Arte, fundo escuro e vermelho nas ações | Landing e ficha pública mantêm atmosfera, mas oferecem informações diferentes para decidir |
| [Mercado Livre](https://www.mercadolivre.com.br/) | Cabeçalho amarelo, área neutra e ação azul | Busca persiste; filtros e cartões dão ordem à comparação. Marca e ação podem ter cores diferentes |
| [Inter](https://inter.co/) | Citrina nos títulos, laranja e controles arredondados | Home e Conta PJ conectam assuntos diferentes por tipografia, imagem e ações |

O Canva documenta [tokens e variantes](https://www.canva.dev/docs/apps/app-ui-kit/design-tokens/) e a composição responsiva no [Easel](https://www.canva.dev/blog/engineering/adding-responsiveness-to-canvas-design-system/). O relato do [Hawkins, no Netflix Studio, de 2021](https://netflixtechblog.com/hawkins-diving-into-the-reasoning-behind-our-design-system-964a7357547) e a [entrevista sobre Andes publicada pela Figma](https://www.figma.com/customers/mercado-libre-scales-design-across-latin-america/) sustentam base compartilhada e composições específicas. Não comprovam a implementação atual de cada página observada.

## Da referência para as telas

1. Em `design/direcoes/ideias.md`, ligue **sinal observado → mensagem percebida → regra aproveitável → aplicação no produto**. Marque a interpretação. O repertório acima não substitui as duas novas referências de fora do setor.
2. Em `DESIGN.md`, registre o que se repete: papéis de cor, tipografia, tratamento de imagem, voz e formas. Separe marca, ação, foco e estados; evite valores isolados por tela.
3. Defina o que varia entre marca, trabalho e tarefa curta. Componentes compartilham tokens, variantes e estados; composições específicas ficam no domínio que as usa.
4. Na tela-modelo, confira a continuidade na navegação, no conteúdo e nos estados. Reuse essas regras nas telas seguintes e documente exceções. Uma campanha não define sozinha um sistema.

## O que não levar

Respeite o piso do kit. Evite:

- Logos, fontes proprietárias, textos e imagens de terceiros como ativos do produto.
- Banners cobrindo a tarefa, texto pequeno e movimento sem controle. Carrossel exige motivo, pausa e navegação acessível. Texto sobre imagem pede contraste calculado.
- Transferir densidade comercial ou efeitos de campanha para telas de trabalho.

## Como usar nas três direções

Em superfície de marca, cada direção tem hierarquia e recursos visuais com propósito que continuam nos componentes. Escala, área de cor e tema dependem de `MARCA.md` e da tarefa. Confira identidade e clichês em `references/marca/identidade.md` e `references/marca/anti-generico.md`.

Identidade exigente não dispensa o piso: contraste, foco, teclado, zoom e movimento reduzido continuam valendo.
