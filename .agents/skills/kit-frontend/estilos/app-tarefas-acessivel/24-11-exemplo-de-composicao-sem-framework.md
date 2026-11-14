## 11. Exemplo de composição sem framework

O exemplo usa as classes e tokens deste documento. Insira os dois blocos CSS em um arquivo de estilos ou em `<style>`. Os SVGs são espaços reservados: substitua-os pelos desenhos Phosphor Duotone apropriados, mantendo o caráter decorativo. Rotas e eventos devem ser conectados ao produto.

### 11.1 Catálogo

```html
<div class="ui-screen">
  <a class="ui-skip" href="#conteudo">Pular para o conteúdo</a>
  <header class="ui-topbar">
    <div class="ui-topbar__start">
      <span class="ui-brand">
        <span class="ui-brand__name">Aplicativo</span>
      </span>
    </div>
    <nav class="ui-tabbar ui-tabbar--top" aria-label="Menu principal">
      <a class="ui-tab" href="/inicio"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,120v96H152V152H104v64H40V120a8,8,0,0,1,2.34-5.66l80-80a8,8,0,0,1,11.32,0l80,80A8,8,0,0,1,216,120Z" opacity="0.2"/><path d="M219.31,108.68l-80-80a16,16,0,0,0-22.62,0l-80,80A15.87,15.87,0,0,0,32,120v96a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V160h32v56a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V120A15.87,15.87,0,0,0,219.31,108.68ZM208,208H160V152a8,8,0,0,0-8-8H104a8,8,0,0,0-8,8v56H48V120l80-80,80,80Z"/></svg></span>Início</a>
      <a class="ui-tab ui-tab--active" href="/explorar" aria-current="page"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M128,32a96,96,0,1,0,96,96A96,96,0,0,0,128,32Zm16,112L80,176l32-64,64-32Z" opacity="0.2"/><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216ZM172.42,72.84l-64,32a8.05,8.05,0,0,0-3.58,3.58l-32,64A8,8,0,0,0,80,184a8.1,8.1,0,0,0,3.58-.84l64-32a8.05,8.05,0,0,0,3.58-3.58l32-64a8,8,0,0,0-10.74-10.74ZM138,138,97.89,158.11,118,118l40.15-20.07Z"/></svg></span>Explorar</a>
      <a class="ui-tab" href="/acompanhar"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,64V192H128V64Z" opacity="0.2"/><path d="M224,128a8,8,0,0,1-8,8H128a8,8,0,0,1,0-16h88A8,8,0,0,1,224,128ZM128,72h88a8,8,0,0,0,0-16H128a8,8,0,0,0,0,16Zm88,112H128a8,8,0,0,0,0,16h88a8,8,0,0,0,0-16ZM82.34,42.34,56,68.69,45.66,58.34A8,8,0,0,0,34.34,69.66l16,16a8,8,0,0,0,11.32,0l32-32A8,8,0,0,0,82.34,42.34Zm0,64L56,132.69,45.66,122.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32,0l32-32a8,8,0,0,0-11.32-11.32Zm0,64L56,196.69,45.66,186.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32,0l32-32a8,8,0,0,0-11.32-11.32Z"/></svg></span>Acompanhar</a>
      <a class="ui-tab" href="/conta"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M224,128a95.76,95.76,0,0,1-31.8,71.37A72,72,0,0,0,128,160a40,40,0,1,0-40-40,40,40,0,0,0,40,40,72,72,0,0,0-64.2,39.37h0A96,96,0,1,1,224,128Z" opacity="0.2"/><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24ZM74.08,197.5a64,64,0,0,1,107.84,0,87.83,87.83,0,0,1-107.84,0ZM96,120a32,32,0,1,1,32,32A32,32,0,0,1,96,120Zm97.76,66.41a79.66,79.66,0,0,0-36.06-28.75,48,48,0,1,0-59.4,0,79.66,79.66,0,0,0-36.06,28.75,88,88,0,1,1,131.52,0Z"/></svg></span>Conta</a>
    </nav>
    <div class="ui-topbar__end"><button class="ui-topbtn ui-topbtn--listen" type="button">Ouvir</button></div>
  </header>
  <main id="conteudo" class="ui-main ui-main--wide" aria-labelledby="catalog-title">
    <h1 class="ui-title" id="catalog-title">Explorar atividades</h1>
    <div class="ui-catalog">
      <div class="ui-search" role="search">
        <label class="ui-sr-only" for="busca">Buscar atividade</label>
        <input class="ui-search__input" id="busca" type="search" placeholder="Buscar atividade">
      </div>
      <div class="ui-catalog__body">
        <section class="ui-catalog__filters" aria-labelledby="filter-title">
          <h2 class="ui-section__title" id="filter-title">Filtrar atividades</h2>
          <div class="ui-chips" role="group" aria-label="Filtros">
            <button class="ui-chip" type="button" aria-pressed="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M232,56V200a16,16,0,0,1-16,16H40a16,16,0,0,1-16-16V56A16,16,0,0,1,40,40H216A16,16,0,0,1,232,56Z" opacity="0.2"/><path d="M205.66,85.66l-96,96a8,8,0,0,1-11.32,0l-40-40a8,8,0,0,1,11.32-11.32L104,164.69l90.34-90.35a8,8,0,0,1,11.32,11.32Z"/></svg> Perto de mim</button>
            <button class="ui-chip" type="button" aria-pressed="false">Nesta semana</button>
          </div>
        </section>
        <section class="ui-catalog__results" aria-label="Resultados">
          <p class="ui-catalog__summary" role="status">Página 1 · Atividades 1 a 1</p>
          <ul class="ui-list">
            <li class="ui-catalog-item">
              <article class="ui-card ui-card--pad">
                <div class="ui-card__head">
                  <span class="ui-icon ui-icon--cat-2" aria-hidden="true">
                    <svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,48V88H40V48a8,8,0,0,1,8-8H208A8,8,0,0,1,216,48Z" opacity="0.2"/><path d="M208,32H184V24a8,8,0,0,0-16,0v8H88V24a8,8,0,0,0-16,0v8H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM72,48v8a8,8,0,0,0,16,0V48h80v8a8,8,0,0,0,16,0V48h24V80H48V48ZM208,208H48V96H208V208Z"/></svg>
                  </span>
                  <div class="ui-card__headtext">
                    <h2 class="ui-card__title"><a class="ui-card__link" href="/atividades/oficina">Oficina de fotografia</a></h2>
                    <p class="ui-card__sub">Espaço Horizonte · exemplo fictício</p>
                    <div class="ui-card__badge"><span class="ui-badge ui-badge--info">Inscrições abertas</span></div>
                  </div>
                </div>
                <ul class="ui-facts"><li class="ui-fact">Sábado, às 10h</li><li class="ui-fact">Unidade Centro</li></ul>
              </article>
            </li>
          </ul>
          <nav class="ui-catalog__pagination" aria-label="Páginas de atividades">
            <button class="ui-btn ui-btn--secondary ui-btn--inline" type="button" disabled>Anterior</button>
            <span>Página 1</span>
            <button class="ui-btn ui-btn--secondary ui-btn--inline" type="button" disabled>Próxima</button>
          </nav>
        </section>
      </div>
    </div>
  </main>
  <nav class="ui-tabbar ui-tabbar--bottom" aria-label="Menu principal">
    <a class="ui-tab" href="/inicio"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,120v96H152V152H104v64H40V120a8,8,0,0,1,2.34-5.66l80-80a8,8,0,0,1,11.32,0l80,80A8,8,0,0,1,216,120Z" opacity="0.2"/><path d="M219.31,108.68l-80-80a16,16,0,0,0-22.62,0l-80,80A15.87,15.87,0,0,0,32,120v96a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V160h32v56a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V120A15.87,15.87,0,0,0,219.31,108.68ZM208,208H160V152a8,8,0,0,0-8-8H104a8,8,0,0,0-8,8v56H48V120l80-80,80,80Z"/></svg></span>Início</a>
    <a class="ui-tab ui-tab--active" href="/explorar" aria-current="page"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M128,32a96,96,0,1,0,96,96A96,96,0,0,0,128,32Zm16,112L80,176l32-64,64-32Z" opacity="0.2"/><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216ZM172.42,72.84l-64,32a8.05,8.05,0,0,0-3.58,3.58l-32,64A8,8,0,0,0,80,184a8.1,8.1,0,0,0,3.58-.84l64-32a8.05,8.05,0,0,0,3.58-3.58l32-64a8,8,0,0,0-10.74-10.74ZM138,138,97.89,158.11,118,118l40.15-20.07Z"/></svg></span>Explorar</a>
    <a class="ui-tab" href="/acompanhar"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,64V192H128V64Z" opacity="0.2"/><path d="M224,128a8,8,0,0,1-8,8H128a8,8,0,0,1,0-16h88A8,8,0,0,1,224,128ZM128,72h88a8,8,0,0,0,0-16H128a8,8,0,0,0,0,16Zm88,112H128a8,8,0,0,0,0,16h88a8,8,0,0,0,0-16ZM82.34,42.34,56,68.69,45.66,58.34A8,8,0,0,0,34.34,69.66l16,16a8,8,0,0,0,11.32,0l32-32A8,8,0,0,0,82.34,42.34Zm0,64L56,132.69,45.66,122.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32,0l32-32a8,8,0,0,0-11.32-11.32Zm0,64L56,196.69,45.66,186.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32,0l32-32a8,8,0,0,0-11.32-11.32Z"/></svg></span>Acompanhar</a>
    <a class="ui-tab" href="/conta"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M224,128a95.76,95.76,0,0,1-31.8,71.37A72,72,0,0,0,128,160a40,40,0,1,0-40-40,40,40,0,0,0,40,40,72,72,0,0,0-64.2,39.37h0A96,96,0,1,1,224,128Z" opacity="0.2"/><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24ZM74.08,197.5a64,64,0,0,1,107.84,0,87.83,87.83,0,0,1-107.84,0ZM96,120a32,32,0,1,1,32,32A32,32,0,0,1,96,120Zm97.76,66.41a79.66,79.66,0,0,0-36.06-28.75,48,48,0,1,0-59.4,0,79.66,79.66,0,0,0-36.06,28.75,88,88,0,1,1,131.52,0Z"/></svg></span>Conta</a>
  </nav>
</div>
```
