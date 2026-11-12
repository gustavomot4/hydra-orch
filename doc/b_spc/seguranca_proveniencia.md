# S16 — Segurança local e proveniência

## Contrato entregue pela T09

Todas as rotas HTTP, inclusive health, inferência, documentação e aliases M1,
exigem um token Bearer. Ausência de configuração impede o startup antes de
inicializar gateway, banco ou SSH. Requisições sem token ou com credencial inválida
retornam `401 unauthorized` e `WWW-Authenticate: Bearer`, inclusive em loopback.
A CLI que chama diretamente o serviço local continua independente de HTTP.

O operador configura exatamente uma variável externa: `HYDRA_API_TOKEN_HASH`
(preferida) ou `HYDRA_API_TOKEN`. Tokens têm 32 a 4096 caracteres sem espaços;
o operador deve gerar valores aleatórios. A aplicação mantém apenas o verificador
PBKDF2-HMAC-SHA256 com salt aleatório de 16 bytes, 600.000 iterações e digest
de 32 bytes. O formato é `pbkdf2_sha256$iterations$salt_hex$digest_hex`.
Verificadores carregados exigem entre 600.000 e 2.000.000 iterações. A comparação
usa `hmac.compare_digest`; a derivação por requisição roda fora do event loop.
Rotação exige substituir a configuração externa e reiniciar o servidor.
Nenhuma credencial é escrita em YAML, SQLite ou arquivo pelo serviço de auth.

`HYDRA_CORS_ALLOW_ORIGINS` aceita uma lista JSON de origens HTTP(S) explícitas
em `localhost`, `127.0.0.1` ou `[::1]`, sem credenciais, paths, query ou fragmento.
O padrão preserva portas 8000, 3000 e 5173 em localhost/127.0.0.1.
Wildcard e origens externas são recusados. Origin não autorizado retorna 403
antes da autenticação. Clientes nativos podem omitir Origin e continuam sujeitos
ao Bearer. Preflight OPTIONS com Origin permitido não exige Bearer, pois browsers
não o enviam nessa etapa; o middleware CORS valida método e headers e não executa
o endpoint. OPTIONS comum continua autenticado.

## Sanitização e integridade

`core/redaction.py` remove campos sensíveis recursivamente e padrões textuais
de tokens conhecidos, Bearer, senhas, credenciais OAuth, URLs com user:pass e
chaves privadas PEM completas ou truncadas. O marcador é `[REDACTED]` e a
operação é idempotente. IDs, hashes e contadores de tokens são preservados.

- Eventos são sanitizados antes do INSERT na mesma transação do estado.
- Replay sanitiza também payloads legados sem reescrever sua sequência.
- JSON de evidência/erros e payloads SSE têm uma barreira de saída adicional.
- O logging padrão sanitiza mensagem, argumentos, traceback e stack antes dos handlers.
- Logs stdout/stderr de workers e checks são sanitizados antes da gravação;
  SHA-256 e tamanho descrevem os bytes sanitizados efetivamente armazenados.

Patches e arquivos do repositório não são reescritos pelo redactor; isso mudaria
o código e sua atribuição. Logs antigos em disco e outros dados legados no SQLite
não são expurgados automaticamente. Credenciais sem rótulo ou padrão reconhecível
não têm detecção garantida. O corpus benigno de testes verifica preservação de
2000 mensagens sintéticas; não certifica a taxa RNF05 em tráfego real.

## Validação e limites do gate

`tests/test_auth.py` cobre falhas de autenticação/configuração, ausência de token
no startup, preflight, CORS inválido, redaction recursiva/textual, logs com exceção,
persistência SQLite, replay/SSE e hashes de logs sanitizados. Testes de servidor
usam autenticação explícita, mantendo as verificações funcionais M1.

T09 não fecha isoladamente G-SEG: autorização de raízes/path traversal do catálogo
pertence à T11; consentimento, discovery, SecretRef e isolamento de extensões
dependem de T17–T20. Certificação de um driver externo também permanece separada.

## Contrato T17 — consentimento e memória (antes da implementação)

