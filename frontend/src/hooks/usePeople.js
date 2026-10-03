import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { peopleApi } from '../api/people';
import { queryKeys } from './queryKeys';

/** Everyone with an account (BU Head). */
export function usePeople() {
  return useQuery({ queryKey: queryKeys.people, queryFn: peopleApi.list });
}

/** A change to people: the list is fetched again afterwards. */
function usePeopleMutation(mutationFn) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.people }),
  });
}

/** Import engineers from the HR export; the result holds the temporary passwords, once. */
export function useImportPeople() {
  return usePeopleMutation(peopleApi.import);
}

/** A new temporary password for an engineer who forgot theirs. */
export function useResetPassword() {
  return usePeopleMutation(peopleApi.resetPassword);
}

/** `{ id, full_name, username, job_role }` */
export function useUpdatePerson() {
  return usePeopleMutation(({ id, ...fields }) => peopleApi.update(id, fields));
}

/** `{ id, active }` */
export function useSetPersonActive() {
  return usePeopleMutation(({ id, active }) => peopleApi.setActive(id, active));
}

export function useDeletePerson() {
  return usePeopleMutation(peopleApi.remove);
}

/** `{ id, makeBuHead, password }` */
export function useChangeRole() {
  return usePeopleMutation(({ id, makeBuHead, password }) => peopleApi.changeRole(id, makeBuHead, password));
}
