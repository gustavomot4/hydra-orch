## 10. Três referências, não uma

O erro mais comum ao "seguir um padrão bonito" é aplicar a linguagem da **página
de marketing** dentro de uma **ferramenta**. São produtos diferentes — inclusive
dentro da própria Apple, que usa um sistema no apple.com e outro na Apple Store
e nos apps do macOS.

| Tipo | Referência | Corpo | Botão primário | Superfície | Ritmo |
| --- | --- | --- | --- | --- | --- |
| **Vitrine** (landing, página de produto) | página de produto | 17px | pílula de 44px | sem cartão; faixa de capítulo em `--sunken` | seção de 96 / 104px |
| **Fluxo** (checkout, onboarding, cadastro) | fluxo de pagamento | 17px | pílula de 44px, fixa embaixo | cartão de fluxo (raio 12px), coluna de 560px | uma decisão por tela |
| **Ferramenta** (painel, console, admin) | app de desktop / loja | 14px | retângulo de 32px, raio 8px | página `--paper` + cartão `--surface` (raio 18px) | linha de 36px, gutter de 22px |

Se você usar corpo de 17px e pílula de 44px numa tabela densa, vai ter uma tela
bonita onde cabe metade dos dados.

**Na vitrine, o teste da seção 1 se traduz assim.** Entram: herói (título, uma
linha de apoio, a ação e uma mídia), até 6 blocos de recurso (mídia, título e
parágrafo), preço, perguntas, um fechamento que repete a ação do herói e o
rodapé legal (separador `--line`, texto de 14px em `--ink-2`, links de
navegação). Imagem do produto entra porque mostra o que se está comprando.
Depoimento só entra com nome, função e um resultado medido. Parede de
logotipos e contador de vaidade não entram.

**No fluxo, uma regra específica:** a ação primária vai numa **barra fixa
inferior**, que contém o botão primário e, acima dele, **uma linha de resumo**
do que já foi escolhido (item · preço), em 14px. Nada além disso. Botão de
avanço inline sai da tela enquanto a pessoa rola a lista de opções — e a barra
fixa é o espaço mais valioso do celular. Com a janela de até 480px de altura ela
deixa de ser fixa (5.9).

---
