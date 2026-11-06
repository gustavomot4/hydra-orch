# prd_funcional — Especificação Funcional do hydra-orch

**Identificador Formal:** `prd_funcional.md`
**Caminho Canônico:** `doc/b_spc/prd_funcional.md`
**Versão:** `v01_00_0000`
**Status:** `PROPOSTO / EM DESENVOLVIMENTO`
**Autoridade:** Arquitetura do hydra-orch alinhada a `taxonomia_file_system.md` e [`plano_desenvolvimento.md`](../a_context/plano_desenvolvimento.md).
**Escopo:** Requisitos funcionais (RF01 a RF25), jornadas de usuário, regras de negócio e critérios de aceite.

**Estado das capacidades:** RF01–RF15 formam o núcleo e a expansão já especificados; RF16–RF25 formalizam a visão ampliada e permanecem `PROPOSTO / NÃO IMPLEMENTADO` até seus gates técnicos e certificações.

---

Status: especificação proposta para implementação. Base: revisão registrada no [plano](../a_context/plano_desenvolvimento.md). Não representa funcionalidades já certificadas. Este documento detalha o comportamento esperado; o [PRD técnico](prd_tecnico.md) define sua realização.

## 1. Propósito

Permitir que um usuário organize áreas de trabalho, projetos e repositórios, escolha ou componha perfis de agentes e acompanhe tarefas de engenharia por uma interface visual e pelas superfícies CLI/API. O Hydra deve coordenar inferência, executores, sessões, evidências e decisões apoiado em arquivos, patches e checks verificáveis, sem transformar saída textual em prova de execução.

## 2. Justificativa e usuários

O operador visual ou terminal configura áreas, projeto, repositórios, perfil de execução e limites; o revisor aceita ou rejeita resultados e integração. No MVP, ambos são o mesmo usuário local. O agente cliente consome inferência ou comandos explícitos de execução. O executor é um sistema externo, sem autoridade para aprovar seu próprio resultado. Em fases posteriores, o usuário poderá acompanhar sessões e threads de múltiplos agentes, revisar memória e autorizar recursos descobertos ou extensões.

Valor esperado: reduzir coordenação manual mantendo rastreabilidade de mudanças, decisões e recuperação de falhas. Medir proporção de tarefas aceitas com checks, falhas que preservam trabalho, reconexões sem perda de eventos e retomadas sem efeitos duplicados; metas de latência, custo e produtividade dependem de baseline posterior.

## 3. Contrato funcional

### Escopo

MVP (V0): um operador, uma área/projeto local, um repositório, tarefa delimitada, um executor CLI selecionado explicitamente, resultado revisável e integração em branch dedicada. Inclui listar, consultar, cancelar e revisar execução pela CLI/API mínima. Gateway é opcional. A UI pode acompanhar o MVP somente quando consumir estado persistido e enviar os mesmos comandos autorizados da CLI/API.

Roadmap de produto: V1 acrescenta control plane visual; V2 acrescenta áreas, projetos, múltiplos repositórios e perfis combináveis; V3 acrescenta coordenação, threads e seleção adaptativa; V4 acrescenta memória consentida, discovery, extensões, personalização, acessibilidade ampliada e transportes certificados. Multiusuário, publicação automática irrestrita e garantia universal de compatibilidade com provedores ficam fora do primeiro marco.

