### 3.5 Formulário progressivo de 1 campo (padrão de captura de lead)

Na leitura do autor, o detalhe mais inteligente do site analisado: a faixa de CTA pede **um campo por vez**, com contador `1 de 5` e um botão-seta. A intenção é reduzir o atrito percebido (hipótese do autor, sem medição).

- Um único campo visível por vez: `.input` de 44px, fundo `--white`, `border-radius: var(--r-full)`. **Ao lado** dele, não dentro, o botão-seta circular de 44px: fundo `--white`, ícone `--brand-text`, `aria-label="Próximo campo"`.
- Label acima do campo, com asterisco antes do texto: `* E-mail`. Dentro da faixa o asterisco herda a cor do texto (`--on-brand`); na cor da marca ele sumiria no fundo. O campo leva `required`, e a legenda "* obrigatório" aparece ao lado do contador.
- Contador `1 de 5` à direita, abaixo do campo, em `--fs-caption` e na cor do texto da faixa. Ele fica numa região `aria-live="polite"` que anuncia "Passo 2 de 5" a cada troca.
- Avança com Enter **ou** clique na seta. Do passo 2 em diante há um botão "Voltar" (texto sublinhado em `--fs-caption`, à esquerda do contador). A cada troca o foco vai para o novo campo.
- Ordem dos 5 campos, com `type` e `autocomplete`: **E-mail** (`email` / `email`) → **Nome** (`text` / `name`) → **Telefone/WhatsApp** (`tel` / `tel`) → **Cidade** (`text` / `address-level2`) → **Curso de interesse** (`<select>`). E-mail primeiro porque é o campo que o navegador preenche sozinho e o que identifica o lead.
- **Privacidade** (recomendação técnica; não substitui orientação jurídica): abaixo do campo, desde o passo 1, o texto "Ao continuar, você concorda em receber contato da {Marca} sobre cursos e matrícula. [Política de Privacidade]". Nada é gravado nem enviado a ferramenta de rastreamento antes do envio do último passo.

| Estado | O que aparece |
|---|---|
| Erro de campo | `aria-invalid="true"` no campo; abaixo dele, ícone de alerta + mensagem em peso 600 na cor do texto da faixa, em `<p role="alert">` ligado por `aria-describedby` ("Digite um e-mail válido, como nome@exemplo.com") |
| Enviando | a seta vira indicador de progresso e o botão fica `disabled` |
| Sucesso | o formulário é trocado por "Pronto, {nome}! Enviamos a confirmação para {e-mail}." e o foco vai para esse texto |
| Falha de envio | "Não foi possível enviar. Seus dados continuam aqui." + botão "Tentar de novo" (`.btn-pill--on-brand`) |
