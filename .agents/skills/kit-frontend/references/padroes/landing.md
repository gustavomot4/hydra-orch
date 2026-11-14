# Landing e site institucional

**Quando:** página de apresentação de produto ou empresa. É onde a cara de IA mais aparece e onde a identidade pode ir mais longe. Leia junto `references/marca/criatividade.md`, que traz o que os sites admirados fazem: esta ficha cuida do que precisa funcionar; aquela, do impacto. O estilo `base-design-system` é sóbrio de propósito e não serve como padrão para landing de impacto.

## Regra

- **A primeira tela diz o que é, para quem e o que fazer.** Em 5 segundos, sem rolar. Título concreto, do setor, com a palavra que o cliente usaria. (G01)
- **Herói vem do assunto:** o produto real, o lugar real, o resultado real. Nada de captura flutuando em perspectiva nem blob.
- **Só o que convence.** Cada bloco responde a uma objeção de quem vai comprar. Sem contador de vaidade e sem logos de quem não é cliente. Depoimento só real, com nome e resultado.
- **Uma ação principal, repetida no fim.** Negócio local: telefone, WhatsApp e endereço sempre à vista.
- **Ritmo:** troque composição entre os blocos: não repita a mesma grade de cartões. Texto de leitura com até 70 caracteres por linha.
- **Mobile primeiro de verdade:** mais de metade do público chega pelo celular. A primeira dobra é desenhada em 375px.
- **Desempenho é parte do design:** imagem principal com `fetchpriority="high"` e dimensões declaradas; `loading="lazy"` no resto; WebP ou AVIF; fonte com subconjunto. HTML vindo do servidor; conteúdo legível sem JavaScript.
- **Dados pessoais:** nenhum rastreador antes do aceite. Recusar pesa igual a aceitar. Aviso de cookies não bloqueia a página e não cobre o conteúdo em zoom alto.
- **Carrossel:** só quando indispensável, com pausa, sem autoplay fora do herói.
- **SEO local:** `title` e `description` únicos, HTML semântico, JSON-LD do tipo do negócio.

## No processo do kit

Vem do teste de 01/11/2026 (`docs/testes/2026-11-01-oficina/relatorio.md`, no repositório do kit).

- **A home é a tela principal** das três direções.
- **Estados da etapa 5.** Site estático não carrega dados. No lugar de carregando e sucesso, confira que tudo funciona sem JavaScript e que há página de erro (404) com saída para o início e para a ação principal. O vazio, quando existe, diz o que fazer.
- **Entrega mínima:** página de privacidade, SEO local, `og:image` com o endereço completo, ícone de aba e de celular. Dado do negócio que o dono não confirmou fica como "a preencher".
- **Barra fixa no celular:** se ela traz a ação principal, tire o mesmo botão da primeira dobra (`g-acao-repetida`).
- **Foto que ainda não existe:** espaço do tamanho exato, listado em `design/midia.md`. Conferido o texto sobre ele, marque com `data-conferido="a11y-contraste-imagem"`.

## Como fugir do template

Comece pelo conteúdo real do negócio, nunca por seções de modelo. Mostre o que só essa empresa tem: o endereço, a foto real do espaço, o preço, o nome de quem atende. Use `references/marca/identidade.md` e dê à página um elemento que só exista nela.

**Verifique:** `g-muito-texto`, `ia-cards-iguais`, `ia-texto-cliche`, `a11y-camadas-fixas`. Teste a primeira dobra em 375px e a página em conexão lenta.
