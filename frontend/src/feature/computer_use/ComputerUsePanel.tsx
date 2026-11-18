import { useEffect, useId, useMemo, useState } from 'react';
import { Eye, Monitor, OctagonX, Server, ShieldAlert, ShieldCheck } from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useCapabilities } from '@/hook/useCapabilities';

export interface ComputerUsePanelProps {
  hostId?: string;
  onHostChange?: (hostId: string) => void;
  className?: string;
}

function readDetailString(
  detail: Record<string, unknown> | undefined,
  key: string,
): string | null {
  if (!detail) {
    return null;
  }
  const value = detail[key];
  if (typeof value === 'string' && value.trim().length > 0) {
    return value.trim();
  }
  return null;
}

function formatComputerUseUnavailableReason(reason: string | null | undefined): string | null {
  if (!reason) {
    return null;
  }
  const normalized = reason.trim();
  if (!normalized) {
    return null;
  }
  if (normalized === 'uncertified_parking_lot_bridge') {
    return 'Executor de controle do computador ainda não certificado neste host.';
  }
  return normalized.replace(/_/g, ' ');
}

export function ComputerUsePanel({
  hostId = 'local',
  onHostChange,
  className = '',
}: ComputerUsePanelProps) {
  const hostSelectId = useId();
  const { hosts, getHostCapability, isLoading } = useCapabilities();
  const [selectedHostId, setSelectedHostId] = useState<string>(hostId);

  useEffect(() => {
    setSelectedHostId(hostId);
  }, [hostId]);

  const hostOptions = useMemo(() => {
    const byId = new Map<string, { hostId: string; label: string }>();
    for (const entry of hosts) {
      const details = [entry.transport_type, entry.platform].filter(Boolean).join(', ');
      byId.set(entry.host_id, {
        hostId: entry.host_id,
        label: details ? `${entry.host_id} (${details})` : entry.host_id,
      });
    }
    if (!byId.has('local')) {
      byId.set('local', { hostId: 'local', label: 'local' });
    }
    if (!byId.has(selectedHostId)) {
      byId.set(selectedHostId, { hostId: selectedHostId, label: selectedHostId });
    }
    return Array.from(byId.values());
  }, [hosts, selectedHostId]);

  const handleHostChange = (nextHostId: string) => {
    setSelectedHostId(nextHostId);
    onHostChange?.(nextHostId);
  };

  const selectedHostEntry = useMemo(
    () => hosts.find((entry) => entry.host_id === selectedHostId) ?? null,
    [hosts, selectedHostId],
  );

  const resolvedCapability = getHostCapability(selectedHostId, 'computer_use');
  const detail = resolvedCapability.detail;

  const transportId =
    readDetailString(detail, 'transport_id') ?? selectedHostEntry?.transport_id ?? '—';
  const targetWindow =
    readDetailString(detail, 'target_window') ??
    readDetailString(detail, 'target_app') ??
    (selectedHostEntry?.target_identity?.trim() || null);

  const isUnavailable =
    resolvedCapability.status === 'unavailable' || resolvedCapability.status === 'degraded';
  const unavailableReason = formatComputerUseUnavailableReason(resolvedCapability.reason);

  return (
    <div
      data-testid="computer-use-panel"
      className={`mx-auto flex w-full max-w-4xl flex-col gap-4 bg-[var(--bg-main)] px-4 py-6 text-[var(--text-primary)] md:px-8 ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Monitor aria-hidden="true" className="h-5 w-5 text-[var(--text-muted)]" />
            <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
              Controle do computador
            </h1>
            <span className="rounded-md border border-[var(--border)] bg-[var(--bg-sidebar)] px-2 py-0.5 text-xs text-[var(--text-muted)]">
              Requer host certificado
            </span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Execução supervisionada com janela visível, aprovação humana e parada de emergência.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor={hostSelectId}
            className="inline-flex items-center gap-1 text-xs text-[var(--text-muted)]"
          >
            <Server aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Host</span>
          </label>
          <select
            id={hostSelectId}
            value={selectedHostId}
            onChange={(e) => handleHostChange(e.target.value)}
            className="min-h-[32px] min-w-[24px] rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] max-md:min-h-[44px] [@media(pointer:coarse)]:min-h-[44px]"
          >
            {hostOptions.map((opt) => (
              <option key={opt.hostId} value={opt.hostId}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {isLoading ? (
        <div
          role="status"
          className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 text-sm text-[var(--text-muted)]"
        >
          Verificando capacidades do host <code className="font-mono">{selectedHostId}</code>...
        </div>
      ) : isUnavailable ? (
        <section
          aria-label="Controle do computador indisponível"
          className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-[var(--text-primary)]">
              <ShieldAlert aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
              <h2 className="text-sm font-semibold">Controle do computador</h2>
            </div>
            <StatusBadge status={resolvedCapability.status} />
          </div>
          <p className="mt-2 text-xs text-[var(--text-muted)]">
            O host <code className="font-mono text-[var(--text-primary)]">{selectedHostId}</code>{' '}
            não possui certificação ativa para este recurso. A interface não simula cliques nem
            capturas sem executor certificado.
          </p>
          {unavailableReason ? (
            <p className="mt-2 text-xs text-[var(--text-muted)]">
              Situação: <span className="text-[var(--text-primary)]">{unavailableReason}</span>
            </p>
          ) : null}
        </section>
      ) : (
        <section
          aria-label="Governança de controle do computador"
          data-testid="computer-use-certified-surface"
          className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[var(--status-success)]" />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                Executor certificado no host <code className="font-mono">{selectedHostId}</code>
              </h2>
            </div>
            <StatusBadge status="available" labelOverride="Executor pronto" compact />
          </div>

          <div
            data-testid="computer-use-target-requirement"
            className="rounded-lg border border-[var(--border)] bg-[var(--bg-main)] p-3.5 text-xs"
          >
            <div className="flex items-center gap-2 font-medium text-[var(--text-primary)]">
              <Eye aria-hidden="true" className="h-4 w-4 text-[var(--status-info)]" />
              <span>Requisito obrigatório de janela ou alvo visível</span>
            </div>
            <p className="mt-1.5 text-[var(--text-muted)]">
              Alvo reportado:{' '}
              <span className="text-[var(--text-primary)]">
                {targetWindow ?? 'Nenhum alvo ativo — seleção visível de janela ou aplicativo é obrigatória'}
              </span>
            </p>
            <p className="mt-1.5 text-xs text-[var(--text-muted)]">
              A perda ou ocultação da janela alvo interrompe imediatamente a ação; o efeito de cada
              etapa é validado apenas mediante nova observação verificada.
            </p>
          </div>

          <div
            data-testid="computer-use-hitl-invariant"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          >
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-main)] p-3.5 text-xs">
              <div className="flex items-center gap-2 font-medium text-[var(--text-primary)]">
                <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[var(--status-warning)]" />
                <span>Aprovação humana obrigatória</span>
              </div>
              <p className="mt-1.5 text-xs text-[var(--text-muted)]">
                Ações com efeito colateral (cliques, preenchimento de formulários e navegação fora
                da lista permitida) exigem aprovação explícita (
                <code className="font-mono">task.needs_approval</code>).
              </p>
            </div>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-main)] p-3.5 text-xs">
              <div className="flex items-center gap-2 font-medium text-[var(--text-primary)]">
                <OctagonX aria-hidden="true" className="h-4 w-4 text-[var(--status-error)]" />
                <span>Parada de emergência</span>
              </div>
              <p className="mt-1.5 text-xs text-[var(--text-muted)]">
                Pausa imediata e interrupção de emergência ativas durante sessões autorizadas; o
                painel não exibe captura falsa nem simula cliques sintéticos.
              </p>
            </div>
          </div>

          <dl className="grid grid-cols-1 gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-main)] p-3.5 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-[var(--text-muted)]">Transporte certificado</dt>
              <dd className="mt-0.5 text-[var(--text-primary)]">
                {transportId === '—' ? '—' : <code className="font-mono">{transportId}</code>}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--text-muted)]">Sistema do host</dt>
              <dd className="mt-0.5 text-[var(--text-primary)]">
                {selectedHostEntry?.platform ?? '—'}
              </dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  );
}
