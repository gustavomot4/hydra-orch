### 3.2 Card de curso (tile de imagem com overlay)

Na leitura do autor, o padrão mais forte do site analisado: faixa horizontal de tiles com imagem de fundo, gradiente escuro na base, nome do idioma e um "Conheça".

```html
<a class="course-tile" href="/cursos/ingles">
  <img src="ingles.webp" alt="" width="596" height="512" loading="lazy">
  <div class="course-tile__body">
    <h3>Inglês</h3>
    <span class="course-tile__cta">Conheça</span>
  </div>
</a>
```
```css
.course-tile {
  position: relative; display: block; overflow: hidden;
  aspect-ratio: 298 / 256;              /* ~1.16:1 */
  color: var(--white); text-decoration: none;
}
.course-tile img { display: block; width: 100%; height: 100%; object-fit: cover; transition: transform var(--t-slow); }
.course-tile:hover img { transform: scale(1.06); }
.course-tile::after {                    /* legibilidade do texto sobre foto */
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(to top, rgb(0 0 0 / .8) 0%, rgb(0 0 0 / .55) 50%, transparent 100%);
  transition: background-color var(--t-slow);
}
.course-tile:hover::after { background-color: rgb(0 0 0 / .2); }   /* o overlay escurece */
.course-tile__body { position: absolute; inset: auto 0 0 0; z-index: 1; padding: var(--space-4); }
.course-tile__body h3 {
  margin: 0 0 var(--space-2); font-size: var(--fs-card); font-weight: 600; color: inherit;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden;   /* no maximo 2 linhas */
}
.course-tile__cta { font-size: var(--fs-caption); font-weight: 700; line-height: var(--lh-caption); text-transform: uppercase; }

/* foco por dentro: o trilho do carrossel recorta o que sai do tile */
.course-tile:focus-visible        { outline-offset: -2px; box-shadow: none; }
.course-tile:focus-visible::after { box-shadow: inset 0 0 0 4px var(--heading); }
```

- **Forma e grade:** tiles sem raio e encostados (`gap: 0`), formando uma faixa contínua dentro do `.container`. Por tela: 1,2 abaixo de 768px, 2 de 768 a 1199px, 4 a partir de 1200px. Com mais tiles que isso, a faixa é um carrossel (§3.10).
- **Contraste:** nome e "Conheça" ficam na metade de baixo do tile, onde o overlay tem alfa de 0,55 ou mais. No pior caso (foto branca) o texto branco fica a 4,74:1 no ponto mais claro dessa metade. Nome com mais de 2 linhas é cortado; escreva nomes que caibam.
- **Acessibilidade:** `alt=""` na imagem, que é decorativa. O link não leva `aria-label`: seu nome acessível já é "Inglês Conheça", que começa pelo texto visível.
