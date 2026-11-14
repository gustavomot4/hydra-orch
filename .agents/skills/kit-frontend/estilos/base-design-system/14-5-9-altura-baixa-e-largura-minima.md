### 5.9 Altura baixa e largura mínima

**Com a janela de até 480px de altura, tudo o que é fixo rola junto.** O zoom de
400% num monitor de 1280 × 1024 dá uma janela de 320 × 256, e uma barra de 48px
ali já cobre quase um quinto do que a pessoa vê; com a barra do fluxo, a metade.
Nessa altura a barra translúcida e a barra de topo da ferramenta deixam de ser
`sticky`, `scroll-padding-top` volta a 0 e a barra inferior do fluxo vira o fim
da página. Modal e gaveta, que a pessoa abre e fecha, continuam fixos.

```css
@media (max-height: 480px) {
  .bar, .barra-mobile { position: static; }
  html { scroll-padding-top: 0; }
}
```

**Nenhuma largura de 320px a 1440px rola a página na horizontal.** Barra de
navegação, ações do topo e grupos de controles quebram linha em vez de sair da
tela (`flex-wrap: wrap`); campo tem `max-width: 100%`. Em tabela, o que não cabe
é cortado por coluna (ver Tabela, na seção 7), nunca por rolagem.

---
