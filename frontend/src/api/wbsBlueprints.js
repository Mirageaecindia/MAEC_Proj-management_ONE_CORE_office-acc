import { api } from './client';

/** The five phases' standard tasks, added to a project from WBS Structure's phase cards. */
export const wbsBlueprintsApi = {
  list: () => api.get('/api/wbs-blueprints'),
  add: (projectId, key) => api.post(`/api/projects/${projectId}/wbs-blueprints/${key}`),
};
