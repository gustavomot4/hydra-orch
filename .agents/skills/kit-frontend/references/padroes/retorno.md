# Retorno: aviso, erro, confirmação, desfazer

Escolha o tipo pela gravidade e por quem precisa agir.

| Situação | Use |
| --- | --- |
| Ação concluída, sem consequência | Aviso curto na tela, com `role="status"` |
| Ação concluída e reversível | Aviso com "Desfazer". Melhor que perguntar antes |
| Ação irreversível (cancelar, apagar, falta) | Diálogo, com o número real do impacto: "Apagar 143 registros" |
| Erro que impede continuar | Mensagem no lugar do problema, com `role="alert"` |
| Situação que precisa de atenção | Faixa na própria tela, que não some sozinha |

## Mensagem

Estrutura: o que aconteceu, o que fazer, e o que acontece se não fizer, quando importar. Fale com "você". Sem "por favor" nem "desculpe" em erro simples; guarde para quando a consequência é grave. Sem jargão, sem código. Não sabe a causa? Diga que algo deu errado e dê o próximo passo. Se há várias causas possíveis, comece pela solução mais provável.

Botão com verbo e objeto: "Cancelar consulta", nunca "Sim" ou "OK". No diálogo, o foco abre na opção segura e Esc fecha sem fazer nada.

## Aviso temporário

- Fica de 5 a 8 segundos, conforme o tamanho; pausa com foco ou ponteiro.
- Nunca é o único lugar de uma informação ou ação importante. Tela com "Desfazer" mantém outro caminho para reverter.
- Acima de barras e botão flutuante, sem cobrir ação. Máximo de 3.
- Texto do aviso e estado da tela concordam. (G19)

## Movimento

Mostra de onde algo veio; nada se mexe sozinho. Tudo em 100 a 300ms, com `prefers-reduced-motion` zerando. Jogo e entretenimento são outra regra. (G22)

**Como os grandes fazem:** Atlassian dá a estrutura da mensagem; WhatsApp e Gmail popularizaram o "Desfazer" no lugar de perguntar antes (observação).
