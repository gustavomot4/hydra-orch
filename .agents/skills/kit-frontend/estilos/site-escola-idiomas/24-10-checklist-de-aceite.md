## 10. Checklist de aceite

**Tokens e tipografia**
- [ ] Tokens do §1 definidos em um único arquivo; nenhuma cor em hex nem a cor da marca escrita em componente (a exceção é o preto com alfa dos scrims, §3.2 e §5.2); `--brand` é a única cor de marca escrita; `color-scheme: light` declarado
- [ ] Montserrat variável (`wght 400..700`), auto-hospedada, com `font-display: swap`; só os pesos 400, 500, 600 e 700 aparecem no CSS
- [ ] Corpo em 17px com altura de linha 1.7; títulos com `clamp()` de termo `rem + vw`; nenhum `font-size` em `px` (exceto o piso de `--fs-ui`) e nenhuma media query de tipografia
- [ ] Com a marca padrão, os pares do §7 dão as razões da tabela; com outra marca, os quatro testes do §1.1 foram refeitos e todo par de texto passa 4,5:1 e todo limite de campo, 3,0:1

**Layout**
- [ ] CSS base do celular; toda media query é `min-width` em 576, 768 ou 1200px; nada rola na horizontal a 320px de largura
- [ ] Seções com 60px em cima e embaixo; a partir de 768px, 100px em cima e 120px embaixo; fundos alternados como nas tabelas do §5.2 e do §5.3
- [ ] Home na ordem do §5.2 (12 seções); template de curso do §5.3 reaproveitado para todos os idiomas

**Conversão**
- [ ] As duas conversões (Pré-matrícula e Teste de nível) visíveis em toda página: no header a partir de 1200px, na barra fixa de 56px abaixo disso
- [ ] "Encontre uma unidade" na faixa 1 do header, na seção 5 da home e no passo 1 da pré-matrícula; busca por CEP, estado, cidade ou nome, com os estados do §5.4
- [ ] Wizard de pré-matrícula em 3 passos, com selects em cascata, os estados do §5.5 e, para menor de 18 anos, o bloco do responsável
- [ ] Faixa de CTA com formulário de 1 campo por vez, texto de consentimento com link para a Política de Privacidade e nada gravado antes do último passo
- [ ] Teste de nível em 4 etapas (§5.7); SEO local do §5.9 (JSON-LD `LanguageSchool` por unidade e `Course` por curso, `sitemap.xml`)

**Acessibilidade**
- [ ] Foco de teclado visível em todo interativo pela regra global do §1; nenhum `outline: none`; alvos de 44px nos botões e campos
- [ ] Todo campo com `<label for>`, `type` e `autocomplete`; erro com borda de 2px `--danger`, ícone e texto em `role="alert"`
- [ ] `<html lang="pt-BR">`, skip link, um `<h1>` por página, `<title>` único, landmarks; `aria-label` em todo link de texto genérico e em todo botão só de ícone
- [ ] Texto sobre foto só com scrim (hero e tile de curso)
- [ ] Carrosséis com setas, bullets, `inert` nos slides fora da vista e autoplay só no hero, com botão de pausa
- [ ] `prefers-reduced-motion: reduce` respeitado também no JS: Swiper sem autoplay e em `slide`, contador no valor final, sem revelação de scroll

**Desempenho e dados pessoais**
- [ ] Home, cursos e unidades com o conteúdo no HTML do servidor (SSG ou SSR); conteúdo legível com JS desligado
- [ ] Imagens em WebP com `srcset`, `width`, `height` e `alt` real (ou `alt=""` se decorativa); `loading="lazy"` abaixo da dobra e nunca na imagem do hero, que leva `fetchpriority="high"`
- [ ] Em 320 × 256 (altura até 480px), header, barra das conversões, cookie bar, chat e Libras rolam junto com a página e nada fixo cobre a janela; todo link fora de parágrafo tem 44px de altura (§4).
- [ ] Cookie bar não-bloqueante, com `Recusar` e `Aceitar` de mesmo peso; nenhuma tag de rastreamento dispara antes do aceite; eventos do item 10 do §8 só depois dele
- [ ] Chat só carrega depois da primeira interação; VLibras carrega com `defer` e o botão aparece ao chegar; chat no canto inferior direito acima da cookie bar e da barra das conversões; Libras no meio da borda direita
- [ ] Lighthouse ≥ 90 em Performance, Acessibilidade, SEO e Boas Práticas

---
