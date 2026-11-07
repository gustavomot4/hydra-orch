# Padrões dos Repositórios

> **Identificador Formal:** `padrao_repositorio.md`  
> **Caminho Canônico:** `ws/a_input/a_standard_requirement/padrao_repositorio.md`  
> **Origem / Proveniência:** Anexo `PADROES_REPOSITORIOS.md` recebido externamente via email em 06/11/2026.  
> **Status:** `NORMATIVO EXTERNO / REFERÊNCIA DE PADRÃO`

---

## 1. Classificação dos Componentes (Tipos de Unidade)

| Sigla | Nome | Descrição |
|---|---|---|
| AG | Agente de Desenvolvimento Assistido por IA | Ferramentas, agentes, skills e orquestração |
| AP | Aplicativo | Aplicação principal (ex: ConectaRocinha) |
| MS | Microserviço Oficial | Serviço com dono responsável, Docker próprio, frontend + backend dedicados, schema próprio no banco do AP |
| TP | Microserviço Temporário | Desenvolvido pelo dono do AP, ainda não é o MS oficial, Docker próprio, frontend + backend dedicados, schema próprio |
| MD | Módulo Interno | Pertence ao AP, não tem Docker independente, roda no Docker do AP, tem frontend + backend dedicados, schema próprio |
| MK | Mock | Mock de serviço externo (ex: NuBank, AbacatePay, SMTP) |

---

## 2. Nomenclatura de Pastas Raiz (Estrutura do Repositório)

- `ag_<nome>` → Agentes (ex: `ag_agent_dsv`, `ag_ap_conecta_rocinha`)
- `ap_<nome>` → Aplicativos (ex: `ap_conecta_rocinha`)
- `ms_<nome>` → Microserviços Oficiais (ex: `ms_access`)
- `tp_<nome>` → Microserviços Temporários (ex: `tp_cnr_access`, `tp_epayment`)
- `md_<nome>` → Módulos (ex: `md_admin`)
- `mk_<nome>` → Mocks (ex: `mk_smtp`)

---

## 3. Estrutura Interna Padrão de Cada Unidade

Todas as unidades (AP, MS, TP, MD) seguem a mesma estrutura básica:

```
<tipo>_<nome>/
├── a_backend/
│   ├── a_code/
│   │   ├── src/              # Código fonte
│   │   ├── script/
│   │   │   ├── compile.sh    # Script de compilação
│   │   │   └── test.sh       # Script de testes
│   │   └── Cargo.toml        # Para projetos Rust
│   └── t_test_unit_a_tokio/  # Testes unitários Rust (Tokio)
├── b_middleware/             # Middleware (quando aplicável)
├── c_frontend/
│   ├── a_code/
│   │   ├── src/
│   │   └── componentes/
│   └── t_test_unit_a_cypress/ # Testes unitários Frontend (Cypress)
├── d_test/                   # Testes (ver seção 5)
├── e_doc/                    # Documentação (ver seção 6)
├── f_infra/
│   ├── a_docker/             # Dockerfiles, docker-compose
│   └── b_terraform/          # Terraform (quando aplicável)
├── g_video/                  # Evidências em vídeo
├── ws_input/                 # Entradas de workspace
│   ├── a_standard_requirement/
│   ├── b_project_requirement/
│   └── c_agent_requirement/
│       └── a_skill/
├── z_mis/                    # Miscelânea / histórico
└── m_migrate/                # Migrações de banco (ver seção 8)
```

**Notas:**
- `target` (Rust) é saída gerada e deve ser ignorada (não versionar).
- Para MD (módulos): não existe `f_infra/a_docker` próprio — roda no Docker do AP.
- Para MK (mocks): estrutura simplificada, sem `b_middleware`, `m_migrate`.

---

## 4. Workspace Operacional (Raiz do Repositório)

```
ws/
├── a_input/                  # Entradas
│   ├── a_standard_requirement/   # Padrões normativos recebidos externamente
│   ├── b_project_requirement/    # Requisitos do cliente/projeto
│   ├── c_brand/                  # Identidade visual
│   ├── d_profissao/              # Domínio de profissões
│   └── e_provenance/             # Rastreabilidade/procedência
└── b_output/                 # Saídas (planos, relatórios, entregas)
    ├── <timestamp>_<nome>.md   # Planos de execução versionados
    ├── relatorios/
    └── conecta_rocinha.doc/    # Entregas empacotadas (ZIP + checksum)
```

---

## 5. Estrutura de Testes (d_test/)

