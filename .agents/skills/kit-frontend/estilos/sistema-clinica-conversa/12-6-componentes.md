## 6. Componentes

Todo componente interativo tem os estados padrão, hover, foco, ativo e desabilitado; os que recebem dado têm também erro e carregando. Foco por teclado é sempre o contorno da base (seção 2), salvo onde o componente diz outra coisa. Ícones são de traço, do conjunto Lucide (pacote `lucide-react` ou `lucide`), com `aria-hidden="true"` quando há texto ao lado.

**Alvo de toque.** Controle isolado (botão de ícone, fechar, item de lista, botão principal) tem pelo menos `--target` de altura e de largura. Controles em grupo (chips, horários, paginação, segmentado, botões pequenos lado a lado) têm pelo menos `--control-sm` de altura. Todos ficam acima do mínimo de 24 × 24 px da WCAG 2.2.

### 6.1 Botão

```css
.button { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-8);
  height: var(--control-md); padding: 0 var(--space-18); border: var(--line-control) solid transparent; border-radius: var(--radius-md);
  font-size: var(--text-body); font-weight: var(--weight-semibold); white-space: nowrap; text-decoration: none;
  transition: background-color var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast); }
.button svg { width: var(--icon); height: var(--icon); flex: none; }
.button.sm { height: var(--control-sm); padding: 0 var(--space-14); border-radius: var(--radius-sm); font-size: var(--text-small); }
.button.sm svg { width: var(--icon-md); height: var(--icon-md); }
.button.lg { height: var(--control-lg); padding: 0 var(--space-24); border-radius: var(--radius); font-size: var(--text-lead); }
.button.block { width: 100%; }
.button:active:not(:disabled) { transform: translateY(1px); }
.button:disabled { opacity: .55; }
```

| Variante | Fundo | Texto | Borda | Hover | Uso |
| --- | --- | --- | --- | --- | --- |
| `primary` | `--primary` | `--primary-foreground` | — | fundo `--primary-hover` | A ação principal da tela ou do detalhe |
| `secondary` | `--card` | `--foreground` | `--border` | borda `--border-strong`, fundo `--card-soft` | Ação ao lado da principal, Voltar, Remarcar, Ligar, Ficha |
| `ghost` | transparente | `--foreground` | — | fundo `--muted` | Botão de ícone, fechar |
| `soft` | `--primary-soft` | `--primary` | — | fundo `--primary-soft-hover` | Agendar de novo |
| `danger` | `--card` | `--destructive` | `--border` | fundo `--destructive-soft`, borda `color-mix(in srgb, var(--destructive) 25%, var(--card))` | Faltou, Cancelar |
| `whatsapp` | `--whatsapp` | `--on-dark` | — | fundo `--whatsapp-hover` | Só o botão que abre a conversa com o paciente |
| `dark` | `--foreground` | `--on-dark` | — | fundo `--foreground-hover` | Confirmação de ação destrutiva no diálogo |

- **Ativo:** mantém a cor do hover e desce 1 px.
- **Desabilitado:** opacidade 0,55, cursor `not-allowed`, sem hover.
- **Carregando:** o ícone dá lugar a `loader-circle` girando (`--duration-spin`, linear, infinito); o botão fica desabilitado com `aria-busy="true"` e mantém o texto, para a largura não pular.
- **Botão de ícone:** `--target` × `--target`, raio `--radius-md`, ícone `--icon`, variante `ghost` ou `secondary`, com `aria-label` e `title` iguais.
- **Link com cara de botão:** a mesma classe num `<a>`. Link externo (conversa, telefone) abre com `target="_blank" rel="noreferrer"`, exceto `tel:`.
