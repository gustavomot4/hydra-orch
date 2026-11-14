### 3. Stack e arquitetura

Padrão para projeto novo: React, Vite, JavaScript/JSX e CSS Modules, com rotas em hash para funcionar em hospedagem estática e ao recarregar uma rota direta. Sem biblioteca visual pronta. Fonte servida localmente, em WOFF2 (família e pesos na seção 4). Node 22 ou mais novo. Não acrescente dependências sem necessidade. Se o projeto já usa TypeScript, mantenha; lint não substitui checagem de tipos.

Em evolução, a stack, a organização de pastas e a biblioteca visual do repositório prevalecem sobre esta seção. MVVM vale para módulos novos. Migração é decisão a confirmar, nunca pressuposto.

Organização MVVM por módulo, em `src/feature/<modulo>/{model,repository,view_model,view}`:

| Camada | Responsabilidade | Não pode |
| --- | --- | --- |
| View (`.jsx`) | Marcação, semântica, CSS, foco | Conter regra, acessar dados ou armazenamento |
| ViewModel (hook) | Rascunho do formulário, filtros, estado de envio, comandos, parâmetros da rota | Tocar em DOM, CSS ou armazenamento |
| Model | Funções puras: validação, regras, projeções, agregações | Importar React, DOM ou persistência |
| Repository | Executar o Model dentro de uma transação da sessão de dados | Importar React ou Views |

- A sessão de dados mantém um snapshot compartilhado, aceita uma gravação por vez, grava registro, histórico e auditoria juntos e só publica o novo estado depois de persistir.
- Na demonstração local, o armazenamento é o `localStorage`, em uma chave `<produto>:dados` com campo `versao` (em evolução, mantenha a chave que já existe). Antes de gravar, a sessão relê a chave; se outra aba gravou (evento `storage`), recarrega o snapshot e pede para repetir a ação.
- Com API existente, o Repository chama a API e não há snapshot local. Idempotência, conflito de versão, histórico e auditoria passam a ser do servidor: use o que o contrato oferece e leve à tabela de decisões o que ele não cobre.
- Configure o ESLint para impor essas fronteiras com `no-restricted-imports` e `no-restricted-globals` por pasta. Sem isso a separação se desfaz em poucas semanas.
- Uma regra usada por mais de um módulo fica em um único arquivo de funções puras. Nunca copie a regra.
- Cálculos de tela (posição em calendário, totais, agrupamentos) são funções puras testáveis sem navegador; a View só converte o resultado em posição, texto e cor.
- Componentes compartilhados desde o início: campo com rótulo e erro, botão, cabeçalho de página, estados de carregamento, vazio e erro, lista paginada, seletor com busca, abas e etiqueta de situação. Todos os tokens da seção 4 em um único arquivo.
