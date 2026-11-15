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
          onChange={() => onChange('single', false)}
        />
        Um agente acompanha o pedido
      </label>
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          type="radio"
          name={group}
          className="h-6 w-6"
          checked={mode === 'swarm'}
          onChange={() => onChange('swarm', automatic)}
        />
        Coordenar tarefas com agentes
      </label>
      {mode === 'swarm' && (
        <>
          <p>
            O coordenador lê o projeto, cria até quatro tarefas e executa até duas em paralelo.
            Verificações e revisão de agente precedem a consolidação na cópia da conversa. Para
            executar, permita edições em um projeto Git.
          </p>
          <label className="flex min-h-11 cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              className="h-6 w-6 shrink-0"
              checked={automatic}
              onChange={(e) => onChange(mode, e.target.checked)}
            />
            Escolher entre combos OmniRoute já testados para cada tarefa
          </label>
          {automatic && (
            <p>
              A escolha considera o nome do combo e a latência observada no teste. Ela mantém o
              agente e a conexão escolhidos; ainda não compara qualidade por tarefa.
            </p>
          )}
        </>
      )}
    </fieldset>
  );
}
