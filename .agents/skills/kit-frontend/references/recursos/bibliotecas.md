# Bibliotecas e geração de mídia

Catálogo para não escrever à mão o que já existe, e para conseguir o que um agente sozinho não produz: imagem, vídeo, som e 3D. Licença e tamanho conferidos no npm em 30/10/2026, salvo marcação. Confira de novo antes de instalar.

## Regras

1. **O que o projeto já usa vem primeiro.** Só acrescente se resolver um problema real da tela.
2. **O nativo vem antes:** CSS para transição, `<dialog>` para diálogo, `<details>` para expansível, `popover` para balão.
3. **Antes de instalar:** `npm view <pacote> license dist.unpackedSize`. Sem licença clara, não use em produto.
4. **Protótipo pode usar CDN.** Produção instala com versão fixa e serve do próprio projeto.
5. **Biblioteca pronta traz a aparência pronta.** Use o comportamento e troque o visual (`references/marca/anti-generico.md`).
6. **Movimento e 3D custam.** Respeite `prefers-reduced-motion`, ofereça alternativa estática e meça o peso num celular simples.

## Código

| Precisa de | Use | Pacote | Licença | Observação |
| --- | --- | --- | --- | --- |
| Diálogo, combobox, abas e menus acessíveis em React | React Aria Components | `react-aria-components` | Apache-2.0 | O mais completo em acessibilidade. Sem visual |
| O mesmo, em peças separadas | Radix Primitives | `@radix-ui/react-dialog` e outros | MIT | Base do shadcn/ui |
| O mesmo, fora do React | Ark UI | `@ark-ui/react`; há versões para outros frameworks (não conferidas) | MIT | Sem visual |
| Ícones com personalidade | Phosphor | `@phosphor-icons/web` | MIT | Seis pesos, inclusive duotone |
| Ícones de traço | Iconoir, Tabler | `iconoir`, `@tabler/icons-webfont` | MIT; a Tabler não declara no npm: confira | Boas opções ao Lucide |
| Ícones padrão de gerador | Lucide | `lucide` | ISC | Serve, mas é a escolha de inércia. Decida |
| Fonte servida pelo projeto | Fontsource | `@fontsource-variable/<familia>` | A da fonte: confira | Sem CDN em produção, por causa da LGPD. Qual escolher: `references/recursos/fontes.md` |
| Gerar paleta com contraste | `scripts/paleta.mjs` | Nenhum | Do kit | Parte de uma cor e calcula todos os pares |
| Logotipo em curvas | `scripts/logotipo.py`, com fonttools; em JavaScript, opentype.js | `fonttools` (pip), `opentype.js` | fonttools: MIT, por conhecimento geral; opentype.js: MIT | `logotipo.py` aplica o kerning da fonte: confira no olho |
| Reduzir fonte a um subconjunto | pyftsubset, subset-font | `fonttools` (pip), `subset-font` | subset-font: BSD-3-Clause | Fonte com subconjunto latino pesa bem menos |
| Animação de interface | Motion | `motion` | MIT | Para o que CSS não resolve |
| Animação com linha do tempo e rolagem | GSAP | `gsap` | Licença própria, gratuita, não é de código aberto: leia | Para peças de marca |
| Animação feita em ferramenta | dotLottie, Rive | `@lottiefiles/dotlottie-web`, `@rive-app/canvas` | MIT | Pedem um arquivo de animação. A Hyper3D carrega Rive |
| Carrossel | Embla, Swiper | `embla-carousel`, `swiper` | MIT | Embla é o menor. Swiper aparece em Nubank, 99 e Fortnite. Siga as regras de pausa |
| Rolagem suavizada | Lenis | `lenis` | MIT | Evite salvo pedido: mexe na rolagem nativa e no zoom |
| Modelo 3D numa página, com pouco código | model-viewer | `@google/model-viewer` | Apache-2.0 | Tem `alt` e carrega `.glb`. Comece por ele |
| Cena 3D sob medida | Three.js | `three` | MIT | Peso alto; exija versão estática |
| Cena feita em editor visual | Spline | `@splinetool/viewer` | Sem licença no npm: leia os termos | Conveniente, com dependência do serviço |
| Gráfico completo | ECharts | `echarts` | Apache-2.0 | Grande; importe só os módulos usados |
| Gráfico sob medida em React | visx | `@visx/visx` | MIT | Peças de baixo nível |
| Gráfico simples | SVG à mão | Nenhum | Nenhuma | Costuma bastar e pesa quase nada |
| Conversão e cálculo de cor | culori | `culori` | MIT | OKLCH para sRGB, usado para gerar paletas |
| Escalas de cor prontas | Radix Colors | `@radix-ui/colors` | MIT | Use a lógica; os valores prontos viram padrão |
| Varredura extra de acessibilidade | axe | `@axe-core/playwright` | MPL-2.0 | Complementa `scripts/verificar.mjs` em projeto com Playwright |

## Mídia pronta

Baseado em conhecimento geral, não conferido nesta rodada. Confirme a licença de cada arquivo.

| Precisa de | Onde |
| --- | --- |
| Modelos 3D, texturas e iluminação | Poly Haven, ambientCG |
| Modelos 3D estilizados, para jogo | Kenney |
| Fontes | Google Fonts, Fontshare |
| Foto | Unsplash, Pexels. Banco de imagem denuncia: é o último recurso |

## Gerar imagem, vídeo, som e 3D com IA

Sem imagem, a tela fica sem a principal coisa que os sites admirados têm (`references/marca/criatividade.md`). Ordem de preferência:

1. Foto e material reais do negócio.
2. Mídia gerada com um estilo único, escrito no `DESIGN.md`.
3. Ilustração própria em SVG, feita pelo agente.
4. Nenhuma imagem. Banco de imagem só se o resto não for possível.

| Ferramenta | O que faz | Como o agente usa |
| --- | --- | --- |
| [CozyGPU](https://cozygpu.com/models) | Monta 12 modelos abertos (6 de imagem, 4 de vídeo, 2 de áudio) em GPU na nuvem, na conta RunPod do dono, com cobrança por segundo de uso | A página não cita API. O agente escreve os prompts em `design/midia.md` e o dono gera |
| [Hyper3D Rodin](https://hyper3d.ai/pt) | Gera modelo 3D a partir de texto ou imagem | O site cita API e integrações, não testadas. Exporte `.glb` e mostre com `model-viewer` |

Se o ambiente tiver um gerador disponível, use-o. Se não tiver, não finja: entregue `design/midia.md` (modelo em `assets/modelos/midia.md`) e um substituto do tamanho exato na tela.

**Regras para o que é gerado:**

- **Um estilo só.** Escreva um parágrafo de estilo no `DESIGN.md` e repita em todo prompt. Imagens sem unidade denunciam mais que nenhuma.
- **Nada de pessoa falsa como real.** Rosto gerado não pode se passar por cliente, funcionário ou depoimento. Sem imagem de pessoa real sem autorização.
- **Licença por modelo.** Modelos abertos têm licenças diferentes, e alguns proíbem uso comercial. Registre a licença em `design/midia.md`.
- **Sem marca nem personagem de terceiros.**
- **Entrega técnica:** WebP ou AVIF, `width` e `height` declarados, `alt` real, `loading="lazy"` fora da primeira dobra. Vídeo com pausa, sem som automático e com imagem estática para movimento reduzido.
- **Confira antes de usar:** mãos, texto dentro da imagem e detalhes do setor costumam sair errados.
