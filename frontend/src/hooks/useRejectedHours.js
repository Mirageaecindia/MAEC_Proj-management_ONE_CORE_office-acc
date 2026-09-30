import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { rejectedHoursApi } from '../api/rejectedHours';
import { queryKeys } from './queryKeys';

/** A project's rejected hours that can still be approved again (leads and the BU Head). */
export function useRejectedHours(projectId, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.rejectedHours(projectId),
    queryFn: () => rejectedHoursApi.list(projectId),
    enabled: Boolean(projectId) && enabled,
  });
}

/** Approve rejected hours again: `{ id, reason, attendedOnly }`. */
export function useReapproveHours(projectId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason, attendedOnly }) => rejectedHoursApi.reapprove(id, reason, attendedOnly),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.rejectedHours(projectId) }),
  });
}
