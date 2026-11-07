# Sistema de Design e Direções Visuais: Hydra (hydra-orch)

**Identificador Formal:** `design_system.md`  
**Caminho Canônico:** `doc/b_spc/design_system.md`  
**Versão:** `v01_00_0000`  
**Status:** `PROPOSTO / AGUARDANDO ESCOLHA DA DIREÇÃO`  
**Autoridade:** Especificação de identidade visual e tokens para o Control Plane e UI do Hydra.  
**Conformidade:** WCAG 2.2 Nível AA (todos os pares de contraste testados via OKLCH).

---

## 1. Princípio Fundamental de Design

> **Convenção na interação, identidade na expressão.**  
> Como navegar, preencher, filtrar diffs e confirmar execuções segue o que qualquer desenvolvedor sênior já domina. Tipografia, paleta de cores, geometria, iconografia e voz são a assinatura exclusiva do Hydra.

---

## 2. As Três Direções Visuais Comparadas

| Dimensão | Direção A: "Steel Slate Precision" (Familiar) | Direção B: "Bioluminescent Abyssal Hydra" (Própria) | Direção C: "Monolith Titanium & Amber" (Inesperada) |
|---|---|---|---|
| **Conceito Chave** | *Telemetria Cirúrgica e Cockpit Aeroespacial.* | *O Mito da Hidra: Regeneração Bioelétrica Abissal.* | *Instrumentação Monolítica de Hardware de Alta Precisão.* |
| **Arquétipo** | Console de missão crítica e alta confiabilidade (tipo Linear / Apple Pro). | Organismo cibernético resiliente de águas profundas. | Módulo de rack analógico industrial de instrumentação pesada. |
| **Cor Primária (Hex)** | `#184e77` (Azul Aço Marítimo Profundo) | `#0e5f4b` (Verde Esmeralda Abissal / Hydra Teal) | `#854d0e` (Âmbar Técnico Industrial) |
| **Fundo da Interface** | `#f4f7fb` (Ardósia suave) | `#f3f8f6` (Menta-oceano neutro) | `#faf6f3` (Titânio aquecido / Papel técnico) |
| **Texto Principal** | `#131c23` (Contraste 17.2:1) | `#111e19` (Contraste 17.1:1) | `#211911` (Contraste 17.3:1) |
| **Tipografia Título** | **Instrument Sans** (Display 600/700) | **Hanken Grotesk** (Geométrica 700/800) | **Barlow Condensed / Archivo** (Display 800/900) |
| **Tipografia Corpo** | **Instrument Sans** (Regular 400/500) | **Instrument Sans** (Regular 400/500) | **Public Sans / Schibsted** (Regular 400) |
| **Tipografia Código/Dados** | **JetBrains Mono** (Tabular-nums) | **JetBrains Mono** (Tabular-nums) | **JetBrains Mono** (Tabular-nums) |
| **Raios e Geometria** | `rounded: 6px` (controles) / `8px` (cards) | `rounded: 8px` (controles) / `12px` (cards) | `rounded: 2px` a `4px` (industrial reto) |
| **Elevação e Camadas** | Linha fina `#d8dfe6` + sombra suave `1px` | Separação tonal e contorno `#d7e1dd` | Borda técnica demarcada `1.5px solid #e4dcd6`, 0 sombras |
| **Elemento-Assinatura** | *DAG Stream Pipeline Bar:* telemetria de voo. | *Trifurcated Node Badges:* nós de 3 pontas da Hidra. | *Rack Hardware Status Switcher:* chave seletora com código 3 dígitos. |

---

## 3. Especificação Completa dos Tokens de Cores (OKLCH + WCAG 2.2 AA)

Todas as cores foram geradas pelo algoritmo `paleta.mjs` garantindo contraste mínimo de **4.5:1** para textos normais e **3.0:1** para controles e foco:

### 3.1. Direção A: "Steel Slate Precision"
```yaml
colors:
  background: "#f4f7fb"
  surface: "#ffffff"
  on-background: "#131c23"      # 16.05:1 contra background
  on-surface: "#131c23"         # 17.24:1 contra surface
  muted: "#606a74"              # 5.51:1 contra surface
  line: "#d8dfe6"
  border-control: "#838e98"     # 3.34:1 contra surface
  primary: "#184e77"            # 8.77:1 contra texto branco
  on-primary: "#ffffff"
  primary-hover: "#013d65"      # 11.31:1 contra texto branco
  primary-text: "#184e77"       # 8.77:1 contra surface
  primary-soft: "#e2f1fe"
  on-primary-soft: "#184e77"    # 7.62:1 contra primary-soft
  focus: "#184e77"
  # Retornos Semânticos
  danger: "#a43b35"
  danger-soft: "#fee9e6"
  on-danger: "#ffffff"
  success: "#007835"
  success-soft: "#e1f5e4"
  warning: "#8a5601"
  warning-soft: "#fcecd9"
  info: "#0465af"
  info-soft: "#e3f0fe"
```

