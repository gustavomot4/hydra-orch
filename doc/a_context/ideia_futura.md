# ideia_futura — Catálogo de Ideias Futuras e Expansões de Longo Prazo (Parking Lot)

**Identificador Formal:** `ideia_futura.md`
**Caminho Canônico:** `doc/a_context/ideia_futura.md`
**Versão:** `v01_00_0000`
**Status:** `PARKING LOT / FORA DO ESCOPO NORMATIVO ATUAL`
**Autoridade:** Decisão arquitetural de enxugamento de escopo do `hydra-orch` para proteger o foco nos marcos M1 a M4 (V0 a V4).
**Escopo:** Registro preservado das propostas exploratórias de Horizontes Futuros (antigos V5 e V6): comandos estendidos de sessão, geração multimodal (imagem, áudio, vídeo), conversação por voz full-duplex, automação de desktop/navegador (Computer Use), RAG corporativo híbrido, conectores externos de tickets (Jira/Kanbanize) e Local LLM Foundry (quantização GGUF e LoRA).

---

## 1. Purpose (Propósito)

Preservar de forma estruturada e auditável todas as ideias de expansão de longo prazo concebidas durante a fase exploratória do `hydra-orch`, mantendo-as **estritamente fora do backlog ativo (T01–T28)** e dos PRDs normativos (`doc/b_spc/prd_funcional.md` e `doc/b_spc/prd_tecnico.md`) até que o núcleo de engenharia de software autônoma (Horizontes V0 a V4 / Marcos M1 a M4) esteja 100% implementado, testado e certificado em produção.

---

## 2. Why (Justificativa do Isolamento em Parking Lot)

A revisão cética de arquitetura identificou que misturar geração de vídeo/música, chat de voz full-duplex (< 500 ms TTFT), automação de mouse/teclado e quantização de modelos GGUF com o núcleo de orquestração de Git Worktrees gerava três riscos graves:
1. **Diluição de Foco (Scope Creep):** 16 tarefas periféricas (antigas T29–T44, somando 105 Story Points — 34% do esforço total do projeto) competiam por atenção documental e arquitetural antes mesmo de o primeiro agente alterar um arquivo real com validação `pytest` (Marco M1).
2. **Acoplamento de Dependências Pesadas:** Bibliotecas como `faster-whisper`, `sounddevice`, `pyautogui`, `llama-cpp-python` e `sqlite-vss` introduzem dependências nativas de sistema operacional, áudio e GPU que dificultam a portabilidade e os testes herméticos do control plane.
3. **Poluição de Contratos Core:** Entidades de mídia, voz e quantização poluíam o esquema relacional do banco de checkpoints e os diagramas do control plane.

Ao isolar essas capacidades neste documento canônico (`doc/a_context/ideia_futura.md`), nenhuma ideia é perdida, mas o repositório permanece enxuto, coerente e 100% focado em **Engenharia de Software Autônoma Verificável**.

---

## 3. Catálogo de Ideias Futuras Preservadas (Horizontes Pós-M4)

### 3.1. Ideia F01 — Comandos Canônicos de Sessão e Controle de Esforço (Antigo RF31 / RT31 / T29)
- **Conceito:** Suporte a comandos operacionais rápidos via CLI/UI: `/compact` (sumarização de contexto preservando decisões ativas), `/plan` (modo de planejamento estritamente read-only sem mutação no filesystem), `/build` (conversão do plano aprovado em `RunSpec` executável) e parâmetro `reasoning_effort` (`low`, `medium`, `high`, `max`) repassado via options para provedores compatíveis.
- **Critério para Promoção:** Após estabilização do `session_service.py` (T14) no Marco M3.

### 3.2. Ideia F02 — Geração e Gestão de Artefatos Multimodais (Antigo RF32 / RT32 / RNF13 / T30)
- **Conceito:** Orquestrar jobs assíncronos de geração de Imagem (FLUX, Stable Diffusion), Áudio (MusicGen, AudioCraft) e Vídeo (CogVideo, Sora API) desacoplados do stream de código. Persistência em `.orchestrator/artifact/` com verificação SHA-256, validação de MIME type e metadados estruturados (prompt, seed, dimensões, modelo).
- **Critério para Promoção:** Apenas se houver demanda comprovada para geração automatizada de assets visuais/sonoros dentro de projetos de front-end ou jogos.

### 3.3. Ideia F03 — Inspetor Dinâmico e Catálogo Avançado de MCPs (Antigo RF33 / RT33 / T31)
- **Conceito:** Evoluir o suporte básico a MCP (já coberto em T19 no V4) para um painel completo de inspeção dinâmica em tempo real (`tools/list`) via stdio/SSE/HTTP, permitindo ativar/desativar ferramentas individuais por tarefa e invalidar automaticamente ferramentas cujo schema JSON seja modificado em runtime (`untrusted`).
- **Critério para Promoção:** Após entrega de T19 (Skills, MCPs e `SecretRef`) no Marco M4.

