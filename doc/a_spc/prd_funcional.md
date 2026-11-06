# PRD funcional

Status: especificação proposta para implementação. Base: revisão registrada no [plano](plano_desenvolvimento.md). Não representa funcionalidades já certificadas. Este documento detalha o comportamento esperado; o [PRD técnico](prd_tecnico.md) define sua realização.

## 1. Propósito

Permitir que um desenvolvedor delegue tarefas de engenharia, acompanhe execução e decida sobre resultados apoiado em arquivos, patches e checks verificáveis.

## 2. Justificativa e usuários

O operador configura projeto, executor e limites; o revisor aceita ou rejeita resultados e integração. No MVP, ambos são o mesmo usuário local. O agente cliente consome inferência ou comandos explícitos de execução. O executor é um sistema externo, sem autoridade para aprovar seu próprio resultado.

Valor esperado: reduzir coordenação manual mantendo rastreabilidade de mudanças e recuperação de falhas. Medir proporção de tarefas aceitas com checks, falhas que preservam trabalho e retomadas sem efeitos duplicados; metas de latência e produtividade dependem de baseline posterior.

## 3. Contrato funcional

### Escopo

MVP: um operador, repositório local, tarefa delimitada, um executor CLI certificado, resultado revisável e integração em branch dedicada. Inclui listar, consultar, cancelar e revisar execução pela CLI/API mínima. Gateway é opcional.

Expansão: swarm com dependências, relay, persistência entre tentativas, quota, reparo, API completa, UI e transportes remotos. Multiusuário, publicação automática irrestrita e garantia universal de compatibilidade com provedores ficam fora do primeiro marco.

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

### Jornadas

1. Operador seleciona projeto/base, executor e orçamento; informa tarefa, arquivos e checks.
2. Hydra valida configuração e contrato, registra run e prepara worktree.
3. Executor trabalha; operador acompanha eventos e pode cancelar.
4. Hydra coleta diff e executa checks; resultado fica disponível para revisão.
5. Revisor aceita ou rejeita; integração aceita é validada separadamente e gera evidência.

Falha de executor, check ou merge interrompe o avanço correspondente e preserva artefatos. Repetir cria uma tentativa nova vinculada à anterior. Em swarm, tarefas independentes podem continuar conforme política do run; dependentes de tarefa rejeitada ficam bloqueadas.

### Regras de negócio

- RB01: código de processo zero e texto `DONE` não bastam para aceite.
- RB02: simulação deve aparecer como simulação e não pode ser integrada como trabalho real.
- RB03: tarefa de implementação exige patch ou justificativa verificável de ausência de mudança; revisão pode entregar relatório.
- RB04: aceite de tarefa não equivale a integração concluída; integração requer checks da combinação.
- RB05: permissões deste checkout não autorizam publicação em todos os projetos operados pelo produto.
- RB06: espera, fallback e reparo obedecem a orçamento; custo desconhecido permanece desconhecido.

## 4. Pré-condições

Projeto acessível, base Git existente, configuração válida e executor com capacidade declarada. Credenciais ficam no mecanismo do provedor ou em referência de ambiente, sem entrar na spec. Certificação real é separada dos testes offline.

## 5. Pós-condições

Toda execução consultável possui estado e evidência, inclusive falha/cancelamento. Sucesso significa tarefas obrigatórias aceitas e integração validada quando solicitada. Uma run apenas de revisão pode concluir sem merge. Critérios não atendidos impedem sucesso.

## 6. Invariantes

Preservar trabalho do operador, separar inferência de comandos de execução, manter histórico de tentativas e decisões, não ocultar indisponibilidade. A UI deve oferecer navegação por teclado, rótulos e estados textuais além de cor.

## 7. Falhas

CLI ausente: corrigir configuração e repetir. Quota ausente: mostrar desconhecido. Conflito: preservar branch e pedir resolução. Perda de conexão: consultar run existente. Crash após ferramenta: reconciliar efeitos antes de repetir. Arquivo fora do escopo: rejeitar resultado e reter diff.

## 8. Desenvolvimento por tasks

Cada RF gera tasks na etapa indicada do [plano](plano_desenvolvimento.md). Cada task deve conter ID, RF/RT relacionado, dependências, arquivos próprios, exemplo de entrada, saída esperada e teste negativo. O [PRD técnico](prd_tecnico.md) fornece a primeira decomposição implementável. RF não pode ser marcado concluído apenas porque sua documentação foi criada.

## 9. Exemplo de aceite

Dada uma função com teste falhando em repo temporário, quando o executor corrige somente o arquivo permitido e o check passa, então a tarefa fica pronta para revisão. Quando aceita e combinada numa branch de integração com checks aprovados, o run conclui. Se o processo apenas imprime uma correção, a tarefa não é aceita.
