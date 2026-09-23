import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';
import { queryKeys } from './queryKeys';

export const LEAD_DISCIPLINES = ['electrical', 'mechanical', 'bim'];

/** Projects visible to the signed-in user. */
export function useProjects() {
  return useQuery({ queryKey: queryKeys.projects, queryFn: projectsApi.list });
}

/** Lead accounts per discipline for the Create Project dropdowns: { electrical: [...], ... }. */
export function useProjectLeads() {
  return useQueries({
    queries: LEAD_DISCIPLINES.map((discipline) => ({
      queryKey: queryKeys.projectLeads(discipline),
      queryFn: () => projectsApi.leads(discipline),
      staleTime: 5 * 60_000,
    })),
    combine: (results) => ({
      leads: Object.fromEntries(LEAD_DISCIPLINES.map((discipline, i) => [discipline, results[i].data ?? []])),
      error: results.find((result) => result.error)?.error ?? null,
      isLoading: results.some((result) => result.isLoading),
    }),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: projectsApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: projectsApi.remove,
    onSuccess: (_result, projectId) => {
      queryClient.setQueryData(queryKeys.projects, (projects = []) =>
        projects.filter((p) => p.id !== projectId),
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
}
