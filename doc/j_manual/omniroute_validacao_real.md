# Validação Real OmniRoute v3.8.52 (:20128)

> Documento técnico da integração real e somente leitura entre o **hydra-orch** e o daemon local **OmniRoute v3.8.52** (`http://127.0.0.1:20128`). Complementa o índice operacional em [README.md](README.md) e os contratos de interface em [../b_spc/ui_contratos.md](../b_spc/ui_contratos.md).

---

## 1. Resumo Executivo e Estado em Repouso

- **Configuração segura no repositório ([../../config.yaml](../../config.yaml)):** `omniroute.enabled: false` e `connection_mode: "disabled"` mantêm o comportamento padrão offline-first (modo direto sem dependência do gateway externo).
- **Credencial sem hardcode:** `omniroute.api_key_env: "OMNIROUTE_API_KEY"` lê exclusivamente a variável de ambiente em runtime; segredos, tokens e arquivos `.env` externos nunca são gravados no código nem versionados.
- **Compatibilidade retroativa:** O cliente [../../src/hydra_orch/bridge/omniroute_client.py](../../src/hydra_orch/bridge/omniroute_client.py) e todos os seus pontos de chamada (`cli.py`, `router.py`, `server.py`, `tui.py`) suportam o protocolo real do OmniRoute v3.8.52 preservando fallback para payloads legados utilizados nos mocks herméticos da suíte.

---

## 2. Alinhamento de Protocolo HTTP e Autenticação

| Capacidade | Endpoint / Mecanismo Real (`3.8.52`) | Implementação no `OmniRouteClient` |
|---|---|---|
| **Autenticação Bearer** | `Authorization: Bearer <OMNIROUTE_API_KEY>` | `_resolve_api_key()` e `_build_client()` leem `api_key_env` (ou chave explícita em testes) e injetam o header Bearer. Todos os 6 callers propagam `api_key_env`. |
| **Healthcheck e Warmup Frio** | `GET /v1/models` com fallback `GET /api/health` | `is_available()` trata `200` como disponível e `401`/`403` como indisponível; em `503` (ex.: `catalog_build_timeout` no aquecimento inicial), valida `status` `"ok"`/`"healthy"` em `/api/health`. |
| **Catálogo de Modelos** | `GET /v1/models` | `list_models()` (`source: "omniroute:models_api"`) normaliza IDs de modelos com timeout de leitura de `10.0s`. |
| **Telemetria de Quotas** | `GET /api/usage/quota` (`{"providers": [...]}`) + `GET /api/usage/provider-limits` (`{"caches": {...}}`) | `get_quota_status()` combina limites por conexão e agregados por provedor com salvaguardas anti-placeholder (`timeout` `8.0s`). |
| **Conexões / Contas** | Fallback de `GET /v1/accounts` (404 na v3.8.52) para `GET /api/providers` (`{"connections": [...]}`) | `list_accounts()` (`timeout` `6.0s`) normaliza conexões usando rótulos sintéticos sem PII nem credenciais (`source: "omniroute:providers_api"`). |

### Catálogo `logical_models` ([../../config.yaml](../../config.yaml))

Os modelos primários e estratégias de fallback configurados no `config.yaml` foram validados contra `GET /v1/models` no daemon local:

- `architect_heavy.primary`: `agy/claude-opus-5-5-high`
- `fullstack_coder.primary`: `codex/gpt-6-astra`
- `context_and_docs.primary`: `agy/gemini-4-argon-high`
- Estratégias automáticas amostradas: `auto/best-reasoning`, `auto/best-coding`, `auto/fast`

---

## 3. Salvaguardas de Honestidade, Consolidação de Quotas e Privacidade

1. **Rejeição de placeholders sintéticos (`_parse_real_quota_provider_item`):**
   O endpoint `/api/usage/quota` do OmniRoute v3 pode emitir itens sem medição real (`quotaTotal=null`, `quotaUsed=0`, `percentRemaining=100`, `resetAt=null`) ou com estado inativo/expirado (`expired`, `invalid`, `error`, `disabled`, `revoked`, `inactive`, `unauthorized`). Nessas condições, o Hydra rejeita a leitura sintética e retorna `status: "unknown"`, `remaining_percent: null` — nunca fabricando `0%` nem `100%`.

2. **Priorização de janelas de limite (`_parse_provider_limits_cache`):**
   Ao ler `/api/usage/provider-limits`, janelas finitas já esgotadas (`<= 0%`) têm prioridade de sinalização; havendo capacidade positiva, janelas curtas de sessão/`5h` (`windowSeconds <= 28800`) precedem limites semanais mais longos. Entradas com `unlimited: true`, sem limite finito e sem erro registram `100.0%`.

