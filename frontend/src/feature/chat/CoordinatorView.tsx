import { ReactNode, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronRight,
  Layers,
  RefreshCw,
  ShieldCheck,
  Terminal,
  User,
  Wifi,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  CHAT_TIMELINE_STATE_META,
  ChatTimelineState,
  CheckBadgeItem,
  HitlRequestItem,
  RunDetailSnapshot,
  TimelineRenderItem,
  WorkerCardModel,
} from './chatTypes';
import { HitlInlineCard } from './HitlInlineCard';
import { WorkerCard } from './WorkerCard';

export interface CheckBadgeProps {
  check: CheckBadgeItem;
}

export function CheckBadge({ check }: CheckBadgeProps) {
  const statusKind =
    check.status === 'passed'
      ? 'succeeded'
      : check.status === 'failed'
        ? 'failed'
        : check.status === 'pending'
          ? 'waiting'
          : 'unknown';

  const statusLabel =
    check.status === 'passed'
      ? 'Aprovado'
      : check.status === 'failed'
        ? 'Falhou'
        : check.status === 'pending'
          ? 'Pendente'
          : 'Desconhecido';

  return (
    <div
      data-testid={`check-badge-${check.taskId ?? 'run'}-${check.checkId}`}
      data-check-id={check.checkId}
      data-check-status={check.status}
      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono font-medium text-[#E8E8E8]">{check.checkId}</span>
          {check.taskId ? (
            <span className="font-mono text-[10px] text-[#969696]">({check.taskId})</span>
          ) : null}
          {check.exitCode !== null ? (
            <span className="font-mono text-[10px] text-[#969696]">
              exit {check.exitCode}
            </span>
          ) : null}
          {check.durationSeconds !== null ? (
            <span className="font-mono text-[10px] text-[#969696]">
              {check.durationSeconds.toFixed(1)}s
            </span>
          ) : null}
        </div>
        {check.commandText ? (
          <p className="truncate font-mono text-[11px] text-[#969696]" title={check.commandText}>
            $ {check.commandText}
          </p>
        ) : null}
      </div>

      <StatusBadge status={statusKind} labelOverride={statusLabel} compact />
    </div>
  );
}

function formatTimelineTime(iso: string): string {
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

function StepGroupCard({ group }: { group: Extract<TimelineRenderItem, { kind: 'step_group' }> }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      data-testid={`step-group-${group.id}`}
      className="rounded-xl border border-[#303030] bg-[#1C1C1C] px-3 py-2"
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2 text-left text-xs text-[#969696] transition-colors hover:text-[#E8E8E8]"
      >
        <span className="inline-flex items-center gap-1.5 font-medium">
          {expanded ? (
            <ChevronDown aria-hidden="true" className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
          )}
          <span>{group.title}</span>
        </span>
        <span className="font-mono text-[11px]">{formatTimelineTime(group.timestamp)}</span>
      </button>

      {expanded ? (
        <ul className="mt-2 space-y-1.5 border-t border-[#303030] pt-2">
          {group.steps.map((step) => (
            <li
              key={step.id}
              className="flex items-start justify-between gap-2 rounded-lg bg-[#141414] px-2.5 py-1.5 text-xs"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[11px] text-[#969696]">{step.eventType}</span>
                  {step.taskId ? (
                    <span className="rounded border border-[#303030] px-1 py-0.5 font-mono text-[10px] text-[#969696]">
                      {step.taskId}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-[#E8E8E8]">{step.title}</p>
                {step.detail ? (
                  <p className="mt-0.5 font-mono text-[11px] text-[#969696]">{step.detail}</p>
                ) : null}
              </div>
              <span className="shrink-0 font-mono text-[10px] text-[#969696]">
                {step.seq !== null ? `#${step.seq} · ` : ''}
                {formatTimelineTime(step.timestamp)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export interface CoordinatorViewProps {
  runId: string;
  snapshot: RunDetailSnapshot | null;
  timelineState: ChatTimelineState;
  timelineItems: TimelineRenderItem[];
  checks: CheckBadgeItem[];
  workers: WorkerCardModel[];
  interventions: HitlRequestItem[];
  retryingTaskIds?: Set<string>;
  isRefreshing?: boolean;
  errorMessage?: string | null;
  lastHeartbeatAt?: string | null;
  client?: ControlPlaneClient;
  composerSlot?: ReactNode;
  onRefreshSnapshot?: () => void;
  onReconnectStream?: () => void;
  onRetryTask?: (taskId: string) => Promise<void> | void;
  onInterventionResponded?: (updated: HitlRequestItem) => void;
  onOpenTerminal?: (runId: string) => void;
}

export function CoordinatorView({
  runId,
  snapshot,
  timelineState,
  timelineItems,
  checks,
  workers,
  interventions,
  retryingTaskIds,
  isRefreshing = false,
  errorMessage = null,
  lastHeartbeatAt = null,
  client,
  composerSlot,
  onRefreshSnapshot,
  onReconnectStream,
  onRetryTask,
  onInterventionResponded,
  onOpenTerminal,
}: CoordinatorViewProps) {
  const [mobilePanel, setMobilePanel] = useState<'coordinator' | 'workers'>('coordinator');
  const stateMeta = CHAT_TIMELINE_STATE_META[timelineState];

  const wavesMap = new Map<number, WorkerCardModel[]>();
  for (const w of workers) {
    const list = wavesMap.get(w.wave) ?? [];
    list.push(w);
    wavesMap.set(w.wave, list);
  }
  const sortedWaves = Array.from(wavesMap.entries()).sort(([a], [b]) => a - b);

  return (
    <div
      data-testid="coordinator-view"
      data-timeline-state={timelineState}
      className="flex h-full min-h-0 flex-col bg-[#141414] text-[#E8E8E8]"
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#303030] bg-[#181818] px-4 py-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-[#969696]">{runId}</span>
            {snapshot ? (
              <span className="rounded border border-[#303030] bg-[#202020] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]">
                {snapshot.mode === 'swarm'
                  ? 'Swarm'
                  : snapshot.mode === 'relay'
                    ? 'Relay'
                    : 'Persistente'}
              </span>
            ) : null}
            {snapshot ? <StatusBadge status={snapshot.status} compact /> : null}
            <span
              data-testid="sse-timeline-state-badge"
              data-state={timelineState}
              title={stateMeta.description}
            >
              <StatusBadge
                status={stateMeta.badgeStatus}
                labelOverride={`SSE: ${stateMeta.label}`}
                compact
              />
            </span>
          </div>

          <h1 className="truncate text-sm font-semibold text-[#E8E8E8]">
            {snapshot?.objective ?? 'Conversa coordenada'}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {lastHeartbeatAt ? (
            <span className="hidden items-center gap-1 font-mono text-[11px] text-[#969696] xl:inline-flex">
              <Wifi aria-hidden="true" className="h-3 w-3 text-[#22C55E]" />
              <span>{formatTimelineTime(lastHeartbeatAt)}</span>
            </span>
          ) : null}

          {onOpenTerminal ? (
            <button
              type="button"
              onClick={() => onOpenTerminal(runId)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs text-[#E8E8E8] transition-colors hover:bg-[#282828]"
            >
              <Terminal aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
              <span>Terminal</span>
            </button>
          ) : null}

          {onReconnectStream && (timelineState === 'idle' || timelineState === 'stale_cursor') ? (
            <button
              type="button"
              onClick={onReconnectStream}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs text-[#E8E8E8] transition-colors hover:bg-[#282828]"
            >
              <Wifi aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
              <span>Reconectar stream</span>
            </button>
          ) : null}

          {onRefreshSnapshot ? (
            <button
              type="button"
              disabled={isRefreshing}
              onClick={onRefreshSnapshot}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:opacity-50"
            >
              <RefreshCw
                aria-hidden="true"
                className={`h-3.5 w-3.5 text-[#969696] ${isRefreshing ? 'motion-safe:animate-spin' : ''}`}
              />
              <span>Atualizar</span>
            </button>
          ) : null}

          <div className="flex rounded-lg border border-[#303030] bg-[#141414] p-0.5 lg:hidden">
            <button
              type="button"
              onClick={() => setMobilePanel('coordinator')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                mobilePanel === 'coordinator'
                  ? 'bg-[#282828] text-[#E8E8E8]'
                  : 'text-[#969696]'
              }`}
            >
              Coordenador
            </button>
            <button
              type="button"
              onClick={() => setMobilePanel('workers')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                mobilePanel === 'workers'
                  ? 'bg-[#282828] text-[#E8E8E8]'
                  : 'text-[#969696]'
              }`}
            >
              Workers ({workers.length})
            </button>
          </div>
        </div>
      </header>

      {timelineState === 'stale_cursor' ? (
        <div
          role="status"
          data-testid="stale-cursor-banner"
          className="flex flex-wrap items-center justify-between gap-2 border-b border-[#F59E0B]/40 bg-[#F59E0B]/10 px-4 py-2 text-xs text-[#FCD34D]"
        >
          <span>
            Cursor SSE expirado (HTTP 410). Recuperando snapshot HTTP durável sem reenviar mutações.
          </span>
        </div>
      ) : null}

      {errorMessage ? (
        <div
          role="alert"
          className="border-b border-[#EF4444]/40 bg-[#EF4444]/10 px-4 py-2 text-xs text-[#FCA5A5]"
        >
          {errorMessage}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section
          aria-label="Linha do tempo do coordenador"
          data-testid="coordinator-timeline-pane"
          className={`flex min-h-0 flex-col border-r border-[#303030] ${
            mobilePanel === 'workers' ? 'hidden lg:flex' : 'flex'
          }`}
        >
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {timelineItems.length === 0 ? (
              <div className="rounded-xl border border-[#303030] bg-[#202020] p-4 text-xs text-[#969696]">
                Aguardando eventos duráveis do run <span className="font-mono">{runId}</span>...
              </div>
            ) : (
              timelineItems.map((item) => {
                if (item.kind === 'step_group') {
                  return <StepGroupCard key={item.id} group={item} />;
                }
                const isUser = item.role === 'user';
                return (
                  <article
                    key={item.id}
                    data-testid={`timeline-message-${item.id}`}
                    className={`rounded-xl border p-3.5 ${
                      isUser
                        ? 'border-[#303030] bg-[#202020]'
                        : 'border-[#303030] bg-[#1C1C1C]'
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-1.5 font-medium text-[#E8E8E8]">
                        {isUser ? (
                          <User aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
                        ) : (
                          <Bot aria-hidden="true" className="h-3.5 w-3.5 text-[#60A5FA]" />
                        )}
                        <span>{item.author}</span>
                        {item.taskId ? (
                          <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] text-[#969696]">
                            {item.taskId}
                          </span>
                        ) : null}
                      </div>
                      <span className="font-mono text-[11px] text-[#969696]">
                        {item.seq ? `#${item.seq} · ` : ''}
                        {formatTimelineTime(item.timestamp)}
                      </span>
                    </div>

                    <p className="mt-2 whitespace-pre-wrap text-sm text-[#E8E8E8]">
                      {item.content}
                    </p>

                    {item.hasUnverifiedCompletionClaim ? (
                      <div
                        role="note"
                        data-testid="unverified-claim-warning"
                        className="mt-2.5 flex items-center gap-2 rounded-lg border border-[#F59E0B]/40 bg-[#F59E0B]/10 px-2.5 py-1.5 text-xs text-[#FCD34D]"
                      >
                        <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                        <span>
                          Resposta textual do agente não marca checks como aprovados. Consulte o painel de verificações canônicas do backend.
                        </span>
                      </div>
                    ) : null}
                  </article>
                );
              })
            )}

            <section
              aria-label="Verificações canônicas do backend"
              data-testid="canonical-checks-panel"
              className="rounded-xl border border-[#303030] bg-[#202020] p-3.5"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[#969696]" />
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
                    Verificações canônicas (Backend)
                  </h2>
                </div>
                <span className="font-mono text-[11px] text-[#969696]">
                  {checks.length} {checks.length === 1 ? 'check' : 'checks'}
                </span>
              </div>

              {checks.length === 0 ? (
                <p className="mt-2 text-xs text-[#969696]">
                  Nenhuma verificação registrada pelo backend até o momento.
                </p>
              ) : (
                <div className="mt-2.5 space-y-1.5">
                  {checks.map((chk) => (
                    <CheckBadge key={`${chk.taskId ?? 'run'}-${chk.checkId}`} check={chk} />
                  ))}
                </div>
              )}
            </section>

            <HitlInlineCard
              runId={runId}
              requests={interventions}
              client={client}
              onResponded={onInterventionResponded}
            />
          </div>

          {composerSlot ? (
            <div className="border-t border-[#303030] bg-[#181818] p-3">{composerSlot}</div>
          ) : null}
        </section>

        <aside
          aria-label="Painel de subagentes e workers"
          data-testid="workers-panel"
          className={`flex min-h-0 flex-col bg-[#1C1C1C] ${
            mobilePanel === 'coordinator' ? 'hidden lg:flex' : 'flex'
          }`}
        >
          <div className="flex items-center justify-between border-b border-[#303030] px-4 py-3">
            <div className="flex items-center gap-2">
              <Layers aria-hidden="true" className="h-4 w-4 text-[#969696]" />
              <h2 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
                Subagentes e Workers
              </h2>
            </div>
            <span className="rounded border border-[#303030] bg-[#202020] px-2 py-0.5 font-mono text-[11px] text-[#969696]">
              {workers.length}
            </span>
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3.5">
            {sortedWaves.length === 0 ? (
              <div className="rounded-xl border border-[#303030] bg-[#202020] p-4 text-xs text-[#969696]">
                Nenhum worker ou tarefa vinculada a este run.
              </div>
            ) : (
              sortedWaves.map(([wave, waveWorkers]) => (
                <section
                  key={`wave-${wave}`}
                  data-testid={`worker-wave-group-${wave}`}
                  className="space-y-2"
                >
                  <div className="flex items-center justify-between px-1">
                    <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#969696]">
                      {snapshot?.mode === 'swarm'
                        ? `Swarm Wave ${wave}`
                        : `Etapa ${wave + 1} (Wave ${wave})`}
                    </h3>
                    <span className="font-mono text-[11px] text-[#969696]">
                      {waveWorkers.length}{' '}
                      {waveWorkers.length === 1 ? 'worker' : 'workers'}
                    </span>
                  </div>
                  <div className="space-y-2.5">
                    {waveWorkers.map((worker) => (
                      <WorkerCard
                        key={worker.taskId}
                        worker={worker}
                        onRetryTask={onRetryTask}
                        isRetrying={retryingTaskIds?.has(worker.taskId) ?? false}
                      />
                    ))}
                  </div>
                </section>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
