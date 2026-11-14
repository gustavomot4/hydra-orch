### 5.7 Teste de nível (`/teste-de-nivel`)

É a segunda conversão primária e tem fluxo próprio, em quatro etapas com o stepper do §3.7:

1. **Idioma:** escolha do idioma, em cards de rádio (um `<fieldset>` com `<legend>`).
2. **Questões:** 15 questões de múltipla escolha, uma por tela, com "Questão 4 de 15", "Voltar" e "Próxima". Cada questão é um `<fieldset>`; o enunciado no idioma testado leva `lang`. Sem tempo limite.
3. **Seus dados:** nome e e-mail, com o texto de consentimento do §3.5. Vêm depois das questões, não antes.
4. **Resultado:** nível estimado (por exemplo "Intermediário — B1"), uma frase sobre o que ele significa, o curso indicado e o par `.btn-outline` "Encontrar uma unidade" + `.btn-primary` "Fazer pré-matrícula".

Estados: sair no meio guarda as respostas no próprio navegador e oferece "Continuar de onde parei"; falha de envio mostra "Não foi possível calcular seu resultado." + "Tentar de novo", sem perder as respostas.

### 5.8 Demais páginas do menu

Todas usam header, footer e a faixa final de CTA do §5.3. Uma linha por página:

| Página | Blocos | CTA |
|---|---|---|
| **Sobre nós** | hero interno · história (linha do tempo) · números · prêmios | `.btn-primary` "Fazer pré-matrícula" |
| **Blog (lista)** | título · filtro por categoria · `.grid-cards` com 9 posts · paginação | "Continuar lendo" em cada card |
| **Blog (post)** | `<article>` com `<h1>`, data em `<time>`, texto em coluna de até 720px · 3 posts relacionados | faixa final de CTA |
| **E-book** | capa + lista do que o material traz · formulário de nome e e-mail com o consentimento do §3.5 | `.btn-primary` "Baixar e-book" |
| **Faça parte / Trabalhe conosco** | texto · vagas ou formulário | `.btn-primary` "Enviar" |
| **Seja um franqueado** | landing própria: hero · números da rede · etapas · formulário | `.btn-primary` "Quero ser franqueado" |
| **Fale conosco** | formulário (nome, e-mail, unidade, mensagem) · canais | `.btn-primary` "Enviar mensagem" |
| **Política de Privacidade** | texto corrido em coluna de até 720px, com sumário | — |
| **404** | "Página não encontrada" · busca do site · links para Cursos e Unidades | `.btn-primary` "Voltar para a home" |

### 5.9 SEO local e dados estruturados

- Cada unidade tem URL própria, `/unidades/{uf}/{cidade}/{slug}`, com nome, endereço e telefone em texto (não em imagem) e JSON-LD `LanguageSchool`: `name`, `address`, `geo`, `telephone`, `openingHours`, `url`.
- Páginas de curso com JSON-LD `Course`.
- `<title>` e `meta description` únicos por página; `<link rel="canonical">`; `sitemap.xml` com cursos, unidades e posts.
- Se o site atende mais de um país ou idioma (o passo 1 da pré-matrícula tem "País"), `hreflang` em cada versão.

---
