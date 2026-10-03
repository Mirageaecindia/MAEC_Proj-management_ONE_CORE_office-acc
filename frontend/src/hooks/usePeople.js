import { useMutation } from '@tanstack/react-query';
import { peopleApi } from '../api/people';

/** Import engineers from the HR export; the result holds the temporary passwords, once. */
export function useImportPeople() {
  return useMutation({ mutationFn: peopleApi.import });
}

/** A new temporary password for an engineer who forgot theirs. */
export function useResetPassword() {
  return useMutation({ mutationFn: peopleApi.resetPassword });
}
