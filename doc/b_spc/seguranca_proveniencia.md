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
