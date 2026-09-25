/** Every query key in one place, so invalidation always targets the right cache entries. */
export const queryKeys = {
  projects: ['projects'],
  projectLeads: (discipline) => ['project-leads', discipline],
  executiveDashboard: (projectId) => ['executive-dashboard', projectId],
  workSummary: (projectId) => ['work-summary', projectId],
  notifications: ['notifications'],
  sharepointMirror: (projectId) => ['sharepoint-mirror', projectId],
};
