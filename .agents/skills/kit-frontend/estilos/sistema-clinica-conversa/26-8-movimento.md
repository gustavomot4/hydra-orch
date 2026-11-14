## 8. Movimento

O movimento só mostra de onde algo veio. Nada pisca, nada se repete sozinho, exceto o carregando.

| O que | Duração | Curva | Movimento |
| --- | --- | --- | --- |
| Hover e troca de cor de botão | `--duration-fast` | padrão do navegador | `background-color`, `border-color`, `color` |
| Menu suspenso | `--duration-fast` | `ease-out` | opacidade de 0 a 1 |
| Véu e diálogo | `--duration-base` | `ease-out` | opacidade de 0 a 1; o diálogo também sobe 4% |
| Painel lateral (por cima da página) | `--duration-slow` | `ease-out` | desliza 24 px da direita |
| Folha inferior | `--duration-slow` | `ease-out` | sobe 40 px |
| Aviso | `--duration-slow` ao entrar, `--duration-fast` ao sair | `ease-out`, `ease-in` | sobe 16 px; sai só com opacidade |
| Botão flutuante com aviso na tela | `--duration-slow` | `ease-out` | `bottom`: sobe para ficar acima da pilha de avisos e desce quando ela some |
| Conteúdo do Painel ao trocar de mês | `--duration-slow` | padrão | opacidade 0,7 até chegar o dado novo |
| Carregando em botão e campo | `--duration-spin` | `linear` | giro contínuo |
| Esqueleto | `--duration-shimmer` | `ease-in-out` | brilho contínuo da direita para a esquerda |

Não animam: troca de tela, troca de visão e de período na agenda, a coluna de detalhe da Agenda abrindo e fechando (a grade muda de largura de uma vez), a linha "agora" (salta a cada 30 s), a mudança de cor de uma situação e a rolagem inicial da grade.

Com `prefers-reduced-motion: reduce`, a regra da base (seção 2) zera as durações e para as repetições: painel, folha, diálogo e aviso aparecem no lugar, o esqueleto fica parado e o ícone de carregando fica parado ao lado do texto. O tempo do aviso não muda.
