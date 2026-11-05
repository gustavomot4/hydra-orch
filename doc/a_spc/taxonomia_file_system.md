# taxonomia_file_system — Taxonomia Oficial do File System do hydra-orch

**Identificador Formal:** `taxonomia_file_system.md`  
**Caminho Canônico:** `doc/a_spc/taxonomia_file_system.md`  
**Versão:** `v01_00_0000`  
**Status:** `APROVADO / NORMATIVO`  
**Autoridade:** Síntese normativa baseada nos padrões de governança do `hydra-orch` (`AGENTS.md`, `doc/a_spc/CONTEXTO-ORQUESTRACAO.md` e diretrizes de arquitetura do projeto).  
**Escopo:** Todo o repositório `hydra-orch` (código-fonte, testes, documentação, workspaces e artefatos de configuração).

---

## 1. Design by Contract (DBC-9)

### 1.1. Purpose (Propósito)
Estabelecer uma taxonomia de file system determinística, unificada e canônica para o repositório `hydra-orch`, eliminando ambiguidades estruturais, retrabalho de refatoração, bugs de importação e desperdício de tokens de contexto para desenvolvedores humanos e agentes LLM autônomos.

### 1.2. Why (Justificativa)
Modelos de linguagem operam sob janelas de contexto restritas e custosas. Quando agentes de software (como Antigravity, Cursor, Claude Code, Gemini CLI ou workers de swarm) exploram um repositório com árvores profundas, alternância caótica entre singular e plural (`docs/` vs `doc/`, `models/` vs `model.py`, `adapters/` vs `adapter/`) ou raiz poluída com rascunhos, dezenas de milhares de tokens são consumidos em varreduras cegas de diretórios. A padronização estrita no singular, a ordenação alfabética por prefixos de leitura (`a_...`, `b_...`) e a limpeza absoluta da raiz tornam o repositório previsível em $O(1)$ para agentes e humanos.

### 1.3. Contract (Contrato Estrutural)
1. **Nomenclatura no Singular:** Toda pasta e arquivo controlado pela equipe deve estar rigorosamente no singular, exceto pela lista exaustiva de exceções técnicas de ecossistema.
2. **Raiz Limpa:** Nenhum arquivo temporário, PRD solto, log, dump de prompt ou script efêmero é permitido na raiz. A raiz contém exclusivamente manifestos de empacotamento, configurações globais e diretrizes de agentes.
3. **Fluxo Ordenado por Prefixos:** Diretórios de documentação e workspace utilizam prefixos sequenciais (`a_...`, `b_...`) que refletem a progressão cognitiva de leitura.
4. **Desacoplamento de Execução:** Os prefixos sequenciais orientam a navegação e a leitura humana/LLM; as dependências de execução do sistema em runtime permanecem governadas exclusivamente por contratos explícitos e grafos de tarefas.
5. **Preservação de Packaging Python:** A estrutura do pacote `src/hydra_orch` e da suíte `tests/` mantém compatibilidade integral com Hatchling (PEP 517/621) e pytest.

### 1.4. Preconditions (Pré-condições)
- O repositório possui Git inicializado com upstream configurado e checkout limpo antes de qualquer reestruturação física.
- A suíte de testes existente (`pytest tests`) executa com 100% de sucesso no ambiente de referência antes de qualquer movimentação.
- O mapeamento atômico de imports antigos (`hydra_orch.models` $\rightarrow$ `hydra_orch.model`, `hydra_orch.adapters` $\rightarrow$ `hydra_orch.adapter`) está pronto para execução coordenada.

### 1.5. Postconditions (Pós-condições)
- A pasta legada `docs/` é substituída por `doc/`, subdividida em `doc/a_spc/` e `doc/b_manual/`.
- Todos os PRDs soltos na raiz são transferidos e normalizados para `doc/a_spc/`.
- O workspace operacional `ws/` está criado com `ws/a_input/` (versionado) e `ws/b_output/` (ignorado, salvo `.gitkeep` e `README.md`).
- A pasta interna `src/hydra_orch/adapters/` é renomeada para `src/hydra_orch/adapter/`.
- O módulo interno `src/hydra_orch/models.py` é renomeado para `src/hydra_orch/model.py`.
- O caminho de runtime de worktrees do swarm é padronizado em `.orchestrator/worktree/`.
- Todos os imports, referências em arquivos de governança (`AGENTS.md`, `README.md`, `.windsurf/rules/project.md`, `.github/copilot-instructions.md`) e testes automatizados estão atualizados e passam com 100% de aprovação.

