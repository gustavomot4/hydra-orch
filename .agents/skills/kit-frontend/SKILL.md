---
name: kit-frontend
description: Cria e refatora frontend com identidade própria, padrões consolidados do mercado e acessibilidade verificada, para aprovar na primeira rodada e evitar retrabalho. Use em qualquer pedido de tela, página, landing, painel, formulário, tema, visual, UI ou UX, em qualquer stack, inclusive "deixa mais bonito", "está com cara de IA", "refatora o frontend" ou "não gostei desse visual".
compatibility: Os scripts pedem Node 22 ou mais novo e Chrome, Edge ou Chromium instalado. Sem eles, a skill funciona com a verificação manual.
metadata:
  version: "3.2.0"
---

# Kit de frontend

## Antes de qualquer coisa

1. Leia `references/gosto/perfil.md` e `references/gosto/correcoes-coletadas.md`. Abra as outras referências conforme a etapa pedir.
2. No projeto, leia o que existir: `design/correcoes.md`, `DESIGN.md`, `MARCA.md`, `PRODUTO.md`.
3. Em caso de conflito, vale esta ordem:
   1. O piso de `references/qualidade/acessibilidade.md`. Se um pedido bater nele, avise e proponha uma saída.
   2. O pedido explícito nesta conversa.
   3. `design/correcoes.md`.
   4. `DESIGN.md` e `MARCA.md`.
   5. `references/gosto/perfil.md`.
   6. `references/padroes/`.
   7. O estilo de partida, com as ressalvas de `references/recursos/estilos.md`.

## Escolha o caminho

| Situação | Caminho |
| --- | --- |
| Projeto sem telas e sem `DESIGN.md` | Etapas 1 a 8 |
| Site institucional ou landing, novo | Etapas 1 a 8. A home é a tela principal, e os estados da etapa 5 vêm de `references/padroes/landing.md` |
| Produto existente sem `DESIGN.md`, ou "está com cara de IA" | Rode a verificação nas telas atuais, mostre o diagnóstico com capturas e siga as etapas 1 a 8. Se já há marca, a etapa 2 a documenta |
| Pedido de marca, identidade ou brief | Etapas 1 a 4: o kit de identidade vem depois da direção |
| Tela nova com `DESIGN.md` aprovado | Etapas 6 a 8 |
| Ajuste pontual | Etapas 6 a 8, só na tela e nas iguais a ela |
| Pedido só de revisão | Etapa 7, sem alterar nada |

## Vale desde a primeira tela

Estas regras moram em `references/`, mas valem já nas três direções. Deixá-las para depois faz o dono escolher uma tela que vai mudar:

- **Site público:** botão de Libras desde as direções. É uma linha, sem vídeo (`references/padroes/midia-e-libras.md`).
- **Altura até 480px:** o que é fixo passa a rolar junto.
- **Hover:** só dentro de `@media (hover: hover) and (pointer: fine)`.
- **Barra de ação fixa no celular:** tire o mesmo botão da primeira dobra.
- **Logo em SVG:** versão para alto contraste (`references/qualidade/acessibilidade.md`).

## As etapas

### 1. Entender

Crie `PRODUTO.md` a partir de `assets/modelos/produto.md`. Aproveite o código e os documentos. Faça até 5 perguntas que mudem decisões de tela, com uma recomendação por pergunta. Preencha `publicos:` seguindo `references/qualidade/publicos.md`.

### 2. Marca: portão

Defina a mensagem antes do visual. Use `assets/modelos/marca.md` e `references/marca/criar-marca.md`. Registre hipóteses sobre personas e o que cada decisão de marca muda na tela. Confira com `scripts/conferir-marca.mjs`. Com marca existente, peça o logo e as cores originais. Para começar do zero, siga "Quando a pessoa não tem nada" na referência.

Mostre um resumo de até 10 linhas. **Pare e espere a confirmação.**

### 3. Três direções: portão

