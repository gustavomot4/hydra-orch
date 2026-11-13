import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  ArtifactViewer,
  DiffViewer,
  MarkdownSafeView,
  type ArtifactPreviewResult,
  type RunArtifactItem,
} from '@/feature/artifact';
import {
  SplitTerminalView,
  TerminalPane,
  type PtyChunk,
  type PtySessionInfo,
  type PtyWebSocketLike,
} from '@/feature/terminal';

function makeSession(overrides: Partial<PtySessionInfo> = {}): PtySessionInfo {
  return {
    session_id: 'pty-sess-01',
    workspace_id: 'ws-01',
    host_id: 'local',
    cwd: 'C:/repo/hydra',
    command: ['codex'],
    pid: 4242,
    cols: 120,
    rows: 32,
    status: 'running',
    detached: false,
    exit_code: null,
    backend_kind: 'pipe_bridge',
    pty_certified: false,
    last_seq: 0,
    oldest_seq: 0,
    created_at: '2026-11-13T00:00:00Z',
    finished_at: null,
    ...overrides,
  };
}

function makeChunk(seq: number, sessionId: string, text: string): PtyChunk {
  return {
    seq,
    session_id: sessionId,
    stream: 'stdout',
    text,
    raw_bytes_len: text.length,
    timestamp: '2026-11-13T00:00:01Z',
  };
}

function makePreview(overrides: Partial<ArtifactPreviewResult> = {}): ArtifactPreviewResult {
  return {
    artifact_id: 'art-1',
    run_id: 'run-1',
    rel_path: 'file.txt',
    kind: 'text',
    render_mode: 'text',
    mime_type: 'text/plain',
    size_bytes: 100,
    sha256: 'abc1234567890',
    supported: true,
    status: 'ok',
    content: null,
    sanitized_markdown: null,
    content_base64: null,
    script_stripped: false,
    redacted: false,
    reason: null,
    ...overrides,
  };
}

class FakeWebSocket implements PtyWebSocketLike {
  readyState = 0; // CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(public readonly url: string) {}

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
    this.readyState = 3;
  }

  emitOpen(): void {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }

  emitServerJson(payload: unknown): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(payload) }));
  }

  emitError(): void {
    this.onerror?.(new Event('error'));
    this.readyState = 3;
    this.onclose?.({ code: 1006, reason: 'ws failed' } as CloseEvent);
  }
}

