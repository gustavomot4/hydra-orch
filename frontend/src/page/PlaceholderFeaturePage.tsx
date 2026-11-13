import { Layers } from 'lucide-react';
import { CapabilityGate } from '@/component/CapabilityGate';
import { StatusBadge } from '@/component/StatusBadge';
import { CapabilityKey } from '@/hook/useCapabilities';
import { TabKind, useLayoutStore } from '@/store/layoutStore';

export interface PlaceholderFeaturePageProps {
  kind: TabKind;
  title: string;
  targetWave: string;
  targetModule: string;
  description: string;
  capability?: CapabilityKey;
}

export function PlaceholderFeaturePage({
  kind,
  title,
  targetWave,
  targetModule,
  description,
  capability,
}: PlaceholderFeaturePageProps) {
  const selectedHostId = useLayoutStore((s) => s.selectedHostId);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectedRunId = useLayoutStore((s) => s.selectedRunId);
  const selectedSessionId = useLayoutStore((s) => s.selectedSessionId);

  const body = (
    <div
      data-testid={`placeholder-page-${kind}`}
      className="mx-auto w-full max-w-3xl space-y-4 px-4 py-8 md:px-8"
    >
      <div className="rounded-2xl border border-[#303030] bg-[#202020] p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <Layers aria-hidden="true" className="h-5 w-5 text-[#969696]" />
            <h1 className="text-lg font-semibold text-[#E8E8E8]">{title}</h1>
          </div>
          <StatusBadge status="queued" labelOverride={targetWave} />
        </div>

        <p className="mt-3 text-sm text-[#969696]">{description}</p>

        <dl className="mt-4 grid gap-3 rounded-xl border border-[#303030] bg-[#141414] p-4 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-[#969696]">Módulo alvo</dt>
            <dd className="mt-0.5 font-mono text-[#E8E8E8]">{targetModule}</dd>
          </div>
          <div>
            <dt className="text-[#969696]">Host selecionado</dt>
            <dd className="mt-0.5 font-mono text-[#E8E8E8]">{selectedHostId}</dd>
          </div>
          <div>
            <dt className="text-[#969696]">Projeto selecionado</dt>
            <dd className="mt-0.5 font-mono text-[#E8E8E8]">
              {selectedProjectId ?? 'Nenhum'}
            </dd>
          </div>
          <div>
            <dt className="text-[#969696]">Run / Sessão</dt>
            <dd className="mt-0.5 font-mono text-[#E8E8E8]">
              {selectedSessionId ?? selectedRunId ?? 'Nenhum'}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );

  if (capability) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8 md:px-8">
        <CapabilityGate hostId={selectedHostId} capability={capability} title={title}>
          {body}
        </CapabilityGate>
      </div>
    );
  }

  return body;
}
