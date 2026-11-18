---
version: alpha
name: Hydra
description: Mesa livre de agentes com base preta e detalhes laranja
colors:
  primary: "#ffab66"
  on-primary: "#28170b"
  surface: "#202020"
  on-surface: "#e8e8e8"
  muted: "#b4b4b4"
  border-control: "#767676"
  focus: "#ffab66"
  danger: "#ffaaa1"
  on-danger: "#28170b"
typography:
  title:
    fontFamily: "Inter"
    fontSize: 1.75rem
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Inter"
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: "JetBrains Mono"
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
---

# Hydra — sistema visual

Direção escolhida pelo dono em 15/11/2026: composição A (canvas livre e conversa/detalhe lateral) com o laranja da proposta C. Calibração posterior explícita: “exagerou no laranja, o principal é preto ainda”. Preto e cinza neutro dominam as superfícies; o laranja fica em ações, seleção e detalhes. Escolha direta do dono, sem juízo externo.

## Identidade e estrutura

Hydra aproxima o operador do trabalho dos agentes: pedido, responsáveis, atividade e resultado. A navegação mostra nomes completos. A Área de trabalho é o destino principal para acompanhar; Novo chat inicia pedidos e Alterações concentra revisão. Infraestrutura técnica fica recolhida. Logo existente preservado.

## Compactação aprovada — 15/11/2026

O dono aprovou integralmente as três vistas de compactação e autorizou a construção. A composição usa navegação por projeto pai com seções recolhíveis, cabeçalhos curtos, painéis ajustáveis/ocultáveis e listas de modelos com prévias de três itens. Remover os atalhos predefinidos do chat. Adicionar pasta abre o seletor nativo diretamente no desktop. Modelo e conexão permanecem junto do compositor. A árvore compartilha pais reais entre navegação e escolha do trabalho.

Tokens de tamanho: interface compacta 14px, confortável 16px e ampla 18px na escala de 100%; escala configurável de 80 a 120% aplicada ao tamanho raiz em unidades relativas ao padrão do navegador. Texto de conversa 12–24px e terminal 10–24px independentes; conversa focada com limite de 800px ou expandida. No desktop compacto, linhas de navegação de 32px, controles de 32px, cabeçalhos com 8px de respiro; confortável 36px/12px e ampla 44px/16px. Textos auxiliares conservam piso de 12px. Divisores têm linha visual de 1px e área de interação de 24px no mouse, 44px no toque. Alvos de toque continuam com pelo menos 44px. Detalhe lateral entre 260 e 640px; divisão principal entre 25 e 75%. Layout salva preferências localmente e permite restaurar os tamanhos sem apagar conversas ou fechar sessões.

Tab aceita somente conclusão visível; menus têm precedência. Histórico por projeto/conversa preserva rascunho e só usa setas nos limites do campo. Sugestões contextuais são somente texto, dispensáveis e não enviam pedidos nem executam ferramentas automaticamente. Nenhuma inferência recorrente é habilitada sem orçamento definido.

## Tokens

Fonte canônica: `frontend/src/style/tokens.css`. Tipografia Inter para interface e JetBrains Mono apenas para código, logs e identificadores. Corpo 16px no canvas; informações auxiliares a partir de 12px. Espaçamento em passos de 4px, raios de 8/12/16px; alvos de 44px nas ações novas.

| Token | Cor | Uso |
| --- | --- | --- |
| `--bg-main` | #141414 | Fundo preto principal |
| `--bg-rail` | #181818 | Trilho superior de abas e cabeçalhos discretos entre fundo e navegação |
| `--bg-sidebar` | #1c1c1c | Navegação em cinza escuro neutro |
| `--bg-surface` | #202020 | Cards e painéis elevados |
| `--bg-hover` | #282828 | Hover e agrupamentos |
| `--border` | #767676 | Controles e limites de superfícies, mínimo 3:1 sobre o hover |
| `--canvas-dot` | #454545 | Grade pontilhada discreta de orientação espacial na Área de trabalho |
| `--text-primary` | #e8e8e8 | Texto principal |
| `--text-muted` | #b4b4b4 | Texto auxiliar |
| `--accent` | #ffab66 | Ação principal, seleção, marca e foco |
| `--accent-hover` | #ffc18c | Realce de ponteiro fino na ação principal mantendo texto escuro legível |
| `--accent-soft` | #33251c | Pequenas áreas de seleção |
| `--btn-primary-bg` | #ffab66 | Fundo da ação primária |
| `--btn-primary-text` | #28170b | Texto escuro sobre ação primária (contraste 9,26:1) |
| `--status-success` | #8ed8b0 | Conclusão verificada |
| `--status-warning` | #f6cb79 | Espera ou atenção |
| `--status-error` | #ffaaa1 | Falha |
| `--status-info` | #8bcfe0 | Trabalho em andamento |

