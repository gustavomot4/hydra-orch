### 5.5 Grade

```css
.grid { display: grid; grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr));
        column-gap: 40px; row-gap: 82px; }
@media (max-width: 1068px) { .grid { column-gap: 24px; } }
@media (max-width: 734px)  { .grid { grid-template-columns: minmax(0, 1fr); } }   /* coluna única */
```

Colunas: **2** para bloco de mídia + texto, **3** para bloco só de texto curto
(pergunta, característica). Em ≤734px, sempre 1.

O gap de **linha** é muito maior que o de **coluna**. É isso que faz blocos
irmãos lerem como blocos, e não como uma malha.

### 5.6 Alinhamento: à esquerda por padrão

Contagem do autor numa página de produto do apple.com: de 164 blocos de texto,
**102 à esquerda** e 61 centralizados (as duas parcelas somam 163; a contagem
original não diz onde ficou o bloco restante). O próprio herói do MacBook Air é
**à esquerda**.

**Regra:** centralize apenas quando o bloco é **dono sozinho da faixa
horizontal** — abertura de capítulo, com título e no máximo uma linha de apoio.
Abertura centralizada não leva botão: herói com ação fica à esquerda. Dentro de
coluna, célula de grade, cartão, tabela ou formulário: **sempre à esquerda**.

O **texto** de formulário e o título de painel ficam à esquerda: centralizá-los é
copiar a impressão errada. A **coluna** de um formulário, de uma edição ou de um
detalhe, essa sim, fica centralizada na área útil (`margin-inline: auto`), com
sobra igual dos dois lados. Alinhar à esquerda é regra do texto, não da posição
da coluna: o formulário de fluxo (560px) e o `.shell` já nascem centralizados.

### 5.7 Fundo cinza marca capítulo, não alterna

A troca de fundo (`--paper` ↔ `--sunken`) separa **capítulos**, não seções
consecutivas. Proporção medida pelo autor: ~1 bloco cinza para cada 3 brancos.

⚠️ Faixa de fundo tem que ser **full-bleed** (borda a borda, sem raio). Um bloco
cinza com margem lateral e canto arredondado flutuando no meio da página fica
pior do que a borda de 1px que você estava tentando remover.

### 5.8 Espaçamento: uma escala fechada

Distância entre elementos sai desta lista, e só dela:

```
4 · 8 · 12 · 16 · 20 · 24 · 32 · 40
```

| Entre | Espaço |
| --- | --- |
| Título de item e sua segunda linha · campo e frase de erro | 4px |
| Título e linha de apoio · rótulo e campo · botões lado a lado · ícone ou avatar e texto | 8px |
| Campos empilhados · cabeçalho de cartão e conteúdo | 16px |
| Linha de apoio e ação | 32px |
| Ação e mídia · um bloco de conteúdo e o seguinte | 40px (32px em ≤1068) |
| Cartões e colunas de ferramenta | `--gutter` (22px) |

12, 20 e 24 são paddings: 12px no lado de campo, botão e célula; 24 / 20 / 16
no cartão (5.4). Gutter (22px), gaps da grade (40 / 82) e ritmo de seção (5.4)
têm token próprio e ficam fora da escala. Medida interna de componente — o
inset de 2px do segmented, o padding de 10px do item de navegação — está na
especificação dele (seção 7) e não se reaproveita.
