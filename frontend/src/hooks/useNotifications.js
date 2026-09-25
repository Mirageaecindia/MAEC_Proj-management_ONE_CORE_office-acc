import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationsApi } from '../api/notifications';
import { queryKeys } from './queryKeys';

const POLL_MS = 60_000;

/** The signed-in user's notifications (personal + role-wide), refreshed every minute. */
export function useNotifications({ enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.notifications,
    queryFn: notificationsApi.list,
    enabled,
    refetchInterval: POLL_MS,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: notificationsApi.markRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });
}
