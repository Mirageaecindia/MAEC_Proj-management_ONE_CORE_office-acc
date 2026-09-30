import { api } from './client';

/** Rejected hours a project's leads and the BU Head may approve again within seven days. */
export const rejectedHoursApi = {
  list: (projectId) => api.get(`/api/projects/${projectId}/rejected-hours`),
  /** `attendedOnly`: approve an unattended day only up to the engineer's last visit. */
  reapprove: (entryId, reason, attendedOnly = false) =>
    api.post(`/api/time-log-entries/${entryId}/reapprove`, { reason, attended_only: attendedOnly }),
};
