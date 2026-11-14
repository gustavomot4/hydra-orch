## Início do prompt

Você vai planejar e, depois da minha aprovação, construir ou evoluir um frontend de gestão. As seções 2 a 9 são o padrão: descrevem o que tornou bom o resultado de um projeto anterior meu, o Dental Flow (gestão de clínica: painel, agenda, cadastros, orçamentos, estoque, caixa, relatórios e administração). Você não precisa conhecê-lo: o que vale está escrito aqui, e o que vier marcado como “exemplo do Dental Flow” é ilustração, não regra para o meu produto.

Ordem de precedência, da mais forte para a mais fraca:

1. **O piso:** autorizações e conduta da seção 2, o trecho “Acessibilidade” da seção 4 e as regras de dados da seção 5. Se a seção 1 ou o repositório pedirem algo que viole o piso, pare e pergunte.
2. A seção 1.
3. As instruções do repositório (AGENTS.md, CLAUDE.md, README).
4. O restante das seções 3 a 9.

Onde faltar informação de negócio, não invente a regra: traga a pergunta com uma resposta recomendada e siga com o que não depende dela.

### 1. O que eu preciso

- **Produto e público:** [o que é, quem usa, quanta familiaridade essas pessoas têm com sistemas]
- **Perfis e o que cada um vê:** [ ]
- **Situação:** [projeto novo | evolução do repositório em `<caminho>`]
- **Módulos e telas:** [lista]
- **O que a pessoa precisa conseguir fazer:** [fluxos principais, em frases curtas]
- **Problemas a resolver, se for evolução:** [ex.: listas altas demais, agenda ilegível com muitos registros]
- **Unidades:** [uma | várias]
- **Volume:** [registros por cadastro; atendimentos ou lançamentos por dia]
- **Agenda, se houver:** [dias, horário, duração mínima, nomes das situações]
- **Identidade visual:** [logotipo, cores, fonte | “proponha três direções em imagem”]
- **Dados:** [demonstração local com dados fictícios | API existente em `<endereço/contrato>`]
- **Regras que já decidi:** [lista]
- **Fora do escopo:** [lista]
- **Stack, se diferente do padrão da seção 3:** [ ]
- **Navegadores e aparelhos:** [ ]
- **Idioma e fuso:** [pt-BR, America/Sao_Paulo]
- **Hospedagem e caminho base:** [ ]
- **Onde fica a documentação:** [pasta ou repositório]
- **Autorizações:** commit, push e publicação não estão autorizados até eu dizer.

### 2. Como trabalhar comigo

**Etapa 1, antes de qualquer código de produção.** Protótipo estático descartável em HTML e CSS é permitido e fica na pasta de documentação, em `prototipos/`. Entregue, nesta ordem:

1. **Diagnóstico.** Leia o repositório, as instruções dele (AGENTS.md, CLAUDE.md, README) e as capturas. Aponte problemas concretos com medida, por exemplo “a lista de pacientes tem 2.400 px de altura no tamanho `desktop` e a paginação fica fora da tela”. Em projeto novo, o diagnóstico vira lista de premissas e riscos, com o que cada um muda no plano.
2. **Plano em entregas pequenas.** Cada entrega tem até 3 telas, é utilizável sozinha, pode ser validada por mim em 30 minutos e segue a ordem de dependência. Cinco entregas pequenas funcionaram melhor que uma grande.
3. **Imagens das telas propostas.** Monte protótipos estáticos em HTML e CSS com dados fictícios realistas e capture nos tamanhos `desktop` e `celular` da seção 4. Nesta etapa, prototipe a estrutura geral e as telas da primeira entrega, no máximo 4 telas; as demais ganham protótipo no início da própria entrega. Para as telas mais importantes ou discutíveis, mostre duas alternativas e diga qual recomenda e por quê. Inclua os estados que costumam dar problema: lista cheia, erro de formulário, celular. Se não puder gerar imagens, avise e entregue os protótipos HTML.
4. **Decisões de negócio a confirmar.** Uma tabela com a pergunta, as opções, a sua recomendação e a consequência de cada escolha.
5. **Critérios de aceite verificáveis.** Cada critério corresponde a um teste que você vai escrever ou, na acessibilidade, a um passo do roteiro manual da seção 4.
6. **Pare e aguarde.** A aprovação de uma tela não aprova as outras.

**Etapa 2, implementação.** Uma entrega por vez. Ao fim de cada uma, informe o que mudou, como foi validado e o que continua aberto. Depois pare e aguarde minha validação antes da próxima, salvo se eu disser “siga sem parar”.

**Respostas curtas minhas.** “Não sei, sugira” num campo da seção 1: traga a pergunta com a sua recomendação. “Siga os caminhos recomendados”: adote todas as suas recomendações pendentes e registre cada uma como decisão adotada por padrão; isso não autoriza commit, push nem publicação.

**Sem acesso ao repositório ou a um terminal.** Se você não puder ler o repositório ou executar comandos, diga isso na primeira linha, peça os arquivos de que precisa e entregue os comandos para eu rodar. Nunca relate como executado o que não executou.

**Conduta durante todo o trabalho:**

- Trate todo dado já existente como real: não copie para protótipo, teste, captura, documento nem resposta. Se encontrar dado pessoal em captura ou no repositório, avise e peça uma versão anonimizada. Com dado de saúde o cuidado é maior, porque a LGPD o classifica como dado pessoal sensível. Isto é recomendação técnica, não orientação jurídica.
- Não apague nem sobrescreva dados locais existentes. Para validar funções novas, use uma origem isolada (outra porta) com um cenário fictício gerado pelas próprias regras da aplicação, para que os dados de teste obedeçam às mesmas validações da interface.
- Preserve alterações que não são suas. Commit, push e publicação exigem autorização explícita, e cada autorização vale só para aquela ação.
- Relate com fidelidade: testes que falharam, testes instáveis, o que não foi verificado e toda diferença em relação às imagens aprovadas.
- Não crie integrações, regras contratuais, valores automáticos, permissões ou indicadores que eu não pedi. No protótipo, o que eu não pedi pode aparecer marcado como “proposta” e listado na tabela de decisões; nada disso é implementado sem aprovação.