### 1.6. Invariants (Invariantes Arquiteturais)
- **Nenhum arquivo sem dono:** Todo arquivo reside em sua subpasta designada pela taxonomia.
- **Invariância Temporal em Nomes:** Nomes de arquivos não possuem timestamps ou versões no nome; o histórico cronológico de um artefato pertence unicamente ao Git.
- **Isolamento de Runtime:** O diretório `.orchestrator/` e o workspace `ws/b_output/` nunca persistem lixo de execução no controle de versão.
- **Singularidade Absoluta:** Nenhuma pasta nova controlada pelo time pode ser criada com sufixo ou semântica no plural.

### 1.7. Failure Modes (Modos de Falha e Anti-patterns)
- **Falha FM-01 (Pluralização Espúria):** Criar pastas como `docs`, `scripts`, `models`, `templates`, `utils`, `helpers`. **Mitigação:** Rejeição imediata em revisão estática e aplicação da tabela de conversão para singular.
- **Falha FM-02 (Poluição da Raiz):** Gravar arquivos `.md` soltos, scripts de teste pontuais (`test_quick.py`) ou arquivos de dump na raiz. **Mitigação:** Alocação estrita em `ws/a_input/`, `doc/a_spc/` ou `tests/`.
- **Falha FM-03 (Quebra de CI por Renomeação Cega):** Renomear pastas reservadas por ferramentas (`.github/workflows` para `.github/workflow`). **Mitigação:** Consulta prévia à tabela de exceções técnicas obrigatórias.
- **Falha FM-04 (Acoplamento de Prefixo ao Runtime):** Supor que o módulo em `a_...` deva necessariamente rodar antes do módulo em `b_...` em tempo de execução. **Mitigação:** O catálogo e grafo de execução do orchestrator mandam na execução; prefixos mandam na leitura.
- **Falha FM-05 (Import Broken pós-Reorganização):** Renomear subpacotes Python sem atualizar todos os arquivos chamadores e a suíte de testes. **Mitigação:** Execução de `pytest` e busca global por padrões de import antigos antes de qualquer commit.

### 1.8. How (Como Aplicar e Manter)
1. **Auditoria de Entrada:** Antes de adicionar qualquer pasta ou arquivo, consulte a tabela de taxonomia oficial (§ 4) e a tabela de termos singulares (§ 3).
2. **Criação de Documentos:** Documentos de especificação e arquitetura são criados em `doc/a_spc/` utilizando nomenclatura estritamente no singular, formato snake_case em minúsculas e sem prefixos de times externos (ex.: `prd_universal_modo_execucao.md`, `prd_hydra_orch_final.md`, `taxonomia_file_system.md`). Manuais e tutoriais operacionais vão para `doc/b_manual/`.
3. **Troca de Contexto Operacional:** Entradas versionáveis de tarefas para agentes e orquestradores são depositadas em `ws/a_input/`; saídas locais de execução ficam confinadas em `ws/b_output/`.
4. **Refatoração Contínua:** Ao detectar qualquer termo plural em código, configuração ou pasta, o agente responsável deve emitir a correção para o formato singular compatível.

### 1.9. Examples (Exemplos Canônicos)
- **Incorreto:** `docs/specifications/auth_specs_2026.md` $\rightarrow$ **Correto:** `doc/a_spc/auth_spec.md`
- **Incorreto:** `src/hydra_orch/adapters/ui_cdp.py` $\rightarrow$ **Correto:** `src/hydra_orch/adapter/ui_cdp.py`
- **Incorreto:** `src/hydra_orch/models.py` $\rightarrow$ **Correto:** `src/hydra_orch/model.py`
- **Incorreto:** `.orchestrator/worktrees/task_1/` $\rightarrow$ **Correto:** `.orchestrator/worktree/task_1/`
- **Incorreto:** `tests_unit/` ou `testes/` $\rightarrow$ **Correto:** `tests/` (raiz canônica do ecossistema Python)
- **Incorreto:** `workspace/inputs/brief.json` $\rightarrow$ **Correto:** `ws/a_input/brief.json`

---

## 2. Objetivo e Princípios

### 2.1. Princípio da Previsibilidade Determinística para LLMs
Agentes autônomos tomam decisões baseadas na exploração estrutural do repositório. Em repositórios desorganizados, o agente gasta sucessivas chamadas de ferramentas (`list_dir`, `find_by_name`, `grep_search`) apenas para inferir onde estão arquivos básicos. A taxonomia unificada garante que qualquer agente que leia o arquivo `AGENTS.md` saiba, a priori, a localização exata de qualquer insumo ou saída.