`ConsentService` registra solicitação `memory` para um escopo explícito
`principal`, `area`, `workspace` ou `project`. O principal autenticado deve ser
proprietário desse contexto. Transições permitidas: requested → granted/denied;
granted → revoked/expired. Revogação/expiração também desativam as memórias
vinculadas na mesma transação e geram auditoria imutável em `commands`.
Consentimento revogado nunca é reativado; uma nova concessão exige outro registro.

`MemoryStore` compartilha o SQLite e o registry com `ConsentService`. Escrita,
consulta e alteração exigem escopo/principal correspondentes e consentimento
atualmente granted. Conteúdo textual passa por redaction antes do INSERT, sem
captura automática de checkpoints, logs ou artefatos. Autoria vem do caller
identificado. Retenção explícita de 1 dia ou 30 dias gera expires_at; consultas
expiram registros vencidos antes de selecioná-los. Alteração exige versão
esperada e incrementa version; auditoria guarda versões/hashes, sem cópias do
conteúdo anterior. A versão atual é consultável, sem promessa de histórico textual.

A API local autenticada usa principal fixo `operator` (um operador local, sem
identidade fornecida em headers/body) e expõe `/v1/control-plane/consents` e
`/v1/control-plane/memory`. Consentimento ausente/inativo/incorreto retorna 409;
outro principal/contexto retorna 403. Preferências multiusuário e comandos CLI
estendidos não fazem parte desta entrega. Os módulos de execução não importam
`MemoryStore`; snapshots e admissão já recusam consentimento revogado/expirado.

Testes devem comprovar zero escrita sem consentimento, revogação imediata,
expiração, isolamento de principal/escopo/checkpoints, atualização concorrente,
auditoria atômica e redaction na persistência/HTTP. Redaction reconhece padrões
conhecidos de segredo e identificadores pessoais comuns; não constitui detecção
universal de PII em texto livre. O operador deve aprovar apenas conteúdo adequado.

### Superfície T17 entregue

- `POST /v1/control-plane/consents`: solicita com `scope_type` e `scope_id`.
- `GET /v1/control-plane/consents`: lista solicitações do escopo/principal.
- `POST /v1/control-plane/consents/{id}`: decisão explícita com
  `action=granted|denied|revoked|expired`; `/revoke` é atalho para revogação.
- `POST /v1/control-plane/memory`: recebe `scope_type`, `scope_id`, `content`,
  `consent_id` e `retention_policy=day|month` (1 ou 30 dias).
- `GET /v1/control-plane/memory`: consulta ativa por escopo e texto opcional.
- `PUT /v1/control-plane/memory/{id}?expected_version=N`: atualiza conteúdo e
  retenção; preserva escopo/consentimento. Versão desatualizada retorna 409.
- `POST /v1/control-plane/memory/{id}/revoke`: revoga a entrada individual.

As tabelas da migração 0002 são suficientes; nenhum script já aplicado é alterado.
Auditoria em `commands(scope=consent_memory)` contém ação, ator, ID, versões e
hash do conteúdo sanitizado. Não replica o texto da memória em logs de auditoria.
Consultas não devolvem conteúdos expirados/revogados nem autorizam coleta de
checkpoints, mesmo quando o consentimento do escopo está ativo.

## Contrato T18 — discovery local (antes da implementação)

Discovery é opt-in e usa raízes absolutas explícitas do operador, sem procurar
automaticamente no HOME. O scan é limitado em entradas/profundidade/tamanho,
ignora symlinks e diretórios de runtime/dependências e reconhece `SKILL.md`,
`skill.json`, `mcp.json`, `memory.json`, `session.json` e `hydra-resource.json`.
Manifestações JSON/YAML são dados: nada é importado, executado ou ativado.

O SQLite recebe proveniência, hash SHA-256 e capabilities declaradas, sempre
`untrusted` no primeiro encontro. Aprovação explícita exige o hash visto pelo
operador e capabilities conhecidas. Ativação exige aprovação e nova verificação
do arquivo; hash alterado, origem ausente ou raiz revogada bloqueiam o uso e
invalidam aprovação. Estado e auditoria são transacionais; dono/origem são
registrados em comandos imutáveis e impedem acesso por outro principal.

