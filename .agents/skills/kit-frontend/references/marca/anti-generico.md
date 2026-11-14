# O que denuncia interface genérica

Geradores repetem as mesmas escolhas porque são as médias do que viram. Cada item abaixo é um padrão a evitar **quando vem por inércia**. Com motivo escrito no `DESIGN.md`, qualquer um pode ser usado. `[script]` indica o que `scripts/verificar.mjs` detecta.

**O teste final:** cubra o logo e o nome. Dá para saber de quem é a tela? Se ela serviria para qualquer empresa de qualquer setor, não terminou.

**Um item isolado não é o problema.** Sites que o dono admira usam alguns destes: uma palavra do título em cor, Inter, Poppins. Eles compensam com imagem, escala ou ideia. O que denuncia é a soma, sem nada de próprio. Tirar todos os clichês também não basta: título de 48px, cor só no botão e nenhuma imagem é a outra cara do gerador. Veja `references/marca/criatividade.md`.

## Cor

- Índigo, violeta ou lilás da paleta padrão do Tailwind (`#6366f1`, `#4f46e5`, `#4338ca`). `[script: ia-indigo]`
- Paleta inteira de valores padrão do Tailwind ou do shadcn, sem nenhuma decisão. `[script: ia-paleta-padrao]`
- Gradiente de roxo para azul. Gradiente em texto. `[script: ia-gradiente-roxo, ia-texto-gradiente]`
- Quase preto com um acento neon.
- Creme com serifa e terracota: virou o novo padrão de quem foge do índigo. `[script: ia-creme-terracota]`
- Cinza puro nos neutros, sem nenhum tom da marca.
- Texto cinza claro para parecer elegante. Passa do contraste antes de parecer elegante.

## Tipografia

- Inter, Roboto, Poppins ou Montserrat em tudo, sem decisão. `[script: ia-fonte-padrao]`
- Hierarquia só por tamanho, sem peso nem cor.
- Um rótulo pequeno, em caixa alta e espaçado, acima de cada título. `[script: ia-sobrancelha]`
- Uma palavra do título em itálico, cor ou gradiente diferente. `[script: ia-palavra-destaque]`
- Monoespaçada em rótulo, para parecer técnico. Fica para código e dado. `[script: ia-mono-enfeite]`
- Título com letras tão apertadas que as palavras se colam: "Seulook, dodiaàfesta". `[script: a11y-letra-apertada]`

## Composição

- Três ou quatro cartões iguais, com ícone em quadradinho, título e duas linhas. `[script: ia-cards-iguais]`
- Cartão dentro de cartão. `[script: ia-cartao-em-cartao]`
- Tudo com o mesmo raio grande e a mesma sombra suave.
- Herói centralizado: título, subtítulo, dois botões e uma captura flutuando em perspectiva.
- Painel padrão: barra lateral escura, quatro indicadores em linha, gráfico de área, tabela de "recentes".
- Cartão com borda colorida só à esquerda. `[script: ia-borda-esquerda]`
- Seções alternando branco e cinza sem relação com o conteúdo.
- Pílula colorida para tudo que é etiqueta.
- Numeração 01 / 02 / 03 em conteúdo que não é sequência. `[script: ia-numeracao]`
- Número enorme, rótulo pequeno e acento, em série. `[script: ia-metrica-heroi]`
- Jornal: fios finos, colunas densas e raio zero, sem o assunto pedir. `[script: ia-jornal]`
- Sombra dura deslocada, fora de um mundo neobrutalista. `[script: ia-sombra-dura]`
- Vidro e desfoque como decoração. `[script: ia-vidro]`
- Linha de metadados com pontos médios: "Edição 12 · Outono · São Paulo". `[script: ia-pontos-medios]`

## Marca e ícones

- Iniciais ou ícone genérico dentro de um quadrado colorido no lugar do logo. `[script: g-logo-em-quadrado]`
- Ícone de faíscas para "inteligente", raio para "rápido", escudo para "seguro". `[script: ia-faisca]`
- Emoji no lugar de ícone. `[script: ia-emoji]`
- Um ícone do mesmo pacote padrão em cada item, mesmo quando o texto já diz tudo.
- Seta no fim do botão: "Começar agora →". `[script: ia-seta]`

## Movimento

- A mesma animação de entrada em todas as seções.
- Cartão que sobe e ganha sombra em todo hover.
- Brilho e pulsação sem significado. `[script: ia-pulso]`

## Texto

- Frases vazias: "Transforme seu negócio", "Solução completa", "Sem complicação", "Bem-vindo de volta", "Sua jornada". `[script: ia-texto-cliche]`
- Tríades de adjetivos: "Simples. Rápido. Seguro."
- Frase de efeito em negativa: "Não é só tecnologia, é tempo devolvido". `[script: ia-frase-de-efeito]`
- Números de vaidade inventados: "+10 mil clientes", "99,9%".
- Depoimentos falsos e logos de empresas que não são clientes.
- Subtítulo que repete o título com outras palavras.
- Linguagem de anúncio em tela de trabalho. Quem usa todo dia precisa de rótulo, não de promessa.
- Erro que não diz o que fazer.

## O que colocar no lugar

Volte a `references/marca/identidade.md`: conceito do mundo do produto, elemento-assinatura funcional, voz de quem é do setor. Substituir um clichê por outro não conta.

Dados de exemplo fazem parte da identidade. "João Silva", "Empresa ABC" e valores redondos denunciam tanto quanto a cor. Use nomes e situações que existiriam nesse negócio.
