# Marca: Hydra (hydra-orch)

**Brief:** Completo  
**Data:** 2026-11-06  
**Status:** Proposto para aprovação  
**Norma de Referência:** `kit-frontend` (Regras G01 a G23, Anti-Genérico e Criação de Marca)

---

## 1. Essência

- **Promessa, em uma frase:** Orquestração autônoma e resiliente de agentes de engenharia que divide tarefas em worktrees Git isolados, auto-regenera falhas de compilação e nunca entrega código sem verificação de testes.
- **Por que existe:** Desenvolvedores e equipes de engenharia perdem horas gerenciando tarefas concorrentes de modelos de IA, resolvendo conflitos em branches, rodando compilações manuais e lidando com falhas silenciosas de agentes em loop. O Hydra transforma automação probabilística em pipelines de software determinísticos, observáveis e auditáveis.
- **O que nunca seria:** Um chatbot conversacional genérico, um assistente com respostas prolixas ou uma interface decorativa com gradientes roxos de IA, ícones de faísca (✨) e promessas ocas de "mágica". O Hydra é maquinário pesado de software, silencioso e preciso.

---

## 2. Identidade Existente

- **O que já existe:** Apenas o nome **Hydra** (e o identificador de pacote `hydra-orch`).
- **O que precisa ficar:** O nome Hydra e o significado central da hidra (múltiplas cabeças autônomas trabalhando coordenadas; quando uma falha, o sistema regenera e cura a execução).
- **O que precisa ser criado:** Logotipo (símbolo e tipografia), paleta de cores acessível, tipografia de sistema, tom de voz, regras de geometria e componentes visuais de controle.

---

## 3. Público e Personas

### Persona 1: Alex, Staff Software Engineer & Tech Lead
- **Base:** Hipótese baseada em operadores de agentes autônomos e arquitetos de software.
- **Objetivo:** Delegar refatorações complexas, migrações de dezenas de arquivos e auditorias de segurança em paralelo, com certeza matemática de que a suíte de testes protegerá a branch principal.
- **Medo:** Agentes modificando arquivos fora do escopo, inserindo vulnerabilidades ou queimando orçamentos de tokens em loops infinitos sem entregar nada utilizável.
- **Contexto de uso:** Monitor de alta resolução no desktop ou notebook em plantão; terminal, IDE e navegador sempre abertos simultaneamente.
- **Familiaridade com tecnologia:** Avançada (Git avançado, Docker, CI/CD, Python, Rust, automação de infraestrutura).
- **Como validar:** Sessão de teste observando o uso do painel durante um run com 5 subagentes paralelos.

### Persona 2: Beatriz, Engenheira de Software Pleno & Operadora de IA
- **Base:** Hipótese baseada em desenvolvedores que utilizam LLMs no dia a dia.
- **Objetivo:** Acompanhar o progresso dos agentes em tempo real, inspecionar diffs de código gerados, aprovar ações sensíveis (HITL) com um clique e entender diagnósticos de falhas rapidamente.
- **Medo:** Ficar perdida em logs gigantescos de terminal, não saber qual agente quebrou o build ou não conseguir reverter alterações parciais.
- **Contexto de uso:** Alternando rapidamente entre tarefas no editor de código e o painel de controle do Hydra.
- **Familiaridade com tecnologia:** Alta (desenvolvimento web, REST APIs, testes unitários).
- **Como validar:** Entrevista rápida de usabilidade sobre o fluxo de aprovação de diffs.

---

## 4. Concorrentes e Espaço Livre

| Quem | Cor e Tipografia | Tom | O que faz bem | Espaço Livre do Hydra |
| --- | --- | --- | --- | --- |
| **Claude Code / Aider** | Terminal monocromático / CLI texto puro | Técnico, conciso, focado | Velocidade instantânea no terminal para tarefas pontuais | Não oferece visualização espacial de DAGs paralelos, telemetria de múltiplos worktrees nem painel de aprovação visual para equipes. |
| **Devin / OpenHands** | Web SaaS, tons escuros padrão com roxo/azul | Produto em nuvem, corporativo | Execução ponta a ponta com máquina virtual remota | É lento por depender de VMs remotas, custoso, sem controle estrito de soberania de dados local e sem motores de healing baseados em tree-sitter. |
| **LangGraph / Flowise** | Diagramas em caixa, visual neutro/genérico | Abstrato, voltado a fluxos conceituais | Desenho de pipelines lógicos | Focado em lógica de nós, não em engenharia real de software (não gerencia worktrees Git reais, compilações, nem testes herméticos). |

**Espaço Livre do Hydra:** Um **Console Soberano de Engenharia Local-First**. Une a velocidade cirúrgica de um terminal CLI de alta performance à clareza espacial de uma telemetria de controle aéreo — claro por padrão, focado apenas no dado valioso, sem alucinações visuais e com governança estrita.

---

## 5. Personalidade com Custo

As três palavras que definem o Hydra, cada uma com o que ela **recusa expressamente**:

