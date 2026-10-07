import { useQuery } from '@tanstack/react-query';
import { performanceApi } from '../api/performance';
import { queryKeys } from './queryKeys';

/** The signed-in person's own work on the project; refreshed when they come back to the tab. */
export function useMyPerformance(projectId) {
  return useQuery({
    queryKey: queryKeys.myPerformance(projectId),
    queryFn: () => performanceApi.mine(projectId),
    enabled: Boolean(projectId),
    refetchOnWindowFocus: true,
    refetchInterval: 60_000,
  });
}
