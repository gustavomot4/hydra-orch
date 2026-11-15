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
---

# Hydra — sistema visual

Direção escolhida pelo dono em 15/11/2026: composição A (canvas livre e conversa/detalhe lateral) com o laranja da proposta C. Calibração posterior explícita: “exagerou no laranja, o principal é preto ainda”. Preto e cinza neutro dominam as superfícies; o laranja fica em ações, seleção e detalhes. Escolha direta do dono, sem juízo externo.

## Identidade e estrutura

Hydra aproxima o operador do trabalho dos agentes: pedido, responsáveis, atividade e resultado. A navegação mostra nomes completos. A Área de trabalho é o destino principal para acompanhar; Novo chat inicia pedidos e Alterações concentra revisão. Infraestrutura técnica fica recolhida. Logo existente preservado.

## Tokens

Fonte canônica: `frontend/src/style/tokens.css`. Tipografia Inter para interface e JetBrains Mono apenas para código, logs e identificadores. Corpo 16px no canvas; informações auxiliares a partir de 12px. Espaçamento em passos de 4px, raios de 8/12/16px; alvos de 44px nas ações novas.

| Token | Cor | Uso |
| --- | --- | --- |
| `--bg-main` | #141414 | Fundo preto principal |
| `--bg-sidebar` | #1c1c1c | Navegação em cinza escuro neutro |
| `--bg-surface` | #202020 | Cards e painéis elevados |
| `--bg-hover` | #282828 | Hover e agrupamentos |
| `--border` | #767676 | Controles e limites de superfícies, mínimo 3:1 sobre o hover |
| `--text-primary` | #e8e8e8 | Texto principal |
| `--text-muted` | #b4b4b4 | Texto auxiliar |
| `--accent` | #ffab66 | Ação principal, seleção, marca e foco |
| `--accent-soft` | #33251c | Pequenas áreas de seleção |
| `--status-success` | #8ed8b0 | Conclusão verificada |
| `--status-warning` | #f6cb79 | Espera ou atenção |
| `--status-error` | #ffaaa1 | Falha |
| `--status-info` | #8bcfe0 | Trabalho em andamento |

## Área de trabalho

Canvas com fundo pontilhado, pan por arrasto do fundo, zoom limitado, enquadrar, organizar e minimapa. Cards podem ser reposicionados e conservam a posição por trabalho. Seleção abre detalhe lateral no desktop; em telas pequenas, lista e detalhe em fluxo vertical. Lista é alternativa sem arrasto e sem zoom. Navegação por teclado tem ações explícitas para mover/enquadrar.

No mundo espacial, uma base lógica de 16px é ampliada junto com toda a geometria por um fator medido em `rem`: aumentar a fonte do navegador amplia cards, rótulos e portas juntos, sem cortar o conteúdo. O mapa continua navegável por pan, enquadramento e teclado; a lista oferece a alternativa em fluxo.

Dados vêm das conversas e execuções persistidas. Relações mostram delegação, dependência e revisão com proveniência. Um worker em execução não recebe mensagens arbitrárias pelo canvas: a conversa continua pelo chat canônico. Não anunciar comunicação direta entre workers nem criar eventos ou revisores fictícios. Ausência de registro aparece como ausência.

## Do's and Don'ts

- Inter é mantida porque preserva a continuidade da interface existente e oferece leitura consistente de português em telas operacionais.
- Laranja identifica a ação e a seleção porque foi a escolha explícita do dono; estados usam outras cores acompanhadas de texto e ícone.
- Preto continua principal. Não pintar fundos, sidebar ou cards de marrom, nem usar degradês extensos em laranja.
- Mostrar ação e último evento, sem gráficos ou porcentagens não observados.
- Foco visível, contraste mínimo AA, alternativa ao arrasto, redução de movimento e modo de alto contraste são parte da implementação.

## Verificação

Registrar provas e limites da rodada no manual Windows e nos artefatos locais ignorados em `ws/b_output/`. Capturas com dados fictícios, sem contas, prompts ou projetos do operador. Verificador automatizado não substitui leitor de tela nem teste com pessoas.
