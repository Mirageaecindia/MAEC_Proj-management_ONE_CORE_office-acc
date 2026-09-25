import { api } from './client';

export const governanceApi = {
  executiveDashboard: (projectId) => api.get(`/api/projects/${projectId}/executive-dashboard`),
  workSummary: (projectId) => api.get(`/api/projects/${projectId}/work-summary`),
  decideExtension: (projectId, requestId, { decision, comments }) =>
    api.post(`/api/projects/${projectId}/extension-requests/${requestId}/decision`, { decision, comments }),
  stopExecution: (projectId, { comments, discipline }) =>
    api.post(`/api/projects/${projectId}/governance/stop-execution`, { comments, discipline }),
  resumeExecution: (projectId, { comments }) =>
    api.post(`/api/projects/${projectId}/governance/resume-execution`, { comments }),
};
