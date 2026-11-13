import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Mic,
  MicOff,
  RefreshCw,
  Square,
  Trash2,
} from 'lucide-react';
import { StatusBadge, StatusKind } from '@/component/StatusBadge';
import {
  DICTATION_NOTICE,
  DICTATION_STATE_LABELS,
  DictationSpeechAdapter,
  DictationState,
  createBrowserSpeechAdapter,
  formatDictationErrorMessage,
} from './dictationTypes';

export interface DictationControlProps {
  onInsertTranscript: (editedText: string) => void;
  speechAdapter?: DictationSpeechAdapter;
  lang?: string;
  disabled?: boolean;
  initialDraft?: string;
  className?: string;
}

function mapStateToBadge(state: DictationState): { status: StatusKind; label: string } {
  switch (state) {
    case 'idle':
      return { status: 'queued', label: DICTATION_STATE_LABELS.idle };
    case 'listening':
      return { status: 'running', label: DICTATION_STATE_LABELS.listening };
    case 'permission_denied':
      return { status: 'failed', label: 'Permissão negada' };
    case 'unavailable':
      return { status: 'unavailable', label: 'Indisponível' };
    case 'draft_ready':
      return { status: 'ready', label: DICTATION_STATE_LABELS.draft_ready };
    case 'error':
      return { status: 'failed', label: 'Erro' };
  }
}