### 2.2. Princípio da Raiz Limpa (Clean Root Policy)
A raiz de um repositório é o índice de primeira ordem do projeto. Uma raiz congestionada por documentos pontuais e artefatos de depuração:
- Polui o prompt de sistema do agente, que frequentemente carrega a listagem de arquivos da raiz.
- Aumenta a taxa de erro na identificação de arquivos de configuração canônicos.
- Confunde ferramentas automáticas de empacotamento e inspeção de segurança.

A raiz do `hydra-orch` contém exclusivamente os manifestos contratuais do projeto e as interfaces declarativas dos agentes.

### 2.3. Princípio da Economia de Tokens e Eficiência de Contexto
A estrutura física do repositório é projetada para minimizar o payload de tokens transmitido às APIs de LLMs:
- **Árvores rasas e ordenadas:** Pastas agrupadas por função cognitiva reduzem o tamanho das árvores retornadas por ferramentas de exploração.
- **Zero Duplicação Histórica:** Pastas de histórico local (como `z_history`, cópias antigas ou backups de rascunhos) são proibidas; o Git preserva o histórico de forma compacta e fora do contexto operacional.
- **Invariância de Nomes:** Eliminar timestamps dos nomes de arquivos impede o acúmulo de arquivos variantes (ex.: `spec_v1.md`, `spec_v2.md`, `spec_final.md`), que competem entre si no contexto do agente.

---

## 3. Diretriz de Nomenclatura no Singular

### 3.1. Regra Geral
**Toda e qualquer pasta e todo arquivo controlado pela equipe deve utilizar nomenclatura estritamente no singular.**  
Esta regra é de cumprimento compulsório e aplica-se a pacotes de código, módulos, pastas de documentação, catálogos, templates, scripts, modelos de dados e workspaces.

### 3.2. Tabela de Termos Plurais Proibidos e Formas no Singular

A tabela a seguir consolida os termos plurais proibidos e suas respectivas formas obrigatórias no singular para o ecossistema do `hydra-orch`. Qualquer termo listado na coluna "Termo Plural Proibido" deve ser convertido para a respectiva "Forma no Singular Obrigatória":

| # | Termo Plural Proibido | Forma no Singular Obrigatória | Contexto de Aplicação no Repositório |
|---|---|---|---|
| 1 | `docs` / `documentations` | `doc` | Pasta principal de documentação (`doc/`) |
| 2 | `adapters` | `adapter` | Subpacote de provedores (`src/hydra_orch/adapter/`) |
| 3 | `models` | `model` | Módulo de esquemas de dados (`src/hydra_orch/model.py`) |
| 4 | `worktrees` | `worktree` | Diretório de runtime de isolamento (`.orchestrator/worktree/`) |
| 5 | `scripts` | `script` | Scripts auxiliares de build, CI ou automação local |
| 6 | `templates` | `template` | Modelos de geração de arquivos ou contratos |
| 7 | `examples` | `example` | Exemplos de requisições, payloads ou código |
| 8 | `references` | `reference` | Materiais de consulta e especificações importadas |
| 9 | `briefs` | `brief` | Documentos de instruções de tarefas e missões |
| 10 | `assets` | `asset` | Recursos estáticos, ícones ou diagramas gerados |
| 11 | `controls` | `control` | Políticas de validação, limites de taxa e checagens |
| 12 | `boundaries` | `boundary` | Definições de limites de isolamento de tarefas |
| 13 | `patterns` | `pattern` | Padrões de arquitetura e expressões regulares |
| 14 | `migrations` | `migration` (ou `m_migrate`) | Scripts e esquemas de evolução de banco de dados |
| 15 | `diagnostics` | `diagnostic` | Rotinas de checagem de saúde e probes de rede |
| 16 | `secrets` | `secret` | Chaves e credenciais (sempre em arquivos ignorados) |
| 17 | `conventions` | `convention` | Regras de formatação e sintaxe |
| 18 | `operations` | `operation` | Procedimentos operacionais e rotinas de manutenção |
| 19 | `practices` | `practice` | Boas práticas recomendadas |
| 20 | `guidelines` | `guideline` | Diretrizes de arquitetura e engenharia |
| 21 | `agents` | `agent` | Subpastas ou módulos de agentes individuais |
| 22 | `applications` | `application` | Módulos de aplicação principal |
| 23 | `deliverables` | `deliverable` | Artefatos entregáveis e produtos de execução |
| 24 | `microservices` | `microservice` | Módulos de microsserviços ou conectores desacoplados |
| 25 | `rules` | `rule` | Regras de governança ou catálogos de decisão |
| 26 | `sources` | `source` | Fontes originais de referência |
| 27 | `specialists` | `specialist` | Módulos de agentes especialistas do swarm |
| 28 | `standards` | `standard` | Padrões formais normativos |
| 29 | `events` | `event` | Eventos de mensageria ou registros de auditoria |
| 30 | `analytics` | `analysis` | Relatórios de análise e métricas |
| 31 | `skills` | `skill` | Habilidades e capacidades de agentes |
| 32 | `prompts` | `prompt` | Modelos de prompts de sistema estruturados |
| 33 | `workflows` | `workflow` | Definições de fluxo de trabalho (fora do .github) |
| 34 | `requirements` | `requirement` | Requisitos de produto e negócio |
| 35 | `instructions` | `instruction` | Instruções de execução e tarefas |
| 36 | `plugins` | `plugin` | Extensões e pontes externas |
| 37 | `activities` | `activity` | Diagramas de fluxo e passos de processo |
| 38 | `classes` | `class` | Diagramas de classes ou estruturas de objetos |
| 39 | `policies` | `policy` | Políticas de segurança e autorização |
| 40 | `files` | `file` | Manipulação de arquivos e utilitários de I/O |
| 41 | `users` | `user` | Gestão de perfis e identidades de usuários |
| 42 | `services` | `service` | Serviços de background e daemons |
| 43 | `tables` | `table` | Definições de tabelas de banco de dados |
| 44 | `logs` | `log` | Saídas de log e registros operacionais |
| 45 | `tests` (interno) | `test` | Módulos internos de teste (ex: `test_engine.py`) |
| 46 | `modules` | `module` | Módulos isolados de código |
| 47 | `components` | `component` | Componentes de interface ou subsistemas |
| 48 | `schemas` | `schema` | Esquemas JSON, Pydantic ou validações OpenAPI |
| 49 | `tools` | `tool` | Ferramentas CLI e utilitários auxiliares |
| 50 | `resources` | `resource` | Recursos alocados de hardware ou conectividade |
| 51 | `images` | `image` | Imagens, capturas de tela e assets visuais |

