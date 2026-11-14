# Marca: o que definir antes da tela

Sem isto, a identidade nasce de decisões de tela e vira gosto do momento. Aqui se define o que o produto quer dizer, para quem e contra quem. As direções visuais (`references/marca/identidade.md`) são formas de expressar a marca, não o ponto de partida.

Já existe marca? **Documente, não invente.** Preencha `MARCA.md` com o que existe e marque as lacunas. **Peça o arquivo do logo e as cores originais antes de confirmar o brief**: quem decide precisa se reconhecer nas direções. Se o arquivo não vier, escreva o nome em texto, em letra parecida, e diga que é provisório. Não desenhe um substituto: num teste real, o símbolo redesenhado a partir de uma miniatura virou outra coisa (`docs/testes/2026-10-31-outro-agente`, no repositório do kit).

## Tamanho certo

| Produto | Brief | Kit de identidade |
| --- | --- | --- |
| Pequeno negócio, ferramenta interna, demonstração | `curto`: uma página | Logotipo, cor e fonte |
| Produto para clientes | `completo` | Kit inteiro |
| Marca que vai investir no mercado | `completo` e personas com pesquisa | Kit como ponto de partida para um designer |

Na dúvida, comece curto. Um brief longo que ninguém lê não muda tela nenhuma.

## Quando a pessoa não tem nada

Quem não tem marca não consegue responder "qual é a sua mensagem?". Não pergunte o que ela não sabe. **Faça perguntas que qualquer um responde e, depois, ofereça opções para escolher.**

### Perguntas

1. O que você vende, e para quem? Como diria numa conversa.
2. Por que um cliente volta, ou por que indicaria você?
3. Cite de 2 a 4 sites ou aplicativos de que gosta, de qualquer setor, e um de que não gosta.
4. Quem faz a mesma coisa perto de você, ou o que seu cliente usa hoje?
5. Já existe algo que precisa ficar: nome, cor, logo, foto?

"Não sei" é resposta válida: siga com a sua proposta, marcada como hipótese.

### Referências

Meça o que a pessoa citou:

```bash
node scripts/medir-referencia.mjs https://site-de-que-ela-gosta.com.br
```

O script lista fontes, escala, cores, raios e mídia, sem clicar em nada. Diga o que os sites têm em comum e confirme: gostar de um site não é gostar de tudo nele. Se um site bloquear o acesso, peça uma captura à pessoa. Copie o raciocínio, nunca a marca.

### Opções para escolher

| Falta | O agente oferece | Como |
| --- | --- | --- |
| Nome | 5 opções, com o motivo de cada uma | O agente não confere registro: INPI e domínio ficam com a pessoa |
| Mensagem | 3 promessas, de ângulos diferentes | Uma frase cada |
| Personalidade | 3 conjuntos de três palavras | Cada conjunto com uma frase de exemplo |
| Voz | A mesma mensagem de erro, em 3 tons | É mais fácil escolher lendo do que definindo |
| Cor | 3 paletas | 3 cores vindas do mundo do produto, longe dos concorrentes: `node scripts/paleta.mjs "#cor" --evitar "#concorrente"` |
| Fonte | 3 candidatas | `references/recursos/fontes.md` |
| Logotipo | 3 logotipos tipográficos | `scripts/logotipo.py`, com cada candidata de fonte. Depois da escolha da direção, a fonte está decidida: varie o símbolo ou o arranjo |

Junte para não cansar. Mensagem, personalidade e voz vão numa única rodada, em texto curto. Cor, fonte e logotipo aparecem juntos nas três direções: ninguém escolhe bem uma paleta no abstrato. Se a pessoa disser "escolhe você", decida e marque como provisório.

Diga a verdade sobre o resultado: é um bom ponto de partida, feito em horas. Não substitui um estúdio de marca, e a escolha precisa ser testada com gente do público.

## Como conduzir o brief

1. **Deduza primeiro:** código, documentos, site atual e conversa.
2. **Pergunte no máximo 5 coisas**, cada uma com a sua recomendação. Pergunte por escolha e por exemplo, não por adjetivo: "Se o produto fosse uma pessoa do setor, quem seria?", "Qual concorrente você não quer parecer?", "O que um cliente diria ao indicar?".
3. **Escreva `MARCA.md`** a partir de `assets/modelos/marca.md`. Veja o nível esperado em `assets/exemplos/marca.md`.
4. **Mostre um resumo de até 10 linhas e espere a confirmação.** Quem decide não lê brief longo.

## Regras do brief

**Todo item muda uma decisão.** A seção "O que isso muda na tela" é obrigatória: "Usa com a mão suja → alvo de 48px". Se nada muda, corte. Hobby e foto de persona não mudam nada.

**Personalidade com custo.** Três palavras, cada uma com o que ela recusa: "Direta, não seca". Palavras que qualquer concorrente diria não valem: moderno, inovador, confiável, simples, premium, profissional.

**Tom em quatro dimensões.** Marque onde o produto fica em cada uma: formal ou casual, sério ou engraçado, respeitoso ou irreverente, neutro ou entusiasmado. O tom varia com o momento: um erro é mais sério que uma boas-vindas. A personalidade não muda.

