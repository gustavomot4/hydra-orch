## 1. O princípio

> **Subtração antes de decoração.**

Cada elemento na tela precisa responder a uma pergunta:

**"Que decisão do usuário este dado muda?"**

Se a resposta for *"nenhuma"*, ele **sai**. Não é reduzido, não é movido para o
rodapé, não vira um ícone menor: sai.

Não valem como resposta: "dá contexto", "mostra profissionalismo", "transmite
confiança", "preenche o espaço", "o concorrente tem". Uma decisão real é do tipo
*"cancelar este pedido"*, *"ligar para o cliente das 15h"*, *"subir o preço"*,
*"escolher o plano anual"*, *"ir até lá hoje"*.

**Espaço vazio é resultado aceito, não problema a resolver.** Com uma condição:
o vazio não pode deixar a tela torta. Coluna de largura limitada fica centralizada
na área útil (5.6), com sobra igual dos dois lados; nada termina à esquerda com
um vazio grande à direita.

Duas consequências que as pessoas resistem:

- **Dado duplicado é dado a menos, não a mais.** Se o mesmo número aparece num
  card, num gráfico e numa tabela da mesma tela, dois deles saem. Duas exceções:
  o item herói pode repetir na lista de onde ele vem, e o painel de detalhe
  repete os campos da linha selecionada.
- **Texto que ensina o óbvio é ruído.** Numa ferramenta usada todo dia, "clique
  para editar" é insulto na décima abertura. Texto explicativo só onde a
  interface não se explica sozinha, e no máximo **uma linha**.

### Como auditar uma tela existente

1. Liste **todos** os elementos visuais (card, KPI, gráfico, coluna, botão,
   chip, parágrafo, selo, ornamento). Conte.
2. Para cada um, escreva a decisão concreta que ele muda — ou escreva
   literalmente "nenhuma".
3. Corte tudo que ficou com "nenhuma".
4. Conte de novo. **A redução tem que ser real**: reagrupar os mesmos elementos
   com outro nome, ou empurrá-los para um modal, não é subtração — é maquiagem.
5. Separe **controle** (o usuário age nele) de **display** (o usuário só lê).
   Cortar display é subtração; cortar controle é **perda funcional** e precisa
   de aprovação humana explícita.

---
