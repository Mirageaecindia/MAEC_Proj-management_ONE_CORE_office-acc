import { api } from './client';

/** The five phases' standard tasks, added to a project from WBS Structure's phase cards. */
export const wbsBlueprintsApi = {
  list: () => api.get('/api/wbs-blueprints'),
  /** How much of the blueprint is already in the project. */
  preview: (projectId, key) => api.get(`/api/projects/${projectId}/wbs-blueprints/${key}`),
  /** `again`: a full second copy instead of only what is missing. */
  add: (projectId, key, again = false) =>
    api.post(`/api/projects/${projectId}/wbs-blueprints/${key}${again ? '?again=true' : ''}`),
};
