import { api } from './client';

export const projectsApi = {
  list: ({ includeArchived = false } = {}) =>
    api.get(`/api/projects${includeArchived ? '?include_archived=true' : ''}`),
  get: (projectId) => api.get(`/api/projects/${projectId}`),
  create: (payload) => api.post('/api/projects', payload),
  update: (projectId, payload) => api.put(`/api/projects/${projectId}`, payload),
  remove: (projectId) => api.delete(`/api/projects/${projectId}`),
  archive: (projectId, comments) => api.post(`/api/projects/${projectId}/archive`, { comments }),
  unarchive: (projectId, comments) => api.post(`/api/projects/${projectId}/unarchive`, { comments }),
  leads: () => api.get('/api/project-leads'),
};
