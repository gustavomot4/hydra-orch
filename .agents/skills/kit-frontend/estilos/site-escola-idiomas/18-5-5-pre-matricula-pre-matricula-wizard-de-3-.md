### 5.5 Pré-matrícula (`/pre-matricula`) — wizard de 3 passos

**Passo 1 — Unidade:** campo de CEP como atalho ("Digite seu CEP para achar a unidade mais próxima") e, abaixo dele, selects em cascata `País → Estado → Cidade → Bairro → Unidade` (cada um só habilita ao preencher o anterior; desabilitado tem a aparência do §3.6). Se a página abre com `?unidade={slug}` (vinda do card de unidade), o wizard começa no passo 2 com a unidade já mostrada e um link "Trocar unidade".
**Passo 2 — Sobre Você:** nome, data de nascimento, e-mail, telefone. Se a data indicar menos de 18 anos, aparece o bloco "Responsável": nome, e-mail e telefone do responsável e a caixa, desmarcada por padrão, "Sou responsável legal e autorizo o tratamento dos dados do aluno para fins de matrícula".
**Passo 3 — Curso:** curso, formato (em grupo / individual), meio (presencial / on-line) e turno (manhã / tarde / noite). Abaixo, o resumo dos três passos para revisão, o link para a Política de Privacidade e o botão "Enviar pré-matrícula".

Cada passo tem "Voltar" (`.btn-outline`) e "Continuar" (`.btn-primary`); os dados preenchidos são mantidos ao voltar. Os itens de consentimento são recomendação técnica e não substituem orientação jurídica.

| Estado | O que aparece |
|---|---|
| Erro de validação | erro de campo do §3.6 em cada campo; o foco vai para o primeiro campo com erro |
| Enviando | "Enviar pré-matrícula" fica `disabled` com o rótulo "Enviando…" |
| Sucesso | tela "Pré-matrícula recebida": número de protocolo, unidade escolhida, "A unidade entra em contato em até {N} dias úteis" e `.btn-outline` "Fazer teste de nível" |
| Falha de envio | "Não foi possível enviar. Seus dados continuam aqui." + `.btn-primary` "Tentar de novo" |

Por que funciona, na leitura do autor: escolher a unidade **primeiro** ancora o lead a uma escola física real (e roteia o lead ao franqueado certo). No wizard de pré-matrícula, não peça dados pessoais antes de o usuário ter escolhido "onde".

### 5.6 Footer (na cor `--brand-dark`)

`<footer>` com logo na cor do texto + 4 colunas de links + copyright. Colunas, cada uma num `<nav aria-label>`: **Sobre nós · Cursos · Faça parte · Acesso**. Repita ali `Pré-matrícula`, `Teste de nível`, `Trabalhe Conosco`, `Seja um franqueado` e `Política de Privacidade`. Texto e links em `--on-brand-dark` sobre `--brand-dark` (7,44:1 com a marca padrão), links sublinhados no hover e no foco. Abaixo de 768px as colunas empilham. O link `Política de Privacidade` da linha do copyright, que fica fora de parágrafo, tem `display: inline-flex` e `min-height: 44px`.
