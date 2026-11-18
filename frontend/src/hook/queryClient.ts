import { QueryClient } from '@tanstack/react-query';
import { ControlPlaneApiError } from '@/type/controlPlane';

const registeredClients = new Set<QueryClient>();

export function createHydraQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if (
            error instanceof ControlPlaneApiError &&
            (error.status === 401 || error.status === 403 || error.status === 404)
          ) {
            return false;
          }
          return failureCount < 1;
        },
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
  registeredClients.add(client);
  return client;
}

export const hydraQueryClient: QueryClient = createHydraQueryClient();

export function clearHydraQueryClients(): void {
  hydraQueryClient.clear();
  for (const client of registeredClients) {
    client.clear();
  }
}
