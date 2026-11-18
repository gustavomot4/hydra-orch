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
  iconOnlyMobile?: boolean;
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
  iconOnlyMobile = false,
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

    const handleFailure = (
      code:
        | 'not-allowed'
        | 'service-not-allowed'
        | 'unavailable'
        | 'aborted'
        | 'audio-capture'
        | 'no-speech'
        | 'network'
        | 'unknown',
      message?: string,
    ) => {
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
              setState(draftTextRef.current.trim().length > 0 ? 'draft_ready' : 'idle');
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
  const labelVisibilityClass = iconOnlyMobile ? 'max-md:sr-only' : '';

  return (
    <section
      aria-label="Controle de ditado por voz"
      data-testid="dictation-control"
      data-dictation-state={state}
      className={`rounded-2xl border border-[var(--border)] bg-[var(--bg-sidebar)] p-3 text-xs text-[var(--text-primary)] ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 font-medium text-[var(--text-primary)]">
            {state === 'unavailable' || state === 'permission_denied' ? (
              <MicOff aria-hidden="true" className="h-3.5 w-3.5 text-[var(--text-muted)]" />
            ) : (
              <Mic aria-hidden="true" className="h-3.5 w-3.5 text-[var(--text-primary)]" />
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
              aria-label={iconOnlyMobile ? 'Parar ditado' : undefined}
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1.5 rounded-lg border border-[var(--status-info)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--status-info)] transition-colors hover:bg-[var(--bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <Square aria-hidden="true" className="h-3 w-3" />
              <span className={labelVisibilityClass}>Parar ditado</span>
            </button>
          ) : state === 'permission_denied' || state === 'error' ? (
            <button
              type="button"
              disabled={disabled}
              onClick={startListening}
              aria-label={iconOnlyMobile ? 'Tentar novamente' : undefined}
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
              <span className={labelVisibilityClass}>Tentar novamente</span>
            </button>
          ) : state === 'unavailable' ? (
            <button
              type="button"
              disabled
              aria-label={iconOnlyMobile ? 'Ditado indisponível' : undefined}
              className="inline-flex min-h-[32px] min-w-[32px] cursor-not-allowed items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-3 py-1.5 text-xs text-[var(--text-muted)] opacity-70 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <MicOff aria-hidden="true" className="h-3.5 w-3.5" />
              <span className={labelVisibilityClass}>Ditado indisponível</span>
            </button>
          ) : (
            <button
              type="button"
              disabled={disabled}
              onClick={startListening}
              aria-label={iconOnlyMobile ? 'Iniciar ditado' : undefined}
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <Mic aria-hidden="true" className="h-3.5 w-3.5 text-[var(--text-muted)]" />
              <span className={labelVisibilityClass}>Iniciar ditado</span>
            </button>
          )}
        </div>
      </div>

      <p data-testid="dictation-mode-notice" className="mt-1.5 text-xs text-[var(--text-muted)]">
        {DICTATION_NOTICE}
      </p>

      {state === 'unavailable' ? (
        <div
          role="status"
          data-testid="dictation-unavailable-notice"
          className="mt-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-main)] px-3 py-2 text-xs text-[var(--text-muted)]"
        >
          {DICTATION_STATE_LABELS.unavailable}
        </div>
      ) : null}

      {(state === 'permission_denied' || state === 'error') && errorMessage ? (
        <div
          role="alert"
          data-testid="dictation-error-notice"
          className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--status-error)] bg-[var(--bg-main)] px-3 py-2 text-xs text-[var(--status-error)]"
        >
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            disabled={disabled}
            onClick={startListening}
            className="min-h-[32px] min-w-[32px] shrink-0 rounded-md border border-[var(--status-error)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
          >
            Tentar novamente
          </button>
        </div>
      ) : null}

      {showPreview ? (
        <div
          data-testid="dictation-draft-preview"
          className="mt-3 space-y-2 rounded-xl border border-[var(--border)] bg-[var(--bg-main)] p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label htmlFor={previewId} className="text-xs font-medium text-[var(--text-primary)]">
              Rascunho revisável do ditado
            </label>
            <span className="text-xs text-[var(--text-muted)]">
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
            className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
          />

          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleDiscard}
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
            >
              <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Descartar</span>
            </button>

            <button
              type="button"
              disabled={draftText.trim().length === 0}
              onClick={handleInsert}
              className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center gap-1.5 rounded-lg bg-[var(--btn-primary-bg)] px-3 py-1.5 text-xs font-medium text-[var(--btn-primary-text)] transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
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
