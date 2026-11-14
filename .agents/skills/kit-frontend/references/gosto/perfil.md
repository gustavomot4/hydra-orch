# Perfil de gosto do dono do kit

Tirado das mensagens que ele escreveu ao aprovar ou reprovar telas e indicar referências, de agosto a novembro de 2026. Cada regra traz a frase e a data. Prevalece sobre `references/padroes/` e `estilos/`, e perde para o piso de `references/qualidade/acessibilidade.md`, para o `DESIGN.md` aprovado no projeto e para um pedido explícito na conversa.

Em uma frase: **em tela de trabalho, limpo e direto como a Apple e familiar como o WhatsApp e o Uber; em tela de marca, impacto como Nubank e Valorant. Sempre com cara própria, e sem nada que pareça feito por IA.**

As regras marcadas com `[script]` são checadas por `scripts/verificar.mjs`. As outras você confere e relata.

## O que ele sempre quer

| Id | Regra | De onde veio |
| --- | --- | --- |
| G01 | **Bater o olho e saber o que fazer.** Em 5 segundos a pessoa diz o que a tela informa e qual é a próxima ação. Uma ação principal por tela. `[script]` | "é difícil o usuário já bater o olho e saber o que fazer" (02/09) |
| G02 | **Só o valioso.** Cada elemento precisa mudar uma decisão de quem usa. Espaço não é para preencher. Tire indicador, gráfico e texto que não mudam nada. | "queremos que tenha apenas o valioso, não precisa preencher espaços" (02/09); "elimine da dashboard coisas que não geram valor" (01/10) |
| G03 | **Pouco texto.** Título curto, sem subtítulo explicativo por padrão. Indicador é rótulo e número. `[script]` | "muito texto em algumas partes, principalmente as KPI" (01/10) |
| G04 | **Poucos cliques na tarefa essencial.** Conte os cliques da tarefa mais frequente e relate o número. | "consegue fazer o agendamento em poucos cliques" (02/09) |
| G05 | **Claro por padrão, com cor interessante.** Tema claro é a base. Limpo não pode virar sem graça: a paleta tem decisão própria. | "esse tom mais claro encaixou perfeitamente" (02/09); "coloque cores mais interessantes" (09/10) |
| G06 | **Identidade antes de código, e nada de cara de IA.** Siga `references/marca/identidade.md` e `references/marca/anti-generico.md`. | "muito genérico, muita cara de IA" (09/10); "o sistema não tem identidade visual" (28/10) |
| G07 | **O computador usa a tela do computador.** Nada de layout de celular esticado ou encolhido num monitor. `[script]` | "parece que só pegou tudo que tava no celular e colou no PC, tem muito espaço livre" (20/08) |
| G08 | **Equilíbrio visual na área útil.** Página de largura limitada (formulário, edição, detalhe) fica centralizada na área útil. Nada termina à esquerda com um vazio grande à direita. `[script]` | "espaço muito grande sem conteúdo nenhum e não está centralizado"; "a grande maioria está mais alinhada para a esquerda" (28/10) |
| G09 | **Sem rolagem presa.** Nada de área com rolagem própria dentro de página que também rola. Coluna de detalhe acompanha a rolagem. `[script]` | "você tem que scrollar todos os pacientes do card ao lado primeiro" (28/10) |
| G10 | **Lista grande pagina.** Sempre com faixa e total. `[script]` | "algumas listas são muito grandes, coloque paginações" (28/10) |
| G11 | **Dado que cresce não vai em dropdown.** Use busca com sugestões. Lista suspensa só para opções fixas e poucas. `[script]` | "evite dropdown onde recebe bastante dados" (28/10) |
| G12 | **Tabela diz o que é cada dado.** Cabeçalho sempre; no celular, cada valor com o nome. `[script]` | "uma tabela que mostra os dados mas não fala que dados são" (28/10) |
| G13 | **Situações que não se confundem.** Cor próxima não basta: mude também forma, ícone e texto. Compare duas a duas as situações que ficam lado a lado. | "uma pessoa pode confundir o confirmado com o concluído" (28/10) |
| G14 | **Gráfico de bater o olho.** Rótulo direto no dado, no máximo duas séries sem pedido, e a frase que o gráfico responde como título. | "o gráfico de entrada e saída está confuso, bater o olho e já saber" (28/10) |
| G15 | **O sistema preenche por mim.** Endereço pelo CEP (ViaCEP), `autocomplete` em todo campo, nunca pedir de novo. Comece do contexto: clicar num horário vazio já abre o agendamento com o horário. | "ninguém merece ficar escrevendo todos os campos do endereço" (28/10) |
| G16 | **Familiar para quem só usa o celular.** Barra de abas, folha inferior, "Desfazer", lista de conversas. Copie o comportamento, nunca a aparência. | "pra ela tecnologia é Instagram, Uber, WhatsApp" (28/10) |
| G17 | **Logo não vai em quadradinho.** Nada de iniciais num quadrado colorido. Entregue versões da marca (positiva, negativa) e use a que respira no fundo. `[script]` | "a logo dentro desse quadrado fica muito feia" (28/10) |
| G18 | **Nada solto.** Todo controle pertence a um grupo com sentido. Ícone sozinho na barra precisa de motivo. | "achei meio estranho esse botão de pesquisa solto na navbar" (28/10) |
| G19 | **Estado e ação dizem a mesma coisa.** A situação escrita e o botão seguinte não podem parecer contraditórios. | "aparece se foi confirmado ou não, mas no botão está iniciar atendimento" (28/10) |
| G20 | **Responsivo de verdade.** Formulário longo é o que mais quebra: teste cada um em 375 e 320. `[script]` | "a tela de agendar consulta tem muitos erros de responsividade" (28/10) |
| G21 | **Tema escuro só com estudo.** Nunca inverta cores. Siga `references/padroes/tema-escuro.md` e mostre ideias antes de aplicar. | "esse modo escuro está muito feio"; "faça um estudo com outros do mercado" (09/10) |
| G22 | **Emoção quando o produto pede.** Em jogo e entretenimento, animação, som e imagem são o produto. Só de bater o olho a pessoa sabe o que é. | "sinto que falta emoção" (20/08) |
| G23 | **Para todos, de verdade.** Libras, pouca leitura, daltonismo e baixa visão são requisito de produto, e não podem custar a identidade. Liste quem usa em `publicos:` e siga `references/qualidade/publicos.md`. `[script]` | "com acessibilidades (libras, leitura, daltonismos, pessoas com pouca leitura, pessoas com pouca visibilidade etc...) para todos, bonito, intuitivo" (30/10) |