### 3.2. Direção B: "Bioluminescent Abyssal Hydra" (Recomendada)
```yaml
colors:
  background: "#f3f8f6"
  surface: "#ffffff"
  on-background: "#111e19"      # 15.99:1 contra background
  on-surface: "#111e19"         # 17.16:1 contra surface
  muted: "#5e6d67"              # 5.44:1 contra surface
  line: "#d7e1dd"
  border-control: "#81908a"     # 3.34:1 contra surface
  primary: "#0e5f4b"            # 7.62:1 contra texto branco
  on-primary: "#ffffff"
  primary-hover: "#024d3c"      # 9.86:1 contra texto branco
  primary-text: "#0e5f4b"       # 7.62:1 contra surface
  primary-soft: "#d5f8eb"
  on-primary-soft: "#0e5f4b"    # 6.69:1 contra primary-soft
  focus: "#0e5f4b"
  # Retornos Semânticos
  danger: "#a43b35"
  danger-soft: "#fee9e6"
  on-danger: "#ffffff"
  success: "#007835"            # Verde Healer verificado
  success-soft: "#e1f5e4"
  warning: "#8a5601"
  warning-soft: "#fcecd9"
  info: "#0465af"
  info-soft: "#e3f0fe"
```

### 3.3. Direção C: "Monolith Titanium & Amber"
```yaml
colors:
  background: "#faf6f3"
  surface: "#ffffff"
  on-background: "#211911"      # 16.13:1 contra background
  on-surface: "#211911"         # 17.33:1 contra surface
  muted: "#72675d"              # 5.51:1 contra surface
  line: "#e4dcd6"
  border-control: "#958a80"     # 3.37:1 contra surface
  primary: "#854d0e"            # 6.85:1 contra texto branco
  on-primary: "#ffffff"
  primary-hover: "#703e01"      # 8.83:1 contra texto branco
  primary-text: "#854d0e"       # 6.85:1 contra surface
  primary-soft: "#ffead9"
  on-primary-soft: "#854d0e"    # 5.88:1 contra primary-soft
  focus: "#854d0e"
  # Retornos Semânticos
  danger: "#a43b35"
  danger-soft: "#fee9e6"
  on-danger: "#ffffff"
  success: "#007835"
  success-soft: "#e1f5e4"
  warning: "#8a5601"
  warning-soft: "#fcecd9"
  info: "#0465af"
  info-soft: "#e3f0fe"
```

---

## 4. Estudo de Tema Escuro (Norma G21 do Kit)

Conforme a regra **G21** (`Tema escuro só com estudo, nunca invertendo cores`), as três direções contam com contrapartes escuras calculadas em OKLCH com fundo dessaturado, superfícies elevadas e cores de ação clareadas para preservar legibilidade sem ofuscar:

- **Direção A (Dark Slate):**
  - Fundo: `#0d151c` | Superfície: `#16222b` | Texto: `#e1eaef` | Primário: `#6da5cf`
- **Direção B (Abyssal Night - Recomendada):**
  - Fundo: `#0b1613` | Superfície: `#13221e` | Texto: `#e0ebe7` | Primário: `#6ec5ad`
- **Direção C (Industrial Black & Bronze):**
  - Fundo: `#161412` | Superfície: `#221f1c` | Texto: `#ece6df` | Primário: `#deb887`

---

## 5. Escala Tipográfica e Teste de Caracteres

A escala é harmônica com base `1rem = 16px`:

| Nível | Token | Tamanho / Altura | Peso | Aplicação |
|---|---|---|---|---|
| **Display Herói** | `text-4xl` | `2.25rem` (36px) / 1.15 | 700 / 800 | Nome do Hydra no cabeçalho / Métricas heróicas |
| **Título de Seção** | `text-2xl` | `1.5rem` (24px) / 1.25 | 600 / 700 | Títulos de painel (`Runs Ativos`, `DAG do Swarm`) |
| **Subtítulo / Card** | `text-lg` | `1.125rem` (18px) / 1.35 | 600 | Identificador de Worktree e Nomes de Tarefas |
| **Corpo Padrão** | `text-base` | `1.0rem` (16px) / 1.5 | 400 | Descrições de planos e notas de diff |
| **Rótulo Técnico** | `text-sm` | `0.875rem` (14px) / 1.4 | 500 / 600 | Badges, cabeçalhos de tabela, botões |
| **Código / Hash** | `text-xs-mono` | `0.8125rem` (13px) / 1.45 | 400 / 500 | Hashes SHA-256, paths de arquivos, tempos (`12ms`) |

### Teste de Acentuação e Alinhamento Numérico Obrigatório:
> *« Não há pão, ação e coração: R$ 1.234,56 às 14:30 · run #86b599e concluído em 1.42s »*
- As três fontes escolhidas possuem suporte nativo pleno a diacríticos portugueses (`ã`, `ç`, `õ`, `é`) e suporte a numerais tabulares `tabular-nums` para que colunas de dados não trepidem em atualizações em tempo real.