### 3.3. Exceções Técnicas Justificadas

Exceções à regra do singular são restritas e autorizadas exclusivamente quando a renomeação quebrar contratos externos de ferramentas, runners de CI/CD ou convenções inegociáveis de plataformas.

1. **`.github/workflows`:** O runner do GitHub Actions exige que arquivos YAML de workflow estejam localizados exatamente sob `.github/workflows/`. Qualquer alteração causará o cancelamento imediato de toda a integração contínua.
2. **`.github/skills` e `.github/prompts`:** Contratos específicos de descoberta de extensões e symlinks mantidos para compatibilidade com ecossistemas Copilot/Codex.
3. **`AGENTS.md`:** Nome de arquivo contratual estabelecido pela governança do projeto e reconhecido por ecossistemas multiagente como o ponto único de entrada de políticas.
4. **`requirements.txt`:** Arquivo canônico do ecossistema Python reconhecido por instaladores e contêineres Docker legados.
5. **`.cursor/rules` e `.windsurf/rules`:** Diretórios canônicos exigidos pelas IDEs agênticas Cursor e Windsurf para descoberta de regras de projeto em tempo real.
6. **`tests/` (Raiz de Testes Python):** A pasta de testes no nível superior do repositório permanece `tests/` para assegurar descoberta automática transparente pelo `pytest` e compatibilidade com ferramentas padrão de empacotamento. Contudo, todos os subdiretórios e arquivos internos a ela devem ser singularizados conforme a regra.
7. **Siglas e Nomes Próprios Preservados:** Substantivos que terminam naturalmente com a letra 's' sem constituir pluralização de um artefato não sofrem alteração:
   - `DevOps`, `DevSecOps`
   - `Postgres`, `PostgreSQL`
   - `Kubernetes`
   - `MS` (Microserviço), `TS` (TypeScript), `WS` (Workspace)
8. **Campos Internos de Protocolos e APIs:** A regra de nomenclatura no singular aplica-se estritamente a nomes de pastas e arquivos no sistema de arquivos. Campos de protocolos JSON, especificações OpenAPI de terceiros, variáveis de bibliotecas externas e textos descritivos não são singularizados de forma artificial.

---

## 4. Ordenação por Prefixos Sequenciais (`a_...`, `b_...`, etc.)

### 4.1. Fundamentação Cognitiva
Sistemas operacionais e ferramentas de linha de comando (`ls`, `dir`, `list_dir`) exibem pastas em ordem alfabética por padrão. O uso de prefixos alfabéticos sequenciais (`a_`, `b_`, `c_`, etc.) introduz determinismo na sequência de descoberta e leitura de artefatos por agentes e desenvolvedores:
- Primeiro, consome-se a fundamentação conceitual e a especificação (`a_spc`).
- Em seguida, examina-se o guia prático e a operação (`b_manual`).
- No ciclo de trabalho, primeiro isola-se a entrada da missão (`a_input`), para somente então avaliar as saídas geradas (`b_output`).

