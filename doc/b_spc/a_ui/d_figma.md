# Design Figma — acesso e orientação de implementação

Registro atualizado em 2026-11-08. O design é uma referência visual de implementação e navegação, com dados simulados. Não comprova frontend funcional, execução de agentes, terminal PTY, consumo real ou integração com provedores.

## Acesso

- [Arquivo editável](https://www.figma.com/design/9d07tpKkHO5pa902QuL0nx?node-id=18-8).
- [Protótipo navegável — novo chat](https://www.figma.com/proto/9d07tpKkHO5pa902QuL0nx?node-id=18-8&starting-point-node-id=18%3A8).
- [Protótipo — conversa e agentes juntos](https://www.figma.com/proto/9d07tpKkHO5pa902QuL0nx?node-id=7-6&starting-point-node-id=7%3A6).
- [Protótipo — Codex CLI e Claude Code CLI lado a lado](https://www.figma.com/proto/9d07tpKkHO5pa902QuL0nx?node-id=7-69&starting-point-node-id=7%3A69).

**File key:** `9d07tpKkHO5pa902QuL0nx`.
**Página de referência atual:** `Protótipo navegável` — page ID `7:5`.
**Página histórica:** `Hydra • Conceito UI`; não usar suas telas antigas para reconstruir o estilo atual.

O acesso depende das permissões da conta Figma e da conexão do agente. Registrar o link no Git não concede acesso. Se houver bloqueio, informar qual arquivo/nó não pôde ser lido e solicitar acesso ao responsável; não afirmar que o design foi inspecionado apenas por conhecer a URL.

## Mapa das telas

Na última revisão desta conversa, as 18 telas do protótipo estavam alcançáveis e sem destinos de navegação inválidos. O arquivo é editável e pode mudar; conferir o estado atual antes de implementar.

| Tela | Node ID |
| --- | --- |
| Novo chat centralizado | `18:8` |
| Conversa com coordenador e workers | `7:6` |
| Coordenação / agentes agrupados | `7:134` |
| Terminais Codex e Claude Code lado a lado | `7:69` |
| Codex CLI em painel completo | `22:8` |
| Claude Code CLI em painel completo | `22:239` |
| Recursos | `7:205` |
| Contas e consumo | `7:279` |
| Busca global | `7:359` |
| Automações / inativo e ativo | `7:439`, `7:832` |
| Emulador móvel / inativo e ativo | `7:519`, `7:901` |
| Controle do computador / inativo e ativo | `7:599`, `7:970` |
| Ditado e anexos / inativo e ativo | `7:679`, `7:1039` |
| Configurações e perfil | `18:454` |

Para montar uma URL de nó, trocar `:` por `-` no parâmetro `node-id`. Nas ferramentas Figma, usar o ID com `:`. As telas desktop de referência medem 1920 × 1100; a implementação precisa se adaptar à viewport e validar mobile separadamente.

## Direção visual consolidada

- Interface em português, sem as três bolinhas de janela no canto superior esquerdo.
- Barra estreita de aplicativos à esquerda, com perfil e configurações; sidebar adjacente com Novo chat, busca, tarefas, automações, fixados e projetos.
- Hierarquia visível por recuos e guias: projeto → conversa → agentes da conversa. Preservar os agentes agrupados no mesmo workspace.
- Novo chat com título no centro da área principal e compositor centralizado na parte inferior, sem deslocamento para a esquerda.
- Conversa com coordenador ao centro e workers empilhados à direita; modos de terminal individual e dividido para Codex CLI e Claude Code CLI.
- Rodapé compacto: ícone do provedor + barra + percentual, com alinhamento vertical uniforme. Não exibir nome do provedor nem horário de reset no rodapé. Detalhes pertencem à tela de consumo.
- Claude 59%, Codex 42% e Agy 24% são exemplos visuais. Não fixar esses valores no produto nem substituir métricas desconhecidas por zero.

| Papel visual | Referência consolidada |
| --- | --- |
| Fundo principal | `#141414` |
| Sidebar | `#1C1C1C` |
| Barra de aplicativos | `#181818` |
| Cartão / painel | `#202020` |
| Borda / separador | `#303030` |
| Texto principal | `#E8E8E8` |
| Texto secundário | `#969696` |
| Botão principal | fundo `#E8E8E8`, texto `#181818` |

Usar Inter na interface e JetBrains Mono no terminal. As telas de recursos, busca, consumo, configurações e estados ativos devem seguir o mesmo padrão neutro do chat; não recuperar os cartões esverdeados do conceito anterior. Cores dos logos e de estados semânticos podem permanecer específicas.

O estilo solicitado é o do [shadcn/ui](https://ui.shadcn.com/), com composição de Sidebar, Tabs, Card, Input, Button, Separator e Progress. Os ícones de interface foram substituídos por SVGs do [repositório oficial Lucide](https://github.com/lucide-icons/lucide/tree/main/icons), mantendo os logos dos provedores. Usar SVGs/componentes Lucide na implementação; evitar emojis, símbolos tipográficos e redesenhos manuais para os controles. O arquivo Figma contém camadas editáveis, mas não é evidência de instalação da biblioteca shadcn/ui nem de vínculo a um kit publicado.

## Como o próximo agente deve trabalhar

1. Ler este guia, o [processo de construção](c_process.md), os PRDs e a stack do repositório. Reconciliar o escopo com o [backlog](../../a_context/backlog.md) e o [registro de ideias futuras](../../a_context/ideia_futura.md): telas de emulação, voz e controle do computador não promovem capacidades futuras para o escopo atual.
2. Abrir o arquivo pelo conector Figma, quando disponível. Carregar as skills exigidas pela ferramenta para leitura de design e implementação; usar o file key e os node IDs deste guia. Em caso de indisponibilidade do conector, abrir o arquivo no Figma e registrar a limitação da inspeção.
3. Inspecionar a página `Protótipo navegável`, obter o contexto dos nós relevantes e conferir screenshots atuais. Verificar também as telas adjacentes e os estados ativo/inativo para preservar consistência.
4. Implementar os componentes compartilhados e o tema uma única vez. Conectar navegação e dados pelos contratos do Hydra; exemplos de CLI e mensagens no mockup são conteúdo ilustrativo, não comandos autorizados para execução.
5. Comparar as telas implementadas com os mesmos nós do Figma. Validar centralização, hierarquia, SVGs, rodapé, estados, teclado e responsividade. Testar a integração real separadamente dos cenários simulados.
6. Registrar divergências, decisões e evidências de validação; atualizar este guia caso mudem o arquivo, a página ou os IDs de referência.

O Figma orienta apresentação e interação. Contratos de API, permissões e critérios de execução continuam nos documentos canônicos do projeto. Divergências entre design e contrato devem ser resolvidas explicitamente antes de conectar a ação real.
