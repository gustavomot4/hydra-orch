### 6.11 Paginação

Listas que crescem mostram 20 itens por página. A página atual fica no endereço (`?pagina=3`), para voltar da ficha ao mesmo lugar.

- `<nav aria-label="Páginas de pacientes">` abaixo da lista, `display: flex; justify-content: space-between; flex-wrap: wrap`, espaço `--space-10` × `--space-16`.
- **Resumo:** "Mostrando **21–40** de **134** pacientes", `--text-small` `--muted-foreground`, números em `--foreground` tabulares.
- **Botões:** "Anterior" (`chevron-left`) e "Próxima" (`chevron-right`) com `padding: 0 var(--space-14)`; números com largura mínima 42 px. Todos com altura 42 px, raio `--radius-md`, borda `--line-control` `--border`, fundo `--card`, `--text-ui` `--weight-bold`, números tabulares, espaço `--space-4` entre números.
- **Números mostrados:** a primeira, a última, a atual e as vizinhas; "…" no lugar de saltos maiores que uma página.
- **Estados:** hover com borda `--primary`; página atual com fundo e borda `--primary`, texto `--primary-foreground`, `aria-current="page"`; "Anterior" na primeira página e "Próxima" na última ficam desabilitados (texto `--muted-foreground`, fundo transparente, opacidade 0,6).
- **Abaixo de 600 px:** os números somem e entra "Página 3 de 7" entre os botões; o resumo ocupa a linha de cima, centralizado.
- Trocar de página rola até o topo da lista se ele saiu da tela.

### 6.12 Esqueleto, estado vazio e erro

- **Esqueleto:** blocos empilhados com espaço `--space-10`, raio `--radius`, fundo `linear-gradient(90deg, var(--muted), var(--card-soft), var(--muted))` com `background-size: 200% 100%`, animado da direita para a esquerda em `--duration-shimmer` `ease-in-out` infinito. O conjunto tem `role="status"` e `aria-label="Carregando"`. A quantidade e a altura de cada tela estão na seção 7. Nunca a palavra "Carregando…" sozinha no lugar da lista.
- **Estado vazio:** coluna centralizada, espaço `--space-10`, `padding: var(--space-48) var(--space-20)`, fundo `--card`, borda `--line` `--border`, raio `--radius-lg`. Círculo de 56 px `--primary-soft` com ícone `--icon-lg` `--primary`; título `h2` em `--text-section` `--weight-extrabold`; uma frase em `--muted-foreground` com largura máxima de 46 caracteres; a ação que resolve, quando houver.
- **Erro ao carregar:** o mesmo bloco, com `role="alert"`, círculo `--destructive-soft` e `circle-alert` `--destructive`, título "Não foi possível carregar", a mensagem do servidor ou "Tente de novo em instantes." e o botão "Tentar de novo" (`secondary`, `rotate-cw`, altura `--target`).
