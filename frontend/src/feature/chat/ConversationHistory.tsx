import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { WorkspaceTreeNode } from '@/hook/useWorkspaceHierarchy';

export function ConversationHistory({
  onSelect,
  filter,
}: {
  onSelect: (node: WorkspaceTreeNode) => void;
  filter: string;
}) {
  const client = useControlPlaneClient();
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState(filter);
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(0);
      setSearch(filter);
    }, 200);
    return () => clearTimeout(timer);
  }, [filter]);
  const chats = useQuery({
    queryKey: ['control-plane', 'conversations', page, search],
    queryFn: () =>
      client.request<{ items: { id: string; title: string; project_id: string }[]; total: number }>(
        `/v1/control-plane/conversations?limit=10&offset=${page * 10}&q=${encodeURIComponent(search)}`,
      ),
    refetchInterval: 5000,
    retry: false,
  });
  if (!chats.data?.total)
    return (
      <section className="px-2 py-3 text-sm text-[#D1D1D1]" aria-label="Conversas recentes">
        <h3 className="mb-2 font-semibold text-[#E8E8E8]">Conversas</h3>
        {chats.isError ? (
          <button className="min-h-11 text-left underline" onClick={() => void chats.refetch()}>
            Carregar conversas novamente
          </button>
        ) : (
          <p role="status">
            {chats.isLoading
              ? 'Carregando conversas…'
              : search
                ? 'Nenhuma conversa com essa busca.'
                : 'Seus pedidos enviados aparecem aqui.'}
          </p>
        )}
      </section>
    );
  return (
    <section className="border-t border-[#303030] px-2 py-3" aria-label="Conversas recentes">
      <h3 className="mb-2 text-sm font-semibold text-[#E8E8E8]">Conversas</h3>
      {chats.data.items.map((chat) => (
        <button
          key={chat.id}
          className="block min-h-11 w-full break-words rounded-lg px-2 py-2 text-left text-sm text-[#D1D1D1]"
          onClick={() =>
            onSelect({
              id: chat.id,
              kind: 'session',
              label: chat.title,
              status: 'active',
              hostId: 'local',
              projectId: chat.project_id,
              runId: chat.id,
              children: [],
            })
          }
        >
          {chat.title}
        </button>
      ))}
      {chats.data.total > 10 && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[#D1D1D1]">
          <button className="min-h-11 px-2" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Anterior
          </button>
          <span>
            {page * 10 + 1}–{Math.min((page + 1) * 10, chats.data.total)} de {chats.data.total}
          </span>
          <button
            className="min-h-11 px-2"
            disabled={(page + 1) * 10 >= chats.data.total}
            onClick={() => setPage(page + 1)}
          >
            Próxima
          </button>
        </div>
      )}
    </section>
  );
}