**Personas: poucas, e honestas sobre a base.**

| Base | O que é | Como tratar |
| --- | --- | --- |
| `hipótese` | Suposição, sem pesquisa | É o padrão do agente. Pode reforçar uma premissa errada: diga como validar |
| `pesquisa` | Entrevistas com pessoas reais; de 5 a 30 já ajudam | Cite quantas |
| `dado` | Pesquisa em escala ou uso real do produto | Cite a fonte |

De 1 a 3 personas: objetivo, medo, contexto de uso e familiaridade com tecnologia. Sem dados reais de pessoas.

**Concorrentes olhados de verdade.** De 3 a 5, incluindo o que a pessoa usa hoje, mesmo que seja caderno ou WhatsApp. Abra as telas com `scripts/medir-referencia.mjs` e anote cor, fonte e tom. "Não verificado" só depois de tentar. Termine dizendo qual é o espaço livre: o que ninguém ocupa e faz sentido para este produto.

**Sem palpite sobre o setor.** O brief curto não tem seção de concorrentes, mas isso não autoriza dizer que uma cor ou um jeito é comum sem ter olhado. Abra duas ou três telas com `scripts/medir-referencia.mjs`, ou diga que é impressão.

**Sem promessa falsa.** Não invente número, prêmio nem depoimento.

## Kit de identidade

Faça **depois** da escolha da direção (etapa 4 da skill), para não desenhar logo de uma direção descartada.

| Peça | Arquivo | Regra |
| --- | --- | --- |
| Logotipo | `design/marca/logo-positivo.svg`, `logo-negativo.svg` | Em curvas, sem `<text>`. Legível com 24px de altura. 3:1 contra o fundo. Sem iniciais em quadrado (G17). Na tela, com versão para alto contraste (`references/qualidade/acessibilidade.md`) |
| Ícone | `design/marca/icone.svg` | Funciona em 16 e 32px, como ícone de aba e de aplicativo |
| Cor, tipografia, forma | `DESIGN.md` | Valores e motivos, com contraste calculado |
| Fontes | `design/marca/fontes/` | WOFF2 com subconjunto latino e o arquivo de licença ao lado |
| Imagem e ilustração | `design/midia.md` | Um estilo único. Ver `references/recursos/bibliotecas.md` |
| Voz | `MARCA.md` | Frases reais de botão, vazio, erro e sucesso, só as que a tela vai usar |
| Manual | `design/marca/manual.html` | Uma página: logotipo e usos errados, cor, tipo, voz e o que não fazer |
| Aplicações | No manual, depois da tela-modelo | A marca em uma tela real, um post quadrado e o ícone do aplicativo |

Confira com `node scripts/conferir-marca.mjs` e rode `scripts/verificar.mjs` no manual.

## Logotipo: o que esperar

Um agente resolve bem o **logotipo tipográfico**: o nome, numa fonte escolhida, com um detalhe próprio. É o caminho padrão.

```bash
python scripts/logotipo.py fonte.woff2 "Nome" design/marca/logo.svg --peso 800 --eixo opsz=96 --cor "#14304f" --simbolo simbolo.svg --cor-simbolo "#b3261e" --variantes
```

O script aplica o kerning da fonte e aceita outros eixos, como `--eixo opsz=96`. Olhe o resultado e corrija pares com `--ajuste "r,e:-14"`. Com `--simbolo`, ele põe o desenho ao lado do nome; com `--variantes`, grava `logo-positivo.svg`, `logo-negativo.svg` e `logo-sobre-marca.svg`. Sem logo definido, gere 3 versões e mostre cada uma com 24 e 64px de altura, sobre fundo claro e escuro. Antes da direção, varie a fonte; depois dela, o símbolo ou o arranjo. Um logotipo que só funciona grande está reprovado.

Um **símbolo** só se tiver ideia simples, do mundo do produto: uma forma geométrica, poucos traços. Se sair genérico, diga. Não entregue um símbolo fraco só para ter um. Para símbolo memorável, indique gerador de imagem ou designer, e registre em `design/midia.md`.

## Fonte: três níveis

| Nível | O que é | Quem faz |
| --- | --- | --- |
| 1 | Fonte aberta pouco usada, com escala e peso marcantes (`references/recursos/fontes.md`) | O agente. É o padrão |
| 2 | Logotipo próprio e fonte aberta adaptada | O agente, com revisão de quem entende |
| 3 | Família exclusiva, do zero | Um designer de tipos, quando o produto justificar |

Na SIL Open Font License (a da maioria das fontes do Google Fonts), pode modificar e usar comercialmente, sem vender a fonte sozinha e mantendo a licença junto. Versão modificada não pode usar o Nome Reservado, se a fonte tiver um. Um logotipo feito com a fonte é um documento criado com ela, e a licença não o alcança. Confira a licença de cada fonte. Isso é leitura técnica, não parecer jurídico.

## Depois do brief

- Cada direção de `references/marca/identidade.md` precisa expressar `MARCA.md`. Direção que contradiz o brief sai, por mais bonita que seja.
- O `DESIGN.md` cita a marca e explica como cada escolha a expressa.
- Se o dono escolher contra o brief, é o brief que está errado: pergunte o motivo e atualize.
