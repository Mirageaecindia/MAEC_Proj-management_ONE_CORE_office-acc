import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { peopleApi } from '../api/people';
import { queryKeys } from './queryKeys';

/** Everyone with a profile (BU Head). */
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

/** Import engineers' profiles from the HR export (no passwords: they sign in at MAEC One). */
export function useImportPeople() {
  return usePeopleMutation(peopleApi.import);
}

/** One profile, for someone with a seat in MAEC One and none here yet. */
export function useAddPerson() {
  return usePeopleMutation(peopleApi.add);
}

/** `{ id, full_name, job_role }` */
export function useUpdatePerson() {
  return usePeopleMutation(({ id, ...fields }) => peopleApi.update(id, fields));
}

/** `{ id, makeBuHead }`, once the BU Head confirmed it. */
export function useChangeRole() {
  return usePeopleMutation(({ id, makeBuHead }) => peopleApi.changeRole(id, makeBuHead));
}
