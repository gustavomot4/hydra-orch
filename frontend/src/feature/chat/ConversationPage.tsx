import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createParser } from 'eventsource-parser';
import { Link } from 'react-router-dom';
import { Square } from 'lucide-react';
import { PromptComposer } from '@/feature/composer';
import { AttachmentDropzone, AttachmentItemView } from '@/feature/attachment';
import { DictationControl } from '@/feature/dictation';
import { clearComposerDraft, SLASH_COMMANDS } from '@/feature/composer/composerTypes';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  clearPendingSend,
  ConversationSnapshot,
  pendingMessage,
  pendingSendKey,
  ConversationRoute,
  defaultRoute,
  routeSelection,
} from './conversationTypes';
import { ConversationRoutePicker } from './ConversationRoutePicker';
import { ConversationWorkflow, ExecutionMode } from './ConversationWorkflow';

const labels: Record<string, string> = {
  queued: 'Aguardando envio',
  running: 'Agente trabalhando…',
  stopping: 'Interrompendo…',
  completed: 'Resposta concluída',
  failed: 'Não foi possível concluir',
  cancelled: 'Interrompido',
};
// In an existing chat, workflow changes require the header's revisioned save.
const conversationCommands = SLASH_COMMANDS.filter((item) => item.command !== '/swarm');

