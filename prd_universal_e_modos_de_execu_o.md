# PRD: Arquitetura Universal e Modos de Execução

O Gemini Pro pode sim ser utilizado como aplicativo local e controlado da mesma forma que os demais, sem ficar restrito a uma aba comum de navegador. Existem três formas diretas de integrá-lo como interface na sua máquina:

* **App Desktop via PWA/Chromium (`--app`):** Ao instalar o Gemini como aplicativo (ou lançá-lo via binário do Chrome/Edge/Brave com `--app=https://gemini.google.com --remote-debugging-port=9224`), ele roda em uma janela dedicada idêntica ao app do Claude e do ChatGPT (que também usam Chromium/Electron por baixo), expondo a mesma árvore DOM para o seu orquestrador.
* **Google Antigravity e Gemini CLI:** O próprio Antigravity já é uma interface desktop agêntica nativa onde os modelos Gemini Pro operam diretamente sobre o código. Além disso, o Gemini CLI permite enviar prompts direto pelo terminal usando sua conta Google autenticada.
* **Google AI Studio (App Dedicado):** Também pode ser aberto como janela isolada via CDP, dando acesso direto às versões específicas do Gemini Pro com controle de temperatura e instruções de sistema.

## 1. Arquitetura Universal de Provedores (Plug-and-Play)

Para que o seu orquestrador não fique preso a três ferramentas fixas, ele deve usar o padrão **Universal Provider Adapter**. Cada IA ou ferramenta que o usuário tiver disponível entra no arquivo `config.yaml` através de um entre quatro conectores padronizados:

| Tipo de Conector | Ferramentas Suportadas | Como o Orquestrador Controla |
| :--- | :--- | :--- |
| **1. Conector UI / CDP** | Claude (Pro/Free), ChatGPT (Plus/Free), Gemini (Pro/Free), DeepSeek Web | Conecta via porta de depuração (`localhost:922X`), envia prompts em paralelo por abas/janelas e monitora o streaming em tempo real. |
| **2. Conector de IDE Agêntica** | Google Antigravity, Cursor, Windsurf | Dispara tarefas via CLI interna, extensões ponte (bridge) no VS Code/fork ou automação de janela focada em workspaces isolados. |
| **3. Conector de API / Gateway** | OpenRouter, DeepSeek API, Groq, Anthropic/OpenAI API | Requisições HTTP REST assíncronas diretas (usado apenas se o usuário quiser cadastrar chaves pagas ou modelos gratuitos do OpenRouter). |
| **4. Conector Local & Remoto (SSH)** | Ollama, LM Studio, vLLM (no próprio PC ou em outro PC forte via SSH) | Conecta em `localhost:11434` ou abre túnel automático `ssh -N -L 11435:localhost:11434 user@pc-forte` para usar a GPU remota. |

## 2. Os 3 Modos de Execução Configuráveis pelo Usuário

No painel ou arquivo de configuração do orquestrador, o usuário escolhe como deseja que as respostas e tarefas sejam geradas:

* **Modo 1 — Enxame Paralelo (Multi-Session Swarm):** O orquestrador recebe um pedido grande, fatia o projeto em frentes independentes de acordo com o tamanho e dificuldade de cada parte e abre várias sessões simultâneas (Claude, GPT, Gemini, Antigravity, DeepSeek, PC via SSH trabalhando ao mesmo tempo).
* **Modo 2 — Esteira Sequencial com Failover Instantâneo (Relay Mode):** Uma tarefa passa de mão em mão em etapas (ex: Modelo A planeja → Modelo B codifica → Modelo C testa). Se os tokens de um modelo acabarem no meio da geração, outra IA assume do exato ponto de corte imediatamente (*Hot-Handoff*).
* **Modo 3 — Foco Persistente com Auto-Resume (Estilo Nativo Claude):** O usuário fixa sua IA preferida para a tarefa. Se a cota de 5 horas do Claude Pro acabar no meio de um arquivo, o orquestrador salva o código parcial no buffer, lê o horário de retorno na interface, hiberna a sessão e retoma a geração sozinho assim que os tokens voltam.

