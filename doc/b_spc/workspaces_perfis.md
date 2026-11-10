# S14 — Base relacional do control plane, workspaces e perfis

## Entrega T10

T10 entrega o schema SQLite e o ciclo de migração. Os serviços de registry,
catálogo e resolução de perfis são descritos nas entregas T11–T13 abaixo; a presença
de tabelas por si só não ativa agentes, plugins ou recursos.

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

## Entrega T11 — WorkspaceRegistry

O serviço `core/workspace_registry.py` persiste áreas, workspaces, projetos,
repositórios e concessões, com IDs UUIDv7 compatíveis com Python 3.10+. Cada chamada
recebe o principal autenticado do adaptador; o registry não autentica identidade
por conta própria. `allowed_roots` é obrigatório, sem descoberta ou concessão
implícita. A propriedade de área permite administrar a hierarquia; o uso de
qualquer repositório, inclusive secundário, exige autorização própria e vigente
para read/write/execute/integrate.

Traversal é recusado antes de Git; realpath é conferido contra a allowlist.
`resolve_path` também valida globs e symlinks contra a raiz registrada. Branch e
SHA são resolvidos por Git sem fallback silencioso. Permissões são relidas depois
da inspeção de Git para respeitar revogações concorrentes. Essas verificações
não constituem sandbox contra mutações externas posteriores; o executor deve
revalidar no uso. Arquivar um workspace bloqueia novas resoluções.

Adoção de projeto legado exige comando explícito e revision vigente, sem criar
permissão de repositório. Mutações e auditoria em `commands(scope=registry)` são
atômicas. As superfícies CLI/API estendidas pertencem a T23; a API M1 não passa a
usar o registry automaticamente. Testes usam Git e SQLite em diretórios temporários.

## Entrega T12 — AgentRegistry

`AgentDefinition` é um contrato congelado com driver, versão, capabilities e
limitações. `AgentRegistry.register_agent` grava definições e declarações
atomicamente, sempre sem certificação. As capabilities suportadas pelo runner
são um teto técnico; não comprovam suporte efetivo de um provedor externo.
O alias de configuração `claude-code` usa a invocação real de `claude_code`.

`resolve_capabilities` exige capabilities compatíveis, CLI disponível e certificado
para o SO atual. Nenhum subprocesso é iniciado pelo catálogo. A certificação
é importada explicitamente por um operador de um relatório localizado sob
`certification_root`; não é inferida da instalação da CLI ou da existência do
arquivo. O relatório deve declarar driver, versão, SO, capabilities, checks
(cwd/scope/timeout/cancel_process_tree/artifact_hash), ausência de simulação,
data e hash do executável. O catálogo valida estrutura, associação e hashes;
a veracidade dos checks é responsabilidade do job emissor e da aprovação do
operador. Não há certificação real de Codex/Claude entregue pelos testes sintéticos.

Cada certificado atual usa um registro auxiliar em `capability_declarations`
com name=certification, version=SO e certified_on=data; o documento e seus hashes
ficam na auditoria imutável `commands(scope=agent_certificate)`, vinculada pelo ID
da declaração. A importação substitui apenas o certificado atual do mesmo SO;
revogação remove a referência ativa e preserva a auditoria. `is_certified` é
um indicador de apresentação; a seleção sempre relê o certificado específico.
Relatório ou executável alterado/inacessível invalida a seleção. Não é permitido
usar certificação de outro SO para execução local. Dependências transitivas do
executável e a integridade do host permanecem responsabilidade da certificação
externa e dos transportes T22.

## Entrega T13 — perfis e snapshots

`ProfileDefinition` é congelado e valida orçamento, referências sem duplicação,
modo e capabilities exigidas. Criação/atualização mantém JSON e associações
relacionais na mesma transação, com auditoria e revision otimista. O catálogo
de agentes, registry de repositórios e ProfileService compartilham a mesma
instância do ExecutionStore, evitando inicializações aninhadas sob writer lock.

Antes de produzir a configuração efetiva, o serviço exige grant execute no
repositório e certificação atual de agente/executor. Componentes descobertos
precisam estar aprovados. Memória habilitada exige consentimento granted, sem
revogação, do mesmo principal, purpose=memory e scope=project:<id>. Credenciais
brutas em componentes são recusadas. Resolução de segredos, ativação de skills/MCPs
e execução pertencem às tarefas posteriores; ProfileService não spawna processos.

`resource_limits_json` contém BudgetPolicy e required_capabilities. `snapshot`
verifica project/root do run e fixa uma configuração por run antes da primeira
tentativa. O JSON canônico UTF-8 tem SHA-256; persistência e evento
`profile.snapshot_created` são atômicos. Mudanças futuras do perfil não alteram
snapshots antigos, e repetição para o mesmo perfil/run retorna o original.
Outro perfil no mesmo run é conflito. A leitura verifica integridade e exige
autorização atual; configurações aninhadas são cópias, sem mutação do DTO.
Integrar a seleção do perfil ao despacho dos modos é responsabilidade da T25;
a API/CLI estendida permanece em T23.
