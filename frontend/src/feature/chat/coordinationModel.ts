import { CoordinationProgress, CoordinationTask, ConversationTurn } from './conversationTypes';

export function taskState(
  task: CoordinationTask,
  progress: CoordinationProgress | undefined,
  turnState?: ConversationTurn['state'],
) {
  const validation = (progress?.operation ?? task.operation) === 'validate';
  let state = progress?.state ?? 'planned';
  if (['starting', 'running'].includes(state) && ['failed', 'cancelled'].includes(turnState ?? ''))
    state = 'stopped';
  if (['starting', 'running'].includes(state) && turnState === 'stopping') state = 'stopping';
  if (['starting', 'running'].includes(state) && turnState === 'completed') state = 'unknown';
  const labels: Record<string, string> = {
    planned: 'Não iniciada',
    starting: 'Iniciando',
    running: validation ? 'Verificando' : 'Trabalhando',
    accepted: validation ? 'Validada' : 'Revisão aprovada',
    completed: 'Concluída',
    failed: 'Falhou',
    rejected: 'Revisão recusada',
    ready_for_review: 'Aguardando revisão',
    reviewing: 'Em revisão',
    stopped: 'Interrompida',
    stopping: 'Interrompendo',
    unknown: 'Sem conclusão registrada',
    cancelled: 'Cancelada',
  };
  const tone = ['accepted', 'completed'].includes(state)
    ? 'success'
    : ['failed', 'rejected'].includes(state)
      ? 'error'
      : ['starting', 'running'].includes(state)
        ? 'info'
        : 'muted';
  const symbol = tone === 'success' ? '✓' : tone === 'error' ? '!' : tone === 'info' ? '▶' : '◇';
  return { state, label: labels[state] ?? 'Estado não informado', tone, symbol, validation };
}

export function checkDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return 'Duração não informada';
  return `${seconds.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`;
}
