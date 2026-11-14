## 5. Anatomia das páginas (arquitetura de informação)

### 5.1 Header

**A partir de 1200px: duas faixas, 143px (`--header-h`).**

```
+- Faixa 1 (64px) ---------------------------------------------------------------------------------------+
| [LOGO]      [ Pesquisar no site ......................]      (pino) Encontre uma unidade     [Acesso v] |
+- Faixa 2 (79px) ---------------------------------------------------------------------------------------+
| Home  Sobre Nos v  Cursos v  Blog  E-book  Faca Parte v  Seja um Franqueado  Fale Conosco               |
|                                                                                       [Pre-matricula]   |
|                                                                                        Teste de nivel   |
+---------------------------------------------------------------------------------------------------------+
```
- `<header>` com `position: sticky; top: 0; z-index: 10` e fundo `--white`. A borda inferior de 1px `--border` é a última linha da faixa 2 (contada nos seus 79px), para que o header some os 143px de `--header-h`. As duas faixas usam o `.container`.
- **Faixa 1:** logo; busca do site (§3.6); o link **"Encontre uma unidade"** com ícone de pino, que leva a `/unidades` (`--fs-ui`/600, `--brand-text-dark`, sublinhado); e **`Acesso ▾`**, um `.btn-outline` que abre um dropdown agrupado por perfil — padrão essencial em escola com portal:
  `Para o aluno` (Portal do Aluno, plataforma online) · `Para o franqueado` (Painel, sistema de gestão, webmail) · `Para o professor` (Portal do Professor).
- **Faixa 2:** `<nav aria-label="Principal">` numa linha só, com links em `--fs-ui`/500 `--heading` e `gap: 28px`; o item da página atual fica em `--brand-text`, peso 700, com `aria-current="page"`.
- **CTA duplo à direita da faixa 2:** `.btn-primary` "Pré-matrícula" e, 4px abaixo, o link "Teste de nível" (`--fs-caption`/600, `line-height: var(--lh-heading)`, `--brand-text-dark`, sublinhado, `padding-block: 4px`: 25px de altura, acima do mínimo de 24px para alvo). Botão, respiro e link somam 73px e cabem nos 79px da faixa. Hierarquia clara de compromisso.
- **Dropdown:** o gatilho é um `<button aria-expanded aria-controls>`. O painel fechado tem `visibility: hidden` (não só `opacity: 0`, que deixaria os links focáveis e invisíveis). Abre com clique, Enter e Espaço; Esc fecha e devolve o foco ao gatilho. Entrada: `opacity` + `translateY(-6px)` em `var(--t-fast)`. Painel: fundo `--white`, raio `--r-md`, sombra `--shadow-card`, itens com 44px de altura.

**Abaixo de 1200px: uma faixa de 64px e uma barra fixa no pé da tela.**

```
+- Header (64px) -----------------------+
| [=]           [LOGO]           (pino) |
+---------------------------------------+
|               conteudo                |
+- Barra das conversoes (56px) ---------+
| [ Teste de nivel ]  [ Pre-matricula ] |
+---------------------------------------+
```
- **Header:** hambúrguer à esquerda, logo centralizado, atalho de unidades (ícone de pino) à direita. Os dois botões têm 44px e `aria-label` ("Abrir menu", "Encontre uma unidade").
- **Barra das conversões:** `position: fixed; bottom: 0`, altura de 56px (`--cta-bar-h`) mais `env(safe-area-inset-bottom)`, fundo `--white`, borda superior de 1px `--border`. Dois botões de 44px em duas colunas `repeat(2, minmax(0, 1fr))`: `.btn-outline` "Teste de nível" e `.btn-primary` "Pré-matrícula". Em 320px cada coluna tem cerca de 124px, menos que um rótulo da Montserrat: os botões têm `padding: 4px var(--space-2)`, `white-space: normal` e `line-height: 1.2`, e o rótulo quebra em duas linhas em vez de sair da barra. É ela que mantém as duas conversões sempre visíveis; a partir de 1200px ela some (`--cta-bar-h: 0px`) e o CTA duplo do header assume.
- **Side-nav:** o hambúrguer abre um `<dialog>` modal (foco preso, fundo inerte, Esc fecha) com botão "Fechar" de 44px. Conteúdo, nesta ordem: busca do site, "Encontre uma unidade", os links de navegação, o grupo "Acesso" e os dois CTAs.
