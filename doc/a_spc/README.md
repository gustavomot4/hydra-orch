# Especificações Técnicas e Contratos (doc/a_spc)

Este diretório contém especificações formais, documentos de requisitos (PRDs) e diretrizes arquiteturais do **hydra-orch**.

## Catálogo de Especificações

Leitura para implementação: [PRD funcional](prd_funcional.md) → [PRD técnico e tasks](prd_tecnico.md) → [classes](diagrama_classe.md) e [MER](mer.md) → [plano de entregas](plano_desenvolvimento.md). Esses documentos descrevem o alvo proposto; o PRD unificado abaixo permanece como visão histórica.

| Arquivo | Descrição |
|---|---|
| `taxonomia_file_system.md` | Norma oficial de organização do repositório, regra de singular e economia de tokens |
| `CONTEXTO-ORQUESTRACAO.md` | Investigação de referência do Alethe, arquitetura de execução e lacunas do scaffold |
| `prd_hydra_orch.md` | PRD unificado do produto, modos de execução (Swarm, Relay, Persistente), conectores e integração com agentes SWE |
| `arquitetura_hydra_omniroute_ui.md` | Limites entre Hydra, OmniRoute, executores e futura interface visual |
| `contrato_execucao.md` | Contratos de tarefa, resultado, evento e checkpoint verificáveis |
| [plano_desenvolvimento.md](plano_desenvolvimento.md) | Revisão integral do checkout, lacunas priorizadas, sequência de specs e gates de entrega |