1. **Cirúrgico**, não burocrático:
   *O que abraça:* Mostra o diff exato, a linha do erro no teste, o tempo em milissegundos e a ação recomendada em um único campo visual.
   *O que recusa:* Formulários longos com campos desnecessários, confirmações redundantes para ações triviais e menus aninhados que escondem a informação.
2. **Resiliente**, não passivo:
   *O que abraça:* Quando um subagente falha em um teste ou atinge limite de taxa, o sistema ativa handoffs, auto-cura e persistência de checkpoints sem travar a sessão.
   *O que recusa:* Mensagens genéricas de erro que jogam o problema de volta ao colo do operador sem contexto do que já foi tentado.
3. **Soberano**, não exibicionista:
   *O que abraça:* Roda localmente no hardware do usuário, respeita seus arquivos, sua privacidade e seus segredos. Comunica resultados com sobriedade.
   *O que recusa:* Efeitos visuais desnecessários de "IA mágica", popups intrusivos, animações que atrasam a visualização e dados de marketing na tela de trabalho.

---

## 6. Tom de Voz em Quatro Dimensões

| Dimensão | Posição | Justificativa |
|---|---|---|
| **Formal vs Casual** | **Pragmático e Técnico** | Nem jargão corporativo inchado, nem gírias artificiais. A linguagem de um engenheiro sênior no pull request. |
| **Sério vs Engraçado** | **Sério e Focado** | Erro de teste, falha de merge ou vulnerabilidade de segurança não admitem piadas ou ironias. O tom é objetivo. |
| **Respeitoso vs Irreverente** | **Respeitoso e Silencioso** | Respeita o foco e o tempo do operador. Não interrompe sem motivo; quando interrompe, é porque precisa de decisão humana (HITL). |
| **Neutro vs Entusiasmado** | **Neutro e Factível** | Sem exclamações falsas ("Incrível!", "Uhuu!"). O Hydra reporta métricas e fatos verificados. |

---

## 7. Mensagem e Voz

- **Em 5 segundos, quem usa precisa sentir:** *"Tenho o controle total do que está acontecendo na minha máquina e posso confiar que o código será testado antes de ser aplicado."*
- **E lembrar:** *"O Hydra isola o trabalho, testa a fundo e resolve sem alucinar."*

### Frases Reais da Interface (Anti-Clichê)

| Situação | Frase Genérica de IA (Evitada) | Frase Oficial do Hydra |
|---|---|---|
| **Botão de Ação Primária** | `Começar mágica agora →` | `Executar plano` / `Aprovar e aplicar diff` |
| **Botão de Interrupção** | `Cancelar tudo` | `Abortar run (preservar worktrees)` |
| **Estado Vazio (Sem Tarefas)** | `Sua jornada começa aqui! Crie seu primeiro agente incrível.` | `Nenhum run ativo. Dispare uma tarefa pelo terminal ou selecione um workspace.` |
| **Diagnóstico de Erro** | `Ops! Algo deu errado com a IA. Tente novamente.` | `Falha no teste tests/test_auth.py:42: AssertionError. Healer gerou proposta de patch.` |
| **Confirmação de Sucesso** | `Parabéns! Sua tarefa foi finalizada com perfeição!` | `Run #142 concluído: 18 testes aprovados em 2.1s · 3 arquivos alterados · 0 regressões.` |
| **Bloqueio de Segurança (HITL)** | `Atenção: ação arriscada!` | `Aprovação necessária: execução de comando com efeito colateral fora do sandbox.` |

---

## 8. O Que Isso Muda na Tela

| Do Brief de Marca | Decisão de Design e Interface |
|---|---|
| **G01: Bater o olho e saber o que fazer** | A tela principal destaca em primeiro plano o card do Run ativo com barra de progresso do DAG e o botão da próxima ação (`Inspecionar diff` ou `Aprovar`). |
| **G02: Só o valioso** | Métricas são estritamente operacionais: Tarefas ativas, Testes rodados, Duração e Tokens consumidos. Zero gráficos de área decorativos sem eixo ou utilidade. |
| **G03: Pouco texto** | Títulos concisos (`Runs`, `DAG de Tarefas`, `Workspaces`). Rótulos objetivos sem subtítulos redundantes. |
| **G05: Claro por padrão com cor própria** | Base clara e arejada com contraste testado (mínimo 4.5:1), com neutros sutilmente tingidos pelo matiz da marca, sem cinza puro opaco. |
| **G06: Sem cara de IA** | Banimento da paleta padrão Tailwind índigo (`#6366f1`), gradientes roxos, estrelinhas de faísca (✨) e robôs. O símbolo representa múltiplos nós e fluxo de execução com engenharia gráfica precisa. |
| **G17: Logo respira livre** | O logotipo do Hydra vive em vetor puro sobre o fundo, sem ser enjaulado dentro de quadrados ou círculos coloridos. |
| **G23: Acessibilidade de alta precisão** | Rótulos tabulares (`tabular-nums`) para números e hashes, suporte nativo a alto contraste e navegação 100% por teclado (`Tab`, atalhos de terminal). |
