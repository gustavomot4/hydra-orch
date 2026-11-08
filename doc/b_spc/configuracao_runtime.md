# Configuração de runtime — S01 / T01

## 1. Propósito

Definir a configuração tipada e a seleção de rotas antes de executar inferência ou iniciar processos. Referências: [PRD técnico](prd_tecnico.md), [plano mestre](../a_context/plano_desenvolvimento.md) e [taxonomia](../a_context/taxonomia_file_system.md).

## 2. Justificativa

Provedores habilitados implicitamente, aliases CLI convertidos em CDP e parâmetros inválidos mascaram a capacidade efetiva. Configurar uma CLI não comprova sua instalação, autenticação ou certificação.

## 3. Contrato

- `hydra`: portas válidas, `default_mode` inteiro 1/2/3, modelo preferido opcional, `inference_fallback_chain` explícita e caminhos relativos sob `.orchestrator/`. Concorrência, intervalos e timeout são positivos; reparos permitem zero.
- `execution`: driver `codex`, `claude-code`, `gemini`, `opencode` ou `aider`; modelo opcional e timeout. É configuração preparatória: a execução e a certificação serão implementadas em T04.
- `providers`: registros nomeados em `ui_cdp`, `ide_bridge`, `api_gateway` e `remote_local`. Entradas são desabilitadas por padrão; nomes são únicos entre transportes. `ssh_remote` é reservado e deriva exclusivamente de `remote_ssh_gpu`, usando sua porta local encaminhada.
- APIs usam `api_key_env`; credencial de entrada habilitada deve existir no ambiente. Endpoints aceitam HTTP(S), sem credenciais na URL. Campos desconhecidos e URLs inválidas são recusados.
- `omniroute.logical_models`: cada alias declara `primary`, fallbacks, dificuldade 1–10 e `adapter` opcional. Executor CLI e adaptador de inferência são independentes; não há conversão implícita Codex → ChatGPT CDP ou Claude Code → Claude CDP.
- A configuração padrão habilita somente o adaptador local Ollama; disponibilidade real depende de serviço/modelo instalados pelo operador. Os nomes de modelos externos no YAML são exemplos, não suporte certificado.
- Gateway desligado não é consultado, inclusive para quota. `optional` não condiciona inferência direta à saúde do gateway; `required` exige preflight antes da inicialização do runtime e da geração. Combinações contraditórias de `enabled` e `connection_mode` são erros. Inicialização automática do daemon não é suportada.
- O proxy usa o modelo resolvido do alias quando o cliente informa um identificador `hydra-*`. Um modelo concreto informado pelo cliente é preservado. Provedor solicitado explicitamente precisa ter adaptador habilitado.
- Seleção por dificuldade considera aliases elegíveis por ordem decrescente de `min_difficulty`, seguida da cadeia configurada. Sem rota, lança `provider_unavailable`; nunca inventa um adaptador `mock`.
- O endpoint de chat não executa o swarm legado: `hydra-swarm`/modo swarm retorna `422 unsupported_mode` e não é anunciado na lista de modelos. Execução de tarefas em worktree depende de M1.

## 4. Pré-condições

Validar configuração antes de criar subprocessos. Rodar testes com fixtures locais e HTTP simulado. Nenhum teste exige conta, CLI de agente ou modelo externo.

## 5. Pós-condições

Somente adaptadores habilitados são instanciados; aliases conservam a identidade do modelo. Erros de rota/dependência retornam HTTP 503 estruturado antes de abrir SSE. Quota ausente usa `unknown` e valores nulos.

## 6. Invariantes

Arquivo explícito ausente nunca causa fallback para outro arquivo. A carga explícita não contamina o cache padrão. O cache padrão acompanha o caminho resolvido da configuração. YAML exige objeto com chaves únicas; segredos não entram em exemplos versionados. Recursos externos permanecem não certificados até evidência própria.

## 7. Falhas e migração

- Configuração inválida: falhar com diagnóstico; não corrigir silenciosamente políticas obrigatórias.
- Arquivo ausente/YAML inválido: `ConfigError`; alias ausente: `UnknownAliasError`; segredo ausente: `SecretNotFoundError` durante validação.
- Gateway obrigatório indisponível: `gateway_unavailable`, sem iniciar túnel ou geração.
- Dados legados em `.hydra/`: parar execuções, guardar backup, migrar manualmente os caminhos para `.orchestrator/` e conferir integridade antes de retomar. O loader não move, apaga ou interpreta checkpoints antigos como runs novos.
- Configuração anterior com provedores implícitos: declarar as entradas necessárias em `providers`, habilitar apenas as desejadas e vincular aliases via `adapter`. Remover a antiga raiz `orchestrator`; usar `hydra` e `modes` conforme o YAML versionado. Trocar `enabled: false` + `required` por uma política consistente.

## 8. Procedimento e validação

Carregar YAML → rejeitar duplicidades → resolver referências de ambiente → validar modelos/campos/referências → registrar adaptadores habilitados → verificar rota e dependência obrigatória → gerar inferência. CLI e API compartilham o router e as mesmas regras; o serviço de tarefas será entregue nas etapas seguintes.

Testes em `tests/test_config.py`, `tests/test_router.py`, `tests/test_server.py` e `tests/test_engine.py` cobrem os contratos, a política de gateway e ausência de efeitos Git pelo chat. Retomada durável, ferramentas no proxy, roteamento via gateway e execução real de drivers permanecem fora desta entrega.

## 9. Exemplo

Configuração mínima de inferência direta; o modelo precisa existir no Ollama local:

```yaml
hydra:
  default_mode: 2
  inference_fallback_chain: [coder]
providers:
  remote_local:
    local:
      enabled: true
      base_url: http://127.0.0.1:11434
      default_model: qwen2.5-coder:7b
omniroute:
  enabled: false
  connection_mode: disabled
  logical_models:
    coder:
      primary: local/qwen2.5-coder:7b
      min_difficulty: 1
```

`hydra run "Explique esta função" --mode relay --provider coder` gera texto; não edita arquivos do projeto.

## Gaps e glossário

- **Pendências:** T04 certifica o executor; T07 entrega o serviço de tarefas; T16 expande roteamento via gateway. Não há certificação externa nesta entrega.
- **Alias:** nome lógico que referencia um modelo e sua rota declarada.
- **CDP:** transporte de automação de navegador, independente de uma CLI.
- **Preflight:** verificação obrigatória anterior ao início do runtime.
- **Runtime:** arquivos locais de estado e execução, ignorados pelo Git.