export function DictationControl({
  onInsertTranscript,
  speechAdapter,
  lang = 'pt-BR',
  disabled = false,
  initialDraft = '',
  className = '',
}: DictationControlProps) {
  const previewId = useId();
  const activeAdapter = useMemo(
    () => speechAdapter ?? createBrowserSpeechAdapter(),
    [speechAdapter],
  );

  const supported = activeAdapter.isSupported();
  const [state, setState] = useState<DictationState>(() => {
    if (!supported) {
      return 'unavailable';
    }
    return initialDraft.trim().length > 0 ? 'draft_ready' : 'idle';
  });
  const [draftText, setDraftText] = useState(initialDraft);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const stateRef = useRef<DictationState>(state);
  stateRef.current = state;
  const draftTextRef = useRef(draftText);
  draftTextRef.current = draftText;
  const committedTextRef = useRef(initialDraft.trim());
  const sessionTokenRef = useRef(0);

  useEffect(() => {
    const isNowSupported = activeAdapter.isSupported();
    if (!isNowSupported) {
      setState('unavailable');
      return;
    }
    if (stateRef.current === 'unavailable') {
      setState(draftTextRef.current.trim().length > 0 ? 'draft_ready' : 'idle');
    }
  }, [activeAdapter]);

  useEffect(() => {
    return () => {
      sessionTokenRef.current += 1;
      if (stateRef.current === 'listening') {
        activeAdapter.abort?.();
        if (!activeAdapter.abort) {
          activeAdapter.stop();
        }
      }
    };
  }, [activeAdapter]);

  const startListening = useCallback(() => {
    if (disabled) {
      return;
    }
    if (!activeAdapter.isSupported()) {
      setState('unavailable');
      setErrorMessage(DICTATION_STATE_LABELS.unavailable);
      return;
    }

    sessionTokenRef.current += 1;
    const token = sessionTokenRef.current;
    committedTextRef.current = draftTextRef.current.trim();
    setErrorMessage(null);
    setState('listening');

    const handleFailure = (code: 'not-allowed' | 'service-not-allowed' | 'unavailable' | 'aborted' | 'audio-capture' | 'no-speech' | 'network' | 'unknown', message?: string) => {
      if (sessionTokenRef.current !== token) {
        return;
      }
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        setState('permission_denied');
        setErrorMessage(DICTATION_STATE_LABELS.permission_denied);
        return;
      }
      if (code === 'unavailable') {
        setState('unavailable');
        setErrorMessage(DICTATION_STATE_LABELS.unavailable);
        return;
      }
      if (code === 'aborted') {
        setState(draftTextRef.current.trim().length > 0 ? 'draft_ready' : 'idle');
        return;
      }
      setState('error');
      setErrorMessage(formatDictationErrorMessage(code, message));
    };

    try {
      const maybePromise = activeAdapter.start(
        {
          onStart: () => {
            if (sessionTokenRef.current !== token) {
              return;
            }
            setState('listening');
          },
          onResult: (result) => {
            if (sessionTokenRef.current !== token) {
              return;
            }
            const cleanPiece = result.transcript.trim();
            if (result.replace) {
              if (result.isFinal) {
                committedTextRef.current = cleanPiece;
              }
              draftTextRef.current = result.transcript;
              setDraftText(result.transcript);
              return;
            }

            if (result.isFinal) {
              const nextCommitted = [committedTextRef.current, cleanPiece]
                .filter((segment) => segment.length > 0)
                .join(' ');
              committedTextRef.current = nextCommitted;
              draftTextRef.current = nextCommitted;
              setDraftText(nextCommitted);
            } else {
              const preview = [committedTextRef.current, cleanPiece]
                .filter((segment) => segment.length > 0)
                .join(' ');
              draftTextRef.current = preview;
              setDraftText(preview);
            }
          },
          onError: (err) => {
            handleFailure(err.code, err.message);
          },
          onEnd: () => {
            if (sessionTokenRef.current !== token) {
              return;
            }
            if (stateRef.current === 'listening') {
              setState(
                draftTextRef.current.trim().length > 0 ? 'draft_ready' : 'idle',
              );
            }
          },
        },
        { lang },
      );

      if (maybePromise && typeof (maybePromise as Promise<void>).then === 'function') {
        void (maybePromise as Promise<void>).catch((err: unknown) => {
          const rawName = err instanceof Error ? err.name : '';
          const isPerm =
            rawName === 'NotAllowedError' ||
            rawName === 'PermissionDeniedError' ||
            rawName === 'SecurityError';
          handleFailure(
            isPerm ? 'not-allowed' : 'unknown',
            err instanceof Error ? err.message : undefined,
          );
        });
      }
    } catch (err) {
      const rawName = err instanceof Error ? err.name : '';
      const isPerm =
        rawName === 'NotAllowedError' ||
        rawName === 'PermissionDeniedError' ||
        rawName === 'SecurityError';
      handleFailure(
        isPerm ? 'not-allowed' : 'unknown',
        err instanceof Error ? err.message : undefined,
      );
    }
  }, [activeAdapter, disabled, lang]);

  const handleStop = useCallback(() => {
    sessionTokenRef.current += 1;
    activeAdapter.stop();
    setState(draftTextRef.current.trim().length > 0 ? 'draft_ready' : 'idle');
  }, [activeAdapter]);

  const handleDiscard = useCallback(() => {
    sessionTokenRef.current += 1;
    if (stateRef.current === 'listening') {
      if (activeAdapter.abort) {
        activeAdapter.abort();
      } else {
        activeAdapter.stop();
      }
    }
    committedTextRef.current = '';
    draftTextRef.current = '';
    setDraftText('');
    setErrorMessage(null);
    setState(activeAdapter.isSupported() ? 'idle' : 'unavailable');
  }, [activeAdapter]);

  const handleInsert = useCallback(() => {
    if (draftTextRef.current.trim().length === 0) {
      return;
    }
    sessionTokenRef.current += 1;
    if (stateRef.current === 'listening') {
      activeAdapter.stop();
    }
    const textToInsert = draftTextRef.current;
    onInsertTranscript(textToInsert);
    committedTextRef.current = '';
    draftTextRef.current = '';
    setDraftText('');
    setErrorMessage(null);
    setState(activeAdapter.isSupported() ? 'idle' : 'unavailable');
  }, [activeAdapter, onInsertTranscript]);

  const badge = mapStateToBadge(state);
  const showPreview = state === 'draft_ready' || draftText.length > 0;

  return (
    <section
      aria-label="Controle de ditado por voz"
      data-testid="dictation-control"
      data-dictation-state={state}
      className={`rounded-2xl border border-[#303030] bg-[#1C1C1C] p-3 text-xs text-[#E8E8E8] ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 font-medium text-[#E8E8E8]">
            {state === 'unavailable' || state === 'permission_denied' ? (
              <MicOff aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
            ) : (
              <Mic aria-hidden="true" className="h-3.5 w-3.5 text-[#E8E8E8]" />
            )}
            <span>Ditado por voz</span>
          </span>

          <StatusBadge status={badge.status} labelOverride={badge.label} compact />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {state === 'listening' ? (
            <button
              type="button"
              onClick={handleStop}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#3B82F6]/50 bg-[#3B82F6]/15 px-3 py-1.5 text-xs font-medium text-[#93C5FD] transition-colors hover:bg-[#3B82F6]/25"
            >
              <Square aria-hidden="true" className="h-3 w-3" />
              <span>Parar ditado</span>
            </button>
          ) : state === 'permission_denied' || state === 'error' ? (
            <button
              type="button"
              disabled={disabled}
              onClick={startListening}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs font-medium text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Tentar novamente</span>
            </button>
          ) : state === 'unavailable' ? (
            <button
              type="button"
              disabled
              className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#969696] opacity-70"
            >
              <MicOff aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Ditado indisponível</span>
            </button>
          ) : (
            <button
              type="button"
              disabled={disabled}
              onClick={startListening}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs font-medium text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Mic aria-hidden="true" className="h-3.5 w-3.5 text-[#969696]" />
              <span>Iniciar ditado</span>
            </button>
          )}
        </div>
      </div>

      <p
        data-testid="dictation-mode-notice"
        className="mt-1.5 text-[11px] text-[#969696]"
      >
        {DICTATION_NOTICE}
      </p>

      {state === 'unavailable' ? (
        <div
          role="status"
          data-testid="dictation-unavailable-notice"
          className="mt-2.5 rounded-xl border border-[#303030] bg-[#141414] px-3 py-2 text-xs text-[#969696]"
        >
          {DICTATION_STATE_LABELS.unavailable}
        </div>
      ) : null}

      {(state === 'permission_denied' || state === 'error') && errorMessage ? (
        <div
          role="alert"
          data-testid="dictation-error-notice"
          className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
        >
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            disabled={disabled}
            onClick={startListening}
            className="shrink-0 rounded-md border border-[#EF4444]/40 bg-[#202020] px-2.5 py-1 text-[11px] font-medium text-[#E8E8E8] hover:bg-[#282828]"
          >
            Tentar novamente
          </button>
        </div>
      ) : null}

      {showPreview ? (
        <div
          data-testid="dictation-draft-preview"
          className="mt-3 space-y-2 rounded-xl border border-[#303030] bg-[#141414] p-3"
        >
          <div className="flex items-center justify-between gap-2">
            <label
              htmlFor={previewId}
              className="text-xs font-medium text-[#E8E8E8]"
            >
              Rascunho revisável do ditado
            </label>
            <span className="text-[11px] text-[#969696]">
              Revise antes de inserir — não envia automaticamente
            </span>
          </div>

          <textarea
            id={previewId}
            rows={3}
            value={draftText}
            onChange={(event) => {
              const nextValue = event.target.value;
              committedTextRef.current = nextValue.trim();
              draftTextRef.current = nextValue;
              setDraftText(nextValue);
            }}
            placeholder="O texto transcrito aparecerá aqui para revisão..."
            className="w-full resize-y rounded-lg border border-[#303030] bg-[#202020] p-2.5 text-sm text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
          />

          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleDiscard}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#E8E8E8]"
            >
              <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Descartar</span>
            </button>

            <button
              type="button"
              disabled={draftText.trim().length === 0}
              onClick={handleInsert}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Check aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Inserir no rascunho</span>
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
