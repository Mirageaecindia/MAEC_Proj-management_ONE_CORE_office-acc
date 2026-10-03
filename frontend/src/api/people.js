import { api } from './client';

/** Onboarding (BU Head), until the company's global admin application takes it over. */
export const peopleApi = {
  /** The HR export as a file: `{ created: [{ username, full_name, employee_code, temporary_password }], skipped }`. */
  import: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/api/people/import', form);
  },
  /** `{ username, full_name, temporary_password }` */
  resetPassword: (username) => api.post('/api/people/reset-password', { username }),
};