describe('TerminalPane & SplitTerminalView (PTY)', () => {
  it('displays host_id, cwd, session_id, honest Pipe bridge capability badge, ANSI & Unicode via WS, and handles multiline paste + close dialog', async () => {
    const sockets: FakeWebSocket[] = [];
    const requests: Array<{ path: string; method?: string; body?: unknown }> = [];
    const session = makeSession();

    const mockClient = {
      request: vi.fn(async (path: string, options?: { method?: string; body?: unknown }) => {
        requests.push({ path, method: options?.method, body: options?.body });
        if (path.endsWith('/resize')) {
          return { ...session, cols: 140, rows: 40 };
        }
        if (path.endsWith('/interrupt')) {
          return { ...session, status: 'cancelled', exit_code: 130 };
        }
        if (path.endsWith('/close')) {
          const keepRunning = Boolean(
            (options?.body as { keep_running?: boolean } | undefined)?.keep_running,
          );
          return {
            ...session,
            status: keepRunning ? 'running' : 'cancelled',
            detached: keepRunning,
            exit_code: keepRunning ? null : 0,
          };
        }
        return session;
      }),
    } as unknown as ControlPlaneClient;

    const onClosed = vi.fn();

    render(
      <TerminalPane
        session={session}
        title="Codex Terminal"
        client={mockClient}
        token="secret-token"
        transportPreference="ws"
        webSocketFactory={(url) => {
          const ws = new FakeWebSocket(url);
          sockets.push(ws);
          return ws;
        }}
        onClosed={onClosed}
      />,
    );

    expect(screen.getByTestId('pty-meta-host')).toHaveTextContent('local');
    expect(screen.getByTestId('pty-meta-cwd')).toHaveTextContent('C:/repo/hydra');
    expect(screen.getByTestId('pty-meta-session')).toHaveTextContent('pty-sess-01');
    expect(screen.getByTestId('pty-capability-badge')).toHaveTextContent(
      'Pipe bridge (não ConPTY certificado)',
    );

    expect(sockets).toHaveLength(1);
    expect(sockets[0].url).toContain('after_seq=0');

    sockets[0].emitOpen();
    sockets[0].emitServerJson({
      type: 'chunk',
      chunk: makeChunk(1, session.session_id, '\u001b[32mPASS\u001b[0m olá 🚀\r\n'),
    });

    await waitFor(() => {
      const output = screen.getByTestId('terminal-output');
      expect(output).toHaveTextContent('PASS olá 🚀');
      expect(within(output).getByText('PASS')).toHaveStyle({ color: '#4ADE80' });
    });

    // Type command + Enter in headless input
    const input = screen.getByTestId('terminal-input');
    fireEvent.change(input, { target: { value: 'ls' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    const sentInputs = sockets[0].sent.map(
      (raw) => JSON.parse(raw) as { type: string; data?: string },
    );
    expect(sentInputs).toContainEqual({ type: 'input', data: 'ls' });
    expect(sentInputs).toContainEqual({ type: 'input', data: '\r' });

    // Multiline paste opens review dialog; Cancelar aborts without transmitting
    const sentBeforePaste = sockets[0].sent.length;
    fireEvent.paste(input, {
      clipboardData: {
        getData: () => 'rm -rf nope\nsecond line\n',
      },
    });
    expect(screen.getByTestId('multiline-paste-dialog')).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId('multiline-paste-dialog')).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByTestId('multiline-paste-dialog')).not.toBeInTheDocument();
    expect(sockets[0].sent).toHaveLength(sentBeforePaste);

    // Multiline paste confirm sends content to PTY
    fireEvent.paste(input, {
      clipboardData: {
        getData: () => 'echo linha1\necho linha2\n',
      },
    });
    expect(screen.getByTestId('multiline-paste-dialog')).toBeInTheDocument();
    expect(sockets[0].sent).toHaveLength(sentBeforePaste);

    fireEvent.click(screen.getByRole('button', { name: 'Enviar para o terminal' }));
    await waitFor(() => {
      const afterPaste = sockets[0].sent
        .slice(sentBeforePaste)
        .map((raw) => JSON.parse(raw) as { type: string; data?: string });
      expect(afterPaste).toContainEqual({ type: 'input', data: 'echo linha1\necho linha2\n' });
    });

    // Resize triggers POST /resize
    fireEvent.click(screen.getByRole('button', { name: 'Ajustar dimensões do terminal' }));
    await waitFor(() => {
      expect(
        requests.some(
          (r) => r.path.endsWith('/pty/sessions/pty-sess-01/resize') && r.method === 'POST',
        ),
      ).toBe(true);
    });

    // Close button opens TerminalCloseDialog and sends keep_running: true
    fireEvent.click(screen.getByRole('button', { name: 'Fechar terminal' }));
    const closeDialog = screen.getByTestId('terminal-close-dialog');
    expect(closeDialog).toBeInTheDocument();

    fireEvent.click(
      within(closeDialog).getByRole('button', { name: /Manter processo em segundo plano/i }),
    );
    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path.endsWith('/pty/sessions/pty-sess-01/close') &&
            (r.body as { keep_running?: boolean })?.keep_running === true,
        ),
      ).toBe(true);
    });
    expect(onClosed).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: 'pty-sess-01' }),
      true,
    );
  });

  it('shows certified PTY capability badge, exit code when exited, and handles HTTP 410 cursor_expired replay reset', async () => {
    const certifiedSession = makeSession({
      session_id: 'pty-cert-02',
      backend_kind: 'conpty',
      pty_certified: true,
    });

    let outputCalls = 0;
    const mockClient = {
      request: vi.fn(async (path: string, options?: { method?: string; body?: unknown }) => {
        if (path.includes('/output')) {
          outputCalls += 1;
          if (outputCalls === 1) {
            throw new ControlPlaneApiError(410, {
              code: 'cursor_expired',
              message: 'Backlog cursor expirado',
              run_id: null,
              retryable: true,
            });
          }
          return {
            session: { ...certifiedSession, status: 'exited', exit_code: 0, last_seq: 3 },
            chunks: [makeChunk(3, certifiedSession.session_id, 'backlog restaurado\n')],
          };
        }
        if (path.endsWith('/interrupt')) {
          return { ...certifiedSession, status: 'cancelled', exit_code: 130 };
        }
        if (path.endsWith('/close')) {
          return {
            ...certifiedSession,
            status: 'cancelled',
            exit_code: 0,
            detached: Boolean((options?.body as { keep_running?: boolean })?.keep_running),
          };
        }
        return certifiedSession;
      }),
    } as unknown as ControlPlaneClient;

    render(
      <TerminalPane
        session={certifiedSession}
        client={mockClient}
        transportPreference="poll"
      />,
    );

    expect(screen.getByTestId('pty-capability-badge')).toHaveTextContent('PTY certificado (conpty)');

    await waitFor(() => {
      expect(screen.getByTestId('terminal-output')).toHaveTextContent('backlog restaurado');
    });
    expect(screen.getByText(/Cursor after_seq=0 expirado \(HTTP 410\)/i)).toBeInTheDocument();
    expect(screen.getByText('Código de saída: 0')).toBeInTheDocument();
  });

  it('supports interrupt and keep_running=false termination in TerminalCloseDialog and preserves split/single panes in SplitTerminalView', async () => {
    const sockets: FakeWebSocket[] = [];
    const requests: Array<{ path: string; body?: unknown }> = [];
    const primary = makeSession({ session_id: 'pty-codex', command: ['codex'] });
    const secondary = makeSession({ session_id: 'pty-claude', command: ['claude'] });

    const mockClient = {
      request: vi.fn(async (path: string, options?: { method?: string; body?: unknown }) => {
        requests.push({ path, body: options?.body });
        if (path.includes('pty-codex/interrupt')) {
          return { ...primary, status: 'cancelled', exit_code: 130 };
        }
        if (path.includes('pty-claude/close')) {
          return { ...secondary, status: 'cancelled', exit_code: 0 };
        }
        return primary;
      }),
    } as unknown as ControlPlaneClient;

    render(
      <SplitTerminalView
        primarySession={primary}
        secondarySession={secondary}
        client={mockClient}
        token="tok"
        transportPreference="ws"
        webSocketFactory={(url) => {
          const ws = new FakeWebSocket(url);
          sockets.push(ws);
          return ws;
        }}
      />,
    );

    expect(sockets).toHaveLength(2);
    sockets[0].emitOpen();
    sockets[0].emitServerJson({
      type: 'chunk',
      chunk: makeChunk(1, primary.session_id, 'codex ready\n'),
    });
    sockets[1].emitOpen();
    sockets[1].emitServerJson({
      type: 'chunk',
      chunk: makeChunk(1, secondary.session_id, 'claude ready\n'),
    });

    await waitFor(() => {
      expect(screen.getByTestId('terminal-slot-primary')).toHaveTextContent('codex ready');
      expect(screen.getByTestId('terminal-slot-secondary')).toHaveTextContent('claude ready');
    });

    // Switch to single-primary then back to split — output remains preserved
    fireEvent.click(screen.getByRole('button', { name: 'Codex CLI' }));
    expect(screen.getByTestId('terminal-slot-secondary')).toHaveClass('hidden');
    fireEvent.click(screen.getByRole('button', { name: 'Lado a lado' }));
    expect(screen.getByTestId('terminal-slot-secondary')).not.toHaveClass('hidden');
    expect(screen.getByTestId('terminal-slot-primary')).toHaveTextContent('codex ready');

    // Interrupt primary and terminate secondary via close dialog
    const primarySlot = screen.getByTestId('terminal-slot-primary');
    fireEvent.click(within(primarySlot).getByRole('button', { name: 'Interromper processo' }));
    await waitFor(() => {
      expect(requests.some((r) => r.path.endsWith('/pty/sessions/pty-codex/interrupt'))).toBe(true);
    });

    const secondarySlot = screen.getByTestId('terminal-slot-secondary');
    fireEvent.click(within(secondarySlot).getByRole('button', { name: 'Fechar terminal' }));
    const dialog = screen.getByTestId('terminal-close-dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Encerrar processo' }));
    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path.endsWith('/pty/sessions/pty-claude/close') &&
            (r.body as { keep_running?: boolean })?.keep_running === false,
        ),
      ).toBe(true);
    });
  });
});