## 3. Como Funciona a Execução em Várias Sessões Simultâneas (Exemplo: "App de Barbearia")

Quando você envia um único prompt macro — *"Construa uma aplicação completa de uma barbearia com agendamento, painel de barbeiros e pagamento"* —, rodar 4 ou 5 IAs ao mesmo tempo exige evitar que uma sobrescreva o código da outra.

O orquestrador resolve isso em **3 fases automatizadas** usando **Contratos de Interface** e **Git Worktrees** (pastas/branches paralelas do mesmo repositório):

### Fase A: Decomposição e Contrato Único (Duração: ~30 segundos)
Antes de abrir as sessões paralelas, o **Analisador de Complexidade** do orquestrador usa um modelo arquiteto para criar um JSON de **Contrato Base** (quais rotas de API vão existir, nomes das tabelas do banco e estrutura de pastas) e classifica as sub-tarefas por peso:
* **Dificuldade Alta / Crítica** → Alocada para Claude Pro, Antigravity ou Cursor.
* **Dificuldade Média / Volume de Código** → Alocada para ChatGPT Plus ou DeepSeek.
* **Contexto Amplo / Documentação e Integração** → Alocada para Gemini Pro.
* **Tarefas Repetitivas / Boilerplate e Testes** → Alocada para LLM Local via SSH ou planos Free.

### Fase B: Disparo das Sessões Paralelas Simultâneas
Com o contrato travado, o orquestrador abre 4 a 5 sessões ao mesmo tempo, cada uma trabalhando em seu módulo isolado:
1. **Sessão 1 (Claude Pro / Antigravity) — Arquitetura e Core Backend:** Cria a lógica complexa de conflito de horários na agenda dos barbeiros e regras de comissão.
2. **Sessão 2 (ChatGPT Plus / Cursor) — Frontend e UI:** Constrói em paralelo as telas em React/Next.js (calendário de agendamento do cliente e dashboard administrativo) seguindo o Contrato Base da Fase A.
3. **Sessão 3 (DeepSeek / PC Forte via SSH) — Banco de Dados e Testes:** Escreve os schemas Prisma/SQL, cria dados falsos (*seeds*) para testar a barbearia e gera os testes unitários.
4. **Sessão 4 (Gemini Pro) — Documentação e Revisão de Contexto:** Lê continuamente os arquivos gerados pelas Sessões 1, 2 e 3, mantendo a documentação técnica (`README.md`, Swagger/OpenAPI) atualizada e apontando divergências de variáveis entre o Backend e o Frontend.

### Fase C: Sincronização e Merge Automático
À medida que cada sessão termina sua frente, o orquestrador une os arquivos, roda o comando de build/teste no terminal local e, se houver algum erro de integração entre o que o GPT fez no Front e o que o Claude fez no Back, dispara uma sessão rápida de correção automática.

## 4. Especificação Técnica dos Conectores (Universal Provider Adapter)

Para garantir que o **hydra-orch** consiga interagir com qualquer ferramenta sem acoplamento rígido, cada driver implementa uma interface padrão baseada em quatro métodos fundamentais: `initialize()`, `send_prompt()`, `check_token_limit()` e `extract_response()`.

### 4.1. Conector UI / CDP (Chrome DevTools Protocol)
Utilizado para controlar instâncias locais dos aplicativos desktop (Claude, ChatGPT, Gemini, DeepSeek Web) executados com portas de depuração abertas.
* **Funcionamento:** O orquestrador conecta via WebSocket local (`ws://127.0.0.1:922X/devtools/browser`) utilizando **Playwright Async**.
* **Manipulação de DOM:** O driver injeta texto no elemento textarea ativo (`#prompt-textarea` ou equivalentes) e dispara o evento de envio sem roubar o foco do sistema operacional.
* **Monitoramento de Stream:** Verifica a remoção do botão de interrupção (*Stop Generation*) e a exibição do botão de cópia para garantir que a resposta foi totalmente renderizada.

