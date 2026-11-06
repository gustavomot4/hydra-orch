# Documentação Técnica do hydra-orch

Esta pasta reúne a documentação canônica do projeto **hydra-orch**, estruturada rigorosamente conforme as diretrizes de taxonomia oficial da equipe (`doc/b_spc/taxonomia_file_system.md`), ordenação sequencial por prefixos cognitivos (`a_...`, `b_...`) e regra da singularidade absoluta.

## Fluxo Sequencial de Leitura e Ciclo de Vida da Engenharia

A organização segue ordem alfabética sequencial correspondente à progressão de leitura humana e consumo por agentes LLM:

| Prefixo | Diretório | Domínio Documental | Finalidade Principal |
|---|---|---|---|
| `a_` | [`a_context/`](a_context/) | Contexto & Planejamento | Investigação de referência do Alethe, diagnóstico do checkout e plano mestre de desenvolvimento |
| `b_` | [`b_spc/`](b_spc/) | Especificações & PRDs | PRD funcional, PRD técnico, PRD unificado, contratos de execução, arquitetura e taxonomia |
| `c_` | [`c_activity/`](c_activity/) | Atividades & Processos | Diagramas de fluxo de atividades, pipelines e interações de agentes |
| `d_` | [`d_mer/`](d_mer/) | Dados & MER | Modelo Entidade-Relacionamento e esquemas relacionais de persistência em SQLite |
| `e_` | [`e_class/`](e_class/) | Classes & Tipagem | Diagramas de classes, modelagem de objetos e interfaces de provedores/executores |
| `f_` | [`f_api/`](f_api/) | Interfaces & OpenAPI | Especificações de rotas HTTP, payloads REST e documentação OpenAPI/Swagger |
| `g_` | [`g_code/`](g_code/) | Código & Arquitetura | Especificações de decomposição de pacotes, módulos internos e engines |
| `h_` | [`h_test/`](h_test/) | Testes & Qualidade | Matrizes de rastreabilidade de requisitos (RF/RT), planos de testes herméticos e gates |
| `i_` | [`i_infra/`](i_infra/) | Infraestrutura & Deploy | Configurações de contêineres, túneis SSH, gateways de inferência e provisionamento |
| `j_` | [`j_manual/`](j_manual/) | Manuais & Operação | Runbooks operacionais, manuais de usuário, guias de configuração e procedimentos de descarte |

Consulte [`b_spc/taxonomia_file_system.md`](b_spc/taxonomia_file_system.md) para a norma formal de nomenclatura e organização.
Para iniciar o desenvolvimento orientado a tarefas, consulte [`a_context/plano_desenvolvimento.md`](a_context/plano_desenvolvimento.md).
