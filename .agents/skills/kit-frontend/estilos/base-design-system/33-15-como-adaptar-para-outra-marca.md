## 15. Como adaptar para outra marca

1. Escolha o *hue* do acento pela marca. Se a marca é vermelha, tire o acento da
   faixa vermelha, senão ele e `--danger` voltam a ser a mesma cor (4.3).
2. Escureça até `--accent` bater o requisito de 4.2: ≥ 4,5:1 sobre `--fill`
   aplicado em `--sunken`, o que pede cerca de 5,8:1 com branco. Com isso o mesmo
   hex serve de fundo de botão **e** de link, e você não precisa de um segundo
   tom.
3. Derive `--accent-hover` (mais claro, ainda dentro do requisito) e
   `--accent-active` (mais escuro). `--danger` segue o mesmo requisito.
4. Escolha a **temperatura** dos neutros, quente ou fria, e refaça
   `--paper`, `--surface`, `--sunken`, `--fill`, `--line`, `--ink`, `--ink-2` e
   `--ink-3` nela. Não misture. Metas: `--ink` ≥ 12:1; `--ink-2` ≥ 4,5:1 sobre
   `--sunken` e sobre `--fill` em `--paper`; `--ink-3` ≥ 3:1 sobre `--surface`,
   `--paper` e `--sunken`.
5. Confira `--surface` sobre `--paper`. Abaixo de 1,08:1 a `--shadow-card` é
   obrigatória (4.4); se quiser dispensá-la, escureça o papel.
6. Se trocar a família da fonte, recalibre o tracking de 12 a 17px e de 48px ou
   mais (3.4) e confira os line-heights (3.3): a tabela vale para Inter com
   `opsz`. Rampa, raios, alvos, breakpoints e regras de composição são
   **estruturais** e valem para qualquer marca.
7. Atualize os valores nos três formatos da seção 12 (CSS, JSON, Tailwind) e
   **refaça a tabela 9.1** com os valores novos, par por par.
