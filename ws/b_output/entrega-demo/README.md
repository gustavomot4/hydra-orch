# Artefatos publicados da demonstração

Entrega de 16/11/2026. Estes arquivos finais são versionados; os diretórios de
execução e diagnóstico que deram origem à entrega continuam locais e ignorados.

- [Vídeo MP4](Hydra-swarm-OmniRoute-demo.mp4): 85,4 segundos, 1440 × 900, sem áudio.
  Mostra configuração do OmniRoute, prompt, swarm, navegação no canvas,
  verificações concluídas e o site gerado. As esperas foram aceleradas.
- [Site institucional gerado](Horizonte-site-gerado.zip): extraia e abra
  `index.html`. Horizonte Arquitetura é uma empresa fictícia; o site não foi
  publicado na internet.
- [Bundle do frontend Hydra](Hydra-frontend.zip): contém `dist/`, com o build
  local de produção usado na demonstração. Pode ser extraído em `frontend/`.
- [Prompt inicial](prompt.txt), [registro da execução](demo-receipt.json),
  [manifesto da edição](edit-manifest.json) e
  [verificação do site](site-verification.json).
- Capturas finais: [canvas](swarm-completed.png), [interação](canvas-interaction.png),
  [conversa](completed-chat.png), [site desktop](site-desktop.png) e
  [site no celular](site-verified-mobile.png). Os arquivos `video-*.jpg` são
  quadros extraídos do MP4 publicado.
- [SHA-256 dos arquivos](SHA256SUMS.txt), incluindo o executável da raiz.

O iniciador Windows está em [`Hydra.exe`](../../../Hydra.exe), na raiz do
repositório, e suas fontes estão em `src/launcher/`. Ele usa o checkout e as
instalações locais de Python e Node. Consulte o
[manual de inicialização](../../../doc/j_manual/iniciar_windows.md).

## Evidência e pendências

A execução `cr-2fb4a7aa09` terminou com dois workers aceitos, testes e revisão de
agente, consolidando os arquivos na cópia da conversa. O coordenador usou o combo
`dev-agent-gpt`; os workers usaram `dev-rapido`, pelo executor Codex.

A auditoria adicional do site encontrou cinco ocorrências de contraste
insuficiente. O refinamento posterior `cr-4eb0a2de4a` atingiu o limite de 600
segundos e não foi aprovado nem consolidado. O vídeo e o ZIP mostram a geração
principal concluída; não apresentam esse refinamento como realizado. Não houve
teste com leitor de tela real ou com usuários.

As correções de execução do Hydra foram publicadas em `ea5c403` e `a87d039`.
A rodada final relevante teve 111 testes aprovados. Esta publicação de artefatos
não executa novamente os provedores e não acrescenta uma nova geração ao vídeo.
