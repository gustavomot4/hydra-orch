### 5.3 Página de curso (`/cursos/{idioma}`) — template reutilizável

| # | Bloco | Fundo | CTA de fechamento |
|---|---|---|---|
| 1 | **Hero interno**: ilustração do idioma em tons de `--brand-deep` e `--brand-dark`, sem bandeiras, com o scrim do hero (§5.2); `<h1>` "Curso de Inglês", subtítulo motivacional, 1 parágrafo | ilustração + scrim | par de pílulas: `--ghost` "Fazer teste de nível" + `--on-brand` "Fazer pré-matrícula" |
| 2 | **"{Idioma} para todas as fases da vida"** — 3 blocos por faixa etária (`.grid-cards`), cada um com **badge de idade** (`4 a 10 anos`, `11 a 14 anos`, `15 anos ou mais`), `<h3>` e descrição | `--white` | `.btn-outline` "Saiba mais" em cada bloco, com `aria-label="Saiba mais: {nome do bloco}"` |
| 3 | **Modalidades de aula** — 4 cards (`.grid-cards--4`): Em grupo · Individual · Presencial · On-line | `--brand-tint` | `.btn-primary` "Fazer pré-matrícula" |
| 4 | **Metodologia** — `.split`: texto + 2 blocos (Método próprio · Recursos tecnológicos) | `--white` | `.btn-outline` "Conheça!" |
| 5 | **Séries/níveis** — acordeões por faixa (§3.9): `Kids`, `Teens`, `Young Adults & Adults`, cada rótulo com `lang="en"` | `--bg-gray` | `.btn-primary` "Fazer pré-matrícula" |
| 6 | **Faixa final** — `.cta-band` sem `--overlap`, dentro de uma `.section--tight`: "Teste seu nível de inglês" | `--white` | `.btn-pill--on-brand` "Fazer teste" |

*Segmentar por idade antes de qualquer outra coisa é, na leitura do autor, o padrão mais importante de escola de idiomas.* As modalidades são sempre as mesmas quatro, em dois eixos — **formato** (em grupo ou individual) e **meio** (presencial ou on-line) — aqui, no §8 e no passo 3 da pré-matrícula.

### 5.4 Busca de unidades (`/unidades`)

- Hero em `--brand` liso, texto em `--on-brand`, com ilustração isométrica do mapa em tons da marca e headline pessoal: **"{Marca} perto de você!"**.
- Barra de busca larga logo abaixo do hero: `<label>` visível "Onde você quer estudar?", campo com o placeholder `CEP, cidade, estado ou nome da unidade` e `.btn-primary` "Buscar". Ao lado, o botão "Usar minha localização" (`.btn-outline`, com ícone). A localização só é pedida ao navegador depois desse clique, nunca ao carregar a página.
- Resultado em cards de unidade (§3.11), em `.grid-cards`, ordenados por distância quando há CEP ou localização e por nome nos outros casos; 9 por vez, com o botão "Ver mais unidades". O número de resultados é anunciado numa região `aria-live="polite"` ("12 unidades em Campinas").
- A mesma barra, sem o hero, é a seção 5 da home; lá o envio leva a `/unidades?q={termo}`.

| Estado | O que aparece |
|---|---|
| Inicial (sem busca) | as unidades do estado mais buscado ou, com localização permitida, as 9 mais próximas |
| Carregando | 3 cards-esqueleto no lugar da lista e `aria-busy="true"` na região de resultados |
| Sem resultado | "Não encontramos unidades para "{termo}"." + as 3 unidades mais próximas, quando houver CEP ou localização + `.btn-outline` "Conhecer as aulas on-line" |
| Termo inválido (CEP incompleto) | erro de campo do §3.6: "Digite o CEP com 8 números." |
| Localização negada | "Não foi possível usar sua localização. Busque por CEP ou cidade." abaixo do campo, que recebe o foco |
| Falha de rede | "Não foi possível buscar agora." + `.btn-outline` "Tentar de novo"; o termo digitado é mantido |
