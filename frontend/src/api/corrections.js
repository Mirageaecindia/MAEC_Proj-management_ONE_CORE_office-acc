import { api } from './client';

/**
 * Corrections: an engineer asks to move hours of one day from one of their subtasks to
 * another on the same project; the target task's reviewer decides.
 */
export const correctionsApi = {
  list: (projectId) => api.get(`/api/projects/${projectId}/hours-corrections`),
  /** `body`: { work_date, from_task_id, to_task_id, hours, note } */
  propose: (projectId, body) => api.post(`/api/projects/${projectId}/hours-corrections`, body),
  /** `action`: 'approve' | 'reject' | 'cancel' */
  decide: (correctionId, action, reason = null) =>
    api.post(`/api/hours-corrections/${correctionId}/${action}`, { reason }),
};