Sem código de produção antes da escolha. Cada direção expressa o `MARCA.md`. Siga `references/marca/identidade.md` e `references/marca/criatividade.md`, e confira `references/marca/anti-generico.md`. Para imagem, vídeo, 3D e animação, veja `references/recursos/bibliotecas.md`; o que você não puder gerar vai para `design/midia.md` (modelo em `assets/modelos/midia.md`).

- **Antes de qualquer referência,** escreva a primeira ideia em `design/direcoes/primeira-ideia.md`. Depois, `design/direcoes/ideias.md` (modelo em `assets/modelos/ideias.md`): duas referências de fora do setor medidas com `scripts/medir-referencia.mjs` e os três conceitos, no máximo um vindo da primeira ideia. Não recomende nada ainda.
- Nas referências, ligue sinal visual, mensagem percebida, regra de sistema e aplicação no produto (`references/marca/criatividade.md`). Separe observação de interpretação.
- Em `design/direcoes/`: a tela mais usada do produto (num site, a home), com os mesmos dados, em três arquivos HTML estáticos que diferem em ideia, tipografia, composição e cor. Título, imagem e ordem das seções são de cada direção. Cada um com o próprio CSS, sem gerador nem folha comum, e sem sacola, diálogo ou filtro funcionando. Gere cada paleta com `scripts/paleta.mjs`. Sem fonte definida, escolha com `references/recursos/fontes.md`.
- Com marca existente, use o logo real e faça ao menos uma direção partir de como ela aparece hoje. Sem o arquivo, escreva o nome em texto: não desenhe um substituto.
- Rode `scripts/comparar-direcoes.mjs design/direcoes` e refaça as quase iguais. Rode a verificação nas três e corrija as falhas. Olhe a página inteira de cada uma, até o fim.
- Rode `scripts/escolha-cega.mjs design/direcoes` e entregue o pedido a dois agentes novos, um de cada vez, que só veem as imagens. Se discordarem, é empate: leve as duas ao dono. Se ambos disserem "nenhuma", refaça as direções uma vez. Sem agente novo, escreva "escolha sem juízo externo" no `DESIGN.md`.
- Monte o material com `scripts/prancha.mjs design/direcoes`: as imagens em 1440 × 900 e 375 × 812 e a página inteira, com nome, conceito em uma frase, elemento-assinatura e o que a escolha cega apontou. Leve as frases de crítica dos avaliadores, não só o voto. Texto mínimo: quem decide olha a imagem.

**Pare e espere a escolha.** Misturas são bem-vindas. Se as três forem rejeitadas, registre o motivo em `design/correcoes.md` e refaça. Registre a direção escolhida no mesmo arquivo e aplique as críticas pertinentes.

**Decisão delegada.** Se o dono pediu para você seguir, escolha pela avaliação cega e resolva eventual empate. Registre a escolha provisória no `DESIGN.md` antes do código. Mostre as demais direções na entrega.

### 4. Travar

Escreva `DESIGN.md` a partir de `assets/modelos/design.md` (exemplo preenchido em `assets/exemplos/design.md`): o que se repete entre telas e o que varia por superfície. Gere os tokens da stack do projeto. Rode `scripts/contraste.mjs DESIGN.md`. Toda cor e todo tamanho usados daqui em diante vêm dele: confira com `scripts/conferir-tokens.mjs <pasta do código>`.

Prepare `design/marca/` conforme `references/marca/criar-marca.md`. Se o pedido inclui logo, gere 3 opções com `scripts/logotipo.py`, variando símbolo ou arranjo sobre a fonte escolhida. Use a tela-modelo nas aplicações do manual. Relate as limitações da proposta.

### 5. Tela-modelo: portão

Em código real: a casca (navegação nas larguras de `references/padroes/navegacao.md`) e a tela da etapa 3, com carregando, vazio, erro e sucesso. Site estático troca esses estados pelos de `references/padroes/landing.md`. Rode a verificação e mostre as capturas, junto com as opções de logo: é uma decisão a mais, não uma parada a mais.

**Pare e espere a aprovação.** Aplique as correções às telas seguintes.

### 6. Construir

No máximo 3 telas por entrega. Antes de cada tela, leia o padrão correspondente:

