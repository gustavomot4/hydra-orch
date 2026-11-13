import { createParser, ParseEvent } from 'eventsource-parser';
import { ApiErrorSchema, ControlPlaneApiError, RunStatus } from '@/type/controlPlane';
import {
  ChatTimelineState,
  HitlRequestItem,
  RunDetailSnapshot,
  RunSseEvent,
} from './chatTypes';

export class EventDeduplicator {
  private highestSeq = 0;
  private readonly seenSeqs = new Set<number>();
  private readonly seenIds = new Set<string>();
  private lastCursorId: string | null = null;

  get cursor(): string | null {
    return this.lastCursorId;
  }

  get maxSeq(): number {
    return this.highestSeq;
  }

  accept(
    candidate: { id?: string | null; seq?: number | null },
    options?: { allowBackfill?: boolean },
  ): boolean {
    const seq =
      typeof candidate.seq === 'number' && Number.isFinite(candidate.seq) && candidate.seq > 0
        ? Math.floor(candidate.seq)
        : null;
    const rawId =
      typeof candidate.id === 'string' && candidate.id.trim().length > 0
        ? candidate.id.trim()
        : null;

    if (seq !== null) {
      if (this.seenSeqs.has(seq)) {
        return false;
      }
      if (!options?.allowBackfill && seq <= this.highestSeq) {
        return false;
      }
      if (rawId && this.seenIds.has(rawId)) {
        return false;
      }
      this.seenSeqs.add(seq);
      if (seq > this.highestSeq) {
        this.highestSeq = seq;
        this.lastCursorId = rawId ?? String(seq);
      }
      if (rawId) {
        this.seenIds.add(rawId);
      }
      return true;
    }

    if (rawId) {
      if (this.seenIds.has(rawId)) {
        return false;
      }
      this.seenIds.add(rawId);
      this.lastCursorId = rawId;
      return true;
    }

    return true;
  }

  reset(initialCursor?: string | number | null): void {
    this.highestSeq = 0;
    this.seenSeqs.clear();
    this.seenIds.clear();
    this.lastCursorId = null;

    if (typeof initialCursor === 'number' && Number.isFinite(initialCursor) && initialCursor > 0) {
      this.highestSeq = Math.floor(initialCursor);
      this.lastCursorId = String(this.highestSeq);
    } else if (typeof initialCursor === 'string' && initialCursor.trim().length > 0) {
      const parsed = Number(initialCursor.trim());
      if (Number.isFinite(parsed) && parsed > 0) {
        this.highestSeq = Math.floor(parsed);
      }
      this.lastCursorId = initialCursor.trim();
    }
  }
}

export function deriveTimelineState(params: {
  connectionPhase: 'idle' | 'connecting' | 'streaming' | 'stale_cursor' | 'closed';
  runStatus?: RunStatus | string | null;
  hasPendingHitl?: boolean;
}): ChatTimelineState {
  if (params.connectionPhase === 'stale_cursor') {
    return 'stale_cursor';
  }
  switch (params.runStatus) {
    case 'cancelled':
      return 'cancelled';
    case 'failed':
      return 'failed';
    case 'succeeded':
      return 'completed';
    case 'waiting':
      return 'paused_hitl';
    case 'reviewing':
      return 'reviewing';
    default:
      break;
  }
  if (params.hasPendingHitl) {
    return 'paused_hitl';
  }
  if (params.connectionPhase === 'connecting') {
    return 'connecting';
  }
  if (params.connectionPhase === 'streaming') {
    return 'streaming';
  }
  return 'idle';
}

export function parseSseEventPayload(
  rawData: string,
  eventName?: string,
  eventId?: string,
  defaultRunId = '',
): RunSseEvent | null {
  if (!rawData || rawData.trim() === '' || rawData.trim() === '[DONE]') {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawData);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  const numericSeq =
    typeof record.seq === 'number' && Number.isFinite(record.seq)
      ? Math.floor(record.seq)
      : eventId && /^\d+$/.test(eventId.trim())
        ? Number(eventId.trim())
        : 0;

  const resolvedId =
    eventId && eventId.trim().length > 0
      ? eventId.trim()
      : typeof record.id === 'string' && record.id.trim().length > 0
        ? record.id.trim()
        : numericSeq > 0
          ? String(numericSeq)
          : undefined;

  const resolvedType =
    typeof record.type === 'string' && record.type.trim().length > 0
      ? record.type.trim()
      : eventName && eventName.trim().length > 0
        ? eventName.trim()
        : 'event';

  const payload =
    record.payload && typeof record.payload === 'object' && !Array.isArray(record.payload)
      ? (record.payload as Record<string, unknown>)
      : record;

  return {
    id: resolvedId,
    run_id:
      typeof record.run_id === 'string' && record.run_id.trim().length > 0
        ? record.run_id.trim()
        : defaultRunId,
    seq: numericSeq,
    type: resolvedType,
    correlation_id: typeof record.correlation_id === 'string' ? record.correlation_id : null,
    task_id: typeof record.task_id === 'string' ? record.task_id : null,
    attempt_id: typeof record.attempt_id === 'string' ? record.attempt_id : null,
    session_id: typeof record.session_id === 'string' ? record.session_id : null,
    thread_id: typeof record.thread_id === 'string' ? record.thread_id : null,
    payload,
    timestamp:
      typeof record.timestamp === 'string' && record.timestamp.trim().length > 0
        ? record.timestamp
        : new Date().toISOString(),
  };
}

