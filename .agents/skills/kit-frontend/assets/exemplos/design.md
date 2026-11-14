---
version: alpha
name: Casa Ferreira
description: O salão visto pelas cadeiras, não pelo relógio
colors:
  primary: "#b3261e"
  on-primary: "#ffffff"
  navy: "#14304f"
  on-navy: "#ffffff"
  background: "#f1f4f6"
  on-background: "#10213a"
  surface: "#ffffff"
  on-surface: "#10213a"
  muted: "#485a6e"
  line: "#cfd8e0"
  success: "#17603f"
  warning: "#7a3f00"
typography:
  display:
    fontFamily: Barlow Condensed
    fontSize: 3rem
    fontWeight: 700
    lineHeight: 1
  client:
    fontFamily: Barlow Condensed
    fontSize: 2.75rem
    fontWeight: 700
    lineHeight: 1.02
  heading:
    fontFamily: Barlow Condensed
    fontSize: 1.375rem
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: Barlow
    fontSize: 1.0625rem
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: Barlow
    fontSize: 0.9375rem
    fontWeight: 600
    lineHeight: 1.4
rounded:
  none: 0px
spacing:
  sm: 8px
  md: 16px
  lg: 20px
  xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.none}"
    height: 48px
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.navy}"
    rounded: "{rounded.none}"
    height: 44px
  topbar:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.on-navy}"
    height: 56px
  page-secondary-text:
    backgroundColor: "{colors.background}"
    textColor: "{colors.muted}"
  card-secondary-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
  chair-occupied-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
  chair-free-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.success}"
  status-unconfirmed:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warning}"
---

<!-- Exemplo preenchido de DESIGN.md, para um produto fictício. Tela de origem: docs/testes/2026-10-30-calibracao/direcoes/direcao-b.html, no repositório do kit.
     Não copie os valores. Copie o nível de decisão: cada escolha tem motivo e sairia errada em outro setor. -->

## Overview

**Conceito:** o salão visto pelas cadeiras, não pelo relógio. Um sistema de trabalho, mas com a cara da fachada de uma barbearia.

**Direção aprovada:** B, em 30/10/2026, comparada com uma lista tipo conversa e um cartaz.

**Elemento-assinatura:** a listra do poste de barbeiro na lateral do cartão marca a cadeira ocupada. Ela é informação, não enfeite: dá para saber quantas cadeiras estão livres de longe, sem ler.

**Voz:** a de quem trabalha no balcão. Botão: "Sentou na cadeira", "Terminou". Vazio: "Ninguém marcado para hoje na cadeira 2." Erro: "Não deu para salvar. Confira a conexão e tente de novo."

**Público:** dono e recepção, em pé, olhando de relance entre um atendimento e outro, no computador do balcão e no celular.

## Colors

Vermelho, marinho e branco são as cores do poste. Azulejo frio no fundo, para o vermelho se destacar.

- **`primary`:** ação principal e estado "Ocupada". Só um botão por tela usa o preenchimento.
- **`navy`:** barra superior e contorno de botão secundário.
- **`success` e `warning`:** "Confirmado" e "A confirmar", sempre com ícone e texto. "A confirmar" também leva sublinhado tracejado.
- **`muted`:** texto de apoio. Passa 4,5:1 sobre `background` e sobre `surface`.

## Typography

Barlow Condensed lembra letreiro pintado e faz o nome do cliente caber grande numa coluna estreita. Barlow, da mesma família, dá corpo legível em tamanho pequeno. Tamanhos em `rem`.

O nome de quem está na cadeira é o maior texto da tela, porque é o que a recepção procura.

## Layout

A unidade da tela é a cadeira. A partir de 1100px, uma coluna por cadeira, ocupando a largura inteira. Abaixo disso, uma coluna só, na ordem das cadeiras. Abaixo de 840px, a navegação desce para abas no rodapé. Com altura de até 480px, barras deixam de ser fixas.

## Elevation & Depth

Sem sombra. Camadas se separam por tom e por linha de 1px em `line`.

## Shapes

Cantos retos em tudo, como o azulejo e a placa. A única diagonal da tela é a listra, e é por isso que ela chama a atenção.

## Components

**Cartão de cadeira:** faixa lateral de 18px (listrada quando ocupada, lisa quando livre), número e barbeiro, estado escrito, nome do cliente, ação seguinte e, abaixo, a lista de quem vem depois.

**Foco:** anel de 3px com 2px de afastamento, em `primary` nas áreas claras e branco na barra `navy`, onde o vermelho daria 2,05:1.

## Do's and Don'ts

- Faça: escreva "Ocupada até 14:30". A listra nunca é o único sinal.
- Faça: nomeie a ação pelo que aconteceu no salão ("Sentou na cadeira"), não pelo estado do sistema.
- Não faça: logo em quadrado. A marca é o nome, em letreiro.
- Não faça: usar a listra como decoração em outro lugar. Se aparecer fora da cadeira, ela deixa de significar.
- Não faça: arredondar cantos para "suavizar".
