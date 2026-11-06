# arquitetura_hydra_omniroute_ui — Fronteiras Arquiteturais do hydra-orch

**Identificador Formal:** `arquitetura_hydra_omniroute_ui.md`
**Caminho Canônico:** `doc/b_spc/arquitetura_hydra_omniroute_ui.md`
**Versão:** `v01_00_0000`
**Status:** `APROVADO / NORMATIVO`
**Autoridade:** Arquitetura do hydra-orch, delimitando responsabilidades entre control plane, gateway OmniRoute opcional, executores e UI.
**Escopo:** Interfaces de control plane, desacoplamento de inferência e ciclo de vida de tarefas.

---

## Propósito

Definir uma arquitetura em que o **Hydra** seja o control plane de engenharia de software, o **OmniRoute** seja um gateway opcional de inferência e a futura interface visual seja uma consumidora da API do Hydra. Esta especificação não declara que uma UI, integração de gateway ou executor real já esteja concluído.

## Fronteiras de responsabilidade

```text
Interface visual (web, desktop ou mobile)
  -> consulta projetos, execuções, worktrees, diffs, quotas e decisões
Hydra control plane
  -> planeja, cria tarefas, isola workspace, valida, integra e persiste estado
Executores de agentes
  -> Codex CLI, Claude Code, Gemini CLI, OpenCode, Aider, IDE bridge ou agente local
OmniRoute opcional
  -> escolhe modelo/provedor, aplica fallback e expõe quota/custo
Git e ambientes de execução
  -> branches, worktrees, testes, artefatos e integração
```

O OmniRoute não substitui o executor de engenharia: uma resposta de modelo não comprova edição, testes ou merge. A interface visual não decide resultados; ela mostra o estado persistido e envia comandos explícitos ao Hydra.

## Modos de instalação

| Perfil | Componentes | Uso |
| --- | --- | --- |
| Direto | Hydra + uma CLI autenticada | Primeiro uso e desenvolvimento local simples |
| Gateway | Hydra + OmniRoute + executores | Fallback, quota, múltiplas contas e modelos |
| Remoto | Perfil Gateway + host SSH | Worktrees e agentes no PC forte ou servidor próprio |
| Visual | Qualquer perfil + cliente UI | Operação, inspeção de diffs e aprovação humana |

O `config.yaml` usa `omniroute.enabled` e `omniroute.connection_mode` para diferenciar gateway desligado, opcional ou obrigatório. O Hydra deve falhar de forma clara quando o modo `required` estiver configurado e o gateway não estiver disponível.

## Interface visual planejada

A interface deve ser construída contra endpoints versionados do control plane. O primeiro contrato disponível é `GET /v1/control-plane/bootstrap`, que informa capacidades configuradas e marca explicitamente read models ainda não implementados.

As telas iniciais são:

1. **Projetos e execuções:** objetivo, branch base, estado e orçamento.
2. **Fila de tarefas:** dependências, responsável, provedor, executor e tentativa atual.
3. **Worktrees e diffs:** arquivos modificados, checks, revisão, aprovação, descarte e integração.
4. **Provedores e quota:** gateway ativo, contas elegíveis, fallback escolhido e motivo.
5. **Eventos e checkpoints:** progresso, bloqueios, falhas, retomadas e artefatos.

Nenhuma tela deve inferir sucesso a partir de texto do agente. As ações de aprovar, integrar, interromper e repetir devem depender do estado persistido em `TaskResult` e nos eventos.

## Sequência de entrega

1. Implementar os contratos de execução e uma persistência local por run/tarefa/tentativa.
2. Conectar CLI e API às engines reais e remover caminhos de sucesso simulado.
3. Expor read models de projetos, execuções, tarefas, worktrees, diffs e quotas.
4. Criar um cliente web separado que consuma somente esses contratos.
5. Adicionar desktop/mobile somente depois de estabilizar API, autenticação e reconexão.

## Decisões de produto

- O OmniRoute é integração opcional, não cópia de código nem requisito absoluto para iniciar o Hydra.
- Orca e Claude Squad são referências de experiência de operação; o Hydra não precisa reproduzir seus terminais ou aplicativos antes de estabilizar a execução verificável.
- Alethe é referência para briefs, resultados, waves e gates de integração.
- A unidade de verdade do Hydra é o artefato verificável: patch, commit, check executado, evento persistido e decisão de integração.
