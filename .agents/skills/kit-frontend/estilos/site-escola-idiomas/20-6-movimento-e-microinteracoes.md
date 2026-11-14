## 6. Movimento e microinterações

| Elemento | Comportamento |
|---|---|
| **Entrada de seção** | `opacity: 0; transform: translateY(50px)` → `opacity: 1; translateY(0)` em `var(--t-slow)` quando entra na viewport (transição de CSS disparada por IntersectionObserver). Uma vez só, sem repetir ao voltar. |
| **Texto do hero** | `translateY(10px)` + fade, escalonado (80ms entre linhas) |
| **Hover de tile de curso** | imagem `scale(1.06)` e overlay mais escuro (`rgb(0 0 0 / .2)` a mais), os dois em `var(--t-slow)` |
| **Hover de card** | `translateY(-4px)` + sombra `--shadow-hover`, em `var(--t-base)` |
| **Hover de botão** | só troca de cor, em `var(--t-fast)`. **Nunca** escala nem pula. |
| **Contador de números** | anima de 0 até o valor ao entrar na tela (ex.: `0+ → {N}+ anos`). O valor final já está no HTML. |
| **Carrosséis** | Swiper com as regras do §3.10. Hero: `coverflow` a partir de 1200px, com os slides laterais visíveis, desfocados e `inert`; `slide` abaixo disso; autoplay de 6s com botão de pausa. Cursos e depoimentos: `slide`, sem autoplay. |
| **Scroll** | nativo. Sem biblioteca de smooth scroll. |

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important; animation-iteration-count: 1 !important;
    transition-duration: 1ms !important; scroll-behavior: auto !important;
  }
}
```

O bloco acima só alcança o que é CSS. O que roda em JS também precisa obedecer: com `matchMedia('(prefers-reduced-motion: reduce)').matches`, o Swiper é criado com `autoplay: false` e efeito `slide`, o contador mostra o valor final sem contar, e a revelação de scroll não é aplicada.

⚠️ **Armadilha real observada no site:** o conteúdo revelado por scroll fica **invisível para crawlers e para prints** se o JS falhar ou o observer não disparar. Renderize com `opacity: 1` por padrão e aplique o estado inicial da animação só via JS — senão você perde SEO e acessibilidade.

---
