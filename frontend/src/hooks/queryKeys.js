/** Every query key in one place, so invalidation always targets the right cache entries. */
export const queryKeys = {
  projects: ['projects'], // prefix: invalidates every project list and project
  projectList: (includeArchived) => ['projects', 'list', { includeArchived }],
  project: (projectId) => ['projects', 'detail', String(projectId)],
  projectLeads: ['project-leads'],
  executiveDashboard: (projectId) => ['executive-dashboard', projectId],
  workSummary: (projectId) => ['work-summary', projectId],
  notifications: ['notifications'],
  tracking: ['tracking'],
  people: ['people'],
  serverDate: ['server-date'],
  rejectedHours: (projectId) => ['rejected-hours', String(projectId)],
  teamMembers: (projectId) => ['team-members', String(projectId)],
  sharepointMirror: (projectId) => ['sharepoint-mirror', projectId],
};
