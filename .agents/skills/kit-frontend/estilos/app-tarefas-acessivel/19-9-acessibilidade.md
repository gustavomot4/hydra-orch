## 9. Acessibilidade

**Meta da aplicação de destino: WCAG 2.2 AA.** O guia fornece pares de cor calculados e regras de implementação. A inspeção da origem não constitui uma certificação de acessibilidade de todas as jornadas.

### 9.1 Contraste calculado

As tabelas usam luminância relativa sRGB: converter cada canal para 0–1; usar `c / 12,92` quando `c <= 0,04045` e `((c + 0,055) / 1,055)^2,4` nos demais casos; combinar com pesos 0,2126, 0,7152 e 0,0722; calcular `(Lmaior + 0,05) / (Lmenor + 0,05)`.

O limite adotado é 4,5:1 para os pares de texto e 3:1 para ícone informativo, contorno de campo, foco e estado de controle. As razões são arredondadas apenas para exibição; o resultado usa o valor sem arredondamento. Nomes das categorias foram neutralizados conforme os tokens.

#### Claro

| Uso e fundo | Texto ou traço | Fundo | Razão | Critério | Resultado |
| --- | --- | --- | --- | --- | --- |
| Texto principal sobre `--ui-bg` | `#111a20` | `#f3f6f8` | 16,23:1 | Texto 4,5 | Passa |
| Texto principal sobre `--ui-bar` | `#111a20` | `#ffffff` | 17,61:1 | Texto 4,5 | Passa |
| Texto principal sobre `--ui-surface` | `#111a20` | `#ffffff` | 17,61:1 | Texto 4,5 | Passa |
| Texto principal sobre `--ui-surface-2` | `#111a20` | `#edf2f5` | 15,62:1 | Texto 4,5 | Passa |
| Texto secundário sobre `--ui-bg` | `#384249` | `#f3f6f8` | 9,47:1 | Texto 4,5 | Passa |
| Texto secundário sobre `--ui-bar` | `#384249` | `#ffffff` | 10,28:1 | Texto 4,5 | Passa |
| Texto secundário sobre `--ui-surface` | `#384249` | `#ffffff` | 10,28:1 | Texto 4,5 | Passa |
| Texto secundário sobre `--ui-surface-2` | `#384249` | `#edf2f5` | 9,11:1 | Texto 4,5 | Passa |
| Texto de ação sobre `--ui-bg` | `#014261` | `#f3f6f8` | 9,91:1 | Texto 4,5 | Passa |
| Texto de ação sobre `--ui-bar` | `#014261` | `#ffffff` | 10,75:1 | Texto 4,5 | Passa |
| Texto de ação sobre `--ui-surface` | `#014261` | `#ffffff` | 10,75:1 | Texto 4,5 | Passa |
| Texto de ação sobre `--ui-surface-2` | `#014261` | `#edf2f5` | 9,53:1 | Texto 4,5 | Passa |
| Texto de ação sobre `--ui-action-soft` | `#014261` | `#e7f3fc` | 9,54:1 | Texto 4,5 | Passa |
| Botão primário sobre `--ui-action` | `#ffffff` | `#025e88` | 7,10:1 | Texto 4,5 | Passa |
| Destaque sobre `--ui-highlight` | `#ffffff` | `#025e88` | 7,10:1 | Texto 4,5 | Passa |
| Opção escolhida sobre `--ui-selected` | `#014261` | `#e7f3fc` | 9,54:1 | Texto 4,5 | Passa |
| Menu escolhido sobre `--ui-tab-active` | `#025e88` | `#e7f3fc` | 6,29:1 | Texto 4,5 | Passa |
| Desabilitado sobre `--ui-disabled` | `#4b565d` | `#e4e8ea` | 6,11:1 | Texto 4,5 | Passa |
| Sucesso sobre `--ui-ok-soft` | `#0a554f` | `#d9f5ee` | 7,52:1 | Texto 4,5 | Passa |
| Aviso sobre `--ui-warn-soft` | `#7c3a03` | `#f9f5c8` | 7,68:1 | Texto 4,5 | Passa |
| Erro sobre `--ui-danger-soft` | `#8f1616` | `#fee2df` | 7,48:1 | Texto 4,5 | Passa |
| Neutro sobre `--ui-neutral-soft` | `#384249` | `#e4e8ea` | 8,33:1 | Texto 4,5 | Passa |
| Contagem sobre `--ui-count` | `#ffffff` | `#b42b01` | 6,39:1 | Texto 4,5 | Passa |
| Contato opcional sobre `--ui-contact` | `#06281c` | `#25d366` | 7,97:1 | Texto 4,5 | Passa |
| Ícone 1 sobre `--ui-bg` | `#025e88` | `#f3f6f8` | 6,54:1 | UI 3,0 | Passa |
| Ícone 1 sobre `--ui-surface` | `#025e88` | `#ffffff` | 7,10:1 | UI 3,0 | Passa |
| Ícone 2 sobre `--ui-bg` | `#8a4b00` | `#f3f6f8` | 6,27:1 | UI 3,0 | Passa |
| Ícone 2 sobre `--ui-surface` | `#8a4b00` | `#ffffff` | 6,80:1 | UI 3,0 | Passa |
| Ícone 3 sobre `--ui-bg` | `#077674` | `#f3f6f8` | 5,02:1 | UI 3,0 | Passa |
| Ícone 3 sobre `--ui-surface` | `#077674` | `#ffffff` | 5,45:1 | UI 3,0 | Passa |
| Ícone 4 sobre `--ui-bg` | `#9f1640` | `#f3f6f8` | 7,27:1 | UI 3,0 | Passa |
| Ícone 4 sobre `--ui-surface` | `#9f1640` | `#ffffff` | 7,89:1 | UI 3,0 | Passa |
| Ícone neutro sobre `--ui-bg` | `#384249` | `#f3f6f8` | 9,47:1 | UI 3,0 | Passa |
| Ícone neutro sobre `--ui-surface` | `#384249` | `#ffffff` | 10,28:1 | UI 3,0 | Passa |
| Borda de campo sobre `--ui-bg` | `#7d8991` | `#f3f6f8` | 3,30:1 | UI 3,0 | Passa |
| Borda de campo sobre `--ui-surface` | `#7d8991` | `#ffffff` | 3,58:1 | UI 3,0 | Passa |
| Borda de campo sobre `--ui-surface-2` | `#7d8991` | `#edf2f5` | 3,18:1 | UI 3,0 | Passa |
| Foco sobre `--ui-bg` | `#025e88` | `#f3f6f8` | 6,54:1 | UI 3,0 | Passa |
| Foco sobre `--ui-bar` | `#025e88` | `#ffffff` | 7,10:1 | UI 3,0 | Passa |
| Foco sobre `--ui-surface` | `#025e88` | `#ffffff` | 7,10:1 | UI 3,0 | Passa |
| Foco sobre `--ui-surface-2` | `#025e88` | `#edf2f5` | 6,29:1 | UI 3,0 | Passa |
| Interruptor desligado sobre `--ui-toggle-off` | `#ffffff` | `#7d8991` | 3,58:1 | UI 3,0 | Passa |
| Interruptor ligado sobre `--ui-toggle-on` | `#ffffff` | `#077674` | 5,45:1 | UI 3,0 | Passa |
| Texto principal sobre `--ui-action-soft` | `#111a20` | `#e7f3fc` | 15,62:1 | Texto 4,5 | Passa |
| Texto principal sobre `--ui-ok-soft` | `#111a20` | `#d9f5ee` | 15,30:1 | Texto 4,5 | Passa |
| Texto secundário sobre `--ui-action-soft` | `#384249` | `#e7f3fc` | 9,11:1 | Texto 4,5 | Passa |
| Texto secundário sobre `--ui-ok-soft` | `#384249` | `#d9f5ee` | 8,93:1 | Texto 4,5 | Passa |
| Ação de erro sobre `--ui-bg` | `#8f1616` | `#f3f6f8` | 8,43:1 | Texto 4,5 | Passa |
| Ação de erro sobre `--ui-surface` | `#8f1616` | `#ffffff` | 9,15:1 | Texto 4,5 | Passa |
| Ação de erro sobre `--ui-surface-2` | `#8f1616` | `#edf2f5` | 8,12:1 | Texto 4,5 | Passa |
| Foco em superfície semântica sobre `--ui-action-soft` | `#025e88` | `#e7f3fc` | 6,29:1 | UI 3,0 | Passa |
| Foco em superfície semântica sobre `--ui-ok-soft` | `#025e88` | `#d9f5ee` | 6,17:1 | UI 3,0 | Passa |
| Foco em superfície semântica sobre `--ui-warn-soft` | `#025e88` | `#f9f5c8` | 6,39:1 | UI 3,0 | Passa |
| Foco em superfície semântica sobre `--ui-danger-soft` | `#025e88` | `#fee2df` | 5,80:1 | UI 3,0 | Passa |
| Foco em superfície semântica sobre `--ui-neutral-soft` | `#025e88` | `#e4e8ea` | 5,75:1 | UI 3,0 | Passa |
