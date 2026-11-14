## 8. Conversão e confiança — os padrões que geram valor

São padrões que o autor observou no site analisado e considera os que geram valor; o guia não traz dados de conversão.

1. **Escada de compromisso.** Ofereça sempre três degraus: *ler* (blog/e-book) → *experimentar* (teste de nível gratuito, aula experimental) → *converter* (pré-matrícula). O "Teste de nível" é o degrau do meio e existe em toda página.
2. **Isca de conteúdo.** Um item de menu inteiro dedicado a `E-book`. Material gratuito troca conteúdo por e-mail.
3. **Prova social em três camadas:** números (`{N}+ anos`), prêmios/selos institucionais (`{prêmio} {N}×`), e depoimentos nominais de alunos. Use as três — cada uma convence um público diferente.
4. **Segmentação por idade antes de tudo.** Pais e adultos são compradores diferentes. Rotule com faixa etária explícita (`4 a 10 anos`).
5. **Modalidade explícita.** Formato (em grupo ou individual) e meio (presencial ou on-line), comparados lado a lado. É a primeira dúvida de quem procura curso hoje.
6. **Ancoragem local.** Buscador de unidades na faixa 1 do header, na seção 5 da home e como passo 1 da matrícula.
7. **Rota do franqueado.** Se o modelo for franquia, `Seja um Franqueado` fica no menu principal — é um funil B2B independente com sua própria landing page.
8. **Chat flutuante:** bolha circular de 56px em `--brand`, ícone em `--on-brand`, sombra `--shadow-brand`, `aria-label="Abrir chat"`, no canto inferior direito: `right: 24px; bottom: calc(var(--cta-bar-h) + var(--cookie-h) + 24px)`. Resposta rápida para dúvida de matrícula. O script do chat só carrega depois da primeira interação com a página.
9. **Cookie bar LGPD** ancorada no pé da tela, sem modal (com altura até 480px ela rola junto, §4): `position: fixed; bottom: var(--cta-bar-h)`, fundo `--dark`, texto `--white`. Três controles: `Recusar` e `Aceitar`, com a mesma receita e o mesmo peso visual (fundo `--white`, texto `--heading`, raio `--r-sm`, 44px), e o link `Preferências`, que abre as categorias Necessários / Desempenho / Marketing. Link para a Política de Privacidade no texto. O JS grava a altura da barra em `--cookie-h` ao exibir e zera ao fechar, para que ela não cubra o chat, o fim da página nem o elemento em foco.
10. **Rastreamento:** GTM + GA4 + Meta Pixel + TikTok Pixel + Clarity. Nenhuma tag dispara antes do aceite na cookie bar (Consent Mode v2), e cada uma respeita a categoria escolhida. Clarity com mascaramento de todos os campos de formulário. Depois do aceite, dispare eventos nomeados em: `clicou_pre_matricula`, `enviou_lead_newsletter`, `iniciou_teste_nivel`, `buscou_unidade`, `concluiu_pre_matricula`.

Os itens 9 e 10, o texto de consentimento do §3.5 e o bloco do responsável do §5.5 são recomendação técnica para tratar dados pessoais com cuidado. Não substituem orientação jurídica sobre a LGPD.

---
