import { api } from './client';

/** `?a=1&b=2` from the filters that are set. */
function query(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value !== null && value !== undefined) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

/** The audit log: your own activity, or everyone's for the BU Head. */
export const auditApi = {
  mine: (filters) => api.get(`/api/audit/mine${query(filters)}`),
  everyone: (filters) => api.get(`/api/audit${query(filters)}`),
  /** The filtered entries as CSV text (BU Head). */
  exportCsv: (filters) =>
    api.get(`/api/audit/export${query({ ...filters, limit: undefined, offset: undefined })}`),
};