### 4.2. Desacoplamento entre Ordem de Leitura e Grafo de Execução
**Regra Fundamental de Arquitetura:**  
A ordenação sequencial alfabética estabelece **apenas e tão-somente a ordem de leitura e exploração cognitiva**. Ela **NÃO** define nem restringe o grafo de execução em tempo de execução (runtime).

O orquestrador do `hydra-orch` (módulos `core/router.py`, `core/swarm.py` e catálogo de tarefas) executa etapas de acordo com um Grafo Acíclico Dirigido (DAG) governado por contratos de dependência explícitos (Design by Contract DBC-9). Dessa forma:
- O módulo `adapter/` pode ser instanciado antes ou depois de `core/`, dependendo da árvore de resolução de injeção de dependências do Python.
- Uma tarefa de swarm pode processar dados em paralelo sem respeitar a ordem alfabética dos módulos.
- Mantém-se o desacoplamento absoluto entre ergonomia de documentação/file system e flexibilidade de engenharia de software.

---

## 5. Estrutura Canônica de Pastas e Hierarquia Oficial do hydra-orch

A árvore canônica oficial do repositório `hydra-orch` é definida conforme a seguinte topologia:

```
hydra-orch/
│
├── .agents/                    # Metadados e sessões de agentes de trabalho (ignorado para código do produto)
│   └── teamwork/              # Coordenação interna de agentes (briefings, handoffs e despachos)
│
├── .cursor/                    # Configurações da IDE Cursor
│   └── rules/                 # Regras contextuais do Cursor (exceção técnica)
│       └── project.mdc        # Instruções de projeto do Cursor
│
├── .github/                    # Configurações do GitHub e automações
│   ├── copilot-instructions.md # Diretriz de integração com assistente Copilot
│   └── workflows/             # Ações e pipelines de CI/CD (planejado/exceção técnica)
│
├── .orchestrator/              # Configurações e checkpoints de runtime do orquestrador
│   ├── CONTRACT.md            # Contrato imutável de tarefas do swarm
│   ├── checkpoints.sqlite     # Banco de dados local de checkpoints e estados (runtime gerado/ignorado)
│   └── worktree/              # Diretório base das branches e worktrees do swarm (runtime gerado/ignorado)
│
├── .windsurf/                  # Configurações da IDE Windsurf
│   └── rules/                 # Regras contextuais do Windsurf (exceção técnica)
│       └── project.md         # Instruções de projeto do Windsurf
│
├── doc/                        # Documentação oficial do projeto (singular)
│   ├── README.md              # Guia e índice geral da documentação técnica
│   ├── a_spc/                 # Especificações formais, PRDs e padrões de governança
│   │   ├── CONTEXTO-ORQUESTRACAO.md               # Contexto arquitetural e achados de agentes
│   │   ├── prd_hydra_orch_final.md                # Visão geral e especificação consolidada do produto
│   │   ├── prd_universal_modo_execucao.md        # PRD dos modos swarm, relay e persistente (singular)
│   │   ├── README.md                              # Catálogo e índice de especificações técnicas
│   │   └── taxonomia_file_system.md              # Este documento oficial de taxonomia
│   └── b_manual/              # Manuais de operação, runbooks e guias do usuário
│       ├── .gitkeep           # Preserva o diretório no controle de versão
│       └── README.md          # Guia e índice de manuais operacionais
│
├── ws/                         # Workspace operacional de dados (singular)
│   ├── README.md              # Visão geral do workspace e isolamento de dados
│   ├── a_input/               # Entradas versionadas, briefs, requisitos e schemas de tarefas
│   │   ├── .gitkeep           # Preserva o diretório no controle de versão
│   │   └── README.md          # Diretrizes de submissão de entradas operacionais
│   └── b_output/              # Saídas de execução local, patches e relatórios (ignorado no Git)
│       ├── .gitkeep           # Preserva o diretório no controle de versão
│       └── README.md          # Diretrizes sobre ciclo de vida de saídas efêmeras
│
├── src/                        # Código-fonte oficial do pacote Python (PEP 517/621)
│   └── hydra_orch/            # Pacote principal distribuível
│       ├── __init__.py        # Exportações canônicas e versão do pacote
│       ├── cli.py             # Ponto de entrada da CLI (Typer)
│       ├── config.py          # Configurações e modelos Pydantic de setup
│       ├── model.py           # Modelos de dados e schemas de domínio (singular)
│       ├── server.py          # Servidor HTTP compatível com API OpenAI (FastAPI)
│       ├── adapter/           # Conectores padronizados para provedores (singular)
│       │   ├── __init__.py    # Registro de adaptadores
│       │   ├── api_gateway.py # Conector REST HTTP direto (OpenRouter, DeepSeek)
│       │   ├── base.py        # Interface base Universal Provider Adapter
│       │   ├── ide_bridge.py  # Conector para IDEs agênticas (Antigravity, Cursor)
│       │   ├── remote_local.py# Conector para modelos locais e túnel SSH (Ollama)
│       │   └── ui_cdp.py      # Conector de automação via CDP (Claude, ChatGPT, Gemini)
│       └── core/              # Núcleo do motor de orquestração
│           ├── __init__.py    # Inicialização do núcleo
│           ├── checkpointer.py# Persistência de checkpoints e retomada de estado
│           ├── router.py      # Roteador de modelos e gerenciador de fallback
│           ├── ssh_tunnel.py  # Gerenciador de túneis SSH automáticos
│           └── swarm.py       # Decompositor de tarefas e orquestrador de worktrees
│
├── tests/                      # Suíte de testes automatizados (pytest)
│   ├── test_checkpointer.py   # Testes unitários do mecanismo de checkpoint
│   ├── test_config.py         # Testes de carregamento de configuração
│   ├── test_model.py          # Testes de validação dos esquemas de dados de `model.py` (singular)
│   ├── test_router.py         # Testes do roteador inteligente e seleção de complexidade
│   └── test_server.py         # Testes de inicialização da API FastAPI e túnel SSH
│
├── .gitignore                  # Regras de exclusão do controle de versão
├── AGENTS.md                   # Diretrizes canônicas para agentes autônomos no repositório
├── CLAUDE.md                   # Ponto de entrada e regras para Claude Code
├── config.yaml                 # Configuração operacional padrão da instância do orquestrador
├── GEMINI.md                   # Ponto de entrada e regras para Gemini CLI
├── pyproject.toml              # Manifesto do projeto Python e configuração do Hatchling
└── README.md                   # Apresentação do produto, arquitetura e instruções gerais
```

