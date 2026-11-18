import type { ReportedModel } from './conversationTypes';
import openai from './brand/openai.png';
import anthropic from './brand/anthropic.svg';
import alibabaCloud from './brand/alibabacloud.svg';
import deepseek from './brand/deepseek.svg';
import meta from './brand/meta.svg';
import mistral from './brand/mistralai.svg';

const companies: Record<string, { name: string; mark?: string }> = {
  openai: { name: 'OpenAI', mark: openai },
  anthropic: { name: 'Anthropic', mark: anthropic },
  google: { name: 'Google' },
  alibaba: { name: 'Alibaba Cloud', mark: alibabaCloud },
  deepseek: { name: 'DeepSeek', mark: deepseek },
  meta: { name: 'Meta', mark: meta },
  mistral: { name: 'Mistral AI', mark: mistral },
  xai: { name: 'xAI' },
};

export function ModelIdentity({ identity }: { identity?: ReportedModel | null }) {
  if (!identity) return <span className="text-[var(--text-muted)]">Modelo não informado</span>;
  const company = identity.company ? companies[identity.company] : undefined;
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 break-all">
      {company?.mark && (
        <img
          src={company.mark}
          alt=""
          className="h-[1.125em] w-[1.125em] shrink-0 object-contain"
        />
      )}
      <span className="font-semibold">{identity.model}</span>
      {company && <span className="text-[var(--text-muted)]">{company.name}</span>}
    </span>
  );
}
