# Documentação Técnica do hydra-orch

**Versão:** `v01_02_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`

Esta pasta reúne a documentação canônica do projeto **hydra-orch**, estruturada rigorosamente conforme as diretrizes de taxonomia oficial da equipe (`doc/a_context/taxonomia_file_system.md`), ordenação sequencial por prefixos cognitivos (`a_...`, `b_...`) e regra da singularidade absoluta.

---

## Fluxo Sequencial de Leitura e Ciclo de Vida da Engenharia

A organização segue ordem alfabética sequencial correspondente à progressão de leitura humana e consumo por agentes LLM:

| Prefixo | Diretório | Domínio Documental | Finalidade Principal | Status |
|---------|-----------|-------------------|----------------------|--------|
| `a_` | [`a_context/`](a_context/) | Contexto & Planejamento | Investigação Alethe, diagnóstico, plano mestre S00–S28, roadmap estratégico, backlog de tasks, taxonomia e visão | ✅ Completo |
| `b_` | [`b_spc/`](b_spc/) | Especificações & PRDs | PRD Funcional (RF01–38) e PRD Técnico (RT01–38, RNF01–15, Contratos, DDL) | ✅ Completo |
| `c_` | [`c_activity/`](c_activity/) | Atividades & Processos | Casos de uso UC01–UC10 com Mermaid TB/LR, DBC-9, Meta-JSON | ✅ Completo |
| `d_` | [`d_mer/`](d_mer/) | Dados & MER | Modelo Entidade-Relacionamento (núcleo + expansão), DDL SQLite, índices | ✅ Completo |
| `e_` | [`e_class/`](e_class/) | Classes & Tipagem | Diagramas de classes (núcleo + control plane), interfaces, serviços | ✅ Completo |
| `f_` | [`f_api/`](f_api/) | Interfaces & OpenAPI | OpenAPI 3.0 completo `/v1/control-plane/*` + `/v1/chat/completions` | ✅ Completo |
| `g_` | [`g_code/`](g_code/) | Código & Arquitetura | Stack tecnológica normativa (`stack.md`), decomposição de pacotes | ✅ Completo |
| `h_` | [`h_test/`](h_test/) | Testes & Qualidade | Matriz RF/RT→Testes, estratégia hermética, cobertura, security/a11y | ✅ Completo |
| `i_` | [`i_infra/`](i_infra/) | Infraestrutura & Deploy | SSH, OmniRoute, contêineres, sandboxing, certificação drivers | ✅ Completo |
| `j_` | [`j_manual/`](j_manual/) | Manuais & Operação | Instalação, config, CLI, UI, runbooks, disaster recovery, auditoria, a11y | ✅ Completo |

---

## Resumo dos Artefatos Principais

### Contexto e Planejamento (`a_context/`)
| Arquivo | Versão | Escopo |
|---------|--------|--------|
| [`roadmap.md`](a_context/roadmap.md) | `v01_00_0000` | Horizontes V0–V6, marcos M1–M4, subgates M4a/b/c, critérios DoR/DoD de marco e matriz de riscos |
| [`backlog.md`](a_context/backlog.md) | `v01_00_0000` | Catálogo unificado das 44 tasks (T01–T44), 309 SP (Fibonacci), 16 ondas e matriz anti-colisão |
| [`plano_desenvolvimento.md`](a_context/plano_desenvolvimento.md) | `v01_00_0000` | Diagnóstico de código, catálogo de gaps A01–A18 e sequência de specs S00–S28 |
| [`taxonomia_file_system.md`](a_context/taxonomia_file_system.md) | `v01_00_0000` | Norma arquitetural de singularidade estrita, prefixos e isolamento `.orchestrator/` |
| [`visao_produto.md`](a_context/visao_produto.md) | `v01_00_0000` | Visão estratégica original do produto (V5.0), modos Swarm/Relay/Persistente |
| [`CONTEXTO-ORQUESTRACAO.md`](a_context/CONTEXTO-ORQUESTRACAO.md) | `v01_00_0000` | Registro histórico de investigação do Alethe e arquitetura de comunicação entre agentes |

