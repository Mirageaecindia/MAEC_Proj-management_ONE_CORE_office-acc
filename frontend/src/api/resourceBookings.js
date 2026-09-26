import { api } from './client';

export const resourceBookingsApi = {
  reject: (projectId, reason) => api.post(`/api/projects/${projectId}/resource-bookings/reject`, { reason }),
};
