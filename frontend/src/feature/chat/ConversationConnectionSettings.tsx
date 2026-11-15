import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { clearPendingSend, pendingSendKey } from './conversationTypes';

interface Settings {
  base_url: string;
  enabled: boolean;
  credential_available: boolean;
  credential_env: string;
  version: number;
}
export function ConversationConnectionSettings() {
  const client = useControlPlaneClient();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['conversation-connection'],
    queryFn: () => client.request<Settings>('/v1/control-plane/conversation-routes/connection'),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const [url, setUrl] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [testing, setTesting] = useState(false);
  useEffect(() => {
    if (query.data) {
      setUrl(query.data.base_url);
      setEnabled(query.data.enabled);
    }
  }, [query.data]);
  async function save() {
    if (!query.data || saving) return;
    setSaving(true);
    setFeedback('');
    const body = { base_url: url, enabled, expected_version: query.data.version };
    try {
      await client.request('/v1/control-plane/conversation-routes/connection', {
        method: 'PUT',
        body: { ...body, idempotency_key: pendingSendKey('omniroute-settings', body) },
      });
      clearPendingSend('omniroute-settings');
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ['conversation-route-catalog'] });
      await queryClient.invalidateQueries({ queryKey: ['conversation-route-description'] });
      await queryClient.invalidateQueries({ queryKey: ['control-plane', 'omniroute-inventory'] });
      setFeedback('Configuração salva. Conversas existentes mantêm a configuração de cada envio.');
    } catch (e) {
      setFeedback(e instanceof Error ? e.message : 'Não foi possível salvar.');
    } finally {
      setSaving(false);
    }
  }
  async function test() {
    setTesting(true);
    setFeedback('');
    try {
      const data = await client.request<{ status: string; combos: unknown[] }>(
        '/v1/control-plane/omniroute/combos?refresh=true',
      );
      setFeedback(
        data.status === 'connected'
          ? `Conexão confirmada. ${data.combos.length} combos encontrados. Nenhum pedido foi enviado a um modelo.`
          : `Conexão não disponível (${data.status}). Confira o endereço, o serviço e a credencial.`,
      );
    } catch (e) {
      setFeedback(e instanceof Error ? e.message : 'Não foi possível testar a conexão.');
    } finally {
      setTesting(false);
    }
  }
  return (
    <section
      aria-labelledby="omniroute-settings-title"
      className="rounded-xl border border-[#666] bg-[#202020] p-5"
    >
      <h2 id="omniroute-settings-title" className="text-lg font-semibold">
        Conexão OmniRoute
      </h2>
      <p className="mt-2 text-sm text-[#D1D1D1]">
        Conecte seus modelos e combos. A escolha de qual usar fica no Novo chat e no cabeçalho da
        conversa.
      </p>
      {query.isError ? (
        <p role="alert" className="mt-3 text-sm">
          Não foi possível carregar.{' '}
          <button className="min-h-11 underline" onClick={() => void query.refetch()}>
            Tentar de novo
          </button>
        </p>
      ) : query.isLoading ? (
        <p role="status" className="mt-3">
          Carregando conexão…
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-8 w-8 shrink-0"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Habilitar conexão OmniRoute
          </label>
          <label className="block text-sm" htmlFor="omniroute-url">
            Endereço da API
          </label>
          <input
            id="omniroute-url"
            type="url"
            className="min-h-11 w-full rounded border border-[#666] bg-[#1C1C1C] px-3 text-sm"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <p className="text-sm text-[#D1D1D1]">
            {query.data?.credential_available
              ? 'Credencial disponível no backend. Você não precisa colá-la aqui.'
              : `Credencial ausente. Configure ${query.data?.credential_env ?? 'OMNIROUTE_API_KEY'} no ambiente do backend e reinicie o Hydra.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              className="min-h-11 rounded border border-[#666] px-3 text-sm"
              disabled={saving}
              onClick={() => void save()}
            >
              {saving ? 'Salvando…' : 'Salvar conexão'}
            </button>
            <button
              className="min-h-11 rounded border border-[#666] px-3 text-sm"
              disabled={testing || saving}
              onClick={() => void test()}
            >
              {testing ? 'Consultando…' : 'Testar conexão salva'}
            </button>
            <Link
              to="/"
              className="flex min-h-11 items-center rounded border border-[#666] px-3 text-sm"
            >
              Abrir Novo chat
            </Link>
          </div>
        </div>
      )}
      {feedback && (
        <p role="status" className="mt-3 text-sm text-[#D1D1D1]">
          {feedback}
        </p>
      )}
    </section>
  );
}