export function ConversationPage({ conversationId }: { conversationId: string }) {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const lock = useAuthStore((s) => s.lock);
  const queryKey = ['control-plane', 'conversation', conversationId];
  const snapshot = useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      client.request<ConversationSnapshot>(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}`,
        { signal },
      ),
    refetchInterval: 2500,
    retry: false,
  });
  const [draft, setDraft] = useState('');
  const [attachments, setAttachments] = useState<AttachmentItemView[]>([]);
  const [sending, setSending] = useState(false);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [routeDraft, setRouteDraft] = useState<ConversationRoute | null>(null);
  const [routeReady, setRouteReady] = useState(true);
  const [savingRoute, setSavingRoute] = useState(false);
  const [workflowDraft, setWorkflowDraft] = useState<ExecutionMode>('single');
  const [autoDraft, setAutoDraft] = useState(false);
  const sendingRef = useRef(false);
  const cursorRef = useRef(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const followOutputRef = useRef(true);
  const renderedSeqRef = useRef<number | null>(null);
  const data = snapshot.data;
  const dataId = data?.id;
  const dataTitle = data?.title;
  const lastSeq = data?.last_seq;
  cursorRef.current = lastSeq ?? 0;

  useEffect(() => {
    if (dataId && dataTitle !== undefined) {
      document.title = `${dataTitle} · Hydra`;
      const layout = useLayoutStore.getState();
      const matching = Object.values(layout.tabs).filter(
        (t) => t.runId === dataId && t.title !== dataTitle,
      );
      if (matching.length)
        useLayoutStore.setState({
          tabs: Object.fromEntries(
            Object.entries(layout.tabs).map(([id, tab]) => [
              id,
              tab.runId === dataId ? { ...tab, title: dataTitle } : tab,
            ]),
          ),
        });
    }
  }, [dataId, dataTitle]);
  useEffect(() => {
    if (dataId) headingRef.current?.focus();
  }, [dataId]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  useEffect(() => {
    let parent = pageRef.current?.parentElement;
    while (parent && !/auto|scroll/.test(getComputedStyle(parent).overflowY))
      parent = parent.parentElement;
    if (!parent) return;
    const container = parent;
    const onScroll = () => {
      followOutputRef.current =
        container.scrollHeight - container.scrollTop - container.clientHeight < 160;
    };
    container.addEventListener('scroll', onScroll, { passive: true });
    return () => container.removeEventListener('scroll', onScroll);
  }, [dataId]);
  useEffect(() => {
    if (
      lastSeq !== undefined &&
      renderedSeqRef.current !== null &&
      renderedSeqRef.current !== lastSeq &&
      followOutputRef.current
    )
      endRef.current?.scrollIntoView({ block: 'end' });
    if (lastSeq !== undefined) renderedSeqRef.current = lastSeq;
  }, [lastSeq]);
  useEffect(() => {
    const controller = new AbortController();
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      if (!refreshTimer)
        refreshTimer = setTimeout(() => {
          refreshTimer = undefined;
          void queryClient.invalidateQueries(
            {
              queryKey: ['control-plane', 'conversation', conversationId],
            },
            { cancelRefetch: false },
          );
        }, 100);
    };
    async function connect() {
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(
            `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/events`,
            {
              headers: {
                Authorization: `Bearer ${token}`,
                'Last-Event-ID': String(cursorRef.current),
              },
              signal: controller.signal,
            },
          );
          if (response.status === 401) {
            lock('Conecte-se novamente para continuar a conversa.');
            return;
          }
          if (!response.ok || !response.body) throw new Error('stream');
          setConnected(true);
          refresh();
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          const parser = createParser((event) => {
            if (event.type === 'event') refresh();
          });
          try {
            while (!controller.signal.aborted) {
              const { done, value } = await reader.read();
              if (done) break;
              parser.feed(decoder.decode(value, { stream: true }));
            }
          } finally {
            reader.releaseLock();
          }
        } catch {
          /* The durable snapshot remains visible during reconnect. */
        }
        if (!controller.signal.aborted) {
          setConnected(false);
          await new Promise<void>((resolve) => {
            const finish = () => {
              clearTimeout(timer);
              controller.signal.removeEventListener('abort', finish);
              resolve();
            };
            const timer = setTimeout(finish, 1000);
            controller.signal.addEventListener('abort', finish, { once: true });
          });
        }
      }
    }
    void connect();
    return () => {
      controller.abort();
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [conversationId, token, queryClient, lock]);

  async function send() {
    if (sendingRef.current || !data || !draft.trim()) return;
    sendingRef.current = true;
    setSending(true);
    setError(null);
    const payload = {
      content: draft.trim(),
      expected_last_seq: data.last_seq,
      draft_session_id: conversationId,
      attachment_ids: attachments.map((a) => a.attachment_id).filter(Boolean),
      ...(data.route_revision !== undefined
        ? { expected_route_revision: data.route_revision }
        : {}),
    };
    try {
      if (attachments.some((a) => !['local_ready', 'transferred'].includes(a.status)))
        throw new Error('Aguarde os anexos ou remova os que falharam.');
      const accepted = await client.request<{ turn_id: string; seq: number }>(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/messages`,
        { method: 'POST', body: pendingMessage(conversationId, payload) },
      );
      setDraft('');
      followOutputRef.current = true;
      setAttachments([]);
      clearComposerDraft(conversationId);
      clearPendingSend(conversationId);
      // A persisted send is usable immediately. An overlapping background read
      // must neither keep the composer disabled nor hide the accepted message.
      await queryClient.cancelQueries({ queryKey });
      queryClient.setQueryData<ConversationSnapshot>(queryKey, (previous) => {
        if (!previous || previous.turns.some((t) => t.id === accepted.turn_id)) return previous;
        return {
          ...previous,
          last_seq: Math.max(previous.last_seq, accepted.seq),
          turns: [
            ...previous.turns,
            {
              id: accepted.turn_id,
              ordinal: previous.turns.length + 1,
              content: payload.content,
              response: '',
              state: 'queued',
              error: null,
              diff: '',
              attachments: attachments.map((a) => ({
                filename: a.filename,
                attachment_id: a.attachment_id!,
              })),
              route: previous.route,
              route_revision: previous.route_revision,
              execution_mode: previous.execution_mode,
            },
          ],
        };
      });
      void snapshot.refetch({ cancelRefetch: false });
      requestAnimationFrame(() => pageRef.current?.querySelector('textarea')?.focus());
    } catch (err) {
      if (err instanceof ControlPlaneApiError && err.status === 409)
        clearPendingSend(conversationId);
      setError(
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : err instanceof Error
            ? err.message
            : 'Não foi possível enviar. Tente novamente.',
      );
      void snapshot.refetch();
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  async function cancel(turnId: string) {
    setCancelling(turnId);
    setError(null);
    try {
      await client.request(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(turnId)}/cancel`,
        { method: 'POST' },
      );
      await snapshot.refetch();
      requestAnimationFrame(() => pageRef.current?.querySelector('textarea')?.focus());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Não foi possível interromper. Tente novamente.',
      );
    } finally {
      setCancelling(null);
    }
  }

  async function saveRoute() {
    if (!data || !routeDraft || !routeReady || savingRoute) return;
    setSavingRoute(true);
    setError(null);
    const body = {
      route: routeSelection(routeDraft),
      expected_revision: data.route_revision ?? 0,
      ...(data.execution_mode !== undefined
        ? { execution_mode: workflowDraft, auto_route: autoDraft }
        : {}),
    };
    try {
      await client.request(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/route`,
        {
          method: 'PATCH',
          body: { ...body, idempotency_key: pendingSendKey(`route:${conversationId}`, body) },
        },
      );
      clearPendingSend(`route:${conversationId}`);
      await snapshot.refetch();
      setRouteDraft(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Não foi possível mudar a configuração.');
      void snapshot.refetch();
    } finally {
      setSavingRoute(false);
    }
  }

  if (!data)
    return (
      <div className="p-6">
        <h1 className="mb-3 text-xl font-semibold">Conversa</h1>
        {snapshot.isError ? (
          <div role="alert">
            Não foi possível abrir a conversa.{' '}
            <button className="min-h-11 underline" onClick={() => void snapshot.refetch()}>
              Tentar novamente
            </button>
          </div>
        ) : (
          <p role="status">Carregando conversa…</p>
        )}
      </div>
    );
  const active = data.turns.find((t) => t.state === 'running' || t.state === 'stopping');
  return (
    <div
      ref={pageRef}
      className="mx-auto w-full max-w-3xl px-4 py-6 text-[#E8E8E8] sm:px-6"
      data-testid="conversation-page"
    >
      <header className="mb-6 border-b border-[#303030] pb-4">
        {data.project_name && <p className="mb-2 text-sm text-[#D1D1D1]">{data.project_name}</p>}
        <h1 ref={headingRef} tabIndex={-1} className="break-words text-xl font-semibold">
          {data.title}
        </h1>
        <p className="mt-2 text-sm text-[#D1D1D1]">
          {data.executor === 'codex' ? 'Codex' : 'Claude Code'} ·{' '}
          {data.access_mode === 'read-only' ? 'Somente leitura' : 'Edições em cópia isolada'}
          {data.route?.target_ref && (
            <>
              {' '}
              · {data.route.connection_mode === 'omniroute' ? 'OmniRoute · ' : ''}
              {data.route.target_ref}
            </>
          )}
        </p>
        {data.route_revision !== undefined && (
          <button
            type="button"
            className="mt-2 min-h-11 rounded-lg border border-[#666] px-3 text-sm"
            aria-expanded={Boolean(routeDraft)}
            onClick={() => {
              setWorkflowDraft(data.execution_mode ?? 'single');
              setAutoDraft(data.auto_route ?? false);
              setRouteDraft(
                routeDraft
                  ? null
                  : routeSelection(data.route ?? defaultRoute(data.executor as 'codex' | 'claude')),
              );
            }}
          >
            Trocar modelo ou combo
          </button>
        )}
        <Link
          className="ml-2 mt-2 inline-flex min-h-11 items-center rounded-lg border border-[#666] px-3 text-sm"
          to={`/agentes?chat=${encodeURIComponent(conversationId)}`}
        >
          Ver agentes
        </Link>
        {routeDraft && (
          <div className="mt-3 rounded-lg border border-[#666] p-3">
            <p className="mb-3 text-sm text-[#D1D1D1]">
              A mesma conversa continua com seus arquivos e histórico. A escolha vale para os
              próximos envios; mensagens já na fila mantêm a configuração anterior.
            </p>
            <label htmlFor="conversation-agent" className="mb-1 block text-sm">
              Agente
            </label>
            <select
              id="conversation-agent"
              className="mb-3 min-h-11 w-full rounded-lg border border-[#666] bg-[#1C1C1C] px-3 text-sm"
              disabled={savingRoute}
              value={routeDraft.executor}
              onChange={(e) => setRouteDraft(defaultRoute(e.target.value as 'codex' | 'claude'))}
            >
              <option value="codex">Codex</option>
              <option value="claude">Claude Code</option>
            </select>
            <ConversationRoutePicker
              value={routeDraft}
              onChange={setRouteDraft}
              onReadyChange={setRouteReady}
              disabled={savingRoute}
            />
            {data.execution_mode !== undefined && (
              <ConversationWorkflow
                mode={workflowDraft}
                automatic={autoDraft}
                onChange={(mode, automatic) => {
                  setWorkflowDraft(mode);
                  setAutoDraft(automatic);
                }}
                disabled={savingRoute}
              />
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="min-h-11 rounded border border-[#666] px-3 text-sm disabled:opacity-50"
                disabled={savingRoute || !routeReady}
                onClick={() => void saveRoute()}
              >
                {savingRoute ? 'Salvando…' : 'Usar nos próximos envios'}
              </button>
              <button
                type="button"
                className="min-h-11 rounded border border-[#666] px-3 text-sm"
                disabled={savingRoute}
                onClick={() => setRouteDraft(null)}
              >
                Cancelar troca
              </button>
            </div>
          </div>
        )}
        {!connected && (
          <p role="status" className="mt-2 text-sm text-[#D1D1D1]">
            Reconectando… Suas mensagens estão salvas.
          </p>
        )}
        {data.legacy_run_id && (
          <Link
            className="mt-2 inline-block min-h-11 py-2 underline"
            to={`/chat/${data.legacy_run_id}`}
          >
            Ver execução anterior
          </Link>
        )}
      </header>
      <div className="space-y-6" aria-label="Mensagens da conversa">
        {data.turns.map((turn) => (
          <section
            key={turn.id}
            data-testid={`conversation-turn-${turn.ordinal}`}
            className="min-w-0 space-y-3"
          >
            <div className="ml-auto max-w-full rounded-2xl border border-[#666] bg-[#282828] px-4 py-3 sm:max-w-[90%]">
              <h2 className="mb-1 text-sm font-semibold text-[#D1D1D1]">Você</h2>
              <p className="whitespace-pre-wrap break-words">{turn.content}</p>
              {turn.attachments.map((a) => (
                <p className="mt-2 break-words text-sm text-[#D1D1D1]" key={a.attachment_id}>
                  Anexo: {a.filename}
                </p>
              ))}
            </div>
            <div className="min-w-0 px-1 py-2">
              <h2 className="mb-2 text-sm font-semibold text-[#D1D1D1]">
                {(turn.route?.executor ?? data.executor) === 'codex' ? 'Codex' : 'Claude Code'}
                {turn.route?.target_ref && <> · {turn.route.target_ref}</>}
              </h2>
              {turn.response && (
                <div
                  className="whitespace-pre-wrap break-words leading-relaxed"
                  data-testid="agent-response"
                >
                  {turn.response}
                </div>
              )}
              {turn.coordination?.plan && (
                <div className="my-3 rounded-lg border border-[#666] p-3 text-sm">
                  <h3 className="font-semibold">Tarefas deste pedido</h3>
                  <p className="my-2 text-[#D1D1D1]">{turn.coordination.plan.objective}</p>
                  <ol className="list-decimal space-y-3 pl-5">
                    {turn.coordination.plan.tasks.map((task) => {
                      const progress = turn.coordination?.tasks?.[task.id];
                      return (
                        <li key={task.id}>
                          <p>
                            {task.title} ·{' '}
                            {(
                              {
                                starting: 'Iniciando',
                                accepted: 'Revisão aprovada',
                                rejected: 'Revisão recusada',
                                failed: 'Verificação falhou',
                              } as Record<string, string>
                            )[progress?.state ?? ''] ?? 'Planejada'}
                          </p>
                          <p className="break-words text-[#D1D1D1]">{task.paths.join(', ')}</p>
                          {progress?.route?.target_ref && (
                            <p>Destino: {progress.route.target_ref}</p>
                          )}
                          {progress?.reason && (
                            <p className="mt-1 text-[#D1D1D1]">{progress.reason}</p>
                          )}
                          {progress?.review && (
                            <p className="mt-1 text-[#D1D1D1]">Revisão: {progress.review}</p>
                          )}
                        </li>
                      );
                    })}
                  </ol>
                  {turn.coordination.run_id && turn.coordination.phase && (
                    <Link
                      className="mt-3 inline-block min-h-11 py-2 underline"
                      to={`/chat/${turn.coordination.run_id}`}
                    >
                      Ver execução e verificações
                    </Link>
                  )}
                </div>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <p role="status" className="text-sm text-[#D1D1D1]">
                  {labels[turn.state]}
                </p>
                {['queued', 'running', 'stopping'].includes(turn.state) && (
                  <button
                    className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-[#666] px-3 text-sm"
                    disabled={turn.state === 'stopping' || cancelling === turn.id}
                    onClick={() => void cancel(turn.id)}
                  >
                    <Square size={14} aria-hidden="true" />
                    {turn.state === 'queued'
                      ? 'Cancelar envio'
                      : turn.state === 'stopping'
                        ? 'Interrompendo…'
                        : 'Parar'}
                  </button>
                )}
              </div>
              {turn.error && (
                <p
                  role="alert"
                  className="mt-2 whitespace-pre-wrap break-words text-sm text-[#FCA5A5]"
                >
                  {turn.error}
                </p>
              )}
              {data.tools.some((t) => t.turn_id === turn.id) && (
                <details className="mt-3 text-sm text-[#D1D1D1]">
                  <summary className="w-fit cursor-pointer py-2">Atividade do agente</summary>
                  {data.tools
                    .filter((t) => t.turn_id === turn.id)
                    .map((tool) => (
                      <div key={tool.seq} className="my-2">
                        <p>{tool.payload.tool}</p>
                        {tool.payload.detail && (
                          <pre className="whitespace-pre-wrap break-all text-xs">
                            {tool.payload.detail}
                          </pre>
                        )}
                      </div>
                    ))}
                </details>
              )}
              {turn.diff && (
                <details className="mt-3 text-sm">
                  <summary className="w-fit cursor-pointer py-2">Revisar alterações</summary>
                  <p className="my-2 text-[#D1D1D1]">
                    Alterações preservadas na cópia desta conversa, aguardando revisão.
                  </p>
                  <pre className="whitespace-pre-wrap break-all rounded-lg border border-[#666] p-3 text-xs">
                    {turn.diff}
                  </pre>
                </details>
              )}
            </div>
          </section>
        ))}
      </div>
      <div className="mt-6 border-t border-[#303030] pt-4">
        {active && (
          <p className="mb-3 text-sm text-[#D1D1D1]">
            Você pode enviar outra mensagem. Ela será respondida em seguida.
          </p>
        )}
        <AttachmentDropzone
          sessionId={conversationId}
          workspaceId={data.project_id}
          hostId="local"
          attachments={attachments}
          onAttachmentsChange={setAttachments}
          compact
        >
          <PromptComposer
            draft={draft}
            onDraftChange={setDraft}
            sessionKey={conversationId}
            hideModeSelector
            slashCommands={conversationCommands}
            visibleTextareaLabel
            textareaAriaLabel="Sua mensagem"
            placeholder="Continue a conversa…"
            onSubmit={() => void send()}
            isSubmitting={sending}
            submitLabel="Enviar"
            renderAttachControl={null}
            renderDictationControl={
              <details className="text-sm text-[#D1D1D1]">
                <summary className="flex min-h-8 cursor-pointer items-center px-2 [@media(pointer:coarse)]:min-h-[44px]">
                  Ditado por voz
                </summary>
                <DictationControl
                  onInsertTranscript={(text) =>
                    setDraft((current) =>
                      current.trim() ? `${current.trimEnd()} ${text.trim()}` : text.trim(),
                    )
                  }
                />
              </details>
            }
          />
        </AttachmentDropzone>
        {error && (
          <div
            ref={errorRef}
            tabIndex={-1}
            role="alert"
            className="mt-3 rounded-lg border border-[#FCA5A5] p-3 text-sm text-[#FCA5A5]"
          >
            {error}
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
