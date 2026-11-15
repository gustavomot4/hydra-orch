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

## 7. Conversa por modelo/combo — execução de 14–15/11/2026

Esta seção amplia a validação somente leitura anterior. Houve inferência explicitamente autorizada para provar ferramentas e continuidade; o teste de catálogo acima continua sem inferência.

O catálogo local do OmniRoute `3.8.52` mostrou dez combos e 2.306 modelos naquele instante. Os nomes incluem `dev-agent`, `dev-rapido`, `planejamento`, `review`, `docs`, `rapido`, `free-agent`, `free-chat`, `contexto-longo` e `dev-agent-gpt`. Quantidade e disponibilidade podem mudar. A resposta do Hydra não expõe definições brutas, contas ou labels internos.

Prova real: Codex `0.169.0-alpha.11.1` com combo **dev-rapido** leu um conteúdo aleatório desconhecido no prompt, escreveu outro arquivo com o mesmo fato e, em um segundo turno nativo, recuperou esse fato sem reler. O teste completo durou **66,17 s**; registro UTC `2026-11-15T00:46:05Z` (14/11 às 21:46 em São Paulo). Ele comprova a rota e upstream observados naquele teste, sem certificar individualmente os fallbacks não exercitados. Um teste de leitura anterior, com o mesmo perfil de ferramentas, durou cerca de 8,1 s.

Foi necessário um perfil privado do Codex e um transporte Responses restrito a ferramentas de função suportadas. Sem isso, o upstream chegou a devolver texto com aparência de comando e nenhuma execução de ferramenta; esse retorno foi considerado falha. O adaptador não interpreta esse texto como ação. No Windows, o perfil conserva o sandbox solicitado e seleciona a implementação `unelevated`; não usa `danger-full-access` para certificar a rota.

Limites reais encontrados:

- Uma rota Codex via gateway recebeu 429 por limiar de contas configurado. Isso não comprova indisponibilidade da conta direta do agente.
- Testes de `review` e de um modelo Claude excederam o tempo limite. Os destinos permaneceram não verificados. Nenhum fallback direto foi aplicado pelo Hydra.
- A prova real A→B→A não foi concluída devido à indisponibilidade upstream. Continuidade A→B→A, fila imutável, revisão concorrente, cancelamento e reconstrução com referências têm testes controlados separados.
- Claude Code `2.1.222`: protocolo implementado, mas sem prova real autenticada de ferramentas/continuidade nesta entrega. Combos mistos ficam bloqueados para esse executor.
- Não foi feito benchmark comparativo de qualidade ou custo dos agentes. Tempo de certificação inclui duas chamadas e não deve ser apresentado como tempo habitual de resposta.

Para usar: em **Configurações e perfil → Conexão OmniRoute**, habilite o endereço da API e use **Salvar conexão → Testar conexão salva**. Este último só consulta metadados. A credencial é resolvida no backend pelo ambiente, sem campo de senha na interface. Em **Novo chat**, escolha agente, conexão OmniRoute e procure seu modelo/combo. **Testar combinação** executa a prova explícita de ferramentas, podendo consumir provedor. Apenas prova vigente libera o envio. A troca no cabeçalho vale para os próximos envios da mesma conversa.

Em **Opções da conversa**, a coordenação é opt-in; em leitura ela só prepara o plano. Para executar tarefas, selecione uma pasta Git e permita edições na cópia isolada. Pastas sem Git continuam funcionando com um agente. O roteamento automático de workers usa combos já testados, dentro da conexão/agente escolhidos, e informa a regra; não anuncia seleção universal do melhor LLM. Ver [contrato de coordenação](../b_spc/fluxo_conversa.md).

Validação local final: 39 testes de conversa/rotas/pastas/desktop; 38 de API, seletor e motores; mais 18 testes de coordenação/rotas incluindo cancelamento de worker e leitura dos logs pela API. As contagens possuem sobreposição e não devem ser somadas como testes distintos. A coordenação usou subprocessos, verificações e worktrees reais com CLI controlada, sem certificar um swarm de provedores reais.

O launcher existente foi exercitado em runtime isolado: autenticação automática sem digitar token, cadastro de pasta comum, preservação de porta ocupada, encerramento do backend próprio e liberação da porta. Os terminais já abertos nas instâncias antigas foram preservados. Na fixture de terminal WebSocket, o eco medido foi de 113 ms e a inicialização de 4.077 ms sob carga de testes; isso não mede o arranque real do Claude Code.