### Especificações Normativas (`b_spc/`)
| Arquivo | Versão | Escopo |
|---------|--------|--------|
| `prd_funcional.md` | `v01_02_0000` | RF01–RF38, UC01–UC10, RB01–RB28, proposta de valor |
| `prd_tecnico.md` | `v01_02_0000` | RT01–RT38, RNF01–RNF15, contratos de execução, DDL SQLite, T01–T44, S00–S28 |

### Casos de Uso (`c_activity/`)
| Arquivo | Fluxo | Requisitos |
|---------|-------|------------|
| `uc01_task_execution.md` | UC01 | RF01–RF08, RF15 / RT01–RT10, RT12 |
| `uc02_swarm_healing.md` | UC02 | RF03–RF06, RF09, RF12, RF15 / RT04–RT07, RT12 |
| `uc03_relay_persist.md` | UC03 | RF10, RF11, RF20, RF26, RF27 / RT08, RT09, RT16, RT18, RT26, RT27 |
| `uc04_cancel_preserve.md` | UC04 | RF04–RF06, RF15 / RT04–RT06, RT11 |
| `uc05_discovery_activation.md` | UC05 | RF17, RF22, RF24 / RT14, RT20, RT21, RT22 |

### Modelo de Dados (`d_mer/`)
- `mer.md` — Especificação DBC-9 completa (núcleo + expansão)
- `mer.mmd` — Diagrama Mermaid ER visual

### Diagramas de Classes (`e_class/`)
- `diagrama_classe.md` — Especificação DBC-9 (núcleo + expansão)
- `diagrama_classe.mmd` — Diagrama Mermaid class visual

### API (`f_api/`)
- `openapi.yaml` — OpenAPI 3.0 completo com todos endpoints núcleo + expansão

### Testes (`h_test/`)
- `README.md` — Matriz rastreabilidade 45+ requisitos, estratégia hermética, categorias TST_UNIT/INT/E2E/NEG/SEC/A11Y

### Infraestrutura (`i_infra/`)
- `README.md` — Topologia, SSH reverso, OmniRoute, Docker, sandboxing, certificação, multiplataforma

### Manuais (`j_manual/`)
- `README.md` — Índice 11 manuais: instalação, config, auth, SSH, CLI, UI, modos, runbooks, disaster recovery, auditoria, a11y

---

## Contadores Normativos Atuais

| Categoria | Range | Status |
|-----------|-------|--------|
| **RF** (Requisitos Funcionais) | RF01 – RF38 | Proposto |
| **RT** (Requisitos Técnicos) | RT01 – RT38 | Proposto |
| **RNF** (Requisitos Não-Funcionais) | RNF01 – RNF15 | Proposto |
| **UC** (Casos de Uso) | UC01 – UC10 | Documentado |
| **RB** (Regras de Negócio) | RB01 – RB28 | Definido |
| **T** (Tasks de Implementação) | T01 – T44 | Proposto |
| **S** (Etapas de Faseamento) | S00 – S28 | Planejado |
| **M** (Marcos / Slices) | M1 – M4 (V0 a V6) | Planejado |
| **SP** (Story Points Totais) | 309 SP (Fibonacci) | Estimado |
| **O** (Ondas de Execução) | Onda 1 a Onda 16 | Estruturado |

---

## Faseamento de Entregas (Resumo)

```text
V0 (Núcleo Verificável):      S00 → S01 → S02 → S03 → S04 → S05 → M1 (T01–T08)
V1 (Control Plane + HITL):    M1  → S10 (API) → S11 (UI) → T09, T26
V2 (Workspaces e Perfis):     S14 (T10, T11, T12, T13)
V3 (Coordenação, Rotas, Swarm): S06 → S07 → S08 → S15 (T14, T15, T16, T25)
Gate Segurança V4:            S16 (auth, secrets, consent, allowlists)
V4 (Memória, Discovery, Ext):  S16 → S17 (T17, T18, T19, T20, T27)
                              → S18 (T21, T22)
                              → S19 (T28: budget + packaging)
                              → S20 (T23, T24: CLI, CI, manuals)
V5 (Multimodal & Interação):  S21 (session commands: T29) → S22 (multimodal: T30)
                              → S26 (voice duplex: T37, T38) → S27 (computer use: T39, T40, T41)
V6 (Knowledge, Hub & Foundry): S23 (mcp control: T31) → S24 (rag knowledge: T32, T33, T34)
                              → S25 (issue trackers: T35, T36) → S28 (local foundry: T42, T43, T44)
```

