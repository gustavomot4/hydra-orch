import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createParser } from 'eventsource-parser';
import { Link } from 'react-router-dom';
import { Square } from 'lucide-react';
import { PromptComposer } from '@/feature/composer';
import { AttachmentDropzone, AttachmentItemView } from '@/feature/attachment';
import { DictationControl } from '@/feature/dictation';
import { clearComposerDraft } from '@/feature/composer/composerTypes';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { ControlPlaneApiError } from '@/type/controlPlane';
import { clearPendingSend, ConversationSnapshot, pendingMessage } from './conversationTypes';

const labels: Record<string, string> = {
  queued: 'Aguardando envio',
  running: 'Agente trabalhando…',
  stopping: 'Interrompendo…',
  completed: 'Resposta concluída',
  failed: 'Não foi possível concluir',
  cancelled: 'Interrompido',
};

export function ConversationPage({ conversationId }: { conversationId: string }) {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const lock = useAuthStore((s) => s.lock);
  const queryKey = ['control-plane', 'conversation', conversationId];
  const snapshot = useQuery({
    queryKey,
    queryFn: () =>
      client.request<ConversationSnapshot>(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}`,
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
  const sendingRef = useRef(false);
  const cursorRef = useRef(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const followOutputRef = useRef(true);
  const renderedSeqRef = useRef<number | null>(null);
  const data = snapshot.data;
  cursorRef.current = data?.last_seq ?? 0;

  useEffect(() => {
    if (data) {
      document.title = `${data.title} · Hydra`;
      headingRef.current?.focus();
    }
  }, [data?.id]);
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
  }, [data?.id]);
  useEffect(() => {
    if (
      data &&
      renderedSeqRef.current !== null &&
      renderedSeqRef.current !== data.last_seq &&
      followOutputRef.current
    )
      endRef.current?.scrollIntoView({ block: 'end' });
    if (data) renderedSeqRef.current = data.last_seq;
  }, [data?.last_seq]);
  useEffect(() => {
    const controller = new AbortController();
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      if (!refreshTimer)
        refreshTimer = setTimeout(() => {
          refreshTimer = undefined;
          void queryClient.invalidateQueries({
            queryKey: ['control-plane', 'conversation', conversationId],
          });
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
    };
    try {
      if (attachments.some((a) => !['local_ready', 'transferred'].includes(a.status)))
        throw new Error('Aguarde os anexos ou remova os que falharam.');
      await client.request(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/messages`,
        { method: 'POST', body: pendingMessage(conversationId, payload) },
      );
      setDraft('');
      followOutputRef.current = true;
      setAttachments([]);
      clearComposerDraft(conversationId);
      clearPendingSend(conversationId);
      await snapshot.refetch();
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
        </p>
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
                {data.executor === 'codex' ? 'Codex' : 'Claude Code'}
              </h2>
              {turn.response && (
                <div
                  className="whitespace-pre-wrap break-words leading-relaxed"
                  data-testid="agent-response"
                >
                  {turn.response}
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
