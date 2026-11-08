# Análise de referência

## Evidência e limites

O [repositório público do Orca](https://github.com/stablyai/orca) contém áreas desktop, native e mobile e configuração Electron/Vite. Esta análise consultou sua apresentação pública e documentação de produto; não auditou sua implementação interna nem executou o aplicativo. A existência de uma função documentada no Orca não comprova suporte no Hydra. O [changelog](https://github.com/stablyai/orca/releases) é fonte de acompanhamento, não compromisso automático de paridade.

As imagens fornecidas mostram hierarquia host → projeto → workspace/branch → sessão; sidebar persistente; abas; coordenador e workers em painéis; eventos recolhíveis; compositor inferior; indicadores de consumo. A sobreposição do telefone ilustra acesso compacto, mas não demonstra um emulador embutido.

## Recursos solicitados e fontes

| Recurso | Referência consultada | Direção para Hydra |
| --- | --- | --- |
| Arquivos para agentes | [File explorer](https://www.onorca.dev/docs/editing/file-explorer) | Arrastar arquivo do explorador ou imagem externa para anexar ao prompt, com destino explícito |
| Jump Anywhere | [Quick Open](https://www.onorca.dev/docs/model/quick-open) | Busca global por host, projeto, workspace e aba; teclado e recentes |
| Rich Previews | [Viewers](https://www.onorca.dev/docs/editing/viewers) | Imagens, PDF e Markdown em painel adjacente ao agente |
| Mobile Emulator | [CLI / emulator](https://www.onorca.dev/docs/cli/overview#mobile-emulator) | Bridge de dispositivo com seleção, imagem, tap e digitação; a página detalha iOS Simulator; Android solicitado depende de validação específica |
| Dictation | [Voice](https://www.onorca.dev/docs/settings#voice) | Atalho, escolha de microfone, indicador de gravação e transcrição editável |
| Usage & Accounts | [Usage tracking](https://www.onorca.dev/docs/agents/usage-tracking) | Quotas, resets e seleção de conta quando suportada; distinguir estimativa de medição |
| Automations | [Automations](https://www.onorca.dev/docs/cli/automations) | Prompt, alvo, agenda, fuso, habilitação e histórico de execução |
| Computer Use | [Computer use](https://www.onorca.dev/docs/cli/computer-use) | Selecionar app/janela, observar, agir e verificar; capacidades e permissões por host |

## Adaptação ao projeto

Adotar a composição visual do Orca com identidade Hydra e os estados reais do control plane. A stack do Hydra já especifica React/TypeScript/Vite, Radix, Tailwind, Zustand e TanStack Query. Não substituir essa decisão por Electron apenas porque o produto de referência o utiliza. A necessidade de shell desktop ou bridge local deve ser decidida numa etapa própria, considerando PTY, arquivos, áudio e captura do SO.

Não copiar nomes de modelos, dados de consumo ou o indicador “Full access” como valores padrão. Controles refletem capacidades efetivas do executor e políticas do Hydra. Reuso futuro de código/ícones do Orca exige verificar licença e atribuição do arquivo específico; esta entrega incorpora apenas os anexos e links solicitados.
