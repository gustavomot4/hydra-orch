# Correções deste projeto

Toda reprovação do dono entra aqui **antes** de corrigir a tela. Leia este arquivo antes de criar ou alterar qualquer tela: ele prevalece sobre `DESIGN.md`.

Uma linha por correção:

`- AAAA-MM-DD | tela | o que foi reprovado, nas palavras da pessoa | regra geral | onde mais foi corrigido`

A escolha entre propostas também entra, porque vira calibração do gosto:

`- AAAA-MM-DD | escolha | o que foi escolhido e o que a escolha cega apontou | sinal, ainda não regra | nenhum`

<!-- kit-frontend:correcoes -->

- 2026-11-14 | navegação e início | “complicado de entender” e “tem que procurar bastante e ler bastante para saber o que fazer” | mostrar a tarefa principal na primeira dobra, com o projeto selecionado junto do campo; adiar detalhes técnicos para quando forem necessários | registrado para as propostas
- 2026-11-14 | barra lateral | “ela deveria espandir mais e mostrar os nomes” | mostrar ícone e nome na navegação por padrão e permitir ajustar a largura no desktop | registrado para as propostas
- 2026-11-14 | identidade | “mais ousado, marcante e que chame mais atenção” | dar expressão ao modo de iniciar e acompanhar trabalho, mantendo a leitura rápida | registrado para as propostas
- 2026-11-14 | escolha | “não gostei de nenhuma” e “a atual ja me agrada bastante”, com prioridade para “melhorar a ux” | usar a interface existente como base e concentrar mudanças na navegação, na clareza das ações e no fluxo de trabalho | Novo chat e barra lateral
- 2026-11-14 | terminal e início | “está travando dms”, “a interface dele vem toda errada” e “ainda eu não consegui rodar nenhum prompt” | manter a sessão e a renderização ao redimensionar, reduzir o atraso de entrada e explicar como abrir o agente e enviar um prompt | Terminal e Novo chat
- 2026-11-14 | fluxo principal | “a pessoa pode e deve poder conversar na parte de novo chat” e “deixar o mais facil possivel” | iniciar o agente e continuar a conversa pelo Novo chat, com projeto contextual e detalhes avançados sob demanda | planejamento do fluxo de conversa
- 2026-11-14 | pastas e revisão | “a pasta é um repo git e aparece isso”, “não posso trabalhar em uma pasta que não é .git?” e “has no attempts to review” | aceitar pasta comum no chat sem criar Git; preservar o original em cópia isolada; oferecer revisão apenas quando existe resultado | cadastro de pasta, conversa e revisão
- 2026-11-14 | terminal | “o terminal do claude code está muito lento ainda” | restaurar a sessão existente ao voltar à tela e impedir a criação repetida de processos para a mesma sessão | Terminal
- 2026-11-14 | abertura e navegação | “porque precisa de um token para acessar?”, “um executável para subir o sistema e parar ele” e “projetos e sessão ... bem confusa” | gerenciar acesso local no executável; mostrar pastas e conversas como estrutura principal, com organização técnica sob demanda | executável, autenticação e barra lateral
- 2026-11-14 | troca de modelo e combo | “eu quero mudar de modelos e combos sem perder o contexto” | permitir a troca na mesma conversa para os próximos envios; preservar histórico, arquivos e decisões; registrar a configuração por turno e preparar o contexto quando a sessão nativa não puder continuar | plano de conexão ao OmniRoute e continuidade da conversa