export function parseSseText(
  text: string,
  defaultRunId = '',
): { events: RunSseEvent[]; retryMs: number | null; sawHeartbeat: boolean } {
  const events: RunSseEvent[] = [];
  let retryMs: number | null = null;
  let sawHeartbeat = false;

  const parser = createParser((parsed: ParseEvent) => {
    if (parsed.type === 'reconnect-interval') {
      retryMs = parsed.value;
      return;
    }
    if (parsed.event === 'heartbeat') {
      sawHeartbeat = true;
      return;
    }
    const ev = parseSseEventPayload(parsed.data, parsed.event, parsed.id, defaultRunId);
    if (ev) {
      events.push(ev);
    }
  });

  const normalizedText =
    text.trim().length === 0
      ? ''
      : text.endsWith('\n\n')
        ? text
        : text.endsWith('\n')
          ? `${text}\n`
          : `${text}\n\n`;
  if (normalizedText) {
    parser.feed(normalizedText);
  }
  parser.reset();
  return { events, retryMs, sawHeartbeat };
}

function buildAuthHeaders(
  token: string | null | undefined,
  extra?: Record<string, string>,
): Record<string, string> {
  const headers: Record<string, string> = { ...(extra ?? {}) };
  if (token && token.trim().length > 0) {
    headers.Authorization = `Bearer ${token.trim()}`;
  }
  return headers;
}

async function parseJsonResponse<T>(
  response: Response,
  onUnauthorized?: () => void,
): Promise<T> {
  const text = await response.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }
  if (!response.ok) {
    const errParsed = ApiErrorSchema.safeParse(parsed);
    const payload = errParsed.success
      ? errParsed.data
      : {
          code: response.status === 401 ? 'unauthorized' : 'http_error',
          message: `Falha na requisição (${response.status})`,
          run_id: null,
          retryable: false,
        };
    if (response.status === 401) {
      onUnauthorized?.();
    }
    throw new ControlPlaneApiError(response.status, payload);
  }
  return parsed as T;
}

export interface RunSnapshotBundle {
  snapshot: RunDetailSnapshot;
  events: RunSseEvent[];
  interventions: HitlRequestItem[];
}

export interface FetchRunSnapshotOptions {
  runId: string;
  token: string | null;
  baseUrl?: string;
  sessionId?: string;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
  onUnauthorized?: () => void;
}

/**
 * Fetches canonical HTTP run snapshot + bounded event replay + HITL interventions.
 * Never sends token in query string and never sends Last-Event-ID during snapshot recovery.
 */
