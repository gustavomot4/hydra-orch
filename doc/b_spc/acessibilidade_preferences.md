# S18a — Preferências Reversíveis e Acessibilidade WCAG AA (T21 / RF23 / RT23)

**Identificador Formal:** `S18a`
**Caminho Canônico:** `doc/b_spc/acessibilidade_preferences.md`
**Versão:** `v01_00_0000`
**Status:** `NORMATIVO (T21)`
**Autoridade:** Arquitetura do `hydra-orch`, realizando [`prd_funcional.md`](prd_funcional.md) (`RF23`, `RB17`), [`prd_tecnico.md`](prd_tecnico.md) (`RT23`, §3.6, §7.A) e complementando [`a_ui/b_interface.md`](a_ui/b_interface.md) (`S11`).
**Escopo:** Serviço de preferências escopadas/reversíveis (`PreferenceService`, `Preference`, `PreferenceSnapshot`) e contrato verificável de acessibilidade WCAG AA (`AccessibilitySettings`, `AccessibilityChecklist`, `contrast_ratio`, `validate_a11y_contract`, `assert_ui_command_authorized`).

---

## 1. Purpose (Propósito)

Especificar formalmente o contrato de **preferências reversíveis com snapshot imutável por run** e o **contrato verificável de acessibilidade WCAG AA** com guarda explícita de autoridade para a interface visual do `hydra-orch`, implementados em `src/hydra_orch/core/preferences.py` e validados por suítes herméticas em `tests/test_preferences.py` e `tests/test_a11y.py`.

## 2. Why (Justificativa)

1. **Previsibilidade entre execuções:** Alterar preferências de tema, layout, movimento ou comportamento durante um `run` em andamento não pode mutar retroativamente a configuração efetiva daquela execução. O `PreferenceSnapshot` fixa um hash SHA-256 canônico por `run_id`.
2. **Controle do operador sobre inferência:** Sugestões automáticas ou preferências inferidas (`inferred_opt_in`) só podem existir com consentimento explícito (`opt_in=True`) e **jamais** podem sobrescrever ou sobrepor preferências declaradas explicitamente (`explicit`).
3. **Reversibilidade auditável:** Toda alteração de preferência é registrada atomicamente em `commands(scope='preferences')`, permitindo reverter para estados anteriores sem perda de rastreabilidade.
4. **Acessibilidade mensurável e fronteira de autoridade:** Acessibilidade WCAG AA não deve ser apenas declarativa; deve ser verificável por funções determinísticas (luminância relativa sRGB, contraste >= 4.5:1 / 3.0:1, foco visível, navegação por teclado, roles semânticos, rótulos textuais independentes de cor e `reduce_motion`), mantendo a UI estritamente como consumidora sem autoridade para aprovar tarefas sem comando versionado.

## 3. Contract (Contrato Formal)

### 3.1 Preferências Escopadas e Reversíveis (`PreferenceService`)

- **Escopos suportados (`ScopeType`):** `user`, `area`, `project`, persistidos na tabela `preferences` (`migration/0002_control_plane.sql`) com unicidade `(scope_type, scope_id, key)` e coluna `version >= 1`.
- **Origens (`PreferenceSource`):**
  - `explicit`: definida diretamente pelo operador.
  - `inferred_opt_in`: inferida somente quando `opt_in=True` é fornecido explicitamente na chamada.
- **Regras de precedência:**
  - **Mutação no mesmo escopo:** Uma preferência `inferred_opt_in` **nunca** sobrescreve uma preferência `explicit` existente para o mesmo `(scope_type, scope_id, key)` — falha com `ContractViolation("explicit_preference_precedence", ...)`.
  - **Resolução efetiva (`resolve_effective`):** `explicit > inferred_opt_in` e, dentro da mesma precedência de origem, `project > area > user`.
- **Higiene e segredos:** Chaves, identificadores de escopo, atores e valores passam por `hydra_orch.core.redaction.redact` / `redact_text` e validação JSON estrita (`allow_nan=False`). Qualquer segredo ou credencial detectado é recusado com `ContractViolation("secret_in_preference", ...)`.
- **Auditoria e reversão (`revert_preference`):**
  - Toda criação, atualização e reversão grava na mesma transação SQLite um registro de auditoria em `commands(scope='preferences')` contendo `action`, `preference_id`, `scope_type`, `scope_id`, `key`, `actor`, `previous_state` e `new_state`.
  - `revert_preference(...)` restaura atomicamente a versão anterior registrada na auditoria (ou remove o registro se a reversão atingir a criação inicial na versão `1`, registrando a remoção na auditoria), incrementando o contador monotônico `version` quando há restauração de valor prévio e respeitando `expected_version` quando informado.
