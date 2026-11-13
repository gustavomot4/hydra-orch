import { useRef, useState } from 'react';
import { Check, Clock, MessageSquareWarning, ShieldAlert, X } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  createIdempotencyKey,
  HitlRequestItem,
  HitlRespondPayload,
} from './chatTypes';

export interface HitlInlineCardProps {
  runId: string;
  requests: HitlRequestItem[];
  actor?: string;
  client?: ControlPlaneClient;
  onResponded?: (updated: HitlRequestItem) => void;
}

function formatIsoBrief(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function HitlInlineCard({
  runId,
  requests,
  actor,
  client,
  onResponded,
}: HitlInlineCardProps) {
  const defaultClient = useControlPlaneClient();
  const activeClient = client ?? defaultClient;
  const principalId = useAuthStore((s) => s.principalId) ?? 'operator';
  const effectiveActor = actor ?? principalId;

  const [draftsById, setDraftsById] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [errorById, setErrorById] = useState<Record<string, string>>({});
  const inFlightRef = useRef<Set<string>>(new Set());

  const pendingRequests = requests.filter((req) => req.state === 'pending');
  const resolvedRequests = requests.filter((req) => req.state !== 'pending');

  if (requests.length === 0) {
    return null;
  }

  async function handleRespond(req: HitlRequestItem, approved: boolean) {
    if (inFlightRef.current.has(req.request_id) || submittingId === req.request_id) {
      return;
    }

    const rawText = (draftsById[req.request_id] ?? '').trim();
    const responseText =
      rawText.length > 0
        ? rawText
        : req.kind === 'needs_approval'
          ? approved
            ? 'Aprovado pelo operador'
            : 'Recusado pelo operador'
          : '';

    if (responseText.length === 0) {
      setErrorById((prev) => ({
        ...prev,
        [req.request_id]: 'Informe uma resposta antes de enviar.',
      }));
      return;
    }

    inFlightRef.current.add(req.request_id);
    setSubmittingId(req.request_id);
    setErrorById((prev) => {
      const next = { ...prev };
      delete next[req.request_id];
      return next;
    });

    const idempotencyKey = createIdempotencyKey('hitl-resp');
    const payload: HitlRespondPayload = {
      response: responseText,
      actor: effectiveActor,
      expected_revision: req.revision,
      approved,
    };

    try {
      const updated = await activeClient.request<HitlRequestItem>(
        `/v1/control-plane/runs/${encodeURIComponent(runId)}/interventions/${encodeURIComponent(req.request_id)}/response`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey },
          body: payload,
        },
      );
      setDraftsById((prev) => {
        const next = { ...prev };
        delete next[req.request_id];
        return next;
      });
      onResponded?.(updated);
    } catch (err) {
      const msg =
        err instanceof ControlPlaneApiError
          ? err.payload.message
          : err instanceof Error
            ? err.message
            : 'Falha ao enviar resposta de intervenção HITL.';
      setErrorById((prev) => ({ ...prev, [req.request_id]: msg }));
    } finally {
      inFlightRef.current.delete(req.request_id);
      setSubmittingId((curr) => (curr === req.request_id ? null : curr));
    }
  }

  return (
    <section
      aria-label="Intervenções humanas (HITL)"
      data-testid="hitl-inline-section"
      className="space-y-3"
    >
      {pendingRequests.map((req) => {
        const isSubmitting = submittingId === req.request_id;
        const draftValue = draftsById[req.request_id] ?? '';
        const errorMessage = errorById[req.request_id];

        return (
          <div
            key={req.request_id}
            data-testid={`hitl-card-${req.request_id}`}
            data-hitl-state={req.state}
            className="rounded-xl border border-[#F59E0B]/45 bg-[#202020] p-4 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                {req.kind === 'needs_approval' ? (
                  <ShieldAlert aria-hidden="true" className="h-4 w-4 text-[#FCD34D]" />
                ) : (
                  <MessageSquareWarning aria-hidden="true" className="h-4 w-4 text-[#FCD34D]" />
                )}
                <span className="text-xs font-semibold uppercase tracking-wide text-[#FCD34D]">
                  {req.kind === 'needs_approval'
                    ? 'Aprovação humana necessária'
                    : 'Contexto humano necessário'}
                </span>
                {req.task_id ? (
                  <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]">
                    {req.task_id}
                  </span>
                ) : null}
              </div>

              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[#969696]">
                  <Clock aria-hidden="true" className="h-3 w-3" />
                  Prazo: {formatIsoBrief(req.deadline)}
                </span>
                <StatusBadge status="waiting" labelOverride="Pendente" compact />
              </div>
            </div>

            <p className="mt-2.5 text-sm text-[#E8E8E8]">{req.question}</p>

            <div className="mt-3 space-y-2">
              <label htmlFor={`hitl-input-${req.request_id}`} className="sr-only">
                Resposta da intervenção HITL
              </label>
              <textarea
                id={`hitl-input-${req.request_id}`}
                rows={2}
                disabled={isSubmitting}
                value={draftValue}
                onChange={(e) =>
                  setDraftsById((prev) => ({
                    ...prev,
                    [req.request_id]: e.target.value,
                  }))
                }
                placeholder={
                  req.kind === 'needs_approval'
                    ? 'Justificativa ou instrução adicional (opcional ao aprovar/recusar)...'
                    : 'Digite o contexto solicitado pelo coordenador...'
                }
                className="w-full resize-none rounded-lg border border-[#303030] bg-[#141414] px-3 py-2 text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none disabled:opacity-60"
              />

              {errorMessage ? (
                <p
                  role="alert"
                  className="rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1.5 text-xs text-[#FCA5A5]"
                >
                  {errorMessage}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-[#969696]">
                  rev.{req.revision} · id {req.request_id}
                </span>

                <div className="flex items-center gap-2">
                  {req.kind === 'needs_approval' ? (
                    <>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handleRespond(req, false)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-1.5 text-xs font-medium text-[#FCA5A5] transition-colors hover:bg-[#EF4444]/20 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <X aria-hidden="true" className="h-3.5 w-3.5" />
                        <span>{isSubmitting ? 'Enviando...' : 'Recusar'}</span>
                      </button>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handleRespond(req, true)}
                        className="inline-flex items-center gap-1 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Check aria-hidden="true" className="h-3.5 w-3.5" />
                        <span>{isSubmitting ? 'Enviando...' : 'Aprovar'}</span>
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => void handleRespond(req, true)}
                      className="inline-flex items-center gap-1 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Check aria-hidden="true" className="h-3.5 w-3.5" />
                      <span>{isSubmitting ? 'Enviando...' : 'Enviar resposta'}</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {resolvedRequests.length > 0 ? (
        <div className="space-y-1.5">
          {resolvedRequests.map((req) => (
            <div
              key={req.request_id}
              data-testid={`hitl-resolved-${req.request_id}`}
              data-hitl-state={req.state}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#303030] bg-[#181818] px-3 py-2 text-xs text-[#969696]"
            >
              <div className="min-w-0 flex-1">
                <span className="font-medium text-[#E8E8E8]">{req.question}</span>
                {req.response ? (
                  <span className="ml-2 text-[#969696]">→ {req.response}</span>
                ) : null}
              </div>
              <StatusBadge
                status={req.state === 'answered' ? 'accepted' : req.state === 'denied' ? 'failed' : 'cancelled'}
                labelOverride={
                  req.state === 'answered'
                    ? 'Respondido'
                    : req.state === 'denied'
                      ? 'Recusado'
                      : req.state === 'expired'
                        ? 'Expirado'
                        : 'Cancelado'
                }
                compact
              />
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