export async function fetchRunSnapshot(
  options: FetchRunSnapshotOptions,
): Promise<RunSnapshotBundle> {
  const baseUrl = (options.baseUrl ?? '').replace(/\/+$/, '');
  const fetchFn = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const encodedRunId = encodeURIComponent(options.runId);

  const runHeaders = buildAuthHeaders(options.token, { Accept: 'application/json' });
  const runResp = await fetchFn(`${baseUrl}/v1/control-plane/runs/${encodedRunId}`, {
    method: 'GET',
    headers: runHeaders,
    signal: options.signal,
  });
  const snapshot = await parseJsonResponse<RunDetailSnapshot>(runResp, options.onUnauthorized);

  const eventsParams = new URLSearchParams({ follow: 'false', after_seq: '0' });
  if (options.sessionId) {
    eventsParams.set('session_id', options.sessionId);
  }
  const eventsResp = await fetchFn(
    `${baseUrl}/v1/control-plane/runs/${encodedRunId}/events?${eventsParams.toString()}`,
    {
      method: 'GET',
      headers: buildAuthHeaders(options.token, {
        Accept: 'text/event-stream, application/json',
      }),
      signal: options.signal,
    },
  );

  let events: RunSseEvent[] = [];
  if (eventsResp.ok) {
    const contentType = eventsResp.headers.get('content-type') ?? '';
    const rawBody = await eventsResp.text();
    if (contentType.includes('application/json') || rawBody.trim().startsWith('[') || rawBody.trim().startsWith('{')) {
      try {
        const json = JSON.parse(rawBody) as unknown;
        const arr = Array.isArray(json)
          ? json
          : json && typeof json === 'object' && Array.isArray((json as { items?: unknown[] }).items)
            ? (json as { items: unknown[] }).items
            : [];
        events = arr
          .map((item) => parseSseEventPayload(JSON.stringify(item), undefined, undefined, options.runId))
          .filter((item): item is RunSseEvent => item !== null);
      } catch {
        events = parseSseText(rawBody, options.runId).events;
      }
    } else {
      events = parseSseText(rawBody, options.runId).events;
    }
  } else if (eventsResp.status === 401) {
    options.onUnauthorized?.();
  }

  let interventions: HitlRequestItem[] = [];
  const hitlResp = await fetchFn(
    `${baseUrl}/v1/control-plane/runs/${encodedRunId}/interventions`,
    {
      method: 'GET',
      headers: runHeaders,
      signal: options.signal,
    },
  );
  if (hitlResp.ok) {
    const hitlData = await parseJsonResponse<HitlRequestItem[]>(hitlResp, options.onUnauthorized);
    if (Array.isArray(hitlData)) {
      interventions = hitlData;
    }
  } else if (hitlResp.status === 401) {
    options.onUnauthorized?.();
  }

  return { snapshot, events, interventions };
}

export interface ConnectRunSseOptions {
  runId: string;
  token: string | null;
  baseUrl?: string;
  sessionId?: string;
  lastEventId?: string | number | null;
  follow?: boolean;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
  deduplicator?: EventDeduplicator;
  fallbackToSnapshotOn410?: boolean;
  onEvent: (event: RunSseEvent) => void;
  onStateChange?: (state: ChatTimelineState) => void;
  onSnapshotRecovery?: (bundle: RunSnapshotBundle, acceptedEvents: RunSseEvent[]) => void;
  onHeartbeat?: (timestamp: string) => void;
  onError?: (error: Error) => void;
  onUnauthorized?: () => void;
}

export interface RunSseConnectionResult {
  status: 'completed' | 'aborted' | 'recovered_from_410' | 'error';
  lastCursor: string | null;
  eventsAccepted: number;
}

/**
 * Connects to /v1/control-plane/runs/{run_id}/events over fetch + eventsource-parser.
 * - Sends Authorization: Bearer <token> and Last-Event-ID headers (no token in URL).
 * - Deduplicates events by seq / id.
 * - Handles HTTP 410 cursor_expired via clean GET snapshot fallback without retrying mutations.
 */
