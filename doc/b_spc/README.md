# b_spc — Especificações Técnicas e Contratos (doc/b_spc)

**Identificador Formal:** `b_spc`
**Caminho Canônico:** `doc/b_spc/`
**Versão:** `v02_00_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch, norma para implementação e testes.
**Escopo:** Especificações formais normativas, PRDs, contratos e diretrizes arquiteturais.

---

Este diretório contém as especificações formais do **hydra-orch**. Todas as decisões de implementação e testes devem derivar destes documentos.

## Fluxo de Leitura Normativo

Para implementação e testes, seguir a sequência:

1. [`prd_funcional.md`](prd_funcional.md) — Requisitos funcionais **RF01 a RF30**, casos de uso **UC01 a UC05**, regras de negócio **RB01 a RB20**, critérios de aceite observáveis
2. [`prd_tecnico.md`](prd_tecnico.md) — Requisitos técnicos **RT01 a RT30**, requisitos não-funcionais **RNF01 a RNF10**, contratos formais de execução, máquinas de estado, API REST, algoritmos centrais, critérios negativos, tasks **T01 a T28**
3. [`../a_context/taxonomia_file_system.md`](../a_context/taxonomia_file_system.md) — Norma de organização do repositório (singularidade, prefixos ordenados, runtime `.orchestrator/`)
4. [`../g_code/architecture.md`](../g_code/architecture.md) — Fronteiras arquiteturais: Hydra control plane, OmniRoute gateway opcional, executores, UI
5. [`../d_mer/mer.md`](../d_mer/mer.md) — Modelo Entidade-Relacionamento completo (núcleo + expansão), DDL SQLite, índices
6. [`../e_class/diagrama_classe.md`](../e_class/diagrama_classe.md) — Diagrama de classes e interfaces (núcleo + expansão control plane)
7. [`../c_activity/`](../c_activity/) — Casos de uso **UC01 a UC05** com diagramas Mermaid TB/LR, DBC-9, Meta-Information JSON
8. [`../f_api/openapi.yaml`](../f_api/openapi.yaml) — Especificação OpenAPI 3.0 completa para `/v1/control-plane/*` e `/v1/chat/completions`
9. [`../h_test/README.md`](../h_test/README.md) — Matriz de rastreabilidade RF/RT → testes, estratégia hermética, critérios de cobertura
10. [`../i_infra/README.md`](../i_infra/README.md) — Infraestrutura: SSH, OmniRoute, contêineres, sandboxing, certificação drivers
11. [`../j_manual/README.md`](../j_manual/README.md) — Manuais operacionais: instalação, configuração, CLI, UI, runbooks, recuperação, auditoria, acessibilidade
12. [`../a_context/plano_desenvolvimento.md`](../a_context/plano_desenvolvimento.md) — Plano mestre de entregas, fases S00–S20, gates, marcos M1–M4 (V0–V4)
13. [`../a_context/roadmap.md`](../a_context/roadmap.md) — Roadmap estratégico com horizontes V0–V4, marcos M1–M4 e matriz de riscos
14. [`../a_context/backlog.md`](../a_context/backlog.md) — Backlog operacional com as 28 tasks normativas (T01–T28), 204 SP e 11 ondas de execução

## Catálogo de Especificações

| Arquivo | Tipo | Descrição | Versão |
|---------|------|-----------|--------|
| [`entrega_operacao.md`](entrega_operacao.md) | S13 / M1 / T08 (DBC-9) | CI hermético multiplataforma, retenção verificada por SHA-256 e manual operacional M1 | `v01_00_0000` |
| [`api_control_plane.md`](api_control_plane.md) | S10 / M1 / T07 (DBC-9) | Entrada unificada M1 (CLI e API REST/SSE) sobre `RunService`, idempotência, revisão e loopback auth | — |
| [`integracao_git.md`](integracao_git.md) | S05 / T05–T06 (DBC-9) | Workspace Git isolado em worktree real, SHA fixo, escopo, integração serializada e decomposição T06 | — |
| [`executor_cli.md`](executor_cli.md) | S04 / T04 (DBC-9) | Runner de subprocessos CLI, cwd real, env filtrado, tree kill e dry-run isolado | — |
| [`persistencia_execucao.md`](persistencia_execucao.md) | S03 / T03 (DBC-9) | Persistência transacional SQLite WAL, migrações versionadas e idempotência | — |
| [`contrato_execucao.md`](contrato_execucao.md) | S02 / T02 (DBC-9) | Specs de execução, estados, evidência declarada e revisão explícita | — |
| [`configuracao_runtime.md`](configuracao_runtime.md) | S01 / T01 (DBC-9) | Configuração estrita, provedores explícitos, aliases, política de gateway e migração manual | — |
| [`prd_funcional.md`](prd_funcional.md) | PRD Funcional (DBC-9) | RF01–RF30, UC01–UC05, RB01–RB20, proposta de valor e critérios de aceite observáveis | `v01_02_0000` |
| [`prd_tecnico.md`](prd_tecnico.md) | PRD Técnico (DBC-9) | RT01–RT30, RNF01–RNF10, contratos canônicos de execução, DDL SQLite, algoritmos, T01–T28 | `v01_02_0000` |

## Contadores Normativos Atuais

| Categoria | Range | Status |
|-----------|-------|--------|
| **RF** (Requisitos Funcionais) | RF01 – RF30 | Proposto |
| **RT** (Requisitos Técnicos) | RT01 – RT30 | Proposto |
| **RNF** (Requisitos Não-Funcionais) | RNF01 – RNF10 | Proposto |
| **UC** (Casos de Uso) | UC01 – UC05 | Documentado |
| **RB** (Regras de Negócio) | RB01 – RB20 | Definido |
| **T** (Tasks de Implementação) | T01 – T28 | Proposto |
| **S** (Etapas de Faseamento) | S00 – S20 | Planejado |
| **M / V** (Marcos / Slices) | M1 – M4 (V0 a V4) | Planejado |

## Convenções de Documentação (DBC-9)

Todos os PRDs e especificações seguem o padrão **DBC-9** (Design by Contract — 9 partes):

1. **Purpose** — Propósito do artefato/fluxo
2. **Why** — Justificativa e valor
3. **Contract** — Contrato formal (entradas, saídas, comportamento)
4. **Preconditions** — Pré-condições para execução
5. **Postconditions** — Pós-condições garantidas
6. **Invariants** — Invariantes arquiteturais
7. **Failure Modes** — Modos de falha e comportamentos obrigatórios
8. **How** — Como realizar (algoritmo, arquitetura, implementação)
9. **Examples** — Exemplos concretos de uso/aceite

**Extras obrigatórios:**
- **GAPs** — Decisões abertas com IDs rastreáveis (GAP-XXX-##)
- **Glossary e Acrônimos** — Tabela alfabética única (termos + siglas misturados)

## Diagramas Mermaid

- **Activities (c_activity):** `flowchart TB` (vertical) + `flowchart LR` (horizontal) — mesmas lanes, nós, guards
- **MER (d_mer):** `erDiagram` — modelo relacional visual
- **Classes (e_class):** `classDiagram` — entidades, serviços, interfaces, relacionamentos
- **Meta-Information JSON** — Embutido em cada PRD de fluxo: `flow_id`, `lanes[]`, `activities[]`, `transitions[]`, `requirements[]`, `apis[]`

## Rastreabilidade Mínima

```text
RF → UC → RT → RNF → Task (T##) → Etapa (S##) → Evidência (Teste) → Caso Negativo (§7.A)
```

Cada requisito deve ter:
- Task técnica com DoD (Definition of Done)
- Teste(s) automatizado(s) no mesmo commit
- Caso de teste negativo correspondente (critérios objetivos §7.A do PRD técnico)

## Princípios de Governança

1. **Nenhuma capacidade anunciada sem gate concluído** — RF/RT propostos permanecem `NÃO IMPLEMENTADO` até testes passarem
2. **Documentação precede implementação** — Specs atualizadas antes do código
3. **Testes herméticos** — Zero dependências externas (contas, GPU, rede) na suíte offline
4. **Segurança por padrão** — Auth local, CORS estrito, redaction centralizada, tokens hasheados
5. **Acessibilidade verificável** — WCAG AA checklist automatizado + manual
6. **Economia de tokens** — Singularidade, prefixos, raiz limpa, invariância temporal

---

**Para o histórico e plano de desenvolvimento:** [`doc/a_context/`](../a_context/)<br>
**Para diagramas de atividades:** [`doc/c_activity/`](../c_activity/)<br>
**Para modelo de dados:** [`doc/d_mer/`](../d_mer/)<br>
**Para diagramas de classes:** [`doc/e_class/`](../e_class/)<br>
**Para especificação OpenAPI:** [`doc/f_api/`](../f_api/)<br>
**Para testes:** [`doc/h_test/`](../h_test/)<br>
**Para infraestrutura:** [`doc/i_infra/`](../i_infra/)<br>
**Para manuais:** [`doc/j_manual/`](../j_manual/)
## Referência de interface

- [UI inspirada no Orca](a_ui/README.md) — imagens fornecidas, análise de referência, requisitos de chat/terminal e processo de construção (proposta).

- [S16 — Segurança local e proveniência (T09)](seguranca_proveniencia.md)

- [S14 — Base relacional, workspaces e perfis (T10)](workspaces_perfis.md)
