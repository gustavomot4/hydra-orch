### 5. Dados e regras

- **Contrato de armazenamento.** Mantenha chave, versão, IDs e relações. Prefira mudanças aditivas: campos e coleções novos são opcionais e lidos como vazios quando ausentes. A leitura nunca grava. Mudança incompatível precisa ser proposta com a migração antes de ser feita.
- **Nada é atribuído em silêncio.** Registro antigo sem um dado novo aparece como pendência (exemplo do Dental Flow: “Sem clínica”), com uma tela para vincular explicitamente os registros escolhidos. Texto livre antigo é exibido como “registro anterior”, sem conversão automática.
- **Desconhecido não é zero.** Valor não informado fica vazio, é contado à parte e nunca entra em soma como zero.
- **Operações idempotentes.** Repetir uma ação de conclusão devolve o registro existente, sem duplicar itens nem histórico.
- **Situação que exige registro vira ação.** Se “Concluída” depende de informar o que foi feito, ela sai do campo de situação e passa a ser um botão com tela própria.
- **Travas explícitas.** O que foi enviado ou validado não muda até ser devolvido para correção. Estados de documentos (rascunho, enviado, em correção, validado) são independentes do estado do registro de origem.
- **Efeitos colaterais só quando pedidos.** Concluir um atendimento não cria lançamento financeiro; registrar estoque não cria pagamento.
- **Histórico e auditoria.** Cada gravação efetiva registra data, responsável e o que mudou, na mesma transação. Salvar sem mudança não gera evento.
- **Dinheiro em centavos inteiros.** Não invente desconto, arredondamento, comissão ou repasse.
- **Demonstração não é segurança.** Login e perfis locais são telas de demonstração: não persista senhas e não trate uma visão local como controle de acesso. Enquanto os dados forem locais, a tela de entrada mostra: “Demonstração: os dados ficam só neste navegador, sem proteção. Não cadastre pessoas reais.”
- **Dado fictício reconhecível.** Demonstração, protótipo, teste e documentação só levam dados fictícios, feitos para não se confundirem com reais: nomes inventados, e-mail em `example.com`, telefone com DDD 00 e CPF com dígito verificador inválido. Se a validação da interface recusar um desses valores, deixe o campo vazio; não gere um número válido.

### 6. Validação

Antes de dizer que uma entrega está pronta, rode e relate o resultado real de:

1. Lint.
2. Havendo TypeScript, `tsc --noEmit`.
3. Testes unitários dos Models, sem navegador e sem framework extra (`node --test`). Cada regra dos critérios de aceite tem um teste.
4. Build normal e build com o caminho base da hospedagem.
5. Testes de ponta a ponta com Playwright (`@playwright/test`) em dois projetos, `desktop` e `celular`, nos tamanhos da seção 4, no servidor de desenvolvimento e também na prévia do build final.

O que os testes de ponta a ponta precisam provar:

- Cada fluxo completo, seguido de recarregar a página e comparar o que ficou gravado.
- Falha de leitura e de gravação: mensagem, foco, preenchimento conservado e repetição sem duplicar. Esses testes dependem do painel de revisão e rodam só onde ele existe (servidor de desenvolvimento e origem isolada); na prévia do build, um teste confirma que `#/revisao` não existe.
- Teclado e foco nos diálogos e formulários.
- Uma varredura com axe (`@axe-core/playwright`) em todas as telas, dividida por grupo de telas, mais: nomes muito longos sem espaços, os tamanhos `reflow`, `zoom-200`, `tablet` e `desktop-largo`, nenhum erro de JavaScript e armazenamento inalterado pela simples consulta (com API: nenhuma requisição de escrita ao consultar).
- Que nenhum texto visível tem menos de 14 px e nenhum controle tem menos de 44 × 44 px, medidos por script em cada tela.
- Que listas principais mostram busca e paginação sem rolar a página no tamanho `desktop`, medindo a altura do documento contra a da janela.
- Que snapshots antigos abrem sem conversão e sem gravação (com API, este teste não se aplica).

Complete com capturas reais das telas na origem isolada e uma tabela de medidas (altura do documento e da janela, rolagem horizontal, menor fonte e menor controle, erros de console). Diga o que essa prova não cobre: teste com pessoas, leitor de tela, dispositivo físico, backend.
