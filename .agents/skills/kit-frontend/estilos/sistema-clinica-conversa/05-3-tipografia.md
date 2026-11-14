## 3. Tipografia

Uma família só, a Figtree, servida pelo próprio projeto (pacote `@fontsource/figtree`, subconjunto latino, pesos 400, 500, 600, 700 e 800) ou pelo Google Fonts com `display=swap`. Números que se comparam em coluna (horários, valores, CPF, telefone, páginas) usam `font-variant-numeric: tabular-nums`.

| Papel | Tamanho | Peso | Altura de linha | Espaçamento | Onde |
| --- | --- | --- | --- | --- | --- |
| Destaque da entrada | `--text-hero` | `--weight-extrabold` | `--leading-tight` | `--tracking-hero` | Só a frase de boas-vindas da tela Entrar |
| Título da tela | `--text-display`; abaixo de 768 px, `--text-display-sm` | `--weight-extrabold` | `--leading-tight` | `--tracking-display` | O `h1` de cada tela |
| Número grande | `--text-display-sm` | `--weight-extrabold` | `--leading-tight` | `--tracking-display` | Valor de indicador, hora do cartão "Próximo", total no anel |
| Nome em destaque | `--text-title` | `--weight-extrabold` | `--leading-tight` | `--tracking-title` | Nome no detalhe da consulta e na ficha, título de diálogo, número da produção |
| Marca e dia | `--text-heading` | `--weight-extrabold` na marca, `--weight-bold` no dia | `--leading-tight` | `--tracking-title` na marca, 0 no dia | Nome do produto na barra, número do dia na faixa de dias |
| Título de bloco | `--text-section` | `--weight-extrabold` | `--leading-body` | 0 | `h2` de cartão, título de estado vazio |
| Leitura de linha | `--text-lead` | `--weight-bold` | `--leading-body` | 0 | Horário da lista, nome no cartão "Próximo", busca de pacientes, botão grande |
| Corpo | `--text-body` | `--weight-regular`; nome em lista `--weight-bold` | `--leading-body` | 0 | Texto corrido, valor de campo, nome do paciente na lista |
| Interface | `--text-ui` | `--weight-semibold`; rótulo de campo `--weight-bold` | `--leading-body` | 0 | Rótulo, chip, aba, item de menu, paginação |
| Secundário | `--text-small` | `--weight-regular` | `--leading-body` | 0 | Segunda linha de item, dica de campo, pílula de situação, erro de campo |
| Legenda | `--text-caption` | `--weight-semibold` | `--leading-body` | 0 | Duração, dia da semana, selo, legenda de gráfico |
| Rótulo em maiúsculas | `--text-caption`; `--text-small` no título do painel; `--text-micro` no rótulo "PRÓXIMO" e no cabeçalho de colunas | `--weight-extrabold`; `--weight-bold` no título do painel | `--leading-body` | `--tracking-caps` | Grupo "MANHÃ · 8", cabeçalho do mês, grupo de horários, título do painel, rótulo "PRÓXIMO", cabeçalho de colunas das listas |
| Miúdo | `--text-micro` | `--weight-bold` | `--leading-card` | 0 | Conteúdo do cartão da grade, horas do eixo, rótulo da barra de abas |

Regras:

- Todo tamanho de fonte é escrito em `rem` (1rem = 16 px), nunca em `px`: quem aumenta a letra no navegador precisa ser obedecido. Os valores em px desta tabela e do texto são o resultado com a letra no tamanho padrão.
- Nenhum texto que a pessoa precise ler fica abaixo de `--text-micro`; a exceção são as iniciais dos círculos (4.2), que repetem o nome escrito ao lado. No celular, valor de campo e texto corrido ficam em `--text-body`.
- Título de tela tem uma linha; quebra com `overflow-wrap: anywhere` se o nome for longo. Nome em lista e em cartão corta com reticências (`white-space: nowrap; overflow: hidden; text-overflow: ellipsis`), nunca quebra.
- Saudação da tela Hoje: "Bom dia" antes de 12 h, "Boa tarde" antes de 18 h, "Boa noite" depois, seguida do primeiro nome de quem entrou.
