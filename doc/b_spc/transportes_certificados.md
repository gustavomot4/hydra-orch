# S18b — Transportes Certificados (`transportes_certificados.md`)

**Identificador Formal:** `transportes_certificados.md`  
**Caminho Canônico:** `doc/b_spc/transportes_certificados.md`  
**Etapa / Task:** `S18b / T22`  
**Versão:** `v01_00_0000`  
**Status:** `IMPLEMENTADO / VERIFICADO OFFLINE (T22)`  
**Autoridade:** Derivado normativo de [`prd_funcional.md`](prd_funcional.md) (RF14, RF25, RB09, RB20), [`prd_tecnico.md`](prd_tecnico.md) (RT14, RT24, §3.6, §7.A, §8.2 T22), [`../d_mer/mer.md`](../d_mer/mer.md), [`../e_class/diagrama_classe.md`](../e_class/diagrama_classe.md), [`../f_api/openapi.yaml`](../f_api/openapi.yaml), [`../i_infra/README.md`](../i_infra/README.md) e [`../h_test/README.md`](../h_test/README.md).  
**Escopo:** Contrato formal do registro de transportes (`src/hydra_orch/bridge/transport_registry.py`), certificação explícita por SO/versão/alvo/checks com auditoria em `commands(scope='transport')`, verificação estrita de alvo (incluindo CDP), healthcheck tipado e redigido em `transport_health`, e endurecimento de `SshTunnelManager` (`src/hydra_orch/bridge/ssh_tunnel.py`) com `StrictHostKeyChecking=yes`, pinning em `known_hosts`/SHA-256 e isolamento de portas e buffers por `session_id`.

---

## 1. Purpose (Propósito)

Estabelecer o contrato verificável para cadastro, certificação explícita, validação de alvo, monitoramento de saúde e isolamento de sessões concorrentes dos transportes locais e remotos (`local`, `ssh`, `ide`, `cdp`, `remote`) do **hydra-orch**, garantindo que nenhum transporte seja considerado confiável por padrão, que divergências de identidade ou host key SSH abortem imediatamente sem bypass silencioso, e que saídas de sessões concorrentes permaneçam isoladas e sanitizadas.

---

## 2. Why (Justificativa)

Antes da T22, o transporte SSH em `bridge/ssh_tunnel.py` utilizava o padrão inseguro `StrictHostKeyChecking=accept-new`, não verificava `known_hosts` nem fingerprints SHA-256 antes do spawn, e mantinha apenas uma porta local fixa e um processo único sem isolamento por sessão. Em paralelo, o adaptador CDP (`bridge/cdp_fallback.py` / `adapter/ui_cdp.py`) selecionava uma página arbitrária quando a URL esperada não correspondia, violando RF14/RT24. Além disso, as tabelas `transport_definitions` e `transport_health` criadas na migração `0002_control_plane.sql` ainda não possuíam serviço de domínio com auditoria transacional e bloqueio de transportes não certificados em modo estrito/produção.

---

## 3. Contract (Contrato Formal)

### 3.1. Entidades (`src/hydra_orch/bridge/transport_registry.py`)
- **`TransportDefinition`** (`ExecutionModel`):
  - `transport_id: Identifier` (UUIDv7 por padrão), `type ∈ {"local", "ssh", "ide", "cdp", "remote"}`, `target_identity: NonEmpty`, `capabilities: tuple[NonEmpty, ...] | dict[str, Any]`, `is_certified: bool = False`, `created_at: UtcTimestamp | None`.
  - **Validação estrita de `target_identity`:** recusa string vazia, espaços/caracteres de controle, userinfo em URL ou autoridade (`user@host`, `user:pass@host`, `scheme://user:pass@host`), parâmetros de query sensíveis (`token=`, `secret=`, `api_key=`, `password=`, etc.) e qualquer padrão detectado por `core/redaction.py`.
- **`TransportCertificationReport`** (`ExecutionModel`):
  - `transport_id`, `transport_type`, `platform ∈ {"Linux", "Windows", "Darwin"}`, `version`, `target_identity`, `fingerprint` (obrigatório em formato `SHA256:<base64>` para `ssh`), `passed_checks`, `simulated: Literal[False]`, `issued_at`.
  - **Checks obrigatórios por tipo (`REQUIRED_CHECKS_BY_TYPE`):**
    - Comuns: `{"target_identity", "healthcheck"}`.
    - Adicionais para `ssh`: `{"host_key_verification", "session_isolation"}`.
    - Adicionais para `cdp`: `{"target_page_validation"}`.
- **`TransportHealth`** (`ExecutionModel`):
  - `health_id`, `transport_id`, `status ∈ {"unknown", "healthy", "degraded", "unreachable"}`, `last_check_at`, `error_detail` (obrigatoriamente redigido por `redact_text`).
