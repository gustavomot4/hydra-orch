### 3.11 Demais componentes

Ícones: Lucide, traço de 2px, 24px, em `currentColor`. Ícone decorativo leva `aria-hidden="true"`; botão só de ícone leva `aria-label`.

| Componente | Receita |
|---|---|
| **Card de modalidade** | `.card.card--static` com `.card__body`; ícone de 24px em `--brand-text-dark` dentro de um círculo de 56px `--brand-tint`; `<h3>` em `--fs-item`/600; descrição em corpo. Sem link próprio: o CTA fica no fim da seção. |
| **Card de depoimento** | `.card.card--static` com `.card__body`; `<blockquote>` em corpo; avatar de 48px com as iniciais (fundo `--brand-tint`, texto `--brand-text-dark` 700); nome em `--fs-ui`/600 `--heading`; curso e unidade em `--fs-caption` `--paragraph`. |
| **Card de unidade** | `.card.card--static` com `.card__body`; nome em `<h3>` (`--fs-item`/600); endereço em `<address>`; telefone em `<a href="tel:…">`; links "WhatsApp" e "Ver no mapa"; `.btn-primary` "Fazer pré-matrícula nesta unidade", que leva a `/pre-matricula?unidade={slug}`. |
| **Item com ícone** | o mesmo círculo de 56px com ícone; `<h4>` em `--fs-item`/600; texto em corpo; `gap: var(--space-3)` entre círculo e texto. |
| **Contador** | número em `--fs-section`/700 `--brand-text`; rótulo em `--fs-caption`/600 `--heading`. O valor final está escrito no HTML; a contagem é só efeito visual (§6). |
| **Linha do tempo** | `<ol>`; em cada marco, ano em `--fs-card`/700 `--brand-deep`, título em `--fs-item`/600 e texto em corpo; trilho de 2px `--border` com ponto de 12px `--brand`. Vertical abaixo de 768px; horizontal a partir daí, com as regras do carrossel se não couber. |
| **Dropdown, side-nav, barra das conversões** | §5.1 |
| **Cookie bar e bolha de chat** | §8, itens 8 e 9 |

---