O verificador completo do kit encontrou zero falhas e três avisos em Novo chat e Conversa: áreas de toque da navegação, fonte existente e posição inicial de Tab após foco programático. Configurações ficou com zero falhas e cinco avisos, relativos a textos pequenos, áreas de toque, cartões aninhados, fonte e monoespaçada existentes. Três checkboxes abaixo do piso de 24 px foram ampliados e a verificação repetida. Foram exercitados tamanhos de tela, fonte a 200%, contraste forçado e axe; leitor de tela real e testes com pessoas não foram executados. Evidências locais e capturas permanecem fora do Git em `ws/b_output/`.

As consultas de versão/login fecham sua entrada padrão, evitando herdar o pipe aberto do launcher no Windows. Um teste abre esse pipe deliberadamente e exige retorno do probe. Na interface, o aceite durável libera o compositor antes da atualização do snapshot; leituras canceladas recebem `AbortSignal`. O primeiro projeto carregado preserva um pedido já digitado, enquanto trocas posteriores conservam rascunhos independentes. Essas regressões têm testes próprios.

Na rodada final, os sete cenários Playwright passaram em 1,9 minuto, incluindo pasta sem Git, terminal WebSocket, conversa/reload/cancelamento, troca A→B→A, opções de coordenação, cenário integrado e ditado controlado. Houve uma suíte completa de 52 testes de frontend aprovada e, após acrescentar a regressão do primeiro rascunho, sete testes focados de compositor/rotas passaram. Os nove testes de rota passaram após o ajuste de stdin. Estes resultados não substituem a validação de provedores reais descrita acima.

## 8. Diagnóstico do operador e Claude Code — 15/11/2026

O comando local `claude-omni` usa `CLAUDE_CONFIG_DIR` separado e as variáveis de endereço/credencial do gateway. Seu perfil também mapeia os modelos auxiliares para combos. Testado com `dev-rapido`, leu um fato aleatório de arquivo e o copiou por `Read`/`Write` (13,76 s); uma retomada nativa recuperou o fato sem releitura (5,99 s). Um primeiro teste do wrapper falhou antes da inferência por perda de aspas no JSON inline do MCP ao atravessar PowerShell; usar um arquivo de configuração MCP resolveu o teste. Exit code zero do wrapper não foi usado como prova.

O adaptador do Hydra foi validado separadamente com seu próprio perfil privado, sem importar configurações globais do operador: Claude Code `2.1.222` + combo `dev-rapido` comprovou leitura, escrita e continuidade em dois turnos, em 27,56 s, às `2026-11-15T17:53:19Z`. A prova foi registrada no banco de uso somente após conferir o mesmo fingerprint de definição/CLI. Não comprova todos os combos ou fallbacks. O bloqueio genérico de destinos não-Claude foi substituído por certificação específica. A descrição informa que tradução para destinos não-Claude não tem suporte oficial da Anthropic; essa restrição de suporte não significa impossibilidade técnica do gateway.

O Codex estava instalado e autenticado, mas o processo Hydra iniciado pelo Windows não tinha seu caminho no PATH. A descoberta agora consulta o pacote `OpenAI.Codex` registrado quando o PATH não contém a CLI, sem fixar o caminho versionado. Testado também com PATH sem Codex. Trocar conta pode afetar autenticação/cota; não explica, por si só, um executável que não foi encontrado. Instâncias antigas precisam reiniciar para carregar a descoberta atualizada; terminais em uso não foram encerrados pelo diagnóstico.

A execução `cr-227ae97467` usou Codex com `free-agent`. O worker fez leituras, recebeu depois HTTP 400 `Invalid agent request` do transporte local Hydra e encerrou com código 1. O resultado contém `checks_executed: []` e nenhuma alteração: os testes não chegaram a ser executados. O registro antigo não guardou o corpo rejeitado nem o motivo específico, portanto não permite atribuir com certeza qual campo provocou o 400. O transporte agora aceita chamadas sem ferramentas depois da admissão inicial, como em compactação, preserva a trava do alvo e devolve erro JSON com o motivo em vez de HTML genérico. Há teste controlado dessa sequência; a reprodução integral daquele pedido real não foi executada novamente.

A mensagem de falha do coordenador diferencia encerramento do worker antes dos checks de falha em checks executados. Para uma explicação sem alteração de código, o modo individual continua sendo o caminho apropriado; uma execução coordenada com somente uma tarefa não representa trabalho paralelo. O plano registrado naquela execução pretendia leitura, apesar de o fluxo estar em modo de edição; não se deve concluir que o sistema precisaria alterar arquivos para responder à pergunta.
