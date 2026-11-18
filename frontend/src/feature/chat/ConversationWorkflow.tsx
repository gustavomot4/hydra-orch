import { useId } from 'react';

export type ExecutionMode = 'single' | 'swarm';

export function ConversationWorkflow({
  mode,
  automatic,
  onChange,
  disabled = false,
}: {
  mode: ExecutionMode;
  automatic: boolean;
  onChange: (mode: ExecutionMode, automatic: boolean) => void;
  disabled?: boolean;
}) {
  const group = useId();
  return (
    <fieldset disabled={disabled} className="my-3 space-y-2 text-sm text-[#D1D1D1]">
      <legend className="mb-1 font-semibold text-[#E8E8E8]">Como trabalhar</legend>
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          type="radio"
          name={group}
          className="h-6 w-6"
          checked={mode === 'single'}
          onChange={() => onChange('single', automatic)}
        />
        Um agente acompanha o pedido
      </label>
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          type="radio"
          name={group}
          className="h-6 w-6"
          checked={mode === 'swarm'}
          onChange={() => onChange('swarm', true)}
        />
        Coordenar tarefas com agentes
      </label>
      {mode === 'swarm' && <p>Até quatro tarefas, com verificações e revisão na cópia isolada.</p>}
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          className="h-6 w-6 shrink-0"
          checked={automatic}
          onChange={(event) => onChange(mode, event.target.checked)}
        />
        Escolher modelo automaticamente
      </label>
      {automatic && (
        <p>O Hydra avalia as capacidades e a cota conhecida dentro da conexão selecionada.</p>
      )}
    </fieldset>
  );
}