| ID | Requisito | Aceite observável | Etapa |
| --- | --- | --- | --- |
| RF01 | Cadastrar projeto por raiz Git e selecionar base | Raiz inválida é recusada; SHA base é exibido e preservado | S01/S05 |
| RF02 | Configurar executor, modelo, modo e limites | Config inválida falha antes do processo; gateway desligado permite modo direto | S01 |
| RF03 | Submeter objetivo com escopo e critérios de aceite | Retorna run ID; repetição com mesma chave/payload retorna mesmo run | S02/S03/M1 |
| RF04 | Executar tarefa em workspace isolado | Diff atribuído à tentativa; ausência de CLI é erro, nunca sucesso simulado | S04/S05 |
| RF05 | Acompanhar progresso e consultar evidências | Exibe estado, tentativa, checks, diff e motivo de falha, inclusive após reinício | S03/M1/S10 |
| RF06 | Cancelar execução | Confirma término do processo/descendentes ou informa falha de cancelamento; preserva arquivos | S04/M1 |
| RF07 | Aceitar ou rejeitar resultado | Exige versão atual e checks obrigatórios; rejeição mantém evidência | S05/M1 |
| RF08 | Integrar resultados aceitos | Valida combinação em branch dedicada; conflito não altera branch do operador | S05 |
| RF09 | Planejar tarefas com dependências e executar swarm | Ciclo é recusado; dependente aguarda aceite; concorrência respeita limite | S06 |
| RF10 | Retomar ou trocar executor após interrupção | Mantém instruções e efeitos comprovados; efeito ambíguo bloqueia repetição automática | S07 |
| RF11 | Consultar quota e escolher rota elegível | Informa origem/frescor; desconhecido não aparece como 100% disponível | S08 |
| RF12 | Solicitar reparação limitada | Nova tentativa aplica mudança e repete checks; orçamento esgotado termina com falha | S09 |
| RF13 | Operar interface visual | UI mostra estado persistido e reconecta pelo cursor; comandos seguem mesmas regras da CLI | S10/S11 |
| RF14 | Usar SSH/IDE/CDP conforme capacidade certificada | Alvo incorreto é recusado; inferência não é anunciada como execução de ferramentas | S12 |
| RF15 | Exportar evidência e descartar runtime | Exportação redigida; descarte explícito não remove trabalho sem retenção comprovada | S13 |
| RF16 | Gerenciar áreas de trabalho, projetos e múltiplos repositórios | Raiz, branch, SHA, escopo e autorização de cada repositório são exibidos; acesso implícito é recusado; proposto/não implementado | V2 / S10+ |
| RF17 | Criar perfil combinando agente, modelo, executor, skills, MCP e memória | Perfil mostra capabilities, origem, versão, permissões e limitações; combinação inválida falha antes da execução; proposto/não implementado | V2 / S01–S03 |
| RF18 | Exibir sessões e threads multiagente | Cada sessão/thread possui identidade, agente, estado, eventos e relação de origem; visibilidade não implica swarm implementado; proposto/não implementado | V3 / S06–S07 |
| RF19 | Exibir observabilidade operacional | Fila, estado, duração, tokens e custo são vinculados ao run; valor ausente aparece como `unknown`/`stale`, nunca como zero inventado; proposto/não implementado | V1/V3 / S03/S08/S10 |
| RF20 | Selecionar rota adaptativamente | Hydra registra candidatos, motivo, capabilities, fallback e origem da decisão; OmniRouter é opcional; proposto/não implementado | V3 / S08 |
| RF21 | Persistir memória adaptativa com consentimento e escopo | Memória só é gravada após consentimento; escopo, autor, versão, retenção e revogação são consultáveis; não é confundida com checkpoint; proposto/não implementado | V4 / gate de segurança |
| RF22 | Descobrir skills, MCPs, memórias e sessões locais de forma controlada | Discovery é opt-in, limitado a raízes autorizadas, registra origem/hash e não ativa recursos automaticamente; proposto/não implementado | V4 / gate de proveniência |
| RF23 | Personalizar interface, comportamento e acessibilidade | Preferências são escopadas e reversíveis; UI funciona por teclado, possui labels, estados textuais e não depende apenas de cor; proposto/não implementado | V1/V4 / S11 |
| RF24 | Instalar e operar extensões/plugins | Plugin declara origem, versão, permissões e capabilities; instalação requer consentimento e revogação impede novos efeitos; proposto/não implementado | V4 / gate de extensão |
| RF25 | Usar transportes locais/remotos certificados | Cada transporte expõe capabilities declaradas; alvo, identidade, healthcheck, autorização e falhas são verificáveis; proposto/não implementado | V4 / S12–S13 |

### Jornadas

1. Operador seleciona projeto/base, executor e orçamento; informa tarefa, arquivos e checks.
2. Hydra valida configuração e contrato, registra run e prepara worktree.
3. Executor trabalha; operador acompanha eventos e pode cancelar.
4. Hydra coleta diff e executa checks; resultado fica disponível para revisão.
5. Revisor aceita ou rejeita; integração aceita é validada separadamente e gera evidência.
6. Na superfície visual, o usuário pode selecionar área, projeto, repositórios e perfil de execução; a UI apresenta o snapshot efetivo antes de iniciar.
7. Em fases propostas, o usuário acompanha sessões/threads, fila, agente/modelo, duração, tokens e custo; métricas ausentes aparecem como desconhecidas.
8. Discovery, memória e extensões apresentam origem, permissões e pedido de consentimento antes de qualquer ativação ou persistência.

Falha de executor, check ou merge interrompe o avanço correspondente e preserva artefatos. Repetir cria uma tentativa nova vinculada à anterior. Em swarm, tarefas independentes podem continuar conforme política do run; dependentes de tarefa rejeitada ficam bloqueadas. Essas jornadas ampliadas permanecem propostas até suas etapas e gates.

### Regras de negócio

