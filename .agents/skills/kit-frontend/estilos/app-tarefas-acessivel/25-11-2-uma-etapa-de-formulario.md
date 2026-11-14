### 11.2 Uma etapa de formulário

```html
<div class="ui-screen">
  <a class="ui-skip" href="#conteudo">Pular para o conteúdo</a>
  <header class="ui-topbar">
    <div class="ui-topbar__start">
      <span class="ui-brand ui-brand--desktop">
        <span class="ui-brand__name">Aplicativo</span>
      </span>
      <a class="ui-topbtn" href="/explorar"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M112,56V200L40,128Z" opacity="0.2"/><path d="M216,120H120V56a8,8,0,0,0-13.66-5.66l-72,72a8,8,0,0,0,0,11.32l72,72A8,8,0,0,0,120,200V136h96a8,8,0,0,0,0-16ZM104,180.69,51.31,128,104,75.31Z"/></svg> Voltar</a>
    </div>
    <nav class="ui-tabbar ui-tabbar--top" aria-label="Menu principal">
      <a class="ui-tab" href="/inicio"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,120v96H152V152H104v64H40V120a8,8,0,0,1,2.34-5.66l80-80a8,8,0,0,1,11.32,0l80,80A8,8,0,0,1,216,120Z" opacity="0.2"/><path d="M219.31,108.68l-80-80a16,16,0,0,0-22.62,0l-80,80A15.87,15.87,0,0,0,32,120v96a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V160h32v56a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V120A15.87,15.87,0,0,0,219.31,108.68ZM208,208H160V152a8,8,0,0,0-8-8H104a8,8,0,0,0-8,8v56H48V120l80-80,80,80Z"/></svg></span>Início</a>
      <a class="ui-tab ui-tab--active" href="/explorar" aria-current="true"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M128,32a96,96,0,1,0,96,96A96,96,0,0,0,128,32Zm16,112L80,176l32-64,64-32Z" opacity="0.2"/><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216ZM172.42,72.84l-64,32a8.05,8.05,0,0,0-3.58,3.58l-32,64A8,8,0,0,0,80,184a8.1,8.1,0,0,0,3.58-.84l64-32a8.05,8.05,0,0,0,3.58-3.58l32-64a8,8,0,0,0-10.74-10.74ZM138,138,97.89,158.11,118,118l40.15-20.07Z"/></svg></span>Explorar</a>
      <a class="ui-tab" href="/acompanhar"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M216,64V192H128V64Z" opacity="0.2"/><path d="M224,128a8,8,0,0,1-8,8H128a8,8,0,0,1,0-16h88A8,8,0,0,1,224,128ZM128,72h88a8,8,0,0,0,0-16H128a8,8,0,0,0,0,16Zm88,112H128a8,8,0,0,0,0,16h88a8,8,0,0,0,0-16ZM82.34,42.34,56,68.69,45.66,58.34A8,8,0,0,0,34.34,69.66l16,16a8,8,0,0,0,11.32,0l32-32A8,8,0,0,0,82.34,42.34Zm0,64L56,132.69,45.66,122.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32,0l32-32a8,8,0,0,0-11.32-11.32Zm0,64L56,196.69,45.66,186.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32,0l32-32a8,8,0,0,0-11.32-11.32Z"/></svg></span>Acompanhar</a>
      <a class="ui-tab" href="/conta"><span class="ui-tab__pill" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M224,128a95.76,95.76,0,0,1-31.8,71.37A72,72,0,0,0,128,160a40,40,0,1,0-40-40,40,40,0,0,0,40,40,72,72,0,0,0-64.2,39.37h0A96,96,0,1,1,224,128Z" opacity="0.2"/><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24ZM74.08,197.5a64,64,0,0,1,107.84,0,87.83,87.83,0,0,1-107.84,0ZM96,120a32,32,0,1,1,32,32A32,32,0,0,1,96,120Zm97.76,66.41a79.66,79.66,0,0,0-36.06-28.75,48,48,0,1,0-59.4,0,79.66,79.66,0,0,0-36.06,28.75,88,88,0,1,1,131.52,0Z"/></svg></span>Conta</a>
    </nav>
    <div class="ui-topbar__end"><button class="ui-topbtn ui-topbtn--listen" type="button">Ouvir</button></div>
  </header>
  <main id="conteudo" class="ui-main ui-main--wide" aria-labelledby="step-title">
    <div class="ui-steps">
      <span class="ui-steps__bar ui-steps__bar--on" aria-hidden="true"></span>
      <span class="ui-steps__bar ui-steps__bar--on" aria-hidden="true"></span>
      <span class="ui-steps__bar" aria-hidden="true"></span>
      <span class="ui-steps__label">Passo 2 de 3</span>
    </div>
    <h1 class="ui-title" id="step-title">Quando você prefere participar?</h1>
    <p class="ui-lead">Escolha uma opção.</p>
    <fieldset class="ui-fieldset">
      <legend class="ui-sr-only">Horário de participação</legend>
      <div class="ui-options">
        <label class="ui-option">
          <input class="ui-option__input" type="radio" name="horario" value="manha" checked>
          <span class="ui-option__text">De manhã<span class="ui-option__sub">Antes do almoço</span></span>
          <span class="ui-option__check" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M232,56V200a16,16,0,0,1-16,16H40a16,16,0,0,1-16-16V56A16,16,0,0,1,40,40H216A16,16,0,0,1,232,56Z" opacity="0.2"/><path d="M205.66,85.66l-96,96a8,8,0,0,1-11.32,0l-40-40a8,8,0,0,1,11.32-11.32L104,164.69l90.34-90.35a8,8,0,0,1,11.32,11.32Z"/></svg></span>
        </label>
        <label class="ui-option">
          <input class="ui-option__input" type="radio" name="horario" value="tarde">
          <span class="ui-option__text">De tarde</span>
          <span class="ui-option__check" aria-hidden="true"><svg viewBox="0 0 256 256" fill="currentColor" focusable="false" aria-hidden="true"><path d="M232,56V200a16,16,0,0,1-16,16H40a16,16,0,0,1-16-16V56A16,16,0,0,1,40,40H216A16,16,0,0,1,232,56Z" opacity="0.2"/><path d="M205.66,85.66l-96,96a8,8,0,0,1-11.32,0l-40-40a8,8,0,0,1,11.32-11.32L104,164.69l90.34-90.35a8,8,0,0,1,11.32,11.32Z"/></svg></span>
        </label>
      </div>
    </fieldset>
  </main>
  <div class="ui-footer ui-footer--wide">
    <div class="ui-footer__inner"><button class="ui-btn ui-btn--primary" type="button">Continuar</button></div>
  </div>
</div>
```

Os exemplos apresentam a composição visual. O agente deve implementar os controladores e a semântica de formulário pertinente, além de substituir os símbolos de navegação pelos SVGs da família escolhida.
