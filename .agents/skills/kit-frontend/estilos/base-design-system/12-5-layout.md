## 5. Layout

### 5.1 Largura: 980px é o CONTEÚDO, não o contêiner

A medida famosa da Apple é o texto, não a caixa:

```css
*, *::before, *::after { box-sizing: border-box; }   /* sem isto a caixa vira 1068 e o conteúdo, 1024 */
.shell { max-width: 1024px; margin-inline: auto; padding-inline: 22px; }   /* 1024 − 44 = 980 */
```

⚠️ Declarar `max-width: 980px` com padding de 20px entrega **940px** de conteúdo
— 40px a menos, com o rótulo de que é a medida da Apple.

| Contexto | Largura |
| --- | --- |
| Conteúdo de vitrine | **980px** (contêiner 1024 + 22) |
| Parágrafo, em qualquer tipo de tela | no máximo **692px** |
| Formulário de fluxo | **560px** (`class="shell shell-fluxo"`) |
| Ferramenta | **fluida**, com gutter de 22px |

⚠️ **Não trave uma ferramenta em 980px.** Essa régua é largura de *leitura em
coluna única*. Num painel, tabela e grade de cartões ocupam a largura
disponível; só as **colunas de texto** ficam limitadas em 692px.

⚠️ **O conteúdo para de crescer em 980px.** O `.shell` mede 1024px (980 de
conteúdo) em qualquer janela de 1024px ou mais. Não deixe a linha de leitura esticar em monitor grande.

### 5.2 Breakpoints: uma régua só

```
≤734   |   735–1068   |   ≥1069
```

Use **estes** no produto inteiro. Misturar 720/767/768 com 734/1068 cria dois
sistemas de dobra e o bug aparece exatamente na faixa entre eles.

(A Apple tem ainda um corte em 1441px e um em 833px, este **exclusivo da altura
da barra de navegação**. Aqui nenhum dos dois muda nada, então não entram na
régua.)

Breakpoint mede largura, e só largura. Ele não diz se o ponteiro é dedo ou
mouse — para isso, ver 6.3.

### 5.3 Gutter no mobile é proporcional, não fixo

```css
@media (max-width: 734px) { .shell { width: 87.5%; max-width: none; padding-inline: 0; } }
```

A margem cresce de 20px num aparelho de 320 para 27px num de 430. Um gutter fixo
aperta o telefone grande. Em 735px a régua muda e a margem volta a 22px: o
conteúdo vai de 642px (em 734) para 691px (em 735), e esse salto é o corte entre
telefone e tablet, não um erro.

### 5.4 Ritmo vertical

O par é **assimétrico**: o rodapé da seção é maior que o topo.

| Contexto | ≥1069 | 735–1068 | ≤734 |
| --- | --- | --- | --- |
| Seção de vitrine (topo / rodapé) | 96px / 104px | 80px / 88px | 72px / 78px |
| Bloco de conteúdo | 40px | 32px | 32px |
| Padding de cartão | 24px | 20px | 16px |

⚠️ **Na medição do autor, a Apple usa 110–162px, e copiar isso quebra páginas
curtas.** Ela sustenta esse ar porque a página de produto tem 18 blocos e o
leitor rola 6.000px. Numa página de 5 seções, 110px faz o rodapé encostar na
dobra e a página lê como inacabada.

⚠️ **Nunca use ritmo de vitrine numa ferramenta.** Ali o padding de cartão (24px)
e o gutter (22px) são o ritmo: 22px entre cartões e entre colunas.
