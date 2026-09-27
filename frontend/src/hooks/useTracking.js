import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { trackingApi } from '../api/tracking';
import { queryKeys } from './queryKeys';

const HEARTBEAT_MS = 60_000;

/**
 * The engineer's Login/Logout state, kept alive by a heartbeat every minute.
 *
 * Mounted app-wide for engineers, so the heartbeat runs on every page and in
 * background tabs. The server counts Logout − Login; when the heartbeats stop
 * (laptop off), it pauses the time and resumes the session on the next one,
 * which also fires as soon as the window regains focus or the network returns.
 */
export function useTrackingState({ enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.tracking,
    queryFn: trackingApi.heartbeat,
    enabled,
    refetchInterval: HEARTBEAT_MS,
    refetchIntervalInBackground: true,
  });
}

function useTrackingMutation(mutationFn) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    // A heartbeat still in flight would otherwise overwrite the new state with the old one.
    onMutate: () => queryClient.cancelQueries({ queryKey: queryKeys.tracking }),
    onSuccess: (state) => queryClient.setQueryData(queryKeys.tracking, state),
  });
}

export function useStartTracking() {
  return useTrackingMutation(trackingApi.start);
}

export function useLogoutTracking() {
  return useTrackingMutation(trackingApi.logout);
}
