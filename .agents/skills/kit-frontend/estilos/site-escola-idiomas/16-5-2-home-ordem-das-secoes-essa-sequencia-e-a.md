### 5.2 Home — ordem das seções (essa sequência é a receita)

| # | Seção | Fundo | CTA de fechamento | Função de negócio |
|---|---|---|---|---|
| 1 | **Hero carrossel** (Swiper, 4 slides, bullets; coverflow a partir de 1200px) | foto + scrim | par de pílulas: `--ghost` "Fazer teste de nível" + `--brand` "Fazer pré-matrícula" | Campanha sazonal / matrícula |
| 2 | **Faixa de CTA de lead** (`.cta-band.cta-band--overlap` com o formulário progressivo) | `--brand` | botão-seta do formulário | Captura de e-mail acima da dobra |
| 3 | **Sobre / método** (`.split`: imagem + texto + números) | `--white` | `.btn-outline` "Saiba mais" | Confiança |
| 4 | **Cursos** — faixa de tiles | `--white` | cada tile é o link ("Conheça") | Navegação comercial principal |
| 5 | **Busca de unidade** (`.section--tight`: título em `--fs-card` + o campo do §5.4) | `--bg-gray` | `.btn-primary` "Buscar" | Ancoragem local |
| 6 | **Recursos digitais** (app, plataforma) | `--white` | `.btn-outline` "Conheça!" | Diferencial competitivo moderno |
| 7 | **Viagens e intercâmbios** (`.split`) | `--brand-tint` | `.btn-outline` "Conheça!" | Upsell / sonho |
| 8 | **Por que nós** — contadores + prêmios/selos | `--white` | `.btn-outline` "Saiba mais" | Prova social institucional |
| 9 | **Linha do tempo** ("{N} décadas de história") | `--brand-tint` | `.btn-outline` "Conheça nossa história" | Autoridade e longevidade |
| 10 | **Depoimentos de alunos** (carrossel de cards) | `--bg-gray` | par: `.btn-outline` "Fazer teste de nível" + `.btn-primary` "Fazer pré-matrícula" | Prova social pessoal |
| 11 | **Blog** (3 posts em `.grid-cards`) | `--white` | `.btn-outline` "Saiba mais", com `aria-label="Saiba mais: todos os posts do blog"` | SEO e nutrição de lead |
| 12 | **Footer** (§5.6) | `--brand-dark` | repete as duas conversões | Navegação completa + repetição do CTA |

- **Hero:** um `<h1>` só, no slide 1; nos outros slides o título é um `<p>` com o mesmo estilo. Texto em `--white` sobre scrim obrigatório: abaixo de 768px, `rgb(0 0 0 / .6)` sobre o slide inteiro; a partir de 768px, `linear-gradient(90deg, rgb(0 0 0 / .7) 0%, rgb(0 0 0 / .55) 55%, transparent 100%)`, com o texto restrito aos 55% da esquerda. No pior caso (foto branca) isso dá 5,74:1 e 4,74:1. A imagem do slide 1 leva `fetchpriority="high"`, `width` e `height`, sem `loading="lazy"`.
- **Brancos seguidos:** 3 e 4 são os únicos; a faixa de tiles, que é imagem de ponta a ponta, separa as duas.
- **Eyebrow:** uma linha acima do H2 nas seções 3, 4 e 6 a 11, com o nome curto da seção ("Sobre nós", "Cursos", "Blog"), a 16px (`--space-3`) do título. Não entra no hero, na faixa de CTA nem na busca de unidade, e só existe na home.
- **Números e prêmios** são os da escola: `{N}+ anos`, `{N} unidades`, `{prêmio} {N}×`. Não copie os do site analisado.

> Se você precisa cortar, mantenha **1, 2, 4, 5, 8, 10, 12**. Na leitura do autor, é o esqueleto mínimo de uma home de escola de idiomas que converte.
