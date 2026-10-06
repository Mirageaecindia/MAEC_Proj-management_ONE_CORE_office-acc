import { api } from './client';

/** A lead's team on a project: the people Assign Engineer offers. */
export const teamMembersApi = {
  get: (projectId) => api.get(`/api/projects/${projectId}/team-members`),
  /** The team becomes exactly `employeeIds`. */
  replace: (projectId, employeeIds) =>
    api.put(`/api/projects/${projectId}/team-members`, { employee_ids: employeeIds }),
};
