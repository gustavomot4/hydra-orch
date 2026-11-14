import { describe, expect, it } from 'vitest';
import { clearPendingSend, pendingMessage } from '@/feature/chat/conversationTypes';

describe('durable chat sends', () => {
  it('reuses the accepted send identity and original cursor after a lost response and fresh snapshot', () => {
    const scope = 'conversation-reconnect';
    clearPendingSend(scope);
    const first = pendingMessage(scope, {
      content: 'Explique o README',
      expected_last_seq: 4,
      attachment_ids: [],
    });
    const retry = pendingMessage(scope, {
      content: 'Explique o README',
      expected_last_seq: 15,
      attachment_ids: [],
    });
    expect(retry.idempotency_key).toBe(first.idempotency_key);
    expect(retry.expected_last_seq).toBe(4);
    clearPendingSend(scope);
    const next = pendingMessage(scope, {
      content: 'Explique o README',
      expected_last_seq: 15,
      attachment_ids: [],
    });
    expect(next.idempotency_key).not.toBe(first.idempotency_key);
    expect(next.expected_last_seq).toBe(15);
  });
});