export async function connectRunEventStream(
  options: ConnectRunSseOptions,
): Promise<RunSseConnectionResult> {
  const baseUrl = (options.baseUrl ?? '').replace(/\/+$/, '');
  const fetchFn = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const dedup = options.deduplicator ?? new EventDeduplicator();
  const follow = options.follow ?? true;

  if (options.lastEventId !== undefined && options.lastEventId !== null && !dedup.cursor) {
    dedup.reset(options.lastEventId);
  }

  const cursorToSend =
    options.lastEventId !== undefined && options.lastEventId !== null
      ? String(options.lastEventId).trim()
      : dedup.cursor;

  const qs = new URLSearchParams({ follow: follow ? 'true' : 'false' });
  if (options.sessionId) {
    qs.set('session_id', options.sessionId);
  }
  const url = `${baseUrl}/v1/control-plane/runs/${encodeURIComponent(options.runId)}/events?${qs.toString()}`;

  const headers = buildAuthHeaders(options.token, {
    Accept: 'text/event-stream',
  });
  if (cursorToSend && cursorToSend.length > 0) {
    headers['Last-Event-ID'] = cursorToSend;
  }

  options.onStateChange?.('connecting');

  let response: Response;
  try {
    response = await fetchFn(url, {
      method: 'GET',
      headers,
      signal: options.signal,
    });
  } catch (err) {
    if (options.signal?.aborted) {
      return { status: 'aborted', lastCursor: dedup.cursor, eventsAccepted: 0 };
    }
    const error = err instanceof Error ? err : new Error('Falha ao conectar ao stream SSE');
    options.onError?.(error);
    options.onStateChange?.('idle');
    return { status: 'error', lastCursor: dedup.cursor, eventsAccepted: 0 };
  }

  if (response.status === 410) {
    options.onStateChange?.('stale_cursor');
    if (options.fallbackToSnapshotOn410 !== false) {
      try {
        const bundle = await fetchRunSnapshot({
          runId: options.runId,
          token: options.token,
          baseUrl: options.baseUrl,
          sessionId: options.sessionId,
          signal: options.signal,
          fetchImpl: fetchFn,
          onUnauthorized: options.onUnauthorized,
        });
        const acceptedSnapshotEvents: RunSseEvent[] = [];
        for (const ev of bundle.events) {
          if (dedup.accept(ev, { allowBackfill: true })) {
            acceptedSnapshotEvents.push(ev);
          }
        }
        options.onSnapshotRecovery?.(bundle, acceptedSnapshotEvents);
        const hasPendingHitl = bundle.interventions.some((i) => i.state === 'pending');
        options.onStateChange?.(
          deriveTimelineState({
            connectionPhase: 'closed',
            runStatus: bundle.snapshot.status,
            hasPendingHitl,
          }),
        );
        return {
          status: 'recovered_from_410',
          lastCursor: dedup.cursor,
          eventsAccepted: acceptedSnapshotEvents.length,
        };
      } catch (snapErr) {
        const error =
          snapErr instanceof Error ? snapErr : new Error('Falha ao recuperar snapshot após HTTP 410');
        options.onError?.(error);
        return { status: 'error', lastCursor: dedup.cursor, eventsAccepted: 0 };
      }
    }
    return { status: 'recovered_from_410', lastCursor: dedup.cursor, eventsAccepted: 0 };
  }

  if (!response.ok) {
    try {
      await parseJsonResponse<unknown>(response, options.onUnauthorized);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(`Erro SSE HTTP ${response.status}`);
      options.onError?.(error);
    }
    options.onStateChange?.('idle');
    return { status: 'error', lastCursor: dedup.cursor, eventsAccepted: 0 };
  }

  options.onStateChange?.('streaming');
  let eventsAccepted = 0;

  const parser = createParser((parsed: ParseEvent) => {
    if (parsed.type === 'reconnect-interval') {
      return;
    }
    if (parsed.event === 'heartbeat') {
      try {
        const hb = JSON.parse(parsed.data) as { timestamp?: string };
        options.onHeartbeat?.(hb.timestamp ?? new Date().toISOString());
      } catch {
        options.onHeartbeat?.(new Date().toISOString());
      }
      return;
    }
    const ev = parseSseEventPayload(parsed.data, parsed.event, parsed.id, options.runId);
    if (!ev) {
      return;
    }
    if (dedup.accept(ev)) {
      eventsAccepted += 1;
      options.onEvent(ev);
      if (ev.type === 'hitl.requested' || ev.type === 'run.waiting') {
        options.onStateChange?.('paused_hitl');
      } else if (ev.type === 'hitl.resolved' || ev.type === 'run.resumed') {
        options.onStateChange?.('streaming');
      } else if (ev.type === 'run.cancelled') {
        options.onStateChange?.('cancelled');
      } else if (ev.type === 'run.finished') {
        const finishedStatus =
          typeof ev.payload.status === 'string' ? ev.payload.status : undefined;
        options.onStateChange?.(
          deriveTimelineState({
            connectionPhase: 'closed',
            runStatus: finishedStatus ?? 'completed',
          }),
        );
      }
    }
  });

  parser.reset();

  try {
    if (response.body && typeof response.body.getReader === 'function') {
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let streamDone = false;
      while (!streamDone) {
        if (options.signal?.aborted) {
          await reader.cancel().catch(() => undefined);
          return { status: 'aborted', lastCursor: dedup.cursor, eventsAccepted };
        }
        const { done, value } = await reader.read();
        if (done) {
          const tail = decoder.decode();
          if (tail) {
            parser.feed(tail);
          }
          streamDone = true;
        } else if (value) {
          parser.feed(decoder.decode(value, { stream: true }));
        }
      }
    } else {
      const text = await response.text();
      if (text) {
        parser.feed(text);
      }
    }
  } catch (err) {
    if (options.signal?.aborted) {
      return { status: 'aborted', lastCursor: dedup.cursor, eventsAccepted };
    }
    const error = err instanceof Error ? err : new Error('Stream SSE interrompido');
    options.onError?.(error);
    return { status: 'error', lastCursor: dedup.cursor, eventsAccepted };
  }

  return { status: 'completed', lastCursor: dedup.cursor, eventsAccepted };
}
