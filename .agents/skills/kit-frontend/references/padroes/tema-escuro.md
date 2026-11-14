# Tema escuro

Pedido explicitamente depois de um tema escuro reprovado. (G21) Só crie quando o produto pedir, e mostre ideias em imagem antes de aplicar.

## Regra

- **Não é inversão.** É uma paleta nova, com seus próprios pares calculados.
- **Fundo sem preto puro:** cinza muito escuro, tingido pelo matiz da marca. Sobre `#000`, texto branco cria halo em muita gente.
- **Elevação por claridade:** quanto mais alta a camada, mais clara. Sombra quase não aparece no escuro. Defina de 3 a 4 níveis.
- **Texto sem branco puro** na leitura longa: de 87 a 92% de claridade. Contraste continua em 4,5:1 ou mais.
- **Cor de marca precisa de outro tom.** A cor saturada do tema claro vibra no escuro. Clareie e dessature, e recalcule o par com o texto em cima.
- **Situações ganham par próprio:** texto claro sobre fundo escuro do mesmo matiz.
- **Imagem e sombra:** reduza um pouco o brilho de foto e troque ilustração de fundo branco.
- **Três estados:** claro, escuro e seguir o sistema. Guarde a escolha e aplique antes da primeira pintura, para não piscar.
- **`color-scheme: dark`** para controles nativos e barras de rolagem.
- **Alto contraste é outro tema.** Não use como substituto, e respeite `forced-colors`.

## Como testar

Todos os pares em `scripts/contraste.mjs`. Capture as telas principais nos dois temas. Olhe em ambiente escuro e claro. Foco, borda de campo e gráfico continuam em 3:1.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| Material | Elevação por camada mais clara, fundo escuro não preto, cores dessaturadas (conhecimento geral) |
| Apple | Verificar contraste nos dois modos; versão de maior contraste quando a pessoa pedir |
| Linear | Geração de tema a partir de poucas variáveis, para claro e escuro saírem do mesmo sistema |

Exemplo completo de três temas em `estilos/app-tarefas-acessivel/`, com a ressalva de `references/recursos/estilos.md` sobre a paleta.
