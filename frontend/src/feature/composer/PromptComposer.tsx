import { ChangeEvent, KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Mic, Paperclip, Send } from 'lucide-react';
import {
  clearComposerDraft,
  ComposerTriggerMatch,
  DEFAULT_MENTION_ITEMS,
  detectComposerTrigger,
  loadComposerDraft,
  MentionItem,
  OrchestrationMode,
  ORCHESTRATION_MODE_LABELS,
  PromptComposerProps,
  replaceTriggerToken,
  saveComposerDraft,
  SLASH_COMMANDS,
  SlashCommandItem,
} from './composerTypes';
import { MentionPopover } from './MentionPopover';
import { SlashCommandMenu } from './SlashCommandMenu';
import { useLayoutStore } from '@/store/layoutStore';
import { readPromptHistory } from './promptHistory';

export function PromptComposer({
  draft: controlledDraft,
  onDraftChange,
  mode: controlledMode,
  onModeChange,
  selectedProjectId = '',
  onSubmit,
  isSubmitting = false,
  sessionKey,
  placeholder = 'Descreva a tarefa ou comando (/review, /swarm, @agente)...',
  submitLabel = 'Enviar',
  submitDisabled = false,
  disabled = false,
  hideModeSelector = false,
  mentionItems,
  slashCommands,
  onSlashCommand,
  renderAttachControl,
  renderDictationControl,
  attachmentChips,
  textareaAriaLabel = 'Descreva a tarefa para o coordenador',
  visibleTextareaLabel = false,
  className = '',
  toolbarStart,
  completion,
}: PromptComposerProps) {
  const historyEnabled = useLayoutStore((s) => s.promptHistoryEnabled);
  const keyboardHintsVisible = useLayoutStore((s) => s.keyboardHintsVisible);
  const suggestionsEnabled = useLayoutStore((s) => s.suggestionsEnabled);
  const historyCursor = useRef(-1);
  const historyDraft = useRef('');
  const [historyRevision, setHistoryRevision] = useState(0);
  const [focused, setFocused] = useState(false);
  const [composing, setComposing] = useState(false);
  const [dismissedCompletion, setDismissedCompletion] = useState('');
  const ghostRef = useRef<HTMLDivElement>(null);
  const effectiveSessionKey =
    sessionKey?.trim() || (selectedProjectId ? `project:${selectedProjectId}` : 'default');
  const isControlled = controlledDraft !== undefined && onDraftChange !== undefined;

  const [internalDraft, setInternalDraft] = useState<string>(() =>
    loadComposerDraft(effectiveSessionKey),
  );
  const [internalMode, setInternalMode] = useState<OrchestrationMode>('relay');
  const [cursorPos, setCursorPos] = useState<number>(0);
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [dismissedAtPos, setDismissedAtPos] = useState<number | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const prevSessionKeyRef = useRef<string>(effectiveSessionKey);
  const previousProjectRef = useRef(selectedProjectId);
  const didHydrateMountRef = useRef<boolean>(false);
  const listboxId = useId();

  const currentDraft = isControlled ? controlledDraft : internalDraft;
  const currentMode = controlledMode ?? internalMode;
  const history = useMemo(
    () => (historyEnabled ? readPromptHistory(effectiveSessionKey) : []),
    // Read after a successful send clears the draft as well as after an explicit clear.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [effectiveSessionKey, currentDraft, historyRevision, historyEnabled],
  );
  useEffect(() => {
    const clear = () => {
      setHistoryRevision((n) => n + 1);
      historyCursor.current = -1;
    };
    window.addEventListener('hydra-history-cleared', clear);
    return () => window.removeEventListener('hydra-history-cleared', clear);
  }, []);
  useEffect(() => {
    historyCursor.current = -1;
    historyDraft.current = '';
    setDismissedCompletion('');
  }, [effectiveSessionKey]);

  useEffect(() => {
    if (!didHydrateMountRef.current) {
      didHydrateMountRef.current = true;
      const saved = loadComposerDraft(effectiveSessionKey);
      if (isControlled && controlledDraft === '' && saved.length > 0) {
        onDraftChange(saved);
      }
      return;
    }

    if (prevSessionKeyRef.current !== effectiveSessionKey) {
      // The initial project can arrive after the user has begun typing. Carry
      // that unassigned draft forward; explicit project switches still restore
      // the separate draft belonging to the selected project.
      const assigningFirstProject = !previousProjectRef.current && Boolean(selectedProjectId);
      const restored =
        assigningFirstProject && currentDraft.trim()
          ? currentDraft
          : loadComposerDraft(effectiveSessionKey);
      if (assigningFirstProject && currentDraft.trim()) {
        saveComposerDraft(effectiveSessionKey, currentDraft);
        clearComposerDraft(prevSessionKeyRef.current);
      }
      prevSessionKeyRef.current = effectiveSessionKey;
      setInternalDraft(restored);
      setActiveIndex(0);
      setDismissedAtPos(null);
      if (onDraftChange) {
        onDraftChange(restored);
      }
    }
    previousProjectRef.current = selectedProjectId;
  }, [
    effectiveSessionKey,
    isControlled,
    controlledDraft,
    onDraftChange,
    selectedProjectId,
    currentDraft,
  ]);

  useEffect(() => {
    if (isControlled && prevSessionKeyRef.current === effectiveSessionKey) {
      saveComposerDraft(effectiveSessionKey, controlledDraft);
    }
  }, [isControlled, controlledDraft, effectiveSessionKey]);

  const updateDraft = (nextValue: string, nextCursor?: number, fromHistory = false) => {
    if (!fromHistory) historyCursor.current = -1;
    saveComposerDraft(effectiveSessionKey, nextValue);
    if (!isControlled) {
      setInternalDraft(nextValue);
    }
    onDraftChange?.(nextValue);
    setDismissedAtPos(null);
    setActiveIndex(0);
    if (nextCursor !== undefined) {
      setCursorPos(nextCursor);
      const previousFocus = document.activeElement;
      requestAnimationFrame(() => {
        if (textareaRef.current && document.activeElement === previousFocus) {
          textareaRef.current.focus();
          textareaRef.current.setSelectionRange(nextCursor, nextCursor);
        }
      });
    }
  };

  const handleModeChange = (nextMode: OrchestrationMode) => {
    if (controlledMode === undefined) {
      setInternalMode(nextMode);
    }
    onModeChange?.(nextMode);
  };

  const trigger: ComposerTriggerMatch | null = useMemo(() => {
    const detected = detectComposerTrigger(currentDraft, cursorPos);
    if (!detected) {
      return null;
    }
    if (dismissedAtPos !== null && dismissedAtPos === detected.startIndex) {
      return null;
    }
    return detected;
  }, [currentDraft, cursorPos, dismissedAtPos]);

  const allMentions = useMemo(
    () => (mentionItems && mentionItems.length > 0 ? mentionItems : DEFAULT_MENTION_ITEMS),
    [mentionItems],
  );
  const allCommands = useMemo(
    () => (slashCommands && slashCommands.length > 0 ? slashCommands : SLASH_COMMANDS),
    [slashCommands],
  );

  const filteredMentions = useMemo(() => {
    if (trigger?.kind !== 'mention') {
      return [];
    }
    const q = trigger.query.trim().toLowerCase();
    if (!q) {
      return allMentions;
    }
    return allMentions.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.id.toLowerCase().includes(q) ||
        (item.description?.toLowerCase().includes(q) ?? false),
    );
  }, [trigger, allMentions]);

  const filteredCommands = useMemo(() => {
    if (trigger?.kind !== 'slash') {
      return [];
    }
    const q = trigger.query.trim().toLowerCase();
    if (!q) {
      return allCommands;
    }
    return allCommands.filter(
      (cmd) =>
        cmd.command.slice(1).toLowerCase().includes(q) || cmd.label.toLowerCase().includes(q),
    );
  }, [trigger, allCommands]);

  const isMentionOpen = trigger?.kind === 'mention' && filteredMentions.length > 0;
  const isSlashOpen = trigger?.kind === 'slash' && filteredCommands.length > 0;
  const isPopoverOpen = isMentionOpen || isSlashOpen;
  const activeOptionCount = isMentionOpen
    ? filteredMentions.length
    : isSlashOpen
      ? filteredCommands.length
      : 0;
  const candidate =
    currentDraft.length >= 2
      ? ([...history]
          .reverse()
          .find(
            (text) =>
              text.toLocaleLowerCase().startsWith(currentDraft.toLocaleLowerCase()) &&
              text !== currentDraft,
          ) ?? completion)
      : completion;
  const ghost =
    suggestionsEnabled &&
    focused &&
    !composing &&
    !isPopoverOpen &&
    !disabled &&
    !isSubmitting &&
    cursorPos === currentDraft.length &&
    candidate &&
    candidate !== dismissedCompletion &&
    candidate.toLocaleLowerCase().startsWith(currentDraft.toLocaleLowerCase()) &&
    candidate !== currentDraft
      ? candidate.slice(currentDraft.length)
      : '';
  const safeActiveIndex =
    activeOptionCount > 0
      ? ((activeIndex % activeOptionCount) + activeOptionCount) % activeOptionCount
      : 0;

  const handleSelectMention = (item: MentionItem) => {
    if (!trigger) {
      return;
    }
    const replacement = `@${item.insertText ?? item.label}`;
    const { nextText, nextCursor } = replaceTriggerToken(
      currentDraft,
      trigger.startIndex,
      trigger.endIndex,
      replacement,
    );
    updateDraft(nextText, nextCursor);
  };

  const handleSelectSlashCommand = (cmd: SlashCommandItem) => {
    if (!trigger) {
      return;
    }
    if (cmd.command === '/limpar') {
      clearComposerDraft(effectiveSessionKey);
      updateDraft('', 0);
      setStatusNotice('Rascunho limpo.');
      onSlashCommand?.(cmd);
      return;
    }
    if (cmd.command === '/swarm') {
      handleModeChange('swarm');
      setStatusNotice('Modo alterado para Swarm.');
      const handled = onSlashCommand?.(cmd);
      if (handled !== true) {
        const before = currentDraft.slice(0, trigger.startIndex);
        const after = currentDraft.slice(trigger.endIndex).replace(/^\s+/, '');
        const cleaned = `${before}${after}`;
        updateDraft(cleaned, before.length);
      }
      return;
    }

    const handled = onSlashCommand?.(cmd);
    if (handled === true) {
      const before = currentDraft.slice(0, trigger.startIndex);
      const after = currentDraft.slice(trigger.endIndex).replace(/^\s+/, '');
      updateDraft(`${before}${after}`, before.length);
      return;
    }

    const { nextText, nextCursor } = replaceTriggerToken(
      currentDraft,
      trigger.startIndex,
      trigger.endIndex,
      cmd.command,
    );
    updateDraft(nextText, nextCursor);
  };

  const triggerSubmit = () => {
    if (disabled || submitDisabled || isSubmitting || currentDraft.trim().length === 0) {
      return;
    }
    const payload = currentDraft;
    onSubmit?.(payload);
    if (!isControlled) {
      clearComposerDraft(effectiveSessionKey);
      setInternalDraft('');
      setCursorPos(0);
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const nextValue = e.target.value;
    const nextPos = e.target.selectionStart ?? nextValue.length;
    setStatusNotice(null);
    setCursorPos(nextPos);
    updateDraft(nextValue);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || composing) return;
    if (isPopoverOpen && activeOptionCount > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((prev) => (prev + 1) % activeOptionCount);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((prev) => (prev - 1 + activeOptionCount) % activeOptionCount);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        if (trigger) {
          setDismissedAtPos(trigger.startIndex);
        }
        return;
      }
      if ((e.key === 'Enter' && !e.shiftKey) || (e.key === 'Tab' && !e.shiftKey)) {
        e.preventDefault();
        if (isMentionOpen) {
          handleSelectMention(filteredMentions[safeActiveIndex]);
        } else if (isSlashOpen && e.key === 'Tab' && trigger) {
          const { nextText, nextCursor } = replaceTriggerToken(
            currentDraft,
            trigger.startIndex,
            trigger.endIndex,
            filteredCommands[safeActiveIndex].command,
          );
          updateDraft(nextText, nextCursor);
        } else if (isSlashOpen) {
          handleSelectSlashCommand(filteredCommands[safeActiveIndex]);
        }
        return;
      }
    }

    const noSelection = e.currentTarget.selectionStart === e.currentTarget.selectionEnd;
    if (!e.shiftKey && !e.altKey && !e.metaKey && !e.ctrlKey && noSelection) {
      if (e.key === 'Tab' && ghost) {
        e.preventDefault();
        updateDraft(currentDraft + ghost, (currentDraft + ghost).length);
        return;
      }
      if (e.key === 'Escape' && ghost) {
        e.preventDefault();
        setDismissedCompletion(candidate ?? '');
        return;
      }
      const atFirstLine = !currentDraft.slice(0, e.currentTarget.selectionStart).includes('\n');
      const atLastLine = !currentDraft.slice(e.currentTarget.selectionEnd).includes('\n');
      if (
        history.length &&
        ((e.key === 'ArrowUp' && atFirstLine) ||
          (e.key === 'ArrowDown' && atLastLine && historyCursor.current >= 0))
      ) {
        e.preventDefault();
        if (historyCursor.current < 0) historyDraft.current = currentDraft;
        const next = Math.min(
          history.length - 1,
          Math.max(-1, historyCursor.current + (e.key === 'ArrowUp' ? 1 : -1)),
        );
        historyCursor.current = next;
        const text = next < 0 ? historyDraft.current : history[history.length - 1 - next];
        updateDraft(text, text.length, true);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      triggerSubmit();
    }
  };

  const syncCursorPosition = () => {
    if (textareaRef.current) {
      setCursorPos(textareaRef.current.selectionStart ?? currentDraft.length);
    }
  };

  return (
    <div
      data-testid="prompt-composer"
      data-session-key={effectiveSessionKey}
      className={`w-full ${className}`}
    >
      {isMentionOpen ? (
        <MentionPopover
          items={filteredMentions}
          activeIndex={safeActiveIndex}
          onSelect={handleSelectMention}
          listboxId={`${listboxId}-mentions`}
        />
      ) : null}

      {isSlashOpen ? (
        <SlashCommandMenu
          commands={filteredCommands}
          activeIndex={safeActiveIndex}
          onSelect={handleSelectSlashCommand}
          listboxId={`${listboxId}-commands`}
        />
      ) : null}

      <div className="rounded-2xl border border-[#303030] bg-[#202020] p-3 shadow-lg">
        {attachmentChips ? (
          <div data-testid="composer-attachment-chips" className="mb-2 flex flex-wrap gap-1.5">
            {attachmentChips}
          </div>
        ) : null}

        <label
          htmlFor={`${listboxId}-textarea`}
          className={visibleTextareaLabel ? 'mb-1 block text-sm font-semibold' : 'sr-only'}
        >
          {textareaAriaLabel}
        </label>
        <div className="composer-input-wrap">
          {ghost && (
            <div ref={ghostRef} aria-hidden="true" className="composer-ghost">
              <span>{currentDraft}</span>
              {ghost}
            </div>
          )}
          <textarea
            ref={textareaRef}
            id={`${listboxId}-textarea`}
            rows={3}
            disabled={disabled || isSubmitting}
            value={currentDraft}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onClick={syncCursorPosition}
            onKeyUp={syncCursorPosition}
            onFocus={() => {
              setFocused(true);
              syncCursorPosition();
            }}
            onBlur={() => setFocused(false)}
            onCompositionStart={() => setComposing(true)}
            onCompositionEnd={() => setComposing(false)}
            onScroll={(e) => {
              if (ghostRef.current) ghostRef.current.scrollTop = e.currentTarget.scrollTop;
            }}
            placeholder={placeholder}
            aria-label={textareaAriaLabel}
            role={isPopoverOpen ? 'combobox' : undefined}
            aria-autocomplete={isPopoverOpen ? 'list' : ghost ? 'inline' : undefined}
            aria-describedby={keyboardHintsVisible ? `${listboxId}-hint` : undefined}
            aria-haspopup={isPopoverOpen ? 'listbox' : undefined}
            aria-expanded={isPopoverOpen ? true : undefined}
            aria-controls={
              isMentionOpen
                ? `${listboxId}-mentions`
                : isSlashOpen
                  ? `${listboxId}-commands`
                  : undefined
            }
            aria-activedescendant={
              isMentionOpen
                ? `${listboxId}-mentions-opt-${safeActiveIndex}`
                : isSlashOpen
                  ? `${listboxId}-commands-opt-${safeActiveIndex}`
                  : undefined
            }
            className={`composer-textarea w-full resize-y rounded-lg border border-transparent bg-transparent px-2 py-2 text-sm text-[#E8E8E8] placeholder:text-[#969696] disabled:opacity-60 ${visibleTextareaLabel ? 'min-h-24 border-[var(--border)] bg-[var(--bg-rail)]' : ''}`}
          />
        </div>
        <p hidden={!keyboardHintsVisible} id={`${listboxId}-hint`} className="composer-key-hint">
          {ghost
            ? 'Tab aceita a sugestão · Esc dispensa'
            : historyEnabled
              ? '↑ ↓ histórico nos limites do campo · Shift+Enter nova linha'
              : 'Shift+Enter nova linha'}
        </p>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[#303030] pt-2.5">
          <div className="flex flex-wrap items-center gap-2">
            {toolbarStart}
            {!hideModeSelector ? (
              <>
                <label htmlFor={`${listboxId}-mode`} className="sr-only">
                  Modo de orquestração
                </label>
                <select
                  id={`${listboxId}-mode`}
                  disabled={disabled || isSubmitting}
                  value={currentMode}
                  onChange={(e) => handleModeChange(e.target.value as OrchestrationMode)}
                  className="min-h-9 rounded-lg border border-[#666] bg-[#141414] px-2.5 py-1 text-sm text-[#E8E8E8] [@media(pointer:coarse)]:min-h-[44px]"
                >
                  {Object.entries(ORCHESTRATION_MODE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </>
            ) : null}

            {renderAttachControl !== undefined ? (
              renderAttachControl
            ) : (
              <span
                title="Slot de anexos conectado na Onda 15 (T38)"
                className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#141414] px-2 py-1 text-[11px] text-[#969696]"
              >
                <Paperclip aria-hidden="true" className="h-3 w-3" />
                <span>Anexos</span>
              </span>
            )}

            {renderDictationControl !== undefined ? (
              renderDictationControl
            ) : (
              <span
                title="Slot de ditado revisável conectado na Onda 15 (T38)"
                className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#141414] px-2 py-1 text-[11px] text-[#969696]"
              >
                <Mic aria-hidden="true" className="h-3 w-3" />
                <span>Ditado</span>
              </span>
            )}
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            {statusNotice ? (
              <span role="status" className="text-[11px] text-[#969696]">
                {statusNotice}
              </span>
            ) : null}
            <button
              type="button"
              aria-label={isSubmitting ? 'Enviando...' : submitLabel}
              disabled={
                disabled || submitDisabled || isSubmitting || currentDraft.trim().length === 0
              }
              onClick={triggerSubmit}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3.5 py-1.5 text-sm font-semibold text-[#181818] transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 [@media(pointer:coarse)]:min-h-[44px]"
            >
              <Send aria-hidden="true" className="h-3.5 w-3.5" />
              <span>{isSubmitting ? 'Enviando...' : submitLabel}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
