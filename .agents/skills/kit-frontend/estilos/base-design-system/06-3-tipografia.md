## 3. Tipografia

### 3.1 Uma família (no máximo duas)

Uma família resolve 95% dos produtos. Uma segunda só se justifica quando existe
uma voz de marca a carregar, e nesse caso ela fica **restrita aos títulos de uma
única superfície** (a vitrine), nunca na ferramenta.

| Stack | O que usar |
| --- | --- |
| Web | **Inter** com o eixo `opsz` — ver 3.5 |
| iOS / macOS | SF Pro (sistema) |
| Android | Roboto / Roboto Flex |
| Desktop nativo | fonte do sistema |
| Documento / e-mail | fonte do sistema, sem webfont |

⚠️ **Não confie em stack de sistema na web.** `-apple-system` resolve para San
Francisco só em macOS/iOS; no Windows e no Android o navegador ignora a
palavra-chave e usa o próximo nome da stack (Segoe UI, Roboto) — três desenhos
com altura de x e ritmo diferentes. Toda a calibração abaixo fica presa a uma
fonte que a maioria dos visitantes não tem.

E o argumento definitivo: **a própria apple.com não usa `-apple-system`**. Ela
auto-hospeda a SF Pro — 63 arquivos `@font-face`, na contagem do autor. "Stack
de sistema" não é o padrão Apple; **servir uma webfont é**. Deixe a stack de
sistema como *fallback*, nunca como plano.

### 3.2 Rampa de tamanhos

Uma lista fechada. Nunca invente 15px, 16px, 18px, 24px.

```
12 · 14 · 17 · 21 · 28 · 40 · 48 · 56
```

**No máximo 4 tamanhos por tela.** Cada tipo de tela já tem os seus quatro, um
por papel:

| Papel | Vitrine | Fluxo | Ferramenta |
| --- | --- | --- | --- |
| Display (herói) | 56 / 600 | 28 / 600 | 28 / 600 |
| Título de seção (600) · apoio do herói (400) | 28 | 21 | 17 |
| Corpo (400) · título de bloco (600) | 17 | 17 | 14 |
| Legenda, rótulo, rodapé, cabeçalho de coluna | 14 | 14 | 12 |

40 e 48 existem para o display da vitrine encolher: `--t-display` vale 56 em
≥1069px, 48 em 735–1068px e 40 em ≤734px, e os três contam como um tamanho só.

Quer um quinto tamanho? Tire outro.

### 3.3 Line-height é fórmula, não tabela

```css
--lh-titulo: calc(1em + 4px);   /* todo título, nos 8 degraus */
--lh-corpo:  calc(1em + 8px);   /* parágrafo de leitura, em 17 e em 14 */
--lh-denso:  calc(1em + 6px);   /* 14 e 12 em tabela, lista, rótulo e legenda */
--lh-botao:  calc(1em + 3px);   /* rótulo de botão e de segmented */
```

Confere em toda a rampa, como título: 56→60 · 48→52 · 40→44 · 28→32 · 21→25 ·
17→21 · 14→18 · 12→16. Corpo: 17→25 · 14→22. Denso: 14→20 · 12→18. Botão:
17→20 · 14→17.

⚠️ **Declare o line-height em cada classe de texto, nunca só no `body`.**
`calc(1em + Npx)` é resolvido em px no elemento em que foi declarado e herdado
como comprimento: um `body` de 17px passa 25px para um `h1` de 56px, e todo
título quebra. As classes da seção 12 já declaram um por um.
