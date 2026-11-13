import { FormEvent, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Eye, EyeOff, KeyRound, Lock, ShieldCheck } from 'lucide-react';
import { createControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useAuthStore } from '@/store/authStore';
import { ControlPlaneApiError } from '@/type/controlPlane';

export function AuthGate() {
  const queryClient = useQueryClient();
  const authError = useAuthStore((s) => s.authError);
  const status = useAuthStore((s) => s.status);
  const setAuthenticating = useAuthStore((s) => s.setAuthenticating);
  const authenticate = useAuthStore((s) => s.authenticate);
  const setAuthError = useAuthStore((s) => s.setAuthError);

  const [tokenInput, setTokenInput] = useState('');
  const [showToken, setShowToken] = useState(false);

  const isSubmitting = status === 'authenticating';

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = tokenInput.trim();
    if (!trimmed) {
      setAuthError('Informe um token Bearer local válido para continuar.');
      return;
    }

    setAuthenticating();
    const probeClient = createControlPlaneClient(trimmed);
    try {
      const bootstrap = await probeClient.getBootstrap();
      queryClient.setQueryData(['control-plane', 'bootstrap', 'authenticated'], bootstrap);
      authenticate(trimmed, 'operator');
      setTokenInput('');
    } catch (err) {
      if (err instanceof ControlPlaneApiError) {
        if (err.status === 401 || err.status === 403) {
          setAuthError('Token Bearer recusado pelo Control Plane (HTTP 401).');
        } else {
          setAuthError(err.payload.message || `Erro ao validar token (${err.status}).`);
        }
      } else {
        setAuthError('Não foi possível conectar ao servidor Control Plane (/v1/control-plane/bootstrap).');
      }
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#141414] px-4 py-8 text-[#E8E8E8]">
      <section
        aria-labelledby="auth-gate-title"
        className="w-full max-w-md rounded-2xl border border-[#303030] bg-[#202020] p-6 shadow-2xl"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#303030] bg-[#181818]">
            <Lock aria-hidden="true" className="h-5 w-5 text-[#E8E8E8]" />
          </div>
          <div>
            <h1 id="auth-gate-title" className="text-base font-semibold text-[#E8E8E8]">
              Hydra Control Plane
            </h1>
            <p className="text-xs text-[#969696]">Autenticação local via token Bearer</p>
          </div>
        </div>

        <p className="mt-4 text-xs leading-relaxed text-[#969696]">
          Insira o token configurado em <span className="font-mono text-[#E8E8E8]">HYDRA_API_TOKEN</span>.
          O token é mantido apenas no <span className="font-mono text-[#E8E8E8]">sessionStorage</span>{' '}
          desta aba e nunca é gravado na URL.
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
          <div>
            <label
              htmlFor="hydra-bearer-token-input"
              className="mb-1.5 block text-xs font-medium text-[#E8E8E8]"
            >
              Token Bearer
            </label>
            <div className="relative flex items-center">
              <KeyRound
                aria-hidden="true"
                className="pointer-events-none absolute left-3 h-4 w-4 text-[#969696]"
              />
              <input
                id="hydra-bearer-token-input"
                name="bearerToken"
                type={showToken ? 'text' : 'password'}
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="Cole o token local do Hydra..."
                disabled={isSubmitting}
                className="w-full rounded-lg border border-[#303030] bg-[#141414] py-2.5 pl-9 pr-10 font-mono text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setShowToken((prev) => !prev)}
                aria-label={showToken ? 'Ocultar token' : 'Mostrar token'}
                className="absolute right-2 rounded p-1 text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]"
              >
                {showToken ? (
                  <EyeOff aria-hidden="true" className="h-4 w-4" />
                ) : (
                  <Eye aria-hidden="true" className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {authError ? (
            <div
              role="alert"
              className="rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
            >
              {authError}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#E8E8E8] px-4 py-2.5 text-sm font-medium text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ShieldCheck aria-hidden="true" className="h-4 w-4" />
            <span>{isSubmitting ? 'Validando token...' : 'Conectar ao Control Plane'}</span>
          </button>
        </form>
      </section>
    </main>
  );
}
