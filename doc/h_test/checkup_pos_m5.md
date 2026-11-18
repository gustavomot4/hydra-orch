# Checkup pós-M5 e correções da coordenação

Data da verificação: 17/11/2026. Ambiente: Windows, Python 3.12.10, pytest 8.4.2, Vitest 2.1.9 e Playwright com backend e executores locais controlados. Sem inferência paga ou certificação de contas reais.

## Escopo entregue

- Recuperação por fast-forward da atualização do README anteriormente isolada em `codex/chat-2c6b62e5c65d443b`, seguida de revisão das afirmações sobre implementação e validação.
- Operações distintas de validação e edição no plano coordenado. Validações não iniciam workers de código e não exigem diff; o contrato de patch, checks e revisão das edições permanece obrigatório.
- Checks próprios de Vitest, TypeScript com projeto explícito, ESLint, build e documentação. Um teste Python arbitrário deixa de ser a recomendação de aceite de Markdown.
- Suíte pytest dividida por arquivo em validações, com limite por check, saída preservada em timeout e progresso persistido ao terminar cada arquivo. Teto total padrão de uma hora, mantendo limites próprios de planejamento e workers.
- Diagnóstico de aceite com código de saída, trechos redigidos e referências a logs; agregação das falhas de workers paralelos. Executável ausente recebe diagnóstico de localização/PATH, sem afirmar falha de autenticação.
- Estabilização do harness de interface: dois workers jsdom, até 15 segundos por fluxo de teste, e espera pelo estado final no E2E da pasta comum. Sem retries automáticos e sem remover asserções de comportamento.
- Atualização dos testes de migração para as versões `0001`–`0006`, incluindo tabelas/colunas de conversação, roundtrip de rollback, backup e guardas contra perda de dados.

Detalhes operacionais e limites estão no [manual de checkup](../j_manual/checkup_coordenado.md).

## Resultados

| Bloco | Resultado |
| --- | --- |
| Python: base principal | 633 cenários: 627 aprovados na rodada principal (1.232,71 s) e seis expectativas de migração corrigidas e aprovadas na revalidação do arquivo completo. |
| Python: API e integração (`test_server.py`, `test_integration.py`) | 43 aprovados; 629,25 s. |
| Python: coordenador e resolução do executável | 31 aprovados na rodada inicial; mais dois cenários de plano misto e divisão por arquivo incluídos e aprovados nas rodadas direcionadas. |
| Python: regressão do progresso de validações | 4 aprovados, incluindo plano misto, divisão por arquivo e validação sem patch. |
| Python: diagnóstico de timeout e checker Markdown | 2 aprovados. |
| Python: migrações | 19 aprovados após corrigir seis expectativas antigas de versão. As guardas de rollback e integridade continuam sendo verificadas. |
| Python: OmniRoute/PTY | 20 aprovados, 2 ignorados por opt-in live. |
| Frontend: typecheck e lint | Aprovados. |
| Frontend: `npm run test` | 70 aprovados, 18 arquivos, após estabilizar o harness. |
| Frontend: `npm run build` | Aprovado; aviso de bundle grande preservado. |
| Frontend: E2E | 12 cenários aprovados na suíte principal e o cenário de pasta comum aprovado na repetição direcionada após ajustar a espera. Um cenário opcional do kit ficou ignorado. |
| Documentação | Links locais e `git diff --check` aprovados. |
| Descoberta real de CLIs, sem inferência | Codex e Claude Code encontrados; os comandos locais de status retornaram autenticação ativa para ambos. |

A coleta final encontrou **733 testes Python**. A cobertura combinada dos blocos e revalidações totaliza **731 testes únicos aprovados e 2 ignorados por opt-in live**. Isso não representa uma única execução monolítica sem falhas: as seis falhas iniciais de migração foram corrigidas e revalidadas.

As validações foram realizadas fora de workers de IA. O bloco principal exclui os arquivos executados nos blocos separados, com logs locais em `ws/b_output/checkup_*.log` (ignorados no Git). Não somar repetições direcionadas como se fossem novos testes únicos.

## Falhas encontradas e revalidação

O teste de navegação do primeiro Vitest e, depois, um fluxo de autenticação excederam os cinco segundos originais sob carga. A rodada final usa concorrência limitada e 15 segundos por fluxo e mantém todos os 70 testes. No E2E, a resposta da pasta comum estava concluída no backend após o limite inicial da asserção; a repetição passou aguardando o estado terminal antes de conferir o texto integral.

Seis falhas Python de migração esperavam apenas versões até `0004`. O banco real preservava corretamente `0005` e `0006`. As expectativas foram atualizadas e o arquivo completo de migrações foi executado novamente, incluindo integridade, backup, rollback auditado e recusa de perda de dados.

## Avisos e limites

- Persistem avisos de depreciação de Starlette/httpx e React Router, avisos de `act(...)` em testes React e ausência de canvas completo no jsdom. O terminal e o canvas também foram exercitados em navegador real pelo E2E.
- O build avisa sobre o bundle JavaScript acima de 500 kB. Não houve mudança de empacotamento da aplicação nesta tarefa.
- A primeira tentativa local teve sessões interrompidas; logs parciais não foram considerados sucesso. Os resultados acima vêm das rodadas concluídas e das repetições explicitadas.
- O status local de autenticação não certifica disponibilidade ou comportamento de um provedor real, nem a autorização de um modelo/combo no OmniRoute. Nenhuma solicitação de inferência foi enviada para essa conferência.
- O bloco aberto de funcionalidades futuras do planejamento não especificava entregas novas. O trabalho se concentrou no checkup, documentação e nas falhas concretas de Chat/Swarm do relatório.