Perfis com recursos descobertos exigem o verificador de discovery compartilhado.
Snapshot faz preflight antes de sua transação, e o scheduler revalida os recursos
do perfil fixado a cada despacho. Não há importação automática de memórias ou
sessões descobertas; autorização de uso/segredos e protocolos ficam na T19.

No POSIX, leitura usa descritores relativos, O_NOFOLLOW e identidade da raiz;
no fallback portátil, caminhos/identidades são conferidos antes/depois da leitura.
Isso não certifica uma sandbox contra mutação hostil concorrente em todos os SOs.
A suíte prova arquivos/symlinks reais temporários, alteração de hash, revogação,
aprovação exata, limites e recusa de componentes alterados antes do uso.

### Superfície T18 entregue

`DiscoveryService(store, allowed_roots=[...], enabled=True)` configura raízes de um
operador local. `scan(root, principal_id=...)` retorna metadados `untrusted`;
`approve(id, expected_hash, principal_id=...)` confirma exatamente o hash
revisado. `decide(id, 'active'|'rejected'|'revoked', ...)`, `get`, `list` e
`require_approved` revalidam o arquivo antes de responder/usar. Recurso revogado
ou rejeitado não é reativado por novo scan nem por mudança de conteúdo.

`ProfileService(..., discovery=service)` exige o mesmo store e recusa recurso
descoberto sem verificador explícito. Pré-validação do snapshot preserva a
invalidação no SQLite mesmo quando a criação do snapshot é recusada. A admissão
da orquestração também verifica os componentes do perfil fixado. A tabela 0002
permanece intacta; `commands(scope=discovery_owner)` fixa o dono/proveniência e
`commands(scope=discovery)` audita descoberta, decisões e invalidações sem copiar
conteúdo dos arquivos. Novas superfícies CLI/HTTP pertencem à integração T23;
esta entrega disponibiliza o serviço Python e o gate de uso em perfis.

## Contrato T19 — skills, MCPs e referências de segredos (antes da implementação)

`SkillRegistry` (`core/skill_registry.py`) gerencia `SecretRef`, `SkillDefinition` e
`McpDefinition` nas tabelas da migração 0002 sem alterar scripts já aplicados.
`SecretRef` aceita apenas identificadores de referência (`source_key` compatível com
`^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$`); literais com padrão de token, alta entropia ou
alterados por `redact` são recusados com `secret_value_rejected`. O provedor `env`
resolve variáveis apenas no momento do spawn; `vault` e `keyring` recusam
explicitamente com `secret_provider_unavailable`, sem simulação nem fallback.

`SkillDefinition` e `McpDefinition` declaram permissões em vocabulário fechado
(`fs:read`, `fs:write`, `net:loopback`, `net:external`, `process:spawn`,
`secret:<ref_id>`). Endpoints não podem conter `userinfo`, parâmetros de token nem
segredos embutidos. Quando vinculados a `discovered_resource_id`, exigem recurso
`approved` ou `active` via `DiscoveryService.require_approved`, com `resource_type`
compatível e `checksum == content_hash`. Revogações de skill, MCP ou `SecretRef` são
gravadas atomicamente em `commands(scope=skill_registry)` usando apenas IDs e hashes,
nunca valores brutos.

`SecretResolver` produz um `SecretBundle` restrito à memória (representação mascarada,
sem serialização). Variável ausente bloqueia o spawn com `secret_unavailable`. Os
segredos resolvidos entram apenas via `allowed_env` em `filter_worker_env` sob nomes
que não colidem com `_SAFE_ENV_EXACT`, e são registrados em um scrubber de literais
por tentativa em `core/redaction.py` para mascaramento (`[REDACTED]`) antes da
gravação de stdout/stderr, eventos e artefatos; se um literal resolvido aparecer no
diff do patch, a integração é recusada com `secret_in_patch`.

