import { Bot, FileCode2, FolderGit2 } from 'lucide-react';
import { MentionItem, MentionKind } from './composerTypes';

export interface MentionPopoverProps {
  items: MentionItem[];
  activeIndex: number;
  onSelect: (item: MentionItem) => void;
  listboxId: string;
}

const KIND_META: Record<MentionKind, { label: string; Icon: typeof FileCode2 }> = {
  file: { label: 'Arquivo', Icon: FileCode2 },
  workspace: { label: 'Workspace', Icon: FolderGit2 },
  agent: { label: 'Agente', Icon: Bot },
};

export function MentionPopover({
  items,
  activeIndex,
  onSelect,
  listboxId,
}: MentionPopoverProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div
      id={listboxId}
      role="listbox"
      aria-label="Menções de arquivos, workspaces e agentes"
      data-testid="mention-popover"
      className="mb-2 max-h-56 overflow-y-auto rounded-xl border border-[#303030] bg-[#1C1C1C] p-1.5 shadow-xl"
    >
      <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#969696]">
        Mencionar (@) · ↑↓ navegar · Enter selecionar · Esc fechar
      </div>
      {items.map((item, idx) => {
        const meta = KIND_META[item.kind];
        const Icon = meta.Icon;
        const isActive = idx === activeIndex;
        return (
          <button
            key={item.id}
            id={`${listboxId}-opt-${idx}`}
            type="button"
            role="option"
            aria-selected={isActive}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(item);
            }}
            className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
              isActive
                ? 'bg-[#282828] text-[#E8E8E8]'
                : 'text-[#E8E8E8] hover:bg-[#202020]'
            }`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />
              <div className="min-w-0">
                <p className="truncate font-mono text-xs text-[#E8E8E8]">@{item.label}</p>
                {item.description ? (
                  <p className="truncate text-[11px] text-[#969696]">{item.description}</p>
                ) : null}
              </div>
            </div>
            <span className="shrink-0 rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 text-[10px] text-[#969696]">
              {meta.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
