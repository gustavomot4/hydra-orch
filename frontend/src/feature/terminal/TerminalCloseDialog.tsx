import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, PauseCircle, Power, X } from 'lucide-react';
import { PtySessionInfo } from './terminalTypes';

export interface TerminalCloseDialogProps {
  open: boolean;
  session: PtySessionInfo;
  isSubmitting?: boolean;
  errorMessage?: string | null;
  onOpenChange: (open: boolean) => void;
  onKeepRunning: () => void;
  onTerminate: () => void;
}

export function TerminalCloseDialog({
  open,
  session,
  isSubmitting = false,
  errorMessage = null,
  onOpenChange,
  onKeepRunning,
  onTerminate,
}: TerminalCloseDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[var(--bg-main)]/80" />
        <Dialog.Content
          data-testid="terminal-close-dialog"
          aria-describedby="terminal-close-dialog-desc"
          className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,480px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 text-[var(--text-primary)] shadow-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[var(--status-warning)] bg-[var(--bg-main)] text-[var(--status-warning)]">
                <AlertTriangle aria-hidden="true" className="h-4 w-4" />
              </div>
              <div>
                <Dialog.Title className="text-sm font-semibold text-[var(--text-primary)]">
                  Fechar terminal ativo?
                </Dialog.Title>
                <p className="text-xs text-[var(--text-muted)]">
                  O processo ainda está em execução nesta sessão.
                </p>
              </div>
            </div>

            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Cancelar fechamento"
                disabled={isSubmitting}
                className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-lg p-1.5 text-[var(--text-muted)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] [@media(hover:hover)_and_(pointer:fine)]:hover:text-[var(--text-primary)] disabled:opacity-50 max-md:min-h-[44px] max-md:min-w-[44px] [@media(pointer:coarse)]:min-h-[44px] [@media(pointer:coarse)]:min-w-[44px]"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <Dialog.Description
            id="terminal-close-dialog-desc"
            className="mt-4 text-xs leading-relaxed text-[var(--text-muted)]"
          >
            Escolha se deseja manter o processo em execução em segundo plano para reconectar mais
            tarde ou encerrar toda a árvore de processos agora.
          </Dialog.Description>

          <dl className="mt-4 space-y-1.5 border-y border-[var(--border)] py-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[var(--text-muted)]">Sessão</dt>
              <dd className="min-w-0 truncate text-[var(--text-primary)]">
                <code>{session.session_id}</code>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[var(--text-muted)]">Host</dt>
              <dd className="text-[var(--text-primary)]">
                <code>{session.host_id}</code>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[var(--text-muted)]">Diretório</dt>
              <dd className="min-w-0 break-all text-right text-[var(--text-primary)] [overflow-wrap:anywhere]">
                <code>{session.cwd}</code>
              </dd>
            </div>
          </dl>

          {errorMessage ? (
            <div
              role="alert"
              className="mt-3 rounded-lg border border-[var(--status-error)] bg-[var(--bg-main)] px-3 py-2 text-xs text-[var(--status-error)]"
            >
              {errorMessage}
            </div>
          ) : null}

          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={isSubmitting}
                className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--bg-rail)] px-3 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] disabled:opacity-50 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
              >
                Cancelar
              </button>
            </Dialog.Close>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={onKeepRunning}
              className="inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-lg bg-[var(--btn-primary-bg)] px-3 py-2 text-xs font-medium text-[var(--btn-primary-text)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-60 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
            >
              <PauseCircle aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Manter processo em segundo plano</span>
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={onTerminate}
              className="inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-lg border border-[var(--status-error)] bg-[var(--bg-main)] px-3 py-2 text-xs font-medium text-[var(--status-error)] transition-colors [@media(hover:hover)_and_(pointer:fine)]:hover:bg-[var(--bg-hover)] disabled:cursor-not-allowed disabled:opacity-60 max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
            >
              <Power aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Encerrar processo</span>
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