`ProfileService` e a admissão da orquestração validam existência, ausência de
revogação e compatibilidade de permissões antes do snapshot e antes de cada despacho;
snapshots fixam somente IDs e hashes. `McpClient` (`bridge/mcp_client.py`) implementa
transporte `stdio` isolado com `filter_worker_env`, grupo de processos próprio,
`cancel_process_tree`, JSON-RPC 2.0 delimitado por linha (`initialize`, `tools/list`,
`tools/call`), validação de `declared_tools` (`mcp_tools_mismatch`), checagem de
permissão por ferramenta (`mcp_permission_denied`), limite de bytes, timeout e
redaction de respostas; `sse` e `websocket` são recusados com
`mcp_transport_uncertified` (reservados à T22). Superfícies CLI/HTTP estendidas
permanecem na T23.

## Contrato T20 — isolamento de extensões e plugins (antes da implementação)

Decomposição obrigatória (13 SP):
- **T20.1**: Contrato normativo pré-código em S16.
- **T20.2**: Extensão de `ConsentService` (`core/consent.py`) para `purpose='extension'` e
  modelos/validação de manifesto e integridade em `core/extension_host.py`.
- **T20.3**: Executor isolado em `bridge/extension_runner.py` com subprocesso separado,
  `filter_worker_env`, IPC JSON-RPC 2.0 via pipes e guarda `sys.addaudithook`.
- **T20.4**: `ExtensionHost` com máquina de estados `ExtensionInstall`, revogação
  síncrona via `cancel_process_tree`, quarentena por anomalia e rollback para versão
  anterior aprovada.
- **T20.5**: Integração com `SecretResolver` (apenas no spawn) e `redaction_scope`.
- **T20.6**: Suíte hermética `tests/test_extension.py` e rastreabilidade RT22.

`ExtensionManifest` exige `name`, `version`, `entrypoint` validado contra `allowed_roots`
(sem `..` nem symlink externo), `permissions_required` no vocabulário fechado
(`fs:read`, `fs:write`, `net:loopback`, `net:external`, `process:spawn`, `secret:<ref_id>`),
`compatible_api_version` compatível com `EXTENSION_API_VERSION = "1.0"` (mesmo major
`1.x`, erro `extension_incompatible_api`), e `checksum` SHA-256 idêntico ao arquivo em
disco (`extension_checksum_mismatch`). Credenciais brutas no manifesto ou payload são
recusadas (`redact`).

Instalação e ativação exigem `ConsentRecord` vigente com `purpose='extension'` e
`principal_id` proprietário (`consent_required`). As transições permitidas de
`ExtensionInstall` seguem estritamente `proposed -> consented -> installed -> active`;
`active -> disabled -> active`; `active -> quarantined`; `{proposed, consented,
installed, active, disabled, quarantined} -> revoked`; e `{active, disabled,
quarantined} -> rolled_back`. Revogação do consentimento ou da instalação encerra o
processo filho sincronamente via `cancel_process_tree`, bloqueia novas chamadas com
`extension_revoked` e registra auditoria imutável em `commands(scope='extension')`.
`rollback` restaura a versão anterior aprovada/não revogada do mesmo `name` ou falha
com `rollback_unavailable`.

Cada extensão roda em processo filho separado (`python -I`, `cwd` isolado em diretório
próprio da instalação, grupo de processos isolado, `filter_worker_env` sem variáveis
`HYDRA_*` ou caminhos do DB core). Para entrypoints Python, um bootstrapper instala
`sys.addaudithook` antes de carregar a extensão para bloquear acesso ao arquivo SQLite
do núcleo (`-wal`/`-shm`), escrita/leitura fora das raízes autorizadas pelas permissões,
soquetes fora de `net:*` e `subprocess` sem `process:spawn`; violações reportam anomalia
e colocam a instalação em `quarantined`. Limite explícito: entrypoints binários
não-Python contam com isolamento de processo/env/diretório/tree-kill do SO, sem o hook
de auditoria do interpretador Python. Superfícies HTTP/CLI estendidas permanecem na T23.
