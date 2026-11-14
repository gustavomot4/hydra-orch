# Estilos de partida

Cinco receitas completas, extraídas de produtos reais. Um estilo dá **estrutura, medidas e comportamento**. Ele não é a identidade do produto: cor, fonte, forma e voz vêm do `DESIGN.md`.

Use no máximo um por projeto: eles dão ordens opostas. Leia `estilos/<slug>/indice.md` e abra só as seções da tarefa.

| Estilo | Ponto de partida para | Tamanho total |
| --- | --- | --- |
| `sistema-gestao` | Sistema de trabalho no computador: cadastros, listas, agenda, relatórios. Traz processo, arquitetura e testes | cerca de 12 mil tokens |
| `sistema-clinica-conversa` | Sistema com hora marcada, usado no computador e no celular por gente sem familiaridade | cerca de 34 mil tokens |
| `app-tarefas-acessivel` | Aplicativo público: catálogo, solicitações, comunidade. Três temas e três tamanhos de letra | cerca de 35 mil tokens |
| `site-escola-idiomas` | Site institucional focado em matrícula e captação | cerca de 22 mil tokens |
| `base-design-system` | Landing, fluxo curto ou ferramenta densa, em linguagem de subtração | cerca de 24 mil tokens |

Se nenhum couber, não force: use só `references/padroes/` e o `DESIGN.md`.

## O que trocar antes de usar

Estes pontos contrariam `references/gosto/perfil.md` ou `references/qualidade/acessibilidade.md`, e o kit prevalece. Conferidos em 31/10/2026 contra a versão atual de cada PRD.

| Estilo | Não siga | Faça |
| --- | --- | --- |
| Todos | Tokens de cor, fonte e raio como estão | Substitua pelos do `DESIGN.md`; mantenha medidas de alvo, linha e espaçamento |
| `sistema-clinica-conversa`, `sistema-gestao` | Barras fixas em janela baixa: o PRD não traz a regra | Com altura até 480px, tudo o que é fixo rola junto |
| `sistema-clinica-conversa` | Ícone `sparkles` em Procedimento | Ícone do assunto |
| `sistema-gestao` | Barra lateral escura como identidade | É o painel que recebeu a reclamação de cara de IA. Mantenha a arquitetura, troque a expressão |
| `sistema-gestao` | "Use os tokens abaixo sem alterar" quando falta identidade | Direções de `references/marca/identidade.md` |
| `sistema-gestao` | Exemplos só de computador | Regras de `references/padroes/navegacao.md` para celular, conferidas em 375px |
| `base-design-system` | Inter como padrão, sem decisão | Etapa de direções; fonte escolhida com motivo |
| `base-design-system` | Texto de 12px e controles de 32px como padrão | Só em ferramenta densa para especialista; público geral usa 16px e 44px |
| `site-escola-idiomas` | Estrutura copiada de um concorrente, trocando só `--brand` | Mantenha o que é convenção do setor; a expressão é da escola |
| `site-escola-idiomas` | `<h2>` seguido de `<h4>` | Não pule nível de título |

Os exemplos ainda têm falhas nas medições novas de letra em 200% e espaçamento: não copie alturas fixas deles. A lista está em `docs/pendencias.md`, no repositório do kit.
