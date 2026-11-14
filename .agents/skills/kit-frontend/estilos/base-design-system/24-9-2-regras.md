### 9.2 Regras

- **Contraste:** texto ≥ 4,5:1 · texto grande e elemento de interface ≥ 3:1.
  Texto grande, nesta rampa, é 28px ou mais.
- **Anel de foco ≥ 3:1** contra todo fundo em que aparece. Acento com alfa
  **reprova** — ver 6.4.
- **Foco nunca encoberto:** `scroll-padding-top` igual à altura da barra fixa;
  com a barra inferior do fluxo, `scroll-padding-bottom` igual à altura dela.
- **Nunca codifique informação só por cor.** Sempre cor + (texto | peso |
  posição | forma).
- **Todo controle tem nome acessível.** Com rótulo visível: `<label for>` ou
  `aria-labelledby`. Sem rótulo visível: `aria-label`. A palavra ao lado do
  interruptor costuma ser o único nome que o leitor de tela tem — ligue-a ao
  controle.
- **Teclado:** tudo que o mouse faz, o teclado faz. A linha "Semântica e
  teclado" de cada componente da seção 7 é parte do aceite.
- **Alvo:** 44px em `pointer: coarse`, 28px com ponteiro fino (6.3).
- **Estrutura:** `<html lang="…">`; o primeiro elemento focável é o link "Pular
  para o conteúdo", visível no foco, apontando para o `<main>`; um `<main>`, um
  `<h1>`, títulos sem pular nível; cada `<nav>` com `aria-label`.
- **Zoom e reflow:** a 200% de zoom e a 320px de largura nada é cortado e nada
  rola na horizontal. Por isso as alturas são `min-height`, as fontes estão em
  `rem` e a tabela vira cartões em ≤734px.
- **Espaçamento de texto:** com line-height 1,5, espaço entre parágrafos de 2em,
  letter-spacing 0,12em e word-spacing 0,16em, nada é cortado nem se sobrepõe.
- **`forced-colors`:** borda feita com `box-shadow` some nesse modo. O campo
  ganha `outline: 1px solid CanvasText` dentro de
  `@media (forced-colors: active)`.
- **Ordem de leitura = ordem visual.** Não use `order` do flex/grid para
  reorganizar conteúdo que importa.
- **Movimento reduzido respeitado** (seção 8).

---
