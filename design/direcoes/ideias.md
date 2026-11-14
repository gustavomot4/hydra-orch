# Direções para o Hydra

## Referências de fora do setor

As homepages foram medidas em 14/11/2026 a 1440 × 900. As capturas de referência são saídas locais do kit.

| Referência | Setor | Medida | O que levar |
| --- | --- | --- | --- |
| [Pentagram](https://www.pentagram.com/) | Consultoria de design | ws/b_output/hydra_design/referencia/pentagram.com.jpg. O maior visual ocupou 67% da dobra. A fonte chegou a 52 px. | Uma área dominante orienta o olhar. No Hydra, ela enquadra a criação da tarefa. |
| [Figma](https://www.figma.com/) | Software de design colaborativo | ws/b_output/hydra_design/referencia/figma.com.jpg. Títulos de 56 px e 44 px. Uma sobreposição cobriu 12% da dobra. | A escala distingue a ação principal do contexto. No Hydra, a pergunta em destaque conduz ao campo. |

Na leitura das referências, a Pentagram usa escala para concentrar atenção em um trabalho por vez. A Figma apresenta uma proposta principal antes de desdobrar ferramentas. Aplicação no Hydra: tarefa e botão dominam a primeira leitura, com configurações agrupadas e sessões em uma área própria. A fotografia de portfólio e a densidade da navegação de marketing pertencem às páginas de referência.

## Conceitos

| Direção | Conceito | Origem | Parte da primeira ideia? |
| --- | --- | --- | --- |
| A · Mesa de comando | Escreva a tarefa e confira projeto, agente e modo no mesmo painel. | Console atual, tipografia condensada e sinalização em âmbar. | Sim |
| B · Campo de trabalho | Comece pela pergunta, com as configurações junto do objetivo e navegação à direita no desktop. | Hierarquia da Figma e uso de uma área dominante na Pentagram. | Não |
| C · Central de sessões | Veja as sessões recentes no topo e crie uma tarefa no formulário abaixo. | Rotina de alternar entre execuções e revisar estados. | Não |

## Escopo

Hipótese de uso para aprovação: operadora ou operador técnico que precisa cadastrar tarefas e retomar sessões com frequência. A tela escolhida é a entrada `/`, hoje chamada Novo chat. A ação **Criar tarefa** representa registrar o objetivo e abrir a execução criada, coerente com o envio atual de `execute: false`. Os exemplos de projeto e sessão são fictícios. A interface das três propostas é estática, com edição local de campos e menu móvel nativo. Ajuste de largura da sidebar e navegação entre telas pertencem à implementação após a escolha.

## Verificação

O comparador passou nos três pares. O verificador do kit registrou zero falhas e avisos nas três direções, em 1440, 768, 375 e 320 px, e o axe-core registrou zero violações nas execuções. No Chrome, o menu móvel abriu com Enter e fechou com Espaço, o objetivo aceitou digitação e o modo pôde ser alterado. A criação e a abertura de sessões dependem da futura integração. Ficam pendentes o teste com leitor de tela real e a validação com usuários.

Dois avaliadores independentes escolheram a Mesa de comando por margem leve. As observações sobre cada opção estão em [notas.json](notas.json). A direção depende da decisão do responsável pelo produto.
