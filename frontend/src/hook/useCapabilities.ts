import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '@/store/authStore';
import { useBootstrap } from '@/hook/useBootstrap';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  CapabilitiesEndpointResponse,
  ControlPlaneApiError,
  HostCapabilitiesMap,
  HostEntry,
} from '@/type/controlPlane';

export type CapabilityKey = keyof HostCapabilitiesMap;

export interface ResolvedCapability {
  status: 'available' | 'degraded' | 'unavailable';
  supported: boolean;
  certified: boolean;
  reason: string | null;
  detail?: Record<string, unknown>;
}

export function useCapabilities() {
  const token = useAuthStore((state) => state.token);
  const client = useControlPlaneClient();
  const bootstrapQuery = useBootstrap();

  const capabilitiesQuery = useQuery<CapabilitiesEndpointResponse, ControlPlaneApiError>({
    queryKey: ['control-plane', 'capabilities'],
    queryFn: () => client.getCapabilities(),
    enabled: Boolean(token),
    staleTime: 30_000,
    retry: false,
  });

  const hostCapabilities =
    capabilitiesQuery.data?.host_capabilities ?? bootstrapQuery.data?.capabilities ?? null;

  const hosts = useMemo<HostEntry[]>(() => {
    if (!hostCapabilities?.hosts) {
      return [];
    }
    return Object.values(hostCapabilities.hosts);
  }, [hostCapabilities]);

  const getHostCapability = (hostId: string, capability: CapabilityKey): ResolvedCapability => {
    const entry = hostCapabilities?.hosts?.[hostId] ?? hostCapabilities?.hosts?.['local'];
    const cap = entry?.capabilities?.[capability];
    if (!cap) {
      return {
        status: 'unavailable',
        supported: false,
        certified: false,
        reason: 'capability_unknown',
      };
    }
    return {
      status: cap.status,
      supported: cap.supported,
      certified: cap.certified,
      reason: 'reason' in cap && cap.reason ? cap.reason : null,
      detail: cap as unknown as Record<string, unknown>,
    };
  };

  return {
    ...capabilitiesQuery,
    hostCapabilities,
    hosts,
    agents: capabilitiesQuery.data?.agents ?? [],
    drivers: capabilitiesQuery.data?.drivers ?? [],
    getHostCapability,
  };
}
