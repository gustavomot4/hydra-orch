import { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { CapabilityKey, useCapabilities } from '@/hook/useCapabilities';
import { StatusBadge } from '@/component/StatusBadge';

export interface CapabilityGateProps {
  hostId?: string;
  capability: CapabilityKey;
  title?: string;
  allowDegraded?: boolean;
  children: ReactNode;
}

export function CapabilityGate({
  hostId = 'local',
  capability,
  title,
  allowDegraded = true,
  children,
}: CapabilityGateProps) {
  const { getHostCapability, isLoading } = useCapabilities();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-[#303030] bg-[#202020] p-4 text-sm text-[#969696]">
        Verificando capacidades do host <span className="font-mono">{hostId}</span>...
      </div>
    );
  }

  const resolved = getHostCapability(hostId, capability);

  if (resolved.status === 'unavailable' || (resolved.status === 'degraded' && !allowDegraded)) {
    return (
      <section
        aria-label={title ?? `Capacidade ${capability} indisponível`}
        className="rounded-xl border border-[#303030] bg-[#202020] p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[#E8E8E8]">
            <ShieldAlert aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-sm font-semibold">
              {title ?? `Capacidade "${capability}" indisponível`}
            </h3>
          </div>
          <StatusBadge status={resolved.status} />
        </div>
        <p className="mt-2 text-xs text-[#969696]">
          O host <span className="font-mono text-[#E8E8E8]">{hostId}</span> não possui certificação
          ativa para este recurso. A interface não simula execução sem executor ou bridge certificado.
        </p>
        {resolved.reason ? (
          <p className="mt-2 font-mono text-xs text-[#969696]">
            Motivo: <span className="text-[#E8E8E8]">{resolved.reason}</span>
          </p>
        ) : null}
      </section>
    );
  }

  if (resolved.status === 'degraded') {
    return (
      <div className="space-y-3">
        <div
          role="note"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#F59E0B]/40 bg-[#F59E0B]/10 px-3 py-2 text-xs text-[#FCD34D]"
        >
          <span>
            Modo degradado no host <span className="font-mono">{hostId}</span>
            {resolved.reason ? ` (${resolved.reason})` : ''} — execução sem certificação plena.
          </span>
          <StatusBadge status="degraded" compact />
        </div>
        {children}
      </div>
    );
  }

  return <>{children}</>;
}