### 5.1. Detalhamento dos Diretórios e Arquivos Canônicos

#### 5.1.1. Raiz do Repositório (`/`)
Apenas os seguintes 7 arquivos são permitidos na raiz do repositório:
1. `AGENTS.md`: Diretrizes e políticas de governança para qualquer agente atuando no repositório.
2. `CLAUDE.md`: Apontamento transparente para `AGENTS.md` para assistentes da família Claude.
3. `GEMINI.md`: Apontamento transparente para `AGENTS.md` para assistentes da família Gemini.
4. `README.md`: Visão geral do produto, instruções de instalação e início rápido.
5. `pyproject.toml`: Configuração formal do pacote Python, dependências e metadados de build (Hatchling).
6. `config.yaml`: Arquivo de configuração de runtime (portas, adaptadores, timeouts, worktrees).
7. `.gitignore`: Regras de exclusão Git (ambientes virtuais, caches Python, saídas locais).

*É estritamente vedada a presença de PRDs avulsos, rascunhos de chat, scripts temporários ou pastas de histórico na raiz.*

#### 5.1.2. Documentação (`doc/`)
Substitui a pasta plural `docs/`. Divide-se formalmente em:
- `doc/README.md`: Visão geral e guia de navegação da documentação técnica.
- `doc/a_spc/`: Especificações formais e normativas. Contém:
  - `taxonomia_file_system.md`: A presente especificação oficial de taxonomia.
  - `CONTEXTO-ORQUESTRACAO.md`: Registro da arquitetura de orquestração e achados comparativos de agentes.
  - `prd_universal_modo_execucao.md`: PRD consolidando a especificação técnica dos modos de execução (Swarm, Relay e Persistente) e dos adaptadores universais.
  - `prd_hydra_orch_final.md`: PRD consolidado descrevendo a visão completa do produto e integração com agentes SWE.
  - `README.md`: Catálogo e índice de especificações técnicas.
- `doc/b_manual/`: Manuais operacionais, procedimentos de deploy, runbooks de manutenção e guias de usuário.
  - `README.md`: Guia e índice de manuais operacionais.
  - `.gitkeep`: Marcador para versionamento da pasta.