## Como ele decide

- **Por imagem, não por texto.** Mostre três propostas em imagem, com texto mínimo. "o core são as imagens, não exagere nos textos" (28/10).
- **Pega o melhor de cada proposta.** Escolher "a A com a agenda da B" é normal. Registre a mistura no `DESIGN.md`.
- **Decide com a equipe e o cliente.** Entregue as imagens num formato fácil de repassar (PDF ou página). Um pedido do cliente pode vetar parte da proposta: a agenda em grade, com horas num eixo e dias no outro, foi exigência.
- **Testa de verdade e volta com lista.** Quando ele reclama de uma tela, verifique todas: "tem várias páginas com esse mesmo problema".
- **Pede prova.** Diga o que rodou, com o resultado real, e o que não foi verificado.

## Calibração por imagem

Escolhas feitas olhando telas lado a lado. Cada linha é um sinal, não uma regra: vira regra quando se repete em outro produto.

| Data | Tela e opções | Escolha | O que sugere |
| --- | --- | --- | --- |
| 30/10/2026 | Tela Hoje de uma barbearia fictícia. A: lista como a de conversas. B: o salão por cadeira, com a listra do poste. C: cartaz com o próximo cliente | **B** | Prefere a tela organizada por algo real do negócio a uma lista genérica. Aceita tipografia com caráter e cantos retos num sistema de trabalho, quando têm função |