Velaturas de diálogos modais usam preto translúcido (#000000) para isolar foco sem alterar a paleta de superfície; menus flutuantes sobre o canvas usam sombra escura discreta (#160b08) restrita à elevação.

## Área de trabalho

Canvas com fundo pontilhado, pan por arrasto do fundo, zoom limitado, enquadrar, organizar e minimapa. Cards podem ser reposicionados e conservam a posição por trabalho. Seleção abre detalhe lateral no desktop; em telas pequenas, lista e detalhe em fluxo vertical. Lista é alternativa sem arrasto e sem zoom. Navegação por teclado tem ações explícitas para mover/enquadrar.

No mundo espacial, uma base lógica de 16px é ampliada junto com toda a geometria por um fator medido em `rem`: aumentar a fonte do navegador amplia cards, rótulos e portas juntos, sem cortar o conteúdo. O mapa continua navegável por pan, enquadramento e teclado; a lista oferece a alternativa em fluxo.

Dados vêm das conversas e execuções persistidas. Relações mostram delegação, dependência e revisão com proveniência. Um worker em execução não recebe mensagens arbitrárias pelo canvas: a conversa continua pelo chat canônico. Não anunciar comunicação direta entre workers nem criar eventos ou revisores fictícios. Ausência de registro aparece como ausência.

## Do's and Don'ts

- Inter é mantida porque preserva a continuidade da interface existente e oferece leitura consistente de português em telas operacionais.
- JetBrains Mono é restrita a código, logs e identificadores técnicos porque preserva alinhamento tabular sem virar enfeite.
- Laranja identifica a ação e a seleção porque foi a escolha explícita do dono; estados usam outras cores acompanhadas de texto e ícone.
- Preto continua principal. Não pintar fundos, sidebar ou cards de marrom, nem usar degradês extensos em laranja.
- Mostrar ação e último evento, sem gráficos ou porcentagens não observados.
- Foco visível, contraste mínimo AA, alternativa ao arrasto, redução de movimento e modo de alto contraste são parte da implementação.

## Conversa e início — correção de 15/11/2026

Conversa tem cabeçalho compacto, histórico com rolagem e compositor sempre disponível na parte inferior da área útil. Modelo, combo e modo ficam junto do compositor, com diálogo acessível para alterar a configuração dos próximos envios. Em altura até 480px, a composição inteira volta ao fluxo da página. Mensagens do usuário usam superfície cinza discreta e largura pelo conteúdo; respostas do agente têm leitura editorial sem caixa, com Markdown seguro, títulos, subtítulos, listas, tabelas e código. Atividade aparece em cinza claro e detalhes recolhíveis, separada da resposta.

Novo chat apresenta o compositor primeiro. Pastas já cadastradas são escolhidas em árvore/busca com caminhos para distinguir nomes; adicionar pasta abre diretamente o Explorer no desktop, com entrada de caminho em navegadores sem integração nativa. Agente, conexão e modelo usam controles compactos com a seleção atual visível; opções avançadas abrem um diálogo. Atalhos de prompts predefinidos foram retirados por solicitação do dono; conclusão por Tab aparece dentro do campo. A direção segue o pedido explícito de familiaridade com Codex e Claude Code; não é uma nova escolha de marca.

O arrasto funciona no corpo do card, preservando clique para abrir detalhes e alça com setas para teclado. Eventos autenticados atualizam o mapa sem aguardar o polling de recuperação. Subagentes nativos são registros observados do protocolo da CLI, não execuções gerenciadas pelo RunService; mostrar essa origem nos detalhes. Não inferir delegação pela resposta textual nem habilitar ferramentas ou permissões novas para preencher o mapa.

Referências primárias consultadas para interação e eventos: [Claude Code interativo](https://code.claude.com/docs/en/interactive-mode), [seleção de modelo](https://code.claude.com/docs/en/model-config), [eventos Codex exec](https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs) e [mensagens de tarefas Claude](https://code.claude.com/docs/en/agent-sdk/typescript#sdktaskstartedmessage). As escolhas de composição são adaptação ao Hydra, não uma alegação de equivalência entre os produtos.

## Acompanhamento do trabalho coordenado

Conversa e Área de trabalho distinguem edição por agente de verificação local. Validações mostram Hydra como executor, checks observados, duração e saída registrada; não recebem revisão de agente fictícia. Planos mistos conservam ambas as operações no mapa. Um turno interrompido não continua exibindo uma tarefa como se estivesse trabalhando.

Na conversa, o plano usa uma lista compacta com tipo, estado em texto e ícone, contagem de conclusões observadas e detalhes recolhíveis. Comandos, caminhos e logs aparecem sob demanda. Detalhes de checks usam a mesma apresentação na conversa e no inspetor. A fonte usa rem, espaços em passos de 4px, bordas e cores dos tokens existentes, linhas com alvo de 44px e texto quebrável em telas pequenas e zoom. Nenhuma troca de identidade visual.

Token auxiliar `--font-size-caption: max(0.75rem, 12px)` mantém o piso de 12px quando a escala compacta reduz o tamanho raiz e continua crescendo com a fonte do navegador.
Legendas e textos auxiliares no piso usam entrelinha de pelo menos 1,5 para não herdar uma altura menor após a correção do tamanho da fonte.

Os controles de evidência usam `--control-target-min: max(2.75rem, 44px)`, mantendo o alvo de toque de 44px também na escala compacta.

Cards conservam altura mínima lógica de 202px e crescem quando o título ou o espaçamento exigem; o título não é limitado a duas linhas. A ação resumida mantém seu conteúdo integral no inspetor. A lista continua sendo alternativa em fluxo.

## Evidência da implementação

### Conversa, modelos e revisão por arquivo

A rodada de conclusão segue as três telas apresentadas, mantendo a identidade atual. Em Conversa, a marca acompanha o identificador observado e o compositor mostra uma miniatura de imagem com remoção no próprio cartão. Na Área de trabalho, o seletor e Novo pedido compartilham o cabeçalho, e a rota selecionada aparece no inspetor. Em Alterações, o projeto, os arquivos e a comparação são o caminho principal. Ações de execução ficam no fluxo avançado. Os controles novos usam o alvo de toque e os tokens existentes.

Registrar provas e limites da rodada no manual Windows e nos artefatos locais ignorados em `ws/b_output/`. Capturas com dados fictícios, sem contas, prompts ou projetos do operador. Verificador automatizado não substitui leitor de tela nem teste com pessoas.
