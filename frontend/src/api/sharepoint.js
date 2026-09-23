import { api } from './client';

export const sharepointApi = {
  mirror: (projectId) => api.get(`/api/projects/${projectId}/sharepoint-mirror`),
};
