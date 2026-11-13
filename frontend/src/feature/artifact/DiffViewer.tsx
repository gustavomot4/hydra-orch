import { useMemo, useState } from 'react';
import { Columns2, FileDiff, List } from 'lucide-react';
import { buildSideBySideRows, parseUnifiedDiff } from './artifactApi';

export type DiffLayoutMode = 'unified' | 'side-by-side';

export interface DiffViewerProps {
  diffText: string;
  filePath?: string;
  defaultLayout?: DiffLayoutMode;
  className?: string;
}

export function DiffViewer({
  diffText,
  filePath,
  defaultLayout = 'unified',
  className = '',
}: DiffViewerProps) {
  const [layout, setLayout] = useState<DiffLayoutMode>(defaultLayout);
  const parsed = useMemo(() => parseUnifiedDiff(diffText), [diffText]);
  const sideBySideRows = useMemo(() => buildSideBySideRows(parsed.rows), [parsed.rows]);

  return (
    <div
      data-testid="diff-viewer"
      data-diff-layout={layout}
      className={`flex flex-col overflow-hidden rounded-xl border border-[#303030] bg-[#141414] ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#303030] bg-[#1C1C1C] px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileDiff aria-hidden="true" className="h-4 w-4 shrink-0 text-[#969696]" />
          <span className="truncate font-mono text-xs font-medium text-[#E8E8E8]">
            {filePath ?? 'Diff'}
          </span>
          <span className="rounded border border-[#22C55E]/40 bg-[#22C55E]/10 px-1.5 py-0.5 font-mono text-[11px] text-[#4ADE80]">
            +{parsed.additions}
          </span>
          <span className="rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-1.5 py-0.5 font-mono text-[11px] text-[#FCA5A5]">
            -{parsed.deletions}
          </span>
        </div>

        <div role="group" aria-label="Modo de exibição do diff" className="flex items-center gap-1">
          <button
            type="button"
            aria-pressed={layout === 'unified'}
            onClick={() => setLayout('unified')}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
              layout === 'unified'
                ? 'border-[#3B82F6]/60 bg-[#202020] text-[#E8E8E8]'
                : 'border-[#303030] bg-[#181818] text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
            }`}
          >
            <List aria-hidden="true" className="h-3 w-3" />
            <span>Unificado</span>
          </button>
          <button
            type="button"
            aria-pressed={layout === 'side-by-side'}
            onClick={() => setLayout('side-by-side')}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
              layout === 'side-by-side'
                ? 'border-[#3B82F6]/60 bg-[#202020] text-[#E8E8E8]'
                : 'border-[#303030] bg-[#181818] text-[#969696] hover:bg-[#282828] hover:text-[#E8E8E8]'
            }`}
          >
            <Columns2 aria-hidden="true" className="h-3 w-3" />
            <span>Lado a lado</span>
          </button>
        </div>
      </div>

      {parsed.rows.length === 0 ? (
        <p className="p-4 text-xs text-[#969696]">Nenhuma alteração de diff para exibir.</p>
      ) : layout === 'unified' ? (
        <div className="overflow-x-auto font-mono text-xs">
          <table className="w-full border-collapse">
            <tbody>
              {parsed.rows.map((row, idx) => {
                const rowClasses =
                  row.kind === 'add'
                    ? 'bg-[#22C55E]/10 text-[#86EFAC]'
                    : row.kind === 'del'
                      ? 'bg-[#EF4444]/10 text-[#FCA5A5]'
                      : row.kind === 'hunk'
                        ? 'bg-[#3B82F6]/10 text-[#93C5FD]'
                        : row.kind === 'meta'
                          ? 'bg-[#181818] text-[#969696]'
                          : 'text-[#E8E8E8]';
                const marker = row.kind === 'add' ? '+' : row.kind === 'del' ? '-' : ' ';

                return (
                  <tr key={idx} className={rowClasses}>
                    <td className="w-11 select-none border-r border-[#303030]/60 px-2 py-0.5 text-right tabular-nums text-[#969696]">
                      {row.oldLine ?? ''}
                    </td>
                    <td className="w-11 select-none border-r border-[#303030]/60 px-2 py-0.5 text-right tabular-nums text-[#969696]">
                      {row.newLine ?? ''}
                    </td>
                    <td className="w-5 select-none px-1.5 py-0.5 text-center">{marker}</td>
                    <td className="whitespace-pre px-2 py-0.5">{row.text}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="overflow-x-auto font-mono text-xs">
          <table className="w-full border-collapse table-fixed">
            <thead>
              <tr className="border-b border-[#303030] bg-[#181818] text-[11px] text-[#969696]">
                <th className="w-11 px-2 py-1 text-right font-normal">Orig.</th>
                <th className="px-2 py-1 text-left font-medium text-[#E8E8E8]">Anterior</th>
                <th className="w-11 border-l border-[#303030] px-2 py-1 text-right font-normal">
                  Novo
                </th>
                <th className="px-2 py-1 text-left font-medium text-[#E8E8E8]">Modificado</th>
              </tr>
            </thead>
            <tbody>
              {sideBySideRows.map((row, idx) => {
                if (row.leftKind === 'hunk' || row.leftKind === 'meta') {
                  return (
                    <tr
                      key={idx}
                      className={
                        row.leftKind === 'hunk'
                          ? 'bg-[#3B82F6]/10 text-[#93C5FD]'
                          : 'bg-[#181818] text-[#969696]'
                      }
                    >
                      <td colSpan={4} className="whitespace-pre px-3 py-0.5">
                        {row.leftText}
                      </td>
                    </tr>
                  );
                }

                const leftClass =
                  row.leftKind === 'del'
                    ? 'bg-[#EF4444]/10 text-[#FCA5A5]'
                    : row.leftKind === 'empty'
                      ? 'bg-[#181818]/60 text-[#969696]'
                      : 'text-[#E8E8E8]';
                const rightClass =
                  row.rightKind === 'add'
                    ? 'bg-[#22C55E]/10 text-[#86EFAC]'
                    : row.rightKind === 'empty'
                      ? 'bg-[#181818]/60 text-[#969696]'
                      : 'text-[#E8E8E8]';

                return (
                  <tr key={idx} className="border-b border-[#303030]/40 last:border-b-0">
                    <td
                      className={`select-none border-r border-[#303030]/60 px-2 py-0.5 text-right tabular-nums text-[#969696] ${leftClass}`}
                    >
                      {row.leftLine ?? ''}
                    </td>
                    <td className={`whitespace-pre-wrap break-all px-2 py-0.5 ${leftClass}`}>
                      {row.leftText ?? ''}
                    </td>
                    <td
                      className={`select-none border-l border-r border-[#303030]/60 px-2 py-0.5 text-right tabular-nums text-[#969696] ${rightClass}`}
                    >
                      {row.rightLine ?? ''}
                    </td>
                    <td className={`whitespace-pre-wrap break-all px-2 py-0.5 ${rightClass}`}>
                      {row.rightText ?? ''}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
