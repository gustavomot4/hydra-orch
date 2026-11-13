import { KeyboardEvent, useRef, useState } from 'react';
import { Brain, FolderSearch, KeyRound, Puzzle, ShieldCheck } from 'lucide-react';
import type { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ConsentMemoryPanel } from './ConsentMemoryPanel';
import { DiscoveryExtensionsPanel } from './DiscoveryExtensionsPanel';
import { SecretsTransportsBudgetPanel } from './SecretsTransportsBudgetPanel';
import { SkillsMcpsPanel } from './SkillsMcpsPanel';

export type GovernanceTab =
  | 'skills_mcps'
  | 'discovery_extensions'
  | 'consent_memory'
  | 'secrets_transports_budget';

export interface GovernancePageProps {
  initialRunId?: string | null;
  initialTab?: GovernanceTab;
  client?: ControlPlaneClient;
}

const GOVERNANCE_TABS: ReadonlyArray<{
  id: GovernanceTab;
  label: string;
  Icon: typeof Puzzle;
}> = [
  { id: 'skills_mcps', label: 'Skills e MCPs', Icon: Puzzle },
  { id: 'discovery_extensions', label: 'Discovery e Extensões', Icon: FolderSearch },
  { id: 'consent_memory', label: 'Memória e Consentimento', Icon: Brain },
  { id: 'secrets_transports_budget', label: 'Segredos, SSH e Orçamento', Icon: KeyRound },
];

export function GovernancePage({
  initialRunId = null,
  initialTab = 'skills_mcps',
  client,
}: GovernancePageProps) {
  const [activeTab, setActiveTab] = useState<GovernanceTab>(initialTab);
  const tabRefs = useRef<Record<GovernanceTab, HTMLButtonElement | null>>({
    skills_mcps: null,
    discovery_extensions: null,
    consent_memory: null,
    secrets_transports_budget: null,
  });

  const handleTabKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight') {
      nextIndex = (index + 1) % GOVERNANCE_TABS.length;
    } else if (e.key === 'ArrowLeft') {
      nextIndex = (index - 1 + GOVERNANCE_TABS.length) % GOVERNANCE_TABS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = GOVERNANCE_TABS.length - 1;
    }

    if (nextIndex !== null) {
      e.preventDefault();
      const targetTab = GOVERNANCE_TABS[nextIndex];
      if (targetTab) {
        setActiveTab(targetTab.id);
        tabRefs.current[targetTab.id]?.focus();
      }
    }
  };

  return (
    <div
      data-testid="governance-page"
      className="mx-auto flex min-h-full w-full max-w-6xl flex-col gap-5 bg-[#141414] px-4 py-6 text-[#E8E8E8] md:px-8"
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[#303030] pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ShieldCheck aria-hidden="true" className="h-5 w-5 text-[#969696]" />
            <h1 className="text-xl font-semibold tracking-tight text-[#E8E8E8]">
              Recursos e Governança
            </h1>
          </div>
          <p className="text-xs text-[#969696]">
            Controle de skills, servidores MCP, varredura opt-in, extensões isoladas, consentimento e memória, referências SecretRef, SSH e orçamento.
          </p>
        </div>
      </header>

      <div
        role="tablist"
        aria-label="Seções de governança e recursos"
        className="flex flex-wrap items-center gap-1.5 rounded-xl border border-[#303030] bg-[#181818] p-1.5"
      >
        {GOVERNANCE_TABS.map((tab, index) => {
          const isSelected = activeTab === tab.id;
          const Icon = tab.Icon;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[tab.id] = el;
              }}
              id={`governance-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-controls={`governance-tabpanel-${tab.id}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(e) => handleTabKeyDown(e, index)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                isSelected
                  ? 'bg-[#202020] text-[#E8E8E8] ring-1 ring-[#303030]'
                  : 'text-[#969696] hover:bg-[#1C1C1C] hover:text-[#E8E8E8]'
              }`}
            >
              <Icon aria-hidden="true" className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      <section
        id={`governance-tabpanel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`governance-tab-${activeTab}`}
        className="min-h-0 flex-1"
      >
        {activeTab === 'skills_mcps' ? <SkillsMcpsPanel client={client} /> : null}
        {activeTab === 'discovery_extensions' ? (
          <DiscoveryExtensionsPanel client={client} />
        ) : null}
        {activeTab === 'consent_memory' ? <ConsentMemoryPanel client={client} /> : null}
        {activeTab === 'secrets_transports_budget' ? (
          <SecretsTransportsBudgetPanel initialRunId={initialRunId} client={client} />
        ) : null}
      </section>
    </div>
  );
}