- **`TargetValidation`** (`ExecutionModel`):
  - `transport_id`, `transport_type`, `expected_identity`, `observed_identity`, `matched: Literal[True]`, `validated_at`.

### 3.2. Serviço `TransportRegistry(store: ExecutionStore)`
- `register_transport(definition) -> TransportDefinition` (alias `register`): persiste em `transport_definitions` sempre com `is_certified = 0` (`False`), mesmo se a entrada informar `True`, e audita em `commands(scope='transport')`.
- `get_transport(transport_id)` / `list_transports(certified_only=False)`: consulta persistida no SQLite WAL.
- `certify_transport(transport_id, report, *, principal_id, platform_name=None) -> str`: exige `principal_id` explícito, valida `report.simulated is False`, correspondência de `transport_id`/`type`/`target_identity`, plataforma operacional (`platform.system()` ou `platform_name`), checks obrigatórios e fingerprint SHA-256 para `ssh`; atualiza `is_certified = 1` e registra auditoria imutável em `commands(scope='transport')`.
- `revoke_certification(transport_id, *, principal_id, reason=...) -> str`: define `is_certified = 0` e registra `transport.certification_revoked` em `commands(scope='transport')`.
- `require_certified(transport_id, *, strict=True, production_mode=True, platform_name=None) -> TransportDefinition`: em modo estrito ou produção, bloqueia com `ContractViolation(code="transport_uncertified")` qualquer transporte com `is_certified=0`, revogado ou sem registro de auditoria válido para o SO/alvo atual.
- `assert_target(transport_id, observed_identity, *, strict=False, production_mode=False, platform_name=None) -> TargetValidation`: compara `observed_identity` com `target_identity` segundo as regras do tipo (`cdp`, `ssh`, etc.) e levanta `ContractViolation(code="transport_target_mismatch")` em qualquer divergência.
- `select_cdp_target(expected_target, pages)` / `select_cdp_target_for(...)`: seleciona apenas página CDP (`type == "page"`, com `webSocketDebuggerUrl`) cuja URL corresponda estritamente a `expected_target`; **nunca** seleciona página aleatória ou primeira página como fallback.
- `check_health(transport_id, *, probe=None) -> TransportHealth`: executa `probe` síncrona ou assíncrona (ou registra `status="unknown"` quando `probe is None`), sanitiza `error_detail` com `redact_text`, persiste amostra em `transport_health` e retorna `TransportHealth`.

### 3.3. Endurecimento de `SshTunnelManager` (`src/hydra_orch/bridge/ssh_tunnel.py`)
- **`StrictHostKeyChecking=yes` obrigatório:** padrão alterado de `accept-new` para `yes`; configurações com `no`, `off`, `accept-new` ou `ask` são recusadas imediatamente com `TransportSecurityError` (subclasse de `ContractViolation`, código `ssh_insecure_host_key_checking`).
- **Verificação de Host Key (`verify_host_key`):** suporta `known_hosts_file` (entradas planas `host`, `[host]:port`, padrões negados `!pattern`, hashes HMAC-SHA1 `|1|salt|hash` e marcadores `@revoked`), `expected_host_key_fingerprint` (`SHA256:<base64>`) e verificador injetável `host_key_verifier(host, port)`. Se o arquivo não existir, o host não constar, a chave estiver revogada ou o fingerprint divergir, aborta imediatamente com `TransportSecurityError` antes de iniciar qualquer subprocesso.
- **Isolamento de sessões concorrentes:**
  - `allocate_session_port(session_id, *, preferred_port=None) -> int`: alocação sincronizada por lock que garante porta local loopback distinta por sessão ativa (`port_conflict` em colisão explícita).
  - `open_session(session_id, ...) -> SessionTunnelHandle`: verifica host key, aloca porta isolada e cria `SessionTunnelHandle` com buffers `stdout`/`stderr` separados por `session_id` (sanitizados via `redact_text` sob lock próprio).
  - `close_session(session_id, *, keep_logs=True)`: encerra processo da sessão (se ativo) e libera a porta local para reuso futuro sem afetar outras sessões.

---

## 4. Preconditions (Pré-condições)

1. Banco SQLite inicializado via `ExecutionStore.initialize()` com a migração `0002_control_plane.sql` aplicada (`transport_definitions`, `transport_health`) e tabela `commands` presente (`0001_initial_core.sql`).
2. Para conexões SSH reais ou em fixture offline, arquivo `known_hosts_file` válido ou `host_key_verifier` injetado.
3. Para certificação, evidência real (`simulated=False`) assinada por operador (`principal_id` não vazio).

---

## 5. Postconditions (Pós-condições)

