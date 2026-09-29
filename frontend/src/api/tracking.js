import { api } from './client';

/**
 * Subtask Login/Logout. Each call returns `{ active_session }`: the subtask the engineer is
 * logged in to, or null. The heartbeat also reports the engineer's last visit to the app
 * (`lastActiveAt`, ISO) and returns `over_mark` (past 8 h today) and `system_logout`.
 */
export const trackingApi = {
  heartbeat: (lastActiveAt = null) =>
    api.post('/api/subtask-tracking/heartbeat', { last_active_at: lastActiveAt }),
  start: (subtaskId) => api.post('/api/subtask-tracking/start', { subtask_id: subtaskId }),
  logout: () => api.post('/api/subtask-tracking/logout'),
};
