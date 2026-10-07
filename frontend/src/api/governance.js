import { api } from './client';

export const governanceApi = {
  executiveDashboard: (projectId) => api.get(`/api/projects/${projectId}/executive-dashboard`),
  workSummary: (projectId) => api.get(`/api/projects/${projectId}/work-summary`),
  /** A lead asks the BU Head for more hours on the project. */
  requestExtension: (projectId, { requestedHours, justification }) =>
    api.post(`/api/projects/${projectId}/extension-requests`, {
      requested_hours: requestedHours,
      justification: justification || null,
    }),
  decideExtension: (projectId, requestId, { decision, comments }) =>
    api.post(`/api/projects/${projectId}/extension-requests/${requestId}/decision`, { decision, comments }),
  stopExecution: (projectId, { comments, discipline }) =>
    api.post(`/api/projects/${projectId}/governance/stop-execution`, { comments, discipline }),
  resumeExecution: (projectId, { comments }) =>
    api.post(`/api/projects/${projectId}/governance/resume-execution`, { comments }),
};