#### 5.1.3. Workspace Operacional (`ws/`)
O workspace operacional provê uma fronteira estanque entre o código-fonte da aplicação e o tráfego de dados de trabalho:
- `ws/README.md`: Visão geral e política de governança do workspace.
- `ws/a_input/`: Entradas versionáveis. Concentra briefs de tarefas, esquemas contratuais de novos módulos a serem gerados, datasets sintéticos de referência e solicitações estruturadas. Contém `README.md` e `.gitkeep`.
- `ws/b_output/`: Saídas de execução local. Destinado a receber artefatos intermediários gerados por agentes ou execuções locais (patches `.diff`, relatórios sintéticos de inspeção, bundles locais de exportação). É integralmente ignorado no Git pelo `.gitignore`, com exceção de seu `README.md` e `.gitkeep`.

#### 5.1.4. Pacote Python (`src/hydra_orch/`)
O código-fonte segue integralmente as diretrizes do Hatchling e da PEP 621:
- `model.py`: Substitui o arquivo plural `models.py`. Contém todas as definições de classes Pydantic (`ChatMessage`, `ChatCompletionRequest`, `ChatCompletionResponse`, `ChatCompletionChunk`, etc.).
- `adapter/`: Substitui a pasta plural `adapters/`. Contém a implementação dos adaptadores universais (`base.py`, `api_gateway.py`, `ide_bridge.py`, `remote_local.py`, `ui_cdp.py`).
- `core/`: Contém os componentes centrais de roteamento, checkpoints, comunicação e coordenação de swarm.
- `cli.py`: Fornece a interface de linha de comando `hydra` via Typer.
- `config.py`: Parser e validador de configurações baseado no arquivo `config.yaml`.
- `server.py`: Servidor HTTP FastAPI que expõe os endpoints compatíveis com a API OpenAI.

#### 5.1.5. Suíte de Testes (`tests/`)
Mantém a raiz `tests/` para descoberta automática de testes via `pytest`. Os testes unitários e de integração são co-localizados (e não utilizam `__init__.py`, preservando o namespace do pacote):
- `test_checkpointer.py`: Validação de escrita e recuperação de checkpoints em banco SQLite.
- `test_config.py`: Validação de carregamento e valores padrão de `config.yaml`.
- `test_model.py`: Validação de serialização e parsing de schemas definidos em `model.py` (singularizado).
- `test_router.py`: Validação de lógica de seleção de adaptadores por faixa de complexidade e fallback.
- `test_server.py`: Validação de inicialização da API FastAPI, rotas HTTP e gerenciamento do túnel SSH.

#### 5.1.6. Runtime Swarm (`.orchestrator/`)
O diretório `.orchestrator/` armazena o contrato de execução e o estado das instâncias do swarm:
- `CONTRACT.md`: Contrato imutável de fatiamento de código para execução concorrente.
- `worktree/`: Substitui o caminho plural `.orchestrator/worktrees/`. Hospeda os checkouts temporários do Git associados a cada branch do swarm durante execuções paralelas.
- `checkpoints.sqlite`: Base de dados transacional para checkpoints (ignorado no Git).

---

## 6. Otimização de Tokens e Prevenção de Desvios (Anti-Drift)

Para prevenir o consumo descontrolado de tokens de contexto e garantir alinhamento contínuo entre agentes e desenvolvedores, são estabelecidas três regras invioláveis:

### 6.1. Proibição de Arquivos de Conversação Efêmeros
- É **terminantemente proibido** commitar arquivos do tipo `CHAT`, `PROMPT`, `RESULT`, transcrições de sessões ou logs brutos de bate-papo de assistentes no repositório.
- Perguntas, respostas de descoberta e justificativas devem ser sintetizadas diretamente em registros formais de decisão (como handoffs, documentação em `doc/a_spc/` ou mensagens de commit estruturadas).
- Arquivos de evidência de execução pertencem a branches isoladas ou relatórios sumarizados em `ws/b_output/`, nunca na raiz ou no código-fonte.

### 6.2. Invariância de Nomes de Arquivos (Proibição de Timestamps)
- Diretriz fundamental de governança do `hydra-orch` (`AGENTS.md` e taxonomia normativa): **nenhum arquivo de documentação, especificação ou código deve conter timestamps, datas ou sufixos incrementais em seu nome**.
- Exemplo Incorreto: `PRD_Swarm_20261105.md`, `taxonomia_v2_final.md`.
- Exemplo Correto: `taxonomia_file_system.md`, `prd_universal_modo_execucao.md`, `prd_hydra_orch_final.md`.
- **Justificativa:** Nomes mutáveis quebram referências cruzadas em Markdown, invalidam caches de LLM, obrigam buscas globais recorrentes e acumulam arquivos zumbis no repositório. A evolução cronológica de qualquer arquivo é controlada unicamente pelos metadados do Git.

