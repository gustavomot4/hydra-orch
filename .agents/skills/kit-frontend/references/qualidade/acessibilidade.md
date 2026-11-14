# Acessibilidade: o piso

Piso do kit: **WCAG 2.2 AA** e **ABNT NBR 17225:2025**. O art. 63 da Lei 13.146/2015 trata da acessibilidade e do símbolo em sites de empresas com sede ou representação no Brasil e de órgãos de governo.

Em caso de conflito com o pedido, gosto ou estilo, proponha uma solução que respeite o piso.

Relate o que foi verificado e como. A avaliação inclui ferramentas automáticas, teclado, leitor de tela e testes com pessoas.

## Para quem, e o que muda para cada um

Preencha `publicos:` no `PRODUTO.md` e siga `references/qualidade/publicos.md`.

| Quem | O que precisa | Regra |
| --- | --- | --- |
| Pessoa cega | Estrutura e nomes | Semântica nativa, títulos em ordem, nome em todo controle, avisos anunciados |
| Baixa visão, pessoa idosa | Texto que cresce sem quebrar | Fonte em `rem`, zoom de 200% e 400%, contraste, nada de texto em imagem |
| Daltonismo | Sinal além da cor | Texto, forma ou ícone em todo estado |
| Mobilidade reduzida, tremor | Alvo grande e teclado | 44 × 44 no toque, tudo pelo teclado, sem exigir arrasto |
| Baixo letramento, pouca familiaridade | Clareza | Frases curtas, uma decisão por tela, ícone sempre com texto, padrões conhecidos |
| Pessoa surda | Equivalente visual e língua própria | Legenda em vídeo, nada só em áudio, português simples, Libras em site público (`references/padroes/midia-e-libras.md`) |
| Sensível a movimento | Controle | `prefers-reduced-motion`, nada piscando, pausa em todo carrossel |
| Situação temporária | Contraste e tamanho | Sol na tela, uma mão só, conexão ruim |

## Regras com número

| Tema | Regra | Critério |
| --- | --- | --- |
| Contraste de texto | 4,5:1; texto de 24px ou mais, ou 18,66px em negrito, 3:1 | 1.4.3 |
| Contraste de interface | 3:1 para borda de campo, ícone que informa, foco e gráfico | 1.4.11 |
| Cor | Nada informa só pela cor | 1.4.1 |
| Mídia | Legenda em vídeo com fala; pausa em todo movimento que dura mais de 5s | 1.2.2, 2.2.2 |
| Nome de controle | `aria-label` contém o texto visível | 2.5.3 |
| Alvo | Mínimo de 24 × 24px. Padrão do kit: 44 × 44px no toque | 2.5.8 |
| Fonte | Em `rem`. Corpo de pelo menos 16px em tela de uso geral; nada abaixo de 12px | 1.4.4 |
| Largura | Sem rolagem horizontal em 320px de largura (1280px com zoom de 400%) | 1.4.10 |
| Espaçamento de texto | Nada cortado com altura de linha 1,5 e espaçamento entre letras 0,12em | 1.4.12 |
| Foco | Sempre visível, 3:1, nunca coberto por barra fixa | 2.4.7, 2.4.11 |
| Teclado | Tudo acessível, sem armadilha, ordem lógica | 2.1.1, 2.1.2, 2.4.3 |
| Arrasto | Toda ação de arrastar tem alternativa sem arrasto | 2.5.7 |
| Erros | Identificados em texto, com sugestão de correção | 3.3.1, 3.3.3 |
| Entrada repetida | Não peça de novo o que já foi informado | 3.3.7 |
| Login | Sem teste cognitivo; permita colar senha e usar gerenciador | 3.3.8 |
| Ajuda | No mesmo lugar em todas as telas | 3.2.6 |
| Tempo | Aviso com ação não some enquanto tiver foco ou ponteiro; a ação também existe em outro lugar | 2.2.1 |

## O que agentes costumam errar

- **Barra fixa em zoom alto.** Em janela baixa, cabeçalho, abas e aviso de cookies cobrem a tela. Regra do kit: com altura até 480px, tudo o que é fixo passa a rolar junto.

```css
@media (max-height: 480px) {
  .barra-superior, .barra-inferior, .barra-de-acoes, .aviso-de-cookies { position: static; }
}
```

- **Logo em SVG com cor fixa.** Em alto contraste, o fundo vira preto e o logo escuro some (`a11y-logo-alto-contraste`). Dê a versão para fundo escuro:

```html
<picture><source media="(forced-colors: active)" srcset="logo-negativo.svg"><img src="logo-positivo.svg" alt="Nome"></picture>
```

