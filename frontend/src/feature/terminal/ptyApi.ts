import { createParser } from 'eventsource-parser';
import { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ApiErrorSchema, ControlPlaneApiError } from '@/type/controlPlane';
import {
  PtyChunk,
  PtyInputResponse,
  PtyOutputResponse,
  PtySessionCreatePayload,
  PtySessionInfo,
} from './terminalTypes';

export async function openPtySession(
  client: ControlPlaneClient,
  payload: PtySessionCreatePayload,
): Promise<PtySessionInfo> {
  return client.request<PtySessionInfo>('/v1/control-plane/pty/sessions', {
    method: 'POST',
    body: payload,
  });
}

export async function listPtySessions(client: ControlPlaneClient): Promise<PtySessionInfo[]> {
  return client.request<PtySessionInfo[]>('/v1/control-plane/pty/sessions');
}

export async function getPtySession(
  client: ControlPlaneClient,
  sessionId: string,
): Promise<PtySessionInfo> {
  return client.request<PtySessionInfo>(
    `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function writePtyInput(
  client: ControlPlaneClient,
  sessionId: string,
  data: string,
): Promise<PtyInputResponse> {
  return client.request<PtyInputResponse>(
    `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}/input`,
    {
      method: 'POST',
      body: { data },
    },
  );
}

export async function resizePtySession(
  client: ControlPlaneClient,
  sessionId: string,
  cols: number,
  rows: number,
): Promise<PtySessionInfo> {
  return client.request<PtySessionInfo>(
    `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}/resize`,
    {
      method: 'POST',
      body: { cols, rows },
    },
  );
}

export async function interruptPtySession(
  client: ControlPlaneClient,
  sessionId: string,
): Promise<PtySessionInfo> {
  return client.request<PtySessionInfo>(
    `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}/interrupt`,
    {
      method: 'POST',
    },
  );
}

export async function readPtyOutput(
  client: ControlPlaneClient,
  sessionId: string,
  afterSeq = 0,
): Promise<PtyOutputResponse> {
  return client.request<PtyOutputResponse>(
    `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}/output?after_seq=${encodeURIComponent(String(afterSeq))}`,
  );
}

export async function closePtySession(
  client: ControlPlaneClient,
  sessionId: string,
  keepRunning: boolean,
): Promise<PtySessionInfo> {
  return client.request<PtySessionInfo>(
    `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}/close`,
    {
      method: 'POST',
      body: { keep_running: keepRunning },
    },
  );
}

export function buildPtyWebSocketUrl(
  sessionId: string,
  afterSeq = 0,
  baseUrl?: string,
): string {
  const path = `/v1/control-plane/pty/sessions/${encodeURIComponent(sessionId)}/ws?after_seq=${encodeURIComponent(String(afterSeq))}`;
  if (baseUrl && baseUrl.trim().length > 0) {
    const clean = baseUrl.trim().replace(/\/+$/, '');
    if (clean.startsWith('https://')) {
      return `wss://${clean.slice('https://'.length)}${path}`;
    }
    if (clean.startsWith('http://')) {
      return `ws://${clean.slice('http://'.length)}${path}`;
    }
    if (clean.startsWith('ws://') || clean.startsWith('wss://')) {
      return `${clean}${path}`;
    }
  }
  if (typeof window !== 'undefined' && window.location) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}${path}`;
  }
  return `ws://127.0.0.1:8000${path}`;
}

export interface StreamPtySseOptions {
  sessionId: string;
  afterSeq: number;
  token: string | null;
  signal: AbortSignal;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  onChunk: (chunk: PtyChunk) => void;
  onState: (session: PtySessionInfo) => void;
}

export async function streamPtySse(options: StreamPtySseOptions): Promise<void> {
  const baseUrl = (options.baseUrl ?? '').replace(/\/+$/, '');
  const fetchFn = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Last-Event-ID': String(options.afterSeq),
  };
  if (options.token && options.token.trim().length > 0) {
    headers.Authorization = `Bearer ${options.token.trim()}`;
  }

  const url = `${baseUrl}/v1/control-plane/pty/sessions/${encodeURIComponent(options.sessionId)}/stream?after_seq=${encodeURIComponent(String(options.afterSeq))}`;
  const response = await fetchFn(url, {
    method: 'GET',
    headers,
    signal: options.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    let parsedJson: unknown = null;
    if (text) {
      try {
        parsedJson = JSON.parse(text);
      } catch {
        parsedJson = null;
      }
    }
    const parsedErr = ApiErrorSchema.safeParse(parsedJson);
    throw new ControlPlaneApiError(
      response.status,
      parsedErr.success
        ? parsedErr.data
        : {
            code: response.status === 410 ? 'cursor_expired' : 'http_error',
            message: `Falha no stream PTY (${response.status})`,
            run_id: null,
            retryable: response.status >= 500,
          },
    );
  }

  const parser = createParser((event) => {
    if (event.type !== 'event') {
      return;
    }
    try {
      if (event.event === 'pty.chunk') {
        const chunk = JSON.parse(event.data) as PtyChunk;
        options.onChunk(chunk);
      } else if (event.event === 'pty.state') {
        const session = JSON.parse(event.data) as PtySessionInfo;
        options.onState(session);
      }
    } catch {
      // Ignora payload SSE malformado sem derrubar o stream
    }
  });

  if (!response.body || typeof response.body.getReader !== 'function') {
    const bodyText = await response.text();
    if (bodyText) {
      parser.feed(bodyText);
    }
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  try {
    for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
      if (chunk.value) {
        parser.feed(decoder.decode(chunk.value, { stream: true }));
      }
    }
    const tail = decoder.decode();
    if (tail) {
      parser.feed(tail);
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // Lock já liberado
    }
  }
}
