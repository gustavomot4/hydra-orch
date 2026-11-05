# Instruções compartilhadas — hydra-orch

Estas regras valem para agentes trabalhando neste repositório. Instruções explícitas mais recentes do usuário e restrições da plataforma prevalecem.

## Contexto

- Repositório principal: https://github.com/gustavomot4/hydra-orch.git.
- Leia `docs/CONTEXTO-ORQUESTRACAO.md` antes de decisões de arquitetura; distingue achados do Alethe, implementação atual e propostas.
- Python >= 3.10, pacote em `src/hydra_orch`, testes em `tests`, configuração em `pyproject.toml` e `config.yaml`.
- O Git e o pacote Python já estão inicializados. Preserve esse histórico; não recrie o repositório ou o pacote a cada tarefa.
- Não descreva geração de texto como execução comprovada de agentes ou implementação concluída sem validar o comportamento.

## Autorização permanente de versionamento

O usuário autorizou que o agente responsável pela tarefa atualize o repositório ao iniciar e faça commit e push das alterações concluídas ao terminar, sem pedir confirmação rotineira a cada tarefa. Esta autorização vale para este projeto e pode ser alterada por instrução explícita posterior. Não concede permissão para publicar segredos, sobrescrever trabalho alheio, contornar proteções ou mudar a autenticação.

## Início de cada tarefa/prompt

1. Resolva a raiz com `git rev-parse --show-toplevel` e confirme que é o projeto esperado. Confira `git status --short --branch`, `git remote -v`, a branch atual e seu upstream.
2. Se a pasta não for um checkout Git, procure o checkout esperado antes de agir. Não execute `git init` dentro de uma subpasta de outro repositório. Só inicialize uma nova raiz se essa for a tarefa solicitada.
3. Registre alterações e commits que já existiam antes da tarefa. Preserve arquivos staged, unstaged e untracked do usuário ou de outros agentes.
4. Com checkout limpo e upstream configurado, execute `git pull --ff-only` antes de editar. Se a branch pretendida não tiver upstream, faça `git fetch origin` e examine sua relação com a branch remota antes de configurar tracking ou publicar.
5. Com alterações locais, faça fetch quando possível e avalie se é seguro atualizar; não faça pull, stash, reset, checkout ou commit automático dessas alterações para liberar a atualização. Se não puder sincronizar sem afetá-las, informe a limitação e prossiga apenas com trabalho independente do estado remoto.
6. Se o pull falhar por divergência, conflito, rede ou permissão, relate o motivo real. Não use force, rebase automático nem descarte commits para fazer o comando passar. Só altere áreas independentes quando houver contexto suficiente; deixe ações dependentes da resolução pendentes.
7. Para perguntas sem alteração de arquivos, verifique o estado e sincronize quando seguro; não crie commits vazios nem execute push sem necessidade.

## Durante a implementação

- Mantenha mudanças focadas na solicitação e documente decisões relevantes para a próxima sessão.
- Rode validações proporcionais à mudança. Para comportamento Python, use os testes relevantes (`python -m pytest tests/...`); para documentação, confira links locais e `git diff --check`.
- Não instale dependências, execute provedores pagos ou rode fluxos que alteram branches/worktrees apenas para validar uma edição documental.
- Agentes paralelos devem trabalhar em worktrees isoladas com propriedade de arquivos. Apenas o agente líder integra e faz push da tarefa; workers delegados devolvem resultados/patches sem iniciar pulls, commits ou pushes concorrentes. Uma tarefa de worker explicitamente instruída pelo líder prevalece sobre o ciclo de publicação geral.
- Nunca versionar credenciais, `.env`, bancos locais, logs, ambientes virtuais ou artefatos de execução. Inspecione conteúdo novo antes de adicioná-lo ao Git.

## Encerramento de tarefas com mudanças

1. Revise `git diff`, `git status` e os arquivos novos. Diferencie arquivos da tarefa de mudanças preexistentes.
2. Execute os checks adequados e `git diff --check`. Não alegue testes aprovados quando não foram executados. Não publique código sabidamente quebrado como tarefa concluída; em caso de bloqueio, preserve o trabalho e explique o que falta.
3. Adicione apenas arquivos ou hunks pertencentes à tarefa, usando caminhos explícitos; evite `git add .` quando houver trabalho de terceiros. Preserve o staging preexistente e não o inclua no seu commit. Se não houver forma segura de separar mudanças sobrepostas, informe o impedimento.
4. Crie um commit descritivo (`docs:`, `feat:`, `fix:`, `test:` ou `chore:`) sem solicitar confirmação rotineira.
5. Faça push normal para o upstream da branch de trabalho. Se uma nova branch de tarefa ainda não tiver upstream e a publicação estiver autorizada, use `git push -u origin <branch>`. Nunca force push nem troque de branch silenciosamente. Respeite branch protections; se exigirem PR, preserve o commit e informe o caminho necessário.
6. Se o remoto avançou, busque as alterações e examine os commits. Não sobrescreva o remoto; sincronize apenas quando puder preservar o histórico e validar o resultado. Divergência exige resolução explícita, não repetição cega do push.
7. Em erro 403/autenticação, mantenha o commit local e informe qual acesso falta. Não altere credenciais, proprietário ou remote para contornar a recusa. Um push recusado continua pendente até confirmação de sucesso.
8. Confirme o resultado com `git status --short --branch` e, após push, compare `HEAD` ao upstream. Informe hash, branch, validações e se a publicação foi concluída ou ficou pendente.

## Alcance entre ferramentas

`AGENTS.md` é a fonte única desta política. `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/project.mdc` e `.windsurf/rules/project.md` encaminham para ela. Ao atualizar a política, mantenha os encaminhamentos consistentes.

Ferramentas que não carregam esses arquivos automaticamente devem receber este arquivo como contexto explícito. Estes arquivos são instruções para agentes com acesso ao checkout, não hooks que executam Git em qualquer chat. Restrições do cliente, sessões sem filesystem/Git e permissões do GitHub continuam valendo.
