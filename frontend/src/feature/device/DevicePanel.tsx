import { useEffect, useId, useMemo, useState } from 'react';
import { Server, ShieldAlert, ShieldCheck, Smartphone } from 'lucide-react';
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

function formatDeviceUnavailableReason(reason: string | null | undefined): string | null {
  if (!reason) {
    return null;
  }
  const normalized = reason.trim();
  if (!normalized) {
    return null;
  }
  if (normalized === 'uncertified_parking_lot_bridge') {
    return 'Conector de emulador móvel ainda não certificado neste host.';
  }
  return normalized.replace(/_/g, ' ');
}

export function DevicePanel({
  hostId = 'local',
  onHostChange,
  className = '',
}: DevicePanelProps) {
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

  const isUnavailable =
    resolvedCapability.status === 'unavailable' || resolvedCapability.status === 'degraded';
  const unavailableReason = formatDeviceUnavailableReason(resolvedCapability.reason);

  return (
    <div
      data-testid="device-panel"
      className={`mx-auto flex w-full max-w-4xl flex-col gap-4 bg-[var(--bg-main)] px-4 py-6 text-[var(--text-primary)] md:px-8 ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Smartphone aria-hidden="true" className="h-5 w-5 text-[var(--text-muted)]" />
            <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
              Emulador móvel
            </h1>
            <span className="rounded-md border border-[var(--border)] bg-[var(--bg-sidebar)] px-2 py-0.5 text-xs text-[var(--text-muted)]">
              Requer host certificado
            </span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Prontidão dos conectores iOS e Android certificados por host.
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
          aria-label="Emulador móvel indisponível"
          className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-[var(--text-primary)]">
              <ShieldAlert aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
              <h2 className="text-sm font-semibold">Emulador móvel</h2>
            </div>
            <StatusBadge status={resolvedCapability.status} />
          </div>
          <p className="mt-2 text-xs text-[var(--text-muted)]">
            O host <code className="font-mono text-[var(--text-primary)]">{selectedHostId}</code>{' '}
            não possui certificação ativa para este recurso. A interface não simula execução sem
            conector certificado.
          </p>
          {unavailableReason ? (
            <p className="mt-2 text-xs text-[var(--text-muted)]">
              Situação: <span className="text-[var(--text-primary)]">{unavailableReason}</span>
            </p>
          ) : null}
        </section>
      ) : (
        <section
          aria-label="Prontidão do conector de emulador móvel"
          data-testid="device-certified-surface"
          className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck aria-hidden="true" className="h-4 w-4 text-[var(--status-success)]" />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                Conector certificado no host <code className="font-mono">{selectedHostId}</code>
              </h2>
            </div>
            <StatusBadge status="available" labelOverride="Bridge pronto" compact />
          </div>

          <p className="text-xs text-[var(--text-muted)]">
            Prontidão verificada por metadados reais do transporte. Controles de interação móvel
            exigem sessão ativa vinculada a dispositivo ou SDK real; nenhuma tela ou toque sintético
            é simulado neste painel.
          </p>

          <div
            role="group"
            aria-label="Estado das plataformas móveis"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          >
            <div
              data-testid="device-platform-ios"
              className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-3.5 py-3"
            >
              <div>
                <div className="text-xs font-medium text-[var(--text-primary)]">
                  Simulador iOS
                </div>
                <div className="text-xs text-[var(--text-muted)]">Certificação independente</div>
              </div>
              <StatusBadge status={iosStatus} compact />
            </div>

            <div
              data-testid="device-platform-android"
              className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-main)] px-3.5 py-3"
            >
              <div>
                <div className="text-xs font-medium text-[var(--text-primary)]">
                  Emulador Android (ADB)
                </div>
                <div className="text-xs text-[var(--text-muted)]">Certificação independente</div>
              </div>
              <StatusBadge status={androidStatus} compact />
            </div>
          </div>

          <section aria-label="Metadados do dispositivo alvo">
            <dl className="grid grid-cols-1 gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-main)] p-3.5 text-xs sm:grid-cols-2">
              <div>
                <dt className="text-[var(--text-muted)]">Host selecionado</dt>
                <dd className="mt-0.5 text-[var(--text-primary)]">
                  <code className="font-mono">{selectedHostId}</code>
                </dd>
              </div>
              <div>
                <dt className="text-[var(--text-muted)]">Transporte certificado</dt>
                <dd className="mt-0.5 text-[var(--text-primary)]">
                  {transportId === '—' ? (
                    '—'
                  ) : (
                    <code className="font-mono">{transportId}</code>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--text-muted)]">Dispositivo ou alvo reportado</dt>
                <dd className="mt-0.5 text-[var(--text-primary)]">{targetDevice}</dd>
              </div>
              <div>
                <dt className="text-[var(--text-muted)]">Sistema do host</dt>
                <dd className="mt-0.5 text-[var(--text-primary)]">
                  {selectedHostEntry?.platform ?? '—'}
                </dd>
              </div>
            </dl>
          </section>
        </section>
      )}
    </div>
  );
}
