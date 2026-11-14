### 3.4 Tracking é função do TAMANHO, não do papel

O espaçamento lateral desenhado na fonte é proporcional ao corpo. Em corpo
grande o branco entre letras cresce junto e passa a parecer frouxo — o aperto
precisa ser devolvido à mão.

| Tamanho | letter-spacing |
| --- | --- |
| 56px | `-0.005em` |
| 48px | `-0.003em` |
| 21 · 28 · 40px | `0` |
| 17px | `-0.011em` |
| 14px | `-0.008em` |
| 12px | `-0.005em` |

Esta tabela foi calibrada para **Inter com o eixo `opsz`**. Com outra família,
recalibre (seção 15).

⚠️ **Duas armadilhas, e as duas fazem estrago:**

1. **Não copie o tracking da Apple literalmente no corpo pequeno.** Ela usa
   `-0.022em` em 17px porque a SF Pro Text é um desenho com espaçamento lateral
   largo. Na avaliação do autor, a Inter já nasce mais apertada — o mesmo número
   fecha demais e come a legibilidade. De 12 a 17px a tabela usa **metade**.
2. **Não aplique tracking positivo no corpo médio.** A Apple usa `+0.004` a
   `+0.012em` entre 19 e 32px, mas isso é compensação por usar o corte *Display*
   em corpo pequeno. Com o eixo `opsz` a compensação é automática — copiar é
   **corrigir duas vezes** e o texto fica frouxo. **Zere em 21, 28 e 40px.**

### 3.5 Optical sizing

O mecanismo central da tipografia da Apple é trocar a fonte por tamanho: SF Pro
**Text** até 17px, SF Pro **Display** de 19px para cima. Na web isso sai de graça
com uma fonte de eixo `opsz`:

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,600&display=swap" rel="stylesheet">
```

Não há CSS a escrever: `font-optical-sizing: auto` já é o valor inicial. Só não
o desligue (`none`).

Com o eixo ligado, a Inter estreita sozinha conforme o corpo cresce, de 14px até
32px (os limites do eixo na URL acima) — o mesmo trabalho da troca
Text→Display.

⚠️ **O `opsz,` na URL não é decorativo.** `family=Inter:wght@...` e
`family=Inter:opsz,wght@...` servem **arquivos diferentes**. Esquecer o `opsz,`
desliga o recurso em silêncio, sem erro nenhum.

⚠️ Navegador antigo ignora `font-optical-sizing` e trava no corte Text. Os
títulos ficam levemente largos e nada mais quebra — **mas não apoie a hierarquia
no opsz**. Ela tem que se sustentar em peso e tamanho sozinha.

### 3.6 Pesos

**Só 400 e 600.** Nada de 500, 700, 800. (Observação do autor: não existe peso
700 na tipografia de marketing da apple.com.)

**Hierarquia se resolve por peso antes de tamanho.** Título e corpo compartilham
a **mesma cor**; o que os separa é 600 contra 400. Esse é o ganho real — cabe em
4 degraus e funciona em qualquer densidade.