| 30/10/2026 | Tela principal de uma marmitaria fictícia: uma tela feita por agente sem o kit contra três direções feitas com ele | **A, lista e detalhe, a mais familiar** | Para uma dona que não entende de tecnologia, prefere o formato que ela já conhece, sem painel de indicadores e com pouco texto |
| 01/11/2026 | Site de uma oficina de bairro, em teste do kit. A: conversa de WhatsApp. B: ordem de serviço. C: luzes do painel | **A, a conversa** | De novo o formato familiar para público leigo. Os dois agentes da escolha cega apontaram a B |

Nas três vezes ele só deu a escolha, sem motivo: a coluna da direita é leitura do agente. Na primeira, a prancha recomendava a B, o que pode ter pesado. Na segunda, a prancha dizia qual tela vinha do kit, que é dele, e não recomendava nenhuma.

Hipótese a confirmar: a escolha muda com o público. Quanto menos familiaridade de quem usa, mais pesa o formato conhecido. A clínica aponta para o mesmo lado: em 28/10, o grupo preferiu a proposta "conversa". A oficina também, e mostra que a escolha cega não prevê o dono: use a crítica dos avaliadores, não só o voto.

## Referências que ele cita

| Referência | O que aproveitar | Contexto |
| --- | --- | --- |
| Apple | Limpeza, hierarquia, poucos elementos, tom claro | Pedido em 02/09 e origem do `base-design-system` |
| WhatsApp, Instagram | Lista de conversas, familiaridade | Público leigo |
| Uber, 99, iFood, GetNinjas | Fluxo direto, uma decisão por vez, escolha por cartões | População com níveis variados de letramento |
| EA FC | Menus com impacto, animação, imagem | Só para jogo |
| Nubank, C6, Itaú, 99, iFood Parceiros | Título enorme, cor de marca em área grande, foto real, um campo na primeira dobra | Citados em 30/10 como os que gosta, para criatividade |
| Valorant, Fortnite, Epic Store | Arte dominante, tipografia de impacto, escuro com cor forte | Citados em 30/10, para criatividade |
| Hyper3D, CozyGPU, Cequence | Produto em ação, ilustração própria, diagrama | Citados em 30/10, para criatividade |

Como aplicar essas referências está em `references/marca/criatividade.md`. Ele citou os sites sem dizer do que gosta em cada um: o "o que aproveitar" dessas três linhas é leitura do agente.

## Referências indicadas em 01/11/2026

McDonald’s, Burger King, Canva, Globoplay, Netflix Brasil, Mercado Livre e Inter. Links e análise em `references/marca/criatividade.md`.

> "site que eu acho bonito e o kit deveria pegar inspirações neles, para entender como essas marcas construa sua identidade visual e como elas transmite isso e como elas construem o seus sistemas" — dono do kit, 01/11/2026, nesta conversa.

Pedido confirmado: estudar identidade, sua transmissão e construção de sistemas. Ele não escolheu cor, fonte, tema ou detalhe de cada site. As interpretações do estudo são do agente e dependem da marca e do público do projeto; não ampliam automaticamente G05 ou G22.

## Já reprovado

- Paleta índigo e lilás padrão do Tailwind (`#6366f1`, `#a5b4fc`, `#c7d2fe`): "muita cara de IA".
- Tema escuro por inversão de cores.
- Barra lateral escura com turquesa e cartões brancos iguais: o painel administrativo genérico.
- Tela densa, cansativa, com muita informação ao mesmo tempo.
- Marca dentro de quadrado colorido.

## Ainda sem resposta: pergunte uma vez e registre aqui

1. Há fontes que ele prefere ou detesta?
2. Tema escuro é desejado por padrão ou só quando o produto pedir?
3. Quanto de expressão ele aceita num sistema de trabalho? Em 30/10 escolheu a mais própria numa barbearia e a mais familiar numa marmitaria. Falta entender o que decide.
4. Do que exatamente ele gosta em cada site citado em 30/10? Mostre `references/marca/criatividade.md` e peça para ele marcar o que acertou e o que errou.

## Como este arquivo cresce

Correção recebida em projeto vai para `design/correcoes.md` (ver `SKILL.md`, etapa 8). O comando `kit coletar` junta as correções em `references/gosto/correcoes-coletadas.md`. Quando a mesma correção aparece em dois projetos, ela vira regra aqui.