### 6.3. Isolamento de Contexto e Escopo Cirúrgico
- Agentes autônomos **não devem** carregar o repositório inteiro em contexto para executar uma tarefa pontual.
- O contexto de trabalho de um agente deve ser delimitado cirurgicamente:
  1. Leitura de `AGENTS.md` para instruções de governança da sessão.
  2. Leitura da especificação correspondente em `doc/a_spc/`.
  3. Leitura dos insumos em `ws/a_input/`.
  4. Escrita exclusivamente nos arquivos de destino indicados pelo contrato.
- A exclusão permanente de diretórios legados como `z_history` assegura que nenhum agente processe código ou instruções depreciadas como se fossem diretrizes ativas.

---

## 7. Glossary e Acrônimos

A tabela a seguir consolida em ordem alfabética unificada todas as siglas, termos técnicos e conceitos utilizados na governança e na taxonomia do repositório:

| Termo / Sigla | Definição e Aplicação na Arquitetura |
|---|---|
| **AG** | Agent (Agente) — Repositório, unidade ou módulo de software agêntico autônomo baseado em LLM. |
| **Anti-Drift** | Conjunto de regras e práticas que impedem que agentes autônomos se desviem da arquitetura canônica e das regras de governança ao longo de iterações sucessivas. |
| **AP** | Application (Aplicação) — Produto ou aplicação completa que coordena múltiplos módulos e microsserviços. |
| **CDP** | Chrome DevTools Protocol — Protocolo de comunicação WebSocket utilizado para automatizar navegadores e aplicativos baseados em Chromium (Claude, ChatGPT, Gemini). |
| **Clean Root** | Política de governança que restringe os arquivos permitidos na raiz do repositório ao mínimo necessário para build e governança. |
| **DBC-9** | Design by Contract em 9 partes — Padrão de engenharia de software para especificações formais contendo: Purpose, Why, Contract, Preconditions, Postconditions, Invariants, Failure Modes, How e Examples. |
| **Failover** | Mecanismo automático de comutação que transfere a execução para um provedor alternativo quando o provedor primário atinge limite de cota ou erro. |
| **GAP** | Lacuna arquitetural ou técnica formalmente registrada como pendente de decisão ou especificação pelo usuário/líder. |
| **Hot-Handoff** | Transferência instantânea e contínua de contexto e estado de geração entre modelos distintos sem perda de progresso no arquivo. |
| **LLM** | Large Language Model — Modelo fundacional de linguagem utilizado como motor de inferência e raciocínio para geração de código e orquestração. |
| **MD** | Módulo interno da aplicação — Unidade funcional de software que vive no contexto interno da aplicação sem container independente dedicado. |
| **MK** | Mock — Serviço externo emulado ou dublê de teste para integrações de terceiros. |
| **MS** | Microservice (Microsserviço) — Unidade independente de serviço de backend com escopo de domínio focado e container próprio. |
| **PEP 517/621** | Padrões de empacotamento da linguagem Python que especificam o uso de `pyproject.toml` para metadados de projeto e backends de build modernos (como Hatchling). |
| **PRD** | Product Requirements Document — Documento formal que especifica os requisitos de negócio, funcionais e técnicos de um entregável. |
| **PRM** | Prompt — Arquivo de texto que encapsula instruções de sistema estruturadas para direcionar o comportamento de um modelo de linguagem. |
| **Relay Mode** | Modo de execução sequencial no qual tarefas passam de um modelo para outro em pipeline com tolerância a falhas. |
| **Single Source of Truth** | Princípio de engenharia segundo o qual cada dado, regra ou configuração possui um único local canônico de definição no sistema. |
| **SPC** | Specification (Especificação) — Documento técnico normativo vigente de uma unidade ou módulo do sistema. |
| **Swarm Mode** | Modo de execução concorrente no qual múltiplas instâncias de LLM operam em paralelo sobre worktrees isolados do Git sob um contrato imutável. |
| **TP** | Temporary (Serviço Temporário) — Módulo ou serviço em estágio transitório ou experimental antes de promoção a componente oficial. |
| **UI** | User Interface — Camada de interface gráfica e visual de interação com o usuário final. |
| **Universal Adapter** | Padrão arquitetural de conector plug-and-play que abstrai provedores heterogêneos sob uma interface comum. |
| **Worktree** | Recurso nativo do Git que permite vincular múltiplos diretórios de trabalho a um único repositório, viabilizando execução concorrente isolada. |
| **WS** | Workspace — Diretório operacional delimitado para intercâmbio de dados de entrada (`ws/a_input`) e saídas locais (`ws/b_output`). |
