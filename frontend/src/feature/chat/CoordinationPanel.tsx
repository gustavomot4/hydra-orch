import { Link } from 'react-router-dom';
import { CoordinationCheck, ConversationTurn } from './conversationTypes';
import { checkDuration, taskState } from './coordinationModel';
import './coordination.css';

export function CheckEvidence({ checks }: { checks: CoordinationCheck[] }) {
  if (!checks.length)
    return <p className="coordination-note">Nenhuma verificação concluída registrada.</p>;
  return (
    <ul className="check-evidence" aria-label="Verificações registradas">
      {checks.map((check) => (
        <li key={check.check_id}>
          <details>
            <summary>
              <span
                className={`coordination-state is-${check.exit_code === 0 ? 'success' : 'error'}`}
              >
                <span aria-hidden="true">{check.exit_code === 0 ? '✓' : '!'}</span>
                <span>
                  {check.exit_code === 0
                    ? 'Passou'
                    : check.exit_code === 124
                      ? 'Tempo esgotado'
                      : 'Falhou'}
                </span>
              </span>
              <span className="check-name">{check.check_id}</span>
              <span className="coordination-note">{checkDuration(check.duration_seconds)}</span>
            </summary>
            <div className="check-content">
              <p className="coordination-note">Código de saída: {check.exit_code}</p>
              {check.cwd && <p className="coordination-note">Pasta: {check.cwd}</p>}
              <p className="coordination-note">Comando executado</p>
              <pre>{check.command.join(' ')}</pre>
              {check.output ? (
                <pre aria-label={`Saída de ${check.check_id}`}>{check.output}</pre>
              ) : (
                <p className="coordination-note">Sem trecho de saída registrado.</p>
              )}
            </div>
          </details>
        </li>
      ))}
    </ul>
  );
}

export function CoordinationPanel({ turn }: { turn: ConversationTurn }) {
  const coordination = turn.coordination;
  if (!coordination?.plan) return null;
  const tasks = coordination.plan.tasks;
  const states = tasks.map((task) => taskState(task, coordination.tasks?.[task.id], turn.state));
  const completed = states.filter((s) => ['accepted', 'completed'].includes(s.state)).length;
  const failed = states.filter((s) => s.tone === 'error').length;
  return (
    <section className="coordination-panel" aria-label="Trabalho coordenado">
      <header>
        <h3>Tarefas deste pedido</h3>
        <p role="status">
          {completed} de {tasks.length} concluídas{failed > 0 ? ` · ${failed} com falha` : ''}
        </p>
      </header>
      <details className="coordination-details">
        <summary>Objetivo do trabalho</summary>
        <p>{coordination.plan.objective}</p>
      </details>
      <ol className="coordination-task-list">
        {tasks.map((task, i) => {
          const progress = coordination.tasks?.[task.id];
          const state = states[i];
          return (
            <li key={task.id} className="coordination-task">
              <div className="coordination-task-heading">
                <h4>{task.title}</h4>
                <span className={`coordination-state is-${state.tone}`}>
                  <span aria-hidden="true">{state.symbol}</span>
                  <span>{state.label}</span>
                </span>
              </div>
              <p className="coordination-note">
                {state.validation ? 'Verificação local · Hydra' : 'Edição por agente'}
                {progress?.route?.target_ref ? ` · ${progress.route.target_ref}` : ''}
              </p>
              {progress?.summary && state.tone === 'error' && (
                <p className="coordination-failure">{progress.summary.split('\n')[0]}</p>
              )}
              {state.validation && !progress?.checks?.length && (
                <p className="coordination-note">Aguardando resultados das verificações.</p>
              )}
              {progress?.checks && <CheckEvidence checks={progress.checks} />}
              <details className="coordination-details">
                <summary>Detalhes da tarefa</summary>
                <ul>
                  {task.paths.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
                {progress?.reason && <p>{progress.reason}</p>}
                {progress?.review && <p>Revisão: {progress.review}</p>}
                {progress?.summary && !progress.checks?.length && <pre>{progress.summary}</pre>}
              </details>
            </li>
          );
        })}
      </ol>
      {coordination.run_id && coordination.phase && (
        <Link className="coordination-link" to={`/chat/${encodeURIComponent(coordination.run_id)}`}>
          Ver execução e verificações
        </Link>
      )}
    </section>
  );
}
