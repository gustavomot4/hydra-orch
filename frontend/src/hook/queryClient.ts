import { QueryClient } from '@tanstack/react-query';
import { ControlPlaneApiError } from '@/type/controlPlane';

export function createHydraQueryClient(): QueryClient {
  return new QueryClient({
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
}
