import { useEffect, useId, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Dialog from '@radix-ui/react-dialog';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ConversationRoute, routeSelection } from './conversationTypes';
import { ChatChoice } from './ChatDialog';

interface Target {
  id: string;
  name: string;
  target_kind: 'model' | 'combo';
  compatibility?: 'verified' | 'unverified' | 'unsupported';
  reason?: string;
}
interface Catalog {
  status: string;
  combos: Target[];
  models: Target[];
  direct_models: { id: string; name: string }[];
}
const field =
  'min-h-11 w-full rounded-lg border border-[#666] bg-[#1C1C1C] px-3 py-2 text-sm text-[#E8E8E8]';
const statusLabels: Record<string, string> = {
  connected: 'Conectado ao OmniRoute',
  disabled: 'A conexão OmniRoute está desligada no backend.',
  credential_missing: 'A credencial do OmniRoute não está disponível no backend.',
  access_denied:
    'O OmniRoute recusou o acesso ao catálogo. Confira a credencial e suas permissões.',
  timeout: 'O OmniRoute demorou para responder.',
  unavailable: 'O OmniRoute não está disponível.',
};

export function ConversationRoutePicker({
  value,
  onChange,
  disabled = false,
  onReadyChange,
}: {
  value: ConversationRoute;
  onChange: (value: ConversationRoute) => void;
  disabled?: boolean;
  onReadyChange?: (ready: boolean) => void;
}) {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = ['conversation-route-catalog', value.executor, value.connection_mode];
  const query = useQuery({
    queryKey: key,
    queryFn: () =>
      client.request<Catalog>(
        `/v1/control-plane/omniroute/combos?executor=${value.executor}&connection_mode=${value.connection_mode}`,
      ),
    staleTime: 30000,
    retry: false,
  });
  const catalog = query.data;
  const selected = (catalog?.combos ?? []).find(
    (c) => c.name === value.target_ref && value.target_kind === 'combo',
  );
  const selectionKey = ['conversation-route-description', routeSelection(value)];
  const description = useQuery({
    queryKey: selectionKey,
    queryFn: () =>
      client.request<{ compatibility: string; reason: string }>(
        '/v1/control-plane/conversation-routes/describe',
        { method: 'POST', body: routeSelection(value) },
      ),
    enabled: value.connection_mode === 'omniroute' && Boolean(value.target_ref),
    staleTime: 30000,
    retry: false,
  });
  const verified =
    value.connection_mode === 'direct' || description.data?.compatibility === 'verified';
  // The server is the final admission check, including when the catalog changes.
  const ready =
    value.connection_mode === 'direct' ||
    Boolean(value.target_ref && catalog?.status === 'connected' && verified);
  useEffect(() => {
    onReadyChange?.(ready);
  }, [ready, onReadyChange]);
  const update = (next: ConversationRoute) => {
    setError(null);
    onChange(next);
    onReadyChange?.(next.connection_mode === 'direct');
  };
  const targets = [...(catalog?.combos ?? []), ...(catalog?.models ?? [])];
  const normalize = (text: string) =>
    text
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase();
  const matches = targets.filter((t) => normalize(t.name).includes(normalize(search)));
  async function test() {
    setTesting(true);
    setError(null);
    try {
      await client.request('/v1/control-plane/conversation-routes/verify', {
        method: 'POST',
        body: routeSelection(value),
      });
      await queryClient.invalidateQueries({ queryKey: selectionKey });
      await queryClient.invalidateQueries({ queryKey: key });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Não foi possível comprovar a combinação.');
      onReadyChange?.(false);
    } finally {
      setTesting(false);
    }
  }
  return (
    <div className="mb-4 space-y-3" data-testid="conversation-route-picker">
      <div className="flex flex-wrap gap-3">
        <div className="min-w-0 flex-[1_1_10rem]">
          <span className="mb-1 block text-sm text-[#D1D1D1]">Conexão</span>
          <div className="chat-agent-options">
            {[
              { id: 'direct', name: 'Conta do agente' },
              { id: 'omniroute', name: 'OmniRoute' },
            ].map((option) => (
              <label key={option.id}>
                <input
                  type="radio"
                  name={`${id}-connection`}
                  checked={value.connection_mode === option.id}
                  disabled={disabled || testing}
                  onChange={() =>
                    update({
                      ...value,
                      connection_mode: option.id as ConversationRoute['connection_mode'],
                      target_kind: 'model',
                      target_ref: '',
                    })
                  }
                />
                {option.name}
              </label>
            ))}
          </div>
        </div>
        <div className="min-w-0 flex-[2_1_12rem]">
          {value.connection_mode === 'direct' ? (
            <>
              <ChatChoice
                label="Modelo"
                value={value.target_ref}
                options={[{ id: '', name: 'Padrão do agente' }, ...(catalog?.direct_models ?? [])]}
                disabled={disabled || testing}
                onChange={(id) => update({ ...value, target_ref: id, target_kind: 'model' })}
              />
            </>
          ) : (
            <>
              <span id={`${id}-target-label`} className="mb-1 block text-sm text-[#D1D1D1]">
                Modelo ou combo
              </span>
              <Dialog.Root open={open} onOpenChange={setOpen}>
                <Dialog.Trigger
                  className={`${field} text-left`}
                  disabled={disabled || testing}
                  aria-labelledby={`${id}-target-label ${id}-target-value`}
                >
                  <span id={`${id}-target-value`}>
                    {value.target_ref || 'Escolher modelo ou combo'}
                  </span>
                </Dialog.Trigger>
                <Dialog.Portal>
                  <Dialog.Overlay className="chat-catalog-overlay" />
                  <Dialog.Content className="chat-dialog chat-catalog">
                    <Dialog.Title className="text-lg font-semibold">
                      Escolher modelo ou combo
                    </Dialog.Title>
                    <Dialog.Description className="mb-3 text-sm text-[#D1D1D1]">
                      Combos usam as regras que você cadastrou no OmniRoute.
                    </Dialog.Description>
                    <label htmlFor={`${id}-search`} className="mb-1 text-sm">
                      Buscar pelo nome
                    </label>
                    <input
                      id={`${id}-search`}
                      className={field}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                    <p role="status" className="py-2 text-sm text-[#D1D1D1]">
                      Mostrando {Math.min(30, matches.length)} de {matches.length}
                    </p>
                    <div className="min-h-0 overflow-y-auto">
                      {matches.slice(0, 30).map((t) => (
                        <button
                          type="button"
                          key={`${t.target_kind}:${t.id}`}
                          disabled={t.compatibility === 'unsupported'}
                          className="mb-1 min-h-11 w-full rounded border border-[#666] px-3 py-2 text-left text-sm disabled:opacity-60"
                          onClick={() => {
                            update({ ...value, target_kind: t.target_kind, target_ref: t.name });
                            setOpen(false);
                          }}
                        >
                          <span className="block break-words font-medium">{t.name}</span>
                          <span className="block text-xs text-[#D1D1D1]">
                            {t.target_kind === 'combo' ? 'Combo' : 'Modelo'}
                            {t.reason ? ` · ${t.reason}` : ''}
                          </span>
                        </button>
                      ))}
                      {!matches.length && (
                        <p className="py-3 text-sm">
                          Nenhum resultado. Atualize a conexão ou ajuste a busca.
                        </p>
                      )}
                    </div>
                    <Dialog.Close className="mt-3 min-h-11 rounded border border-[#666] px-3">
                      Fechar
                    </Dialog.Close>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
            </>
          )}
        </div>
      </div>
      {value.connection_mode === 'omniroute' && (
        <div className="space-y-2 text-sm text-[#D1D1D1]">
          <p role="status">
            {query.isFetching
              ? 'Consultando o OmniRoute…'
              : query.isError
                ? 'Não foi possível consultar a conexão.'
                : (statusLabels[catalog?.status ?? ''] ?? 'Aguardando conexão.')}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="min-h-11 rounded border border-[#666] px-3"
              disabled={query.isFetching || testing}
              onClick={() => {
                setError(null);
                void client
                  .request<Catalog>(
                    `/v1/control-plane/omniroute/combos?executor=${value.executor}&refresh=true`,
                  )
                  .then((data) => {
                    queryClient.setQueryData(key, data);
                    void queryClient.invalidateQueries({ queryKey: selectionKey });
                  })
                  .catch(() => setError('Não foi possível atualizar a conexão.'));
              }}
            >
              Atualizar combos
            </button>
            {value.target_ref && !verified && (
              <button
                type="button"
                className="min-h-11 rounded border border-[#666] px-3"
                disabled={
                  testing ||
                  disabled ||
                  catalog?.status !== 'connected' ||
                  selected?.compatibility === 'unsupported'
                }
                onClick={() => void test()}
                aria-busy={testing}
              >
                {testing ? 'Testando ferramentas e continuidade…' : 'Testar combinação'}
              </button>
            )}
          </div>
          {testing && (
            <p role="status">
              O agente vai ler e editar arquivos de teste isolados. Isso usa o modelo escolhido e
              pode levar cerca de um minuto.
            </p>
          )}
          {value.target_ref && !ready && !testing && (
            <p>
              Antes do primeiro envio, teste se esta combinação consegue usar arquivos e manter o
              contexto.
            </p>
          )}
          {description.isError && (
            <p role="alert">
              {description.error instanceof Error
                ? description.error.message
                : 'Não foi possível validar a seleção.'}
            </p>
          )}
          {verified && (
            <p>
              Combinação verificada. Fallbacks ainda não acionados não foram testados
              individualmente.
            </p>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-[#FCA5A5]">
          {error}
        </p>
      )}
    </div>
  );
}