**Regra:** Nenhuma etapa da expansão antecede conclusão do marco M1 (execução verificável local).

---

## Princípios de Governança

1. **Nenhuma capacidade anunciada sem gate concluído** — RF/RT propostos permanecem `NÃO IMPLEMENTADO` até testes passarem
2. **Documentação precede implementação** — Specs atualizadas antes do código
3. **Testes herméticos** — Zero dependências externas (contas, GPU, rede) na suíte offline
4. **Segurança por padrão** — Auth local, CORS estrito, redaction centralizada, tokens hasheados (PBKDF2/Argon2)
5. **Acessibilidade verificável** — WCAG AA checklist automatizado + manual
6. **Economia de tokens** — Singularidade, prefixos, raiz limpa, invariância temporal (sem timestamps em nomes)

---

## Convenção DBC-9 (Obrigatória em todos PRDs)

1. **Purpose** — Propósito
2. **Why** — Justificativa
3. **Contract** — Contrato formal (entradas, saídas, comportamento)
4. **Preconditions** — Pré-condições
5. **Postconditions** — Pós-condições
6. **Invariants** — Invariantes arquiteturais
7. **Failure Modes** — Modos de falha e comportamentos obrigatórios
8. **How** — Algoritmo/arquitetura/implementação
9. **Examples** — Exemplos concretos

**Extras:** GAPs (IDs rastreáveis) + Glossary e Acrônimos (tabela alfabética única)

---

## Diagramas Mermaid — Convenções

- **Activities (`c_activity/`):** `flowchart TB` + `flowchart LR` — mesmas lanes, nós, guards
- **MER (`d_mer/`):** `erDiagram` — modelo relacional
- **Classes (`e_class/`):** `classDiagram` — entidades, serviços, interfaces
- **Meta-Information JSON** — Embutido: `flow_id`, `lanes[]`, `activities[]`, `transitions[]`, `requirements[]`, `apis[]`

---

## Rastreabilidade Mínima

```text
RF → UC → RT → RNF → Task (T##) → Etapa (S##) → Evidência (Teste) → Caso Negativo (§7.A)
```

---

## Próximos Passos para Implementação

1. **Consultar o Backlog Operacional** — Ler [`a_context/backlog.md`](a_context/backlog.md) para critérios DoR/DoD de cada task e matriz anti-colisão.
2. **Iniciar pela Onda 1 (Fundações V0)**:
   - **T01:** Config canônica tipada (`config.py`, `config.yaml`, testes).
   - **T02:** Contratos canônicos e máquinas de estado (`model.py`, testes).
   - **T03:** Store relacional transacional SQLite WAL e migração (`core/checkpointer.py`, testes).
3. **Seguir o Faseamento por Ondas** — Avançar de O1 a O16 conforme os gates de saída definidos em [`a_context/roadmap.md`](a_context/roadmap.md).

---

**Roadmap Estratégico:** [`a_context/roadmap.md`](a_context/roadmap.md)<br>
**Backlog Operacional:** [`a_context/backlog.md`](a_context/backlog.md)<br>
**Norma de Taxonomia:** [`a_context/taxonomia_file_system.md`](a_context/taxonomia_file_system.md)<br>
**Plano Mestre:** [`a_context/plano_desenvolvimento.md`](a_context/plano_desenvolvimento.md)<br>
**Contexto Histórico:** [`a_context/CONTEXTO-ORQUESTRACAO.md`](a_context/CONTEXTO-ORQUESTRACAO.md)