- **Snapshot imutável por run (`snapshot_for_run`):**
  - Verifica que o `run_id` existe em `runs`.
  - Resolve as preferências efetivas para os escopos informados (`user_id`, `area_id`, `project_id`), serializa em JSON canônico UTF-8 (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`) e calcula `preferences_hash = sha256(canonical_json)`.
  - Persiste `PreferenceSnapshot` em `preference_snapshots` e emite o evento `preference.snapshot_created` na mesma transação (`ExecutionStore._insert_event_in_tx`).
  - Chamadas idempotentes com o mesmo `run_id` e mesma configuração (`preferences_hash` idêntico) retornam o snapshot original sem duplicar eventos.
  - Tentar sobrescrever um snapshot existente para o mesmo `run_id` com configuração divergente falha com `ContractViolation("preference_snapshot_conflict", ...)`.
  - Alterações posteriores na tabela `preferences` não modificam snapshots já gravados.

### 3.2 Contrato Verificável WCAG AA e Guarda de UI

- **`contrast_ratio(foreground, background) -> float` e `relative_luminance(hex_color) -> float`:**
  - Implementam exatamente a fórmula WCAG 2.1 de luminância relativa sRGB ($L = 0.2126 R + 0.7152 G + 0.0722 B$ com limiar de linearização `0.04045`) e razão de contraste $(L_1 + 0.05) / (L_2 + 0.05) \in [1.0, 21.0]$.
  - Limiares normativos: `>= 4.5:1` para texto normal (`normal_text`) e `>= 3.0:1` para texto grande (`large_text`) e componentes de UI (`ui_component`).
- **`AccessibilitySettings` e `AccessibilityChecklist` (`validate_a11y_contract`):**
  - Valida os 6 critérios obrigatórios de `RF23 / RT23`:
    1. `keyboard_navigation`: operabilidade integral por teclado (`keyboard_navigation=True` e controles com `keyboard_accessible=True`).
    2. `focus_visible`: indicador de foco visível (`focus_visible=True`, `focus_outline_px >= 1` e controles com `focus_visible=True`).
    3. `semantic_roles`: uso de roles semânticos reconhecidos e rótulos acessíveis não vazios em todos os controles declarados.
    4. `textual_status_labels`: comunicação de estado nunca dependente apenas de cor (`textual_status_labels=True` e todo controle com indicador de estado possui `status_text` explícito).
    5. `contrast_wcag_aa`: todos os pares `ColorTokenPair` declarados satisfazem o contraste mínimo WCAG AA (`4.5:1` texto normal; `3.0:1` texto grande/componentes).
    6. `reduce_motion`: suporte à preferência de redução de movimento (`respects_prefers_reduced_motion=True`, ausência de animações que ignorem `reduce_motion=True` e `effective_animation_ms = 0` quando ativo).
- **Guarda de autoridade da UI (`assert_ui_command_authorized` / `UiCommandEnvelope`):**
  - Rejeita qualquer tentativa da UI de aprovar/aceitar tarefa (`accept_task`) ou mutar estado sem um envelope `UiCommandEnvelope` explicitamente versionado (`command_version="1.0"`), com `command_id`, `actor`, `idempotency_key` (16–64 caracteres), `expected_revision >= 1` e referências explícitas (`result_id`, `reason`).

## 4. Preconditions (Pré-condições)

- Banco SQLite inicializado com as migrações `0001_initial_core.sql` (`runs`, `events`, `commands`) e `0002_control_plane.sql` (`preferences`, `preference_snapshots`), com `PRAGMA foreign_keys = ON` e `journal_mode = WAL`.
- Para `snapshot_for_run(run_id, ...)`, o `run_id` deve existir na tabela `runs` em estado não terminal (`queued`, `running` ou `waiting`) caso ainda não possua snapshot.
- Para preferências `inferred_opt_in`, o chamador deve fornecer explicitamente `opt_in=True`.

## 5. Postconditions (Pós-condições)

- Toda mutação bem-sucedida em `preferences` possui entrada correspondente na tabela `commands(scope='preferences')` na mesma transação.
- `snapshot_for_run` garante que exista exatamente um registro imutável em `preference_snapshots` para o `run_id` e exatamente um evento `preference.snapshot_created` correspondente em `events`.
- `validate_a11y_contract` retorna um `AccessibilityChecklist` completo com os resultados por critério e razões de contraste calculadas, ou lança `ContractViolation("a11y_contract_violation", ...)` quando `raise_on_failure=True`.

## 6. Invariants (Invariantes)

1. **Precedência explícita inviolável:** Preferência `inferred_opt_in` jamais sobrescreve preferência `explicit` no armazenamento nem se sobrepõe a `explicit` na resolução efetiva.
2. **Imutabilidade de snapshot:** Uma vez gravado, um `PreferenceSnapshot` é imutável; seu `preferences_hash` corresponde sempre ao SHA-256 do JSON canônico UTF-8 de `resolved_preferences_json`.
3. **Atomicidade transacional:** Estado em `preferences`/`preference_snapshots`, auditoria em `commands` e evento `preference.snapshot_created` confirmam ou revertem juntos.
4. **Redaction obrigatória:** Nenhum token, chave privada, senha ou credencial em URL pode ser persistido em `preferences` ou `commands`.
5. **UI não é autoridade:** A camada visual é consumidora de read models; aceite ou mutação exige comando versionado autenticado e revisado pelo backend.

## 7. Failure Modes (Modos de Falha)

| Caso / Condição | Código `ContractViolation` / Erro | Comportamento Obrigatório |
|---|---|---|
| Inferida sem `opt_in=True` | `opt_in_required` | Bloqueio antes da escrita; nenhuma linha alterada |
| Inferida tenta sobrescrever explícita | `explicit_preference_precedence` | Bloqueio; preferência explícita intacta |
| Valor/chave/ator com segredo | `secret_in_preference` | Rejeição via `redact`; nada gravado |
| Revisão otimista divergente | `optimistic_lock_conflict` (`OptimisticLockError`) | Mutação/reversão rejeitada |
| Reversão sem histórico / alvo inválido | `resource_not_found` / `preference_revert_unavailable` | Nenhuma alteração no banco |
| Snapshot conflitante no mesmo `run_id` | `preference_snapshot_conflict` | Snapshot original preservado |
| Adulteração de snapshot em disco/DB | `preference_integrity` | Leitura falha na verificação de hash/JSON canônico |
| Violação WCAG AA | `a11y_contract_violation` | Checklist falha com lista de violações |
| Aceite UI sem comando versionado | `ui_command_required` / `ui_command_invalid` | Bloqueio explícito; estado da tarefa inalterado |

## 8. How (Como Realizar)

- **Módulo Python:** [`src/hydra_orch/core/preferences.py`](../../src/hydra_orch/core/preferences.py) reutiliza `ExecutionStore`, `new_id`, `redact` / `redact_text` e `ExecutionModel` / `ContractViolation` de [`model.py`](../../src/hydra_orch/model.py).
- **Evento de domínio:** [`model.py`](../../src/hydra_orch/model.py) inclui `"preference.snapshot_created"` em `RunEvent.event_type` para validação ponta a ponta via `ExecutionStore._insert_event_in_tx` e `ExecutionStore.get_events`.
- **Serialização canônica:** `canonical_json` utiliza `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`, garantindo determinismo entre processos para `preferences_hash`.
- **Verificação WCAG AA:** Implementada com matemática sRGB pura sem dependências externas, permitindo execução 100% offline na suíte marcada com `@pytest.mark.a11y`.

## 9. Examples (Exemplos)

### 9.1 Precedência e Snapshot Imutável

```python
await service.set_preference("user", "operator", "ui.theme", "light", source="explicit")
await service.set_preference("area", "area-1", "ui.theme", "solarized", source="explicit")
await service.set_preference("project", "proj-1", "ui.theme", "dark", source="explicit")

# Resolve project > area > user => "dark"
effective = await service.resolve_effective(user_id="operator", area_id="area-1", project_id="proj-1")
assert effective["ui.theme"] == "dark"

# Tentativa de inferida sobrescrever explícita é bloqueada:
# await service.set_preference("project", "proj-1", "ui.theme", "neon", source="inferred_opt_in", opt_in=True)
# -> ContractViolation("explicit_preference_precedence", ...)
```

### 9.2 Verificação de Contraste WCAG AA

```python
ratio = contrast_ratio("#eeeeee", "#141414")
assert ratio >= 4.5
checklist = validate_a11y_contract(AccessibilitySettings(reduce_motion=True))
assert checklist.passed is True
assert checklist.effective_animation_ms == 0
```

---

## GAPs

- **GAP-S18A-01 (Rotas HTTP e CLI de Preferências):** Exposição dos endpoints `/v1/control-plane/preferences*` e comandos `hydra preference` fica vinculada à etapa `T23` (`cli.py`, `server.py`, `openapi.yaml`).
- **GAP-S18A-02 (Auditoria em navegador real da futura UI):** Quando a aplicação visual (`S11`) for construída, os critérios estruturais validados aqui no contrato Python deverão ser complementados por verificação E2E com leitor de tela e inspeção DOM real em navegador.

## Glossary e Acrônimos

| Termo | Significado |
|---|---|
| `a11y` | Numerônimo para Acessibilidade (*Accessibility*) |
| `DBC-9` | Design by Contract em 9 seções normativas |
| `Preference` | Preferência tipada, versionada e escopada (`user`, `area`, `project`) |
| `PreferenceSnapshot` | Fotografia imutável e hasheada (SHA-256) das preferências efetivas de um `run` |
| `RF23 / RT23` | Requisito Funcional 23 e Requisito Técnico 23 (Preferências reversíveis e acessibilidade WCAG AA) |
| `SHA-256` | Função de hash criptográfico de 256 bits (64 caracteres hexadecimais) |
| `sRGB` | Espaço de cores padrão utilizado na fórmula de luminância relativa da W3C WCAG |
| `UI` | Interface do Usuário (*User Interface*) — consumidora estrita de read models |
| `WCAG AA` | *Web Content Accessibility Guidelines* nível AA (contraste >= 4.5:1 texto normal, >= 3.0:1 texto grande/componentes) |
