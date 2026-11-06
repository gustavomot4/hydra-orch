# f_api — Especificações de Interfaces Externas e OpenAPI

Este diretório concentra as especificações formais de endpoints HTTP, contratos REST do control plane e documentação OpenAPI / Swagger do **hydra-orch**.

## Conteúdo Planejado

- Especificação OpenAPI (YAML/JSON) para as rotas `/v1/control-plane/*` propostas no [PRD técnico](../b_spc/prd_tecnico.md).
- Contratos de streaming SSE para `/v1/control-plane/runs/{id}/events`.
- Contrato da rota compatível com OpenAI `/v1/chat/completions`.
