import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { describe, expect, it, vi } from 'vitest';
import {
  AttachmentDropzone,
  AttachmentItemView,
  AttachmentList,
  bytesToBase64,
} from '@/feature/attachment';
import {
  DICTATION_NOTICE,
  DictationAdapterCallbacks,
  DictationControl,
  DictationSpeechAdapter,
} from '@/feature/dictation';
import { QuickOpenDialog, QuickOpenSearchItem } from '@/feature/quickopen';
import { createControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useLayoutStore } from '@/store/layoutStore';

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('T38 QuickOpenDialog (7:359 / UI05)', () => {
  it('debounces search, switches scopes, supports full keyboard navigation and keeps existing drafts/tabs intact', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();
    useLayoutStore.getState().openTab({
      id: 'tab:existing-chat',
      kind: 'chat',
      title: 'Sessão aberta',
      route: '/chat/sess-open',
      sessionId: 'sess-open',
      closable: true,
    });

    const sampleItems: QuickOpenSearchItem[] = [
      {
        kind: 'run',
        id: 'run-101',
        title: 'Refatorar parser SSE',
        subtitle: 'hydra-orch · running',
        host_id: 'local',
        workspace_id: 'ws-1',
        project_id: 'proj-1',
        run_id: 'run-101',
        session_id: null,
        tab_hint: 'chat',
      },
      {
        kind: 'session',
        id: 'sess-202',
        title: 'Terminal Codex CLI',
        subtitle: 'Session · running',
        host_id: 'local',
        workspace_id: 'ws-1',
        project_id: 'proj-1',
        run_id: 'run-101',
        session_id: 'sess-202',
        tab_hint: 'terminal',
      },
      {
        kind: 'artifact',
        id: 'art-303',
        title: 'relatorio.md',
        subtitle: 'markdown · docs/relatorio.md',
        host_id: 'local',
        workspace_id: 'ws-1',
        project_id: 'proj-1',
        run_id: 'run-101',
        session_id: null,
        tab_hint: 'artifact',
      },
    ];

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/v1/control-plane/search')) {
        const parsed = new URL(url, 'http://localhost');
        const scope = parsed.searchParams.get('scope');
        const filtered =
          scope && scope !== 'all'
            ? sampleItems.filter((item) => {
                if (scope === 'sessions') return item.kind === 'session';
                if (scope === 'runs') return item.kind === 'run';
                if (scope === 'artifacts') return item.kind === 'artifact';
                return true;
              })
            : sampleItems;
        return new Response(
          JSON.stringify({
            query: parsed.searchParams.get('q') ?? '',
            scope,
            items: filtered,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({}), { status: 404 });
    });

    const client = createControlPlaneClient('test-token', { fetchImpl: fetchMock });
    const onSelectItem = vi.fn();

    function Harness() {
      const [open, setOpen] = useState(true);
      const [draft, setDraft] = useState('Rascunho preservado da sessão');
      return (
        <div>
          <textarea
            aria-label="Rascunho ativo"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <QuickOpenDialog
            open={open}
            onOpenChange={setOpen}
            onSelectItem={onSelectItem}
            debounceMs={20}
            client={client}
          />
        </div>
      );
    }

    render(<Harness />);

    const dialog = await screen.findByTestId('quickopen-dialog');
    const combobox = within(dialog).getByRole('combobox', { name: 'Buscar no Control Plane' });
    const listbox = within(dialog).getByRole('listbox', { name: 'Resultados da busca' });
    expect(combobox).toHaveAttribute('aria-controls', listbox.id);

    // Scope filter tabs
    for (const label of [
      'Tudo',
      'Áreas',
      'Workspaces',
      'Projetos',
      'Runs',
      'Sessões',
      'Artefatos',
    ]) {
      expect(within(dialog).getByRole('tab', { name: label })).toBeInTheDocument();
    }

    await user.type(combobox, 'refatorar');

    const options = await within(dialog).findAllByRole('option');
    expect(options).toHaveLength(3);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/v1/control-plane/search?q=refatorar&scope=all&host_id=local&limit=25'),
      expect.any(Object),
    );

    // Keyboard navigation: ArrowDown, End, Home, ArrowUp
    expect(combobox).toHaveAttribute('aria-activedescendant', options[0].id);

    await user.keyboard('{ArrowDown}');
    expect(combobox).toHaveAttribute('aria-activedescendant', options[1].id);
    expect(options[1]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{End}');
    expect(combobox).toHaveAttribute('aria-activedescendant', options[2].id);

    await user.keyboard('{Home}');
    expect(combobox).toHaveAttribute('aria-activedescendant', options[0].id);

    await user.keyboard('{ArrowUp}');
    expect(combobox).toHaveAttribute('aria-activedescendant', options[2].id);

    // Accessibility check while dialog has active options
    const axeResult = await axe.run(dialog, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(axeResult.violations).toEqual([]);

    // Scope switching filters results
    await user.click(within(dialog).getByRole('tab', { name: 'Sessões' }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('scope=sessions'),
        expect.any(Object),
      );
    });
    const sessionOptions = await within(dialog).findAllByRole('option');
    expect(sessionOptions).toHaveLength(1);
    expect(sessionOptions[0]).toHaveTextContent('Terminal Codex CLI');

    // Enter selects active option and closes dialog
    combobox.focus();
    await user.keyboard('{Enter}');
    expect(onSelectItem).toHaveBeenCalledTimes(1);
    expect(onSelectItem).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'session',
        id: 'sess-202',
        session_id: 'sess-202',
        tab_hint: 'terminal',
      }),
    );

    await waitFor(() => {
      expect(screen.queryByTestId('quickopen-dialog')).toBeNull();
    });

    // Unrelated draft and open tabs remain completely intact
    expect(screen.getByLabelText('Rascunho ativo')).toHaveValue('Rascunho preservado da sessão');
    expect(useLayoutStore.getState().panes.primary.tabIds).toContain('tab:existing-chat');
  });

  it('closes on Escape and shows retryable alert on search failure', async () => {
    const user = userEvent.setup();
    let shouldFail = true;
    const fetchMock = vi.fn(async () => {
      if (shouldFail) {
        return new Response(
          JSON.stringify({ code: 'search_error', message: 'Índice indisponível' }),
          { status: 500 },
        );
      }
      return new Response(
        JSON.stringify({
          query: 'hydra',
          scope: 'all',
          items: [
            {
              kind: 'project',
              id: 'proj-1',
              title: 'hydra-orch',
              subtitle: 'main',
              host_id: 'local',
              workspace_id: 'ws-1',
              project_id: 'proj-1',
              run_id: null,
              session_id: null,
              tab_hint: 'workspace',
            },
          ],
        }),
        { status: 200 },
      );
    });

    const client = createControlPlaneClient('test-token', { fetchImpl: fetchMock });
    const onOpenChange = vi.fn();

    render(
      <QuickOpenDialog
        open={true}
        onOpenChange={onOpenChange}
        onSelectItem={vi.fn()}
        debounceMs={10}
        client={client}
      />,
    );

    const combobox = await screen.findByRole('combobox', { name: 'Buscar no Control Plane' });
    await user.type(combobox, 'hydra');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Índice indisponível');

    shouldFail = false;
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByRole('option')).toHaveTextContent('hydra-orch');

    combobox.focus();
    await user.keyboard('{Escape}');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe('T38 AttachmentDropzone & AttachmentList (UI04 / UI05)', () => {
  it('blocks forbidden extensions client-side without calling backend and shows dismissible alert', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    const client = createControlPlaneClient('test-token', { fetchImpl: fetchMock });

    render(
      <AttachmentDropzone
        sessionId="sess-1"
        workspaceId="ws-1"
        hostId="local"
        client={client}
      />,
    );

    const fileInput = screen.getByLabelText('Selecionar arquivos para anexar') as HTMLInputElement;
    const forbiddenFiles = [
      new File(['<html><script>alert(1)</script></html>'], 'evil.html', { type: 'text/html' }),
      new File(['<svg onload=alert(1)></svg>'], 'icon.svg', { type: 'image/svg+xml' }),
      new File(['alert(1)'], 'app.js', { type: 'application/javascript' }),
      new File(['MZ\x90\x00'], 'run.exe', { type: 'application/octet-stream' }),
      new File(['@echo off'], 'setup.bat', { type: 'text/plain' }),
      new File(['Write-Host hi'], 'deploy.ps1', { type: 'text/plain' }),
      new File(['#!/bin/sh'], 'build.sh', { type: 'text/plain' }),
    ];

    for (const badFile of forbiddenFiles) {
      fireEvent.change(fileInput, { target: { files: [badFile] } });
      const banner = await screen.findByTestId('attachment-error-banner');
      expect(banner).toHaveTextContent(badFile.name);
      await user.click(within(banner).getByRole('button', { name: 'Dispensar aviso de erro' }));
      expect(screen.queryByTestId('attachment-error-banner')).toBeNull();
    }

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('encodes binary files without corruption via FileReader/ArrayBuffer, tracks upload lifecycle, handles drag/drop, paste and retry', async () => {
    const user = userEvent.setup();
    const deferred = createDeferred<Response>();
    let attempt = 0;

    const binaryBytes = new Uint8Array([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0xff, 0xfe, 0x80, 0x7f, 0x01,
    ]);
    const expectedBase64 = bytesToBase64(binaryBytes);
    const pngFile = new File([binaryBytes], 'screenshot.png', { type: 'image/png' });

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      attempt += 1;
      if (attempt === 1) {
        return deferred.promise;
      }
      if (attempt === 2) {
        return new Response(
          JSON.stringify({ code: 'upload_failed', message: 'Erro temporário no servidor' }),
          { status: 500 },
        );
      }
      const parsedBody = JSON.parse(String(init?.body ?? '{}'));
      return new Response(
        JSON.stringify({
          attachment_id: 'att-bin-1',
          workspace_id: parsedBody.workspace_id,
          session_id: 'sess-local',
          host_id: parsedBody.host_id,
          filename: parsedBody.filename,
          mime_type: parsedBody.mime_type,
          size_bytes: binaryBytes.length,
          sha256: 'deadbeefcafe1234567890abcdef1234567890abcdef1234567890abcdef1234',
          storage_rel_path: 'files/sess-local/att-bin-1_screenshot.png',
          transfer_status: 'local_ready',
          remote_confirmed: false,
          created_at: '2026-11-13T00:00:00Z',
        }),
        { status: 201 },
      );
    });

    const client = createControlPlaneClient('test-token', { fetchImpl: fetchMock });

    const { container } = render(
      <AttachmentDropzone
        sessionId="sess-local"
        workspaceId="ws-1"
        hostId="local"
        client={client}
      />,
    );

    const dropzone = screen.getByTestId('attachment-dropzone');
    fireEvent.dragEnter(dropzone, { dataTransfer: { files: [pngFile] } });
    expect(screen.getByTestId('attachment-drop-overlay')).toHaveTextContent(
      'Solte os arquivos para anexar à sessão',
    );

    fireEvent.drop(dropzone, { dataTransfer: { files: [pngFile] } });
    expect(screen.queryByTestId('attachment-drop-overlay')).toBeNull();

    // First upload stays pending until deferred resolves
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    const firstItem = screen.getByRole('listitem');
    expect(firstItem).toHaveTextContent('screenshot.png');
    expect(firstItem).toHaveTextContent('image/png');
    expect(firstItem).toHaveTextContent('14 B');
    expect(firstItem).toHaveAttribute('data-upload-status', 'enviando');

    const sentPayload = JSON.parse(String(fetchMock.mock.calls[0][1]?.body ?? '{}'));
    expect(sentPayload.content_base64).toBe(expectedBase64);
    const decoded = Uint8Array.from(atob(sentPayload.content_base64), (c) => c.charCodeAt(0));
    expect(Array.from(decoded)).toEqual(Array.from(binaryBytes));

    // Resolve first attempt as local_ready
    deferred.resolve(
      new Response(
        JSON.stringify({
          attachment_id: 'att-bin-0',
          workspace_id: 'ws-1',
          session_id: 'sess-local',
          host_id: 'local',
          filename: 'screenshot.png',
          mime_type: 'image/png',
          size_bytes: binaryBytes.length,
          sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
          storage_rel_path: 'files/sess-local/att-bin-0_screenshot.png',
          transfer_status: 'local_ready',
          remote_confirmed: false,
          created_at: '2026-11-13T00:00:00Z',
        }),
        { status: 201 },
      ),
    );

    const readyRow = await screen.findByTestId('attachment-item-att-bin-0');
    expect(readyRow).toHaveAttribute('data-upload-status', 'local_ready');
    expect(readyRow).toHaveTextContent('Pronto local');
    expect(readyRow).toHaveTextContent('SHA-256: 0123456789ab');

    // Paste handler upload -> fails first (attempt 2), then retries (attempt 3)
    const pasteFile = new File(['# Nota colada'], 'pasted.md', { type: 'text/markdown' });
    fireEvent.paste(dropzone, {
      clipboardData: {
        files: [pasteFile],
        items: [],
      },
    });

    const errBanner = await screen.findByTestId('attachment-error-banner');
    expect(errBanner).toHaveTextContent('Erro temporário no servidor');
    const errorItem = screen
      .getAllByRole('listitem')
      .find((el) => el.getAttribute('data-upload-status') === 'erro');
    expect(errorItem).toBeDefined();

    await user.click(within(errBanner).getByRole('button', { name: 'Tentar novamente' }));
    const retriedRow = await screen.findByTestId('attachment-item-att-bin-1');
    expect(retriedRow).toHaveAttribute('data-upload-status', 'local_ready');
    expect(retriedRow).toHaveTextContent('SHA-256: deadbeefcafe');

    const axeResult = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(axeResult.violations).toEqual([]);
  });

  it('requires explicit confirmation before transferring remote-host attachments', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/v1/control-plane/sessions/sess-remote/attachments') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            attachment_id: 'att-remote-1',
            workspace_id: 'ws-1',
            session_id: 'sess-remote',
            host_id: 'ssh-gpu-1',
            filename: 'spec.md',
            mime_type: 'text/markdown',
            size_bytes: 128,
            sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
            storage_rel_path: 'files/sess-remote/att-remote-1_spec.md',
            transfer_status: 'pending_remote_confirm',
            remote_confirmed: false,
            created_at: '2026-11-13T00:00:00Z',
          }),
          { status: 201 },
        );
      }
      if (
        url.endsWith(
          '/v1/control-plane/sessions/sess-remote/attachments/att-remote-1/confirm-transfer',
        ) &&
        init?.method === 'POST'
      ) {
        return new Response(
          JSON.stringify({
            attachment_id: 'att-remote-1',
            workspace_id: 'ws-1',
            session_id: 'sess-remote',
            host_id: 'ssh-gpu-1',
            filename: 'spec.md',
            mime_type: 'text/markdown',
            size_bytes: 128,
            sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
            storage_rel_path: 'files/sess-remote/att-remote-1_spec.md',
            transfer_status: 'transferred',
            remote_confirmed: true,
            created_at: '2026-11-13T00:00:00Z',
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({}), { status: 404 });
    });

    const client = createControlPlaneClient('test-token', { fetchImpl: fetchMock });
    const onConfirmed = vi.fn();

    render(
      <AttachmentDropzone
        sessionId="sess-remote"
        workspaceId="ws-1"
        hostId="ssh-gpu-1"
        client={client}
        onConfirmed={onConfirmed}
      />,
    );

    const fileInput = screen.getByLabelText('Selecionar arquivos para anexar');
    await user.upload(fileInput, new File(['# Spec'], 'spec.md', { type: 'text/markdown' }));

    const remoteRow = await screen.findByTestId('attachment-item-att-remote-1');
    expect(remoteRow).toHaveAttribute('data-upload-status', 'pending_remote_confirm');
    expect(screen.getByTestId('attachment-host-badge-att-remote-1')).toHaveTextContent(
      'Destino: ssh-gpu-1',
    );

    // Must NOT silently auto-transfer
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onConfirmed).not.toHaveBeenCalled();

    const confirmBtn = screen.getByRole('button', {
      name: 'Confirmar transferência de spec.md para ssh-gpu-1',
    });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByTestId('attachment-item-att-remote-1')).toHaveAttribute(
        'data-upload-status',
        'transferred',
      );
    });
    expect(onConfirmed).toHaveBeenCalledWith(
      expect.objectContaining({
        attachment_id: 'att-remote-1',
        remote_confirmed: true,
        transfer_status: 'transferred',
      }),
    );

    // Standalone AttachmentList renders cleanly with typed items
    const standaloneView: AttachmentItemView[] = [];
    const { container: listContainer } = render(<AttachmentList items={standaloneView} />);
    expect(within(listContainer).getByTestId('attachment-list-empty')).toBeInTheDocument();
  });
});

