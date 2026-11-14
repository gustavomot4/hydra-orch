### 6.2 Campo

| Parte | Regra |
| --- | --- |
| Rótulo | Sempre visível, acima do campo, `--text-ui` `--weight-bold`, ligado ao campo por `for`. Campo opcional leva " (opcional)" em `--weight-medium` `--muted-foreground`; obrigatório não leva marca, porque é a maioria. |
| Controle | Altura mínima `--field`, raio `--radius`, borda `--line-control` `--input`, fundo `--card`, `padding: 0 var(--space-14)`, texto `--text-body` `--foreground`. Texto de exemplo em `--placeholder`, só para mostrar formato. |
| Dica | Abaixo do campo, `--text-small` `--muted-foreground`, ligada por `aria-describedby`. Some quando há erro. |
| Hover | Borda `--muted-foreground`. |
| Foco | Sem contorno; borda `--primary` e halo `box-shadow: 0 0 0 4px var(--primary-soft)`. Vale para foco por mouse e por teclado. |
| Erro | `aria-invalid="true"`, borda `--line-error` `--destructive`, halo de foco `--destructive-soft`. Mensagem abaixo, `--text-small` `--weight-semibold` `--destructive`, com `circle-alert` `--icon-sm`, ligada por `aria-describedby`. |
| Desabilitado | Fundo `--muted`, texto `--muted-foreground`. |
| Carregando | Quando o campo dispara uma busca (CEP), um `loader-circle` `--icon` gira dentro do campo, à direita, com rótulo oculto "Buscando o endereço". |
| Ícone à esquerda | `--icon` `--muted-foreground`, a 16 px da borda; texto com `padding-left: 46px`. |
| Botão dentro do campo | 46 × 46 px, a 4 px da borda direita, fundo transparente, hover `--muted`; texto com `padding-right: 56px`. Ex.: mostrar senha, com `aria-pressed`. |

- **Lista de seleção nativa:** só para listas fixas e curtas (unidade, forma de pagamento). `appearance: none`, seta `chevron-down` `--icon` em `--muted-foreground` a 12 px da direita, `padding-right: 40px`.
- **Texto longo:** `padding: var(--space-12) var(--space-14)`, altura mínima 96 px, `resize: vertical`.
- **Caixa de marcar:** 22 × 22 px com `accent-color: var(--primary)`, rótulo à direita em `--weight-semibold`, linha com altura mínima `--target`.
- **Máscaras e teclado:** CPF `000.000.000-00` e CEP `00000-000` com `inputmode="numeric"`; celular `(00) 00000-0000` com `inputmode="tel"`; e-mail com `type="email"`. Preencha `autocomplete` (`name`, `tel`, `email`, `postal-code`, `address-line1`, `username`, `current-password`).
- **Endereço:** CEP primeiro. Com 8 dígitos, a busca preenche rua e bairro e o foco vai para o número. Se a busca falhar, os campos ficam livres para digitar e a dica diz isso. Rua ocupa a linha inteira; Número leva o exemplo "Ex.: 120 ou s/n"; Complemento, "Apto, bloco, sala".