### 4.2. Conector de IDE Agêntica
Responsável por interagir com ferramentas de desenvolvimento como **Google Antigravity**, **Cursor** e **Windsurf**.
* **Funcionamento:** Executa comandos via interface de linha de comando (`CLI`) integrada ou gerencia sub-processos em diretórios de workspace isolados (`.hydra/workspaces/`).
* **Sincronização:** Permite que o agente edite diretamente arquivos locais enquanto o orquestrador monitora as alterações via git status em tempo real.

### 4.3. Conector de API / Gateway
Canal padrão para serviços baseados em HTTP REST e Server-Sent Events (SSE).
* **Ferramentas:** OpenRouter, DeepSeek API, Groq, Anthropic API, OpenAI API.
* **Uso:** Utilizado quando o usuário opta por consumir créditos de API para tarefas rápidas de suporte ou quando prefere modelos leves sem sobrecarregar as interfaces visuais.

### 4.4. Conector Local & Remoto (SSH)
Gerencia a computação local ou distribuída na rede doméstica.
* **Funcionamento:** Mantém um túnel SSH persistente (`autossh`) direcionando portas de servidores de inferência como **Ollama** ou **vLLM** (`localhost:11434` no PC remoto para `localhost:11435` na máquina de trabalho).
* **Fallback Automático:** Caso a latência da rede exceda $500\text{ ms}$ ou o túnel caia, o tráfego é redirecionado instantaneamente para os adaptadores de nuvem ou IA local primária.

## 5. Mecanismo de Resiliência: Checkpointing e Auto-Resume

Para evitar qualquer perda de progresso durante o desenvolvimento de software, o orquestrador gerencia um banco de dados local em **SQLite** (`.hydra/state.db`) que armazena o histórico completo de cada sessão paralela.

### 5.1. O Buffer de Checkpoint (Stream Checkpointer)
* A cada bloco de 5 tokens gerados por qualquer LLM (seja via UI, API ou Local), o estado atual do arquivo ou resposta é gravado no buffer local.
* Se ocorrer uma queda abrupta de conexão, interrupção de rede ou esgotamento de cota de tokens (como o limite de 5 horas do Claude Pro), o sistema impede a perda do código gerado.

### 5.2. Estratégias de Recuperação Configuráveis
O comportamento do orquestrador após uma interrupção de cota depende do modo escolhido pelo usuário:
1. **Espera Ativa (Auto-Resume):** O driver lê o temporizador exibido na interface gráfica do app (ex: *"Reseta em 2h 15m"*), entra em modo de repouso e, no exato segundo da liberação, dispara a continuação do prompt enviando o último trecho salvo como âncora.
2. **Failover Instantâneo (Hot-Handoff):** O sistema abandona a sessão atual, empacota o código parcial gerado até o momento do corte e o envia imediatamente para o próximo provedor na fila (ex: ChatGPT Plus ou DeepSeek) para finalizar o módulo sem atraso.

## 6. Fluxo de Trabalho do Servidor Compatível com OpenAI

O **hydra-orch** expõe um servidor local FastAPI em `http://localhost:8000/v1/chat/completions`, permitindo integração imediata com ferramentas como **Cline**, **Aider** e **OpenCode**.

```
[Agente SWE: Cline / Aider]
           │
           ▼ (POST /v1/chat/completions)
[Servidor FastAPI Local (:8000)]
           │
           ├─> Analisa complexidade e tamanho da tarefa
           ├─> Aplica regras do config.yaml (Modo 1, 2 ou 3)
           └─> Despacha para o Conector adequado (CDP, IDAs, API ou SSH)
```

Quando o agente de código envia uma requisição de completion, o servidor intercepta o payload, avalia a complexidade utilizando as regras definidas no arquivo de configuração e direciona a requisição para o adaptador correspondente, retornando a resposta formatada no padrão exigido pelo ecossistema OpenAI.