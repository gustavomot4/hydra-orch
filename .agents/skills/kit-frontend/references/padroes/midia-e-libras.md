# Mídia e Libras

Libras é uma língua, com gramática própria, e não substitui o português escrito (Lei 10.436/2002). Para muitos surdos, o texto é segunda língua, então a legenda nem sempre basta (W3C, critério 1.2.6). Uma coisa não dispensa a outra.

## Três níveis

| Nível | Onde vale | O que entregar |
| --- | --- | --- |
| 1. Base | Todo site público | VLibras, mais português simples em toda a tela |
| 2. Conteúdo que decide | Saúde, dinheiro, direitos, consentimento, primeiro uso | Vídeo com intérprete humano ao lado do texto, com legenda |
| 3. Vídeo do produto | Tutorial, institucional, campanha | Legenda, transcrição e janela de Libras |

O nível 3 é AAA na WCAG (1.2.6): decisão do produto, não piso. Quem deve validar a escolha são pessoas surdas.

## VLibras

Gratuito, do governo federal, com tradução automática do português por avatar. Serve para texto corrido. Não use como única forma de explicar uma decisão importante.

```html
<script src="https://vlibras.gov.br/app/vlibras-plugin.js" defer></script>
```

Com essa linha, o botão apareceu na borda direita em teste de 31/10/2026, no Chrome. Para trocar o lado ou o avatar, a documentação oficial cita `new window.VLibras.Widget({ position: 'L', avatar: 'guga' })`. Em teste de 01/11/2026, `position: 'L'` levou o botão para a esquerda, e `'BR'` e `'TR'` não o tiraram do lugar. O avatar não foi testado.

- **Desde as três direções.** O botão ocupa a borda da tela e faz parte do que o dono está escolhendo. Não deixe para depois.
- **Carregue sem esperar interação.** Quem precisa de Libras precisa ver o botão ao chegar. Use `defer` ou tempo ocioso, nunca "depois do primeiro clique".
- **Janela baixa.** Com altura até 480px, confira se o botão não cobre conteúdo nem foco.
- **Celular.** O botão mede 40 × 40px, a 10px da borda direita e no meio da altura (medido em 375 × 812, em 01/11/2026), e o texto passa por baixo ao rolar (`q-camada-sobre-texto`). No texto corrido, reserve a margem: `padding-right: 52px` abaixo de 768px. Balão, cartão e botão podem passar por baixo, porque rolar resolve: diga isso no relatório.
- **Depende de terceiros.** O script baixa arquivos de `vlibras.gov.br` e de `cdn.jsdelivr.net`, e o serviço pode sair do ar. Cite na política de privacidade. O restante da tela não pode depender dele.
- **Não basta.** Não é atestado de acessibilidade. Há também opção comercial (Hand Talk), que não foi avaliada.

## Vídeo e áudio

| Regra | Como | Critério |
| --- | --- | --- |
| Legenda em todo vídeo com fala | `<track kind="captions" srclang="pt-BR">`, com quem fala e os sons que importam | 1.2.2 |
| Sem autoplay com som | Vídeo começa pela pessoa. Fundo decorativo é mudo, sem informação | 1.4.2 |
| Pausa em todo movimento | Controles nativos, ou botão "Pausar" visível; movimento reduzido para o vídeo decorativo | 2.2.2 |
| Áudio tem transcrição | Link visível logo abaixo do player, em texto da página | 1.2.1 |
| O que só se vê é descrito | Narre o que aparece, ou ofereça audiodescrição | 1.2.3, 1.2.5 |
| Janela de Libras | Gravada no vídeo, ou segundo vídeo ao lado, sem cobrir legenda nem ação | 1.2.6 |
| Tamanho reservado | `width` e `height` no `<video>`, para a tela não pular | Desempenho |

Aviso sonoro nunca é o único sinal: repita em texto e, no celular, com vibração quando houver.

## Na lei

O art. 63 da Lei 13.146/2015 obriga a acessibilidade em sites de empresas com sede ou representação comercial no país e de órgãos de governo, e pede símbolo de acessibilidade em destaque. O que isso exige de cada caso é questão jurídica.

`scripts/verificar.mjs` acusa vídeo sem legenda (`a11y-video-legenda`), vídeo sem pausa (`a11y-video-sem-controle`), áudio sem transcrição (`a11y-audio-transcricao`) e superfície pública sem Libras (`a11y-libras`: aviso, e falha quando `publicos:` traz `surdos-libras`). Ele só vê se o recurso está na página: não julga a qualidade da tradução.

**De onde veio:** Lei 10.436/2002, Lei 13.146/2015, W3C (1.2.6) e documentação do VLibras, lidos na fonte. Os demais critérios de mídia vêm de conhecimento geral da WCAG 2.2. Registro em `docs/pesquisa/benchmark.md`, no repositório do kit.
