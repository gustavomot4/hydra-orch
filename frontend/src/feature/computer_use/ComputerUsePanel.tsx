import { useEffect, useId, useMemo, useState } from 'react';
import { Eye, Monitor, OctagonX, Server, ShieldCheck } from 'lucide-react';
import { CapabilityGate } from '@/component/CapabilityGate';
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

export function ComputerUsePanel({
  hostId = 'local',
  onHostChange,
  className = '',
}: ComputerUsePanelProps) {
  const hostSelectId = useId();
  const { hosts, getHostCapability } = useCapabilities();
  const [selectedHostId, setSelectedHostId] = useState<string>(hostId);

  useEffect(() => {
    setSelectedHostId(hostId);
  }, [hostId]);

  const hostOptions = useMemo(() => {
    const byId = new Map<string, { hostId: string; label: string }>();
    for (const entry of hosts) {
      const details = [entry.transport_type, entry.platform].filter(Boolean).join(' · ');
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

  return (
    <div
      data-testid="computer-use-panel"
      className={`mx-auto flex w-full max-w-4xl flex-col gap-4 bg-[#141414] px-4 py-6 text-[#E8E8E8] md:px-8 ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[#303030] pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Monitor aria-hidden="true" className="h-5 w-5 text-[#969696]" />
            <h1 className="text-lg font-semibold tracking-tight text-[#E8E8E8]">
              Controle do computador
            </h1>
            <span className="rounded-md border border-[#303030] bg-[#1C1C1C] px-2 py-0.5 font-mono text-[11px] text-[#969696]">
              Parking Lot F07 · Capability-gated
            </span>
          </div>
          <p className="text-xs text-[#969696]">
            Superfície governada por certificação de host, alvo visual explícito, HITL e parada de emergência.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor={hostSelectId} className="inline-flex items-center gap-1 text-xs text-[#969696]">
            <Server aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Host:</span>
          </label>
          <select
            id={hostSelectId}
            aria-label="Selecionar host para controle do computador"
            value={selectedHostId}
            onChange={(e) => handleHostChange(e.target.value)}
            className="rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8]"
          >
            {hostOptions.map((opt) => (
              <option key={opt.hostId} value={opt.hostId}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      <CapabilityGate
        hostId={selectedHostId}
        capability="computer_use"
        allowDegraded={false}
        title="Controle do computador"
      >
        <section
          aria-label="Governança de controle do computador"
          data-testid="computer-use-certified-surface"
          className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#303030] pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[#4ADE80]" />
              <h2 className="text-sm font-semibold text-[#E8E8E8]">
                Executor certificado no host <span className="font-mono">{selectedHostId}</span>
              </h2>
            </div>
            <StatusBadge status="available" labelOverride="Executor pronto" compact />
          </div>

          <div
            data-testid="computer-use-target-requirement"
            className="rounded-lg border border-[#303030] bg-[#141414] p-3.5 text-xs"
          >
            <div className="flex items-center gap-2 font-medium text-[#E8E8E8]">
              <Eye aria-hidden="true" className="h-4 w-4 text-[#93C5FD]" />
              <span>Requisito obrigatório de janela / alvo visível</span>
            </div>
            <p className="mt-1.5 text-[#969696]">
              Alvo reportado:{' '}
              <span className="font-mono text-[#E8E8E8]">
                {targetWindow ?? 'Nenhum alvo ativo — seleção visível de janela/app é obrigatória'}
              </span>
            </p>
            <p className="mt-1.5 text-[11px] text-[#969696]">
              A perda ou ocultação da janela alvo interrompe imediatamente a ação; o efeito de cada
              etapa é validado apenas mediante nova observação verificada.
            </p>
          </div>

          <div
            data-testid="computer-use-hitl-invariant"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          >
            <div className="rounded-lg border border-[#303030] bg-[#141414] p-3.5 text-xs">
              <div className="flex items-center gap-2 font-medium text-[#E8E8E8]">
                <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[#FCD34D]" />
                <span>Invariante HITL obrigatória</span>
              </div>
              <p className="mt-1.5 text-[11px] text-[#969696]">
                Ações com efeito colateral (cliques, preenchimento de formulários e navegação fora
                da allowlist) exigem aprovação HITL explícita (<span className="font-mono">task.needs_approval</span>).
              </p>
            </div>

            <div className="rounded-lg border border-[#303030] bg-[#141414] p-3.5 text-xs">
              <div className="flex items-center gap-2 font-medium text-[#E8E8E8]">
                <OctagonX aria-hidden="true" className="h-4 w-4 text-[#FCA5A5]" />
                <span>Parada de emergência (Emergency Stop)</span>
              </div>
              <p className="mt-1.5 text-[11px] text-[#969696]">
                Pausa imediata e interrupção de emergência ativas durante sessões autorizadas; o
                painel não exibe captura falsa nem simula cliques sintéticos.
              </p>
            </div>
          </div>

          <dl className="grid grid-cols-1 gap-3 rounded-lg border border-[#303030] bg-[#141414] p-3.5 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-[#969696]">Transporte certificado</dt>
              <dd className="mt-0.5 font-mono text-[#E8E8E8]">{transportId}</dd>
            </div>
            <div>
              <dt className="text-[#969696]">Sistema do host</dt>
              <dd className="mt-0.5 font-mono text-[#E8E8E8]">
                {selectedHostEntry?.platform ?? '—'}
              </dd>
            </div>
          </dl>
        </section>
      </CapabilityGate>
    </div>
  );
}
