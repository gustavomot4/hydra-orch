#### Checklist de aceite

Uma entrega só está pronta com todos os itens marcados e com a evidência de cada um no relatório.

- [ ] Os passos desta seção rodaram (o de TypeScript só havendo TypeScript) e o relatório traz o resultado real de cada um, inclusive o que falhou.
- [ ] No tamanho `desktop`, toda lista principal mostra busca e paginação sem rolar a página; a tabela de medidas traz a altura do documento e a da janela.
- [ ] Nenhuma tela tem rolagem horizontal nos tamanhos `reflow` e `zoom-200`.
- [ ] Zero violação no axe em cada grupo de telas, e o roteiro manual foi feito tela por tela (seção 4, Acessibilidade, “Como provar”).
- [ ] Toda cor usada é um token e todo par de texto e fundo está na tabela de contraste (seção 4).
- [ ] Nenhum texto abaixo de 14 px e nenhum controle abaixo de 44 × 44 px, medidos por script nas telas novas; a tabela de medidas traz a menor fonte e o menor controle.
- [ ] Cada tela nova foi exercitada em carregamento, vazio, erro de leitura, erro de gravação e sucesso (seção 4, Estados).
- [ ] Recarregar a página depois de cada fluxo mantém o que foi gravado, e a simples consulta não grava nada (seção 5).
- [ ] Protótipos, testes, capturas e documentos só têm dados fictícios (seção 2, Conduta; seção 5).
- [ ] O relatório lista toda diferença em relação às imagens aprovadas e diz o que não foi verificado.
- [ ] Nenhum commit, push ou publicação foi feito sem autorização dada para aquela ação.

### 7. Documentação e relatório

- README com o comportamento atual, como executar (com a versão do Node) e os limites.
- Um documento por entrega: pedido, decisões adotadas, contrato de dados, o que mudou, evidência executada, diferenças em relação ao aprovado e dependências abertas. Separe sempre decisão confirmada, proposta, implementação e evidência.
- Uma ficha curta por módulo com regras, arquivos, testes e limites, e um índice para localizar tudo.
- Guarde junto da documentação as imagens aprovadas, os protótipos (`prototipos/`), o gerador do cenário fictício e o servidor da origem isolada, com caminhos relativos.
- No relatório final, comece pelo que foi encontrado e validado, depois liste o que depende de mim.

### 8. Armadilhas que já custaram tempo

- **Lista que “cabe” só no monitor grande.** Meça no tamanho `desktop`, que já desconta as barras do navegador, e escreva um teste; a paginação some com dois registros a mais.
- **Compactar diminuindo a fonte.** Texto abaixo de 14 px, ou rótulo de campo abaixo de 16 px, piora a leitura. Compacte com espaçamento e com uma linha por registro.
- **Título removido para ganhar espaço.** Quebra a hierarquia de títulos. Oculte visualmente e mantenha no HTML.
- **Texto longo sem espaços.** Estoura grades e tabelas. Use `overflow-wrap: anywhere` e `min-width: 0` nas colunas flexíveis, e teste com nomes de 300 caracteres.
- **Rota em hash que não remonta.** Navegar para a mesma rota não reinicia o formulário. Trate isso na aplicação e, nos testes, navegue pelos links da interface.
- **Envio duplo no mesmo instante.** Desabilitar o botão não basta; trave no ViewModel e torne a operação idempotente no Model.
- **axe no meio de uma transição.** Ele pode ler uma cor intermediária e acusar contraste. Nas varreduras, emule movimento reduzido.
- **Moeda em pt-BR.** O separador entre “R$” e o número é um espaço não separável; nos testes use `\s`.
- **Seletores ambíguos.** O mesmo nome aparece na lista e na auditoria. Use papel, nome exato e a região.
- **Varredura única de todas as telas.** Estoura o tempo limite conforme o sistema cresce. Divida por grupo de telas.
- **Teste sensível a tempo.** Testes com relógio simulado ou envio lento falham quando a máquina está ocupada. Não rode processos pesados em paralelo e repita o teste isolado antes de concluir que é defeito.
- **Dois builds, uma pasta.** O build normal e o da hospedagem escrevem no mesmo lugar. O último build precisa ser o que será servido ou testado.
- **Migração “esperta”.** Preencher por inferência um dado que falta cria dado falso (exemplo do Dental Flow: unidade, forma de atendimento, valor). Pendência visível e vinculação explícita.
- **Indicador sem definição, ou com a definição escrita no cartão.** Todo número do painel tem a definição a um toque, dizendo o que conta e o que não conta. No cartão ficam só o rótulo e o número: texto a mais atrapalha quem precisa bater o olho.
