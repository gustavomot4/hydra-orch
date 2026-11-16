import { ConversationSnapshot } from '@/feature/chat/conversationTypes';

/** Suggestions come from recorded state only; no inference, tools or automatic send. */
export function contextualSuggestion(chat: ConversationSnapshot): string | undefined {
  const last = chat.turns.at(-1);
  if (!last || ['queued', 'running', 'stopping'].includes(last.state)) return;
  if (last.state === 'failed')
    return `Analise o que impediu a conclusão de “${chat.title.slice(0, 120)}” e proponha como continuar.`;
  if (last.state === 'cancelled')
    return `Resuma o que foi feito em “${chat.title.slice(0, 120)}” e o que falta continuar.`;
  const pending = last.coordination?.plan?.tasks.find((task) => {
    const state = last.coordination?.tasks?.[task.id]?.state;
    return !state || !['accepted', 'succeeded', 'completed'].includes(state);
  });
  if (pending)
    return `${chat.access_mode === 'read-only' ? 'Detalhe os próximos passos para' : 'Continue com a tarefa'}: ${pending.title.slice(0, 180)}.`;
  if (last.diff?.trim())
    return 'Revise as alterações deste resultado e indique o que ainda falta validar.';
  const nextSteps = last.response?.split(
    /(?:^|\n)\s*#{0,4}\s*(?:pr[oó]ximos? passos?|a seguir|next steps?)\s*:?\s*\n/i,
  )[1];
  const action = nextSteps
    ?.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)$/m)?.[1]
    ?.replace(/[*`]/g, '')
    .trim();
  if (action && action.length <= 240)
    return `${chat.access_mode === 'read-only' ? 'Detalhe como realizar o próximo passo' : 'Continue com o próximo passo'}: ${action}`;
}
