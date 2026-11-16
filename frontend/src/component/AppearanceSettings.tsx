import { useLayoutStore } from '@/store/layoutStore';
import { clearPromptHistory } from '@/feature/composer/promptHistory';

export function AppearanceSettings() {
  const state = useLayoutStore();
  const numbers = [
    ['interfaceScale', 'Escala da interface (%)', 80, 120, 5],
    ['chatFontSize', 'Texto da conversa (px)', 12, 24, 1],
    ['terminalFontSize', 'Texto do terminal (px)', 10, 24, 1],
  ] as const;
  return (
    <fieldset className="appearance-settings">
      <legend>Tamanhos e painéis</legend>
      <p>As alterações são salvas neste navegador e aplicadas imediatamente.</p>
      <label>
        Densidade da interface
        <select
          value={state.density}
          onChange={(e) => state.setDensity(e.target.value as typeof state.density)}
        >
          <option value="compact">Compacta</option>
          <option value="comfortable">Confortável</option>
          <option value="spacious">Ampla</option>
        </select>
      </label>
      {numbers.map(([key, label, min, max, step]) => (
        <label key={key}>
          {label}
          <span className="appearance-number">
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              aria-label={label}
              value={state[key]}
              onChange={(e) => state.setAppearance({ [key]: Number(e.target.value) })}
            />
            <output>{state[key]}</output>
          </span>
        </label>
      ))}
      <label>
        Largura da conversa
        <select
          value={state.chatExpanded ? 'expanded' : 'focused'}
          onChange={(e) => state.setAppearance({ chatExpanded: e.target.value === 'expanded' })}
        >
          <option value="focused">Focada</option>
          <option value="expanded">Expandida</option>
        </select>
      </label>
      {(
        [
          ['sidebarCollapsed', 'Mostrar barra lateral', !state.sidebarCollapsed],
          ['inspectorVisible', 'Mostrar detalhes dos agentes', state.inspectorVisible],
          ['statusBarVisible', 'Mostrar barra de status', state.statusBarVisible],
          ['conversationsVisible', 'Mostrar conversas nos projetos', state.conversationsVisible],
          ['foldersVisible', 'Mostrar subpastas cadastradas', state.foldersVisible],
          ['promptHistoryEnabled', 'Histórico de prompts com ↑ e ↓', state.promptHistoryEnabled],
          ['suggestionsEnabled', 'Sugestões com Tab', state.suggestionsEnabled],
        ] as const
      ).map(([key, label, checked]) => (
        <label className="appearance-toggle" key={key}>
          <span>{label}</span>
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) =>
              key === 'sidebarCollapsed'
                ? state.setSidebarCollapsed(!e.target.checked)
                : state.setAppearance({ [key]: e.target.checked })
            }
          />
        </label>
      ))}
      <div className="appearance-actions">
        <button type="button" onClick={state.resetAppearance}>
          Restaurar tamanhos e painéis
        </button>
        <button
          type="button"
          onClick={() => {
            clearPromptHistory();
            window.dispatchEvent(new Event('hydra-history-cleared'));
          }}
        >
          Limpar histórico de prompts
        </button>
      </div>
    </fieldset>
  );
}
