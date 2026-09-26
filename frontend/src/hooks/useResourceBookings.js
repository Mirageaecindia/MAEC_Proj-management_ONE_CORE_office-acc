import { useMutation } from '@tanstack/react-query';
import { resourceBookingsApi } from '../api/resourceBookings';

/** BU Head sends a pending booking submission back to the Lead, with a reason. */
export function useRejectResourceBookings() {
  return useMutation({
    mutationFn: ({ projectId, reason }) => resourceBookingsApi.reject(projectId, reason),
  });
}
