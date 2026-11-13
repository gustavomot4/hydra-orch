# f_api — Especificações de Interfaces Externas e OpenAPI

Este diretório concentra os contratos formais de endpoints HTTP, streaming SSE e documentação OpenAPI do **hydra-orch** (implementados em `src/hydra_orch/server.py` e validados em `tests/test_server.py` e `tests/test_ci_negative_gate.py`).

## Conteúdo Canônico

- [`openapi.yaml`](openapi.yaml) — Especificação **OpenAPI 3.0.3** com **77 paths** cobrindo:
  - Rotas de Control Plane `/v1/control-plane/*` (áreas, workspaces, projetos/repositórios, agentes, perfis, runs, tasks, revisões, integração, descarte, sessões/threads, métricas, HITL, consentimento, memória, discovery, skills, MCPs, secret refs, extensões, preferências, transportes, tokens locais, resolução de conflitos 3-way, budget e empacotamento de PR).
  - Streams SSE (`/v1/control-plane/runs/{id}/events` e `/v1/control-plane/sessions/{id}/events`) com `Last-Event-ID`, replay ordenado e `heartbeat`.
  - Rota compatível com OpenAI `/v1/chat/completions` e endpoints operacionais (`/health`, `/models`, `/orchestrator/status`) protegidos por Bearer auth (`PBKDF2-SHA256`), CORS restrito e redação automática de segredos.
