import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { PromptComposer } from '@/feature/composer';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  buildCoordinatorTimeline,
  buildWorkerCards,
  ChatTimelineState,
  createIdempotencyKey,
  extractCanonicalChecks,
  HitlRequestItem,
  RunDetailSnapshot,
  RunSseEvent,
} from './chatTypes';
import { CoordinatorView } from './CoordinatorView';
import {
  connectRunEventStream,
  deriveTimelineState,
  EventDeduplicator,
  fetchRunSnapshot,
} from './sseClient';

export interface ChatTimelinePageProps {
  runId?: string;
  sessionId?: string;
  initialCursor?: string | number | null;
  connectStreamOnTerminal?: boolean;
  client?: ControlPlaneClient;
  fetchImpl?: typeof fetch;
  onOpenTerminal?: (runId: string) => void;
}

interface ActiveThreadRef {
  sessionId: string;
  threadId: string;
  lastSeq: number;
}

const TERMINAL_RUN_STATUSES = new Set(['succeeded', 'failed', 'cancelled']);

function mergeEventsSorted(existing: RunSseEvent[], incoming: RunSseEvent[]): RunSseEvent[] {
  if (incoming.length === 0) {
    return existing;
  }
  const merged = [...existing, ...incoming];
  merged.sort((a, b) => {
    if (a.seq > 0 && b.seq > 0 && a.seq !== b.seq) {
      return a.seq - b.seq;
    }
    return a.timestamp.localeCompare(b.timestamp);
  });
  return merged;
}

