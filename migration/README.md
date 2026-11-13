# migration — Migrações de Banco de Dados SQLite

Diretório canônico para scripts SQL versionados de evolução de esquema do SQLite (`.orchestrator/checkpoints.sqlite`).

## Convenções

1. Nomes de arquivo: `####_nome_descritivo.sql` (4 dígitos sequenciais, minúsculas, singular, snake_case).
2. Cada script é atômico e idempotente quando executado pelo runner de migração.
3. Versões aplicadas são registradas na tabela `schema_migrations`.
4. Tabelas legadas são mantidas para compatibilidade retroativa com serviços legados.

## Histórico de Migrações

- `0001_initial_core.sql`: Esquema relacional canônico do núcleo V0 / M1 (projetos, runs, tasks, attempts, workspaces, results, artifacts, checks, reviews, eventos, integrações, handoff, comandos, orçamento, métricas, rotas e preservação legada).

- `0002_control_plane.sql`: Hierarquia organizacional (`area_workspaces`), catálogo/perfis, sessões, consentimento, recursos, extensões, preferências, transportes, acesso e conflitos. Preserva `workspaces` de tentativa.
- `rollback/0002_control_plane.sql`: Down explícito para 0001, com recusa de perda de dados e tentativas ativas. Scripts down não entram no glob de migração up.
- `0003_ui_automation.sql`: Tabelas duráveis de automações (`automation_schedules`, `automation_runs`) para agendamentos cron/intervalo/one-shot na UI e CLI.
- `rollback/0003_ui_automation.sql`: Down explícito de `0003_ui_automation.sql` para `0002`, preservando dados até confirmação/estado vazio.

## Operação T10

SQLite >= 3.35 com JSON1. O runner fixa checksums up/down, faz backup SQLite consistente com WAL antes de alterar o schema, serializa startups e valida FKs. O lote de scripts pendentes é atômico; falhas capturadas são auditadas em `migration_history`.

Com o serviço parado, `await store.rollback_migrations("0001")` cria backup e só remove a expansão se estiver vazia e sem alterações nos campos novos de projects/events. Não existe descarte forçado. Backups locais ficam em `migration_backup/` ao lado do banco; proteja e retenha esses arquivos conforme a política do projeto.

Contrato detalhado e limites: [S14](../doc/b_spc/workspaces_perfis.md). Não edite scripts já aplicados; crie uma nova versão.
