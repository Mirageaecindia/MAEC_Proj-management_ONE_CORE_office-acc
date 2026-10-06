import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { teamMembersApi } from '../api/teamMembers';
import { queryKeys } from './queryKeys';

/** Employee ids in the lead's team for the project (leads only). */
export function useTeamMembers(projectId, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.teamMembers(projectId),
    queryFn: async () => (await teamMembersApi.get(projectId)).employee_ids,
    enabled: Boolean(projectId) && enabled,
  });
}

/** Save the team: `employeeIds` replaces it. */
export function useSaveTeamMembers(projectId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (employeeIds) => teamMembersApi.replace(projectId, employeeIds),
    onSuccess: (saved) => queryClient.setQueryData(queryKeys.teamMembers(projectId), saved.employee_ids),
  });
}
