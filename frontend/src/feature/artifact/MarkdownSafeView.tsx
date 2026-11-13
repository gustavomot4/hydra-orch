import { Fragment, ReactNode, useMemo } from 'react';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { isSafeMarkdownHref, sanitizeMarkdownText } from './artifactApi';

export interface MarkdownSafeViewProps {
  markdown: string;
  scriptStripped?: boolean;
  redacted?: boolean;
  className?: string;
}

const INLINE_TOKEN_RE = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let tokenIdx = 0;

  INLINE_TOKEN_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = INLINE_TOKEN_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const key = `${keyPrefix}-${tokenIdx}`;
    tokenIdx += 1;

    if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code
          key={key}
          className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[12px] text-[#E8E8E8]"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(
        <strong key={key} className="font-semibold text-[#E8E8E8]">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      parts.push(
        <em key={key} className="italic text-[#E8E8E8]">
          {token.slice(1, -1)}
        </em>,
      );
    } else if (token.startsWith('[')) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (linkMatch) {
        const label = linkMatch[1];
        const href = linkMatch[2].trim();
        if (isSafeMarkdownHref(href)) {
          parts.push(
            <a
              key={key}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#60A5FA] underline decoration-[#60A5FA]/50 hover:text-[#93C5FD]"
            >
              {label}
            </a>,
          );
        } else {
          parts.push(
            <span
              key={key}
              title="URI bloqueada por política anti-XSS"
              className="rounded bg-[#EF4444]/10 px-1 text-[#FCA5A5] line-through"
            >
              {label}
            </span>,
          );
        }
      } else {
        parts.push(token);
      }
    } else {
      parts.push(token);
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function renderMarkdownBlocks(markdown: string): ReactNode[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks: ReactNode[] = [];
  let idx = 0;
  let blockKey = 0;

  while (idx < lines.length) {
    const line = lines[idx];

    if (!line.trim()) {
      idx += 1;
      continue;
    }

    // Fenced code block
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim();
      const codeLines: string[] = [];
      idx += 1;
      while (idx < lines.length && !lines[idx].trim().startsWith('```')) {
        codeLines.push(lines[idx]);
        idx += 1;
      }
      if (idx < lines.length) {
        idx += 1;
      }
      blocks.push(
        <div
          key={`block-${blockKey}`}
          className="overflow-x-auto rounded-xl border border-[#303030] bg-[#141414]"
        >
          {lang ? (
            <div className="border-b border-[#303030] bg-[#181818] px-3 py-1 font-mono text-[11px] text-[#969696]">
              {lang}
            </div>
          ) : null}
          <pre className="p-3 font-mono text-xs leading-relaxed text-[#E8E8E8]">
            <code>{codeLines.join('\n')}</code>
          </pre>
        </div>,
      );
      blockKey += 1;
      continue;
    }

    // Horizontal rule
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      blocks.push(<hr key={`block-${blockKey}`} className="border-[#303030]" />);
      blockKey += 1;
      idx += 1;
      continue;
    }

    // Headings
    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const content = renderInlineMarkdown(headingMatch[2], `h-${blockKey}`);
      const sizeClass =
        level === 1
          ? 'text-lg font-semibold text-[#E8E8E8]'
          : level === 2
            ? 'text-base font-semibold text-[#E8E8E8]'
            : 'text-sm font-semibold text-[#E8E8E8]';
      blocks.push(
        <div key={`block-${blockKey}`} role="heading" aria-level={level} className={sizeClass}>
          {content}
        </div>,
      );
      blockKey += 1;
      idx += 1;
      continue;
    }

    // Blockquote
    if (line.trimStart().startsWith('>')) {
      const quoteLines: string[] = [];
      while (idx < lines.length && lines[idx].trimStart().startsWith('>')) {
        quoteLines.push(lines[idx].trimStart().replace(/^>\s?/, ''));
        idx += 1;
      }
      blocks.push(
        <blockquote
          key={`block-${blockKey}`}
          className="border-l-2 border-[#3B82F6] bg-[#181818] px-3 py-2 text-xs text-[#969696]"
        >
          {quoteLines.map((qLine, qIdx) => (
            <p key={qIdx}>{renderInlineMarkdown(qLine, `q-${blockKey}-${qIdx}`)}</p>
          ))}
        </blockquote>,
      );
      blockKey += 1;
      continue;
    }

    // Unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (idx < lines.length && /^\s*[-*+]\s+/.test(lines[idx])) {
        items.push(lines[idx].replace(/^\s*[-*+]\s+/, ''));
        idx += 1;
      }
      blocks.push(
        <ul key={`block-${blockKey}`} className="list-disc space-y-1 pl-5 text-sm text-[#E8E8E8]">
          {items.map((item, itemIdx) => (
            <li key={itemIdx}>{renderInlineMarkdown(item, `ul-${blockKey}-${itemIdx}`)}</li>
          ))}
        </ul>,
      );
      blockKey += 1;
      continue;
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (idx < lines.length && /^\s*\d+\.\s+/.test(lines[idx])) {
        items.push(lines[idx].replace(/^\s*\d+\.\s+/, ''));
        idx += 1;
      }
      blocks.push(
        <ol key={`block-${blockKey}`} className="list-decimal space-y-1 pl-5 text-sm text-[#E8E8E8]">
          {items.map((item, itemIdx) => (
            <li key={itemIdx}>{renderInlineMarkdown(item, `ol-${blockKey}-${itemIdx}`)}</li>
          ))}
        </ol>,
      );
      blockKey += 1;
      continue;
    }

    // Pipe table
    if (line.includes('|') && idx + 1 < lines.length && /^\s*\|?[\s:-]+\|/.test(lines[idx + 1])) {
      const headerCells = line
        .split('|')
        .map((c) => c.trim())
        .filter((c, cIdx, arr) => !(c === '' && (cIdx === 0 || cIdx === arr.length - 1)));
      idx += 2;
      const bodyRows: string[][] = [];
      while (idx < lines.length && lines[idx].includes('|') && lines[idx].trim()) {
        const rowCells = lines[idx]
          .split('|')
          .map((c) => c.trim())
          .filter((c, cIdx, arr) => !(c === '' && (cIdx === 0 || cIdx === arr.length - 1)));
        bodyRows.push(rowCells);
        idx += 1;
      }
      blocks.push(
        <div key={`block-${blockKey}`} className="overflow-x-auto rounded-lg border border-[#303030]">
          <table className="w-full border-collapse text-left text-xs">
            <thead className="bg-[#181818] text-[#E8E8E8]">
              <tr>
                {headerCells.map((cell, cellIdx) => (
                  <th key={cellIdx} className="border-b border-[#303030] px-3 py-2 font-semibold">
                    {renderInlineMarkdown(cell, `th-${blockKey}-${cellIdx}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, rIdx) => (
                <tr key={rIdx} className="border-b border-[#303030]/60 last:border-b-0">
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-1.5 text-[#E8E8E8]">
                      {renderInlineMarkdown(cell, `td-${blockKey}-${rIdx}-${cIdx}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      blockKey += 1;
      continue;
    }

    // Paragraph
    const paraLines: string[] = [];
    while (
      idx < lines.length &&
      lines[idx].trim() &&
      !lines[idx].trim().startsWith('```') &&
      !/^(#{1,6})\s+/.test(lines[idx]) &&
      !lines[idx].trimStart().startsWith('>') &&
      !/^\s*[-*+]\s+/.test(lines[idx]) &&
      !/^\s*\d+\.\s+/.test(lines[idx])
    ) {
      paraLines.push(lines[idx]);
      idx += 1;
    }
    blocks.push(
      <p key={`block-${blockKey}`} className="text-sm leading-relaxed text-[#E8E8E8]">
        {paraLines.map((pLine, pIdx) => (
          <Fragment key={pIdx}>
            {pIdx > 0 ? ' ' : null}
            {renderInlineMarkdown(pLine, `p-${blockKey}-${pIdx}`)}
          </Fragment>
        ))}
      </p>,
    );
    blockKey += 1;
  }

  return blocks;
}

export function MarkdownSafeView({
  markdown,
  scriptStripped = false,
  redacted = false,
  className = '',
}: MarkdownSafeViewProps) {
  const { sanitized, strippedOnClient } = useMemo(
    () => sanitizeMarkdownText(markdown),
    [markdown],
  );
  const blocks = useMemo(() => renderMarkdownBlocks(sanitized), [sanitized]);
  const anyScriptStripped = scriptStripped || strippedOnClient;

  return (
    <div
      data-testid="markdown-safe-view"
      className={`space-y-3 rounded-xl border border-[#303030] bg-[#202020] p-4 ${className}`}
    >
      {anyScriptStripped || redacted ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-[#303030] pb-2.5 text-[11px]">
          {anyScriptStripped ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-[#F59E0B]/40 bg-[#F59E0B]/10 px-2 py-0.5 text-[#FCD34D]">
              <ShieldAlert aria-hidden="true" className="h-3 w-3" />
              <span>Conteúdo ativo/script bloqueado por política anti-XSS</span>
            </span>
          ) : null}
          {redacted ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-[#22C55E]/40 bg-[#22C55E]/10 px-2 py-0.5 text-[#4ADE80]">
              <ShieldCheck aria-hidden="true" className="h-3 w-3" />
              <span>Segredos redigidos</span>
            </span>
          ) : null}
        </div>
      ) : null}

      {blocks.length === 0 ? (
        <p className="text-xs text-[#969696]">Documento Markdown vazio.</p>
      ) : (
        <div className="space-y-3">{blocks}</div>
      )}
    </div>
  );
}
