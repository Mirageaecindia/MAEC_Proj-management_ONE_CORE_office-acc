import { api } from './client';

export const notificationsApi = {
  list: () => api.get('/api/notifications'),
  markRead: (notificationId) => api.post(`/api/notifications/${notificationId}/read`),
};
