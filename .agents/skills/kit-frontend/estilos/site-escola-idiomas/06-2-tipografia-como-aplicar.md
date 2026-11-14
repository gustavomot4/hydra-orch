## 2. Tipografia — como aplicar

| Papel | Tamanho | Peso | Altura de linha | Cor | Detalhes |
|---|---|---|---|---|---|
| **H1 hero** | `--fs-hero` (36 a 60px) | 700 | `--lh-tight` (1.15) | `--white` sobre imagem com scrim / `--heading` sobre branco | `margin-bottom: var(--space-3)` |
| **Subtítulo do hero** | `--fs-hero-sub` (18 a 25px) | 600 | `--lh-snug` (1.3) | herda do hero | |
| **Título de seção (H2)** | `--fs-section` (28 a 50px) | 700 | `--lh-heading` (1.2) | `--brand-deep` | alinhado à esquerda, `margin-bottom: var(--heading-mb)`; grande e no tom escuro da marca, é a assinatura visual |
| **Título da faixa de CTA** | `--fs-cta` (24 a 40px) | 700 | `--lh-heading` | `--on-brand` | caixa alta |
| **Eyebrow / rótulo** | `--fs-caption` (14px) | 700 | `--lh-caption` (1.4) | `--heading` | caixa alta, pílula com `border: 1px solid var(--border)`, `padding: var(--space-2) var(--space-4)`, `border-radius: var(--r-full)`; uso no §5.2 |
| **H3 de tile e de bloco** | `--fs-card` (22 a 27px) | 600 | `--lh-heading` | `--heading` (`--white` no tile) | `margin-bottom: var(--space-3)` |
| **H4 de item** | `--fs-item` (20px) | 600 | `--lh-heading` | `--heading` | `margin-bottom: var(--space-3)` |
| **Título de card** (`.card__title`) | `--fs-item` (20px) | 600 | `--lh-snug` | `--heading` | é um `<h3>` com tamanho de H4 |
| **Corpo** | **`--fs-body` (17px)** | 400 | **`--lh-body` (1.7)** | `--paragraph` (`#666`) | nunca preto puro no corpo |
| **Corpo do hero** | `--fs-body-lg` (17 a 20px) | 500 | `--lh-lead` (1.6) | herda do hero | só dentro do hero |
| **Link de navegação** | `--fs-ui` (16px) | 500 | `--lh-heading` | `--heading` | ativo: `--brand-text`, peso 700 e `aria-current="page"` |
| **Label e texto de campo** | `--fs-ui` (16px) | 600 no label, 400 no campo | 1.5 | `--heading` no label, `--input-text` no campo | |
| **Botão** | `--fs-caption` (14px) | 700 | `--lh-heading` | conforme a variante (§3.1) | pílula: sempre caixa alta, por CSS. `.btn-primary` e `.btn-outline`: caixa de frase |
| **Data, tag, badge, contador de passo** | `--fs-caption` (14px) | 400 na data, 700 nos demais | `--lh-caption` | conforme a receita | |

**Regras:**
- **Nunca** use `#000` nem em título nem em texto. Títulos = `--heading` (`#04000b`), corpo = `--paragraph` (`#666`).
- Corpo em **17px**, não 16px, com altura de linha 1.7 (17/28.9). Aumenta legibilidade para um público amplo (crianças a adultos, pais lendo no celular).
- H1, H2, subtítulo do hero, H3, título da faixa de CTA e corpo do hero usam `clamp()` com termo fluido `rem + vw` e limites em `rem`: o texto cresce com o zoom do navegador e com a fonte padrão do usuário. H4, corpo e textos de 14px são fixos em `rem`. Zero media query para tipografia e nenhum `font-size` fixo em `px` (o único `px` é o piso de 16px de `--fs-ui`, que evita o zoom automático do iOS nos campos).
- `letter-spacing: 0` em tudo. Nada de tracking dramático.
- Pesos carregados: 400, 500, 600 e 700. Nenhum outro.
- Rótulos de botão em caixa de frase no HTML ("Fazer pré-matrícula", "Saiba mais"); a caixa alta da pílula, do eyebrow e da tag vem de `text-transform`, nunca do texto digitado.

---
