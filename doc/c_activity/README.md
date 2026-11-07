# c_activity — Diagramas de Atividades e Fluxos Operacionais

**Identificador Formal:** `c_activity`
**Caminho Canônico:** `doc/c_activity/`
**Versão:** `v01_01_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch, complementando `prd_funcional.md` e `prd_tecnico.md`.
**Escopo:** Casos de uso detalhados (UC01 a UC05) com diagramas de atividades Mermaid (TB/LR), DBC-9 e Meta-Information JSON.

---

Este diretório concentra as especificações completas dos casos de uso operacionais do **hydra-orch**, cada um em arquivo próprio seguindo o padrão DBC-9 com diagramas Mermaid em duas orientações (Vertical TB e Horizontal LR) e metainformações JSON embutidas.

## Conteúdo Atual

| Arquivo | Fluxo | Descrição | Requisitos Principais |
|---------|-------|-----------|----------------------|
| `uc01_task_execution.md` | UC01 | Submissão e revisão de tarefa simples (caminho feliz) | RF01–RF08, RF15 / RT01–RT10, RT12 |
| `uc02_swarm_healing.md` | UC02 | Execução em Swarm com DAG, paralelas e auto-healing | RF03–RF06, RF09, RF12, RF15 / RT04–RT07, RT12 |
| `uc03_relay_persist.md` | UC03 | Interrupção por rate limit e continuidade (Relay / Persistente) | RF10, RF11, RF20, RF26, RF27 / RT08, RT09, RT16, RT18, RT26, RT27 |
| `uc04_cancel_preserve.md` | UC04 | Cancelamento forçado com preservação de trabalho parcial | RF04–RF06, RF15 / RT04–RT06, RT11 |
| `uc05_discovery_activation.md` | UC05 | Descoberta e ativação controlada de ferramentas locais (MCP/Skill) | RF17, RF22, RF24 / RT14, RT20, RT21, RT22 |

## Padrão de Documentação (DBC-9 + Mermaid + JSON)

Cada arquivo UC segue a estrutura normativa da equipe:

1. **Contrato do fluxo** — 9 partes DBC-9: Purpose, Why, Contract, Preconditions, Postconditions, Invariants, Failure Modes, How, Examples
2. **Design** — Dois diagramas Mermaid `flowchart`:
   - `TB` (Top-Bottom / Vertical) — visão hierárquica por lanes (subgraphs)
   - `LR` (Left-Right / Horizontal) — visão sequencial por lanes
   - Mesmas lanes, atividades, conexões e guards nas duas orientações
3. **Meta-Information** — JSON válido com: `flow_id`, `lanes[]`, `activities[]`, `transitions[]`, `requirements[]`, `apis[]`
4. **GAPs** — Decisões abertas com IDs rastreáveis (GAP-UC##-##)
5. **Glossary e Acrônimos** — Tabela alfabética de termos e siglas do fluxo

## Convenções Mermaid

- **Lanes** = `subgraph` com IDs estáveis (`lane_operator`, `lane_hydra`, `lane_executor`, `lane_git`, `lane_db`, `lane_omni`, `lane_fs`, `lane_catalog`, `lane_exec`)
- **Atividades** = nós com IDs únicos e rótulos descritivos
- **Decisões** = nós `{{...}}` (diamante)
- **Guards** = rótulos nas setas (`guard: "condição"`)
- **Transições** mapeadas 1:1 no JSON `transitions[]`

## Rastreabilidade

```text
UC → RF/RT → Tasks (T01–T28) → Testes → Evidência
```

Os casos de uso UC01–UC05 cobrem funcionalmente os requisitos RF01–RF30 e tecnicamente os RT01–RT30 conforme a matriz de rastreabilidade em `prd_tecnico.md` (§8.4).

## Próximos Fluxos Planejados (Fase V4)

- `uc06_hitl_interaction.md` — HITL detalhado (needs_context, needs_approval, timeout, retomada)
- `uc07_conflict_resolution.md` — Resolução assistida de conflitos (3-way, auto_repair, manual, discard)
- `uc08_budget_governance.md` — Budgeting: alerta 80%, congelamento 100%, extensão, budget_exhausted
- `uc09_pr_packaging.md` — PR Package automático: branch, descrição, commits, checks, diff, métricas
- `uc10_memory_consent.md` — Memória adaptativa: consentimento, escopo, versão, revogação, isolamento checkpoints
- `uc11_transport_certification.md` — Transportes: SSH host key, healthcheck, IDE/CDP, isolamento saídas
- `uc12_accessibility_preferences.md` — A11y: teclado, foco, roles, contraste, redução movimento, snapshot/run

---

**Nota:** Diagramas BPMN/Draw.io/XML não são gerados. A representação Mermaid TB/LR + JSON embutido é o contrato único de fluxo. Não criar arquivos CHAT/PROMPT/RESULT como entregáveis ativos.