# Correções deste projeto

Toda reprovação do dono entra aqui **antes** de corrigir a tela. Leia este arquivo antes de criar ou alterar qualquer tela: ele prevalece sobre `DESIGN.md`.

Uma linha por correção:

`- AAAA-MM-DD | tela | o que foi reprovado, nas palavras da pessoa | regra geral | onde mais foi corrigido`

A escolha entre propostas também entra, porque vira calibração do gosto:

`- AAAA-MM-DD | escolha | o que foi escolhido e o que a escolha cega apontou | sinal, ainda não regra | nenhum`

<!-- kit-frontend:correcoes -->

- 2026-11-16 | preparação do projeto | “uma pasta .git não poderia atrapalhar em nada se não tem cria”, “o orquestrador tem que ser o mais automático possível” | preparar automaticamente o Git necessário na cópia isolada; não exigir comandos Git, troca de modo ou mudança de pasta para iniciar a coordenação; preservar a origem e o histórico | coordenador, orientação da conversa e documentação

- 2026-11-15 | aprovação | “sim aprovo tudo, pode começar o build” | construir a composição compacta das três vistas, com painéis ajustáveis, hierarquia por projeto, catálogos limitados e compositor sem atalhos predefinidos | implementação autorizada da compactação

- 2026-11-15 | densidade e espaço | “sistema apertado”, “tudo ... muito grande”, “aumentar ou diminuir ... ocultar ou mostrar” | propor uma composição de trabalho compacta, tamanhos independentes de interface/texto/editor, painéis ajustáveis e seções recolhíveis; preservar preto predominante e legibilidade | estudo visual antes do planejamento e implementação
- 2026-11-15 | hierarquia e listas extensas | “conversas, pastas ... deveria poder ocultar”, “separados pelo seu pai”, “lista imensas ... modelos” | agrupar trabalho pelo projeto/pasta pai, expandir filhos sob demanda e limitar prévias de catálogos com abertura de lista pesquisável e paginada | propostas de sidebar, seleção de trabalho e cotas
- 2026-11-15 | compositor, pastas e catálogo | “tire essas opções rápidas”, “tab ... próximo passo provável”, “setas ... últimos prompts”, “abrir o explorador”, “combos ... disponíveis ... demorando” | remover atalhos de prompts da proposta; prever sugestão discreta aceita por Tab e histórico com setas sem quebrar edição; priorizar seletor nativo de pasta; investigar latência do catálogo sem disparar inferência | estudo visual e diagnóstico, sem alterar produto nesta etapa

- 2026-11-15 | cards e atualização | “podermos arrastar ele de um lado para o outro”, “deveria aparecer na hora nos cards” | arrastar pelo corpo do card, distinguir clique de movimento, atualizar por eventos e representar subagentes somente quando observados no protocolo | canvas, eventos e snapshots
- 2026-11-15 | conversa e início | “mudar modelo ... fica preso em cima”, “texto deveria ter estilização melhor”, “balão ... muito feio”, “dropdown ... ruins” | manter compositor e configuração acessíveis no rodapé; resposta em Markdown, atividade discreta em cinza, mensagem do usuário compacta; substituir formulário inicial por contexto junto do compositor e busca de pastas; seguir interação familiar de Codex e Claude Code, mantendo o preto | Novo chat e Conversa

- 2026-11-15 | calibração de cor | “exagerou no laranja, o principal é preto ainda” | preto e cinza neutro dominam fundo, sidebar e cards; laranja aparece só em ações, foco, seleção e pequenos detalhes, sem fundos marrons nem degradê amplo | tokens, navegação e canvas

- 2026-11-15 | escolha e cor | “gostei mais da versão a ... cores da versão c ... utilize mais das cores no sistema, esta muito preto” | construir a mesa livre com detalhe lateral da A; adotar laranja/cobre da C em ações, seleção, navegação e superfícies quentes, com estados distintos e legíveis | canvas, casca e tokens compartilhados

- 2026-11-15 | organização avançada | “ainda estou confuso ... area de trabalho infinita ... cards os agentes trabalhando ... linhas ... clicar no card e mostra o chat” | estudar canvas navegável com cards e relações observáveis, detalhe por seleção e alternativa em lista; preservar a base visual atual; apresentar imagens antes da implementação | propostas visuais pendentes de escolha

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
