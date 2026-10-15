import { api } from './client';

/** Project estimation (BU Head): resourcing estimates made before a project exists, saved by name. */
export const estimationsApi = {
  codes: () => api.get('/api/estimations/codes'),
  list: () => api.get('/api/estimations'),
  get: (estimationId) => api.get(`/api/estimations/${estimationId}`),
  create: (payload) => api.post('/api/estimations', payload),
  update: (estimationId, payload) => api.put(`/api/estimations/${estimationId}`, payload),
  remove: (estimationId) => api.delete(`/api/estimations/${estimationId}`),
};