1. Todo `TransportDefinition` recém-registrado é persistido com `is_certified = 0` e evento `transport.registered` em `commands(scope='transport')`.
2. Toda certificação ou revogação é atômica com o registro de auditoria em `commands(scope='transport')`.
3. Toda amostra de saúde produzida por `check_health` é persistida em `transport_health` com `last_check_at` UTC e `error_detail` redigido.
4. Sessões SSH concorrentes operam em portas locais distintas e com logs `stdout`/`stderr` completamente isolados por `session_id`.

---

## 6. Invariants (Invariantes)

1. **Invariante Não-Certificado por Padrão:** Registro de transporte nunca concede certificação; mock/simulação (`simulated=True`) nunca certifica transporte.
2. **Invariante Sem Bypass Silencioso (RT24):** `StrictHostKeyChecking` só aceita `yes`; host ausente em `known_hosts`, chave revogada ou fingerprint divergente sempre aborta antes do spawn.
3. **Invariante Sem Fallback Aleatório em CDP (RF14):** Alvo CDP ausente ou divergente sempre resulta em `transport_target_mismatch`, nunca na escolha da primeira aba disponível.
4. **Invariante Zero Segredos Persistidos (RB20):** `target_identity` recusa credenciais/userinfo na entrada; `error_detail`, logs de sessão SSH e payloads em `commands` passam por redaction determinística antes da persistência.
5. **Invariante de Isolamento Concorrente:** Nenhuma sessão SSH compartilha porta local ativa nem mistura linhas de buffer com outra sessão.

---

## 7. Failure Modes (Modos de Falha)

| Situação | Exceção / Status | Código | Comportamento Obrigatório |
|---|---|---|---|
| `strict_host_key_checking` igual a `no`, `off` ou `accept-new` | `TransportSecurityError` (`ContractViolation`) | `ssh_insecure_host_key_checking` | Rejeita na inicialização/verificação antes de qualquer comando SSH |
| `known_hosts_file` ausente ou ilegível | `TransportSecurityError` | `ssh_known_hosts_missing` / `ssh_known_hosts_unreadable` | Aborta antes do spawn; nenhum processo iniciado |
| Host não listado no `known_hosts` ou chave `@revoked` | `TransportSecurityError` | `ssh_host_key_unknown` / `ssh_host_key_revoked` | Aborta imediatamente sem bypass |
| Host key divergente do esperado/pinado | `TransportSecurityError` | `ssh_host_key_mismatch` | Aborta imediatamente antes do spawn |
| Transporte não certificado ou revogado em modo produção/estrito | `ContractViolation` | `transport_uncertified` | Bloqueia uso do transporte |
| Relatório de certificação simulado, de outro SO ou sem checks | `ValidationError` / `ContractViolation` | `certification_invalid` | Mantém `is_certified = 0`; nenhuma certificação gravada |
| `target_identity` com segredo ou userinfo (`user:pass@host`, `user@host`) | `ValidationError` | — | Recusa criação/cadastro do transporte |
| Alvo observado divergente ou página CDP ausente | `ContractViolation` | `transport_target_mismatch` | Falha observavelmente; nunca escolhe página aleatória |
| Falha/exceção na probe de saúde | `TransportHealth(status="unreachable")` | — | Persiste amostra com `error_detail` redigido |
| Colisão explícita de `preferred_port` entre sessões ativas | `ContractViolation` | `port_conflict` | Recusa alocação duplicada |

---

## 8. How (Arquitetura e Implementação)

1. **`src/hydra_orch/bridge/ssh_tunnel.py`:**
   - Normalização e cálculo offline de fingerprints `SHA256:<base64>` a partir de blobs base64 de chave pública OpenSSH (`compute_ssh_host_key_fingerprint`).
   - Parser completo de `known_hosts` (`parse_known_hosts`), suportando múltiplos padrões separados por vírgula, negação `!pattern`, portas não padrão `[host]:port`, entradas `@revoked` e hashes HMAC-SHA1 `|1|salt|digest`.
   - `SshTunnelManager.verify_host_key(...)` executa validação determinística combinando `known_hosts_file`, `expected_host_key_fingerprint` e `host_key_verifier` injetável, sendo invocada obrigatoriamente por `start_tunnel()` e `open_session()`.
   - `SshTunnelManager._session_lock` protege o conjunto `_allocated_ports` e o dicionário `_sessions: dict[str, SessionTunnelHandle]`, utilizando bind efêmero em `127.0.0.1:0` (com fallback determinístico em faixa alta caso sockets estejam restritos) para garantir unicidade de portas locais entre sessões concorrentes.
