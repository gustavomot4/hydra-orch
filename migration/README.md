# migration — Migrações de Banco de Dados SQLite

Diretório canônico para scripts SQL versionados de evolução de esquema do SQLite (`.orchestrator/checkpoints.sqlite`).

## Convenções

1. Nomes de arquivo: `####_nome_descritivo.sql` (4 dígitos sequenciais, minúsculas, singular, snake_case).
2. Cada script é atômico e idempotente quando executado pelo runner de migração.
3. Versões aplicadas são registradas na tabela `schema_migrations`.
4. Tabelas legadas são mantidas para compatibilidade retroativa com serviços legados.

## Histórico de Migrações

- `0001_initial_core.sql`: Esquema relacional canônico do núcleo V0 / M1 (projetos, runs, tasks, attempts, workspaces, results, artifacts, checks, reviews, eventos, integrações, handoff, comandos, orçamento, métricas, rotas e preservação legada).
