# Hydra — diagnóstico para o estudo de compactação

Data: 2026-11-15. Escopo: leitura de código, duas consultas locais de catálogo e mockups para escolha visual. Nenhum componente, preferência ou serviço foi alterado. O [plano proposto](compactacao-plano.md) acompanha a composição em [compactacao-primeira-ideia.md](compactacao-primeira-ideia.md) e depende da escolha visual antes da execução.

## Catálogo OmniRoute

Consultas à API local `GET /v1/control-plane/omniroute/combos?executor=codex&connection_mode=omniroute`, sem inferência ou alteração de configurações:

| Consulta | HTTP | Tempo total | Resposta | Conteúdo |
| --- | --- | --- | --- | --- |
| Primeira leitura desta medição | 200 | 3,606 s | 239.133 bytes | 10 combos e 2.295 modelos |
| Leitura seguinte, com cache aquecido | 200 | 0,828 s | 239.133 bytes | 10 combos e 2.295 modelos |

São duas amostras da API, não uma medição do tempo entre clique e renderização, nem um benchmark. A primeira leitura não comprova que todo o processo estava frio. Contas, credenciais e conteúdo privado do catálogo não fazem parte deste documento.

Achados confirmados no código:

- `frontend/src/feature/chat/ConversationRoutePicker.tsx`: a busca filtra em memória. Busca vazia já inclui todos os destinos e a tela limita a apresentação aos primeiros 30. Digitar não é necessário para requisitar ou liberar o catálogo. Durante a primeira consulta, a ausência de dados pode mostrar a mensagem de nenhum resultado, confundindo espera com busca vazia. O catálogo é consultado na montagem do componente de configuração, sem pré-carregamento antecipado específico.
- `src/hydra_orch/bridge/omniroute_client.py`, `conversation_catalog`: saúde, combos e modelos são requisitados em paralelo, mas a resposta agregada aguarda os três. A lista extensa de modelos pode atrasar a apresentação dos combos.
- `src/hydra_orch/core/conversation_route.py`, `catalog`: antes de devolver as opções, percorre combos e aguarda `describe` para cada um em sequência. Cada descrição prepara o store e consulta evidência de compatibilidade no SQLite. A leitura inicial da versão da CLI também está nesse caminho e é armazenada em cache. O cache bruto tem validade de 30 segundos; a resposta ainda agrega até 5.000 modelos.
- A seleção faz uma consulta separada de descrição/compatibilidade. Exibir a lista e permitir executar um destino são estados distintos; acelerar a apresentação não pode dispensar a validação de ferramentas e continuidade já exigida pelo backend.

Direção a detalhar após a escolha: mostrar combos iniciais sem pesquisa obrigatória, tratar carregamento/erro/vazio separadamente, reaproveitar dados recentes enquanto atualiza, separar a abertura da lista do inventário completo e reduzir trabalho repetido de descrição/SQLite. Medir cada etapa antes de atribuir uma parcela exata do atraso ou escolher a mudança de contrato da API. Não executar testes pagos de combinação ao abrir um seletor.

## Espaço, listas e fluxo

- Já há largura ajustável e recolhimento da sidebar em `frontend/src/store/layoutStore.ts`. A proposta amplia esse mecanismo para o detalhe lateral e os painéis divididos, com restauração e persistência de tamanhos.
- O modo compacto atual em `frontend/src/index.css` muda principalmente a fonte raiz para 13px. Dimensões fixas de componentes continuam grandes; é necessário estudar alturas, margens e densidade, separando fonte do chat, terminal e zoom do canvas.
- `frontend/src/component/Sidebar.tsx` mantém conversas e pastas como grupos extensos separados. A seleção da área de trabalho também é plana. A árvore proposta deve usar os vínculos reais de projeto, conversa e execução, sem inventar parentescos nem percorrer todo o disco.
- `frontend/src/feature/quota/ProviderQuotaCard.tsx` apresenta todos os modelos em chips. `frontend/src/feature/quota/QuotaAccountsPage.tsx` também apresenta todo o inventário em tabela. A proposta limita a prévia no card e abre uma lista pesquisável paginada. As cotas continuam expressando disponibilidade observada da janela; não se inferem limites de tokens.
- `frontend/src/page/NovoChatPage.tsx` abre um modal intermediário antes do seletor nativo. O endpoint de seleção de pasta e o diálogo Windows já existem no launcher. A proposta é abrir diretamente o seletor no desktop e comunicar cancelamento/erro sem exigir um segundo clique. Não foi aberto o diálogo nativo nesta etapa de estudo.
- `frontend/src/feature/composer/PromptComposer.tsx` já usa Tab e setas em menus de menções/comandos; não oferece histórico de prompts ou conclusão contextual inline. Qualquer proposta deve preservar a precedência desses menus, a navegação por teclado e o rascunho. Os atalhos predefinidos da página inicial serão retirados na implementação solicitada.

## Limite da evidência

Mockups usam dados fictícios e não provam atualização ao vivo de agentes, seleção nativa, persistência, acessibilidade ou desempenho da interface. Não foram executados testes de frontend, pois esta entrega não altera código. A futura implementação precisa verificar teclado, redimensionamento, zoom, viewport pequena, limites das listas e o fluxo real no navegador/desktop.
