import { api } from './client';

/** People (BU Head): profiles in this app. Signing in, passwords and access (a seat,
 *  deactivating a leaver) are managed in MAEC One. */
export const peopleApi = {
  /** Everyone with a profile: `[{ id, username, full_name, role, employee_code, job_role, is_active,
   *  can_edit, can_make_bu_head, can_remove_bu_head }]`. */
  list: () => api.get('/api/people'),
  /** The HR export as a file: `{ created: [{ username, full_name, employee_code }], skipped }`. */
  import: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/api/people/import', form);
  },
  /** One person: `{ employee_code, full_name, email, job_role }` -> `{ username, full_name, employee_code }`. */
  add: (person) => api.post('/api/people', person),
  /** Only the fields given change: `{ full_name, job_role }`. Never the email: it is who they are in MAEC One. */
  update: (id, fields) => api.patch(`/api/people/${id}`, fields),
  /** `makeBuHead`: promote (true) or take the role back (false), after the BU Head confirmed it. */
  changeRole: (id, makeBuHead) =>
    api.post(`/api/people/${id}/${makeBuHead ? 'make-bu-head' : 'remove-bu-head'}`, { confirm: true }),
};
