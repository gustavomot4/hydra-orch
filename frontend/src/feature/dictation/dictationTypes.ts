export type DictationState =
  | 'idle'
  | 'listening'
  | 'permission_denied'
  | 'unavailable'
  | 'draft_ready'
  | 'error';

export type DictationErrorCode =
  | 'not-allowed'
  | 'service-not-allowed'
  | 'audio-capture'
  | 'no-speech'
  | 'network'
  | 'aborted'
  | 'unavailable'
  | 'unknown';

export interface DictationResultEvent {
  transcript: string;
  isFinal: boolean;
  /** When true, replaces accumulated transcript instead of appending. */
  replace?: boolean;
}

export interface DictationErrorEvent {
  code: DictationErrorCode;
  message?: string;
}

export interface DictationAdapterCallbacks {
  onStart?: () => void;
  onResult?: (event: DictationResultEvent) => void;
  onError?: (event: DictationErrorEvent) => void;
  onEnd?: () => void;
}

export interface DictationSpeechAdapter {
  isSupported: () => boolean;
  start: (
    callbacks: DictationAdapterCallbacks,
    options?: { lang?: string },
  ) => void | Promise<void>;
  stop: () => void;
  abort?: () => void;
}

export const DICTATION_NOTICE =
  'Captura de texto por voz (não é modo conversação duplex RF36)';

export const DICTATION_STATE_LABELS: Record<DictationState, string> = {
  idle: 'Inativo',
  listening: 'Ouvindo',
  permission_denied:
    'Permissão de microfone negada — clique para tentar novamente ou revise permissões do navegador',
  unavailable: 'Ditado por voz indisponível neste navegador',
  draft_ready: 'Rascunho revisável',
  error: 'Erro no ditado por voz',
};

interface BrowserSpeechResultAlternative {
  transcript?: string;
}

interface BrowserSpeechResult {
  isFinal?: boolean;
  0?: BrowserSpeechResultAlternative;
}

interface BrowserSpeechResultEvent {
  results?: ArrayLike<BrowserSpeechResult>;
}

interface BrowserSpeechErrorEvent {
  error?: string;
  message?: string;
}

interface BrowserSpeechRecognitionInstance {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onresult: ((event: BrowserSpeechResultEvent) => void) | null;
  onerror: ((event: BrowserSpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type BrowserSpeechRecognitionCtor = new () => BrowserSpeechRecognitionInstance;

interface WindowWithSpeechRecognition {
  SpeechRecognition?: BrowserSpeechRecognitionCtor;
  webkitSpeechRecognition?: BrowserSpeechRecognitionCtor;
}

function resolveSpeechRecognitionCtor(): BrowserSpeechRecognitionCtor | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const win = window as unknown as WindowWithSpeechRecognition;
  const ctor = win.SpeechRecognition ?? win.webkitSpeechRecognition;
  return typeof ctor === 'function' ? ctor : null;
}

function normalizeBrowserErrorCode(rawError?: string): DictationErrorCode {
  switch (rawError) {
    case 'not-allowed':
    case 'service-not-allowed':
    case 'audio-capture':
    case 'no-speech':
    case 'network':
    case 'aborted':
      return rawError;
    default:
      return 'unknown';
  }
}

export function formatDictationErrorMessage(
  code: DictationErrorCode,
  customMessage?: string,
): string {
  if (customMessage && customMessage.trim().length > 0) {
    return customMessage;
  }
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return DICTATION_STATE_LABELS.permission_denied;
    case 'unavailable':
      return DICTATION_STATE_LABELS.unavailable;
    case 'audio-capture':
      return 'Nenhum microfone acessível foi encontrado para captura.';
    case 'no-speech':
      return 'Nenhuma fala foi detectada. Clique para tentar novamente.';
    case 'network':
      return 'Falha de rede no reconhecimento de voz do navegador.';
    case 'aborted':
      return 'Captura de voz interrompida.';
    case 'unknown':
    default:
      return 'Não foi possível concluir a captura de voz.';
  }
}

export function createBrowserSpeechAdapter(): DictationSpeechAdapter {
  let activeInstance: BrowserSpeechRecognitionInstance | null = null;

  return {
    isSupported: () => resolveSpeechRecognitionCtor() !== null,
    start: (callbacks, options) => {
      const Ctor = resolveSpeechRecognitionCtor();
      if (!Ctor) {
        callbacks.onError?.({
          code: 'unavailable',
          message: DICTATION_STATE_LABELS.unavailable,
        });
        return;
      }

      if (activeInstance) {
        try {
          activeInstance.abort();
        } catch {
          // Ignora erro ao abortar instância anterior
        }
        activeInstance = null;
      }

      const recognition = new Ctor();
      recognition.lang = options?.lang ?? 'pt-BR';
      recognition.interimResults = true;
      recognition.continuous = true;

      recognition.onstart = () => {
        callbacks.onStart?.();
      };

      recognition.onresult = (event) => {
        const results = event.results;
        if (!results) {
          return;
        }
        const parts: string[] = [];
        let allFinal = results.length > 0;
        for (let i = 0; i < results.length; i += 1) {
          const entry = results[i];
          const text = entry?.[0]?.transcript?.trim();
          if (text) {
            parts.push(text);
          }
          if (!entry?.isFinal) {
            allFinal = false;
          }
        }
        callbacks.onResult?.({
          transcript: parts.join(' '),
          isFinal: allFinal,
          replace: true,
        });
      };

      recognition.onerror = (event) => {
        const code = normalizeBrowserErrorCode(event.error);
        callbacks.onError?.({
          code,
          message: formatDictationErrorMessage(code, event.message),
        });
      };

      recognition.onend = () => {
        if (activeInstance === recognition) {
          activeInstance = null;
        }
        callbacks.onEnd?.();
      };

      activeInstance = recognition;
      try {
        recognition.start();
      } catch (err) {
        activeInstance = null;
        const rawName = err instanceof Error ? err.name : '';
        const code: DictationErrorCode =
          rawName === 'NotAllowedError' || rawName === 'SecurityError'
            ? 'not-allowed'
            : 'unknown';
        callbacks.onError?.({
          code,
          message: formatDictationErrorMessage(
            code,
            err instanceof Error ? err.message : undefined,
          ),
        });
      }
    },
    stop: () => {
      try {
        activeInstance?.stop();
      } catch {
        // Ignora erro ao parar reconhecimento já encerrado
      }
    },
    abort: () => {
      try {
        activeInstance?.abort();
      } catch {
        // Ignora erro ao abortar reconhecimento já encerrado
      } finally {
        activeInstance = null;
      }
    },
  };
}
