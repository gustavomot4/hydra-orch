# a_context — Contexto, Achados de Investigação e Planejamento

Este diretório concentra a documentação de contexto conceitual, registros históricos de investigação técnica, planejamento mestre de desenvolvimento e o catálogo de ideias futuras (Parking Lot) do **hydra-orch**.

## Artefatos Canônicos

| Arquivo | Tipo | Descrição |
|---|---|---|
| [`CONTEXTO-ORQUESTRACAO.md`](CONTEXTO-ORQUESTRACAO.md) | Relatório de Investigação | Contexto arquitetural de agentes, estudo de referência do Alethe, achados e lacunas do scaffold |
| [`plano_desenvolvimento.md`](plano_desenvolvimento.md) | Plano Mestre | Revisão integral do repositório, catálogo de lacunas (A01–A18), gates de entrega e sequência de specs (S00–S20, M1–M4) |
| [`plano_fluxo_conversa.md`](plano_fluxo_conversa.md) | Próxima entrega | Conversa pelo Novo chat com início do agente, respostas incrementais, contexto, interrupção e retomada |
| [`roadmap.md`](roadmap.md) | Roadmap Estratégico | Visão executiva de horizontes focados em engenharia de software (V0 a V4), marcos M1 a M4, gates formais DoR/DoD e matriz de riscos |
| [`backlog.md`](backlog.md) | Backlog Operacional | Catálogo canônico das 28 tasks normativas (T01 a T28), prioridades P0–P2, estimativas em Fibonacci (204 SP), 11 ondas e matriz anti-colisão |
| [`visao_produto.md`](visao_produto.md) | Visão Estratégica | Visão unificada do produto, arquitetura Swarm em Duas Ondas (Wave 0 + Wave 1), Handoff por Estado Git/Worktree e conectores |
| [`taxonomia_file_system.md`](taxonomia_file_system.md) | Norma Arquitetural | Norma de governança do repositório, singularidade estrita (`migration/`, `adapter/`, `model.py`), prefixos `a_..j_` e runtime `.orchestrator/` |
| [`ideia_futura.md`](ideia_futura.md) | Parking Lot (Pós-M4) | Propostas congeladas fora do escopo ativo: geração multimodal (imagem/áudio/vídeo), voz duplex, Computer Use, RAG corporativo, Jira/Kanbanize e quantização GGUF |

Para as especificações formais e normativas de requisitos (PRD Funcional e Técnico), consulte [`doc/b_spc/`](../b_spc/).
Para arquitetura de módulos e código, consulte [`doc/g_code/`](../g_code/).
