import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { trackingApi } from '../api/tracking';
import { queryKeys } from './queryKeys';

const HEARTBEAT_MS = 60_000;
const VISIT_EVENTS = ['pointerdown', 'keydown', 'focus'];

/** When the engineer last visited the app: a click, a key press or switching to its tab. */
let lastVisit = null;

function noteVisit() {
  if (document.visibilityState === 'visible') lastVisit = new Date().toISOString();
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') noteVisit();
}

/**
 * The engineer's Login/Logout state, kept alive by a heartbeat every minute.
 *
 * Mounted app-wide for engineers, so the heartbeat runs on every page and in
 * background tabs. The server counts Logout − Login; when the heartbeats stop
 * (laptop off), it pauses the time and resumes the session on the next one,
 * which also fires as soon as the window regains focus or the network returns.
 * Each heartbeat carries the engineer's last visit: past 8 h in a day, thirty
 * minutes without one logs them out on the server (at that last visit).
 */
export function useTrackingState({ enabled = true } = {}) {
  useEffect(() => {
    if (!enabled) return undefined;
    noteVisit();
    VISIT_EVENTS.forEach((event) => window.addEventListener(event, noteVisit, { passive: true }));
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      VISIT_EVENTS.forEach((event) => window.removeEventListener(event, noteVisit));
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [enabled]);

  return useQuery({
    queryKey: queryKeys.tracking,
    queryFn: () => trackingApi.heartbeat(lastVisit),
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
