# Processo de construção

Este roteiro é uma proposta incremental. O [protótipo visual no Figma](d_figma.md) foi criado; os gates de implementação e integração abaixo permanecem pendentes. O protótipo não comprova execução real de agentes ou terminais.

| Etapa | Trabalho e dependência | Entrega / gate de saída |
| --- | --- | --- |
| 1. Reconciliação | Ler PRDs, stack, OpenAPI e código real; mapear UI01–UI11 para RF/RT/tasks existentes, em especial sessões RT16, acessibilidade RF23, HITL RF27, voz RF36 e Computer Use RF37 | Matriz existente/proposto/ausente revisada; lacunas de PTY, anexos, emulação e agendas registradas no backlog sem renumerar contratos |
| 2. Contratos | Definir capacidades por host, identidade de sessão, anexos e PTY; revisar auth, erros, cancelamento e replay | Schemas e testes de contrato com fixtures, incluindo falha e reconexão; atualizar OpenAPI apenas para decisões aprovadas |
| 3. Fundação visual | Usar stack do projeto; criar tokens, shell, árvore, abas, splits e compositor | Telas com fixtures claramente marcadas; revisão contra o [design atual no Figma](d_figma.md) e as imagens de referência, em desktop e mobile; teclado e contraste aprovados |
| 4. Chat real | Conectar histórico, SSE, envio, parada, HITL e cards de workers | Run de executor falso produz eventos verificáveis; replay sem duplicação; nenhum sucesso inferido de texto |
| 5. Terminal real | Escolher biblioteca de renderização e bridge PTY; provar Windows e Unix separadamente | Unicode/ANSI, resize, interrupção, exit e reconexão demonstrados; ciclo de processo sem órfãos |
| 6. Arquivos e navegação | Implementar anexos, explorer, busca global e previews | Arquivo local/remoto no agente correto; rejeição de caminho indevido; PDF/imagem/Markdown e erro de upload exercitados |
| 7. Uso e contas | Integrar métricas e capabilities de conta | Quota com fonte/reset, unknown/stale; troca suportada sem expor credencial nem interromper silenciosamente run |
| 8. Automação | Implementar scheduler persistente, fuso, política de sobreposição e retry | Testar reinício, horário de verão, máquina offline, execução perdida e disparo duplicado; histórico com vínculo ao run |
| 9. Ditado | Integrar microfone e STT com revisão do texto | Cancelar captura, recuperar permissão negada e editar texto antes de enviar; distinguir ditado simples da voz duplex prevista em RF36 |
| 10. Emulação e Computer Use | Bridges por SO/dispositivo, seleção de alvo, evidência visual e HITL | iOS em host compatível, Android com bridge próprio; ciclo observar/agir/verificar e parada efetiva; capacidades não certificadas ficam indisponíveis |
| 11. Integração e entrega | Consolidar E2E, acessibilidade, desempenho, documentação e empacotamento | Build/lint/typecheck e testes adequados aprovados; manual com limitações reais por SO e matriz de recursos disponíveis |

## Sequenciamento

Primeiro marco: shell + chat + terminal em uma máquina, com executor falso e contratos reais. Segundo: arquivos, busca, previews, métricas e contas suportadas. Terceiro: agendas e ditado. Quarto: dispositivos, Computer Use e acesso remoto/mobile. As fases avançadas fazem parte do escopo desejado, mas dependem de bridges e serviços além do frontend.

Não fixar prazo sem estimar essas integrações. Não escolher versão de dependência apenas por este documento: confrontar a stack canônica com versões suportadas e registrar eventual atualização antes de instalar.

## Cenário integrado de aceite

1. Selecionar host, projeto e workspace; abrir chat do coordenador e terminal ao lado.
2. Anexar imagem e arquivo por drag/drop e por teclado; revisar e enviar.
3. Receber eventos de worker real ou fixture explicitamente identificada; navegar ao worker e voltar sem perder rascunho.
4. Abrir Markdown, PDF e imagem gerados em painel adjacente.
5. Derrubar e restaurar conexão; comprovar replay, deduplicação e ausência de reenvio automático.
6. Conferir consumo desconhecido e conhecido, reset e conta escolhida para a próxima execução.
7. Agendar tarefa de teste, reiniciar serviço e verificar um único disparo por ocorrência.
8. Ditar e revisar texto; testar permissão negada e cancelamento.
9. No host certificado, abrir emulador e Computer Use, observar ação e resultado e testar interrupção/HITL.
10. Repetir navegação essencial por teclado, leitor de tela, viewport estreito e zoom 200%.

## Evidência necessária para concluir cada incremento

Registrar ambiente, commit, capabilities, cenário, resultado esperado/observado e limitações. Testes herméticos devem usar executor falso e fixtures, sem provedores pagos. Integrações reais são verificadas separadamente e não podem ser anunciadas como aprovadas por mock. Guardar capturas/logs de runtime fora do Git conforme a política do projeto; versionar somente fixtures sanitizadas deliberadas.
