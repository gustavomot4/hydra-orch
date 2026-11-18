import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';

interface ApplyResult {
  status: 'applied' | 'noop';
  applied_files: string[];
  deleted_files: string[];
}

export function ApplyConversationChanges({
  conversationId,
  projectName,
}: {
  conversationId: string;
  projectName?: string;
}) {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const apply = useMutation({
    mutationFn: (force: boolean) =>
      client.request<ApplyResult>(
        `/v1/control-plane/conversations/${encodeURIComponent(conversationId)}/apply`,
        {
          method: 'POST',
          body: { force },
        },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['control-plane', 'conversation', conversationId],
        }),
        queryClient.invalidateQueries({
          queryKey: ['control-plane', 'conversation-changes', conversationId],
        }),
      ]);
    },
  });
  const conflicts =
    apply.error instanceof ControlPlaneApiError &&
    apply.error.payload.code === 'workspace_sync_conflict'
      ? apply.error.payload.conflicts
      : undefined;
  const count = apply.data ? apply.data.applied_files.length + apply.data.deleted_files.length : 0;

  return (
    <div className="my-2 space-y-2">
      <button
        type="button"
        className="chat-text-button chat-primary-action"
        disabled={apply.isPending}
        onClick={() => apply.mutate(false)}
      >
        {apply.isPending ? 'Aplicando…' : 'Aplicar ao projeto'}
      </button>
      {projectName && <p className="text-sm text-[var(--text-muted)]">Destino: {projectName}</p>}
      {apply.isSuccess && (
        <p role="status">
          {count
            ? `Alterações aplicadas ao projeto original (${count} ${count === 1 ? 'arquivo' : 'arquivos'}).`
            : 'O projeto já está atualizado.'}
        </p>
      )}
      {apply.isError && <p role="alert">{apply.error.message}</p>}
      {Boolean(conflicts?.length) && (
        <>
          <ul className="list-disc break-words pl-6">
            {conflicts?.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
          <p>A aplicação forçada substitui as mudanças locais nesses arquivos.</p>
          <button type="button" className="chat-text-button" onClick={() => apply.mutate(true)}>
            Sobrescrever conflitos e aplicar
          </button>
        </>
      )}
    </div>
  );
}
