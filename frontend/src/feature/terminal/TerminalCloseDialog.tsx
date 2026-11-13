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
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content
          data-testid="terminal-close-dialog"
          aria-describedby="terminal-close-dialog-desc"
          className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,480px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-[#303030] bg-[#202020] p-6 text-[#E8E8E8] shadow-2xl focus:outline-none"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#F59E0B]/40 bg-[#F59E0B]/10 text-[#FCD34D]">
                <AlertTriangle aria-hidden="true" className="h-4 w-4" />
              </div>
              <div>
                <Dialog.Title className="text-sm font-semibold text-[#E8E8E8]">
                  Fechar terminal ativo?
                </Dialog.Title>
                <p className="text-xs text-[#969696]">
                  O processo ainda está em execução nesta sessão PTY.
                </p>
              </div>
            </div>

            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Cancelar fechamento"
                disabled={isSubmitting}
                className="rounded-lg p-1 text-[#969696] transition-colors hover:bg-[#282828] hover:text-[#E8E8E8] disabled:opacity-50"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <Dialog.Description
            id="terminal-close-dialog-desc"
            className="mt-4 text-xs leading-relaxed text-[#969696]"
          >
            Escolha se deseja apenas desconectar a interface preservando o processo em segundo
            plano (com reconexão via cursor <span className="font-mono text-[#E8E8E8]">after_seq</span>)
            ou encerrar toda a árvore de processos agora.
          </Dialog.Description>

          <dl className="mt-4 space-y-1.5 rounded-xl border border-[#303030] bg-[#141414] p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[#969696]">Sessão</dt>
              <dd className="truncate font-mono text-[#E8E8E8]">{session.session_id}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[#969696]">Host</dt>
              <dd className="font-mono text-[#E8E8E8]">{session.host_id}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[#969696]">Diretório (cwd)</dt>
              <dd className="truncate font-mono text-[#E8E8E8]">{session.cwd}</dd>
            </div>
          </dl>

          {errorMessage ? (
            <div
              role="alert"
              className="mt-3 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
            >
              {errorMessage}
            </div>
          ) : null}

          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={isSubmitting}
                className="rounded-lg border border-[#303030] bg-[#181818] px-3 py-2 text-xs font-medium text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:opacity-50"
              >
                Cancelar
              </button>
            </Dialog.Close>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={onKeepRunning}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[#303030] bg-[#E8E8E8] px-3 py-2 text-xs font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              <PauseCircle aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Manter processo em segundo plano</span>
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={onTerminate}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[#EF4444]/50 bg-[#EF4444]/15 px-3 py-2 text-xs font-medium text-[#FCA5A5] transition-colors hover:bg-[#EF4444]/25 disabled:cursor-not-allowed disabled:opacity-60"
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
