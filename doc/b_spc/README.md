# b_spc — Especificações Técnicas e Contratos (doc/b_spc)

Este diretório contém as especificações formais normativas, documentos de requisitos de produto (PRDs) e diretrizes arquiteturais vigentes do **hydra-orch**.

## Fluxo de Leitura Normativo

Para implementação e testes, seguir a sequência:
1. [`prd_funcional.md`](prd_funcional.md) (Requisitos funcionais RF01 a RF15 e critérios de aceite)
2. [`prd_tecnico.md`](prd_tecnico.md) (Requisitos técnicos RT01 a RT12, contratos e decomposição em tasks T01 a T08)
3. [`../d_mer/mer.md`](../d_mer/mer.md) (Modelo Entidade-Relacionamento e persistência SQLite)
4. [`../e_class/diagrama_classe.md`](../e_class/diagrama_classe.md) (Diagrama de classes e arquitetura de objetos)
5. [`../a_context/plano_desenvolvimento.md`](../a_context/plano_desenvolvimento.md) (Plano mestre de entregas e gates)

## Catálogo de Especificações

| Arquivo | Tipo | Descrição |
|---|---|---|
| [`prd_funcional.md`](prd_funcional.md) | PRD Funcional (DBC-9) | Requisitos de usuário, jornadas, regras de negócio e critérios observáveis de aceite |
| [`prd_tecnico.md`](prd_tecnico.md) | PRD Técnico (DBC-9) | Arquitetura alvo, máquinas de estado, API control plane, drivers e tasks T01 a T08 |
| [`prd_hydra_orch.md`](prd_hydra_orch.md) | PRD de Visão | Visão unificada do produto, modos Swarm, Relay e Persistente, e conectores |
| [`contrato_execucao.md`](contrato_execucao.md) | Contrato de Interface | Especificação das entidades RunSpec, TaskSpec, TaskAttempt, TaskResult e RunEvent |
| [`arquitetura_hydra_omniroute_ui.md`](arquitetura_hydra_omniroute_ui.md) | Fronteiras Arquiteturais | Delimitação entre Hydra control plane, OmniRoute gateway, executores e interface visual |
| [`taxonomia_file_system.md`](taxonomia_file_system.md) | Norma Arquitetural | Norma oficial de organização do repositório, regra de singularidade e economia de tokens |

Para o histórico e plano de desenvolvimento, consulte [`doc/a_context/`](../a_context/).
Para manuais de operação, consulte [`doc/j_manual/`](../j_manual/).
