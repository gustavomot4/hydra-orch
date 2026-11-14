### 4.2 Iniciais coloridas

Cada pessoa (paciente, profissional, usuário) é representada por um círculo com as iniciais. A cor identifica a pessoa, não a situação, por isso a paleta é pastel: fundos claros com pouca saturação e texto escuro do mesmo tom. Assim as iniciais não competem com as seis situações, que usam cor saturada, contorno, preenchimento e hachura.

| Tom | Fundo | Texto |
| --- | --- | --- |
| 0, pêssego | `--avatar-1-bg` `#FCE3D6` | `--avatar-1-fg` `#8E3A19` |
| 1, menta | `--avatar-2-bg` `#DDF0E6` | `--avatar-2-fg` `#1D6B45` |
| 2, lavanda | `--avatar-3-bg` `#E3E8FB` | `--avatar-3-fg` `#3446A3` |
| 3, rosa | `--avatar-4-bg` `#F7E3EF` | `--avatar-4-fg` `#8E2F6B` |
| 4, creme | `--avatar-5-bg` `#FFEFC4` | `--avatar-5-fg` `#6E4B00` |
| 5, céu | `--avatar-6-bg` `#DDEDF6` | `--avatar-6-fg` `#245D7E` |

O tom 0 usa o par `--avatar-1-*`, o tom 5 usa o `--avatar-6-*`. Receita:

```css
.avatar[data-tone="0"] { background: var(--avatar-1-bg); color: var(--avatar-1-fg); }
.avatar[data-tone="1"] { background: var(--avatar-2-bg); color: var(--avatar-2-fg); }
.avatar[data-tone="2"] { background: var(--avatar-3-bg); color: var(--avatar-3-fg); }
.avatar[data-tone="3"] { background: var(--avatar-4-bg); color: var(--avatar-4-fg); }
.avatar[data-tone="4"] { background: var(--avatar-5-bg); color: var(--avatar-5-fg); }
.avatar[data-tone="5"] { background: var(--avatar-6-bg); color: var(--avatar-6-fg); }
```

O contraste de cada par está na seção 9.1; todos passam 4,5:1.

- **Iniciais:** primeira letra do primeiro nome e do último sobrenome, em maiúsculas, depois de tirar "Dr." ou "Dra." do começo. Nome de uma palavra dá uma letra; nome vazio dá "?".
- **Escolha do tom:** sempre o mesmo para o mesmo nome, em qualquer tela. Percorra o nome completo, caractere a caractere, com `hash = (hash * 31 + código UTF-16 do caractere) >>> 0`, partindo de 0; o tom é `hash % 6`.
- **Forma:** círculo, `--weight-bold`, `letter-spacing: 0.2px`, `aria-hidden="true"` (o nome está sempre escrito ao lado).

| Tamanho | Diâmetro | Fonte das iniciais | Onde |
| --- | --- | --- | --- |
| `xxs` | 18 px | 8,5 px | Profissional dentro do cartão da grade |
| `xs` | 24 px | 10,5 px | Chip de profissional, opção do combobox |
| `sm` | 36 px | 13 px | Menu da conta, cabeçalho de coluna por profissional |
| `md` | 44 px | 15 px | Item de lista |
| `lg` | 56 px | 19 px | Paciente escolhido no agendamento |
| `xl` | 68 px | 24 px | Detalhe da consulta, ficha do paciente |