describe('T38 DictationControl (7:679, 7:1039 / UI08)', () => {
  it('shows unavailable state honestly when browser speech API is absent', async () => {
    const onInsert = vi.fn();
    const { container } = render(<DictationControl onInsertTranscript={onInsert} />);

    const root = screen.getByTestId('dictation-control');
    expect(root).toHaveAttribute('data-dictation-state', 'unavailable');
    expect(screen.getByTestId('dictation-mode-notice')).toHaveTextContent(DICTATION_NOTICE);
    expect(screen.getByTestId('dictation-unavailable-notice')).toHaveTextContent(
      'Ditado por voz indisponível neste navegador',
    );
    expect(screen.getByRole('button', { name: 'Ditado indisponível' })).toBeDisabled();
    expect(onInsert).not.toHaveBeenCalled();

    const axeResult = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(axeResult.violations).toEqual([]);
  });

  it('captures speech only into editable draft preview, never auto-submits, and recovers from permission denial', async () => {
    const user = userEvent.setup();
    let activeCallbacks: DictationAdapterCallbacks | null = null;
    let shouldDenyPermission = true;

    const fakeAdapter: DictationSpeechAdapter = {
      isSupported: () => true,
      start: vi.fn((callbacks) => {
        activeCallbacks = callbacks;
        if (shouldDenyPermission) {
          callbacks.onError?.({ code: 'not-allowed' });
          return;
        }
        callbacks.onStart?.();
      }),
      stop: vi.fn(() => {
        activeCallbacks?.onEnd?.();
      }),
      abort: vi.fn(() => {
        activeCallbacks?.onEnd?.();
      }),
    };

    const onInsertTranscript = vi.fn();
    const onFormSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());

    const { container } = render(
      <form onSubmit={onFormSubmit}>
        <DictationControl
          onInsertTranscript={onInsertTranscript}
          speechAdapter={fakeAdapter}
        />
      </form>,
    );

    const root = screen.getByTestId('dictation-control');
    expect(root).toHaveAttribute('data-dictation-state', 'idle');
    expect(root).toHaveTextContent('Inativo');
    expect(root).toHaveTextContent(DICTATION_NOTICE);

    // 1. Permission denied -> explicit guidance + retry recovery
    await user.click(screen.getByRole('button', { name: 'Iniciar ditado' }));
    expect(root).toHaveAttribute('data-dictation-state', 'permission_denied');
    expect(screen.getByTestId('dictation-error-notice')).toHaveTextContent(
      'Permissão de microfone negada — clique para tentar novamente ou revise permissões do navegador',
    );

    // 2. Grant permission and retry -> listening -> draft_ready
    shouldDenyPermission = false;
    await user.click(
      within(screen.getByTestId('dictation-error-notice')).getByRole('button', {
        name: 'Tentar novamente',
      }),
    );

    expect(root).toHaveAttribute('data-dictation-state', 'listening');
    expect(root).toHaveTextContent('Ouvindo');

    act(() => {
      activeCallbacks!.onResult?.({ transcript: 'Analisar logs', isFinal: false });
      activeCallbacks!.onResult?.({ transcript: 'Analisar logs do worker', isFinal: true });
    });

    await user.click(screen.getByRole('button', { name: 'Parar ditado' }));
    expect(root).toHaveAttribute('data-dictation-state', 'draft_ready');
    expect(root).toHaveTextContent('Rascunho revisável');

    // Never auto-inserts or auto-submits
    expect(onInsertTranscript).not.toHaveBeenCalled();
    expect(onFormSubmit).not.toHaveBeenCalled();

    const previewBox = screen.getByLabelText('Rascunho revisável do ditado');
    expect(previewBox).toHaveValue('Analisar logs do worker');

    const axeResult = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(axeResult.violations).toEqual([]);

    // User edits draft and explicitly inserts it
    await user.type(previewBox, ' e validar testes');
    await user.click(screen.getByRole('button', { name: 'Inserir no rascunho' }));

    expect(onInsertTranscript).toHaveBeenCalledTimes(1);
    expect(onInsertTranscript).toHaveBeenCalledWith('Analisar logs do worker e validar testes');
    expect(onFormSubmit).not.toHaveBeenCalled();
    expect(root).toHaveAttribute('data-dictation-state', 'idle');

    // Discard path clears draft without inserting
    await user.click(screen.getByRole('button', { name: 'Iniciar ditado' }));
    act(() => {
      activeCallbacks!.onResult?.({ transcript: 'Texto descartado', isFinal: true });
    });
    await user.click(await screen.findByRole('button', { name: 'Descartar' }));

    expect(onInsertTranscript).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('dictation-draft-preview')).toBeNull();
    expect(root).toHaveAttribute('data-dictation-state', 'idle');
  });

  it('uses webkitSpeechRecognition browser fallback when speechAdapter prop is omitted', async () => {
    const user = userEvent.setup();
    const instances: Array<{
      lang: string;
      interimResults: boolean;
      continuous: boolean;
      onstart: (() => void) | null;
      onresult: ((event: { results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
      onerror: ((event: { error: string }) => void) | null;
      onend: (() => void) | null;
      start: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
      abort: ReturnType<typeof vi.fn>;
    }> = [];

    class MockWebkitSpeechRecognition {
      lang = '';
      interimResults = false;
      continuous = false;
      onstart: (() => void) | null = null;
      onresult: ((event: { results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn(() => {
        this.onstart?.();
      });
      stop = vi.fn(() => {
        this.onend?.();
      });
      abort = vi.fn();

      constructor() {
        instances.push(this);
      }
    }

    const win = window as unknown as { webkitSpeechRecognition?: unknown };
    const prev = win.webkitSpeechRecognition;
    win.webkitSpeechRecognition = MockWebkitSpeechRecognition;

    try {
      const onInsert = vi.fn();
      render(<DictationControl onInsertTranscript={onInsert} />);

      const root = screen.getByTestId('dictation-control');
      expect(root).toHaveAttribute('data-dictation-state', 'idle');

      await user.click(screen.getByRole('button', { name: 'Iniciar ditado' }));
      expect(instances).toHaveLength(1);
      expect(instances[0].lang).toBe('pt-BR');
      expect(root).toHaveAttribute('data-dictation-state', 'listening');

      act(() => {
        instances[0].onresult?.({
          results: [{ isFinal: true, 0: { transcript: 'Abrir terminal local' } }],
        });
      });

      await user.click(screen.getByRole('button', { name: 'Parar ditado' }));
      expect(root).toHaveAttribute('data-dictation-state', 'draft_ready');

      await user.click(screen.getByRole('button', { name: 'Inserir no rascunho' }));
      expect(onInsert).toHaveBeenCalledWith('Abrir terminal local');
    } finally {
      if (prev === undefined) {
        delete win.webkitSpeechRecognition;
      } else {
        win.webkitSpeechRecognition = prev;
      }
    }
  });
});
