## 9. Stack recomendada

Parte do que o autor identificou no site analisado, reduzida ao que o guia precisa:

- **Next.js ou Astro, com SSG ou SSR.** É obrigatório: home, cursos e unidades precisam sair em HTML do servidor, pelo alerta do §6 e pelo SEO local do §5.9. SPA renderizado só no cliente não serve.
- **Swiper** para todos os carrosséis (hero, cursos, depoimentos), com as regras do §3.10; com `prefers-reduced-motion: reduce` é criado sem autoplay e com efeito `slide` (§6)
- **Revelação de scroll em CSS + IntersectionObserver**, sem biblioteca de animação; não é aplicada com `prefers-reduced-motion: reduce` (§6)
- **Scroll nativo**, sem biblioteca de smooth scroll
- **Tailwind** com o config do §1.2, ou CSS puro com as custom properties
- **Montserrat** variável (`wght 400..700`), auto-hospedada via `@fontsource-variable/montserrat`, com `font-display: swap`. Só os pesos 400, 500, 600 e 700 são usados.
- **Lucide** para os ícones
- **VLibras** (`https://vlibras.gov.br/app/vlibras-plugin.js`) para acessibilidade em Libras, carregado com `defer`, sem esperar interação: quem precisa de Libras precisa ver o botão ao chegar

O site analisado usa também Framer Motion e Lenis; este guia dispensa os dois para não pôr três bibliotecas de animação na conta de desempenho.

---
