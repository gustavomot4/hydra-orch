### 6.6 Cartão "Próximo"

Responde "quem é o próximo?". É a consulta Agendada ou Confirmada de hoje com o início mais cedo a partir de 10 minutos atrás.

- `<section aria-label="Próximo paciente" data-surface="dark">`, fundo `--foreground`, texto `--on-dark`, raio `--radius-lg`, `padding: var(--space-10) var(--space-12) var(--space-10) var(--space-18)`, espaço `--space-16`, `flex-wrap: wrap`, margem inferior `--space-14`.
- **Rótulo:** ponto de 8 px em `--on-dark-accent` com halo `0 0 0 4px color-mix(in srgb, var(--on-dark-accent) 22%, transparent)` e o texto "PRÓXIMO · EM 20 MIN" em `--text-micro` `--weight-extrabold` `--tracking-caps` maiúsculo `--on-dark-accent`. O tempo diz "agora" quando já passou do início, "em 20 min" abaixo de 1 hora e "em 1 h 15 min" acima.
- **Corpo** (um `<button>` que abre o detalhe): hora em `--text-display-sm` `--weight-extrabold` números tabulares; ao lado, nome em `--text-lead` `--weight-bold` e "Procedimento · Profissional · 30 min" em `--text-small` `--on-dark-muted`. Hover: fundo `color-mix(in srgb, var(--on-dark) 6%, transparent)`, raio `--radius-md`.
- **Ações**, à direita: "Iniciar atendimento" (`stethoscope`), só se a consulta estiver Confirmada, com fundo `--on-dark-accent` e texto `--foreground`; "WhatsApp" (`message-circle`), com fundo `--on-dark-fill` e texto `--on-dark`. Ambos na altura `--control-md`.
- **Compacto** (agenda abaixo de 900 px): `padding: var(--space-8) var(--space-12)`, raio `--radius-box`, hora em `--text-title`, nome em `--text-ui`, segunda linha em `--text-caption`, sem as ações; tocar abre o detalhe.
- Abaixo de 600 px, corpo e ações ocupam a largura toda e os botões dividem a linha. A 375 px o cartão tem 313 px de largura útil, e "Iniciar atendimento" (144 px de ícone e texto) mais "WhatsApp" (106 px) não cabem com o `padding` de `--space-18` do botão (precisam de ≈330 px): os botões ficam com `padding: 0 var(--space-12)` e `flex: 1 1 auto` (cada um com o seu conteúdo e a sobra dividida igualmente) e o contêiner das ações com `min-width: 0`, senão os botões o empurram para fora do cartão.

```css
@media (max-width: 599px) {
  .next-body, .next-actions { flex: 1 1 100%; }
  .next-actions { min-width: 0; }
  .next-actions .button { flex: 1 1 auto; min-width: 0; padding: 0 var(--space-12); }
}
```

### 6.7 Linha "agora"

- **Na lista do dia:** um item `aria-hidden="true"` entre a última consulta que já começou e a primeira que ainda não começou. Ponto de 10 px `--accent` com halo `0 0 0 4px var(--accent-soft)`, a palavra "Agora" em `--text-caption` `--weight-bold` `--accent-text` e uma linha de 2 px `--accent` até a borda, `margin: var(--space-4) var(--space-14)`. Se todas as consultas já começaram, a linha não aparece.
- **Na grade:** seção 7.2.
- A hora usada pela linha, pelo cartão "Próximo" e pelos grupos é atualizada a cada 30 s.
