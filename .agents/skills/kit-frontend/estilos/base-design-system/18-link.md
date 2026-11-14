### Link

Dentro de frase: `--accent` com **sublinhado permanente**
(`text-decoration: underline; text-underline-offset: 2px`). A cor sozinha não
separa o link do texto vizinho — `--accent` contra `--ink` dá 2,07:1, e a WCAG
pede 3:1 ou um segundo sinal. Sem sublinhado só a ação terciária isolada, fora
de parágrafo. Link de navegação (barra, lateral, rodapé): `--ink` ou `--ink-2`,
sem sublinhado; o hover sublinha.

### Campo

| Medida | Valor |
| --- | --- |
| Altura | `--h-controle`: 32px na ferramenta com ponteiro fino, 44px em `pointer: coarse`. Em fluxo e vitrine, 44px sempre |
| Raio · padding lateral | 8px · 12px |
| Fundo · texto | `--surface` · `--ink` |
| Fonte | 14px na ferramenta; 17px em fluxo, vitrine e em `pointer: coarse` (abaixo de 16px o iOS dá zoom no foco) |
| Borda | `box-shadow: inset 0 0 0 1px var(--ink-3)` — não `border`, para não mexer no box model. 4,04:1 sobre `--surface` |
| Rótulo | visível, acima, a 8px do campo: 14px, peso 600, `--ink`. Campo sem rótulo visível (busca) leva `aria-label` |
| Placeholder | `--ink-2`. É exemplo de preenchimento, nunca o rótulo |
| Hover | borda `--ink-2` |
| Foco | a borda engrossa para 2px em `--accent`; no lugar do anel, `outline: 2px solid transparent` (que aparece em `forced-colors`) |
| Desabilitado | fundo `--fill`, sem borda, texto `--ink-2` |
| Erro | borda de 2px em `--danger` + **uma frase** 4px abaixo, em `--danger`, dizendo o que corrigir. `aria-invalid="true"` no campo e a frase ligada por `aria-describedby` |

`<select>` e `<textarea>` seguem o campo: mesma borda, raio e estados.
Checkbox e radio são os nativos, com `accent-color: var(--ink)`, 16px, rótulo à
direita a 8px, dentro do mesmo `<label>`.

Formulário que coleta dado pessoal diz, antes do botão de envio, para que o
dado serve e onde está a política de privacidade.

### Lista agrupada

O padrão que mais muda a percepção de qualidade:

- contêiner `--surface` com raio 12px, sem borda em volta de **cada** linha;
  dentro de um cartão, o próprio cartão é o contêiner;
- separador `--line` **recuado** até onde o conteúdo começa (o padding lateral
  da linha, ou depois do avatar/ícone);
- linha de 44px, padding lateral 16px (dentro de cartão, o padding do cartão);
  segunda linha de texto no tamanho de legenda, `--ink-2`;
- `hover` = fundo `--sunken`, não borda.

**Semântica e teclado:** `<ul>` / `<li>`. Linha clicável é um `<a>` ou
`<button>` que ocupa a linha inteira.
