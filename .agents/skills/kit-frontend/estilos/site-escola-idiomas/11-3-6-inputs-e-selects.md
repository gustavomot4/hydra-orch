### 3.6 Inputs e selects

```css
.input, .select {
  display: block; width: 100%; min-height: 44px;
  padding: var(--space-2) 12px;
  border: 1px solid var(--border-input);
  border-radius: var(--r-sm);
  font: inherit; font-size: var(--fs-ui); line-height: 1.5;   /* 16px+ evita zoom automatico no iOS */
  background: var(--white); color: var(--input-text);
}
.cta-band .input { border-color: var(--white); border-radius: var(--r-full); padding-inline: var(--space-4); }   /* campo da faixa de CTA */
.input:hover, .select:hover { border-color: var(--heading); }
.input:disabled, .select:disabled { background: var(--bg-gray); color: var(--paragraph); cursor: not-allowed; }
.input[aria-invalid="true"], .select[aria-invalid="true"] { border-width: 2px; border-color: var(--danger); }   /* a altura continua 44px */

.label       { display: block; margin-bottom: var(--space-2); font-size: var(--fs-ui); font-weight: 600; line-height: 1.5; color: var(--heading); }
.label .req  { color: var(--brand-text); }   /* asterisco na cor da marca ANTES do texto: "* E-mail" */
.cta-band .label, .cta-band .label .req { color: inherit; }   /* sobre a marca, tudo na cor do texto da faixa */

.field__error { display: flex; gap: var(--space-2); margin: var(--space-2) 0 0; font-size: var(--fs-caption); line-height: var(--lh-caption); font-weight: 600; color: var(--danger); }
.cta-band .field__error { color: inherit; }
```

- **Foco:** a regra global do §1 (anel duplo). Não use `outline: none` nem troque a cor da borda no foco: se a marca for vermelha, uma borda na cor da marca parece erro.
- **Erro:** borda de 2px em `--danger` + ícone de alerta + mensagem em `<p class="field__error" role="alert">`, ligada ao campo por `aria-describedby`. Nunca só a cor.
- **Obrigatório:** asterisco com `aria-hidden="true"`, `required` no campo e a legenda "* obrigatório" no topo do formulário.
- **Atributos:** todo campo tem `<label for>`, `type` e `autocomplete` (`email`, `name`, `tel`, `bday`, `postal-code`, `address-level2`).
- **Busca no header:** input com ícone de lupa à esquerda (`padding-left: 48px`), largura máxima de 560px e fundo `--brand-tint` (tint da marca), para se destacar do branco sem virar caixa cinza. A borda continua `--border-input` (4,25:1 sobre o tint).

### 3.7 Stepper (wizard de matrícula)

```
(✓) Unidade ————————— (2) Sobre Você - - - - - - - ( 3 ) Curso
```
- É uma `<ol>`; o passo atual leva `aria-current="step"`.
- Passo concluído: círculo de 32px preenchido com `--brand`, ícone de check em `--on-brand`, rótulo em `--heading` peso 600.
- Passo atual: círculo de 32px preenchido com `--brand`, número em `--on-brand`, rótulo em `--brand-text` peso 700.
- Passos futuros: círculo de 32px com borda de 2px `--border-input` e número em `--paragraph`; rótulo em `--paragraph` peso 400.
- Linha conectora de 2px: `--brand` até o passo atual, `--border-input` adiante.
- Abaixo de 768px a linha vira vertical e os passos empilham.
