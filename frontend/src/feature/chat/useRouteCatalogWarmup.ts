import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ConversationRoute } from './conversationTypes';

/** Read-only warmup uses the picker's cache; it never certifies a route or invokes a model. */
export function useRouteCatalogWarmup(route?: ConversationRoute) {
  const query = useQueryClient();
  const client = useControlPlaneClient();
  const executor = route?.executor;
  const mode = route?.connection_mode;
  useEffect(() => {
    if (mode !== 'omniroute' || !executor) return;
    void query.prefetchQuery({
      queryKey: ['conversation-route-catalog', executor, mode],
      queryFn: ({ signal }) =>
        client.request(
          `/v1/control-plane/omniroute/combos?executor=${executor}&connection_mode=${mode}&include_models=false`,
          { signal },
        ),
      staleTime: 30000,
      retry: false,
    });
  }, [query, client, executor, mode]);
}
