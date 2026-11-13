import { useEffect, useId, useMemo, useState } from 'react';
import { Server, ShieldCheck, Smartphone } from 'lucide-react';
import { CapabilityGate } from '@/component/CapabilityGate';
import { StatusBadge } from '@/component/StatusBadge';
import { useCapabilities } from '@/hook/useCapabilities';

export interface DevicePanelProps {
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

export function DevicePanel({
  hostId = 'local',
  onHostChange,
  className = '',
}: DevicePanelProps) {
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

  const resolvedCapability = getHostCapability(selectedHostId, 'mobile_emulator');
  const detail = resolvedCapability.detail;

  const platformsRecord =
    detail && typeof detail.platforms === 'object' && detail.platforms !== null
      ? (detail.platforms as Record<string, unknown>)
      : null;

  const iosStatus =
    typeof platformsRecord?.ios === 'string' && platformsRecord.ios.trim().length > 0
      ? platformsRecord.ios.trim()
      : 'unknown';
  const androidStatus =
    typeof platformsRecord?.android === 'string' && platformsRecord.android.trim().length > 0
      ? platformsRecord.android.trim()
      : 'unknown';

  const transportId =
    readDetailString(detail, 'transport_id') ?? selectedHostEntry?.transport_id ?? '—';
  const targetDevice =
    readDetailString(detail, 'target_device') ??
    readDetailString(detail, 'device_name') ??
    (selectedHostEntry?.target_identity?.trim() || '—');

  return (
    <div
      data-testid="device-panel"
      className={`mx-auto flex w-full max-w-4xl flex-col gap-4 bg-[#141414] px-4 py-6 text-[#E8E8E8] md:px-8 ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[#303030] pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Smartphone aria-hidden="true" className="h-5 w-5 text-[#969696]" />
            <h1 className="text-lg font-semibold tracking-tight text-[#E8E8E8]">
              Emulador móvel
            </h1>
            <span className="rounded-md border border-[#303030] bg-[#1C1C1C] px-2 py-0.5 font-mono text-[11px] text-[#969696]">
              Parking Lot F06 · Capability-gated
            </span>
          </div>
          <p className="text-xs text-[#969696]">
            Painel condicional de prontidão para bridges móveis certificados (iOS / Android) por host.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor={hostSelectId} className="inline-flex items-center gap-1 text-xs text-[#969696]">
            <Server aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Host:</span>
          </label>
          <select
            id={hostSelectId}
            aria-label="Selecionar host para emulador móvel"
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
        capability="mobile_emulator"
        allowDegraded={false}
        title="Emulador móvel"
      >
        <section
          aria-label="Prontidão do bridge de emulador móvel"
          data-testid="device-certified-surface"
          className="space-y-4 rounded-xl border border-[#303030] bg-[#202020] p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#303030] pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[#4ADE80]" />
              <h2 className="text-sm font-semibold text-[#E8E8E8]">
                Bridge certificado no host <span className="font-mono">{selectedHostId}</span>
              </h2>
            </div>
            <StatusBadge status="available" labelOverride="Bridge pronto" compact />
          </div>

          <p className="text-xs text-[#969696]">
            Prontidão verificada por metadados reais do transporte. Controles de interação móvel
            exigem sessão ativa vinculada a dispositivo/SDK real; nenhuma tela ou toque sintético é
            simulado neste painel.
          </p>

          <div
            aria-label="Estado das plataformas móveis"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          >
            <div
              data-testid="device-platform-ios"
              className="flex items-center justify-between rounded-lg border border-[#303030] bg-[#141414] px-3.5 py-3"
            >
              <div>
                <div className="text-xs font-medium text-[#E8E8E8]">iOS Simulator / Bridge</div>
                <div className="text-[11px] text-[#969696]">Certificação independente</div>
              </div>
              <StatusBadge status={iosStatus} compact />
            </div>

            <div
              data-testid="device-platform-android"
              className="flex items-center justify-between rounded-lg border border-[#303030] bg-[#141414] px-3.5 py-3"
            >
              <div>
                <div className="text-xs font-medium text-[#E8E8E8]">Android Emulator / ADB</div>
                <div className="text-[11px] text-[#969696]">Certificação independente</div>
              </div>
              <StatusBadge status={androidStatus} compact />
            </div>
          </div>

          <dl
            aria-label="Metadados do dispositivo alvo"
            className="grid grid-cols-1 gap-3 rounded-lg border border-[#303030] bg-[#141414] p-3.5 text-xs sm:grid-cols-2"
          >
            <div>
              <dt className="text-[#969696]">Host selecionado</dt>
              <dd className="mt-0.5 font-mono text-[#E8E8E8]">{selectedHostId}</dd>
            </div>
            <div>
              <dt className="text-[#969696]">Transporte certificado</dt>
              <dd className="mt-0.5 font-mono text-[#E8E8E8]">{transportId}</dd>
            </div>
            <div>
              <dt className="text-[#969696]">Dispositivo / alvo reportado</dt>
              <dd className="mt-0.5 font-mono text-[#E8E8E8]">{targetDevice}</dd>
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
