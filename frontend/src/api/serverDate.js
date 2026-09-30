import { api } from './client';

/** The server's current day (UTC): `{ date: 'YYYY-MM-DD', datetime, timezone }`. */
export const serverDateApi = {
  get: () => api.get('/api/server-date'),
};
