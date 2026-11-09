# S14 — Base relacional do control plane, workspaces e perfis

## Entrega T10

T10 entrega o schema SQLite e o ciclo de migração. Os serviços de registry,
catálogo e resolução de perfis são entregas posteriores (T11–T13); a presença
de tabelas não certifica esses serviços nem ativa agentes, plugins ou recursos.

`0001_initial_core.sql` é imutável. A migração aditiva
`migration/0002_control_plane.sql` preserva as tabelas e linhas do núcleo e do
streaming. Projetos legados continuam válidos sem workspace, branch ou SHA
inventados: as novas referências opcionais começam em NULL.

## Mapeamento físico e integridade

| Área | Armazenamento da expansão |
|---|---|
| Hierarquia | `areas`, `area_workspaces`, `repositories`, `authorizations`; novas colunas opcionais em `projects` |
| Catálogo e perfis | `agent_definitions`, `capability_declarations`, `profiles`, `profile_snapshots`, `profile_skills`, `profile_mcps` |
| Sessões | `sessions`, `threads`; referências opcionais e índices em `events` |
| Consentimento e recursos | `consent_records`, `memory_entries`, `discovered_resources`, `skill_definitions`, `secret_refs`, `mcp_definitions` |
| Extensões | `extension_manifests`, `extension_installs` |
| Preferências | `preferences`, `preference_snapshots` |
| Transporte e acesso | `transport_definitions`, `transport_health`, `access_tokens` |
| Integração | `conflict_reports`; orçamento, métricas, rotas, handoff e PR packages já pertencem à 0001 |

O `Workspace` lógico do MER é `area_workspaces`. A tabela `workspaces` existente
permanece exclusivamente vinculada às tentativas/worktrees Git. Essa distinção
preserva a compatibilidade M1 e evita misturar contexto organizacional com
isolamento de execução. IDs textuais são gerados pelos futuros serviços.

FKs usam RESTRICT para contexto e histórico referenciados; CASCADE fica limitado
a declarações e associações dependentes. Índices cobrem lookup de hierarquia,
perfil, sessão, thread, consentimento e transporte. O pai de uma thread deve
pertencer à mesma sessão; ciclos mais longos e correlação run/sessão/evento
exigem validação transacional do serviço T14.

Snapshots permitem um registro por run e vários snapshots históricos do mesmo
perfil. A validação do conteúdo/hash e a imutabilidade por política pertencem à
T13. Perfis armazenam referências declarativas JSON e associações relacionais;
o serviço deve validá-las conjuntamente na mesma transação, sem ativação automática.

Recursos descobertos começam em `untrusted`; agentes e transportes começam sem
certificação. JSON inválido, estados não catalogados, referências inexistentes e
hashes de acesso fora do formato PBKDF2 são recusados pelo banco. `secret_refs`
contém apenas localização externa, sem coluna para valor bruto. FKs de memória
e instalações exigem consentimento existente; verificar concessão ativa,
revogação e escopo é responsabilidade de T17–T20.

## Migração, backup e auditoria

`ExecutionStore.initialize()` aplica a sequência de scripts SQL conhecida pelo
checkout. Versões devem ser únicas e ordenadas com quatro dígitos. Checksums
SHA-256 normalizam finais de linha; scripts up e down são fixados na aplicação.
Schema desconhecido, sequência aplicada com lacunas ou scripts alterados
impedem a atualização. O legado sem checksum da T03 permanece compatível.

Sob `BEGIN IMMEDIATE`, o migrador relê as versões aplicadas, exclui writers
concorrentes e cria um backup com a API SQLite, incluindo páginas confirmadas
do WAL. Um reader separado faz a cópia enquanto a conexão principal mantém o
lock sem writes pendentes. O backup é criado exclusivamente, sem sobrescrever
arquivos, com `integrity_check`. O bootstrap das tabelas de controle/auditoria
ocorre antes desse snapshot; os dados de domínio ainda não foram alterados.
Só depois são aplicados os scripts pendentes
em uma transação para o lote, mantendo FKs habilitadas e verificando
`foreign_key_check`. Uma falha desfaz DDL, dados e registros de versão do lote.

Backups ficam em `migration_backup/<uuid>.sqlite` ao lado do banco, normalmente
`.orchestrator/migration_backup/`; são dados locais sensíveis e nunca versionados.
`migration_history` registra versão, direção up/down, checksum do script, caminho
do backup, sucesso/falha e data. O histórico de sucesso é atômico com a migração;
falhas capturadas são registradas depois do rollback. Queda abrupta pode deixar
backup órfão sem entrada de falha; não há limpeza automática de evidências.

## Downgrade explícito e seguro

Com o serviço parado, use `await store.rollback_migrations("0001")`, ou forneça
`backup_path=` para escolher um arquivo novo. O método não inicializa nem atualiza
o schema antes de decidir o downgrade. A T10 fornece somente down de 0002 para
0001, em `migration/rollback/0002_control_plane.sql`; não remove o núcleo 0001.
SQLite >= 3.35 com JSON1 é necessário para o schema e para DROP COLUMN.

O down recusa qualquer linha nas tabelas novas, valores novos em projects/events
ou tentativas queued/running. Não há opção de descarte forçado. Se já houver dados
da expansão, preserve o banco atual e planeje exportação/migração desses dados
antes de tentar o downgrade. O backup é obrigatório também para downgrade, e
os mesmos checksums/FKs/transações continuam em vigor. Falha de qualquer comando
down restaura o schema inteiro e registra a recusa, preservando o backup.

Após sucesso, o mesmo store continua na versão escolhida para consulta. Um
novo store inicializado pelo checkout atual reaplica 0002; para operação duradoura
na versão anterior, use um checkout compatível e mantenha o serviço parado até
concluir o procedimento. `get_migration_history()` lê sem atualizar o schema.

## Aceite

`tests/test_migration.py` cobre bancos novos, upgrade com registros de runs e worktrees
no schema, preservação de streaming, backup WAL, restart, inicialização concorrente,
up/down/up, recusa de perda de dados, scripts alterados/ausentes, falhas de SQL e
de FK com rollback atômico, defaults sem confiança implícita e isolamento das
relações. A suíte não usa modelos externos nem serviços de rede.
