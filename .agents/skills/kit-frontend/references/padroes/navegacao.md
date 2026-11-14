# Navegação e casca

**Quando:** a estrutura fixa do produto, em todas as telas.

## Regra por largura

Faixas baseadas nas classes de janela do Android, que qualquer plataforma pode usar:

| Largura | Navegação | Conteúdo |
| --- | --- | --- |
| Até 599px | Barra de abas embaixo, 3 a 5 itens, sempre com ícone e texto. O resto em "Mais" | 1 coluna |
| 600 a 839px | Abas embaixo ou trilho lateral | 1 coluna, ou 2 quando há lista e detalhe |
| 840 a 1199px | Trilho ou barra superior | 2 colunas |
| 1200px ou mais | Barra lateral ou superior | Até 3 áreas; a tela é usada de verdade (G07) |

Em altura de até 480px (celular deitado, zoom alto), tudo o que é fixo passa a rolar junto.

## Regra

- **O menu mostra só o que o perfil pode abrir**, sempre na mesma ordem.
- **Item atual:** fundo, peso e `aria-current="page"`, não só cor.
- **Ação principal:** no topo à direita no computador; no celular, botão flutuante com rótulo ou barra fixa no rodapé. Nunca as duas barras inferiores ao mesmo tempo.
- **Voltar:** tela interna tem voltar visível. O botão do navegador sempre funciona; filtros e aba ficam na URL.
- **Marca:** leva ao início. Sem quadradinho de iniciais. (G17)
- **Busca:** quando importante, campo visível num lugar com sentido. Evite a lupa solta. (G18)
- **Pular para o conteúdo** é o primeiro item no Tab. No celular, o conteúdo vem antes da barra de abas na ordem de leitura.
- **Coluna de detalhe** ao lado da lista acompanha a rolagem. Só o corpo dela rola, e a ação principal fica sempre à vista. (G09)
- **Hover** só dentro de `@media (hover: hover) and (pointer: fine)`. Alvo se decide por `pointer`, não por largura.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| Android, classes de janela | Faixas em 600, 840, 1200 e 1600dp; altura compacta abaixo de 480dp desaconselha dois painéis |
| Apple | Controles com 44pt no toque e 28pt com mouse; ampliação de texto de pelo menos 200% |
| Linear | Navegação recua para o conteúdo aparecer: barra lateral com contraste baixo, ícones menores |
| WhatsApp, Instagram | Abas embaixo, poucos destinos, ícone e rótulo (observação) |

## Erros comuns

Menu de hambúrguer no computador; layout de celular centralizado num monitor; barra lateral fixa em 320px; dois menus para a mesma coisa; ícone sem texto em público leigo; rota nova sem foco no título.

**Verifique:** `g-pouco-uso-da-tela`, `a11y-camadas-fixas`, `a11y-pular`, `g-logo-em-quadrado`.
