# Escolher fonte

Para quem não tem fonte definida. Todas abaixo são gratuitas, com licença OFL-1.1 conferida no npm em 30/10/2026, e podem ser servidas pelo próprio projeto. A descrição do caráter é uma leitura, não uma regra.

**Esta lista é ponto de partida.** Se todo projeto usar a primeira da fila, ela vira o novo padrão de gerador. Consulte também o catálogo do Google Fonts.

## Por personalidade

Parta das três palavras de `MARCA.md`.

| Personalidade | Famílias | Pacote `@fontsource…` |
| --- | --- | --- |
| Direta e prática | Hanken Grotesk, Schibsted Grotesk, Instrument Sans, Public Sans, Albert Sans | `-variable/hanken-grotesk`, `-variable/schibsted-grotesk`, `-variable/instrument-sans`, `-variable/public-sans`, `-variable/albert-sans` |
| Calorosa e próxima | Figtree, Nunito, Karla, Mulish | `-variable/figtree`, `-variable/nunito`, `-variable/karla`, `-variable/mulish` |
| Forte, de cartaz ou letreiro | Barlow Condensed, Archivo, Big Shoulders Display, Anton, League Gothic, Saira Condensed, Oswald | `/barlow-condensed`, `-variable/archivo`, `-variable/big-shoulders-display`, `/anton`, `-variable/league-gothic`, `/saira-condensed`, `-variable/oswald` |
| Diferente, com atitude | Bricolage Grotesque, Familjen Grotesk, Syne, Unbounded | `-variable/bricolage-grotesque`, `-variable/familjen-grotesk`, `-variable/syne`, `-variable/unbounded` |
| Elegante, editorial | Newsreader, Literata, Source Serif 4, DM Serif Display, Instrument Serif | `-variable/newsreader`, `-variable/literata`, `-variable/source-serif-4`, `/dm-serif-display`, `/instrument-serif` |
| Técnica e precisa | IBM Plex Sans, Sora, Red Hat Display; JetBrains Mono para código e dados | `-variable/ibm-plex-sans`, `-variable/sora`, `-variable/red-hat-display`, `-variable/jetbrains-mono` |
| Manual, de caderno | Caveat, Kalam, Gloria Hallelujah. Só em detalhe, nunca em texto corrido | `-variable/caveat`, `/kalam`, `/gloria-hallelujah` |
| Leitura em primeiro lugar | Atkinson Hyperlegible Next, Lexend. Boas para baixa visão e público amplo | `-variable/atkinson-hyperlegible-next`, `-variable/lexend` |

Por inércia, evite: Inter, Roboto, Poppins, Montserrat, Open Sans e Lato, que o verificador aponta. Fraunces e Space Grotesk também viraram padrão. Se uma delas for a escolha certa, escreva o motivo em "Do's and Don'ts" no `DESIGN.md`.

## Como escolher

1. **Pegue 3 candidatas**, de grupos que a marca aceite, e não a primeira que vier à cabeça.
2. **Teste com este texto real**, nos pesos que vai usar, em 14, 16 e 48px:

   > Não há pão, ação e coração: R$ 1.234,56 às 14:30

   Acentos desenhados à parte, números que não alinham e peso que some em tamanho pequeno eliminam a candidata. Para coluna de números, confira `font-variant-numeric: tabular-nums`.
3. **Mostre na tela.** A escolha acontece nas três direções, em imagem, não numa lista de nomes.
4. **Uma família resolve a maioria.** Use duas só se o contraste tiver função: condensada nos títulos e neutra no texto.
5. **Sistema de trabalho pede leitura em 14 a 16px.** Fonte de impacto fica no título e nos números.

## Como servir

Fonte instalada no seu computador não vai para o aparelho da pessoa. Num projeto com bundler:

```bash
npm install @fontsource-variable/hanken-grotesk
```

```js
import '@fontsource-variable/hanken-grotesk';
```

O nome no CSS leva o sufixo: `font-family: 'Hanken Grotesk Variable', system-ui, sans-serif`. O nome exato está no arquivo CSS do pacote.

Em HTML puro, copie de `node_modules/<pacote>/files/` o WOFF2 do subconjunto `latin`, que cobre `ã õ ç`, para `design/marca/fontes/`, com o arquivo de licença ao lado:

```css
@font-face {
  font-family: 'Hanken Grotesk';
  src: url('fontes/hanken-grotesk-latin-wght-normal.woff2') format('woff2');
  font-weight: 100 900;
  font-display: swap;
}
```

Carregue só os pesos usados. Sem acesso a npm, baixe do Google Fonts e reduza com `pyftsubset`.
