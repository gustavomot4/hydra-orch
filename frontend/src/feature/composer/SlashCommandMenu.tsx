import { TerminalSquare } from 'lucide-react';
import { SlashCommandItem } from './composerTypes';

export interface SlashCommandMenuProps {
  commands: SlashCommandItem[];
  activeIndex: number;
  onSelect: (command: SlashCommandItem) => void;
  listboxId: string;
}

export function SlashCommandMenu({
  commands,
  activeIndex,
  onSelect,
  listboxId,
}: SlashCommandMenuProps) {
  if (commands.length === 0) {
    return null;
  }

  return (
    <div
      id={listboxId}
      role="listbox"
      aria-label="Comandos rápidos"
      data-testid="slash-command-menu"
      className="mb-2 max-h-56 overflow-y-auto rounded-xl border border-[#303030] bg-[#1C1C1C] p-1.5 shadow-xl"
    >
      <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#969696]">
        Comandos (/) · ↑↓ navegar · Enter executar · Esc fechar
      </div>
      {commands.map((cmd, idx) => {
        const isActive = idx === activeIndex;
        return (
          <button
            key={cmd.command}
            id={`${listboxId}-opt-${idx}`}
            type="button"
            role="option"
            aria-selected={isActive}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(cmd);
            }}
            className={`flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
              isActive
                ? 'bg-[#282828] text-[#E8E8E8]'
                : 'text-[#E8E8E8] hover:bg-[#202020]'
            }`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <TerminalSquare aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />
              <div className="min-w-0">
                <p className="font-mono text-xs font-medium text-[#E8E8E8]">{cmd.command}</p>
                <p className="truncate text-[11px] text-[#969696]">{cmd.description}</p>
              </div>
            </div>
            <span className="shrink-0 text-[11px] text-[#969696]">{cmd.label}</span>
          </button>
        );
      })}
    </div>
  );
}