- **`min-width: 320px` no `body`.** Com barra de rolagem clássica no Windows, cria rolagem horizontal. Não declare.
- **`outline: none`** sem substituto de 3:1. O halo claro em volta do campo não basta como único sinal.
- **Anel de foco de uma cor só.** A cor de marca que passa sobre o fundo claro pode reprovar sobre a barra escura. Meça contra cada fundo e troque a cor do anel nas áreas escuras.
- **`maximum-scale=1`** na meta viewport. Nunca.
- **Placeholder como rótulo.** Some ao digitar. Rótulo visível sempre acima do campo.
- **`<div>` clicável.** Use `<button>` e `<a>`.
- **Combobox, abas e menu feitos à mão com ARIA errado.** Prefira o nativo ou uma base testada (React Aria, Radix). Se fizer à mão, siga o WAI-ARIA Authoring Practices.
- **Texto truncado sem saída.** `title` não chega a quem usa toque ou teclado. O conteúdo completo precisa existir em outro lugar.
- **`aria-label` que não contém o texto visível.** Quem usa controle por voz fala o que vê (2.5.3).
- **Mudança sem anúncio.** Resultado de busca e confirmação usam `role="status"`; erro urgente usa `role="alert"`.
- **Rota de SPA sem foco.** A cada troca de tela, atualize `document.title` e mova o foco para o `h1`.
- **Título com letras apertadas.** De −0,05em para baixo as palavras se colam (`a11y-letra-apertada`); com `dislexia` ou `pouca-leitura`, o limite é −0,03em e vira falha. É decisão do kit, a partir de um teste real, não critério da WCAG.
- **Foto com `height` no HTML e sem `height:auto` no CSS.** O `aspect-ratio` é ignorado e a foto fica na altura original (`q-foto-cortada`). Na primeira dobra, ninguém vê.
- **Página pesada.** Quem usa dados móveis paga por foto em PNG. O verificador avisa acima de 2 MB e reprova acima de 5 MB no celular (`q-pagina-pesada`). Os limites são decisão do kit.

## Roteiro de verificação

Rode `scripts/verificar.mjs` em cada tela. Depois faça à mão e relate cada item como feito ou não feito:

1. **Só teclado:** percorra a tela com Tab, Shift+Tab, Enter, Espaço, Esc e setas. O foco aparece sempre? Abre e fecha diálogo devolvendo o foco?
2. **Zoom:** 200% e 400%. Nada some, nada rola para o lado, barra fixa não cobre.
3. **Letra grande:** aumente a fonte padrão do navegador para 200%. O texto precisa crescer.
4. **Leitor de tela:** comece lendo `leitor-de-tela.txt`. Depois, NVDA no Windows, VoiceOver no Mac ou iPhone, TalkBack no Android. Percorra por títulos, preencha um formulário com erro, abra um diálogo. Se não puder rodar, escreva "leitor de tela não verificado".
5. **Sem cor:** abra `prancha.html`. Toda situação continua distinguível sem verde, sem vermelho, sem azul e em cinza?
6. **Alto contraste:** veja `alto-contraste.png`. O verificador acusa campo sem contorno; o resto é com o olho. Borda feita com `box-shadow` some.
7. **Movimento reduzido:** ative no sistema. Nada se move sozinho.
8. **Linguagem:** leia em voz alta. Alguém sem familiaridade entende na primeira leitura?
9. **Página inteira:** abra `desktop-inteira.jpg` e `celular-inteira.jpg` e olhe até o fim. Catálogo e rodapé não aparecem na primeira dobra.

### Prova de interação

Nos controles usados na jornada, registre a tecla, o foco ou estado antes e depois e a evidência da mudança.

- **Diálogo modal:** abra pelo teclado, confira o foco inicial, use Tab e Shift+Tab até as bordas e feche com Esc. Confira o foco de volta no acionador ou no próximo controle previsto no fluxo.
- **Acordeão:** use Enter e Espaço. Compare `aria-expanded` com a visibilidade do painel associado e confira se seu conteúdo entra e sai da ordem de Tab conforme o estado.
- **SPA:** faça a navegação real, inclusive por botão. Confira o título, o foco no novo conteúdo e a indicação de mudança.
- **Formulário:** provoque um erro com dados fictícios. Confira o foco, o vínculo do campo à mensagem e, com leitor de tela, o que foi anunciado.

Para o piloto semântico, passe `--axe <caminho-local-do-axe.min.js>` ao verificador. O `axe.json` registra violações, itens inconclusivos e falhas do motor. Confira os inconclusivos à mão. O piloto roda regras ARIA no documento principal em desktop.

## Linguagem simples

Frase curta, voz ativa e palavra do dia a dia. Botão com verbo e objeto ("Marcar horário"), e a ação mantém o nome em todo o fluxo: "Publicar" gera o aviso "Publicado". Evite sigla sem explicação. Nunca mostre código de erro. Diga o que aconteceu e o que fazer. Para público com letramento variado, use ícone e texto juntos, e teste com alguém do público.

Roteiro para reescrever, a partir do art. 5º da Lei 15.263/2025 (que vale para o poder público, mas serve a todos): ordem direta, uma ideia por parágrafo, palavra comum no lugar de jargão, sigla só depois do nome completo, listas e tabelas quando couber, o principal primeiro, voz ativa, sem oração intercalada, e teste da mensagem com o público.

O verificador acusa parágrafo difícil por um índice adaptado ao português (`a11y-leitura-dificil`). Abaixo de 10 é texto jurídico; com `pouca-leitura`, o limite sobe para 50. Em 13 textos de teste, os fáceis deram de 66 a 89 e os jurídicos, de −86 a −4. É alerta, nunca aprovação: texto curto e confuso passa. O índice não vale para botão nem rótulo.
