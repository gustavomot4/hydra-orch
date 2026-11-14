## 13. Registro de origem e limite da inspeção

Esta seção registra como o guia foi extraído. Ela pode permanecer como histórico e não é dependência para implementar em outro projeto.

| Fonte | Uso no guia |
| --- | --- |
| `prd_frontend/prds/modelo-de-prd.md` e `CONTRIBUTING.md` | Cabeçalho, escopo, uso, tokens, receitas, contraste e checklist |
| PRDs `base-design-system`, `site-escola-idiomas` e `sistema-gestao` | Referências de organização e de nível de especificação; sem herança visual |
| `src/styles/tokens.css`, `base.css` e `ui.css` do frontend CNR | Valores e receitas da identidade atual |
| `src/ui`, `src/shell`, `src/lib/theme.ts` e `src/lib/useMediaQuery.ts` | Composição, estados, navegação, preferência de tema e letra |
| CSS de catálogo, perfil, avisos, cursos e comércio | Adaptações amplas e mídia |
| `src/dev/Gallery.tsx` e `gallery.pacote2.tsx` | Inventário de 60 telas, passos e variações com dados fictícios |
| Rotas e páginas do CNR | Modelos de tarefa e limites funcionais observáveis |

**Versão de origem:** checkout `3rd_ap_connecta_rocinha`, branch `a_dsv_gustavo_am`, HEAD `9cc0edb`, com alterações locais preexistentes. O guia retrata os arquivos presentes em 10/10/2026; não representa apenas o conteúdo desse commit.

**Cobertura visual:** as 60 entradas da galeria foram abertas e capturadas em 1440 × 900 e em 375 × 812. Foram conferidas mais 31 situações em 320 × 800 com letra a 130% e alto contraste, além de amostras do tema escuro e do painel inferior. As medições de largura dessas 151 situações não mostraram rolagem horizontal da página. Foram revisadas as capturas em pranchas e amostras individuais; essa verificação não equivale a ensaio integral de todas as operações.

**Comportamento do painel conferido:** a amostra abre como diálogo, fecha com Escape e devolve o foco ao acionador. Isso não comprova, por si só, todos os requisitos assistivos do diálogo.

**Exemplos do próprio guia:** os dois blocos HTML foram extraídos e renderizados com o CSS deste arquivo em oito combinações de largura, tema e tamanho de letra. Foram conferidos catálogo e etapa de formulário em 1440 px e 375 px no tema claro, 375 px no escuro e 320 px no alto contraste com letra a 130%. Essas amostras preservaram a troca de navegação e não mostraram rolagem horizontal da página.

**Acesso externo:** login, cadastro e recuperação de senha do MS_Access foram observados separadamente. Usam composição própria de formulário em cartão central. Os tokens deste guia descrevem a identidade do aplicativo CNR; não afirmam que aquela interface de acesso já usa as mesmas receitas. A autenticação de um destino pode ter provedor próprio ou receber uma adaptação visual explicitamente implementada.

**Limites:** a galeria usa dados fictícios e adaptadores locais de desenvolvimento. A inspeção é de aparência, composição e alguns comportamentos de interface. Ela não prova autorização, contratação, pagamento, envio externo, persistência em backend, leitura de tela, todas as condições de zoom ou conformidade integral com WCAG. Os critérios adicionais dessas áreas permanecem no checklist da implementação de destino.

O arquivo está pronto para revisão e reutilização como especificação visual. O estado `rascunho` do cabeçalho indica que não passou pelo processo completo de publicação do catálogo de referência, que também exige exemplos próprios e auditoria editorial.