export function ChatTimelinePage({
  runId: propRunId,
  sessionId: propSessionId,
  initialCursor = null,
  connectStreamOnTerminal = false,
  client,
  fetchImpl,
  onOpenTerminal,
}: ChatTimelinePageProps) {
  const params = useParams<{ id?: string }>();
  const defaultClient = useControlPlaneClient();
  const activeClient = client ?? defaultClient;
  const token = useAuthStore((s) => s.token);
  const lock = useAuthStore((s) => s.lock);
  const selectedRunId = useLayoutStore((s) => s.selectedRunId);

  const effectiveRunId = (propRunId ?? params.id ?? selectedRunId ?? '').trim();

  const [snapshot, setSnapshot] = useState<RunDetailSnapshot | null>(null);
  const [events, setEvents] = useState<RunSseEvent[]>([]);
  const [interventions, setInterventions] = useState<HitlRequestItem[]>([]);
  const [timelineState, setTimelineState] = useState<ChatTimelineState>('idle');
  const [retryingTaskIds, setRetryingTaskIds] = useState<Set<string>>(() => new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSubmittingMessage, setIsSubmittingMessage] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastHeartbeatAt, setLastHeartbeatAt] = useState<string | null>(null);
  const [activeThread, setActiveThread] = useState<ActiveThreadRef | null>(null);
  const [messageDraft, setMessageDraft] = useState('');

  const deduplicatorRef = useRef<EventDeduplicator>(new EventDeduplicator());
  const streamAbortRef = useRef<AbortController | null>(null);
  const inFlightRetryRef = useRef<Set<string>>(new Set());
  const inFlightMessageRef = useRef<boolean>(false);
  const mountedRef = useRef<boolean>(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const resolveActiveThread = useCallback(
    async (runId: string) => {
      try {
        const sessions = await activeClient.listSessions(runId);
        const targetSession =
          (propSessionId
            ? sessions.find((s) => s.id === propSessionId)
            : sessions.find((s) => s.state === 'running' || s.state === 'waiting')) ??
          sessions[0];
        if (!targetSession) {
          if (mountedRef.current) {
            setActiveThread(null);
          }
          return;
        }
        const threads = await activeClient.listSessionThreads(targetSession.id);
        const targetThread =
          threads.find((t) => t.parent_thread_id === null) ?? threads[0];
        if (mountedRef.current) {
          setActiveThread(
            targetThread
              ? {
                  sessionId: targetSession.id,
                  threadId: targetThread.id,
                  lastSeq: targetThread.last_seq,
                }
              : null,
          );
        }
      } catch {
        if (mountedRef.current) {
          setActiveThread(null);
        }
      }
    },
    [activeClient, propSessionId],
  );

  const loadSnapshotOnly = useCallback(
    async (runId: string, signal?: AbortSignal) => {
      setIsRefreshing(true);
      try {
        const bundle = await fetchRunSnapshot({
          runId,
          token,
          sessionId: propSessionId,
          signal,
          fetchImpl,
          onUnauthorized: () => lock('Sessão expirada ou token inválido (HTTP 401).'),
        });
        if (!mountedRef.current || signal?.aborted) {
          return null;
        }
        setSnapshot(bundle.snapshot);
        setInterventions(bundle.interventions);

        const accepted: RunSseEvent[] = [];
        for (const ev of bundle.events) {
          if (deduplicatorRef.current.accept(ev, { allowBackfill: true })) {
            accepted.push(ev);
          }
        }
        if (accepted.length > 0) {
          setEvents((prev) => mergeEventsSorted(prev, accepted));
        }

        const hasPendingHitl = bundle.interventions.some((req) => req.state === 'pending');
        setTimelineState((prev) =>
          prev === 'streaming'
            ? hasPendingHitl
              ? 'paused_hitl'
              : deriveTimelineState({
                  connectionPhase: 'streaming',
                  runStatus: bundle.snapshot.status,
                  hasPendingHitl,
                })
            : deriveTimelineState({
                connectionPhase: 'closed',
                runStatus: bundle.snapshot.status,
                hasPendingHitl,
              }),
        );
        setErrorMessage(null);
        return bundle;
      } catch (err) {
        if (!mountedRef.current || signal?.aborted) {
          return null;
        }
        const msg =
          err instanceof ControlPlaneApiError
            ? err.payload.message
            : err instanceof Error
              ? err.message
              : 'Falha ao carregar snapshot do run.';
        setErrorMessage(msg);
        return null;
      } finally {
        if (mountedRef.current) {
          setIsRefreshing(false);
        }
      }
    },
    [token, propSessionId, fetchImpl, lock],
  );

  const startEventStream = useCallback(
    (runId: string, cursorOverride?: string | number | null) => {
      streamAbortRef.current?.abort();
      const controller = new AbortController();
      streamAbortRef.current = controller;

      const cursorToUse =
        cursorOverride !== undefined && cursorOverride !== null
          ? cursorOverride
          : deduplicatorRef.current.cursor;

      void connectRunEventStream({
        runId,
        token,
        sessionId: propSessionId,
        lastEventId: cursorToUse,
        follow: true,
        signal: controller.signal,
        fetchImpl,
        deduplicator: deduplicatorRef.current,
        onUnauthorized: () => lock('Sessão expirada ou token inválido (HTTP 401).'),
        onStateChange: (nextState) => {
          if (mountedRef.current && !controller.signal.aborted) {
            setTimelineState(nextState);
          }
        },
        onHeartbeat: (ts) => {
          if (mountedRef.current && !controller.signal.aborted) {
            setLastHeartbeatAt(ts);
          }
        },
        onEvent: (ev) => {
          if (!mountedRef.current || controller.signal.aborted) {
            return;
          }
          setEvents((prev) => mergeEventsSorted(prev, [ev]));
          if (ev.type === 'hitl.requested' || ev.type === 'hitl.resolved') {
            void activeClient
              .request<HitlRequestItem[]>(
                `/v1/control-plane/runs/${encodeURIComponent(runId)}/interventions`,
              )
              .then((items) => {
                if (mountedRef.current && Array.isArray(items)) {
                  setInterventions(items);
                }
              })
              .catch(() => undefined);
          }
          if (
            ev.type === 'task.started' ||
            ev.type === 'task.failed' ||
            ev.type === 'attempt.finished' ||
            ev.type === 'check.finished' ||
            ev.type === 'run.finished' ||
            ev.type === 'run.cancelled'
          ) {
            void loadSnapshotOnly(runId, controller.signal);
          }
        },
        onSnapshotRecovery: (bundle, acceptedEvents) => {
          if (!mountedRef.current || controller.signal.aborted) {
            return;
          }
          setSnapshot(bundle.snapshot);
          setInterventions(bundle.interventions);
          if (acceptedEvents.length > 0) {
            setEvents((prev) => mergeEventsSorted(prev, acceptedEvents));
          }
          setErrorMessage(null);
        },
        onError: (err) => {
          if (mountedRef.current && !controller.signal.aborted) {
            setErrorMessage(err.message);
          }
        },
      });
    },
    [token, propSessionId, fetchImpl, lock, activeClient, loadSnapshotOnly],
  );

  useEffect(() => {
    streamAbortRef.current?.abort();
    deduplicatorRef.current.reset(initialCursor);
    setSnapshot(null);
    setEvents([]);
    setInterventions([]);
    setErrorMessage(null);
    setLastHeartbeatAt(null);
    setTimelineState('idle');

    if (!effectiveRunId) {
      return;
    }

    const controller = new AbortController();

    void (async () => {
      const bundle = await loadSnapshotOnly(effectiveRunId, controller.signal);
      if (!mountedRef.current || controller.signal.aborted) {
        return;
      }
      void resolveActiveThread(effectiveRunId);

      const shouldConnectStream =
        connectStreamOnTerminal ||
        !bundle ||
        !TERMINAL_RUN_STATUSES.has(bundle.snapshot.status);
      if (shouldConnectStream) {
        startEventStream(effectiveRunId, initialCursor);
      }
    })();

    return () => {
      controller.abort();
      streamAbortRef.current?.abort();
    };
  }, [
    effectiveRunId,
    initialCursor,
    connectStreamOnTerminal,
    loadSnapshotOnly,
    resolveActiveThread,
    startEventStream,
  ]);

  const handleRetryTask = useCallback(
    async (taskId: string) => {
      if (!effectiveRunId || inFlightRetryRef.current.has(taskId)) {
        return;
      }
      inFlightRetryRef.current.add(taskId);
      setRetryingTaskIds((prev) => {
        const next = new Set(prev);
        next.add(taskId);
        return next;
      });
      setErrorMessage(null);

      try {
        await activeClient.request<unknown>(
          `/v1/control-plane/runs/${encodeURIComponent(effectiveRunId)}/tasks/${encodeURIComponent(taskId)}/retry`,
          {
            method: 'POST',
            body: {},
          },
        );
        await loadSnapshotOnly(effectiveRunId);
      } catch (err) {
        const msg =
          err instanceof ControlPlaneApiError
            ? err.payload.message
            : err instanceof Error
              ? err.message
              : `Falha ao reexecutar tarefa ${taskId}.`;
        setErrorMessage(msg);
      } finally {
        inFlightRetryRef.current.delete(taskId);
        if (mountedRef.current) {
          setRetryingTaskIds((prev) => {
            const next = new Set(prev);
            next.delete(taskId);
            return next;
          });
        }
      }
    },
    [effectiveRunId, activeClient, loadSnapshotOnly],
  );

  const handleInterventionResponded = useCallback(
    (updated: HitlRequestItem) => {
      setInterventions((prev) =>
        prev.map((item) => (item.request_id === updated.request_id ? updated : item)),
      );
      if (effectiveRunId) {
        void loadSnapshotOnly(effectiveRunId);
      }
    },
    [effectiveRunId, loadSnapshotOnly],
  );

  const handleSendThreadMessage = useCallback(
    async (submittedText?: string) => {
      const content = (submittedText ?? messageDraft).trim();
      if (!effectiveRunId || !activeThread || !content || inFlightMessageRef.current) {
        return;
      }
      inFlightMessageRef.current = true;
      setIsSubmittingMessage(true);
      setErrorMessage(null);

      try {
        const result = await activeClient.request<{ seq?: number }>(
          `/v1/control-plane/runs/${encodeURIComponent(effectiveRunId)}/sessions/${encodeURIComponent(activeThread.sessionId)}/threads/${encodeURIComponent(activeThread.threadId)}/messages`,
          {
            method: 'POST',
            headers: { 'Idempotency-Key': createIdempotencyKey('msg-send') },
            body: {
              content,
              expected_last_seq: activeThread.lastSeq,
            },
          },
        );
        if (mountedRef.current) {
          setMessageDraft('');
          if (typeof result?.seq === 'number') {
            setActiveThread((prev) =>
              prev ? { ...prev, lastSeq: result.seq as number } : null,
            );
          }
          await loadSnapshotOnly(effectiveRunId);
        }
      } catch (err) {
        if (mountedRef.current) {
          const msg =
            err instanceof ControlPlaneApiError
              ? err.payload.message
              : err instanceof Error
                ? err.message
                : 'Falha ao enviar mensagem para a thread.';
          setErrorMessage(msg);
        }
      } finally {
        inFlightMessageRef.current = false;
        if (mountedRef.current) {
          setIsSubmittingMessage(false);
        }
      }
    },
    [effectiveRunId, activeThread, messageDraft, activeClient, loadSnapshotOnly],
  );

  const checks = useMemo(
    () => extractCanonicalChecks(snapshot, events),
    [snapshot, events],
  );
  const workers = useMemo(
    () => buildWorkerCards(snapshot, events),
    [snapshot, events],
  );
  const timelineItems = useMemo(
    () => buildCoordinatorTimeline(snapshot, events),
    [snapshot, events],
  );

  if (!effectiveRunId) {
    return (
      <div
        data-testid="chat-timeline-empty"
        className="flex h-full items-center justify-center bg-[#141414] p-6 text-sm text-[#969696]"
      >
        Selecione uma conversa na barra lateral ou inicie um novo chat.
      </div>
    );
  }

  const canSendFollowUp = Boolean(
    activeThread && (!snapshot || !TERMINAL_RUN_STATUSES.has(snapshot.status)),
  );

  return (
    <CoordinatorView
      runId={effectiveRunId}
      snapshot={snapshot}
      timelineState={timelineState}
      timelineItems={timelineItems}
      checks={checks}
      workers={workers}
      interventions={interventions}
      retryingTaskIds={retryingTaskIds}
      isRefreshing={isRefreshing}
      errorMessage={errorMessage}
      lastHeartbeatAt={lastHeartbeatAt}
      client={activeClient}
      onRefreshSnapshot={() => void loadSnapshotOnly(effectiveRunId)}
      onReconnectStream={() => startEventStream(effectiveRunId)}
      onRetryTask={handleRetryTask}
      onInterventionResponded={handleInterventionResponded}
      onOpenTerminal={onOpenTerminal}
      composerSlot={
        <PromptComposer
          sessionKey={`run:${effectiveRunId}`}
          draft={messageDraft}
          onDraftChange={setMessageDraft}
          mode={snapshot?.mode ?? 'relay'}
          hideModeSelector
          disabled={!canSendFollowUp}
          isSubmitting={isSubmittingMessage}
          submitLabel="Enviar mensagem"
          placeholder={
            canSendFollowUp
              ? 'Enviar instrução complementar ou comando (@agente, /review)...'
              : activeThread
                ? 'Run encerrado — histórico somente leitura.'
                : 'Aguardando thread de sessão ativa para mensagens complementares.'
          }
          onSubmit={(text) => void handleSendThreadMessage(text)}
          onSlashCommand={(cmd) => {
            if (cmd.command === '/terminal' && onOpenTerminal) {
              onOpenTerminal(effectiveRunId);
              return true;
            }
            if (cmd.command === '/status') {
              void loadSnapshotOnly(effectiveRunId);
              return true;
            }
            return false;
          }}
        />
      }
    />
  );
}