| Tela ou peça | Leia |
| --- | --- |
| Lista, tabela, busca, filtro | `references/padroes/lista-tabela.md` |
| Formulário, cadastro, passo a passo | `references/padroes/formulario.md` |
| Escolha entre opções, dropdown | `references/padroes/selecao.md` |
| Menu, casca, responsividade | `references/padroes/navegacao.md` |
| Painel, indicadores, gráfico | `references/padroes/painel.md` |
| Agenda, calendário | `references/padroes/agenda.md` |
| Carregando, vazio, erro | `references/padroes/estados.md` |
| Aviso, confirmação, desfazer | `references/padroes/retorno.md` |
| Vídeo, áudio, Libras | `references/padroes/midia-e-libras.md` |
| Landing, site, tela de marca | `references/padroes/landing.md` e `references/marca/criatividade.md` |
| Escolher biblioteca, ícone, animação, 3D, gerar mídia | `references/recursos/bibliotecas.md` |
| Tema escuro | `references/padroes/tema-escuro.md` |
| Receita completa de um tipo de produto | `references/recursos/estilos.md` |

Reaproveite os componentes já feitos. Valor novo entra no `DESIGN.md` primeiro. Em dados de exemplo, use nomes e situações do setor, nunca dados reais.

### 7. Verificar

Em cada tela alterada, com ela no ar ou como arquivo:

```bash
node <pasta da skill>/scripts/verificar.mjs http://localhost:5173/agenda
```

O verificador mede quatro tamanhos, foco, letra em 200%, alto contraste, peso, links internos e texto de implementação exposto. Em `design/verificacao/<tela>/` ficam `resultado.json`, as capturas (`desktop-inteira.jpg` e `celular-inteira.jpg` mostram a página inteira), `prancha.html` e `leitor-de-tela.txt`.

- Corrija falhas e resolva ou justifique avisos. Decisão aprovada entra no `DESIGN.md`.
- Corrija pelo relatório primeiro. Na última rodada, abra uma vez a página inteira e a prancha. A primeira dobra pode esconder defeitos. Em cinco segundos, identifique o que a tela informa e qual ação oferece.
- Percorra a tarefa principal a partir do `PRODUTO.md` e registre o resultado conforme `references/qualidade/jornadas.md`.
- Faça o roteiro de `references/qualidade/acessibilidade.md`, que inclui a prova de interação e o uso opcional do axe-core.

**Sem Node ou sem navegador:** cole `scripts/tela.js` no console e confira o `resultado.achados`. **Sem como executar nada:** diga isso na primeira linha, entregue os comandos e nunca relate como executado o que não foi.

### 8. Aprender

Quando o dono reprovar algo, nesta ordem:

1. Registre em `design/correcoes.md` (modelo em `assets/modelos/correcoes.md`): o que foi reprovado, nas palavras dele, e a **regra geral**.
2. Procure o mesmo problema em **todas** as telas e corrija a classe do problema, não o caso.
3. Se ele contradiz o `DESIGN.md`, atualize o `DESIGN.md`.

## Como relatar

Curto, com imagem. Nesta ordem:

1. O que mudou, com as capturas.
2. Resultado real do verificador, por tela: falhas e avisos restantes, com o motivo.
3. Resultado da jornada, cliques, evidência e ponto de bloqueio, quando houver.
4. O que não foi verificado, com cada item do roteiro manual que ficou de fora. Se não houve teste com leitor de tela ou com pessoas, escreva isso. Nunca diga "acessível" ou "em conformidade" sem dizer como verificou.
5. O que depende da pessoa.

## Conduta

- Trate dado que já existe como real: não copie para protótipo, teste ou captura. Com dado de saúde, o cuidado é maior.
- Não invente regra de negócio, indicador, número, depoimento nem integração. Traga a pergunta com a sua recomendação.
- Não afirme nada sobre o setor ou os concorrentes sem ter olhado. Sem medir, diga que é impressão.
- Preserve o que não é seu. Commit, push e publicação só com autorização, e cada autorização vale só para aquela ação.
- Relate com fidelidade o que falhou, o que ficou instável e toda diferença em relação ao que foi aprovado.
