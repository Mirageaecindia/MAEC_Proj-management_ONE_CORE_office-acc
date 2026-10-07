import { api } from './client';

/** The signed-in person's own work on a project: their tasks, their hours, their plan. */
export const performanceApi = {
  mine: (projectId) => api.get(`/api/engineer-performance-dashboard?project_id=${projectId}`),
};
