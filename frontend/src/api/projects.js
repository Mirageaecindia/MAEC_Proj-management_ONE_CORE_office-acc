import { api } from './client';

export const projectsApi = {
  list: () => api.get('/api/projects'),
  get: (projectId) => api.get(`/api/projects/${projectId}`),
  create: (payload) => api.post('/api/projects', payload),
  remove: (projectId) => api.delete(`/api/projects/${projectId}`),
  leads: (discipline) => api.get(`/api/project-leads?discipline=${encodeURIComponent(discipline)}`),
};
