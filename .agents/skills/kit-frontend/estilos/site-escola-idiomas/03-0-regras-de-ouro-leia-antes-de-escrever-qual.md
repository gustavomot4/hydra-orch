## 0. Regras de ouro (leia antes de escrever qualquer linha)

1. **Uma cor de marca só.** Todo o site vive em cor da marca + branco + cinza-texto. Nada de paleta multicolorida, nem nas ilustrações (sem bandeiras). A cor da marca aparece em: botões, títulos de seção, footer, faixa de CTA, rótulos ativos e ícones. O resto é branco, com os dois fundos alternados do §4 (`--brand-tint` e `--bg-gray`).
2. **Uma família tipográfica só.** Montserrat em quatro pesos (400/500/600/700). Zero fonte secundária. Isso elimina a maior parte das decisões e mantém a coesão.
3. **Toda seção termina em uma ação.** Nenhum bloco é puramente informativo: cada um fecha com o CTA indicado nas tabelas do §5.2 e do §5.3 ("Saiba mais", "Conheça!", "Fazer pré-matrícula" ou "Fazer teste de nível").
4. **Duas conversões primárias, sempre visíveis:** `Pré-matrícula` (botão sólido) e `Teste de nível` (ação secundária). A partir de 1200px as duas ficam na faixa 2 do header, que acompanha a rolagem; abaixo disso, numa barra fixa no pé da tela (§5.1). Todo o site empurra para essas duas.
5. **A busca por unidade é função de primeira classe.** Escola de idiomas é negócio local. "Encontre uma unidade" é navegação, não rodapé: fica na faixa 1 do header, na seção 5 da home e no passo 1 da pré-matrícula.
6. **Respiro generoso, com medida.** A partir de 768px, seções com 100px de padding em cima e 120px embaixo; abaixo disso, 60px em cima e embaixo. Nunca aperte.
7. **Mobile-first de verdade.** O CSS base é o do celular e toda media query é `min-width` (576, 768 e 1200px). No mobile o header tem hambúrguer, logo e atalho de unidades; o hero vira 1 coluna; a faixa de CTA empilha.
8. **Sem tema escuro.** Declare `color-scheme: light`.

---
