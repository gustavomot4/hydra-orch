import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { DiffViewer } from '@/feature/artifact/DiffViewer';
import { ApplyConversationChanges } from './ApplyConversationChanges';

interface ChangeReview {
  project_name: string;
  title: string;
  agent_added: string[];
  agent_modified: string[];
  agent_deleted: string[];
  conflicts: string[];
}

export function ConversationChanges({ conversationId }: { conversationId: string }) {
  const client = useControlPlaneClient();
  const [selectedFile, setSelectedFile] = useState('');
  const endpoint = `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/changes`;
  const key = ['control-plane', 'conversation-changes', conversationId];
  const review = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => client.request<ChangeReview>(endpoint, { signal }),
    retry: false,
  });
  const changes = review.data;
  const files = changes
    ? [
        ...changes.agent_added.map((name) => ({ name, status: 'Adicionado' })),
        ...changes.agent_modified.map((name) => ({ name, status: 'Modificado' })),
        ...changes.agent_deleted.map((name) => ({ name, status: 'Removido' })),
      ].sort((left, right) => left.name.localeCompare(right.name))
    : [];
  const path = files.some((file) => file.name === selectedFile) ? selectedFile : files[0]?.name;
  const preview = useQuery({
    queryKey: [...key, path],
    queryFn: ({ signal }) =>
      client.request<{ diff: string }>(`${endpoint}?${new URLSearchParams({ path: path ?? '' })}`, {
        signal,
      }),
    enabled: Boolean(path),
    retry: false,
  });

  return (
    <section aria-labelledby="conversation-changes-title" className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          {changes && (
            <p className="break-words text-sm text-[var(--text-muted)]">{changes.project_name}</p>
          )}
          <h1 id="conversation-changes-title" className="text-xl font-semibold">
            Alterações
          </h1>
          {changes && <p className="break-words font-medium">{changes.title}</p>}
        </div>
        <Link className="chat-text-button" to={`/chat/${encodeURIComponent(conversationId)}`}>
          Voltar à conversa
        </Link>
      </div>
      {review.isPending && <p role="status">Carregando alterações…</p>}
      {review.isError && (
        <div role="alert">
          {review.error.message}{' '}
          <button type="button" className="chat-text-button" onClick={() => void review.refetch()}>
            Atualizar revisão
          </button>
        </div>
      )}
      {changes && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3 border-t border-[var(--border)] pt-3">
            {files.length === 0 ? (
              <p role="status" className="text-base font-semibold">
                O projeto já está atualizado
              </p>
            ) : (
              <h2 className="text-base font-semibold">
                {files.length}{' '}
                {files.length === 1 ? 'arquivo na cópia da conversa' : 'arquivos na cópia da conversa'}
              </h2>
            )}
            {files.length > 0 && (
              <ApplyConversationChanges
                conversationId={conversationId}
                projectName={changes.project_name}
              />
            )}
          </div>
          {changes.conflicts.length > 0 && (
            <p role="status" className="break-words text-sm text-[var(--status-warning)]">
              Alterações locais em conflito: {changes.conflicts.join(', ')}
            </p>
          )}
          {files.length > 0 && (
            <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(12rem,1fr)_minmax(0,2fr)]">
              <section
                aria-labelledby="changed-file-list"
                className="min-w-0 rounded-lg border border-[var(--border)] bg-[var(--bg-rail)] p-3"
              >
                <h3 id="changed-file-list" className="mb-2 font-semibold">
                  Arquivos alterados
                </h3>
                <ul>
                  {files.map((file) => (
                    <li key={file.name}>
                      <button
                        type="button"
                        aria-pressed={path === file.name}
                        onClick={() => setSelectedFile(file.name)}
                        className="flex min-h-11 w-full min-w-0 flex-wrap items-center justify-between gap-x-3 rounded-md px-2 text-left aria-pressed:bg-[var(--bg-hover)]"
                      >
                        <span className="min-w-0 break-all">{file.name}</span>
                        <span className="text-sm text-[var(--text-muted)]">{file.status}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
              <section aria-label="Comparação do arquivo" className="min-w-0">
                {preview.isPending && <p role="status">Carregando comparação…</p>}
                {preview.isError && <p role="alert">{preview.error.message}</p>}
                {preview.data && <DiffViewer diffText={preview.data.diff} filePath={path} />}
              </section>
            </div>
          )}
        </>
      )}
    </section>
  );
}