### 3.4. Ideia F04 — RAG Corporativo e Pessoal Híbrido (Antigo RF34 / RT34 / RNF14 / T32–T34)
- **Conceito:** Base de conhecimento multi-coleção com ingestão sanitizada (via `Redactor`) de PDF, Markdown e código-fonte. Armazenamento físico isolado em `.orchestrator/knowledge/knowledge.db` (jamais misturado ao banco de checkpoints técnicos), combinando busca vetorial densa (cosseno) + busca lexical esparsa (SQLite FTS5 BM25) fundidas por Reciprocal Rank Fusion (RRF), respeitando um teto rígido de tokens (`rag_token_budget`) e tratando todo conteúdo recuperado como dado não confiável (prevenção de prompt injection).
- **Critério para Promoção:** Após consolidação da memória consentida (T17) no Marco M4.

### 3.5. Ideia F05 — Conectores Bidirecionais de Issue Trackers: Jira, Kanbanize, GitHub e GitLab (Antigo RF35 / RT35 / T35–T36)
- **Conceito:** Interface `TicketProvider` que converte cards/issues em `RunSpec` e sincroniza transições de estado guiadas por eventos do Hydra (ex.: `run.started` $\rightarrow$ "In Progress", `task.ready_for_review` $\rightarrow$ "In Review", anexando links de PR e resumo de checks). O banco local do Hydra permanece como única autoridade da verdade (falhas de rede na API do Jira/Kanbanize nunca bloqueiam a execução local).
- **Critério para Promoção:** Após conclusão do empacotamento automático de PR (`PRPackager`, T28) no Marco M4.

### 3.6. Ideia F06 — Conversação por Voz Full-Duplex com Barge-In (Antigo RF36 / RT36 / RNF11 / T37–T38)
- **Conceito:** Diálogo bidirecional por áudio via WebSocket streaming (chunks PCM/Opus) integrando transcrição local/API (STT Whisper), síntese de voz (TTS Kokoro/ElevenLabs) e detecção de atividade de voz (VAD) para interrupção imediata (*barge-in*) com latência TTFT $< 500\text{ ms}$. Regra de segurança estrita: o canal de voz é exclusivamente informativo e conversacional, nunca podendo autorizar merges, deleções ou aprovações HITL destrutivas sem confirmação visual autenticada.
- **Critério para Promoção:** Projeto independente ou plugin opcional de interface humana após V4.

### 3.7. Ideia F07 — Computer Use e Automação de Desktop/Browser com Safety Governor (Antigo RF37 / RT37 / RNF12 / T39–T41)
- **Conceito:** Automação de navegador (Playwright isolado por workspace) e desktop OS (captura de screenshots, coordenadas de mouse e teclado) governada por um `ComputerUseGovernor`. Toda ação de efeito colateral (cliques, preenchimento de formulários, navegação fora da allowlist) exige interceptação HITL (`task.needs_approval`) com screenshot anotado e token assinado com expiração de 60 segundos.
- **Critério para Promoção:** Quando houver necessidade de testes E2E visuais autônomos após estabilização do HITL (T26).

### 3.8. Ideia F08 — Hub e Foundry de LLMs Locais: Quantização GGUF e Modelfiles (Antigo RF38 / RT38 / RNF15 / T42–T44)
- **Conceito:** Catálogo unificado de instâncias locais (Ollama, LM Studio, vLLM, `llama.cpp`) com monitoramento de VRAM/RAM, download direto do Hugging Face com validação SHA-256, pipeline de conversão e quantização para formato GGUF (`Q4_K_M`, `Q8_0`) executado em subprocesso isolado com semáforo de concorrência máxima igual a 1, além de construtor interativo de `Modelfile` e anexação de adaptadores LoRA.
- **Critério para Promoção:** Como ferramenta utilitária complementar após o roteamento adaptativo local/SSH (T16 e T22) estar maduro.

---

## 4. Regras de Governança do Parking Lot

1. **Proibição de Acoplamento Precoce:** Nenhum módulo de `src/hydra_orch/` deve importar bibliotecas ou declarar schemas referentes às ideias F01–F08 durante a implementação dos Marcos M1 a M4.
2. **Rito de Reativação:** Para promover qualquer item deste documento ao escopo ativo, o Marco M4 (Gate G-M4) deve estar formalmente concluído e uma nova especificação individual em `doc/b_spc/` deve ser aprovada seguindo o padrão DBC-9.
