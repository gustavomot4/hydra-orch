## 13. Checklist de aceite

Todos os itens são **verificáveis**, não opinião. Onde o script de auditoria
(abaixo) confere o item, o nome do campo vem entre parênteses.

**Composição** (viewports 1440×900 e 390×844, seção 2)
- [ ] Teste dos 5 segundos passa: dá para dizer o que a tela informa e qual é a ação.
- [ ] Exatamente 1 informação herói.
- [ ] Exatamente 1 ação primária visível, ou zero, declarado, em tela de leitura (`acentoFundo`).
- [ ] No máximo 5 blocos de informação sem rolar.
- [ ] Nenhum dado aparece duas vezes na mesma tela, salvo as duas exceções da seção 1.
- [ ] Todo texto auxiliar cabe em 1 linha e tem até 60 caracteres.

**Tipografia**
- [ ] No máximo 2 famílias no produto; a segunda só nos títulos da vitrine (`familias`).
- [ ] No máximo 4 tamanhos nesta tela, todos de `12·14·17·21·28·40·48·56`; 40, 48 e 56 contam como um (`tamanhos`).
- [ ] Só pesos 400 e 600 (`pesos`).
- [ ] Zero `text-transform: uppercase` (`caixaAlta`).
- [ ] Line-height e tracking declarados em cada classe de texto, com os valores de 3.3 e 3.4, nunca só no `body`.
- [ ] `tabular-nums` em toda coluna numérica.
- [ ] A URL da fonte tem `opsz,` (3.5).

**Cor**
- [ ] Um acento: no máximo 1 preenchimento e 3 textos em `--accent` por viewport (`acentoFundo`, `acentoTexto`).
- [ ] `--danger` só em erro de campo, estado crítico e ação destrutiva, sempre com texto por extenso.
- [ ] Todo par de texto e fundo está na tabela 9.1, nenhum par proibido aparece e nenhum texto tem `opacity` (`textoComOpacity`).
- [ ] Nenhuma informação só por cor: cada caso tem o segundo sinal da tabela 9.1.
- [ ] Anel de foco visível, com contraste de pelo menos 3:1 contra o fundo em que aparece.

**Geometria e layout**
- [ ] Raios só da escada `6·8·12·18·28·50%·980`, cada componente no seu (6.1) (`raiosFora`).
- [ ] Sombras só `--shadow-card`, `--shadow-control` e `--shadow-modal`, cada uma no seu papel (`sombrasFora`).
- [ ] Espaçamento só da escala `4·8·12·16·20·24·32·40` (5.8).
- [ ] Vitrine: contêiner com 980px de conteúdo e parágrafos de até 692px. Fluxo: coluna de 560px. Ferramenta: fluida (`conteudo`).
- [ ] Breakpoints 734 e 1068, e só eles.
- [ ] Nada rola na horizontal em 320px nem em 768px, e nada fixo cobre a janela de 320 × 256 (5.9).
- [ ] Texto alinhado à esquerda, exceto abertura de capítulo; coluna de largura limitada (fluxo, formulário, detalhe) centralizada na área útil, com sobra igual dos dois lados.
- [ ] Alvo de 44px em `pointer: coarse` e de 28px com ponteiro fino.
- [ ] Nenhuma ação depende de `hover`.

**Estados e acessibilidade**
- [ ] Vazio, carregando, erro e "tudo feito" existem e foram vistos.
- [ ] Todo componente interativo tem padrão, hover, foco, pressionado, desabilitado e, nos que recebem dado, erro.
- [ ] Botão desabilitado diz o que falta e usa `aria-disabled`.
- [ ] Confirmação destrutiva mostra o número real do impacto.
- [ ] Passada de `Tab` em todos os controles: o anel aparece, não é cortado e não fica atrás de barra fixa.
- [ ] Estrutura de 9.2: `lang`, link de pular, um `<main>`, um `<h1>`, `<nav>` com nome (`estrutura`).
- [ ] A 200% de zoom e a 320px de largura nada é cortado e nada rola na horizontal.
- [ ] `prefers-reduced-motion: reduce` zera as animações.
