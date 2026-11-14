### 6.9 Botão flutuante

Abaixo de 1100 px, a ação principal da tela (Agendar, Novo paciente) sai do cabeçalho e flutua.

- `position: fixed; right: var(--space-18); bottom: calc(var(--tabbar) + var(--space-18) + env(safe-area-inset-bottom))`, `z-index: var(--z-fab)`.
- Variante `primary`, altura `--fab`, `padding: 0 var(--space-24) 0 var(--space-18)`, raio `--radius-lg`, `--shadow-fab`, ícone (`plus` ou `user-plus`) e rótulo curto: "Agendar", "Novo paciente". Nunca só o ícone.
- A lista embaixo dele reserva 72 px de margem inferior, para o botão não cobrir a paginação nem o último item.
- **Com aviso na tela** (6.10), o botão sobe para ficar acima da pilha de avisos, com a mesma transição do aviso: `transition: bottom var(--duration-slow) ease-out`. A base passa a ser a barra de abas + a altura da pilha + `--space-10`; o `--space-16` é a distância que a própria área de avisos mantém da barra. A área de avisos mede a pilha e a publica no `<html>` (`--toast-stack`, em px, e o atributo `data-toast` enquanto houver aviso):

```css
.fab { transition: bottom var(--duration-slow) ease-out; }
html[data-toast] .fab { bottom: calc(var(--tabbar) + var(--space-16) + var(--toast-stack) + var(--space-10) + env(safe-area-inset-bottom)); }
```

```js
const area = document.querySelector('.toasts');
new ResizeObserver(() => {
  const altura = area.getBoundingClientRect().height;
  document.documentElement.style.setProperty('--toast-stack', altura + 'px');
  document.documentElement.toggleAttribute('data-toast', altura > 0);
}).observe(area);
```

- **Camadas**, de baixo para cima: conteúdo, botão flutuante (`--z-fab`), barra de abas (`--z-tabbar`), véu (`--z-overlay`), painel e folha (`--z-panel`), aviso (`--z-toast`). Botão e aviso não se sobrepõem; o aviso fica acima de tudo, inclusive do véu, e continua clicável com um painel aberto.

### 6.10 Aviso com "Desfazer"

Aviso curto embaixo, depois de uma ação que mudou um dado.

- **Área:** `position: fixed`, centralizada, `bottom: var(--space-24)` (abaixo de 1100 px, `calc(var(--tabbar) + var(--space-16) + env(safe-area-inset-bottom))`), largura `min(var(--overlay-width), calc(100vw - 32px))`, avisos empilhados com espaço `--space-10`, `z-index: var(--z-toast)`. No máximo 3 ao mesmo tempo; o quarto tira o mais antigo.
- **Aviso** (`data-surface="dark"`): `display: flex`, espaço `--space-12`, `padding: var(--space-12) var(--space-10) var(--space-12) var(--space-14)`, raio `--radius-box`, fundo `--foreground`, texto `--on-dark`, `--shadow-lg`.
- **Ícone:** círculo de 34 px com fundo `--on-dark-fill`; `check-check` `--icon-md` em `--on-dark-accent`, ou `circle-alert` em `--on-dark-danger` no erro.
- **Texto:** título em `--text-ui` `--weight-bold`; descrição opcional em `--text-small` `--on-dark-muted`.
- **Desfazer:** altura `--control-sm`, `padding: 0 var(--space-12)`, raio `--radius-sm`, fundo `--on-dark-fill`, texto `--on-dark-accent` `--weight-bold`. Desfazer volta a situação anterior e mostra "Situação restaurada", sem novo Desfazer.
- **Fechar:** 38 × 38 px, fundo transparente, `x` `--icon-md` em `--on-dark-muted`, `aria-label="Fechar aviso"`.
- **Abaixo de 600 px:** o aviso tem duas linhas. Em cima, o ícone e o texto, que ocupa o resto da linha; embaixo, "Desfazer" e "Fechar" alinhados à direita (sem "Desfazer", só "Fechar", também à direita), com espaço de `--space-8` entre as linhas. "Fechar" continua. A 375 px o texto tem 273 px e "Consulta de Helena confirmada" cabe numa linha.

```css
@media (max-width: 599px) {
  .toast { flex-wrap: wrap; row-gap: var(--space-8); }
  .toast-text { flex: 1 1 calc(100% - 34px - var(--space-12)); }
  .toast-undo, .toast-text + .toast-close { margin-left: auto; }
}
```

- **Tempo:** 5 s, pausado enquanto o ponteiro ou o foco estiver no aviso. Arrastar para baixo fecha.
- **Movimento:** entra subindo 16 px com opacidade de 0 a 1 em `--duration-slow` `ease-out`; sai com opacidade até 0 em `--duration-fast` `ease-in`.
- **Erro:** "Não foi possível mudar a situação", com a mensagem do servidor na descrição e sem Desfazer.