3. **Consolidação canônica e lookup no seletor ([../../src/hydra_orch/core/route_selector.py](../../src/hydra_orch/core/route_selector.py)):**
   Aliases de provedores (`agy`, `antigravity`, `gemini` → `gemini_pro`; `codex`, `openai`, `chatgpt` → `chatgpt_plus`; `claude`, `anthropic` → `claude_pro`) são consolidados via `_CANONICAL_QUOTA_KEY` e consultados de forma consistente em `RouteSelector` via `_QUOTA_KEY_ALIASES` e `_lookup_quota_observation()`. Provedores adicionais com medição real observada (como `github` e `cursor`) são preservados no mapa de quotas.

4. **Redação estrita de PII e segredos (`_normalize_provider_connection`, `_scrub_emails`, `_redact`):**
   Conexões de `/api/providers` nunca copiam campos sensíveis (`accessToken`, `refreshToken`, `providerSpecificData`, `apiKey`, `email`, `displayName`). Cada entrada recebe um identificador de conexão e um rótulo sintético (`<provider> (<authType>) · <id[:8]>`), passando em seguida por `_EMAIL_RE` (`[REDACTED_EMAIL]`) e `redact(...)` para garantir ausência total de endereços de e-mail e tokens nas APIs `/v1/quota` e `/v1/control-plane/omniroute/inventory`.

---

## 4. Evidência Sanitizada da Validação Ao Vivo

Execução somente leitura realizada contra `omniroute` `3.8.52` em `127.0.0.1:20128` via [../../tests/test_omniroute_live.py](../../tests/test_omniroute_live.py):

- **Disponibilidade e catálogo:** `available: true`, `models_status: "available"`, `model_count: 2294`, com presença confirmada dos primários configurados e estratégias `auto/*`.
- **Contas / conexões:** `accounts_source: "omniroute:providers_api"`, `accounts_count: 14`, `zero_at_in_all_payloads: true` (zero ocorrências de `@`, zero tokens e zero chaves sensíveis).
- **Quotas observadas vs desconhecidas:**
  - `chatgpt_plus` (`codex`): `observed` (`100.0%`, `has_reset: true`, `omniroute:provider_limits_api`)
  - `gemini_pro` (`gemini` / `agy` / `antigravity`): `observed` (`22.57%`, `has_reset: true`, `omniroute:provider_limits_api`)
  - `github`: `observed` (`0.0%`, `has_reset: true`, `omniroute:provider_limits_api`)
  - `cursor`: `observed` (`96.0%`, `has_reset: true`, `omniroute:provider_limits_api`)
  - `claude_pro` (`claude`) e provedores sem telemetria corroborada (`nvidia`, `opencode-go`, `opencode-zen`, `uncloseai`, `duckduckgo-web`, `cloudflare-playground`, `aihorde`): `status: "unknown"`, `remaining_percent: null`
- **Higiene pós-teste:** após o encerramento com `omniroute stop`, a porta `127.0.0.1:20128` permaneceu fechada (`False`).

---

## 5. Como Reexecutar (Offline vs Opt-In Ao Vivo)

### Suíte offline hermética (CI e desenvolvimento padrão)

Cobertura com transportes mockados sanitizados do protocolo OmniRoute v3 e compatibilidade legada em [../../tests/test_route_selector.py](../../tests/test_route_selector.py):

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_route_selector.py -v
```

Na suíte completa padrão (`python -m pytest tests -q`), [../../tests/test_omniroute_live.py](../../tests/test_omniroute_live.py) é ignorado automaticamente com *skip* quando `HYDRA_OMNIROUTE_LIVE` não é igual a `"1"`.

### Validação ao vivo somente leitura (opt-in local)

1. Defina `OMNIROUTE_API_KEY` no ambiente atual (sem salvar em arquivos do repositório).
2. Inicie o daemon local temporariamente:
   ```powershell
   omniroute serve --daemon --no-open --no-tray
   ```
3. Execute os testes opt-in de controle/leitura:
   ```powershell
   $env:PYTHONPATH = "$PWD\src"
   $env:HYDRA_OMNIROUTE_LIVE = "1"
   python -m pytest tests/test_omniroute_live.py -v
   ```
4. Pare o daemon ao finalizar:
   ```powershell
   omniroute stop
   ```

---

## 6. Limites Honestos de Escopo

- **Zero inferência paga automatizada:** `tests/test_omniroute_live.py` valida exclusivamente leitura de catálogo (`/v1/models`), saúde (`/api/health`), quotas (`/api/usage/quota` e `/api/usage/provider-limits`), provedores (`/api/providers`) e endpoints FastAPI `/v1/quota` e `/v1/control-plane/omniroute/inventory`. Nenhuma chamada `/v1/chat/completions` é disparada.
- **Provedores sem telemetria:** provedores sem endpoint de cota suportado ou com credencial expirada continuam reportando `status: "unknown"` e `remaining_percent: null` até nova autenticação e medição válida.