describe('ArtifactViewer, DiffViewer & MarkdownSafeView', () => {
  const sampleArtifacts: RunArtifactItem[] = [
    {
      id: 'art-diff',
      artifact_id: 'art-diff',
      run_id: 'run-1',
      attempt_id: 'att-1',
      kind: 'patch',
      relative_path: 'changes.diff',
      size_bytes: 180,
      sha256: 'abc1234567890',
      created_at: '2026-11-13T00:00:00Z',
    },
    {
      id: 'art-md',
      artifact_id: 'art-md',
      run_id: 'run-1',
      attempt_id: 'att-1',
      kind: 'report',
      relative_path: 'SUMMARY.md',
      size_bytes: 240,
      sha256: 'def1234567890',
      created_at: '2026-11-13T00:00:01Z',
    },
    {
      id: 'art-img',
      artifact_id: 'art-img',
      run_id: 'run-1',
      attempt_id: 'att-1',
      kind: 'export',
      relative_path: 'screen.png',
      size_bytes: 512,
      sha256: '111222333444',
      created_at: '2026-11-13T00:00:02Z',
    },
    {
      id: 'art-pdf',
      artifact_id: 'art-pdf',
      run_id: 'run-1',
      attempt_id: 'att-1',
      kind: 'report',
      relative_path: 'audit.pdf',
      size_bytes: 2048,
      sha256: '555666777888',
      created_at: '2026-11-13T00:00:03Z',
    },
    {
      id: 'art-html',
      artifact_id: 'art-html',
      run_id: 'run-1',
      attempt_id: 'att-1',
      kind: 'export',
      relative_path: 'evil.html',
      size_bytes: 120,
      sha256: '999000111222',
      created_at: '2026-11-13T00:00:04Z',
    },
    {
      id: 'art-big',
      artifact_id: 'art-big',
      run_id: 'run-1',
      attempt_id: 'att-1',
      kind: 'log',
      relative_path: 'huge.log',
      size_bytes: 10_000_000,
      sha256: '333444555666',
      created_at: '2026-11-13T00:00:05Z',
    },
  ];

  const previewsById: Record<string, ArtifactPreviewResult> = {
    'art-diff': makePreview({
      artifact_id: 'art-diff',
      rel_path: 'changes.diff',
      kind: 'diff',
      render_mode: 'diff',
      mime_type: 'text/x-diff',
      size_bytes: 180,
      content: '@@ -1,2 +1,2 @@\n-const a = 1;\n+const a = 2;\n',
    }),
    'art-md': makePreview({
      artifact_id: 'art-md',
      rel_path: 'SUMMARY.md',
      kind: 'markdown',
      render_mode: 'markdown',
      mime_type: 'text/markdown',
      size_bytes: 240,
      script_stripped: true,
      redacted: true,
      sanitized_markdown:
        '# Relatório Seguro\n\nTexto com [link seguro](https://example.com) e [xss](javascript:alert(1)).\n\n<script>alert(1)</script><img src=x onerror=alert(2)>',
    }),
    'art-img': makePreview({
      artifact_id: 'art-img',
      rel_path: 'screen.png',
      kind: 'image',
      render_mode: 'image',
      mime_type: 'image/png',
      size_bytes: 512,
      content_base64:
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=',
    }),
    'art-pdf': makePreview({
      artifact_id: 'art-pdf',
      rel_path: 'audit.pdf',
      kind: 'pdf',
      render_mode: 'pdf',
      mime_type: 'application/pdf',
      size_bytes: 2048,
      content_base64: 'JVBERi0xLjQK',
    }),
    'art-html': makePreview({
      artifact_id: 'art-html',
      rel_path: 'evil.html',
      kind: 'unsupported',
      render_mode: 'unsupported',
      mime_type: 'text/html',
      size_bytes: 120,
      supported: false,
      status: 'unsupported_media_type',
      reason: 'active_html_blocked',
    }),
  };

  it('switches safely across diff (unified/side-by-side), sanitized markdown, raster image, pdf, unsupported banner, and HTTP 413 preview_too_large banner', async () => {
    const mockClient = {
      request: vi.fn(async (path: string) => {
        if (path === '/v1/control-plane/runs/run-1/artifacts') {
          return sampleArtifacts;
        }
        const match = /\/artifacts\/([^/]+)\/content/.exec(path);
        const artifactId = match?.[1] ?? '';
        if (artifactId === 'art-big') {
          throw new ControlPlaneApiError(413, {
            code: 'preview_too_large',
            message: 'Arquivo ultrapassa 512 KB de preview.',
            run_id: 'run-1',
            retryable: false,
          });
        }
        return previewsById[artifactId];
      }),
    } as unknown as ControlPlaneClient;

    render(<ArtifactViewer runId="run-1" client={mockClient} />);

    // Diff preview loads first
    await waitFor(() => {
      expect(screen.getByTestId('diff-viewer')).toBeInTheDocument();
    });
    expect(screen.getByTestId('diff-viewer')).toHaveTextContent('const a = 2;');
    fireEvent.click(screen.getByRole('button', { name: 'Lado a lado' }));
    expect(screen.getByTestId('diff-viewer')).toHaveAttribute('data-diff-layout', 'side-by-side');

    // Switch to Markdown safe view — no <script> or javascript: href rendered
    fireEvent.click(screen.getByRole('button', { name: /SUMMARY\.md/i }));
    await waitFor(() => {
      expect(screen.getByTestId('markdown-safe-view')).toBeInTheDocument();
    });
    const mdContainer = screen.getByTestId('markdown-safe-view');
    expect(mdContainer.querySelector('script')).toBeNull();
    expect(mdContainer).toHaveTextContent('Relatório Seguro');
    expect(within(mdContainer).getByRole('link', { name: 'link seguro' })).toHaveAttribute(
      'href',
      'https://example.com',
    );
    expect(within(mdContainer).queryByRole('link', { name: 'xss' })).toBeNull();

    // Switch to Image
    fireEvent.click(screen.getByRole('button', { name: /screen\.png/i }));
    await waitFor(() => {
      expect(screen.getByTestId('artifact-image-preview')).toBeInTheDocument();
    });
    expect(screen.getByAltText('screen.png')).toHaveAttribute(
      'src',
      expect.stringContaining('data:image/png;base64,'),
    );

    // Switch to PDF
    fireEvent.click(screen.getByRole('button', { name: /audit\.pdf/i }));
    await waitFor(() => {
      expect(screen.getByTestId('artifact-pdf-preview')).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: /Baixar PDF/i })).toHaveAttribute(
      'href',
      expect.stringContaining('data:application/pdf;base64,'),
    );

    // Switch to Unsupported HTML
    fireEvent.click(screen.getByRole('button', { name: /evil\.html/i }));
    await waitFor(() => {
      expect(screen.getByTestId('artifact-unsupported-banner')).toBeInTheDocument();
    });
    expect(screen.getByTestId('artifact-unsupported-banner')).toHaveTextContent(
      'Tipo de mídia não suportado',
    );

    // Switch to Oversized 413 file
    fireEvent.click(screen.getByRole('button', { name: /huge\.log/i }));
    await waitFor(() => {
      expect(screen.getByTestId('artifact-too-large-banner')).toBeInTheDocument();
    });
    expect(screen.getByTestId('artifact-too-large-banner')).toHaveTextContent('HTTP 413');
  });

  it('neutralizes raw HTML event handlers in standalone MarkdownSafeView and DiffViewer renders +/- stats', () => {
    render(
      <div>
        <MarkdownSafeView
          markdown={'<div onclick="alert(1)">ok</div>\n<script>steal()</script>\n## Título'}
          scriptStripped
        />
        <DiffViewer diffText={'@@ -1 +1 @@\n-velho\n+novo\n'} filePath="src/a.ts" />
      </div>,
    );

    const md = screen.getByTestId('markdown-safe-view');
    expect(md.querySelector('script')).toBeNull();
    expect(md.innerHTML).not.toContain('<script');
    expect(md).toHaveTextContent('Título');

    const diff = screen.getByTestId('diff-viewer');
    expect(diff).toHaveTextContent('+1');
    expect(diff).toHaveTextContent('-1');
  });
});
