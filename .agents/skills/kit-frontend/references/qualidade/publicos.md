# Públicos: o que muda para cada um

O piso de `references/qualidade/acessibilidade.md` vale sempre. Esta ficha diz o que muda quando se sabe quem vai usar. No Brasil, 14,4 milhões de pessoas têm deficiência (45,4% delas com 60 anos ou mais) e 29% de quem tem de 15 a 64 anos é analfabeto funcional. "Para todos" não é um nicho.

## Como ativar

No `PRODUTO.md`, liste quem usa e onde a tela fica. Sem pesquisa, marque como hipótese: errar por excesso custa pouco.

```
publicos: [surdos-libras, pouca-leitura, idosos]
superficie: publica
```

`verificar.mjs` lê esses campos, ou `--publicos a,b` na linha de comando. Um público listado muda o rigor de algumas checagens e, principalmente, as decisões de tela abaixo.

## Por público

| Valor | Na tela | Verificador | À mão |
| --- | --- | --- | --- |
| `surdos-libras` | Siga `references/padroes/midia-e-libras.md`. Em site público, a base é um botão de VLibras, sem vídeo. Português simples: para muitos surdos, o texto é segunda língua. Nada só em som. Contato por mensagem, não só por telefone | `a11y-libras` vira falha em superfície pública; `a11y-video-legenda` | Tarefa com uma pessoa surda |
| `pouca-leitura` | Coluna única e menu linear. O principal no alto. Ícone sempre com texto. Nada se mexendo perto do texto. Busca que aceita erro de digitação | `a11y-icone-sem-texto` e `a11y-letra-apertada` viram falha; `a11y-leitura-dificil` aperta o limite | Leia em voz alta. Tarefa com alguém do público |
| `idosos` | Alvo de 44px também com mouse. Ícone com texto. Sem gesto escondido nem tempo limite. Letra que cresce sem quebrar | `a11y-icone-sem-texto`, `a11y-letra-200`, `a11y-espacamento` | Letra do aparelho no máximo, num celular simples |
| `baixa-visao` | Contraste acima do mínimo no que decide a tarefa. Nada que dependa só de passar o mouse. Temas e tamanho de letra, quando o uso for diário | `a11y-letra-200`, `a11y-espacamento`, `a11y-alto-contraste`; visão embaçada na prancha | Zoom de 400% e alto contraste do sistema |
| `pessoas-cegas` | Títulos em ordem, regiões com nome, mudanças anunciadas. Tabela de verdade em vez de grade de `div` | `a11y-nome`, `a11y-titulos`; leia `leitor-de-tela.txt` | NVDA, VoiceOver ou TalkBack numa tarefa inteira |
| `daltonismo` | Situação com texto ou forma além da cor. Gráfico com rótulo direto no dado e forma por série. Evite separar só por vermelho e verde | `a11y-so-cor`; olhe `prancha.html` | Compare na prancha as situações lado a lado (G13) |
| `dislexia` | Até 80 caracteres por linha, texto sem justificar, entrelinha de 1,5, sem bloco em itálico ou caixa alta, sem letras apertadas. Não prometa "fonte para dislexia" | `a11y-linha-longa`, `a11y-justificado`, `a11y-entrelinha`, `a11y-italico-longo`, `a11y-caixa-alta`; `a11y-letra-apertada` vira falha | Leitura com alguém do público |
| `cognitivo` | Sempre dá para voltar e desfazer. Nada depende de memorizar nem de tempo. Um passo por vez. Linguagem literal. Ajuda humana fácil de achar | `a11y-icone-sem-texto`, `a11y-leitura-dificil` | Percorra a tarefa sem instrução prévia |
| `mobilidade` | Alvo grande, tudo pelo teclado, alternativa a arrasto | `a11y-alvo`, `a11y-teclado`, `a11y-clique-sem-semantica` | Tarefa inteira só com teclado |

Fonte para dislexia: o estudo de Wery e Diliberto, com 12 alunos, não achou ganho da OpenDyslexic sobre Arial ou Times. As regras de layout vêm do critério 1.4.8 da WCAG, de nível AAA: aqui são decisão do kit, não exigência de conformidade.

## O que o verificador entrega para isto

- **`prancha.html`:** a tela sem verde, sem vermelho, sem azul, sem cor, embaçada e em alto contraste. Procure duas situações que passaram a parecer iguais. Mostre a prancha ao dono junto das capturas.
- **`leitor-de-tela.txt`:** o que a árvore de acessibilidade entrega, na ordem. Se a tela não faz sentido lida assim, não faz sentido num leitor de tela.
- **Limite honesto:** simulação encontra problema, não prova ausência. Gráfico e situação que só a cor separa continuam dependendo do olho.

## Preferências dentro do produto

Em aplicativo de uso diário, ofereça temas e tamanho de letra como em `estilos/app-tarefas-acessivel`. Respeite antes o que o sistema já pede: `prefers-reduced-motion`, `prefers-contrast`, `forced-colors`, tamanho de fonte do navegador. A preferência fica salva na conta ou no aparelho.

## O que não fazer

- **Widget milagroso.** Barra de acessibilidade, avatar ou "correção automática" não torna um site acessível. A FTC obrigou a accessiBe a pagar US$ 1 milhão por prometer conformidade automática sem provas.
- **Declarar sem testar.** Público listado não é público atendido. No relatório, diga o que foi testado com pessoas. Se foi nada, escreva isso.
