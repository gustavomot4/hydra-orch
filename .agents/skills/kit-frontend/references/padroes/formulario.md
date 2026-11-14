# Formulário

**Quando:** cadastro, edição, agendamento, qualquer coleta de dados.

## Regra

- **Peça só o necessário.** Obrigatório é o que a regra de negócio exige. Marque os **opcionais** com "(opcional)"; não use asterisco quando a maioria é obrigatória.
- **Rótulo visível acima do campo.** Dica de uma frase abaixo do rótulo. Placeholder só como exemplo de formato.
- **Preencha pela pessoa.** CEP preenche o endereço, com foco indo para o número; se a busca falhar, os campos ficam livres. `autocomplete` e `inputmode` em todo campo. Comece do contexto da tela de origem. (G15)
- **Tamanho do campo sugere o tamanho da resposta.** Largura limitada e formulário centralizado na área útil. (G08)
- **Mais de 8 campos:** divida em seções com título. Para público com pouca familiaridade, uma pergunta por tela, com "Voltar" no topo e "Continuar" fixo no rodapé.
- **Valide ao tentar avançar**, não enquanto a pessoa digita. Aceite formatos variados: limpe espaço e pontuação de número e código antes de validar.
- **Erro em três lugares:** prefixo "Erro:" no título da aba, resumo no topo com foco e links para os campos, mensagem junto de cada campo. Em formulário curto, leve o foco direto ao primeiro campo com erro.
- **Mensagem que resolve:** diga o que corrigir ("Digite o CEP com 8 números"), nunca "Campo inválido". Borda de 2px, ícone e texto. (`references/padroes/retorno.md`)
- **Nunca perca o que foi digitado.** Falha de envio mantém tudo e leva o foco ao aviso.
- **Bloqueie envio duplo** até na lógica, não só no botão. O botão mostra "Salvando…".
- **Confirme antes de sair** com alterações não salvas.
- **Dado pessoal:** diga para que serve e onde está a política, antes do botão de envio.
- **Escolha única até 5 opções:** botões de opção visíveis. Mais que isso, ver `references/padroes/selecao.md`.

## Como os grandes fazem

| Sistema | O que aproveitar |
| --- | --- |
| GOV.UK | Validar ao avançar; resumo de erros com foco; "Erro:" no título; uma pergunta por página; "Continuar"; link "Voltar" no topo; não pedir duas vezes |
| Atlassian | Mensagem de erro: causa, o que fazer, o que acontece se não fizer; sem "por favor" nem "desculpe" para erro simples |
| Uber, iFood | Um passo por tela, resumo sempre à vista, escolha por cartão (observação) |

GOV.UK desliga o `required` nativo e usa `novalidate` para controlar a mensagem. Faça o mesmo quando houver validação própria.

## Erros comuns

Rótulo dentro do campo; campo de data em três dropdowns; máscara que impede colar; erro só em cor; botão desabilitado sem dizer o que falta; formulário que quebra em 375px; campos colados à esquerda com o vazio à direita.

**Verifique:** `a11y-nome`, `a11y-alvo`, `g-colado-a-esquerda`, e rode em 375 e 320 cada formulário. Force o erro e faça o caminho só com teclado.
