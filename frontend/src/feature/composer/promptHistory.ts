const KEY = 'hydra_prompt_history_v1';
const LIMIT = 50;
export function readPromptHistory(context: string): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? '{}')[context];
    return Array.isArray(value)
      ? value.filter((s): s is string => typeof s === 'string').slice(-LIMIT)
      : [];
  } catch {
    return [];
  }
}
export function rememberPrompt(context: string, text: string) {
  if (!text.trim() || text.length > 20000) return;
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    const contexts = typeof value === 'object' && value && !Array.isArray(value) ? value : {};
    // Bound contexts as well as entries, without persisting drafts in the history.
    delete contexts[context];
    contexts[context] = [
      ...readPromptHistory(context).filter((s) => s !== text),
      text.slice(0, 20000),
    ].slice(-LIMIT);
    const keys = Object.keys(contexts);
    keys.slice(0, Math.max(0, keys.length - 50)).forEach((k) => delete contexts[k]);
    while (JSON.stringify(contexts).length > 500000 && Object.keys(contexts).length > 1)
      delete contexts[Object.keys(contexts)[0]];
    while (JSON.stringify(contexts).length > 500000 && contexts[context].length > 1)
      contexts[context].shift();
    localStorage.setItem(KEY, JSON.stringify(contexts));
  } catch {
    /* Storage may be disabled. Editing remains available. */
  }
}
export function clearPromptHistory() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* optional storage */
  }
}
