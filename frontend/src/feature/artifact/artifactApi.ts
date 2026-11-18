import { ControlPlaneClient } from '@/hook/useControlPlaneClient';

export type PreviewKind = 'markdown' | 'text' | 'diff' | 'image' | 'pdf' | 'unsupported';
export type PreviewStatus = 'ok' | 'unsupported_media_type';

export interface RunArtifactItem {
  id: string;
  artifact_id: string;
  run_id: string;
  attempt_id: string | null;
  relative_path: string;
  kind: string;
  sha256: string;
  size_bytes: number;
  created_at: string;
}

export interface ArtifactPreviewResult {
  artifact_id?: string;
  run_id?: string;
  rel_path: string;
  kind: PreviewKind;
  render_mode: PreviewKind;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  supported: boolean;
  status: PreviewStatus;
  content: string | null;
  sanitized_markdown: string | null;
  content_base64: string | null;
  script_stripped: boolean;
  redacted: boolean;
  reason: string | null;
}

export const SAFE_IMAGE_MIME_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
]);

export async function listRunArtifacts(
  client: ControlPlaneClient,
  runId: string,
  kind?: string,
): Promise<RunArtifactItem[]> {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return client.request<RunArtifactItem[]>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/artifacts${qs}`,
  );
}

export async function getArtifactPreview(
  client: ControlPlaneClient,
  runId: string,
  artifactId: string,
  maxBytes?: number,
): Promise<ArtifactPreviewResult> {
  const qs =
    typeof maxBytes === 'number' && Number.isFinite(maxBytes)
      ? `?max_bytes=${encodeURIComponent(String(Math.round(maxBytes)))}`
      : '';
  return client.request<ArtifactPreviewResult>(
    `/v1/control-plane/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}/content${qs}`,
  );
}

const ACTIVE_TAG_RE = /<\s*(\/?)\s*(script|iframe|object|embed|svg|math)\b[^<>]*>/gi;

function stripActiveTags(raw: string): string {
  // Index closing tags in reverse once. Repeated unmatched openings must not
  // trigger a separate scan of the remaining input for each opening.
  const tags = [...raw.matchAll(ACTIVE_TAG_RE)];
  const endByName = new Map<string, number>();
  const ranges = tags.map(() => 0);
  for (let index = tags.length - 1; index >= 0; index -= 1) {
    const tag = tags[index];
    const name = tag[2].toLowerCase();
    const end = tag.index + tag[0].length;
    if (tag[1]) endByName.set(name, end);
    ranges[index] = tag[1] || /\/\s*>$/.test(tag[0]) ? end : (endByName.get(name) ?? end);
  }

  const output: string[] = [];
  let cursor = 0;
  tags.forEach((tag, index) => {
    if (tag.index < cursor) return;
    output.push(raw.slice(cursor, tag.index));
    cursor = ranges[index];
  });
  output.push(raw.slice(cursor));
  return output.join('');
}

const INLINE_EVENT_HANDLER_RE = /(?<=[\s<])on[a-z]{1,32}\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi;
const DANGEROUS_MD_LINK_RE =
  /(\]\(\s*)(?:javascript\s*:|vbscript\s*:|data\s*:\s*text\/html\b)[^)\]\r\n]*\)/gi;

export function sanitizeMarkdownText(raw: string): {
  sanitized: string;
  strippedOnClient: boolean;
} {
  let out = stripActiveTags(raw);
  out = out.replace(INLINE_EVENT_HANDLER_RE, '');
  out = out.replace(DANGEROUS_MD_LINK_RE, '$1#blocked-uri)');
  return {
    sanitized: out,
    strippedOnClient: out !== raw,
  };
}

export function isSafeMarkdownHref(rawUrl: string): boolean {
  const trimmed = rawUrl.trim();
  if (!trimmed || trimmed === '#blocked-uri' || /[\\\p{Cc}]/u.test(trimmed) || trimmed.startsWith('//')) {
    return false;
  }
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith('javascript:') ||
    lower.startsWith('vbscript:') ||
    lower.startsWith('data:')
  ) {
    return false;
  }
  return (
    lower.startsWith('https://') ||
    lower.startsWith('http://') ||
    lower.startsWith('mailto:') ||
    trimmed.startsWith('#') ||
    trimmed.startsWith('/') ||
    trimmed.startsWith('./') ||
    trimmed.startsWith('../')
  );
}

export function formatByteSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return '—';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export type DiffRowKind = 'context' | 'add' | 'del' | 'hunk' | 'meta';

export interface DiffLineRow {
  kind: DiffRowKind;
  oldLine: number | null;
  newLine: number | null;
  text: string;
}

export interface DiffSideBySideRow {
  leftLine: number | null;
  leftText: string | null;
  leftKind: 'context' | 'del' | 'empty' | 'hunk' | 'meta';
  rightLine: number | null;
  rightText: string | null;
  rightKind: 'context' | 'add' | 'empty' | 'hunk' | 'meta';
}

export interface ParsedDiffStats {
  rows: DiffLineRow[];
  additions: number;
  deletions: number;
}

const HUNK_HEADER_RE = /^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/;

export function parseUnifiedDiff(diffText: string): ParsedDiffStats {
  const normalized = diffText.replace(/\r\n/g, '\n');
  if (!normalized.trim()) {
    return { rows: [], additions: 0, deletions: 0 };
  }

  const lines = normalized.split('\n');
  if (lines[lines.length - 1] === '') {
    lines.pop();
  }

  const rows: DiffLineRow[] = [];
  let oldCursor = 1;
  let newCursor = 1;
  let additions = 0;
  let deletions = 0;
  let seenHunk = false;

  for (const line of lines) {
    const hunkMatch = HUNK_HEADER_RE.exec(line);
    if (hunkMatch) {
      seenHunk = true;
      oldCursor = Number.parseInt(hunkMatch[1], 10);
      newCursor = Number.parseInt(hunkMatch[2], 10);
      rows.push({ kind: 'hunk', oldLine: null, newLine: null, text: line });
      continue;
    }

    if (
      line.startsWith('diff --git ') ||
      line.startsWith('index ') ||
      line.startsWith('--- ') ||
      line.startsWith('+++ ') ||
      line.startsWith('\\ No newline')
    ) {
      rows.push({ kind: 'meta', oldLine: null, newLine: null, text: line });
      continue;
    }

    if (line.startsWith('+')) {
      additions += 1;
      rows.push({ kind: 'add', oldLine: null, newLine: newCursor, text: line.slice(1) });
      newCursor += 1;
    } else if (line.startsWith('-')) {
      deletions += 1;
      rows.push({ kind: 'del', oldLine: oldCursor, newLine: null, text: line.slice(1) });
      oldCursor += 1;
    } else {
      const text = seenHunk && line.startsWith(' ') ? line.slice(1) : line;
      rows.push({ kind: 'context', oldLine: oldCursor, newLine: newCursor, text });
      oldCursor += 1;
      newCursor += 1;
    }
  }

  return { rows, additions, deletions };
}

export function buildSideBySideRows(rows: DiffLineRow[]): DiffSideBySideRow[] {
  const result: DiffSideBySideRow[] = [];
  let idx = 0;

  while (idx < rows.length) {
    const row = rows[idx];
    if (row.kind === 'hunk' || row.kind === 'meta') {
      result.push({
        leftLine: null,
        leftText: row.text,
        leftKind: row.kind,
        rightLine: null,
        rightText: row.text,
        rightKind: row.kind,
      });
      idx += 1;
      continue;
    }

    if (row.kind === 'context') {
      result.push({
        leftLine: row.oldLine,
        leftText: row.text,
        leftKind: 'context',
        rightLine: row.newLine,
        rightText: row.text,
        rightKind: 'context',
      });
      idx += 1;
      continue;
    }

    // Group contiguous del + add blocks side by side
    const dels: DiffLineRow[] = [];
    const adds: DiffLineRow[] = [];
    while (idx < rows.length && rows[idx].kind === 'del') {
      dels.push(rows[idx]);
      idx += 1;
    }
    while (idx < rows.length && rows[idx].kind === 'add') {
      adds.push(rows[idx]);
      idx += 1;
    }

    const pairCount = Math.max(dels.length, adds.length);
    for (let i = 0; i < pairCount; i += 1) {
      const delRow = dels[i];
      const addRow = adds[i];
      result.push({
        leftLine: delRow ? delRow.oldLine : null,
        leftText: delRow ? delRow.text : null,
        leftKind: delRow ? 'del' : 'empty',
        rightLine: addRow ? addRow.newLine : null,
        rightText: addRow ? addRow.text : null,
        rightKind: addRow ? 'add' : 'empty',
      });
    }
  }

  return result;
}
