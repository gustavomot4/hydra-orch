## 6. Geometria: raios, sombra, alvos

### 6.1 Escada de raios

Uma lista fechada. Não existe 3px, 4px, 10px, 16px nem 20px:

```
6px · 8px · 12px · 18px · 28px · 50% · 980px
```

| Uso | Raio |
| --- | --- |
| Botão de vitrine e de fluxo, chip, trilho do interruptor | `980px` (pílula) |
| Mídia | `28px` |
| Cartão de ferramenta, superfície desenhada dentro de mídia | `18px` |
| Cartão de fluxo, modal, contêiner de lista agrupada | `12px` |
| Campo, botão de ferramenta, trilho do segmented, toast | `8px` |
| Item de navegação lateral, pílula do segmented, cabeçalho de tabela, bloco de carregamento | `6px` |
| Avatar, botão do interruptor | `50%` |

Raio de dentro = raio de fora menos a distância entre as bordas: trilho de 8px
com inset de 2px dá pílula de 6px.

⚠️ **Arredondar pela metade é pior que não arredondar.** Raio 0 em tudo é uma
postura coerente. Mas se arredondar o cartão e esquecer o interruptor, a pílula
da navegação e o *segmented*, o resultado lê como bug, não como estilo. **É tudo
ou nada.**

### 6.2 Sombra: três papéis, nenhuma outra

Na leitura do autor, a folha de produção inteira de uma página de produto da
Apple (1,3 MB) contém **uma única sombra de elevação**. Todo o resto é anel de
foco ou `none`.

**Separe superfícies por tom e por espaço.** Quase nunca por sombra, e
praticamente nunca por borda de 1px.

Aqui existem três sombras, uma por papel:

| Token | Valor | Papel |
| --- | --- | --- |
| `--shadow-card` | `2px 4px 12px 0 rgba(0, 0, 0, 0.08)` | cartão `--surface` sobre a página (obrigatória com os tokens padrão — ver 4.4) |
| `--shadow-control` | `0 1px 2px 0 rgba(0, 0, 0, 0.18)` | peça móvel de controle: pílula do segmented, botão do interruptor |
| `--shadow-modal` | `0 16px 48px 0 rgba(0, 0, 0, 0.18)` | camada flutuante: modal e menu |

Nenhum outro `box-shadow` de elevação existe. A borda de campo é `inset` e não
é elevação; o anel de foco é `outline`.

### 6.3 Alvos

| Ponteiro | Mínimo |
| --- | --- |
| Fino (`pointer: fine` — mouse, trackpad) | 28px |
| Grosso (`pointer: coarse` — dedo) | **44px**, em qualquer largura de tela |

⚠️ **Largura de tela não diz qual é o ponteiro.** Um tablet de 1024px é toque;
uma janela de 600px no desktop é mouse. Alvo e hover se decidem por `pointer` e
`hover`, nunca por breakpoint.

⚠️ **Não engorde o botão para chegar aos 44px.** A Apple mantém o botão em ~35px
de caixa e estica a **área de clique** com margem invisível:

```css
:root { --alvo: 28px; }
@media (pointer: coarse) { :root { --alvo: 44px; } }

.btn, .chave, .terciario { position: relative; }
.btn::after, .chave::after, .terciario::after {          /* alvo, não caixa */
  content: ''; position: absolute; top: 50%; left: 50%;
  width: max(100%, var(--alvo)); height: max(100%, var(--alvo));
  transform: translate(-50%, -50%);
}
```

Copiar só o padding cria regressão de acessibilidade; copiar 44px de caixa
destrói a densidade da ferramenta. Faça as duas coisas separadamente.

Campo, segmented, item de navegação e linha de tabela não usam o truque: neles
a própria caixa cresce no toque (`--h-controle` 32 → 44px, `--h-linha`
36 → 44px). Link dentro de frase é isento, pela exceção de texto corrido da
WCAG 2.5.8.

⚠️ **Hover não existe no toque.** Nenhuma ação pode depender dele: um botão
revelado em hover apaga o alvo *e* o dado no aparelho onde a pessoa mais usa o
produto. Alvos são persistentes. Todo estilo de hover vai dentro de
`@media (hover: hover) and (pointer: fine)`, para não ficar grudado depois do
toque.
