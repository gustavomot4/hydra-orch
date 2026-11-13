import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  FolderGit2,
  RotateCcw,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { CheckBadgeItem, WorkerCardModel } from './chatTypes';

export interface WorkerCardProps {
  worker: WorkerCardModel;
  onRetryTask?: (taskId: string) => Promise<void> | void;
  isRetrying?: boolean;
}

function formatTraceTime(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(parsed);
}

function renderCheckPill(chk: CheckBadgeItem) {
  const statusKind =
    chk.status === 'passed'
      ? 'succeeded'
      : chk.status === 'failed'
        ? 'failed'
        : chk.status === 'pending'
          ? 'waiting'
          : 'unknown';
  const label =
    chk.status === 'passed'
      ? `${chk.checkId}: Aprovado`
      : chk.status === 'failed'
        ? `${chk.checkId}: Falhou`
        : chk.status === 'pending'
          ? `${chk.checkId}: Pendente`
          : `${chk.checkId}: Desconhecido`;

  return (
    <span
      key={`${chk.taskId ?? 'run'}-${chk.checkId}`}
      data-testid={`worker-check-${chk.taskId ?? 'run'}-${chk.checkId}`}
      data-check-status={chk.status}
    >
      <StatusBadge status={statusKind} labelOverride={label} compact />
    </span>
  );
}

export function WorkerCard({ worker, onRetryTask, isRetrying = false }: WorkerCardProps) {
  const [traceExpanded, setTraceExpanded] = useState(false);

  const durationBadgeText =
    worker.durationSeconds !== null
      ? `Worked for ${worker.durationSeconds}s`
      : worker.status === 'running'
        ? 'Em execução'
        : 'Duração: —';

  const modeLabel =
    worker.mode === 'swarm' ? 'Swarm' : worker.mode === 'relay' ? 'Relay' : 'Persistente';

  return (
    <article
      data-testid={`worker-card-${worker.taskId}`}
      data-worker-wave={worker.wave}
      className="rounded-xl border border-[#303030] bg-[#202020] p-3.5 text-left"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-xs font-semibold text-[#E8E8E8]">
              {worker.taskId}
            </span>
            <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] text-[#969696]">
              Wave {worker.wave} · {modeLabel}
            </span>
            {worker.attemptOrdinal !== null ? (
              <span className="font-mono text-[10px] text-[#969696]">
                tentativa #{worker.attemptOrdinal}
              </span>
            ) : null}
          </div>

          <p className="text-xs font-medium text-[#E8E8E8]">{worker.objective}</p>
        </div>

        <StatusBadge status={worker.status} compact />
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px] text-[#969696]">
        <span className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#141414] px-2 py-0.5 text-[#E8E8E8]">
          <Cpu aria-hidden="true" className="h-3 w-3 text-[#969696]" />
          <span>{worker.executorId}</span>
          {worker.model ? (
            <span className="font-mono text-[#969696]">({worker.model})</span>
          ) : null}
        </span>

        <span
          data-testid={`worker-duration-${worker.taskId}`}
          className="inline-flex items-center gap-1 rounded-md border border-[#303030] bg-[#181818] px-2 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
        >
          <Clock aria-hidden="true" className="h-3 w-3 text-[#969696]" />
          <span>{durationBadgeText}</span>
        </span>
      </div>

      <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-[11px] text-[#969696]">
        <FolderGit2 aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />
        <span className="truncate" title={worker.worktreePath ?? 'Worktree não provisionado'}>
          {worker.worktreePath ?? 'Worktree não provisionado'}
        </span>
      </div>

      {worker.checks.length > 0 ? (
        <div
          aria-label={`Verificações da tarefa ${worker.taskId}`}
          className="mt-2.5 flex flex-wrap gap-1.5"
        >
          {worker.checks.map(renderCheckPill)}
        </div>
      ) : null}

      {worker.summary ? (
        <p className="mt-2 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1.5 text-xs text-[#969696]">
          {worker.summary}
        </p>
      ) : null}

      {worker.failures.length > 0 ? (
        <div className="mt-2 space-y-1">
          {worker.failures.map((f, idx) => (
            <div
              key={`${worker.taskId}-fail-${idx}`}
              role="alert"
              className="rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1.5 text-xs text-[#FCA5A5]"
            >
              <span className="font-mono font-semibold">{f.code}:</span> {f.message}
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#303030] pt-2">
        <button
          type="button"
          aria-expanded={traceExpanded}
          onClick={() => setTraceExpanded((prev) => !prev)}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-[#969696] transition-colors hover:text-[#E8E8E8]"
        >
          {traceExpanded ? (
            <ChevronDown aria-hidden="true" className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
          )}
          <span>Trace ({worker.traceRows.length})</span>
        </button>

        {worker.canRetry && onRetryTask ? (
          <button
            type="button"
            disabled={isRetrying}
            onClick={() => void onRetryTask(worker.taskId)}
            data-testid={`retry-task-${worker.taskId}`}
            className="inline-flex items-center gap-1 rounded-lg bg-[#E8E8E8] px-2.5 py-1 text-[11px] font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw aria-hidden="true" className="h-3 w-3" />
            <span>{isRetrying ? 'Reexecutando...' : 'Tentar novamente'}</span>
          </button>
        ) : null}
      </div>

      {traceExpanded ? (
        <div
          data-testid={`worker-trace-rows-${worker.taskId}`}
          className="mt-2 space-y-1 border-t border-[#303030] pt-2"
        >
          {worker.traceRows.length === 0 ? (
            <p className="text-[11px] text-[#969696]">Nenhum evento de trace registrado ainda.</p>
          ) : (
            worker.traceRows.map((row) => (
              <div
                key={row.id}
                className="flex items-start justify-between gap-2 rounded-md bg-[#141414] px-2 py-1 text-[11px]"
              >
                <div className="min-w-0 flex-1">
                  <span className="font-mono text-[#969696]">{row.eventType}</span>
                  <p className="text-[#E8E8E8]">{row.summary}</p>
                  {row.detail ? (
                    <p className="truncate font-mono text-[10px] text-[#969696]">{row.detail}</p>
                  ) : null}
                </div>
                <span className="shrink-0 font-mono text-[10px] text-[#969696]">
                  {row.seq !== null ? `#${row.seq} · ` : ''}
                  {formatTraceTime(row.timestamp)}
                </span>
              </div>
            ))
          )}
        </div>
      ) : null}
    </article>
  );
}