2. **`src/hydra_orch/bridge/transport_registry.py`:**
   - Validadores Pydantic e de domínio impedem segredos e userinfo em `target_identity` e `capabilities`.
   - `TransportRegistry(store)` reutiliza `ExecutionStore._connect()`, `_transaction()` e `_record_command_in_tx(scope="transport")` para persistência atômica nas tabelas `transport_definitions`, `transport_health` e `commands`.
   - `assert_target` e `select_cdp_target` normalizam URLs (esquema, host, porta, caminho) e fingerprints SHA-256 para validação estrita sem fallback aleatório.
   - `check_health` aceita probes síncronas ou assíncronas, captura exceções sem propagar credenciais (aplicando `redact_text`) e grava histórico completo em `transport_health`.

---

## 9. Examples (Exemplos de Uso e Aceite)

### 9.1. Registro, Bloqueio Não Certificado, Certificação e Revogação
```python
registry = TransportRegistry(store)
ssh_def = await registry.register_transport(
    TransportDefinition(
        type="ssh",
        target_identity="gpu-node.local:22",
        capabilities=("tunnel", "remote_exec"),
    )
)
assert ssh_def.is_certified is False
# Em modo estrito/produção, bloqueia antes da certificação:
# await registry.require_certified(ssh_def.transport_id) -> ContractViolation("transport_uncertified")

report = TransportCertificationReport(
    transport_id=ssh_def.transport_id,
    transport_type="ssh",
    platform=platform.system(),
    version="OpenSSH_9.6",
    target_identity="gpu-node.local:22",
    fingerprint="SHA256:...",
    passed_checks=("target_identity", "healthcheck", "host_key_verification", "session_isolation"),
    simulated=False,
)
await registry.certify_transport(ssh_def.transport_id, report, principal_id="operator")
```

### 9.2. Verificação Estrita de Host Key e Sessões SSH Isoladas
```python
manager = SshTunnelManager(
    {
        "host": "gpu-node.local",
        "port": 2222,
        "known_hosts_file": str(known_hosts_path),
        "expected_host_key_fingerprint": expected_fp,
    },
    host_key_verifier=lambda host, port: observed_fp,
)
s1 = manager.open_session("session-a")
s2 = manager.open_session("session-b")
assert s1.local_port != s2.local_port
```

---

## GAPs

- **GAP-TRANS-01:** Integração de rotas HTTP (`/v1/control-plane/transports`, `/transports/{id}/health`) em `server.py` e subcomandos `hydra transport` em `cli.py` pertence às entregas de CLI/API estendida (T23) e não altera os módulos desta task.
- **GAP-TRANS-02:** Atualização direta de `UiCdpAdapter` (`adapter/ui_cdp.py`) para consumir `TransportRegistry.select_cdp_target` em runtime permanece desacoplada até a ligação dos adaptadores ao registry de transportes.
- **GAP-TRANS-03:** `RemoteSshGpuConfig` em `config.py` ainda não declara campos `known_hosts_file` e `expected_host_key_fingerprint`; enquanto `config.yaml` mantiver `extra="forbid"`, esses campos podem ser injetados programaticamente ou adicionados em evolução futura de configuração.

---

## Glossary e Acrônimos

| Termo / Sigla | Significado |
|---|---|
| `assert_target` | Operação do `TransportRegistry` que valida correspondência exata entre alvo registrado e observado |
| `CDP` | Chrome DevTools Protocol; protocolo WebSocket de automação de navegador |
| `DBC-9` | Design by Contract em 9 seções normativas usado nas especificações do `hydra-orch` |
| `known_hosts` | Arquivo padrão OpenSSH contendo chaves públicas e identificadores de hosts confiáveis |
| `MITM` | Man-in-the-Middle; ataque de interceptação detectado pela divergência de host key |
| `Pinning` | Fixação explícita da identidade criptográfica (`SHA256`) esperada de um endpoint remoto |
| `Redaction` | Sanitização determinística de segredos, tokens e userinfo antes de logs e persistência |
| `SessionTunnelHandle` | Estrutura isolada por `session_id` contendo porta local alocada e buffers próprios |
| `SHA-256` | Algoritmo de hash criptográfico usado no fingerprint canônico de chaves SSH |
| `StrictHostKeyChecking` | Diretiva OpenSSH que exige chave previamente conhecida (`yes`) e recusa conexão em divergência |
| `TransportDefinition` | Entidade persistida em `transport_definitions` descrevendo tipo, alvo, capabilities e certificação |
| `TransportHealth` | Amostra tipada de saúde (`unknown`, `healthy`, `degraded`, `unreachable`) em `transport_health` |
| `TransportRegistry` | Serviço responsável por persistência, certificação auditada, validação de alvo e healthchecks |
| `Userinfo` | Componente `user[:password]@` em URI/autoridade, recusado em `target_identity` |