- RB01: código de processo zero e texto `DONE` não bastam para aceite.
- RB02: simulação deve aparecer como simulação e não pode ser integrada como trabalho real.
- RB03: tarefa de implementação exige patch ou justificativa verificável de ausência de mudança; revisão pode entregar relatório.
- RB04: aceite de tarefa não equivale a integração concluída; integração requer checks da combinação.
- RB05: permissões deste checkout não autorizam publicação em todos os projetos operados pelo produto.
- RB06: espera, fallback e reparo obedecem a orçamento; custo desconhecido permanece desconhecido.
- RB07: recursos descobertos localmente são não confiáveis até validação de origem, hash, capabilities, escopo e consentimento; existência no filesystem não autoriza ativação.
- RB08: memória persistente é opt-in, escopada e revogável; secrets e PII não entram em memória, eventos, prompts ou exportações sem política explícita.
- RB09: plugin, skill, MCP e transporte precisam declarar permissões e capabilities; incompatibilidade ou revogação bloqueia novos efeitos.
- RB10: a UI mostra decisões e estado persistido, mas não aprova, integra ou transforma texto em evidência sem comando e gate correspondentes.

## 4. Pré-condições

Projeto acessível, base Git existente, configuração válida e executor com capacidade declarada. Credenciais ficam no mecanismo do provedor ou em referência de ambiente, sem entrar na spec. Certificação real é separada dos testes offline. Para RF16–RF25, áreas, repositórios, agentes, perfis, recursos descobertos, memória e extensões precisam de escopo e autorização explícitos; nenhum recurso é ativado por descoberta implícita.

## 5. Pós-condições

Toda execução consultável possui estado e evidência, inclusive falha/cancelamento. Sucesso significa tarefas obrigatórias aceitas e integração validada quando solicitada. Uma run apenas de revisão pode concluir sem merge. Critérios não atendidos impedem sucesso.

## 6. Invariantes

Preservar trabalho do operador, separar inferência de comandos de execução, manter histórico de tentativas e decisões, não ocultar indisponibilidade. A UI deve oferecer navegação por teclado, foco visível, rótulos/roles, estados textuais além de cor, leitura por tecnologia assistiva, contraste e opção de redução de movimento. Checkpoint de execução não é memória adaptativa; memória requer consentimento, escopo, retenção e revogação.

## 7. Falhas

CLI ausente: corrigir configuração e repetir. Quota ausente: mostrar desconhecido. Conflito: preservar branch e pedir resolução. Perda de conexão: consultar run existente. Crash após ferramenta: reconciliar efeitos antes de repetir. Arquivo fora do escopo: rejeitar resultado e reter diff. Discovery fora da raiz, recurso conflitante, memória sem consentimento, thread perdida ou extensão incompatível: não ativar, não persistir efeitos e registrar a causa.

## 8. Desenvolvimento por tasks

Cada RF gera tasks na etapa indicada do [plano](../a_context/plano_desenvolvimento.md). Cada task deve conter ID, RF/RT relacionado, slice V0–V4, dependências, arquivos próprios, exemplo de entrada, saída esperada, evidência, teste negativo e status `proposto/não implementado` quando a capacidade ainda não tiver gate concluído. O [PRD técnico](prd_tecnico.md) fornece a primeira decomposição implementável. RF não pode ser marcado concluído apenas porque sua documentação foi criada.

A rastreabilidade mínima é:

```text
RF -> slice -> etapa S/M -> task técnica -> evidência -> caso negativo
```

Para RF16–RF25, as tasks futuras devem cobrir autorização, proveniência, consentimento, revogação, reconexão, acessibilidade e isolamento antes de anunciar a capacidade. O contrato técnico, o modelo de dados e a arquitetura precisam ser atualizados em uma etapa documental própria antes da implementação dessas entidades.

## 9. Exemplos de aceite

**Núcleo verificável:** dada uma função com teste falhando em repo temporário, quando o executor corrige somente o arquivo permitido e o check passa, então a tarefa fica pronta para revisão. Quando aceita e combinada numa branch de integração com checks aprovados, o run conclui. Se o processo apenas imprime uma correção, a tarefa não é aceita.

**Perfil e observabilidade propostos:** dada uma tarefa em uma área autorizada, quando o usuário seleciona um perfil de agente/modelo/executor, então o Hydra exibe capabilities, origem, versão, permissões e limites antes da execução. Fila, duração, tokens ou custo sem fonte aparecem como `unknown`/`stale`; nenhum valor é inventado.

**Memória e discovery propostos:** dada uma preferência do usuário, quando o Hydra solicita consentimento explícito e o usuário aprova, então a memória registra escopo, versão, origem, retenção e revogação. Um item descoberto fora da raiz autorizada, com hash conflitante ou sem capability conhecida, não é ativado.

**Sessões e extensões propostas:** dada uma execução com threads, quando a conexão cai, o Hydra reconcilia eventos por cursor e deduplica sem declarar conclusão prematura. Uma extensão sem manifesto compatível, permissão ou confiança não inicia nem produz efeitos.
