import { api } from './client';

/** People (BU Head), until the company's global admin application takes it over. */
export const peopleApi = {
  /** Everyone with an account: `[{ id, username, full_name, role, employee_code, job_role, is_active,
   *  must_change_password, can_edit, can_delete }]`. Never passwords. */
  list: () => api.get('/api/people'),
  /** The HR export as a file: `{ created: [{ username, full_name, employee_code, temporary_password }], skipped }`. */
  import: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/api/people/import', form);
  },
  /** `{ username, full_name, temporary_password }` */
  resetPassword: (username) => api.post('/api/people/reset-password', { username }),
  /** Only the fields given change: `{ full_name, username, job_role }`. */
  update: (id, fields) => api.patch(`/api/people/${id}`, fields),
  setActive: (id, active) => api.post(`/api/people/${id}/${active ? 'reactivate' : 'deactivate'}`),
  remove: (id) => api.delete(`/api/people/${id}`),
  /** `makeBuHead`: promote (true) or take the role back (false); confirmed with the BU Head's own password. */
  changeRole: (id, makeBuHead, password) =>
    api.post(`/api/people/${id}/${makeBuHead ? 'make-bu-head' : 'remove-bu-head'}`, { password }),
};
