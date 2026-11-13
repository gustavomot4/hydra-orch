import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '@/store/authStore';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { BootstrapData, ControlPlaneApiError } from '@/type/controlPlane';

export function useBootstrap() {
  const token = useAuthStore((state) => state.token);
  const client = useControlPlaneClient();

  return useQuery<BootstrapData, ControlPlaneApiError>({
    queryKey: ['control-plane', 'bootstrap', token ? 'authenticated' : 'locked'],
    queryFn: () => client.getBootstrap(),
    enabled: Boolean(token),
    retry: (failureCount, error) => {
      if (error instanceof ControlPlaneApiError && (error.status === 401 || error.status === 403)) {
        return false;
      }
      return failureCount < 1;
    },
    staleTime: 30_000,
  });
}
