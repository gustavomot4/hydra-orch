### 7.6 Entrar

Duas colunas, `grid-template-columns: minmax(0, 1fr) minmax(0, 560px)`, fundo `--card`, altura mínima `100dvh`.

- **Ilustração**, à esquerda, `aria-hidden="true"`: bloco `--primary-soft` com `margin: var(--space-16) 0 var(--space-16) var(--space-16)`, raio 32 px, `padding: var(--space-56)`, conteúdo alinhado embaixo com espaço `--space-20`. Dois círculos decorativos: 420 px de `color-mix(in srgb, var(--primary) 8%, transparent)` saindo pelo canto superior direito e 180 px de `--accent-soft` no meio. Por cima: o nome da marca em `--text-title`, a frase "Olá! Que bom ter você aqui." em `--text-hero` e "Quem vem hoje e quem ainda não confirmou." em `--text-section` `--weight-regular` `--muted-foreground`, largura máxima 440 px.
- **Formulário**, à direita, centralizado na vertical, `padding: var(--space-56) clamp(24px, 5vw, 64px)`, espaço `--space-18`: marca (só o nome, em `--text-heading`); `h1` "Entrar"; "Use o usuário e a senha que a clínica criou para você." em `--muted-foreground`; campos Usuário (`user-round`, `autocomplete="username"`, foco inicial) e Senha (`lock-keyhole`, botão de mostrar e esconder com `eye` e `eye-off`); botão `lg` `block` "Entrar"; e a caixa de ajuda (fundo `--background`, raio `--radius-box`, `padding: var(--space-14)`, `life-buoy` `--primary`, `--text-ui` `--muted-foreground`): "Esqueceu a senha? Peça para o responsável da clínica criar uma nova para você."
- **Estados:** campos vazios mostram o erro no campo; usuário ou senha errados mostram alerta `danger` "Usuário ou senha incorretos. Confira e tente de novo." acima do formulário e limpam a senha; sessão encerrada mostra alerta `info` "Sua sessão terminou. Entre novamente para continuar."; enquanto confere, o botão fica em carregando. Depois de entrar, a pessoa volta para a tela que tentou abrir ou para Hoje.
- **Abaixo de 900 px:** só o formulário, `padding: var(--space-32) var(--space-20) var(--space-40)`, alinhado no topo.

### 7.7 Estados de acesso e textos

| Situação | Ícone | Título | Texto | Ação |
| --- | --- | --- | --- | --- |
| Sem acesso | `shield-alert` | Esta área é do responsável pela clínica | Seu perfil não tem acesso a esta tela. Se precisar dela, fale com o responsável. | Voltar para Hoje |
| Endereço inexistente | `map-pin-off` | Não encontramos esta página | O endereço pode ter mudado. Use o menu para chegar à tela que você procura. | Voltar para Hoje |
| Erro numa tela | `triangle-alert` | Algo deu errado nesta tela | Os dados salvos não foram afetados. Se continuar, avise o suporte. | Tentar de novo; Voltar para Hoje |
| Sessão encerrada | — | — | Volta para Entrar com o alerta do 7.6 | — |

Esses estados usam o bloco de estado vazio (6.12) dentro da casca, com o menu à vista, e um `h1` oculto com o título.

Textos: frases curtas, verbo no início do botão ("Agendar consulta", "Salvar paciente", "Marcar falta"), sem "registro", "vincular" nem códigos de erro na tela. Seta é ícone, nunca "←" ou "→" escrito. Datas por extenso no cabeçalho ("Quarta, 28 de outubro") e `dd/mm/aaaa` nos campos; horas em `HH:MM`; valores em reais com `R$` e vírgula.
