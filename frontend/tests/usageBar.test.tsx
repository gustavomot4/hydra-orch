import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createHydraQueryClient } from '@/hook/queryClient';
import { UsageBar } from '@/component/UsageBar';
import { QuotaStatusPayload } from '@/type/controlPlane';

function renderUsageBar(quota: QuotaStatusPayload) {
  const qc = createHydraQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <UsageBar quota={quota} />
    </QueryClientProvider>,
  );
}

describe('UsageBar compact footer contract', () => {
  it('renders observed percentage, em-dash for unknown (never 0%), and marks stale without clutter', () => {
    const quota: QuotaStatusPayload = {
      status: 'observed',
      claude_pro: {
        status: 'observed',
        remaining_percent: 64,
        resets_in_seconds: 3600,
      },
      chatgpt_plus: {
        status: 'unknown',
        remaining_percent: null,
        resets_in_seconds: null,
      },
      gemini_pro: {
        status: 'stale',
        remaining_percent: 28,
        resets_in_seconds: 900,
      },
    };

    renderUsageBar(quota);

    const claudeRow = screen.getByTestId('usage-row-claude_pro');
    expect(within(claudeRow).getByText('64%')).toBeInTheDocument();
    expect(claudeRow).toHaveAttribute('data-quota-status', 'observed');

    const codexRow = screen.getByTestId('usage-row-chatgpt_plus');
    expect(within(codexRow).getByText('—')).toBeInTheDocument();
    expect(within(codexRow).queryByText('0%')).toBeNull();
    expect(codexRow).toHaveAttribute('data-quota-status', 'unknown');

    const agyRow = screen.getByTestId('usage-row-gemini_pro');
    expect(agyRow).toHaveAttribute('data-quota-status', 'stale');
    expect(within(agyRow).getByTestId('usage-stale-gemini_pro')).toBeInTheDocument();
    expect(within(agyRow).getByText('28%')).toBeInTheDocument();

    // Compact footer must NOT show provider names, account emails, or reset timers
    const footer = screen.getByTestId('usage-bar-footer');
    expect(footer.textContent).not.toMatch(/claude|codex|chatgpt|gemini|reset|min|hora/i);
  });
});
