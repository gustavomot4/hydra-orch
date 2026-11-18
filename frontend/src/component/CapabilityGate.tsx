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
      <div
        role="status"
        className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 text-sm text-[var(--text-muted)]"
      >
        Verificando capacidades do host <span className="font-mono">{hostId}</span>...
      </div>
    );
  }

  const resolved = getHostCapability(hostId, capability);

  if (resolved.status === 'unavailable' || (resolved.status === 'degraded' && !allowDegraded)) {
    return (
      <section
        aria-label={title ?? `Capacidade ${capability} indisponível`}
        className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[var(--text-primary)]">
            <ShieldAlert aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
            <h2 className="text-sm font-semibold">
              {title ?? `Capacidade "${capability}" indisponível`}
            </h2>
          </div>
          <StatusBadge status={resolved.status} />
        </div>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          O host <span className="font-mono text-[var(--text-primary)]">{hostId}</span> não possui
          certificação ativa para este recurso. A interface não simula execução sem executor ou
          bridge certificado.
        </p>
        {resolved.reason ? (
          <p className="mt-2 font-mono text-xs text-[var(--text-muted)]">
            Motivo: <span className="text-[var(--text-primary)]">{resolved.reason}</span>
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
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--status-warning)] bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--status-warning)]"
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
