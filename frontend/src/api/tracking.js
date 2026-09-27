import { api } from './client';

/** Subtask Login/Logout. Each call returns `{ active_session }`: the subtask the engineer is logged in to, or null. */
export const trackingApi = {
  heartbeat: () => api.post('/api/subtask-tracking/heartbeat'),
  start: (subtaskId) => api.post('/api/subtask-tracking/start', { subtask_id: subtaskId }),
  logout: () => api.post('/api/subtask-tracking/logout'),
};