```
d_test/
├── a_unit/           # Testes unitários (função/método isolado)
├── b_coverage/       # Cobertura de código (não substitui testes)
├── c_system/         # Testes de sistema (interação entre componentes)
│   ├── a_common/
│   │   ├── a_data_dictionary/
│   │   └── b_data_mass/
│   ├── b_test_case/
│   ├── c_test_scenario/
│   └── d_test_script/
├── d_load/           # Testes de carga (pico esperado dentro de SLA)
├── e_integration/    # Testes de integração E2E (perspectiva do usuário)
├── f_stress/         # Testes de estresse (sobrecarga, ponto de falha)
├── g_capacity/       # Testes de capacidade (limite antes de violar SLA)
├── h_performance/    # Performance (latência, recursos baseline→pico)
├── i_security/       # Segurança (critérios dependem do contrato)
└── r_report/         # Relatório consolidado (report.md geral + por tipo)
```

**Estados válidos de relatório:** `NOT_RUN`, `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `SKIPPED`  
**Campos obrigatórios do report.md:** Escopo, Comando, Resultado, Limite

---

## 6. Organização da Documentação (e_doc/)

```
e_doc/
├── a_Context/        # Contexto do produto, arquitetura geral, orientações
├── b_SPC/            # Especificações definitivas (PRD Markdown)
│   ├── <unidade>_SPC_functional.md
│   └── <unidade>_SPC_technical.md
├── c_ActivityD/      # Diagramas de atividades (Mermaid)
├── d_MER/            # Modelagem Entidade-Relacionamento
├── e_Class/          # Modelagem de classes
├── f_Swagger/        # Contratos HTTP (Swagger/OpenAPI) + AsyncAPI
├── g_Code/           # Documentação permanente de código
├── h_Test/           # Documentação permanente de testes
├── i_Infra/          # Documentação permanente de infraestrutura
└── j_Manual/         # Manuais operacionais
```

**Nomes de arquivo (padrão):**
- `<TIPO>_<NomeArtefato>_PRD.md`
- `<TIPO>_<Nome>_Swagger.yml`

**Glossário:** Todo PRD deve ter seção "Glossary e Acrônimos" — tabela única, mista (termos + siglas), ordenada alfabeticamente.  
**Requisitos DBC-9:** Purpose, Why, Contract, Preconditions, Postconditions, Invariants, Failure Modes, How, Examples.

---

## 7. Convenções de Banco de Dados

### Nomes

| Objeto | Padrão |
|---|---|
| Database | `DB_<APP>` (ex: `DB_CNR`) |
| Schema | `<APP>_SC_<COMPONENTE>_<ShortDs>` (ex: `CNR_SC_CNR_Candidato`) |
| Tabela | `<APP>_<COMPONENTE>_TB_<ShortDs>` (ex: `CNR_CNR_TB_Candidato`) |
| Sequence | `<APP>_<COMPONENTE>_SQ_<ShortDs>` |
| Queue | `<APP>_<COMPONENTE>_QU_<ShortDs>` |
| Queue Temporária | `TMP_<COMPONENTE>_QU_<ShortDs>` |

### Categorias de Objeto

- `TB` — Tabela
- `SP` — Stored Procedure
- `FC` — Função
- `SQ` — Sequence
- `IX` — Índice
- `VW` — View
- `QU` — Fila

### Colunas (Notação MER)

`TTTT t_xxxx_yy [ZZ] "99z"`

- **TTTT:** Tipo PostgreSQL
- **t:** `i`=integer, `f`=float, `c`=char, `s`=string, `b`=boolean, `dt`=date, `ts`=timestamp, `o`=object
- **yy:** Significado
  - `id`: identification
  - `nm`: name
  - `cd`: code
  - `gl`: flag
  - `nr`: number
  - `ds`: description
  - `ac`: acronym
  - `tp`: type

---

## 8. Migrações (m_migrate/)

```
m_migrate/
├── v00_01_0000_04oct2026_2004/     # Pacote de migração
│   ├── sql/
│   │   └── main.sql
│   ├── migrate_do.sh
│   ├── migrate_undo.sh
│   └── README.md                   # Com seção "Modificações" preenchida
├── v00_01_0000_04oct2026_2004_complemento.md
└── README.md                       # Índice geral
```

**Padrão do pacote:** `v<release>_<seq>_<timestamp>`
- Release: 2 dígitos (ex: 00, 01, 02)
- Seq: 2 dígitos
- Número: 4 dígitos
- Timestamp: `ddmmmyyyy_hhmm` (UTC, meses em inglês: jan, feb, mar...)
- Arquivos obrigatórios: `main.sql`, `migrate_do.sh`, `migrate_undo.sh`, `README.md`

---

## 9. Códigos de Resultado (Result Codes)

Máscara: `XXX_YYYZZZ_99999`

| Segmento | Significado |
|---|---|
| `XXX` | Sigla de 3 chars do AP/componente |
| `YYY` | `SUC` (sucesso), `ERR` (erro), `DBG` (debug), `WRN` (aviso), `INF` (info) |
| `ZZZ` | `ALL` (comum), `TCN` (técnico), `FNC` (funcional) |
| `99999` | 5 dígitos (00000–99999) |

*Exemplo:* `CNR_SUCALL_00001`

---

## 10. Nomenclatura de Serviços (Docker/Cloud)

Máscara: `{projeto}-{runtime}-{layer}-{tipo}-{owner}-{serviço}`

| Campo | Valores |
|---|---|
| runtime | `svc`, `job` |
| layer | `fnt` (frontend), `bck` (backend), `mid` (middleware) |
| tipo | `gtw` (gateway), `dbs` (database), `brk` (broker), `web`, `api` |
| owner | `3rd` (terceiros), `int` (próprio/interno) |

---

## 11. Versionamento Git

| Ambiente | Branch |
|---|---|
| Development | `a_dsv_merge___` |
| Test | `b_tst_merge___` |
| UAT | `c_uat_flavio_ss` |
| Production | `d_prd_flavio_ss` |

**Regras:**
- PR do filho antes do PR do pai
- Pai aponta para commit publicado
- Branch própria obrigatória para contribuição
- Publicação requer autorização da sessão
- Commit guidance: resumo, Done, Doing, ToDo

---

## 12. Releases

Padrão: `vXX_YY_ZZZZ` (pontos permitidos conforme projeto)
- `XX` — rearquitetura
- `YY` — enhancement/change
- `ZZZZ` — bugfix

---

## 13. Estrutura de Agentes (ag/)

```
ag/
├── ag_agent_dsv/               # Agente agnóstico (autoridade compartilhada)
│   ├── ag_agent_dsv/
│   │   ├── a_common/           # Núcleo compartilhado
│   │   │   ├── a_agent/        # Identidade, fronteiras
│   │   │   ├── b_skill/        # Skills (a_core, b_project)
│   │   │   ├── c_script/       # Validação, comandos
│   │   │   ├── d_brain/        # Decisões, catálogos, grafos
│   │   │   ├── e_context/      # Índice de procedência
│   │   │   ├── f_tool/         # Ferramentas
│   │   │   ├── g_orchestration/# Orquestração
│   │   │   ├── h_validation/   # Critérios de prova
│   │   │   ├── i_observe/      # Observabilidade
│   │   │   ├── j_infra/        # Infraestrutura do agente
│   │   │   └── z_mis/          # Miscelânea
│   │   ├── b_app_brandnew/     # Reserva estrutural
│   │   ├── c_app_modern/       # Reserva estrutural
│   │   └── d_app_analytic/     # Reserva estrutural
│   └── ws/                     # Workspace do agente
├── ag_ap_<nome>/               # Agente específico do AP
│   ├── ag_ap_<nome>/
│   │   └── a_common/           # Contexto e procedimentos locais
│   └── ws/                     # Planos de execução versionados aqui
└── ag_<tipo>_<nome>/           # Agentes de MS/TP/MD (se necessário)
```

---

## 14. Regras de Nomenclatura (Singular Obrigatório)

**Regra:** Nenhuma pasta nem artefato controlado pela equipe pode ter nome no plural.

**Exceções técnicas (ferramentas):**
- `.github/workflows`
- `.github/skills`
- `.github/prompts`
- `AGENTS.md`
- `requirements.txt`
- `copilot-instructions.md`
- `.obsidian/core-plugins.json`

**Siglas preservadas:** MS, TS, DevOps, DevSecOps, Postgres, PostgreSQL, Kubernetes

---

## 15. Convenções Rust

| Item | Padrão |
|---|---|
| Diretório de scripts | `script/` |
| Script de compilação | `compile.sh` |
| Script de testes | `test.sh` |
| Diretório target | `t_target/` (ignorado) |
| Warnings bloqueiam deploy | Sim |
| LLVM | Não permitido (GAP-010) |

---

## 16. JSON de Negócio (Payload)

Padrão de campo: `^[sifbdxuo][A-Z][A-Za-z0-9]*$`
- Prefixo minúsculo do tipo + PascalCase
- `s`=string, `i`=integer, `f`=float, `b`=boolean, `d`=date, `x`=object, `u`=uuid, `o`=outro
- Arrays usam prefixo `o` (não primitivo)
- Arquivos de ferramentas preservam seus contratos: `package.json`, `tsconfig.json`, `.eslintrc.json`, etc.

---

## 17. Diagramas de Classes

- Todos os identificadores são privados (prefixo `-`).
- Notação Mermaid.

---

## 18. Exemplos de API

```
e_doc/a_spc/example/
├── <operationId>_request.json
└── <operationId>_response.json
```
- Um arquivo por operação e direção.
- `snake_case` do `operationId` no nome do arquivo.

---

## 19. Vídeos (Evidências e Demos)

| Tipo | Máscara | Diretório |
|---|---|---|
| Evidência | `ap_<APP>_d_system_video_<CASO_CENARIO>.mp4` | `d_test/c_system/d_test_script/` |
| Demo | `ap_<APP>_v_video_<RELEASE>_<STAMP>.mp4` | `g_video/` |
| Prompt evidência | `ap_<APP>_d_system_video_<CASO_CENARIO>_prompt.md` | Mesmo da evidência |
| Prompt demo | `ap_<APP>_v_video_<RELEASE>_<STAMP>_prompt.md` | `g_video/` |

- Prompts de construção devem ser versionados.
- `.gitignore`: `ap_???_*.mp4`

---

## 20. Unidades do ConectaRocinha (Exemplo de Aplicação)

| Unidade | Tipo | Caminho | Status |
|---|---|---|---|
| ConectaRocinha | AP | `ap/ap_conecta_rocinha` | Implementado |
| WWW | Frontend do AP | `ms/ap_cnr_www` | Implementado |
| Access Externo | MS (gitlink) | `ms/ms_access` | Externo protegido |
| Access Local | TP | `tp/tp_access` | Implementado |
| CNR Access | TP | `tp/tp_cnr_access` | Implementado |
| EPayment | TP | `tp/tp_epayment` | Implementado |
| Observe | TP | `tp/tp_observe` | Implementado |
| WAP | TP | `tp/tp_wap` | Implementado |
| Entity | TP | `tp/tp_entity` | Reserva (sem impl.) |
| Notify | TP | `tp/tp_notify` | Reserva (sem impl.) |
| SMTP Mock | MK | `mk/mk_smtp` | Implementado |

---

## 21. Decisões Pendentes (GAPs)

| GAP | Descrição |
|---|---|
| GAP-001 a GAP-012 | Diversos (compilador Rust, arranjo Access/Keycloak, archive frio, etc.) |
| PLN-D01, PLN-D05 | Planejamento documental pendente |
| GAP-007, GAP-008 | Gaps de escopo/nome |

---

## 22. Resumo Visual da Árvore Completa

```
raiz/
├── ag/
│   ├── ag_agent_dsv/
│   └── ag_ap_conecta_rocinha/
├── ap/
│   └── ap_conecta_rocinha/
├── ms/
│   ├── ms_access/              (gitlink externo)
│   └── ap_cnr_www/
├── tp/
│   ├── tp_access/
│   ├── tp_cnr_access/
│   ├── tp_epayment/
│   ├── tp_observe/
│   ├── tp_wap/
│   ├── tp_entity/
│   └── tp_notify/
├── mk/
│   └── mk_smtp/
├── md/
│   └── (módulos futuros: md_admin, etc.)
├── ws/
│   ├── a_input/
│   └── b_output/
├── z_history/                  (histórico preservado)
├── README.md
├── AGENTS.md
├── CHANGELOG.md
└── LICENSE
```

---

## 23. Referências Rápidas

| Documento | Localização |
|---|---|
| Padrões completos (standard.json) | `ag/ag_agent_dsv/ag_agent_dsv/a_common/d_brain/b_graph/catalog/standard.json` |
| Regras (rule.json) | `ag/ag_agent_dsv/ag_agent_dsv/a_common/d_brain/b_graph/catalog/rule.json` |
| Catálogo de unidades | `ag/ag_ap_conecta_rocinha/ag_ap_conecta_rocinha/a_common/d_brain/b_graph/catalog/unit.json` |
| Regras locais | `ag/ag_ap_conecta_rocinha/ag_ap_conecta_rocinha/a_common/d_brain/b_graph/catalog/local_rule.json` |
| PRD Funcional AP | `ap/ap_conecta_rocinha/e_doc/b_SPC/ap_conecta_rocinha_SPC_functional.md` |
| PRD Técnico AP | `ap/ap_conecta_rocinha/e_doc/b_SPC/ap_conecta_rocinha_SPC_technical.md` |

> **Nota final:** As regras são evolutivas; consulte os arquivos JSON de catálogo para a versão mais recente.
